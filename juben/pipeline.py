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
    # 主配置兼容两处位置：项目根（旧约定）或 config/ 子目录（juben init 的实际输出）
    main_path = project_dir / "project_config.yaml"
    if not main_path.exists():
        alt_path = project_dir / "config" / "project_config.yaml"
        if alt_path.exists():
            main_path = alt_path
        else:
            raise FileNotFoundError(
                f"Config not found: {main_path} (also tried {alt_path})"
            )
    with open(main_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 加载子配置：先按主配置声明的相对路径，再回退 config/ 子目录
    config_dir = project_dir
    config_sub = project_dir / "config"
    paths = cfg.get("config_paths", {})
    if not paths and config_sub.exists():
        # 主配置在 config/ 下时，默认加载同目录子配置
        for sub in ("characters", "locations", "events", "action_rules",
                    "beat_triggers", "hook_templates", "prompt_style"):
            sub_path = config_sub / f"{sub}.yaml"
            if sub_path.exists():
                with open(sub_path, encoding="utf-8") as f:
                    cfg[sub.replace("-", "_")] = yaml.safe_load(f)
    for key, rel_path in paths.items():
        full_path = config_dir / rel_path
        if not full_path.exists() and config_sub.exists():
            alt = config_sub / Path(rel_path).name
            if alt.exists():
                full_path = alt
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
                # v1.2: recipe可显式指定景别/运镜（如打脸事件强制ECU+crash_zoom），
                # ShotCompiler会服从（此前这两个字段被静默忽略）
                "event_shot_type": recipe.get("shot_type", ""),
                "event_camera": recipe.get("camera", ""),
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
                shot["hook_applied"] = tpl["id"]  # 标记已挂钩子，断崖合成器不再重复替换
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
# 断崖合成器（每集最后1-2个shot强制悬念构图）
# ============================================================

# 内置断崖构图模板（门半开/转身回眸/话说到一半/手悬停/黑影现身）
CLIFFHANGER_DEFAULT_TEMPLATES = [
    {"id": "door_half_open",
     "text": "{char} pushes the door — it swings half-open, the room beyond pitch dark, and every sound inside stops the instant the gap widens"},
    {"id": "turn_look_back",
     "text": "{char} turns to leave, then looks back over the shoulder, eyes locking on something off-frame, lips pressed tight"},
    {"id": "line_cut_half",
     "text": "{char} leans closer, lips parting to speak — the words never land before the frame locks on the widening eyes"},
    {"id": "hand_freezes",
     "text": "{char} reaches for the door handle and freezes, fingertips trembling an inch from the metal"},
    {"id": "silhouette_step_in",
     "text": "a tall silhouette steps silently into the doorway behind {char}, close enough to touch, unseen"},
]

# 视为"弱收尾"的动作短语（命中才允许被断崖模板替换，不丢剧情内容）
CLIFFHANGER_WEAK_ENDINGS = [
    "stands still", "breathing slowly", "gaze lowered", "eyes unfocused",
    "stands behind", "looks down", "stares at", "gazes at", "speaks softly",
    "sets the cup down", "turns on the faucet", "walks through the door",
    "stands up", "sits down", "walks out", "turns and leaves", "nods slowly",
    "shakes head", "looks up", "turns around", "wipes", "clears cups",
    "dries hands", "folds the cleaning rag", "places down", "puts away",
]


def apply_cliffhanger(shots: list[dict], cliff_cfg: Any = None):
    """把每集最后1-2个shot强制成悬念构图（对齐Stage1的cliffhanger设计）。

    规则：
    - 最后1-2个shot打 cliffhanger 标记（渲染层会追加断崖悬念短语）
    - WS/MS 降为 CU（断崖不用远景）
    - 最后一个 shot 运镜强制 push（缓推逼近）
    - 只有"弱收尾"动作（黑名单/中性动作）才替换成断崖模板，剧情动作不丢
    """
    cfg = cliff_cfg if isinstance(cliff_cfg, dict) else {}
    if cfg.get("enabled") is False or not shots:
        return
    n = max(1, int(cfg.get("last_shots", 2)))
    templates = cfg.get("templates") or CLIFFHANGER_DEFAULT_TEMPLATES
    weak_markers = cfg.get("weak_endings") or CLIFFHANGER_WEAK_ENDINGS
    force_cam = cfg.get("force_camera", "push")

    targets = shots[-n:]
    for k, shot in enumerate(reversed(targets)):  # k=0 是最后一个
        shot["cliffhanger"] = True
        if shot.get("shot_type") in ("WS", "MS"):
            shot["shot_type"] = "CU"
        if k == 0:
            shot["camera_movement"] = force_cam if force_cam else shot.get("camera_movement", "push")
        # 弱动作才替换为断崖构图（hook模板已是悬念动作，跳过）
        act = (shot.get("action_visual") or "").lower()
        weak = (not act) or any(m in act for m in weak_markers)
        if weak and not shot.get("hook_applied"):
            tpl = templates[shot.get("shot_id", 0) % len(templates)] \
                if isinstance(templates, list) and templates else None
            if tpl:
                char = shot.get("characters", ["Character"])[0] if shot.get("characters") else "Character"
                shot["action_visual"] = tpl.get("text", "").replace("{char}", char)
                shot["cliffhanger_template"] = tpl.get("id", "")


# ============================================================
# 节拍定位（pacing-aware 分镜，爆款对齐）
# 9 点卡点表不只用于校验——每个 shot 必须知道自己服务于哪个节拍，
# 运镜/景别/情绪按节拍执行，否则中段就是均匀分布的"信息真空"。
# ============================================================

PACING_MARKS = [
    (3, "3s_Hook"), (15, "15s_Conflict"), (30, "30s_Retention"),
    (45, "45s_Escalation"), (60, "60s_Explosion"), (75, "75s_Satisfaction"),
    (82, "82s_Twist"), (90, "90s_Cliffhanger"),
]

# 节拍 → 运镜/景别/渲染语言（爆点给 crash zoom，蓄力给缓推，爽点给拉回反应镜头）
PACING_GRAMMAR = {
    "3s_Hook": {"shot_type": "CU", "camera": "push",
                "style": "strong sensory impact in the first frame, hook established immediately"},
    "15s_Conflict": {"shot_type": "CU", "camera": "push",
                     "style": "positions clash, stakes rising, rapid exchange"},
    "30s_Retention": {"shot_type": "MCU", "camera": "push",
                      "style": "a secret surfaces in the framing, tension building"},
    "45s_Escalation": {"shot_type": "CU", "camera": "static",
                       "style": "the humiliator pushes one notch higher, pressure at breaking point"},
    "60s_Explosion": {"shot_type": "MCU", "camera": "crash_zoom",
                      "style": "the blow lands — high-energy turn, physical or public reversal"},
    "75s_Satisfaction": {"shot_type": "MCU", "camera": "pull",
                         "style": "reaction beat: onlookers gasp, the aggressor's face collapses"},
    "82s_Twist": {"shot_type": "CU", "camera": "push",
                  "style": "a new variable enters the frame, the win sours into a bigger threat"},
    "90s_Cliffhanger": {"shot_type": "CU", "camera": "push",
                        "style": "suspense cliffhanger framing, cut before the answer is revealed"},
}


def apply_pacing(shots: list[dict]) -> None:
    """按累计时长给每个 shot 打 pacing_label，并套用节拍运镜/景别语法。
    幂等：重复调用不叠加。"""
    if not shots:
        return
    t = 0.0
    for shot in shots:
        dur = float(shot.get("duration") or 0)
        mid = t + dur / 2.0
        label = PACING_MARKS[0][1]
        for mark, name in PACING_MARKS:
            if mid >= mark:
                label = name
        shot["pacing_label"] = label
        t += dur

    for shot in shots:
        label = shot.get("pacing_label")
        rule = PACING_GRAMMAR.get(label)
        if not rule:
            continue
        # 景别：只在原判定过宽时收紧（WS/MS → CU/MCU），不放宽已有 ECU/CU
        want_st = rule["shot_type"]
        if shot.get("shot_type") in ("WS", "MS", "") or not shot.get("shot_type"):
            shot["shot_type"] = want_st
        elif label == "60s_Explosion" and shot.get("shot_type") in ("WS", "FS"):
            shot["shot_type"] = "MCU"
        # 运镜：爆点强制 crash_zoom；其他节拍只在原运镜是 static 时升级
        if label == "60s_Explosion":
            shot["camera_movement"] = rule["camera"]
        elif shot.get("camera_movement") in ("static", ""):
            shot["camera_movement"] = rule["camera"]
        # 情绪兜底：关键词匹配不到时的节拍级覆盖（爆点不能是暖光，断崖不能是平铺）
        emotion_override = {"60s_Explosion": "Shock", "90s_Cliffhanger": "Tension",
                            "3s_Hook": "Tension", "45s_Escalation": "Tension"}
        want = emotion_override.get(label)
        if want and shot.get("emotion", "Neutral") in ("Neutral", "Warmth"):
            shot["emotion"] = want
        shot["pacing_style"] = rule["style"]


# ============================================================
# BeatExtractor
# ============================================================

class BeatExtractor:
    """通用Beat提取器"""

    @staticmethod
    def _normalize_chars(raw: Any) -> dict:
        """角色表归一化，兼容三种来源：
        1) config/characters.yaml（juben init 生成，{'characters': [list]}，条目无 en 字段）
        2) characters.json（bootstrap 产出，{'characters': {name: {en, pronouns, role}}})
        3) 直接的 {name: info} 字典
        统一成 {中文名: {en, pronouns, role}}；缺 en 时回退用名字本身。
        """
        items: Any = raw
        if isinstance(raw, dict) and "characters" in raw:
            items = raw["characters"]
        out: dict = {}
        if isinstance(items, list):
            for info in items:
                if not isinstance(info, dict):
                    continue
                name = str(info.get("name") or "").strip()
                if not name:
                    continue
                out[name] = {
                    "en": str(info.get("en") or name),
                    "pronouns": info.get("pronouns", []) or [],
                    "role": info.get("role") or info.get("archetype") or "",
                }
        elif isinstance(items, dict):
            for name, info in items.items():
                if isinstance(info, str):
                    out[str(name)] = {"en": info, "pronouns": [], "role": ""}
                elif isinstance(info, dict):
                    out[str(name)] = {
                        "en": str(info.get("en") or name),
                        "pronouns": info.get("pronouns", []) or [],
                        "role": info.get("role") or "",
                    }
        return out

    def __init__(self, config: dict):
        self.cfg = config
        self.chars = self._normalize_chars(config.get("characters", {}))
        self.events = config.get("events", {})
        self.event_engine = EventEngine(self.events.get("events", []) if isinstance(self.events, dict) else [])
        self.triggers = config.get("beat_triggers", {})
        self._last_dlg_speaker = ""  # 跨 beat 的说话人连读追踪（省略主语的开场白沿用）
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
        # 爆款对齐兜底词库：模板词表覆盖不到的短剧高频动作（掀桌/攥拳/切石/下跪…）
        DRAMA_ACTION_MAP = {
            "掀翻椅子": "flips the chair over", "攥碎": "crushes it in his fist",
            "攥紧": "clenches his fist hard", "掰开手指": "pries the fingers open",
            "下跪": "drops to his knees", "跪下": "drops to his knees",
            "画线": "marks a cutting line on the stone with chalk",
            "落刀": "drives the cutting blade down", "切石": "feeds the stone into the saw",
            "摘下": "takes off", "捡起": "picks up", "转身": "turns around sharply",
            "后退": "stumbles backward", "掀开": "pulls the cover off",
            "举起": "holds it up high", "砸": "slams it down", "摔": "slams it down",
            "推门": "pushes the door open", "夺门而出": "bolts out the door",
            "卷起袖子": "rolls up the sleeve", "拍案": "slams the table",
        }
        for zh_act, en_act in DRAMA_ACTION_MAP.items():
            if zh_act in text:
                return self._apply_rewrite(f"{char} {en_act}", char)
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
                # 说话人只在台词行本身里找（"林晚冷笑："）——扫整段会把同 beat
                # 后文提到的角色误判为说话人（群众台词被标成主角）
                for name, info in self.chars.items():
                    if name in raw:
                        dlg_speaker = info["en"]
                        break
                if not dlg_speaker:
                    # 无归属台词：省略主语开头（……/——）视为上一说话人连读，
                    # 否则按群众杂音处理（TTS 用群杂音色，配音才不会张冠李戴）
                    if self._last_dlg_speaker and raw.startswith(("……", "——", "—")):
                        dlg_speaker = self._last_dlg_speaker
                    else:
                        dlg_speaker = "Crowd"
                self._last_dlg_speaker = dlg_speaker

        if voice_text:
            vt = "inner_voice"
        elif dlg_text:
            vt = "onscreen"

        # 爆款对齐：beat 级场景检测（公盘/仓库/当铺…），场景氛围才能进提示词
        loc_map_cfg = self.cfg.get("locations") or {}
        if isinstance(loc_map_cfg, dict) and set(loc_map_cfg.keys()) == {"locations"}:
            loc_map_cfg = loc_map_cfg["locations"]
        beat_loc = ""
        if isinstance(loc_map_cfg, dict):
            for zh_key, en_loc in loc_map_cfg.items():
                if isinstance(en_loc, str) and zh_key in text:
                    beat_loc = en_loc
                    break
        return {
            "beat_id": beat_id,
            "location": beat_loc,
            "space": self._detect_space(text),
            "characters_present": chars,
            "primary_char": primary,
            "action_visual": action,
            "spoken_dialogue": dlg_text,
            "dialogue_speaker": dlg_speaker,
            "inner_voice": voice_text,
            "voice_type": vt,
            # v1.2 台词密集支持：本beat全部口播台词（多行）+ 字数，
            # 供时长推算（中文4-5字/秒）与长台词拆镜使用。
            # 仅在纯口播beat填充（有心声时沿用旧行为：心声优先，口播丢弃）
            "dialogue_all": "\n".join(dialogues) if dlg_text else "",
            "dialogue_chars": sum(len(d) for d in dialogues) if dlg_text else 0,
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

    # 冲突/打脸/揭露类事件（强制怼脸近景）
    CONFLICT_EVENTS = {"face_slap", "identity_reveal", "kneel_beg", "confrontation"}
    # 反转瞬间（强制快切运镜 crash zoom）
    REVERSAL_EVENTS = {"face_slap", "identity_reveal", "rebirth_awaken"}
    # 冲突类动作短语（英文action_visual里检测）
    CONFLICT_ACTION_KEYWORDS = [
        "slap", "kneel", "grab", "slam", "shove", "smash", "accuse",
        "expose", "confront", "tear", "snatch", "goes pale", "snaps eyes open",
        "clenches fist", "kicks", "throws",
    ]
    # 景别/运镜别名归一（events.yaml recipe → 引擎枚举）
    SHOT_TYPE_ALIASES = {
        "WIDE": "WS", "EWS": "WS", "WS": "WS", "FS": "FS",
        "ECU": "ECU", "CU": "CU", "MCU": "MCU", "MS": "MS", "OTS": "CU",
    }
    CAMERA_ALIASES = {
        "slow_zoom_in": "push", "zoom_in": "push", "slow_pull_back": "pull",
        "pull_back": "pull", "static": "static", "push": "push",
        "pull": "pull", "rapid_push": "rapid_push", "handheld": "handheld",
        "whip_pan": "whip_pan", "crash_zoom": "crash_zoom", "pan": "static",
        "crash_zoom_in": "crash_zoom", "whip_pan_left": "whip_pan",
        "whip_pan_right": "whip_pan",
    }
    # 台词语速默认（中文约4-5字/秒，取4.5；爆款语料7.6字/秒为上限极值）
    SPEECH_DEFAULTS = {
        "chars_per_second": 4.5,
        "pause_seconds": 0.6,
        "min_shot_seconds": 3.0,
        "max_shot_seconds": 8.0,
        "split_long_dialogue": True,
    }

    def __init__(self, config: dict):
        self.cfg = config
        self.style = config.get("prompt_style", {})
        self.emotion_shot = self.style.get("emotion_shot_map", {})
        self.emotion_camera = self.style.get("emotion_camera_map", {})
        self.emotion_lighting = self.style.get("emotion_lighting_map", {})
        self.camera_semantic = self.style.get("camera_semantic_map", {})
        self.voice_emotion = self.style.get("voice_emotion_map", {})
        self.merge_cfg = self.style.get("beat_merge", {})
        # 台词→时长推算参数（prompt_style.speech 可覆盖）
        self.speech = {**self.SPEECH_DEFAULTS, **(self.style.get("speech") or {})}

    def compile(self, beats: list[dict], target: int | None = 90, location: str = "") -> list[dict]:
        """target=总时长目标(秒)做整体缩放；target=None 时不限制总时长，
        每镜头按剧情+台词自然长度走（适合逐镜头生成后剪成长视频）。"""
        # v1.2 台词保底：超长台词的beat先拆成多个镜头（每镜台词念得完）
        beats = self._split_long_dialogue_beats(beats)
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
            sfloor = self._speech_seconds(beat)

            # v1.2 冲突对话+双人在场 → 过肩正反打（竖屏打脸戏标配）
            framing = ""
            dlg = beat.get("spoken_dialogue", "")
            if st in ("CU", "MCU") and vt == "onscreen" and dlg \
                    and len(beat.get("characters_present", [])) >= 2:
                framing = "over-the-shoulder"

            shots.append({
                "shot_id": i + 1, "shot_type": st, "camera_movement": cam,
                "camera_angle": self._angle(emotion), "duration": dur,
                "_speech_floor": sfloor,
                "location": beat.get("location") or location,
                "space": beat.get("space", "Physical"),
                "characters": beat.get("characters_present", []),
                "action_visual": beat.get("action_visual", ""),
                "dialogue": beat.get("dialogue_all") or dlg,
                "dialogue_speaker": beat.get("dialogue_speaker", ""),
                "voice_type": vt,
                "inner_voice": beat.get("inner_voice", ""),
                "focus_object": beat.get("focus_object", ""),
                "lighting": self.emotion_lighting.get(emotion, "Natural"),
                "emotion": emotion,
                "framing": framing,
                "visual_anchors": [beat.get("focus_object", "")] if beat.get("focus_object") else [],
                "beat_id": beat.get("beat_id"),
                "event_type": beat.get("event_type", ""),
            })

        if target:
            self._adjust(shots, target)
        # 爆款对齐：节拍定位（在 _adjust 定稿时长后执行，标签按最终秒数落位）
        apply_pacing(shots)
        # 剧本过薄预警：beat 太少时即使每镜顶到 8s 上限也凑不满单集时长，
        # 说明 Scribe 正文注水不足量（台词/事件密度不够），回写窗口加戏
        if target:
            total_dur = sum(float(s.get("duration") or 0) for s in shots)
            if total_dur < target * 0.6:
                print(f"⚠ 剧本过薄：全部镜头仅 {total_dur:.0f}s（目标 {target}s）。"
                      f"需要更多冲突回合/台词/事件，回到 Scribe 加密叙事，不要拉长镜头硬凑。",
                      flush=True)
        return shots

    # --- 台词→时长推算（中文4-5字/秒） ---

    def _speech_seconds(self, beat: dict) -> float:
        """该镜头台词念完所需秒数。中文按字数/语速，英文台词(兼容出海)按词数/3。"""
        vt = beat.get("voice_type", "none")
        cps = float(self.speech.get("chars_per_second", 4.5))
        pause = float(self.speech.get("pause_seconds", 0.6))
        cn_chars = 0
        if vt == "inner_voice":
            cn_chars = len(beat.get("inner_voice", "") or "")
        else:
            # onscreen或未标voice_type：数全部口播台词
            cn_chars = int(beat.get("dialogue_chars", 0)) or len(beat.get("dialogue_all", "") or "") \
                or len(beat.get("spoken_dialogue", "") or "")
        secs = cn_chars / cps if cn_chars else 0.0
        # 英文台词兼容（line_en由上层项目注入时生效）
        line_en = beat.get("inner_voice_en", "") if vt == "inner_voice" else beat.get("line_en", "")
        if line_en:
            secs = max(secs, len(line_en.split()) / 3.0)
        return round(secs + (pause if secs else 0.0), 2)

    def _split_long_dialogue_beats(self, beats: list[dict]) -> list[dict]:
        """台词超过单镜可念上限的beat拆成多个镜头（每镜保留原画面，台词分段）。"""
        if not self.speech.get("split_long_dialogue", True):
            return beats
        max_s = float(self.speech.get("max_shot_seconds", 8.0))
        pause = float(self.speech.get("pause_seconds", 0.6))
        cps = float(self.speech.get("chars_per_second", 4.5))
        max_chars = max(10, int((max_s - pause) * cps))
        out = []
        for b in beats:
            dlg = b.get("dialogue_all") or b.get("spoken_dialogue", "") or ""
            if b.get("voice_type", "none") == "onscreen" and len(dlg) > max_chars:
                chunks = self._split_cn_text(dlg, max_chars)
                for i, ch in enumerate(chunks):
                    nb = dict(b)
                    nb["spoken_dialogue"] = ch
                    nb["dialogue_all"] = ch
                    nb["dialogue_chars"] = len(ch)
                    if i > 0:
                        # 后续段：保持说话状态，填充动作轮换（同一动作连用N镜=画面复读）
                        who = b.get("primary_char", "Character")
                        fillers = [
                            f"{who} keeps speaking, leaning forward, jaw tight with conviction",
                            f"{who} keeps speaking, one hand slicing the air for emphasis",
                            f"{who} keeps speaking, stepping closer, voice harder",
                            f"{who} keeps speaking, eyes locked on the listener, breath quickening",
                            f"{who} keeps speaking, palms open in a defiant shrug",
                        ]
                        nb["action_visual"] = fillers[i % len(fillers)]
                    out.append(nb)
            else:
                out.append(b)
        return out

    @staticmethod
    def _split_cn_text(text: str, max_chars: int) -> list[str]:
        """按中文句末标点切分并贪心打包成≤max_chars的段落。"""
        parts = [p for p in re.split(r'(?<=[。！？!?…；;])', text) if p.strip()]
        if len(parts) <= 1:
            # 无标点：硬切
            return [text[i:i + max_chars] for i in range(0, len(text), max_chars)] or [text]
        chunks, buf = [], ""
        for p in parts:
            if buf and len(buf) + len(p) > max_chars:
                chunks.append(buf)
                buf = p
            else:
                buf += p
        if buf:
            chunks.append(buf)
        return chunks

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

    def _normalize_shot_type(self, val) -> str:
        """events recipe景别归一（'Wide'→'WS'等），非法值返回''"""
        if not val:
            return ""
        return self.SHOT_TYPE_ALIASES.get(str(val).strip().upper(), "")

    def _normalize_camera(self, val) -> str:
        if not val:
            return ""
        return self.CAMERA_ALIASES.get(str(val).strip().lower(), "")

    def _is_conflict(self, beat: dict) -> bool:
        """冲突/打脸/揭露类beat：强制怼脸近景"""
        if beat.get("event_type") in self.CONFLICT_EVENTS:
            return True
        if beat.get("emotion") == "Shock":
            return True
        act = (beat.get("action_visual") or "").lower()
        return any(kw in act for kw in self.CONFLICT_ACTION_KEYWORDS)

    def _is_reversal(self, beat: dict) -> bool:
        """反转瞬间：接crash zoom等快切语言"""
        if beat.get("event_type") in self.REVERSAL_EVENTS:
            return True
        act = (beat.get("action_visual") or "").lower()
        return beat.get("emotion") == "Shock" and any(
            kw in act for kw in ("slap", "kneel", "expose", "reveal", "goes pale", "snaps eyes open"))

    def _choose_shot_type(self, beat, idx, last, ecu):
        # 动作文本显式指定景别 → 服从剧本（冷开场特写钩子等，优先级最高）
        # 出海英文配音模式下口型由Veo跟台词生成，说话镜头也可怼脸(ECU)秀口型对齐
        explicit = self._explicit_shot(beat)
        if explicit:
            return explicit
        # events recipe 显式指定景别 → 服从（打脸/读心/闪回等事件镜头语言）
        ev = self._normalize_shot_type(beat.get("event_shot_type"))
        if ev:
            return ev
        # 转场beat才用WS（远景只用于转场/定场）
        if beat.get("space") == "Transition":
            return "WS"
        if idx == 0:
            return "WS"
        # 冲突/打脸/揭露 → 怼脸CU（Shock升ECU），对话对手戏走正反打
        if self._is_conflict(beat):
            return "ECU" if beat.get("emotion") == "Shock" else "CU"
        if beat.get("space") == "Mental":
            return "CU"
        # onscreen 对话：按情绪给景别，竖屏下限MCU（近景怼脸利于口型+字幕构图）
        if beat.get("spoken_dialogue") and beat.get("voice_type") == "onscreen":
            if beat.get("emotion") in ("Shock", "Tension"):
                return "CU"
            pref = self.emotion_shot.get(beat.get("emotion", "Neutral"), "MCU")
            if pref in ("WS", "MS"):
                pref = "MCU"  # 对话镜头禁用远景/中景
            if pref == last:
                pref = {"ECU": "CU", "CU": "MCU", "MCU": "MS", "MS": "MCU"}.get(pref, "MCU")
            return pref
        focus = beat.get("focus_object", "")
        if focus:
            return "CU" if (last == "ECU" or ecu >= 2) else "ECU"
        if beat.get("spoken_dialogue"):
            return "MS" if last == "MCU" else "MCU"
        pref = self.emotion_shot.get(beat.get("emotion", "Neutral"), "MS")
        if pref == "WS":
            pref = "MS"  # 非转场内容不用远景
        if pref == last:
            pref = {"CU": "MCU", "MCU": "MS", "MS": "MCU"}.get(pref, "MCU")
        return pref

    def _choose_camera(self, beat, st, last):
        # events recipe 显式指定运镜 → 服从
        ev_cam = self._normalize_camera(beat.get("event_camera"))
        if ev_cam:
            return ev_cam
        # 反转瞬间 → crash zoom（快切语言，references/camera-language.md）
        if self._is_reversal(beat):
            return "crash_zoom"
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

    def _calc_duration(self, beat, total, target):
        # target=None：不限总时长，每镜给自然基准5s，再按台词/内容微调
        base = (target / max(1, total)) if target else 5.0
        wc = len(beat.get("action_visual", "")) + len(beat.get("spoken_dialogue", ""))
        if wc > 100: base *= 1.2
        elif wc < 30: base *= 0.7
        if beat.get("space") == "Mental" or beat.get("focus_object"):
            base *= 1.1
        max_s = float(self.speech.get("max_shot_seconds", 8.0))
        min_s = float(self.speech.get("min_shot_seconds", 3.0))
        # 台词保底（v1.2）：时长必须够把台词念完。
        # 中文按字数/4.5字每秒，英文按3词/秒（line_en兼容出海），否则配音/字幕被截断。
        speech_floor = self._speech_seconds(beat)
        dur = max(min_s, min(max_s, base))
        return round(max(dur, speech_floor), 1)

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

    def _adjust(self, shots, target):
        if not shots: return
        # 台词镜头的念白保底时长(speech_floor)不可被缩放击穿，否则配音截断
        def floor(s):
            return s.get("_speech_floor", 3.0)
        max_s = float(self.speech.get("max_shot_seconds", 8.0))
        cur = sum(s["duration"] for s in shots)
        if cur <= 0: return
        r = target / cur
        for s in shots:
            s["duration"] = round(max(floor(s), min(max_s, s["duration"] * r)), 1)
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
              "rapid_push": "rapid push-in", "handheld": "handheld camera",
              "whip_pan": "whip pan", "crash_zoom": "crash zoom in", "dolly_zoom": "dolly zoom"}
    ANG_EN = {"eye-level": "eye level", "low": "low angle looking up", "high": "high angle looking down"}
    LIGHT_EN = {"Natural": "natural daylight, soft shadows", "Warm": "warm golden light",
                "Low key": "low key lighting, deep shadows", "High contrast": "high contrast dramatic lighting"}
    MOOD_EN = {"Neutral": "neutral, observational", "Tension": "tense, suspenseful",
               "Shock": "shocked, dramatic", "Sadness": "sad, melancholic",
               "Warmth": "warm, heartwarming", "Mystery": "mysterious, intriguing"}

    # 统一负向提示词（Veo3常见失误：畸形手/换脸/水印/随机加对白）
    DEFAULT_NEGATIVE = ("deformed hands, extra fingers, distorted face, face swap, "
                        "identity drift, outfit change, watermark, subtitles burned in, text overlay, logo, "
                        "camera shake, glitch, blurry, low resolution, extra people, duplicate characters")
    # 竖屏安全区：脸在上2/3，底部留字幕，顶部留标题
    SAFE_AREA_EN = ("vertical 9:16 composition, subject placed in the upper two-thirds of the frame, "
                    "keep the bottom 15% of the frame clear for subtitles, "
                    "leave a slim top margin clear for the episode title")
    CLIFFHANGER_EN = "suspense cliffhanger framing, cut before the answer is revealed"
    OTS_EN = "over-the-shoulder shot-reverse-shot framing"

    def __init__(self, config: dict):
        self.chars = BeatExtractor._normalize_chars(config.get("characters", {}))
        style = config.get("prompt_style", {})
        active = style.get("active_renderer", "flow_v1")
        renderers = style.get("renderers", {})
        self.renderer_cfg = renderers.get(active, {})
        self.renderer_style = self.renderer_cfg.get("style", "hybrid")
        self.suffix = self.renderer_cfg.get("suffix", "cinematic, 9:16 vertical, photorealistic, 4K")
        self.char_first = self.renderer_cfg.get("character_first", True)
        # character_mode: "reference"=只引用角色名(配合Flow角色系统) | "inline"=每镜头塞长相描述
        self.char_mode = self.renderer_cfg.get("character_mode", "inline")
        # reference模式下的一致性锁（Flow角色系统之外的每镜头保险）
        self.consistency_lock = self.renderer_cfg.get(
            "consistency_lock", "identical face and same outfit as the character reference, no outfit change")
        # 负向提示词（可配置；输出到 shot["negative_prompt"]，导出层单独成行）
        self.negative_prompt = str(style.get("negative_prompt") or self.DEFAULT_NEGATIVE)
        # 竖屏安全区提示（每镜头注入）
        self.safe_area = style.get("safe_area", True)
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
        # 过肩正反打（冲突对手戏）
        if shot.get("framing") == "over-the-shoulder":
            parts.append(self.OTS_EN)
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
        # 竖屏安全区（字幕/标题留白）+ 断崖悬念构图
        if self.safe_area:
            parts.append(self.SAFE_AREA_EN)
        # 节拍渲染语言：爆点/蓄力/爽点各有专属镜头语言（pacing-aware）
        pacing_style = shot.get("pacing_style")
        if pacing_style:
            parts.append(pacing_style)
        if shot.get("cliffhanger"):
            parts.append(self.CLIFFHANGER_EN)
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
        # v1.2 中文台词兜底：line_en缺失（默认中文链路）时用中文原句+中文口型指令，
        # 修复"有台词镜头被渲染成 lips closed"的口型事故
        line_zh = shot.get("dialogue", "") if vt == "onscreen" else shot.get("inner_voice", "")
        mouth, audio = "", ""
        if vt == "onscreen" and (line_en or line_zh) and spk_en:
            if len(chars) > 1:
                others = [c for c in chars if c != spk_en]
                if line_en:
                    mouth = cfg.get("onscreen_multi_tpl", "").format(
                        speaker=spk_en, line_en=line_en, tone=tone, accent=accent,
                        others=", ".join(others))
                else:
                    mouth = cfg.get(
                        "onscreen_multi_tpl_zh",
                        '{speaker} speaks in Chinese, saying: "{line_zh}", {tone} delivery, '
                        'natural lip sync in Chinese, subtitle-friendly framing; '
                        '{others} stay silent with closed lips, listening').format(
                        speaker=spk_en, line_zh=line_zh, tone=tone, accent=accent,
                        others=", ".join(others))
            elif line_en:
                mouth = cfg.get("onscreen_tpl", "").format(
                    speaker=spk_en, line_en=line_en, tone=tone, accent=accent)
            else:
                mouth = cfg.get(
                    "onscreen_tpl_zh",
                    '{speaker} speaks in Chinese, saying: "{line_zh}", {tone} delivery, '
                    'natural lip sync in Chinese, subtitle-friendly framing with the face '
                    'in the upper frame, {accent}').format(
                    speaker=spk_en, line_zh=line_zh, tone=tone, accent=accent)
            audio = cfg.get("dialogue_audio", "")
        elif vt == "onscreen" and line_zh and not spk_en:
            # 群杂台词（说话人无法归属，如围观起哄）：渲染为背景人声而非主角口型，
            # 否则这些镜头会被错误渲染成"无人说话"
            mouth = ('a crowd of background voices speaking in Chinese, saying: "{line_zh}", '
                     'overlapping chatter, no single identifiable speaker, subtitle-friendly framing').format(
                line_zh=line_zh)
            audio = cfg.get("dialogue_audio", "")
        elif vt == "inner_voice" and (line_en or line_zh):
            spk = spk_en or (chars[0] if chars else "the character")
            if line_en:
                mouth = cfg.get("inner_voice_tpl", "").format(
                    speaker=spk, line_en=line_en, tone=tone, accent=accent)
            else:
                mouth = cfg.get(
                    "inner_voice_tpl_zh",
                    '{speaker} stays silent with lips closed, a {tone} intimate interior '
                    'monologue voiceover in Chinese as if heard inside the head: "{line_zh}", '
                    'same voice as {speaker} but internalized, {accent}').format(
                    speaker=spk, line_zh=line_zh, tone=tone, accent=accent)
            iva = cfg.get("inner_voice_audio", "")
            audio = f"{ambient}, {iva}" if ambient else iva
        else:
            if chars:
                # 无声镜头：明确 no dialogue（Veo3常见失误是随机加对白）
                mouth = cfg.get("none_mouth", "lips closed, no speaking, no dialogue")
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
        if self.safe_area: parts.append("9:16 vertical, bottom 15% clear for subtitles")
        if shot.get("cliffhanger"): parts.append(self.CLIFFHANGER_EN)
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
        if self.safe_area: parts.append("9:16 vertical, subject in upper two-thirds, bottom clear for subtitles")
        if shot.get("cliffhanger"): parts.append(self.CLIFFHANGER_EN)
        parts.append(self.suffix)
        return ", ".join(parts)

    def _char_phrase(self, ce):
        # v1.2 角色一致性：每镜头都带外观锚点（发型/服装/年龄短语），避免换装穿帮。
        # reference模式 = Flow角色系统管长相，附加一致性锁短语做双保险；
        # inline模式 = 首次全量锚点，后续短锚点。
        tag = self._tag(ce)
        return f"{ce} ({tag})" if tag else ce

    def _tag(self, ce):
        info = None
        for inf in self.chars.values():
            if isinstance(inf, dict) and inf.get("en") == ce:
                info = inf
                break
        if info is None:
            return ce if self.char_mode == "inline" else ""
        if self.char_mode == "reference":
            # Flow 角色系统保证长相；仍注入轻量一致性锁（服装锚点）防换装
            anchor = info.get("prompt_anchor_short") or info.get("prompt_anchor", "")
            return self.consistency_lock if not anchor else f"{anchor}, {self.consistency_lock}"
        # inline模式：full/short字段优先（旧项目），否则用 characters.yaml 的英文锚点
        full = info.get("full") or info.get("prompt_anchor") or ce
        short = info.get("short") or info.get("prompt_anchor_short") or full
        return full if self._count.get(ce, 0) <= 1 else short


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

        # === 爆款对齐：真实判别性检查（此前评分器恒 100 分，是摆设） ===
        # 6. pacing_coverage: 9 点节拍覆盖率（钩子/蓄力/爆点/爽点/断崖缺一不可）
        labels = {s.get("pacing_label") for s in shots}
        required = {"3s_Hook", "45s_Escalation", "60s_Explosion", "75s_Satisfaction", "90s_Cliffhanger"}
        covered = sum(1 for r in required if r in labels)
        scores["pacing_coverage"] = round(covered / len(required) * 100)

        # 7. speech_floor_respect: 台词镜头时长 >= 念完台词所需（配音不被截断）
        dlg_shots = [s for s in shots if (s.get("audio", {}).get("dialogue_zh")
                                          or s.get("audio", {}).get("voiceover_zh"))]
        if dlg_shots:
            ok = sum(1 for s in dlg_shots
                     if float(s.get("duration") or 0) >= float(s.get("_speech_floor") or 0) - 0.05)
            scores["speech_floor_respect"] = round(ok / len(dlg_shots) * 100)
        else:
            scores["speech_floor_respect"] = 100

        # 8. cliffhanger_present: 末镜必须断崖
        scores["cliffhanger_present"] = 100 if shots and shots[-1].get("cliffhanger") else 0

        # 9. emotion_variety: 情绪至少 3 种（全程 Neutral = 情绪平线，必划走）
        distinct_emotions = {s.get("emotion", "Neutral") for s in shots}
        scores["emotion_variety"] = round(min(1, len(distinct_emotions) / 3) * 100)

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
            txt = a["dialogue_zh"].strip()
        if txt:
            lines.append(f"{seq}\n{_fmt(t)} --> {_fmt(t+dur)}\n{txt}\n")
            seq += 1
        t += dur
    path.write_text("\n".join(lines), encoding="utf-8")

def _fmt(s):
    return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d},{int(s%1*1000):03d}"


