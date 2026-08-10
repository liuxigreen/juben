"""
StoryBeat Pipeline v2.0 — 通用分镜引擎

架构原则：
1. 代码零硬编码
2. 配置分层加载（主config→子文件）
3. 事件类型化（ability/vision/evidence都是event recipe）
4. 钩子冷却（LRU策略）
5. Beat合并策略（config声明）
6. 质量评分（不hard fail，给分）
"""
import json, re, sys, os, time
from pathlib import Path
from typing import Any

import yaml


# ============================================================
# 配置加载（支持分层）
# ============================================================

def load_config(project_dir: Path) -> dict:
    """加载主配置 + 所有子配置"""
    main_path = project_dir / "project_config.yaml"
    if not main_path.exists():
        raise FileNotFoundError(f"Config not found: {main_path}")
    with open(main_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 加载子配置
    config_dir = project_dir
    paths = cfg.get("config_paths", {})
    for key, rel_path in paths.items():
        full_path = config_dir / rel_path
        if full_path.exists():
            with open(full_path, encoding="utf-8") as f:
                cfg[key] = yaml.safe_load(f)

    return cfg


# ============================================================
# 事件引擎（通用event recipe）
# ============================================================

class EventEngine:
    """通用事件引擎：根据触发词匹配event recipe，注入镜头序列"""

    def __init__(self, events: list[dict]):
        self.events = events or []

    def match(self, text: str) -> dict | None:
        """匹配事件类型"""
        for event in self.events:
            triggers = event.get("triggers", [])
            if any(kw in text for kw in triggers):
                return event
        return None

    def make_recipe_beats(self, event: dict, char: str, beat_id_start: int) -> list[dict]:
        """从event recipe生成beats"""
        beats = []
        for i, recipe in enumerate(event.get("shot_recipe", [])):
            beats.append({
                "beat_id": beat_id_start + i,
                "space": recipe.get("space", "Physical"),
                "characters_present": [char],
                "primary_char": char,
                "action_visual": recipe.get("action", "").replace("{char}", char),
                "spoken_dialogue": "",
                "dialogue_speaker": "",
                "inner_voice": "",
                "voice_type": "none",
                "focus_object": recipe.get("focus", ""),
                "emotion": recipe.get("emotion", "Neutral"),
                "source_text": f"[event: {event.get('type', 'unknown')}]",
                "event_type": event.get("type"),
            })
        return beats


# ============================================================
# 钩子管理器（LRU冷却）
# ============================================================

class HookManager:
    """钩子模板管理器，支持LRU冷却"""

    def __init__(self, config: dict):
        hook_cfg = config.get("hook_templates", {})
        if isinstance(hook_cfg, dict):
            self.templates = hook_cfg.get("hook_templates", [])
            self.blacklist = hook_cfg.get("blacklist", [])
            sel = hook_cfg.get("hook_selection", {})
            self.cooldown = sel.get("forbid_repeat_within", 2)
        else:
            self.templates = []
            self.blacklist = []
            self.cooldown = 2

        self._usage_history = []  # 最近使用的template id

    def apply(self, shots: list[dict]):
        """替换章末中性动作为钩子"""
        if len(shots) < 2 or not self.templates:
            return

        for shot in shots[-2:]:
            act = shot.get("action_visual", "").lower()
            if not any(bad in act for bad in self.blacklist):
                continue

            # LRU选择：找最近未用的模板
            tpl = self._pick_template()
            if tpl:
                char = shot.get("characters", ["Character"])[0]
                shot["action_visual"] = tpl["text"].replace("{char}", char)
                self._usage_history.append(tpl["id"])
                if len(self._usage_history) > 10:
                    self._usage_history.pop(0)

    def _pick_template(self) -> dict | None:
        """LRU选择模板"""
        recent = set(self._usage_history[-self.cooldown:]) if self._usage_history else set()
        for tpl in self.templates:
            if tpl["id"] not in recent:
                return tpl
        # 全部冷却中，选最久未用的
        for tpl in self.templates:
            if self._usage_history and tpl["id"] != self._usage_history[-1]:
                return tpl
        return self.templates[0] if self.templates else None


# ============================================================
# BeatExtractor
# ============================================================

class BeatExtractor:
    """通用Beat提取器"""

    def __init__(self, config: dict):
        self.cfg = config
        self.chars = config.get("characters", {})
        self.events = config.get("events", {})
        self.event_engine = EventEngine(self.events.get("events", []) if isinstance(self.events, dict) else [])
        self.triggers = config.get("beat_triggers", {})
        self.action_rules = config.get("action_rules", {})
        self.action_templates = self.action_rules.get("action_templates", [])
        self.action_rewrite = self.action_rules.get("action_rewrite", {})
        self.anchor_map = self.action_rules.get("anchor_map", {})
        self.micro_actions = self.action_rules.get("micro_actions", {})
        self.nouns = self.action_rules.get("nouns", {})
        self.verbs = self.action_rules.get("verbs", {})
        self.style = config.get("prompt_style", {})
        self.emotion_map = self.style.get("emotion_map", {})
        self.space_map = self.style.get("space_map", {})
        self.merge_cfg = self.style.get("beat_merge", {})

    def extract(self, chapter_text: str) -> list[dict]:
        paras = self._split(chapter_text)
        if not paras:
            return []

        beats = []
        current_group = []
        beat_id = 1
        prev_speaker = ""
        in_event = False

        for para in paras:
            speaker = self._detect_speaker(para, prev_speaker)
            prev_text = current_group[-1] if current_group else ""

            if current_group and self._should_cut(prev_text, para, prev_speaker, speaker):
                combined = "\n".join(current_group)

                # 检查是否匹配事件recipe
                event = self.event_engine.match(combined)
                if event and not in_event:
                    primary = self._detect_subject(combined)
                    recipe_beats = self.event_engine.make_recipe_beats(event, primary, beat_id)
                    beats.extend(recipe_beats)
                    beat_id += len(recipe_beats)
                    in_event = True
                    current_group = [para]
                    prev_speaker = speaker
                    continue

                beat = self._make_beat(beat_id, current_group)
                if beat:
                    beats.append(beat)
                    beat_id += 1
                current_group = []
                in_event = False

            current_group.append(para)
            if speaker:
                prev_speaker = speaker

        if current_group:
            beat = self._make_beat(beat_id, current_group)
            if beat:
                beats.append(beat)

        return beats

    def _should_cut(self, prev_text: str, curr_text: str, prev_sp: str, curr_sp: str) -> bool:
        # 事件触发
        if self.event_engine.match(curr_text):
            return True
        # 痕迹
        if any(kw in curr_text for kw in self.triggers.get("trace", [])):
            return True
        # 说话人切换
        if curr_sp and prev_sp and curr_sp != prev_sp:
            return True
        # 对话→叙述
        if re.search(r'["\u300c]', prev_text) and not re.search(r'["\u300c]', curr_text):
            return True
        # 场景
        scene_kw = self.triggers.get("scene", [])
        if any(kw in curr_text for kw in scene_kw) and not any(kw in prev_text for kw in scene_kw):
            return True
        # 动作
        if any(kw in curr_text for kw in self.triggers.get("action", [])):
            return True
        # 情绪
        if any(kw in curr_text for kw in self.triggers.get("emotion", [])):
            return True
        # 通讯
        comm = self.triggers.get("comm_pattern", "")
        if comm and re.search(comm, curr_text):
            return True
        return False

    # --- 角色检测 ---
    def _detect_chars(self, text: str) -> list[str]:
        found = []
        for name, info in self.chars.items():
            if name in text:
                found.append(info["en"])
            elif any(p in text for p in info.get("pronouns", [])):
                found.append(info["en"])
        return found if found else [self._default_char()]

    def _detect_subject(self, text: str) -> str:
        for name, info in self.chars.items():
            if name in text:
                return info["en"]
        for name, info in self.chars.items():
            if any(p in text for p in info.get("pronouns", [])):
                return info["en"]
        return self._default_char()

    def _default_char(self) -> str:
        for name, info in self.chars.items():
            if info.get("role") == "protagonist":
                return info["en"]
        return list(self.chars.values())[0]["en"] if self.chars else "Character"

    def _detect_speaker(self, para: str, prev: str) -> str:
        for name, info in self.chars.items():
            if re.search(rf"{name}(?:说|道|问|答|喊|叫)", para):
                return info["en"]
        if re.search(r"他(?:说|道|问|答)", para):
            male = [i["en"] for i in self.chars.values() if i.get("gender") == "male"]
            return prev if prev in male else (male[0] if male else prev)
        if re.search(r"她(?:说|道|问|答)", para):
            female = [i["en"] for i in self.chars.values() if i.get("gender") == "female"]
            return prev if prev in female else (female[0] if female else prev)
        if re.search(r'["\u300c]', para):
            for name, info in self.chars.items():
                if name in para:
                    return info["en"]
        return prev

    # --- 动作翻译 ---
    def _translate_action(self, text: str, char: str) -> str:
        for tpl in self.action_templates:
            if re.search(tpl["pattern"], text):
                result = tpl["en"].replace("{char}", char) if "{char}" in tpl["en"] else tpl["en"]
                return self._apply_rewrite(result, char)
        for zh, en in self.micro_actions.items():
            if zh in text:
                return self._apply_rewrite(f"{char} {en}", char)
        fn = [self.nouns[k] for k in self.nouns if k in text]
        fv = [self.verbs[k] for k in self.verbs if k in text]
        if fv and fn:
            return self._apply_rewrite(f"{char} {fv[0]} the {fn[0]}", char)
        if fv:
            return self._apply_rewrite(f"{char} {fv[0]}", char)
        if fn:
            return self._apply_rewrite(f"{char} gazes at the {fn[0]}", char)
        fallback = self.action_rules.get("action_fallback", "{char} stands still")
        return self._apply_rewrite(fallback.replace("{char}", char), char)

    def _apply_rewrite(self, action: str, char: str) -> str:
        action_lower = action.lower()
        for bad, rewrite in self.action_rewrite.items():
            if bad in action_lower:
                return rewrite.replace("{char}", char)
        return action

    # --- 辅助 ---
    def _extract_dialogue(self, text: str) -> list[str]:
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
        results = []
        for p in [r'\*["](.*?)["]\*', r'\*[\u300c](.*?)[\u300d]\*', r'\*(.{5,}?)\*']:
            results.extend(re.findall(p, text))
        return results

    def _extract_anchor(self, text: str) -> str:
        for zh, en in self.anchor_map.items():
            if zh in text:
                return en
        return ""

    def _detect_emotion(self, text: str) -> str:
        for emotion, keywords in self.emotion_map.items():
            if any(kw in text for kw in keywords):
                return emotion
        return "Neutral"

    def _detect_space(self, text: str) -> str:
        for space, keywords in self.space_map.items():
            if any(kw in text for kw in keywords):
                return space
        return "Physical"

    def _make_beat(self, beat_id: int, paragraphs: list[str]) -> dict | None:
        text = "\n".join(paragraphs)
        chars = self._detect_chars(text)
        primary = self._detect_subject(text)
        action = self._translate_action(text, primary)
        inner = self._extract_inner_voice(text)
        dialogues = self._extract_dialogue(text)

        dlg_text, dlg_speaker, voice_text, vt = "", "", "", "none"
        hints = self.triggers.get("inner_voice_hints", ["……"])

        if inner:
            voice_text = inner[0][:100]
        if dialogues:
            raw = dialogues[0][:80]
            if any(raw.startswith(h) for h in hints):
                voice_text = voice_text or raw
            elif not voice_text:
                dlg_text = raw
                for name, info in self.chars.items():
                    if name in text:
                        dlg_speaker = info["en"]
                        break
                if not dlg_speaker:
                    dlg_speaker = primary

        if voice_text:
            vt = "inner_voice"
        elif dlg_text:
            vt = "onscreen"

        return {
            "beat_id": beat_id,
            "space": self._detect_space(text),
            "characters_present": chars,
            "primary_char": primary,
            "action_visual": action,
            "spoken_dialogue": dlg_text,
            "dialogue_speaker": dlg_speaker,
            "inner_voice": voice_text,
            "voice_type": vt,
            "focus_object": self._extract_anchor(text),
            "emotion": self._detect_emotion(text),
            "source_text": text[:80],
        }

    @staticmethod
    def _split(text: str) -> list[str]:
        return [l.strip() for l in text.strip().split("\n") if l.strip() and not l.startswith("#")]


# ============================================================
# ShotCompiler（含防复读 + 合并策略）
# ============================================================

class ShotCompiler:
    DUR_MIN, DUR_MAX = 3.0, 7.5

    def __init__(self, config: dict):
        self.cfg = config
        self.style = config.get("prompt_style", {})
        self.emotion_shot = self.style.get("emotion_shot_map", {})
        self.emotion_camera = self.style.get("emotion_camera_map", {})
        self.emotion_lighting = self.style.get("emotion_lighting_map", {})
        self.camera_semantic = self.style.get("camera_semantic_map", {})
        self.voice_emotion = self.style.get("voice_emotion_map", {})
        self.merge_cfg = self.style.get("beat_merge", {})

    def compile(self, beats: list[dict], target: int | None = 90, location: str = "") -> list[dict]:
        """target=总时长目标(秒)做整体缩放；target=None 时不限制总时长，
        每镜头按剧情+台词自然长度走（适合逐镜头生成后剪成长视频）。"""
        max_shots = self.merge_cfg.get("max_shots_per_chapter", 25)
        if len(beats) > max_shots:
            beats = self._merge_beats(beats, max_shots)

        shots = []
        total = len(beats)
        last_st, last_cam, ecu_count = None, None, 0
        recent_pairs = []

        for i, beat in enumerate(beats):
            st = self._choose_shot_type(beat, i, last_st, ecu_count)
            cam = self._choose_camera(beat, st, last_cam)
            pair = (st, cam)
            if len(recent_pairs) >= 2 and recent_pairs[-1] == pair and recent_pairs[-2] == pair:
                alt = {"static": "push", "push": "static", "pull": "static", "rapid_push": "push", "handheld": "static"}
                cam = alt.get(cam, "push")
                pair = (st, cam)
            recent_pairs.append(pair)
            if len(recent_pairs) > 3:
                recent_pairs.pop(0)

            dur = self._calc_duration(beat, total, target)
            emotion = beat.get("emotion", "Neutral")

            if st == "ECU":
                ecu_count += 1
            last_st, last_cam = st, cam

            # 台词念白保底时长（供_adjust保护，不被缩放击穿）
            vt = beat.get("voice_type", "none")
            line_en = beat.get("inner_voice_en", "") if vt == "inner_voice" else beat.get("line_en", "")
            sfloor = round(len(line_en.split()) / 3.0 + 0.6, 1) if line_en else 3.0

            shots.append({
                "shot_id": i + 1, "shot_type": st, "camera_movement": cam,
                "camera_angle": self._angle(emotion), "duration": dur,
                "_speech_floor": sfloor,
                "location": location, "space": beat.get("space", "Physical"),
                "characters": beat.get("characters_present", []),
                "action_visual": beat.get("action_visual", ""),
                "dialogue": beat.get("spoken_dialogue", ""),
                "inner_voice": beat.get("inner_voice", ""),
                "focus_object": beat.get("focus_object", ""),
                "lighting": self.emotion_lighting.get(emotion, "Natural"),
                "emotion": emotion,
                "visual_anchors": [beat.get("focus_object", "")] if beat.get("focus_object") else [],
                "beat_id": beat.get("beat_id"),
                "event_type": beat.get("event_type", ""),
            })

        if target:
            self._adjust(shots, target)
        return shots

    # 动作文本显式指定景别时的识别（服从剧本，避免机位与动作描述打架）
    SHOT_KEYWORDS = [
        ("ECU", ["extreme close-up", "extreme closeup", "macro", "怼脸", "大特写"]),
        ("CU",  ["close-up", "close up", "closeup", "特写"]),
        ("WS",  ["wide shot", "wide angle", "establishing shot", "远景", "全景"]),
        ("MS",  ["medium shot", "中景"]),
        ("MCU", ["medium close-up", "medium closeup", "中近景"]),
    ]

    def _explicit_shot(self, beat):
        """动作描述里显式写了景别就返回它，否则 None。ECU/CU 优先匹配。"""
        act = beat.get("action_visual", "").lower()
        for st, kws in self.SHOT_KEYWORDS:
            if any(kw in act for kw in kws):
                return st
        return None

    def _choose_shot_type(self, beat, idx, last, ecu):
        # 动作文本显式指定景别 → 服从剧本（冷开场特写钩子等，优先级最高）
        # 出海英文配音模式下口型由Veo跟台词生成，说话镜头也可怼脸(ECU)秀口型对齐
        explicit = self._explicit_shot(beat)
        if explicit:
            return explicit
        if idx == 0:
            return "WS"
        if beat.get("space") == "Mental":
            return "CU"
        # onscreen 对话：按情绪给景别（激烈情绪可怼脸CU秀口型），优先于道具特写
        if beat.get("spoken_dialogue") and beat.get("voice_type") == "onscreen":
            pref = self.emotion_shot.get(beat.get("emotion", "Neutral"), "MCU")
            if pref == last:
                pref = {"ECU": "CU", "CU": "MCU", "MCU": "MS", "MS": "MCU"}.get(pref, "MCU")
            return pref
        focus = beat.get("focus_object", "")
        if focus:
            return "CU" if (last == "ECU" or ecu >= 2) else "ECU"
        if beat.get("spoken_dialogue"):
            return "MS" if last == "MCU" else "MCU"
        pref = self.emotion_shot.get(beat.get("emotion", "Neutral"), "MS")
        if pref == last:
            pref = {"CU": "MCU", "MCU": "MS", "MS": "MCU"}.get(pref, "MCU")
        return pref

    def _choose_camera(self, beat, st, last):
        act = beat.get("action_visual", "").lower()
        for kw, cam in self.camera_semantic.items():
            if kw in act:
                return cam
        pref = self.emotion_camera.get(beat.get("emotion", "Neutral"), "static")
        if pref == last:
            pref = {"static": "push", "push": "static", "pull": "static", "rapid_push": "push"}.get(pref, "static")
        return pref

    @staticmethod
    def _angle(emotion):
        return "low" if emotion in ("Shock", "Tension") else "high" if emotion == "Sadness" else "eye-level"

    @staticmethod
    def _calc_duration(beat, total, target):
        # target=None：不限总时长，每镜给自然基准5s，再按台词/内容微调
        base = (target / max(1, total)) if target else 5.0
        wc = len(beat.get("action_visual", "")) + len(beat.get("spoken_dialogue", ""))
        if wc > 100: base *= 1.2
        elif wc < 30: base *= 0.7
        if beat.get("space") == "Mental" or beat.get("focus_object"):
            base *= 1.1
        # 台词保底：有英文台词时，时长必须够念完（英文约3词/秒 + 0.6s头尾停顿）
        # 否则配音会被截断（"I'm out"丢失）。取 line_en 或按语音类型选源
        vt = beat.get("voice_type", "none")
        line_en = beat.get("inner_voice_en", "") if vt == "inner_voice" else beat.get("line_en", "")
        speech_floor = 0.0
        if line_en:
            speech_floor = len(line_en.split()) / 3.0 + 0.6
        return round(max(3.0, speech_floor, min(7.5, base)), 1)

    def _merge_beats(self, beats, max_count):
        never_merge = set(self.merge_cfg.get("never_merge", []))
        scored = []
        for i, b in enumerate(beats):
            s = 0
            if b.get("space") in ("Mental", "Transition"): s += 3
            if b.get("focus_object"): s += 2
            if b.get("spoken_dialogue"): s += 1
            if b.get("event_type"): s += 5  # 事件beat永不合并
            scored.append((i, s))
        keep = set()
        for i, _ in sorted(scored, key=lambda x: -x[1]):
            if len(keep) >= max_count: break
            keep.add(i)
        merged, buf = [], None
        for i, b in enumerate(beats):
            if i in keep:
                if buf: merged.append(buf); buf = None
                merged.append(b)
            else:
                if buf:
                    buf["action_visual"] += " " + b.get("action_visual", "")
                    if b.get("spoken_dialogue") and not buf.get("spoken_dialogue"):
                        buf["spoken_dialogue"] = b["spoken_dialogue"]
                else:
                    buf = dict(b)
        if buf: merged.append(buf)
        return merged[:max_count]

    @staticmethod
    def _adjust(shots, target):
        if not shots: return
        # 台词镜头的念白保底时长(speech_floor)不可被缩放击穿，否则配音截断
        def floor(s):
            return s.get("_speech_floor", 3.0)
        cur = sum(s["duration"] for s in shots)
        if cur <= 0: return
        r = target / cur
        for s in shots:
            s["duration"] = round(max(floor(s), min(8.0, s["duration"] * r)), 1)
        # 若因保底导致总时长超标，只压缩"无台词、超过3s"的镜头，保护念白镜头
        t = sum(s["duration"] for s in shots)
        if t > target * 1.15:
            flex = [s for s in shots if floor(s) <= 3.0 and s["duration"] > 3.0]
            excess = t - target
            flex_total = sum(s["duration"] - 3.0 for s in flex)
            if flex_total > 0:
                r2 = max(0.0, 1 - excess / flex_total)
                for s in flex:
                    s["duration"] = round(max(3.0, 3.0 + (s["duration"] - 3.0) * r2), 1)


# ============================================================
# PromptRenderer
# ============================================================

class PromptRenderer:
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
        self.chars = config.get("characters", {})
        style = config.get("prompt_style", {})
        active = style.get("active_renderer", "flow_v1")
        renderers = style.get("renderers", {})
        self.renderer_cfg = renderers.get(active, {})
        self.renderer_style = self.renderer_cfg.get("style", "hybrid")
        self.suffix = self.renderer_cfg.get("suffix", "cinematic, 9:16 vertical, photorealistic, 4K")
        self.char_first = self.renderer_cfg.get("character_first", True)
        # character_mode: "reference"=只引用角色名(配合Flow角色系统) | "inline"=每镜头塞长相描述
        self.char_mode = self.renderer_cfg.get("character_mode", "inline")
        # 音频/口型控制（Veo 3.1 适配）
        self.audio_cfg = style.get("audio_control", {})
        # 情绪→面部表演指令（有角色时注入，解决表情不丰富）
        self.expression_map = self.audio_cfg.get("expression_map", {})
        self._count = {}

    def reset(self):
        self._count.clear()

    def render(self, shot: dict, location: str = "") -> str:
        if self.renderer_style == "keyword":
            return self._render_keyword(shot, location)
        elif self.renderer_style == "concise":
            return self._render_concise(shot, location)
        else:
            return self._render_narrative(shot, location)

    def _render_narrative(self, shot, location):
        """叙事型（Veo/Flow）：完整句子描述"""
        parts = []
        st, cm, ca = shot.get("shot_type", "MS"), shot.get("camera_movement", "static"), shot.get("camera_angle", "eye-level")
        parts.append(f"{self.SHOT_EN.get(st, 'medium shot')}, {self.CAM_EN.get(cm, 'static camera')}, {self.ANG_EN.get(ca, 'eye level')}")
        if self.char_first:
            cp = []
            for ce in shot.get("characters", []):
                self._count[ce] = self._count.get(ce, 0) + 1
                cp.append(self._char_phrase(ce))
            if cp: parts.append(f"featuring {', '.join(cp)}")
        act = shot.get("action_visual", "")
        if act: parts.append(act)
        if not self.char_first:
            cp = []
            for ce in shot.get("characters", []):
                self._count[ce] = self._count.get(ce, 0) + 1
                cp.append(self._char_phrase(ce))
            if cp: parts.append(f"featuring {', '.join(cp)}")
        anchors = shot.get("visual_anchors", [])
        if anchors: parts.append(f"close-up detail on {', '.join(anchors)}")
        if location: parts.append(f"in {location}")
        parts.append(self.LIGHT_EN.get(shot.get("lighting", "Natural"), "natural daylight"))
        parts.append(self.MOOD_EN.get(shot.get("emotion", "Neutral"), "neutral, observational"))
        # 面部表演层：有角色出镜才注入具体微表情（空镜/道具特写不加）
        if shot.get("characters"):
            expr = self.expression_map.get(shot.get("emotion", "Neutral"), "")
            if expr:
                subj = shot["characters"][0] if len(shot["characters"]) == 1 else "the characters"
                parts.append(f"{subj}: {expr}")
        # 口型 + 音轨控制层（Veo 3.1）
        mouth, audio = self._audio_parts(shot, location)
        if mouth: parts.append(mouth)
        parts.append(self.suffix)
        if audio: parts.append(audio)
        return ", ".join(parts)

    def _spk_en(self, shot):
        """dialogue_speaker → 英文名（已是英文则原样返回）"""
        chars = shot.get("characters", [])
        spk = shot.get("dialogue_speaker", "")
        if spk in chars:
            return spk
        info = self.chars.get(spk)
        return info.get("en", "") if isinstance(info, dict) else ""

    def _audio_parts(self, shot, location):
        """返回 (表演/口型指令, 音轨指令)。支持两种模式：
        dubbed_en : Veo 直接出英文配音+口型（出海）
        post_dub  : 嘴动不吐词/锁嘴，后期配音"""
        if not self.audio_cfg.get("enabled"):
            return "", ""
        mode = self.audio_cfg.get("mode", "post_dub")
        vt = shot.get("voice_type", "none")
        chars = shot.get("characters", [])
        ambient = self.audio_cfg.get("ambient_map", {}).get(
            location, self.audio_cfg.get("default_ambient", ""))
        if mode == "dubbed_en":
            return self._audio_dubbed_en(shot, vt, chars, ambient)
        return self._audio_post_dub(shot, vt, chars, ambient)

    def _audio_dubbed_en(self, shot, vt, chars, ambient):
        cfg = self.audio_cfg.get("dubbed_en", {})
        accent = self.audio_cfg.get("accent", "American accent")
        tone = self.audio_cfg.get("tone_map", {}).get(shot.get("emotion", "Neutral"), "calm, even")
        spk_en = self._spk_en(shot)
        line_en = shot.get("line_en", "")
        mouth, audio = "", ""
        if vt == "onscreen" and line_en and spk_en:
            if len(chars) > 1:
                others = [c for c in chars if c != spk_en]
                mouth = cfg.get("onscreen_multi_tpl", "").format(
                    speaker=spk_en, line_en=line_en, tone=tone, accent=accent,
                    others=", ".join(others))
            else:
                mouth = cfg.get("onscreen_tpl", "").format(
                    speaker=spk_en, line_en=line_en, tone=tone, accent=accent)
            audio = cfg.get("dialogue_audio", "")
        elif vt == "inner_voice" and line_en:
            spk = spk_en or (chars[0] if chars else "the character")
            mouth = cfg.get("inner_voice_tpl", "").format(
                speaker=spk, line_en=line_en, tone=tone, accent=accent)
            iva = cfg.get("inner_voice_audio", "")
            audio = f"{ambient}, {iva}" if ambient else iva
        else:
            if chars:
                mouth = cfg.get("none_mouth", "lips closed, no speaking")
            suffix = cfg.get("ambient_suffix", "")
            audio = f"{ambient}, {suffix}" if ambient else suffix
        return mouth, audio

    def _audio_post_dub(self, shot, vt, chars, ambient):
        cfg = self.audio_cfg.get("post_dub", {})
        mm = cfg.get("mouth_map", {})
        mouth = ""
        if chars:
            if vt == "onscreen" and len(chars) > 1:
                spk_en = self._spk_en(shot)
                if spk_en and spk_en in chars:
                    others = [c for c in chars if c != spk_en]
                    mouth = f"{spk_en} {mm.get('onscreen','')}; {', '.join(others)} listening with lips closed"
                else:
                    mouth = mm.get("onscreen", "")
            else:
                mouth = mm.get(vt, "")
        if vt == "inner_voice":
            audio = cfg.get("inner_voice_audio", "")
        else:
            suffix = cfg.get("audio_suffix", "")
            audio = f"{ambient}, {suffix}" if ambient else suffix
        return mouth, audio

    def _render_keyword(self, shot, location):
        """关键词型（Kling）：逗号分隔关键词"""
        parts = []
        st = shot.get("shot_type", "MS")
        parts.append(self.SHOT_EN.get(st, "medium shot"))
        act = shot.get("action_visual", "")
        if act: parts.append(act)
        for ce in shot.get("characters", []):
            self._count[ce] = self._count.get(ce, 0) + 1
            parts.append(ce)
        anchors = shot.get("visual_anchors", [])
        if anchors: parts.extend(anchors)
        if location: parts.append(location)
        parts.append(self.LIGHT_EN.get(shot.get("lighting", "Natural"), "").split(",")[0])
        parts.append(self.suffix)
        return ", ".join(parts)

    def _render_concise(self, shot, location):
        """简洁型（Runway）：主体+动作+风格"""
        parts = []
        act = shot.get("action_visual", "")
        chars = ", ".join(shot.get("characters", []))
        if chars and act:
            parts.append(f"{chars}: {act}")
        elif act:
            parts.append(act)
        if location: parts.append(f"in {location}")
        parts.append(self.suffix)
        return ", ".join(parts)

    def _char_phrase(self, ce):
        # reference 模式：只输出角色名（无括号描述），配合 Flow 角色系统
        tag = self._tag(ce)
        return f"{ce} ({tag})" if tag else ce

    def _tag(self, ce):
        # reference 模式：只用角色名，长相由 Flow 角色系统保证一致（不塞描述）
        if self.char_mode == "reference":
            return ""
        for info in self.chars.values():
            if info.get("en") == ce:
                return info.get("full", ce) if self._count.get(ce, 0) <= 1 else info.get("short", ce)
        return ce


# ============================================================
# 质量评分
# ============================================================

class QualityScorer:
    """通用质量评分（不hard fail，给分）"""

    def score(self, shots: list[dict], beats: list[dict]) -> dict:
        total = len(shots)
        if total == 0:
            return {"total": 0, "scores": {}}

        scores = {}

        # 1. action_has_verb_object: 动作是否有主谓宾
        has_verb = sum(1 for s in shots if self._has_verb_object(s.get("action_visual", "")))
        scores["action_completeness"] = round(has_verb / total * 100)

        # 2. focus_rendered: 有focus时是否在prompt里
        focus_shots = [s for s in shots if s.get("focus_object")]
        if focus_shots:
            rendered = sum(1 for s in focus_shots if s.get("focus_object", "").lower() in s.get("veo_prompt", "").lower())
            scores["focus_rendered"] = round(rendered / len(focus_shots) * 100)
        else:
            scores["focus_rendered"] = 100

        # 3. shot_variety: 连续3镜多样性
        repeats = 0
        for i in range(2, total):
            p1 = (shots[i-2]["shot_type"], shots[i-2]["camera_movement"])
            p2 = (shots[i-1]["shot_type"], shots[i-1]["camera_movement"])
            p3 = (shots[i]["shot_type"], shots[i]["camera_movement"])
            if p1 == p2 == p3: repeats += 1
        scores["shot_variety"] = round((1 - repeats / max(1, total - 2)) * 100)

        # 4. dialogue_voice_separation
        overlap = sum(1 for s in shots if s.get("audio", {}).get("dialogue_zh") and s.get("audio", {}).get("voiceover_zh"))
        scores["audio_separation"] = round((1 - overlap / max(1, total)) * 100)

        # 5. character_coverage
        empty_chars = sum(1 for s in shots if not s.get("characters"))
        scores["character_coverage"] = round((1 - empty_chars / max(1, total)) * 100)

        scores["overall"] = round(sum(scores.values()) / len(scores))
        return {"total": total, "scores": scores}

    @staticmethod
    def _has_verb_object(text: str) -> bool:
        if not text: return False
        words = text.split()
        return len(words) >= 3  # 至少主+谓+宾


# ============================================================
# SRT
# ============================================================

def generate_srt(shots, path):
    lines, seq, t = [], 1, 0.0
    for shot in shots:
        dur = shot.get("duration", 5.0)
        a = shot.get("audio", {})
        vt = a.get("voice_type", "none")
        txt = ""
        if vt == "inner_voice" and a.get("voiceover_zh"):
            txt = f"（心声）{a['voiceover_zh']}"
        elif vt == "onscreen" and a.get("dialogue_zh"):
            txt = a["dialogue_zh"]
        if txt:
            lines.append(f"{seq}\n{_fmt(t)} --> {_fmt(t+dur)}\n{txt}\n")
            seq += 1
        t += dur
    path.write_text("\n".join(lines), encoding="utf-8")

def _fmt(s):
    return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d},{int(s%1*1000):03d}"


