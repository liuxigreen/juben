"""
Flow Professional Prompt Generator v1.0

基于：
- Google Veo 3.1 5-part prompt formula
- facial-expression-prompting 人物表演框架
- 我们的分镜数据（shots.json）

输出：可直接粘贴到Google Flow的工业级提示词
"""
import json
from pathlib import Path

# ===== 5-Part Formula 组件 =====

# 1. Cinematography（镜头语言）
SHOT_SPEC = {
    "WS": {"name": "wide shot", "desc": "establishing environment, spatial context"},
    "MS": {"name": "medium shot", "desc": "waist-up, natural conversation distance"},
    "MCU": {"name": "medium close-up", "desc": "chest-up, emotional engagement"},
    "CU": {"name": "close-up", "desc": "face and shoulders, intimate emotional detail"},
    "ECU": {"name": "extreme close-up", "desc": "single feature fills frame, micro-expression or object detail"},
}

CAMERA_SPEC = {
    "static": {"name": "static camera", "desc": "locked frame, contemplative stillness"},
    "push": {"name": "slow dolly forward", "desc": "gradual approach, building intimacy or tension"},
    "pull": {"name": "slow dolly backward", "desc": "gradual withdrawal, isolation or revelation"},
    "rapid_push": {"name": "rapid push-in", "desc": "sudden approach, shock or discovery"},
    "handheld": {"name": "handheld camera with slight drift", "desc": "documentary immediacy, vulnerability"},
}

ANGLE_SPEC = {
    "eye-level": {"name": "eye-level", "desc": "neutral, empathetic perspective"},
    "low": {"name": "slight low angle", "desc": "subtle power, tension, unease"},
    "high": {"name": "slight high angle", "desc": "vulnerability, smallness, observation"},
}

# 2. Subject（角色描述 - 从config读取）
# 3. Action（动作 - 从分镜数据读取）
# 4. Context（场景环境）
COFFEE_SHOP_CONTEXT = {
    "base": "inside a small intimate Chinese coffee shop",
    "details": [
        "wooden counter with worn patina",
        "yellowed sticky notes with handwriting covering one wall",
        "vintage espresso machine behind the counter",
        "afternoon light filtering through lace curtains",
        "a few small round tables with mismatched chairs",
        "the smell of freshly ground beans hangs in the air",
    ],
    "time_map": {
        "Neutral": "soft afternoon daylight",
        "Tension": "late afternoon, long shadows creeping across the counter",
        "Shock": "the light seems to hold still, frozen in the moment",
        "Sadness": "grey overcast light, muted colors",
        "Warmth": "golden hour light, warm amber tones",
        "Mystery": "dim interior, single practical light source, deep shadows",
    },
}

# 5. Style & Ambiance（风格氛围）
STYLE_BASE = "photorealistic Chinese short drama, shot on anamorphic lens, shallow depth of field, natural film grain, 24fps"

# ============================================================
# 爆款对齐升级：
# 1) 场景上下文按 shot.location 动态匹配（旧版硬编码咖啡店，全剧穿帮成同一间店）
# 2) 统一负向提示词（Veo3 常见翻车：多手指/换脸/水印/随机加对白）
# 3) 无台词镜头显式标注 no dialogue；台词镜头标注 lip-sync
# ============================================================

NEGATIVE_PROMPT = (
    "Negative prompt: deformed hands, extra fingers, warped face, inconsistent "
    "character appearance, face swap, changing outfits between shots, watermark, "
    "text overlay, random dialogue, camera shake, low quality, blurry"
)

GENERIC_CONTEXT = {
    "base": "in a modern Chinese city, interior location matching the scene",
    "details": [
        "contemporary Chinese urban interior",
        "practical props that match the scene's social setting",
        "natural window light mixed with practical lamps",
        "clean vertical framing with headroom for titles and subtitles",
    ],
}

