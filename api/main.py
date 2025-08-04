import os
import sys
import argparse
import logging
import time
import pathlib
import asyncio
import threading
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from utils import kill_process_on_port, monitor_parent, kill_orphaned_processes
from sqlmodel import create_engine, Session, select
from api_cache_optimization import TimedCache, cached
from db_mgr import (
    DBManager, TaskStatus, TaskResult, TaskType, TaskPriority, Task,
    MyFiles, FileCategory, FileFilterRule, FileExtensionMap, ProjectRecognitionRule,
)
from myfiles_mgr import MyFilesManager
from screening_mgr import ScreeningManager
from parsing_mgr import ParsingMgr
from task_mgr import TaskManager
from lancedb_mgr import LanceDBMgr
from models_mgr import ModelsMgr

# --- Centralized Logging Setup ---
def setup_logging(logging_dir: str = None):
    """
    Configures the root logger for the application.

    args:
        logging_dir (str): The directory where log files will be stored.
    """
    
    try:
        # Determine log directory
        if logging_dir is not None:
            log_dir = pathlib.Path(logging_dir)
        else:
            script_path = os.path.abspath(__file__)
            log_dir = pathlib.Path(script_path).parent / 'logs'
        if not log_dir.exists():
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

    except Exception as e:
        # Fallback to basic config if setup fails
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Error setting up custom logging: {e}", exc_info=True)

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
        # try:
        #     logger.info("启动通知检查任务...")
        #     asyncio.create_task(check_notifications())
        # except Exception as notify_err:
        #     logger.error(f"启动通知检查任务失败: {str(notify_err)}", exc_info=True)
            
        # Start monitor can kill self process if parent process is dead or exit
        try:
            logger.info("启动父进程监控线程...")
            monitor_thread = threading.Thread(target=monitor_parent, daemon=True)
            monitor_thread.start()
            logger.info("父进程监控线程已启动")
        except Exception as monitor_err:
            logger.error(f"启动父进程监控线程失败: {str(monitor_err)}", exc_info=True)

        # 配置解析库的警告和日志级别
        try:
            from parsing_mgr import configure_parsing_warnings
            configure_parsing_warnings()
            logger.info("解析库日志配置已应用")
        except Exception as parsing_config_err:
            logger.error(f"配置解析库日志失败: {str(parsing_config_err)}", exc_info=True)

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


# 周期性检查新通知并广播
# async def check_notifications():
#     while True:
#         # 广播消息
#         # await manager.broadcast("New notification")
#         await asyncio.sleep(8)

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

# Add the new tagging API router
from tagging_api import get_router as get_tagging_router
tagging_router = get_tagging_router(get_session=get_session)
app.include_router(tagging_router, prefix="", tags=["tagging"])

