from sqlmodel import (
    Field, 
    SQLModel, 
    create_engine, 
    Session, 
    select, 
    inspect, 
    text, 
    # asc, 
    # and_, 
    # or_, 
    # desc, 
    # not_,
    Column,
    Enum,
    JSON,
)
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Dict, Optional, Any
    
# 任务状态枚举
class TaskStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# 任务结果状态
class TaskResult(str, PyEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

# 3种任务优先级
class TaskPriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# 2种任务类型
class TaskType(str, PyEnum):
    INDEX = "index"  # 索引任务
    INSIGHT = "insight"  # 洞察任务

# 供worker使用的tasks表
class Task(SQLModel, table=True):
    __tablename__ = "t_tasks"
    id: int = Field(default=None, primary_key=True)
    task_name: str
    task_type: str = Field(sa_column=Column(Enum(TaskType, values_callable=lambda obj: [e.value for e in obj]), default=TaskType.INDEX.value))
    priority: str = Field(sa_column=Column(Enum(TaskPriority, values_callable=lambda obj: [e.value for e in obj]), default=TaskPriority.MEDIUM.value))
    status: str = Field(sa_column=Column(Enum(TaskStatus, values_callable=lambda obj: [e.value for e in obj]), default=TaskStatus.PENDING.value))
    created_at: datetime = Field(default=datetime.now())  # 创建时间
    updated_at: datetime = Field(default=datetime.now())  # 更新时间
    start_time: datetime | None = Field(default=None)  # 任务开始时间
    result: str | None = Field(sa_column=Column(Enum(TaskResult, values_callable=lambda obj: [e.value for e in obj]), default=None))
    error_message: str | None = Field(default=None)  # 错误信息
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
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

# 取得授权状态
class AuthStatus(str, PyEnum):
    PENDING = "pending"  # 等待授权，或叫未请求授权
    AUTHORIZED = "authorized"  # 已授权，或者叫已经授权
    UNAUTHORIZED = "unauthorized"  # 未授权，或者叫拒绝授权

# 监控的文件、文件夹表，用来存储文件、文件夹的路径和状态
class MyFiles(SQLModel, table=True):
    __tablename__ = "t_myfiles"
    id: int = Field(default=None, primary_key=True)
    path: str
    alias: str | None = Field(default=None)  # 别名
    is_blacklist: bool = Field(default=False)  # 是否是用户不想监控的文件或文件夹(黑名单)
    auth_status: str = Field(sa_column=Column(Enum(AuthStatus, values_callable=lambda obj: [e.value for e in obj]), default=AuthStatus.PENDING.value))
    created_at: datetime = Field(default=datetime.now())  # 创建时间
    updated_at: datetime = Field(default=datetime.now())  # 更新时间
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 文件粗筛规则类型枚举
class RuleType(str, PyEnum):
    EXTENSION = "extension"  # 文件扩展名分类
    FILENAME = "filename"    # 文件名模式/关键词识别
    FOLDER = "folder"        # 项目文件夹识别
    STRUCTURE = "structure"  # 项目结构特征识别

# 规则优先级
class RulePriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# 规则操作类型
class RuleAction(str, PyEnum):
    INCLUDE = "include"  # 包含在处理中
    EXCLUDE = "exclude"  # 排除在处理外
    TAG = "tag"         # 标记特定类型，但不影响处理流程

# 文件分类表 - 存储不同的文件分类
class FileCategory(SQLModel, table=True):
    __tablename__ = "t_file_categories"
    id: int = Field(default=None, primary_key=True)
    name: str  # 分类名称，如 "document", "image", "audio_video" 等
    description: str | None = Field(default=None)  # 分类描述
    icon: str | None = Field(default=None)  # 可选的图标标识
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 粗筛规则表 - 用于Rust端初步过滤文件
class FileFilterRule(SQLModel, table=True):
    __tablename__ = "t_file_filter_rules"
    id: int = Field(default=None, primary_key=True)
    name: str  # 规则名称
    description: str | None = Field(default=None)  # 规则描述
    rule_type: str = Field(sa_column=Column(Enum(RuleType, values_callable=lambda obj: [e.value for e in obj])))
    category_id: int | None = Field(default=None, foreign_key="t_file_categories.id")  # 关联的文件分类ID
    priority: str = Field(sa_column=Column(Enum(RulePriority, values_callable=lambda obj: [e.value for e in obj]), default=RulePriority.MEDIUM.value))
    action: str = Field(sa_column=Column(Enum(RuleAction, values_callable=lambda obj: [e.value for e in obj]), default=RuleAction.INCLUDE.value))
    enabled: bool = Field(default=True)  # 规则是否启用
    is_system: bool = Field(default=True)  # 是系统规则还是用户自定义规则
    pattern: str  # 匹配模式（正则表达式、通配符或关键词）
    pattern_type: str = Field(default="regex")  # 模式类型：regex, glob, keyword
    extra_data: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 额外的配置数据，如嵌套文件结构规则
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 文件扩展名映射表 - 将扩展名映射到文件分类
class FileExtensionMap(SQLModel, table=True):
    __tablename__ = "t_file_extensions"
    id: int = Field(default=None, primary_key=True)
    extension: str  # 不含点的扩展名，如 "pdf", "docx"
    category_id: int = Field(foreign_key="t_file_categories.id")
    description: str | None = Field(default=None)  # 可选描述
    priority: str = Field(sa_column=Column(Enum(RulePriority, values_callable=lambda obj: [e.value for e in obj]), default=RulePriority.MEDIUM.value))
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 项目识别规则表 - 识别项目文件夹的规则
class ProjectRecognitionRule(SQLModel, table=True):
    __tablename__ = "t_project_recognition_rules"
    id: int = Field(default=None, primary_key=True)
    name: str  # 规则名称
    description: str | None = Field(default=None)  # 规则描述
    rule_type: str  # 规则类型：name_pattern(名称模式), structure(结构特征), metadata(元数据特征)
    pattern: str  # 匹配模式
    priority: str = Field(sa_column=Column(Enum(RulePriority, values_callable=lambda obj: [e.value for e in obj]), default=RulePriority.MEDIUM.value))
    indicators: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 指示器，如文件夹结构模式
    enabled: bool = Field(default=True)  # 规则是否启用
    is_system: bool = Field(default=True)  # 系统规则还是用户规则
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 文件粗筛结果状态枚举
class FileScreenResult(str, PyEnum):
    PENDING = "pending"       # 等待进一步处理
    PROCESSED = "processed"   # 已被Python处理
    IGNORED = "ignored"       # 被忽略（符合排除规则）
    FAILED = "failed"         # 处理失败

# 粗筛结果表 - 存储Rust进行初步规则匹配后的结果
class FileScreeningResult(SQLModel, table=True):
    __tablename__ = "t_file_screening_results"
    id: int = Field(default=None, primary_key=True)
    file_path: str            # 文件完整路径
    file_name: str            # 文件名（含扩展名）
    file_size: int            # 文件大小（字节）
    extension: str | None = Field(default=None)  # 文件扩展名（不含点）
    file_hash: str | None = Field(default=None)  # 文件哈希值（可能是部分哈希）
    created_time: datetime | None = Field(default=None)  # 文件创建时间
    modified_time: datetime   # 文件最后修改时间
    accessed_time: datetime | None = Field(default=None)  # 文件最后访问时间
    
    # 粗筛分类结果
    category_id: int | None = Field(default=None)  # 根据扩展名或规则确定的分类ID
    matched_rules: List[int] | None = Field(default=None, sa_column=Column(JSON))  # 匹配的规则ID列表
    
    # 额外元数据和特征
    extra_metadata: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 其他元数据信息
    tags: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 初步标记的标签
    
    # 处理状态
    status: str = Field(sa_column=Column(Enum(FileScreenResult, values_callable=lambda obj: [e.value for e in obj]), default=FileScreenResult.PENDING.value))
    error_message: str | None = Field(default=None)  # 错误信息，如果有
    
    # 任务关联和时间戳
    task_id: int | None = Field(default=None)  # 关联的处理任务ID（如果有）
    created_at: datetime = Field(default=datetime.now())  # 记录创建时间
    updated_at: datetime = Field(default=datetime.now())  # 记录更新时间
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 文件精炼结果状态枚举
class FileRefineStatus(str, PyEnum):
    PENDING = "pending"       # 等待进一步处理
    PROCESSING = "processing" # 正在处理中
    COMPLETE = "complete"     # 处理完成
    FAILED = "failed"         # 处理失败
    IGNORED = "ignored"       # 被忽略

# 文件精炼分析类型枚举
class FileAnalysisType(str, PyEnum):
    BASIC = "basic"           # 基本分析（元数据整理）
    CONTENT = "content"       # 内容分析（文本提取、简单NLP）
    DEEP = "deep"             # 深度分析（LLM处理、高级特征提取）
    RELATIONSHIP = "relationship"  # 关联分析（文件间关系）
    PROJECT = "project"       # 项目识别分析

# 文件精炼结果表 - 存储Python对文件进行深度分析后的结果
class FileRefineResult(SQLModel, table=True):
    __tablename__ = "t_file_refine_results"
    id: int = Field(default=None, primary_key=True)
    screening_id: int = Field(foreign_key="t_file_screening_results.id", index=True)  # 关联的粗筛结果ID
    task_id: int | None = Field(default=None, foreign_key="t_tasks.id", index=True)   # 关联的处理任务ID
    
    # 基本信息
    file_path: str            # 文件完整路径（冗余存储，便于查询）
    analysis_type: str = Field(sa_column=Column(Enum(FileAnalysisType, values_callable=lambda obj: [e.value for e in obj]), default=FileAnalysisType.BASIC.value))
    status: str = Field(sa_column=Column(Enum(FileRefineStatus, values_callable=lambda obj: [e.value for e in obj]), default=FileRefineStatus.PENDING.value))
    
    # 处理结果
    content_summary: str | None = Field(default=None)  # 文件内容摘要
    extracted_text: str | None = Field(default=None)   # 提取的文本（可能部分）
    language: str | None = Field(default=None)         # 检测到的语言
    topics: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 主题标签
    named_entities: Dict[str, List[str]] | None = Field(default=None, sa_column=Column(JSON))  # 命名实体（人名、地点、组织等）
    key_phrases: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 关键短语
    sentiment: Dict[str, float] | None = Field(default=None, sa_column=Column(JSON))  # 情感分析结果
    readability_metrics: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 可读性指标
    
    # 额外特征和元数据
    extra_metadata: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 额外元数据
    features: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 提取的特征
    
    # 项目和关联信息
    project_id: int | None = Field(default=None)  # 关联的项目ID（如果已识别）
    related_files: List[int] | None = Field(default=None, sa_column=Column(JSON))  # 关联文件ID列表
    similar_files: List[Dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))  # 相似文件和相似度
    
    # 处理统计
    processing_time: float | None = Field(default=None)  # 处理耗时（秒）
    tokens_processed: int | None = Field(default=None)   # 处理的token数量
    error_message: str | None = Field(default=None)      # 错误信息（如果有）
    
    # 时间戳
    created_at: datetime = Field(default=datetime.now())  # 记录创建时间
    updated_at: datetime = Field(default=datetime.now())  # 记录更新时间
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 洞察类型枚举
class InsightType(str, PyEnum):
    FILE_ACTIVITY = "file_activity"     # 文件活动洞察
    PROJECT_UPDATE = "project_update"   # 项目更新洞察
    CLEANUP = "cleanup"                 # 清理建议
    CONTENT_HIGHLIGHT = "content_highlight"  # 内容亮点
    USAGE_PATTERN = "usage_pattern"     # 使用模式
    CUSTOM = "custom"                   # 自定义洞察

