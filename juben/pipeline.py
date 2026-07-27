"""
StoryBeat Pipeline — 通用分镜引擎 v1.0

架构原则：
1. 代码零硬编码（零角色名、零动作模板、零题材数据）
2. 所有题材数据从 project_config.yaml 读取
3. 发现问题只改通用逻辑或配置，不改代码里的具体数据

流水线：
  剧本 → BeatExtractor(config) → ShotCompiler(config) → PromptRenderer(config) → Lint(config) → SRT
"""
import json, re, sys, os
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# 配置加载
# ============================================================

def load_config(project_dir: Path) -> dict:
    """加载项目配置文件"""
    config_path = project_dir / "project_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# BeatExtractor — 从剧本提取Visual Beat
# ============================================================

class BeatExtractor:
    """
    通用Beat提取器。
    
    所有切分规则、角色检测、动作翻译都从config读取。
    代码只包含"怎么用配置"的逻辑，不包含"配置内容"。
    """

    def __init__(self, config: dict):
        self.cfg = config
        self.chars = config.get("characters", {})
        self.ability = config.get("ability_events", {})
        self.cut_triggers = config.get("beat_cut_triggers", {})
        self.action_templates = config.get("action_templates", [])
        self.action_rewrite = config.get("action_rewrite", {})
        self.anchor_map = config.get("anchor_map", {})
        self.emotion_map = config.get("emotion_map", {})
        self.space_map = config.get("space_map", {})
        self.micro_actions = config.get("micro_actions", {})
        self.nouns = config.get("nouns", {})
        self.verbs = config.get("verbs", {})

    def extract(self, chapter_text: str) -> list[dict]:
        """从章节文本提取visual beats"""
        paras = self._split_paragraphs(chapter_text)
        if not paras:
            return []

        beats = []
        current_group = []
        beat_id = 1
        prev_speaker = ""
        in_reading = False

        for para in paras:
            speaker = self._detect_speaker(para, prev_speaker)
            prev_text = current_group[-1] if current_group else ""

            if current_group and self._should_cut(prev_text, para, prev_speaker, speaker):
                combined = "\n".join(current_group)
                if self._is_ability_event(combined) and not in_reading:
                    # 注入能力镜头模板
                    primary = self._detect_subject(combined)
                    for tpl in self.ability.get("camera_template", []):
                        beats.append(self._make_template_beat(beat_id, tpl, primary))
                        beat_id += 1
                    in_reading = True
                    current_group = [para]
                    prev_speaker = speaker
                    continue
                else:
                    beat = self._make_beat(beat_id, current_group)
                    if beat:
                        beats.append(beat)
                        beat_id += 1
                    current_group = []
                    in_reading = False

            current_group.append(para)
            if speaker:
                prev_speaker = speaker

        if current_group:
            beat = self._make_beat(beat_id, current_group)
            if beat:
                beats.append(beat)

        return beats

    # --- 切分逻辑（通用，规则从配置读） ---

    def _should_cut(self, prev_text: str, curr_text: str, prev_speaker: str, curr_speaker: str) -> bool:
        """判断是否切分beat（所有触发词从config读取）"""
        # 能力事件
        if self._is_ability_event(curr_text):
            return True
        # 痕迹变化（从config读）
        trace_kw = self.cut_triggers.get("trace", [])
        if any(kw in curr_text for kw in trace_kw):
            return True
        # 说话人切换
        if curr_speaker and prev_speaker and curr_speaker != prev_speaker:
            return True
        # 对话→叙述
        if re.search(r'["\u300c]', prev_text) and not re.search(r'["\u300c]', curr_text):
            return True
        # 场景切换（从config读）
        scene_kw = self.cut_triggers.get("scene", [])
        if any(kw in curr_text for kw in scene_kw) and not any(kw in prev_text for kw in scene_kw):
            return True
        # 动作切换（从config读）
        action_kw = self.cut_triggers.get("action", [])
        if any(kw in curr_text for kw in action_kw):
            return True
        # 情绪切换（从config读）
        emotion_kw = self.cut_triggers.get("emotion", [])
        if any(kw in curr_text for kw in emotion_kw):
            return True
        # 通讯切分（从config读）
        comm_pattern = self.cut_triggers.get("comm_pattern", "")
        if comm_pattern and re.search(comm_pattern, curr_text):
            return True
        return False

    def _is_ability_event(self, text: str) -> bool:
        """判断是否是能力发动事件（触发词从config读）"""
        triggers = self.ability.get("trigger_keywords", [])
        return any(kw in text for kw in triggers)

    # --- 角色检测（从config读角色表和指代词） ---

    def _detect_chars_in_text(self, text: str) -> list[str]:
        """检测文本中出现的角色"""
        found = []
        for name, info in self.chars.items():
            # 显式名字匹配
            if name in text:
                found.append(info["en"])
                continue
            # 指代词匹配（从config读）
            pronouns = info.get("pronouns", [])
            if any(p in text for p in pronouns):
                found.append(info["en"])
        return found if found else [self._default_char()]

    def _detect_subject(self, text: str) -> str:
        """检测动作主体（从config读指代词）"""
        for name, info in self.chars.items():
            if name in text:
                return info["en"]
        # 指代词推断
        for name, info in self.chars.items():
            pronouns = info.get("pronouns", [])
            if any(p in text for p in pronouns):
                return info["en"]
        return self._default_char()

    def _default_char(self) -> str:
        """默认角色（配置里的protagonist）"""
        for name, info in self.chars.items():
            if info.get("role") == "protagonist":
                return info["en"]
        # 兜底：第一个角色
        return list(self.chars.values())[0]["en"] if self.chars else "Character"

    def _detect_speaker(self, paragraph: str, prev_speaker: str) -> str:
        """检测说话人"""
        # 直接匹配 "角色名+说/道/问/答"
        for name, info in self.chars.items():
            if re.search(rf"{name}(?:说|道|问|答|喊|叫|应|回)", paragraph):
                return info["en"]
        # 代词推断
        if re.search(r"他(?:说|道|问|答)", paragraph):
            male = [info["en"] for info in self.chars.values() if info.get("gender") == "male"]
            return prev_speaker if prev_speaker in male else (male[0] if male else prev_speaker)
        if re.search(r"她(?:说|道|问|答)", paragraph):
            female = [info["en"] for info in self.chars.values() if info.get("gender") == "female"]
            return prev_speaker if prev_speaker in female else (female[0] if female else prev_speaker)
        # 引号对话，看前面最近的角色名
        if re.search(r'["\u300c]', paragraph):
            for name, info in self.chars.items():
                if name in paragraph:
                    return info["en"]
        return prev_speaker

    # --- 动作翻译（从config读模板） ---

    def _translate_action(self, text: str, char: str) -> str:
        """将中文动作翻译为英文（模板从config读）"""
        # 模板匹配
        for tpl in self.action_templates:
            if re.search(tpl["pattern"], text):
                result = tpl["en"]
                translated = result.replace("{char}", char) if "{char}" in result else result
                return self._apply_rewrite(translated, char)
        # 微动作匹配（从config读）
        for zh, en in self.micro_actions.items():
            if zh in text:
                return self._apply_rewrite(f"{char} {en}", char)
        # 名词+动词组合兜底
        fn = [self.nouns[k] for k in self.nouns if k in text]
        fv = [self.verbs[k] for k in self.verbs if k in text]
        if fv and fn:
            return self._apply_rewrite(f"{char} {fv[0]} the {fn[0]}", char)
        if fv:
            return self._apply_rewrite(f"{char} {fv[0]}", char)
        if fn:
            return self._apply_rewrite(f"{char} gazes at the {fn[0]}", char)
        # 最终兜底（从config读）
        fallback = self.cfg.get("action_fallback", "{char} stands still")
        return self._apply_rewrite(fallback.replace("{char}", char), char)

    def _apply_rewrite(self, action: str, char: str) -> str:
        """翻译后应用黑名单改写（英文→英文）"""
        action_lower = action.lower()
        for bad, rewrite in self.action_rewrite.items():
            if bad in action_lower:
                return rewrite.replace("{char}", char)
        return action

    # --- 辅助提取 ---

    def _extract_dialogue(self, text: str) -> list[str]:
        """提取对话（排除心声*标记）"""
        # 先收集心声标记
        inner_markers = set()
        for p in [r'\*["](.*?)["]\*', r'\*[\u300c](.*?)[\u300d]\*', r'\*(.{5,}?)\*']:
            inner_markers.update(re.findall(p, text))
        matches = re.findall(r'["\u300c]([^"\u300d]+)["\u300d]', text)
        result = []
        for m in matches:
            if len(m) <= 2:
                continue
            is_inner = any(m[:20] in im or im[:20] in m for im in inner_markers)
            if not is_inner:
                result.append(m)
        return result

    def _extract_inner_voice(self, text: str) -> list[str]:
        """提取心声"""
        results = []
        for p in [r'\*["](.*?)["]\*', r'\*[\u300c](.*?)[\u300d]\*', r'\*(.{5,}?)\*']:
            results.extend(re.findall(p, text))
        return results

    def _extract_anchor(self, text: str) -> str:
        """提取图腾/焦点物（从config读）"""
        for zh, en in self.anchor_map.items():
            if zh in text:
                return en
        return ""

    def _detect_emotion(self, text: str) -> str:
        """检测情绪（从config读）"""
        for emotion, keywords in self.emotion_map.items():
            if any(kw in text for kw in keywords):
                return emotion
        return "Neutral"

    def _detect_space(self, text: str) -> str:
        """检测空间类型（从config读）"""
        for space, keywords in self.space_map.items():
            if any(kw in text for kw in keywords):
                return space
        return "Physical"

    # --- Beat构建 ---

    def _make_beat(self, beat_id: int, paragraphs: list[str]) -> dict | None:
        """构建单个beat"""
        text = "\n".join(paragraphs)
        chars = self._detect_chars_in_text(text)
        primary = self._detect_subject(text)
        action = self._translate_action(text, primary)

        inner = self._extract_inner_voice(text)
        dialogues = self._extract_dialogue(text)

        dialogue_text, dialogue_speaker, inner_text, voice_type = "", "", "", "none"

        if inner:
            inner_text = inner[0][:100]
        if dialogues:
            raw_dlg = dialogues[0][:80]
            # 心声特征检测（通用：省略号开头、心理关键词）
            inner_hints = self.cfg.get("inner_voice_hints", ["……"])
            if any(raw_dlg.startswith(h) for h in inner_hints):
                inner_text = inner_text or raw_dlg
            elif not inner_text:
                dialogue_text = raw_dlg
                for name, info in self.chars.items():
                    if name in text:
                        dialogue_speaker = info["en"]
                        break
                if not dialogue_speaker:
                    dialogue_speaker = primary

        if inner_text:
            voice_type = "inner_voice"
        elif dialogue_text:
            voice_type = "onscreen"

        return {
            "beat_id": beat_id,
            "space": self._detect_space(text),
            "characters_present": chars,
            "primary_char": primary,
            "action_visual": action,
            "spoken_dialogue": dialogue_text,
            "dialogue_speaker": dialogue_speaker,
            "inner_voice": inner_text,
            "voice_type": voice_type,
            "focus_object": self._extract_anchor(text),
            "emotion": self._detect_emotion(text),
            "source_text": text[:80],
        }

    def _make_template_beat(self, beat_id: int, tpl: dict, char: str) -> dict:
        """从能力模板构建beat"""
        return {
            "beat_id": beat_id,
            "space": tpl.get("space", "Mental"),
            "characters_present": [char],
            "primary_char": char,
            "action_visual": tpl.get("action", "").replace("{char}", char),
            "spoken_dialogue": "",
            "dialogue_speaker": "",
            "inner_voice": "",
            "voice_type": "none",
            "focus_object": tpl.get("focus", ""),
            "emotion": tpl.get("emotion", "Mystery"),
            "source_text": "[ability template]",
        }

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        return [l.strip() for l in text.strip().split("\n") if l.strip() and not l.startswith("#")]


