"""
SemanticCalibrator — Micro-LLM语义校准器

在规则草稿之后，用小LLM校准语义问题：
1. 角色归属：谁实际在画面里（不是提到的人）
2. 地点锁定：实际物理发生地
3. 三分类：台词 / 心声 / 旁白
4. 可拍动作：抽象描述→物理可拍
5. 图腾检测：哪些物理道具出镜

设计原则：
- 只做校准，不做创作
- 每次输入≤150字的单个beat
- 输出严格JSON
- 无LLM时用规则兜底（不崩溃）
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Micro-LLM prompt模板（每个beat一次调用，~300token）
CALIBRATION_PROMPT = """你是短剧分镜的语义校准器。请从以下文本中提取结构化事实。

## 原文
{text}

## 已知角色
{characters}

## 已知位置
{location}

## 输出JSON（严格遵守）
```json
{{
  "characters_present": ["实际物理在场的角色名，不包括只被提到的人"],
  "location": "实际物理发生地",
  "spoken_dialogue": "角色张嘴说出的台词（若无则为空字符串）",
  "inner_voice": "读心/心声/旁白（若无则为空字符串）",
  "action_visual": "客观物理动作描述（英文，15-40词，摄像机能拍到的画面）",
  "emotion": "情绪基调（Shock/Tension/Sadness/Warmth/Neutral）",
  "visual_anchors": ["当前出现的具体物理道具"]
}}
```

