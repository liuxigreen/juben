"""
SmartAdapter v3 — 通用AI分镜与镜头编译引擎（最终版）

流水线：
  1. VisualBeatChunker（LLM一次调用切10-20个Visual Beat）
  2. SmartShotCompiler（Python状态机：景别/运镜/时长/防复读）
  3. PromptRenderer（纯英文槽位化prompt）
  4. StoryboardLint（质量闸门）

LLM负责理解（切Beat），Python负责计算（选镜头）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from .episode.schema import (
    CameraAngle, CameraMovement, Cliffhanger, Episode,
    PacingCheckpoint, PacingLabel, RenderStyle,
    Shot, ShotType, VisualConsistency,
)
from .episode.rhythm import RhythmValidator
from .visual_beat_chunker import VisualBeatChunker
from .prompt_renderer import PromptRenderer
from .storyboard_lint import StoryboardLint

logger = logging.getLogger(__name__)


# ============================================================
# 景别/运镜/光影映射
# ============================================================

SHOT_DUR_MIN = 3.0
SHOT_DUR_MAX = 7.5

EMOTION_SHOT_MAP = {
    "Shock": "CU", "Tension": "MCU", "Sadness": "MCU",
    "Warmth": "MS", "Neutral": "MS", "Mystery": "CU",
}

EMOTION_CAMERA_MAP = {
    "Shock": "rapid_push", "Tension": "push", "Sadness": "pull",
    "Warmth": "static", "Neutral": "static", "Mystery": "push",
}

EMOTION_LIGHTING_MAP = {
    "Shock": "High contrast", "Tension": "Low key", "Sadness": "Low key",
    "Warmth": "Warm", "Neutral": "Natural", "Mystery": "Low key",
}


class SmartShotCompiler:
    """
    Python状态机：把Visual Beat编译为镜头规格。
    
    职责：
    - 景别判定与连续ECU熔断
    - 运镜交替防复读
    - 时长物理钳位
    - 场景开头强卡WS/MS
    """

    def __init__(self):
        self.last_shot_type: str | None = None
        self.last_camera: str | None = None
        self.ecu_count: int = 0
        self.cu_count: int = 0

    def compile(
        self,
        beats: list[dict],
        target_duration: int = 90,
        location: str = "",
        max_shots: int = 25,
    ) -> list[dict]:
        """编译所有beat为镜头列表"""
        # 镜头数硬上限：合并相邻非关键beat
        if len(beats) > max_shots:
            beats = self._merge_beats(beats, max_shots)

        shots = []
        total_beats = len(beats)

        for i, beat in enumerate(beats):
            shot = self._compile_beat(beat, i, total_beats, target_duration, location)
            shots.append(shot)

        # 调整总时长（硬上限：不超过target的110%）
        self._adjust_duration(shots, target_duration)

        # 时长二次钳位：如果仍超标，强制压缩
        total = sum(s["duration"] for s in shots)
        if total > target_duration * 1.1:
            ratio = target_duration / total
            for s in shots:
                s["duration"] = round(max(SHOT_DUR_MIN, s["duration"] * ratio), 1)

        # 重置状态（每章独立）
        self.__init__()

        return shots

    @staticmethod
    def _merge_beats(beats: list[dict], max_count: int) -> list[dict]:
        """合并相邻非关键beat，使总数不超过max_count"""
        if len(beats) <= max_count:
            return beats

        # 优先保留：ability类型、有focus_object的、有dialogue的
        priority = []
        for i, beat in enumerate(beats):
            score = 0
            if beat.get("space") in ("Mental", "Transition"):
                score += 3
            if beat.get("focus_object"):
                score += 2
            if beat.get("spoken_dialogue"):
                score += 1
            priority.append((i, score))

        # 标记哪些beat必须独立保留（高优先级）
        keep = set()
        for i, score in sorted(priority, key=lambda x: -x[1]):
            if len(keep) >= max_count:
                break
            keep.add(i)

        # 合并未保留的beat到相邻beat
        merged = []
        buffer = None
        for i, beat in enumerate(beats):
            if i in keep:
                if buffer:
                    merged.append(buffer)
                    buffer = None
                merged.append(beat)
            else:
                if buffer:
                    # 合并到buffer
                    buffer["action_visual"] += " " + beat.get("action_visual", "")
                    if beat.get("spoken_dialogue") and not buffer.get("spoken_dialogue"):
                        buffer["spoken_dialogue"] = beat["spoken_dialogue"]
                    if beat.get("focus_object") and not buffer.get("focus_object"):
                        buffer["focus_object"] = beat["focus_object"]
                else:
                    buffer = dict(beat)  # copy

        if buffer:
            merged.append(buffer)

        return merged[:max_count]

    def _compile_beat(
        self,
        beat: dict,
        index: int,
        total: int,
        target: int,
        location: str,
    ) -> dict:
        """编译单个beat为镜头"""
        # --- 景别判定 ---
        shot_type = self._choose_shot_type(beat, index)

        # --- 运镜判定 ---
        camera = self._choose_camera(beat, shot_type)

        # --- 时长计算 ---
        duration = self._calculate_duration(beat, total, target)

        # --- 光影 ---
        emotion = beat.get("emotion", "Neutral")
        lighting = EMOTION_LIGHTING_MAP.get(emotion, "Natural")

        # --- 视角 ---
        angle = self._choose_angle(emotion)

        # --- 节奏卡点 ---
        pacing = self._assign_pacing(index, total)

        # --- 更新状态 ---
        self.last_shot_type = shot_type
        self.last_camera = camera
        if shot_type == "ECU":
            self.ecu_count += 1
        if shot_type == "CU":
            self.cu_count += 1

        return {
            "shot_id": index + 1,
            "pacing_label": pacing,
            "shot_type": shot_type,
            "camera_movement": camera,
            "camera_angle": angle,
            "duration": duration,
            "location": location,
            "space": beat.get("space", "Physical"),
            "characters": beat.get("characters_present", []),
            "action_visual": beat.get("action_visual", ""),
            "dialogue": beat.get("spoken_dialogue", ""),
            "inner_voice": beat.get("inner_voice", ""),
            "focus_object": beat.get("focus_object", ""),
            "lighting": lighting,
            "emotion": emotion,
            "visual_anchors": [beat.get("focus_object", "")] if beat.get("focus_object") else [],
        }

    def _choose_shot_type(self, beat: dict, index: int) -> str:
        """
        景别判定（含连续ECU熔断）。
        
        优先级：
        1. 第一镜头 → WS（场景建立）
        2. Mental空间 → CU
        3. focus_object + 能力事件 → ECU（受熔断限制）
        4. focus_object（普通） → CU
        5. 对话 → MCU
        6. 默认 → MS
        """
        # 第一镜头：场景建立
        if index == 0:
            return "WS"

        space = beat.get("space", "Physical")
        focus = beat.get("focus_object", "")
        has_dialogue = bool(beat.get("spoken_dialogue"))

        # Mental空间 → CU
        if space == "Mental":
            return "CU"

        # focus_object → ECU/CU（受熔断限制）
        if focus:
            # 连续ECU熔断：上一个也是ECU或本场已2个ECU → 降级为CU
            if self.last_shot_type == "ECU" or self.ecu_count >= 2:
                return "CU"
            return "ECU"

        # 对话 → MCU
        if has_dialogue:
            # 防复读
            if self.last_shot_type == "MCU":
                return "MS"
            return "MCU"

        # 情绪驱动
        emotion = beat.get("emotion", "Neutral")
        preferred = EMOTION_SHOT_MAP.get(emotion, "MS")

        # 防复读
        if preferred == self.last_shot_type:
            alt = {"CU": "MCU", "MCU": "MS", "MS": "MCU"}
            preferred = alt.get(preferred, "MCU")

        return preferred

    def _choose_camera(self, beat: dict, shot_type: str) -> str:
        """运镜判定（防复读）"""
        emotion = beat.get("emotion", "Neutral")
        preferred = EMOTION_CAMERA_MAP.get(emotion, "static")

        # 防复读
        if preferred == self.last_camera:
            alt = {"static": "push", "push": "static", "pull": "static", "rapid_push": "push"}
            preferred = alt.get(preferred, "static")

        return preferred

    @staticmethod
    def _choose_angle(emotion: str) -> str:
        if emotion in ("Shock", "Tension"):
            return "low"
        if emotion == "Sadness":
            return "high"
        return "eye-level"

    @staticmethod
    def _calculate_duration(beat: dict, total_beats: int, target: int) -> float:
        """时长计算（物理钳位3-7.5s）"""
        base = target / max(1, total_beats)

        # 内容密度调整
        action_len = len(beat.get("action_visual", ""))
        dialogue_len = len(beat.get("spoken_dialogue", ""))
        word_count = action_len + dialogue_len

        if word_count > 100:
            base *= 1.2
        elif word_count < 30:
            base *= 0.7

        # 能力事件/图腾镜头稍长
        if beat.get("space") == "Mental" or beat.get("focus_object"):
            base *= 1.1

        return round(max(SHOT_DUR_MIN, min(SHOT_DUR_MAX, base)), 1)

    @staticmethod
    def _assign_pacing(index: int, total: int) -> str:
        ratio = index / max(1, total - 1)
        if ratio <= 0.15:
            return "3s_Hook"
        elif ratio <= 0.35:
            return "15s_Retention"
        elif ratio <= 0.55:
            return "30s_Explosion"
        elif ratio <= 0.75:
            return "60s_Satisfaction"
        return "90s_Cliffhanger"

    @staticmethod
    def _adjust_duration(shots: list[dict], target: int):
        """调整总时长"""
        if not shots:
            return
        current = sum(s["duration"] for s in shots)
        if current <= 0:
            return
        ratio = target / current
        for s in shots:
            s["duration"] = round(
                max(SHOT_DUR_MIN, min(SHOT_DUR_MAX, s["duration"] * ratio)), 1
            )


# ============================================================
# 主适配器
# ============================================================

class SmartAdapterV3:
    """
    SmartAdapter v3 主适配器。
    
    用法：
        adapter = SmartAdapterV3(project_dir, llm_fn=my_llm)
        result = adapter.adapt(chapter_text, chapter_num=1)
    """

    def __init__(
        self,
        project_dir: str | Path,
        llm_fn: Callable[[str], str] | None = None,
        render_style: RenderStyle = RenderStyle.REALISTIC,
    ):
        self.project_dir = Path(project_dir)
        self.render_style = render_style

        # 加载项目配置
        self.characters = self._load_json("characters.json").get("characters", [])
        self.locations = self._load_json("locations.json")
        self.anchors = self._load_json("entity_anchors.json").get("anchors", [])

        # 初始化组件
        self.chunker = VisualBeatChunker(llm_fn=llm_fn, characters=self.characters)
        self.compiler = SmartShotCompiler()
        self.char_tags = self._build_character_tags()
        self.renderer = PromptRenderer(character_tags=self.char_tags)
        self.lint = StoryboardLint()
        self.validator = RhythmValidator()

        # 默认场景位置（从locations.json）
        self.default_location = self.locations.get("default_location", "")

    def _load_json(self, filename: str) -> dict:
        path = self.project_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _build_character_tags(self) -> dict[str, str]:
        tags = {}
        for char in self.characters:
            name = char.get("name", "")
            appearance = char.get("appearance", {})
            desc_parts = []
            if appearance.get("age"):
                desc_parts.append(f"{appearance['age']}")
            if appearance.get("description"):
                desc_parts.append(appearance["description"][:50])
            if appearance.get("attire"):
                desc_parts.append(appearance["attire"][:30])
            tags[name] = ", ".join(desc_parts) if desc_parts else name
        return tags

    def adapt(
        self,
        chapter_text: str,
        chapter_num: int,
        target_duration: int = 90,
    ) -> dict:
        """
        将纯剧本转换为分镜数据。
        
        流水线：
        1. VisualBeatChunker（LLM切Beat）
        2. SmartShotCompiler（Python编译镜头）
        3. PromptRenderer（英文prompt）
        4. StoryboardLint（质量检查）
        """
        # --- Step 1: LLM切Beat ---
        beats = self.chunker.chunk(chapter_text)
        logger.info(f"Ch{chapter_num}: {len(beats)} visual beats extracted")

        if not beats:
            logger.error(f"Ch{chapter_num}: No beats extracted!")
            return self._empty_result(chapter_num, chapter_text)

        # --- Step 2: Python编译镜头 ---
        location = self._detect_location(chapter_text) or self.default_location
        shots = self.compiler.compile(beats, target_duration, location)
        logger.info(f"Ch{chapter_num}: {len(shots)} shots compiled")

        # --- Step 3: 英文Prompt渲染 ---
        # 先翻译location
        raw_loc = shots[0].get("location", "") if shots else ""
        location_en = self._translate_location(raw_loc)
        for shot in shots:
            shot["location_en"] = location_en
            rendered = self.renderer.render_with_dialogue(shot)
            shot["veo_prompt"] = rendered["veo_prompt"]

        # --- Step 4: Lint质检 ---
        scene_locations = {i: location for i in range(len(beats))}
        violations = self.lint.check(shots, scene_locations)
        lint_pass = self.lint.is_pass(violations)

        if not lint_pass:
            logger.warning(f"Ch{chapter_num} Lint FAIL:\n{self.lint.format_report(violations)}")

        # --- 组装输出 ---
        return self._build_output(shots, beats, chapter_num, chapter_text, violations, lint_pass)

    def _detect_location(self, text: str) -> str:
        """从文本检测主位置"""
        loc_keywords = {}
        if "locations" in self.locations and isinstance(self.locations["locations"], list):
            for loc in self.locations["locations"]:
                loc_keywords[loc] = [loc]
                if "咖啡" in loc:
                    loc_keywords[loc].extend(["吧台", "磨豆", "杯壁", "红茶"])
                elif "面馆" in loc:
                    loc_keywords[loc].extend(["面碗", "排风扇"])
                elif "巷子" in loc:
                    loc_keywords[loc].extend(["青石板", "月光"])

        for loc, kws in loc_keywords.items():
            if any(kw in text for kw in kws):
                return loc
        return ""

    def _build_output(
        self,
        shots: list[dict],
        beats: list[dict],
        chapter_num: int,
        chapter_text: str,
        violations: list,
        lint_pass: bool,
    ) -> dict:
        """组装最终输出"""
        total_duration = sum(s["duration"] for s in shots)
        all_chars = list(set(c for s in shots for c in s.get("characters", [])))

        # 构建Episode对象
        episode_shots = []
        for s in shots:
            st = s.get("shot_type", "MS")
            cm = s.get("camera_movement", "static")
            ca = s.get("camera_angle", "eye-level")
            episode_shots.append(Shot(
                shot_id=s["shot_id"],
                shot_type=ShotType(st) if st in [e.value for e in ShotType] else ShotType.MS,
                camera_movement=CameraMovement(cm) if cm in [e.value for e in CameraMovement] else CameraMovement.STATIC,
                camera_angle=CameraAngle(ca) if ca in [e.value for e in CameraAngle] else CameraAngle.EYE_LEVEL,
                duration=s["duration"],
                action=s.get("action_visual", ""),
                lighting=s.get("lighting", "Natural"),
                mood=s.get("emotion", "Neutral"),
                emotion_tag=s.get("emotion", ""),
                pacing_label=s.get("pacing_label", ""),
                location=s.get("location", ""),
                characters_present=s.get("characters", []),
                dialogue=s.get("dialogue", ""),
                visual_anchors=s.get("visual_anchors", []),
            ))

        episode = Episode(
            episode_number=chapter_num,
            duration_estimate_seconds=round(total_duration),
            word_count_estimate=len(chapter_text),
            shots=episode_shots,
            cliffhanger=Cliffhanger(
                type="shock",
                line=shots[-1].get("action_visual", "") if shots else "",
            ),
            hook_density="high",
            scene_count=max(1, len(set(b.get("space", "Physical") for b in beats))),
            characters_involved=all_chars,
            script_text=chapter_text,
        )

        return {
            "episode": episode,
            "shots": shots,
            "beats": beats,
            "lint_violations": [
                {"shot_id": v.shot_id, "rule": v.rule, "severity": v.severity, "message": v.message}
                for v in violations
            ],
            "lint_pass": lint_pass,
            "total_duration": round(total_duration),
            "shot_count": len(shots),
            "beat_count": len(beats),
        }

    def _translate_location(self, location: str) -> str:
        """将中文location翻译为英文"""
        translations = {
            "念想咖啡店": "Nianxiang coffee shop",
            "念想咖啡店吧台": "Nianxiang coffee shop bar counter",
            "面馆": "noodle shop",
            "巷子": "narrow alley",
            "苏念的公寓": "Su Nian's apartment",
            "写字楼": "office building",
            "公园": "small park",
        }
        for zh, en in translations.items():
            if zh in location:
                return en
        return location

    def _empty_result(self, chapter_num: int, chapter_text: str) -> dict:
        return {
            "episode": Episode(episode_number=chapter_num, duration_estimate_seconds=0, word_count_estimate=len(chapter_text)),
            "shots": [], "beats": [], "lint_violations": [], "lint_pass": False,
            "total_duration": 0, "shot_count": 0, "beat_count": 0,
        }

    # --- 便捷方法 ---

    def adapt_from_file(self, chapter_num: int, target_duration: int = 90) -> dict:
        for subdir in ("chapters", "story"):
            path = self.project_dir / subdir / f"{chapter_num:03d}.md"
            if path.exists():
                return self.adapt(path.read_text(), chapter_num, target_duration)
        raise FileNotFoundError(f"Chapter {chapter_num} not found")

    def get_veo_prompts(self, result: dict) -> list[dict]:
        return [
            {
                "shot_id": s["shot_id"],
                "veo_prompt": s.get("veo_prompt", ""),
                "duration": s["duration"],
                "shot_type": s["shot_type"],
                "camera": s["camera_movement"],
                "characters": s.get("characters", []),
                "location": s.get("location", ""),
                "dialogue": s.get("dialogue", ""),
                "inner_voice": s.get("inner_voice", ""),
                "anchors": s.get("visual_anchors", []),
                "space": s.get("space", "Physical"),
            }
            for s in result.get("shots", [])
        ]
