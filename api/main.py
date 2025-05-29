from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import uvicorn
import argparse
import os
import time
from utils import kill_process_on_port, monitor_parent, kill_orphaned_processes
import pathlib
import logging
from sqlmodel import create_engine, Session, select
import multiprocessing
from db_mgr import DBManager, TaskStatus, TaskResult, TaskType, TaskPriority, AuthStatus, MyFiles, FileCategory, FileFilterRule, FileExtensionMap, ProjectRecognitionRule
from task_mgr import TaskManager
from screening_mgr import ScreeningManager
from refine_mgr import RefineManager
from myfiles_mgr import MyFilesManager
from contextlib import asynccontextmanager
import asyncio
import threading
from datetime import datetime
import json
from enum import Enum
import sys  # 添加在文件顶部其他 import 语句附近

# 设置日志记录
logger = logging.getLogger(__name__) # Use __name__ for logger

# 记录启动时的环境信息
print(f"环境变量: TAURI_DEBUG={os.environ.get('TAURI_DEBUG')}, VSCODE_DEBUG={os.environ.get('VSCODE_DEBUG')}")
print(f"调试模式: {sys.argv}")
print(f"Python 版本: {sys.version}")
print(f"当前工作目录: {os.getcwd()}")

try:
    # 确定日志目录 - 尝试多种方式确保找到正确路径
    script_path = os.path.abspath(__file__)
    print(f"脚本路径: {script_path}")
    
    # 首先尝试直接从脚本路径获取
    parents_logs_dir = pathlib.Path(script_path).parent / 'logs'
    
    # 如果上面的目录不存在，尝试从当前工作目录
    if not parents_logs_dir.exists():
        current_dir = pathlib.Path(os.getcwd())
        if 'api' in str(current_dir):
            # 如果当前目录包含 'api'
            parents_logs_dir = current_dir / 'logs'
        else:
            # 尝试在当前目录下找 api/logs
            parents_logs_dir = current_dir / 'api' / 'logs'
    
    print(f"日志目录路径: {parents_logs_dir}")
    # 确保日志目录存在
    parents_logs_dir.mkdir(exist_ok=True, parents=True)
    
    logger.setLevel(logging.INFO)
    
    # 添加控制台处理器，确保日志同时输出到终端
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)
    
    # 添加文件处理器
    log_filename = f'api_{time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time()))}.log'
    log_filepath = parents_logs_dir / log_filename
    print(f"日志文件路径: {log_filepath}")
    
    # 确保不重复添加处理器
    file_handler_exists = False
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            file_handler_exists = True
            break
    
    if not file_handler_exists:
        try:
            file_handler = logging.FileHandler(log_filepath)
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
            print(f"文件日志处理器已添加: {log_filepath}")
        except Exception as e:
            print(f"添加文件日志处理器失败: {e}")
            # 记录详细的错误信息
            import traceback
            traceback.print_exc()
