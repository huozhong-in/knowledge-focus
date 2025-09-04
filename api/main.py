import os
import sys
import argparse
import logging
import time
import threading
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from utils import kill_process_on_port, monitor_parent, kill_orphaned_processes
from sqlmodel import create_engine, Session, select
from db_mgr import (
    DBManager, 
    TaskStatus, 
    TaskResult, 
    TaskType, 
    TaskPriority, 
    Task, 
    SystemConfig,
)
from screening_mgr import FileScreeningResult
from models_mgr import ModelsMgr
from lancedb_mgr import LanceDBMgr
from file_tagging_mgr import FileTaggingMgr, configure_parsing_warnings
from multivector_mgr import MultiVectorMgr
from task_mgr import TaskManager
from models_api import get_router as get_models_router
from tagging_api import get_router as get_tagging_router
from chatsession_api import get_router as get_chatsession_router
from myfolders_api import get_router as get_myfolders_router
from screening_api import get_router as get_screening_router
from search_api import get_router as get_search_router
from unified_tools_api import get_router as get_tools_router
from documents_api import get_router as get_documents_router

# 初始化logger
logger = logging.getLogger(__name__)

# --- Centralized Logging Setup ---
def setup_logging(logging_dir: str):
    """
    Configures the root logger for the application.

    args:
        logging_dir (str): The directory where log files will be stored.
    """
    
    try:
        # Determine log directory
        log_dir = Path(logging_dir)
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

# 本地大模型API端点添加
models_router = get_models_router(external_get_session=get_session)
app.include_router(models_router, prefix="", tags=["models"])

# 添加新的标签API路由
tagging_router = get_tagging_router(external_get_session=get_session)
app.include_router(tagging_router, prefix="", tags=["tagging"])

# 添加聊天会话API路由
chatsession_router = get_chatsession_router(external_get_session=get_session)
app.include_router(chatsession_router, prefix="", tags=["chat-sessions"])

# 添加文件管理API路由
myfolders_router = get_myfolders_router(external_get_session=get_session)
app.include_router(myfolders_router, prefix="", tags=["myfolders"])

# 添加粗筛API路由
screening_router = get_screening_router(external_get_session=get_session)
app.include_router(screening_router, prefix="", tags=["screening"])

# 添加搜索API路由
search_router = get_search_router(external_get_session=get_session)
app.include_router(search_router, prefix="", tags=["search"])

# 添加工具API路由
tools_router = get_tools_router(external_get_session=get_session)
app.include_router(tools_router, prefix="", tags=["tools"])

# 添加文档API路由
documents_router = get_documents_router(external_get_session=get_session)
app.include_router(documents_router, prefix="", tags=["documents"])

# 获取 TaskManager 的依赖函数
def get_task_manager(session: Session = Depends(get_session)):
    """获取任务管理器实例"""
    return TaskManager(session)

