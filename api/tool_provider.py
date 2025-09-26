"""
工具提供者服务 - 为 Agent 运行时提供动态工具列表

此模块负责：
1. 根据会话ID和场景动态加载工具
2. 为 PydanticAI Agent 提供工具对象列表  
3. 管理工具的分类、权限和可用性

这是 AGENT_DEV_PLAN.md 阶段2任务4的核心实现
"""

import logging
import importlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from sqlmodel import Session, select
from sqlalchemy import Engine
from db_mgr import ChatSession, Tool, Scenario, ToolType
from backend_tool_caller import g_backend_tool_caller
from utils import update_json_field_safely

logger = logging.getLogger()

class ToolProvider:
    """工具提供者 - 负责为不同会话和场景提供相应的工具集"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get_tools_for_session(self, session_id: Optional[int] = None) -> List[Callable]:
        """
        为指定会话获取工具列表
        
        这是 AGENT_DEV_PLAN.md 中要求的核心方法
        
        Args:
            session_id: 会话ID，如果为None则返回默认工具集
            
        Returns:
            可供PydanticAI Agent使用的工具函数列表
        """
        try:
            # 获取默认工具
            tools = self._get_default_tools()
            if session_id:
                # 获取会话信息
                with Session(self.engine) as session:
                    chat_session = session.get(ChatSession, session_id)
                    if chat_session:
                        # 获取用户选择的工具
                        for tool_name in chat_session.selected_tool_names:
                            tool_func = self._load_tool_function(tool_name)
                            if tool_func:
                                tools.append(tool_func)
                        
                        # 获取场景的预置工具
                        if chat_session.scenario_id:
                            tools.extend(self._get_scenario_tools(chat_session.scenario_id))
                
            return tools
        except Exception as e:
            logger.error(f"获取会话工具失败: {e}")
            return []
    
    def get_session_scenario_system_prompt(self, session_id: int) -> str | None:
        '''如果session_id对应的会话有配置场景，则返回场景的system_prompt'''
        try:
            with Session(self.engine) as session:
                chat_session = session.get(ChatSession, session_id)
                if chat_session and chat_session.scenario_id:
                    scenario = session.get(Scenario, chat_session.scenario_id)
                    if scenario:
                        return scenario.system_prompt
        except Exception as e:
            logger.error(f"获取会话 {session_id} 的场景system_prompt失败: {e}")
        return None

    def _get_scenario_tools(self, scenario_id: int) -> List[Callable]:
        """根据场景ID获取预置工具"""
        tools = []
        try:
            with Session(self.engine) as session:
                scenario = session.get(Scenario, scenario_id)
                if scenario and scenario.preset_tool_names:
                    preset_tool_names = scenario.preset_tool_names
                    for tool_name in preset_tool_names:
                        tool_func = self._load_tool_function(tool_name)
                        if tool_func:
                            tools.append(tool_func)
                
                    logger.info(f"为场景 {scenario_id} 加载了 {len(tools)} 个工具")

        except Exception as e:
            logger.error(f"加载场景工具失败: {e}")
        
        return tools
    
    def _get_default_tools(self) -> List[Callable]:
        """获取默认工具集"""
        tools = []
        
        # 默认加载的工具ID列表
        default_tool_names = [
            "get_current_time",  # 获取当前时间的工具
            # "file_search",  # 本机文件搜索工具
            # "memory_summary",  # 上下文工程(二期)：汇总会话历史记录
        ]
        
        for tool_name in default_tool_names:
            tool_func = self._load_tool_function(tool_name)
            if tool_func:
                tools.append(tool_func)
        
        logger.info(f"加载了 {len(tools)} 个默认工具")
        return tools
    
    def _load_tool_function(self, tool_name: str) -> Optional[Callable]:
        """根据工具ID动态加载工具函数"""
        try:
            # 从数据库获取工具信息
            with Session(self.engine) as session:
                tool = session.exec(
                    select(Tool).where(Tool.name == tool_name)
                ).first()

                if not tool:
                    logger.warning(f"工具 {tool_name} 在数据库中未找到")
                    return None
                
                # 根据工具类型加载函数
                if tool.tool_type == ToolType.CHANNEL:
                    # 工具通道类型 - 包装为异步调用前端的函数
                    return self._create_channel_tool_wrapper(tool)
                elif tool.tool_type == ToolType.DIRECT:
                    # 直接调用类型 - 动态导入Python函数
                    return self._import_direct_tool(tool)
                elif tool.tool_type == ToolType.MCP:
                    # MCP类型 - 返回调用器
                    return self.get_mcp_tool_caller(tool)
                else:
                    logger.warning(f"不支持的工具类型: {tool.tool_type}")
                    return None
                
        except Exception as e:
            logger.error(f"加载工具 {tool_name} 失败: {e}")
            return None
    
    def _create_channel_tool_wrapper(self, tool: Tool) -> Callable:
        """为工具通道类型的工具创建包装函数"""
        async def channel_tool_wrapper(ctx=None, **kwargs):
            """工具通道包装器 - 调用前端工具"""
            try:
                # 注意：传递给前端时不包含RunContext，只传递业务参数
                result = await g_backend_tool_caller.call_frontend_tool(
                    tool_name=tool.name,
                    timeout=30.0,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(f"工具通道调用失败 {tool.name}: {e}")
                return {"success": False, "error": str(e)}
        
        # 设置函数属性用于Agent识别
        channel_tool_wrapper.__name__ = tool.name
        
        # 尝试从原始函数定义处获取文档字符串
        original_doc = self._get_original_function_doc(tool)
        if original_doc:
            channel_tool_wrapper.__doc__ = original_doc
        else:
            # 如果无法获取原始文档，回退到使用数据库描述
            channel_tool_wrapper.__doc__ = f'{tool.description}\n'
        
        # 动态生成参数信息并附加到函数上（用于PydanticAI）
        sig_info = self._get_function_signature_info(tool)
        if sig_info:
            # 为PydanticAI提供参数信息
            channel_tool_wrapper.__annotations__ = {}
            if 'properties' in sig_info:
                for param_name in sig_info['properties']:
                    # 简单的类型映射，可以根据需要改进
                    channel_tool_wrapper.__annotations__[param_name] = str
        
        return channel_tool_wrapper
    
    def _get_original_function_doc(self, tool: Tool) -> Optional[str]:
        """从原始函数定义处获取文档字符串"""
        try:
            # 检查是否有model_path信息
            metadata = tool.metadata_json
            if not metadata or 'model_path' not in metadata:
                return None
            
            # 解析模块路径和函数名
            module_name, function_name = metadata['model_path'].split(':')
            
            # 动态导入模块
            module = importlib.import_module(module_name)
            
            # 获取函数
            if hasattr(module, function_name):
                func = getattr(module, function_name)
                if callable(func) and func.__doc__:
                    return func.__doc__
                else:
                    logger.debug(f"函数 {module_name}.{function_name} 没有文档字符串")
            else:
                logger.debug(f"模块 {module_name} 中未找到函数 {function_name}")
            
            return None
            
        except Exception as e:
            logger.debug(f"获取原始函数文档失败 {tool.name}: {e}")
            return None
    
    def _get_function_signature_info(self, tool: Tool) -> Dict[str, Any]:
        """从原始函数定义处获取参数签名信息"""
        try:
            import inspect
            
            # 检查是否有model_path信息
            metadata = tool.metadata_json
            if not metadata or 'model_path' not in metadata:
                return {}
            
            # 解析模块路径和函数名
            module_name, function_name = metadata['model_path'].split(':')
            
            # 动态导入模块
            module = importlib.import_module(module_name)
            
            # 获取函数
            if hasattr(module, function_name):
                func = getattr(module, function_name)
                if callable(func):
                    sig = inspect.signature(func)
                    params = {}
                    for param_name, param in sig.parameters.items():
                        if param_name != 'ctx':  # 排除RunContext参数
                            param_info = {
                                "type": "string",  # 默认为string，可以根据需要改进
                                "description": f"参数 {param_name}"
                            }
                            # 如果有默认值，标记为可选
                            if param.default != inspect.Parameter.empty:
                                param_info["default"] = param.default
                            params[param_name] = param_info
                    
                    return {
                        "type": "object",
                        "properties": params,
                        "required": [p for p, param in sig.parameters.items() 
                                   if p != 'ctx' and param.default == inspect.Parameter.empty]
                    }
            
            return {}
            
        except Exception as e:
            logger.debug(f"获取函数签名信息失败 {tool.name}: {e}")
            return {}
    
    def _import_direct_tool(self, tool: Tool) -> Optional[Callable]:
        """动态导入直接调用类型的工具"""
        try:
            # 解析模块路径和函数名
            # 假设 tool.metadata_json 格式为 {"model_path": "tools.calculator:add"}
            metadata = tool.metadata_json
            if 'model_path' in metadata:
                module_name, function_name = metadata['model_path'].split(':')
            else:
                return None
            
            # 动态导入模块
            module = importlib.import_module(module_name)
            
            # 获取函数
            if hasattr(module, function_name):
                func = getattr(module, function_name)
                if callable(func):
                    return func
                else:
                    logger.warning(f"{module_name}.{function_name} 不是可调用对象")
            else:
                logger.warning(f"模块 {module_name} 中未找到函数 {function_name}")
            
            return None
            
        except Exception as e:
            logger.error(f"导入工具函数失败 {tool.module_path}: {e}")
            return None
    
    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        """获取可用场景列表"""
        try:
            with Session(self.engine) as session:
                stmt = select(Scenario)
                scenarios = session.exec(stmt).all()

                return [
                    {
                        "id": scenario.id,
                        "name": scenario.name,
                        "description": scenario.description,
                        "preset_tool_count": len(scenario.preset_tool_names) if scenario.preset_tool_names else 0
                    }
                    for scenario in scenarios
                ]
            
        except Exception as e:
            logger.error(f"获取场景列表失败: {e}")
            return []
    
    def get_mcp_tool_api_key(self, tool_name: str) -> str:
        """获取MCP类型工具的api_key"""
        try:
            with Session(self.engine) as session:
                stmt = select(Tool).where(Tool.name == tool_name)
                tool = session.exec(stmt).first()
                if tool:
                    if tool.metadata_json and 'api_key' in tool.metadata_json:
                        return tool.metadata_json['api_key']  # 初始化是空字符串
                    else:
                        logger.warning(f"MCP工具 {tool_name} 未配置api_key")
                        return ""
                else:
                    logger.warning(f"MCP工具 {tool_name} 未找到")
                    return ""
        except Exception as e:
            logger.error(f"获取MCP工具api_key失败 {tool_name}: {e}")
            return ""
    
    def set_mcp_tool_api_key(self, tool_name: str, api_key: str) -> bool:
        """设置MCP类型工具的api_key"""
        try:
            with Session(self.engine) as session:
                stmt = select(Tool).where(Tool.name == tool_name)
                tool = session.exec(stmt).first()
                if tool:
                    # 使用通用方法安全更新JSON字段
                    update_json_field_safely(tool, 'metadata_json', {'api_key': api_key})
                    
                    # 更新时间戳
                    tool.updated_at = datetime.now()
                    
                    session.add(tool)
                    session.commit()
                    session.refresh(tool)
                    
                    # 验证结果
                    saved_api_key = tool.metadata_json.get('api_key', '') if tool.metadata_json else ''
                    if saved_api_key == api_key:
                        logger.info(f"设置MCP工具 {tool_name} 的api_key成功")
                        return True
                    else:
                        logger.error(f"设置MCP工具 {tool_name} 的api_key失败: 保存值不匹配")
                        return False
                else:
                    logger.warning(f"MCP工具 {tool_name} 未找到")
                    return False
        except Exception as e:
            logger.error(f"设置MCP工具api_key失败 {tool_name}: {e}", exc_info=True)
            return False
    
    def get_mcp_tool_caller(self, tool: Tool) -> Optional[Callable]:
        """获取MCP类型工具的调用器"""
        # TODO 对于非remote server的情况，需要本地先启动mcp server
        metadata = tool.metadata_json
        if 'model_path' in metadata:
            module_name, function_name = metadata['model_path'].split(':')
        else:
            return None
        
        # 动态导入模块
        module = importlib.import_module(module_name)
        
        # 获取函数
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                return func
            else:
                logger.warning(f"{module_name}.{function_name} 不是可调用对象")
        else:
            logger.warning(f"模块 {module_name} 中未找到函数 {function_name}")
        

# 测试代码
if __name__ == "__main__":
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    tool_provider = ToolProvider(engine)

    # # 获取默认工具列表
    # default_tools = tool_provider._get_default_tools()
    # print("默认工具列表:")
    # for tool in default_tools:
    #     print(f" - {tool.__name__}: {tool.__doc__}")
    
    # # 获取可用场景列表
    # scenarios = tool_provider.get_available_scenarios()
    # print("可用场景列表:")
    # for scenario in scenarios:
    #     print(f" - {scenario['name']}: {scenario['description']} (预置工具数: {scenario['preset_tool_count']})")

    # # 根据场景ID获取预置工具
    # preset_tools = tool_provider._get_scenario_tools(scenario_id=1)
    # print("场景 ID 1 对应的预置工具列表:")
    # for tool in preset_tools:
    #     print(f" - {tool.__name__}: {tool.__doc__}")
    
    # 为指定会话获取工具列表
    # tools = tool_provider.get_tools_for_session(session_id=1)
    # print("聊天会话ID对应的工具列表:")
    # for tool in tools:
    #     print(f" - {tool.__name__}: {tool.__doc__}")

    # # 获取聊天会话ID对应的场景system_prompt
    # system_prompt = tool_provider.get_session_scenario_system_prompt(session_id=1)
    # print(f"聊天会话ID对应的场景system_prompt: {system_prompt}")

    # 测试MCP工具的api_key设置和获取
    tool_name = "search_use_tavily"
    print(f"原始MCP工具 {tool_name} 的api_key:", tool_provider.get_mcp_tool_api_key(tool_name))
    success = tool_provider.set_mcp_tool_api_key(tool_name, "test_api_key_123")
    print(f"设置MCP工具 {tool_name} 的api_key结果:", success)
    print(f"更新后MCP工具 {tool_name} 的api_key:", tool_provider.get_mcp_tool_api_key(tool_name))
    