# 获取 MyFilesManager 的依赖函数
def get_myfiles_manager(session: Session = Depends(get_session)):
    """获取文件/文件夹管理器实例"""
    return MyFilesManager(session)

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
    db_directory = os.path.dirname(db_path)
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)

    while not stop_event.is_set():
        try:
            with Session(engine) as session:
                task_mgr = TaskManager(session)
                task: Task = task_mgr.get_next_task()

                if task is None:
                    time.sleep(5) # 没有任务时，等待5秒
                    continue

                logger.info(f"任务处理线程接收任务: ID={task.id}, Name='{task.task_name}', Type='{task.task_type}', Priority={task.priority}")
                task_mgr.update_task_status(task.id, TaskStatus.RUNNING)

                models_mgr = ModelsMgr(session)
                parsing_mgr = ParsingMgr(session, lancedb_mgr, models_mgr)

                if task.task_type == TaskType.TAGGING.value:
                    # 高优先级任务: 通常是单个文件处理
                    if task.priority == TaskPriority.HIGH.value and task.extra_data and 'screening_result_id' in task.extra_data:
                        logger.info(f"开始处理高优先级标记任务 (Task ID: {task.id})")
                        success = parsing_mgr.process_single_file_task(task.extra_data['screening_result_id'])
                        if success:
                            task_mgr.update_task_status(task.id, TaskStatus.COMPLETED, result=TaskResult.SUCCESS)
                            
                            # 检查是否需要自动衔接MULTIVECTOR任务（仅当文件被pin时）
                            _check_and_create_multivector_task(session, task_mgr, task.extra_data.get('screening_result_id'))
                        else:
                            task_mgr.update_task_status(task.id, TaskStatus.FAILED, result=TaskResult.FAILURE)
                    # 低优先级任务: 批量处理
                    else:
                        logger.info(f"开始批量标记任务 (Task ID: {task.id})")
                        result_data = parsing_mgr.process_pending_batch(task_id=task.id, batch_size=10) # 每次处理10个
                        
                        # 无论批量任务处理了多少文件，都将触发任务标记为完成
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.COMPLETED, 
                            result=TaskResult.SUCCESS, 
                            message=f"批量处理完成: 处理了 {result_data.get('processed', 0)} 个文件。"
                        )
                
                elif task.task_type == TaskType.MULTIVECTOR.value:
                    # 引入ChunkingMgr
                    from chunking_mgr import ChunkingMgr
                    chunking_mgr = ChunkingMgr(session, lancedb_mgr, models_mgr)
                    
                    # 高优先级任务: 单文件处理（用户pin操作或文件变化衔接）
                    if task.priority == TaskPriority.HIGH.value and task.extra_data and 'file_path' in task.extra_data:
                        file_path = task.extra_data['file_path']
                        logger.info(f"开始处理高优先级多模态向量化任务 (Task ID: {task.id}): {file_path}")
                        
                        try:
                            success = chunking_mgr.process_document(file_path)
                            if success:
                                task_mgr.update_task_status(
                                    task.id, 
                                    TaskStatus.COMPLETED, 
                                    result=TaskResult.SUCCESS,
                                    message=f"多模态向量化完成: {file_path}"
                                )
                                logger.info(f"多模态向量化成功完成: {file_path}")
                            else:
                                task_mgr.update_task_status(
                                    task.id, 
                                    TaskStatus.FAILED, 
                                    result=TaskResult.FAILURE,
                                    message=f"多模态向量化失败: {file_path}"
                                )
                                logger.error(f"多模态向量化失败: {file_path}")
                        except Exception as e:
                            error_msg = f"多模态向量化异常: {file_path} - {str(e)}"
                            task_mgr.update_task_status(
                                task.id, 
                                TaskStatus.FAILED, 
                                result=TaskResult.FAILURE,
                                message=error_msg
                            )
                            logger.error(error_msg, exc_info=True)
                    else:
                        # 中低优先级任务: 批量处理（未来支持）
                        logger.info(f"批量多模态向量化任务暂未实现 (Task ID: {task.id})")
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.COMPLETED, 
                            result=TaskResult.SUCCESS,
                            message="批量多模态向量化任务已跳过"
                        )
                
                else:
                    logger.warning(f"未知的任务类型: {task.task_type} for task ID: {task.id}")
                    task_mgr.update_task_status(task.id, TaskStatus.FAILED, result=TaskResult.FAILURE, message=f"Unknown task type: {task.task_type}")

        except Exception as e:
            logger.error(f"任务处理线程发生意外错误: {e}", exc_info=True)
            time.sleep(30)

    logger.info("任务处理线程已停止")

