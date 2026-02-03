"""
剧集验证模块
提供API+计算混合验证机制，解决Bangumi API剧集信息语义不准确问题
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import re

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)


logger = get_logger("episode_validator")


class ValidationStrategy(Enum):
    """验证策略枚举"""

    API_ONLY = "api_only"  # 仅使用API数据
    CALCULATION_OVERRIDE = "calculation_override"  # 计算结果覆盖API数据
    HYBRID_TRUST_API = "hybrid_trust_api"  # 混合模式，优先信任API
    HYBRID_TRUST_CALC = "hybrid_trust_calc"  # 混合模式，优先信任计算


@dataclass
class EpisodeInfo:
    """剧集信息数据类"""

    eps: int  # API返回的当前集数
    eps_count: int  # 总集数
    air_date: Optional[str]  # 开播日期
    name: str  # 番剧名称
    name_cn: str  # 中文名称
    subject_id: int  # 条目ID
    status: Optional[str] = None  # API状态

    # 计算得出信息
    calculated_eps: Optional[int] = None  # 计算得出的当前集数
    validation_strategy: Optional[ValidationStrategy] = None  # 使用的验证策略
    contradiction_type: Optional[str] = None  # 检测到的矛盾类型
    confidence_score: float = 0.0  # 置信度分数


@dataclass
class ValidationResult:
    """验证结果数据类"""

    should_validate: bool  # 是否应该进行验证
    trigger_reason: str  # 触发验证的原因
    calculated_eps: Optional[int] = None  # 计算得出的当前集数
    strategy: ValidationStrategy = ValidationStrategy.API_ONLY  # 使用的策略
    contradiction_type: Optional[str] = None  # 矛盾类型
    confidence: float = 0.0  # 置信度
    log_messages: List[str] = None  # 日志信息

    def __post_init__(self):
        if self.log_messages is None:
            self.log_messages = []


class EpisodeValidator:
    """剧集验证器主类"""

    def __init__(self):
        self.validation_enabled = True
        self.strict_mode = True  # 严格模式，更严格的矛盾检测阈值

        # 验证触发条件参数
        self.max_episodes_for_validation = 50  # 最大集数限制
        self.max_age_years = 3  # 最大年份限制
        self.min_weeks_since_premiere = 2  # 开播后最少周数

        # 矛盾检测阈值
        self.contradiction_thresholds = {
            "completion_misjudgment": 0,  # 完结误判阈值
            "progress_lag": 2,  # 进度滞后阈值
            "progress_ahead": 3,  # 进度超前阈值
            "zero_episode_anomaly": self.min_weeks_since_premiere,  # 零值异常阈值
        }

        # 置信度计算权重
        self.confidence_weights = {
            "episodes_complete": 0.4,  # 剧集列表完整性
            "air_date_recent": 0.3,  # 开播日期近期性
            "eps_reasonable": 0.2,  # 集数合理性
            "consistency_check": 0.1,  # 一致性检查
        }

    def should_validate_subject(self, subject_data: Dict[str, Any]) -> ValidationResult:
        """
        判断是否应该对番剧进行验证

        Args:
            subject_data: 从API获取的番剧数据

        Returns:
            ValidationResult: 验证触发条件判断结果
        """
        result = ValidationResult(should_validate=False, trigger_reason="不满足验证条件")

        # 解析基础数据
        eps_count = subject_data.get("eps_count", 0)
        air_date_str = subject_data.get("date", "")
        name = subject_data.get("name", "未知番剧")

        result.log_messages.append(f"开始评估验证条件: {name}")
        result.log_messages.append(f"总集数: {eps_count}, 开播日期: {air_date_str}")

        # 1. 集数限制检查
        if eps_count > self.max_episodes_for_validation:
            result.trigger_reason = f"总集数{eps_count}超过限制{self.max_episodes_for_validation}"
            result.log_messages.append(result.trigger_reason)
            return result

        # 2. 开播日期检查
        air_date = self._parse_date(air_date_str)
        if not air_date:
            result.trigger_reason = "无法解析开播日期"
            result.log_messages.append(result.trigger_reason)
            return result

        age_days = (datetime.now() - air_date).days
        age_years = age_days / 365.25

        if age_years > self.max_age_years:
            result.trigger_reason = f"番剧年代{age_years:.1f}年超过限制{self.max_age_years}年"
            result.log_messages.append(result.trigger_reason)
            return result

        # 3. 数据完整性检查
        if eps_count <= 0:
            result.trigger_reason = "总集数数据无效"
            result.log_messages.append(result.trigger_reason)
            return result

        # 4. 剧场版、OVA等特殊类型排除
        subject_type = subject_data.get("type", "").lower()
        if self._is_special_type(subject_type, subject_data):
            result.trigger_reason = f"特殊类型{subject_type}，排除验证"
            result.log_messages.append(result.trigger_reason)
            return result

        # 5. 计算置信度
        confidence = self._calculate_validation_confidence(subject_data, air_date)
        result.confidence = confidence

        # 通过所有检查，应该进行验证
        result.should_validate = True
        result.trigger_reason = "满足所有验证条件"
        result.log_messages.append(f"验证通过，置信度: {confidence:.2f}")

        return result

    def validate_episode_info(
        self, subject_data: Dict[str, Any], episodes_data: Optional[List[Dict[str, Any]]] = None
    ) -> EpisodeInfo:
        """
        验证剧集信息并返回修正后的数据

        Args:
            subject_data: API获取的番剧基础数据
            episodes_data: API获取的剧集列表数据（可选）

        Returns:
            EpisodeInfo: 验证后的剧集信息
        """
        # 构造基础信息
        eps = subject_data.get("eps", 0)
        eps_count = subject_data.get("eps_count", 0)
        air_date = subject_data.get("date", "")
        name = subject_data.get("name", "未知番剧")
        name_cn = subject_data.get("name_cn", "")
        subject_id = subject_data.get("id", 0)
        status = subject_data.get("status", "")

        episode_info = EpisodeInfo(
            eps=eps,
            eps_count=eps_count,
            air_date=air_date,
            name=name,
            name_cn=name_cn,
            subject_id=subject_id,
            status=status,
        )

        # 检查是否应该验证
        validation_result = self.should_validate_subject(subject_data)
        episode_info.validation_strategy = ValidationStrategy.API_ONLY

        if not validation_result.should_validate:
            logger.info(f"{name} 跳过验证: {validation_result.trigger_reason}")
            return episode_info

        # 执行验证计算
        calculated_eps = self._calculate_episode_count(subject_data, episodes_data)
        episode_info.calculated_eps = calculated_eps

        # 检测矛盾
        contradiction_type = self._detect_contradiction(eps, calculated_eps, subject_data)
        episode_info.contradiction_type = contradiction_type

        # 确定验证策略
        strategy = self._determine_validation_strategy(contradiction_type, validation_result.confidence)
        episode_info.validation_strategy = strategy

        # 根据策略调整最终结果
        if strategy in [ValidationStrategy.CALCULATION_OVERRIDE, ValidationStrategy.HYBRID_TRUST_CALC]:
            episode_info.eps = calculated_eps

        episode_info.confidence_score = validation_result.confidence

        # 记录详细日志
        log_msg = f"{name} 验证完成: API={eps}, 计算={calculated_eps}, 策略={strategy.value}"
        if contradiction_type:
            log_msg += f", 矛盾={contradiction_type}"
        logger.info(log_msg)

        return episode_info

    def _calculate_episode_count(
        self, subject_data: Dict[str, Any], episodes_data: Optional[List[Dict[str, Any]]]
    ) -> int:
        """
        计算当前应该播出的集数

        Args:
            subject_data: 番剧基础数据
            episodes_data: 剧集列表数据

        Returns:
            int: 计算得出的当前集数
        """
        # 方法1: 基于剧集列表的精确计算
        if episodes_data and len(episodes_data) > 0:
            calculated = self._calculate_from_episodes_list(episodes_data)
            if calculated > 0:
                logger.debug(f"使用剧集列表计算结果: {calculated}")
                return calculated

        # 方法2: 基于周更规律的估算计算
        calculated = self._calculate_from_air_date(subject_data)
        logger.debug(f"使用周更规律计算结果: {calculated}")
        return calculated

    def _calculate_from_episodes_list(self, episodes_data: List[Dict[str, Any]]) -> int:
        """
        基于剧集列表精确计算当前集数

        Args:
            episodes_data: 剧集列表数据

        Returns:
            int: 计算得出的当前集数
        """
        today = datetime.now().date()
        aired_count = 0

        for episode in episodes_data:
            # 只计算本篇剧集 (type=0)
            if episode.get("type") != 0:
                continue

            air_date_str = episode.get("airdate", "")
            if not air_date_str:
                continue

            air_date = self._parse_date(air_date_str)
            if air_date and air_date.date() <= today:
                aired_count += 1

        return aired_count

    def _calculate_from_air_date(self, subject_data: Dict[str, Any]) -> int:
        """
        基于开播日期和周更规律估算当前集数

        Args:
            subject_data: 番剧基础数据

        Returns:
            int: 估算的当前集数
        """
        air_date_str = subject_data.get("date", "")
        eps_count = subject_data.get("eps_count", 0)

        air_date = self._parse_date(air_date_str)
        if not air_date or eps_count <= 0:
            return 0

        # 计算开播以来的周数
        today = datetime.now()
        weeks_since_premiere = (today - air_date).days / 7

        # 基本集数计算：每周一集
        estimated_eps = min(int(weeks_since_premiere), eps_count)

        # 考虑一些特殊情况
        # 1. 第一周通常算第1集
        if weeks_since_premiere >= 1:
            estimated_eps = max(estimated_eps, 1)

        # 2. 不超过总集数
        estimated_eps = min(estimated_eps, eps_count)

        return max(0, estimated_eps)

    def _detect_contradiction(self, api_eps: int, calculated_eps: int, subject_data: Dict[str, Any]) -> Optional[str]:
        """
        检测API数据与计算结果之间的矛盾

        Args:
            api_eps: API返回的当前集数
            calculated_eps: 计算得出的当前集数
            subject_data: 番剧基础数据

        Returns:
            Optional[str]: 检测到的矛盾类型，无矛盾则返回None
        """
        if calculated_eps <= 0:
            return None  # 无法有效计算，不判断矛盾

        eps_count = subject_data.get("eps_count", 0)
        air_date = self._parse_date(subject_data.get("date", ""))

        # 0. 零值异常检测（优先级最高）
        if api_eps == 0 and air_date:
            weeks_since_premiere = (datetime.now() - air_date).days / 7
            if weeks_since_premiere > self.contradiction_thresholds["zero_episode_anomaly"]:
                return "zero_episode_anomaly"

        # 1. 完结误判检测
        if api_eps >= eps_count and calculated_eps < eps_count:
            if eps_count - calculated_eps > self.contradiction_thresholds["completion_misjudgment"]:
                return "completion_misjudgment"

        # 2. 进度滞后检测
        if calculated_eps - api_eps > self.contradiction_thresholds["progress_lag"]:
            return "progress_lag"

        # 3. 进度超前检测
        if api_eps - calculated_eps > self.contradiction_thresholds["progress_ahead"]:
            return "progress_ahead"

        return None

    def _determine_validation_strategy(
        self, contradiction_type: Optional[str], confidence: float
    ) -> ValidationStrategy:
        """
        根据矛盾类型和置信度确定验证策略

        Args:
            contradiction_type: 矛盾类型
            confidence: 验证置信度

        Returns:
            ValidationStrategy: 验证策略
        """
        # 无矛盾，信任API
        if not contradiction_type:
            return ValidationStrategy.API_ONLY

        # 根据矛盾类型和置信度选择策略
        if confidence > 0.8:
            # 高置信度，优先计算结果
            return ValidationStrategy.CALCULATION_OVERRIDE
        elif confidence > 0.5:
            # 中等置信度，混合模式但偏向计算
            return ValidationStrategy.HYBRID_TRUST_CALC
        else:
            # 低置信度，混合模式但偏向API
            return ValidationStrategy.HYBRID_TRUST_API

    def _calculate_validation_confidence(self, subject_data: Dict[str, Any], air_date: datetime) -> float:
        """
        计算验证置信度

        Args:
            subject_data: 番剧数据
            air_date: 开播日期

        Returns:
            float: 置信度分数 (0.0-1.0)
        """
        scores = {}

        # 1. 剧集列表完整性 (如果有eps数据则认为完整)
        eps = subject_data.get("eps", 0)
        eps_count = subject_data.get("eps_count", 0)
        if eps > 0 and eps_count > 0:
            scores["episodes_complete"] = 1.0
        else:
            scores["episodes_complete"] = 0.3

        # 2. 开播日期近期性
        age_days = (datetime.now() - air_date).days
        if age_days <= 365:  # 1年内
            scores["air_date_recent"] = 1.0
        elif age_days <= 365 * 2:  # 2年内
            scores["air_date_recent"] = 0.7
        elif age_days <= 365 * 3:  # 3年内
            scores["air_date_recent"] = 0.4
        else:
            scores["air_date_recent"] = 0.1

        # 3. 集数合理性
        if 1 <= eps_count <= 50:
            scores["eps_reasonable"] = 1.0
        elif 51 <= eps_count <= 100:
            scores["eps_reasonable"] = 0.6
        else:
            scores["eps_reasonable"] = 0.2

        # 4. 一致性检查 (eps不超过eps_count)
        if eps <= eps_count:
            scores["consistency_check"] = 1.0
        else:
            scores["consistency_check"] = 0.0

        # 加权计算最终置信度
        confidence = sum(scores[key] * self.confidence_weights[key] for key in self.confidence_weights)

        return min(1.0, max(0.0, confidence))

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        解析日期字符串

        Args:
            date_str: 日期字符串

        Returns:
            Optional[datetime]: 解析后的日期对象
        """
        if not date_str:
            return None

        # 尝试多种日期格式
        date_formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y.%m.%d",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # 尝试匹配年份 (如 "2022年")
        year_match = re.match(r"(\d{4})年", date_str)
        if year_match:
            year = int(year_match.group(1))
            return datetime(year, 1, 1)

        logger.warning(f"无法解析日期格式: {date_str}")
        return None

    def _is_special_type(self, subject_type: str, subject_data: Dict[str, Any]) -> bool:
        """
        判断是否为特殊类型（剧场版、OVA等）

        Args:
            subject_type: 类型字符串
            subject_data: 番剧数据

        Returns:
            bool: 是否为特殊类型
        """
        special_keywords = ["剧场版", "movie", "ova", "oad", "sp", "special", "总集篇", "合集", "精选"]

        # 检查类型字段
        if any(keyword in subject_type.lower() for keyword in special_keywords):
            return True

        # 检查名称字段
        name = (subject_data.get("name", "") + " " + subject_data.get("name_cn", "")).lower()

        return any(keyword in name for keyword in special_keywords)


# 便捷函数
def create_episode_validator(strict_mode: bool = True) -> EpisodeValidator:
    """
    创建剧集验证器实例

    Args:
        strict_mode: 是否启用严格模式

    Returns:
        EpisodeValidator: 验证器实例
    """
    validator = EpisodeValidator()
    validator.strict_mode = strict_mode
    return validator


async def validate_anime_episode(
    subject_data: Dict[str, Any], episodes_data: Optional[List[Dict[str, Any]]] = None, strict_mode: bool = True
) -> EpisodeInfo:
    """
    验证动漫剧集信息的便捷函数

    Args:
        subject_data: API获取的番剧数据
        episodes_data: API获取的剧集列表数据
        strict_mode: 是否启用严格模式

    Returns:
        EpisodeInfo: 验证后的剧集信息
    """
    validator = create_episode_validator(strict_mode)
    return validator.validate_episode_info(subject_data, episodes_data)