# ============================================================
# ShotCompiler — 镜头编译（纯逻辑，从config读映射表）
# ============================================================

class ShotCompiler:
    """
    通用镜头编译器。
    景别/运镜/时长规则固定，映射表从config读取。
    """

    DUR_MIN = 3.0
    DUR_MAX = 7.5

    def __init__(self, config: dict):
        self.cfg = config
        self.emotion_shot = config.get("emotion_shot_map", {})
        self.emotion_camera = config.get("emotion_camera_map", {})
        self.emotion_lighting = config.get("emotion_lighting_map", {})
        self.camera_semantic = config.get("camera_semantic_map", {})
        self.voice_emotion = config.get("voice_emotion_map", {})

    def compile(self, beats: list[dict], target_duration: int = 90, location: str = "") -> list[dict]:
        """编译beats为shots"""
        if len(beats) > 25:
            beats = self._merge_beats(beats, 25)

        shots = []
        total = len(beats)
        last_shot_type = None
        last_camera = None
        ecu_count = 0
        recent_pairs = []  # 最近3个(shot_type, camera)组合，防复读

        for i, beat in enumerate(beats):
            shot_type = self._choose_shot_type(beat, i, last_shot_type, ecu_count)
            camera = self._choose_camera(beat, shot_type, last_camera)
            # 连续3镜防复读：如果最近2个都是同一组合，强制换
            pair = (shot_type, camera)
            if len(recent_pairs) >= 2 and recent_pairs[-1] == pair and recent_pairs[-2] == pair:
                # 强制换运镜
                alt_cam = {"static": "push", "push": "static", "pull": "static", "rapid_push": "push", "handheld": "static"}
                camera = alt_cam.get(camera, "push")
                pair = (shot_type, camera)
            recent_pairs.append(pair)
            if len(recent_pairs) > 3:
                recent_pairs.pop(0)
            duration = self._calc_duration(beat, total, target_duration)
            emotion = beat.get("emotion", "Neutral")
            lighting = self.emotion_lighting.get(emotion, "Natural")
            angle = self._choose_angle(emotion)

            if shot_type == "ECU":
                ecu_count += 1

            last_shot_type = shot_type
            last_camera = camera

            shot = {
                "shot_id": i + 1,
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
                "beat_id": beat.get("beat_id"),
            }
            shots.append(shot)

        self._adjust_duration(shots, target_duration)
        return shots

    def _choose_shot_type(self, beat: dict, index: int, last: str | None, ecu_count: int) -> str:
        if index == 0:
            return "WS"
        space = beat.get("space", "Physical")
        focus = beat.get("focus_object", "")
        has_dialogue = bool(beat.get("spoken_dialogue"))

        if space == "Mental":
            return "CU"
        if focus:
            if last == "ECU" or ecu_count >= 2:
                return "CU"
            return "ECU"
        if has_dialogue:
            if last == "MCU":
                return "MS"
            return "MCU"
        emotion = beat.get("emotion", "Neutral")
        preferred = self.emotion_shot.get(emotion, "MS")
        if preferred == last:
            alt = {"CU": "MCU", "MCU": "MS", "MS": "MCU"}
            preferred = alt.get(preferred, "MCU")
        return preferred

    def _choose_camera(self, beat: dict, shot_type: str, last: str | None) -> str:
        # 语义匹配（从config读）
        action = beat.get("action_visual", "").lower()
        for keyword, camera in self.camera_semantic.items():
            if keyword in action:
                return camera
        emotion = beat.get("emotion", "Neutral")
        preferred = self.emotion_camera.get(emotion, "static")
        if preferred == last:
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
    def _calc_duration(beat: dict, total: int, target: int) -> float:
        base = target / max(1, total)
        word_count = len(beat.get("action_visual", "")) + len(beat.get("spoken_dialogue", ""))
        if word_count > 100:
            base *= 1.2
        elif word_count < 30:
            base *= 0.7
        if beat.get("space") == "Mental" or beat.get("focus_object"):
            base *= 1.1
        return round(max(3.0, min(7.5, base)), 1)

    @staticmethod
    def _merge_beats(beats: list[dict], max_count: int) -> list[dict]:
        if len(beats) <= max_count:
            return beats
        scored = []
        for i, b in enumerate(beats):
            score = 0
            if b.get("space") in ("Mental", "Transition"):
                score += 3
            if b.get("focus_object"):
                score += 2
            if b.get("spoken_dialogue"):
                score += 1
            scored.append((i, score))
        keep = set()
        for i, _ in sorted(scored, key=lambda x: -x[1]):
            if len(keep) >= max_count:
                break
            keep.add(i)
        merged = []
        buffer = None
        for i, b in enumerate(beats):
            if i in keep:
                if buffer:
                    merged.append(buffer)
                    buffer = None
                merged.append(b)
            else:
                if buffer:
                    buffer["action_visual"] += " " + b.get("action_visual", "")
                    if b.get("spoken_dialogue") and not buffer.get("spoken_dialogue"):
                        buffer["spoken_dialogue"] = b["spoken_dialogue"]
                else:
                    buffer = dict(b)
        if buffer:
            merged.append(buffer)
        return merged[:max_count]

    @staticmethod
    def _adjust_duration(shots: list[dict], target: int):
        if not shots:
            return
        current = sum(s["duration"] for s in shots)
        if current <= 0:
            return
        ratio = target / current
        for s in shots:
            s["duration"] = round(max(3.0, min(7.5, s["duration"] * ratio)), 1)
        total = sum(s["duration"] for s in shots)
        if total > target * 1.1:
            ratio2 = target / total
            for s in shots:
                s["duration"] = round(max(3.0, s["duration"] * ratio2), 1)


