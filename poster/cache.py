"""
海报缓存管理器
负责海报文件的存储、索引和生命周期管理
"""

import os
import json
import base64
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from threading import Lock

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger("poster_cache")


class PosterCache:
    """海报缓存管理器"""

    def __init__(self, storage_path: str, max_days: int = 7):
        self.storage_path = storage_path
        self.max_days = max_days
        self.cache_file = os.path.join(storage_path, "cache.json")
        self._lock = Lock()

        # 确保目录存在
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(os.path.join(storage_path, "daily"), exist_ok=True)
        os.makedirs(os.path.join(storage_path, "weekly"), exist_ok=True)

        self._load_cache_index()

    def _load_cache_index(self):
        """加载缓存索引"""
        self._cache_index = {}

        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache_index = json.load(f)
                logger.info(f"缓存索引加载成功，共{len(self._cache_index)}个条目")
            else:
                logger.info("缓存索引文件不存在，创建新索引")
                self._save_cache_index()
        except Exception as e:
            logger.error(f"加载缓存索引失败: {e}")
            self._cache_index = {}

    def _save_cache_index(self):
        """保存缓存索引"""
        try:
            self._cache_index["last_updated"] = datetime.now().isoformat()

            with self._lock:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache_index, f, ensure_ascii=False, indent=2)

            logger.debug("缓存索引保存成功")
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")

    def _get_filename(self, poster_type: str, date_str: str) -> str:
        """生成文件名"""
        sub_dir = "daily" if poster_type == "daily" else "weekly"
        return f"{poster_type}_{date_str}.png"

    def _get_filepath(self, poster_type: str, date_str: str) -> str:
        """获取文件路径"""
        sub_dir = "daily" if poster_type == "daily" else "weekly"
        filename = self._get_filename(poster_type, date_str)
        return os.path.join(self.storage_path, sub_dir, filename)

    async def save_poster(
        self, poster_type: str, image_bytes: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """保存海报

        Args:
            poster_type: 海报类型 (daily/weekly)
            image_bytes: 图片二进制数据
            metadata: 附加元数据

        Returns:
            海报信息字典
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            filename = self._get_filename(poster_type, date_str)
            filepath = self._get_filepath(poster_type, date_str)

            # 保存图片文件
            with open(filepath, "wb") as f:
                f.write(image_bytes)

            # 增强元数据
            enhanced_metadata = {
                "type": poster_type,
                "filename": filename,
                "filepath": filepath,
                "size": len(image_bytes),
                "created_at": datetime.now().isoformat(),
                "base64": base64.b64encode(image_bytes).decode(),
                "date_str": date_str,
                "cache_version": "2.0",
            }

            if metadata:
                enhanced_metadata.update(metadata)

            poster_info = enhanced_metadata

            # 更新缓存索引
            with self._lock:
                self._cache_index[poster_type] = poster_info

            self._save_cache_index()

            logger.info(f"海报保存成功: {poster_type} -> {filepath}")
            return poster_info

        except Exception as e:
            logger.error(f"保存海报失败: {e}")
            raise

    async def get_poster(self, poster_type: str) -> Optional[Dict[str, Any]]:
        """获取海报信息

        Args:
            poster_type: 海报类型

        Returns:
            海报信息字典或None
        """
        try:
            with self._lock:
                if poster_type not in self._cache_index:
                    return None

                poster_info = self._cache_index[poster_type]

                # 检查文件是否存在
                if not os.path.exists(poster_info.get("filepath", "")):
                    logger.warning(f"海报文件不存在: {poster_info.get('filepath')}")
                    del self._cache_index[poster_type]
                    self._save_cache_index()
                    return None

                # 检查是否过期
                created_date = datetime.fromisoformat(poster_info.get("created_at", ""))
                if datetime.now() - created_date > timedelta(days=self.max_days):
                    logger.info(f"海报已过期: {poster_type}")
                    await self.delete_poster(poster_type)
                    return None

                # 重新读取base64数据（如果内存中没有）
                if "base64" not in poster_info:
                    try:
                        with open(poster_info["filepath"], "rb") as f:
                            poster_info["base64"] = base64.b64encode(f.read()).decode()
                    except Exception as e:
                        logger.error(f"读取海报文件失败: {e}")
                        return None

                return poster_info

        except Exception as e:
            logger.error(f"获取海报失败: {e}")
            return None

    async def delete_poster(self, poster_type: str) -> bool:
        """删除海报

        Args:
            poster_type: 海报类型

        Returns:
            是否删除成功
        """
        try:
            with self._lock:
                if poster_type not in self._cache_index:
                    return True

                poster_info = self._cache_index[poster_type]
                filepath = poster_info.get("filepath", "")

                # 删除文件
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info(f"删除海报文件: {filepath}")

                # 从索引中移除
                del self._cache_index[poster_type]

            self._save_cache_index()
            return True

        except Exception as e:
            logger.error(f"删除海报失败: {e}")
            return False

    async def cleanup_old_posters(self) -> int:
        """清理过期的海报文件

        Returns:
            清理的文件数量
        """
        cleaned_count = 0
        cutoff_date = datetime.now() - timedelta(days=self.max_days)

        try:
            # 清理各子目录中的文件
            for sub_dir in ["daily", "weekly"]:
                dir_path = os.path.join(self.storage_path, sub_dir)
                if not os.path.exists(dir_path):
                    continue

                for filename in os.listdir(dir_path):
                    if not filename.endswith(".png"):
                        continue

                    filepath = os.path.join(dir_path, filename)
                    try:
                        # 检查文件修改时间
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if file_mtime < cutoff_date:
                            os.remove(filepath)
                            cleaned_count += 1
                            logger.info(f"清理过期海报: {filename}")
                    except Exception as e:
                        logger.error(f"清理文件失败 {filename}: {e}")

            # 清理缓存索引中的过期条目
            with self._lock:
                expired_keys = []
                for key, poster_info in self._cache_index.items():
                    if key in ["last_updated"]:
                        continue

                    try:
                        created_date = datetime.fromisoformat(poster_info.get("created_at", ""))
                        if created_date < cutoff_date:
                            expired_keys.append(key)
                    except Exception:
                        expired_keys.append(key)

                for key in expired_keys:
                    del self._cache_index[key]

            if expired_keys:
                self._save_cache_index()
                logger.info(f"清理过期缓存索引: {len(expired_keys)}个")

            logger.info(f"海报清理完成，共清理{cleaned_count}个文件")
            return cleaned_count

        except Exception as e:
            logger.error(f"清理海报失败: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            stats = {
                "total_posters": 0,
                "daily_poster_exists": False,
                "weekly_poster_exists": False,
                "total_size": 0,
                "last_updated": self._cache_index.get("last_updated"),
            }

            with self._lock:
                for key, poster_info in self._cache_index.items():
                    if key in ["last_updated"]:
                        continue

                    stats["total_posters"] += 1
                    stats["total_size"] += poster_info.get("size", 0)

                    if key == "daily":
                        stats["daily_poster_exists"] = True
                    elif key == "weekly":
                        stats["weekly_poster_exists"] = True

            return stats

        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}

    async def preload_base64_data(self) -> Dict[str, str]:
        """预加载所有海报的base64数据到内存"""
        base64_cache = {}

        try:
            with self._lock:
                for poster_type, poster_info in self._cache_index.items():
                    if poster_type in ["last_updated"]:
                        continue

                    if "base64" not in poster_info:
                        filepath = poster_info.get("filepath", "")
                        if os.path.exists(filepath):
                            with open(filepath, "rb") as f:
                                poster_info["base64"] = base64.b64encode(f.read()).decode()

                    if "base64" in poster_info:
                        base64_cache[poster_type] = poster_info["base64"]

            logger.info(f"预加载base64数据完成，共{len(base64_cache)}个海报")
            return base64_cache

        except Exception as e:
            logger.error(f"预加载base64数据失败: {e}")
            return {}


# 全局缓存实例
_global_cache: Optional[PosterCache] = None


def get_global_poster_cache() -> PosterCache:
    """获取全局海报缓存实例"""
    global _global_cache
    if _global_cache is None:
        # 使用插件目录下的posters文件夹
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        storage_path = os.path.join(plugin_dir, "posters")
        _global_cache = PosterCache(storage_path)
    return _global_cache
