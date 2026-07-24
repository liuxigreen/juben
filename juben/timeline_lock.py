"""
Timeline Lock — 章节骨架物理字数锁

核心铁律：
- 前20章禁止触发高阶反派的正面冲突
- 每个剧情节点有最小字数要求（弹簧必须压够才能弹）
- LLM不能跳过节点，只能按顺序推进

使用方式：
    from juben.timeline_lock import TimelineLock
    lock = TimelineLock.from_config("timeline_lock.json")
    lock.validate_chapter(5, chapter_text)  # 检查第5章是否违规
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PlotNode:
    """剧情节点 — 一个不可跳过的剧情阶段"""

    def __init__(
        self,
        node_id: str,
        name: str,
        chapter_range: list[int],
        min_words: int = 0,
        description: str = "",
        required_before: Optional[list[str]] = None,
        forbidden_elements: Optional[list[str]] = None,
    ):
        self.node_id = node_id
        self.name = name
        self.chapter_range = chapter_range  # [start, end] 章节范围
        self.min_words = min_words  # 该节点的最小总字数
        self.description = description
        self.required_before = required_before or []  # 必须先完成的节点
        self.forbidden_elements = forbidden_elements or []  # 该节点内禁止出现的元素

    def contains_chapter(self, chapter: int) -> bool:
        return self.chapter_range[0] <= chapter <= self.chapter_range[1]

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "chapter_range": self.chapter_range,
            "min_words": self.min_words,
            "description": self.description,
            "required_before": self.required_before,
            "forbidden_elements": self.forbidden_elements,
        }


class TimelineLockResult:
    """校验结果"""

    def __init__(self):
        self.violations: list[dict] = []
        self.passed: bool = True

    def add_violation(self, severity: str, node_id: str, description: str):
        self.violations.append({
            "severity": severity,
            "node_id": node_id,
            "description": description,
        })
        if severity == "critical":
            self.passed = False

    def __repr__(self):
        if self.passed:
            return f"TimelineLockResult(PASS, {len(self.violations)} warnings)"
        return f"TimelineLockResult(FAIL, {len(self.violations)} violations)"


class TimelineLock:
    """Timeline Lock — 章节骨架物理约束引擎"""

    def __init__(self, nodes: list[PlotNode]):
        self.nodes = {n.node_id: n for n in nodes}
        self._sorted_nodes = sorted(nodes, key=lambda n: n.chapter_range[0])

    @classmethod
    def from_config(cls, config_path: str | Path) -> "TimelineLock":
        """从JSON配置文件加载"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Timeline Lock配置不存在: {path}，使用默认配置")
            return cls.from_skeleton("50chap-standard")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = []
        for n in data.get("nodes", []):
            nodes.append(PlotNode(**n))
        return cls(nodes)

    @classmethod
    def from_skeleton(cls, skeleton_name: str = "50chap-standard") -> "TimelineLock":
        """从skeleton配置文件加载（支持20chap-fast/50chap-standard/100chap-epic）"""
        skeleton_dir = Path(__file__).parent / "skeleton"
        skeleton_path = skeleton_dir / f"{skeleton_name}.json"
        
        if not skeleton_path.exists():
            logger.warning(f"Skeleton配置不存在: {skeleton_path}，使用默认50chap-standard")
            skeleton_path = skeleton_dir / "50chap-standard.json"
        
        if not skeleton_path.exists():
            logger.warning(f"默认skeleton配置也不存在，使用硬编码默认值")
            return cls._from_hardcoded_default()

        with open(skeleton_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = []
        for n in data.get("nodes", []):
            nodes.append(PlotNode(**n))
        return cls(nodes)

    @classmethod
    def from_default(cls) -> "TimelineLock":
        """默认配置 — 适用于50章的悬疑/复仇类题材（向后兼容）"""
        return cls.from_skeleton("50chap-standard")

    @classmethod
    def _from_hardcoded_default(cls) -> "TimelineLock":
        """硬编码默认值（最后的fallback）"""
        nodes = [
            PlotNode(
                node_id="act1_setup",
                name="第一幕：入局",
                chapter_range=[1, 10],
                min_words=15000,
                description="建立世界观、引入主角困境、展示核心能力、埋下第一条线索",
                forbidden_elements=[
                    "反派大boss正面登场",
                    "主角直接对抗最高层反派",
                    "真相全部揭开",
                ],
            ),
            PlotNode(
                node_id="act1_complication",
                name="第一幕：复杂化",
                chapter_range=[11, 20],
                min_words=15000,
                description="盟友出现、信息差建立、第一个小胜利、发现更大的阴谋",
                required_before=["act1_setup"],
                forbidden_elements=[
                    "反派大boss被逮捕",
                    "所有秘密被揭开",
                    "主角获得最终胜利",
                ],
            ),
            PlotNode(
                node_id="act2_rising",
                name="第二幕：上升",
                chapter_range=[21, 30],
                min_words=15000,
                description="深入敌方内部、收集关键证据、遭遇重大挫折、信任危机",
                required_before=["act1_complication"],
                forbidden_elements=[
                    "反派主动交代一切",
                    "轻松获得关键证据",
                ],
            ),
            PlotNode(
                node_id="act2_crisis",
                name="第二幕：危机",
                chapter_range=[31, 40],
                min_words=15000,
                description="主角陷入绝境、盟友背叛或牺牲、核心秘密揭露",
                required_before=["act2_rising"],
            ),
            PlotNode(
                node_id="act3_climax",
                name="第三幕：高潮",
                chapter_range=[41, 48],
                min_words=12000,
                description="最终对决、反派伏法、真相大白",
                required_before=["act2_crisis"],
            ),
            PlotNode(
                node_id="act3_resolution",
                name="第三幕：收尾",
                chapter_range=[49, 50],
                min_words=3000,
                description="善后、角色归处、情感收束",
                required_before=["act3_climax"],
            ),
        ]
        return cls(nodes)

    def get_current_node(self, chapter: int) -> Optional[PlotNode]:
        """获取当前章节所在的剧情节点"""
        for node in self._sorted_nodes:
            if node.contains_chapter(chapter):
                return node
        return None

    def validate_chapter(
        self,
        chapter: int,
        chapter_text: str,
        completed_nodes: Optional[list[str]] = None,
        recent_chapter_texts: Optional[list[str]] = None,
    ) -> TimelineLockResult:
        """
        校验一个章节是否违反Timeline Lock。

        Args:
            chapter: 章节号
            chapter_text: 章节正文
            completed_nodes: 已完成的节点ID列表
            recent_chapter_texts: 最近几章的正文（用于主题重复检测）

        Returns:
            TimelineLockResult
        """
        result = TimelineLockResult()
        completed = completed_nodes or []

        # 1. 找到当前节点
        current_node = self.get_current_node(chapter)
        if current_node is None:
            result.add_violation("warning", "unknown", f"第{chapter}章不在任何剧情节点范围内")
            return result

        # 2. 检查前置节点是否完成
        for req_id in current_node.required_before:
            if req_id not in completed:
                req_node = self.nodes.get(req_id)
                req_name = req_node.name if req_node else req_id
                result.add_violation(
                    "critical",
                    current_node.node_id,
                    f"前置节点 '{req_name}' 未完成，不能进入 '{current_node.name}'"
                )

        # 3. 检查禁止元素
        for forbidden in current_node.forbidden_elements:
            if self._text_contains_element(chapter_text, forbidden):
                result.add_violation(
                    "critical",
                    current_node.node_id,
                    f"第{chapter}章包含禁止元素: '{forbidden}'（当前节点: {current_node.name}）"
                )

        # 4. 主题不重复检测（新增）
        if recent_chapter_texts:
            repetition = self._check_theme_repetition(chapter_text, recent_chapter_texts)
            if repetition:
                result.add_violation(
                    "warning",
                    current_node.node_id,
                    repetition
                )

        return result

    def _text_contains_element(self, text: str, element: str) -> bool:
        """检查文本是否包含指定元素（模糊匹配）"""
        # 简单的关键词匹配，可以后续升级为语义匹配
        element_lower = element.lower()
        text_lower = text.lower()

        # 拆分关键词，全部出现才算命中
        keywords = element_lower.replace("、", ",").replace("，", ",").split(",")
        keywords = [k.strip() for k in keywords if k.strip()]

        return all(kw in text_lower for kw in keywords)

    def _check_theme_repetition(self, current_text: str, recent_texts: list[str]) -> str | None:
        """
        检测当前章节与最近章节的主题重复。

        规则：
        - 提取每章的关键词（去掉停用词后的高频词）
        - 如果当前章与前一章的关键词重叠率 > 60%，触发警告
        """
        import re
        from collections import Counter

        # 停用词
        stop_words = {
            "的", "了", "在", "是", "和", "与", "也", "都", "就", "不",
            "她", "他", "我", "你", "们", "这", "那", "有", "被", "从",
            "到", "把", "让", "对", "为", "着", "过", "说", "道", "一",
            "个", "上", "下", "里", "中", "来", "去", "得", "能", "会",
            "可", "以", "所", "之", "其", "而", "但", "又", "如", "及",
            "没", "很", "还", "更", "已", "并", "或", "则", "等", "将",
            "向", "当", "比", "因", "此", "虽", "然", "若", "即", "何",
        }

        def extract_keywords(text: str) -> set[str]:
            """提取关键词（简单的分词+去停用词）"""
            # 去掉标点和数字
            clean = re.sub(r'[^\u4e00-\u9fff]', '', text)
            # 按字拆分，去停用词
            words = [c for c in clean if c not in stop_words and len(c) > 0]
            # 统计词频，取top30
            counter = Counter(words)
            return {w for w, _ in counter.most_common(30)}

        current_keywords = extract_keywords(current_text)

        for i, prev_text in enumerate(recent_texts[-2:]):  # 只检查最近2章
            prev_keywords = extract_keywords(prev_text)
            if not prev_keywords:
                continue

            overlap = len(current_keywords & prev_keywords)
            total = min(len(current_keywords), len(prev_keywords))
            if total > 0 and overlap / total > 0.6:
                common = list(current_keywords & prev_keywords)[:5]
                return (
                    f"第{len(recent_texts) - i}章与当前章主题高度重叠（关键词重叠率{overlap/total:.0%}）。"
                    f"共同关键词: {', '.join(common)}。"
                    f"建议：引入新的场景/角色/冲突，避免读者感到重复。"
                )

        return None

    def get_chapter_guidance(self, chapter: int) -> str:
        """获取当前章节的写作指导（注入到Scribe prompt中）"""
        current_node = self.get_current_node(chapter)
        if current_node is None:
            return ""

        guidance = [
            f"## 当前剧情节点: {current_node.name}",
            f"章节范围: {current_node.chapter_range[0]}-{current_node.chapter_range[1]}",
            f"节点描述: {current_node.description}",
        ]

        if current_node.forbidden_elements:
            guidance.append("\n### ⛔ 本阶段禁止出现的元素:")
            for forbidden in current_node.forbidden_elements:
                guidance.append(f"  - {forbidden}")

        if current_node.required_before:
            guidance.append("\n### ✅ 前置要求:")
            for req_id in current_node.required_before:
                req_node = self.nodes.get(req_id)
                if req_node:
                    guidance.append(f"  - {req_node.name}: {req_node.description}")

        return "\n".join(guidance)

    def generate_config(self, output_path: str | Path):
        """导出配置到JSON文件"""
        data = {
            "nodes": [n.to_dict() for n in self._sorted_nodes]
        }
        path = Path(output_path)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Timeline Lock配置已导出: {path}")