except Exception as e:
    print(f"设置日志记录时出错: {e}")
    import traceback
    traceback.print_exc()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 在应用启动时执行初始化操作
    logger.info("应用正在启动...")
    
    try:
        logger.info(f"调试信息: Python版本 {sys.version}")
        logger.info(f"调试信息: 当前工作目录 {os.getcwd()}")
        
        # 初始化数据库引擎
        if hasattr(app.state, "db_path"):
            sqlite_url = f"sqlite:///{app.state.db_path}"
            logger.info(f"初始化数据库引擎，URL: {sqlite_url}")
            try:
                app.state.engine = create_engine(sqlite_url, echo=False)
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
        
        # 初始化进程池和任务处理者
        try:
            # 强制使用单worker模式，以确保文件处理过程中具有全局一致的视角
            # 这对于精炼过程中的文件关联分析和聚类功能至关重要
            # 多worker可能导致处理过程中的全局状态不一致，影响分析质量
            from config import FORCE_SINGLE_WORKER
            processes = 1 if FORCE_SINGLE_WORKER else max(1, multiprocessing.cpu_count() // 2)
            logger.info(f"初始化进程池，强制单worker模式: {FORCE_SINGLE_WORKER}, 工作进程数: {processes}")
            app.state.process_pool = multiprocessing.Pool(processes=processes)
            
            for processor_id in range(processes):
                logger.info(f"启动工作进程 {processor_id}...")
                app.state.process_pool.apply_async(task_processor, args=(processor_id, app.state.db_path))
            logger.info(f"所有 {processes} 个工作进程已启动")
        except Exception as pool_err:
            logger.error(f"初始化进程池失败: {str(pool_err)}", exc_info=True)
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
            if hasattr(app.state, "process_pool") and app.state.process_pool is not None:
                logger.info("关闭进程池...")
                app.state.process_pool.close()
                app.state.process_pool.terminate()  # 终止所有工作进程
                app.state.process_pool.join()
                logger.info("进程池已关闭")
        except Exception as pool_close_err:
            logger.error(f"关闭进程池失败: {str(pool_close_err)}", exc_info=True)
        
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

# 获取 MyFilesManager 的依赖函数
def get_myfiles_manager(session: Session = Depends(get_session)):
    """获取文件/文件夹管理器实例"""
    return MyFilesManager(session)

@app.post("/init_db")
def init_db(session: Session = Depends(get_session)):
    """首次打开App，初始化数据库结构"""
    print("初始化数据库结构")
    db_mgr = DBManager(session)
    db_mgr.init_db()

    return {"message": "数据库结构已初始化"}

# 新增：获取所有配置信息的API端点
@app.get("/config/all")
def get_all_configuration(
    session: Session = Depends(get_session),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """
    获取所有Rust端进行文件处理所需的配置信息。
    包括文件分类、粗筛规则、文件扩展名映射、项目识别规则以及监控的文件夹列表。
    """
    try:
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
        
        return {
            "file_categories": file_categories,
            "file_filter_rules": file_filter_rules,
            "file_extension_maps": file_extension_maps,
            "project_recognition_rules": project_recognition_rules,
            "monitored_folders": monitored_folders,
            "full_disk_access": full_disk_access  # 添加此字段告知客户端完全磁盘访问权限状态
        }
    except Exception as e:
        logger.error(f"Error fetching all configuration: {e}", exc_info=True)
        # Consider raising HTTPException for client feedback
        return {"error": str(e)}

# 任务处理者
def task_processor(processor_id: int, db_path: str = None):
    """处理任务的工作进程(实现了超时控制)"""
    logger.info(f"{processor_id}号任务处理者已启动")
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url, echo=False)
    session = Session(engine)
    
    # 初始化各种管理器
    _task_mgr = TaskManager(session)
    _screening_mgr = ScreeningManager(session)
    _refine_mgr = RefineManager(session)
    
    # 创建线程池用于执行任务，便于实现超时控制
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            while True:
                # 获取下一个待处理任务
                task = _task_mgr.get_next_task()
                
                if not task:
                    time.sleep(2)  # 没有任务时等待
                    continue
                
                # 将任务状态更新为运行中
                _task_mgr.update_task_status(task.id, TaskStatus.RUNNING)
                logger.info(f"{processor_id}号处理任务: {task.id} - {task.task_name}")
                
                # 根据任务类型确定处理函数
                if task.task_type == TaskType.REFINE.value:
                    process_func = lambda: process_refine_task(task, _screening_mgr, _refine_mgr)
                elif task.task_type == TaskType.INSIGHT.value:
                    process_func = lambda: process_insight_task(task, _refine_mgr)
                else:
                    logger.warning(f"未知任务类型: {task.task_type}")
                    _task_mgr.update_task_status(
                        task.id, 
                        TaskStatus.FAILED, 
                        TaskResult.FAILURE, 
                        f"未知任务类型: {task.task_type}"
                    )
                    continue
                
                # 提交任务到线程池，设置超时时间（秒）
                TASK_TIMEOUT = 600  # 10分钟超时，为批量处理提供充足时间
                future = executor.submit(process_func)
                
                try:
                    # 等待任务完成，最多等待TASK_TIMEOUT秒
                    result = future.result(timeout=TASK_TIMEOUT)
                    # 更新任务状态
                    if result:
                        _task_mgr.update_task_status(task.id, TaskStatus.COMPLETED, TaskResult.SUCCESS)
                        logger.info(f"{processor_id}号任务 {task.id} 处理完成")
                    else:
                        _task_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.FAILURE, "任务处理失败")
                        logger.error(f"{processor_id}号任务 {task.id} 处理失败")
                except TimeoutError:
                    # 任务超时处理
                    logger.error(f"{processor_id}号任务 {task.id} 处理超时")
                    _task_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.TIMEOUT, f"任务处理超时（{TASK_TIMEOUT}秒）")
                except Exception as e:
                    # 任务异常处理
                    logger.error(f"{processor_id}号任务 {task.id} 处理异常: {str(e)}")
                    _task_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.FAILURE, str(e))
            
        except Exception as e:
            logger.error(f"{processor_id}号任务处理失败: {str(e)}")