规则：
- characters_present 只包含实际出镜的人，不包括台词里提到的人
- spoken_dialogue 是张嘴说的话，inner_voice 是读心/旁白，必须分开
- action_visual 必须是摄像机能拍到的物理动作，禁止心理描写
- 如果有读心场景，action_visual 应描述"闭眼""杯壁""手部特写"等可拍画面
"""


class SemanticCalibrator:
    """
    语义校准器。
    
    用法：
        calibrator = SemanticCalibrator(llm_fn=my_llm_function)
        calibrated = calibrator.calibrate_beat(beat_text, known_chars, known_location)
    """

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        characters: list[dict] | None = None,
    ):
        """
        Args:
            llm_fn: LLM调用函数，签名 fn(prompt) -> str
                    None则用规则兜底
            characters: 角色列表 [{"name": "苏念", ...}, ...]
        """
        self.llm_fn = llm_fn
        self.char_names = [c.get("name", "") for c in (characters or []) if c.get("name")]

    def calibrate_beat(
        self,
        beat_text: str,
        scene_location: str = "",
    ) -> dict:
        """
        校准单个Beat。
        
        Args:
            beat_text: Beat文本（≤150字）
            scene_location: 场景级位置（从SceneExtractor继承）
            
        Returns:
            校准后的结构化数据
        """
        if self.llm_fn:
            return self._calibrate_with_llm(beat_text, scene_location)
        else:
            return self._calibrate_with_rules(beat_text, scene_location)

    def _calibrate_with_llm(self, beat_text: str, scene_location: str) -> dict:
        """用LLM校准"""
        prompt = CALIBRATION_PROMPT.format(
            text=beat_text,
            characters=", ".join(self.char_names) if self.char_names else "未知",
            location=scene_location or "未标注",
        )

        try:
            response = self.llm_fn(prompt)
            return self._parse_llm_response(response, scene_location)
        except Exception as e:
            logger.warning(f"LLM calibration failed: {e}, falling back to rules")
            return self._calibrate_with_rules(beat_text, scene_location)

    def _parse_llm_response(self, response: str, fallback_location: str) -> dict:
        """解析LLM的JSON响应"""
        # 提取JSON
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                # 兜底location
                if not result.get("location"):
                    result["location"] = fallback_location
                return result
            except json.JSONDecodeError:
                pass

        # 解析失败，用规则兜底
        logger.warning("Failed to parse LLM response as JSON")
        return self._calibrate_with_rules(response, fallback_location)

    def _calibrate_with_rules(self, beat_text: str, scene_location: str) -> dict:
        """
        规则兜底校准（无LLM时使用）。
        
        比v2的纯正则更精确：
        - 只取动作句主语作为在场角色
        - 用引号位置区分台词和心声
        - 过滤抽象描述
        """
        # 1. 角色归属（只取动作句主语）
        characters_present = self._extract_present_characters(beat_text)

        # 2. 地点锁定（继承Scene）
        location = scene_location or "未标注"

        # 3. 三分类
        spoken, inner = self._classify_dialogue(beat_text)

        # 4. 可拍动作
        action_visual = self._extract_filmable_action(beat_text)

        # 5. 情绪
        emotion = self._infer_emotion(beat_text)

        # 6. 视觉图腾
        anchors = self._extract_anchors(beat_text)

        return {
            "characters_present": characters_present,
            "location": location,
            "spoken_dialogue": spoken,
            "inner_voice": inner,
            "action_visual": action_visual,
            "emotion": emotion,
            "visual_anchors": anchors,
        }

    def _extract_present_characters(self, text: str) -> list[str]:
        """
        提取实际在场角色（不包括只被提到的人）。
        
        规则：角色名必须是某个动作句的主语，不能只在台词/描述中出现。
        """
        present = []
        for name in self.char_names:
            # 检查角色名是否作为动作主语出现
            # 模式: "名字 + 动作" 或 "名字 + 的 + 身体部位"
            action_patterns = [
                rf'{re.escape(name)}(?:用|把|端|拿|走|站|坐|转|看|低头|抬头|闭|睁|攥|摸|掏|推|拉|按|敲|喝|吃|放)',
                rf'{re.escape(name)}的(?:手|眼|脸|头|嘴|唇|指|脚|背|肩)',
                rf'{re.escape(name)}(?:说|道|问|答|喊|叫|叹|笑|哭)',
            ]
            for pattern in action_patterns:
                if re.search(pattern, text):
                    present.append(name)
                    break

        return present

    def _classify_dialogue(self, text: str) -> tuple[str, str]:
        """
        三分类：台词 vs 心声。
        
        规则：
        - 带*号或（旁白/心声/内心）标记 → inner_voice
        - 普通引号对话 → spoken_dialogue
        - 引号内含"她像一个人"等第三人称描述 → inner_voice
        """
        spoken = []
        inner = []

        # 提取所有引号内容
        matches = re.findall(r'["\u300c]([^"\u300d]+)["\u300d]', text)

        for match in matches:
            # 检查是否是心声
            is_inner = False

            # 带*号标记
            if '*' in match or text.find(f'*"{match}"') >= 0:
                is_inner = True

            # 第三人称描述（"她像一个人"）
            if re.match(r'^她|他|它|这|那', match) and len(match) > 10:
                is_inner = True

            # 内容分析：如果包含"想到""感觉""回忆"等
            if any(kw in match for kw in ["想到", "感觉", "回忆", "印象", "像一个人"]):
                is_inner = True

            if is_inner:
                inner.append(match)
            else:
                spoken.append(match)

        # 过滤声效
        sound_pattern = re.compile(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$')
        spoken = [s for s in spoken if len(s) > 2 and not sound_pattern.match(s)]

        return (spoken[0] if spoken else ""), (inner[0] if inner else "")

    def _extract_filmable_action(self, text: str) -> str:
        """
        提取可拍摄的物理动作（过滤抽象描述）。
        
        规则：
        - 优先取有具体道具/身体部位的动作句
        - 过滤"语速""语气""心想""觉得"等抽象词
        - 控制在15-40字
        """
        abstract = {
            "语速", "语气", "心想", "觉得", "感到", "认为", "意识到",
            "明白", "知道", "理解", "暗想", "像在", "像是", "想起",
            "回忆", "记忆", "想不起来", "记不清", "震惊", "愤怒",
        }

        # 按句子切分
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

        # 优先找有具体道具的动作句
        concrete_kw = [
            "手", "眼", "杯", "灯", "门", "窗", "钥匙", "手机", "筷子",
            "碗", "茶", "纸巾", "便签", "疤痕", "口红", "水", "咖啡",
        ]

        for sent in sentences:
            if any(abs_kw in sent for abs_kw in abstract):
                continue
            if any(c_kw in sent for c_kw in concrete_kw):
                # 有具体道具
                if len(sent) > 50:
                    sent = sent[:50]
                return sent

        # 兜底：取第一个非抽象动作句
        for sent in sentences:
            if not any(abs_kw in sent for abs_kw in abstract):
                if len(sent) > 50:
                    sent = sent[:50]
                return sent

        return text[:40] if text else ""

    def _infer_emotion(self, text: str) -> str:
        """推断情绪"""
        signals = {
            "Shock": ["猛地", "突然", "瞳孔", "愣住", "不敢相信", "灭了", "闪了"],
            "Tension": ["攥紧", "心跳", "发抖", "冰凉", "紧张", "急促"],
            "Sadness": ["泪", "哭", "痛", "苦", "冷", "空荡荡"],
            "Warmth": ["微笑", "温暖", "柔", "轻", "缓缓"],
        }
        for emotion, keywords in signals.items():
            if any(kw in text for kw in keywords):
                return emotion
        return "Neutral"

    def _extract_anchors(self, text: str) -> list[str]:
        """提取视觉图腾"""
        anchor_keywords = [
            "唇印", "口红印", "疤痕", "便签", "字迹", "钥匙", "手机屏幕",
            "杯沿", "手背", "左手", "无名指", "猫", "拉花", "灯管", "茶水",
            "水珠", "墨渍", "印痕",
        ]
        return [kw for kw in anchor_keywords if kw in text]

    def calibrate_beats(self, beats: list[dict], scene_location: str = "") -> list[dict]:
        """
        批量校准多个Beat。
        
        Args:
            beats: Beat数据列表，每个包含 text, scene_index 等
            scene_location: 场景级位置
            
        Returns:
            校准后的数据列表
        """
        results = []
        for beat in beats:
            calibrated = self.calibrate_beat(
                beat.get("text", ""),
                scene_location,
            )
            # 合并原始数据
            calibrated["beat_id"] = beat.get("beat_id", 0)
            calibrated["scene_index"] = beat.get("scene_index", 0)
            calibrated["beat_type"] = beat.get("beat_type", "action")
            calibrated["raw_text"] = beat.get("text", "")
            results.append(calibrated)

        return results
