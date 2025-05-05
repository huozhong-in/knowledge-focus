from sqlmodel import (
    Field, 
    SQLModel, 
    create_engine, 
    Session, 
    select, 
    inspect, 
    text, 
    asc, 
    and_, 
    or_, 
    desc, 
    not_,
)
from datetime import datetime
from enum import Enum

# 表结构设计
class Settings(SQLModel, table=True):
    __tablename__ = "t_settings"
    id: int = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: str
    description: str | None = None

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

# 3种任务优先级
class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# 供worker使用的tasks表
class Task(SQLModel, table=True):
    __tablename__ = "t_tasks"
    id: int = Field(default=None, primary_key=True)
    task_name: str
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)  # 任务优先级，默认中等
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default=datetime.now())  # 创建时间，默认UTC时间
    updated_at: datetime = Field(default=datetime.now())  # 更新时间
    start_time: datetime | None = Field(default=None)  # 任务开始时间
    result: TaskResult | None = Field(default=None)  # 任务结果
    error_message: str | None = Field(default=None)  # 错误信息
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
            TaskStatus: lambda v: v.value,
            }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(**data)


class DBManager:
    """数据库管理类，负责直接操作各业务模块数据表，从上层拿到session，自己不管理数据库连接"""
    
    def __init__(self, session: Session) -> None:
        self.session = session
        

    def init_db(self) -> bool:
        """初始化数据库"""
        engine = self.session.get_bind()
        inspector = inspect(engine)

        # 创建表
        with engine.connect() as conn:
            if not inspector.has_table(Task.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Task.__table__])
                # 适当增加索引
                # if not any([col['name'] == 'idx_talker_id' for col in inspector.get_indexes(Settings.__tablename__)]):
                #     conn.execute(text(f'CREATE INDEX idx_talker_id ON {Settings.__tablename__} (id);'))
        
        return True
    
    def get_next_task(self) -> Task | None:
        """获取下一个待处理任务
        如果有优先级高的任务，则返回优先级最高的任务，否则返回最早创建的待处理任务
        这里假设任务表中有多个任务，且状态为PENDING的任务可能有不同的优先级
        """
        statement = select(Task).where(Task.status == TaskStatus.PENDING).order_by(desc(Task.priority), asc(Task.created_at)).limit(1)
        task = self.session.exec(statement).first()
        return task
    
    def update_task_status(self, task_id: int, status: TaskStatus, result: TaskResult | None = None, error_message: str | None = None) -> bool:
        """更新任务状态"""
        statement = select(Task).where(Task.id == task_id)
        task = self.session.exec(statement).first()
        if not task:
            return False
        
        task.status = status
        task.result = result
        task.error_message = error_message
        task.updated_at = datetime.now()
        
        self.session.add(task)
        self.session.commit()
        return True
    
    def add_task(self, task_name: str, priority: TaskPriority = TaskPriority.MEDIUM) -> Task:
        """添加新任务"""
        task = Task(task_name=task_name, priority=priority)
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task


if __name__ == '__main__':
    db_mgr = DBManager(Session(create_engine("sqlite:////Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db")))
    db_mgr.init_db()
    print("数据库初始化完成")