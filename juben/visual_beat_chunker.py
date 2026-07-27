"""
Visual Beat Chunker — Micro-LLM视觉切片器

用一次LLM调用把整章文本切成10-20个Visual Beat。
LLM负责理解，Python负责计算。

输入：整章文本（≤2000字）
输出：结构化VisualBeat数组（JSON）
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

# 切片Prompt — 强制英文输出，严格JSON
CHUNK_PROMPT = """You are a storyboard beat extractor for vertical short drama (9:16, Veo video generation).

CRITICAL RULES:
- ALL text fields (action_visual, spoken_dialogue, inner_voice) MUST be in ENGLISH. No Chinese characters anywhere.
- action_visual: ONLY physical, filmable actions. No thoughts, no feelings, no abstract concepts.
- Use character real names (e.g. "Su Nian" not "she"). Always resolve pronouns to names.
- spoken_dialogue = words spoken OUT LOUD. inner_voice = mind reading / voice-over / monologue. NEVER mix them.
- focus_object = specific physical prop visible in close-up (cup, scar, phone, etc.)

Split the script into 10-20 Visual Beats. Each beat = one camera shot.

Cut when: camera angle changes, time jumps, space changes (Physical->Mental), speaker changes, or major physical action completes.
Do NOT cut mid-action (e.g. "picks up cup, drinks" is ONE beat).
DO cut at: ability activation (mind reading), trace changes (scar appearing), speaker switches, scene transitions.

Space types:
- "Physical": real world visible action
- "Mental": mind reading, visions, flashbacks, supernatural perception
- "Transition": crossing between real and mental (e.g. closing eyes to activate ability)

Emotions: Neutral, Tension, Shock, Sadness, Warmth, Mystery

Script:
{text}

Known characters: {characters}

