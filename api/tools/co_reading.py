# import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Dict, 
    List, 
    # Literal,
    )
# from pydantic import BaseModel
from pydantic_graph.persistence.file import FileStatePersistence
# from pydantic_ai import RunContext
from pydantic_graph import (
    BaseNode,
    End,
    # Edge,
    Graph,
    GraphRunContext,
)
from backend_tool_caller import g_backend_tool_caller
# import pyautogui
# from Quartz.CoreGraphics import (
#     CGEventCreateScrollWheelEvent,
#     CGEventPost,
#     CGEventSetLocation,
#     kCGEventSourceStateHIDSystemState,
#     # kCGScrollEventUnitPixel,
# )
# from Quartz import (
#     CGPoint,
#     kCGWindowOwnerName,
#     kCGWindowName,
#     kCGWindowNumber,
#     kCGWindowBounds,
#     kCGWindowListOptionOnScreenOnly,
#     kCGWindowListExcludeDesktopElements,
#     CGWindowListCopyWindowInfo,
#     kCGNullWindowID,
# )
# from sqlmodel import Session
# from models_mgr import ModelsMgr
import logging
logger = logging.getLogger()

# # PDF阅读器坐标缓存 - 全局变量用于保存PDF阅读器中心点坐标
# _pdf_reader_center_point = None

# def set_pdf_reader_center_point(x: int, y: int):
#     """设置PDF阅读器中心点坐标"""
#     global _pdf_reader_center_point
#     _pdf_reader_center_point = {"x": x, "y": y}
#     print(f"PDF阅读器中心点坐标已保存: ({x}, {y})")

# def get_pdf_reader_center_point():
#     """获取PDF阅读器中心点坐标"""
#     return _pdf_reader_center_point

# def clear_pdf_reader_center_point():
#     """清除PDF阅读器中心点坐标"""
#     global _pdf_reader_center_point
#     _pdf_reader_center_point = None
# class _WindowBounds(BaseModel):
#     x: int
#     y: int
#     width: int
#     height: int

# class _WindowInfo(BaseModel):
#     application_name: str
#     window_name: str
#     window_id: int
#     bounds: _WindowBounds

# def _get_window_list() -> List[_WindowInfo]:
#     """
#     获取窗口列表
#     """
#     # Define options for window listing:
#     # kCGWindowListOptionOnScreenOnly: Only include windows that are currently visible on screen.
#     # kCGWindowListExcludeDesktopElements: Exclude elements like the desktop background and icons.
#     options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements

#     # Get the window information list
#     window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

#     windows = []
#     for window_info in window_list:
#         # Extract relevant information
#         owner_name = window_info.get(kCGWindowOwnerName, "Unknown Application")
#         window_name = window_info.get(kCGWindowName, "Untitled Window")
#         window_id = window_info.get(kCGWindowNumber)
#         bounds_dict = window_info.get(kCGWindowBounds, {})

#         # Create WindowBounds object
#         window_bounds = _WindowBounds(
#             x=int(bounds_dict.get("X", 0)),
#             y=int(bounds_dict.get("Y", 0)),
#             width=int(bounds_dict.get("Width", 0)),
#             height=int(bounds_dict.get("Height", 0)),
#         )

#         # Create WindowInfo object
#         window_info_obj = _WindowInfo(
#             application_name=owner_name,
#             window_name=window_name,
#             window_id=window_id,
#             bounds=window_bounds,
#         )

#         windows.append(window_info_obj)

#     return windows

# def _send_scroll_at_point(x, y, dy: int = 22) -> bool:
#     """
#     发送滚动事件

#     Args:
#         x (int): 鼠标的X坐标
#         y (int): 鼠标的Y坐标
#         dy (int): 滚动的距离，负值反向滚动
#     """
#     # print("pyautogui.size():", pyautogui.size())
#     # 获取当前鼠标位置
#     ori_pos = pyautogui.position()
#     # print("原始鼠标位置:", ori_pos.x, ori_pos.y)
#     # 创建滚动事件
#     event = CGEventCreateScrollWheelEvent(
#         None, kCGEventSourceStateHIDSystemState, 1, dy
#     )
#     # 设置事件发生的坐标位置
#     target_location = CGPoint(x, y)
#     CGEventSetLocation(event, target_location)
#     # 发送事件
#     CGEventPost(kCGEventSourceStateHIDSystemState, event)
#     # Reset to original location
#     pyautogui.moveTo(ori_pos.x, ori_pos.y)
#     return True

# def scroll_pdf_reader(ctx: RunContext, direction: Literal["up", "down"] = "down", amount: int = 10) -> Dict:
#     """
#     智能滚动PDF阅读器 - 自动使用缓存的中心点坐标
    
#     Args:
#         direction: 滚动方向 "up" 或 "down"
#         amount: 滚动距离
#     """
#     try:
#         # 检查是否有缓存的坐标
#         center_point = get_pdf_reader_center_point()
#         if not center_point:
#             return {
#                 "success": False, 
#                 "message": "未找到PDF阅读器坐标，请先打开PDF文件"
#             }
        
