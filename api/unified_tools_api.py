"""
统一工具API - 整合工具直接调用和工具通道机制

此模块提供：
1. 工具直接调用API（前端透过FastAPI调用Python功能）
2. 工具通道响应API（工具通道机制: Python端工具透过TypeScript在前端做具体执行）
3. 工具提供者API（获取工具列表等，为动态组织给agent的工具/工具集列表做支持）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
import logging

from backend_tool_caller import g_backend_tool_caller

logger = logging.getLogger(__name__)

def get_router(external_get_session: callable) -> APIRouter:
    """获取统一的工具API路由器"""
    router = APIRouter()

    # ==================== 前端直接调用API ====================

    # ==================== 工具通道响应API ====================
    # 新的工具通道机制相关API
    
    class ToolResponseModel(BaseModel):
        """工具响应数据模型"""
        call_id: str
        success: bool
        result: Optional[Any] = None
        error: Optional[str] = None
        duration: Optional[float] = None

    @router.post("/tools/response")
    async def handle_tool_response(response: ToolResponseModel):
        """
        接收前端工具执行响应
        
        前端执行完工具后，通过此API将结果返回给Python后端
        """
        try:
            logger.info(f"收到工具响应: call_id={response.call_id}, success={response.success}")
            
            # 将响应传递给工具调用器
            g_backend_tool_caller.handle_tool_response(response.model_dump())
            
            return {"status": "ok", "message": "Response handled successfully"}
            
        except Exception as e:
            logger.error(f"处理工具响应失败: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to handle tool response: {str(e)}")

    @router.get("/tools/pending")
    async def get_pending_calls():
        """
        获取当前等待响应的工具调用列表
        
        用于调试和监控
        """
        try:
            pending_calls = list(g_backend_tool_caller.pending_calls.keys())
            return {
                "pending_calls": pending_calls,
                "count": len(pending_calls)
            }
        except Exception as e:
            logger.error(f"获取等待调用列表失败: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get pending calls: {str(e)}")

    @router.post("/tools/test")
    async def test_frontend_tool_call(test_request: dict):
        """
        测试前端工具调用
        
        用于开发和调试工具通道
        
        Args:
            test_request: {"tool_name": "工具名称", "参数名": "参数值", ...}
        """
        try:
            tool_name = test_request.get("tool_name")
            if not tool_name:
                raise HTTPException(status_code=400, detail="Missing tool_name parameter")
            
            # 提取除tool_name之外的所有参数作为kwargs
            kwargs = {k: v for k, v in test_request.items() if k != "tool_name"}
            
            logger.info(f"测试工具调用: {tool_name}, 参数: {kwargs}")
            
            # 根据工具名称调用对应的Python包装函数，而不是直接调用前端工具
            if tool_name == "handle_pdf_reading":
                from tools.co_reading import handle_pdf_reading
                pdf_path = kwargs.get("pdfPath")
                if not pdf_path:
                    raise HTTPException(status_code=400, detail="Missing pdfPath parameter")
                result = await handle_pdf_reading(pdf_path)
                
            elif tool_name == "handle_pdf_reader_screenshot":
                from tools.co_reading import handle_pdf_reader_screenshot
                pdf_path = kwargs.get("pdfPath")
                if not pdf_path:
                    raise HTTPException(status_code=400, detail="Missing pdfPath parameter")
                result = await handle_pdf_reader_screenshot(pdf_path)
                
            elif tool_name == "ensure_accessibility_permission":
                from tools.co_reading import ensure_accessibility_permission
                result = await ensure_accessibility_permission()
                
            elif tool_name == "handle_activate_pdf_reader":
                from tools.co_reading import handle_activate_pdf_reader
                pdf_path = kwargs.get("pdfPath")
                if not pdf_path:
                    raise HTTPException(status_code=400, detail="Missing pdfPath parameter")
                action = kwargs.get("action", "focus")
                result = await handle_activate_pdf_reader(pdf_path, action)
                
            else:
                # 对于其他工具，直接调用前端工具
                result = await g_backend_tool_caller.call_frontend_tool(
                    tool_name=tool_name,
                    timeout=10.0,
                    **kwargs
                )
            
            return {
                "status": "success",
                "result": result,
                "tool_name": tool_name
            }
            
        except Exception as e:
            logger.error(f"测试工具调用失败: {e}")
            raise HTTPException(status_code=500, detail=f"Tool call failed: {str(e)}")
    
    # ==================== 工具提供者API ====================

    @router.get("/tools/list")
    async def get_available_tools(session_id: Optional[int] = None):
        """
        根据前端会话session_id获取工具列表
        
        # TODO: 这里将来要集成 tool_provider.py 的逻辑
        """
        tools = [
            {
                "id": "scroll_pdf_reader",
                "name": "滚动PDF阅读器",
                "description": "智能滚动PDF阅读器。会自动使用之前打开PDF时保存的中心点坐标，无需指定具体坐标。",
                "category": "co_reading",
                "type": "direct",  # 直接调用
                "parameters": {
                    "direction": {"type": "string", "required": True, "enum": ["up", "down"], "description": "滚动方向"},
                    "amount": {"type": "integer", "required": False, "default": 10, "description": "滚动距离"}
                }
            },
            {
                "id": "handle_pdf_reading",
                "name": "阅读PDF",
                "description": "通过系统默认PDF阅读器打开PDF文件。并重新排布窗口，本App位于左侧，PDF阅读器位于右侧。",
                "category": "co_reading",
                "type": "channel",  # 通过工具通道调用
                "parameters": {
                    "pdf_path": {"type": "string", "required": True, "description": "PDF文件路径"}
                }
            },
            {
                "id": "ensure_accessibility_permission",
                "name": "确保辅助功能权限",
                "description": "确保应用具有辅助功能权限",
                "category": "co_reading",
                "type": "channel",
                "parameters": {}
            },
            {
                "id": "handle_activate_pdf_reader",
                "name": "激活PDF阅读器",
                "description": "激活当前PDF阅读器窗口。如果它最小化或被遮挡，会将其恢复并置于前端",
                "category": "co_reading",
                "type": "channel",
                "parameters": {
                    "pdf_path": {"type": "string", "required": True, "description": "PDF文件路径"}
                }
            },
            {
                "id": "handle_pdf_reader_screenshot",
                "name": "PDF截图",
                "description": "对当前PDF页面截图",
                "category": "co_reading",
                "type": "channel",
                "parameters": {
                    "pdf_path": {"type": "string", "required": True, "description": "PDF文件路径"}
                }
            }
        ]
        
        return {
            "tools": tools,
            "session_id": session_id,
            "count": len(tools),
            "categories": {
                "system": [t for t in tools if t["category"] == "system"],
                "pdf_reading": [t for t in tools if t["category"] == "pdf_reading"]
            }
        }

    return router

# 为了向后兼容，保持原来的路由器实例
# router = get_router(None)
