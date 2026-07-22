"""
Location Tracker — 物理位置追踪 + 时空折叠检测

从结构化文本中提取物理位置，检测无逻辑跳跃。
用于Guardian审计门卫的熔断触发条件A。
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# 位置关键词映射
LOCATION_KEYWORDS = {
    "大厂工位区": ["工位", "办公桌", "电脑前", "显示器前", "键盘", "代码"],
    "公司机房": ["机房", "服务器", "机柜", "数据中心", "服务器集群"],
    "会议室": ["会议室", "投影仪", "白板", "会议桌"],
    "公司大楼门口": ["大楼门口", "公司门口", "走出公司", "大厦门口"],
    "便利店": ["便利店", "超市", "小卖部"],
    "公司大楼走廊": ["公司走廊", "公司过道", "公司电梯间", "大楼走廊"],
    "天台": ["天台", "楼顶", "屋顶"],
    "茶水间": ["茶水间", "咖啡机", "饮水机"],
    "地铁": ["地铁", "车厢", "站台"],
    "家": ["家里", "卧室", "出租屋", "回到家里"],
    "医院": ["医院", "病房", "病床", "护士站", "检查室", "住院部"],
    "万达广场": ["万达广场", "万达B座"],
}


@dataclass
class LocationRecord:
    """位置记录"""
    paragraph_index: int
    location: str
    confidence: float  # 0.0-1.0
    evidence: str  # 匹配到的关键词


@dataclass
class LocationJumpResult:
    """位置跳跃检测结果"""
    from_location: str
    to_location: str
    from_para: int
    to_para: int
    is_valid: bool
    reason: str
    severity: str  # "warning" | "critical"


class LocationTracker:
    """物理位置追踪器"""

    def __init__(self, custom_locations: dict[str, list[str]] | None = None):
        self.locations = custom_locations or LOCATION_KEYWORDS
        self.records: list[LocationRecord] = []

    def extract_locations(self, paragraphs: list[str]) -> list[LocationRecord]:
        """从段落列表中提取位置"""
        self.records = []
        for i, para in enumerate(paragraphs):
            location, confidence, evidence = self._match_location(para)
            if location:
                self.records.append(LocationRecord(
                    paragraph_index=i,
                    location=location,
                    confidence=confidence,
                    evidence=evidence,
                ))
        return self.records

    def detect_jumps(self, paragraphs: list[str], max_jump_distance: int = 1) -> list[LocationJumpResult]:
        """
        检测位置跳跃。

        Args:
            paragraphs: 段落列表
            max_jump_distance: 允许的最大跳跃距离（段落数）。
                              1 = 只允许相邻段落切换位置
                              2 = 允许跨1段切换位置

        Returns:
            跳跃检测结果列表
        """
        if not self.records:
            self.extract_locations(paragraphs)

        jumps = []
        for i in range(1, len(self.records)):
            prev = self.records[i - 1]
            curr = self.records[i]

            if prev.location != curr.location:
                para_distance = curr.paragraph_index - prev.paragraph_index

                if para_distance > max_jump_distance:
                    # 检查是否是合理的长距离移动
                    is_valid = self._validate_jump(prev.location, curr.location, para_distance)
                    reason = "" if is_valid else f"从{prev.location}瞬间跳到{curr.location}，跨{para_distance}段无过渡"

                    jumps.append(LocationJumpResult(
                        from_location=prev.location,
                        to_location=curr.location,
                        from_para=prev.paragraph_index,
                        to_para=curr.paragraph_index,
                        is_valid=is_valid,
                        reason=reason,
                        severity="critical" if not is_valid else "warning",
                    ))

        return jumps

    def get_location_timeline(self) -> list[dict]:
        """获取位置时间线（用于调试）"""
        return [
            {
                "para": r.paragraph_index,
                "location": r.location,
                "confidence": r.confidence,
                "evidence": r.evidence,
            }
            for r in self.records
        ]

    def _match_location(self, text: str) -> tuple[str, float, str]:
        """匹配段落中的位置"""
        best_location = ""
        best_confidence = 0.0
        best_evidence = ""

        for location, keywords in self.locations.items():
            matches = []
            for kw in keywords:
                if kw in text:
                    matches.append(kw)

            if matches:
                # 置信度 = 匹配关键词数 / 总关键词数
                confidence = len(matches) / len(keywords)
                if confidence > best_confidence:
                    best_location = location
                    best_confidence = confidence
                    best_evidence = ", ".join(matches)

        return best_location, best_confidence, best_evidence

    def _validate_jump(self, from_loc: str, to_loc: str, distance: int) -> bool:
        """验证跳跃是否合理"""
        # 合理的跳跃对（物理上可能的快速移动）
        valid_transitions = {
            ("大厂工位区", "公司机房"),
            ("公司机房", "大厂工位区"),
            ("大厂工位区", "会议室"),
            ("会议室", "大厂工位区"),
            ("大厂工位区", "茶水间"),
            ("茶水间", "大厂工位区"),
            ("大厂工位区", "公司大楼走廊"),
            ("公司大楼走廊", "大厂工位区"),
            ("公司大楼门口", "公司大楼走廊"),
            ("公司大楼走廊", "公司大楼门口"),
            ("大厂工位区", "天台"),
            ("天台", "大厂工位区"),
        }

        transition = (from_loc, to_loc)
        if transition in valid_transitions:
            return True

        # 跳跃距离超过3段 = 不合理
        if distance > 3:
            return False

        # 默认允许
        return True
