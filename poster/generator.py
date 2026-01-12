"""
海报生成器
整合数据获取、模板渲染和缓存管理
"""

import os
from typing import Dict, Any, Optional, List
from datetime import datetime, date

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


from .renderer import PosterRenderer
from .cache import PosterCache

try:
    from ..utils.bangumi_api import BangumiAPIClient
except ImportError:
    BangumiAPIClient = None

logger = get_logger("poster_generator")


class PosterGenerator:
    """海报生成器"""

    def __init__(self, cache: PosterCache):
        self.cache = cache

    async def generate_daily_poster(self) -> Optional[Dict[str, Any]]:
        """生成每日新番海报"""
        try:
            logger.info("开始生成每日新番海报")

            # 获取今日新番数据
            calendar_data = await self._get_calendar_data()
            if not calendar_data:
                logger.warning("无法获取放送日程数据")
                return None

            # 准备模板数据
            template_data = self._prepare_daily_data(calendar_data)

            # 渲染海报
            async with PosterRenderer() as renderer:
                image_bytes = await renderer.render_poster(template_data, "daily.html")

            # 保存到缓存
            metadata = {
                "anime_count": len(template_data.get("other_animes", []))
                + (1 if template_data.get("main_anime") else 0),
                "date": template_data.get("date"),
                "template": "daily",
            }

            poster_info = await self.cache.save_poster("daily", image_bytes, metadata)

            logger.info("每日新番海报生成成功")
            return poster_info

        except Exception as e:
            logger.error(f"生成每日海报失败: {e}")
            return None

    async def generate_weekly_poster(self) -> Optional[Dict[str, Any]]:
        """生成本周汇总海报"""
        try:
            logger.info("开始生成本周汇总海报")

            # 获取本周数据
            calendar_data = await self._get_calendar_data()
            if not calendar_data:
                logger.warning("无法获取放送日程数据")
                return None

            # 准备周报模板数据
            template_data = self._prepare_weekly_data(calendar_data)

            # 使用周报模板（这里先用daily模板简化）
            async with PosterRenderer() as renderer:
                image_bytes = await renderer.render_poster(template_data, "daily.html")

            # 保存到缓存
            metadata = {
                "anime_count": len(template_data.get("other_animes", [])),
                "date": template_data.get("date"),
                "template": "weekly",
                "week_start": datetime.now().strftime("%Y-%m-%d"),
            }

            poster_info = await self.cache.save_poster("weekly", image_bytes, metadata)

            logger.info("本周汇总海报生成成功")
            return poster_info

        except Exception as e:
            logger.error(f"生成周报海报失败: {e}")
            return None

    async def _get_calendar_data(self) -> Optional[List[Dict[str, Any]]]:
        """获取日历数据"""
        try:
            async with BangumiAPIClient() as client:
                data = await client.get_calendar()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"获取日历数据失败: {e}")
            return None

    def _prepare_daily_data(self, calendar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """准备每日海报数据"""
        today = datetime.now().weekday()  # 0=周日, 1=周一...
        today_name = datetime.now().strftime("%Y年%m月%d日")

        # 找到今天的番剧
        today_animes = []
        for day_info in calendar_data:
            if day_info.get("weekday", {}).get("id") == today:
                today_animes = day_info.get("items", [])
                break

        if not today_animes:
            # 没有今日番剧
            return {
                "date": today_name,
                "has_animes": False,
                "main_anime": None,
                "other_animes": [],
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        # 选择主番剧（评分最高的）
        main_anime = None
        other_animes = []

        # 按评分排序
        sorted_animes = sorted(today_animes, key=lambda x: x.get("rating", {}).get("score", 0), reverse=True)

        if sorted_animes:
            main_anime = self._format_anime_for_template(sorted_animes[0])
            other_animes = [
                self._format_anime_for_template(anime)
                for anime in sorted_animes[1:5]  # 最多显示4个次要番剧
            ]

        return {
            "date": today_name,
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _prepare_weekly_data(self, calendar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """准备周报海报数据"""
        week_start = datetime.now()
        # 获取本周的日期范围
        week_name = f"{week_start.strftime('%Y年第%W周')}"

        # 收集本周所有番剧，按评分排序
        all_animes = []
        for day_info in calendar_data:
            items = day_info.get("items", [])
            all_animes.extend(items)

        # 按评分排序，取前8个
        sorted_animes = sorted(all_animes, key=lambda x: x.get("rating", {}).get("score", 0), reverse=True)
        top_animes = sorted_animes[:8]

        if not top_animes:
            return {
                "date": week_name,
                "has_animes": False,
                "main_anime": None,
                "other_animes": [],
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        # 格式化数据
        main_anime = self._format_anime_for_template(top_animes[0])
        other_animes = [self._format_anime_for_template(anime) for anime in top_animes[1:8]]

        return {
            "date": week_name + " 汇总",
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _format_anime_for_template(self, anime: Dict[str, Any]) -> Dict[str, Any]:
        """格式化番剧数据用于模板"""
        # 基础信息
        name = anime.get("name", "未知番剧")
        name_cn = anime.get("name_cn", "")
        title = name_cn if name_cn else name

        # 评分信息
        rating = anime.get("rating", {})
        score = rating.get("score", 0)
        score_str = f"{score:.1f}" if score > 0 else "暂无"

        # 观看人数
        collection = anime.get("collection", {})
        watchers = collection.get("doing", 0)
        watchers_str = f"{watchers}" if watchers > 0 else "暂无"

        # 放送时间（使用air_date作为fallback）
        air_date = anime.get("air_date", "")
        air_time = anime.get("air_time", air_date[-5:] if air_date else "")
        if not air_time:
            air_time = "时间待定"

        # 封面图片
        images = anime.get("images", {})
        cover_url = images.get("medium") or images.get("common") or images.get("large", "")

        return {
            "title": title,
            "score": score_str,
            "watchers": watchers_str,
            "air_time": air_time,
            "cover_url": cover_url,
        }

    async def get_cached_poster(self, poster_type: str) -> Optional[Dict[str, Any]]:
        """获取缓存的海报"""
        return await self.cache.get_poster(poster_type)

    async def daily_pre_generation(self) -> Dict[str, bool]:
        """每日预生成任务"""
        results = {"daily": False, "weekly": False}

        try:
            # 生成每日海报
            daily_result = await self.generate_daily_poster()
            results["daily"] = daily_result is not None

            # 周一生成周报海报
            if datetime.now().weekday() == 0:  # 周一
                weekly_result = await self.generate_weekly_poster()
                results["weekly"] = weekly_result is not None

            logger.info(f"预生成任务完成: {results}")
            return results

        except Exception as e:
            logger.error(f"预生成任务失败: {e}")
            return results

    async def cleanup_old_posters(self) -> int:
        """清理过期海报"""
        return await self.cache.cleanup_old_posters()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self.cache.get_cache_stats()


# 全局生成器实例
_global_generator: Optional[PosterGenerator] = None


def get_global_poster_generator() -> PosterGenerator:
    """获取全局海报生成器实例"""
    global _global_generator
    if _global_generator is None:
        from .cache import get_global_poster_cache

        cache = get_global_poster_cache()
        _global_generator = PosterGenerator(cache)
    return _global_generator
