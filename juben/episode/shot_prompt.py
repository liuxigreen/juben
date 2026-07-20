"""
Shot Prompt Generator — 分镜提示词生成器

从Episode结构生成可直接喂给Kling/Runway/Veo的提示词。
6组件结构：Subject + Action + Setting + Camera + Lighting + Mood
"""
from __future__ import annotations

from typing import Any

from .schema import Episode, Shot, ShotType, CameraMovement, CameraAngle


# 景别英文描述
SHOT_TYPE_DESC = {
    ShotType.ECU: "extreme close-up",
    ShotType.CU: "close-up",
    ShotType.MCU: "medium close-up",
    ShotType.MS: "medium shot",
    ShotType.FS: "full shot",
    ShotType.EWS: "extreme wide shot",
}

# 运镜英文描述
CAMERA_MOVE_DESC = {
    CameraMovement.STATIC: "static camera",
    CameraMovement.PUSH: "slow dolly forward",
    CameraMovement.PULL: "slow dolly backward",
    CameraMovement.PAN: "horizontal pan",
    CameraMovement.TILT: "vertical tilt",
    CameraMovement.DOLLY: "dolly tracking",
    CameraMovement.TRACKING: "tracking shot",
    CameraMovement.CRANE: "crane shot ascending",
    CameraMovement.HANDHELD: "handheld camera, slight shake",
    CameraMovement.ZOOM: "slow zoom in",
}

# 机位角度英文描述
CAMERA_ANGLE_DESC = {
    CameraAngle.EYE_LEVEL: "eye level",
    CameraAngle.LOW: "low angle",
    CameraAngle.HIGH: "high angle",
    CameraAngle.DUTCH: "Dutch angle",
    CameraAngle.OVERHEAD: "overhead shot",
}


class ShotPromptGenerator:
    """分镜提示词生成器"""

    def __init__(self, style_anchor: str = "cinematic, 4K, photorealistic"):
        self.style_anchor = style_anchor

    def generate_episode_prompts(self, episode: Episode) -> list[dict]:
        """
        为整个Episode生成分镜提示词包。

        Returns:
            [
                {
                    "shot_id": 1,
                    "visual_prompt": "...",  # 可直接喂视频模型
                    "audio_prompt": "...",
                    "duration": 3.0,
                    "shot_type": "CU",
                    "pacing_label": "3s_Hook",
                },
                ...
            ]
        """
        prompts = []
        for shot in episode.shots:
            prompts.append({
                "shot_id": shot.shot_id,
                "visual_prompt": self._build_visual_prompt(shot),
                "audio_prompt": shot.to_audio_prompt(),
                "duration": shot.duration,
                "shot_type": shot.shot_type.value,
                "camera_movement": shot.camera_movement.value,
                "pacing_label": shot.pacing_label,
            })
        return prompts

    def _build_visual_prompt(self, shot: Shot) -> str:
        """构建单个镜头的视觉Prompt（6组件结构）"""
        parts = []

        # 1. 景别+运镜
        shot_desc = SHOT_TYPE_DESC.get(shot.shot_type, "medium shot")
        camera_desc = CAMERA_MOVE_DESC.get(shot.camera_movement, "static camera")
        angle_desc = CAMERA_ANGLE_DESC.get(shot.camera_angle, "eye level")
        parts.append(f"{shot_desc}, {camera_desc}, {angle_desc}")

        # 2. 主体
        if shot.subject:
            parts.append(shot.subject)

        # 3. 动作
        if shot.action:
            parts.append(shot.action)

        # 4. 场景
        if shot.setting:
            parts.append(shot.setting)

        # 5. 光影
        if shot.lighting:
            parts.append(shot.lighting)
        else:
            # 根据情绪推断默认光影
            lighting = self._infer_lighting(shot.mood)
            if lighting:
                parts.append(lighting)

        # 6. 情绪/色彩
        if shot.mood:
            parts.append(f"{shot.mood} mood")

        # 风格锚点（每条prompt固定）
        parts.append(self.style_anchor)

        return ", ".join(parts)

    def _infer_lighting(self, mood: str) -> str:
        """根据情绪推断光影"""
        mood_lighting = {
            "震惊": "high contrast dramatic lighting, harsh shadows",
            "恐惧": "low key lighting, deep shadows, dim",
            "愤怒": "warm red tones, dramatic side lighting",
            "悲伤": "soft diffused lighting, cool blue tones",
            "爽感": "bright warm golden light, rim light",
            "悬念": "chiaroscuro, single light source, mysterious",
            "中性": "natural daylight, soft shadows",
        }
        for key, lighting in mood_lighting.items():
            if key in mood:
                return lighting
        return "natural lighting"

    def generate_reference_block(self, episode: Episode) -> str:
        """
        生成角色参考描述块（用于Element Library绑定）。
        格式：IDENTITY/BODY/FACE/ATTIRE/LAYOUT/STYLE
        """
        blocks = []
        for vc in episode.visual_consistency:
            block = f"## {vc.character_name}\n"
            block += f"IDENTITY: {vc.character_name}\n"
            if vc.appearance:
                block += f"BODY: {vc.appearance}\n"
            if vc.default_attire:
                block += f"ATTIRE: {vc.default_attire}\n"
            if vc.voice_tone:
                block += f"VOICE: {vc.voice_tone}\n"
            block += "STYLE: photorealistic, cinematic, consistent across all shots\n"
            blocks.append(block)

        return "\n".join(blocks)

    def to_kling_multishot(self, episode: Episode) -> str:
        """
        生成Kling 3.0 Multi-Shot格式的prompt。
        可直接粘贴到Kling的Custom Multi-Shot输入框。
        """
        lines = []
        for shot in episode.shots:
            shot_desc = SHOT_TYPE_DESC.get(shot.shot_type, "medium shot")
            camera_desc = CAMERA_MOVE_DESC.get(shot.camera_movement, "static camera")

            line = f"Shot {shot.shot_id} ({shot.duration}s): "
            line += f"{shot_desc}, {camera_desc}. "
            if shot.subject:
                line += f"{shot.subject}. "
            if shot.action:
                line += f"{shot.action}. "
            if shot.dialogue:
                line += f'Dialogue: "{shot.dialogue}". '
            lines.append(line)

        return "\n".join(lines)
