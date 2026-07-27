"""
PromptRenderer — 纯英文槽位化Prompt组装器

将校准后的Shot数据组装为AI视频模型可执行的英文Prompt。
禁止中文长句直接进prompt。

槽位模板：
[SHOT SIZE], [CAMERA MOVE], [ANGLE],
[SUBJECT English], [VISIBLE ACTION English],
[KEY PROP if any], [LOCATION], [LIGHTING], [MOOD],
cinematic, 9:16, photorealistic, 4K
"""
from __future__ import annotations

from typing import Any


# 景别英文
SHOT_TYPE_EN = {
    "ECU": "extreme close-up",
    "CU": "close-up",
    "MCU": "medium close-up",
    "MS": "medium shot",
    "WS": "wide shot",
    "FS": "full shot",
    "EWS": "extreme wide shot",
}

# 运镜英文
CAMERA_MOVE_EN = {
    "static": "static camera",
    "push": "slow dolly forward",
    "pull": "slow dolly backward",
    "handheld": "handheld camera with slight shake",
    "pan": "horizontal pan",
    "tracking": "tracking shot",
    "rapid_push": "rapid push-in",
}

# 视角英文
ANGLE_EN = {
    "eye-level": "eye level",
    "low": "low angle looking up",
    "high": "high angle looking down",
    "Dutch": "Dutch angle",
    "overhead": "overhead top-down",
}

# 光影英文
LIGHTING_EN = {
    "Natural": "natural daylight, soft shadows",
    "Warm": "warm golden light, soft amber tones",
    "Low key": "low key lighting, deep shadows, dim atmosphere",
    "High contrast": "high contrast dramatic lighting, harsh shadows",
    "Moonlight": "cold blue moonlight, silver tones",
    "Neon": "neon lights, colorful glow",
}

# 情绪英文
MOOD_EN = {
    "震惊": "shocked, high tension",
    "紧张": "tense, suspenseful",
    "暧昧": "romantic, intimate",
    "悬疑": "mysterious, intriguing",
    "悲伤": "sad, melancholic",
    "愤怒": "angry, intense",
    "日常": "calm, everyday",
    "中性": "neutral, observational",
    "Neutral": "neutral, observational",
    "Shock": "shocked, dramatic",
    "Tension": "tense, suspenseful",
    "Sadness": "sad, melancholic",
    "Warmth": "warm, heartwarming",
}

import re as _re


