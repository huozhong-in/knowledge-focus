import os
import sys
import argparse
import logging
import time
import threading
import signal
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from utils import kill_process_on_port, monitor_parent, kill_orphaned_processes
from sqlmodel import create_engine, Session, select
from sqlalchemy import Engine, event, text
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
# API路由导入将在lifespan函数中进行

# # 初始化logger
logger = logging.getLogger()

# --- SQLite WAL Mode Setup ---
def setup_sqlite_wal_mode(engine):
    """为SQLite引擎设置WAL模式和优化参数"""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """设置SQLite优化参数和WAL模式"""
        cursor = dbapi_connection.cursor()
        # 启用WAL模式（Write-Ahead Logging）
        # WAL模式允许读写操作并发执行，显著减少锁定冲突
        cursor.execute("PRAGMA journal_mode=WAL")
        # 设置同步模式为NORMAL，在WAL模式下提供良好的性能和安全性平衡
        cursor.execute("PRAGMA synchronous=NORMAL")
        # 设置缓存大小（负数表示KB，这里设置为64MB）
        cursor.execute("PRAGMA cache_size=-65536")
        # 启用外键约束
        cursor.execute("PRAGMA foreign_keys=ON")
        # 设置临时存储为内存模式
        cursor.execute("PRAGMA temp_store=MEMORY")
        # 设置WAL自动检查点阈值（页面数）
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.close()

def create_optimized_sqlite_engine(sqlite_url, **kwargs):
    """创建优化的SQLite引擎，自动配置WAL模式"""
    default_connect_args = {"check_same_thread": False, "timeout": 30}
    # 合并用户提供的connect_args
    if "connect_args" in kwargs:
        default_connect_args.update(kwargs["connect_args"])
    kwargs["connect_args"] = default_connect_args
    # 创建引擎
    engine = create_engine(sqlite_url, echo=False, **kwargs)
    # 设置WAL模式
    setup_sqlite_wal_mode(engine)
    return engine

