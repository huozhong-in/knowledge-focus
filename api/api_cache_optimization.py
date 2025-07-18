"""
Python API 优化方案 - 针对 /config/all 和 /bundle-extensions/for-rust 端点的性能问题
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union, TypeVar, Generic
from functools import lru_cache, wraps
from threading import RLock

# 定义泛型类型
T = TypeVar('T')

class TimedCache(Generic[T]):
    """
    具有过期时间的内存缓存实现
    
    特性:
    1. 线程安全
    2. 自动过期
    3. 支持强制刷新
    4. 记录缓存命中率统计
    """
    
    def __init__(self, expiry_seconds: int = 60):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.expiry_seconds = expiry_seconds
        self.lock = RLock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "total_calls": 0
        }
    
    def get(self, key: str) -> Tuple[bool, Optional[T]]:
        """
        从缓存获取值
        
        返回: (是否命中, 值)
        """
        with self.lock:
            self.stats["total_calls"] += 1
            
            if key not in self.cache:
                self.stats["misses"] += 1
                return False, None
            
            cached_item = self.cache[key]
            current_time = datetime.now()
            
            if current_time > cached_item["expiry_time"]:
                self.stats["misses"] += 1
                return False, None
            
            self.stats["hits"] += 1
            return True, cached_item["value"]
    
    def set(self, key: str, value: T) -> None:
        """设置缓存值"""
        with self.lock:
            expiry_time = datetime.now() + timedelta(seconds=self.expiry_seconds)
            self.cache[key] = {
                "value": value,
                "expiry_time": expiry_time
            }
    
    def invalidate(self, key: str) -> None:
        """使特定键的缓存失效"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self.lock:
            self.cache.clear()
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """获取缓存统计信息"""
        with self.lock:
            stats = dict(self.stats)
            if stats["total_calls"] > 0:
                stats["hit_rate"] = stats["hits"] / stats["total_calls"] * 100
            else:
                stats["hit_rate"] = 0
            return stats

# 全局缓存实例
config_cache = TimedCache[Dict[str, Any]](expiry_seconds=300)  # 5分钟过期
bundle_ext_cache = TimedCache[List[str]](expiry_seconds=600)   # 10分钟过期

def cached(cache_instance: TimedCache[T], key_prefix: str = ""):
    """
    缓存装饰器
    
    使用:
    @cached(config_cache, "config")
    def get_all_config():
        ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = key_prefix
            if args:
                cache_key += "_" + "_".join(str(arg) for arg in args)
            if kwargs:
                cache_key += "_" + "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
            
            # 尝试从缓存获取
            hit, cached_value = cache_instance.get(cache_key)
            if hit:
                return cached_value
            
            # 缓存未命中，执行原始函数
            result = func(*args, **kwargs)
            
            # 保存到缓存
            cache_instance.set(cache_key, result)
            return result
        return wrapper
    return decorator

# 下面是如何在API端点中使用这些缓存功能的示例代码

"""
from fastapi import FastAPI, Depends
from sqlmodel import Session

app = FastAPI()

# 应用缓存到现有API端点
@app.get("/config/all")
def get_all_configuration(
    session: Session = Depends(get_session),
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    # 使用缓存包装函数
    return _get_all_configuration_cached(session, myfiles_mgr)

@cached(config_cache, "config_all")
def _get_all_configuration_cached(session: Session, myfiles_mgr: MyFilesManager):
    # 原本的代码不变
    try:
        file_categories = session.exec(select(FileCategory)).all()
        file_filter_rules = session.exec(select(FileFilterRule)).all()
        file_extension_maps = session.exec(select(FileExtensionMap)).all()
        project_recognition_rules = session.exec(select(ProjectRecognitionRule)).all()
        monitored_folders = session.exec(select(MyFiles)).all()
        
        # 检查完全磁盘访问权限状态 
        full_disk_access = False
        if sys.platform == "darwin":  # macOS
            access_status = myfiles_mgr.check_full_disk_access_status()
            full_disk_access = access_status.get("has_full_disk_access", False)
        
        # 获取 bundle 扩展名列表（直接从数据库获取，不使用正则规则）
        bundle_extensions = myfiles_mgr.get_bundle_extensions_for_rust()
        
        return {
            "file_categories": file_categories,
            "file_filter_rules": file_filter_rules,
            "file_extension_maps": file_extension_maps,
            "project_recognition_rules": project_recognition_rules,
            "monitored_folders": monitored_folders,
            "full_disk_access": full_disk_access,
            "bundle_extensions": bundle_extensions  # 添加直接可用的 bundle 扩展名列表
        }
    except Exception as e:
        logger.error(f"Error fetching all configuration: {e}", exc_info=True)
        # Return a default structure in case of error
        return {
            "file_categories": [],
            "file_filter_rules": [],
            "file_extension_maps": [],
            "project_recognition_rules": [],
            "monitored_folders": [],
            "full_disk_access": False,
            "bundle_extensions": [".app", ".bundle", ".framework", ".fcpbundle", ".photoslibrary", ".imovielibrary"],  # 默认扩展名
            "error_message": f"Failed to fetch configuration: {str(e)}"
        }

# 类似地，为bundle-extensions端点添加缓存
@app.get("/bundle-extensions/for-rust")
def get_bundle_extensions_for_rust(
    myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)
):
    # 添加日志，提示应该使用新的接口
    logger.warning("[API_DEPRECATED] /bundle-extensions/for-rust 接口已被弃用，建议使用 /config/all 接口获取 bundle_extensions 字段")
    
    return _get_bundle_extensions_for_rust_cached(myfiles_mgr)

@cached(bundle_ext_cache, "bundle_extensions_rust")
def _get_bundle_extensions_for_rust_cached(myfiles_mgr: MyFilesManager):
    try:
        extensions = myfiles_mgr.get_bundle_extensions_for_rust()
        return {
            "status": "success",
            "data": extensions,
            "count": len(extensions),
            "message": f"成功获取 {len(extensions)} 个Rust端Bundle扩展名"
        }
    except Exception as e:
        logger.error(f"获取Rust端Bundle扩展名失败: {str(e)}")
        return {"status": "error", "data": [], "message": f"获取失败: {str(e)}"}

# 当有修改操作时，我们需要使相关缓存失效
def invalidate_config_cache():
    config_cache.clear()

def invalidate_bundle_extensions_cache():
    bundle_ext_cache.clear()

# 例如，当添加或修改监控文件夹时，清除配置缓存
@app.post("/directories")
def add_directory(data: Dict[str, Any], session: Session = Depends(get_session)):
    # 处理添加逻辑...
    # 完成后，使配置缓存失效
    invalidate_config_cache()
    return {"status": "success"}

# 当添加或修改Bundle扩展名时，清除相关缓存
@app.post("/bundle-extensions")
def add_bundle_extension(data: Dict[str, Any], myfiles_mgr: MyFilesManager = Depends(get_myfiles_manager)):
    # 处理添加逻辑...
    # 完成后，使Bundle扩展名缓存失效
    invalidate_bundle_extensions_cache()
    return {"status": "success"}
"""