#         x, y = center_point["x"], center_point["y"]
        
#         # 根据方向确定滚动距离（向上为负值）
#         dy = amount if direction.deps == "down" else -amount

#         # 执行滚动
#         success = _send_scroll_at_point(x, y, dy)
        
#         if success:
#             return {
#                 "success": True, 
#                 "message": f"已在坐标({x}, {y})执行{direction.deps}滚动，距离{amount}"
#             }
#         else:
#             return {
#                 "success": False, 
#                 "message": "滚动事件发送失败"
#             }
            
#     except Exception as e:
#         return {"success": False, "message": f"滚动失败: {e}"}

# def _is_window_exist(window_name: str) -> bool:
#     """检查指定窗口是否存在"""
#     windows = _get_window_list()
#     for win in windows:
#         if window_name in win.window_name:
#             return True
#     return False

# async def handle_pdf_reading(ctx: RunContext, pdf_path: str) -> Dict:
#     """
#     使用系统默认PDF阅读器打开PDF文件
#     Args:
#         pdf_path (str): PDF文件的完整路径
#     """
#     try:
#         result = await g_backend_tool_caller.call_frontend_tool(
#             "handle_pdf_reading",
#             pdfPath=pdf_path  # 注意：前端期望的参数名是pdfPath，不是pdf_path
#         )
#         logger.info(f"PDF阅读器打开结果: {result}")

#         # 检查返回的结果是否是坐标数据
#         if isinstance(result, dict) and "x" in result and "y" in result:
#             # 直接使用返回的坐标数据
#             set_pdf_reader_center_point(result["x"], result["y"])
#             return {
#                 "success": True, 
#                 "message": f"PDF文件已打开，阅读器中心点坐标: ({result['x']}, {result['y']})"
#             }
        
#         # 备用检查方式：检查窗口是否存在
#         pdf_file_name = os.path.basename(pdf_path)
#         if _is_window_exist(pdf_file_name):
#             return {"success": True, "message": "PDF文件已打开，但未获取到精确坐标"}
        
#         return {"success": False, "message": "未找到对应的PDF窗口"}
#     except Exception as e:
#         return {"success": False, "message": f"打开PDF失败: {e}"}

# async def handle_pdf_reader_screenshot(ctx: RunContext, pdf_path: str) -> Dict:
#     """
#     对PDF窗口截图

#     Args:
#         pdf_path (str): PDF文件路径
#     """
#     try:
#         result = await g_backend_tool_caller.call_frontend_tool(
#             "handle_pdf_reader_screenshot", 
#             pdfPath=pdf_path  # 前端期望pdfPath参数名
#         )
#         return result
#     except Exception as e:
#         return {"success": False, "message": f"截图失败: {e}"}

# async def ensure_accessibility_permission() -> Dict:
#     """
#     确保已经获得macOS辅助功能权限
#     """
#     try:
#         result = await g_backend_tool_caller.call_frontend_tool(
#             "ensure_accessibility_permission"
#         )
#         return result
#     except Exception as e:
#         return {"success": False, "message": f"权限检查失败: {e}"}

# async def handle_activate_pdf_reader(ctx: RunContext, pdf_path: str, action: str = "focus") -> Dict:
#     """
#     寻找和激活PDF阅读器应用窗口

#     Args:
#         pdf_path (str): PDF文件的完整路径
#         action (str): 激活动作，默认为"focus"
#     """
#     try:
#         result = await g_backend_tool_caller.call_frontend_tool(
#             "handle_activate_pdf_reader",
#             pdfPath=pdf_path,  # 前端期望pdfPath参数名
#             action=action
#         )
#         logger.info(f"激活PDF阅读器结果: {result}")
        
#         # 检查返回的结果是否是坐标数据
#         if isinstance(result, dict) and "x" in result and "y" in result:
#             # 保存PDF阅读器中心点坐标
#             set_pdf_reader_center_point(result["x"], result["y"])
#             return {
#                 "success": True, 
#                 "message": f"PDF阅读器已激活，中心点坐标: ({result['x']}, {result['y']})"
#             }
        
#         # 如果没有返回坐标数据，可能是窗口没找到
#         return {"success": False, "message": "未找到对应的PDF窗口或无法获取坐标"}
#     except Exception as e:
#         return {"success": False, "message": f"控制Preview应用失败: {e}"}


# =============================================================================
# PDF共读状态机数据结构和Graph节点定义
# =============================================================================

@dataclass 
class CoReadingState:
    """共读状态机的状态数据"""
    pdf_path: str
    session_id: int
    pdf_center_point: Dict[str, int] | None = None  # PDF阅读器中心点坐标
    last_user_message: str | None = None  # 最后一条用户消息
    screenshot_count: int = 0  # 截图计数
    created_at: str = field(default_factory=lambda: str(datetime.now()))