LOCATION_CONTEXT_MAP = {
    "咖啡": {
        "base": "inside a small intimate Chinese coffee shop",
        "details": [
            "wooden counter with worn patina",
            "yellowed sticky notes with handwriting covering one wall",
            "vintage espresso machine behind the counter",
            "afternoon light filtering through lace curtains",
        ],
    },
    "办公": {
        "base": "inside a high-rise corporate office, floor-to-ceiling windows",
        "details": [
            "glass conference table with city skyline behind",
            "employee badges and laptop screens glowing",
            "cold blue-white office lighting",
        ],
    },
    "会议": {
        "base": "inside a high-rise corporate boardroom",
        "details": [
            "long polished table, leather chairs",
            "projection screen glow on faces",
            "city skyline through floor-to-ceiling glass",
        ],
    },
    "家": {
        "base": "inside a warm family apartment living room",
        "details": [
            "framed family photos on the wall",
            "fabric sofa with a knitted throw",
            "evening lamp light, warm tones",
        ],
    },
    "客厅": {
        "base": "inside a warm family apartment living room",
        "details": ["fabric sofa", "TV glow", "evening lamp light"],
    },
    "卧室": {
        "base": "inside a softly lit bedroom at night",
        "details": ["bedside lamp glow", "curtains half drawn", "muted warm tones"],
    },
    "医院": {
        "base": "inside a hospital ward corridor",
        "details": [
            "fluorescent white lighting, IV stand",
            "nurses station in soft-focus background",
            "sterile pale green and white palette",
        ],
    },
    "学校": {
        "base": "inside a high school classroom",
        "details": ["rows of desks", "chalk dust in window light", "blackboard handwriting"],
    },
    "教室": {
        "base": "inside a high school classroom",
        "details": ["rows of desks", "chalk dust in window light", "blackboard handwriting"],
    },
    "餐厅": {
        "base": "inside an upscale Chinese restaurant private room",
        "details": ["round banquet table", "lazy susan with dishes", "warm pendant lights"],
    },
    "婚": {
        "base": "inside a wedding banquet hall",
        "details": ["red and gold decorations", "flower arch", "guest tables with champagne"],
    },
    "车": {
        "base": "inside a luxury sedan at night",
        "details": ["city neon streaks past the windows", "leather interior", "dash glow"],
    },
    "豪宅": {
        "base": "inside a palatial mansion hall",
        "details": ["marble floor reflections", "crystal chandelier", "double-height ceiling"],
    },
    "别墅": {
        "base": "inside a palatial mansion hall",
        "details": ["marble floor reflections", "crystal chandelier", "double-height ceiling"],
    },
    "雨": {
        "base": "outdoor city street in heavy rain at night",
        "details": ["neon reflections on wet asphalt", "umbrellas", "headlight halos in the rain"],
    },
}


def _pick_context(shot: dict) -> dict:
    """按 shot.location 关键词匹配场景上下文；未命中回退通用场景。
    mood→光照的 time_map 全场景共用（情绪打光与地点解耦）。"""
    ctx = dict(GENERIC_CONTEXT)
    ctx["time_map"] = COFFEE_SHOP_CONTEXT["time_map"]  # 情绪光照映射与地点无关
    loc = str(shot.get("location") or "")
    for key, mapped in LOCATION_CONTEXT_MAP.items():
        if key in loc:
            merged = dict(mapped)
            merged["time_map"] = ctx["time_map"]
            if len(merged.get("details", [])) < 4:
                merged["details"] = merged.get("details", []) + ctx["details"][:2]
            return merged
    if loc:
        ctx["base"] = f"in a modern Chinese city — {loc}"
    return ctx


LIGHTING_MAP = {
    "Natural": "soft diffused daylight from the window, gentle fill shadows",
    "Warm": "golden hour warmth, amber highlights on skin, soft bokeh from hanging lights",
    "Low key": "low-key lighting, deep pools of shadow, single practical light source, chiaroscuro",
    "High contrast": "high-contrast dramatic lighting, harsh directional key light, deep blacks",
}

MOOD_MAP = {
    "Neutral": "observational, quiet everyday rhythm, understated",
    "Tension": "restrained suspense, held breath, things unsaid",
    "Shock": "sudden rupture in reality, time seems to fracture",
    "Sadness": "melancholic weight, gentle erosion, things lost",
    "Warmth": "intimate connection, gentle humor, small kindnesses",
    "Mystery": "uncanny, something beneath the surface, the ordinary made strange",
}

