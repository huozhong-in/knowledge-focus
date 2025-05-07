from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import uvicorn
import argparse
import os
import time
from utils import kill_process_on_port, monitor_parent
import pathlib
import logging
from sqlmodel import create_engine, Session
import multiprocessing
from db_mgr import TaskStatus, TaskResult, TaskType, InsightType
from task_mgr import TaskManager
from screening_mgr import ScreeningManager
from refine_mgr import RefineManager
from contextlib import asynccontextmanager
import asyncio
import threading
from datetime import datetime
import json

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
    
     # 初始化进程池和任务处理者
    processes = 1 # if multiprocessing.cpu_count() == 1 else multiprocessing.cpu_count() // 2
    app.state.process_pool = multiprocessing.Pool(processes=processes)
    for processor_id in range(processes):
        app.state.process_pool.apply_async(task_processor, args=(processor_id, app.state.db_path))
    
    # 启动通知检查任务
    asyncio.create_task(check_notifications())

    # Start monitor can kill self process if parent process is dead or exit
    monitor_thread = threading.Thread(target=monitor_parent, daemon=True)
    monitor_thread.start()

    # 正式开始服务
    yield
    
    # 退出前的清理工作
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

# 任务处理者
def task_processor(processor_id: int, db_path: str = None):
    """处理任务的工作进程"""
    logger.info(f"{processor_id}号任务处理者已启动")
    try:
        sqlite_url = f"sqlite:///{db_path}"
        engine = create_engine(sqlite_url, echo=False)
        session = Session(engine)
        
        # 初始化各种管理器
        _task_mgr = TaskManager(session)
        _screening_mgr = ScreeningManager(session)
        _refine_mgr = RefineManager(session)
        
        while True:
            task = _task_mgr.get_next_task()
            if not task:
                time.sleep(2)  # 没有任务时等待
                continue
            
            # 将任务状态更新为运行中
            _task_mgr.update_task_status(task.id, TaskStatus.RUNNING)
            logger.info(f"{processor_id}号正在处理任务: {task.id} - {task.task_name}")
            
            task_success = False
            error_message = None
            
            try:
                # 根据任务类型执行不同的处理逻辑
                if task.task_type == TaskType.INDEX.value:
                    # 文件索引任务
                    task_success = process_index_task(task, _screening_mgr, _refine_mgr)
                elif task.task_type == TaskType.INSIGHT.value:
                    # 洞察生成任务
                    task_success = process_insight_task(task, _refine_mgr)
                else:
                    logger.warning(f"未知任务类型: {task.task_type}")
                    error_message = f"未知任务类型: {task.task_type}"
                    task_success = False
            except Exception as e:
                logger.error(f"任务处理出错: {str(e)}")
                error_message = str(e)
                task_success = False
            
            # 更新任务状态
            if task_success:
                _task_mgr.update_task_status(task.id, TaskStatus.COMPLETED, TaskResult.SUCCESS)
                logger.info(f"{processor_id}号将任务 {task.id} 处理完成")
            else:
                _task_mgr.update_task_status(task.id, TaskStatus.FAILED, TaskResult.FAILURE, error_message)
                logger.error(f"{processor_id}号将任务 {task.id} 处理失败: {error_message}")
                
    except Exception as e:
        logger.error(f"{processor_id}号将任务处理失败: {str(e)}")

