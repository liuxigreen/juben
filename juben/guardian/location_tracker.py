"""
Location Tracker — 物理位置追踪 + 时空折叠检测（v2）

v2改动：
1. 位置关键词从项目级 locations.json 动态加载，不硬编码
2. 引入位移介质锁（Transition Media）：有交通/位移动作即豁免时空折叠
3. _validate_jump 不再依赖硬编码的场景转换列表
"""
from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 位移介质（Transition Media）
# 有这些关键词出现在场景切换段落中 → 合法转场，豁免时空折叠
# ============================================================

TRANSITION_MEDIA = {
    "riding": ["骑", "电动车", "头盔", "拧把", "加速", "红绿灯", "穿过街道", "摩托"],
    "driving": ["开车", "驾驶", "方向盘", "油门", "刹车", "停车位", "倒车"],
    "walking": ["走出", "跨过", "推开门", "上楼", "下楼", "拐进", "步行", "沿着", "穿过走廊"],
    "elevator": ["电梯", "按了", "电梯门", "楼层"],
    "transit": ["地铁", "公交", "打车", "出租车", "网约车", "站台", "车厢"],
    "time_pass": ["分钟后", "半小时", "一小时", "抵达", "来到", "一路", "到了", "到达"],
}


# ============================================================
# 默认位置关键词（兜底，项目应提供自己的）
# ============================================================

DEFAULT_LOCATION_KEYWORDS: dict[str, list[str]] = {
    "医院": ["医院", "病房", "病床", "护士站", "检查室", "住院部", "挂号"],
    "家": ["家里", "卧室", "出租屋", "回到家里", "家门口"],
    "街道": ["街道", "马路", "人行道", "十字路口", "红绿灯"],
}


def load_locations_from_project(project_dir: Path) -> dict[str, list[str]] | None:
    """从项目目录加载位置关键词

    优先级：
    1. project_dir/locations.json — 显式定义
    2. 从 chapters/ 已有文本自动提取（TODO）
    3. None → 使用默认
    """
    loc_file = project_dir / "locations.json"
    if loc_file.exists():
        with open(loc_file, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    return None


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
    has_transition_media: bool = False  # 是否检测到位移介质


class LocationTracker:
    """物理位置追踪器（v2：动态加载 + 位移介质锁）"""

    def __init__(self, custom_locations: dict[str, list[str]] | None = None,
                 project_dir: Path | None = None):
        # 优先使用custom_locations，其次从项目加载，最后用默认
        if custom_locations:
            self.locations = custom_locations
        elif project_dir:
            loaded = load_locations_from_project(project_dir)
            self.locations = loaded if loaded else DEFAULT_LOCATION_KEYWORDS
        else:
            self.locations = DEFAULT_LOCATION_KEYWORDS
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

    def detect_jumps(self, paragraphs: list[str], max_jump_distance: int = 2) -> list[LocationJumpResult]:
        """
        检测位置跳跃。

        v2改动：
        - 检查场景切换段落中是否有位移介质
        - 有位移介质 → 自动豁免（is_valid=True）
        - 无位移介质且距离>30段 → 标记为critical
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
                    # 检查中间段落是否有位移介质
                    has_media = self._check_transition_media(
                        paragraphs, prev.paragraph_index, curr.paragraph_index
                    )

                    if has_media:
                        # 有位移介质 → 合法转场
                        jumps.append(LocationJumpResult(
                            from_location=prev.location,
                            to_location=curr.location,
                            from_para=prev.paragraph_index,
                            to_para=curr.paragraph_index,
                            is_valid=True,
                            reason="",
                            severity="warning",
                            has_transition_media=True,
                        ))
                    else:
                        # 无位移介质 → 检查距离
                        is_valid = para_distance <= 30
                        reason = "" if is_valid else f"从{prev.location}瞬间跳到{curr.location}，跨{para_distance}段无过渡"

                        jumps.append(LocationJumpResult(
                            from_location=prev.location,
                            to_location=curr.location,
                            from_para=prev.paragraph_index,
                            to_para=curr.paragraph_index,
                            is_valid=is_valid,
                            reason=reason,
                            severity="critical" if not is_valid else "warning",
                            has_transition_media=False,
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

    def _check_transition_media(self, paragraphs: list[str],
                                 from_idx: int, to_idx: int) -> bool:
        """检查两个位置之间的段落是否包含位移介质

        扫描范围：from_idx 到 to_idx 之间的所有段落（含两端）
        """
        # 收集所有位移介质关键词
        all_media_keywords: list[str] = []
        for keywords in TRANSITION_MEDIA.values():
            all_media_keywords.extend(keywords)

        # 扫描中间段落
        start = max(0, from_idx)
        end = min(len(paragraphs), to_idx + 1)
        for i in range(start, end):
            para = paragraphs[i]
            for kw in all_media_keywords:
                if kw in para:
                    return True

        return False
