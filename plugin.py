"""
每日新番资讯插件主文件
提供新番查询、智能推荐和定时推送功能
"""

from __future__ import annotations

import asyncio
from typing import List, Tuple, Type, Any, Optional
from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseCommand,
    BaseTool,
    ComponentInfo,
    ActionActivationType,
    ConfigField,
    BaseEventHandler,
    EventType,
    MaiMessages,
    ToolParamType,
    ReplyContentType,
)
from src.plugin_system.base.component_types import PythonDependency
from src.common.logger import get_logger

from .utils.bangumi_api import BangumiDataFormatter, get_daily_anime_info, search_anime_info, get_anime_detail
from .utils.cache_manager import cached_get_calendar, cached_search_subject, cached_get_subject_detail
from .utils.scheduler import (
    get_global_scheduler,
    start_scheduler,
    stop_scheduler,
    add_daily_push_task,
    update_daily_push_task,
)

logger = get_logger("daily_anime_plugin")


# ===== Tool组件 =====


class GetDailyAnimeTool(BaseTool):
    """获取每日新番数据工具"""

    name = "get_daily_anime"
    description = "获取每日新番更新信息，包括今日和本周的放送日程"
    parameters = []
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行获取每日新番数据"""
        try:
            # 使用缓存获取数据
            calendar_data = await cached_get_calendar()
            if calendar_data is None:
                return {"name": self.name, "content": "获取每日新番信息失败，请稍后重试"}

            # 格式化数据
            formatted_info = BangumiDataFormatter.format_calendar_info(calendar_data)

            return {"name": self.name, "content": formatted_info}
        except Exception as e:
            logger.error(f"获取每日新番数据失败: {str(e)}")
            return {"name": self.name, "content": f"获取每日新番数据时发生错误: {str(e)}"}


class SearchAnimeTool(BaseTool):
    """搜索番剧信息工具"""

    name = "search_anime"
    description = "根据关键词搜索番剧信息"
    parameters = [
        ("keyword", ToolParamType.STRING, "搜索关键词", True, None),
        ("limit", ToolParamType.INTEGER, "返回结果数量限制", False, None),
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行搜索番剧信息"""
        try:
            keyword: str = function_args.get("keyword", "")
            limit: int = function_args.get("limit", 10)

            if not keyword:
                return {"name": self.name, "content": "请提供搜索关键词"}

            # 使用缓存搜索
            search_results = await cached_search_subject(keyword, type_filter="anime", limit=limit)
            if search_results is None:
                return {"name": self.name, "content": "搜索番剧信息失败，请稍后重试"}

            # 格式化搜索结果
            formatted_results = BangumiDataFormatter.format_search_results(search_results, keyword)

            return {"name": self.name, "content": formatted_results}
        except Exception as e:
            logger.error(f"搜索番剧信息失败: {str(e)}")
            return {"name": self.name, "content": f"搜索番剧信息时发生错误: {str(e)}"}


