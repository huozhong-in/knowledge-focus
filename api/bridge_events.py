"""
桥接事件发送工具模块

此模块提供统一的方法来向Tauri前端发送事件通知。
事件通过标准输出发送，Rust桥接层会捕获并转发给TypeScript前端。

使用方法:
    from bridge_events import BridgeEventSender
    
    sender = BridgeEventSender()
    sender.send_event("task-completed", {"task_id": "123", "result": "success"})
"""

import json
import time
import logging
from typing import Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

class BridgeEventSender:
    """桥接事件发送器"""
    
    # 定义常用的事件类型常量
    class Events(str, Enum):
        TAGS_UPDATED = "tags-updated"
        TASK_COMPLETED = "task-completed"
        FILE_PROCESSED = "file-processed"
        PARSING_PROGRESS = "parsing-progress"
        SCREENING_PROGRESS = "screening-progress"
        MODEL_STATUS_CHANGED = "model-status-changed"
        DATABASE_UPDATED = "database-updated"
        ERROR_OCCURRED = "error-occurred"
        SYSTEM_STATUS = "system-status"
    
    def __init__(self, source: str = "python-backend"):
        """
        初始化桥接事件发送器
        
        Args:
            source: 事件来源标识，用于调试和日志
        """
        self.source = source
    
    def send_event(self, event_name: str, payload: Dict[str, Any] | None = None):
        """
        发送桥接事件到前端
        
        Args:
            event_name: 事件名称
            payload: 事件负载数据，可选
        """
        try:
            # 构建事件数据
            event_data = {
                "event": event_name,
                "payload": self._enrich_payload(payload or {})
            }
            
            # 发送JSON事件
            print(f"EVENT_NOTIFY_JSON:{json.dumps(event_data)}", flush=True)
            
            logger.debug(f"桥接事件已发送: {event_name} from {self.source}")
            
        except Exception as e:
            logger.error(f"发送桥接事件失败 [{event_name}]: {e}")
    
    def _enrich_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        丰富payload，添加通用字段
        
        Args:
            payload: 原始payload
            
        Returns:
            丰富后的payload
        """
        enriched = {
            "timestamp": time.time(),
            "source": self.source,
            **payload  # 原始payload数据
        }
        return enriched
    
    # 便捷方法
    def tags_updated(self, description: str = "标签数据已更新"):
        """通知标签更新"""
        self.send_event(self.Events.TAGS_UPDATED, {
            "description": description
        })
    
    def task_completed(self, task_id: str, result: Any = None, success: bool = True):
        """通知任务完成"""
        self.send_event(self.Events.TASK_COMPLETED, {
            "task_id": task_id,
            "success": success,
            "result": result
        })
    
    def file_processed(self, file_path: str, **kwargs):
        """通知文件处理完成"""
        self.send_event(self.Events.FILE_PROCESSED, {
            "file_path": file_path,
            **kwargs
        })
    
    def progress_update(self, progress_type: str, current: int, total: int, message: str = ""):
        """通知进度更新"""
        event_name = f"{progress_type}-progress"
        self.send_event(event_name, {
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 2) if total > 0 else 0,
            "message": message
        })
    
    def error_occurred(self, error_type: str, message: str, details: Dict[str, Any] = None):
        """通知错误发生"""
        self.send_event(self.Events.ERROR_OCCURRED, {
            "error_type": error_type,
            "message": message,
            "details": details or {}
        })
    
    def system_status(self, status: str, message: str = "", details: Dict[str, Any] = None):
        """通知系统状态变化"""
        self.send_event(self.Events.SYSTEM_STATUS, {
            "status": status,
            "message": message,
            "details": details or {}
        })

# 测试代码
if __name__ == "__main__":
    bridge_events = BridgeEventSender()
    
    def test_basic_events(sender: BridgeEventSender):
        """测试基本事件发送"""
        print("=== 测试基本事件发送 ===")
        
        # 发送各种类型的事件
        sender.tags_updated("这是一个测试标签更新")
        time.sleep(1)
        
        sender.task_completed("test-task-123", {"result": "success", "data": [1, 2, 3]})
        time.sleep(1)
        
        sender.file_processed("/test/path/file.txt", tags_count=5, status="completed")
        time.sleep(1)
        
        sender.progress_update("parsing", 50, 100, "正在解析文件...")
        time.sleep(1)
        
        sender.error_occurred("parsing_error", "文件解析失败", {"file": "/test/error.txt"})
        time.sleep(1)
        
        sender.system_status("ready", "系统准备就绪", {"version": "1.0.0"})
        time.sleep(1)


    def test_custom_events(sender: BridgeEventSender):
        """测试自定义事件"""
        print("\n=== 测试自定义事件 ===")
        sender.send_event("custom-event", {
            "message": "这是一个自定义事件",
            "data": {"key1": "value1", "key2": 42},
            "custom_field": True
        })
        time.sleep(1)
        
        # 测试无payload的事件
        sender.send_event("simple-event")


    # 10秒倒计时
    for i in range(10, 0, -1):
        print(f"倒计时: {i}秒")
        time.sleep(1)
    print("开始桥接事件系统测试...")
    print("Rust端应该能够捕获这些输出并转发给前端\n")
    
    test_basic_events(bridge_events)
    test_custom_events(bridge_events)

    print("\n=== 测试完成 ===")
    print("如果Rust桥接正常工作，前端应该收到上述所有事件")