# ============================================================
# 主流程
# ============================================================

def run_pipeline(project_dir: Path, only_chapter=None):
    cfg = load_config(project_dir)
    extractor = BeatExtractor(cfg)
    compiler = ShotCompiler(cfg)
    renderer = PromptRenderer(cfg)
    hook = HookManager(cfg)
    scorer = QualityScorer()

    default_loc = cfg.get("default_location", "")
    loc_map = cfg.get("locations", {})
    if isinstance(loc_map, dict):
        loc_map = {k: v for k, v in loc_map.items() if isinstance(v, str)}

    # === v1.1.0: 最大章节数改为从config读取, 默认扫描实际chapters/目录 ===
    max_chapter_cfg = cfg.get("max_chapter", 0)
    if max_chapter_cfg > 0:
        max_chapter = max_chapter_cfg
    else:
        # 自动扫描 chapters/ 目录获取最大章节号
        ch_dir = project_dir / "chapters"
        max_chapter = 0
        if ch_dir.exists():
            for f in ch_dir.glob("*.md"):
                try:
                    n = int(f.stem.lstrip("0") or "0")
                    if n > max_chapter:
                        max_chapter = n
                except ValueError:
                    pass
    if max_chapter == 0:
        max_chapter = 20  # fallback

    out = project_dir / "v3_storyboard"
    srt_dir = project_dir / "srt_subtitles"
    out.mkdir(exist_ok=True)
    srt_dir.mkdir(exist_ok=True)

    results = []
    total_score = {"action_completeness": 0, "focus_rendered": 0, "shot_variety": 0, "audio_separation": 0, "character_coverage": 0}

    # 跳过已 lock 的章节 (存在 .md.locked 表示内容已定稿, 不应重复转分镜)
    for ch in range(1, max_chapter + 1):
        if only_chapter and ch != only_chapter:
            continue
        ch_path = project_dir / "chapters" / f"{ch:03d}.md"
        lock_path = project_dir / "chapters" / f"{ch:03d}.md.locked"
        if not ch_path.exists(): continue
        if lock_path.exists(): continue  # 已 lock, 跳过

        text = ch_path.read_text(encoding="utf-8")
        beats = extractor.extract(text)
        if not beats: continue

        loc = default_loc
        if isinstance(loc_map, dict):
            for zh, en in loc_map.items():
                if zh in text: loc = en; break

        shots = compiler.compile(beats, 90, loc)
        renderer.reset()
        for shot in shots:
            shot["characters"] = [cfg.get("characters", {}).get(c, {}).get("en", c) for c in shot.get("characters", [])]
            shot["veo_prompt"] = renderer.render(shot, loc)
            bd = beats[shot["shot_id"] - 1] if shot["shot_id"] <= len(beats) else {}
            shot["audio"] = {
                "dialogue_zh": bd.get("spoken_dialogue", ""),
                "dialogue_speaker": bd.get("dialogue_speaker", ""),
                "voiceover_zh": bd.get("inner_voice", ""),
                "voice_type": bd.get("voice_type", "none"),
                "subtitle": bd.get("inner_voice", "")[:30] if bd.get("inner_voice") else "",
                "emotion_tag": compiler.voice_emotion.get(shot.get("emotion", "Neutral"), "calm"),
                "duration_hint": f"{shot['duration']:.1f}s",
            }
        hook.apply(shots)

        (out / f"ch{ch:03d}_shots.json").write_text(json.dumps(shots, ensure_ascii=False, indent=2))
        (out / f"ch{ch:03d}_beats.json").write_text(json.dumps(beats, ensure_ascii=False, indent=2))
        generate_srt(shots, srt_dir / f"ch{ch:03d}.srt")

        td = sum(s["duration"] for s in shots)
        cn = sum(1 for s in shots if any("\u4e00" <= c <= "\u9fff" for c in s.get("veo_prompt", "")))
        sc = scorer.score(shots, beats)
        for k in total_score:
            total_score[k] += sc["scores"].get(k, 0)

        results.append((ch, len(shots), round(td), cn, sc["scores"]["overall"]))
        print(f"Ch{ch:>2}: {len(shots):>2}S {td:>3.0f}s CN:{cn} Q:{sc['scores']['overall']}", flush=True)

    n = len(results)
    print(f"\n{'='*60}")
    print(f"{n}/20 done | {sum(r[1] for r in results)} shots | {sum(r[3] for r in results)} CN")
    if n > 0:
        for k in total_score:
            total_score[k] = round(total_score[k] / n)
        print(f"Quality: {total_score}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_dir")
    run_pipeline(Path(p.parse_args().project_dir))