def process_index_task(task, screening_mgr, refine_mgr) -> bool:
    """处理文件索引任务
    
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
        except Exception:
            pass
    
    # 检查是否包含粗筛结果ID
    screening_result_id = extra_data.get("screening_result_id")
    if screening_result_id:
        # 处理单个文件
        logger.info(f"处理单个文件索引任务: 粗筛结果ID {screening_result_id}")
        refine_result = refine_mgr.process_pending_file(screening_result_id)
        return refine_result is not None
    else:
        # 批量处理
        file_count = extra_data.get("file_count", 0)
        logger.info(f"处理批量索引任务: 预计 {file_count} 个文件")
        
        # 获取一批待处理的粗筛结果
        batch_size = min(100, max(10, file_count))  # 根据任务规模动态调整批量大小
        pending_results = screening_mgr.get_pending_results(limit=batch_size)
        
        if not pending_results:
            logger.warning("找不到待处理的粗筛结果")
            return False
        
        success_count = 0
        for result in pending_results:
            try:
                refine_result = refine_mgr.process_pending_file(result.id)
                if refine_result:
                    success_count += 1
            except Exception as e:
                logger.error(f"处理粗筛结果 {result.id} 失败: {str(e)}")
        
        logger.info(f"批量处理完成: {success_count}/{len(pending_results)} 个文件成功")
        return success_count > 0

def process_insight_task(task, refine_mgr) -> bool:
    """处理洞察生成任务
    
    Args:
        task: 任务对象
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
        except Exception:
            pass
    
    # 获取分析天数
    days = extra_data.get("days", 7)
    
    # 生成洞察
    logger.info(f"生成洞察任务: 分析最近 {days} 天的文件")
    insights = refine_mgr.generate_insights(days)
    
    # 检查结果
    if insights:
        insight_types = {}
        for insight in insights:
            insight_type = insight.insight_type
            insight_types[insight_type] = insight_types.get(insight_type, 0) + 1
        
        logger.info(f"生成了 {len(insights)} 条洞察: {insight_types}")
        return True
    else:
        logger.warning("没有生成任何洞察")
        return False

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
        # 处理时间字段，将字符串转换为datetime
        for time_field in ["created_time", "modified_time", "accessed_time"]:
            if time_field in data and isinstance(data[time_field], str):
                try:
                    data[time_field] = datetime.fromisoformat(data[time_field].replace("Z", "+00:00"))
                except Exception as e:
                    logger.warning(f"转换时间字段 {time_field} 失败: {str(e)}")
                    # 如果是修改时间字段转换失败，设置为当前时间
                    if time_field == "modified_time":
                        data[time_field] = datetime.now()
        
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
            task = task_mgr.add_task(
                task_name=task_name, 
                task_type="index",  # 索引任务类型
                priority="medium",  # 中等优先级
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
    data_list: List[Dict[str, Any]] = Body(...), 
    screening_mgr: ScreeningManager = Depends(get_screening_manager),
    task_mgr: TaskManager = Depends(lambda session=Depends(get_session): TaskManager(session))
):
    """批量添加文件粗筛结果
    
    参数:
    - data_list: 文件粗筛结果列表
    - auto_create_tasks: 是否自动创建任务（可选，默认 False）
    """
    try:
        # 从请求体中提取全局参数
        if isinstance(data_list, dict):
            auto_create_tasks = data_list.get("auto_create_tasks", False)
            data_list = data_list.get("files", [])
        else:
            auto_create_tasks = False  # 批量模式默认不自动创建任务
        
        # 处理时间字段，将字符串转换为datetime
        for data in data_list:
            for time_field in ["created_time", "modified_time", "accessed_time"]:
                if time_field in data and isinstance(data[time_field], str):
                    try:
                        data[time_field] = datetime.fromisoformat(data[time_field].replace("Z", "+00:00"))
                    except Exception as e:
                        logger.warning(f"转换时间字段 {time_field} 失败: {str(e)}")
                        # 如果是修改时间字段转换失败，设置为当前时间
                        if time_field == "modified_time":
                            data[time_field] = datetime.now()
            # Ensure 'extra_metadata' is used, but allow 'metadata' for backward compatibility from client
            if "metadata" in data and "extra_metadata" not in data:
                data["extra_metadata"] = data.pop("metadata")
        
        # 批量添加粗筛结果
        result = screening_mgr.add_batch_screening_results(data_list)
        
        # 如果需要自动创建任务，创建一个批处理任务
        if auto_create_tasks and result["success"] > 0:
            # 创建一个批处理任务
            task_name = f"批量处理文件: {result['success']} 个文件"
            task = task_mgr.add_task(
                task_name=task_name, 
                task_type="index",  # 索引任务类型 
                priority="medium",  # 中等优先级
                extra_data={"file_count": result["success"]}
            )
            result["task_id"] = task.id
        
        return {
            "success": result["success"] > 0,
            "processed_count": result["success"],
            "failed_count": result["failed"],
            "errors": result.get("errors"),
            "message": f"已处理 {result['success']} 个文件，失败 {result['failed']} 个"
        }
        
    except Exception as e:
        logger.error(f"批量处理文件粗筛结果失败: {str(e)}")
        return {
            "success": False,
            "message": f"批量处理失败: {str(e)}"
        }

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

