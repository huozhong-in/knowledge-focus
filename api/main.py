from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends
from typing import List
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import uvicorn
import argparse
import os
import time
from utils import kill_process_on_port
import pathlib
import logging
from sqlmodel import create_engine, Session
import multiprocessing
from db_mgr import DBManager, TaskStatus, TaskResult, TaskPriority, TaskType
from contextlib import asynccontextmanager

# 设置日志记录
logger = logging.getLogger()
parents_logs_dir = pathlib.Path(__file__).parent / 'logs'
os.mkdir(parents_logs_dir) if not parents_logs_dir.exists() else None
logger.setLevel(logging.INFO)
handler = logging.FileHandler(parents_logs_dir / 'api_{starttime}.log'.format(starttime=time.strftime('%Y%m%d', time.localtime(time.time()))))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 在应用启动时执行初始化操作
    logger.info("应用正在启动...")
    
    # 初始化数据库引擎
    if hasattr(app.state, "db_path"):
        sqlite_url = f"sqlite:///{app.state.db_path}"
        app.state.engine = create_engine(sqlite_url, echo=False)
        logger.info(f"数据库引擎已初始化，路径: {app.state.db_path}")
    else:
        logger.warning("未设置数据库路径，数据库引擎未初始化")
    
     # 初始化进程池
    processes = 1 # if multiprocessing.cpu_count() == 1 else multiprocessing.cpu_count() // 2
    app.state.process_pool = multiprocessing.Pool(processes=processes)
    # 启动任务处理者
    for processor_id in range(processes):
        app.state.process_pool.apply_async(task_processor, args=(processor_id, app.state.db_path))
    yield
    
    if hasattr(app.state, "process_pool") and app.state.process_pool is not None:
        app.state.process_pool.close()
        app.state.process_pool.terminate()  # 终止所有工作进程
        app.state.process_pool.join()
        logger.info("进程池已关闭")
    
    # 在应用关闭时执行清理操作
    if hasattr(app.state, "engine") and app.state.engine is not None:
        app.state.engine.dispose()  # 释放数据库连接池
        logger.info("数据库连接池已释放")
    
    logger.info("应用正在关闭...")

app = FastAPI(lifespan=lifespan)

def get_session():
    """FastAPI依赖函数，用于获取数据库会话"""
    if not hasattr(app.state, "engine") or app.state.engine is None:
        # 确保数据库引擎已初始化
        raise RuntimeError("数据库引擎未初始化")
    
    with Session(app.state.engine) as session:
        yield session

# 任务处理者
def task_processor(processor_id: int, db_path: str = None):
    """处理任务的工作进程"""
    logger.info(f"{processor_id}号任务处理者已启动")
    try:
        sqlite_url = f"sqlite:///{db_path}"
        engine = create_engine(sqlite_url, echo=False)
        _db_mgr = DBManager(session=Session(engine))
        while True:
            task = _db_mgr.get_next_task()
            if not task:
                time.sleep(2)  # 没有任务时等待
                continue
            # 将任务状态更新为运行中
            _db_mgr.update_task_status(task.id, TaskStatus.RUNNING)
            logger.info(f"{processor_id}号正在处理任务: {task.id} - {task.task_name}")
            # 模拟任务处理时间
            time.sleep(5)
            _db_mgr.update_task_status(task.id, TaskStatus.COMPLETED, TaskResult.SUCCESS)
            logger.info(f"{processor_id}号将任务 {task.id} 处理完成")
    except Exception as e:
        logger.error(f"{processor_id}号将任务处理失败: {str(e)}")

def task_processor_v2(processor_id: int, db_path: str = None):
    """处理任务的工作进程"""
    logger.info("任务处理者已启动")
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url, echo=False)
    _db_mgr = DBManager(session=Session(engine))

    # 定义实际执行任务的函数
    def execute_task(task_id, task_name):
        logger.info(f"开始执行任务 {task_id}: {task_name}")
        # 模拟任务处理时间
        time.sleep(5)
        logger.info(f"任务 {task_id} 执行完成")
        return True
    
    # 创建线程池用于执行任务，便于实现超时控制
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            while True:
                # 获取下一个待处理任务
                task = _db_mgr.get_next_task()
                
                if not task:
                    time.sleep(2)  # 没有任务时等待
                    continue
                
                # 将任务状态更新为运行中
                _db_mgr.update_task_status(task.id, TaskStatus.RUNNING)
                logger.info(f"处理任务: {task.id} - {task.task_name}")
                
                # 提交任务到线程池，设置超时时间（秒）
                TASK_TIMEOUT = 30  # 30秒超时
                future = executor.submit(execute_task, task.id, task.task_name)
                
                try:
                    # 等待任务完成，最多等待TASK_TIMEOUT秒
                    result = future.result(timeout=TASK_TIMEOUT)
                    # 更新任务状态为完成
                    _db_mgr.update_task_status(task.id, TaskStatus.COMPLETED, TaskResult.SUCCESS)
                    logger.info(f"任务 {task.id} 处理完成")
                except TimeoutError:
                    # 任务超时处理
                    logger.error(f"任务 {task.id} 处理超时")
                    _db_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.TIMEOUT, f"任务处理超时（{TASK_TIMEOUT}秒）")
            
        except Exception as e:
            logger.error(f"任务处理失败: {str(e)}")
            # 如果有任务正在处理，将其状态更新为失败
            if 'task' in locals() and task:
                try:
                    _db_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.FAILURE, str(e))
                except Exception as update_error:
                    logger.error(f"更新失败任务状态时出错: {str(update_error)}")

