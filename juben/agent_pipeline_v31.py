"""
Agent-as-LLM Pipeline v3.1 — Full rewrite with all fixes
"""
import json, re, sys, os
from pathlib import Path

CHAR_EN = {
    "苏念": "Su Nian", "顾深": "Gu Shen", "林可": "Lin Ke",
    "陈锐": "Chen Rui", "苏远": "Su Yuan", "外婆": "grandmother",
}
CHAR_TAGS_FULL = {
    "Su Nian": "26yo Chinese woman, round face, shoulder-length hair, apron, burn scar on left ring finger",
    "Gu Shen": "30yo Chinese man, tall, silver-framed glasses, dark suit, callus on right index finger",
    "Lin Ke": "25yo Chinese woman, ponytail, colorful nails, large art bag",
    "Chen Rui": "32yo Chinese man, square jaw, short hair, expensive watch",
    "Su Yuan": "young Chinese boy, round face, short hair, warm smile",
}
CHAR_TAGS_SHORT = {
    "Su Nian": "barista, burn scar on ring finger",
    "Gu Shen": "tall man, silver glasses, dark suit",
    "Lin Ke": "ponytail, colorful nails, art bag",
    "Chen Rui": "square jaw, expensive watch",
    "Su Yuan": "round face boy, warm smile",
}
LOC_EN = {
    "念想咖啡店": "Nianxiang coffee shop", "念想": "Nianxiang coffee shop",
    "咖啡店": "coffee shop", "面馆": "noodle shop", "巷子": "narrow alley",
    "公寓": "apartment", "浴室": "bathroom", "写字楼": "office building",
}
ACTION_BLACKLIST = [
    "stands in the scene", "interacts with", "all sounds vanish",
    "all sounds fade", "a vision flashes", "the scar is still visible",
    "character performs action", "walks contract",
]
ACTION_REWRITE = {
    "all sounds vanish": "{char} closes eyes, fingers tighten around cup rim",
    "all sounds fade to silence": "{char} closes eyes, fingers tighten around cup rim",
    "a vision flashes": "{char} pupils contract, body freezes mid-motion",
    "the scar is still visible": "{char} traces finger across the burn scar on left ring finger",
    "stands in the scene": "{char} stands behind counter, gaze lowered, breathing slowly",
    "character performs action": "{char} stands behind counter, breathing slowly",
    "interacts with": "{char} reaches toward",
    "walks contract": "{char} slides contract across counter",
}
ACTION_TEMPLATES = [
    (r"擦.*?吧台", "{char} wipes the counter with a rag"),
    (r"擦.*?桌子", "{char} wipes a table clean"),
    (r"磨.*?豆", "{char} grinds coffee beans, the grinder humming"),
    (r"端.*?咖啡|端.*?杯", "{char} carries a steaming cup"),
    (r"端起.*?杯", "{char} picks up the cup carefully"),
    (r"放下.*?杯|杯子.*?放下", "{char} sets the cup down on the counter"),
    (r"倒.*?水|倒.*?咖啡", "{char} pours water into a cup"),
    (r"泡.*?咖啡|泡.*?茶", "{char} brews coffee, steam rising"),
    (r"拉花", "{char} draws latte art in the foam"),
    (r"做好.*?端", "{char} finishes preparing and carries the cup over"),
    (r"喝了一口|喝了一", "{char} takes a slow sip"),
    (r"喝完|一饮而尽", "{char} drains the cup in one gulp"),
    (r"端起来.*?闭眼|端起.*?闭", "{char} lifts the cup and closes eyes"),
    (r"闭眼$|闭上眼$|闭上眼睛$", "{char} slowly closes eyes"),
    (r"睁开眼|猛地睁开", "{char} snaps eyes open"),
    (r"转身", "{char} turns around"),
    (r"回头", "{char} turns head back"),
    (r"走进来?|走入|走进", "{char} walks through the door"),
    (r"走出去|走出|出了门", "{char} walks out the door"),
    (r"站起来?|起身", "{char} stands up from the seat"),
    (r"坐[到在下]", "{char} sits down"),
    (r"蹲[下去]", "{char} crouches down"),
    (r"弯腰", "{char} bends down"),
    (r"追出去|追[了出来]", "{char} runs out after someone"),
    (r"离开|走了", "{char} turns and leaves"),
    (r"点头", "{char} nods slowly"),
    (r"摇头", "{char} shakes head"),
    (r"低头看|低头", "{char} looks down"),
    (r"抬头", "{char} looks up"),
    (r"盯着|注视", "{char} stares intently"),
    (r"皱眉", "{char} frowns"),
    (r"微笑|笑了", "{char} smiles faintly"),
    (r"愣住|愣了", "{char} freezes mid-motion"),
    (r"脸色.*?白|脸白了", "{char} goes pale"),
    (r"流泪|哭了?|泪.*?下", "{char} tears roll down cheeks"),
    (r"擦.*?泪", "{char} wipes tears from eyes"),
    (r"深吸一口气", "{char} takes a deep breath"),
    (r"攥紧|握紧", "{char} clenches fists tightly"),
    (r"发抖|颤抖", "{char} trembles visibly"),
    (r"手指.*?敲", "{char} taps fingers rhythmically on counter"),
    (r"伸手.*?摸|伸手.*?触", "{char} reaches out to touch gently"),
    (r"翻.*?手|翻过.*?手", "{char} turns hand over to inspect"),
    (r"手.*?停", "{char} hand pauses mid-motion"),
    (r"指甲.*?掐|指甲.*?陷", "{char} digs fingernails into palm"),
    (r"掏.*?手机", "{char} pulls out phone"),
    (r"打字|在.*?打字", "{char} types on phone screen"),
    (r"扫码", "{char} scans QR code on phone"),
    (r"攥.*?钥匙", "{char} grips keys tightly"),
    (r"揭.*?便签", "{char} peels sticky note off the wall"),
    (r"水龙头|开水|打开.*?水", "{char} turns on the faucet"),
    (r"冲洗|冲掉", "{char} rinses under running water"),
    (r"擦干", "{char} dries hands with a towel"),
    (r"收拾|收.*?杯子", "{char} clears cups from the table"),
    (r"叠.*?抹布", "{char} folds the cleaning rag"),
    (r"拿.*?抹布", "{char} picks up a cleaning rag"),
    (r"洗.*?杯", "{char} washes a cup under running water"),
    (r"锁.*?门", "{char} locks the front door"),
    (r"翻.*?合同|翻.*?文件", "{char} flips through contract pages"),
    (r"推.*?名片|推.*?信封|推.*?纸", "{char} slides an envelope across the counter"),
    (r"接过.*?名片|接过.*?信封", "{char} takes the envelope"),
    (r"展开.*?画|打开.*?画", "{char} unrolls a painting on the counter"),
    (r"收起.*?画|卷.*?画", "{char} rolls up the painting"),
    (r"注意到|发现", "{char} notices something unexpected"),
    (r"看到|望见", "{char} sees something"),
    (r"听到", "{char} hears a sound"),
    (r"想起来|想起来了", "{char} suddenly remembers"),
    (r"想不起来|不记得", "{char} struggles to remember"),
    (r"门铃", "the doorbell chimes"),
    (r"风铃", "the wind chimes ring softly"),
    (r"灯.*?灭|灯.*?暗", "the lights flicker and go out"),
    (r"灯.*?亮|灯.*?重新", "the lights come back on"),
    (r"冒热气|冒着热", "steam rises from the cup"),
    (r"涟漪", "ripples spread across the coffee surface"),
    (r"便签.*?淡|字迹.*?淡", "the handwriting on the sticky note fades by one stroke"),
    (r"便签.*?掉|便签.*?落", "the sticky note falls from the wall"),
    (r"疤痕.*?消失|疤痕.*?没了", "the scar on the skin has vanished"),
    (r"印痕.*?消失|印.*?消失", "the mark has disappeared"),
    (r"口红印|唇印", "a faint lipstick mark on the cup rim"),
    (r"墨渍", "a small ink stain on the suit cuff"),
    (r"痣.*?消失|痣.*?没", "the mole has vanished from the skin"),
    (r"手机.*?震|手机.*?响", "the phone buzzes on the counter"),
    (r"消息|收到.*?消息", "a message notification on screen"),
    (r"回拨|拨打", "{char} dials the number again"),
    (r"挂了|挂断", "the call disconnects"),
    (r"接过.*?杯", "{char} accepts the cup"),
    (r"递给|推给", "{char} hands over"),
    (r"叫住|拦住", "{char} calls out to stop someone"),
    (r"弯腰.*?耳边|贴.*?耳边", "{char} leans close and whispers"),
    (r"挥手", "{char} waves goodbye"),
    (r"跪[下来说]", "{char} kneels down"),
]
CAMERA_SEMANTIC = {
    "leaves": "pull", "walks out": "pull", "exits": "pull", "turns and leaves": "pull",
    "opens eyes": "rapid_push", "discovers": "rapid_push", "notices": "rapid_push",
    "snaps eyes open": "rapid_push",
    "stares": "static", "gazes": "static", "contemplates": "static",
    "looks down": "static", "looks up": "static",
    "reaches out": "push", "touches": "push", "picks up": "push",
    "closes eyes": "static", "trembles": "handheld",
}
VOICE_EMOTION = {
    "Neutral": "calm, conversational",
    "Tension": "whispered, restrained, breathing heavy",
    "Shock": "sharp intake of breath, voice breaking",
    "Sadness": "soft, trailing off, voice cracking",
    "Warmth": "gentle, warm tone",
    "Mystery": "low, deliberate, pauses between words",
}
READING_MIND_TEMPLATE = [
    {"space": "Transition", "action": "{char} lifts the cup, fingers trembling around the warm rim",
     "shot_type": "ECU", "camera": "static", "emotion": "Tension", "focus": "cup rim"},
    {"space": "Mental", "action": "{char} closes eyes, eyelashes trembling. Background figures freeze, steam hangs motionless",
     "shot_type": "CU", "camera": "rapid_push", "emotion": "Shock", "focus": ""},
    {"space": "Physical", "action": "{char} looks down at left hand, the scar on the ring finger has changed",
     "shot_type": "ECU", "camera": "static", "emotion": "Mystery", "focus": "scar on ring finger"},
]