# --- Centralized Logging Setup ---
def setup_logging(logging_dir: str):
    """
    Configures the root logger for the application.

    args:
        logging_dir (str): The directory where log files will be stored.
    """
    
    try:
        # Determine log directory
        log_dir = Path(logging_dir) / 'logs'
        # 确保日志目录存在
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_filename = f'api_{time.strftime("%Y%m%d")}.log'
        log_filepath = log_dir / log_filename
        
        # 获取根日志器
        root_logger = logging.getLogger()
        
        # 清除可能存在的默认handlers，避免重复
        if root_logger.handlers:
            root_logger.handlers.clear()
            
        # 设置日志级别
        root_logger.setLevel(logging.INFO)
        
        # 创建formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Console handler - 输出到控制台
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # File handler - 输出到文件
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # 防止日志传播到父logger，避免重复输出
        root_logger.propagate = False
        
        print(f"日志配置成功: 文件路径 {log_filepath}")

    except Exception as e:
        print(f"Failed to set up logging: {e}", file=sys.stderr)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 重新配置logging以确保uvicorn启动后仍然有效
    if hasattr(app.state, "db_path"):
        db_directory = os.path.dirname(app.state.db_path)
        setup_logging(logging_dir=db_directory)
    
    # 在应用启动时执行初始化操作
    logger.info("应用正在启动...")
    
    try:
        logger.info(f"调试信息: Python版本 {sys.version}")
        logger.info(f"调试信息: 当前工作目录 {os.getcwd()}")
        
        # 初始化数据库引擎
        if hasattr(app.state, "db_path"):
            sqlite_url = f"sqlite:///{app.state.db_path}"
            logger.info(f"初始化数据库引擎，URL: {sqlite_url}")
            # 保存数据库目录路径供其他组件使用
            app.state.db_directory = os.path.dirname(app.state.db_path)
            try:
                # 创建优化的SQLite数据库引擎，自动配置WAL模式
                app.state.engine = create_optimized_sqlite_engine(
                    sqlite_url,
                    pool_size=5,       # 设置连接池大小
                    max_overflow=10,   # 允许的最大溢出连接数
                    pool_timeout=30,   # 获取连接的超时时间
                    pool_recycle=1800  # 30分钟回收一次连接
                )
                logger.info("SQLite WAL模式和优化参数已设置")
                logger.info(f"数据库引擎已初始化，路径: {app.state.db_path}")
                
                # 初始化数据库结构 - 使用单连接方法避免连接竞争
                try:
                    logger.info("开始数据库结构初始化...")
                    # 使用单个连接完成所有数据库初始化操作
                    with app.state.engine.connect() as conn:
                        logger.info("设置WAL模式和优化参数...")
                        # 显式设置WAL模式和优化参数（确保在生产环境中也正确设置）
                        conn.execute(text("PRAGMA journal_mode=WAL"))
                        conn.execute(text("PRAGMA synchronous=NORMAL"))
                        conn.execute(text("PRAGMA cache_size=-65536"))
                        conn.execute(text("PRAGMA foreign_keys=ON"))
                        conn.execute(text("PRAGMA temp_store=MEMORY"))
                        conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
                        
                        # 验证WAL模式设置
                        journal_mode = conn.execute(text("PRAGMA journal_mode")).fetchone()[0]
                        if journal_mode.upper() != 'WAL':
                            logger.warning(f"WAL模式设置可能失败，当前模式: {journal_mode}")
                        else:
                            logger.info("WAL模式设置成功")

                        # 最终提交连接级别的事务
                        conn.commit()
                    
                    db_mgr = DBManager(app.state.engine)
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
            kill_orphaned_processes("Python", "task_processor")
            kill_orphaned_processes("python", "high_priority_task_processor")
            kill_orphaned_processes("Python", "high_priority_task_processor")
        except Exception as proc_err:
            logger.error(f"清理孤立进程失败: {str(proc_err)}", exc_info=True)
        
        # 初始化后台任务处理线程（使用共享引擎）
        try:
            logger.info("初始化后台任务处理线程...")
            # 创建一个事件来优雅地停止线程
            app.state.task_processor_stop_event = threading.Event()
            app.state.task_processor_thread = threading.Thread(
                target=task_processor,
                args=(app.state.engine, app.state.db_directory, app.state.task_processor_stop_event),
                daemon=True
            )
            app.state.task_processor_thread.start()
            logger.info("后台任务处理线程已启动")
        except Exception as e:
            logger.error(f"初始化后台任务处理线程失败: {e}", exc_info=True)
            raise
        
        # 初始化高优先级任务处理线程（使用共享引擎）
        try:
            logger.info("初始化高优先级任务处理线程...")
            # 创建一个事件来优雅地停止线程
            app.state.high_priority_task_processor_stop_event = threading.Event()
            app.state.high_priority_task_processor_thread = threading.Thread(
                target=high_priority_task_processor,
                args=(app.state.engine, app.state.db_directory, app.state.high_priority_task_processor_stop_event),
                daemon=True
            )
            app.state.high_priority_task_processor_thread.start()
            logger.info("高优先级任务处理线程已启动")
        except Exception as e:
            logger.error(f"初始化高优先级任务处理线程失败: {e}", exc_info=True)
            raise
        
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

        # 注册API路由（在数据库初始化完成后）
        try:
            logger.info("注册API路由...")
            
            # 动态导入API路由
            from models_api import get_router as get_models_router
            from tagging_api import get_router as get_tagging_router
            from chatsession_api import get_router as get_chatsession_router
            from myfolders_api import get_router as get_myfolders_router
            from screening_api import get_router as get_screening_router
            from search_api import get_router as get_search_router
            from unified_tools_api import get_router as get_tools_router
            from documents_api import get_router as get_documents_router
            from user_api import get_router as get_user_router
            
            # 注册各个API路由
            models_router = get_models_router(get_engine=get_engine, base_dir=app.state.db_directory)
            app.include_router(models_router, prefix="", tags=["models"])
            
            tagging_router = get_tagging_router(get_engine=get_engine, base_dir=app.state.db_directory)
            app.include_router(tagging_router, prefix="", tags=["tagging"])
            
            chatsession_router = get_chatsession_router(get_engine=get_engine, base_dir=app.state.db_directory)
            app.include_router(chatsession_router, prefix="", tags=["chat-sessions"])
            
            myfolders_router = get_myfolders_router(get_engine=get_engine)
            app.include_router(myfolders_router, prefix="", tags=["myfolders"])
            
            screening_router = get_screening_router(get_engine=get_engine)
            app.include_router(screening_router, prefix="", tags=["screening"])
            
            search_router = get_search_router(get_engine=get_engine, base_dir=app.state.db_directory)
            app.include_router(search_router, prefix="", tags=["search"])
            
            tools_router = get_tools_router(get_engine=get_engine)
            app.include_router(tools_router, prefix="", tags=["tools"])
            
            documents_router = get_documents_router(get_engine=get_engine, base_dir=app.state.db_directory)
            app.include_router(documents_router, prefix="", tags=["documents"])
            
            # 用户认证相关路由
            user_router = get_user_router(get_engine=get_engine)
            app.include_router(user_router, prefix="", tags=["user", "auth"])
            
            logger.info("所有API路由注册完成")
        except Exception as router_err:
            logger.error(f"注册API路由失败: {str(router_err)}", exc_info=True)
            raise

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
        
        try:
            if hasattr(app.state, "high_priority_task_processor_thread") and app.state.high_priority_task_processor_thread.is_alive():
                logger.info("正在停止高优先级任务处理线程...")
                app.state.high_priority_task_processor_stop_event.set()
                app.state.high_priority_task_processor_thread.join(timeout=5) # 等待5秒
                if app.state.high_priority_task_processor_thread.is_alive():
                    logger.warning("高优先级任务处理线程在5秒内未停止")
                else:
                    logger.info("高优先级任务处理线程已停止")
        except Exception as e:
            logger.error(f"停止高优先级任务处理线程失败: {e}", exc_info=True)
        
        # 清理可能残留的子进程
        try:
            logger.info("清理可能残留的子进程...")
            kill_orphaned_processes("python", "task_processor")
            kill_orphaned_processes("Python", "task_processor")
            kill_orphaned_processes("python", "high_priority_task_processor")
            kill_orphaned_processes("Python", "high_priority_task_processor")
        except Exception as cleanup_err:
            logger.error(f"清理残留进程失败: {str(cleanup_err)}", exc_info=True)
        
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