# 洞察优先级
class InsightPriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# 洞察表 - 存储基于文件精炼结果生成的有价值洞察
class Insight(SQLModel, table=True):
    __tablename__ = "t_insights"
    id: int = Field(default=None, primary_key=True)
    task_id: int | None = Field(default=None, foreign_key="t_tasks.id", index=True)  # 关联的任务ID
    
    # 洞察内容
    title: str                # 洞察标题
    description: str          # 洞察描述
    insight_type: str = Field(sa_column=Column(Enum(InsightType, values_callable=lambda obj: [e.value for e in obj])))
    priority: str = Field(sa_column=Column(Enum(InsightPriority, values_callable=lambda obj: [e.value for e in obj]), default=InsightPriority.MEDIUM.value))
    
    # 关联数据
    related_files: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 关联文件路径列表
    related_projects: List[int] | None = Field(default=None, sa_column=Column(JSON))  # 关联项目ID列表
    action_items: List[Dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))  # 推荐操作列表
    
    # 生成和状态信息
    generation_method: str | None = Field(default=None)  # 生成方式（规则/LLM）
    score: float | None = Field(default=None)  # 洞察评分（重要性/相关性）
    is_read: bool = Field(default=False)  # 是否已读
    is_dismissed: bool = Field(default=False)  # 是否已忽略
    is_actioned: bool = Field(default=False)  # 是否已采取行动
    
    # 时间戳
    valid_until: datetime | None = Field(default=None)  # 有效期（某些洞察可能过期）
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    # 额外数据
    extra_metadata: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 额外元数据
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 项目信息表 - 存储识别出的项目信息
class Project(SQLModel, table=True):
    __tablename__ = "t_projects"
    id: int = Field(default=None, primary_key=True)
    name: str                 # 项目名称
    path: str                 # 项目根路径
    description: str | None = Field(default=None)  # 项目描述
    
    # 项目特征
    project_type: str | None = Field(default=None)  # 项目类型（代码、文档、设计等）
    programming_languages: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 编程语言列表
    framework: str | None = Field(default=None)     # 使用的框架
    
    # 项目统计
    file_count: int | None = Field(default=None)    # 文件数量
    total_size: int | None = Field(default=None)    # 总大小（字节）
    last_activity: datetime | None = Field(default=None)  # 最后活动时间
    
    # 识别信息
    recognition_confidence: float | None = Field(default=None)  # 识别置信度
    recognition_method: str | None = Field(default=None)  # 识别方法
    
    # 时间戳
    discovered_at: datetime = Field(default=datetime.now())  # 发现时间
    updated_at: datetime = Field(default=datetime.now())     # 更新时间
    
    # 额外数据
    extra_metadata: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 额外元数据
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

