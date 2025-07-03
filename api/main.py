import os
import sys
import argparse
import logging
import time
import pathlib
import asyncio
import threading
from datetime import datetime
import traceback
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from fastapi import FastAPI, Body, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from utils import kill_process_on_port, monitor_parent, kill_orphaned_processes
from sqlmodel import create_engine, Session, select
import multiprocessing
# 导入缓存相关模块
from api_cache_optimization import TimedCache, cached
from db_mgr import (
    DBManager, TaskStatus, TaskResult, TaskType, TaskPriority, 
    MyFiles, FileCategory, FileFilterRule, FileExtensionMap, ProjectRecognitionRule,
    Task,
)
from myfiles_mgr import MyFilesManager
from screening_mgr import ScreeningManager
from parsing_mgr import ParsingMgr
from task_mgr import TaskManager

# --- Centralized Logging Setup ---
def setup_logging():
    """Configures the root logger for the application."""
    try:
        # Determine log directory
        script_path = os.path.abspath(__file__)
        log_dir = pathlib.Path(script_path).parent / 'logs'
        if not log_dir.exists():
            current_dir = pathlib.Path(os.getcwd())
            log_dir = current_dir / 'api' / 'logs' if 'api' not in str(current_dir) else current_dir / 'logs'
        log_dir.mkdir(exist_ok=True, parents=True)

        log_filename = f'api_{time.strftime("%Y%m%d")}.log'
        log_filepath = log_dir / log_filename

        # Get the root logger and configure it
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Avoid adding duplicate handlers
        if not root_logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

            # File handler
            file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        
        logging.getLogger(__name__).info("Logging configured successfully.")

    except Exception as e:
        # Fallback to basic config if setup fails
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Error setting up custom logging: {e}", exc_info=True)

setup_logging()
# --- End Logging Setup ---

# Get a logger for this module
logger = logging.getLogger(__name__)

# 全局缓存实例
config_cache = TimedCache[Dict[str, Any]](expiry_seconds=300)  # 5分钟过期
folder_hierarchy_cache = TimedCache[List[Any]](expiry_seconds=180)  # 3分钟过期
bundle_ext_cache = TimedCache[List[str]](expiry_seconds=600)   # 10分钟过期

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 在应用启动时执行初始化操作
    logger.info("应用正在启动...")
    
    try:
        logger.info(f"调试信息: Python版本 {sys.version}")
        logger.info(f"调试信息: 当前工作目录 {os.getcwd()}")
        
        # 初始化数据库引擋
        if hasattr(app.state, "db_path"):
            sqlite_url = f"sqlite:///{app.state.db_path}"
            logger.info(f"初始化数据库引擎，URL: {sqlite_url}")
            try:
                # For SQLite, especially when accessed by FastAPI (which can use threads for async routes)
                # and potentially by background tasks, 'check_same_thread': False is often needed.
                # The set_sqlite_pragma event listener will configure WAL mode.
                app.state.engine = create_engine(
                    sqlite_url, 
                    echo=False, 
                    connect_args={"check_same_thread": False, "timeout": 30},
                    pool_size=5,       # 设置连接池大小
                    max_overflow=10,   # 允许的最大溢出连接数
                    pool_timeout=30,   # 获取连接的超时时间
                    pool_recycle=1800  # 30分钟回收一次连接
                )
                logger.info(f"数据库引擎已初始化，路径: {app.state.db_path}")
                
                # 初始化数据库结构
                try:
                    logger.info("开始初始化数据库结构...")
                    with Session(app.state.engine) as session:
                        db_mgr = DBManager(session)
                        db_mgr.init_db()
                    logger.info("数据库结构初始化完成")
                except Exception as init_err:
                    logger.error(f"初始化数据库结构失败: {str(init_err)}", exc_info=True)
                    # 继续运行应用，不要因为初始化失败而中断
                    # 可能是因为表已经存在，这种情况是正常的
            except Exception as db_err:
                logger.error(f"初始化数据库引擎失败: {str(db_err)}", exc_info=True)
                raise
        else:
            logger.warning("未设置数据库路径，数据库引擎未初始化")
        
        # 先清理可能存在的孤立子进程
        try:
            logger.info("清理可能存在的孤立子进程...")
            kill_orphaned_processes("python", "task_processor")
        except Exception as proc_err:
            logger.error(f"清理孤立进程失败: {str(proc_err)}", exc_info=True)
        
        # 初始化后台任务处理线程
        try:
            logger.info("初始化后台任务处理线程...")
            # 创建一个事件来优雅地停止线程
            app.state.task_processor_stop_event = threading.Event()
            app.state.task_processor_thread = threading.Thread(
                target=task_processor,
                args=(app.state.db_path, app.state.task_processor_stop_event),
                daemon=True
            )
            app.state.task_processor_thread.start()
            logger.info("后台任务处理线程已启动")
        except Exception as e:
            logger.error(f"初始化后台任务处理线程失败: {e}", exc_info=True)
            raise
        
        # 启动通知检查任务
        try:
            logger.info("启动通知检查任务...")
            asyncio.create_task(check_notifications())
        except Exception as notify_err:
            logger.error(f"启动通知检查任务失败: {str(notify_err)}", exc_info=True)
            
        # Start monitor can kill self process if parent process is dead or exit
        try:
            logger.info("启动父进程监控线程...")
            monitor_thread = threading.Thread(target=monitor_parent, daemon=True)
            monitor_thread.start()
            logger.info("父进程监控线程已启动")
        except Exception as monitor_err:
            logger.error(f"启动父进程监控线程失败: {str(monitor_err)}", exc_info=True)

        # 正式开始服务
        logger.info("应用初始化完成，开始提供服务...")
        yield
    except Exception as e:
        logger.critical(f"应用启动过程中发生严重错误: {str(e)}", exc_info=True)
        # 确保异常传播，这样FastAPI会知道启动失败
        raise
    finally:
        # 退出前的清理工作
        logger.info("应用开始关闭...")
        
        try:
            if hasattr(app.state, "task_processor_thread") and app.state.task_processor_thread.is_alive():
                logger.info("正在停止后台任务处理线程...")
                app.state.task_processor_stop_event.set()
                app.state.task_processor_thread.join(timeout=5) # 等待5秒
                if app.state.task_processor_thread.is_alive():
                    logger.warning("后台任务处理线程在5秒内未停止")
                else:
                    logger.info("后台任务处理线程已停止")
        except Exception as e:
            logger.error(f"停止后台任务处理线程失败: {e}", exc_info=True)
        
        # 在应用关闭时执行清理操作
        try:
            if hasattr(app.state, "engine") and app.state.engine is not None:
                logger.info("释放数据库连接池...")
                app.state.engine.dispose()  # 释放数据库连接池
                logger.info("数据库连接池已释放")
        except Exception as db_close_err:
            logger.error(f"关闭数据库连接失败: {str(db_close_err)}", exc_info=True)
        
        logger.info("应用已完全关闭")

app = FastAPI(lifespan=lifespan)
origins = [
    "http://localhost:1420",  # Your Tauri dev server
    "tauri://localhost",      # Often used by Tauri in production
    "https://tauri.localhost" # Also used by Tauri in production
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specific origins
    # allow_origins=["*"], # Or, to allow all origins (less secure, use with caution)
    allow_credentials=True, # Allows cookies to be included in requests
    allow_methods=["*"],    # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allows all headers
)