def _check_and_create_multivector_task(session: Session, task_mgr: TaskManager, screening_result_id: int):
    """
    检查文件是否处于pin状态，如果是则自动创建MULTIVECTOR任务
    
    Args:
        session: 数据库会话
        task_mgr: 任务管理器
        screening_result_id: 粗筛结果ID
    """
    if not screening_result_id:
        return
    
    try:
        from screening_mgr import ScreeningResult
        # 获取粗筛结果，包含文件路径信息
        screening_result = session.get(ScreeningResult, screening_result_id)
        if not screening_result:
            logger.warning(f"未找到screening_result_id: {screening_result_id}")
            return
        
        file_path = screening_result.file_path
        
        # 检查文件是否在最近8小时内被pin过
        is_recently_pinned = _check_file_pin_status(file_path, session)
        
        if is_recently_pinned:
            logger.info(f"文件 {file_path} 在最近8小时内被pin过，创建MULTIVECTOR任务")
            task_mgr.add_task(
                task_name=f"多模态向量化: {Path(file_path).name}",
                task_type=TaskType.MULTIVECTOR,
                priority=TaskPriority.HIGH,
                extra_data={"file_path": file_path},
                target_file_path=file_path  # 设置冗余字段便于查询
            )
        else:
            logger.info(f"文件 {file_path} 在最近8小时内未被pin过，跳过MULTIVECTOR任务")
            
    except Exception as e:
        logger.error(f"检查和创建MULTIVECTOR任务时发生错误: {e}", exc_info=True)

def _check_file_pin_status(file_path: str, session: Session) -> bool:
    """
    检查文件是否在最近8小时内被pin过（即有成功的MULTIVECTOR任务）
    
    Args:
        file_path: 文件路径
        session: 数据库会话
        
    Returns:
        bool: 文件是否在最近8小时内被pin过
    """
    try:
        task_mgr = TaskManager(session)
        return task_mgr.is_file_recently_pinned(file_path, hours=8)
    except Exception as e:
        logger.error(f"检查文件pin状态时发生错误: {e}", exc_info=True)
        return False
    return file_ext in important_extensions

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

def get_lancedb_manager():
    """获取LanceDB管理器实例"""
    if not hasattr(app.state, "engine") or app.state.engine is None:
        raise RuntimeError("数据库引擎未初始化")
    
    # 从SQLite数据库路径推导出base_dir
    sqlite_url = str(app.state.engine.url)
    if sqlite_url.startswith('sqlite:///'):
        db_path = sqlite_url.replace('sqlite:///', '')
        db_directory = os.path.dirname(db_path)
        return LanceDBMgr(base_dir=db_directory)
    else:
        raise RuntimeError("无法从数据库URL推导出LanceDB路径")