# 指代词→角色映射（修复灰色西装→Gu Shen等）
PRONOUN_MAP = [
    (r"灰色西装|西装男|男人|顾客|他(?!的)", "Gu Shen"),
    (r"姑娘|女孩|女(?!人)", "Su Nian"),
]

def detect_chars(text):
    chars = []
    # 显式角色名
    for zh, en in CHAR_EN.items():
        if zh in text and en in CHAR_TAGS_FULL:
            if en not in chars:
                chars.append(en)
    # 指代词推断
    for pattern, en_name in PRONOUN_MAP:
        if re.search(pattern, text) and en_name in CHAR_TAGS_FULL:
            if en_name not in chars:
                chars.append(en_name)
    return chars if chars else ["Su Nian"]


def detect_speaker(paragraph, prev_speaker=""):
    for zh_name in CHAR_EN:
        if re.search(rf"{zh_name}(?:说|道|问|答|喊|叫|应|回)", paragraph):
            return CHAR_EN[zh_name]
    if re.search(r"他(?:说|道|问|答)", paragraph):
        male = ["Gu Shen", "Chen Rui", "Su Yuan"]
        return prev_speaker if prev_speaker in male else "Gu Shen"
    if re.search(r"她(?:说|道|问|答)", paragraph):
        female = ["Su Nian", "Lin Ke"]
        return prev_speaker if prev_speaker in female else "Su Nian"
    if re.search(r'["「]', paragraph):
        for zh_name, en_name in CHAR_EN.items():
            if zh_name in paragraph:
                return en_name
    return prev_speaker