Return ONLY valid JSON, no markdown, no explanation. Start with {{ and end with }}:
{{
  "beats": [
    {{
      "beat_id": 1,
      "space": "Physical",
      "characters_present": ["Su Nian"],
      "action_visual": "Su Nian wipes the coffee shop counter with a rag, glancing at the door for the third time",
      "spoken_dialogue": "",
      "inner_voice": "",
      "focus_object": "",
      "emotion": "Neutral"
    }}
  ]
}}"""


class VisualBeatChunker:
    """
    用LLM把整章文本切成Visual Beat数组。

    无LLM时用规则兜底（质量下降但不崩溃）。
    """

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        characters: list[dict] | None = None,
    ):
        self.llm_fn = llm_fn
        self.char_names = [c.get("name", "") for c in (characters or []) if c.get("name")]

    def chunk(self, chapter_text: str) -> list[dict]:
        """
        切分整章文本为Visual Beat数组。

        Returns:
            [{"beat_id": 1, "space": "Physical", "characters_present": [...],
              "action_visual": "...", "spoken_dialogue": "...", "inner_voice": "...",
              "focus_object": "...", "emotion": "..."}, ...]
        """
        if self.llm_fn:
            return self._chunk_with_llm(chapter_text)
        else:
            return self._chunk_with_rules(chapter_text)

    def _chunk_with_llm(self, text: str) -> list[dict]:
        """用LLM切分（带重试和fallback）"""
        prompt = CHUNK_PROMPT.format(
            text=text[:3000],
            characters=", ".join(self.char_names) if self.char_names else "unknown",
        )

        # 第一次尝试
        try:
            response = self.llm_fn(prompt)
            beats = self._parse_response(response)
            if beats and len(beats) >= 3:
                return beats
        except Exception as e:
            logger.warning(f"LLM attempt 1 failed: {e}")

        # 第二次尝试（更简短的prompt，强调JSON only）
        try:
            retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY the JSON object. No explanation, no markdown, no extra text. Start with { and end with }."
            response = self.llm_fn(retry_prompt)
            beats = self._parse_response(response)
            if beats and len(beats) >= 3:
                return beats
        except Exception as e:
            logger.warning(f"LLM attempt 2 failed: {e}")

        # Fallback: 规则兜底
        logger.warning("LLM failed, falling back to rules")
        return self._chunk_with_rules(text)

    def _parse_response(self, response: str) -> list[dict]:
        """解析LLM的JSON响应（多级容错）"""
        # Level 1: 直接解析整个响应
        for attempt_text in [response]:
            # 尝试提取JSON块（支持```json...```包裹）
            json_patterns = [
                r'```json\s*\n?(\{.*?\})\s*\n?```',  # ```json...```
                r'```\s*\n?(\{.*?\})\s*\n?```',      # ```...```
                r'(\{[^{}]*"beats"[^{}]*\{.*?\}.*?\})', # 直接JSON with beats
                r'(\{.*"beats".*\})',                      # 宽松匹配
            ]

            for pattern in json_patterns:
                match = re.search(pattern, attempt_text, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1) if match.lastindex else match.group())
                        beats = data.get("beats", [])
                        if beats and len(beats) >= 3:  # 至少3个beat才算有效
                            return self._validate_beats(beats)
                    except json.JSONDecodeError:
                        continue

        # Level 2: 尝试从响应中手动提取beat数组
        beat_pattern = re.findall(r'"beat_id"\s*:\s*(\d+)', response)
        if len(beat_pattern) >= 3:
            # 有beat_id字段，尝试逐个提取
            try:
                # 找到beats数组的开始和结束
                start = response.find('"beats"')
                if start > 0:
                    bracket_start = response.find('[', start)
                    bracket_end = response.rfind(']')
                    if bracket_start > 0 and bracket_end > bracket_start:
                        beats_json = response[bracket_start:bracket_end+1]
                        beats = json.loads(beats_json)
                        return self._validate_beats(beats)
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning("Failed to parse LLM response as JSON")
        return []

    def _validate_beats(self, beats: list) -> list[dict]:
        """验证并规范化beat数据"""
        validated = []
        for i, beat in enumerate(beats):
            if isinstance(beat, dict):
                validated.append({
                    "beat_id": beat.get("beat_id", i + 1),
                    "space": beat.get("space", "Physical"),
                    "characters_present": beat.get("characters_present", []),
                    "action_visual": beat.get("action_visual", ""),
                    "spoken_dialogue": beat.get("spoken_dialogue", ""),
                    "inner_voice": beat.get("inner_voice", ""),
                    "focus_object": beat.get("focus_object", ""),
                    "emotion": beat.get("emotion", "Neutral"),
                })
        return validated

    def _chunk_with_rules(self, text: str) -> list[dict]:
        """
        规则兜底（无LLM时使用）。
        比v2更智能：按段落切分，但识别能力事件和空间切换。
        """
        paragraphs = [p.strip() for p in text.split('\n') if p.strip() and not p.strip().startswith('#')]

        if not paragraphs:
            return []

        beats = []
        beat_id = 1

        # 能力/空间切换关键词
        ability_kw = ["端起", "闭眼", "闭上眼", "世界安静", "声音消失", "听到", "睁开眼", "放下杯子"]
        mental_kw = ["想不起来", "记不清", "模糊", "印痕", "疤痕", "字迹", "便签", "闪回"]
        speaker_change_pattern = re.compile(r'(\w{2,4})(?:说|道|问|答)')

        prev_speaker = ""
        current_group = []

        for para in paragraphs:
            # 检测是否需要切分
            should_cut = False
            space = "Physical"

            # 能力事件 → 必须切分，标记为Mental
            if any(kw in para for kw in ability_kw):
                if current_group:
                    beats.append(self._make_beat(beat_id, current_group, "Physical", prev_speaker))
                    beat_id += 1
                    current_group = []
                should_cut = True
                space = "Mental"

            # 痕迹变化 → 必须切分
            elif any(kw in para for kw in mental_kw):
                should_cut = True

            # 说话人切换
            speaker_match = speaker_change_pattern.search(para)
            if speaker_match:
                speaker = speaker_match.group(1)
                if speaker != prev_speaker and prev_speaker:
                    should_cut = True
                prev_speaker = speaker

            # 对话→叙述切换
            has_dialogue = bool(re.search(r'["「]', para))
            if current_group:
                prev_has_dialogue = bool(re.search(r'["「]', current_group[-1]))
                if prev_has_dialogue and not has_dialogue:
                    should_cut = True

            if should_cut and current_group:
                beats.append(self._make_beat(beat_id, current_group, "Physical", prev_speaker))
                beat_id += 1
                current_group = []

            current_group.append(para)

        # 最后一组
        if current_group:
            beats.append(self._make_beat(beat_id, current_group, "Physical", prev_speaker))

        return beats

    def _make_beat(self, beat_id: int, paragraphs: list[str], space: str, speaker: str) -> dict:
        """构建单个beat"""
        text = "\n\n".join(paragraphs)

        # 提取对话
        dialogues = re.findall(r'["「]([^"」]+)["」]', text)
        sound_pattern = re.compile(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$')
        dialogues = [d for d in dialogues if len(d) > 2 and not sound_pattern.match(d)]

        # 提取心声（带*号的）
        inner = re.findall(r'\*["「]([^"」]+)["」]\*', text)

        # 提取图腾
        anchors = []
        anchor_kw = ["唇印", "口红印", "疤痕", "便签", "字迹", "钥匙", "杯沿", "手背", "左手", "无名指", "印痕", "墨渍"]
        for kw in anchor_kw:
            if kw in text:
                anchors.append(kw)

        # 提取可拍动作（取最长的有具体道具的句子）
        action = self._extract_action(text)

        # 检测空间类型
        if any(kw in text for kw in ["世界安静", "声音消失", "脑海", "浮现", "画面闪过"]):
            space = "Mental"
        elif any(kw in text for kw in ["想不起来", "印痕", "疤痕淡"]):
            space = "Transition"

        # 推断情绪
        emotion = "Neutral"
        if any(kw in text for kw in ["猛地", "突然", "瞳孔", "愣住"]):
            emotion = "Shock"
        elif any(kw in text for kw in ["攥紧", "心跳", "发抖", "紧张"]):
            emotion = "Tension"
        elif any(kw in text for kw in ["泪", "哭", "痛", "冷"]):
            emotion = "Sadness"
        elif any(kw in text for kw in ["微笑", "温暖"]):
            emotion = "Warmth"
        elif any(kw in text for kw in ["消失", "淡了", "模糊", "听不清"]):
            emotion = "Mystery"

        # 提取在场角色（宽松匹配）
        chars = []
        char_names = self.char_names
        for name in char_names:
            # 宽松：只要名字出现在文本中（不限于动作主语）
            if name in text:
                chars.append(name)

        return {
            "beat_id": beat_id,
            "space": space,
            "characters_present": chars,
            "action_visual": action,
            "spoken_dialogue": dialogues[0] if dialogues else "",
            "inner_voice": inner[0] if inner else "",
            "focus_object": anchors[0] if anchors else "",
            "emotion": emotion,
        }

    @staticmethod
    def _extract_action(text: str) -> str:
        """提取可拍动作"""
        abstract = {"语速", "语气", "心想", "觉得", "感到", "认为", "意识到", "明白", "知道", "像在", "像是"}
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 8]

        # 优先取有具体道具的
        concrete = {"手", "眼", "杯", "灯", "门", "钥匙", "手机", "筷子", "茶", "纸巾", "便签", "疤痕", "口红"}
        for sent in sentences:
            if any(a in sent for a in abstract):
                continue
            if any(c in sent for c in concrete):
                return sent[:50]

        # 兜底
        for sent in sentences:
            if not any(a in sent for a in abstract):
                return sent[:50]

        return text[:40]
