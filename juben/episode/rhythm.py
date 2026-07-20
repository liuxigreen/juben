"""
Rhythm Validator — 双轴节奏校验

字数轴锁密度，秒数轴锁节奏。
两条线同时校验，哪条先撞墙哪条触发熔断。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .schema import Episode, PacingCheckpoint, PacingLabel

logger = logging.getLogger(__name__)


# ============================================================
# 节奏卡点定义（双轴）
# ============================================================

PACING_TABLE: list[dict] = [
    {
        "label": PacingLabel.HOOK_3S,
        "word_range": [0, 100],
        "time_range": [0, 3],
        "rule": "动词+特写开局。禁止背景铺垫。必须出现一个具体的感官冲击（坠落感/疼痛/重生的眩晕/血/碎裂声）",
        "emotion": "震惊/恐惧",
    },
    {
        "label": PacingLabel.RETENTION_15S,
        "word_range": [300, 500],
        "time_range": [10, 20],
        "rule": "爆出核心信息差——主角知道但其他人不知道的关键事实。这是留住观众的炸弹",
        "emotion": "掌控感/暗爽",
    },
    {
        "label": PacingLabel.EXPLOSION_30S,
        "word_range": [600, 800],
        "time_range": [25, 35],
        "rule": "视觉/物理冲击（踢飞、玻璃碎、雷劈、打翻茶杯）。必须有物理位移，不能只靠对话",
        "emotion": "紧张/冲击",
    },
    {
        "label": PacingLabel.SATISFACTION_60S,
        "word_range": [1000, 1200],
        "time_range": [50, 65],
        "rule": "小赢——主角获得一个小胜利（点头、表扬、反派愣住、证据到手）",
        "emotion": "暗爽/掌控",
    },
    {
        "label": PacingLabel.CLIFFHANGER_90S,
        "word_range": [1700, 2000],
        "time_range": [80, 95],
        "rule": "断崖。必须在最后一句植入一个具体的未回答问题或突发事件",
        "emotion": "悬念/紧迫",
    },
]


@dataclass
class RhythmViolation:
    """节奏违规"""
    label: str
    dimension: str      # "word" | "time" | "rule"
    expected: str
    actual: str
    severity: str       # "critical" | "warning"


@dataclass
class RhythmResult:
    """校验结果"""
    passed: bool
    violations: list[RhythmViolation] = field(default_factory=list)
    score: float = 0.0


class RhythmValidator:
    """双轴节奏校验器"""

    def __init__(self, custom_table: list[dict] | None = None):
        self.table = custom_table or PACING_TABLE

    def validate_episode(self, episode: Episode) -> RhythmResult:
        """校验单集节奏"""
        violations: list[RhythmViolation] = []

        for cp in episode.pacing_checkpoints:
            # 找到对应的节奏定义
            rule_def = self._find_rule(cp.label)
            if not rule_def:
                continue

            # 字数轴校验
            word_ok = self._check_word_range(cp, rule_def)
            if not word_ok:
                violations.append(RhythmViolation(
                    label=cp.label.value if isinstance(cp.label, PacingLabel) else cp.label,
                    dimension="word",
                    expected=f"{rule_def['word_range'][0]}-{rule_def['word_range'][1]}字",
                    actual=f"{cp.word_range[0]}-{cp.word_range[1]}字",
                    severity="warning",
                ))

            # 秒数轴校验
            time_ok = self._check_time_range(cp, rule_def)
            if not time_ok:
                violations.append(RhythmViolation(
                    label=cp.label.value if isinstance(cp.label, PacingLabel) else cp.label,
                    dimension="time",
                    expected=f"{rule_def['time_range'][0]}-{rule_def['time_range'][1]}秒",
                    actual=f"{cp.time_range[0]}-{cp.time_range[1]}秒",
                    severity="warning",
                ))

        # 检查是否缺少关键卡点
        missing = self._check_missing_checkpoints(episode)
        for m in missing:
            violations.append(RhythmViolation(
                label=m,
                dimension="rule",
                expected="必须存在",
                actual="缺失",
                severity="critical",
            ))

        # 断崖检查
        if not episode.cliffhanger or not episode.cliffhanger.line:
            violations.append(RhythmViolation(
                label="cliffhanger",
                dimension="rule",
                expected="必须有断崖钩子",
                actual="无",
                severity="critical",
            ))

        critical_count = sum(1 for v in violations if v.severity == "critical")
        score = max(0, 10 - critical_count * 3 - len(violations) * 0.5)

        return RhythmResult(
            passed=critical_count == 0,
            violations=violations,
            score=round(score, 1),
        )

    def _find_rule(self, label) -> dict | None:
        """根据标签找到节奏定义"""
        label_str = label.value if isinstance(label, PacingLabel) else label
        for rule in self.table:
            if rule["label"].value == label_str:
                return rule
        return None

    def _check_word_range(self, cp: PacingCheckpoint, rule: dict) -> bool:
        """校验字数区间是否在合理范围"""
        if not cp.word_range or len(cp.word_range) < 2:
            return False
        expected_min, expected_max = rule["word_range"]
        # 允许20%浮动
        margin = (expected_max - expected_min) * 0.2
        return (cp.word_range[0] >= expected_min - margin and
                cp.word_range[1] <= expected_max + margin)

    def _check_time_range(self, cp: PacingCheckpoint, rule: dict) -> bool:
        """校验秒数区间是否在合理范围"""
        if not cp.time_range or len(cp.time_range) < 2:
            return False
        expected_min, expected_max = rule["time_range"]
        margin = (expected_max - expected_min) * 0.3
        return (cp.time_range[0] >= expected_min - margin and
                cp.time_range[1] <= expected_max + margin)

    def _check_missing_checkpoints(self, episode: Episode) -> list[str]:
        """检查是否缺少关键卡点"""
        existing = set()
        for cp in episode.pacing_checkpoints:
            label_str = cp.label.value if isinstance(cp.label, PacingLabel) else cp.label
            existing.add(label_str)

        required = {r["label"].value for r in self.table}
        missing = required - existing
        return list(missing)