@app.post("/pin-file")
def pin_file(
    request: Dict[str, Any] = Body(...),
    task_mgr: TaskManager = Depends(get_task_manager)
):
    """
    Pin一个文件，创建高优先级的多模态向量化任务
    
    参数:
    - file_path: 文件的绝对路径
    
    返回:
    - task_id: 创建的任务ID
    - message: 状态信息
    """
    try:
        file_path = request.get("file_path")
        if not file_path:
            return {"success": False, "error": "缺少file_path参数"}
        
        # 验证文件路径
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        if not os.path.isfile(file_path):
            return {"success": False, "error": f"路径不是文件: {file_path}"}
        
        # 检查文件权限
        if not os.access(file_path, os.R_OK):
            return {"success": False, "error": f"文件无读取权限: {file_path}"}
        
        # 创建高优先级MULTIVECTOR任务
        file_name = os.path.basename(file_path)
        task = task_mgr.add_task(
            task_name=f"Pin文件向量化: {file_name}",
            task_type=TaskType.MULTIVECTOR,
            priority=TaskPriority.HIGH,
            extra_data={"file_path": file_path, "source": "user_pin"},
            target_file_path=file_path
        )
        
        logger.info(f"用户Pin文件成功，创建任务ID: {task.id}, 文件: {file_path}")
        
        return {
            "success": True,
            "task_id": task.id,
            "message": f"文件Pin成功，正在处理: {file_name}",
            "file_path": file_path
        }
        
    except Exception as e:
        logger.error(f"Pin文件时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"Pin文件失败: {str(e)}"}

@app.get("/task/{task_id}")
def get_task_status(task_id: int, task_mgr: TaskManager = Depends(get_task_manager)):
    """
    获取任务状态
    
    参数:
    - task_id: 任务ID
    
    返回:
    - 任务详细信息
    """
    try:
        task = task_mgr.get_task(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}
        
        return {
            "success": True,
            "task": {
                "id": task.id,
                "task_name": task.task_name,
                "task_type": task.task_type,
                "priority": task.priority,
                "status": task.status,
                "result": task.result,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "start_time": task.start_time,
                "extra_data": task.extra_data,
                "target_file_path": task.target_file_path
            }
        }
        
    except Exception as e:
        logger.error(f"获取任务状态时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"获取任务状态失败: {str(e)}"}

@app.get("/images/{image_filename}")
def get_image(image_filename: str, session: Session = Depends(get_session)):
    """
    获取图片文件内容
    
    参数:
    - image_filename: 图片文件名 (例如: image_000000_hash.png)
    
    返回:
    - 图片文件的二进制内容
    """
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        import os
        
        # 验证文件名格式（安全检查）
        if not image_filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            return {"success": False, "error": "不支持的图片格式"}
        
        if ".." in image_filename or "/" in image_filename or "\\" in image_filename:
            return {"success": False, "error": "无效的文件名"}
        
        # 获取docling缓存目录
        try:
            # 从数据库引擎获取基础目录
            sqlite_url = str(app.state.engine.url)
            if sqlite_url.startswith('sqlite:///'):
                db_path = sqlite_url.replace('sqlite:///', '')
                base_dir = Path(db_path).parent
            else:
                base_dir = Path.cwd()
            
            docling_cache_dir = base_dir / "docling_cache"
            image_path = docling_cache_dir / image_filename
            
        except Exception as e:
            logger.error(f"获取docling缓存目录失败: {e}")
            return {"success": False, "error": "无法确定图片存储位置"}
        
        # 检查图片文件是否存在
        if not image_path.exists():
            logger.warning(f"图片文件不存在: {image_path}")
            return {"success": False, "error": f"图片文件不存在: {image_filename}"}
        
        # 验证这个图片是否属于某个已处理的文档（安全检查）
        from sqlmodel import select
        from db_mgr import ParentChunk
        
        # 查找包含此图片文件名的ParentChunk（在metadata的image_file_path中查找）
        stmt = select(ParentChunk).where(
            ParentChunk.chunk_type == "image",
            ParentChunk.metadata_json.contains(image_filename)
        )
        chunk = session.exec(stmt).first()
        
        if not chunk:
            logger.warning(f"图片文件未在数据库中找到关联记录: {image_filename}")
            return {"success": False, "error": "图片文件无效或已过期"}
        
        # 根据文件扩展名确定正确的 MIME 类型
        file_ext = image_filename.lower().split('.')[-1]
        mime_type_map = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'bmp': 'image/bmp',
            'webp': 'image/webp'
        }
        media_type = mime_type_map.get(file_ext, 'image/png')
        
        # 返回图片文件
        return FileResponse(
            path=str(image_path),
            media_type=media_type,
            headers={"Content-Disposition": "inline"}  # 让浏览器直接显示而不是下载
        )
        
    except Exception as e:
        logger.error(f"获取图片时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"获取图片失败: {str(e)}"}

@app.get("/images/by-chunk/{parent_chunk_id}")
def get_image_by_chunk(parent_chunk_id: int, session: Session = Depends(get_session)):
    """
    通过ParentChunk ID获取关联的图片
    
    参数:
    - parent_chunk_id: 父块ID
    
    返回:
    - 图片文件的二进制内容，或重定向到图片端点
    """
    try:
        from fastapi.responses import RedirectResponse
        from pathlib import Path
        from sqlmodel import select
        from db_mgr import ParentChunk
        
        # 查找指定的ParentChunk
        stmt = select(ParentChunk).where(
            ParentChunk.id == parent_chunk_id,
            ParentChunk.chunk_type == "image"
        )
        chunk = session.exec(stmt).first()
        
        if not chunk:
            return {"success": False, "error": f"图片块不存在: {parent_chunk_id}"}
        
        # 从chunk中提取图片文件路径
        image_filename = None
        
        # 从metadata中获取image_file_path
        try:
            metadata = json.loads(chunk.metadata_json)
            image_file_path = metadata.get("image_file_path")
            
            if image_file_path and os.path.exists(image_file_path):
                # metadata中有完整的文件路径
                image_path = Path(image_file_path)
                image_filename = image_path.name
                logger.info(f"Found image file from metadata: {image_filename}")
            else:
                logger.warning(f"Image file path not found or file does not exist: {image_file_path}")
                        
        except Exception as e:
            logger.warning(f"无法从metadata提取图片路径: {e}")
        
        if not image_filename:
            return {"success": False, "error": "无法确定图片文件路径"}
        
        # 重定向到图片获取端点
        return RedirectResponse(url=f"/images/{image_filename}")
        
    except Exception as e:
        logger.error(f"通过chunk获取图片时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"获取图片失败: {str(e)}"}

@app.get("/documents/{document_id}/images")
def get_document_images(document_id: int, session: Session = Depends(get_session)):
    """
    获取文档中的所有图片列表
    
    参数:
    - document_id: 文档ID
    
    返回:
    - 图片列表，包含chunk_id、文件名、描述等信息
    """
    try:
        from sqlmodel import select
        from db_mgr import ParentChunk
        from pathlib import Path
        import json
        
        # 查找文档中所有的图片块
        stmt = select(ParentChunk).where(
            ParentChunk.document_id == document_id,
            ParentChunk.chunk_type == "image"
        )
        image_chunks = session.exec(stmt).all()
        
        images = []
        for chunk in image_chunks:
            try:
                # 提取图片文件名 - 从metadata中获取
                image_filename = None
                
                # 从metadata中获取image_file_path
                try:
                    metadata = json.loads(chunk.metadata_json)
                    image_file_path = metadata.get("image_file_path")
                    
                    if image_file_path and os.path.exists(image_file_path):
                        # metadata中有完整的文件路径
                        image_path = Path(image_file_path)
                        image_filename = image_path.name
                    else:
                        logger.warning(f"Image file path not found or file does not exist for chunk {chunk.id}: {image_file_path}")
                                
                except Exception as e:
                    logger.warning(f"处理图片块 {chunk.id} metadata时出错: {e}")
                
                # 如果无法确定文件名，跳过这个图片块
                if not image_filename:
                    logger.warning(f"无法确定图片块 {chunk.id} 的文件名，跳过")
                    continue
                
                # 获取图片描述 - 现在直接从content字段获取
                image_description = chunk.content if chunk.content else ""
                
                images.append({
                    "chunk_id": chunk.id,
                    "filename": image_filename,
                    "description": image_description,
                    "image_url": f"/images/{image_filename}",
                    "chunk_url": f"/images/by-chunk/{chunk.id}"
                })
                
            except Exception as e:
                logger.warning(f"处理图片块 {chunk.id} 时出错: {e}")
                continue
        
        return {
            "success": True,
            "document_id": document_id,
            "images": images,
            "total_count": len(images)
        }
        
    except Exception as e:
        logger.error(f"获取文档图片列表时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"获取图片列表失败: {str(e)}"}

@app.post("/file-screening/batch")
def add_batch_file_screening_results(
    request: Dict[str, Any] = Body(...), 
    screening_mgr: ScreeningManager = Depends(get_screening_manager),
    task_mgr: TaskManager = Depends(get_task_manager)
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
                        logger.warning(f"转换字符串时间字段 {time_field} 失败: {str(e)}")
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
        task: Task = task_mgr.add_task(
            task_name=task_name,
            task_type=TaskType.TAGGING,
            priority=TaskPriority.MEDIUM,
            extra_data={"file_count": len(data_list)}
        )
        logger.info(f"已创建标记任务 ID: {task.id}，准备处理 {len(data_list)} 个文件")

        # 2. 批量添加粗筛结果，并关联 task_id
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
@app.get("/file-screening/results/search")
def search_files_by_path_substring(
    substring: str,
    limit: int = 100,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """根据路径子字符串搜索文件粗筛结果
    
    参数:
    - substring: 要搜索的路径子字符串
    - limit: 最大返回结果数
    """
    try:
        # 使用 ScreeningManager 的搜索方法，现在返回字典列表
        results_dict = screening_mgr.search_files_by_path_substring(substring, limit)
        
        return {
            "success": True,
            "count": len(results_dict),
            "data": results_dict
        }
        
    except Exception as e:
        logger.error(f"根据路径子字符串搜索文件粗筛结果失败: {str(e)}")
        return {
            "success": False,
            "message": f"搜索失败: {str(e)}"
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
                # 如果不是黑名单，前端会立即启动Rust监控
                if not is_blacklist:
                    # 添加Rust监控的触发信号
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

@app.post("/pin-file")
async def pin_file(
    data: Dict[str, Any] = Body(...),
    task_mgr: TaskManager = Depends(get_task_manager)
):
    """Pin文件并创建多模态向量化任务
    
    用户pin文件时调用此端点，立即创建HIGH优先级的MULTIVECTOR任务
    
    请求体:
    - file_path: 要pin的文件绝对路径
    
    返回:
    - success: 操作是否成功
    - task_id: 创建的任务ID
    - message: 操作结果消息
    """
    try:
        file_path = data.get("file_path")
        
        if not file_path:
            logger.warning("Pin文件请求中未提供文件路径")
            return {
                "success": False,
                "task_id": None,
                "message": "文件路径不能为空"
            }
        
        # 验证文件路径和权限
        if not os.path.exists(file_path):
            logger.warning(f"Pin文件失败，文件不存在: {file_path}")
            return {
                "success": False,
                "task_id": None,
                "message": f"文件不存在: {file_path}"
            }
        
        if not os.access(file_path, os.R_OK):
            logger.warning(f"Pin文件失败，文件无读取权限: {file_path}")
            return {
                "success": False,
                "task_id": None,
                "message": f"文件无读取权限: {file_path}"
            }
        
        # 检查文件类型是否支持
        supported_extensions = {'.pdf', '.docx', '.pptx', '.doc', '.ppt'}
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in supported_extensions:
            logger.warning(f"Pin文件失败，不支持的文件类型: {file_ext}")
            return {
                "success": False,
                "task_id": None,
                "message": f"不支持的文件类型: {file_ext}，支持的类型: {supported_extensions}"
            }
        
        # 创建HIGH优先级MULTIVECTOR任务
        task = task_mgr.add_task(
            task_name=f"Pin文件多模态向量化: {Path(file_path).name}",
            task_type=TaskType.MULTIVECTOR,
            priority=TaskPriority.HIGH,
            extra_data={"file_path": file_path}
        )
        
        logger.info(f"成功创建Pin文件的多模态向量化任务: {file_path} (Task ID: {task.id})")
        
        return {
            "success": True,
            "task_id": task.id,
            "message": f"已创建多模态向量化任务，Task ID: {task.id}"
        }
        
    except Exception as e:
        logger.error(f"Pin文件失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "task_id": None,
            "message": f"Pin文件失败: {str(e)}"
        }

@app.get("/test-bridge-stdout")
def test_bridge_stdout():
    """测试桥接事件的stdout输出能力"""
    from test_bridge_stdout import test_bridge_stdout_main
    test_bridge_stdout_main()
    return {"status": "ok"}


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, default=60315, help="API服务监听端口")
        parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
        parser.add_argument("--db-path", type=str, default="knowledge-focus.db", help="数据库文件路径")
        parser.add_argument("--mode", type=str, default="dev", help="标记是开发环境还是生产环境")
        args = parser.parse_args()

        # 检查数据库路径是否存在
        db_dir = os.path.dirname(os.path.abspath(args.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        if args.mode is not None:
            setup_logging()
        else:
            logging_dir = os.path.join(db_dir, "logs")
            setup_logging(logging_dir)

        logger = logging.getLogger(__name__)
        logger.info("API服务程序启动")
        logger.info(f"命令行参数: port={args.port}, host={args.host}, db_path={args.db_path}, mode={args.mode}")

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