def detect_action_subject(text, default="Su Nian"):
    # 1. 显式角色名
    for zh_name, en_name in CHAR_EN.items():
        if zh_name in text and en_name in CHAR_TAGS_FULL:
            return en_name
    # 2. 男性指代词（灰色西装、男人、顾客等）
    male_kw = ["灰色西装", "西装男", "男人", "顾客", "西装", "领带"]
    if any(kw in text for kw in male_kw):
        return "Gu Shen"
    # 3. 代词"他"（需要上下文，默认Gu Shen）
    if re.search(r"他(?!的)", text) and not re.search(r"她", text):
        # 如果前面有男性角色上下文
        if any(kw in text for kw in ["说", "道", "问", "喝", "坐", "站", "走", "掏"]):
            return "Gu Shen"
    # 4. 女性指代词
    if any(kw in text for kw in ["苏念", "她", "姑娘", "女孩", "老板", "围裙"]):
        return "Su Nian"
    return default


def detect_location(text):
    for zh, en in LOC_EN.items():
        if zh in text:
            return en
    return "Nianxiang coffee shop"


def detect_emotion(text):
    if any(kw in text for kw in ["猛地", "突然", "瞳孔", "愣住", "震惊"]):
        return "Shock"
    if any(kw in text for kw in ["攥紧", "心跳", "发抖", "紧张"]):
        return "Tension"
    if any(kw in text for kw in ["泪", "哭", "痛"]):
        return "Sadness"
    if any(kw in text for kw in ["微笑", "温暖", "笑了"]):
        return "Warmth"
    if any(kw in text for kw in ["消失", "淡了", "模糊", "神秘"]):
        return "Mystery"
    return "Neutral"


