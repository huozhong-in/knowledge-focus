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
from typing import List, Dict, Any, Optional, Callable
from sqlmodel import Session, select
from db_mgr import ChatSession, Tool, Scenario
from backend_tool_caller import g_backend_tool_caller

logger = logging.getLogger(__name__)

class ToolProvider:
    """工具提供者 - 负责为不同会话和场景提供相应的工具集"""
    
    def __init__(self, session: Session):
        self.session = session
    
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
            if session_id:
                # 获取会话信息
                chat_session = self.session.get(ChatSession, session_id)
                if chat_session and chat_session.scenario_id:
                    tools = []
                    # 获取场景的预置工具
                    tools.extend(self._get_scenario_tools(chat_session.scenario_id))
                    # 获取用户为此会话选择的额外工具
                    stmt = select(ChatSession).where(
                        ChatSession.id == session_id
                    )
                    selected_tool_ids = self.session.exec(stmt).first().selected_tool_ids if self.session.exec(stmt).first() else []
                    for selected_tool_id in selected_tool_ids:
                        tool_func = self._load_tool_function(selected_tool_id)
                        if tool_func:
                            tools.append(tool_func)
                    return tools
                else:
                    logger.warning(f"会话 {session_id} 未找到或没有场景，使用默认工具集")
            
            # 返回默认工具集
            return self._get_default_tools()
            
        except Exception as e:
            logger.error(f"获取会话工具失败: {e}")
            return self._get_default_tools()
    
    def get_session_scenario_system_prompt(self, session_id: int) -> str | None:
        '''如果session_id对应的会话有配置场景，则返回场景的system_prompt'''
        try:
            chat_session = self.session.get(ChatSession, session_id)
            if chat_session and chat_session.scenario_id:
                scenario = self.session.get(Scenario, chat_session.scenario_id)
                if scenario:
                    return scenario.system_prompt
        except Exception as e:
            logger.error(f"获取会话 {session_id} 的场景system_prompt失败: {e}")
        return None

    def _get_scenario_tools(self, scenario_id: int) -> List[Callable]:
        """根据场景ID获取预置工具"""
        tools = []
        try:
            scenario = self.session.get(Scenario, scenario_id)
            if scenario and scenario.preset_tool_ids:
                preset_tool_ids = scenario.preset_tool_ids
                for tool_id in preset_tool_ids:
                    tool_func = self._load_tool_function(tool_id)
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
        default_tool_ids = [
            1, #"calculator_add",
            2, #"calculator_multiply",
            3, #"calculator_bmi",
            # 4, #"file_search",
        ]
        
        for tool_id in default_tool_ids:
            tool_func = self._load_tool_function(tool_id)
            if tool_func:
                tools.append(tool_func)
        
        logger.info(f"加载了 {len(tools)} 个默认工具")
        return tools
    
    def _load_tool_function(self, tool_id: str) -> Optional[Callable]:
        """根据工具ID动态加载工具函数"""
        try:
            # 从数据库获取工具信息
            tool = self.session.exec(
                select(Tool).where(Tool.id == tool_id)
            ).first()
            
            if not tool:
                logger.warning(f"工具 {tool_id} 在数据库中未找到")
                return None
            
            # 根据工具类型加载函数
            if tool.tool_type == "channel":
                # 工具通道类型 - 包装为异步调用前端的函数
                return self._create_channel_tool_wrapper(tool)
            elif tool.tool_type == "direct":
                # 直接调用类型 - 动态导入Python函数
                return self._import_direct_tool(tool)
            else:
                logger.warning(f"不支持的工具类型: {tool.tool_type}")
                return None
                
        except Exception as e:
            logger.error(f"加载工具 {tool_id} 失败: {e}")
            return None
    
    def _create_channel_tool_wrapper(self, tool: Tool) -> Callable:
        """为工具通道类型的工具创建包装函数"""
        async def channel_tool_wrapper(**kwargs):
            """工具通道包装器 - 调用前端工具"""
            try:
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
    
    def _import_direct_tool(self, tool: Tool) -> Optional[Callable]:
        """动态导入直接调用类型的工具"""
        try:
            # 解析模块路径和函数名
            # 假设 tool.metadata_json 格式为 {"model_path": "tools.calculator:add"}
            metadata = tool.metadata_json
            if 'model_path' in metadata:
                module_name, function_name = metadata['model_path'].split(':')
            else:
                # TODO 考虑怎么支持MCP
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
    
    # def get_tool_categories(self) -> Dict[str, List[Dict[str, Any]]]:
    #     """获取工具分类信息 - 用于前端UI展示"""
    #     try:
    #         # 获取所有工具
    #         stmt = select(Tool)
    #         tools = self.session.exec(stmt).all()
            
    #         categories = {}
    #         for tool in tools:
    #             category = tool.category or "未分类"
    #             if category not in categories:
    #                 categories[category] = []
                
    #             categories[category].append({
    #                 "id": tool.id,
    #                 "name": tool.name,
    #                 "description": tool.description,
    #                 "tool_type": tool.tool_type,
    #                 "is_preset": tool.is_preset
    #             })
            
    #         return categories
            
    #     except Exception as e:
    #         logger.error(f"获取工具分类失败: {e}")
    #         return {}
    
    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        """获取可用场景列表"""
        try:
            stmt = select(Scenario)
            scenarios = self.session.exec(stmt).all()
            
            return [
                {
                    "id": scenario.id,
                    "name": scenario.name,
                    "description": scenario.description,
                    "preset_tool_count": len(scenario.preset_tool_ids) if scenario.preset_tool_ids else 0
                }
                for scenario in scenarios
            ]
            
        except Exception as e:
            logger.error(f"获取场景列表失败: {e}")
            return []

# 测试代码
if __name__ == "__main__":
    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    tool_provider = ToolProvider(session)

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
    
    # # 为指定会话获取工具列表
    # tools = tool_provider.get_tools_for_session(session_id=1)
    # print("聊天会话ID对应的工具列表:")
    # for tool in tools:
    #     print(f" - {tool.__name__}: {tool.__doc__}")

    # 获取聊天会话ID对应的场景system_prompt
    system_prompt = tool_provider.get_session_scenario_system_prompt(session_id=1)
    print(f"聊天会话ID对应的场景system_prompt: {system_prompt}")
    