# 示例：使用数据库连接的API端点
# @app.get("/db-test")
# def test_db_connection(session: Session = Depends(get_session)):
#     from db_mgr import Settings, DBManager  # 确保db_mgr.py中定义了Settings模型
#     from sqlmodel import select
#     try:
#         # 使用SQLModel操作t_settings表
#         # 检查是否存在测试数据
#         db_mgr = DBManager(session)
#         db_mgr.init_db()  # 确保数据库已初始化
#         statement = select(Settings).where(Settings.name == "test_setting")
#         test_setting = session.exec(statement).first()
        
#         if not test_setting:
#             # 不存在则创建测试数据
#             test_setting = Settings(
#                 name="test_setting", 
#                 value="测试数据",
#                 description="这是一个用于测试数据库连接的设置项"
#             )
#             session.add(test_setting)
#             session.commit()
#             session.refresh(test_setting)
        
#         # 读取最近的5条设置数据
#         statement = select(Settings).order_by(Settings.id.desc()).limit(5)
#         recent_settings = session.exec(statement).all()
        
#         # 使用model_dump()方法转换为可序列化的字典列表
#         settings_data = [s.model_dump() for s in recent_settings]
        
#         return {
#             "status": "success",
#             "message": "数据库连接正常",
#             "data": settings_data
#         }
#     except Exception as e:
#         logger.error(f"数据库操作失败: {str(e)}")
#         return {
#             "status": "error",
#             "message": f"数据库操作失败: {str(e)}"
#         }

@app.get("/")
def read_root():
    # 现在可以在任何路由中使用 app.state.db_path
    return {"Hello": "World", "db_path": app.state.db_path}

# 新增task
@app.post("/tasks")
def create_task(task_data: dict = Body(...), session: Session = Depends(get_session)):
    _db_mgr = DBManager(session)
    task_name = task_data.get("task_name")
    task_type_str = task_data.get("task_type", "index")
    priority_str = task_data.get("priority", "medium")
    
    # 确保task_name不为空
    if not task_name:
        return {"error": "task_name不能为空"}, 400
    
    # 转换priority字符串为枚举值
    try:
        priority = TaskPriority(priority_str.lower())
    except ValueError:
        return {"error": f"无效的priority值: {priority_str}，有效值为: low, medium, high"}, 400
    
    # 转换task_type字符串为枚举值
    try:
        task_type = TaskType(task_type_str.lower())
    except ValueError:
        return {"error": f"无效的task_type值: {task_type_str}，有效值为: index, insight"}, 400
    
    task = _db_mgr.add_task(task_name, task_type, priority)
    return {"task_id": task.id}

# 读取给定绝对路径的文件内容
@app.post("/file-content")
def read_file_content(file_paths: List[str] = Body(...)):
    results = []
    for file_path in file_paths:
        try:
            if not os.path.exists(file_path):
                results.append({
                    "path": file_path,
                    "success": False,
                    "error": "文件不存在",
                    "content": None
                })
                continue
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                results.append({
                    "path": file_path,
                    "success": True,
                    "error": None,
                    "content": content
                })
        except Exception as e:
            results.append({
                "path": file_path,
                "success": False,
                "error": str(e),
                "content": None
            })
    
    return {"results": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=60000, help="API服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
    parser.add_argument("--db-path", type=str, default="knowledge-focus.db", help="数据库文件路径")
    
    args = parser.parse_args()
    
    # 检查端口是否被占用，如果被占用则终止占用进程
    kill_process_on_port(args.port)
    time.sleep(2)  # 等待端口释放
    
    # 设置数据库路径
    app.state.db_path = args.db_path
    
    logging.info(f"API服务启动在: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
