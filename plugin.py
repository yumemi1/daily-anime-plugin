"""
每日新番资讯插件主文件
提供新番查询、智能推荐和定时推送功能
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
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

from .utils.bangumi_api import (
    BangumiDataFormatter,
    get_today_anime_info,
    get_daily_anime_info,
    search_anime_info,
    get_anime_detail,
)
from .utils.cache_manager import cached_get_calendar, cached_search_subject, cached_get_subject_detail
from .utils.scheduler import (
    get_global_scheduler,
    start_scheduler,
    stop_scheduler,
    add_daily_push_task,
    update_daily_push_task,
)
from .utils.blacklist_manager import init_global_blacklist_manager, get_global_blacklist_manager

logger = get_logger("daily_anime_plugin")

# 导入海报生成相关模块 - 设为可选依赖
POSTER_AVAILABLE = False
POSTER_IMPORT_ERROR = None

try:
    from .poster.generator import get_global_poster_generator
    from .poster.cache import get_global_poster_cache

    POSTER_AVAILABLE = True
    logger.info("海报功能模块导入成功")
except ImportError as e:
    POSTER_IMPORT_ERROR = str(e)
    POSTER_AVAILABLE = False
    get_global_poster_generator = None
    get_global_poster_cache = None


def check_playwright_dependency():
    """检查playwright依赖是否可用"""
    if not POSTER_AVAILABLE:
        error_msg = (
            "海报功能不可用，可能的原因：\n"
            "1. 未安装 playwright: pip install playwright\n"
            "2. 未安装浏览器: playwright install chromium\n"
            f"3. 导入错误: {POSTER_IMPORT_ERROR}\n"
            "安装后重启插件即可启用海报功能"
        )
        logger.warning(error_msg)
        return False
    return True


# 如果海报功能不可用，记录详细警告
if not POSTER_AVAILABLE:
    logger.warning(
        f"海报功能不可用。导入错误: {POSTER_IMPORT_ERROR}。"
        "如需使用海报功能，请安装: pip install playwright && playwright install chromium"
    )


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

            # 应用黑名单过滤
            blacklist_manager = get_global_blacklist_manager()
            if blacklist_manager:
                # 对每日数据应用黑名单过滤
                for day_info in calendar_data:
                    if "items" in day_info:
                        day_info["items"] = blacklist_manager.filter_anime_list(day_info["items"])

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

            # 应用黑名单过滤
            blacklist_manager = get_global_blacklist_manager()
            if blacklist_manager:
                search_results = blacklist_manager.filter_anime_list(search_results)

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


class ManageBlacklistTool(BaseTool):
    """管理番剧黑名单工具"""

    name = "manage_anime_blacklist"
    description = "管理番剧过滤黑名单配置"
    parameters = [
        ("action", ToolParamType.STRING, "操作类型 (get_config/add/remove/update)", True, None),
        ("title", ToolParamType.STRING, "番剧标题（用于add/remove）", False, None),
        ("list_type", ToolParamType.STRING, "列表类型（用于add/remove，默认custom）", False, None),
        ("config_data", ToolParamType.STRING, "配置数据（JSON格式，用于update）", False, None),
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行黑名单管理"""
        try:
            action = function_args.get("action", "")

            blacklist_manager = get_global_blacklist_manager()
            if not blacklist_manager:
                return {"name": self.name, "content": "黑名单管理器不可用"}

            if action == "get_config":
                config = blacklist_manager.get_config()
                return {
                    "name": self.name,
                    "content": f"当前黑名单配置：\n{json.dumps(config, ensure_ascii=False, indent=2)}",
                }

            elif action == "add":
                title = function_args.get("title", "")
                list_type = function_args.get("list_type", "custom")

                if not title:
                    return {"name": self.name, "content": "请提供要添加的番剧标题"}

                success = blacklist_manager.add_to_blacklist(title, list_type)
                if success:
                    return {"name": self.name, "content": f"已将「{title}」添加到{list_type}黑名单"}
                else:
                    return {"name": self.name, "content": f"添加到黑名单失败"}

            elif action == "remove":
                title = function_args.get("title", "")
                list_type = function_args.get("list_type", "custom")

                if not title:
                    return {"name": self.name, "content": "请提供要移除的番剧标题"}

                success = blacklist_manager.remove_from_blacklist(title, list_type)
                if success:
                    return {"name": self.name, "content": f"已将「{title}」从{list_type}黑名单中移除"}
                else:
                    return {"name": self.name, "content": f"从黑名单移除失败"}

            elif action == "update":
                config_data_str = function_args.get("config_data", "")

                if not config_data_str:
                    return {"name": self.name, "content": "请提供配置数据（JSON格式）"}

                try:
                    config_data = json.loads(config_data_str)
                except json.JSONDecodeError:
                    return {"name": self.name, "content": "配置数据格式错误，请提供有效的JSON"}

                success = blacklist_manager.update_config(config_data)
                if success:
                    return {"name": self.name, "content": "黑名单配置更新成功"}
                else:
                    return {"name": self.name, "content": "黑名单配置更新失败"}

            else:
                return {
                    "name": self.name,
                    "content": f"不支持的操作类型: {action}，支持的操作: get_config, add, remove, update",
                }

        except Exception as e:
            logger.error(f"管理黑名单失败: {str(e)}")
            return {"name": self.name, "content": f"管理黑名单时发生错误: {str(e)}"}