# 存储活跃的WebSocket连接
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()
# 周期性检查新通知并广播
async def check_notifications():
    while True:
        # 广播消息
        # await manager.broadcast("New notification")
        await asyncio.sleep(8)

def get_session():
    """FastAPI依赖函数，用于获取数据库会话"""
    if not hasattr(app.state, "engine") or app.state.engine is None:
        # 确保数据库引擎已初始化
        raise RuntimeError("数据库引擎未初始化")
    
    with Session(app.state.engine) as session:
        yield session


# # 本地大模型API端点添加
from models_api import get_router as get_models_router
models_router = get_models_router(external_get_session=get_session)
app.include_router(models_router, prefix="", tags=["local-models"])

# 获取 MyFilesManager 的依赖函数
def get_myfiles_manager(session: Session = Depends(get_session)):
    """获取文件/文件夹管理器实例"""
    return MyFilesManager(session)

@app.post("/init_db")
def init_db(session: Session = Depends(get_session)):
    """首次打开App，初始化数据库结构"""
    logger.info("初始化数据库结构")
    db_mgr = DBManager(session)
    db_mgr.init_db()

    return {"message": "数据库结构已初始化"}

# 获取所有配置信息的API端点
@app.get("/config/all")
async def get_all_configuration(
    session: Session = Depends(get_session),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """
    获取所有Rust端进行文件处理所需的配置信息。
    包括文件分类、粗筛规则、文件扩展名映射、项目识别规则以及监控的文件夹列表。
    现在使用缓存机制提高性能，减少数据库查询。
    """
    try:
        # 使用异步超时控制
        try:
            return await asyncio.wait_for(
                _get_all_configuration_async(session, myfiles_mgr), 
                timeout=5.0  # 设置5秒超时
            )
        except asyncio.TimeoutError:
            logger.error("获取配置超时，返回缓存数据或空结果")
            # 尝试从缓存获取
            hit, cached_value = config_cache.get("config_all")
            if hit:
                logger.info("使用缓存数据响应超时请求")
                return cached_value
            # 没有缓存，返回空结果
            raise Exception("获取配置超时")
    except Exception as e:
        logger.error(f"Error fetching all configuration: {e}", exc_info=True)
        # Return a default structure in case of error to prevent client-side parsing issues.
        # The client can check for the presence of 'error_message' or if data arrays are empty.
        return {
            "file_categories": [],
            "file_filter_rules": [],
            "file_extension_maps": [],
            "project_recognition_rules": [],
            "monitored_folders": [],
            "full_disk_access": False,  # Default to false on error
            "error_message": f"Failed to fetch configuration: {str(e)}"
        }

async def _get_all_configuration_async(session: Session, myfiles_mgr: MyFilesManager):
    """异步包装缓存函数，用于超时控制"""
    return _get_all_configuration_cached(session, myfiles_mgr)

@cached(config_cache, "config_all")
def _get_all_configuration_cached(session: Session, myfiles_mgr: MyFilesManager):
    """缓存版本的配置获取函数"""
    start_time = time.time()
    file_categories = session.exec(select(FileCategory)).all()
    file_filter_rules = session.exec(select(FileFilterRule)).all()
    file_extension_maps = session.exec(select(FileExtensionMap)).all()
    project_recognition_rules = session.exec(select(ProjectRecognitionRule)).all()
    monitored_folders = session.exec(select(MyFiles)).all()
    
    # 检查完全磁盘访问权限状态 
    full_disk_access = False
    if sys.platform == "darwin":  # macOS
        access_status = myfiles_mgr.check_full_disk_access_status()
        full_disk_access = access_status.get("has_full_disk_access", False)
        logger.info(f"[CONFIG] Full disk access status: {full_disk_access}")
    
    elapsed = time.time() - start_time
    logger.info(f"[CONFIG] 获取所有配置耗时 {elapsed:.3f}s (从数据库)")
    
    # 获取 bundle 扩展名列表（直接从数据库获取，不使用正则规则）
    bundle_extensions = myfiles_mgr.get_bundle_extensions_for_rust()
    logger.info(f"[CONFIG] 获取到 {len(bundle_extensions)} 个 bundle 扩展名")
    from parsing_mgr import PARSEABLE_EXTENSIONS  # 确保解析器扩展名已加载
    return {
        "file_categories": file_categories,
        "file_filter_rules": file_filter_rules,
        "file_extension_maps": file_extension_maps,
        "project_recognition_rules": project_recognition_rules,
        "monitored_folders": monitored_folders,
        "parsable_extensions": PARSEABLE_EXTENSIONS,
        "full_disk_access": full_disk_access,  # 完全磁盘访问权限状态
        "bundle_extensions": bundle_extensions  # 添加直接可用的 bundle 扩展名列表
    }

# 任务处理者
def task_processor(db_path: str, stop_event: threading.Event):
    """处理任务的后台工作线程"""
    logger.info(f"任务处理线程已启动")
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(
        sqlite_url, 
        echo=False, 
        connect_args={"check_same_thread": False, "timeout": 30}
    )
    
    while not stop_event.is_set():
        try:
            with Session(engine) as session:
                task_mgr = TaskManager(session)
                task = task_mgr.get_next_task()

                if not task:
                    time.sleep(5) # 没有任务时，等待5秒
                    continue

                logger.info(f"任务处理线程接收任务: ID={task.id}, Name='{task.task_name}', Type='{task.task_type}'")
                task_mgr.update_task_status(task.id, TaskStatus.RUNNING)

                if task.task_type == TaskType.PARSING.value:
                    parsing_mgr = ParsingMgr(session)
                    logger.info(f"开始批量解析任务 (Task ID: {task.id})")
                    result_data = parsing_mgr.process_all_pending_parsing_results()
                    
                    if result_data.get("success", False):
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.COMPLETED, 
                            result=TaskResult.SUCCESS, 
                            message=f"成功处理 {result_data.get('processed', 0)} 个文件，成功: {result_data.get('success_count', 0)}, 失败: {result_data.get('failed_count', 0)}"
                        )
                    else:
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.FAILED, 
                            result=TaskResult.FAILURE, 
                            message=f"批量解析失败: {result_data.get('error', '未知错误')}"
                        )
                else:
                    logger.warning(f"未��的任务类型: {task.task_type} for task ID: {task.id}")
                    task_mgr.update_task_status(task.id, TaskStatus.FAILED, result=TaskResult.FAILURE, message=f"Unknown task type: {task.task_type}")

        except Exception as e:
            logger.error(f"任务处理线程发生意外错误: {e}", exc_info=True)
            # 发生严重错误时，等待更长时间避免刷爆日志
            time.sleep(30)

    logger.info("任务处理线程已停止")

# 获取 ScreeningManager 的依赖函数
def get_screening_manager(session: Session = Depends(get_session)):
    """获取文件粗筛结果管理类实例"""
    return ScreeningManager(session)

# 获取 ParsingMgr 的依赖函数
def get_parsing_manager(session: Session = Depends(get_session)):
    """获取文件解析管理类实例"""
    return ParsingMgr(session)

# 获取 TaskManager 的依赖函数
def get_task_manager(session: Session = Depends(get_session)):
    """获取任务管理器实例"""
    return TaskManager(session)