def get_engine():
    """FastAPI依赖函数，用于获取数据库引擎"""
    if not hasattr(app.state, "engine") or app.state.engine is None:
        # 确保数据库引擎已初始化
        raise RuntimeError("数据库引擎未初始化")
    return app.state.engine

# 获取 TaskManager 的依赖函数
def get_task_manager(engine: Engine = Depends(get_engine)) -> TaskManager:
    """获取任务管理器实例"""
    return TaskManager(engine)

# 任务处理者
def _process_task(task: Task, lancedb_mgr, task_mgr: TaskManager, engine: Engine) -> None:
    """通用任务处理逻辑"""
    models_mgr = ModelsMgr(engine=engine, base_dir=app.state.db_directory)
    file_tagging_mgr = FileTaggingMgr(engine=engine, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)
    multivector_mgr = MultiVectorMgr(engine=engine, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)

    if task.task_type == TaskType.TAGGING.value:
        # 检查模型可用性
        if not file_tagging_mgr.check_file_tagging_model_availability():
            logger.warning(f"文件打标签模型暂不可用（可能正在下载或加载中），任务 {task.id} 将保持 PENDING 状态等待重试")
            # 不更新任务状态，保持为 PENDING，让任务处理线程稍后重试
            # 这样可以等待内置模型下载和加载完成
            return
        
        # 高优先级任务: 单个文件处理
        if task.priority == TaskPriority.HIGH.value and task.extra_data and 'screening_result_id' in task.extra_data:
            logger.info(f"开始处理高优先级文件打标签任务 (Task ID: {task.id})")
            success = file_tagging_mgr.process_single_file_task(task.extra_data['screening_result_id'])
            if success:
                task_mgr.update_task_status(task.id, TaskStatus.COMPLETED, result=TaskResult.SUCCESS)
                
                # 检查是否需要自动衔接MULTIVECTOR任务（仅当文件被pin时）
                if multivector_mgr.check_multivector_model_availability():
                    _check_and_create_multivector_task(engine, task_mgr, task.extra_data.get('screening_result_id'))
            else:
                task_mgr.update_task_status(task.id, TaskStatus.FAILED, result=TaskResult.FAILURE)
        # 中低优先级任务: 批量处理
        else:
            logger.info(f"开始批量文件打标签任务 (Task ID: {task.id})")
            result_data = file_tagging_mgr.process_pending_batch(task_id=task.id)
            
            # 无论批量任务处理了多少文件，都将触发任务文件打标签为完成
            task_mgr.update_task_status(
                task.id, 
                TaskStatus.COMPLETED, 
                result=TaskResult.SUCCESS, 
                message=f"批量处理完成: 处理了 {result_data.get('processed', 0)} 个文件。"
            )
    
    elif task.task_type == TaskType.MULTIVECTOR.value:
        if not multivector_mgr.check_multivector_model_availability():
            logger.warning(f"多模态向量化模型暂不可用（可能正在下载或加载中），任务 {task.id} 将保持 PENDING 状态等待重试")
            # 不更新任务状态，保持为 PENDING，让任务处理线程稍后重试
            # 这样可以等待内置模型下载和加载完成
            return
        
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
            # TODO 中低优先级任务: 批量处理（未来支持）
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


