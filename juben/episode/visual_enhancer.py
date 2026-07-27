"""
Visual Enhancer — LLM画面增强器

SmartAdapter出骨架 → 小prompt补画面 → Veo优化输出

设计原则：
  1. 只补画面（15-40字可拍摄动作），不动结构
  2. 每次prompt只处理1个镜头，500token以内
  3. 输出直接对齐Google Veo prompt规范
  4. 角色外貌从characters.json查表注入
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .schema import Episode, Shot, ShotType, CameraMovement, CameraAngle, RenderStyle

logger = logging.getLogger(__name__)


# Veo专用prompt模板（每个镜头一次调用，~400token）
VEO_SHOT_PROMPT = """你是竖屏短剧的分镜导演。把以下镜头骨架改写成电影级画面描述。

## 镜头骨架
- 景别: {shot_type}
- 运镜: {camera_movement}
- 视角: {camera_angle}
- 光影: {lighting}
- 位置: {location}
- 情绪: {emotion}
- 原始动作: {raw_action}
- 原始台词: {raw_dialogue}
- 视觉图腾: {visual_anchors}
- 出场角色: {characters}

## 角色外貌参考
{character_descriptions}

## 输出要求（严格遵守）
1. **visual_action**: 15-40字，只能写摄像机能拍到的物理动作和表情微变化，禁止心理描写
2. **camera_direction**: 运镜指令，英文，如"slow dolly in to CU on trembling fingers"
3. **lighting_setup**: 光影指令，英文，如"warm golden side light, soft shadows"
4. **sound_design**: 音效/环境音，英文，如"ventilation fan hum, distant traffic"
5. **dialogue_line**: 如有台词，保持原文；无则留空
6. **veo_prompt**: 组合以上所有元素，生成一个完整的Veo视频生成prompt（英文，50-80词）

如命中视觉图腾（如杯沿唇印、疤痕），必须在画面中给特写。