class GetAnimeDetailTool(BaseTool):
    """获取番剧详情工具"""

    name = "get_anime_detail"
    description = "根据番剧ID获取详细信息"
    parameters = [
        ("subject_id", ToolParamType.INTEGER, "番剧ID", True, None),
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行获取番剧详情"""
        try:
            subject_id: int = function_args.get("subject_id", 0)

            if subject_id <= 0:
                return {"name": self.name, "content": "请提供有效的番剧ID"}

            # 使用缓存获取详情
            detail_data = await cached_get_subject_detail(subject_id)
            if detail_data is None:
                return {"name": self.name, "content": f"获取番剧详情失败，ID: {subject_id}"}

            # 格式化详情信息
            formatted_detail = BangumiDataFormatter.format_subject_detail(detail_data)

            return {"name": self.name, "content": formatted_detail}
        except Exception as e:
            logger.error(f"获取番剧详情失败: {str(e)}")
            return {"name": self.name, "content": f"获取番剧详情时发生错误: {str(e)}"}


# ===== Command组件 =====


class AnimeTodayCommand(BaseCommand):
    """查询今日新番命令"""

    command_name = "anime_today"
    command_description = "查询今日新番更新信息"
    command_pattern = r"^/anime_today$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行查询今日新番"""
        try:
            # 获取今日新番信息
            info = await get_daily_anime_info()

            # 发送消息
            await self.send_text(info)

            return True, "已获取今日新番信息", True
        except Exception as e:
            logger.error(f"查询今日新番失败: {str(e)}")
            error_msg = f"查询今日新番失败: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, False


class AnimeWeekCommand(BaseCommand):
    """查询本周新番命令"""

    command_name = "anime_week"
    command_description = "查询本周新番更新汇总"
    command_pattern = r"^/anime_week$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行查询本周新番"""
        try:
            # 获取每日放送日程
            calendar_data = await cached_get_calendar()
            if calendar_data is None:
                error_msg = "获取本周新番信息失败，请稍后重试"
                await self.send_text(error_msg)
                return False, error_msg, False

            # 格式化本周信息
            formatted_info = BangumiDataFormatter.format_calendar_info(calendar_data)

            # 添加本周汇总标题
            week_info = f"📺 本周新番汇总\n{formatted_info}"

            # 发送消息
            await self.send_text(week_info)

            return True, "已获取本周新番汇总", True
        except Exception as e:
            logger.error(f"查询本周新番失败: {str(e)}")
            error_msg = f"查询本周新番失败: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, False


class AnimeSearchCommand(BaseCommand):
    """搜索番剧命令"""

    command_name = "anime_search"
    command_description = "搜索特定番剧信息"
    command_pattern = r"^/anime_search\s+(.+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行搜索番剧"""
        try:
            # 从命令中提取关键词
            import re

            match = re.match(self.command_pattern, self.message.processed_plain_text or "")
            if not match:
                error_msg = "命令格式错误，请使用: /anime_search <关键词>"
                await self.send_text(error_msg)
                return False, error_msg, False

            keyword = match.group(1).strip()
            if not keyword:
                error_msg = "请提供搜索关键词"
                await self.send_text(error_msg)
                return False, error_msg, False

            # 搜索番剧
            search_results = await cached_search_subject(keyword, type_filter="anime", limit=10)
            if search_results is None:
                error_msg = "搜索番剧信息失败，请稍后重试"
                await self.send_text(error_msg)
                return False, error_msg, False

            # 格式化搜索结果
            formatted_results = BangumiDataFormatter.format_search_results(search_results, keyword)

            # 发送消息
            await self.send_text(formatted_results)

            return True, f"已搜索番剧: {keyword}", True
        except Exception as e:
            logger.error(f"搜索番剧失败: {str(e)}")
            error_msg = f"搜索番剧失败: {str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, False


# ===== Action组件 =====


class AnimeInfoAction(BaseAction):
    """智能响应新番相关询问"""

    action_name = "anime_info_response"
    action_description = "智能响应用户的新番相关询问"
    activation_type = ActionActivationType.ALWAYS

    action_parameters = {"user_question": "用户关于新番的问题", "context": "对话上下文信息"}
    action_require = [
        "用户询问新番、动漫、番剧相关信息时使用",
        "用户想了解今日或本周新番更新时使用",
        "用户搜索特定番剧信息时使用",
        "用户询问番剧详情时使用",
    ]
    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        """执行智能响应新番询问"""
        try:
            user_question = self.action_data.get("user_question", "")
            context = self.action_data.get("context", "")

            # 分析用户意图
            question_lower = user_question.lower()

            if any(keyword in question_lower for keyword in ["今天", "今日", "daily"]):
                # 获取今日新番
                info = await get_daily_anime_info()
                await self.send_text(info)
                return True, "响应了今日新番询问"

            elif any(keyword in question_lower for keyword in ["本周", "week", "星期"]):
                # 获取本周新番
                calendar_data = await cached_get_calendar()
                if calendar_data:
                    formatted_info = BangumiDataFormatter.format_calendar_info(calendar_data)
                    week_info = f"📺 本周新番汇总\n{formatted_info}"
                    await self.send_text(week_info)
                    return True, "响应了本周新番询问"
                else:
                    await self.send_text("获取本周新番信息失败，请稍后重试")
                    return False, "获取本周新番信息失败"

            elif any(keyword in question_lower for keyword in ["搜索", "search", "找"]):
                # 尝试提取搜索关键词
                import re

                # 简单的关键词提取
                keyword_match = re.search(r'["""](.+?)["""]|搜索\s*(.+?)$|找\s*(.+?)$', user_question)
                keyword = None
                if keyword_match:
                    keyword = keyword_match.group(1) or keyword_match.group(2) or keyword_match.group(3)
                    keyword = keyword.strip()

                if keyword:
                    # 搜索番剧
                    search_results = await cached_search_subject(keyword, type_filter="anime", limit=5)
                    if search_results:
                        formatted_results = BangumiDataFormatter.format_search_results(search_results, keyword)
                        await self.send_text(formatted_results)
                        return True, f"搜索了番剧: {keyword}"
                    else:
                        await self.send_text(f"未找到与「{keyword}」相关的番剧")
                        return True, f"未找到番剧: {keyword}"
                else:
                    await self.send_text("请告诉我您想搜索哪部番剧")
                    return True, "请求搜索关键词"

            else:
                # 通用新番信息响应
                info = await get_daily_anime_info()
                await self.send_text(f"关于新番信息，我为您整理了以下内容：\n\n{info}")
                return True, "响应了通用新番询问"

        except Exception as e:
            logger.error(f"智能响应新番询问失败: {str(e)}")
            error_msg = f"处理您的新番询问时发生错误: {str(e)}"
            await self.send_text(error_msg)
            return False, f"响应失败: {str(e)}"


# ===== EventHandler组件 =====


class DailyPushEventHandler(BaseEventHandler):
    """每日新番推送事件处理器"""

    event_type = EventType.ON_START  # 系统启动时触发
    handler_name = "daily_push_handler"
    handler_description = "设置每日新番定时推送任务"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.push_task = None

    async def execute(self, message: MaiMessages | None) -> Tuple[bool, bool, str | None, None, None]:
        """执行每日推送任务设置"""
        try:
            # 检查是否启用每日推送
            daily_push_enabled = self.get_config("push.daily_push_enabled", False)
            if not daily_push_enabled:
                return True, True, "每日推送功能已禁用", None, None

            # 获取推送配置
            push_time = str(self.get_config("push.push_time", "09:00"))
            push_chat_ids_config = self.get_config("push.push_chat_ids", [])
            push_chat_ids = list(push_chat_ids_config) if push_chat_ids_config is not None else []

            if not push_chat_ids:
                return True, True, "未配置推送目标聊天", None, None

            # 创建推送函数
            async def daily_anime_push(chat_ids: List[str]):
                """每日新番推送函数"""
                try:
                    # 获取今日新番信息
                    info = await get_daily_anime_info()

                    # 添加推送标题
                    push_message = f"🎌 每日新番推送 {push_time}\n\n{info}"

                    # 推送到所有配置的聊天
                    for chat_id in chat_ids:
                        try:
                            # 这里需要根据实际平台发送消息
                            # 暂时使用日志记录
                            logger.info(f"向聊天 {chat_id} 推送每日新番信息")
                            # await self.send_text_to_chat(chat_id, push_message)
                        except Exception as e:
                            logger.error(f"向聊天 {chat_id} 推送失败: {str(e)}")

                except Exception as e:
                    logger.error(f"每日新番推送失败: {str(e)}")

            # 启动调度器
            await start_scheduler()

            # 添加每日推送任务
            await add_daily_push_task(daily_anime_push, push_time, push_chat_ids)

            logger.info(f"每日新番推送任务已设置: {push_time}, 推送到 {len(push_chat_ids)} 个聊天")
            return True, True, f"每日推送任务已设置: {push_time}", None, None

        except Exception as e:
            logger.error(f"设置每日推送任务失败: {str(e)}")
            return True, True, f"设置每日推送任务失败: {str(e)}", None, None


class PluginStopEventHandler(BaseEventHandler):
    """插件停止事件处理器"""

    event_type = EventType.ON_STOP  # 系统停止时触发
    handler_name = "plugin_stop_handler"
    handler_description = "清理定时任务和资源"

    async def execute(self, message: MaiMessages | None) -> Tuple[bool, bool, str | None, None, None]:
        """执行插件停止清理"""
        try:
            # 停止调度器
            await stop_scheduler()

            logger.info("每日新番插件已停止，定时任务已清理")
            return True, True, "插件停止清理完成", None, None

        except Exception as e:
            logger.error(f"插件停止清理失败: {str(e)}")
            return True, True, f"插件停止清理失败: {str(e)}", None, None


# ===== 插件注册 =====


@register_plugin
class DailyAnimePlugin(BasePlugin):
    """每日新番资讯插件"""

    # 插件基本信息 - 使用类属性
    plugin_name: str = "daily_anime_plugin"  # type: ignore
    enable_plugin: bool = True  # type: ignore
    dependencies: List[str] = []  # type: ignore
    python_dependencies: List[str] = ["aiohttp", "pydantic"]  # type: ignore
    config_file_name: str = "config.toml"  # type: ignore

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本信息",
        "api": "Bangumi API配置",
        "cache": "缓存配置",
        "push": "推送配置",
    }

    @property
    def config_schema(self) -> dict:
        return {
            "plugin": {
                "config_version": ConfigField(type=str, default="1.0.0", description="配置文件版本"),
                "enabled": ConfigField(type=bool, default=False, description="是否启用插件"),
            },
            "api": {
                "base_url": ConfigField(type=str, default="https://api.bgm.tv", description="Bangumi API基础URL"),
                "timeout": ConfigField(type=int, default=30, description="API请求超时时间(秒)"),
                "rate_limit_delay": ConfigField(type=float, default=1.0, description="API请求间隔延迟(秒)"),
            },
            "cache": {
                "default_ttl": ConfigField(type=int, default=1800, description="默认缓存过期时间(秒)"),
                "max_size": ConfigField(type=int, default=500, description="最大缓存项数"),
                "calendar_ttl": ConfigField(type=int, default=1800, description="每日放送日程缓存时间(秒)"),
                "search_ttl": ConfigField(type=int, default=3600, description="搜索结果缓存时间(秒)"),
                "detail_ttl": ConfigField(type=int, default=3600, description="番剧详情缓存时间(秒)"),
            },
            "push": {
                "daily_push_enabled": ConfigField(type=bool, default=False, description="是否启用每日推送"),
                "push_time": ConfigField(type=str, default="09:00", description="每日推送时间"),
                "push_chat_ids": ConfigField(type=list, default=[], description="推送目标聊天ID列表"),
            },
        }

    def get_plugin_components(self):
        """返回插件包含的组件列表"""
        return [
            # Tool组件
            (GetDailyAnimeTool.get_tool_info(), GetDailyAnimeTool),
            (SearchAnimeTool.get_tool_info(), SearchAnimeTool),
            (GetAnimeDetailTool.get_tool_info(), GetAnimeDetailTool),
            # Command组件
            (AnimeTodayCommand.get_command_info(), AnimeTodayCommand),
            (AnimeWeekCommand.get_command_info(), AnimeWeekCommand),
            (AnimeSearchCommand.get_command_info(), AnimeSearchCommand),
            # Action组件
            (AnimeInfoAction.get_action_info(), AnimeInfoAction),
            # EventHandler组件
            (DailyPushEventHandler.get_handler_info(), DailyPushEventHandler),
            (PluginStopEventHandler.get_handler_info(), PluginStopEventHandler),
        ]