# 为单个文件创建解析任务
@app.post("/tasks/parse")
def create_parse_task(
    file_path: str,
    parsing_mgr: ParsingMgr = Depends(get_parsing_manager)
):
    """为单个文件创建解析任务

    Args:
        file_path: 文件路径

    Returns:
        任务ID
    """
    try:
        task_id = parsing_mgr.create_rough_parse_task(file_path)
        return {
            "success": True,
            "task_id": task_id
        }
    except Exception as e:
        logger.error(f"创建解析任务失败: {str(e)}")
        return {
            "success": False,
            "message": f"创建解析任务失败: {str(e)}"
        }

# 获取最新的指定类型任务
@app.get("/tasks/latest/{task_type}")
def get_latest_task(
    task_type: str,
    task_mgr: TaskManager = Depends(get_task_manager)
):
    """获取最新的指定类型任务
    
    Args:
        task_type: 任务类型
        
    Returns:
        最新任务信息
    """
    try:
        if task_type not in [t.value for t in TaskType]:
            raise ValueError(f"不支持的任务类型: {task_type}")
        
        # 查询最新的已完成任务
        latest_task = task_mgr.get_latest_completed_task(task_type)
        
        if not latest_task:
            # 如果没有已完成的任务，尝试查找正在运行的任务
            running_task = task_mgr.get_latest_running_task(task_type)
            if running_task:
                return {
                    "success": True,
                    "task_id": str(running_task.id),
                    "status": running_task.status,
                    "created_at": running_task.created_at,
                    "message": "任务正在运行中"
                }
            else:
                # 如果没有正在运行的任务，查找最新的任务（无论状态如何）
                any_task = task_mgr.get_latest_task(task_type)
                if any_task:
                    return {
                        "success": True,
                        "task_id": str(any_task.id),
                        "status": any_task.status,
                        "created_at": any_task.created_at,
                        "message": f"找到一个状态为 {any_task.status} 的任务"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"未找到任何 {task_type} 类型的任务"
                    }
        
        return {
            "success": True,
            "task_id": str(latest_task.id),
            "status": latest_task.status,
            "created_at": latest_task.created_at
        }
    except Exception as e:
        logger.error(f"获取最新任务时出错: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"获取最新任务失败: {str(e)}"
        }