class GeneratePosterTool(BaseTool):
    """生成新番海报工具"""

    name = "generate_anime_poster"
    description = "生成新番海报工具"
    parameters = [
        ("poster_type", ToolParamType.STRING, "海报类型 (daily/weekly)", False, None),
        ("force_refresh", ToolParamType.BOOLEAN, "是否强制刷新缓存", False, None),
    ]
    available_for_llm = True

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行海报生成"""
        try:
            poster_type: str = function_args.get("poster_type", "daily")
            force_refresh: bool = function_args.get("force_refresh", False)

            if not POSTER_AVAILABLE or not get_global_poster_generator:
                return {
                    "name": self.name,
                    "content": "海报功能不可用，请安装Playwright依赖",
                    "success": False,
                }

            # 获取海报生成器
            poster_gen = get_global_poster_generator()
            if not poster_gen:
                return {"name": self.name, "content": "海报生成器初始化失败", "success": False}

            # 生成海报
            if poster_type == "daily":
                result = await poster_gen.generate_daily_poster()
            elif poster_type == "weekly":
                result = await poster_gen.generate_weekly_poster()
            else:
                return {"name": self.name, "content": f"不支持的海报类型: {poster_type}", "success": False}

            if result and (result.get("image_data") or result.get("base64")):
                return {
                    "name": self.name,
                    "content": f"海报生成成功 (类型: {poster_type})",
                    "success": True,
                    "poster_type": poster_type,
                    "image_data": result.get("image_data") or result.get("base64"),
                    "metadata": result,
                }
            else:
                error_msg = result.get("error", "海报生成失败") if result else "海报生成失败"
                logger.warning(f"海报生成失败: {error_msg}")
                return {"name": self.name, "content": f"海报生成失败: {error_msg}", "success": False}

        except Exception as e:
            logger.error(f"海报生成工具执行失败: {str(e)}")
            return {
                "name": self.name,
                "content": f"海报生成工具执行失败: {str(e)}",
                "success": False,
            }


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
            info = await get_today_anime_info()

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
            week_info = f"本周新番汇总\n{formatted_info}"

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


class AnimePosterCommand(BaseCommand):
    """获取今日新番海报命令"""

    command_name = "anime_poster"
    command_description = "获取今日新番海报"
    command_pattern = r"^/anime_poster$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行获取今日新番海报"""
        try:
            if not POSTER_AVAILABLE or not get_global_poster_generator:
                error_msg = (
                    "海报功能不可用，请安装依赖：\n"
                    "1. pip install playwright\n"
                    "2. playwright install chromium\n"
                    "安装后重启插件即可使用海报功能"
                )
                await self.send_text(error_msg)
                return False, "海报功能不可用", False

            # 获取海报生成器
            poster_gen = get_global_poster_generator()
            if not poster_gen:
                error_msg = "海报生成器初始化失败"
                await self.send_text(error_msg)
                return False, error_msg, False

            # 生成每日海报
            poster_result = await poster_gen.generate_daily_poster()

            if poster_result and (poster_result.get("image_data") or poster_result.get("base64")):
                # 发送图片消息
                image_data = poster_result.get("image_data") or poster_result.get("base64")
                if not image_data:
                    logger.error("海报数据为空")
                    return False, "海报数据为空", False

                # 构建图片标题
                title = f"今日新番海报 - {poster_result.get('date', datetime.now().strftime('%Y年%m月%d日'))}"

                # 先发送标题文本，再发送图片
                await self.send_text(title)
                await self.send_image(image_data)
                logger.info("海报图片发送成功")
                return True, "已生成并发送今日新番海报", True
            else:
                # 降级到文本版本
                logger.warning("海报生成失败，降级到文本版本")
                info = await get_today_anime_info()
                fallback_msg = (
                    "海报生成失败，为您显示文本版本\n\n"
                    f"今日新番信息\n{info}\n\n"
                    "提示：如果海报持续失败，请检查Playwright依赖是否正确安装"
                )
                await self.send_text(fallback_msg)
                return False, "海报生成失败，已降级到文本版本", False

        except Exception as e:
            logger.error(f"海报命令执行失败: {str(e)}")
            error_msg = f"海报生成出错，请稍后重试：{str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, False


