"""
Episode Parser — 解析器（不是生成器）

解析Scribe输出的带镜头标注的结构化文本。
不再从纯文本机械切割，而是解析已有的镜头块。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .schema import (
    Cliffhanger,
    Episode,
    PacingCheckpoint,
    PacingLabel,
    Shot,
    ShotType,
    CameraMovement,
    CameraAngle,
)


# 景别标签映射
SHOT_TYPE_MAP = {
    "CU": ShotType.CU,
    "MCU": ShotType.MCU,
    "MS": ShotType.MS,
    "WS": ShotType.FS,  # WS对应全景
    "FS": ShotType.FS,
    "ECU": ShotType.ECU,
    "EWS": ShotType.EWS,
}

# 运镜标签映射
CAMERA_MOVE_MAP = {
    "Static": CameraMovement.STATIC,
    "Push": CameraMovement.PUSH,
    "Pull": CameraMovement.PULL,
    "Shake": CameraMovement.HANDHELD,
    "Pan": CameraMovement.PAN,
    "Handheld": CameraMovement.HANDHELD,
}


# 光影标签映射
LIGHTING_MAP = {
    "Low key": "low_key_cold",
    "Warm": "warm_golden",
    "High contrast": "high_contrast_dramatic",
}

# 视角标签映射
ANGLE_MAP = {
    "Low Angle": CameraAngle.LOW,
    "High Angle": CameraAngle.HIGH,
    "Eye Level": CameraAngle.EYE_LEVEL,
}

class EpisodeParser:
    """
    解析Scribe输出的带镜头标注的结构化文本。

    输入格式（每个镜头块）：
    ```
    ## 镜头 1 | 3s_Hook (0-100字)
    - **【画面机位】**: [CU] + [Push]
    - **【视觉动作】**: 沈清辞的手指被针扎破，血珠迅速渗出
    - **【光影/音效】**: 暖色烛光摇曳 / 针尖刺破皮肤的微小音效被放大
    - **【台词】**: 沈清辞(眼神骤然转冷): "这毒，果然是从宫里出来的。"
    ```
    """

    def parse(self, text: str, episode_number: int = 1) -> Episode:
        """解析带镜头标注的文本，返回Episode"""
        # 1. 按镜头块切割
        shot_blocks = self._split_shot_blocks(text)

        # 2. 解析每个镜头块
        shots = []
        checkpoints = []
        for i, block in enumerate(shot_blocks, 1):
            shot, checkpoint = self._parse_block(block, i)
            if shot:
                shots.append(shot)
            if checkpoint:
                checkpoints.append(checkpoint)

        # 3. 提取断崖钩子（最后一个镜头块的最后一句台词或动作）
        cliffhanger = self._extract_cliffhanger(shot_blocks)

        # 4. 构建Episode
        total_chars = len(text)
        total_duration = sum(s.duration for s in shots)

        return Episode(
            episode_number=episode_number,
            duration_estimate_seconds=int(total_duration),
            word_count_estimate=total_chars,
            pacing_checkpoints=checkpoints,
            shots=shots,
            cliffhanger=cliffhanger,
            hook_density=self._estimate_hook_density(text),
            scene_count=len(shots),
            script_text=text,
            shot_prompts=[{"shot_id": s.shot_id, "prompt": s.to_visual_prompt()} for s in shots],
        )

    def _split_shot_blocks(self, text: str) -> list[str]:
        """按镜头块标题切割"""
        # 匹配 ## 镜头 N | 或 ## Shot N |
        pattern = r'(?=^## (?:镜头|Shot)\s*\d+)'
        blocks = re.split(pattern, text, flags=re.MULTILINE)
        return [b.strip() for b in blocks if b.strip() and re.match(r'^## (?:镜头|Shot)', b.strip())]

    def _parse_block(self, block: str, shot_id: int) -> tuple[Shot | None, PacingCheckpoint | None]:
        """解析单个镜头块"""
        # 提取卡点标签
        pacing_label = self._extract_pacing_label(block)

        # 提取画面机位（4维度）
        shot_type, camera_move, angle = self._extract_camera(block)

        # 提取场景光影
        lighting = self._extract_lighting(block)

        # 提取视觉动作
        visual_action = self._extract_field(block, "视觉动作")

        # 提取场景光影（新格式）
        scene_lighting = self._extract_field(block, "场景光影")
        if not scene_lighting:
            scene_lighting = self._extract_field(block, "光影/音效")

        # 提取台词
        dialogue = self._extract_dialogue(block)

        # 提取情绪（从视觉动作推断）
        emotion = self._infer_emotion(visual_action)

        # 估算时长（5个镜头，目标90秒，每镜头约18秒）
        duration = 18.0  # 固定时长，后续可按内容量调整

        # 构建Shot
        shot = Shot(
            shot_id=shot_id,
            shot_type=shot_type,
            camera_movement=camera_move,
            camera_angle=angle,
            duration=duration,
            subject="",
            action=visual_action,
            setting="",
            lighting=scene_lighting,
            mood=emotion,
            emotion_tag=emotion,
            pacing_label=pacing_label,
        )

        # 构建PacingCheckpoint
        word_count = len(visual_action) + len(dialogue)
        checkpoint = PacingCheckpoint(
            label=PacingLabel(pacing_label) if pacing_label in [e.value for e in PacingLabel] else PacingLabel.HOOK_3S,
            word_range=[0, word_count],  # 粗略
            time_range=[0, duration],
            rule="",
            visual_action=visual_action,
            dialogue=dialogue,
            emotion=emotion,
            passed=True,
        )

        return shot, checkpoint

    def _extract_pacing_label(self, block: str) -> str:
        """提取卡点标签（如 3s_Hook, 15s_Retention）"""
        match = re.search(r'\|\s*(\w+_\w+)', block)
        if match:
            return match.group(1)
        return ""

    def _extract_camera(self, block: str) -> tuple[ShotType, CameraMovement, CameraAngle]:
        """提取画面机位"""
        # 匹配 [CU] + [Push] + [Low Angle] 格式
        camera_block = self._extract_field(block, "画面机位")

        shot_type = ShotType.MS  # 默认中景
        camera_move = CameraMovement.STATIC  # 默认静止
        angle = CameraAngle.EYE_LEVEL  # 默认平视

        # 提取景别
        for tag, st in SHOT_TYPE_MAP.items():
            if f'[{tag}]' in camera_block:
                shot_type = st
                break

        # 提取运镜
        for tag, cm in CAMERA_MOVE_MAP.items():
            if f'[{tag}]' in camera_block:
                camera_move = cm
                break

        # 提取视角
        for tag, a in ANGLE_MAP.items():
            if f'[{tag}]' in camera_block:
                angle = a
                break

        return shot_type, camera_move, angle

    def _extract_lighting(self, block: str) -> str:
        """提取光影标签"""
        scene_lighting = self._extract_field(block, "场景光影")
        for tag, desc in LIGHTING_MAP.items():
            if f'[{tag}]' in scene_lighting:
                return desc
        return ""

    def _extract_field(self, block: str, field_name: str) -> str:
        """提取指定字段的内容"""
        pattern = rf'【{field_name}】[^:：]*[：:]\s*(.+?)(?=\n-|\n##|\Z)'
        match = re.search(pattern, block, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_dialogue(self, block: str) -> str:
        """提取台词"""
        dialogue_block = self._extract_field(block, "台词")
        # 提取引号内的内容
        matches = re.findall(r'["「](.*?)["」]', dialogue_block)
        return matches[0] if matches else dialogue_block

    def _extract_cliffhanger(self, shot_blocks: list[str]) -> Cliffhanger:
        """提取断崖钩子（最后一个镜头块）"""
        if not shot_blocks:
            return Cliffhanger()

        last_block = shot_blocks[-1]
        visual_action = self._extract_field(last_block, "视觉动作")
        dialogue = self._extract_field(last_block, "台词")

        # 判断钩子类型
        combined = visual_action + dialogue
        if "？" in combined or "?" in combined:
            return Cliffhanger(
                type="question",
                line=combined[-200:],
                unanswered_question=combined.split("？")[-2] + "？" if "？" in combined else "",
            )
        elif any(w in combined for w in ["突然", "忽然", "猛地", "瞬间"]):
            return Cliffhanger(
                type="shock",
                line=combined[-200:],
                unanswered_question="接下来会发生什么？",
            )
        else:
            return Cliffhanger(
                type="reveal",
                line=combined[-200:],
                unanswered_question="这个发现意味着什么？",
            )

    def _estimate_hook_density(self, text: str) -> str:
        """估算钩子密度"""
        hook_count = len(re.findall(r'突然|忽然|？|!|真相|秘密', text))
        lines = text.count('\n')
        ratio = hook_count / max(1, lines)
        if ratio > 0.3:
            return "high"
        elif ratio > 0.15:
            return "medium"
        return "low"

    def _infer_emotion(self, text: str) -> str:
        """推断情绪"""
        emotion_keywords = {
            "愤怒": ["攥紧", "咬牙", "瞪", "摔", "砸", "指节发白", "厉喝", "冷笑", "怒吼", "踹"],
            "恐惧": ["颤抖", "冷汗", "退缩", "发抖", "发颤", "哆嗦", "僵直", "瞳孔骤缩"],
            "震惊": ["愣住", "瞳孔", "不敢相信", "呆住", "猛地", "骤然", "一抖", "身体一僵"],
            "悲伤": ["眼泪", "哽咽", "泪珠", "哭泣", "声音发抖", "气若游丝"],
            "爽感": ["微笑", "冷笑", "碾压", "打脸", "眼神坚定", "语气平静"],
            "悬念": ["？", "难道", "究竟", "秘密", "无声", "极轻", "几乎听不见"],
            "紧张": ["急促", "逼近", "破窗", "冲入", "追", "跑", "闪"],
        }
        for emotion, keywords in emotion_keywords.items():
            for kw in keywords:
                if kw in text:
                    return emotion
        return "中性"
