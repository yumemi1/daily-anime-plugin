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
from ..utils.blacklist_manager import get_global_blacklist_manager

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

    def __init__(self, cache: PosterCache, plugin_instance=None):
        self.cache = cache
        self.plugin_instance = plugin_instance

    def filter_anime_list(self, anime_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用全局黑名单管理器过滤番剧列表"""
        blacklist_manager = get_global_blacklist_manager()
        if blacklist_manager:
            return blacklist_manager.filter_anime_list(anime_list)
        return anime_list

    def get_blacklist_config(self) -> Dict[str, Any]:
        """获取当前黑名单配置"""
        blacklist_manager = get_global_blacklist_manager()
        if blacklist_manager:
            return blacklist_manager.get_config()
        return {}

    def update_blacklist_config(self, new_config: Dict[str, Any]) -> bool:
        """更新黑名单配置"""
        blacklist_manager = get_global_blacklist_manager()
        if blacklist_manager:
            return blacklist_manager.update_config(new_config)
        return False

    def add_to_blacklist(self, title: str, list_type: str = "custom") -> bool:
        """添加番剧到黑名单"""
        blacklist_manager = get_global_blacklist_manager()
        if blacklist_manager:
            return blacklist_manager.add_to_blacklist(title, list_type)
        return False

    def remove_from_blacklist(self, title: str, list_type: str = "custom") -> bool:
        """从黑名单中移除番剧"""
        blacklist_manager = get_global_blacklist_manager()
        if blacklist_manager:
            return blacklist_manager.remove_from_blacklist(title, list_type)
        return False

    async def generate_daily_poster(self) -> Optional[Dict[str, Any]]:
        """生成每日新番海报 - 增强错误处理"""
        try:
            logger.info("开始生成每日新番海报")

            # 获取今日新番数据
            calendar_data = await self._get_calendar_data()
            if not calendar_data:
                logger.warning("无法获取放送日程数据")
                return await self._generate_empty_poster("daily", "暂无今日新番数据")

            # 准备模板数据
            template_data = await self._prepare_daily_data(calendar_data)

            # 数据完整性检查
            if not template_data.get("has_animes") or not template_data.get("main_anime"):
                return await self._generate_empty_poster("daily", "今日暂无新番更新")

            # 渲染海报
            async with PosterRenderer() as renderer:
                image_bytes = await renderer.render_poster(template_data, "daily.html")

            # 保存到缓存
            metadata = {
                "anime_count": len(template_data.get("other_animes", [])) + 1,
                "date": template_data.get("date"),
                "template": "daily",
                "success": True,
            }

            poster_info = await self.cache.save_poster("daily", image_bytes, metadata)
            logger.info("每日新番海报生成成功")
            return poster_info

        except Exception as e:
            logger.error(f"生成每日海报失败: {e}")
            # 生成错误状态海报
            return await self._generate_error_poster("daily", str(e))

    async def _generate_empty_poster(self, poster_type: str, message: str) -> Dict[str, Any]:
        """生成空状态海报"""
        empty_data = {
            "date": datetime.now().strftime("%Y年%m月%d日"),
            "has_animes": False,
            "message": message,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        async with PosterRenderer() as renderer:
            image_bytes = await renderer.render_poster(empty_data, "empty.html")
            metadata = {"type": "empty", "message": message}
            return await self.cache.save_poster(f"{poster_type}_empty", image_bytes, metadata)

    async def _generate_error_poster(self, poster_type: str, error_msg: str) -> Dict[str, Any]:
        """生成错误状态海报"""
        error_data = {
            "date": datetime.now().strftime("%Y年%m月%d日"),
            "has_animes": False,
            "error_message": error_msg,
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        async with PosterRenderer() as renderer:
            image_bytes = await renderer.render_poster(error_data, "error.html")
            metadata = {"type": "error", "error": error_msg}
            return await self.cache.save_poster(f"{poster_type}_error", image_bytes, metadata)

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

        # 应用过滤规则
        filtered_animes = self.filter_anime_list(today_animes)

        if not filtered_animes:
            # 过滤后没有番剧
            return {
                "date": today_name,
                "has_animes": False,
                "main_anime": None,
                "other_animes": [],
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        # 选择主番剧（热度最高的）
        main_anime = None
        other_animes = []

        # 按热度排序
        sorted_animes = sorted(filtered_animes, key=self.calculate_popularity_score, reverse=True)

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

        # 收集本周所有番剧
        all_animes = []
        for day_info in calendar_data:
            items = day_info.get("items", [])
            all_animes.extend(items)

        # 应用过滤规则
        filtered_animes = self.filter_anime_list(all_animes)

        # 按热度排序，取前8个
        sorted_animes = sorted(filtered_animes, key=self.calculate_popularity_score, reverse=True)
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
                        "update_status": "连载中" if eps > 0 else "即将开播",
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
            "update_status": "更新中",
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
                            return "今日更新"
                    except ValueError:
                        continue

            return "连载中"
        except Exception as e:
            logger.warning(f"解析更新状态失败: {e}")
            return "连载中"

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

        # 封面图片 - 添加详细调试
        cover_url = ""
        try:
            images = anime.get("images", {})
            logger.info(f"番剧 {title} 图片数据: {images}")

            if isinstance(images, dict):
                cover_url = images.get("medium") or images.get("common") or images.get("large", "")

            logger.info(f"选择的封面URL: {cover_url}")

            # 验证URL可访问性
            if cover_url and not cover_url.startswith("https://via.placeholder"):
                try:
                    import aiohttp

                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        async with session.head(cover_url) as response:
                            logger.info(f"图片 {cover_url} 访问状态: {response.status}")
                            if response.status != 200:
                                logger.warning(f"图片无法访问，状态码: {response.status}")
                                cover_url = ""
                except Exception as e:
                    logger.warning(f"图片访问性检查失败 {cover_url}: {e}")
                    cover_url = ""

        except Exception as e:
            logger.warning(f"获取封面图片失败: {e}")

        if not cover_url:
            logger.warning(f"使用占位图片: {title}")
            cover_url = self.get_fallback_cover_url(title)

        # 追番人数信息
        collection = anime.get("collection", {})
        total_watchers = collection.get("wish", 0) + collection.get("doing", 0) + collection.get("collect", 0)
        watchers_str = f"{total_watchers}" if total_watchers > 0 else "暂无"

        # 播放状态颜色
        air_status = self._get_air_status(anime, episode_info)

        # 确保所有数据都是有效的
        latest_episode = episode_info.get("latest_episode", "第1话") if episode_info else "第1话"
        episode_progress = episode_info.get("episode_progress", "?/?") if episode_info else "?/?"
        update_status = episode_info.get("update_status", "更新中") if episode_info else "更新中"

        return {
            "title": title or "未知番剧",
            "score": score_str,
            "watchers": watchers_str,
            "cover_url": cover_url,
            "latest_episode": latest_episode,
            "episode_progress": episode_progress,
            "update_status": update_status,
            "air_status_color": self._get_status_color(air_status),
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

    def get_fallback_cover_url(self, title: str = "未知番剧") -> str:
        """生成更好的占位图片URL"""
        # 使用更美观的占位图服务
        encoded_title = title[:10]  # 限制长度
        return f"https://via.placeholder.com/360x504/667eea/f5f5f5?text={encoded_title}&font-size=24"

    def calculate_popularity_score(self, anime: Dict[str, Any]) -> float:
        """计算番剧热度分数"""

        # 评分 (0-10)
        rating = anime.get("rating", {}).get("score", 0)

        # 追番人数 (0-∞)
        collection = anime.get("collection", {})
        watchers = collection.get("wish", 0) + collection.get("doing", 0) + collection.get("collect", 0)

        # 更新状态（二值化：正在更新=1，其他=0）
        is_airing = anime.get("air_date", "") != "" and anime.get("eps", 0) > 0

        # 新番加成（30天内开播）
        air_date_str = anime.get("air_date", "")
        new_bonus = 0
        if air_date_str:
            try:
                from datetime import datetime, timedelta

                air_date = datetime.fromisoformat(air_date_str.replace("Z", "+00:00"))
                if (datetime.now(air_date.tzinfo) - air_date).days <= 30:
                    new_bonus = 1.0
            except:
                pass

        # 综合评分计算
        # 评分标准化 (0-1)
        normalized_rating = min(rating / 10.0, 1.0) if rating > 0 else 0

        # 追番人数标准化 (0-1，假设1000人为满分)
        normalized_watchers = min(watchers / 1000.0, 1.0) if watchers > 0 else 0

        # 最终分数：40%评分 + 35%追番人数 + 15%更新状态 + 10%新番加成
        final_score = normalized_rating * 0.4 + normalized_watchers * 0.35 + is_airing * 0.15 + new_bonus * 0.1

        logger.info(
            f"番剧 {anime.get('name', '未知')} 热度计算: "
            f"评分={rating}, 追番={watchers}, 更新={is_airing}, 新番={new_bonus}, "
            f"最终分数={final_score:.3f}"
        )

        return final_score

    def _get_air_status(self, anime: Dict[str, Any], episode_info: Dict[str, Any]) -> str:
        """获取播放状态"""
        eps = anime.get("eps", 0)
        total_eps = anime.get("total_episodes", 0)

        if eps == 0:
            return "即将开播"
        elif total_eps > 0 and eps >= total_eps:
            return "已完结"
        else:
            return "连载中"

    def _get_status_color(self, status: str) -> str:
        """获取状态颜色"""
        colors = {
            "即将开播": "#9f7aea",  # 紫色
            "连载中": "#48bb78",  # 绿色
            "已完结": "#4299e1",  # 蓝色
        }
        return colors.get(status, "#718096")


# 全局生成器实例
_global_generator: Optional[PosterGenerator] = None


def get_global_poster_generator(plugin_instance=None) -> PosterGenerator:
    """获取全局海报生成器实例"""
    global _global_generator
    if _global_generator is None:
        from .cache import get_global_poster_cache

        cache = get_global_poster_cache()
        _global_generator = PosterGenerator(cache, plugin_instance)
    return _global_generator


def set_poster_generator_plugin_instance(plugin_instance) -> None:
    """设置海报生成器的插件实例"""
    global _global_generator
    if _global_generator:
        _global_generator.plugin_instance = plugin_instance
    else:
        from .cache import get_global_poster_cache

        cache = get_global_poster_cache()
        _global_generator = PosterGenerator(cache, plugin_instance)