# ===== 人物表演框架（from facial-expression-prompting）=====

# 情绪→表演配方
PERFORMANCE_RECIPES = {
    "Neutral": {
        "eyes": "steady gaze, natural blink rate, relaxed eyelids",
        "breath": "even, unremarkable",
        "micro": "slight lip tension suggesting habitual composure",
        "body": "economical gestures, practiced routine movements",
    },
    "Tension": {
        "eyes": "gaze darts then locks, blink rate increases, pupils dilate slightly",
        "breath": "shallow, held at transitions, audible exhale",
        "micro": "jaw tightens, fingers press harder than needed, swallow suppressed",
        "body": "shoulders rise half an inch, movements become precise and controlled",
    },
    "Shock": {
        "eyes": "pupils widen, blink freezes mid-lid, stare fixes on middle distance",
        "breath": "sharp inhale caught in chest, exhale delayed",
        "micro": "lips part slightly, brow lifts, nostrils flare",
        "body": "body stills completely for a beat, then one hand moves involuntarily",
    },
    "Sadness": {
        "eyes": "gaze lowers then lifts, eyelids heavy, redness at waterline",
        "breath": "long exhale through nose, chest drops",
        "micro": "lower lip presses against upper, chin dimples, jaw shifts sideways",
        "body": "shoulders curve inward, head tilts down, hands become still",
    },
    "Warmth": {
        "eyes": "gaze softens, crow's feet appear, eyes narrow with genuine smile",
        "breath": "relaxed, natural rhythm returns",
        "micro": "corners of mouth lift asymmetrically, one side before the other",
        "body": "posture opens, weight shifts toward the other person",
    },
    "Mystery": {
        "eyes": "gaze unfocused then sharpens, looks at something others miss",
        "breath": "slightly slower than normal, deliberate",
        "micro": "head tilts a fraction, one eyebrow lifts barely perceptibly",
        "body": "stillness that suggests listening to something beyond the room",
    },
}


