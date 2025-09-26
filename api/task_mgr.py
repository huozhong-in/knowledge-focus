from config import singleton
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
from sqlalchemy import Engine
from datetime import datetime

logger = logging.getLogger()

@singleton
class TaskManager:
    """任务管理器，负责任务的添加、获取、更新等操作"""

    def __init__(self, engine: Engine):
        """初始化任务管理器
        
        Args:
            engine: SQLAlchemy数据库引擎
        """
        self.engine = engine

    def add_task(self, task_name: str, task_type: TaskType, priority: TaskPriority = TaskPriority.MEDIUM, 
                 extra_data: Dict[str, Any] = None, target_file_path: str = None) -> Task:
        """添加新任务
        
        Args:
            task_name: 任务名称
            task_type: 任务类型
            priority: 任务优先级，TaskPriority类型的字符串值
            extra_data: 任务额外数据
            target_file_path: 目标文件路径（用于MULTIVECTOR任务的快速查询）
            
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
            extra_data=extra_data,
            target_file_path=target_file_path
        )
        with Session(self.engine) as session:
            session.add(task)
            session.commit()
            session.refresh(task)
            
            return task
    
    def get_task(self, task_id: int) -> Task | None:
        """根据ID获取任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，如果不存在则返回None
        """
        with Session(self.engine) as session:
            return session.get(Task, task_id)
    
    def get_tasks(self, limit: int = 100) -> List[Task]:
        """获取任务列表
        
        Args:
            limit: 返回记录数量上限
            
        Returns:
            任务对象列表
        """
        with Session(self.engine) as session:
            statement = select(Task).limit(limit)
            return session.exec(statement).all()
    
    def get_next_task(self) -> Task | None:
        """获取下一个待处理的任务，优先处理优先级高的任务"""
        with Session(self.engine) as session:
            return session.exec(
                select(Task)
            .where(Task.status == TaskStatus.PENDING.value)
            .order_by(Task.priority, Task.created_at)
        ).first()
    
    def get_and_lock_next_high_priority_task(self) -> Task | None:
        """原子地获取并锁定下一个高优先级任务"""
        with Session(self.engine) as session:
            # 查找第一个HIGH优先级的PENDING任务
            task = session.exec(
                select(Task)
                .where(Task.status == TaskStatus.PENDING.value)
                .where(Task.priority == TaskPriority.HIGH.value)
                .order_by(Task.created_at)
                .limit(1)
            ).first()
            
            if task:
                # 原子地将状态改为RUNNING，避免其他处理器获取到同一任务
                task.status = TaskStatus.RUNNING.value
                task.start_time = datetime.now()
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()
                logger.info(f"高优先级任务处理器锁定任务: ID={task.id}, Name='{task.task_name}'")
                return task
            else:
                return None
    
    def get_and_lock_next_task(self) -> Task | None:
        """原子地获取并锁定下一个待处理的任务（排除已被锁定的任务）"""
        with Session(self.engine) as session:
            # 查找第一个PENDING状态的任务
            task = session.exec(
                select(Task)
                .where(Task.status == TaskStatus.PENDING.value)
                .order_by(Task.priority, Task.created_at)
                .limit(1)
            ).first()
            
            if task:
                # 原子地将状态改为RUNNING，避免其他处理器获取到同一任务
                task.status = TaskStatus.RUNNING.value
                task.start_time = datetime.now()
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()
                logger.info(f"普通任务处理器锁定任务: ID={task.id}, Name='{task.task_name}'")
                return task
            else:
                return None
    
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
            with Session(self.engine) as session:
                task = session.get(Task, task_id)
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

                session.add(task)
                session.commit()

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
    
    
    def get_latest_completed_task(self, task_type: str) -> Task | None:
        """获取最新的已完成任务
        
        Args:
            task_type: 任务类型
            
        Returns:
            最新的已完成任务对象，如果没有则返回None
        """
        try:
            with Session(self.engine) as session:
                return session.exec(
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
            with Session(self.engine) as session:
                return session.exec(
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
            with Session(self.engine) as session:
                return session.exec(
                    select(Task)
                    .where(Task.task_type == task_type)
                    .order_by(desc(Task.created_at))
                    .limit(1)
            ).first()
        except Exception as e:
            logger.error(f"获取最新任务失败: {e}")
            return None
    
    def is_file_recently_pinned(self, file_path: str, hours: int = 8) -> bool:
        """
        检查文件是否在指定时间内被成功pin过（即有成功的MULTIVECTOR任务）
        
        Args:
            file_path: 文件绝对路径
            hours: 检查的时间窗口（小时），默认8小时
            
        Returns:
            bool: 如果文件在指定时间内有成功的MULTIVECTOR任务则返回True
        """
        try:
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(hours=hours)

            with Session(self.engine) as session:
                task = session.exec(
                    select(Task)
                .where(Task.task_type == TaskType.MULTIVECTOR.value)
                .where(Task.target_file_path == file_path)
                .where(Task.updated_at > cutoff_time)
                .where(Task.status == TaskStatus.COMPLETED.value)
                .where(Task.result == TaskResult.SUCCESS.value)
                .order_by(desc(Task.updated_at))
            ).first()
            
                result = task is not None
                if result:
                    logger.info(f"文件 {file_path} 在最近{hours}小时内被pin过，最后任务ID: {task.id}")
                else:
                    logger.info(f"文件 {file_path} 在最近{hours}小时内未被pin过")
                return result
            
        except Exception as e:
            logger.error(f"检查文件pin状态失败: {e}")
            return False

if __name__ == '__main__':
    from sqlmodel import (
        create_engine, 
    )
    from config import TEST_DB_PATH
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    task_mgr = TaskManager(engine)
    print(task_mgr.get_next_task())
