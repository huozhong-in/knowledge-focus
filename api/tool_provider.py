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
from db_mgr import ChatSession, Tool, Scenario, SessionSelectedTool
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
                    return self._get_scenario_tools(chat_session.scenario_id, session_id)
                else:
                    logger.warning(f"会话 {session_id} 未找到或没有场景，使用默认工具集")
            
            # 返回默认工具集
            return self._get_default_tools()
            
        except Exception as e:
            logger.error(f"获取会话工具失败: {e}")
            return self._get_default_tools()
    
    def _get_scenario_tools(self, scenario_id: int, session_id: int) -> List[Callable]:
        """根据场景ID获取预置工具 + 会话选择的工具"""
        tools = []
        
        try:
            # 1. 获取场景的预置工具
            scenario = self.session.get(Scenario, scenario_id)
            if scenario and scenario.preset_tool_ids:
                preset_tool_ids = scenario.preset_tool_ids
                for tool_id in preset_tool_ids:
                    tool_func = self._load_tool_function(tool_id)
                    if tool_func:
                        tools.append(tool_func)
            
            # 2. 获取用户为此会话选择的额外工具
            stmt = select(SessionSelectedTool).where(
                SessionSelectedTool.session_id == session_id
            )
            selected_tools = self.session.exec(stmt).all()
            
            for selected_tool in selected_tools:
                tool_func = self._load_tool_function(selected_tool.tool_id)
                if tool_func:
                    tools.append(tool_func)
            
            logger.info(f"为场景 {scenario_id} 会话 {session_id} 加载了 {len(tools)} 个工具")
            
        except Exception as e:
            logger.error(f"加载场景工具失败: {e}")
        
        # 如果没有工具，返回默认工具集
        if not tools:
            tools = self._get_default_tools()
        
        return tools
    
    def _get_default_tools(self) -> List[Callable]:
        """获取默认工具集 - 通用工具 + PDF共读工具"""
        tools = []
        
        # 默认加载的工具ID列表
        default_tool_ids = [
            "calculator_add",
            "calculator_multiply", 
            "handle_active_preview_app",
            "handle_scroll_pdf",
            "handle_preview_app_screenshot",
            "handle_control_preview_app",
            "ensure_accessibility_permission"
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
                    tool_name=tool.id,
                    timeout=30.0,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(f"工具通道调用失败 {tool.id}: {e}")
                return {"success": False, "error": str(e)}
        
        # 设置函数属性用于Agent识别
        channel_tool_wrapper.__name__ = tool.id
        channel_tool_wrapper.__doc__ = tool.description
        
        return channel_tool_wrapper
    
    def _import_direct_tool(self, tool: Tool) -> Optional[Callable]:
        """动态导入直接调用类型的工具"""
        try:
            # 解析模块路径和函数名
            # 假设 tool.module_path 格式为 "tools.calculator:add"
            if ':' in tool.module_path:
                module_name, function_name = tool.module_path.split(':')
            else:
                # 如果没有指定函数名，默认使用工具ID
                module_name = tool.module_path
                function_name = tool.id
            
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
    
    def get_tool_categories(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取工具分类信息 - 用于前端UI展示"""
        try:
            # 获取所有工具
            stmt = select(Tool)
            tools = self.session.exec(stmt).all()
            
            categories = {}
            for tool in tools:
                category = tool.category or "未分类"
                if category not in categories:
                    categories[category] = []
                
                categories[category].append({
                    "id": tool.id,
                    "name": tool.name,
                    "description": tool.description,
                    "tool_type": tool.tool_type,
                    "is_preset": tool.is_preset
                })
            
            return categories
            
        except Exception as e:
            logger.error(f"获取工具分类失败: {e}")
            return {}
    
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
    # 这里可以添加测试逻辑
    print("ToolProvider 模块加载成功")
    print("主要功能:")
    print("1. get_tools_for_session() - 为Agent提供工具列表")
    print("2. get_tool_categories() - 获取工具分类")
    print("3. get_available_scenarios() - 获取可用场景")
