"""
PromptRenderer — 纯英文槽位化Prompt组装器

将校准后的Shot数据组装为AI视频模型可执行的英文Prompt。
禁止中文长句直接进prompt。

槽位模板：
[SHOT SIZE], [CAMERA MOVE], [ANGLE],
[SUBJECT English], [VISIBLE ACTION English],
[KEY PROP if any], [LOCATION], [LIGHTING], [MOOD],
cinematic, 9:16, photorealistic, 4K
"""
from __future__ import annotations

from typing import Any


# 景别英文
SHOT_TYPE_EN = {
    "ECU": "extreme close-up",
    "CU": "close-up",
    "MCU": "medium close-up",
    "MS": "medium shot",
    "WS": "wide shot",
    "FS": "full shot",
    "EWS": "extreme wide shot",
}

# 运镜英文
CAMERA_MOVE_EN = {
    "static": "static camera",
    "push": "slow dolly forward",
    "pull": "slow dolly backward",
    "handheld": "handheld camera with slight shake",
    "pan": "horizontal pan",
    "tracking": "tracking shot",
    "rapid_push": "rapid push-in",
}

# 视角英文
ANGLE_EN = {
    "eye-level": "eye level",
    "low": "low angle looking up",
    "high": "high angle looking down",
    "Dutch": "Dutch angle",
    "overhead": "overhead top-down",
}

# 光影英文
LIGHTING_EN = {
    "Natural": "natural daylight, soft shadows",
    "Warm": "warm golden light, soft amber tones",
    "Low key": "low key lighting, deep shadows, dim atmosphere",
    "High contrast": "high contrast dramatic lighting, harsh shadows",
    "Moonlight": "cold blue moonlight, silver tones",
    "Neon": "neon lights, colorful glow",
}

# 情绪英文
MOOD_EN = {
    "震惊": "shocked, high tension",
    "紧张": "tense, suspenseful",
    "暧昧": "romantic, intimate",
    "悬疑": "mysterious, intriguing",
    "悲伤": "sad, melancholic",
    "愤怒": "angry, intense",
    "日常": "calm, everyday",
    "中性": "neutral, observational",
    "Neutral": "neutral, observational",
    "Shock": "shocked, dramatic",
    "Tension": "tense, suspenseful",
    "Sadness": "sad, melancholic",
    "Warmth": "warm, heartwarming",
}


class PromptRenderer:
    """
    纯英文槽位化Prompt组装器。
    
    输入：校准后的Shot数据（字典）
    输出：纯英文Veo prompt字符串
    """

    def __init__(self, character_tags: dict[str, str] | None = None):
        """
        Args:
            character_tags: 角色英文描述标签
                {"苏念": "young Chinese woman, 20s, barista, plain apron", ...}
        """
        self.character_tags = character_tags or {}

    def render(self, shot_data: dict) -> str:
        """
        渲染单个镜头的Veo prompt。
        
        Args:
            shot_data: 校准后的Shot数据，包含：
                - shot_type: str (CU/MCU/MS/WS)
                - camera_movement: str (static/push/pull/handheld)
                - camera_angle: str (eye-level/low/high)
                - lighting: str (Natural/Warm/Low key)
                - emotion: str
                - characters: list[str]
                - action_visual: str (英文或待翻译的中文)
                - dialogue: str
                - location: str
                - visual_anchors: list[str]
                
        Returns:
            纯英文Veo prompt字符串
        """
        parts = []

        # 1. Camera spec
        shot_type = shot_data.get("shot_type", "MS")
        camera_move = shot_data.get("camera_movement", "static")
        angle = shot_data.get("camera_angle", "eye-level")

        shot_en = SHOT_TYPE_EN.get(shot_type, "medium shot")
        camera_en = CAMERA_MOVE_EN.get(camera_move, "static camera")
        angle_en = ANGLE_EN.get(angle, "eye level")

        parts.append(f"{shot_en}, {camera_en}, {angle_en}")

        # 2. Subject (characters with physical tags)
        characters = shot_data.get("characters", [])
        if characters:
            char_parts = []
            for char_name in characters:
                tag = self.character_tags.get(char_name, "")
                if tag:
                    char_parts.append(f"{char_name} ({tag})")
                else:
                    char_parts.append(char_name)
            parts.append(f"featuring {', '.join(char_parts)}")

        # 3. Visible action (must be English, filmable)
        action = shot_data.get("action_visual", "")
        if action:
            # 如果还是中文，直接使用（后续由SemanticCalibrator翻译）
            parts.append(action)

        # 4. Visual anchors
        anchors = shot_data.get("visual_anchors", [])
        if anchors:
            anchor_desc = ", ".join(anchors)
            parts.append(f"close-up detail on {anchor_desc}")

        # 5. Location
        location = shot_data.get("location", "")
        if location:
            parts.append(f"in {location}")

        # 6. Lighting
        lighting = shot_data.get("lighting", "Natural")
        lighting_en = LIGHTING_EN.get(lighting, "natural daylight, soft shadows")
        parts.append(lighting_en)

        # 7. Mood
        emotion = shot_data.get("emotion", "中性")
        mood_en = MOOD_EN.get(emotion, "neutral, observational")
        parts.append(mood_en)

        # 8. Tech specs
        parts.append("cinematic, 9:16 vertical, photorealistic, 4K")

        return ", ".join(parts)

    def render_with_dialogue(self, shot_data: dict) -> dict:
        """
        渲染带分离对话的prompt。
        
        Returns:
            {
                "veo_prompt": "...",  # 纯视觉prompt
                "dialogue_line": "...",  # 台词（如有）
                "inner_voice": "...",  # 心声（如有）
            }
        """
        veo_prompt = self.render(shot_data)

        return {
            "veo_prompt": veo_prompt,
            "dialogue_line": shot_data.get("dialogue", ""),
            "inner_voice": shot_data.get("inner_voice", ""),
        }

    def format_shot_block(self, shot_data: dict) -> str:
        """
        格式化为可读的镜头描述块（用于调试/审查）。
        """
        shot_id = shot_data.get("shot_id", "?")
        pacing = shot_data.get("pacing_label", "")
        duration = shot_data.get("duration", 0)
        shot_type = shot_data.get("shot_type", "MS")
        camera = shot_data.get("camera_movement", "static")
        location = shot_data.get("location", "")
        characters = shot_data.get("characters", [])
        action = shot_data.get("action_visual", "")
        dialogue = shot_data.get("dialogue", "")
        anchors = shot_data.get("visual_anchors", [])

        lines = [f"## Shot {shot_id} | {pacing} ({duration}s)"]
        lines.append(f"- Camera: [{shot_type}] [{camera}]")
        lines.append(f"- Location: {location}")
        lines.append(f"- Characters: {', '.join(characters) if characters else 'none'}")
        lines.append(f"- Action: {action}")
        if dialogue:
            lines.append(f"- Dialogue: {dialogue}")
        if anchors:
            lines.append(f"- Anchors: {', '.join(anchors)}")
        lines.append(f"- Veo: {self.render(shot_data)[:120]}...")

        return "\n".join(lines)
