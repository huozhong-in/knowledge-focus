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
from typing import List, Dict, Any
import os
    
# 任务状态枚举
class TaskStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"  # 添加取消状态

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

# 任务类型
class TaskType(str, PyEnum):
    SCREENING = "screening"
    TAGGING = "tagging"
    MULTIVECTOR = "multivector"
    # REFINE = "refine"
    # MAINTENANCE = "maintenance"

# 供worker使用的tasks表
class Task(SQLModel, table=True):
    __tablename__ = "t_tasks"
    id: int = Field(default=None, primary_key=True)
    task_name: str
    task_type: str = Field(sa_column=Column(Enum(TaskType, values_callable=lambda obj: [e.value for e in obj]), default=TaskType.TAGGING.value))
    priority: str = Field(sa_column=Column(Enum(TaskPriority, values_callable=lambda obj: [e.value for e in obj]), default=TaskPriority.MEDIUM.value))
    status: str = Field(sa_column=Column(Enum(TaskStatus, values_callable=lambda obj: [e.value for e in obj]), default=TaskStatus.PENDING.value))
    created_at: datetime = Field(default=datetime.now())  # 创建时间
    updated_at: datetime = Field(default=datetime.now())  # 更新时间
    start_time: datetime | None = Field(default=None)  # 任务开始时间
    result: str | None = Field(sa_column=Column(Enum(TaskResult, values_callable=lambda obj: [e.value for e in obj]), default=None))
    error_message: str | None = Field(default=None)  # 错误信息
    extra_data: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 任务额外数据
    target_file_path: str | None = Field(default=None, index=True)  # 目标文件路径，专门用于MULTIVECTOR任务的高效查询
    
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

# 监控的文件夹表，用来存储文件夹的路径和状态
class MyFiles(SQLModel, table=True):
    __tablename__ = "t_myfiles"
    id: int = Field(default=None, primary_key=True)
    path: str
    alias: str | None = Field(default=None)  # 别名
    is_blacklist: bool = Field(default=False)  # 是否是用户不想监控的文件夹(黑名单)
    is_common_folder: bool = Field(default=False)  # 是否为常见文件夹（不可删除）
    parent_id: int | None = Field(default=None, foreign_key="t_myfiles.id")  # 父文件夹ID，支持黑名单层级关系
    created_at: datetime = Field(default=datetime.now())  # 创建时间
    updated_at: datetime = Field(default=datetime.now())  # 更新时间
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# macOS Bundle扩展名表
class BundleExtension(SQLModel, table=True):
    __tablename__ = "t_bundle_extensions"
    id: int = Field(default=None, primary_key=True)
    extension: str = Field(index=True, unique=True)  # 扩展名（如.app, .bundle等）
    description: str | None = Field(default=None)  # 描述
    is_active: bool = Field(default=True)  # 是否启用
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 系统配置表
class SystemConfig(SQLModel, table=True):
    __tablename__ = "t_system_config"
    id: int = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)  # 配置键名
    value: str  # 配置值（有可能是JSON字符串）
    description: str | None = Field(default=None)  # 配置描述
    updated_at: datetime = Field(default=datetime.now())
    
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
    OS_BUNDLE = "os_bundle"  # 操作系统特定的bundle文件夹类型

# 规则优先级
class RulePriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# 规则操作类型
class RuleAction(str, PyEnum):
    INCLUDE = "include"  # 包含在处理中
    EXCLUDE = "exclude"  # 排除在处理外
    LABEL = "label"         # 标记特定类型，但不影响处理流程

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

# 标签类型
class TagsType(str, PyEnum):
    SYSTEM = "system" # 系统预定义标签
    USER = "user" # 用户自定义标签
    LLM = "llm" # LLM生成的标签