def detect_space(text):
    if any(kw in text for kw in ["世界安静", "声音消失", "脑海", "画面闪过", "画面碎了"]):
        return "Mental"
    if any(kw in text for kw in ["闭眼", "端起.*?杯"]):
        return "Transition"
    return "Physical"


def translate_action(text, char="Su Nian"):
    for bad in ACTION_BLACKLIST:
        if bad in text.lower():
            for bad_key, rewrite in ACTION_REWRITE.items():
                if bad_key in text.lower():
                    return rewrite.replace("{char}", char)
            return f"{char} stands behind counter, gaze lowered, breathing slowly"
    for pattern, template in ACTION_TEMPLATES:
        if re.search(pattern, text):
            return template.replace("{char}", char) if "{char}" in template else template
    # 提取微动作（比模板更细粒度）
    micro = {
        "盯着": "stares intently at", "注视": "gazes at",
        "皱眉": "frowns slightly", "微笑": "smiles faintly",
        "叹气": "sighs quietly", "吸气": "breathes in sharply",
        "吞咽": "swallows hard", "眨眼": "blinks slowly",
        "侧头": "tilts head", "垂眼": "lowers gaze",
        "抿嘴": "presses lips together", "咬唇": "bites lower lip",
        "攥拳": "clenches fist", "松手": "releases grip",
        "触碰": "touches gently", "抚摸": "traces finger across",
        "靠近": "leans closer", "后退": "steps back",
        "靠在": "leans against", "倚着": "rests against",
        "端详": "examines closely", "翻看": "flips through",
        "凝视": "gazes steadily", "扫视": "glances around",
    }
    for zh, en in micro.items():
        if zh in text:
            return f"{char} {en}"
    nouns = {"咖啡": "coffee cup", "杯子": "cup", "手机": "phone", "便签": "sticky note",
             "照片": "photo", "镜子": "mirror", "门": "door", "窗": "window",
             "伞": "umbrella", "钥匙": "key", "合同": "contract", "名片": "card",
             "茶": "tea cup", "抹布": "rag", "水龙头": "faucet", "水池": "sink",
             "围裙": "apron", "灯": "light", "信": "letter", "画": "painting",
             "钱包": "wallet", "筷子": "chopsticks", "碗": "bowl"}
    verbs = {"看": "gazes at", "拿": "picks up", "放": "places down",
             "走": "walks slowly", "坐": "sits quietly",
             "说": "speaks softly", "洗": "rinses", "擦": "wipes",
             "端": "holds carefully", "喝": "sips", "摸": "touches gently",
             "翻": "flips through", "写": "writes", "收": "puts away"}
    fn = [nouns[k] for k in nouns if k in text]
    fv = [verbs[k] for k in verbs if k in text]
    if fv and fn:
        return f"{char} {fv[0]} the {fn[0]}"
    if fv:
        return f"{char} {fv[0]}"
    if fn:
        return f"{char} stares at the {fn[0]}"
    # 最终兜底：根据上下文生成具体微动作
    if "杯" in text or "咖啡" in text:
        return f"{char} holds the cup with both hands, staring at the surface"
    if "门" in text or "窗" in text:
        return f"{char} stands by the door, gazing outward"
    if "墙" in text or "便签" in text:
        return f"{char} reaches toward the wall, fingers hovering over the note"
    if "手" in text or "指" in text:
        return f"{char} examines own hands, turning them over slowly"
    return f"{char} stands still, shoulders slightly tense, eyes unfocused"


def extract_dialogue(text):
    matches = re.findall(r'["\u300c]([^"\u300d]+)["\u300d]', text)
    sound = re.compile(r"^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$")
    inner_markers = re.findall(r'\*["\u300c]([^"\u300d]+)["\u300d]\*', text)
    result = []
    for m in matches:
        if len(m) <= 2 or sound.match(m) or m in inner_markers:
            continue
        result.append(m)
    return result


