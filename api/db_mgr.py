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
# 任务状态枚举
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
# 任务结果状态
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
# 2种任务类型
class TaskType(str, Enum):
    INDEX = "index"  # 索引任务
    INSIGHT = "insight"  # 洞察任务
# 供worker使用的tasks表
class Task(SQLModel, table=True):
    __tablename__ = "t_tasks"
    id: int = Field(default=None, primary_key=True)
    task_name: str
    task_type: TaskType = Field(default=TaskType.INDEX)  # 任务类型，默认索引任务
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)  # 任务优先级，默认中等
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default=datetime.now())  # 创建时间
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

# 通知表
class Notification(SQLModel, table=True):
    __tablename__ = "t_notifications"
    id: int = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="t_tasks.id", index=True)  # 关联任务ID
    message: str
    created_at: datetime = Field(default=datetime.now())  # 创建时间
    read: bool = Field(default=False)  # 是否已读
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

class DBManager:
    """数据库管理类，负责直接操作各业务模块数据表，从上层拿到session，自己不管理数据库连接"""
    
    def __init__(self, session: Session) -> None:
        self.session = session
        

    def init_db(self) -> bool:
        """初始化数据库"""
        engine = self.session.get_bind()
        inspector = inspect(engine)

        with engine.connect() as conn:
            # 创建任务表
            if not inspector.has_table(Task.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Task.__table__])
                # if not any([col['name'] == 'idx_task_type' for col in inspector.get_indexes(Task.__tablename__)]):
                #     conn.execute(text(f'CREATE INDEX idx_task_type ON {Task.__tablename__} (task_type);'))

            # 创建通知表
            if not inspector.has_table(Notification.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Notification.__table__])
                # 创建触发器 - 当任务表中洞察任务状态完成时插入通知
                conn.execute(text(f"""
                    CREATE TRIGGER IF NOT EXISTS trg_task_status_change
                    AFTER UPDATE ON {Task.__tablename__}
                    FOR EACH ROW
                    WHEN NEW.status = '{TaskStatus.COMPLETED}' AND NEW.task_type = '{TaskType.INSIGHT}'
                    BEGIN
                        INSERT INTO {Notification.__tablename__} (task_id, message)
                        VALUES (NEW.id, ' 任务 ' || NEW.task_name || ' 已完成');
                    END;
                """))
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
    
    def add_task(self, task_name: str, task_type: TaskType = TaskType.INDEX,
 priority: TaskPriority = TaskPriority.MEDIUM) -> Task:
        """添加新任务"""
        task = Task(task_name=task_name, task_type=task_type, priority=priority)
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task


if __name__ == '__main__':
    db_mgr = DBManager(Session(create_engine("sqlite:////Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db")))
    db_mgr.init_db()
    print("数据库初始化完成")