def _generic_task_processor(engine, db_directory: str, stop_event: threading.Event, processor_name: str, task_getter_func: str, sleep_duration: int = 5):
    """通用任务处理器（优化版：缩短事务持续时间）
    
    Args:
        engine: 共享的SQLAlchemy引擎实例
        db_directory: 数据库目录路径（用于LanceDB）
        stop_event: 停止事件
        processor_name: 处理器名称（用于日志）
        task_getter_func: TaskManager中获取任务的方法名
        sleep_duration: 没有任务时的等待时间（秒）
    """
    logger.info(f"{processor_name}已启动")
    
    lancedb_mgr = LanceDBMgr(base_dir=db_directory)

    while not stop_event.is_set():
        task_id = None
        task_to_process = None

        try:
            # --- 获取并锁定任务 ---
            # 获取任务并标记为处理中
            try:
                task_mgr = TaskManager(engine=engine)
                task_getter = getattr(task_mgr, task_getter_func)
                locked_task: Task = task_getter()

                if locked_task:
                    task_id = locked_task.id
                    # 创建一个任务的非托管副本，以便在会话关闭后使用
                    task_to_process = {
                        "id": locked_task.id,
                        "task_name": locked_task.task_name,
                        "task_type": locked_task.task_type,
                        "priority": locked_task.priority,
                        "extra_data": locked_task.extra_data,
                    }
                    logger.info(f"{processor_name}已锁定任务: ID={task_id}")
                else:
                    # 没有任务，直接结束本次循环
                    pass
            except Exception as e:
                logger.error(f"{processor_name}在获取任务时发生错误: {e}", exc_info=True)

            # --- 如果没有任务，则休眠并继续 ---
            if not task_to_process:
                time.sleep(sleep_duration)
                continue

            # --- 执行耗时操作 ---
            logger.info(f"{processor_name}开始处理任务: ID={task_id}, Name='{task_to_process['task_name']}'")
            try:
                task_mgr_for_processing = TaskManager(engine=engine)
                
                # 从字典重建Task对象，或从数据库重新获取
                task_obj_for_processing = task_mgr_for_processing.get_task(task_id)
                if not task_obj_for_processing:
                    raise ValueError(f"任务 {task_id} 在处理前消失")

                # 调用原始的任务处理逻辑，但现在它在一个独立的会话中运行
                # 这个会话仍然可能长时间运行，但它不应该持有对task表的写锁
                _process_task(task=task_obj_for_processing, lancedb_mgr=lancedb_mgr, task_mgr=task_mgr_for_processing, engine=engine)
                
                
                # --- 事务三: 更新最终结果 ---
                # 任务成功完成
                task_mgr_final = TaskManager(engine=engine)
                task_mgr_final.update_task_status(task_id, TaskStatus.COMPLETED, result=TaskResult.SUCCESS)
                logger.info(f"{processor_name}成功完成任务: ID={task_id}")

            except Exception as task_error:
                logger.error(f"{processor_name}处理任务 {task_id} 时发生错误: {task_error}", exc_info=True)
                # --- 事务三 (失败情况): 更新最终结果 ---
                task_mgr_final = TaskManager(engine=engine)
                task_mgr_final.update_task_status(task_id, TaskStatus.FAILED, result=TaskResult.FAILURE, message=str(task_error))
                logger.warning(f"{processor_name}任务失败: ID={task_id}")

        except Exception as e:
            logger.error(f"{processor_name}发生意外的顶层错误: {e}", exc_info=True)
            # 如果在获取任务ID后发生未知错误，也尝试标记任务失败
            if task_id:
                try:
                    task_mgr_final = TaskManager(engine=engine)
                    task_mgr_final.update_task_status(task_id, TaskStatus.FAILED, result=TaskResult.FAILURE, message=f"处理器顶层错误: {e}")
                except Exception as final_update_error:
                    logger.error(f"尝试标记任务 {task_id} 失败时再次出错: {final_update_error}", exc_info=True)
            time.sleep(30) # 发生严重错误时等待更长时间

    logger.info(f"{processor_name}已停止")