请用JSON格式输出：
```json
{{
  "visual_action": "...",
  "camera_direction": "...",
  "lighting_setup": "...",
  "sound_design": "...",
  "dialogue_line": "...",
  "veo_prompt": "..."
}}
```"""


# 角色外貌描述模板
CHARACTER_DESC_TEMPLATE = """{name} ({role}): {appearance}. 默认服装: {attire}. 声线: {voice}."""


class VisualEnhancer:
    """
    LLM画面增强器。
    
    接收SmartAdapter的骨架输出，用小prompt逐镜头增强画面描述。
    输出对齐Google Veo prompt规范。
    """

    def __init__(
        self,
        project_dir: str | Path,
        llm_fn=None,
        render_style: RenderStyle = RenderStyle.REALISTIC,
    ):
        """
        Args:
            project_dir: 项目目录
            llm_fn: LLM调用函数，签名 llm_fn(prompt: str) -> str
                    如果为None，则跳过LLM增强，只做格式转换
            render_style: 渲染风格
        """
        self.project_dir = Path(project_dir)
        self.llm_fn = llm_fn
        self.render_style = render_style

        # 加载角色描述
        self.character_descriptions = self._load_character_descriptions()

    def _load_character_descriptions(self) -> str:
        """从characters.json加载角色外貌描述"""
        chars_file = self.project_dir / "characters.json"
        if not chars_file.exists():
            return "（无角色信息）"

        data = json.loads(chars_file.read_text())
        lines = []
        for char in data.get("characters", []):
            name = char.get("name", "")
            role = char.get("role", "配角")
            appearance = char.get("appearance", {})
            desc = CHARACTER_DESC_TEMPLATE.format(
                name=name,
                role=role,
                appearance=appearance.get("description", "无描述"),
                attire=appearance.get("attire", "日常服装"),
                voice=char.get("voice", "正常语速"),
            )
            lines.append(desc)

        return "\n".join(lines) if lines else "（无角色信息）"

    def enhance_episode(self, episode: Episode) -> Episode:
        """
        增强整个Episode的画面描述。
        
        对每个镜头：
        1. 构建小prompt（~400token）
        2. 调用LLM获取增强画面
        3. 更新Shot的action/lighting/audio_prompt字段
        4. 生成Veo prompt
        """
        for shot in episode.shots:
            enhanced = self._enhance_shot(shot)
            if enhanced:
                # 更新Shot字段
                shot.action = enhanced.get("visual_action", shot.action)
                shot.lighting = enhanced.get("lighting_setup", shot.lighting)
                shot.audio_prompt = enhanced.get("sound_design", shot.audio_prompt)
                shot.dialogue = enhanced.get("dialogue_line", shot.dialogue)

                # 存储Veo prompt到shot的扩展属性
                shot._veo_prompt = enhanced.get("veo_prompt", "")
                shot._camera_direction = enhanced.get("camera_direction", "")

        return episode

    def _enhance_shot(self, shot: Shot) -> dict | None:
        """增强单个镜头"""
        # 构建prompt
        prompt = self._build_shot_prompt(shot)

        if self.llm_fn:
            # 调用LLM
            try:
                response = self.llm_fn(prompt)
                return self._parse_response(response)
            except Exception as e:
                logger.warning(f"Shot {shot.shot_id} LLM enhancement failed: {e}")
                return self._fallback_enhancement(shot)
        else:
            # 无LLM，用规则增强
            return self._fallback_enhancement(shot)

    def _build_shot_prompt(self, shot: Shot) -> str:
        """构建单镜头的LLM prompt"""
        anchors = shot.visual_anchors if hasattr(shot, 'visual_anchors') else []
        characters = shot.characters_present if hasattr(shot, 'characters_present') else []

        return VEO_SHOT_PROMPT.format(
            shot_type=shot.shot_type.value if shot.shot_type else "MCU",
            camera_movement=shot.camera_movement.value if shot.camera_movement else "static",
            camera_angle=shot.camera_angle.value if shot.camera_angle else "eye-level",
            lighting=shot.lighting or "Natural",
            location=shot.location or "未标注",
            emotion=shot.emotion_tag or shot.mood or "中性",
            raw_action=shot.action or "（无动作描述）",
            raw_dialogue=shot.dialogue or "（无台词）",
            visual_anchors=", ".join(anchors) if anchors else "无",
            characters=", ".join(characters) if characters else "未指定",
            character_descriptions=self.character_descriptions,
        )

    @staticmethod
    def _parse_response(response: str) -> dict:
        """解析LLM的JSON响应"""
        # 尝试提取JSON
        import re
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 兜底：按行解析
        result = {}
        for line in response.split('\n'):
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip().strip('"').strip("'")
                value = value.strip().strip('"').strip("'").strip(',')
                if key in ('visual_action', 'camera_direction', 'lighting_setup',
                          'sound_design', 'dialogue_line', 'veo_prompt'):
                    result[key] = value

        return result

    def _fallback_enhancement(self, shot: Shot) -> dict:
        """无LLM时的规则增强（生成Veo格式prompt）"""
        # 构建Veo prompt（英文）
        parts = []

        # 景别+运镜
        shot_desc = self._shot_type_english(shot.shot_type)
        camera_desc = self._camera_english(shot.camera_movement)
        angle_desc = self._angle_english(shot.camera_angle)
        parts.append(f"{shot_desc}, {camera_desc}, {angle_desc}")

        # 角色
        if shot.characters_present:
            parts.append(f"featuring {', '.join(shot.characters_present)}")

        # 动作
        if shot.action:
            parts.append(shot.action)

        # 光影
        if shot.lighting:
            parts.append(f"{shot.lighting} lighting")

        # 情绪
        mood = shot.emotion_tag or shot.mood
        if mood:
            parts.append(f"{mood} mood")

        # 图腾特写
        anchors = shot.visual_anchors if hasattr(shot, 'visual_anchors') else []
        if anchors:
            parts.append(f"close-up on {', '.join(anchors)}")

        # 风格
        parts.append("cinematic, 9:16 vertical, photorealistic, 4K")

        veo_prompt = ", ".join(parts)

        return {
            "visual_action": shot.action,
            "camera_direction": f"{camera_desc} to {shot_desc}",
            "lighting_setup": f"{shot.lighting} lighting" if shot.lighting else "natural lighting",
            "sound_design": shot.audio_prompt or "ambient room tone",
            "dialogue_line": shot.dialogue,
            "veo_prompt": veo_prompt,
        }

    @staticmethod
    def _shot_type_english(shot_type) -> str:
        mapping = {
            "ECU": "extreme close-up",
            "CU": "close-up",
            "MCU": "medium close-up",
            "MS": "medium shot",
            "FS": "full shot",
            "EWS": "extreme wide shot",
        }
        val = shot_type.value if hasattr(shot_type, 'value') else str(shot_type)
        return mapping.get(val, "medium shot")

    @staticmethod
    def _camera_english(camera) -> str:
        mapping = {
            "static": "static camera",
            "push": "slow dolly forward",
            "pull": "slow dolly backward",
            "handheld": "handheld camera with slight shake",
            "pan": "horizontal pan",
            "tracking": "tracking shot",
        }
        val = camera.value if hasattr(camera, 'value') else str(camera)
        return mapping.get(val, "static camera")

    @staticmethod
    def _angle_english(angle) -> str:
        mapping = {
            "eye-level": "eye level",
            "low": "low angle looking up",
            "high": "high angle looking down",
            "Dutch": "Dutch angle",
            "overhead": "overhead top-down",
        }
        val = angle.value if hasattr(angle, 'value') else str(angle)
        return mapping.get(val, "eye level")

    def get_veo_prompts(self, episode: Episode) -> list[dict]:
        """
        提取所有镜头的Veo prompt。
        
        Returns:
            [{"shot_id": 1, "veo_prompt": "...", "duration": 5.0, ...}, ...]
        """
        results = []
        for shot in episode.shots:
            veo_prompt = getattr(shot, '_veo_prompt', '')
            if not veo_prompt:
                # 用fallback生成
                enhanced = self._fallback_enhancement(shot)
                veo_prompt = enhanced.get("veo_prompt", "")

            results.append({
                "shot_id": shot.shot_id,
                "veo_prompt": veo_prompt,
                "duration": shot.duration,
                "shot_type": shot.shot_type.value if shot.shot_type else "MCU",
                "camera_movement": shot.camera_movement.value if shot.camera_movement else "static",
                "camera_direction": getattr(shot, '_camera_direction', ''),
                "location": shot.location,
                "characters": shot.characters_present,
                "visual_anchors": shot.visual_anchors if hasattr(shot, 'visual_anchors') else [],
                "dialogue": shot.dialogue,
            })

        return results