# 常见中文动作→英文翻译词典
ACTION_ZH_EN = {
    "擦拭": "wipes", "擦着": "wipes", "擦": "wipes",
    "走进": "walks in", "走进来": "walks in", "走入": "walks into",
    "坐下": "sits down", "坐到": "sits at", "坐在": "sits at",
    "端起": "picks up", "端着": "holds", "放下": "puts down",
    "闭眼": "closes eyes", "闭上眼": "closes eyes", "闭上眼睛": "closes eyes",
    "睁开眼": "opens eyes", "猛地睁开": "eyes snap open",
    "喝了一口": "takes a sip", "喝": "drinks",
    "转身": "turns around", "转头": "turns head",
    "低头": "looks down", "抬头": "looks up",
    "打字": "types on phone", "打瞌睡": "dozes off",
    "磨豆": "grinds beans", "磨": "grinds",
    "敲击": "taps", "敲": "knocks",
    "消失": "disappears", "离开": "leaves",
    "注意到": "notices", "看到": "sees", "看向": "looks at",
    "站起": "stands up", "站起来": "stands up",
    "扫码": "scans QR code", "付款": "pays",
    "冲洗": "rinses", "冲掉": "rinses off",
    "擦干": "dries", "看了看": "glances at",
    "翻了个身": "turns over", "翻身": "turns over",
    "打盹": "naps", "皱眉": "frowns",
    "攥紧": "clenches", "发抖": "trembles",
    "微笑": "smiles", "点头": "nods",
    "掏出": "takes out", "掏出手机": "pulls out phone",
    "放桌上": "places on table", "放在": "places on",
    "留着": "lingers", "留下": "leaves behind",
    "冒热气": "steaming", "烫手": "hot to touch",
    "旋转门": "revolving door", "玻璃幕墙": "glass curtain wall",
    "水龙头": "faucet", "水池": "sink",
    "口红印": "lipstick mark", "唇印": "lipstick mark",
    "疤痕": "scar", "印痕": "mark", "墨渍": "ink stain",
    "围裙": "apron", "西装": "suit",
    "老大爷": "old man", "女孩": "girl",
    "男人": "man", "女人": "woman",
    "咖啡店": "coffee shop", "咖啡": "coffee",
    "美式": "americano", "红茶": "black tea",
    "吧台": "counter", "桌子": "table",
    "写字楼": "office building",
    "左手": "left hand", "右手": "right hand",
    "无名指": "ring finger", "食指": "index finger",
    "中指": "middle finger",
    "声音消失": "all sounds fade", "声音恢复": "sounds return",
    "世界安静": "world goes silent", "安静": "quiet",
    "脑海": "mind", "浮现": "surfaces",
    "想不起来": "cannot recall", "记得": "remembers",
    "记得那个声音": "remembers that voice",
    "热牛奶": "hot milk",
    "灰色西装": "grey suit",
    "齐肩短发": "shoulder-length hair",
    "银框眼镜": "silver-framed glasses",
    "马尾辫": "ponytail",
    "彩色指甲": "colorful nails",
    "方脸": "square jaw", "短发": "short hair",
    "念想": "Nianxiang",
    "苏念": "Su Nian", "顾深": "Gu Shen",
    "林可": "Lin Ke", "陈锐": "Chen Rui",
}