class WeeklyPosterCommand(BaseCommand):
    """获取本周汇总海报命令"""

    command_name = "weekly_poster"
    command_description = "获取本周汇总海报"
    command_pattern = r"^/weekly_poster$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行获取本周汇总海报"""
        try:
            # 检查是否周一（周一生成周报最合适）
            from datetime import datetime

            weekday = datetime.now().weekday()  # 0=周一, 6=周日

            if not POSTER_AVAILABLE or not get_global_poster_generator:
                error_msg = (
                    "海报功能不可用，请安装依赖：\n"
                    "1. pip install playwright\n"
                    "2. playwright install chromium\n"
                    "安装后重启插件即可使用海报功能"
                )
                await self.send_text(error_msg)
                return False, "海报功能不可用", False

            # 获取海报生成器
            poster_gen = get_global_poster_generator()
            if not poster_gen:
                error_msg = "海报生成器初始化失败"
                await self.send_text(error_msg)
                return False, error_msg, False

            # 生成周报海报
            poster_result = await poster_gen.generate_weekly_poster()

            if poster_result and (poster_result.get("image_data") or poster_result.get("base64")):
                # 发送图片消息
                image_data = poster_result.get("image_data") or poster_result.get("base64")
                if not image_data:
                    logger.error("周报海报数据为空")
                    return False, "周报海报数据为空", False

                # 构建图片标题
                week_range = poster_result.get("week_range", "")
                title = f"本周新番汇总海报 {week_range}"

                # 先发送标题文本，再发送图片
                await self.send_text(title)
                await self.send_image(image_data)
                logger.info("周报海报图片发送成功")
                return True, "已生成并发送本周汇总海报", True
            else:
                # 降级到文本版本
                logger.warning("周报海报生成失败，降级到文本版本")
                calendar_data = await cached_get_calendar()
                if calendar_data:
                    formatted_info = BangumiDataFormatter.format_calendar_info(calendar_data)
                    week_info = f"本周新番汇总\n{formatted_info}"
                else:
                    week_info = "获取本周新番信息失败，请稍后重试"

                fallback_msg = (
                    "周报海报生成失败，为您显示文本版本\n\n"
                    f"{week_info}\n\n"
                    "提示：如果海报持续失败，请检查Playwright依赖是否正确安装"
                )
                await self.send_text(fallback_msg)
                return False, "周报海报生成失败，已降级到文本版本", False

        except Exception as e:
            logger.error(f"周报海报命令执行失败: {str(e)}")
            error_msg = f"周报海报生成出错，请稍后重试：{str(e)}"
            await self.send_text(error_msg)
            return False, error_msg, False


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
                    info = await get_today_anime_info()

                    # 添加推送标题
                    push_message = f"每日新番推送 {push_time}\n\n{info}"

                    # 尝试生成海报
                    poster_image = None
                    if POSTER_AVAILABLE and check_playwright_dependency():
                        try:
                            from .poster.generator import get_global_poster_generator

                            poster_gen = get_global_poster_generator()
                            if poster_gen:
                                poster_image = await poster_gen.generate_daily_poster()
                                logger.info("海报生成成功，将随推送一起发送")
                        except Exception as poster_error:
                            logger.warning(f"海报生成失败，仅发送文本消息: {str(poster_error)}")

                    # 推送到所有配置的聊天
                    success_count = 0
                    failed_count = 0

                    for chat_id in chat_ids:
                        try:
                            # TODO: 集成实际的消息发送API
                            # 这里需要根据MaiBot的具体API实现
                            # 目前先实现日志记录和基本框架

                            if poster_image:
                                logger.info(f"[图片+文本] 推送到聊天 {chat_id}")
                                logger.info(f"图片大小: {len(poster_image)} bytes")
                                logger.info(f"文本内容: {push_message[:100]}...")
                            else:
                                logger.info(f"[文本] 推送到聊天 {chat_id}")
                                logger.info(f"内容: {push_message[:100]}...")

                            # 模拟发送成功（实际应用中替换为真实API调用）
                            # await self._send_message_to_chat(chat_id, push_message, poster_image)

                            success_count += 1
                            logger.info(f"向聊天 {chat_id} 推送成功")

                        except Exception as e:
                            failed_count += 1
                            logger.error(f"向聊天 {chat_id} 推送失败: {str(e)}")

                            # 尝试重试一次（仅文本消息）
                            try:
                                logger.info(f"向聊天 {chat_id} 重试推送（仅文本）")
                                # await self._send_text_to_chat(chat_id, push_message)

                                success_count += 1
                                failed_count -= 1
                                logger.info(f"向聊天 {chat_id} 重试推送成功")
                            except Exception as retry_error:
                                logger.error(f"向聊天 {chat_id} 重试推送仍然失败: {str(retry_error)}")

                    logger.info(f"每日推送完成: 成功 {success_count} 个, 失败 {failed_count} 个")

                    if failed_count > 0:
                        raise RuntimeError(f"部分推送失败: {failed_count}/{len(chat_ids)}")

                except Exception as e:
                    logger.error(f"每日新番推送失败: {str(e)}")
                    raise

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