# 任务处理者
def task_processor(db_path: str, stop_event: threading.Event):
    """处理任务的后台工作线程"""
    logger.info("任务处理线程已启动")
    
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
                file_tagging_mgr = FileTaggingMgr(session, lancedb_mgr, models_mgr)
                multivector_mgr = MultiVectorMgr(session, lancedb_mgr, models_mgr)

                if task.task_type == TaskType.TAGGING.value:
                    # 检查模型可用性
                    if not file_tagging_mgr.check_file_tagging_model_availability():
                        logger.error("相关模型不可用，无法处理文件打标签任务")
                        time.sleep(5)
                        continue
                    # 高优先级任务: 通常是单个文件处理
                    if task.priority == TaskPriority.HIGH.value and task.extra_data and 'screening_result_id' in task.extra_data:
                        logger.info(f"开始处理高优先级文件打标签任务 (Task ID: {task.id})")
                        success = file_tagging_mgr.process_single_file_task(task.extra_data['screening_result_id'])
                        if success:
                            task_mgr.update_task_status(task.id, TaskStatus.COMPLETED, result=TaskResult.SUCCESS)
                            
                            # 检查是否需要自动衔接MULTIVECTOR任务（仅当文件被pin时）
                            if multivector_mgr.check_multivector_model_availability():
                                _check_and_create_multivector_task(session, task_mgr, task.extra_data.get('screening_result_id'))
                        else:
                            task_mgr.update_task_status(task.id, TaskStatus.FAILED, result=TaskResult.FAILURE)
                    # 低优先级任务: 批量处理
                    else:
                        logger.info(f"开始批量文件打标签任务 (Task ID: {task.id})")
                        result_data = file_tagging_mgr.process_pending_batch(task_id=task.id, batch_size=10) # 每次处理10个
                        
                        # 无论批量任务处理了多少文件，都将触发任务文件打标签为完成
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.COMPLETED, 
                            result=TaskResult.SUCCESS, 
                            message=f"批量处理完成: 处理了 {result_data.get('processed', 0)} 个文件。"
                        )
                
                elif task.task_type == TaskType.MULTIVECTOR.value:
                    if not multivector_mgr.check_multivector_model_availability():
                        logger.error("相关模型不可用，无法处理多模态向量化任务")
                        time.sleep(5)
                        continue
                    # 高优先级任务: 单文件处理（用户pin操作或文件变化衔接）
                    if task.priority == TaskPriority.HIGH.value and task.extra_data and 'file_path' in task.extra_data:
                        file_path = task.extra_data['file_path']
                        logger.info(f"开始处理高优先级多模态向量化任务 (Task ID: {task.id}): {file_path}")
                        
                        try:
                            # 传递task_id以便事件追踪
                            success = multivector_mgr.process_document(file_path, str(task.id))
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
                        logger.info(f"其他任务类型暂未实现 (Task ID: {task.id})")
                        task_mgr.update_task_status(
                            task.id, 
                            TaskStatus.COMPLETED, 
                            result=TaskResult.SUCCESS,
                            message="批量处理任务已跳过"
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
        # 获取粗筛结果，包含文件路径信息
        screening_result = session.get(FileScreeningResult, screening_result_id)
        if not screening_result:
            logger.warning(f"未找到screening_result_id: {screening_result_id}")
            return
        
        file_path = screening_result.file_path
        
        # 检查文件是否在最近24小时内被pin过
        is_recently_pinned = _check_file_pin_status(file_path, session)
        
        if is_recently_pinned:
            logger.info(f"文件 {file_path} 在最近24小时内被pin过，创建MULTIVECTOR任务")
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
    检查文件是否在最近24小时内被pin过（即有成功的MULTIVECTOR任务）
    
    Args:
        file_path: 文件路径
        session: 数据库会话
        
    Returns:
        bool: 文件是否在最近24小时内被pin过
    """
    try:
        task_mgr = TaskManager(session)
        return task_mgr.is_file_recently_pinned(file_path, hours=24)
    except Exception as e:
        logger.error(f"检查文件pin状态时发生错误: {e}", exc_info=True)
        return False

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
    }

@app.get("/system-config/{config_key}")
def get_system_config(config_key: str, session: Session = Depends(get_session)):
    """获取系统配置
    
    参数:
    - config_key: 配置键名
    
    返回:
    - 配置值和描述信息
    """
    try:
        config = session.exec(select(SystemConfig).where(SystemConfig.key == config_key)).first()
        if not config:
            return {"success": False, "error": f"配置项 '{config_key}' 不存在"}
        
        return {
            "success": True,
            "config": {
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "updated_at": config.updated_at
            }
        }
        
    except Exception as e:
        logger.error(f"获取系统配置时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"获取配置失败: {str(e)}"}

@app.put("/system-config/{config_key}")
def update_system_config(
    config_key: str, 
    data: Dict[str, Any] = Body(...),
    session: Session = Depends(get_session)
):
    """更新系统配置
    
    参数:
    - config_key: 配置键名
    
    请求体:
    - value: 新的配置值
    
    返回:
    - 更新结果
    """
    try:
        new_value = data.get("value", "")
        
        config = session.exec(select(SystemConfig).where(SystemConfig.key == config_key)).first()
        if not config:
            return {"success": False, "error": f"配置项 '{config_key}' 不存在"}
        
        # 更新配置值和时间戳
        config.value = new_value
        config.updated_at = datetime.now()
        
        session.add(config)
        session.commit()
        
        logger.info(f"系统配置 '{config_key}' 已更新为: {new_value}")
        
        return {
            "success": True,
            "message": f"配置项 '{config_key}' 更新成功",
            "config": {
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "updated_at": config.updated_at
            }
        }
        
    except Exception as e:
        logger.error(f"更新系统配置时发生错误: {e}", exc_info=True)
        return {"success": False, "error": f"更新配置失败: {str(e)}"}

@app.post("/pin-file")
async def pin_file(
    data: Dict[str, Any] = Body(...),
    task_mgr: TaskManager = Depends(get_task_manager),
    session: Session = Depends(get_session)
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

        # 在创建任务前检查多模态向量化所需的模型配置
        lancedb_mgr = LanceDBMgr(os.path.dirname(app.state.db_path))
        models_mgr = ModelsMgr(session)
        multivector_mgr = MultiVectorMgr(session, lancedb_mgr, models_mgr)
        
        # 检查多模态向量化所需的模型是否已配置
        if not multivector_mgr.check_multivector_model_availability():
            logger.warning(f"Pin文件失败，多模态向量化所需的模型配置缺失: {file_path}")
            return {
                "success": False,
                "task_id": None,
                "error_type": "model_missing",
                "message": "多模态向量化需要配置文本模型、视觉模型，请前往设置页面进行配置",
                "missing_models": ["文本模型", "视觉模型"]
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

        # 设置日志目录
        db_dir = os.path.dirname(os.path.abspath(args.db_path))
        logging_dir = os.path.join(db_dir, "logs")
        if not os.path.exists(logging_dir):
            os.makedirs(logging_dir, exist_ok=True)
        setup_logging(logging_dir)
        logger = logging.getLogger(__name__)
        logger.info("API服务程序启动")
        logger.info(f"命令行参数: port={args.port}, host={args.host}, db_path={args.db_path}")

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