class PromptRenderer:
    """
    纯英文槽位化Prompt组装器。
    
    输入：校准后的Shot数据（字典）
    输出：纯英文Veo prompt字符串
    """

    def __init__(self, character_tags: dict[str, str] | None = None):
        """
        Args:
            character_tags: 角色英文描述标签
                {"苏念": "young Chinese woman, 20s, barista, plain apron", ...}
        """
        self.character_tags = character_tags or {}

    def render(self, shot_data: dict) -> str:
        """
        渲染单个镜头的Veo prompt。
        
        Args:
            shot_data: 校准后的Shot数据，包含：
                - shot_type: str (CU/MCU/MS/WS)
                - camera_movement: str (static/push/pull/handheld)
                - camera_angle: str (eye-level/low/high)
                - lighting: str (Natural/Warm/Low key)
                - emotion: str
                - characters: list[str]
                - action_visual: str (英文或待翻译的中文)
                - dialogue: str
                - location: str
                - visual_anchors: list[str]
                
        Returns:
            纯英文Veo prompt字符串
        """
        parts = []

        # 1. Camera spec
        shot_type = shot_data.get("shot_type", "MS")
        camera_move = shot_data.get("camera_movement", "static")
        angle = shot_data.get("camera_angle", "eye-level")

        shot_en = SHOT_TYPE_EN.get(shot_type, "medium shot")
        camera_en = CAMERA_MOVE_EN.get(camera_move, "static camera")
        angle_en = ANGLE_EN.get(angle, "eye level")

        parts.append(f"{shot_en}, {camera_en}, {angle_en}")

        # 2. Subject (characters with physical tags)
        characters = shot_data.get("characters", [])
        if characters:
            char_parts = []
            for char_name in characters:
                tag = self.character_tags.get(char_name, "")
                if tag:
                    char_parts.append(f"{char_name} ({tag})")
                else:
                    char_parts.append(char_name)
            parts.append(f"featuring {', '.join(char_parts)}")

        # 3. Visible action (must be English, filmable)
        action = shot_data.get("action_visual", "")
        if action:
            # 如果含中文，翻译为英文
            if _re.search(r'[\u4e00-\u9fff]', action):
                action = self._translate_action(action)
            parts.append(action)

        # 4. Visual anchors
        anchors = shot_data.get("visual_anchors", [])
        if anchors:
            anchor_desc = ", ".join(anchors)
            parts.append(f"close-up detail on {anchor_desc}")

        # 5. Location
        location = shot_data.get("location_en", "") or shot_data.get("location", "")
        if location:
            parts.append(f"in {location}")

        # 6. Lighting
        lighting = shot_data.get("lighting", "Natural")
        lighting_en = LIGHTING_EN.get(lighting, "natural daylight, soft shadows")
        parts.append(lighting_en)

        # 7. Mood
        emotion = shot_data.get("emotion", "中性")
        mood_en = MOOD_EN.get(emotion, "neutral, observational")
        parts.append(mood_en)

        # 8. Tech specs
        parts.append("cinematic, 9:16 vertical, photorealistic, 4K")

        return ", ".join(parts)

    def render_with_dialogue(self, shot_data: dict) -> dict:
        """
        渲染带分离对话的prompt。
        
        Returns:
            {
                "veo_prompt": "...",  # 纯视觉prompt
                "dialogue_line": "...",  # 台词（如有）
                "inner_voice": "...",  # 心声（如有）
            }
        """
        veo_prompt = self.render(shot_data)

        return {
            "veo_prompt": veo_prompt,
            "dialogue_line": shot_data.get("dialogue", ""),
            "inner_voice": shot_data.get("inner_voice", ""),
        }

    def _translate_action(self, text: str) -> str:
        """将中文action翻译为英文（词典替换+兜底）"""
        result = text
        # 按长度降序替换（先替换长短语）
        for zh, en in sorted(ACTION_ZH_EN.items(), key=lambda x: -len(x[0])):
            result = result.replace(zh, en)
        # 如果还有中文残留，用通用规则处理
        if _re.search(r'[\u4e00-\u9fff]', result):
            # 去掉残留中文标点和无意义词
            result = _re.sub(r'[，。！？、；：""''（）\[\]【】]', ' ', result)
            # 去掉单个残留中文字符（通常是虚词）
            result = _re.sub(r'[\u4e00-\u9fff]{1,2}(?=[^[\u4e00-\u9fff])', '', result)
            result = _re.sub(r'(?<=[^\u4e00-\u9fff])[\u4e00-\u9fff]{1,2}', '', result)
            # 清理多余空格
            result = _re.sub(r'\s+', ' ', result).strip()
        return result if result else "character performs action"

    def format_shot_block(self, shot_data: dict) -> str:
        """
        格式化为可读的镜头描述块（用于调试/审查）。
        """
        shot_id = shot_data.get("shot_id", "?")
        pacing = shot_data.get("pacing_label", "")
        duration = shot_data.get("duration", 0)
        shot_type = shot_data.get("shot_type", "MS")
        camera = shot_data.get("camera_movement", "static")
        location = shot_data.get("location_en", "") or shot_data.get("location", "")
        characters = shot_data.get("characters", [])
        action = shot_data.get("action_visual", "")
        dialogue = shot_data.get("dialogue", "")
        anchors = shot_data.get("visual_anchors", [])

        lines = [f"## Shot {shot_id} | {pacing} ({duration}s)"]
        lines.append(f"- Camera: [{shot_type}] [{camera}]")
        lines.append(f"- Location: {location}")
        lines.append(f"- Characters: {', '.join(characters) if characters else 'none'}")
        lines.append(f"- Action: {action}")
        if dialogue:
            lines.append(f"- Dialogue: {dialogue}")
        if anchors:
            lines.append(f"- Anchors: {', '.join(anchors)}")
        lines.append(f"- Veo: {self.render(shot_data)[:120]}...")

        return "\n".join(lines)