# ============================================================
# PromptRenderer — 英文Prompt生成（从config读角色卡和模板）
# ============================================================

class PromptRenderer:
    """通用Prompt渲染器。所有角色描述从config读取。"""

    SHOT_EN = {"ECU": "extreme close-up", "CU": "close-up", "MCU": "medium close-up",
               "MS": "medium shot", "WS": "wide shot"}
    CAM_EN = {"static": "static camera", "push": "slow dolly forward", "pull": "slow dolly backward",
              "rapid_push": "rapid push-in", "handheld": "handheld camera"}
    ANG_EN = {"eye-level": "eye level", "low": "low angle looking up", "high": "high angle looking down"}
    LIGHT_EN = {"Natural": "natural daylight, soft shadows", "Warm": "warm golden light",
                "Low key": "low key lighting, deep shadows", "High contrast": "high contrast dramatic lighting"}
    MOOD_EN = {"Neutral": "neutral, observational", "Tension": "tense, suspenseful",
               "Shock": "shocked, dramatic", "Sadness": "sad, melancholic",
               "Warmth": "warm, heartwarming", "Mystery": "mysterious, intriguing"}

    def __init__(self, config: dict):
        self.cfg = config
        self.chars = config.get("characters", {})
        self.char_appearance_count = {}

    def reset(self):
        self.char_appearance_count.clear()

    def render(self, shot: dict, location: str = "") -> str:
        """渲染单个shot的veo_prompt"""
        parts = []
        st = shot.get("shot_type", "MS")
        cm = shot.get("camera_movement", "static")
        ca = shot.get("camera_angle", "eye-level")
        parts.append(f"{self.SHOT_EN.get(st, 'medium shot')}, {self.CAM_EN.get(cm, 'static camera')}, {self.ANG_EN.get(ca, 'eye level')}")

        # 角色（首次全写，后续短标签）
        char_parts = []
        for char_en in shot.get("characters", []):
            self.char_appearance_count[char_en] = self.char_appearance_count.get(char_en, 0) + 1
            tag = self._get_char_tag(char_en)
            char_parts.append(f"{char_en} ({tag})")
        if char_parts:
            parts.append(f"featuring {', '.join(char_parts)}")

        action = shot.get("action_visual", "")
        if action:
            parts.append(action)
        anchors = shot.get("visual_anchors", [])
        if anchors:
            parts.append(f"close-up detail on {', '.join(anchors)}")
        if location:
            parts.append(f"in {location}")
        lighting = self.LIGHT_EN.get(shot.get("lighting", "Natural"), "natural daylight")
        parts.append(lighting)
        emotion = shot.get("emotion", "Neutral")
        parts.append(self.MOOD_EN.get(emotion, "neutral, observational"))
        parts.append("cinematic, 9:16 vertical, photorealistic, 4K")
        return ", ".join(parts)

    def _get_char_tag(self, char_en: str) -> str:
        """获取角色标签（首次全写，后续短标签）"""
        for name, info in self.chars.items():
            if info.get("en") == char_en:
                count = self.char_appearance_count.get(char_en, 0)
                if count <= 1:
                    return info.get("full", char_en)
                return info.get("short", char_en)
        return char_en


