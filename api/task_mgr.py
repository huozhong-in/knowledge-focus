import multiprocessing
from db_mgr import TaskStatus, TaskResult, Task, TaskPriority, TaskType
from typing import Dict, Any, List
import threading
import logging
from utils import monitor_parent
from sqlmodel import (
    Session, 
    select, 
    # asc, 
    desc,
    # text,
)
from datetime import datetime

logger = logging.getLogger(__name__)

class TaskManager:
    """任务管理器，负责任务的添加、获取、更新等操作"""

    def __init__(self, session: Session):
        """初始化任务管理器
        
        Args:
            session: SQLAlchemy数据库会话
        """
        self.session: Session = session

    def add_task(self, task_name: str, task_type: TaskType, priority: TaskPriority = TaskPriority.MEDIUM, extra_data: Dict[str, Any] = None) -> Task:
        """添加新任务
        
        Args:
            task_name: 任务名称
            task_type: 任务类型
            priority: 任务优先级，TaskPriority类型的字符串值
            extra_data: 任务额外数据
            
        Returns:
            添加的任务对象
        """
        logger.info(f"添加任务: {task_name}, 类型: {task_type.value}, 优先级: {priority.value}")
        
        task = Task(
            task_name=task_name,
            task_type=task_type.value,
            priority=priority.value,
            status=TaskStatus.PENDING.value,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            extra_data=extra_data
        )
        
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        
        return task
    
    def get_task(self, task_id: int) -> Task | None:
        """根据ID获取任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，如果不存在则返回None
        """
        return self.session.get(Task, task_id)
    
    def get_tasks(self, limit: int = 100) -> List[Task]:
        """获取任务列表
        
        Args:
            limit: 返回记录数量上限
            
        Returns:
            任务对象列表
        """
        statement = select(Task).limit(limit)
        return self.session.exec(statement).all()
    
    def get_next_task(self) -> Task | None:
        """获取下一个待处理的任务，优先处理优先级高的任务"""
        return self.session.exec(
            select(Task)
            .where(Task.status == TaskStatus.PENDING.value)
            .order_by(Task.priority, Task.created_at)
        ).first()
    
    def update_task_status(self, task_id: int, status: TaskStatus, 
                          result: TaskResult = None, message: str = None) -> bool:
        """更新任务状态
        
        Args:
            task_id: 任务ID
            status: 任务状态
            result: 任务结果（可选）
            message: 状态信息（可选）
            
        Returns:
            更新是否成功
        """
        logger.info(f"更新任务 {task_id} 状态: {status.name}")
        
        try:
            task = self.session.get(Task, task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return False
            
            # 设置状态值
            task.status = status.value
            task.updated_at = datetime.now()
            
            if status == TaskStatus.RUNNING:
                task.start_time = datetime.now()
            
            if result:
                task.result = result.value
                
            if message:
                task.error_message = message
                
            # 确保所有日期时间字段都是 datetime 对象
            # 如果已经是字符串格式，则转换回 datetime 对象
            if hasattr(task, 'created_at') and isinstance(task.created_at, str):
                try:
                    task.created_at = datetime.fromisoformat(task.created_at)
                except Exception as e:
                    logger.error(f"转换 created_at 字段失败: {str(e)}")
                    # 如果转换失败，使用当前时间
                    task.created_at = datetime.now()
            
            self.session.add(task)
            self.session.commit()
            
            return True
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def start_task_worker(self, worker_func, args=(), daemon=True) -> threading.Thread:
        """启动任务处理线程
        
        Args:
            worker_func: 工作线程函数
            args: 工作线程函数参数
            daemon: 是否为守护线程
            
        Returns:
            创建的线程对象
        """
        worker_thread = threading.Thread(target=worker_func, args=args, daemon=daemon)
        worker_thread.start()
        return worker_thread
    
    def start_task_process(self, worker_func, args=(), daemon=True) -> multiprocessing.Process:
        """启动任务处理进程
        
        Args:
            worker_func: 工作进程函数
            args: 工作进程函数参数
            daemon: 是否为守护进程
            
        Returns:
            创建的进程对象
        """
        # 创建一个包装函数，在其中运行监控线程和工作函数
        def process_wrapper(*worker_args):
            try:
                # 启动父进程监控线程
                monitor_thread = threading.Thread(target=monitor_parent, daemon=True)
                monitor_thread.start()
                
                # 执行实际的工作函数
                return worker_func(*worker_args)
            except Exception as e:
                logger.error(f"任务处理进程异常: {str(e)}")
                raise
        
        worker_process = multiprocessing.Process(target=process_wrapper, args=args, daemon=daemon)
        worker_process.start()
        return worker_process
    
    def start_process_pool(self, num_processes=None):
        """创建进程池
        
        Args:
            num_processes: 进程数量，默认为CPU核心数
            
        Returns:
            进程池对象
        """
        if num_processes is None:
            num_processes = multiprocessing.cpu_count()
            
        return multiprocessing.Pool(processes=num_processes)
    
    def apply_async_with_monitoring(self, pool, func, args=(), callback=None):
        """异步提交任务到进程池，并确保子进程可以监控父进程
        
        Args:
            pool: 进程池对象
            func: 要执行的函数
            args: 函数参数
            callback: 回调函数
            
        Returns:
            AsyncResult对象
        """
        # 创建一个包装函数，在其中运行监控线程和工作函数
        def monitored_func(*worker_args):
            try:
                # 启动父进程监控线程
                monitor_thread = threading.Thread(target=monitor_parent, daemon=True)
                monitor_thread.start()
                
                # 执行实际的工作函数
                return func(*worker_args)
            except Exception as e:
                logger.error(f"任务处理进程异常: {str(e)}")
                raise
                
        return pool.apply_async(monitored_func, args=args, callback=callback)
    
    def cancel_old_tasks(self, task_type: str, created_before=None) -> int:
        """取消特定类型的旧任务
        
        当提交新任务时，可以用此方法取消同类型的旧任务，避免处理过时的数据
        
        Args:
            task_type: 要取消的任务类型
            created_before: 取消在此时间之前创建的任务，默认为当前时间
            
        Returns:
            取消的任务数量
        """
        logger.info(f"取消类型为 {task_type} 的旧任务")
        
        if created_before is None:
            created_before = datetime.now()
            
        # 查询待取消的任务
        statement = (
            select(Task)
            .where(
                Task.task_type == task_type,
                Task.status == TaskStatus.PENDING.value,
                Task.created_at < created_before
            )
        )
        
        tasks = self.session.exec(statement).all()
        canceled_count = 0
        
        for task in tasks:
            task.status = TaskStatus.CANCELED.value
            task.result = TaskResult.CANCELLED.value  # 设置任务结果为被取消
            task.updated_at = datetime.now()
            task.error_message = "被更新的任务取代"
            self.session.add(task)
            canceled_count += 1
            
        if canceled_count > 0:
            self.session.commit()
            logger.info(f"已取消 {canceled_count} 个类型为 {task_type} 的旧任务")
            
        return canceled_count
    
    def get_latest_completed_task(self, task_type: str) -> Task | None:
        """获取最新的已完成任务
        
        Args:
            task_type: 任务类型
            
        Returns:
            最新的已完成任务对象，如果没有则返回None
        """
        try:
            return self.session.exec(
                select(Task)
                .where(Task.task_type == task_type, Task.status == TaskStatus.COMPLETED.value)
                .order_by(desc(Task.created_at))
                .limit(1)
            ).first()
        except Exception as e:
            logger.error(f"获取最新已完成任务失败: {e}")
            return None
    
    def get_latest_running_task(self, task_type: str) -> Task | None:
        """获取最新的运行中任务
        
        Args:
            task_type: 任务类型
            
        Returns:
            最新的运行中任务对象，如果没有则返回None
        """
        try:
            return self.session.exec(
                select(Task)
                .where(Task.task_type == task_type, Task.status == TaskStatus.RUNNING.value)
                .order_by(desc(Task.created_at))
                .limit(1)
            ).first()
        except Exception as e:
            logger.error(f"获取最新运行任务失败: {e}")
            return None
    
    def get_latest_task(self, task_type: str) -> Task | None:
        """获取最新的任务，无论状态如何
        
        Args:
            task_type: 任务类型
            
        Returns:
            最新的任务对象，如果没有则返回None
        """
        try:
            return self.session.exec(
                select(Task)
                .where(Task.task_type == task_type)
                .order_by(desc(Task.created_at))
                .limit(1)
            ).first()
        except Exception as e:
            logger.error(f"获取最新任务失败: {e}")
            return None

if __name__ == '__main__':
    from sqlmodel import (
        create_engine, 
    )
    from config import TEST_DB_PATH
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
    task_mgr = TaskManager(session)
    print(task_mgr.get_next_task())