@app.post("/tasks/start-initial-parsing")
def start_initial_parsing(task_mgr: TaskManager = Depends(get_task_manager)):
    """由Rust在首次全盘扫描后调用，以触发内容解析和打标签任务"""
    try:
        # 检查是否已有正在运行或待处理的解析任务
        existing_task = task_mgr.get_latest_task(TaskType.PARSING.value)
        if existing_task and existing_task.status in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
            logger.info(f"已存在一个正在进行中的解析任务 (ID: {existing_task.id}, Status: {existing_task.status})，无需创建新任务。")
            return {
                "success": True,
                "task_id": existing_task.id,
                "message": "已存在一个正在进行中的解析任务，无需创建新任务。"
            }

        # 创建一个新的解析任务作为“信号”
        task = task_mgr.add_task(
            task_name="Initial-Parsing-Trigger",
            task_type=TaskType.PARSING.value,
            priority=TaskPriority.LOW.value, # 首次全盘扫描后的解��，使用低优先级
            extra_data={"trigger": "initial_scan_complete"}
        )
        logger.info(f"已创建首次解析的触发任务，ID: {task.id}")
        return {
            "success": True,
            "task_id": task.id,
            "message": "首次解析任务已成功触发。"
        }
    except Exception as e:
        logger.error(f"触发首次解析任务失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}

# 添加用于处理文件粗筛结果的 API 接口
@app.post("/file-screening")
def add_file_screening_result(
    data: Dict[str, Any] = Body(...), 
    screening_mgr: ScreeningManager = Depends(get_screening_manager),
    task_mgr: TaskManager = Depends(lambda session=Depends(get_session): TaskManager(session))
):
    """添加单个文件粗筛结果，并可选地创建后续处理任务
    
    参数:
    - file_path: 文件路径
    - file_name: 文件名
    - file_size: 文件大小（字节）
    - extension: 扩展名（不含点）
    - file_hash: 文件哈希（可选）
    - created_time: 文件创建时间（可选）
    - modified_time: 文件修改时间
    - accessed_time: 文件访问时间（可选）
    - category_id: 分类ID（可选）
    - matched_rules: 匹配的规则ID列表（可选）    
    - metadata: 其他元数据（可选）
    - labels: 标牌列表（可选）
    - auto_create_task: 是否自动创建任务（默认 True）
    """
    try:
        # 处理Unix时间戳（从Rust发送的秒数转换为Python datetime）
        for time_field in ["created_time", "modified_time", "accessed_time"]:
            if time_field in data and isinstance(data[time_field], (int, float)):
                data[time_field] = datetime.fromtimestamp(data[time_field])
                
        # 处理字符串格式的时间字段
        for time_field in ["created_time", "modified_time", "accessed_time"]:
            if time_field in data and isinstance(data[time_field], str):
                try:
                    data[time_field] = datetime.fromisoformat(data[time_field].replace("Z", "+00:00"))
                except Exception as e:
                    logger.warning(f"转换时间字段 {time_field} 失败: {str(e)}")
                    # 如果是修改时间字段转换失败，设置为当前时间
                    if time_field == "modified_time":
                        data[time_field] = datetime.now()
        
        # 确保必填字段有值
        if "modified_time" not in data or data["modified_time"] is None:
            data["modified_time"] = datetime.now()
        
        # Ensure 'extra_metadata' is used, but allow 'metadata' for backward compatibility from client
        if "metadata" in data and "extra_metadata" not in data:
            data["extra_metadata"] = data.pop("metadata")

        # 添加粗筛结果
        # The screening_mgr.add_screening_result will now expect 'extra_metadata'
        result = screening_mgr.add_screening_result(data)
        if not result:
            return {
                "success": False,
                "message": "添加文件粗筛结果失败"
            }
        
        # 检查是否需要自动创建任务
        auto_create_task = data.get("auto_create_task", True)
        if auto_create_task and result.status == "pending":
            # 创建一个处理此文件的任务
            task_name = f"处理文件: {result.file_name}"
            
            # 这里我们使用解析任务类型统一处理
            # 并将单一文件任务也设置为高优先级，确保优先处理单一文件任务
            task = task_mgr.add_task(
                task_name=task_name,
                task_type=TaskType.PARSING.value,  # 使用解析任务类型，与批处理保持一致
                priority=TaskPriority.HIGH.value,  # 高优先级
                extra_data={"screening_result_id": result.id}  # 关联粗筛结果ID
            )
            
            # 更新粗筛结果，关联任务ID
            screening_mgr.update_screening_result(
                result_id=result.id,
                data={"task_id": task.id}
            )
            
            return {
                "success": True,
                "screening_result_id": result.id,
                "task_id": task.id,
                "message": "文件粗筛结果已添加，并创建了处理任务"
            }
        
        return {
            "success": True,
            "screening_result_id": result.id,
            "message": "文件粗筛结果已添加"
        }
        
    except Exception as e:
        logger.error(f"处理文件粗筛结果失败: {str(e)}")
        return {
            "success": False,
            "message": f"处理失败: {str(e)}"
        }

@app.post("/file-screening/batch")
def add_batch_file_screening_results(
    request: Dict[str, Any] = Body(...), 
    screening_mgr: ScreeningManager = Depends(get_screening_manager),
    task_mgr: TaskManager = Depends(lambda session=Depends(get_session): TaskManager(session))
):
    """批量添加文件粗筛结果
    
    参数:
    - data_list: 文件粗筛结果列表
    """
    try:
        # 从请求体中提取数据和参数
        logger.info(f"接收到批量文件粗筛结果，请求体键名: {list(request.keys())}")
        
        # 适配Rust客户端发送的格式: {data_list: [...], auto_create_tasks: true}
        if "data_list" in request:
            data_list = request.get("data_list", [])
        elif isinstance(request, dict):
            data_list = request.get("files", [])
        else:
            # 假设请求体本身就是列表
            data_list = request
            
        if not data_list:
            return {"success": True, "processed_count": 0, "failed_count": 0, "message": "没有需要处理的文件"}

        # 预处理每个文件记录中的时间戳，转换为Python datetime对象
        for data in data_list:
            # 处理Unix时间戳的转换 (从Rust发送的秒数转换为Python datetime)
            if "created_time" in data and isinstance(data["created_time"], (int, float)):
                data["created_time"] = datetime.fromtimestamp(data["created_time"])
                
            if "modified_time" in data and isinstance(data["modified_time"], (int, float)):
                data["modified_time"] = datetime.fromtimestamp(data["modified_time"])
                
            if "accessed_time" in data and isinstance(data["accessed_time"], (int, float)):
                data["accessed_time"] = datetime.fromtimestamp(data["accessed_time"])
        
        # 处理字符串格式的时间字段（处理之前已经先处理了整数时间戳）
        for data in data_list:
            for time_field in ["created_time", "modified_time", "accessed_time"]:
                # 只处理仍然是字符串格式的时间字段（整数时间戳已在前一步转换）
                if time_field in data and isinstance(data[time_field], str):
                    try:
                        data[time_field] = datetime.fromisoformat(data[time_field].replace("Z", "+00:00"))
                    except Exception as e:
                        logger.warning(f"转换字符串时间字段 {time_field} 失���: {str(e)}")
                        # 如果是修改时间字段转换失败，设置为当前时间
                        if time_field == "modified_time":
                            data[time_field] = datetime.now()
                
                # 确保每个时间字段都有值，对于必填字段
                if time_field == "modified_time" and (time_field not in data or data[time_field] is None):
                    logger.warning(f"缺少必填时间字段 {time_field}，使用当前时间")
                    data[time_field] = datetime.now()
                            
            # Ensure 'extra_metadata' is used, but allow 'metadata' for backward compatibility from client
            if "metadata" in data and "extra_metadata" not in data:
                data["extra_metadata"] = data.pop("metadata")

        # 1. 先创建任务，获取 task_id
        task_name = f"批量处理文件: {len(data_list)} 个文件"
        task = task_mgr.add_task(
            task_name=task_name,
            task_type=TaskType.PARSING.value,
            priority=TaskPriority.HIGH.value,
            extra_data={"file_count": len(data_list)}
        )
        logger.info(f"已创建解析任务 ID: {task.id}，准备处理 {len(data_list)} 个文件")

        # 2. 批��添加粗筛结果，并关联 task_id
        result = screening_mgr.add_batch_screening_results(data_list, task_id=task.id)
        
        # 3. 返回结果
        if result["success"] > 0:
            message = f"已为 {result['success']} 个文件创建处理任务，失败 {result['failed']} 个"
        else:
            message = f"未能处理任何文件，失败 {result['failed']} 个"

        return {
            "success": result["success"] > 0,
            "processed_count": result["success"],
            "failed_count": result["failed"],
            "errors": result.get("errors"),
            "task_id": task.id,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"批量处理文件粗筛结果失败: {str(e)}")
        return {
            "success": False,
            "message": f"批量处理失败: {str(e)}"
        }

@app.get("/file-screening/results")
def get_file_screening_results(
    limit: int = 1000,
    category_id: int = None,
    time_range: str = None,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """获取文件粗筛结果列表，支持按分类和时间范围筛选
    
    参数:
    - limit: 最大返回结果数
    - category_id: 可选，按文件分类ID过滤
    - time_range: 可选，按时间范围过滤 ("today", "last7days", "last30days")
    """
    try:
        from datetime import datetime, timedelta
        
        # 基础查询
        results = screening_mgr.get_all_results(limit)
        
        # 如果结果为空，直接返回空列表，防止后续处理出错
        if not results:
            return {
                "success": True,
                "count": 0,
                "data": []
            }
        
        # 转换为可序列化字典列表
        results_dict = [result.model_dump() for result in results]
        
        # 过滤逻辑
        filtered_results = results_dict
        
        # 按分类过滤
        if (category_id is not None):
            filtered_results = [r for r in filtered_results if r.get('category_id') == category_id]
        
        # 按时间范围过滤
        if time_range:
            now = datetime.now()
            # Ensure modified_time is a string before parsing
            date_format = "%Y-%m-%d %H:%M:%S" # Define the correct format

            if time_range == "today":
                today = datetime(now.year, now.month, now.day)
                filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= today]
            elif time_range == "last7days":
                week_ago = now - timedelta(days=7)
                filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= week_ago]
            elif time_range == "last30days":
                month_ago = now - timedelta(days=30)
                filtered_results = [r for r in filtered_results if r.get('modified_time') and datetime.strptime(r.get('modified_time'), date_format) >= month_ago]
        
        return {
            "success": True,
            "count": len(filtered_results),
            "data": filtered_results
        }
        
    except Exception as e:
        logger.error(f"获取文件粗筛结果列表失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"获取失败: {str(e)}"
        }