@app.get("/file-screening/pending")
def get_pending_file_screenings(
    limit: int = 100,
    screening_mgr: ScreeningManager = Depends(get_screening_manager)
):
    """获取待处理的文件粗筛结果列表"""
    try:
        results = screening_mgr.get_pending_results(limit)
        
        # 将模型对象列表转换为可序列化的字典列表
        results_dict = [result.model_dump() for result in results]
        
        return {
            "success": True,
            "count": len(results_dict),
            "data": results_dict
        }
        
    except Exception as e:
        logger.error(f"获取待处理文件粗筛结果列表失败: {str(e)}")
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

@app.get("/")
def read_root():
    # 现在可以在任何路由中使用 app.state.db_path
    return {"Hello": "World", "db_path": app.state.db_path}

# 新增task
@app.post("/tasks")
def create_task(task_data: dict = Body(...), session: Session = Depends(get_session)):
    _task_mgr = TaskManager(session)
    task_name = task_data.get("task_name")
    task_type = task_data.get("task_type", "index")
    priority = task_data.get("priority", "medium")
    

    if not task_name:
        return {"error": "任务名称不能为空"}, 400
    if task_type not in ["index", "insight"]:
        return {"error": "任务类型无效"}, 400
    if priority not in ["low", "medium", "high"]:
        return {"error": "优先级无效"}, 400
    task = _task_mgr.add_task(task_name, task_type, priority)
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（可选）
            data = await websocket.receive_text()
            # 处理客户端消息...
            
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

@app.get("/insight-types")
def get_insight_types():
    """获取可用的洞察类型"""
    try:
        insight_types = [
            {"value": InsightType.FILE_ACTIVITY.value, "label": "文件活动"},
            {"value": InsightType.PROJECT_UPDATE.value, "label": "项目更新"},
            {"value": InsightType.CLEANUP.value, "label": "清理建议"},
            {"value": InsightType.CONTENT_HIGHLIGHT.value, "label": "内容亮点"},
            {"value": InsightType.USAGE_PATTERN.value, "label": "使用模式"},
            {"value": InsightType.CUSTOM.value, "label": "自定义洞察"}
        ]
        
        return {
            "success": True,
            "data": insight_types
        }
        
    except Exception as e:
        logger.error(f"获取洞察类型失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取洞察类型失败: {str(e)}"
        }

@app.put("/insights/{insight_id}/read")
def mark_insight_as_read(
    insight_id: int,
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """将洞察标记为已读"""
    try:
        success = refine_mgr.mark_insight_as_read(insight_id)
        if not success:
            return {
                "success": False,
                "message": f"标记洞察 {insight_id} 为已读失败"
            }
        
        return {
            "success": True,
            "message": f"已将洞察 {insight_id} 标记为已读"
        }
        
    except Exception as e:
        logger.error(f"标记洞察为已读失败: {str(e)}")
        return {
            "success": False,
            "message": f"标记洞察为已读失败: {str(e)}"
        }

@app.put("/insights/{insight_id}/dismiss")
def dismiss_insight(
    insight_id: int,
    refine_mgr: RefineManager = Depends(lambda session=Depends(get_session): RefineManager(session))
):
    """忽略洞察"""
    try:
        success = refine_mgr.dismiss_insight(insight_id)
        if not success:
            return {
                "success": False,
                "message": f"忽略洞察 {insight_id} 失败"
            }
        
        return {
            "success": True,
            "message": f"已忽略洞察 {insight_id}"
        }
        
    except Exception as e:
        logger.error(f"忽略洞察失败: {str(e)}")
        return {
            "success": False,
            "message": f"忽略洞察失败: {str(e)}"
        }

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
        
        if not name or not path:
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
        return {
            "success": False,
            "message": f"获取项目文件失败: {str(e)}"
        }

# 修改task_processor_v2，实现更多功能
def task_processor_v2(processor_id: int, db_path: str = None):
    """处理任务的工作进程"""
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
                if task.task_type == TaskType.INDEX.value:
                    process_func = lambda: process_index_task(task, _screening_mgr, _refine_mgr)
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
                TASK_TIMEOUT = 120  # 2分钟超时
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
