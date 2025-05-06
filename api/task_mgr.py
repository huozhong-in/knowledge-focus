from sqlmodel import (
    Session, 
    select, 
    asc, 
    desc, 
)
from datetime import datetime
from db_mgr import Task, TaskStatus, TaskResult, TaskPriority, TaskType

class TaskManager:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_next_task(self) -> Task | None:
        """获取下一个待处理任务
        如果有优先级高的任务，则返回优先级最高的任务，否则返回最早创建的待处理任务
        这里假设任务表中有多个任务，且状态为PENDING的任务可能有不同的优先级
        """
        statement = select(Task).where(Task.status == TaskStatus.PENDING.value).order_by(desc(Task.priority), asc(Task.created_at)).limit(1)
        task = self.session.exec(statement).first()
        return task
    
    def update_task_status(self, task_id: int, status: TaskStatus, result: TaskResult | None = None, error_message: str | None = None) -> bool:
        """更新任务状态"""
        statement = select(Task).where(Task.id == task_id)
        task = self.session.exec(statement).first()
        if not task:
            return False
        
        # 使用枚举值而不是枚举对象
        task.status = status.value if isinstance(status, TaskStatus) else status
        if result is not None:
            task.result = result.value if isinstance(result, TaskResult) else result
        task.error_message = error_message
        task.updated_at = datetime.now()
        
        self.session.add(task)
        self.session.commit()
        return True
    
    def add_task(self, task_name: str, task_type: TaskType = TaskType.INDEX,
 priority: TaskPriority = TaskPriority.MEDIUM) -> Task:
        """添加新任务"""
        # 使用枚举值而不是枚举对象
        task = Task(
            task_name=task_name, 
            task_type=task_type.value if isinstance(task_type, TaskType) else task_type,
            priority=priority.value if isinstance(priority, TaskPriority) else priority, 
            status=TaskStatus.PENDING.value
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task
    
if __name__ == '__main__':
    pass