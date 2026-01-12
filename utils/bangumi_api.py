"""
Bangumi API客户端封装
提供Bangumi API的异步访问接口
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json


class BangumiAPIClient:
    """Bangumi API客户端"""

    def __init__(self, base_url: str = "https://api.bgm.tv", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit_delay = 1.0  # API限流延迟(秒)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={
                "User-Agent": "yumemi1/MaiBot-DailyAnimePlugin/1.0.0 (https://github.com/yumemi1/daily-anime-plugin)",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求"""
        if not self.session:
            raise RuntimeError("APIClient must be used as async context manager")

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            # API限流控制
            await asyncio.sleep(self.rate_limit_delay)

            async with self.session.request(method, url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    # API限流，增加延迟时间
                    self.rate_limit_delay = min(self.rate_limit_delay * 2, 10.0)
                    await asyncio.sleep(self.rate_limit_delay)
                    raise RuntimeError("API rate limit exceeded, retrying...")
                elif response.status >= 400:
                    error_text = await response.text()
                    raise RuntimeError(f"API request failed: {response.status} - {error_text}")
                else:
                    raise RuntimeError(f"Unexpected response status: {response.status}")

        except aiohttp.ClientError as e:
            raise RuntimeError(f"Network error: {str(e)}")
        except asyncio.TimeoutError:
            raise RuntimeError("Request timeout")

    async def get_calendar(self) -> List[Dict[str, Any]]:
        """获取每日放送日程"""
        try:
            data = await self._request("GET", "/calendar")
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"获取每日放送日程失败: {str(e)}")
            return []

    async def search_subject(
        self, keyword: str, type_filter: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索条目

        Args:
            keyword: 搜索关键词
            type_filter: 类型过滤 (anime, book, music, game, real)
            limit: 返回结果数量限制

        Returns:
            搜索结果列表
        """
        # 类型映射：字符串到整数
        type_mapping = {"book": 1, "anime": 2, "music": 3, "game": 4, "real": 6}

        # 构建请求体
        json_data: Dict[str, Any] = {"keyword": keyword}

        # 添加类型过滤器
        if type_filter:
            type_int = type_mapping.get(type_filter.lower())
            if type_int:
                json_data["filter"] = {"type": [type_int]}

        try:
            # 使用 POST 请求调用新的搜索 API
            data = await self._request("POST", "/v0/search/subjects", params={"limit": limit}, json=json_data)
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            print(f"搜索条目失败: {str(e)}")
            return []

    async def get_subject_detail(self, subject_id: int) -> Optional[Dict[str, Any]]:
        """获取条目详情

        Args:
            subject_id: 条目ID

        Returns:
            条目详情数据
        """
        try:
            data = await self._request("GET", f"/v0/subjects/{subject_id}")
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"获取条目详情失败: {str(e)}")
            return None

    async def get_subject_episodes(self, subject_id: int, episode_type: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取条目剧集列表

        Args:
            subject_id: 条目ID
            episode_type: 剧集类型 (0=本篇, 1=SP, 2=OP, 3=ED)

        Returns:
            剧集列表
        """
        params = {}
        if episode_type is not None:
            params["type"] = episode_type

        try:
            data = await self._request("GET", f"/v0/subjects/{subject_id}/episodes", params=params)
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            print(f"获取剧集列表失败: {str(e)}")
            return []

    async def get_user_collection(
        self, user_id: str, subject_type: int = 2, collection_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户收藏列表

        Args:
            user_id: 用户ID或用户名
            subject_type: 条目类型 (2=动画)
            collection_type: 收藏类型 (wish, doing, collected, on_hold, dropped)

        Returns:
            收藏列表
        """
        params: Dict[str, Any] = {"subject_type": subject_type}
        if collection_type:
            params["type"] = collection_type  # type: ignore

        try:
            data = await self._request("GET", f"/v0/users/{user_id}/collections", params=params)
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            print(f"获取用户收藏失败: {str(e)}")
            return []


class BangumiDataFormatter:
    """Bangumi数据格式化器"""

    @staticmethod
    def format_calendar_info(calendar_data: List[Dict[str, Any]]) -> str:
        """格式化每日放送日程信息"""
        if not calendar_data:
            return "暂无放送日程信息"

        weekday_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        today = datetime.now().weekday()

        result = []
        result.append("📺 每日放送日程\n")

        for day_info in calendar_data:
            weekday = day_info.get("weekday", {}).get("id", 0)
            weekday_name = weekday_names[weekday] if weekday < 7 else "未知"

            # 标记今天
            if weekday == today:
                weekday_name = f"🌟 {weekday_name} (今天)"

            items = day_info.get("items", [])
            if items:
                result.append(f"\n【{weekday_name}】")
                for item in items[:5]:  # 每天最多显示5个
                    name = item.get("name", "未知番剧")
                    name_cn = item.get("name_cn", "")
                    display_name = name_cn if name_cn else name

                    air_time = item.get("air_time", "")
                    if air_time:
                        result.append(f"  🕐 {air_time} {display_name}")
                    else:
                        result.append(f"  📺 {display_name}")

                if len(items) > 5:
                    result.append(f"  ... 还有{len(items) - 5}部番剧")

        return "\n".join(result)

    @staticmethod
    def format_search_results(results: List[Dict[str, Any]], keyword: str) -> str:
        """格式化搜索结果"""
        if not results:
            return f"未找到与「{keyword}」相关的番剧"

        result = []
        result.append(f"🔍 搜索「{keyword}」的结果 (共{len(results)}个):\n")

        for item in results[:10]:  # 最多显示10个结果
            subject_id = item.get("id", 0)
            name = item.get("name", "未知")
            name_cn = item.get("name_cn", "")
            display_name = name_cn if name_cn else name

            summary = item.get("summary", "")
            summary = (summary[:50] + "...") if len(summary) > 50 else summary

            score = item.get("rating", {}).get("score", 0)
            score_str = f"⭐ {score:.1f}" if score > 0 else "⭐ 暂无评分"

            result.append(f"📺 {display_name} (ID: {subject_id})")
            result.append(f"   {score_str}")
            if summary:
                result.append(f"   📝 {summary}")
            result.append("")

        return "\n".join(result)

    @staticmethod
    def format_subject_detail(detail: Optional[Dict[str, Any]]) -> str:
        """格式化条目详情"""
        if not detail:
            return "获取番剧详情失败"

        name = detail.get("name", "未知")
        name_cn = detail.get("name_cn", "")
        display_name = name_cn if name_cn else name

        summary = detail.get("summary", "暂无简介")
        eps = detail.get("eps", 0)
        eps_count = detail.get("eps_count", 0)

        # 评分信息
        rating = detail.get("rating", {})
        score = rating.get("score", 0)
        total = rating.get("total", 0)
        score_str = f"⭐ {score:.1f} ({total}人评分)" if score > 0 else "⭐ 暂无评分"

        # 放送信息
        air_date = detail.get("date", "未知")
        air_weekday = detail.get("air_weekday", 0)
        weekday_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        air_weekday_str = weekday_names[air_weekday] if 0 <= air_weekday < 7 else ""

        # 类型标签
        type_str = detail.get("type", "未知")

        result = []
        result.append(f"📺 {display_name}")
        result.append(f"🏷️ {type_str}")
        result.append(f"📊 {score_str}")

        if air_date:
            air_info = f"📅 {air_date}"
            if air_weekday_str:
                air_info += f" ({air_weekday_str})"
            result.append(air_info)

        if eps_count > 0:
            result.append(f"🎬 共{eps_count}集")
            if eps > 0:
                result.append(f"📺 已更新至{eps}集")

        result.append(f"\n📝 简介:\n{summary}")

        return "\n".join(result)


# 便捷函数
async def get_daily_anime_info() -> str:
    """获取每日新番信息的便捷函数"""
    async with BangumiAPIClient() as client:
        calendar_data = await client.get_calendar()
        return BangumiDataFormatter.format_calendar_info(calendar_data)


async def search_anime_info(keyword: str, limit: int = 10) -> str:
    """搜索番剧信息的便捷函数"""
    async with BangumiAPIClient() as client:
        results = await client.search_subject(keyword, type_filter="anime", limit=limit)
        return BangumiDataFormatter.format_search_results(results, keyword)


async def get_anime_detail(subject_id: int) -> str:
    """获取番剧详情的便捷函数"""
    async with BangumiAPIClient() as client:
        detail = await client.get_subject_detail(subject_id)
        if detail is None:
            return "获取番剧详情失败"
        return BangumiDataFormatter.format_subject_detail(detail)