# 标签表
class Tags(SQLModel, table=True):
    __tablename__ = "t_tags"
    id: int = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # 标签名称
    type: str = Field(default=TagsType.USER.value)
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
    # 在SQLAlchemy中，__table_args__需要是一个元组，最后一个元素可以是包含选项的字典
    __table_args__ = ({
        "sqlite_autoincrement": True,
        "schema": None,
        "sqlite_with_rowid": True,
    },)
    id: int = Field(default=None, primary_key=True)
    file_path: str            # 文件完整路径
    file_name: str = Field(index=True)  # 文件名（含扩展名），增加索引以优化文件名搜索
    file_size: int            # 文件大小（字节）
    extension: str | None = Field(default=None, index=True)  # 文件扩展名（不含点），增加索引以优化按扩展名过滤
    file_hash: str | None = Field(default=None, index=True)  # 文件哈希值（部分哈希: 大于4k的部分，小于4k则是整个文件），增加索引以优化重复文件查找
    created_time: datetime | None = Field(default=None)  # 文件创建时间
    modified_time: datetime = Field(index=True)  # 文件最后修改时间，增加索引以优化时间范围查询
    accessed_time: datetime | None = Field(default=None)  # 文件最后访问时间
    tagged_time: datetime | None = Field(default=None)  # 上一次打标签时间，用来判定是否需要重新处理

    # 粗筛分类结果
    category_id: int | None = Field(default=None, index=True)  # 根据扩展名或规则确定的分类ID（已有索引）
    matched_rules: List[int] | None = Field(default=None, sa_column=Column(JSON))  # 匹配的规则ID列表
    
    # 额外元数据和特征
    extra_metadata: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))  # 其他元数据信息
    labels: List[str] | None = Field(default=None, sa_column=Column(JSON))  # 初步标记的标牌
    tags_display_ids: str | None = Field(default=None)  # 标签ID列表（逗号分隔字符串）
    
    # 处理状态
    status: str = Field(
        sa_column=Column(
            Enum(FileScreenResult, values_callable=lambda obj: [e.value for e in obj]), 
            default=FileScreenResult.PENDING.value,
            index=True  # 增加索引以优化状态过滤
        )
    )
    error_message: str | None = Field(default=None)  # 错误信息，如果有
    
    # 任务关联和时间戳
    task_id: int | None = Field(default=None, index=True)  # 关联的处理任务ID（如果有），增加索引以优化任务关联查询
    created_at: datetime = Field(default=datetime.now())  # 记录创建时间
    updated_at: datetime = Field(default=datetime.now(), index=True)  # 记录更新时间，增加索引以优化按更新时间排序
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
        }

# 文档表
# 用于记录被处理的原始文件信息。
# 设计意图: 管理最原始的入口文件，file_hash能避免重复处理未变更的文件，status字段则可以支持异步处理和失败重试机制。
class Document(SQLModel, table=True):
    __tablename__ = "t_documents"
    id: int = Field(default=None, primary_key=True)
    file_path: str = Field(index=True, unique=True) # 文件的绝对路径，唯一且索引
    file_hash: str # 文件内容的哈希值，用于检测文件是否变更
    docling_json_path: str # Docling解析后存储的JSON文件路径，便于复用
    status: str = Field(default="pending") # 处理状态: pending, processing, done, error
    processed_at: datetime = Field(default_factory=datetime.now)

# 父块表
# 这是系统的核心实体，代表了我们最终要提供给LLM进行答案合成的“原始内容块”。
# 设计意图: 这是“父文档”策略的直接体现。无论原始形态是文字、图片还是我们后来创造的知识卡片，都在这里有一个统一的表示。通过document_id与源文档关联。
class ParentChunk(SQLModel, table=True):
    __tablename__ = "t_parent_chunks"
    id: int = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="t_documents.id", index=True) # 关联的原始文档
    chunk_type: str = Field(index=True) # 类型: 'text', 'image', 'table', 'knowledge_card'
    # 原始内容或其引用
    content: str # 如果是text/knowledge_card, 直接存内容; 如果是image/table, 存储其图片文件的路径
    metadata_json: str # 存储额外元数据, 如页码、位置坐标等
    created_at: datetime = Field(default_factory=datetime.now)

# 子块表
# 代表了用于向量化和检索的“代理”单元。
# 设计意图: 这是连接关系世界和向量世界的“桥梁”。parent_chunk_id建立了清晰的从属关系，而vector_id则指向了它在LanceDB中的“向量化身”。
class ChildChunk(SQLModel, table=True):
    __tablename__ = "t_child_chunks"
    id: int = Field(default=None, primary_key=True)
    parent_chunk_id: int = Field(foreign_key="t_parent_chunks.id", index=True) # 明确的父子关系
    # 用于向量化的文本内容
    retrieval_content: str # 可能是文本摘要、图片描述、或者“图片描述+周围文本”的组合
    vector_id: str = Field(unique=True, index=True) # 与LanceDB中向量记录对应的唯一ID, 如UUID

# 模型来源
class ModelSourceType(str, PyEnum):
    BUILDIN = "buildin" # App内置框架(MLX/llama-cpp-python)直接运行的模型，直接管理下载过程
    CONFIGURABLE = "configurable" # 可配置的模型服务商，本地如Ollama、LM Studio，远程如OpenAI、Anthropic
    VIP = "vip" # 由本App服务端提供的模型组合