def extract_inner_voice(text):
    return re.findall(r'\*["\u300c]([^"\u300d]+)["\u300d]\*', text)


def extract_anchor(text):
    kw = {"口红印": "lipstick mark", "唇印": "lipstick mark", "疤痕": "scar on skin",
          "印痕": "faint mark", "墨渍": "ink stain", "杯沿": "cup rim", "杯壁": "cup wall",
          "便签": "sticky note", "字迹": "handwriting", "钥匙": "key", "照片": "old photo",
          "戒指": "ring", "无名指": "ring finger", "手背": "back of hand", "痣": "mole",
          "画": "watercolor painting", "名片": "business card", "合同": "contract"}
    for zh, en in kw.items():
        if zh in text:
            return en
    return ""


def choose_camera_for_action(action_text, emotion):
    action_lower = action_text.lower()
    for keyword, camera in CAMERA_SEMANTIC.items():
        if keyword in action_lower:
            return camera
    return {"Shock": "rapid_push", "Tension": "push", "Sadness": "pull",
            "Warmth": "static", "Neutral": "static", "Mystery": "push"}.get(emotion, "static")


def split_paragraphs(text):
    return [l.strip() for l in text.strip().split("\n") if l.strip() and not l.startswith("#")]


def is_ability_event(text):
    has_action = any(kw in text for kw in ["端起", "闭眼", "闭上眼", "杯壁", "杯沿", "喝了一口"])
    has_trigger = any(kw in text for kw in ["世界安静", "声音消失", "闭眼", "闭上眼"])
    return has_action and has_trigger


def should_cut(prev_text, curr_text, prev_speaker, curr_speaker):
    if is_ability_event(curr_text):
        return True
    if any(kw in curr_text for kw in ["消失", "淡了", "印痕", "疤痕", "不见了", "没了"]):
        return True
    if curr_speaker and prev_speaker and curr_speaker != prev_speaker:
        return True
    if re.search(r'["\u300c]', prev_text) and not re.search(r'["\u300c]', curr_text):
        return True
    scene_kw = ["窗外", "门口", "门外", "巷子里", "浴室", "镜子前", "镜子里", "墙上", "照片里"]
    if any(kw in curr_text for kw in scene_kw) and not any(kw in prev_text for kw in scene_kw):
        return True
    # 动作切换切分
    action_kw = ["端起", "放下", "站起来", "坐下", "走过去", "走过来", "转过身", "转身",
                 "掏出", "拿出", "打开", "关上", "锁上", "揭下来", "贴回去", "收起来",
                 "回来", "回到", "走到", "离开", "进来", "出去", "追出去",
                 "弯腰", "跪下来", "蹲下", "起身",
                 "收拾", "放进", "冲掉", "注意到", "看到", "发现",
                 "哭了", "笑了", "擦掉", "洗完", "喝完"]
    if any(kw in curr_text for kw in action_kw):
        return True
    # 情绪切换切分
    emotion_kw = ["愣住", "震惊", "突然", "猛地", "忽然", "一下子", "吓了一跳"]
    if any(kw in curr_text for kw in emotion_kw):
        return True
    # 手机/通讯切分
    if re.search(r"手机|消息|电话|来电|挂断|拨打", curr_text):
        return True
    return False


def make_beat(beat_id, paragraphs, primary_char=None):
    text = "\n".join(paragraphs)
    chars = detect_chars(text)
    if primary_char is None:
        primary_char = detect_action_subject(text, chars[0] if chars else "Su Nian")
    action = translate_action(text, primary_char)
    dialogues = extract_dialogue(text)
    inner = extract_inner_voice(text)
    dialogue_text, dialogue_speaker, inner_text, voice_type = "", "", "", "none"
    if inner:
        inner_text = inner[0][:100]
    if dialogues:
        raw_dlg = dialogues[0][:80]
        if raw_dlg.startswith("……") or raw_dlg.startswith("...") or            any(kw in raw_dlg for kw in ["KPI", "合同", "想不起来", "为什么", "她说得对", "不记得"]):
            inner_text = inner_text or raw_dlg
        elif not inner_text:
            dialogue_text = raw_dlg
            for zh_name, en_name in CHAR_EN.items():
                if zh_name in text:
                    dialogue_speaker = en_name
                    break
            if not dialogue_speaker:
                dialogue_speaker = primary_char
    # 设置voice_type
    if inner_text:
        voice_type = "inner_voice"
    elif dialogue_text:
        voice_type = "onscreen"
        for zh_name, en_name in CHAR_EN.items():
            if zh_name in text:
                dialogue_speaker = en_name
                break
        if not dialogue_speaker:
            dialogue_speaker = primary_char
        voice_type = "onscreen"
    anchor = extract_anchor(text)
    space = detect_space(text)
    emotion = detect_emotion(text)
    return {
        "beat_id": beat_id, "space": space, "characters_present": chars,
        "primary_char": primary_char, "action_visual": action,
        "spoken_dialogue": dialogue_text, "dialogue_speaker": dialogue_speaker,
        "inner_voice": inner_text, "voice_type": voice_type,
        "focus_object": anchor, "emotion": emotion, "source_text": text[:80],
    }