def process_refine_task(task, screening_mgr, refine_mgr) -> bool:
    """处理文件精炼任务
    
    Args:
        task: 任务对象
        screening_mgr: 粗筛管理器
        refine_mgr: 精炼管理器
        
    Returns:
        处理成功返回True，失败返回False
    """
    # 获取任务额外数据
    extra_data = {}
    if hasattr(task, 'extra_data') and task.extra_data:
        try:
            if isinstance(task.extra_data, str):
                extra_data = json.loads(task.extra_data)
            elif isinstance(task.extra_data, dict):
                extra_data = task.extra_data
        except Exception as e:
            logger.error(f"解析任务额外数据失败: {str(e)}")
    
    # 检查是否包含粗筛结果ID
    screening_result_id = extra_data.get("screening_result_id")
    if screening_result_id:
        # 处理单个文件
        logger.info(f"处理单个文件精炼任务: 粗筛结果ID {screening_result_id}")
        refine_result = refine_mgr.process_pending_file(screening_result_id)
        return refine_result is not None
    else:
        # 批量处理
        file_count = extra_data.get("file_count", 0)
        logger.info(f"处理批量精炼任务: 预计 {file_count} 个文件")
        
        # 获取一批待处理的粗筛结果，增加批量大小
        batch_size = min(500, max(50, file_count))  # 根据任务规模动态调整批量大小，增加处理能力
        pending_results = screening_mgr.get_pending_results(limit=batch_size)
        
        if not pending_results:
            logger.warning("找不到待处理的粗筛结果")
            return False
        
        total_count = len(pending_results)
        logger.info(f"发现 {total_count} 个待处理的粗筛结果")
        
        # 进度跟踪变量
        success_count = 0
        processed_count = 0
        last_progress_log = time.time()
        progress_interval = 5  # 每5秒记录一次进度
        
        # 批量处理文件
        for index, result in enumerate(pending_results):
            try:
                # 定期记录进度，避免大批量处理时日志过于冗长
                current_time = time.time()
                if current_time - last_progress_log >= progress_interval:
                    logger.info(f"批量处理进度: {processed_count}/{total_count} 完成，{success_count} 成功")
                    last_progress_log = current_time
                    
                # 处理单个文件
                refine_result = refine_mgr.process_pending_file(result.id)
                processed_count += 1
                
                if refine_result:
                    success_count += 1
                    
                # 每处理100个文件记录一次详细进度
                if processed_count % 100 == 0:
                    logger.info(f"已完成 {processed_count}/{total_count} 个文件，成功率: {success_count/processed_count*100:.2f}%")
                    
            except Exception as e:
                processed_count += 1
                logger.error(f"处理粗筛结果 {result.id} ({result.file_path}) 失败: {str(e)}")
        
        # 记录最终处理结果
        success_rate = 0 if total_count == 0 else (success_count/total_count*100)
        logger.info(f"批量处理完成: {success_count}/{total_count} 个文件成功，成功率: {success_rate:.2f}%")
        return success_count > 0