class DBManager:
    """数据库结构管理类，负责新建和后续维护各业务模块数据表结构、索引、触发器等
    从上层拿到session，自己不管理数据库连接"""
    
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
                # 创建触发器 - 当任务表中洞察任务状态成功完成时插入通知
                conn.execute(text(f'''
                    CREATE TRIGGER IF NOT EXISTS notify_insight_task
                    AFTER UPDATE ON {Task.__tablename__}
                    FOR EACH ROW
                    WHEN NEW.task_type = 'insight' AND NEW.status = 'completed' AND NEW.result = 'success'
                    BEGIN
                        INSERT INTO {Notification.__tablename__} (task_id, message, created_at, read)
                        VALUES (NEW.id, '洞察任务完成', CURRENT_TIMESTAMP, 0);
                    END;
                '''))
            
            # 创建文件表
            if not inspector.has_table(MyFiles.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[MyFiles.__table__])
            
            # 创建文件分类表
            if not inspector.has_table(FileCategory.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileCategory.__table__])
                self._init_file_categories()  # 初始化文件分类数据
            
            # 创建文件扩展名映射表
            if not inspector.has_table(FileExtensionMap.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileExtensionMap.__table__])
                self._init_file_extensions()  # 初始化文件扩展名映射数据
            
            # 创建文件过滤规则表
            if not inspector.has_table(FileFilterRule.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileFilterRule.__table__])
                self._init_file_filter_rules()  # 初始化文件过滤规则
            
            # 创建项目识别规则表
            if not inspector.has_table(ProjectRecognitionRule.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ProjectRecognitionRule.__table__])
                self._init_project_recognition_rules()  # 初始化项目识别规则
            
            # 创建文件粗筛结果表
            if not inspector.has_table(FileScreeningResult.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileScreeningResult.__table__])
                # 创建索引 - 为文件路径创建唯一索引
                conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_file_path ON {FileScreeningResult.__tablename__} (file_path);'))
                # 创建索引 - 为文件状态创建索引，便于查询待处理文件
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_file_status ON {FileScreeningResult.__tablename__} (status);'))
                # 创建索引 - 为修改时间创建索引，便于按时间查询
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_modified_time ON {FileScreeningResult.__tablename__} (modified_time);'))
            
            # 创建文件精炼结果表
            if not inspector.has_table(FileRefineResult.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileRefineResult.__table__])
                # 创建索引 - 为文件路径创建索引
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_refine_file_path ON {FileRefineResult.__tablename__} (file_path);'))
                # 创建索引 - 为处理状态创建索引
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_refine_status ON {FileRefineResult.__tablename__} (status);'))
            
            # 创建洞察表
            if not inspector.has_table(Insight.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Insight.__table__])
                # 创建索引 - 为洞察类型创建索引
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_insight_type ON {Insight.__tablename__} (insight_type);'))
                # 创建索引 - 为优先级创建索引
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_insight_priority ON {Insight.__tablename__} (priority);'))
            
            # 创建项目表
            if not inspector.has_table(Project.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Project.__table__])
                # 创建索引 - 为项目路径创建唯一索引
                conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_project_path ON {Project.__tablename__} (path);'))
                
        return True

    def _init_file_categories(self) -> None:
        """初始化文件分类数据"""
        categories = [
            FileCategory(name="document", description="文档类文件", icon="📄"),
            FileCategory(name="image", description="图片类文件", icon="🖼️"),
            FileCategory(name="audio_video", description="音视频文件", icon="🎬"),
            FileCategory(name="archive", description="压缩包文件", icon="🗃️"),
            FileCategory(name="installer", description="安装包文件", icon="📦"),
            FileCategory(name="code", description="代码文件", icon="💻"),
            FileCategory(name="design", description="设计文件", icon="🎨"),
            FileCategory(name="temp", description="临时文件", icon="⏱️"),
            FileCategory(name="other", description="其他类型文件", icon="📎"),
        ]
        self.session.add_all(categories)
        self.session.commit()

    def _init_file_extensions(self) -> None:
        """初始化文件扩展名映射"""
        # 获取分类ID映射
        category_map = {cat.name: cat.id for cat in self.session.exec(select(FileCategory)).all()}
        
        # 文档类扩展名
        doc_extensions = [
            # MS Office
            {"extension": "doc", "category_id": category_map["document"], "description": "Microsoft Word文档(旧版)"},
            {"extension": "docx", "category_id": category_map["document"], "description": "Microsoft Word文档"},
            {"extension": "ppt", "category_id": category_map["document"], "description": "Microsoft PowerPoint演示文稿(旧版)"},
            {"extension": "pptx", "category_id": category_map["document"], "description": "Microsoft PowerPoint演示文稿"},
            {"extension": "xls", "category_id": category_map["document"], "description": "Microsoft Excel电子表格(旧版)"},
            {"extension": "xlsx", "category_id": category_map["document"], "description": "Microsoft Excel电子表格"},
            # Apple iWork
            {"extension": "pages", "category_id": category_map["document"], "description": "Apple Pages文档"},
            {"extension": "key", "category_id": category_map["document"], "description": "Apple Keynote演示文稿"},
            {"extension": "numbers", "category_id": category_map["document"], "description": "Apple Numbers电子表格"},
            # 文本文档
            {"extension": "md", "category_id": category_map["document"], "description": "Markdown文档"},
            {"extension": "markdown", "category_id": category_map["document"], "description": "Markdown文档"},
            {"extension": "txt", "category_id": category_map["document"], "description": "纯文本文档"},
            {"extension": "rtf", "category_id": category_map["document"], "description": "富文本格式文档"},
            # 电子书/固定格式
            {"extension": "pdf", "category_id": category_map["document"], "description": "PDF文档", "priority": "high"},
            {"extension": "epub", "category_id": category_map["document"], "description": "EPUB电子书"},
            {"extension": "mobi", "category_id": category_map["document"], "description": "MOBI电子书"},
            # Web文档
            {"extension": "html", "category_id": category_map["document"], "description": "HTML网页"},
            {"extension": "htm", "category_id": category_map["document"], "description": "HTML网页"},
        ]
        
        # 图片类扩展名
        image_extensions = [
            {"extension": "jpg", "category_id": category_map["image"], "description": "JPEG图片", "priority": "high"},
            {"extension": "jpeg", "category_id": category_map["image"], "description": "JPEG图片", "priority": "high"},
            {"extension": "png", "category_id": category_map["image"], "description": "PNG图片", "priority": "high"},
            {"extension": "gif", "category_id": category_map["image"], "description": "GIF图片"},
            {"extension": "bmp", "category_id": category_map["image"], "description": "BMP图片"},
            {"extension": "tiff", "category_id": category_map["image"], "description": "TIFF图片"},
            {"extension": "heic", "category_id": category_map["image"], "description": "HEIC图片(苹果设备)"},
            {"extension": "webp", "category_id": category_map["image"], "description": "WebP图片"},
            {"extension": "svg", "category_id": category_map["image"], "description": "SVG矢量图"},
            {"extension": "cr2", "category_id": category_map["image"], "description": "佳能RAW格式图片"},
            {"extension": "nef", "category_id": category_map["image"], "description": "尼康RAW格式图片"},
            {"extension": "arw", "category_id": category_map["image"], "description": "索尼RAW格式图片"},
            {"extension": "dng", "category_id": category_map["image"], "description": "通用RAW格式图片"},
        ]
        
        # 音视频类扩展名
        av_extensions = [
            # 音频
            {"extension": "mp3", "category_id": category_map["audio_video"], "description": "MP3音频", "priority": "high"},
            {"extension": "wav", "category_id": category_map["audio_video"], "description": "WAV音频"},
            {"extension": "aac", "category_id": category_map["audio_video"], "description": "AAC音频"},
            {"extension": "flac", "category_id": category_map["audio_video"], "description": "FLAC无损音频"},
            {"extension": "ogg", "category_id": category_map["audio_video"], "description": "OGG音频"},
            {"extension": "m4a", "category_id": category_map["audio_video"], "description": "M4A音频"},
            # 视频
            {"extension": "mp4", "category_id": category_map["audio_video"], "description": "MP4视频", "priority": "high"},
            {"extension": "mov", "category_id": category_map["audio_video"], "description": "MOV视频(苹果设备)", "priority": "high"},
            {"extension": "avi", "category_id": category_map["audio_video"], "description": "AVI视频"},
            {"extension": "mkv", "category_id": category_map["audio_video"], "description": "MKV视频"},
            {"extension": "wmv", "category_id": category_map["audio_video"], "description": "WMV视频(Windows)"},
            {"extension": "flv", "category_id": category_map["audio_video"], "description": "Flash视频"},
            {"extension": "webm", "category_id": category_map["audio_video"], "description": "WebM视频"},
        ]
        
        # 压缩包类扩展名
        archive_extensions = [
            {"extension": "zip", "category_id": category_map["archive"], "description": "ZIP压缩文件", "priority": "high"},
            {"extension": "rar", "category_id": category_map["archive"], "description": "RAR压缩文件"},
            {"extension": "7z", "category_id": category_map["archive"], "description": "7-Zip压缩文件"},
            {"extension": "tar", "category_id": category_map["archive"], "description": "TAR归档文件"},
            {"extension": "gz", "category_id": category_map["archive"], "description": "GZIP压缩文件"},
            {"extension": "bz2", "category_id": category_map["archive"], "description": "BZIP2压缩文件"},
        ]
        
        # 安装包类扩展名
        installer_extensions = [
            {"extension": "dmg", "category_id": category_map["installer"], "description": "macOS磁盘镜像", "priority": "high"},
            {"extension": "pkg", "category_id": category_map["installer"], "description": "macOS安装包", "priority": "high"},
            {"extension": "exe", "category_id": category_map["installer"], "description": "Windows可执行文件", "priority": "high"},
            {"extension": "msi", "category_id": category_map["installer"], "description": "Windows安装包"},
        ]
        
        # 代码类扩展名
        code_extensions = [
            {"extension": "py", "category_id": category_map["code"], "description": "Python源代码"},
            {"extension": "js", "category_id": category_map["code"], "description": "JavaScript源代码"},
            {"extension": "ts", "category_id": category_map["code"], "description": "TypeScript源代码"},
            {"extension": "java", "category_id": category_map["code"], "description": "Java源代码"},
            {"extension": "c", "category_id": category_map["code"], "description": "C源代码"},
            {"extension": "cpp", "category_id": category_map["code"], "description": "C++源代码"},
            {"extension": "h", "category_id": category_map["code"], "description": "C/C++头文件"},
            {"extension": "cs", "category_id": category_map["code"], "description": "C#源代码"},
            {"extension": "php", "category_id": category_map["code"], "description": "PHP源代码"},
            {"extension": "rb", "category_id": category_map["code"], "description": "Ruby源代码"},
            {"extension": "go", "category_id": category_map["code"], "description": "Go源代码"},
            {"extension": "swift", "category_id": category_map["code"], "description": "Swift源代码"},
            {"extension": "kt", "category_id": category_map["code"], "description": "Kotlin源代码"},
            {"extension": "sh", "category_id": category_map["code"], "description": "Shell脚本"},
            {"extension": "bat", "category_id": category_map["code"], "description": "Windows批处理文件"},
            {"extension": "json", "category_id": category_map["code"], "description": "JSON数据文件"},
            {"extension": "yaml", "category_id": category_map["code"], "description": "YAML配置文件"},
            {"extension": "yml", "category_id": category_map["code"], "description": "YAML配置文件"},
            {"extension": "toml", "category_id": category_map["code"], "description": "TOML配置文件"},
            {"extension": "xml", "category_id": category_map["code"], "description": "XML数据文件"},
            {"extension": "css", "category_id": category_map["code"], "description": "CSS样式表"},
            {"extension": "scss", "category_id": category_map["code"], "description": "SCSS样式表"},
        ]
        
        # 设计类扩展名
        design_extensions = [
            {"extension": "psd", "category_id": category_map["design"], "description": "Photoshop设计文件"},
            {"extension": "ai", "category_id": category_map["design"], "description": "Adobe Illustrator设计文件"},
            {"extension": "sketch", "category_id": category_map["design"], "description": "Sketch设计文件"},
            {"extension": "fig", "category_id": category_map["design"], "description": "Figma设计文件"},
            {"extension": "xd", "category_id": category_map["design"], "description": "Adobe XD设计文件"},
        ]
        
        # 临时文件扩展名
        temp_extensions = [
            {"extension": "tmp", "category_id": category_map["temp"], "description": "临时文件"},
            {"extension": "temp", "category_id": category_map["temp"], "description": "临时文件"},
            {"extension": "part", "category_id": category_map["temp"], "description": "未完成下载的部分文件"},
            {"extension": "crdownload", "category_id": category_map["temp"], "description": "Chrome下载临时文件"},
            {"extension": "download", "category_id": category_map["temp"], "description": "下载临时文件"},
            {"extension": "bak", "category_id": category_map["temp"], "description": "备份文件"},
        ]
        
        # 合并所有扩展名
        all_extensions = []
        all_extensions.extend(doc_extensions)
        all_extensions.extend(image_extensions)
        all_extensions.extend(av_extensions)
        all_extensions.extend(archive_extensions)
        all_extensions.extend(installer_extensions)
        all_extensions.extend(code_extensions)
        all_extensions.extend(design_extensions)
        all_extensions.extend(temp_extensions)
        
        # 转换为FileExtensionMap对象并批量插入
        extension_objs = []
        for ext_data in all_extensions:
            priority = ext_data.get("priority", "medium")
            extension_objs.append(
                FileExtensionMap(
                    extension=ext_data["extension"],
                    category_id=ext_data["category_id"],
                    description=ext_data["description"],
                    priority=priority
                )
            )
        
        self.session.add_all(extension_objs)
        self.session.commit()

    def _init_file_filter_rules(self) -> None:
        """初始化文件名模式过滤规则"""
        # 获取分类ID映射
        category_map = {cat.name: cat.id for cat in self.session.exec(select(FileCategory)).all()}
        
        # 文件名状态/版本关键词规则
        status_version_rules = [
            {
                "name": "草稿文件识别",
                "description": "识别包含草稿、Draft等关键词的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(草稿|draft|Draft|DRAFT)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "draft",
                    "tag_name": "草稿",
                    "insight_type": "status"
                }
            },
            {
                "name": "最终版文件识别",
                "description": "识别包含最终版、Final等关键词的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(最终版|终稿|final|Final|FINAL)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "final",
                    "tag_name": "最终版",
                    "insight_type": "status"
                }
            },
            {
                "name": "版本号文件识别",
                "description": "识别包含版本号标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(v\d+|v\d+\.\d+|版本\d+|V\d+)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "versioned",
                    "tag_name": "带版本号",
                    "insight_type": "version"
                }
            },
            {
                "name": "旧版/备份文件识别",
                "description": "识别旧版或备份文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(_old|_旧|_backup|_备份|_bak|副本|Copy of|\(\d+\))",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "backup",
                    "tag_name": "备份/旧版",
                    "insight_type": "cleanup"
                }
            }
        ]
        
        # 文档类型/内容关键词规则
        doc_type_rules = [
            {
                "name": "报告文件识别",
                "description": "识别各类报告文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(报告|Report|report|REPORT)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "report",
                    "tag_name": "报告",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "提案文件识别",
                "description": "识别各类提案文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(提案|Proposal|proposal|PROPOSAL)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "proposal",
                    "tag_name": "提案",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "合同/协议文件识别",
                "description": "识别合同或协议文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(合同|协议|合约|Contract|contract|Agreement|agreement)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "contract",
                    "tag_name": "合同/协议",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "发票/收据文件识别",
                "description": "识别发票或收据文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(发票|收据|Invoice|invoice|Receipt|receipt)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "invoice",
                    "tag_name": "发票/收据",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "演示/幻灯片文件识别",
                "description": "识别演示文稿或幻灯片文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(演示|幻灯片|Presentation|presentation|Slides|slides)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "presentation",
                    "tag_name": "演示/幻灯片",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "周报/月报文件识别",
                "description": "识别周报或月报文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(周报|月报|周总结|月总结|Weekly|weekly|Monthly|monthly)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "report_periodical",
                    "tag_name": "周报/月报",
                    "insight_type": "document_type"
                }
            },
            {
                "name": "简历文件识别",
                "description": "识别简历文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(简历|Resume|resume|CV|cv)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "resume",
                    "tag_name": "简历",
                    "insight_type": "document_type"
                }
            }
        ]
        
        # 时间指示关键词规则
        time_indicators_rules = [
            {
                "name": "年份-月份-日期格式",
                "description": "识别包含YYYY-MM-DD格式日期的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(20\d{2}[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01]))",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "dated_ymd",
                    "tag_name": "带日期",
                    "insight_type": "time"
                }
            },
            {
                "name": "季度标记",
                "description": "识别包含季度标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Q[1-4]|第[一二三四]季度|[一二三四]季度|上半年|下半年)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "quarterly",
                    "tag_name": "季度文件",
                    "insight_type": "time"
                }
            },
            {
                "name": "月份标记",
                "description": "识别包含月份标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[一二三四五六七八九十]{1,2}月)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "monthly",
                    "tag_name": "月度文件",
                    "insight_type": "time"
                }
            }
        ]
        
        # 应用/来源关键词规则
        app_source_rules = [
            {
                "name": "截图文件识别",
                "description": "识别各类截图文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(截图|屏幕截图|Screenshot|screenshot|Screen Shot|screen shot|Snipaste|snipaste|CleanShot)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "priority": RulePriority.HIGH.value,
                "extra_data": {
                    "tag": "screenshot",
                    "tag_name": "截图",
                    "insight_type": "app_source"
                }
            },
            {
                "name": "相机/手机照片识别",
                "description": "识别相机或手机生成的照片文件名模式",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(IMG_\d+|DSC_\d+|DCIM|DSCN\d+)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "camera",
                    "tag_name": "相机照片",
                    "insight_type": "app_source"
                }
            },
            {
                "name": "微信文件识别",
                "description": "识别微信相关的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(微信|WeChat|wechat|MicroMsg|mmexport)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "priority": RulePriority.HIGH.value,
                "extra_data": {
                    "tag": "wechat",
                    "tag_name": "微信文件",
                    "insight_type": "app_source"
                }
            },
            {
                "name": "下载文件识别",
                "description": "识别下载的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(下载|download|Download|DOWNLOAD)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "download",
                    "tag_name": "下载文件",
                    "insight_type": "app_source"
                }
            },
            {
                "name": "视频会议文件识别",
                "description": "识别视频会议相关文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Zoom|zoom|Teams|teams|Meet|meet|会议记录|meeting)",
                "pattern_type": "regex",
                "action": RuleAction.TAG.value,
                "extra_data": {
                    "tag": "meeting",
                    "tag_name": "会议文件",
                    "insight_type": "app_source"
                }
            }
        ]
        
        # 临时/忽略文件规则
        temp_ignore_rules = [
            {
                "name": "Office临时文件",
                "description": "识别Office软件产生的临时文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(~\$)",
                "pattern_type": "regex",
                "action": RuleAction.EXCLUDE.value,
                "priority": RulePriority.HIGH.value,
                "category_id": category_map["temp"]
            },
            {
                "name": "未完成下载文件",
                "description": "识别未完成下载的临时文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(\.part$|\.partial$|\.download$|\.crdownload$)",
                "pattern_type": "regex",
                "action": RuleAction.EXCLUDE.value,
                "priority": RulePriority.HIGH.value,
                "category_id": category_map["temp"]
            },
            {
                "name": "系统缓存文件",
                "description": "识别操作系统生成的缓存文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Thumbs\.db$|\.DS_Store$|desktop\.ini$)",
                "pattern_type": "regex",
                "action": RuleAction.EXCLUDE.value,
                "priority": RulePriority.HIGH.value,
                "category_id": category_map["temp"]
            }
        ]
        
        # 合并所有规则
        all_rules = []
        all_rules.extend(status_version_rules)
        all_rules.extend(doc_type_rules)
        all_rules.extend(time_indicators_rules)
        all_rules.extend(app_source_rules)
        all_rules.extend(temp_ignore_rules)
        
        # 转换为FileFilterRule对象并批量插入
        rule_objs = []
        for rule_data in all_rules:
            priority = rule_data.get("priority", RulePriority.MEDIUM.value)
            rule_objs.append(
                FileFilterRule(
                    name=rule_data["name"],
                    description=rule_data["description"],
                    rule_type=rule_data["rule_type"],
                    category_id=rule_data.get("category_id"),
                    pattern=rule_data["pattern"],
                    pattern_type=rule_data.get("pattern_type", "regex"),
                    action=rule_data["action"],
                    priority=priority,
                    is_system=True,
                    enabled=True,
                    extra_data=rule_data.get("extra_data")
                )
            )
        
        self.session.add_all(rule_objs)
        self.session.commit()
        
    def _init_project_recognition_rules(self) -> None:
        """初始化项目识别规则"""
        # 项目名称模式规则
        name_pattern_rules = [
            {
                "name": "中文项目文件夹",
                "description": "识别中文项目文件夹名称",
                "rule_type": "name_pattern",
                "pattern": r"(项目|工作文件)",
                "priority": RulePriority.MEDIUM.value,
                "indicators": {
                    "min_files": 3,  # 至少包含3个文件才会被识别为项目
                    "insight_score": 70  # 洞察权重分
                }
            },
            {
                "name": "英文项目文件夹",
                "description": "识别英文项目文件夹名称",
                "rule_type": "name_pattern",
                "pattern": r"(Projects?|My Work|Documents|Clients|Cases)",
                "priority": RulePriority.MEDIUM.value,
                "indicators": {
                    "min_files": 5,
                    "insight_score": 70
                }
            },
            {
                "name": "年份项目文件夹",
                "description": "识别包含年份的项目文件夹",
                "rule_type": "name_pattern",
                "pattern": r"(20\d{2}|20\d{2}Q[1-4]|20\d{2}-[A-Za-z0-9]+)",
                "priority": RulePriority.HIGH.value,
                "indicators": {
                    "min_files": 2,
                    "insight_score": 80
                }
            }
        ]
        
        # 项目结构特征规则
        structure_rules = [
            {
                "name": "Git项目",
                "description": "识别Git代码仓库项目",
                "rule_type": "structure",
                "pattern": ".git",
                "priority": RulePriority.HIGH.value,
                "indicators": {
                    "is_code_project": True,
                    "structure_markers": [".git"],
                    "exclude_indexing": ["node_modules", ".git", "dist", "build", "target"],
                    "include_markdown": True,  # 仅索引Markdown文档
                    "insight_score": 90
                }
            },
            {
                "name": "前端项目",
                "description": "识别前端开发项目",
                "rule_type": "structure",
                "pattern": "package.json",
                "priority": RulePriority.HIGH.value,
                "indicators": {
                    "is_code_project": True,
                    "structure_markers": ["node_modules", "package.json"],
                    "exclude_indexing": ["node_modules", "dist", "build"],
                    "include_markdown": True,
                    "insight_score": 85
                }
            },
            {
                "name": "Python项目",
                "description": "识别Python开发项目",
                "rule_type": "structure",
                "pattern": "requirements.txt|setup.py|pyproject.toml",
                "pattern_type": "regex",
                "priority": RulePriority.HIGH.value,
                "indicators": {
                    "is_code_project": True,
                    "structure_markers": ["venv", ".venv", "requirements.txt", "setup.py", "pyproject.toml"],
                    "exclude_indexing": ["venv", ".venv", "__pycache__", ".pytest_cache"],
                    "include_markdown": True,
                    "insight_score": 85
                }
            },
            {
                "name": "通用开发项目",
                "description": "识别包含常见开发目录结构的项目",
                "rule_type": "structure",
                "pattern": "src|include|lib|docs|assets",
                "pattern_type": "regex",
                "priority": RulePriority.MEDIUM.value,
                "indicators": {
                    "is_code_project": True,
                    "structure_markers": ["src", "lib", "include", "docs"],
                    "insight_score": 80
                }
            }
        ]
        
        # 合并所有规则
        all_rules = []
        all_rules.extend(name_pattern_rules)
        all_rules.extend(structure_rules)
        
        # 转换为ProjectRecognitionRule对象并批量插入
        rule_objs = []
        for rule_data in all_rules:
            priority = rule_data.get("priority", RulePriority.MEDIUM.value)
            rule_objs.append(
                ProjectRecognitionRule(
                    name=rule_data["name"],
                    description=rule_data["description"],
                    rule_type=rule_data["rule_type"],
                    pattern=rule_data["pattern"],
                    priority=priority,
                    indicators=rule_data.get("indicators"),
                    is_system=True,
                    enabled=True
                )
            )
        
        self.session.add_all(rule_objs)
        self.session.commit()

if __name__ == '__main__':
    db_mgr = DBManager(Session(create_engine("sqlite:////Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db")))
    db_mgr.init_db()
    print("数据库初始化完成")