def extract_beats_from_chapter(chapter_text, chapter_num):
    paras = split_paragraphs(chapter_text)
    if not paras:
        return []
    beats, current_group, beat_id, prev_speaker, in_reading = [], [], 1, "", False
    for para in paras:
        speaker = detect_speaker(para, prev_speaker)
        prev_text = current_group[-1] if current_group else ""
        if current_group and should_cut(prev_text, para, prev_speaker, speaker):
            combined = "\n".join(current_group)
            if is_ability_event(combined) and not in_reading:
                pc = detect_action_subject(combined, "Su Nian")
                for tpl in READING_MIND_TEMPLATE:
                    beats.append({
                        "beat_id": beat_id, "space": tpl["space"],
                        "characters_present": [pc], "primary_char": pc,
                        "action_visual": tpl["action"].replace("{char}", pc),
                        "spoken_dialogue": "", "dialogue_speaker": "",
                        "inner_voice": "", "voice_type": "none",
                        "focus_object": tpl["focus"], "emotion": tpl["emotion"],
                        "source_text": "[reading mind template]",
                    })
                    beat_id += 1
                in_reading = True
                current_group = [para]
                prev_speaker = speaker
                continue
            else:
                b = make_beat(beat_id, current_group)
                if b:
                    beats.append(b)
                    beat_id += 1
                current_group = []
                in_reading = False
        current_group.append(para)
        if speaker:
            prev_speaker = speaker
    if current_group:
        b = make_beat(beat_id, current_group)
        if b:
            beats.append(b)
    return beats


