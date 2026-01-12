"""
缓存管理器
提供数据缓存和过期管理功能
"""

import time
import json
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from threading import Lock
import asyncio

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger("cache_manager")


class CacheItem:
    """缓存项"""

    def __init__(self, data: Any, expire_time: float):
        self.data = data
        self.expire_time = expire_time
        self.created_time = time.time()

    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.expire_time

    def get_ttl(self) -> float:
        """获取剩余生存时间(秒)"""
        return max(0, self.expire_time - time.time())


class MemoryCache:
    """内存缓存管理器"""

    def __init__(self, default_ttl: int = 1800, max_size: int = 1000):
        self.default_ttl = default_ttl  # 默认过期时间(秒)
        self.max_size = max_size  # 最大缓存项数
        self._cache: Dict[str, CacheItem] = {}
        self._lock = Lock()
        self._last_cleanup = time.time()

    def _cleanup_expired(self):
        """清理过期项"""
        current_time = time.time()
        if current_time - self._last_cleanup < 60:  # 每分钟最多清理一次
            return

        with self._lock:
            expired_keys = []
            for key, item in self._cache.items():
                if item.is_expired():
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]

            self._last_cleanup = current_time

    def _evict_if_needed(self):
        """如果需要则驱逐最旧的项"""
        if len(self._cache) < self.max_size:
            return

        with self._lock:
            if len(self._cache) < self.max_size:
                return

            # 按创建时间排序，删除最旧的项
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1].created_time)

            # 删除最旧的10%项
            evict_count = max(1, len(sorted_items) // 10)
            for key, _ in sorted_items[:evict_count]:
                del self._cache[key]

    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """设置缓存项

        Args:
            key: 缓存键
            data: 缓存数据
            ttl: 过期时间(秒)，None表示使用默认值
        """
        if ttl is None:
            ttl = self.default_ttl

        expire_time = time.time() + ttl

        with self._lock:
            self._cache[key] = CacheItem(data, expire_time)

        self._evict_if_needed()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存项

        Args:
            key: 缓存键

        Returns:
            缓存数据，如果不存在或过期则返回None
        """
        self._cleanup_expired()

        with self._lock:
            item = self._cache.get(key)
            if item and not item.is_expired():
                return item.data
            elif item:
                # 过期了，删除它
                del self._cache[key]

        return None

    def delete(self, key: str) -> bool:
        """删除缓存项

        Args:
            key: 缓存键

        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """获取缓存大小"""
        self._cleanup_expired()
        with self._lock:
            return len(self._cache)

    def keys(self) -> List[str]:
        """获取所有缓存键"""
        self._cleanup_expired()
        with self._lock:
            return list(self._cache.keys())

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        self._cleanup_expired()

        with self._lock:
            total_items = len(self._cache)
            expired_items = sum(1 for item in self._cache.values() if item.is_expired())

            return {
                "total_items": total_items,
                "expired_items": expired_items,
                "valid_items": total_items - expired_items,
                "max_size": self.max_size,
                "default_ttl": self.default_ttl,
                "last_cleanup": self._last_cleanup,
            }


class AsyncCache:
    """异步缓存管理器"""

    def __init__(self, default_ttl: int = 1800, max_size: int = 1000):
        self._memory_cache = MemoryCache(default_ttl, max_size)
        self._lock = asyncio.Lock()

    async def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """异步设置缓存项"""
        async with self._lock:
            self._memory_cache.set(key, data, ttl)

    async def get(self, key: str) -> Optional[Any]:
        """异步获取缓存项"""
        async with self._lock:
            return self._memory_cache.get(key)

    async def delete(self, key: str) -> bool:
        """异步删除缓存项"""
        async with self._lock:
            return self._memory_cache.delete(key)

    async def clear(self) -> None:
        """异步清空所有缓存"""
        async with self._lock:
            self._memory_cache.clear()

    async def size(self) -> int:
        """异步获取缓存大小"""
        async with self._lock:
            return self._memory_cache.size()

    async def keys(self) -> List[str]:
        """异步获取所有缓存键"""
        async with self._lock:
            return self._memory_cache.keys()

    async def get_stats(self) -> Dict[str, Any]:
        """异步获取缓存统计信息"""
        async with self._lock:
            return self._memory_cache.get_stats()


class CacheKeyBuilder:
    """缓存键构建器"""

    @staticmethod
    def calendar_key() -> str:
        """构建每日放送日程缓存键"""
        return "bangumi:calendar"

    @staticmethod
    def search_key(keyword: str, type_filter: Optional[str] = None, limit: int = 10) -> str:
        """构建搜索结果缓存键"""
        type_part = f":{type_filter}" if type_filter else ""
        return f"bangumi:search:{keyword}{type_part}:limit{limit}"

    @staticmethod
    def subject_detail_key(subject_id: int) -> str:
        """构建条目详情缓存键"""
        return f"bangumi:subject:{subject_id}:detail"

    @staticmethod
    def subject_episodes_key(subject_id: int, episode_type: Optional[int] = None) -> str:
        """构建条目剧集缓存键"""
        type_part = f":type{episode_type}" if episode_type is not None else ""
        return f"bangumi:subject:{subject_id}:episodes{type_part}"

    @staticmethod
    def user_collection_key(user_id: str, subject_type: int = 2, collection_type: Optional[str] = None) -> str:
        """构建用户收藏缓存键"""
        type_part = f":{collection_type}" if collection_type else ""
        return f"bangumi:user:{user_id}:collections:type{subject_type}{type_part}"


# 全局缓存实例
_global_cache: Optional[AsyncCache] = None


def get_global_cache() -> AsyncCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = AsyncCache(default_ttl=1800, max_size=500)
    return _global_cache


async def cached_get_calendar(cache_ttl: int = 1800) -> Optional[List[Dict[str, Any]]]:
    """缓存获取每日放送日程"""
    cache = get_global_cache()
    cache_key = CacheKeyBuilder.calendar_key()

    # 尝试从缓存获取
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    # 缓存未命中，从API获取
    try:
        from .bangumi_api import BangumiAPIClient

        async with BangumiAPIClient() as client:
            data = await client.get_calendar()
            if data:
                await cache.set(cache_key, data, cache_ttl)
            return data
    except Exception as e:
        logger.error(f"获取每日放送日程失败: {str(e)}")
        return None


async def cached_search_subject(
    keyword: str, type_filter: Optional[str] = None, limit: int = 10, cache_ttl: int = 3600
) -> Optional[List[Dict[str, Any]]]:
    """缓存搜索条目"""
    cache = get_global_cache()
    cache_key = CacheKeyBuilder.search_key(keyword, type_filter, limit)

    # 尝试从缓存获取
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    # 缓存未命中，从API获取
    try:
        from .bangumi_api import BangumiAPIClient

        async with BangumiAPIClient() as client:
            data = await client.search_subject(keyword, type_filter, limit)
            if data:
                await cache.set(cache_key, data, cache_ttl)
            return data
    except Exception as e:
        logger.error(f"搜索条目失败: {str(e)}")
        return None


async def cached_get_subject_detail(subject_id: int, cache_ttl: int = 3600) -> Optional[Dict[str, Any]]:
    """缓存获取条目详情"""
    cache = get_global_cache()
    cache_key = CacheKeyBuilder.subject_detail_key(subject_id)

    # 尝试从缓存获取
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    # 缓存未命中，从API获取
    try:
        from .bangumi_api import BangumiAPIClient

        async with BangumiAPIClient() as client:
            data = await client.get_subject_detail(subject_id)
            if data:
                await cache.set(cache_key, data, cache_ttl)
            return data
    except Exception as e:
        logger.error(f"获取条目详情失败: {str(e)}")
        return None