# 模型提供者表
# 这张表用来定义模型的来源。它可以是Ollama，可以是OpenAI，也可以是您自己的VIP服务。
# 设计意图: 将“模型从哪里来”这个问题抽象成一个独立的实体，极大地提高了扩展性。未来出现新的托管平台，只需增加一个新的provider_type即可。
class ModelProvider(SQLModel, table=True):
    __tablename__ = "t_model_providers"
    id: int = Field(default=None, primary_key=True)
    # 显示名称，用户可读的名称
    display_name: str = Field(index=True, unique=True)  # - 预填充名字。- VIP服务从云端拉取。- 用户新增openai-compatible类名称
    source_type: str = Field(default=ModelSourceType.CONFIGURABLE.value)
    provider_type: str = Field(default="")  # 提供者类型，来自pydantic_ai.providers
    base_url: str | None = Field(default=None)  # 如果source_type为vip则此项无效，具体值在每个模型配置上
    api_key: str | None = Field(default=None)  # 如果source_type为vip则为加密后的值(密钥暂时写死，实现用户登录后从云端获取)
    # 存放一些特别的provider-specific数据，比如Azure OpenAI的api_version、VertexAI的project_id/location等
    extra_data_json: List[Dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    is_active: bool = Field(default=False)  # 是否启用
    is_user_added: bool = Field(default=True)  # 用户新增的，用户可以删除
    get_key_url: str | None = Field(default=None)
    support_discovery: bool = Field(default=True)
    use_proxy: bool = Field(default=False)

# 模型能力，前端当作i18n的key
class ModelCapability(str, PyEnum):
    TEXT = "text"
    REASONING = "reasoning"
    VISION = "vision"
    TOOL_USE = "tool_use"
    WEB_SEARCH = "web_search"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    # CODE_GENERATION = "code_generation"
    # TTS = "tts"
    # ASR = "asr"
    # IMAGE_GENERATION = "image_generation"
# 模型配置表
# 这张表代表一个具体可用的模型。
# 设计意图: 将一个具体的模型实例（如本地的llama3:8b）与其能力和属性绑定。这些属性可以来自您的云端目录，也可以由用户手动配置。
class ModelConfiguration(SQLModel, table=True):
    __tablename__ = "t_model_configurations"
    id: int = Field(default=None, primary_key=True)
    provider_id: int = Field(foreign_key="t_model_providers.id", index=True) # 关联到提供者
    model_identifier: str # 模型在对应平台官方标识符，如 'gemma:2b', 'gpt-4o'
    display_name: str # 用户可自定义的别名
    # 模型的“能力”清单
    capabilities_json: List[str] = Field(default=[], sa_column=Column(JSON)) # e.g., ['text', 'embedding', 'vision']
    # vip服务的每个模型来自不同的服务商，一定有不同的base_url. 以及model-specific的数据。
    extra_data_json: List[Dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    max_context_length: int = Field(default=0) # This max tokens number includes input, output, and reasoning tokens. 
    max_output_tokens: int = Field(default=0) # This max tokens number includes output tokens only.
    is_enabled: bool = Field(default=True)

# 能力指派表
# 它将App内的具体“任务”指派给一个配置好的“模型”。
# 设计意图: 彻底解耦“功能”和“实现”。当App需要进行“视觉分析”时，它不关心具体是哪个模型，而是去查这张表，找到被指派给vision_analysis这个“岗位”的模型，然后去调用它。用户可以在设置界面中，像拖拽指派任务一样，决定哪个模型负责哪个功能。
class CapabilityAssignment(SQLModel, table=True):
    __tablename__ = "t_capability_assignments"    
    # ModelCapability value作主键
    capability_value: str = Field(primary_key=True)
    # 指派给哪个模型配置来完成这个任务
    model_configuration_id: int = Field(foreign_key="t_model_configurations.id")

# 聊天会话表
class ChatSession(SQLModel, table=True):
    __tablename__ = "t_chat_sessions"
    id: int = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata_json: str | None = Field(default=None, sa_column=Column(JSON)) # 会话元数据：{"topic": "...", "file_count": 3, "message_count": 15}
    is_active: bool = Field(default=True)

# 聊天消息表
class ChatMessage(SQLModel, table=True):
    __tablename__ = "t_chat_messages"
    id: int = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="t_chat_sessions.id", index=True)
    message_id: str = Field(max_length=100)
    role: str = Field(max_length=50)
    content: str | None = Field(default=None)
    # 按AI SDK v5建议，持久化UIMessage作为事实来源：将parts/metadata/sources存为结构化JSON
    parts: str | None = Field(default=None, sa_column=Column(JSON))
    metadata_json: str | None = Field(default=None, sa_column=Column(JSON))
    sources: str | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)

