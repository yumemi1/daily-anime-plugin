"""
海报生成器
整合数据获取、模板渲染和缓存管理
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, date, timedelta

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

            # 使用周报模板
            async with PosterRenderer() as renderer:
                image_bytes = await renderer.render_poster(template_data, "weekly.html")

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
        today = datetime.now().weekday()  # 0=周一, 1=周二, ..., 6=周日
        today_name = datetime.now().strftime("%Y年%m月%d日")

        logger.info(
            f"准备今日(Python weekday={today} = {['周一', '周二', '周三', '周四', '周五', '周六', '周日'][today]})的新番数据"
        )

        # 找到今天的番剧
        today_animes = []
        logger.info(f"查找今日(weekday={today})的番剧，共{len(calendar_data)}天的数据")

        for i, day_info in enumerate(calendar_data):
            weekday_info = day_info.get("weekday", {})
            day_id = weekday_info.get("id")
            day_name = weekday_info.get("cn", weekday_info.get("en", "未知"))
            items_count = len(day_info.get("items", []))

            logger.info(f"第{i}天: id={day_id}, 名称={day_name}, 番剧数={items_count}")

            # 修复Python weekday(0-6)与Bangumi weekday(1-7)的映射
            bangumi_weekday = today + 1
            if day_id == bangumi_weekday:
                today_animes = day_info.get("items", [])
                logger.info(f"找到今日番剧(Bangumi weekday={bangumi_weekday}): {len(today_animes)}部")
                break

        if not today_animes:
            # 没有今日番剧
            logger.warning(f"今日({today})没有找到番剧数据")
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

            # 生成未展示番剧的文字列表
            hidden_animes_list = []
            for anime in sorted_animes[5:]:  # 获取第6位及以后的番剧
                title = anime.get("name_cn") or anime.get("name", "未知番剧")
                # 只添加评分信息，不显示集数
                rating = anime.get("rating", {}).get("score", 0)
                rating_text = f" {rating:.1f}分" if rating > 0 else " 暂无评分"
                hidden_animes_list.append(f"* {title}{rating_text}")

            hidden_animes_text = "\n".join(hidden_animes_list) if hidden_animes_list else ""
            hidden_count = max(0, len(sorted_animes) - 5)  # 未展示的番剧数量
        else:
            other_animes = []
            hidden_animes_text = ""
            hidden_count = 0

        return {
            "date": today_name,
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "hidden_animes": hidden_animes_text,
            "hidden_count": hidden_count,
            "total_count": len(sorted_animes),
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    async def _prepare_weekly_data(self, calendar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """准备周报海报数据"""
        today = datetime.now()

        # 计算本周的开始和结束日期
        days_since_monday = today.weekday()  # 0=周一, 6=周日
        week_start = today - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)

        week_name = f"{week_start.strftime('%Y年第%W周')}"
        week_start_str = week_start.strftime("%m月%d日")
        week_end_str = week_end.strftime("%m月%d日")

        # 收集每日数据和所有番剧
        daily_summary = []
        all_animes = []
        highlights = []

        # 一周7天的中文名称
        week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        for i, day_info in enumerate(calendar_data):
            if i >= 7:  # 只处理一周7天的数据
                break

            weekday_info = day_info.get("weekday", {})
            day_id = weekday_info.get("id", 0)

            # 获取当天的番剧
            items = day_info.get("items", [])
            filtered_items = self.filter_anime_list(items)

            # 每日汇总数据
            day_name = week_days[i] if i < 7 else f"第{i + 1}天"
            main_animes = []
            if filtered_items:
                # 按评分排序，取前3部番剧
                sorted_day_animes = sorted(
                    filtered_items, key=lambda x: x.get("rating", {}).get("score", 0), reverse=True
                )
                for anime in sorted_day_animes[:3]:  # 每天最多显示3部
                    title = anime.get("name_cn") or anime.get("name", "未知番剧")
                    rating = anime.get("rating", {}).get("score", 0)
                    if rating > 0:
                        main_animes.append(f"{title} ({rating:.1f}分)")
                    else:
                        main_animes.append(title)

            # 将多部番剧用换行符连接，或者如果没有番剧则显示空字符串
            main_text = "\n".join(main_animes) if main_animes else ""

            daily_summary.append({"day": day_name, "count": len(filtered_items), "main": main_text})

            # 收集所有番剧
            all_animes.extend(filtered_items)

            # 收集亮点（高评分番剧）
            for anime in filtered_items:
                rating = anime.get("rating", {}).get("score", 0)
                if rating >= 8.0:  # 评分8分以上
                    title = anime.get("name_cn") or anime.get("name", "未知番剧")
                    cover_url = await self._get_anime_cover_url(anime)
                    highlights.append(
                        {
                            "title": title,
                            "rating": rating,
                            "cover_url": cover_url,
                            "display_text": f"{title} ({rating:.1f}分)",
                        }
                    )

        # 应用过滤规则到所有番剧
        filtered_animes = self.filter_anime_list(all_animes)

        # 去重并按热度排序，取前8个
        seen_ids = set()
        unique_animes = []
        for anime in filtered_animes:
            anime_id = anime.get("id")
            if anime_id and anime_id not in seen_ids:
                unique_animes.append(anime)
                seen_ids.add(anime_id)

        sorted_animes = sorted(unique_animes, key=self.calculate_popularity_score, reverse=True)
        top_animes = sorted_animes[:8]

        # 生成更多亮点（热门番剧）
        if not highlights and top_animes:
            for anime in top_animes[:3]:
                rating = anime.get("rating", {}).get("score", 0)
                title = anime.get("name_cn") or anime.get("name", "未知番剧")
                cover_url = await self._get_anime_cover_url(anime)

                if rating > 0:
                    highlights.append(
                        {
                            "title": title,
                            "rating": rating,
                            "cover_url": cover_url,
                            "display_text": f"{title} ({rating:.1f}分)",
                        }
                    )
                else:
                    highlights.append({"title": title, "rating": 0, "cover_url": cover_url, "display_text": title})

        if not top_animes:
            return {
                "week_start": week_start_str,
                "week_end": week_end_str,
                "anime_count": 0,
                "date": week_name,
                "has_animes": False,
                "main_anime": None,
                "other_animes": [],
                "daily_summary": daily_summary,
                "highlights": highlights,
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        # 格式化数据
        main_anime = await self._format_anime_for_template(top_animes[0])
        # 为每周海报添加时间字段
        main_anime["time"] = "本周更新"  # 简化的时间显示

        other_animes_tasks = [self._format_anime_for_template(anime) for anime in top_animes[1:8]]
        other_animes = await asyncio.gather(*other_animes_tasks)

        # 生成未展示番剧的文字列表
        hidden_animes_list = []
        for anime in top_animes[8:]:  # 获取第9位及以后的番剧
            title = anime.get("name_cn") or anime.get("name", "未知番剧")
            rating = anime.get("rating", {}).get("score", 0)
            rating_text = f" {rating:.1f}分" if rating > 0 else " 暂无评分"
            hidden_animes_list.append(f"* {title}{rating_text}")

        hidden_animes_text = "\n".join(hidden_animes_list) if hidden_animes_list else ""
        hidden_count = max(0, len(top_animes) - 8)  # 未展示的番剧数量

        return {
            "week_start": week_start_str,
            "week_end": week_end_str,
            "anime_count": len(filtered_animes),
            "date": week_name + " 汇总",
            "has_animes": True,
            "main_anime": main_anime,
            "other_animes": other_animes,
            "hidden_animes": hidden_animes_text,
            "hidden_count": hidden_count,
            "total_count": len(top_animes),
            "daily_summary": daily_summary,
            "highlights": highlights[:5],  # 最多显示5个亮点
            "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    async def get_episode_info(self, subject_id: int) -> Dict[str, Any]:
        """获取剧集信息 - 简化版本（不显示集数）"""
        # 返回默认的空剧集信息
        return self._get_default_episode_info()

    async def _get_subject_detail_data(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """获取番剧基础数据"""
        try:
            async with BangumiAPIClient() as client:
                subject_detail = await client.get_subject_detail(subject_id)
                if subject_detail:
                    # 标准化字段名称
                    return {
                        "id": subject_detail.get("id", subject_id),
                        "name": subject_detail.get("name", ""),
                        "name_cn": subject_detail.get("name_cn", ""),
                        "eps": subject_detail.get("eps", 0),
                        "eps_count": subject_detail.get("eps_count", 0),
                        "date": subject_detail.get("date", ""),
                        "air_date": subject_detail.get("air_date", ""),
                        "status": subject_detail.get("status", ""),
                        "type": subject_detail.get("type", ""),
                        "infobox": subject_detail.get("infobox", []),
                    }
        except Exception as e:
            logger.debug(f"获取番剧基础数据失败: {subject_id} -> {e}")

        return None

    async def _get_episodes_data(self, subject_id: int) -> Optional[List[Dict[str, Any]]]:
        """获取剧集列表数据"""
        try:
            async with BangumiAPIClient() as client:
                episodes = await client.get_subject_episodes(subject_id, episode_type=0)
                return episodes if episodes else None
        except Exception as e:
            logger.debug(f"获取剧集列表失败: {subject_id} -> {e}")

        return None

    def _convert_episode_info_to_dict(self, episode_info) -> Dict[str, Any]:
        """将EpisodeInfo对象转换为字典格式"""
        if not episode_info:
            return self._get_default_episode_info()

        # 使用验证后的数据
        eps = episode_info.eps
        total_episodes = episode_info.eps_count

        # 格式化最新集数显示
        latest_episode = f"第{eps}话" if eps > 0 else "第1话"

        # 格式化总集数显示
        total_eps_str = str(total_episodes) if total_episodes > 0 else "?"

        # 格式化进度显示
        episode_progress = f"{eps}/{total_eps_str}" if total_episodes > 0 else f"{eps}/?"

        # 判断更新状态
        update_status = self._determine_update_status(eps, total_episodes, episode_info.air_date)

        result = {
            "latest_episode": latest_episode,
            "total_episodes": total_eps_str,
            "episode_progress": episode_progress,
            "update_status": update_status,
        }

        # 添加验证信息到日志
        if episode_info.validation_strategy:
            logger.info(f"剧集验证完成: {episode_info.name} - 策略: {episode_info.validation_strategy.value}")
        if episode_info.contradiction_type:
            logger.info(
                f"检测到矛盾: {episode_info.contradiction_type}, API: {episode_info.eps}, 计算: {episode_info.calculated_eps}"
            )

        return result

    async def _process_original_episode_data(
        self, subject_detail: Dict[str, Any], episodes_data: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """处理原始API数据（降级方案）"""
        # 从基础数据提取信息
        eps = subject_detail.get("eps", 0)
        total_episodes = subject_detail.get("eps_count", 0)
        air_date = subject_detail.get("date", "") or subject_detail.get("air_date", "")

        # 如果没有总集数，尝试从infobox提取
        if total_episodes == 0:
            total_episodes = self._extract_episodes_from_infobox(subject_detail.get("infobox", []))

        # 如果有剧集数据，尝试从中提取更准确的信息
        if episodes_data:
            try:
                latest_ep = self._get_latest_episode(episodes_data)
                total_from_eps = self._get_total_episodes(episodes_data)

                # 优先使用剧集列表的数据
                if latest_ep and latest_ep != "第1话":
                    eps_match = "".join(filter(str.isdigit, latest_ep))
                    if eps_match:
                        eps = int(eps_match)

                if total_from_eps != "?":
                    total_episodes = int(total_from_eps)
            except Exception as e:
                logger.debug(f"处理剧集列表数据失败: {e}")

        return self._format_episode_data(eps, total_episodes, air_date)

    async def _get_episode_info_from_detail(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """从条目详情获取剧集信息"""
        try:
            async with BangumiAPIClient() as client:
                subject_detail = await client.get_subject_detail(subject_id)
                if subject_detail:
                    # 提取基本信息
                    eps = subject_detail.get("eps", 0)  # 已更新集数
                    total_episodes = subject_detail.get("total_episodes", 0)  # 总集数

                    # 如果没有总集数信息，尝试从infobox中提取
                    if total_episodes == 0:
                        total_episodes = self._extract_episodes_from_infobox(subject_detail.get("infobox", []))

                    # 获取播出日期用于状态判断
                    air_date = subject_detail.get("air_date", "")

                    # 格式化和验证数据
                    result = self._format_episode_data(eps, total_episodes, air_date)
                    logger.debug(f"从条目详情获取剧集信息成功: {subject_id} -> {result}")
                    return result

        except Exception as e:
            logger.debug(f"从条目详情获取剧集信息失败: {subject_id} -> {e}")

        return None

    async def _get_episode_info_from_episodes(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """从剧集详情获取剧集信息"""
        try:
            async with BangumiAPIClient() as client:
                episodes = await client.get_subject_episodes(subject_id, episode_type=0)
                if episodes:
                    # 解析最新集数和总集数
                    latest_episode = self._get_latest_episode(episodes)
                    total_episodes = self._get_total_episodes(episodes)
                    update_status = self._get_update_status(episodes)

                    result = {
                        "latest_episode": latest_episode,
                        "total_episodes": total_episodes,
                        "episode_progress": self._format_episode_progress(latest_episode, total_episodes),
                        "update_status": update_status,
                    }
                    logger.debug(f"从剧集详情获取信息成功: {subject_id} -> {result}")
                    return result

        except Exception as e:
            logger.debug(f"从剧集详情获取信息失败: {subject_id} -> {e}")

        return None

    def _format_episode_data(self, eps: int, total_episodes: int, air_date: str = "") -> Dict[str, Any]:
        """格式化剧集数据"""
        # 验证和修正数据
        eps = max(0, int(eps)) if isinstance(eps, (int, str)) and str(eps).isdigit() else 0
        total_episodes = (
            max(0, int(total_episodes))
            if isinstance(total_episodes, (int, str)) and str(total_episodes).isdigit()
            else 0
        )

        # 格式化最新集数显示
        latest_episode = f"第{eps}话" if eps > 0 else "第1话"

        # 格式化总集数显示
        total_eps_str = str(total_episodes) if total_episodes > 0 else "?"

        # 格式化进度显示
        episode_progress = f"{eps}/{total_eps_str}" if total_episodes > 0 else f"{eps}/?"

        # 判断更新状态
        update_status = self._determine_update_status(eps, total_episodes, air_date)

        return {
            "latest_episode": latest_episode,
            "total_episodes": total_eps_str,
            "episode_progress": episode_progress,
            "update_status": update_status,
        }

    def _format_episode_progress(self, latest_episode: str, total_episodes: str) -> str:
        """格式化剧集进度显示"""
        try:
            # 提取数字
            latest_num = 1
            if latest_episode and latest_episode.startswith("第"):
                latest_num = int("".join(filter(str.isdigit, latest_episode))) or 1

            total_num = total_episodes if total_episodes != "?" else "?"

            return f"{latest_num}/{total_num}"
        except Exception:
            return "?/?"

    def _determine_update_status(self, eps: int, total_episodes: int, air_date: str = "") -> str:
        """判断更新状态"""
        if eps == 0:
            if air_date:
                return "即将开播"
            else:
                return "未开播"
        elif total_episodes > 0:
            progress_ratio = eps / total_episodes
            if progress_ratio >= 1.0:
                return "已完结"
            elif progress_ratio >= 0.8:
                return "接近完结"
            else:
                return "连载中"
        else:
            return "连载中"

    async def _get_anime_cover_url(self, anime: Dict[str, Any]) -> str:
        """获取番剧封面URL"""
        title = anime.get("name_cn") or anime.get("name", "未知番剧")

        try:
            images = anime.get("images", {})
            logger.debug(f"番剧 {title} 图片数据: {images}")

            if isinstance(images, dict):
                # 优先使用中等质量的图片
                cover_url = images.get("medium") or images.get("large") or images.get("common", "")
                logger.debug(f"番剧 {title} 初始封面URL: {cover_url}")

                # 验证URL可访问性
                if cover_url and not cover_url.startswith("https://via.placeholder"):
                    validated_url = await self._validate_and_get_final_url(cover_url, title)
                    logger.debug(f"番剧 {title} 验证后URL: {validated_url}")
                    cover_url = validated_url

                if not cover_url:
                    # 生成占位图片
                    cover_url = self.get_fallback_cover_url(title)
                    logger.debug(f"番剧 {title} 使用占位图片: {cover_url}")

                return cover_url
        except Exception as e:
            logger.warning(f"获取封面URL失败: {title} -> {e}")

        # 生成默认占位图片
        cover_url = self.get_fallback_cover_url(title)
        logger.debug(f"番剧 {title} 使用默认占位图片: {cover_url}")
        return cover_url

    def _get_default_episode_info(self) -> Dict[str, Any]:
        """获取默认剧集信息"""
        return {
            "latest_episode": "第1话",
            "total_episodes": "?",
            "episode_progress": "?/?",
            "update_status": "即将开播",
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

        # 封面图片 - 增强的重定向处理和重试机制
        cover_url = ""
        try:
            images = anime.get("images", {})
            logger.debug(f"番剧 {title} 图片数据: {images}")

            if isinstance(images, dict):
                # 优先使用大图以获得更好的清晰度
                cover_url = images.get("large") or images.get("medium") or images.get("common", "")

            logger.debug(f"选择的封面URL: {cover_url}")

            # 验证URL可访问性 - 增强版本
            if cover_url and not cover_url.startswith("https://via.placeholder"):
                cover_url = await self._validate_and_get_final_url(cover_url, title)

        except Exception as e:
            logger.warning(f"获取封面图片失败: {e}")

        if not cover_url:
            logger.info(f"使用占位图片: {title}")
            cover_url = self.get_fallback_cover_url(title)

        # 追番人数信息 - 增强版本
        watchers_str = self._format_collection_count(anime)

        # 数据验证和清理
        validated_data = self._validate_and_clean_data(anime, episode_info, title, score_str, watchers_str, cover_url)

        return validated_data

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
        import urllib.parse

        # 限制长度并编码
        display_title = title[:12] if len(title) > 12 else title
        encoded_title = urllib.parse.quote(display_title)

        # 使用多种颜色方案，基于标题哈希选择
        title_hash = abs(hash(title)) % 5
        color_schemes = [
            ("667eea", "764ba2"),  # 紫色渐变
            ("f093fb", "f5576c"),  # 粉色渐变
            ("4facfe", "00f2fe"),  # 蓝色渐变
            ("43e97b", "38f9d7"),  # 绿色渐变
            ("fa709a", "fee140"),  # 橙色渐变
        ]

        bg_color, text_color = color_schemes[title_hash]

        # 生成占位图URL
        return f"https://ui-avatars.com/api/?name={encoded_title}&size=360&background={bg_color}&color={text_color}&font-size=24&length=2&rounded=false"

    async def _validate_and_get_final_url(self, url: str, title: str = "未知番剧") -> str:
        """验证图片URL并处理重定向，支持重试机制"""
        import aiohttp

        max_retries = 3
        retry_delay = 1.0  # seconds

        # 配置请求头，模拟真实浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://bgm.tv/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=10)

                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    # 使用HEAD请求检查，允许重定向
                    async with session.head(
                        url,
                        allow_redirects=True,
                        ssl=False,  # 允许自签名证书
                    ) as response:
                        logger.info(f"[尝试 {attempt + 1}/{max_retries}] 图片 {url[:100]}... 状态: {response.status}")

                        # 记录重定向信息
                        if response.url != url:
                            logger.info(f"重定向: {url} -> {response.url}")

                        if response.status == 200:
                            # 检查响应头是否确实是图片
                            content_type = response.headers.get("content-type", "").lower()
                            if content_type.startswith("image/"):
                                final_url = str(response.url)
                                logger.info(f"图片验证成功: {title} -> {final_url}")
                                return final_url
                            else:
                                logger.warning(f"URL不是图片类型: {content_type}")
                                return ""
                        elif response.status in [301, 302, 303, 307, 308]:
                            # 重定向状态，但HEAD请求可能不完整，尝试GET
                            logger.info(f"检测到重定向状态 {response.status}，尝试GET请求验证")
                            continue
                        else:
                            logger.warning(f"图片访问失败，状态码: {response.status}")
                            return ""

            except asyncio.TimeoutError:
                logger.warning(f"[尝试 {attempt + 1}] 请求超时: {url}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                return ""
            except aiohttp.ClientError as e:
                logger.warning(f"[尝试 {attempt + 1}] 网络错误: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                return ""
            except Exception as e:
                logger.error(f"[尝试 {attempt + 1}] 未知错误: {type(e).__name__}: {e}")
                return ""

        logger.warning(f"所有重试失败，无法访问图片: {url}")
        return ""

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
        """获取播放状态 - 增强版本"""
        try:
            # 优先使用episode_info中的状态信息
            if episode_info and "update_status" in episode_info:
                return episode_info["update_status"]

            # 从anime基本信息判断
            eps = anime.get("eps", 0)
            total_eps = anime.get("total_episodes", 0)
            air_date = anime.get("air_date", "")

            # 验证数据类型
            eps = max(0, int(eps)) if isinstance(eps, (int, str)) and str(eps).isdigit() else 0
            total_eps = max(0, int(total_eps)) if isinstance(total_eps, (int, str)) and str(total_eps).isdigit() else 0

            # 状态判断逻辑
            if eps == 0:
                if air_date:
                    return "即将开播"
                else:
                    return "未开播"
            elif total_eps > 0:
                progress_ratio = eps / total_eps
                if progress_ratio >= 1.0:
                    return "已完结"
                elif progress_ratio >= 0.8:
                    return "接近完结"
                else:
                    return "连载中"
            else:
                return "连载中"

        except Exception as e:
            logger.warning(f"状态判断失败: {e}")
            return "连载中"

    def _get_status_color(self, status: str) -> str:
        """获取状态颜色"""
        colors = {
            "即将开播": "#9f7aea",  # 紫色
            "连载中": "#48bb78",  # 绿色
            "接近完结": "#ed8936",  # 橙色
            "已完结": "#4299e1",  # 蓝色
            "暂停": "#f6ad55",  # 浅橙色
        }
        return colors.get(status, "#718096")

    def _format_collection_count(self, anime: Dict[str, Any]) -> str:
        """格式化追番人数统计"""
        try:
            collection = anime.get("collection", {})
            if not collection:
                return "暂无"

            # 获取所有状态的计数
            wish = collection.get("wish", 0)  # 想看
            doing = collection.get("doing", 0)  # 在看
            collect = collection.get("collect", 0)  # 看过
            on_hold = collection.get("on_hold", 0)  # 搁置
            dropped = collection.get("dropped", 0)  # 抛弃

            # 验证数据完整性
            for key, value in [
                ("wish", wish),
                ("doing", doing),
                ("collect", collect),
                ("on_hold", on_hold),
                ("dropped", dropped),
            ]:
                if not isinstance(value, int) or value < 0:
                    logger.warning(f"追番人数数据异常 {key}: {value}")
                    return "数据异常"

            # 计算活跃追番人数（想看+在看+看过）
            active_watchers = wish + doing + collect
            total_watchers = active_watchers + on_hold + dropped

            # 格式化显示
            if total_watchers == 0:
                return "暂无"
            elif total_watchers < 1000:
                return f"{total_watchers}人追番"
            elif total_watchers < 10000:
                return f"{total_watchers / 1000:.1f}k人追番"
            elif total_watchers < 100000:
                return f"{total_watchers / 10000:.1f}万人追番"
            else:
                return f"{total_watchers / 100000:.1f}十万人追番"

        except Exception as e:
            logger.warning(f"追番人数格式化失败: {e}")
            return "数据异常"

    def _validate_and_clean_data(
        self,
        anime: Dict[str, Any],
        episode_info: Dict[str, Any],
        title: str,
        score_str: str,
        watchers_str: str,
        cover_url: str,
    ) -> Dict[str, Any]:
        """验证和清理数据，确保所有字段完整性"""
        try:
            # 构建最终数据
            result = {
                "title": self._validate_text_field(title, "未知番剧"),
                "score": self._validate_score_field(score_str),
                "watchers": self._validate_text_field(watchers_str, "暂无"),
                "cover_url": self._validate_url_field(cover_url),
            }

            # 最终验证
            self._final_data_validation(result, anime.get("id", "unknown"))

            return result

        except Exception as e:
            logger.error(f"数据验证失败: {e}")
            # 返回安全的默认数据
            return self._get_safe_default_data(title)

    def _validate_text_field(self, value: Any, default: str) -> str:
        """验证文本字段"""
        if value is None:
            return default
        if not isinstance(value, str):
            value = str(value)
        return value.strip() or default

    def _validate_score_field(self, score_str: str) -> str:
        """验证评分字段"""
        if not score_str:
            return "暂无"

        # 确保评分格式正确
        if score_str == "暂无":
            return score_str

        try:
            # 尝试解析为浮点数并重新格式化
            score = float(score_str)
            if score < 0:
                return "0.0"
            elif score > 10:
                return "10.0"
            else:
                return f"{score:.1f}"
        except (ValueError, TypeError):
            return "暂无"

    def _validate_url_field(self, url: str) -> str:
        """验证URL字段"""
        if not url:
            return ""

        if not isinstance(url, str):
            return ""

        url = url.strip()

        # 检查URL格式
        if not (url.startswith("http://") or url.startswith("https://")):
            return ""

        # 检查长度限制
        if len(url) > 1000:  # 防止过长URL
            return ""

        return url

    def _final_data_validation(self, data: Dict[str, Any], anime_id: Any) -> None:
        """最终数据验证"""
        required_fields = ["title", "score", "watchers"]

        for field in required_fields:
            if field not in data or not data[field]:
                logger.warning(f"数据验证失败 - 缺失字段 {field}: anime_id={anime_id}")
                data[field] = self._get_field_default(field)

    def _get_field_default(self, field: str) -> str:
        """获取字段默认值"""
        defaults = {
            "title": "未知番剧",
            "score": "暂无",
            "watchers": "暂无",
        }
        return defaults.get(field, "")

    def _get_safe_default_data(self, title: str = "未知番剧") -> Dict[str, Any]:
        """获取安全的默认数据"""
        return {
            "title": title or "未知番剧",
            "score": "暂无",
            "watchers": "暂无",
            "cover_url": "",
        }


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
