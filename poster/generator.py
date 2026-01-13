"""
海报生成器
整合数据获取、模板渲染和缓存管理
"""

import os
import asyncio
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

logger = get_logger("poster_generator")

try:
    # 尝试相对导入
    from ..utils.bangumi_api import BangumiAPIClient
except ImportError:
    try:
        # 尝试绝对导入
        from utils.bangumi_api import BangumiAPIClient
    except ImportError:
        try:
            # 最后尝试直接导入
            import sys
            import os

            plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, plugin_dir)
            from utils.bangumi_api import BangumiAPIClient
        except ImportError:
            BangumiAPIClient = None
            logger.warning("无法导入BangumiAPIClient，剧集信息功能将不可用")


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
            template_data = await self._prepare_daily_data(calendar_data)

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
            template_data = await self._prepare_weekly_data(calendar_data)

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
        if BangumiAPIClient is None:
            logger.warning("BangumiAPIClient不可用，无法获取日历数据")
            return None

        try:
            async with BangumiAPIClient() as client:
                data = await client.get_calendar()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"获取日历数据失败: {e}")
            return None

    async def _prepare_daily_data(self, calendar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            main_anime = await self._format_anime_for_template(sorted_animes[0])
            other_animes_tasks = [
                self._format_anime_for_template(anime)
                for anime in sorted_animes[1:5]  # 最多显示4个次要番剧
            ]
            other_animes = await asyncio.gather(*other_animes_tasks)

        return {
            "date": today_name,
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    async def _prepare_weekly_data(self, calendar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        main_anime = await self._format_anime_for_template(top_animes[0])
        other_animes_tasks = [self._format_anime_for_template(anime) for anime in top_animes[1:8]]
        other_animes = await asyncio.gather(*other_animes_tasks)

        return {
            "date": week_name + " 汇总",
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    async def get_episode_info(self, subject_id: int) -> Dict[str, Any]:
        """获取剧集信息"""
        if BangumiAPIClient is None:
            logger.warning("BangumiAPIClient不可用，无法获取剧集信息")
            return {}

        try:
            # 首先尝试获取详细的剧集信息
            async with BangumiAPIClient() as client:
                episodes = await client.get_subject_episodes(subject_id, episode_type=0)
                if episodes:
                    # 解析最新集数和总集数
                    latest_episode = self._get_latest_episode(episodes)
                    total_episodes = self._get_total_episodes(episodes)

                    return {
                        "latest_episode": latest_episode,
                        "total_episodes": total_episodes,
                        "episode_progress": f"{latest_episode}/{total_episodes}",
                        "update_status": self._get_update_status(episodes),
                    }
                else:
                    logger.info(f"无法获取剧集详情，尝试使用条目详情进行降级处理")

        except Exception as e:
            logger.info(f"剧集详情API调用失败，使用降级方案: {e}")

        # 降级方案：从条目详情获取剧集信息
        try:
            async with BangumiAPIClient() as client:
                subject_detail = await client.get_subject_detail(subject_id)
                if subject_detail:
                    # 从条目详情中提取剧集信息
                    eps = subject_detail.get("eps", 0)  # 已更新集数
                    total_episodes = subject_detail.get("total_episodes", 0)  # 总集数

                    # 如果没有总集数信息，尝试从infobox中提取
                    if total_episodes == 0:
                        total_episodes = self._extract_episodes_from_infobox(subject_detail.get("infobox", []))

                    # 格式化剧集信息
                    latest_episode = f"第{eps}话" if eps > 0 else "第1话"
                    total_eps_str = str(total_episodes) if total_episodes > 0 else "未知"
                    episode_progress = f"{eps}/{total_eps_str}" if total_episodes > 0 else f"{eps}/?"

                    return {
                        "latest_episode": latest_episode,
                        "total_episodes": total_eps_str,
                        "episode_progress": episode_progress,
                        "update_status": "📺 连载中" if eps > 0 else "🔄 即将开播",
                    }
                else:
                    logger.warning(f"无法获取条目详情: {subject_id}")

        except Exception as e:
            logger.warning(f"降级获取剧集信息失败: {e}")

        # 最终降级：返回默认值
        return {
            "latest_episode": "第1话",
            "total_episodes": "?",
            "episode_progress": "?/?",
            "update_status": "📺 更新中",
        }

    def _extract_episodes_from_infobox(self, infobox: List[Dict[str, Any]]) -> int:
        """从infobox中提取话数信息"""
        if not infobox:
            return 0

        try:
            for item in infobox:
                if not isinstance(item, dict):
                    continue

                key = item.get("key", "")
                value = item.get("value", "")

                if key == "话数" and value:
                    # 处理话数字段，可能包含"*"或其他字符
                    if isinstance(value, str):
                        # 移除非数字字符
                        import re

                        numbers = re.findall(r"\d+", value)
                        if numbers:
                            return int(numbers[0])
                    elif isinstance(value, (int, float)):
                        return int(value)

            return 0
        except Exception as e:
            logger.warning(f"从infobox提取话数失败: {e}")
            return 0

    def _get_latest_episode(self, episodes: List[Dict[str, Any]]) -> str:
        """获取最新集数"""
        if not episodes:
            return "第1话"

        try:
            # 找到最大的集数
            max_episode = 0
            for episode in episodes:
                if not isinstance(episode, dict):
                    continue
                ep_num = episode.get("ep", 0)
                if isinstance(ep_num, (int, float)) and ep_num > max_episode:
                    max_episode = ep_num

            return f"第{int(max_episode)}话" if max_episode > 0 else "第1话"
        except Exception as e:
            logger.warning(f"解析最新集数失败: {e}")
            return "第1话"

    def _get_total_episodes(self, episodes: List[Dict[str, Any]]) -> str:
        """获取总集数"""
        if not episodes:
            return "?"

        try:
            # 通过最大的sort值推断总集数
            max_sort = 0
            for episode in episodes:
                if not isinstance(episode, dict):
                    continue
                sort = episode.get("sort", 0)
                if isinstance(sort, (int, float)) and sort > max_sort:
                    max_sort = sort

            return str(int(max_sort)) if max_sort > 0 else "?"
        except Exception as e:
            logger.warning(f"解析总集数失败: {e}")
            return "?"

    def _get_update_status(self, episodes: List[Dict[str, Any]]) -> str:
        """获取更新状态"""
        if not episodes:
            return "更新中"

        try:
            # 检查是否有最近一周的剧集
            from datetime import datetime, timedelta

            now = datetime.now()
            week_ago = now - timedelta(days=7)

            for episode in episodes:
                if not isinstance(episode, dict):
                    continue
                air_date = episode.get("airdate")
                if air_date and isinstance(air_date, str):
                    try:
                        ep_date = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
                        if ep_date >= week_ago:
                            return "✅ 今日更新"
                    except ValueError:
                        continue

            return "📺 连载中"
        except Exception as e:
            logger.warning(f"解析更新状态失败: {e}")
            return "📺 连载中"

    async def _format_anime_for_template(self, anime: Dict[str, Any]) -> Dict[str, Any]:
        """格式化番剧数据用于模板"""
        # 基础信息
        name = anime.get("name", "未知番剧")
        name_cn = anime.get("name_cn", "")
        title = name_cn if name_cn else name

        # 评分信息
        rating = anime.get("rating", {})
        score = rating.get("score", 0)
        score_str = f"{score:.1f}" if score > 0 else "暂无"

        # 获取剧集信息
        subject_id = anime.get("id")
        episode_info = {}
        if subject_id and isinstance(subject_id, int):
            episode_info = await self.get_episode_info(subject_id)
        else:
            logger.debug(f"番剧 {title} 没有有效的subject_id，跳过剧集信息获取")

        # 封面图片
        cover_url = ""
        try:
            images = anime.get("images", {})
            if isinstance(images, dict):
                cover_url = images.get("medium") or images.get("common") or images.get("large", "")
        except Exception as e:
            logger.warning(f"获取封面图片失败: {e}")

        if not cover_url:
            # 使用占位图片
            cover_url = "https://via.placeholder.com/300x400/cccccc/666666?text=No+Cover"

        # 确保所有数据都是有效的
        latest_episode = episode_info.get("latest_episode", "第1话") if episode_info else "第1话"
        episode_progress = episode_info.get("episode_progress", "?/?") if episode_info else "?/?"
        update_status = episode_info.get("update_status", "更新中") if episode_info else "更新中"

        return {
            "title": title or "未知番剧",
            "score": score_str,
            "cover_url": cover_url,
            "latest_episode": latest_episode,
            "episode_progress": episode_progress,
            "update_status": update_status,
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