def generate_voice_data(chapter: int, shots: list, path):
    """导出 TTS 配音数据（voice_data.json）：每镜台词/心声、说话人、情感、时长。
    扁平追加式（全剧一个文件），供外部 TTS/合成工具直接消费。"""
    voice_path = Path(path)
    data = []
    if voice_path.exists():
        try:
            data = json.loads(voice_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
    t = 0.0
    for shot in shots:
        a = shot.get("audio", {})
        vt = a.get("voice_type", "none")
        text = (a.get("voiceover_zh") if vt == "inner_voice" else a.get("dialogue_zh", "") or "").strip()
        if not text:
            t += shot.get("duration", 5.0)
            continue
        data.append({
            "chapter": chapter,
            "shot_id": shot.get("shot_id"),
            "start_sec": round(t, 1),
            "duration": shot.get("duration", 5.0),
            "voice_type": vt,
            "speaker": a.get("dialogue_speaker", "") if vt != "inner_voice" else "旁白(心声)",
            "emotion": a.get("emotion_tag", "calm"),
            "text": text,
            "pacing_label": shot.get("pacing_label", ""),
        })
        t += shot.get("duration", 5.0)
    voice_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    if isinstance(loc_map, dict) and set(loc_map.keys()) == {"locations"}:
        loc_map = loc_map["locations"]
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
    total_score = {"action_completeness": 0, "focus_rendered": 0, "shot_variety": 0, "audio_separation": 0,
                   "character_coverage": 0, "pacing_coverage": 0, "speech_floor_respect": 0,
                   "cliffhanger_present": 0, "emotion_variety": 0}

    # 跳过已 lock 的章节 (存在 .md.locked 表示内容已定稿, 不应重复转分镜)
    for ch in range(1, max_chapter + 1):
        if only_chapter and ch != only_chapter:
            continue
        # 章节文件名兼容两种约定：官方 001.md 与技能文档 ch001.md
        ch_path = project_dir / "chapters" / f"{ch:03d}.md"
        if not ch_path.exists():
            alt = project_dir / "chapters" / f"ch{ch:03d}.md"
            if alt.exists():
                ch_path = alt
        lock_path = ch_path.with_suffix(".md.locked")
        if not ch_path.exists(): continue
        if lock_path.exists(): continue  # 已 lock, 跳过

        text = ch_path.read_text(encoding="utf-8")
        beats = extractor.extract(text)
        if not beats:
            print(f"⚠ Ch{ch}: 分镜提取到 0 个 beat（剧本是否为空/格式不符？），跳过", flush=True)
            continue

        loc = default_loc
        if isinstance(loc_map, dict):
            for zh, en in loc_map.items():
                if zh in text: loc = en; break

        shots = compiler.compile(beats, 90, loc)
        # v1.2 修复：钩子/断崖必须在渲染前应用，否则替换后的动作进不了veo_prompt
        hook.apply(shots)
        apply_cliffhanger(shots, cfg.get("hook_templates", {}).get("cliffhanger", {})
                          if isinstance(cfg.get("hook_templates", {}), dict) else {})
        beats_by_id = {b.get("beat_id"): b for b in beats}
        renderer.reset()
        for shot in shots:
            norm_chars = BeatExtractor._normalize_chars(cfg.get("characters", {}))
            shot["characters"] = [norm_chars.get(c, {}).get("en", c) for c in shot.get("characters", [])]
            shot["veo_prompt"] = renderer.render(shot, loc)
            # 统一负向提示词（Veo3畸形手/换脸/水印/随机对白防护，可配置）
            shot["negative_prompt"] = renderer.negative_prompt
            # v1.2 修复：音频来源改用 beat_id 映射+镜头自带字段，
            # 此前用 beats[shot_id-1]，镜头合并/拆分后台词错位
            bd = beats_by_id.get(shot.get("beat_id"), {}) or {}
            shot["audio"] = {
                "dialogue_zh": shot.get("dialogue") or bd.get("spoken_dialogue", ""),
                "dialogue_speaker": shot.get("dialogue_speaker") or bd.get("dialogue_speaker", ""),
                "voiceover_zh": shot.get("inner_voice") or bd.get("inner_voice", ""),
                "voice_type": shot.get("voice_type") or bd.get("voice_type", "none"),
                "subtitle": (shot.get("inner_voice") or bd.get("inner_voice", "") or "")[:30],
                "emotion_tag": compiler.voice_emotion.get(shot.get("emotion", "Neutral"), "calm"),
                "duration_hint": f"{shot['duration']:.1f}s",
            }

        (out / f"ch{ch:03d}_shots.json").write_text(json.dumps(shots, ensure_ascii=False, indent=2))
        (out / f"ch{ch:03d}_beats.json").write_text(json.dumps(beats, ensure_ascii=False, indent=2))
        generate_srt(shots, srt_dir / f"ch{ch:03d}.srt")
        generate_voice_data(ch, shots, project_dir / "voice_data.json")

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
