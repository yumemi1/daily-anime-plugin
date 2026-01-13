"""
全局黑名单管理器
提供统一的番剧过滤功能，支持多种过滤策略
"""

from typing import Dict, List, Any, Tuple, Optional
import copy
from src.common.logger import get_logger

logger = get_logger("anime_blacklist_manager")


class AnimeBlacklistManager:
    """动漫黑名单管理器"""

    def __init__(self, plugin_instance=None):
        self.plugin_instance = plugin_instance
        self.blacklist_config = self._load_blacklist_config()

    def _load_blacklist_config(self) -> Dict[str, Any]:
        """从插件配置加载黑名单设置"""
        try:
            if self.plugin_instance and hasattr(self.plugin_instance, "get_config"):
                config = self.plugin_instance.get_config("filter", {})
                if config:
                    logger.info("从插件配置加载黑名单设置")
                    return config
        except Exception as e:
            logger.warning(f"从插件配置加载黑名单失败，使用默认配置: {e}")

        return self._get_default_blacklist_config()

    def _get_default_blacklist_config(self) -> Dict[str, Any]:
        """获取默认黑名单配置"""
        return {
            "enabled": True,
            "chinese_anime_filter": {"enabled": True, "description": "默认过滤掉中国大陆制作的动画"},
            "keyword_blacklist": {
                "enabled": True,
                "keywords": ["试看集", "PV", "预告", "OP", "ED", "CM", "番外", "OVA", "OAD"],
                "description": "过滤包含特定关键词的内容",
            },
            "studio_blacklist": {"enabled": False, "studios": [], "description": "黑名单制作公司"},
            "custom_blacklist": {"enabled": False, "titles": [], "description": "自定义黑名单番剧标题"},
        }

    def _is_chinese_anime(self, anime: Dict[str, Any]) -> bool:
        """判断是否为中国大陆制作的动画"""
        try:
            # 检查制作公司
            info = anime.get("info", [])
            if isinstance(info, list):
                for item in info:
                    if isinstance(item, dict):
                        key = item.get("key", "")
                        value = item.get("value", "")
                        if key in ["制作", "动画制作", "制作公司"] and self._contains_chinese_company(value):
                            return True

            # 检查简体中文标题优先级（通常国漫会有中文标题）
            name_cn = anime.get("name_cn", "")
            name = anime.get("name", "")
            if name_cn and not name:
                return True

            # 检查地区标记
            if anime.get("platform") or anime.get("region") == "中国大陆":
                return True

        except Exception as e:
            logger.warning(f"判断国漫时出错: {e}")

        return False

    def _contains_chinese_company(self, company_str: str) -> bool:
        """检查是否包含中国动画制作公司关键词"""
        chinese_companies = [
            "腾讯",
            "哔哩哔哩",
            "爱奇艺",
            "优酷",
            "芒果TV",
            "搜狐视频",
            "乐视",
            "若鸿",
            "索以",
            "炎龙",
            "原力",
            "追光",
            "十月数码",
            "米粒",
            "绘梦",
            "绘梦动画",
            "绘梦者",
            "福煦",
            "福煦影视",
            "绘界",
            "绘界文化",
            "澜映",
            "澜映动画",
            "震雷",
            "震雷动画",
            "彩色铅笔",
            "彩色铅笔动漫",
            "大火鸟",
            "大火鸟文化",
            "娃娃鱼",
            "娃娃鱼动画",
            "铁风筝",
            "铁风筝动画",
        ]
        return any(company in company_str for company in chinese_companies)

    def is_blacklisted(self, anime: Dict[str, Any]) -> Tuple[bool, str]:
        """检查番剧是否在黑名单中"""
        if not self.blacklist_config.get("enabled", False):
            return False, ""

        title = anime.get("name", "")
        title_cn = anime.get("name_cn", "")

        # 国漫过滤
        if self.blacklist_config.get("chinese_anime_filter", {}).get("enabled", True) and self._is_chinese_anime(anime):
            return True, "中国动画过滤"

        # 关键词过滤
        keyword_config = self.blacklist_config.get("keyword_blacklist", {})
        if keyword_config.get("enabled", True):
            keywords = keyword_config.get("keywords", [])
            for keyword in keywords:
                if keyword in title or keyword in title_cn:
                    return True, f"关键词过滤: {keyword}"

        # 制作公司过滤
        studio_config = self.blacklist_config.get("studio_blacklist", {})
        if studio_config.get("enabled", False):
            info = anime.get("info", [])
            studios = studio_config.get("studios", [])
            if isinstance(info, list):
                for item in info:
                    if isinstance(item, dict):
                        value = item.get("value", "")
                        if any(studio in value for studio in studios):
                            return True, f"制作公司过滤: {value}"

        # 自定义标题过滤
        custom_config = self.blacklist_config.get("custom_blacklist", {})
        if custom_config.get("enabled", False):
            blacklisted_titles = custom_config.get("titles", [])
            for blacklisted_title in blacklisted_titles:
                if blacklisted_title.lower() in title.lower() or blacklisted_title.lower() in title_cn.lower():
                    return True, f"自定义黑名单: {blacklisted_title}"

        return False, ""

    def filter_anime_list(self, anime_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤番剧列表"""
        if not self.blacklist_config.get("enabled", False):
            return anime_list

        filtered_list = []
        filtered_count = 0

        for anime in anime_list:
            is_blacklisted, reason = self.is_blacklisted(anime)
            if not is_blacklisted:
                filtered_list.append(anime)
            else:
                filtered_count += 1
                title = anime.get("name", anime.get("name_cn", "未知"))
                logger.info(f"过滤番剧: {title} - {reason}")

        logger.info(f"番剧过滤完成: 原始{len(anime_list)}个，过滤掉{filtered_count}个，保留{len(filtered_list)}个")
        return filtered_list

    def get_config(self) -> Dict[str, Any]:
        """获取当前黑名单配置"""
        return copy.deepcopy(self.blacklist_config)

    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """更新黑名单配置"""
        try:
            if not self.plugin_instance or not hasattr(self.plugin_instance, "set_config"):
                logger.error("插件实例不可用，无法更新配置")
                return False

            # 更新插件配置
            self.plugin_instance.set_config("filter", new_config)

            # 重新加载配置
            self.blacklist_config = self._load_blacklist_config()

            logger.info("黑名单配置更新成功")
            return True

        except Exception as e:
            logger.error(f"更新黑名单配置失败: {e}")
            return False

    def add_to_blacklist(self, title: str, list_type: str = "custom") -> bool:
        """添加番剧到黑名单"""
        try:
            if list_type == "custom":
                current_titles = self.blacklist_config["custom_blacklist"]["titles"]
                if title not in current_titles:
                    current_titles.append(title)
                    return self.update_config(self.blacklist_config)
            return False
        except Exception as e:
            logger.error(f"添加到黑名单失败: {e}")
            return False

    def remove_from_blacklist(self, title: str, list_type: str = "custom") -> bool:
        """从黑名单中移除番剧"""
        try:
            if list_type == "custom":
                current_titles = self.blacklist_config["custom_blacklist"]["titles"]
                if title in current_titles:
                    current_titles.remove(title)
                    return self.update_config(self.blacklist_config)
            return False
        except Exception as e:
            logger.error(f"从黑名单移除失败: {e}")
            return False

    def reload_config(self) -> None:
        """重新加载配置"""
        self.blacklist_config = self._load_blacklist_config()
        logger.info("黑名单配置已重新加载")


# 全局黑名单管理器实例
_global_blacklist_manager: Optional[AnimeBlacklistManager] = None


def get_global_blacklist_manager() -> Optional[AnimeBlacklistManager]:
    """获取全局黑名单管理器实例"""
    return _global_blacklist_manager


def set_global_blacklist_manager(manager: AnimeBlacklistManager) -> None:
    """设置全局黑名单管理器实例"""
    global _global_blacklist_manager
    _global_blacklist_manager = manager
    logger.info("全局黑名单管理器已设置")


def init_global_blacklist_manager(plugin_instance=None) -> AnimeBlacklistManager:
    """初始化全局黑名单管理器"""
    manager = AnimeBlacklistManager(plugin_instance)
    set_global_blacklist_manager(manager)
    return manager
