"""
KnowledgeFocus 应用配置模块
"""
from functools import wraps
from uuid import uuid4
from pathlib import Path

# 向量化参数
EMBEDDING_DIMENSIONS = 768
EMBEDDING_MODEL = "mlx-community/embeddinggemma-300m-4bit"

# 视觉模型参数
VLM_MODEL = "mlx-community/Qwen3-VL-4B-Instruct-3bit"

# 测试用本地SQLite数据库路径
TEST_DB_PATH = (Path.home() / "Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db").as_posix()

# 单例
def singleton(cls):
    instances = {}    
    
    @wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance

# 生成短ID的工具函数
def generate_vector_id() -> str:
    """生成用于vector_id的短ID"""
    return str(uuid4()).replace('-', '')[:16]