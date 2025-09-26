"""
统一工具API - 整合工具直接调用和工具通道机制

此模块提供：
1. 工具直接调用API（前端透过FastAPI调用Python功能）
2. 工具通道响应API（工具通道机制: Python端工具透过TypeScript在前端做具体执行）
3. 工具提供者API（获取工具列表等，为动态组织给agent的工具/工具集列表做支持）
"""

from sqlalchemy import Engine
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
import logging
from tool_provider import ToolProvider
from backend_tool_caller import g_backend_tool_caller

logger = logging.getLogger()

def get_router(get_engine: Engine) -> APIRouter:
    """获取统一的工具API路由器"""
    router = APIRouter()

    def get_tool_provider(engine: Engine = Depends(get_engine)) -> ToolProvider:
        return ToolProvider(engine=engine)

    # ==================== 前端直接调用API ====================

    @router.get("/tools/list")
    async def get_available_tools(
        session_id: Optional[int] = None,
        tool_provider: ToolProvider = Depends(get_tool_provider)
    ):
        """
        根据前端会话session_id获取工具列表        
        """
        tools = tool_provider.get_tools_for_session(session_id)
        if tools:
            return {
                "success": True,
                "tools": tools,
                "session_id": session_id,
                "count": len(tools),
            }
        return {
            "success": False,
            "message": "No tools found",
            "session_id": session_id,
        }
    
    @router.post("/tools/mcp/set_api_key")
    async def set_mcp_tool_api_key(
        tool_name: str,
        api_key: str,
        tool_provider: ToolProvider = Depends(get_tool_provider)
    ):
        """
        设置MCP类型工具的API Key
        
        Args:
            tool_name: 工具名称
            api_key: MCP API Key
        """
        try:
            success = tool_provider.set_mcp_tool_api_key(tool_name, api_key)
            if success:
                return {"success": True, "message": f"API key set for {tool_name}"}
            else:
                raise HTTPException(status_code=400, detail=f"Failed to set API key for {tool_name}")
        except HTTPException:
            # 不吞掉业务定义的异常
            raise
        except Exception as e:
            logger.error(f"设置MCP工具api_key失败 {tool_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Error setting API key for {tool_name}: {str(e)}")

    # 读取MCP工具的API Key
    @router.get("/tools/mcp/get_api_key")
    async def get_mcp_tool_api_key(
        tool_name: str,
        tool_provider: ToolProvider = Depends(get_tool_provider)
    ):
        """
        获取MCP类型工具的API Key
        
        Args:
            tool_name: 工具名称
        """
        try:
            api_key = tool_provider.get_mcp_tool_api_key(tool_name)
            if api_key != "":
                return {"success": True, "tool_name": tool_name, "api_key": api_key}
            else:
                # raise HTTPException(status_code=404, detail=f"API key not found for {tool_name}")
                return {"success": False, "message": f"API key not found for {tool_name}", "tool_name": tool_name}
        except Exception as e:
            logger.error(f"获取MCP工具api_key失败 {tool_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Error getting API key for {tool_name}: {str(e)}")

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
            
            # 根据工具名称调用对应的Python包装函数，其内部会利用“工具通道”调用前端工具
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
    

    return router