def process_all_chapters():
    sys.path.insert(0, str(Path.home() / "juben"))
    from juben.adapter_v3 import SmartShotCompiler
    from juben.storyboard_lint import StoryboardLint
    from juben.prompt_renderer import SHOT_TYPE_EN, CAMERA_MOVE_EN, ANGLE_EN, LIGHTING_EN, MOOD_EN

    project_dir = Path.home() / "juben/projects/心声咖啡"
    output_dir = project_dir / "v3_storyboard"
    output_dir.mkdir(exist_ok=True)
    compiler = SmartShotCompiler()
    lint = StoryboardLint()
    char_count = {}
    results = []

    for ch_num in range(1, 21):
        ch_path = project_dir / "chapters" / f"{ch_num:03d}.md"
        if not ch_path.exists():
            continue
        chapter_text = ch_path.read_text(encoding="utf-8")
        beats = extract_beats_from_chapter(chapter_text, ch_num)
        if not beats:
            continue
        location = detect_location(chapter_text)
        shots = compiler.compile(beats, target_duration=90, location=location)
        char_count.clear()
        for shot in shots:
            shot["characters"] = [CHAR_EN.get(c, c) for c in shot.get("characters", [])]
            action_text = shot.get("action_visual", "")
            emotion = shot.get("emotion", "Neutral")
            for keyword in CAMERA_SEMANTIC:
                if keyword in action_text.lower():
                    shot["camera_movement"] = choose_camera_for_action(action_text, emotion)
                    break
            char_parts = []
            for cn in shot.get("characters", []):
                char_count[cn] = char_count.get(cn, 0) + 1
                tag = CHAR_TAGS_FULL.get(cn, cn) if char_count[cn] == 1 else CHAR_TAGS_SHORT.get(cn, cn)
                char_parts.append(f"{cn} ({tag})")
            parts = []
            st = shot.get("shot_type", "MS")
            cm = shot.get("camera_movement", "static")
            ca = shot.get("camera_angle", "eye-level")
            parts.append(f"{SHOT_TYPE_EN.get(st, 'medium shot')}, {CAMERA_MOVE_EN.get(cm, 'static camera')}, {ANGLE_EN.get(ca, 'eye level')}")
            if char_parts:
                parts.append(f"featuring {', '.join(char_parts)}")
            act = shot.get("action_visual", "")
            for bad in ACTION_BLACKLIST:
                if bad in act.lower():
                    char0 = shot.get("characters", ["character"])[0]
                    act = ACTION_REWRITE.get(bad, act).replace("{char}", char0)
                    break
            if act:
                parts.append(act)
            anchors = shot.get("visual_anchors", [])
            if anchors:
                parts.append(f"close-up detail on {', '.join(anchors)}")
            if location:
                parts.append(f"in {location}")
            parts.append(LIGHTING_EN.get(shot.get("lighting", "Natural"), "natural daylight"))
            parts.append(MOOD_EN.get(emotion, "neutral, observational"))
            parts.append("cinematic, 9:16 vertical, photorealistic, 4K")
            shot["veo_prompt"] = ", ".join(parts)
            beat_data = beats[shot["shot_id"] - 1] if shot["shot_id"] <= len(beats) else {}
            shot["audio"] = {
                "dialogue_zh": beat_data.get("spoken_dialogue", ""),
                "dialogue_speaker": beat_data.get("dialogue_speaker", ""),
                "voiceover_zh": beat_data.get("inner_voice", ""),
                "voice_type": beat_data.get("voice_type", "none"),
                "subtitle": beat_data.get("inner_voice", "")[:30] if beat_data.get("inner_voice") else "",
                "emotion_tag": VOICE_EMOTION.get(emotion, "calm, conversational"),
                "duration_hint": f"{shot['duration']:.1f}s",
            }
        scene_locations = {i: location for i in range(len(beats))}
        violations = lint.check(shots, scene_locations)
        lint_pass = lint.is_pass(violations)
        errors = [v for v in violations if v.severity == "error"]
        warns = [v for v in violations if v.severity == "warning"]
        cn = sum(1 for s in shots if any("\u4e00" <= c <= "\u9fff" for c in s.get("veo_prompt", "")))
        total_dur = sum(s["duration"] for s in shots)
        (output_dir / f"ch{ch_num:03d}_shots.json").write_text(json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / f"ch{ch_num:03d}_beats.json").write_text(json.dumps(beats, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "PASS" if lint_pass else "FAIL"
        results.append((ch_num, len(shots), round(total_dur), len(errors), len(warns), status, cn))
        print(f"Ch{ch_num:>2}: {len(shots):>2}S {total_dur:>3.0f}s E:{len(errors)} W:{len(warns)} CN:{cn} {status}", flush=True)
        for v in errors:
            print(f"  ERROR Shot {v.shot_id}: [{v.rule}] {v.message[:80]}")
    print("\n" + "=" * 60)
    ok = sum(1 for r in results if r[5] == "PASS")
    ts = sum(r[1] for r in results)
    te = sum(r[3] for r in results)
    tw = sum(r[4] for r in results)
    print(f"{ok}/20 PASS | {ts} shots | {te} errors | {tw} warnings")


def generate_srt_files():
    project_dir = Path.home() / "juben/projects/心声咖啡"
    srt_dir = project_dir / "srt_subtitles"
    srt_dir.mkdir(exist_ok=True)
    for ch_num in range(1, 21):
        f = project_dir / "v3_storyboard" / f"ch{ch_num:03d}_shots.json"
        if not f.exists():
            continue
        shots = json.loads(f.read_text(encoding="utf-8"))
        srt_lines, seq, t = [], 1, 0.0
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
                srt_lines.append(f"{seq}")
                srt_lines.append(f"{fmt_time(t)} --> {fmt_time(t + dur)}")
                srt_lines.append(text)
                srt_lines.append("")
                seq += 1
            t += dur
        (srt_dir / f"ch{ch_num:03d}.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"SRT files generated: {srt_dir}")


def fmt_time(s):
    h, m, sec, ms = int(s//3600), int(s%3600//60), int(s%60), int(s%1*1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


if __name__ == "__main__":
    process_all_chapters()
    generate_srt_files()