def generate_professional_prompt(shot: dict, char_desc: dict, chapter_num: int) -> str:
    """
    用5-part formula生成专业Flow提示词
    
    Formula: [Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]
    """
    st = shot.get("shot_type", "MS")
    cam = shot.get("camera_movement", "static")
    angle = shot.get("camera_angle", "eye-level")
    emotion = shot.get("emotion", "Neutral")
    action = shot.get("action_visual", "")
    chars = shot.get("characters", [])
    focus = shot.get("focus_object", "")
    lighting = shot.get("lighting", "Natural")
    audio = shot.get("audio", {})
    dur = shot.get("duration", 5.0)
    
    # === Part 1: Cinematography ===
    shot_info = SHOT_SPEC.get(st, SHOT_SPEC["MS"])
    cam_info = CAMERA_SPEC.get(cam, CAMERA_SPEC["static"])
    angle_info = ANGLE_SPEC.get(angle, ANGLE_SPEC["eye-level"])
    
    # 选择镜头描述（根据景别和情绪）
    if st == "ECU":
        lens_desc = "macro lens, extremely shallow depth of field, f/1.4"
    elif st == "CU":
        lens_desc = "85mm portrait lens, shallow depth of field, f/2.0"
    elif st == "MCU":
        lens_desc = "50mm lens, moderate shallow depth of field, f/2.8"
    else:
        lens_desc = "35mm lens, natural depth of field, f/4.0"
    
    cinematography = f"{shot_info['name']}, {cam_info['name']}, {angle_info['name']}, {lens_desc}"
    
    # === Part 2: Subject ===
    subject_parts = []
    for char_en in chars:
        desc = char_desc.get(char_en, {})
        full = desc.get("full", char_en)
        subject_parts.append(full)
    subject = "; ".join(subject_parts) if subject_parts else "a character"
    
    # === Part 3: Action + Performance ===
    perf = PERFORMANCE_RECIPES.get(emotion, PERFORMANCE_RECIPES["Neutral"])
    
    action_parts = [action]
    # 添加人物表演细节（从facial-expression框架）
    if st in ("CU", "ECU", "MCU"):
        action_parts.append(f"eyes: {perf['eyes']}")
        action_parts.append(f"breath: {perf['breath']}")
        action_parts.append(f"micro-expression: {perf['micro']}")
    if st in ("MS", "WS"):
        action_parts.append(f"body language: {perf['body']}")
    
    # 焦点物
    if focus:
        action_parts.append(f"attention on {focus}")
    
    action_text = ". ".join(action_parts)
    
    # === Part 4: Context（按 shot.location 动态匹配，不再全剧一间咖啡店）===
    ctx = _pick_context(shot)
    time_light = ctx["time_map"].get(emotion, "soft afternoon daylight")
    # 随机选3个场景细节
    import random
    random.seed(shot.get("shot_id", 0) + chapter_num * 100)
    details = random.sample(ctx["details"], min(3, len(ctx["details"])))
    context = f"{ctx['base']}, {time_light}, {', '.join(details)}"
    
    # === Part 5: Style & Ambiance ===
    light_desc = LIGHTING_MAP.get(lighting, LIGHTING_MAP["Natural"])
    mood_desc = MOOD_MAP.get(emotion, MOOD_MAP["Neutral"])
    style = f"{STYLE_BASE}, {light_desc}, {mood_desc} mood"
    
    # === 组装完整提示词 ===
    prompt = f"{cinematography}. {subject} — {action_text}. {context}. {style}."
    
    # 音频标注：有台词→口型+语种；无台词→显式 no dialogue（防 Veo3 随机加对白）
    audio_notes = []
    dlg = audio.get("dialogue_zh", "")
    voice = audio.get("voiceover_zh", "")
    if dlg:
        speaker = audio.get("dialogue_speaker", "")
        audio_notes.append(
            f'Dialogue ({speaker}, lip-sync accurate, speaking Mandarin Chinese): "{dlg}"'
        )
    if voice:
        audio_notes.append(f'Voiceover (inner monologue, no lip movement): "{voice}"')
    if not dlg and not voice:
        audio_notes.append("No dialogue, ambient sound only, natural room tone")

    if audio_notes:
        prompt += f" Audio: {'. '.join(audio_notes)}."

    # 时长、画幅与统一负向提示词
    prompt += f" Duration: {dur:.0f}s. Aspect ratio: 9:16 vertical. {NEGATIVE_PROMPT}."

    return prompt


def generate_keyframe_prompt(shot: dict, char_desc: dict) -> str:
    """关键帧静帧提示词（图生视频工作流）：
    即梦/可灵先用文生图出本镜第一帧（人物一致性远好于纯文生视频），
    再把静帧喂给图生视频。复用分镜的场景/构图/表演描述，去掉音频/时长。"""
    st = shot.get("shot_type", "MS")
    st_name = SHOT_SPEC.get(st, {}).get("name", "medium shot")
    subject_parts = []
    for char_en in shot.get("characters", []):
        desc = char_desc.get(char_en, {})
        full = desc.get("full", char_en)
        subject_parts.append(full)
    subject = "; ".join(subject_parts) if subject_parts else "a character"
    perf = PERFORMANCE_RECIPES.get(shot.get("emotion", "Neutral"), PERFORMANCE_RECIPES["Neutral"])
    ctx = _pick_context(shot)
    time_light = ctx["time_map"].get(shot.get("emotion", "Neutral"), "soft afternoon daylight")

    parts = [f"cinematic still frame, {st_name}"]
    if shot.get("characters"):
        parts.append(f"featuring {subject}")
        parts.append(f"expression: {perf.get('eyes', 'focused eyes')}")
    if shot.get("action_visual"):
        parts.append(str(shot["action_visual"]))
    parts.append(f"{ctx['base']}, {time_light}")
    parts.append("photorealistic Chinese short drama, film grain, shallow depth of field, 9:16 vertical, 8k detail")
    parts.append("IDENTITY LOCK: faces and outfits must match the character reference sheet exactly")
    parts.append("Negative prompt: deformed hands, extra fingers, warped face, text, watermark, blurry")
    return ". ".join(parts)