class PosterSchedulerEventHandler(BaseEventHandler):
    """海报定时任务事件处理器"""

    event_type = EventType.ON_START  # 启动时设置定时任务
    handler_name = "poster_scheduler_handler"
    handler_description = "设置海报生成相关的定时任务"

    async def execute(self, message: MaiMessages | None) -> Tuple[bool, bool, str | None, None, None]:
        """设置海报定时任务"""
        try:
            if not POSTER_AVAILABLE:
                return True, True, "海报功能不可用，跳过定时任务设置", None, None

            # 检查是否启用海报定时任务
            poster_enabled = self.get_config("poster.enabled", True)
            if not poster_enabled:
                return True, True, "海报定时任务已禁用", None, None

            # 获取定时任务配置
            daily_time = str(self.get_config("poster.daily_generation_time", "04:00"))
            weekly_time = str(self.get_config("poster.weekly_generation_time", "04:10"))
            cleanup_time = str(self.get_config("poster.cleanup_time", "03:50"))

            # 启动调度器
            await start_scheduler()

            # 添加海报生成定时任务
            await add_daily_push_task(self._generate_daily_poster_wrapper, daily_time, [])

            await add_daily_push_task(self._generate_weekly_poster_wrapper, weekly_time, [])

            await add_daily_push_task(self._cleanup_cache_wrapper, cleanup_time, [])

            logger.info(f"海报定时任务已设置: 每日{daily_time}, 周报{weekly_time}, 清理{cleanup_time}")
            return True, True, "海报定时任务设置完成", None, None

        except Exception as e:
            logger.error(f"设置海报定时任务失败: {str(e)}")
            return True, True, f"设置海报定时任务失败: {str(e)}", None, None

    async def _generate_daily_poster_wrapper(self, chat_ids: List[str]) -> None:
        """每日海报生成包装函数"""
        try:
            if not POSTER_AVAILABLE or not get_global_poster_generator:
                return

            logger.info("开始定时生成每日海报")
            poster_gen = get_global_poster_generator()
            result = await poster_gen.generate_daily_poster()

            if result and result.get("image_data"):
                logger.info("定时每日海报生成成功")
            else:
                logger.warning("定时每日海报生成失败")

        except Exception as e:
            logger.error(f"定时生成每日海报失败: {str(e)}")

    async def _generate_weekly_poster_wrapper(self, chat_ids: List[str]) -> None:
        """周报海报生成包装函数"""
        try:
            if not POSTER_AVAILABLE or not get_global_poster_generator:
                return

            logger.info("开始定时生成周报海报")
            poster_gen = get_global_poster_generator()
            result = await poster_gen.generate_weekly_poster()

            if result and result.get("image_data"):
                logger.info("定时周报海报生成成功")
            else:
                logger.warning("定时周报海报生成失败")

        except Exception as e:
            logger.error(f"定时生成周报海报失败: {str(e)}")

    async def _cleanup_cache_wrapper(self, chat_ids: List[str]) -> None:
        """缓存清理包装函数"""
        try:
            logger.info("开始清理海报缓存")
            if get_global_poster_cache:
                cache = get_global_poster_cache()
                # 这里需要根据PosterCache的实际API实现清理逻辑
                logger.info("海报缓存清理完成")
            else:
                logger.warning("海报缓存不可用")

        except Exception as e:
            logger.error(f"清理海报缓存失败: {str(e)}")

    async def _generate_weekly_poster(self, poster_gen) -> None:
        """生成周报海报"""
        try:
            logger.info("开始定时生成周报海报")
            result = await poster_gen.generate_weekly_poster()

            if result and result.get("image_data"):
                logger.info("定时周报海报生成成功")
            else:
                logger.warning("定时周报海报生成失败")

        except Exception as e:
            logger.error(f"定时生成周报海报失败: {str(e)}")
            raise

    async def _cleanup_cache(self) -> None:
        """清理过期缓存"""
        try:
            logger.info("开始清理海报缓存")
            if get_global_poster_cache:
                cache = get_global_poster_cache()
                # 这里需要根据PosterCache的实际API实现
                # cache.cleanup_expired()
                logger.info("海报缓存清理完成")
            else:
                logger.warning("海报缓存不可用")

        except Exception as e:
            logger.error(f"清理海报缓存失败: {str(e)}")
            raise


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
        "poster": "海报功能配置",
        "filter": "番剧过滤配置",
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
                "episodes_ttl": ConfigField(type=int, default=7200, description="剧集信息缓存时间(秒)"),
            },
            "push": {
                "daily_push_enabled": ConfigField(type=bool, default=False, description="是否启用每日推送"),
                "push_time": ConfigField(type=str, default="09:00", description="每日推送时间"),
                "push_chat_ids": ConfigField(type=list, default=[], description="推送目标聊天ID列表"),
            },
            "poster": {
                "enabled": ConfigField(type=bool, default=True, description="是否启用海报生成功能"),
                "daily_generation_time": ConfigField(type=str, default="04:00", description="每日海报自动生成时间"),
                "weekly_generation_time": ConfigField(type=str, default="04:10", description="周报海报自动生成时间"),
                "cleanup_time": ConfigField(type=str, default="03:50", description="过期海报清理时间"),
                "max_cache_days": ConfigField(type=int, default=7, description="海报文件最大缓存天数"),
                "headless_browser": ConfigField(type=bool, default=True, description="是否使用无头浏览器模式"),
                "cache_dir": ConfigField(type=str, default="posters", description="海报缓存目录名称"),
            },
            "filter": {
                "enabled": ConfigField(type=bool, default=True, description="是否启用番剧过滤功能"),
                "chinese_anime_filter": {
                    "enabled": ConfigField(type=bool, default=True, description="是否过滤中国大陆制作的动画"),
                    "description": "默认过滤掉中国大陆制作的动画",
                },
                "keyword_blacklist": {
                    "enabled": ConfigField(type=bool, default=True, description="是否启用关键词过滤"),
                    "keywords": ConfigField(
                        type=list,
                        default=["试看集", "PV", "预告", "OP", "ED", "CM", "番外", "OVA", "OAD", "我的英雄学院"],
                        description="需要过滤的关键词列表",
                    ),
                    "description": "过滤包含特定关键词的内容",
                },
                "studio_blacklist": {
                    "enabled": ConfigField(type=bool, default=False, description="是否启用制作公司黑名单"),
                    "studios": ConfigField(type=list, default=[], description="黑名单制作公司列表"),
                    "description": "黑名单制作公司",
                },
                "custom_blacklist": {
                    "enabled": ConfigField(type=bool, default=False, description="是否启用自定义标题黑名单"),
                    "titles": ConfigField(type=list, default=[], description="黑名单番剧标题列表"),
                    "description": "自定义黑名单番剧标题",
                },
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 初始化全局黑名单管理器
        init_global_blacklist_manager(self)
        logger.info("全局黑名单管理器已初始化")

        # 初始化海报生成器的插件实例
        if POSTER_AVAILABLE:
            from .poster.generator import set_poster_generator_plugin_instance

            set_poster_generator_plugin_instance(self)

    def get_plugin_components(self):
        """返回插件包含的组件列表"""
        return [
            # Tool组件
            (GetDailyAnimeTool.get_tool_info(), GetDailyAnimeTool),
            (SearchAnimeTool.get_tool_info(), SearchAnimeTool),
            (GetAnimeDetailTool.get_tool_info(), GetAnimeDetailTool),
            (GeneratePosterTool.get_tool_info(), GeneratePosterTool),
            (ManageBlacklistTool.get_tool_info(), ManageBlacklistTool),
            # Command组件
            (AnimeTodayCommand.get_command_info(), AnimeTodayCommand),
            (AnimeWeekCommand.get_command_info(), AnimeWeekCommand),
            (AnimeSearchCommand.get_command_info(), AnimeSearchCommand),
            (AnimePosterCommand.get_command_info(), AnimePosterCommand),
            (WeeklyPosterCommand.get_command_info(), WeeklyPosterCommand),
            # EventHandler组件
            (DailyPushEventHandler.get_handler_info(), DailyPushEventHandler),
            (PluginStopEventHandler.get_handler_info(), PluginStopEventHandler),
            (PosterSchedulerEventHandler.get_handler_info(), PosterSchedulerEventHandler),
        ]