@dataclass
class CoReadingNode(BaseNode[CoReadingState, int, str]):
    """共读状态节点 - 主要的交互状态"""
    
    async def run(self, ctx: GraphRunContext[CoReadingState, int]) -> 'PausedNode | End[str]':
        """
        共读状态的主要逻辑：
        1. 检查PDF窗口状态
        2. 如果窗口正常，等待用户交互
        3. 如果窗口关闭/最小化，转到暂停状态
        """
        logger.info(f"进入共读状态，PDF: {ctx.state.pdf_path}")
        
        # 检查PDF窗口状态
        try:
            pdf_status = await g_backend_tool_caller.call_frontend_tool(
                "isPdfReaderFocused", 
                pdfPath=ctx.state.pdf_path
            )
            
            if not pdf_status.get("exists", False) or pdf_status.get("isMiniaturized", False):
                logger.info("PDF窗口不存在或已最小化，转入暂停状态")
                return PausedNode(reason="pdf_window_unavailable")
            
            # PDF窗口正常，发送状态事件到前端
            from bridge_events import BridgeEventSender
            bridge_sender = BridgeEventSender()
            bridge_sender.send_raw_event("co_reading_active", {
                "pdf_path": ctx.state.pdf_path,
                "session_id": ctx.state.session_id
            })
            
            # 在这里等待用户交互或定时器触发
            # 目前先实现简单的被动回复模式
            logger.info("共读状态激活，等待用户交互")
            
            # 暂时返回End，后续会改为等待用户输入的逻辑
            return End("co_reading_active")
            
        except Exception as e:
            logger.error(f"共读状态检查失败: {e}")
            return PausedNode(reason="error")

@dataclass  
class PausedNode(BaseNode[CoReadingState, int, str]):
    """暂停状态节点 - PDF不可用时的状态"""
    reason: str = "unknown"  # 暂停原因
    
    async def run(self, ctx: GraphRunContext[CoReadingState, int]) -> 'CoReadingNode | End[str]':
        """
        暂停状态的逻辑：
        1. 发送暂停事件到前端（触发Widget显示）
        2. 等待前端用户操作（继续阅读 or 停止阅读）
        """
        logger.info(f"进入暂停状态，原因: {self.reason}")
        
        # 发送暂停状态事件到前端
        from bridge_events import BridgeEventSender
        bridge_sender = BridgeEventSender()
        bridge_sender.send_raw_event("co_reading_paused", {
            "reason": self.reason,
            "pdf_path": ctx.state.pdf_path,
            "session_id": ctx.state.session_id
        })
        
        # 这里需要等待前端用户操作
        # 目前先返回End，后续实现真正的等待逻辑
        logger.info("暂停状态激活，等待用户选择")
        return End("co_reading_paused")

# 创建共读状态机Graph
co_reading_graph = Graph(
    nodes=[CoReadingNode, PausedNode],
    state_type=CoReadingState
)

# =============================================================================
# 共读流协议处理函数
# =============================================================================
# persistence_dir = Path(db_path).parent / "graph_persistence"
# persistence_dir.mkdir(exist_ok=True)

async def stream_co_reading_chat_v5_compatible(
    messages: List[Dict], 
    session_id: int,
    pdf_path: str,
    persistence_dir: Path
):
    """
    共读模式的流协议处理函数
    
    Args:
        messages: 用户消息列表  
        session_id: 会话ID
        pdf_path: PDF文件路径
        persistence_dir: 持久化目录
    """
    try:
        logger.info(f"开始共读模式流处理，session_id: {session_id}, pdf: {pdf_path}")
        
        # 设置持久化文件路径
        persistence_file = persistence_dir / f"co_reading_{session_id}.json"
        persistence = FileStatePersistence(persistence_file)
        persistence.set_graph_types(co_reading_graph)
        
        # 检查是否有之前的状态需要恢复
        if snapshot := await persistence.load_next():
            logger.info("恢复之前的共读状态")
            state = snapshot.state
            next_node = snapshot.node
        else:
            logger.info("开始新的共读会话")
            # 创建新的共读状态
            state = CoReadingState(
                pdf_path=pdf_path,
                session_id=session_id
            )
            next_node = CoReadingNode()
        
        # 开始Graph迭代
        async with co_reading_graph.iter(
            next_node, 
            state=state, 
            persistence=persistence,
            deps=session_id
        ) as run:
            async for node in run:
                logger.info(f"执行Graph节点: {type(node).__name__}")
                
                
        
        # 发送完成标志
        yield f'data: {json.dumps({"type": "finish"})}\n\n'
        yield 'data: [DONE]\n\n'
        
    except Exception as e:
        logger.error(f"共读流处理失败: {e}")
        yield f'data: {json.dumps({"type": "error", "errorText": str(e)})}\n\n'

# Test the functions  
if __name__ == "__main__":
    pass
