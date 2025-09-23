"""
后端工具调用器 - 通用工具通道机制

此模块提供Python端与TypeScript前端之间的通用工具调用机制。
支持异步调用前端工具并等待执行结果。

使用方法:
    from backend_tool_caller import backend_tool_caller
    
    # 在PydanticAI工具中调用前端功能
    result = await backend_tool_caller.call_frontend_tool(
        "handle_pdf_reading", 
        pdf_path="/path/to/file.pdf"
    )
"""

import asyncio
import uuid
import time
import logging
from typing import Any, Dict
from bridge_events import BridgeEventSender

logger = logging.getLogger()

class BackendToolCaller:
    """后端工具调用器 - 负责向前端发送工具调用请求并等待响应"""
    
    def __init__(self):
        self.bridge_sender = BridgeEventSender(source="backend-tool-caller")
        self.pending_calls: Dict[str, asyncio.Event] = {}  # call_id -> Event
        self.call_results: Dict[str, Dict[str, Any]] = {}  # call_id -> result
        self.call_timeouts: Dict[str, float] = {}  # call_id -> timeout_timestamp
        self._cleanup_task_started = False
        
        # 不在初始化时启动清理任务，而是在第一次调用时启动
    
    async def call_frontend_tool(
        self, 
        tool_name: str, 
        timeout: float = 30.0,
        **kwargs
    ) -> Any:
        """
        调用前端工具并等待执行结果
        
        Args:
            tool_name: 前端工具名称
            timeout: 超时时间（秒）
            **kwargs: 传递给前端工具的参数
            
        Returns:
            前端工具的执行结果
            
        Raises:
            asyncio.TimeoutError: 调用超时
            RuntimeError: 前端工具执行失败
        """
        call_id = str(uuid.uuid4())
        start_time = time.time()
        
        # 确保清理任务已启动
        if not self._cleanup_task_started:
            self._start_cleanup_task()
            self._cleanup_task_started = True
        
        logger.info(f"正在调用前端工具: {tool_name} (call_id: {call_id})")
        
        # 创建等待事件
        event = asyncio.Event()
        self.pending_calls[call_id] = event
        self.call_timeouts[call_id] = time.time() + timeout
        
        try:
            # 发送工具调用请求
            self.bridge_sender.send_event(
                BridgeEventSender.Events.TOOL_CALL_REQUEST,
                {
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "args": kwargs,
                    "timeout": timeout,
                    "timestamp": start_time
                }
            )
            
            # 等待响应（带超时）
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"前端工具调用超时: {tool_name} (call_id: {call_id})")
                raise asyncio.TimeoutError(f"Frontend tool '{tool_name}' timeout after {timeout}s")
            
            # 获取结果
            result_data = self.call_results.pop(call_id, {})
            
            if result_data.get("success", False):
                duration = time.time() - start_time
                logger.info(f"前端工具调用成功: {tool_name} (耗时: {duration:.2f}s)")
                return result_data.get("result")
            else:
                error_msg = result_data.get("error", "Unknown error")
                logger.error(f"前端工具调用失败: {tool_name} - {error_msg}")
                raise RuntimeError(f"Frontend tool '{tool_name}' failed: {error_msg}")
                
        finally:
            # 清理资源
            self.pending_calls.pop(call_id, None)
            self.call_results.pop(call_id, None)
            self.call_timeouts.pop(call_id, None)
    
    def handle_tool_response(self, payload: Dict[str, Any]):
        """
        处理前端工具的响应
        
        这个方法将被HTTP API端点调用
        
        Args:
            payload: 响应数据，包含call_id, success, result, error等字段
        """
        call_id = payload.get("call_id")
        if not call_id:
            logger.warning("收到无效的工具响应: 缺少call_id")
            return
        
        if call_id not in self.pending_calls:
            logger.warning(f"收到未知call_id的工具响应: {call_id}")
            return
        
        # 保存结果并触发等待的协程
        self.call_results[call_id] = payload
        self.pending_calls[call_id].set()
        
        success = payload.get("success", False)
        error_msg = payload.get("error")
        
        if success:
            logger.info(f"收到成功的工具响应 (call_id: {call_id})")
        else:
            logger.error(f"收到失败的工具响应 (call_id: {call_id}): {error_msg}")
    
    def _start_cleanup_task(self):
        """启动定期清理任务，清理超时的调用"""
        async def cleanup_expired_calls():
            while True:
                try:
                    await asyncio.sleep(10)  # 每10秒检查一次
                    
                    current_time = time.time()
                    expired_calls = []
                    
                    for call_id, timeout_time in self.call_timeouts.items():
                        if current_time > timeout_time:
                            expired_calls.append(call_id)
                    
                    for call_id in expired_calls:
                        logger.warning(f"清理超时的工具调用: {call_id}")
                        
                        # 设置超时结果
                        self.call_results[call_id] = {
                            "success": False,
                            "error": "Call timeout",
                            "result": None
                        }
                        
                        # 触发等待的协程
                        if call_id in self.pending_calls:
                            self.pending_calls[call_id].set()
                        
                        # 清理资源
                        self.pending_calls.pop(call_id, None)
                        self.call_timeouts.pop(call_id, None)
                        
                except Exception as e:
                    logger.error(f"清理任务出错: {e}")
        
        # 只有在有事件循环时才启动清理任务
        try:
            asyncio.create_task(cleanup_expired_calls())
        except RuntimeError:
            # 如果没有运行的事件循环，暂时跳过
            # 清理任务会在第一次调用工具时启动
            logger.debug("暂时无法启动清理任务，将在第一次调用时启动")
    

# 全局实例
g_backend_tool_caller = BackendToolCaller()

# 测试代码
if __name__ == "__main__":
    pass
