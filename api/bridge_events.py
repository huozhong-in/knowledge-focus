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
import sys
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger()

# 保存原始的stdout引用，确保桥接事件能够直接输出到原始stdout
# 避免被uvicorn或其他日志系统重定向
_ORIGINAL_STDOUT = sys.stdout

def test_stdout_accessibility():
    """
    测试原始stdout是否可访问
    用于调试桥接事件输出问题
    """
    try:
        _ORIGINAL_STDOUT.write("BRIDGE_STDOUT_TEST: Original stdout is accessible\n")
        _ORIGINAL_STDOUT.flush()
        return True
    except Exception as e:
        logger.error(f"原始stdout不可访问: {e}")
        return False

class BridgeEventSender:
    """桥接事件发送器"""
    
    # 定义常用的事件类型常量
    class Events(str, Enum):
        TAGS_UPDATED = "tags-updated"
        TASK_COMPLETED = "task-completed"
        
        FILE_PROCESSED = "file-processed"
        FILE_TAGGING_PROGRESS = "file-tagging-progress"
        MODEL_STATUS_CHANGED = "model-status-changed"
        MODEL_VALIDATION_FAILED = "model-validation-failed"
        DATABASE_UPDATED = "database-updated"
        ERROR_OCCURRED = "error-occurred"
        SYSTEM_STATUS = "system-status"
        
        # 标签相关事件
        TAGGING_MODEL_MISSING = "tagging-model-missing"
        
        # RAG相关事件
        RAG_RETRIEVAL_RESULT = "rag-retrieval-result"
        RAG_PROGRESS = "rag-progress"
        RAG_ERROR = "rag-error"
        
        # 多模态向量化事件
        MULTIVECTOR_STARTED = "multivector-started"
        MULTIVECTOR_PROGRESS = "multivector-progress"
        MULTIVECTOR_COMPLETED = "multivector-completed"
        MULTIVECTOR_FAILED = "multivector-failed"
        
        # 工具通道事件 - 通用工具调用机制
        TOOL_CALL_REQUEST = "tool-call-request"   # Python请求前端执行工具
        TOOL_CALL_RESPONSE = "tool-call-response" # 前端返回执行结果（通过HTTP API）
        TOOL_CALL_ERROR = "tool-call-error"       # 工具执行错误

        # 模型下载事件
        MODEL_DOWNLOAD_PROGRESS = "model-download-progress"
        MODEL_DOWNLOAD_COMPLETED = "model-download-completed"
        MODEL_DOWNLOAD_FAILED = "model-download-failed"
    
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
            
            # 直接写入原始stdout，绕过任何可能的重定向
            # 使用原始stdout确保Rust端能够捕获到输出
            _ORIGINAL_STDOUT.write(f"EVENT_NOTIFY_JSON:{json.dumps(event_data)}\n")
            _ORIGINAL_STDOUT.flush()
            
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
    
    def model_validation_failed(self, provider_type: str, model_id: str, role_type: str, 
                               available_models: list = None, error_message: str = ""):
        """通知模型验证失败"""
        self.send_event(self.Events.MODEL_VALIDATION_FAILED, {
            "provider_type": provider_type,
            "model_id": model_id,
            "role_type": role_type,
            "available_models": available_models or [],
            "error_message": error_message
        })
    
    def tagging_model_missing(self, message: str = "标签生成模型未配置", details: Dict[str, Any] = None):
        """通知标签生成模型缺失"""
        self.send_event(self.Events.TAGGING_MODEL_MISSING, {
            "message": message,
            "details": details or {}
        })

    def model_download_progress(self, model_name: str, current: int, total: int, 
                               message: str = "", stage: str = "downloading"):
        """通知模型下载进度"""
        self.send_event(self.Events.MODEL_DOWNLOAD_PROGRESS, {
            "model_name": model_name,
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 2) if total > 0 else 0,
            "message": message,
            "stage": stage,  # downloading, extracting, completed, failed
            "timestamp": time.time()
        })

    def model_download_completed(self, model_name: str, local_path: str, message: str = ""):
        """通知模型下载完成"""
        self.send_event(self.Events.MODEL_DOWNLOAD_COMPLETED, {
            "model_name": model_name,
            "local_path": local_path,
            "message": message or f"模型 {model_name} 下载完成",
            "timestamp": time.time()
        })

    def model_download_failed(self, model_name: str, error_message: str, details: Dict[str, Any] = None):
        """通知模型下载失败"""
        self.send_event(self.Events.MODEL_DOWNLOAD_FAILED, {
            "model_name": model_name,
            "error_message": error_message,
            "details": details or {},
            "timestamp": time.time()
        })
    
    # 多模态向量化便捷方法    
    def multivector_progress(self, file_path: str, task_id: str, current: int, total: int, 
                           stage: str = "", message: str = ""):
        """通知多模态向量化进度"""
        self.send_event(self.Events.MULTIVECTOR_PROGRESS, {
            "file_path": file_path,
            "task_id": task_id,
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 2) if total > 0 else 0,
            "stage": stage,  # parsing, chunking, vectorizing
            "message": message
        })
    
    def multivector_completed(self, file_path: str, task_id: str, 
                            parent_chunks_count: int = 0, child_chunks_count: int = 0):
        """通知多模态向量化完成"""
        self.send_event(self.Events.MULTIVECTOR_COMPLETED, {
            "file_path": file_path,
            "task_id": task_id,
            "parent_chunks_count": parent_chunks_count,
            "child_chunks_count": child_chunks_count,
            "stage": "completed"
        })
    
    def multivector_failed(self, file_path: str, task_id: str, error_message: str, 
                          help_link: str = "", error_code: str = ""):
        """通知多模态向量化失败"""
        self.send_event(self.Events.MULTIVECTOR_FAILED, {
            "file_path": file_path,
            "task_id": task_id,
            "error_message": error_message,
            "help_link": help_link,
            "error_code": error_code,
            "stage": "failed"
        })

    # RAG相关便捷方法
    def rag_retrieval_result(self, query: str, sources: List[Dict[str, Any]], 
                           session_id: int = None, metadata: Dict[str, Any] = None):
        """通知RAG检索结果"""
        self.send_event(self.Events.RAG_RETRIEVAL_RESULT, {
            "query": query,
            "sources": sources,
            "sources_count": len(sources),
            "session_id": session_id,
            "metadata": metadata or {},
            "timestamp": time.time()
        })
    
    def rag_progress(self, query: str, stage: str, current: int = 0, total: int = 0, 
                    message: str = ""):
        """通知RAG处理进度"""
        self.send_event(self.Events.RAG_PROGRESS, {
            "query": query,
            "stage": stage,  # searching, ranking, formatting
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100, 2) if total > 0 else 0,
            "message": message,
            "timestamp": time.time()
        })
    
    def rag_error(self, query: str, error_message: str, stage: str = "", 
                 details: Dict[str, Any] = None):
        """通知RAG处理错误"""
        self.send_event(self.Events.RAG_ERROR, {
            "query": query,
            "error_message": error_message,
            "stage": stage,
            "details": details or {},
            "timestamp": time.time()
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
        
        # sender.file_processed("/test/path/file.txt", tags_count=5, status="completed")
        # time.sleep(1)
        
        sender.progress_update("parsing", 50, 100, "正在解析文件...")
        time.sleep(1)
        
        sender.error_occurred("parsing_error", "文件解析失败", {"file": "/test/error.txt"})
        time.sleep(1)
        
        sender.system_status("ready", "系统准备就绪", {"version": "1.0.0"})
        time.sleep(1)
        
        sender.model_validation_failed(
            provider_type="ollama",
            model_id="test-model",
            role_type="embedding",
            available_models=["qwen2.5:7b", "llama3.2:3b"],
            error_message="测试模型验证失败事件"
        )
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
    
    # 测试基本事件发送
    test_basic_events(bridge_events)
    
    # 测试自定义事件
    test_custom_events(bridge_events)

    # 模拟模型验证失败
    print("开始测试模型验证失败事件...")
    bridge_events.model_validation_failed(
        provider_type="ollama",
        model_id="nonexistent-model",
        role_type="base",
        available_models=[
            "qwen/qwen2.5-7b-instruct",
            "llama3.2:3b",
            "gemma2:9b"
        ],
        error_message="模型 'nonexistent-model' 在提供商 'ollama' 中不可用"
    )
    print("请检查前端是否收到 toast 通知")
    
    # All Done
    print("\n=== 测试完成 ===")
    print("如果Rust桥接正常工作，前端应该收到上述所有事件")