def export_professional_prompts(project_dir: Path, only_chapter: int = 0):
    """导出所有章节的专业Flow提示词"""
    d = project_dir / "v3_storyboard"
    out_dir = project_dir / "flow_prompts_pro"
    out_dir.mkdir(exist_ok=True)
    
    # 加载角色描述
    import yaml
    char_file = project_dir / "config" / "characters.yaml"
    if char_file.exists():
        chars_raw = yaml.safe_load(char_file.read_text(encoding="utf-8"))
        # 兼容两种格式：{characters: [list]}（juben init 模板）与 {characters: {name: {...}}}
        chars_items = []
        if isinstance(chars_raw, dict):
            c = chars_raw.get("characters", chars_raw)
            chars_items = list(c.values()) if isinstance(c, dict) else c
        elif isinstance(chars_raw, list):
            chars_items = chars_raw
        char_desc = {}
        for info in chars_items:
            if isinstance(info, dict):
                # 缺 en 字段时回退用中文名（模板占位角色没有 en）
                key = str(info.get("en") or info.get("name") or "").strip()
                if key:
                    char_desc[key] = info
    else:
        char_desc = {}
    
    # === v1.1.0: 扫描 v3_storyboard 目录里所有 chN_shots.json ===
    max_chapter = 0
    if d.exists():
        for f in d.glob("ch*_shots.json"):
            try:
                n = int(f.stem.split("_")[0][2:])
                if n > max_chapter:
                    max_chapter = n
            except (ValueError, IndexError):
                pass
    if max_chapter == 0:
        max_chapter = 20  # fallback

    for ch in range(1, max_chapter + 1):
        shots_file = d / f"ch{ch:03d}_shots.json"
        if not shots_file.exists():
            continue
        
        shots = json.loads(shots_file.read_text(encoding="utf-8"))
        lines = []
        lines.append(f"# 第{ch}章 — 专业Flow提示词（5-Part Formula）")
        lines.append(f"# 基于Google Veo 3.1官方提示指南 + 人物表演框架")
        lines.append(f"# 共{len(shots)}个镜头，{sum(s['duration'] for s in shots):.0f}秒")
        lines.append("")
        lines.append("## 提示词结构")
        lines.append("```")
        lines.append("[Cinematography] + [Subject] + [Action+Performance] + [Context] + [Style&Ambiance]")
        lines.append("```")
        lines.append("")
        
        for s in shots:
            prompt = generate_professional_prompt(s, char_desc, ch)
            keyframe = generate_keyframe_prompt(s, char_desc)
            audio = s.get("audio", {})

            lines.append(f"### Shot {s['shot_id']} [{s['shot_type']}] {s['duration']:.0f}s"
                         + (f" （节拍: {s.get('pacing_label', '')}）" if s.get('pacing_label') else ""))
            lines.append(f"**Camera:** {CAMERA_SPEC.get(s.get('camera_movement','static'),{}).get('name','static')}")
            lines.append(f"**Emotion:** {s.get('emotion','Neutral')}")
            if audio.get("dialogue_zh"):
                lines.append(f"**Dialogue:** {audio['dialogue_zh']}")
            if audio.get("voiceover_zh"):
                lines.append(f"**Voiceover:** {audio['voiceover_zh']}")
            lines.append("")
            lines.append("**Prompt:**")
            lines.append(f"```")
            lines.append(prompt)
            lines.append(f"```")
            lines.append("")
            # 图生视频工作流：先出静帧（一致性更好），再图生视频
            lines.append("**Keyframe（先文生图出首帧，再图生视频）:**")
            lines.append(f"```")
            lines.append(keyframe)
            lines.append(f"```")
            lines.append("")
        
        (out_dir / f"ch{ch:03d}_pro_prompts.md").write_text(
            "\n".join(lines), encoding="utf-8")
    
    print(f"Exported professional prompts to {out_dir}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1])
    else:
        project_dir = Path.home() / "juben/projects/心声咖啡"
    export_professional_prompts(project_dir)
