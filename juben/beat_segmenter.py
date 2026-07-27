"""
BeatSegmenter — 场景内最小可拍单元切分器

将场景文本切分为Beat（最小可拍事件单元）。
每个Beat = 一个镜头候选。

切分优先级：
1. 说话人切换
2. 能力发动/痕迹变化事件
3. 对话→动作切换
4. 环境强反馈（碎杯/灯灭/门外人影）
5. 段落边界
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Beat:
    """最小可拍事件单元"""
    beat_id: int
    scene_index: int
    text: str
    beat_type: str  # dialogue / action / ability / environment / transition
    speaker: str = ""  # 说话人（仅dialogue类型）
    has_ability_event: bool = False  # 是否包含能力发动/痕迹变化
    has_anchor: bool = False  # 是否包含视觉图腾
    word_count: int = 0


# 能力发动/痕迹变化关键词
ABILITY_KEYWORDS = [
    "端起", "闭眼", "闭上眼", "世界安静", "声音消失", "听到",
    "睁开眼", "放下杯子", "心声", "脑海里",
    "读心", "读到", "浮现", "画面闪过",
]

# 痕迹变化关键词
TRACE_KEYWORDS = [
    "淡了", "消失", "没了", "不见了", "模糊了", "变浅", "变淡",
    "少了一笔", "缺了一角", "褪色", "光滑", "干净",
    "印痕", "疤痕", "字迹", "便签",
]

# 环境强反馈关键词
ENVIRONMENT_KEYWORDS = [
    "灯闪", "灭了", "暗了", "碎了", "裂了", "震了", "响了",
    "风铃", "门外", "人影", "脚步声", "门铃", "摔",
]


class BeatSegmenter:
    """场景→Beat切分器"""

    def __init__(self, min_beat_size: int = 20):
        self.min_beat_size = min_beat_size

    def segment(self, scene_text: str, scene_index: int) -> list[Beat]:
        """将场景文本切分为Beat列表"""
        # 按段落分
        paragraphs = [p.strip() for p in scene_text.split('\n') if p.strip()]

        if not paragraphs:
            return []

        # 找切分点
        cut_points = self._find_cut_points(paragraphs)

        # 按切分点分组
        beats = self._split_into_beats(paragraphs, cut_points, scene_index)

        return beats

    def _find_cut_points(self, paragraphs: list[str]) -> list[tuple[int, int]]:
        """
        找切分点，返回 (段落索引, 优先级) 列表。
        优先级越高越应该切。
        """
        cuts = []

        for i in range(1, len(paragraphs)):
            prev = paragraphs[i - 1]
            curr = paragraphs[i]
            priority = 0

            # P1: 说话人切换
            prev_speaker = self._extract_speaker(prev)
            curr_speaker = self._extract_speaker(curr)
            if prev_speaker and curr_speaker and prev_speaker != curr_speaker:
                priority = 10

            # P2: 能力发动/痕迹变化
            elif any(kw in curr for kw in ABILITY_KEYWORDS + TRACE_KEYWORDS):
                priority = 9

            # P3: 对话→动作切换
            elif self._has_dialogue(prev) and not self._has_dialogue(curr):
                # 检查是否有物理动作
                if self._has_physical_action(curr):
                    priority = 8

            # P4: 环境强反馈
            elif any(kw in curr for kw in ENVIRONMENT_KEYWORDS):
                priority = 7

            # P5: 动作→对话切换
            elif not self._has_dialogue(prev) and self._has_dialogue(curr):
                priority = 6

            # P6: 段落边界（任何非空段落都可以切）
            else:
                priority = 3

            if priority >= 3:
                cuts.append((i, priority))

        return cuts

    def _split_into_beats(
        self,
        paragraphs: list[str],
        cuts: list[tuple[int, int]],
        scene_index: int,
    ) -> list[Beat]:
        """按切分点分组为Beat"""
        if not cuts:
            # 整个场景作为一个Beat
            text = '\n\n'.join(paragraphs)
            return [Beat(
                beat_id=1,
                scene_index=scene_index,
                text=text,
                beat_type=self._infer_beat_type(text),
                speaker=self._extract_speaker(text),
                has_ability_event=self._has_ability_event(text),
                has_anchor=self._has_trace_change(text),
                word_count=len(text),
            )]

        # 按优先级排序，选最强切分点
        cuts.sort(key=lambda x: -x[1])

        # 选择切分点（保证间距≥1段，每段≥min_beat_size字）
        selected = []
        last = 0
        for idx, priority in cuts:
            if idx - last >= 1:
                selected.append(idx)
                last = idx
            if len(selected) >= 8:  # 最多8个Beat
                break

        selected.sort()

        # 按切分点分组
        beats = []
        beat_id = 1
        prev_idx = 0

        for cut_idx in selected:
            text = '\n\n'.join(paragraphs[prev_idx:cut_idx])
            if text.strip() and len(text.strip()) >= self.min_beat_size:
                beats.append(Beat(
                    beat_id=beat_id,
                    scene_index=scene_index,
                    text=text.strip(),
                    beat_type=self._infer_beat_type(text),
                    speaker=self._extract_speaker(text),
                    has_ability_event=self._has_ability_event(text),
                    has_anchor=self._has_trace_change(text),
                    word_count=len(text.strip()),
                ))
                beat_id += 1
            prev_idx = cut_idx

        # 最后一段
        tail = '\n\n'.join(paragraphs[prev_idx:])
        if tail.strip() and len(tail.strip()) >= self.min_beat_size:
            beats.append(Beat(
                beat_id=beat_id,
                scene_index=scene_index,
                text=tail.strip(),
                beat_type=self._infer_beat_type(tail),
                speaker=self._extract_speaker(tail),
                has_ability_event=self._has_ability_event(tail),
                has_anchor=self._has_trace_change(tail),
                word_count=len(tail.strip()),
            ))

        return beats if beats else [Beat(
            beat_id=1,
            scene_index=scene_index,
            text='\n\n'.join(paragraphs),
            beat_type="action",
            word_count=sum(len(p) for p in paragraphs),
        )]

    # --- 辅助方法 ---

    @staticmethod
    def _extract_speaker(text: str) -> str:
        """提取说话人"""
        match = re.search(r'(\w{2,4})(?:说|道|问|答|喊|叫|冷笑|叹|低声|开口)', text)
        if match:
            return match.group(1)
        # 检查引号对话
        if re.search(r'["\u300c]', text):
            return "unknown_speaker"
        return ""

    @staticmethod
    def _has_dialogue(text: str) -> bool:
        """是否包含对话"""
        return bool(re.search(r'["\u300c][^"\u300d]{2,}["\u300d]', text))

    @staticmethod
    def _has_physical_action(text: str) -> bool:
        """是否包含物理动作"""
        action_kw = [
            "端起", "放下", "转身", "站", "推", "攥", "掏出", "摸", "走",
            "跑", "坐", "擦", "磨", "按", "敲", "喝", "吃", "拿", "放",
            "点头", "抬头", "低头", "闭眼", "睁", "闪", "灭", "碎",
        ]
        return any(kw in text for kw in action_kw)

    @staticmethod
    def _has_ability_event(text: str) -> bool:
        """是否包含能力发动事件"""
        return any(kw in text for kw in ABILITY_KEYWORDS)

    @staticmethod
    def _has_trace_change(text: str) -> bool:
        """是否包含痕迹变化"""
        return any(kw in text for kw in TRACE_KEYWORDS)

    @staticmethod
    def _infer_beat_type(text: str) -> str:
        """推断Beat类型"""
        has_d = bool(re.search(r'["\u300c][^"\u300d]{2,}["\u300d]', text))
        has_ability = any(kw in text for kw in ABILITY_KEYWORDS)
        has_env = any(kw in text for kw in ENVIRONMENT_KEYWORDS)

        if has_ability:
            return "ability"
        if has_env:
            return "environment"
        if has_d:
            return "dialogue"
        return "action"
