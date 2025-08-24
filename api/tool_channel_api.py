"""
工具通道API - 处理前端工具调用响应

提供HTTP端点接收TypeScript前端的工具执行结果
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
import logging

from backend_tool_caller import g_backend_tool_caller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tool-channel"])

class ToolResponseModel(BaseModel):
    """工具响应数据模型"""
    call_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    duration: Optional[float] = None

@router.post("/response")
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

@router.get("/pending")
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

@router.post("/test")
async def test_frontend_tool_call(tool_name: str, **kwargs):
    """
    测试前端工具调用
    
    用于开发和调试工具通道
    """
    try:
        logger.info(f"测试前端工具调用: {tool_name}")
        
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
