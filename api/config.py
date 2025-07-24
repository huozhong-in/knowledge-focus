"""
KnowledgeFocus 应用配置模块
"""

# 进程池配置
# 强制使用单一worker，确保文件处理拥有全局一致视角
# 这对文件关联分析和聚类功能至关重要
# 警告: 不要修改此值，除非您完全理解对文件分析质量的影响!
FORCE_SINGLE_WORKER = True

# 任务处理配置
MAX_TASK_TIMEOUT = 600  # 任务处理超时时间（秒）
DEFAULT_BATCH_SIZE = 100  # 默认批处理大小
MAX_BATCH_SIZE = 500  # 最大批处理大小

# 特性开关
ENABLE_SMART_FOLDERS = True  # 启用智慧文件夹功能
ENABLE_FILE_DEDUPLICATION = True  # 启用文件去重功能

# 向量化维度数
EMBEDDING_DIMENSIONS = 1024

# 测试用本地SQLite数据库路径
TEST_DB_PATH = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
