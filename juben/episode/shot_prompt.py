"""
Shot Prompt Generator — 分镜提示词生成器（v2）

从Episode结构生成可直接喂给Kling/Runway/Veo的提示词。
6组件结构：Subject + Action + Setting + Camera + Lighting + Mood

参考：
- Micro-Drama-Skills的视觉风格预设
- 0xsline的节奏曲线和钩子类型
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

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

# 光影英文描述
LIGHTING_DESC = {
    "Low key": "low key lighting, deep shadows, dim, mysterious",
    "Warm": "warm golden light, soft, inviting",
    "High contrast": "high contrast dramatic lighting, harsh shadows, chiaroscuro",
    "Natural": "natural daylight, soft shadows",
    "Neon": "neon lights, colorful, cyberpunk",
    "Moonlight": "cold blue moonlight, silver tones",
}

# 情绪英文描述
MOOD_DESC = {
    "震惊": "shocked, dramatic, high tension",
    "恐惧": "fearful, tense, suspenseful",
    "愤怒": "angry, intense, aggressive",
    "悲伤": "sad, melancholic, emotional",
    "爽感": "satisfying, triumphant, empowering",
    "悬念": "mysterious, suspenseful, intriguing",
    "甜蜜": "romantic, sweet, heartwarming",
    "紧张": "tense, anxious, high stakes",
    "中性": "neutral, calm, observational",
}

# 视觉风格预设（从.visual_styles.json加载）
DEFAULT_STYLE = "cinematic, 4K, photorealistic, film grain, dramatic lighting"


def load_visual_styles(config_path: str | Path = None) -> dict:
    """加载视觉风格预设"""
    if config_path is None:
        config_path = Path.home() / "juben" / ".config" / "visual_styles.json"
    
    config_path = Path(config_path)
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return {s["id"]: s for s in data.get("styles", [])}
    return {}


class ShotPromptGenerator:
    """分镜提示词生成器（v2）"""

    def __init__(self, style_id: int = 1, config_path: str | Path = None):
        self.styles = load_visual_styles(config_path)
        self.style = self.styles.get(style_id, {})
        self.style_anchor = self.style.get("prompt_suffix", DEFAULT_STYLE)

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
                    "camera_movement": "PUSH",
                    "pacing_label": "Hook",
                    "hook_type": "悬念钩",  # 仅最后镜头
                },
                ...
            ]
        """
        prompts = []
        total_shots = len(episode.shots)
        
        for i, shot in enumerate(episode.shots):
            is_last = (i == total_shots - 1)
            prompts.append({
                "shot_id": shot.shot_id,
                "visual_prompt": self._build_visual_prompt(shot),
                "audio_prompt": shot.to_audio_prompt() if hasattr(shot, 'to_audio_prompt') else "",
                "duration": shot.duration,
                "shot_type": shot.shot_type.value if shot.shot_type else "MCU",
                "camera_movement": shot.camera_movement.value if shot.camera_movement else "STATIC",
                "pacing_label": shot.pacing_label if hasattr(shot, 'pacing_label') else "",
                "hook_type": shot.hook_type if is_last and hasattr(shot, 'hook_type') else None,
            })
        return prompts

    def _build_visual_prompt(self, shot: Shot) -> str:
        """构建单个镜头的视觉Prompt（6组件结构）"""
        parts = []

        # 1. 景别+运镜+角度
        shot_desc = SHOT_TYPE_DESC.get(shot.shot_type, "medium shot") if shot.shot_type else "medium shot"
        camera_desc = CAMERA_MOVE_DESC.get(shot.camera_movement, "static camera") if shot.camera_movement else "static camera"
        angle_desc = CAMERA_ANGLE_DESC.get(shot.camera_angle, "eye level") if shot.camera_angle else "eye level"
        parts.append(f"{shot_desc}, {camera_desc}, {angle_desc}")

        # 2. 主体（Subject）
        if hasattr(shot, 'subject') and shot.subject:
            parts.append(shot.subject)

        # 3. 动作（Action）
        if hasattr(shot, 'action') and shot.action:
            parts.append(shot.action)

        # 4. 场景（Setting）
        if hasattr(shot, 'setting') and shot.setting:
            parts.append(shot.setting)

        # 5. 光影（Lighting）
        if hasattr(shot, 'lighting') and shot.lighting:
            lighting_desc = LIGHTING_DESC.get(shot.lighting, shot.lighting)
            parts.append(lighting_desc)
        else:
            # 根据情绪推断默认光影
            mood = shot.mood if hasattr(shot, 'mood') else ""
            lighting = self._infer_lighting(mood)
            if lighting:
                parts.append(lighting)

        # 6. 情绪/色彩（Mood）
        if hasattr(shot, 'mood') and shot.mood:
            mood_desc = MOOD_DESC.get(shot.mood, f"{shot.mood} mood")
            parts.append(mood_desc)

        # 风格锚点（每条prompt固定）
        parts.append(self.style_anchor)

        # 9:16竖屏
        parts.append("9:16 vertical format")

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
            "紧张": "high contrast, dramatic shadows",
            "甜蜜": "soft warm golden hour light",
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
        if hasattr(episode, 'visual_consistency'):
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
            shot_desc = SHOT_TYPE_DESC.get(shot.shot_type, "medium shot") if shot.shot_type else "medium shot"
            camera_desc = CAMERA_MOVE_DESC.get(shot.camera_movement, "static camera") if shot.camera_movement else "static camera"

            line = f"Shot {shot.shot_id} ({shot.duration}s): "
            line += f"{shot_desc}, {camera_desc}. "
            if hasattr(shot, 'subject') and shot.subject:
                line += f"{shot.subject}. "
            if hasattr(shot, 'action') and shot.action:
                line += f"{shot.action}. "
            if hasattr(shot, 'dialogue') and shot.dialogue:
                line += f'Dialogue: "{shot.dialogue}". '
            lines.append(line)

        return "\n".join(lines)

    def to_seedance_task(self, episode: Episode, character_refs: list[str] = None, scene_refs: list[str] = None) -> dict:
        """
        生成Seedance任务格式。
        参考Micro-Drama-Skills的(@文件名)引用方式。
        """
        task = {
            "episode_id": episode.episode_id if hasattr(episode, 'episode_id') else 0,
            "shots": [],
            "style": self.style.get("name", "Cinematic Film"),
        }
        
        # 添加角色引用
        if character_refs:
            task["character_refs"] = character_refs
        
        # 添加场景引用
        if scene_refs:
            task["scene_refs"] = scene_refs
        
        for shot in episode.shots:
            shot_data = {
                "shot_id": shot.shot_id,
                "duration": shot.duration,
                "visual_prompt": self._build_visual_prompt(shot),
            }
            if hasattr(shot, 'dialogue') and shot.dialogue:
                shot_data["dialogue"] = shot.dialogue
            task["shots"].append(shot_data)
        
        return task
