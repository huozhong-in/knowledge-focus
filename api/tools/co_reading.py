from typing import Dict
from pydantic import BaseModel
# from pydantic_ai.toolsets import FunctionToolset
import pyautogui
from Quartz.CoreGraphics import (
    CGEventCreateScrollWheelEvent,
    CGEventPost,
    CGEventSetLocation,
    kCGEventSourceStateHIDSystemState,
    # kCGScrollEventUnitPixel,
)
from Quartz import (
    CGPoint,
    kCGWindowOwnerName,
    kCGWindowName,
    kCGWindowNumber,
    kCGWindowBounds,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowListExcludeDesktopElements,
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
)


class _WindowBounds(BaseModel):
    x: int
    y: int
    width: int
    height: int


class _WindowInfo(BaseModel):
    application_name: str
    window_name: str
    window_id: int
    bounds: _WindowBounds

# class CoReadingToolset(AbstractToolset):
#     def __init__(self):
#         super().__init__()
#         self.id = "co_reading_toolset"
#         self.label = "Co-Reading Toolset"
    
def get_window_list() -> Dict:
    """
    Get a list of all currently open windows in macOS.
    """
    # Define options for window listing:
    # kCGWindowListOptionOnScreenOnly: Only include windows that are currently visible on screen.
    # kCGWindowListExcludeDesktopElements: Exclude elements like the desktop background and icons.
    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements

    # Get the window information list
    window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

    windows = []
    for window_info in window_list:
        # Extract relevant information
        owner_name = window_info.get(kCGWindowOwnerName, "Unknown Application")
        window_name = window_info.get(kCGWindowName, "Untitled Window")
        window_id = window_info.get(kCGWindowNumber)
        bounds_dict = window_info.get(kCGWindowBounds, {})

        # Create WindowBounds object
        window_bounds = _WindowBounds(
            x=int(bounds_dict.get("X", 0)),
            y=int(bounds_dict.get("Y", 0)),
            width=int(bounds_dict.get("Width", 0)),
            height=int(bounds_dict.get("Height", 0)),
        )

        # Create WindowInfo object
        window_info_obj = _WindowInfo(
            application_name=owner_name,
            window_name=window_name,
            window_id=window_id,
            bounds=window_bounds,
        ).model_dump()

        windows.append(window_info_obj)

    return {"windows": windows}

def send_scroll_at_point(x, y, dy) -> bool:
    """
    Send a scroll event at the specified screen coordinates.
    Args:
        x (int): The x-coordinate on the screen where the scroll event should occur.
        y (int): The y-coordinate on the screen where the scroll event should occur.
        dy (int): The amount to scroll vertically. Positive values scroll up, negative values scroll down.
    """
    try:
        print("pyautogui.size():", pyautogui.size())
        # 获取当前鼠标位置
        ori_pos = pyautogui.position()
        print("原始鼠标位置:", ori_pos.x, ori_pos.y)
        # 创建滚动事件
        event = CGEventCreateScrollWheelEvent(
            None, kCGEventSourceStateHIDSystemState, 1, dy
        )
        # 设置事件发生的坐标位置
        target_location = CGPoint(x, y)
        CGEventSetLocation(event, target_location)
        # 发送事件
        CGEventPost(kCGEventSourceStateHIDSystemState, event)
        # Reset to original location
        pyautogui.moveTo(ori_pos.x, ori_pos.y)
        return True
    except Exception as e:
        print("Error occurred while sending scroll event:", e)
        return False

if __name__ == "__main__":
    # Test the functions
    print(get_window_list())
    print(send_scroll_at_point(1578, 587, -22))