def task_processor(engine, db_directory: str, stop_event: threading.Event):
    """普通任务处理线程工作函数（处理所有优先级任务）"""
    _generic_task_processor(
        engine=engine,
        db_directory=db_directory,
        stop_event=stop_event,
        processor_name="普通任务处理线程",
        task_getter_func="get_and_lock_next_task",
        sleep_duration=5
    )


def high_priority_task_processor(engine, db_directory: str, stop_event: threading.Event):
    """高优先级任务处理线程工作函数（仅处理HIGH优先级任务）"""
    _generic_task_processor(
        engine=engine,
        db_directory=db_directory,
        stop_event=stop_event,
        processor_name="高优先级任务处理线程",
        task_getter_func="get_and_lock_next_high_priority_task",
        sleep_duration=2
    )

def _check_and_create_multivector_task(engine: Engine, task_mgr: TaskManager, screening_result_id: int):
    """
    检查文件是否处于pin状态，如果是则自动创建MULTIVECTOR任务
    
    Args:
        engine: 数据库引擎
        task_mgr: 任务管理器
        screening_result_id: 粗筛结果ID
    """
    if not screening_result_id:
        return
    
    try:
        with Session(bind=engine) as session:
            # 获取粗筛结果，包含文件路径信息
            screening_result = session.get(FileScreeningResult, screening_result_id)
            if not screening_result:
                logger.warning(f"未找到screening_result_id: {screening_result_id}")
                return
            
            file_path = screening_result.file_path
            
            # 检查文件是否在最近24小时内被pin过
            is_recently_pinned = _check_file_pin_status(file_path, task_mgr)
            
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

