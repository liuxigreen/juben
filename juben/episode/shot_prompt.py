"""
Shot Prompt Generator — 分镜提示词生成器（v3 双风格版）

从Episode结构生成可直接喂给Kling/Runway/Veo的提示词。
新增：
- visual_tags 注入（从characters.json查表，零LLM调用）
- 双风格渲染（realistic / comedy）
- style_suffix 全局滤镜
- final_render_prompt 最终输出

6组件结构：Subject + Action + Setting + Camera + Lighting + Mood
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .schema import (
    Episode, Shot, ShotType, CameraMovement, CameraAngle,
    RenderStyle, REALISTIC_SUFFIX, COMEDY_SUFFIX,
)


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

# 视觉风格预设
DEFAULT_STYLE = "cinematic, 4K, photorealistic, film grain, dramatic lighting"


def load_visual_styles(config_path: str | Path | None = None) -> dict:
    """加载视觉风格预设"""
    if config_path is None:
        config_path = Path.home() / "juben" / ".config" / "visual_styles.json"
    
    config_path = Path(config_path)
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return {s["id"]: s for s in data.get("styles", [])}
    return {}


def load_character_visual_tags(project_dir: str | Path) -> dict[str, dict[str, str]]:
    """
    从characters.json加载角色visual_tags。

    Returns:
        {"林默": {"realistic": "...", "comedy": "..."}, ...}
    """
    project_dir = Path(project_dir)
    chars_file = project_dir / "characters.json"
    if not chars_file.exists():
        return {}

    data = json.loads(chars_file.read_text())
    result = {}
    for char in data.get("characters", []):
        name = char.get("name", "")
        tags = char.get("visual_tags", {})
        if name and tags:
            result[name] = tags
    return result


class ShotPromptGenerator:
    """分镜提示词生成器（v3 双风格版）"""

    def __init__(
        self,
        style_id: int = 1,
        render_style: RenderStyle = RenderStyle.REALISTIC,
        config_path: str | Path | None = None,
        project_dir: str | Path | None = None,
    ):
        self.styles = load_visual_styles(config_path)
        self.style = self.styles.get(style_id, {})
        self.style_anchor = self.style.get("prompt_suffix", DEFAULT_STYLE)
        self.render_style = render_style

        # 加载角色visual_tags（零LLM调用，纯查表）
        self.character_tags: dict[str, dict[str, str]] = {}
        if project_dir:
            self.character_tags = load_character_visual_tags(project_dir)

    def generate_episode_prompts(self, episode: Episode) -> list[dict]:
        """
        为整个Episode生成分镜提示词包。

        Returns:
            [
                {
                    "shot_id": 1,
                    "visual_prompt": "...",  # 6组件视觉prompt
                    "character_tags": "...", # 角色材质标签
                    "style_suffix": "...",   # 风格后缀
                    "final_render_prompt": "...", # 最终渲染prompt
                    "audio_prompt": "...",
                    "duration": 3.0,
                    "shot_type": "CU",
                    "camera_movement": "PUSH",
                    "pacing_label": "Hook",
                    "location": "...",
                    "characters_present": [...],
                },
                ...
            ]
        """
        prompts = []
        total_shots = len(episode.shots)
        
        for i, shot in enumerate(episode.shots):
            is_last = (i == total_shots - 1)

            # 查表获取角色visual_tags（零LLM调用）
            char_tags = self._lookup_character_tags(shot)

            # 风格后缀
            style_suffix = REALISTIC_SUFFIX if self.render_style == RenderStyle.REALISTIC else COMEDY_SUFFIX

            # 6组件视觉prompt
            visual_prompt = self._build_visual_prompt(shot)

            # 最终渲染prompt = character_tags + visual + style_suffix
            final_parts = [p for p in [char_tags, visual_prompt, style_suffix] if p]
            final_render_prompt = ", ".join(final_parts)

            prompts.append({
                "shot_id": shot.shot_id,
                "visual_prompt": visual_prompt,
                "character_tags": char_tags,
                "style_suffix": style_suffix,
                "final_render_prompt": final_render_prompt,
                "audio_prompt": shot.to_audio_prompt() if hasattr(shot, 'to_audio_prompt') else "",
                "duration": shot.duration,
                "shot_type": shot.shot_type.value if shot.shot_type else "MCU",
                "camera_movement": shot.camera_movement.value if shot.camera_movement else "STATIC",
                "pacing_label": shot.pacing_label if hasattr(shot, 'pacing_label') else "",
                "location": shot.location if hasattr(shot, 'location') else "",
                "characters_present": shot.characters_present if hasattr(shot, 'characters_present') else [],
            })
        return prompts

    def _lookup_character_tags(self, shot: Shot) -> str:
        """
        从characters.json查表获取角色visual_tags。
        零LLM调用，纯字符串匹配。
        """
        style_key = self.render_style.value  # "realistic" or "comedy"

        # 从shot.characters_present获取出场角色
        characters = shot.characters_present if hasattr(shot, 'characters_present') else []

        # 如果没有指定角色，尝试从shot.subject推断
        if not characters and shot.subject:
            for char_name in self.character_tags:
                if char_name in shot.subject:
                    characters.append(char_name)

        # 查表
        tags = []
        for char_name in characters:
            if char_name in self.character_tags:
                char_tag = self.character_tags[char_name].get(style_key, "")
                if char_tag:
                    tags.append(char_tag)

        return ", ".join(tags) if tags else ""

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
                # 新增：visual_tags
                if vc.visual_tags:
                    block += f"VISUAL_TAGS: {vc.visual_tags}\n"
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

            # 查表获取角色tags
            char_tags = self._lookup_character_tags(shot)

            line = f"Shot {shot.shot_id} ({shot.duration}s): "
            line += f"{shot_desc}, {camera_desc}. "
            if char_tags:
                line += f"[{char_tags}]. "
            if hasattr(shot, 'subject') and shot.subject:
                line += f"{shot.subject}. "
            if hasattr(shot, 'action') and shot.action:
                line += f"{shot.action}. "
            if hasattr(shot, 'dialogue') and shot.dialogue:
                line += f'Dialogue: "{shot.dialogue}". '
            lines.append(line)

        return "\n".join(lines)

    def to_runway_format(self, episode: Episode) -> list[dict]:
        """
        生成Runway Gen-3格式的prompt列表。
        """
        results = []
        for shot in episode.shots:
            char_tags = self._lookup_character_tags(shot)
            visual = self._build_visual_prompt(shot)
            suffix = REALISTIC_SUFFIX if self.render_style == RenderStyle.REALISTIC else COMEDY_SUFFIX

            final_parts = [p for p in [char_tags, visual, suffix] if p]

            results.append({
                "shot_id": shot.shot_id,
                "prompt": ", ".join(final_parts),
                "duration": shot.duration,
                "camera": CAMERA_MOVE_DESC.get(shot.camera_movement, "static camera"),
            })
        return results

    def to_seedance_task(self, episode: Episode, character_refs: list[str] = None, scene_refs: list[str] = None) -> dict:
        """
        生成Seedance任务格式。
        参考Micro-Drama-Skills的(@文件名)引用方式。
        """
        task = {
            "episode_id": episode.episode_id if hasattr(episode, 'episode_id') else 0,
            "shots": [],
            "style": self.style.get("name", "Cinematic Film"),
            "render_style": self.render_style.value,
        }
        
        # 添加角色引用
        if character_refs:
            task["character_refs"] = character_refs
        
        # 添加场景引用
        if scene_refs:
            task["scene_refs"] = scene_refs
        
        for shot in episode.shots:
            char_tags = self._lookup_character_tags(shot)
            visual = self._build_visual_prompt(shot)
            suffix = REALISTIC_SUFFIX if self.render_style == RenderStyle.REALISTIC else COMEDY_SUFFIX
            final_parts = [p for p in [char_tags, visual, suffix] if p]

            shot_data = {
                "shot_id": shot.shot_id,
                "duration": shot.duration,
                "visual_prompt": visual,
                "character_tags": char_tags,
                "style_suffix": suffix,
                "final_render_prompt": ", ".join(final_parts),
            }
            if hasattr(shot, 'dialogue') and shot.dialogue:
                shot_data["dialogue"] = shot.dialogue
            task["shots"].append(shot_data)
        
        return task
