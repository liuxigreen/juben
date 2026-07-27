"""
Episode Adapter v2 — SmartAdapter 三阶段流水线

替代旧版机械切割器，实现纯剧本→结构化分镜的智能转换。

三阶段架构：
  Stage 1: 场景提取（规则+正则）— 从纯剧本中识别语义场景边界
  Stage 2: 镜头设计（语义分析）— 根据内容为四大维度填值
  Stage 3: 画面补全（可选LLM）— 用小prompt补光影/音效/视角细节

四大视觉维度（下游AI视频模型硬通货）：
  - 景别 ShotType:    ECU/CU/MCU/MS/FS/EWS
  - 运镜 CameraMovement: Static/Push/Pull/Handheld/Pan/Tracking
  - 视角 CameraAngle:    Eye Level/Low Angle/High Angle/Dutch/Overhead
  - 光影 Lighting:       Low key/Warm/High contrast/Natural/Moonlight

设计原则：
  1. 零LLM调用完成Stage 1+2（纯规则+正则）
  2. Stage 3可选接入小prompt补全（不依赖scribe_prompt的大prompt）
  3. 所有配置从项目目录动态加载，不硬编码
  4. 输出兼容Episode schema，可直接喂ShotPromptGenerator
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import (
    CameraAngle,
    CameraMovement,
    Cliffhanger,
    Episode,
    PacingCheckpoint,
    PacingLabel,
    RenderStyle,
    Shot,
    ShotType,
    VisualConsistency,
)
from .rhythm import RhythmValidator

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SceneUnit:
    """Stage 1 输出：一个语义场景单元"""
    text: str                    # 原始文本
    characters: list[str]        # 出场角色名
    location: str                # 物理位置
    key_action: str              # 关键可拍摄动作
    dialogues: list[dict]        # [{speaker, text}]
    emotion: str                 # 主导情绪
    has_cliffhanger: bool        # 是否包含钩子
    word_count: int = 0          # 字数
    scene_type: str = "对话"     # 对话/动作/情绪/悬念


@dataclass
class ShotDesign:
    """Stage 2 输出：单个镜头设计"""
    shot_id: int
    scene_index: int
    shot_type: ShotType
    camera_movement: CameraMovement
    camera_angle: CameraAngle
    lighting: str
    duration: float
    visual_action: str
    dialogue: str
    emotion: str
    pacing_label: str
    location: str
    characters: list[str]
    audio_hint: str


# ============================================================
# Stage 1: 场景提取
# ============================================================

class SceneExtractor:
    """
    从纯剧本中提取语义场景单元。
    
    核心原则：只在真正换地点时才切场景。
    角色"站起来""转身走"不算切换——除非检测到新地点关键词。
    """

    def __init__(
        self,
        characters: list[dict],
        locations: dict,
        min_scene_size: int = 200,
    ):
        self.char_names = [c.get("name", "") for c in characters if c.get("name")]
        self.location_keywords = self._build_location_keywords(locations)
        self.min_scene_size = min_scene_size

    def extract(self, chapter_text: str) -> list[SceneUnit]:
        """从章节文本提取场景列表"""
        # Step 1: 按空行分段
        raw_paragraphs = re.split(r'\n\s*\n', chapter_text.strip())
        paragraphs = [p.strip() for p in raw_paragraphs
                      if p.strip() and not p.strip().startswith('#')]

        if not paragraphs:
            return []

        # Step 2: 检测场景切换点
        scene_breaks = self._detect_scene_breaks(paragraphs)

        # Step 3: 按切换点分组为场景
        scenes = self._group_into_scenes(paragraphs, scene_breaks)

        # Step 4: 合并小场景
        scenes = self._merge_small_scenes(scenes)

        return scenes

    # --- 位置关键词构建 ---

    def _build_location_keywords(self, locations: dict) -> dict:
        """
        从locations.json构建位置关键词映射。
        
        支持两种格式：
        1. 简单列表: {"locations": ["咖啡店", "吧台", ...]}
        2. 关键词映射: {"咖啡店": ["吧台", "磨豆", ...]}
        """
        keywords = {}

        if not locations:
            return keywords

        if "locations" in locations and isinstance(locations["locations"], list):
            for loc_name in locations["locations"]:
                keywords[loc_name] = [loc_name]
                # 自动扩展常见别名
                if "咖啡" in loc_name:
                    keywords[loc_name].extend([
                        "吧台", "磨豆", "杯壁", "红茶", "茶水", "便签",
                        "拉花", "咖啡机", "豆子",
                    ])
                elif "面馆" in loc_name:
                    keywords[loc_name].extend([
                        "面碗", "面汤", "排风扇", "油烟", "铁锅", "灶台",
                    ])
                elif "巷子" in loc_name or "巷" in loc_name:
                    keywords[loc_name].extend([
                        "青石板", "月光", "路灯", "影子", "墙壁",
                    ])
                elif "公寓" in loc_name or "家" in loc_name:
                    keywords[loc_name].extend(["卧室", "床", "门框"])
                elif "写字楼" in loc_name:
                    keywords[loc_name].extend(["旋转门", "玻璃幕墙", "电梯"])
        else:
            for loc_name, loc_data in locations.items():
                if isinstance(loc_data, list):
                    keywords[loc_name] = loc_data
                elif isinstance(loc_data, dict):
                    keywords[loc_name] = loc_data.get("keywords", [])

        return keywords

    # --- 场景切换检测 ---

    def _detect_scene_breaks(self, paragraphs: list[str]) -> set[int]:
        """
        检测场景切换点。
        
        切换信号（必须满足位置变化）：
        1. 检测到新位置且与前一段不同
        2. 段落以时空跳跃标记开头 + 伴随位置变化
        """
        breaks = set()
        prev_location = ""

        for i, para in enumerate(paragraphs):
            loc = self._detect_location(para)

            if loc and loc != prev_location and i > 0:
                # 确认前一段不在同一位置
                prev_loc = self._detect_location(paragraphs[i - 1])
                if loc != prev_loc:
                    breaks.add(i)
                    prev_location = loc
            elif loc:
                prev_location = loc

            # 明确时空跳跃标记（必须在段落开头 + 有位置信息）
            time_markers = [
                "第二天", "几小时后", "傍晚", "清晨",
                "回到", "来到", "走到", "走进",
            ]
            if any(para.strip().startswith(m) for m in time_markers):
                if i > 0 and loc:
                    breaks.add(i)
                    prev_location = loc

        return breaks

    def _detect_location(self, para: str) -> str:
        """检测段落中的物理位置"""
        for loc_name, keywords in self.location_keywords.items():
            if any(kw in para for kw in keywords):
                return loc_name
        return ""

    # --- 场景分组 ---

    def _group_into_scenes(
        self, paragraphs: list[str], breaks: set[int],
    ) -> list[SceneUnit]:
        """按切换点将段落分组为场景"""
        scenes = []
        current_group = []
        current_location = ""

        for i, para in enumerate(paragraphs):
            if i in breaks and current_group:
                scene = self._build_scene(current_group, current_location)
                if scene.word_count >= 30:
                    scenes.append(scene)
                current_group = []

            loc = self._detect_location(para)
            if loc:
                current_location = loc
            current_group.append(para)

        # 最后一组
        if current_group:
            scene = self._build_scene(current_group, current_location)
            if scene.word_count >= 30:
                scenes.append(scene)

        return scenes

    def _build_scene(
        self, paragraphs: list[str], fallback_location: str,
    ) -> SceneUnit:
        """从段落组构建场景单元"""
        text = "\n".join(paragraphs)

        # 提取角色
        characters = [n for n in self.char_names if n in text]

        # 提取位置
        location = fallback_location
        for para in paragraphs:
            loc = self._detect_location(para)
            if loc:
                location = loc
                break

        # 提取对话
        dialogues = self._extract_dialogues(text)

        # 提取关键动作
        key_action = self._extract_key_action(text)

        # 推断情绪
        emotion = self._infer_emotion(text)

        # 检测钩子
        has_cliffhanger = self._detect_cliffhanger(text)

        # 推断场景类型
        scene_type = self._infer_scene_type(text, dialogues)

        return SceneUnit(
            text=text,
            characters=characters,
            location=location or "未标注",
            key_action=key_action,
            dialogues=dialogues,
            emotion=emotion,
            has_cliffhanger=has_cliffhanger,
            word_count=len(text),
            scene_type=scene_type,
        )

    # --- 对话提取 ---

    def _extract_dialogues(self, text: str) -> list[dict]:
        """
        提取对话（三级匹配）。
        
        Level 1: 带说话者的引号对话（"XXX"XXX说）
        Level 2: 纯引号对话（过滤声效和过短内容）
        """
        dialogues = []

        # Level 1: 带说话者
        pattern1 = re.findall(
            r'(?:(\w{2,4})(?:说|道|问|答|喊|叫|冷笑|叹|低声|开口|声音|语气))'
            r'[^"]*["\u300c]([^"\u300d]+)["\u300d]',
            text,
        )
        for speaker, line in pattern1:
            if speaker in self.char_names:
                dialogues.append({"speaker": speaker, "text": line})

        # Level 2: 纯引号对话
        pattern2 = re.findall(r'["\u300c]([^"\u300d]{2,})["\u300d]', text)
        sound_effect_pattern = re.compile(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$')

        for line in pattern2:
            if len(line) <= 2:
                continue
            if sound_effect_pattern.match(line):
                continue
            if not any(line in d["text"] for d in dialogues):
                dialogues.append({"speaker": "", "text": line})

        return dialogues

    # --- 关键动作提取 ---

    def _extract_key_action(self, text: str) -> str:
        """提取可拍摄的物理动作（排除心理描写）"""
        abstract = {
            "语速", "语气", "心想", "觉得", "感到", "认为",
            "意识到", "明白", "知道", "理解", "暗想", "像在", "像是",
        }

        # 优先匹配物理动作句
        patterns = [
            r'[^。\n]*(?:端起|放下|转身|站起来|推开门|靠在|攥紧|掏出|摸到|坐下)[^。]*。',
            r'[^。\n]*(?:灯闪|灭了|亮了|震了|溅起|滴|碎|裂|断|掉|消失)[^。]*。',
            r'[^。\n]*(?:眼神|瞳孔|手指|拳头|颤抖|发抖|攥|捏|按)[^。]*。',
            r'[^。\n]*(?:筷子|杯子|碗|茶|灯|门|窗|钥匙|手机|纸巾|便签)[^。]*。',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                m = m.strip()
                if any(a in m for a in abstract):
                    continue
                if 10 <= len(m) <= 60:
                    return m[:60]

        # 兜底：取有具体道具的句子
        sentences = re.split(r'[。！？\n]', text)
        for sent in sentences:
            sent = sent.strip()
            if 10 <= len(sent) <= 50:
                concrete = {"手", "眼", "杯", "灯", "门", "窗", "钥匙", "手机", "筷子", "碗"}
                if any(kw in sent for kw in concrete):
                    if not any(a in sent for a in abstract):
                        return sent[:50]

        return ""

    # --- 情绪推断 ---

    def _infer_emotion(self, text: str) -> str:
        """推断主导情绪"""
        signals = {
            "紧张": ["攥紧", "心跳", "发抖", "冰凉", "齿痕", "掌心"],
            "震惊": ["愣", "呆", "瞳孔", "不敢相信", "猛地", "灭了", "闪了"],
            "暧昧": ["月光", "影子", "眼睛", "想起", "不同", "心跳"],
            "悬疑": ["想不起来", "模糊", "淡了", "消失", "听不清", "黑暗"],
            "悲伤": ["泪", "哭", "痛", "苦", "冷", "空荡荡", "消失"],
            "愤怒": ["怒", "恨", "咬牙", "瞪", "摔", "砸"],
            "日常": ["吃面", "喝", "筷子", "碗", "面汤", "排风扇"],
        }

        scores = {}
        for emotion, keywords in signals.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[emotion] = score

        return max(scores, key=scores.get) if scores else "中性"

    # --- 钩子检测 ---

    def _detect_cliffhanger(self, text: str) -> bool:
        """检测文本末尾是否包含钩子"""
        tail = text[-200:]
        signals = [
            "？", "呢", "听不清", "消失", "没了", "灭了", "黑暗",
            "突然", "忽然", "转身", "走了", "淡了", "想不起来",
        ]
        return any(s in tail for s in signals)

    # --- 场景类型推断 ---

    def _infer_scene_type(self, text: str, dialogues: list[dict]) -> str:
        """推断场景类型"""
        dialogue_ratio = sum(len(d["text"]) for d in dialogues) / max(1, len(text))

        if dialogue_ratio > 0.3:
            return "对话"
        elif any(kw in text for kw in ["追", "跑", "打", "摔", "砸", "冲"]):
            return "动作"
        elif any(kw in text for kw in ["想不起来", "模糊", "闪", "灭了", "黑暗"]):
            return "悬念"
        return "情绪"

    # --- 小场景合并 ---

    def _merge_small_scenes(self, scenes: list[SceneUnit]) -> list[SceneUnit]:
        """将过小的场景合并到相邻场景"""
        if len(scenes) <= 1:
            return scenes

        merged = []
        buffer = None

        for scene in scenes:
            if buffer is None:
                buffer = scene
                continue

            if buffer.word_count < self.min_scene_size:
                buffer = self._merge_two(buffer, scene)
            else:
                merged.append(buffer)
                buffer = scene

        if buffer:
            if merged and buffer.word_count < self.min_scene_size:
                merged[-1] = self._merge_two(merged[-1], buffer)
            else:
                merged.append(buffer)

        return merged

    @staticmethod
    def _merge_two(a: SceneUnit, b: SceneUnit) -> SceneUnit:
        """合并两个场景"""
        return SceneUnit(
            text=a.text + "\n\n" + b.text,
            characters=list(set(a.characters + b.characters)),
            location=b.location if b.location != "未标注" else a.location,
            key_action=b.key_action or a.key_action,
            dialogues=a.dialogues + b.dialogues,
            emotion=b.emotion if b.emotion != "中性" else a.emotion,
            has_cliffhanger=b.has_cliffhanger or a.has_cliffhanger,
            word_count=a.word_count + b.word_count,
            scene_type=b.scene_type if b.scene_type != "中性" else a.scene_type,
        )


# ============================================================
# Stage 2: 镜头设计
# ============================================================

class ShotDesigner:
    """
    从场景单元设计镜头。
    
    核心逻辑：
    - 根据内容选景别（情绪爆发→CU，对话→MCU，环境→MS）
    - 根据叙事位置选运镜（开头→Static，冲突→Push，反应→Pull）
    - 根据内容密度分配时长（不再全员18秒）
    - 自动注入角色标签和位置信息
    """

    # 情绪→景别映射
    EMOTION_SHOT_MAP = {
        "震惊": ShotType.CU,
        "愤怒": ShotType.CU,
        "悲伤": ShotType.CU,
        "恐惧": ShotType.CU,
        "紧张": ShotType.MCU,
        "暧昧": ShotType.MCU,
        "悬疑": ShotType.CU,
        "日常": ShotType.MS,
        "中性": ShotType.MCU,
    }

    # 场景类型→景别映射
    TYPE_SHOT_MAP = {
        "对话": ShotType.MCU,
        "动作": ShotType.MS,
        "悬念": ShotType.CU,
        "情绪": ShotType.MCU,
    }

    # 情绪→运镜映射
    EMOTION_CAMERA_MAP = {
        "震惊": CameraMovement.PUSH,
        "愤怒": CameraMovement.PUSH,
        "悲伤": CameraMovement.PULL,
        "恐惧": CameraMovement.HANDHELD,
        "紧张": CameraMovement.PUSH,
        "暧昧": CameraMovement.PULL,
        "悬疑": CameraMovement.PUSH,
        "日常": CameraMovement.STATIC,
        "中性": CameraMovement.STATIC,
    }

    # 情绪→光影映射
    EMOTION_LIGHTING_MAP = {
        "震惊": "High contrast",
        "愤怒": "High contrast",
        "悲伤": "Low key",
        "恐惧": "Low key",
        "紧张": "High contrast",
        "暧昧": "Warm",
        "悬疑": "Low key",
        "日常": "Natural",
        "中性": "Natural",
    }

    # 情绪→音效映射
    EMOTION_AUDIO_MAP = {
        "震惊": "dramatic sting, silence",
        "愤怒": "tense strings, heartbeat",
        "悲伤": "soft piano, rain",
        "恐惧": "low frequency hum, breathing",
        "紧张": "tickling clock, suspense",
        "暧昧": "soft ambient, warm tones",
        "悬疑": "silence, subtle tension",
        "日常": "ambient room tone",
        "中性": "ambient room tone",
    }

    # 节奏卡点标签序列
    PACING_LABELS = [
        "3s_Hook",
        "15s_Retention",
        "30s_Explosion",
        "60s_Satisfaction",
        "90s_Cliffhanger",
    ]

    def design(
        self,
        scenes: list[SceneUnit],
        target_duration: int = 90,
    ) -> list[ShotDesign]:
        """从场景列表设计镜头"""
        if not scenes:
            return []

        # 计算目标镜头数（每200字≈1镜头，最少3个，最多8个）
        total_words = sum(s.word_count for s in scenes)
        target_shots = max(3, min(8, total_words // 200))

        # 分配节奏卡点
        pacing_labels = self._assign_pacing(scenes, target_shots)

        # 为每个场景生成镜头
        all_shots = []
        shot_id = 1

        for i, scene in enumerate(scenes):
            n_shots = self._decide_shot_count(scene)
            segments = self._split_scene(scene.text, n_shots)
            pacing = pacing_labels[i] if i < len(pacing_labels) else "30s_Explosion"

            for j, segment in enumerate(segments):
                shot = ShotDesign(
                    shot_id=shot_id,
                    scene_index=i,
                    shot_type=self._choose_shot_type(scene),
                    camera_movement=self._choose_camera(scene, i, len(scenes)),
                    camera_angle=self._choose_angle(scene),
                    lighting=self._choose_lighting(scene),
                    duration=0.0,  # 后面统一调整
                    visual_action=self._extract_visual_action(segment),
                    dialogue=self._extract_dialogue(segment),
                    emotion=scene.emotion,
                    pacing_label=pacing,
                    location=scene.location,
                    characters=scene.characters,
                    audio_hint=self._choose_audio(scene),
                )
                all_shots.append(shot)
                shot_id += 1

        # 调整时长使总时长接近目标
        self._adjust_durations(all_shots, target_duration)

        return all_shots

    # --- 节奏卡点分配 ---

    def _assign_pacing(self, scenes: list[SceneUnit], target_shots: int) -> list[str]:
        """根据场景的叙事位置分配节奏卡点"""
        n = len(scenes)
        labels = []

        for i, scene in enumerate(scenes):
            ratio = i / max(1, n - 1)

            if ratio <= 0.15:
                labels.append("3s_Hook")
            elif ratio <= 0.35:
                labels.append("15s_Retention")
            elif ratio <= 0.55:
                labels.append("30s_Explosion")
            elif ratio <= 0.75:
                labels.append("60s_Satisfaction")
            else:
                labels.append("90s_Cliffhanger")

        # 确保最后一个场景是Cliffhanger
        if scenes and scenes[-1].has_cliffhanger:
            labels[-1] = "90s_Cliffhanger"

        return labels

    # --- 镜头数决策 ---

    def _decide_shot_count(self, scene: SceneUnit) -> int:
        """决定场景拆几个镜头"""
        if scene.has_cliffhanger and scene.word_count > 500:
            return 2
        if scene.scene_type == "动作" and scene.word_count > 300:
            return 2
        if scene.word_count > 800:
            return 2
        return 1

    # --- 场景文本分割 ---

    @staticmethod
    def _split_scene(text: str, n_shots: int) -> list[str]:
        """将场景文本拆分为镜头段落"""
        if n_shots <= 1:
            return [text]

        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        if len(paragraphs) <= 1:
            sentences = re.split(r'(?<=[。！？])', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            mid = len(sentences) // 2
            return ["".join(sentences[:mid]), "".join(sentences[mid:])]

        mid = len(paragraphs) // 2
        return ["\n".join(paragraphs[:mid]), "\n".join(paragraphs[mid:])]

    # --- 四大维度选值 ---

    def _choose_shot_type(self, scene: SceneUnit) -> ShotType:
        """选景别：情绪优先，场景类型兜底"""
        return self.EMOTION_SHOT_MAP.get(
            scene.emotion,
            self.TYPE_SHOT_MAP.get(scene.scene_type, ShotType.MCU),
        )

    def _choose_camera(
        self, scene: SceneUnit, scene_index: int, total_scenes: int,
    ) -> CameraMovement:
        """选运镜：情绪驱动+叙事位置"""
        # 结尾场景→Push（悬念感）
        if scene_index == total_scenes - 1 and scene.has_cliffhanger:
            return CameraMovement.PUSH
        return self.EMOTION_CAMERA_MAP.get(scene.emotion, CameraMovement.STATIC)

    @staticmethod
    def _choose_angle(scene: SceneUnit) -> CameraAngle:
        """选视角：情绪决定权力关系"""
        if scene.emotion in ("愤怒", "紧张"):
            return CameraAngle.LOW
        if scene.emotion in ("悲伤", "恐惧"):
            return CameraAngle.HIGH
        return CameraAngle.EYE_LEVEL

    def _choose_lighting(self, scene: SceneUnit) -> str:
        """选光影：情绪基调"""
        return self.EMOTION_LIGHTING_MAP.get(scene.emotion, "Natural")

    def _choose_audio(self, scene: SceneUnit) -> str:
        """选音效：情绪+场景类型"""
        # 优先从文本中提取具体音效
        audio_keywords = {
            "嗡嗡": "electrical hum",
            "咣": "metal clang",
            "嗒嗒": "rhythmic tapping",
            "震": "phone vibration",
            "脚步": "footsteps on stone",
            "排风扇": "ventilation fan whirring",
            "灭了": "light flickering off",
            "亮了": "light flickering on",
            "溅": "liquid splashing",
        }
        for kw, audio in audio_keywords.items():
            if kw in scene.text:
                return audio

        return self.EMOTION_AUDIO_MAP.get(scene.emotion, "ambient room tone")

    # --- 视觉动作提取 ---

    @staticmethod
    def _extract_visual_action(segment: str) -> str:
        """提取可拍摄的视觉动作（15-40字）"""
        abstract = {
            "语速", "语气", "心想", "觉得", "感到", "认为",
            "意识到", "明白", "知道", "理解", "暗想", "像在", "像是",
        }

        patterns = [
            r'[^。\n]*(?:端起|放下|转身|站起来|推开门|靠在|攥紧|掏出|摸到|坐下)[^。]*。',
            r'[^。\n]*(?:灯闪|灭了|亮了|震了|溅起|滴|碎|裂|断|掉|消失)[^。]*。',
            r'[^。\n]*(?:眼神|瞳孔|手指|拳头|颤抖|发抖|攥|捏|按)[^。]*。',
            r'[^。\n]*(?:筷子|杯子|碗|茶|灯|门|窗|钥匙|手机|纸巾|便签)[^。]*。',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, segment)
            for m in matches:
                m = m.strip()
                if any(a in m for a in abstract):
                    continue
                if 10 <= len(m) <= 60:
                    return m[:60]

        # 兜底
        sentences = re.split(r'[。！？\n]', segment)
        for sent in sentences:
            sent = sent.strip()
            if 10 <= len(sent) <= 50:
                concrete = {"手", "眼", "杯", "灯", "门", "窗", "钥匙", "手机"}
                if any(kw in sent for kw in concrete):
                    if not any(a in sent for a in abstract):
                        return sent[:50]

        return segment[:40] if segment else ""

    # --- 台词提取 ---

    @staticmethod
    def _extract_dialogue(segment: str) -> str:
        """提取关键台词（过滤声效）"""
        matches = re.findall(r'["\u300c]([^"\u300d]+)["\u300d]', segment)
        sound_pattern = re.compile(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$')

        filtered = []
        for m in matches:
            if len(m) <= 2:
                continue
            if sound_pattern.match(m):
                continue
            filtered.append(m)

        return min(filtered, key=len) if filtered else ""

    # --- 时长调整 ---

    @staticmethod
    def _adjust_durations(shots: list[ShotDesign], target_duration: int):
        """按比例调整镜头时长，使总时长接近目标"""
        if not shots:
            return

        current = sum(s.duration for s in shots)
        if current <= 0:
            # 全部为0，平均分配
            avg = target_duration / len(shots)
            for s in shots:
                s.duration = round(avg, 1)
            return

        ratio = target_duration / current
        for s in shots:
            s.duration = round(max(2.0, s.duration * ratio), 1)


# ============================================================
# 主适配器（对外接口）
# ============================================================

class EpisodeAdapter:
    """
    章节→单集适配器（SmartAdapter v2）。
    
    替代旧版机械切割器，实现纯剧本→结构化分镜的智能转换。
    
    用法：
        adapter = EpisodeAdapter(project_dir)
        episode = adapter.adapt_chapter(chapter_text, chapter_num=9)
    """

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.validator = RhythmValidator()

        # 加载项目配置
        self.characters = self._load_json("characters.json").get("characters", [])
        self.locations = self._load_json("locations.json")

    def _load_json(self, filename: str) -> dict:
        """加载项目JSON配置"""
        path = self.project_dir / filename
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def adapt_chapter(
        self,
        chapter_text: str,
        chapter_num: int,
        target_duration: int = 90,
        characters: list[dict] | None = None,
    ) -> Episode:
        """
        将纯剧本适配为短剧单集。
        
        Args:
            chapter_text: 章节纯文本
            chapter_num: 章节编号
            target_duration: 目标时长（秒），默认90
            characters: 角色列表（可选，覆盖项目配置）
            
        Returns:
            Episode 对象（兼容下游ShotPromptGenerator）
        """
        chars = characters or self.characters

        # Stage 1: 场景提取
        extractor = SceneExtractor(chars, self.locations)
        scenes = extractor.extract(chapter_text)

        # Stage 2: 镜头设计
        designer = ShotDesigner()
        shot_designs = designer.design(scenes, target_duration)

        # Stage 3: 组装Episode
        episode = self._build_episode(
            shot_designs, scenes, chapter_num, chapter_text, target_duration,
        )

        # 双轴校验
        result = self.validator.validate_episode(episode)
        if not result.passed:
            logger.warning(
                f"Episode {chapter_num} rhythm check: "
                f"{len(result.violations)} violations, score={result.score}"
            )

        return episode

    def _build_episode(
        self,
        shot_designs: list[ShotDesign],
        scenes: list[SceneUnit],
        chapter_num: int,
        chapter_text: str,
        target_duration: int,
    ) -> Episode:
        """从镜头设计组装Episode对象"""
        # 构建Shot列表
        shots = []
        for sd in shot_designs:
            shot = Shot(
                shot_id=sd.shot_id,
                shot_type=sd.shot_type,
                camera_movement=sd.camera_movement,
                camera_angle=sd.camera_angle,
                duration=sd.duration,
                action=sd.visual_action,
                lighting=sd.lighting,
                mood=sd.emotion,
                emotion_tag=sd.emotion,
                pacing_label=sd.pacing_label,
                location=sd.location,
                characters_present=sd.characters,
                audio_prompt=sd.audio_hint,
                dialogue=sd.dialogue,
            )
            shots.append(shot)

        # 构建PacingCheckpoint列表
        checkpoints = []
        for sd in shot_designs:
            checkpoints.append(PacingCheckpoint(
                label=PacingLabel(sd.pacing_label) if sd.pacing_label in [
                    e.value for e in PacingLabel
                ] else PacingLabel.HOOK_3S,
                word_range=[0, len(sd.visual_action) + len(sd.dialogue)],
                time_range=[0, sd.duration],
                rule="",
                visual_action=sd.visual_action,
                dialogue=sd.dialogue,
                emotion=sd.emotion,
                passed=True,
            ))

        # 构建Cliffhanger
        last = shot_designs[-1] if shot_designs else None
        cliffhanger = Cliffhanger(
            type="shock" if last and last.emotion in ("震惊", "悬疑") else "reveal",
            line=last.visual_action if last else "",
            unanswered_question="接下来会发生什么？",
        )

        # 角色视觉一致性
        visual_consistency = self._build_visual_consistency()

        total_duration = sum(s.duration for s in shots)

        return Episode(
            episode_number=chapter_num,
            duration_estimate_seconds=round(total_duration),
            word_count_estimate=len(chapter_text),
            pacing_checkpoints=checkpoints,
            shots=shots,
            cliffhanger=cliffhanger,
            visual_consistency=visual_consistency,
            hook_density="high" if any(
                s.emotion in ("震惊", "悬疑") for s in shot_designs
            ) else "medium",
            scene_count=len(set(s.scene_index for s in shot_designs)),
            characters_involved=list(set(
                c for s in shot_designs for c in s.characters
            )),
            script_text=chapter_text,
            shot_prompts=[
                {"shot_id": s.shot_id, "prompt": s.to_visual_prompt()}
                for s in shots
            ],
        )

    def _build_visual_consistency(self) -> list[VisualConsistency]:
        """从characters.json构建角色视觉一致性"""
        result = []
        for char in self.characters:
            name = char.get("name", "")
            appearance = char.get("appearance", {})
            result.append(VisualConsistency(
                character_name=name,
                appearance=appearance.get("description", ""),
                default_attire=appearance.get("attire", ""),
                voice_tone=char.get("voice", ""),
            ))
        return result

    # --- 便捷方法 ---

    def adapt_chapter_from_file(
        self,
        chapter_num: int,
        target_duration: int = 90,
    ) -> Episode:
        """从文件加载章节并适配"""
        # 尝试多个可能的路径
        for subdir in ("chapters", "story"):
            path = self.project_dir / subdir / f"{chapter_num:03d}.md"
            if path.exists():
                return self.adapt_chapter(
                    path.read_text(), chapter_num, target_duration,
                )

        raise FileNotFoundError(
            f"Chapter {chapter_num} not found in "
            f"{self.project_dir}/chapters/ or {self.project_dir}/story/"
        )

    def get_storyboard_markdown(self, episode: Episode) -> str:
        """生成可读的分镜脚本Markdown"""
        lines = [
            f"# 第{episode.episode_number}章 分镜脚本\n",
            f"**总时长**: {episode.duration_estimate_seconds}s | "
            f"**镜头数**: {len(episode.shots)} | "
            f"**钩子类型**: {episode.cliffhanger.type}\n",
        ]

        for shot in episode.shots:
            lines.append(f"## 镜头 {shot.shot_id} | {shot.pacing_label}")
            lines.append(
                f"- **【画面机位】**: [{shot.shot_type.value}] + "
                f"[{shot.camera_movement.value}] + [{shot.camera_angle.value}]"
            )
            lines.append(f"- **【视觉动作】**: {shot.action}")
            lines.append(
                f"- **【场景光影】**: [{shot.lighting}] + {shot.audio_prompt}"
            )
            if shot.dialogue:
                lines.append(f"- **【角色台词】**: {shot.dialogue}")
            lines.append(f"- **【时长】**: {shot.duration}s")
            lines.append(f"- **【位置】**: {shot.location or '未标注'}")
            lines.append("")

        return "\n".join(lines)
