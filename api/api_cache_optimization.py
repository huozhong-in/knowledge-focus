"""
Python API 优化方案 - 针对 /config/all 端点的性能问题
"""

from datetime import datetime, timedelta
from typing import (
    Dict,
    # List,
    Any,
    Optional,
    Tuple,
    Union,
    TypeVar,
    Generic,
)
from functools import (
    # lru_cache,
    wraps,
)
from threading import RLock

# 定义泛型类型
T = TypeVar("T")


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
        self.stats = {"hits": 0, "misses": 0, "total_calls": 0}

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
            self.cache[key] = {"value": value, "expiry_time": expiry_time}

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


# # 全局缓存实例
# config_cache = TimedCache[Dict[str, Any]](expiry_seconds=300)  # 5分钟过期
# bundle_ext_cache = TimedCache[List[str]](expiry_seconds=600)   # 10分钟过期


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
                cache_key += "_" + "_".join(
                    f"{k}_{v}" for k, v in sorted(kwargs.items())
                )

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