def _check_file_pin_status(file_path: str, task_mgr: TaskManager = Depends(get_task_manager)) -> bool:
    """
    检查文件是否在最近24小时内被pin过（即有成功的MULTIVECTOR任务）
    
    Args:
        file_path: 文件路径
        task_mgr: 任务管理器实例
        
    Returns:
        bool: 文件是否在最近24小时内被pin过
    """
    try:
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
    return {
        "Success": True,
        "message": "API服务运行中",
        "db_path": app.state.db_path,
        "db_pool_status": str(app.state.engine.pool.status()) if hasattr(app.state, "engine") and app.state.engine else "N/A"
        }

# 添加健康检查端点
@app.get("/health")
def health_check():
    """API健康检查端点，用于验证API服务是否正常运行"""
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat(),
    }

@app.get("/system-config/{config_key}")
def get_system_config(config_key: str, engine: Engine = Depends(get_engine)):
    """获取系统配置
    
    参数:
    - config_key: 配置键名
    
    返回:
    - 配置值和描述信息
    """
    try:
        with Session(bind=engine) as session:
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
    engine: Engine = Depends(get_engine),
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
        with Session(bind=engine) as session:
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
    engine: Engine = Depends(get_engine),
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
        from multivector_mgr import SUPPORTED_FORMATS
        file_ext = Path(file_path).suffix.split('.')[-1].lower()
        if file_ext not in SUPPORTED_FORMATS:
            logger.warning(f"Pin文件失败，不支持的文件类型: {file_ext}")
            return {
                "success": False,
                "task_id": None,
                "message": f"不支持的文件类型: {file_ext}，支持的类型: {SUPPORTED_FORMATS}"
            }

        # 在创建任务前检查多模态向量化所需的模型配置
        lancedb_mgr = LanceDBMgr(base_dir=app.state.db_directory)
        models_mgr = ModelsMgr(engine=engine, base_dir=app.state.db_directory)
        multivector_mgr = MultiVectorMgr(engine=engine, lancedb_mgr=lancedb_mgr, models_mgr=models_mgr)
        
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


def signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    print(f"接收到信号 {signum}，开始优雅关闭...")
    # 清理可能残留的子进程
    try:
        kill_orphaned_processes("python", "task_processor")
        kill_orphaned_processes("Python", "task_processor")
        kill_orphaned_processes("python", "high_priority_task_processor")
        kill_orphaned_processes("Python", "high_priority_task_processor")
    except Exception as e:
        print(f"信号处理器清理进程失败: {e}")
    sys.exit(0)

if __name__ == "__main__":
    try:
        # 注册信号处理器
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        parser = argparse.ArgumentParser()
        parser.add_argument("--port", type=int, default=60315, help="API服务监听端口")
        parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
        parser.add_argument("--db-path", type=str, default="knowledge-focus.db", help="数据库文件路径")
        args = parser.parse_args()

        print("API服务程序启动")
        print(f"命令行参数: port={args.port}, host={args.host}, db_path={args.db_path}")

        # 检查端口是否被占用，如果被占用则终止占用进程
        try:
            print(f"检查端口 {args.port} 是否被占用...")
            kill_process_on_port(args.port)
            time.sleep(2)  # 等待端口释放
            print(f"端口 {args.port} 已释放或本来就没被占用")
        except Exception as e:
            print(f"释放端口 {args.port} 失败: {str(e)}")
            # 继续执行，端口可能本来就没有被占用
        
        # 设置数据库路径
        app.state.db_path = args.db_path
        print(f"设置数据库路径: {args.db_path}")
        # 启动服务器
        print(f"API服务启动在: http://{args.host}:{args.port}")
        # 配置uvicorn日志，防止覆盖我们的日志配置
        uvicorn.run(
            app, 
            host=args.host, 
            port=args.port, 
            log_level="info",
            access_log=False,  # 禁用uvicorn的访问日志，使用我们自己的
            use_colors=False   # 禁用颜色输出，保持日志文件的整洁
        )
    
    except Exception as e:
        print(f"API服务启动失败: {str(e)}")

        # 返回退出码2，表示发生错误
        sys.exit(2)