# ============================================================
# ChapterHook — 章末钩子处理
# ============================================================

class ChapterHook:
    """章末钩子：替换最后1-2个中性动作为悬念动作"""

    def __init__(self, config: dict):
        self.cfg = config.get("chapter_hook", {})
        self.blacklist = self.cfg.get("blacklist", [])
        self.templates = self.cfg.get("templates", [])
        self._counter = 0

    def apply(self, shots: list[dict]):
        """替换章末中性动作"""
        if len(shots) < 2 or not self.templates:
            return
        for shot in shots[-2:]:
            act = shot.get("action_visual", "").lower()
            if any(bad in act for bad in self.blacklist):
                self._counter += 1
                import random
                random.seed(shot["shot_id"] + self._counter)
                char = shot.get("characters", ["Character"])[0]
                shot["action_visual"] = random.choice(self.templates).replace("{char}", char)


# ============================================================
# SRT生成
# ============================================================

def generate_srt(shots: list[dict], output_path: Path):
    """生成剪映标准SRT字幕文件"""
    lines = []
    seq = 1
    t = 0.0
    for shot in shots:
        dur = shot.get("duration", 5.0)
        audio = shot.get("audio", {})
        vt = audio.get("voice_type", "none")
        text = ""
        if vt == "inner_voice" and audio.get("voiceover_zh"):
            text = f"（心声）{audio['voiceover_zh']}"
        elif vt == "onscreen" and audio.get("dialogue_zh"):
            text = audio["dialogue_zh"]
        if text:
            lines.append(f"{seq}")
            lines.append(f"{_fmt_time(t)} --> {_fmt_time(t + dur)}")
            lines.append(text)
            lines.append("")
            seq += 1
        t += dur
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_time(s: float) -> str:
    h, m, sec, ms = int(s // 3600), int(s % 3600 // 60), int(s % 60), int(s % 1 * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


# ============================================================
# 主流程
# ============================================================

def run_pipeline(project_dir: Path):
    """运行完整pipeline"""
    config = load_config(project_dir)
    extractor = BeatExtractor(config)
    compiler = ShotCompiler(config)
    renderer = PromptRenderer(config)
    hook = ChapterHook(config)

    # 从config读取location默认值
    default_location = config.get("default_location", "")
    loc_map = config.get("location_map", {})

    output_dir = project_dir / "v3_storyboard"
    srt_dir = project_dir / "srt_subtitles"
    output_dir.mkdir(exist_ok=True)
    srt_dir.mkdir(exist_ok=True)

    results = []

    for ch_num in range(1, 21):
        ch_path = project_dir / "chapters" / f"{ch_num:03d}.md"
        if not ch_path.exists():
            continue

        chapter_text = ch_path.read_text(encoding="utf-8")

        # Step 1: Beat提取
        beats = extractor.extract(chapter_text)
        if not beats:
            continue

        # Step 2: 检测location
        location = default_location
        for zh, en in loc_map.items():
            if zh in chapter_text:
                location = en
                break

        # Step 3: Shot编译
        shots = compiler.compile(beats, target_duration=90, location=location)

        # Step 4: Prompt渲染
        renderer.reset()
        for shot in shots:
            shot["characters"] = [config["characters"].get(c, {}).get("en", c) for c in shot.get("characters", [])]
            shot["veo_prompt"] = renderer.render(shot, location)

            # 音频轨道
            beat_data = beats[shot["shot_id"] - 1] if shot["shot_id"] <= len(beats) else {}
            shot["audio"] = {
                "dialogue_zh": beat_data.get("spoken_dialogue", ""),
                "dialogue_speaker": beat_data.get("dialogue_speaker", ""),
                "voiceover_zh": beat_data.get("inner_voice", ""),
                "voice_type": beat_data.get("voice_type", "none"),
                "subtitle": beat_data.get("inner_voice", "")[:30] if beat_data.get("inner_voice") else "",
                "emotion_tag": compiler.voice_emotion.get(shot.get("emotion", "Neutral"), "calm"),
                "duration_hint": f"{shot['duration']:.1f}s",
            }

        # Step 5: 章末钩子
        hook.apply(shots)

        # Step 6: 保存
        (output_dir / f"ch{ch_num:03d}_shots.json").write_text(json.dumps(shots, ensure_ascii=False, indent=2))
        (output_dir / f"ch{ch_num:03d}_beats.json").write_text(json.dumps(beats, ensure_ascii=False, indent=2))
        generate_srt(shots, srt_dir / f"ch{ch_num:03d}.srt")

        total_dur = sum(s["duration"] for s in shots)
        cn = sum(1 for s in shots if any("\u4e00" <= c <= "\u9fff" for c in s.get("veo_prompt", "")))
        results.append((ch_num, len(shots), round(total_dur), cn))
        print(f"Ch{ch_num:>2}: {len(shots):>2}S {total_dur:>3.0f}s CN:{cn}", flush=True)

    print(f"\n{'='*60}")
    ts = sum(r[1] for r in results)
    tcn = sum(r[3] for r in results)
    print(f"{len(results)}/20 done | {ts} shots | {tcn} CN")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="StoryBeat Pipeline")
    parser.add_argument("project_dir", help="Path to project directory")
    args = parser.parse_args()
    run_pipeline(Path(args.project_dir))