@app.get("/file-screening/pending")
def get_pending_file_screenings(
    limit: int = 500,  # 增加默认返回数量
    category_id: int = None,  # 添加分类过滤
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """获取待处理的文件粗筛结果列表
    
    参数:
    - limit: 最大返回结果数量
    - category_id: 可选，按文件分类ID过滤
    """
    try:
        # 获取待处理结果
        results = screening_mgr.get_pending_results(limit)
        
        # 如果结果为空，直接返回
        if not results:
            return {
                "success": True,
                "count": 0,
                "data": []
            }
            
        # 将模型对象列表转换为可序列化的字典列表
        results_dict = [result.model_dump() for result in results]
        
        # 按分类过滤（如果指定）
        if category_id is not None:
            results_dict = [r for r in results_dict if r.get('category_id') == category_id]
        
        logger.info(f"找到 {len(results_dict)} 个待处理的文件粗筛结果")
        
        return {
            "success": True,
            "count": len(results_dict),
            "data": results_dict
        }
        
    except Exception as e:
        logger.error(f"获取待处理文件粗筛结果列表失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"获取待处理粗筛结果失败: {str(e)}"
        }

# 添加在适当的位置，比如在 get_file_screening_results 函数后面

@app.get("/file-screening/by-time-range/{time_range}")
def get_files_by_time_range(
    time_range: str,
    limit: int = 500,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """根据时间范围获取文件
    
    参数:
    - time_range: 时间范围 ("today", "last7days", "last30days")
    - limit: 最大返回结果数量
    """
    try:
        # 验证时间范围参数
        valid_time_ranges = ["today", "last7days", "last30days"]
        if time_range not in valid_time_ranges:
            logger.warning(f"请求了无效的时间范围: {time_range}")
            return {
                "success": False,
                "message": f"无效的时间范围: {time_range}，有效值为: {valid_time_ranges}"
            }
            
        # 开始计时，用于性能监控
        start_time = time.time()
        
        # 调用 ScreeningManager 中的方法获取数据
        files = screening_mgr.get_files_by_time_range(time_range, limit)
        
        # 计算查询耗时
        query_time = time.time() - start_time
        
        logger.info(f"按时间范围 {time_range} 查询到 {len(files)} 个文件，耗时 {query_time:.3f} 秒")
        
        return {
            "success": True,
            "count": len(files),
            "query_time_ms": int(query_time * 1000),
            "data": files
        }
    except Exception as e:
        logger.error(f"按时间范围获取文件失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"查询失败: {str(e)}"
        }

@app.get("/file-screening/by-category/{category_type}")
def get_files_by_category(
    category_type: str,
    limit: int = 500,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """根据文件分类类型获取文件
    
    参数:
    - category_type: 分类类型 ("image", "audio-video", "archive", 等)
    - limit: 最大返回结果数量
    """
    try:
        # 文件类型和分类ID的映射
        category_mapping = {
            "image": 2,       # 图片的分类ID
            "audio-video": 3, # 音视频的分类ID
            "archive": 4,     # 归档文件的分类ID
            "document": 1     # 文档的分类ID
        }
        
        # 检查类型是否有效
        if category_type not in category_mapping:
            logger.warning(f"请求了无效的分类类型: {category_type}")
            return {
                "success": False,
                "message": f"无效的分类类型: {category_type}，有效值为: {list(category_mapping.keys())}"
            }
            
        # 开始计时，用于性能监控
        start_time = time.time()
        
        # 获取对应的分类ID
        category_id = category_mapping[category_type]
        
        # 调用 ScreeningManager 中的方法获取数据
        files = screening_mgr.get_files_by_category_id(category_id, limit)
        
        # 计算查询耗时
        query_time = time.time() - start_time
        
        logger.info(f"按分类 {category_type} (ID: {category_id}) 查询到 {len(files)} 个文件，耗时 {query_time:.3f} 秒")
        
        return {
            "success": True,
            "count": len(files),
            "query_time_ms": int(query_time * 1000),
            "data": files
        }
    except Exception as e:
        logger.error(f"按分类获取文件失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"查询失败: {str(e)}"
        }

# 将带参数的路由移到最后，避免与特定路由冲突
@app.get("/file-screening/{screening_id}")
def get_file_screening_result(
    screening_id: int,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """获取单个文件粗筛结果"""
    try:
        result = screening_mgr.get_by_id(screening_id)
        if not result:
            return {
                "success": False,
                "message": f"未找到ID为 {screening_id} 的文件粗筛结果"
            }
        
        # 将模型对象转换为可序列化的字典
        result_dict = result.model_dump()
        
        return {
            "success": True,
            "data": result_dict
        }
        
    except Exception as e:
        logger.error(f"获取文件粗筛结果失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取失败: {str(e)}"
        }

@app.put("/file-screening/{screening_id}/status")
def update_file_screening_status(
    screening_id: int,
    status_data: Dict[str, Any] = Body(...),
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """更新文件粗筛结果状态
    
    参数:
    - status: 新状态，可选值: "pending", "processed", "ignored", "failed"
    - error_message: 错误信息（如果状态为 "failed"）
    """
    try:
        from db_mgr import FileScreenResult
        
        status_str = status_data.get("status")
        error_message = status_data.get("error_message")
        
        # 验证状态值是否有效
        try:
            status = FileScreenResult(status_str)
        except ValueError:
            return {
                "success": False,
                "message": f"无效的状态值: {status_str}"
            }
        
        # 更新状态
        success = screening_mgr.update_status(screening_id, status, error_message)
        
        if not success:
            return {
                "success": False,
                "message": f"更新ID为 {screening_id} 的文件粗筛结果状态失败"
            }
        
        return {
            "success": True,
            "message": f"已将ID为 {screening_id} 的文件粗筛结果状态更新为 {status_str}"
        }
        
    except Exception as e:
        logger.error(f"更新文件粗筛结果状态失败: {str(e)}")
        return {
            "success": False,
            "message": f"更新失败: {str(e)}"
        }

@app.get("/file-screening/similar")
def find_similar_files(
    file_hash: str = None,
    file_name: str = None,
    exclude_path: str = None,
    limit: int = 10,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """查找相似文件
    
    可以根据文件哈希值或文件名查找相似文件。优先使用哈希值查找，如果没有指定哈希值则使用文件名。
    
    参数:
    - file_hash: 文件哈希值（可选）
    - file_name: 文件名（可选，当file_hash未提供时使用）
    - exclude_path: 要排除的文件路径（通常是原始文件路径）
    - limit: 返回结果的最大数量
    """
    try:
        if not file_hash and not file_name:
            return {
                "success": False,
                "message": "必须提供file_hash或file_name参数"
            }
        
        # 优先使用哈希值查找（精确匹配）
        if file_hash:
            results = screening_mgr.find_similar_files_by_hash(file_hash, exclude_path, limit)
            search_type = "hash"
        else:
            results = screening_mgr.find_similar_files_by_name(file_name, exclude_path, limit)
            search_type = "name"
        
        # 转换为可序列化字典列表
        results_dict = [result.model_dump() for result in results]
        
        logger.info(f"根据{search_type}查找到 {len(results_dict)} 个相似文件")
        
        return {
            "success": True,
            "count": len(results_dict),
            "search_type": search_type,
            "data": results_dict
        }
        
    except Exception as e:
        logger.error(f"查找相似文件失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"查找失败: {str(e)}"
        }

@app.get("/")
def read_root():
    # 现在可以在任何路由中使用 app.state.db_path
    return {"Hello": "World", "db_path": app.state.db_path}

# 添加健康检查端点
@app.get("/health")
def health_check():
    """API健康检查端点，用于验证API服务是否正常运行"""
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat(),
        "cache_stats": {
            "config": config_cache.get_stats(),
            "folders": folder_hierarchy_cache.get_stats()
        }
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（可选，因为这阶段产品设计只用websocket向前端推送通知）
            _ = await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 添加文件夹管理相关API
@app.get("/directories")
def get_directories(
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    try:
        # 根据系统平台设置 full_disk_access 状态
        # 只在 macOS 上才有意义
        fda_status = False
        if sys.platform == "darwin":  # macOS
            # 在 macOS 上，检查应用是否有完全磁盘访问权限
            access_status = myfiles_mgr.check_full_disk_access_status()
            fda_status = access_status.get("has_full_disk_access", False)
            logger.info(f"[API DEBUG] Full disk access status: {fda_status}, details: {access_status}")

        # 使用 select 语句从数据库获取所有监控的目录
        stmt = select(MyFiles)
        directories_from_db = myfiles_mgr.session.exec(stmt).all()
        
        processed_dirs = []
        for d in directories_from_db:
            dir_dict = {
                "id": getattr(d, 'id', None),
                "path": getattr(d, 'path', None),
                "alias": getattr(d, 'alias', None),
                "is_blacklist": getattr(d, 'is_blacklist', False),
                "created_at": d.created_at.isoformat() if getattr(d, 'created_at', None) else None,
                "updated_at": d.updated_at.isoformat() if getattr(d, 'updated_at', None) else None,
            }
            processed_dirs.append(dir_dict)
        
        logger.info(f"[API DEBUG] /directories returning: fda_status={fda_status}, num_dirs={len(processed_dirs)}")
        return {"status": "success", "full_disk_access": fda_status, "data": processed_dirs}
    except Exception as e:
        logger.error(f"Error in get_directories: {e}", exc_info=True)
        return {"status": "error", "full_disk_access": False, "data": [], "message": str(e)}

@app.post("/directories")
def add_directory(
    data: Dict[str, Any] = Body(...),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """添加新文件夹"""
    try:
        path = data.get("path", "")
        alias = data.get("alias", "")
        is_blacklist = data.get("is_blacklist", False)
        
        if not path: # 修正：之前是 if name或not path:
            return {"status": "error", "message": "路径不能为空"}
        
        success, message_or_dir = myfiles_mgr.add_directory(path, alias, is_blacklist)
        
        if success:
            # 清除相关缓存
            invalidate_config_caches()
            logger.info(f"[CACHE] 已清除缓存，因为添加了新文件夹: {path}")
            
            # 检查返回值是否是字符串或MyFiles对象
            if isinstance(message_or_dir, str):
                return {"status": "success", "message": message_or_dir}
            else:
                # 如果是MyFiles对象，调用model_dump()
                
                # 如果不是黑名单，前端会立即启动Rust监控
                if not is_blacklist:
                    # 添加Rust监控的触发信号（通过WebSocket通知前端或通过某种机制）
                    # 此处日志记录即可，实际监控由前端Tauri通过fetch_and_store_all_config获取最新配置
                    logger.info(f"[MONITOR] 新文件夹已添加，需要立即启动监控: {path}")
                    
                return {"status": "success", "data": message_or_dir.model_dump(), "message": "文件夹添加成功"}
        else:
            return {"status": "error", "message": message_or_dir}
    except Exception as e:
        logger.error(f"添加文件夹失败: {str(e)}")
        return {"status": "error", "message": f"添加文件夹失败: {str(e)}"}

@app.put("/directories/{directory_id}")
def update_directory(
    directory_id: int,
    data: Dict[str, Any] = Body(...),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """更新文件夹的信息"""
    try:
        # 这里可以添加更新文件夹其他信息的逻辑
        return {"status": "success", "message": "文件夹信息更新成功"}
    except Exception as e:
        logger.error(f"更新文件夹信息失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"更新文件夹信息失败: {str(e)}"}

@app.put("/directories/{directory_id}/blacklist")
def toggle_directory_blacklist(
    directory_id: int,
    data: Dict[str, Any] = Body(...), # 包含 is_blacklist: bool
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """切换文件夹的黑名单状态"""
    try:
        is_blacklist = data.get("is_blacklist")
        if not isinstance(is_blacklist, bool):
            return {"status": "error", "message": "无效的黑名单状态参数"}

        success, message_or_dir = myfiles_mgr.toggle_blacklist(directory_id, is_blacklist)
        if success:
            # 清除相关缓存
            invalidate_config_caches()
            logger.info(f"[CACHE] 已清除缓存，因为切换了文件夹 {directory_id} 的黑名单状态为 {is_blacklist}")
            return {"status": "success", "data": message_or_dir.model_dump(), "message": "黑名单状态更新成功"}
        else:
            return {"status": "error", "message": message_or_dir}
    except Exception as e:
        logger.error(f"切换文件夹黑名单状态失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"切换文件夹黑名单状态失败: {str(e)}"}

@app.delete("/directories/{directory_id}")
def delete_directory(
    directory_id: int,
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """删除文件夹"""
    try:
        success, message = myfiles_mgr.remove_directory(directory_id)
        if success:
            # 清除相关缓存
            invalidate_config_caches()
            logger.info(f"[CACHE] 已清除缓存，因为删除了文件夹 {directory_id}")
            return {"status": "success", "message": "文件夹删除成功"}
        else:
            return {"status": "error", "message": message}
    except Exception as e:
        logger.error(f"删除文件夹失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"删除文件夹失败: {str(e)}"}

@app.put("/directories/{directory_id}/alias")
def update_directory_alias(
    directory_id: int,
    data: Dict[str, Any] = Body(...), # 包含 alias: str
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """更新文件夹的别名"""
    try:
        alias = data.get("alias")
        if alias is None: # 允许空字符串作为别名，但不允许None
            return {"status": "error", "message": "别名不能为空"}

        success, message_or_dir = myfiles_mgr.update_alias(directory_id, alias)
        if success:
            return {"status": "success", "data": message_or_dir.model_dump(), "message": "别名更新成功"}
        else:
            return {"status": "error", "message": message_or_dir}
    except Exception as e:
        logger.error(f"更新文件夹别名失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"更新文件夹别名失败: {str(e)}"}

# 在文件末尾添加以下端点，用于初始化默认文件夹和获取权限提示
@app.get("/directories/default")
def initialize_default_directories_endpoint(myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)):
    """初始化默认系统文件夹"""
    try:
        count = myfiles_mgr.initialize_default_directories()
        return {"status": "success", "message": f"成功初始化/检查了 {count} 个默认文件夹。"}
    except Exception as e:
        logger.error(f"初始化默认文件夹失败: {str(e)}")
        return {"status": "error", "message": f"初始化默认文件夹失败: {str(e)}"}

@app.get("/directories/default-list")
def get_default_directories_list(myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)):
    """获取默认系统文件夹列表（不进行数据库操作）"""
    try:
        directories = myfiles_mgr.get_default_directories()
        return {"status": "success", "data": directories}
    except Exception as e:
        logger.error(f"获取默认文件夹列表失败: {str(e)}")
        return {"status": "error", "message": f"获取默认文件夹列表失败: {str(e)}"}

@app.get("/macos-permissions-hint")
def get_macos_permissions_hint_endpoint(myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)):
    """获取 macOS 权限提示"""
    try:
        hint = myfiles_mgr.get_macOS_permissions_hint()
        return {"status": "success", "data": hint}
    except Exception as e:
        logger.error(f"获取 macOS 权限提示失败: {str(e)}")
        return {"status": "error", "message": f"获取 macOS 权限提示失败: {str(e)}"}

@app.post("/directories/{directory_id}/request-access")
def request_directory_access(
    directory_id: int,
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """尝试读取目录以触发系统授权对话框"""
    try:
        success, message = myfiles_mgr.test_directory_access(directory_id)
        if success:
            return {"status": "success", "message": message}
        else:
            return {"status": "error", "message": message}
    except Exception as e:
        logger.error(f"请求目录访问失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"请求目录访问失败: {str(e)}"}

@app.get("/directories/{directory_id}/access-status")
def check_directory_access_status(
    directory_id: int,
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """检查目录的访问权限状态"""
    try:
        success, result = myfiles_mgr.check_directory_access_status(directory_id)
        if success:
            return {"status": "success", "data": result}
        else:
            return {"status": "error", "message": result.get("message", "检查访问状态失败")}
    except Exception as e:
        logger.error(f"检查目录访问状态失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"检查目录访问状态失败: {str(e)}"}

@app.get("/system/full-disk-access-status")
def check_full_disk_access_status(
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """
    Checks the system's full disk access status for the application.
    DEPRECATED: This information is now included in the /directories endpoint.
    This endpoint may be removed in a future version.
    Note: Currently always returns False as the full disk access check is not implemented.
    """
    try:
        # 根据系统平台返回状态
        status = False
        if sys.platform == "darwin":  # macOS
            # 在 macOS 上，我们可以通过检查特定目录的访问权限来判断是否有完全磁盘访问权限
            # 这里简单返回 False，因为现在我们没有这个方法了
            # 如果将来需要这个功能，可以实现新的检查方法
            pass
            
        logger.info(f"[API DEBUG] /system/full-disk-access-status returning: {status}")
        return {"status": "success", "full_disk_access_status": status}
    except Exception as e:
        logger.error(f"Error in check_full_disk_access_status: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.get("/api/files/search", response_model=List[Dict[str, Any]])
async def search_files(
    query: str,
    limit: int = 100,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """
    搜索文件路径包含指定子字符串的文件
    
    Args:
        query: 搜索查询字符串
        limit: 返回结果数量限制
        
    Returns:
        匹配的文件列表
    """
    try:
        logger.info(f"搜索文件路径，查询: '{query}'")
        results = screening_mgr.search_files_by_path_substring(query, limit)
        
        # 将结果转换为字典列表，以便返回给前端
        file_list = []
        for result in results:
            file_dict = {
                "id": result.id,
                "file_path": result.file_path,
                "file_name": result.file_name,
                "file_size": result.file_size,
                "extension": result.extension,
                "modified_time": result.modified_time.strftime("%Y-%m-%d %H:%M:%S") if result.modified_time else None,
                "category_id": result.category_id,
                "labels": result.labels,
                "status": result.status
            }
            file_list.append(file_dict)
            
        return file_list
    except Exception as e:
        logger.error(f"搜索文件路径时出错: {str(e)}")
        return []

# ========== Bundle扩展名管理端点 ==========
@app.get("/bundle-extensions")
def get_bundle_extensions(
    active_only: bool = True,
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """获取Bundle扩展名列表"""
    try:
        extensions = myfiles_mgr.get_bundle_extensions(active_only=active_only)
        extensions_data = []
        for ext in extensions:
            extensions_data.append({
                "id": ext.id,
                "extension": ext.extension,
                "description": ext.description,
                "is_active": ext.is_active,
                "created_at": ext.created_at.isoformat() if ext.created_at else None,
                "updated_at": ext.updated_at.isoformat() if ext.updated_at else None,
            })
        
        return {
            "status": "success",
            "data": extensions_data,
            "count": len(extensions_data),
            "message": f"成功获取 {len(extensions_data)} 个Bundle扩展名"
        }
    except Exception as e:
        logger.error(f"获取Bundle扩展名失败: {str(e)}")
        return {"status": "error", "message": f"获取Bundle扩展名失败: {str(e)}"}

@app.post("/bundle-extensions")
def add_bundle_extension(
    data: Dict[str, Any] = Body(...),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """添加新的Bundle扩展名"""
    try:
        extension = data.get("extension", "").strip()
        description = data.get("description", "").strip()
        
        if not extension:
            return {"status": "error", "message": "扩展名不能为空"}
        
        success, result = myfiles_mgr.add_bundle_extension(extension, description)
        
        if success:
            return {
                "status": "success",
                "data": {
                    "id": result.id,
                    "extension": result.extension,
                    "description": result.description,
                    "is_active": result.is_active,
                    "created_at": result.created_at.isoformat() if result.created_at else None,
                    "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                },
                "message": f"成功添加Bundle扩展名: {result.extension}"
            }
        else:
            return {"status": "error", "message": result}
            
    except Exception as e:
        logger.error(f"添加Bundle扩展名失败: {str(e)}")
        return {"status": "error", "message": f"添加Bundle扩展名失败: {str(e)}"}

@app.delete("/bundle-extensions/{ext_id}")
def remove_bundle_extension(
    ext_id: int,
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """删除Bundle扩展名（设为不活跃）"""
    try:
        success, message = myfiles_mgr.remove_bundle_extension(ext_id)
        
        if success:
            return {"status": "success", "message": message}
        else:
            return {"status": "error", "message": message}
            
    except Exception as e:
        logger.error(f"删除Bundle扩展名失败: {str(e)}")
        return {"status": "error", "message": f"删除Bundle扩展名失败: {str(e)}"}

@app.get("/bundle-extensions/for-rust")
def get_bundle_extensions_for_rust(
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """获取用于Rust端的Bundle扩展名列表"""
    try:
        # 添加日志，提示应该使用新的接口
        logger.warning("[API_DEPRECATED] /bundle-extensions/for-rust 接口已被弃用，建议使用 /config/all 接口获取 bundle_extensions 字段")
        
        extensions = myfiles_mgr.get_bundle_extensions_for_rust()
        return {
            "status": "success",
            "data": extensions,
            "count": len(extensions),
            "message": f"成功获取 {len(extensions)} 个Rust端Bundle扩展名"
        }
    except Exception as e:
        logger.error(f"获取Rust端Bundle扩展名失败: {str(e)}")
        return {"status": "error", "data": [], "message": f"获取失败: {str(e)}"}

# ========== 层级文件夹管理端点 ==========
@app.post("/folders/blacklist/{parent_id}")
def add_blacklist_folder_under_parent(
    parent_id: int,
    data: Dict[str, Any] = Body(...),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager),
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """在指定的白名单父文件夹下添加黑名单子文件夹"""
    try:
        folder_path = data.get("path", "").strip()
        folder_alias = data.get("alias", "").strip() or None
        
        if not folder_path:
            return {"status": "error", "message": "文件夹路径不能为空"}
        
        success, result = myfiles_mgr.add_blacklist_folder(parent_id, folder_path, folder_alias)
        
        if success:
            # 清除相关缓存
            invalidate_config_caches()
            logger.info(f"[CACHE] 已清除缓存，因为添加了黑名单文件夹: {folder_path}")
            
            # 当文件夹变为黑名单时，清理相关的粗筛结果数据
            deleted_count = screening_mgr.delete_screening_results_by_folder(folder_path)
            
            return {
                "status": "success",
                "data": {
                    "id": result.id,
                    "path": result.path,
                    "alias": result.alias,
                    "is_blacklist": result.is_blacklist,
                    "parent_id": result.parent_id,
                    "created_at": result.created_at.isoformat() if result.created_at else None,
                    "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                },
                "message": f"成功添加黑名单文件夹: {result.path}，清理了 {deleted_count} 条相关粗筛结果"
            }
        else:
            return {"status": "error", "message": result}
            
    except Exception as e:
        logger.error(f"添加黑名单文件夹失败: {str(e)}")
        return {"status": "error", "message": f"添加黑名单文件夹失败: {str(e)}"}

@app.get("/folders/hierarchy")
async def get_folder_hierarchy(
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """获取文件夹层级关系（白名单+其下的黑名单）"""
    try:
        # 使用异步超时控制
        try:
            return await asyncio.wait_for(
                _get_folder_hierarchy_async(myfiles_mgr), 
                timeout=3.0  # 设置3秒超时
            )
        except asyncio.TimeoutError:
            logger.error("获取文件夹层级关系超时")
            # 尝试从缓存获取
            hit, cached_value = folder_hierarchy_cache.get("folder_hierarchy")
            if hit:
                logger.info("使用缓存数据响应超时请求")
                return cached_value
            # 没有缓存，返回错误
            return {"status": "error", "message": "获取文件夹层级关系超时"}
    except Exception as e:
        logger.error(f"获取文件夹层级关系失败: {str(e)}")
        return {"status": "error", "message": f"获取文件夹层级关系失败: {str(e)}"}
        
async def _get_folder_hierarchy_async(myfiles_mgr: MyFilesManager):
    """异步包装缓存函数，用于超时控制"""
    return _get_folder_hierarchy_cached(myfiles_mgr)

@cached(folder_hierarchy_cache, "folder_hierarchy")
def _get_folder_hierarchy_cached(myfiles_mgr: MyFilesManager):
    """缓存版本的文件夹层级关系获取函数"""
    start_time = time.time()
    hierarchy = myfiles_mgr.get_folder_hierarchy()
    elapsed = time.time() - start_time
    logger.info(f"[FOLDERS] 获取文件夹层级关系耗时 {elapsed:.3f}s (从数据库)")
    
    return {
        "status": "success",
        "data": hierarchy,
        "count": len(hierarchy),
        "message": f"成功获取 {len(hierarchy)} 个父文件夹的层级关系"
    }

@app.post("/screening/clean-by-path")
def clean_screening_results_by_path(
    data: Dict[str, Any] = Body(...),
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """手动清理指定路径下的粗筛结果（用于添加黑名单子文件夹时）
    
    前端可以使用此端点在用户在白名单下添加黑名单子文件夹后清理数据，
    相当于在集合中扣出一个子集来删掉。
    """
    try:
        folder_path = data.get("path", "").strip()
        
        if not folder_path:
            return {"status": "error", "message": "文件夹路径不能为空"}
        
        # 使用 delete_screening_results_by_path_prefix 方法，用于在白名单下添加黑名单子文件夹
        deleted_count = screening_mgr.delete_screening_results_by_path_prefix(folder_path)
        return {
            "status": "success", 
            "deleted": deleted_count,
            "message": f"已清理 {deleted_count} 条与路径前缀 '{folder_path}' 相关的粗筛结果"
        }
            
    except Exception as e:
        logger.error(f"手动清理粗筛结果失败: {str(e)}")
        return {"status": "error", "message": f"清理失败: {str(e)}"}

@app.post("/clear-screening-data")
def clear_screening_data(
    data: Dict[str, Any] = Body(...),
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """清理指定路径的粗筛数据（供Rust后端调用）- 兼容旧版API
    
    此端点已弃用，只为了向后兼容，请使用 /screening/clean-by-path 代替。
    """
    try:
        folder_path = data.get("folder_path", "").strip()
        
        if not folder_path:
            return {"status": "error", "message": "文件夹路径不能为空"}
        
        # 重定向到新的接口内部实现
        return clean_screening_results_by_path({"path": folder_path}, screening_mgr)
    except Exception as e:
        logger.error(f"清理粗筛数据失败（旧API）: {str(e)}")
        return {"status": "error", "message": str(e)}
            
    except Exception as e:
        logger.error(f"清理粗筛数据失败: {str(e)}")
        return {"status": "error", "message": f"清理失败: {str(e)}"}

def invalidate_config_caches():
    """使所有配置相关缓存失效"""
    config_cache.clear()
    folder_hierarchy_cache.clear()
    logger.info("[CACHE] 所有配置缓存已清除")

@app.post("/screening/delete-by-path")
def delete_screening_by_path(
    data: Dict[str, Any] = Body(...),
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """删除指定路径的文件粗筛记录
    
    当客户端检测到文件删除事件时，调用此API端点删除对应的粗筛记录。
    
    请求体:
    - file_path: 要删除的文件路径
    
    返回:
    - success: 操作是否成功
    - deleted_count: 删除的记录数量
    - message: 操作结果消息
    """
    try:
        file_path = data.get("file_path")
        
        if not file_path:
            logger.warning("删除粗筛记录请求中未提供文件路径")
            return {
                "success": False,
                "deleted_count": 0,
                "message": "文件路径不能为空"
            }
        
        # 对于单个文件删除，我们需要确保路径是精确匹配的
        # 我们可以使用delete_screening_results_by_path_prefix方法，但需要确保只删除这个确切路径
        # 通常情况下，这个路径应该是一个文件路径，不会匹配到其他文件
        
        # 标准化路径
        normalized_path = os.path.normpath(file_path).replace("\\", "/")
        
        # 执行删除操作
        deleted_count = screening_mgr.delete_screening_results_by_path_prefix(normalized_path)
        
        # 记录操作结果
        if deleted_count > 0:
            logger.info(f"成功删除文件 '{normalized_path}' 的粗筛记录，共 {deleted_count} 条")
        else:
            logger.info(f"未找到文件 '{normalized_path}' 的粗筛记录，无需删除")
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"成功删除文件 '{normalized_path}' 的粗筛记录，共 {deleted_count} 条"
        }
        
    except Exception as e:
        logger.error(f"删除文件粗筛记录失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "deleted_count": 0,
            "message": f"删除失败: {str(e)}"
        }
        
if __name__ == "__main__":
    try:
        logger.info("API服务程序启动")
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, default=60315, help="API服务监听端口")
        parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
        parser.add_argument("--db-path", type=str, default="knowledge-focus.db", help="数据库文件路径")
        
        args = parser.parse_args()
        logger.info(f"命令行参数: port={args.port}, host={args.host}, db_path={args.db_path}")
        
        # 检查数据库路径是否存在
        db_dir = os.path.dirname(os.path.abspath(args.db_path))
        if db_dir and not os.path.exists(db_dir):
            logger.warning(f"数据库目录 {db_dir} 不存在，尝试创建...")
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"已创建数据库目录 {db_dir}")
            except Exception as e:
                logger.error(f"创建数据库目录失败: {str(e)}", exc_info=True)
        
        # 检查端口是否被占用，如果被占用则终止占用进程
        try:
            logger.info(f"检查端口 {args.port} 是否被占用...")
            kill_process_on_port(args.port)
            time.sleep(2)  # 等待端口释放
            logger.info(f"端口 {args.port} 已释放或本来就没被占用")
        except Exception as e:
            logger.error(f"释放端口 {args.port} 失败: {str(e)}", exc_info=True)
            # 继续执行，端口可能本来就没有被占用
        
        # 设置数据库路径
        app.state.db_path = args.db_path
        logger.info(f"设置数据库路径: {args.db_path}")
        
        # 启动服务器
        logger.info(f"API服务启动在: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except Exception as e:
        logger.critical(f"API服务启动失败: {str(e)}", exc_info=True)

        # 返回退出码2，表示发生错误
        sys.exit(2)