def process_insight_task(task, refine_mgr) -> bool:
    """处理洞察生成任务
    
    Args:
        task: 任务对象
        refine_mgr: 精炼管理器
        
    Returns:
        处理成功返回True，失败返回False
    """
    return False
    # 获取任务额外数据
    # extra_data = {}
    # if hasattr(task, 'extra_data') and task.extra_data:
    #     try:
    #         if isinstance(task.extra_data, str):
    #             extra_data = json.loads(task.extra_data)
    #         elif isinstance(task.extra_data, dict):
    #             extra_data = task.extra_data
    #     except Exception:
    #         pass
    
    # # 获取分析天数
    # days = extra_data.get("days", 7)
    
    # # 生成洞察
    # logger.info(f"生成洞察任务: 分析最近 {days} 天的文件")
    # insights = refine_mgr.generate_insights(days)
    
    # # 检查结果
    # if insights:
    #     insight_types = {}
    #     for insight in insights:
    #         insight_type = insight.insight_type
    #         insight_types[insight_type] = insight_types.get(insight_type, 0) + 1
        
    #     logger.info(f"生成了 {len(insights)} 条洞察: {insight_types}")
    #     return True
    # else:
    #     logger.warning("没有生成任何洞察")
    #     return False

# 获取 ScreeningManager 的依赖函数
def get_screening_manager(session: Session = Depends(get_session)):
    """获取文件粗筛结果管理类实例"""
    return ScreeningManager(session)

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
    - tags: 标签列表（可选）
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
            
            # 这里我们使用精炼任务类型统一处理
            # 并将单一文件任务也设置为高优先级，确保优先处理单一文件任务
            task = task_mgr.add_task(
                task_name=task_name, 
                task_type=TaskType.REFINE.value,  # 使用精炼任务类型，与批处理保持一致
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
    - auto_create_tasks: 是否自动创建任务（可选，默认 True）
    """
    try:
        # 从请求体中提取数据和参数
        logger.info(f"接收到批量文件粗筛请求，请求体键名: {list(request.keys())}")
        
        # 适配Rust客户端发送的格式: {data_list: [...], auto_create_tasks: true}
        if "data_list" in request:
            data_list = request.get("data_list", [])
            auto_create_tasks = request.get("auto_create_tasks", True)
        # 兼容旧格式: {files: [...], auto_create_tasks: true} 或者直接是列表
        elif isinstance(request, dict):
            auto_create_tasks = request.get("auto_create_tasks", True)
            data_list = request.get("files", [])
        else:
            # 假设请求体本身就是列表
            data_list = request
            auto_create_tasks = True
            
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
        
        # 批量添加粗筛结果
        result = screening_mgr.add_batch_screening_results(data_list)
        
        # 创建一个批处理任务（只要有成功添加的文件就创建任务）
        if result["success"] > 0:
            # 取消之前的批量精炼任务（如果有）
            # 这确保我们只处理最新的任务，避免资源浪费在过时的任务上
            canceled_tasks = task_mgr.cancel_old_tasks(TaskType.REFINE.value)
            if canceled_tasks > 0:
                logger.info(f"已取消 {canceled_tasks} 个旧的精炼任务")
                
            # 创建一个新的批处理任务，使用高优先级确保及时处理
            task_name = f"批量处理文件: {result['success']} 个文件"
            task = task_mgr.add_task(
                task_name=task_name, 
                task_type=TaskType.REFINE.value,  # 使用精炼任务类型
                priority=TaskPriority.HIGH.value,  # 设置为高优先级，确保最新批次优先处理
                extra_data={"file_count": result["success"]}
            )
            result["task_id"] = task.id
            logger.info(f"已创建精炼任务 ID: {task.id}，处理 {result['success']} 个文件")
        
        return {
            "success": result["success"] > 0,
            "processed_count": result["success"],
            "failed_count": result["failed"],
            "task_id": result.get("task_id"),  # 返回任务ID
            "errors": result.get("errors"),
            "message": f"已处理 {result['success']} 个文件，失败 {result['failed']} 个，并创建精炼任务"
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
        if category_id is not None:
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

@app.get("/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "API服务正常运行中"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（可选，因为这阶段产品设计只用websocket向前端推送通知）
            _ = await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 洞察相关API
@app.post("/insights/generate")
def generate_insights(
    data: Dict[str, Any] = Body(...),
    session: Session = Depends(get_session),
    task_mgr: TaskManager = Depends(lambda session=Depends(get_session): TaskManager(session))
):
    """创建洞察生成任务"""
    try:
        days = data.get("days", 7)
        

        if not isinstance(days, int) or days <= 0:
            return {
                "success": False,
                "message": "无效的参数: days 必须是一个正整数"
            }
        # 创建洞察生成任务
        task = task_mgr.add_task(
            task_name=f"生成文件洞察 (最近{days}天)",
            task_type=TaskType.INSIGHT.value,
            priority=data.get("priority", "medium"),
            extra_data={"days": days}
        )
        
        return {
            "success": True,
            "task_id": task.id,
            "message": f"已创建洞察生成任务，将分析最近 {days} 天的文件"
        }
        
    except Exception as e:
        logger.error(f"创建洞察生成任务失败: {str(e)}")
        return {
            "success": False,
            "message": f"创建洞察生成任务失败: {str(e)}"
        }

@app.get("/insights")
def get_insights(
    limit: int = 10,
    only_unread: bool = False,
    insight_type: str = None,
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """获取洞察列表"""
    try:
        insights = refine_mgr.get_insights(limit, only_unread, insight_type)
        
        # 转换为可序列化的字典
        insights_data = []
        for insight in insights:
            insight_dict = insight.model_dump()
            insights_data.append(insight_dict)
        
        return {
            "success": True,
            "count": len(insights_data),
            "data": insights_data
        }
        
    except Exception as e:
        logger.error(f"获取洞察列表失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取洞察列表失败: {str(e)}"
        }

# @app.get("/insight-types")
# def get_insight_types():
#     """获取可用的洞察类型"""
#     try:
#         insight_types = [
#             {"value": InsightType.FILE_ACTIVITY.value, "label": "文件活动"},
#             {"value": InsightType.PROJECT_UPDATE.value, "label": "项目更新"},
#             {"value": InsightType.CLEANUP.value, "label": "清理建议"},
#             {"value": InsightType.CONTENT_HIGHLIGHT.value, "label": "内容亮点"},
#             {"value": InsightType.USAGE_PATTERN.value, "label": "使用模式"},
#             {"value": InsightType.CUSTOM.value, "label": "自定义洞察"}
#         ]
        
#         return {
#             "success": True,
#             "data": insight_types
#         }
        
#     except Exception as e:
#         logger.error(f"获取洞察类型失败: {str(e)}")
#         return {
#             "success": False,
#             "message": f"获取洞察类型失败: {str(e)}"
#         }

# @app.put("/insights/{insight_id}/read")
# def mark_insight_as_read(
#     insight_id: int,
#     refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
# ):
#     """将洞察标记为已读"""
#     try:
#         success = refine_mgr.mark_insight_as_read(insight_id)
#         if not success:
#             return {
#                 "success": False,
#                 "message": f"标记洞察 {insight_id} 为已读失败"
#             }
        
#         return {
#             "success": True,
#             "message": f"已将洞察 {insight_id} 标记为已读"
#         }
        
#     except Exception as e:
#         logger.error(f"标记洞察为已读失败: {str(e)}")
#         return {
#             "success": False,
#             "message": f"标记洞察为已读失败: {str(e)}"
#         }

# @app.put("/insights/{insight_id}/dismiss")
# def dismiss_insight(
#     insight_id: int,
#     refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
# ):
#     """忽略洞察"""
#     try:
#         success = refine_mgr.dismiss_insight(insight_id)
#         if not success:
#             return {
#                 "success": False,
#                 "message": f"忽略洞察 {insight_id} 失败"
#             }
        
#         return {
#             "success": True,
#             "message": f"已忽略洞察 {insight_id}"
#         }
        
#     except Exception as e:
#         logger.error(f"忽略洞察失败: {str(e)}")
#         return {
#             "success": False,
#             "message": f"忽略洞察失败: {str(e)}"
#         }

# 项目相关API
@app.post("/projects")
def create_project(
    data: Dict[str, Any] = Body(...),
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """创建新项目"""
    try:
        name = data.get("name")
        path = data.get("path")
        project_type = data.get("project_type")
        
        if not path:
            return {
                "success": False,
                "message": "项目名称和路径不能为空"
            }
        
        project = refine_mgr.create_project(name, path, project_type)
        if not project:
            return {
                "success": False,
                "message": "创建项目失败"
            }
        
        # 转换为可序列化的字典
        project_data = project.model_dump()
        
        return {
            "success": True,
            "data": project_data,
            "message": f"已创建项目: {name}"
        }
        
    except Exception as e:
        logger.error(f"创建项目失败: {str(e)}")
        return {
            "success": False,
            "message": f"创建项目失败: {str(e)}"
        }

@app.get("/projects")
def get_projects(
    limit: int = 50,
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """获取项目列表"""
    try:
        projects = refine_mgr.get_projects(limit)
        
        # 转换为可序列化的字典
        projects_data = [project.model_dump() for project in projects]
        
        return {
            "success": True,
            "count": len(projects_data),
            "data": projects_data
        }
        
    except Exception as e:
        logger.error(f"获取项目列表失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取项目列表失败: {str(e)}"
        }

@app.get("/projects/{project_id}/files")
def get_project_files(
    project_id: int,
    limit: int = 100,
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """获取项目下的文件"""
    try:
        files = refine_mgr.get_by_project_id(project_id, limit)
        
        # 转换为可序列化的字典
        files_data = [file.model_dump() for file in files]
        
        return {
            "success": True,
            "count": len(files_data),
            "data": files_data
        }
        
    except Exception as e:
        logger.error(f"获取项目文件失败: {str(e)}")

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
            auth_status_value = d.auth_status.value if isinstance(d.auth_status, AuthStatus) else str(d.auth_status)
            
            dir_dict = {
                "id": getattr(d, 'id', None),
                "path": getattr(d, 'path', None),
                "alias": getattr(d, 'alias', None),
                "auth_status": auth_status_value,
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
        auth_status = data.get("auth_status", None)
        
        if not path: # 修正：之前是 if name或not path:
            return {"status": "error", "message": "路径不能为空"}
        
        success, message_or_dir = myfiles_mgr.add_directory(path, alias, is_blacklist, auth_status)
        
        if success:
            # 检查返回值是否是字符串或MyFiles对象
            if isinstance(message_or_dir, str):
                return {"status": "success", "message": message_or_dir}
            else:
                # 如果是MyFiles对象，调用model_dump()
                
                # 如果不是黑名单且设置了auth_status为authorized，立即启动Rust监控
                if not is_blacklist and auth_status == "authorized":
                    # 添加Rust监控的触发信号（通过WebSocket通知前端或通过某种机制）
                    # 此处日志记录即可，实际监控由前端Tauri通过fetch_and_store_all_config获取最新配置
                    logger.info(f"[MONITOR] 新文件夹已添加且已授权，需要立即启动监控: {path}")
                    
                return {"status": "success", "data": message_or_dir.model_dump(), "message": "文件夹添加成功"}
        else:
            return {"status": "error", "message": message_or_dir}
    except Exception as e:
        logger.error(f"添加文件夹失败: {str(e)}")
        return {"status": "error", "message": f"添加文件夹失败: {str(e)}"}

@app.put("/directories/{directory_id}/auth_status")
def update_directory_auth_status(
    directory_id: int,
    data: Dict[str, Any] = Body(...),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    """更新文件夹的授权状态"""
    try:
        auth_status_str = data.get("auth_status")
        if not auth_status_str or auth_status_str not in [status.value for status in AuthStatus]:
            return {"status": "error", "message": "无效的授权状态"}
            
        auth_status = AuthStatus(auth_status_str)
        success, message_or_dir = myfiles_mgr.update_auth_status(directory_id, auth_status)
        if success:
            return {"status": "success", "data": message_or_dir.model_dump(), "message": "授权状态更新成功"}
        else:
            return {"status": "error", "message": message_or_dir}
    except Exception as e:
        logger.error(f"更新文件夹授权状态失败: {directory_id}, {str(e)}")
        return {"status": "error", "message": f"更新文件夹授权状态失败: {str(e)}"}

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