# 会话Pin文件表（会话级隔离）
class ChatSessionPinFile(SQLModel, table=True):
    __tablename__ = "t_chat_session_pin_files"
    id: int = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="t_chat_sessions.id", index=True)
    file_path: str = Field(max_length=500)
    file_name: str = Field(max_length=100)
    pinned_at: datetime = Field(default_factory=datetime.now)
    metadata_json: str | None = Field(default=None, sa_column=Column(JSON))


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
                # conn.execute(text(f'''
                #     CREATE TRIGGER IF NOT EXISTS notify_insight_task
                #     AFTER UPDATE ON {Task.__tablename__}
                #     FOR EACH ROW
                #     WHEN NEW.task_type = 'insight' AND NEW.status = 'completed' AND NEW.result = 'success'
                #     BEGIN
                #         INSERT INTO {Notification.__tablename__} (task_id, message, created_at, read)
                #         VALUES (NEW.id, '洞察任务完成', CURRENT_TIMESTAMP, 0);
                #     END;
                # '''))
            
            # 创建文件表
            if not inspector.has_table(MyFiles.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[MyFiles.__table__])
                self._init_default_directories()  # 初始化默认文件夹
            
            # 创建Bundle扩展名表
            if not inspector.has_table(BundleExtension.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[BundleExtension.__table__])
                self._init_bundle_extensions()  # 初始化Bundle扩展名数据
            
            # 创建系统配置表
            if not inspector.has_table(SystemConfig.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[SystemConfig.__table__])
                system_configs = [
                    {
                        "key": "proxy",
                        "value": "http://127.0.0.1:7890",
                        "description": "代理服务器地址"
                    },
                ]
                for config_data in system_configs:
                    new_config = SystemConfig(
                        key=config_data["key"],
                        value=config_data["value"],
                        description=config_data["description"]
                    )
                    self.session.add(new_config)
                self.session.commit()
            
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
            
            # 创建标签表
            if not inspector.has_table(Tags.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Tags.__table__])
                # # 初始化一些常用标签，预设标签：项目、重要、旅行、汇报、论文等
                # tags_data = [
                #     {"name": "项目", "type": TagsType.SYSTEM.value},
                #     {"name": "重要", "type": TagsType.SYSTEM.value},
                #     {"name": "旅行", "type": TagsType.SYSTEM.value},
                #     {"name": "汇报", "type": TagsType.SYSTEM.value},
                #     {"name": "论文", "type": TagsType.SYSTEM.value},
                # ]
                # for tag in tags_data:
                #     tag_obj = Tags(**tag)
                #     self.session.add(tag_obj)
                # self.session.commit()
            
            # 创建文件粗筛结果表
            if not inspector.has_table(FileScreeningResult.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[FileScreeningResult.__table__])
                # 创建索引 - 为文件路径创建唯一索引
                conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_file_path ON {FileScreeningResult.__tablename__} (file_path);'))
                # 创建索引 - 为文件状态创建索引，便于查询待处理文件
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_file_status ON {FileScreeningResult.__tablename__} (status);'))
                # 创建索引 - 为修改时间创建索引，便于按时间查询
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_modified_time ON {FileScreeningResult.__tablename__} (modified_time);'))
                # 创建索引 - 为task_id创建索引，便于查询关联任务
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_task_id ON {FileScreeningResult.__tablename__} (task_id);'))

            # 创建 FTS5 虚拟表和触发器
            if not inspector.has_table('t_files_fts'):
                conn.execute(text(f"""
                    CREATE VIRTUAL TABLE t_files_fts USING fts5(
                        file_id UNINDEXED,
                        tags_search_ids
                    );
                """))
            
            # 删除旧的触发器（如果存在）
            conn.execute(text("DROP TRIGGER IF EXISTS trg_files_after_insert;"))
            conn.execute(text("DROP TRIGGER IF EXISTS trg_files_after_delete;"))
            conn.execute(text("DROP TRIGGER IF EXISTS trg_files_after_update;"))
            
            # 创建新的触发器
            conn.execute(text(f"""
                CREATE TRIGGER IF NOT EXISTS trg_files_after_insert AFTER INSERT ON {FileScreeningResult.__tablename__}
                BEGIN
                    INSERT INTO t_files_fts (file_id, tags_search_ids)
                    VALUES (NEW.id, REPLACE(IFNULL(NEW.tags_display_ids, ''), ',', ' '));
                END;
            """))

            conn.execute(text(f"""
                CREATE TRIGGER IF NOT EXISTS trg_files_after_delete AFTER DELETE ON {FileScreeningResult.__tablename__}
                BEGIN
                    DELETE FROM t_files_fts WHERE file_id = OLD.id;
                END;
            """))

            conn.execute(text(f"""
                CREATE TRIGGER IF NOT EXISTS trg_files_after_update AFTER UPDATE ON {FileScreeningResult.__tablename__}
                BEGIN
                    DELETE FROM t_files_fts WHERE file_id = OLD.id;
                    INSERT INTO t_files_fts (file_id, tags_search_ids)
                    VALUES (NEW.id, REPLACE(IFNULL(NEW.tags_display_ids, ''), ',', ' '));
                END;
            """))
            
            conn.commit()  # 提交所有更改

            # 创建文档表
            # TODO 根据后续代码里的要求创建索引
            if not inspector.has_table(Document.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[Document.__table__])
            # 创建父块表
            if not inspector.has_table(ParentChunk.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ParentChunk.__table__])
            # 创建子块表
            if not inspector.has_table(ChildChunk.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ChildChunk.__table__])
        
            # 创建聊天会话表
            if not inspector.has_table(ChatSession.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ChatSession.__table__])
            # 创建聊天消息表
            if not inspector.has_table(ChatMessage.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ChatMessage.__table__])
                # INDEX(session_id, created_at)   -- 查询优化
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_chat_message_session ON {ChatMessage.__tablename__} (session_id, created_at);
                """))
                conn.commit()
            # 创建会话Pin文件表
            if not inspector.has_table(ChatSessionPinFile.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ChatSessionPinFile.__table__])
                # UNIQUE(session_id, file_path)   -- 同一会话中文件唯一
                conn.execute(text(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_session_pin_file ON {ChatSessionPinFile.__tablename__} (session_id, file_path);
                """))
                conn.commit()
            
            # 模型提供者表
            if not inspector.has_table(ModelProvider.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ModelProvider.__table__])
                # 初始化默认模型提供者
                data = [
                    {
                        "display_name": "OpenAI", 
                        "provider_type": "openai",
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "https://api.openai.com/v1", 
                        "is_user_added": False,
                        "get_key_url": "https://platform.openai.com/api-keys",
                        "support_discovery": True,
                        "use_proxy": True,
                    },
                    # {
                    #     "display_name": "Azure OpenAI", 
                    #     "provider_type": "azure", 
                    #     "source_type": ModelSourceType.CONFIGURABLE.value, 
                    #     "extra_data_json":{
                    #         "azure_endpoint": "",
                    #         "api_version": "",
                    #         "api_key": "",
                    #     }, 
                    #     "is_user_added": False,
                    #     "get_key_url": "https://azure.microsoft.com/",
                    #     "support_discovery": False
                    # },
                    {
                        "display_name": "Anthropic", 
                        "provider_type": "anthropic", 
                        "source_type": ModelSourceType.CONFIGURABLE.value,
                        "base_url": "https://api.anthropic.com/v1",
                        "is_user_added": False,
                        "get_key_url": "https://console.anthropic.com/settings/keys",
                        "support_discovery": True,
                        "use_proxy": True,
                    },
                    {
                        "display_name": "Google AI Studio", 
                        "provider_type": "google", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "https://generativelanguage.googleapis.com/v1beta",
                        "is_user_added": False,
                        "get_key_url": "https://aistudio.google.com/apikey",
                        "support_discovery": False,
                        "use_proxy": True,
                    },
                    # {
                    #     "display_name": "Google Vertex AI", 
                    #     "provider_type": "google", 
                    #     "source_type": ModelSourceType.CONFIGURABLE.value, 
                    #     "extra_data_json":{
                    #         "project": "",
                    #         "location": "",
                    #     }, 
                    #     "is_user_added": False,
                    #     "get_key_url": "https://console.cloud.google.com/vertex-ai/",
                    #     "support_discovery": False
                    # },
                    {
                        "display_name": "Grok (xAI)", 
                        "provider_type": "grok", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "https://api.x.ai/v1",
                        "is_user_added": False,
                        "get_key_url": "https://console.x.ai/",
                        "support_discovery": True,
                        "use_proxy": True,
                    },
                    {
                        "display_name": "OpenRouter", 
                        "provider_type": "openai", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "https://openrouter.ai/api/v1",
                        "is_user_added": False,
                        "get_key_url": "https://openrouter.ai/keys",
                        "support_discovery": True,
                        "use_proxy": True,
                    },
                    {
                        "display_name": "Groq", 
                        "provider_type": "groq", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "https://api.groq.com/openai/v1",
                        "is_user_added": False,
                        "get_key_url": "https://console.groq.com/keys",
                        "support_discovery": False,
                        "use_proxy": True,
                    },
                    {
                        "display_name": "Ollama", 
                        "provider_type": "openai", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "http://127.0.0.1:11434/v1",
                        "is_user_added": False,
                        "get_key_url": "",
                        "support_discovery": True,
                        "use_proxy": False,
                    },
                    {
                        "display_name": "LM Studio", 
                        "provider_type": "openai", 
                        "source_type": ModelSourceType.CONFIGURABLE.value, 
                        "base_url": "http://127.0.0.1:1234/v0",
                        "is_user_added": False,
                        "get_key_url": "",
                        "support_discovery": True,
                        "use_proxy": False,
                    },
                ]
                self.session.add_all([ModelProvider(**provider) for provider in data])
                self.session.commit()
            
            # 模型配置表
            if not inspector.has_table(ModelConfiguration.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[ModelConfiguration.__table__])
                # provider_id和model_identifier的组合唯一
                conn.execute(text(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_id_model_identifier ON {ModelConfiguration.__tablename__} (provider_id, model_identifier);
                """))
                conn.commit()
            
            # 能力指派表
            if not inspector.has_table(CapabilityAssignment.__tablename__):
                SQLModel.metadata.create_all(engine, tables=[CapabilityAssignment.__table__])
        
        return True

    def _init_bundle_extensions(self) -> None:
        """初始化macOS Bundle扩展名数据"""
        bundle_extensions = [
            # 应用程序Bundle
            {"extension": ".app", "description": "macOS应用程序包"},
            {"extension": ".bundle", "description": "macOS通用Bundle包"},
            {"extension": ".framework", "description": "macOS框架Bundle"},
            {"extension": ".plugin", "description": "macOS插件Bundle"},
            {"extension": ".kext", "description": "macOS内核扩展"},
            
            # 媒体和创意软件Bundle
            {"extension": ".fcpbundle", "description": "Final Cut Pro项目包"},
            {"extension": ".imovielibrary", "description": "iMovie项目库"},
            {"extension": ".tvlibrary", "description": "TV应用库"},
            {"extension": ".theater", "description": "Theater应用库"},
            {"extension": ".photoslibrary", "description": "Photos照片库"},
            {"extension": ".logicx", "description": "Logic Pro X项目包"},
            
            # 办公软件Bundle
            {"extension": ".pages", "description": "Apple Pages文档包"},
            {"extension": ".numbers", "description": "Apple Numbers电子表格包"},
            {"extension": ".key", "description": "Apple Keynote演示文稿包"},
            
            # 开发工具Bundle
            {"extension": ".xcodeproj", "description": "Xcode项目包"},
            {"extension": ".xcworkspace", "description": "Xcode工作空间包"},
            {"extension": ".playground", "description": "Swift Playground包"},
            {"extension": ".xcassets", "description": "Xcode资源目录包"},
            {"extension": ".xcdatamodeld", "description": "Core Data模型包"},
            
            # 设计和自动化Bundle
            {"extension": ".sketch", "description": "Sketch设计文件包"},
            {"extension": ".workflow", "description": "Automator工作流程包"},
            {"extension": ".action", "description": "Automator动作包"},
            {"extension": ".lbaction", "description": "LaunchBar动作包"},
            
            # 系统相关Bundle
            {"extension": ".prefpane", "description": "系统偏好设置面板"},
            {"extension": ".appex", "description": "App扩展"},
            {"extension": ".component", "description": "音频单元组件"},
            {"extension": ".wdgt", "description": "Dashboard小部件"},
            {"extension": ".qlgenerator", "description": "Quick Look生成器"},
            {"extension": ".mdimporter", "description": "Spotlight元数据导入器"},
            {"extension": ".safari-extension", "description": "Safari扩展"},
            
            # 本地化和资源Bundle
            {"extension": ".lproj", "description": "本地化资源目录"},
            {"extension": ".nib", "description": "Interface Builder文件包"},
            {"extension": ".storyboard", "description": "Interface Builder故事板包"},
            
            # 其他Bundle
            {"extension": ".download", "description": "未完成下载的文件包"},
            {"extension": ".scptd", "description": "AppleScript脚本包"},
            {"extension": ".rtfd", "description": "富文本格式目录"},
        ]
        
        bundle_objs = []
        for ext_data in bundle_extensions:
            bundle_objs.append(
                BundleExtension(
                    extension=ext_data["extension"],
                    description=ext_data["description"],
                    is_active=True
                )
            )
        
        self.session.add_all(bundle_objs)
        self.session.commit()
    
    # def _init_system_config(self) -> None:
    #     """初始化系统配置数据，确保所有默认配置项都存在"""

    # def _init_local_model_configs(self) -> None:
    #     """初始化本地模型配置数据"""

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
        stmt = select(FileCategory)
        category_map = {cat.name: cat.id for cat in self.session.exec(stmt).all()}
        
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
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "draft",
                    "label_name": "草稿",
                    "refine_type": "status"
                }
            },
            {
                "name": "最终版文件识别",
                "description": "识别包含最终版、Final等关键词的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(最终版|终稿|final|Final|FINAL)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "final",
                    "label_name": "最终版",
                    "refine_type": "status"
                }
            },
            {
                "name": "版本号文件识别",
                "description": "识别包含版本号标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(v\d+|v\d+\.\d+|版本\d+|V\d+)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "versioned",
                    "label_name": "带版本号",
                    "refine_type": "version"
                }
            },
            {
                "name": "旧版/备份文件识别",
                "description": "识别旧版或备份文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(_old|_旧|_backup|_备份|_bak|副本|Copy of|\(\d+\))",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "backup",
                    "label_name": "备份/旧版",
                    "refine_type": "cleanup"
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
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "report",
                    "label_name": "报告",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "提案文件识别",
                "description": "识别各类提案文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(提案|Proposal|proposal|PROPOSAL)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "proposal",
                    "label_name": "提案",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "合同/协议文件识别",
                "description": "识别合同或协议文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(合同|协议|合约|Contract|contract|Agreement|agreement)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "contract",
                    "label_name": "合同/协议",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "发票/收据文件识别",
                "description": "识别发票或收据文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(发票|收据|Invoice|invoice|Receipt|receipt)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "invoice",
                    "label_name": "发票/收据",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "演示/幻灯片文件识别",
                "description": "识别演示文稿或幻灯片文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(演示|幻灯片|Presentation|presentation|Slides|slides)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "presentation",
                    "label_name": "演示/幻灯片",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "周报/月报文件识别",
                "description": "识别周报或月报文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(周报|月报|周总结|月总结|Weekly|weekly|Monthly|monthly)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "report_periodical",
                    "label_name": "周报/月报",
                    "refine_type": "document_type"
                }
            },
            {
                "name": "简历文件识别",
                "description": "识别简历文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(简历|Resume|resume|CV|cv)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "resume",
                    "label_name": "简历",
                    "refine_type": "document_type"
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
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "dated_ymd",
                    "label_name": "带日期",
                    "refine_type": "time"
                }
            },
            {
                "name": "季度标记",
                "description": "识别包含季度标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Q[1-4]|第[一二三四]季度|[一二三四]季度|上半年|下半年)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "quarterly",
                    "label_name": "季度文件",
                    "refine_type": "time"
                }
            },
            {
                "name": "月份标记",
                "description": "识别包含月份标记的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|[一二三四五六七八九十]{1,2}月)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "monthly",
                    "label_name": "月度文件",
                    "refine_type": "time"
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
                "action": RuleAction.LABEL.value,
                "priority": RulePriority.HIGH.value,
                "extra_data": {
                    "label": "screenshot",
                    "label_name": "截图",
                    "refine_type": "app_source"
                }
            },
            {
                "name": "相机/手机照片识别",
                "description": "识别相机或手机生成的照片文件名模式",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(IMG_\d+|DSC_\d+|DCIM|DSCN\d+)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "camera",
                    "label_name": "相机照片",
                    "refine_type": "app_source"
                }
            },
            {
                "name": "微信文件识别",
                "description": "识别微信相关的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(微信|WeChat|wechat|MicroMsg|mmexport)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "priority": RulePriority.HIGH.value,
                "extra_data": {
                    "label": "wechat",
                    "label_name": "微信文件",
                    "refine_type": "app_source"
                }
            },
            {
                "name": "下载文件识别",
                "description": "识别下载的文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(下载|download|Download|DOWNLOAD)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "download",
                    "label_name": "下载文件",
                    "refine_type": "app_source"
                }
            },
            {
                "name": "视频会议文件识别",
                "description": "识别视频会议相关文件",
                "rule_type": RuleType.FILENAME.value,
                "pattern": r"(Zoom|zoom|Teams|teams|Meet|meet|会议记录|meeting)",
                "pattern_type": "regex",
                "action": RuleAction.LABEL.value,
                "extra_data": {
                    "label": "meeting",
                    "label_name": "会议文件",
                    "refine_type": "app_source"
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
        
        # macOS Bundle文件夹规则
        macos_bundle_rules = []
        
        # 只在macOS平台上添加这些规则
        if os.name == 'posix' and os.uname().sysname == 'Darwin':  # 检测是否为macOS
            macos_bundle_rules = [
                {
                    "name": "Final Cut Pro项目文件夹",
                    "description": "识别Final Cut Pro项目bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.fcpbundle",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "iMovie项目文件夹",
                    "description": "识别iMovie项目bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(imovielibrary|theater|localized|tvlibrary)",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "Photos照片库文件夹",
                    "description": "识别Photos照片库bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.photoslibrary",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "其他常见macOS应用Bundle",
                    "description": "识别其他常见macOS应用Bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(app|framework|plugin|bundle|kext)",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "macOS办公和开发工具Bundle",
                    "description": "识别macOS苹果办公套件和开发工具Bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(pages|numbers|key|logicx|xcodeproj|xcworkspace)",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value, 
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "macOS设计和自动化Bundle",
                    "description": "识别macOS设计和自动化工具Bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(sketch|lproj|workflow|lbaction|action|qlgenerator)",
                    "pattern_type": "regex", 
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "macOS其他系统Bundle",
                    "description": "识别macOS其他系统级Bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(prefpane|appex|component|wdgt|download|xcdatamodeld|scptd|rtfd)",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                },
                {
                    "name": "macOS开发相关Bundle",
                    "description": "识别macOS开发相关Bundle",
                    "rule_type": RuleType.OS_BUNDLE.value,
                    "pattern": r"\.(safari-extension|xcassets|playground)",
                    "pattern_type": "regex",
                    "action": RuleAction.EXCLUDE.value,
                    "priority": RulePriority.HIGH.value
                }
            ]
        
        # 合并所有规则
        all_rules = []
        all_rules.extend(status_version_rules)
        all_rules.extend(doc_type_rules)
        all_rules.extend(time_indicators_rules)
        all_rules.extend(app_source_rules)
        all_rules.extend(temp_ignore_rules)
        all_rules.extend(macos_bundle_rules)
        
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
                    "refine_score": 70  # 精炼权重分
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
                    "refine_score": 70
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
                    "refine_score": 80
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
                    "include_markdown": True,  # 仅处理Markdown文档
                    "refine_score": 90
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
                    "refine_score": 85
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
                    "refine_score": 85
                }
            },
            {
                "name": "通用开发项目",
                "description": "识别包含常见开发文件夹结构的项目",
                "rule_type": "structure",
                "pattern": "src|include|lib|docs|assets",
                "pattern_type": "regex",
                "priority": RulePriority.MEDIUM.value,
                "indicators": {
                    "is_code_project": True,
                    "structure_markers": ["src", "lib", "include", "docs"],
                    "refine_score": 80
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

    def _init_default_directories(self) -> None:
        """初始化默认系统文件夹"""
        import platform
        
        # 检查是否已有文件夹记录，如果有则跳过初始化
        existing_count = self.session.exec(select(MyFiles)).first()
        if existing_count is not None:
            return
        
        default_dirs = []
        system = platform.system()
        
        # 设置用户主目录
        home_dir = os.path.expanduser("~") if system != "Windows" else os.environ.get("USERPROFILE", "")
        
        if system == "Darwin":  # macOS
            # 白名单常用文件夹（用户数据文件夹，通常希望被扫描）
            whitelist_common_dirs = [
                {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                {"name": "文稿", "path": os.path.join(home_dir, "Documents")},
                {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                {"name": "影片", "path": os.path.join(home_dir, "Movies")},
                {"name": "个人项目", "path": os.path.join(home_dir, "Projects")},
            ]
            
        elif system == "Windows":
            # Windows系统
            if home_dir:
                # 白名单常用文件夹
                whitelist_common_dirs = [
                    {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                    {"name": "文档", "path": os.path.join(home_dir, "Documents")},
                    {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                    {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                    {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                    {"name": "视频", "path": os.path.join(home_dir, "Videos")},
                    {"name": "个人项目", "path": os.path.join(home_dir, "Projects")},
                ]
                
            else:
                whitelist_common_dirs = []
        else:
            # Linux系统
            whitelist_common_dirs = [
                {"name": "桌面", "path": os.path.join(home_dir, "Desktop")},
                {"name": "文档", "path": os.path.join(home_dir, "Documents")},
                {"name": "下载", "path": os.path.join(home_dir, "Downloads")},
                {"name": "图片", "path": os.path.join(home_dir, "Pictures")},
                {"name": "音乐", "path": os.path.join(home_dir, "Music")},
                {"name": "视频", "path": os.path.join(home_dir, "Videos")},
                {"name": "个人项目", "path": os.path.join(home_dir, "Projects")},
            ]
        
        # 处理白名单文件夹（用户数据文件夹）
        for dir_info in whitelist_common_dirs:
            if os.path.exists(dir_info["path"]) and os.path.isdir(dir_info["path"]):
                default_dirs.append(
                    MyFiles(
                        path=dir_info["path"],
                        alias=dir_info["name"],
                        is_blacklist=False,
                        is_common_folder=True  # 标记为常见文件夹，界面上不可删除
                    )
                )
        
        if default_dirs:
            self.session.add_all(default_dirs)

            self.session.commit()

if __name__ == '__main__':
    from config import TEST_DB_PATH
    db_mgr = DBManager(Session(create_engine(f'sqlite:///{TEST_DB_PATH}')))
    db_mgr.init_db()
    print("数据库初始化完成")
