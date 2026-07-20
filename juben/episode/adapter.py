"""
Episode Adapter — 章节→单集适配器

将长章节拆分为60-120秒的短剧单集。
核心逻辑：读取章节文本 → 按节奏卡点切割 → 生成Episode结构。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .schema import (
    Cliffhanger,
    Episode,
    PacingCheckpoint,
    PacingLabel,
    Shot,
    ShotType,
    CameraMovement,
)
from .rhythm import RhythmValidator

logger = logging.getLogger(__name__)

# 物理动作关键词（用于死帧检测和卡点校验）
PHYSICAL_ACTIONS = {
    "掏出", "打翻", "推", "拉", "握", "砸", "转身", "跪", "站", "走", "跑",
    "颤抖", "瞳孔收缩", "泼", "摔", "踢", "扇", "掐", "按", "拔", "抽出",
    "冲", "扑", "跌", "爬", "跳", "闪", "躲", "挡", "砍", "刺", "射",
    "抓", "扔", "丢", "捡", "撕", "拆", "关", "开", "举", "放",
    "tremble", "slam", "push", "pull", "grab", "throw", "fall", "run",
    "stand", "kneel", "turn", "reach", "hold", "drop", "break", "shatter",
}

# 非物理动作（镜头拍不出来的抽象心理）
NON_PHYSICAL = {
    "感到", "觉得", "认为", "意识到", "明白", "知道", "理解",
    "心中暗想", "不禁感叹", "突然意识到", "内心", "暗自",
    "feel", "think", "realize", "understand", "know",
}


class EpisodeAdapter:
    """章节→单集适配器"""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.validator = RhythmValidator()

    def adapt_chapter(
        self,
        chapter_text: str,
        chapter_num: int,
        target_duration: int = 90,
        characters: list[dict] | None = None,
    ) -> Episode:
        """
        将章节文本适配为短剧单集。

        Args:
            chapter_text: 章节纯文本
            chapter_num: 章节编号
            target_duration: 目标时长（秒），默认90
            characters: 角色列表（用于视觉一致性）

        Returns:
            Episode 对象
        """
        # 1. 按段落切割
        paragraphs = self._split_paragraphs(chapter_text)
        total_chars = sum(len(p) for p in paragraphs)

        # 2. 按节奏卡点分配段落到卡点
        checkpoints = self._assign_checkpoints(paragraphs, target_duration)

        # 3. 生成镜头清单
        shots = self._generate_shots(paragraphs, checkpoints, characters)

        # 4. 提取断崖钩子
        cliffhanger = self._extract_cliffhanger(paragraphs)

        # 5. 生成视觉一致性描述
        visual_consistency = self._build_visual_consistency(characters or [])

        # 6. 组装Episode
        episode = Episode(
            episode_number=chapter_num,
            duration_estimate_seconds=target_duration,
            word_count_estimate=total_chars,
            pacing_checkpoints=checkpoints,
            shots=shots,
            cliffhanger=cliffhanger,
            visual_consistency=visual_consistency,
            hook_density=self._estimate_hook_density(paragraphs),
            scene_count=max(1, len(shots)),
            characters_involved=[c.get("name", "") for c in (characters or [])],
            script_text=chapter_text,
            shot_prompts=[{"shot_id": s.shot_id, "prompt": s.to_visual_prompt()} for s in shots],
        )

        # 7. 双轴校验
        result = self.validator.validate_episode(episode)
        if not result.passed:
            logger.warning(
                f"Episode {chapter_num} rhythm check failed: "
                f"{len(result.violations)} violations, score={result.score}"
            )

        return episode

    def _split_paragraphs(self, text: str) -> list[str]:
        """按段落切割，过滤空行"""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        return [p.strip() for p in paragraphs if p.strip()]

    def _assign_checkpoints(
        self,
        paragraphs: list[str],
        target_duration: int,
    ) -> list[PacingCheckpoint]:
        """按节奏卡点分配段落"""
        checkpoints = []
        char_offset = 0

        for para in paragraphs:
            para_len = len(para)

            # 判断这个段落应该属于哪个卡点
            label = self._infer_checkpoint(char_offset, para, target_duration)

            # 计算时间轴（按字数比例）
            time_ratio = char_offset / max(1, sum(len(p) for p in paragraphs))
            time_start = time_ratio * target_duration
            time_end = (char_offset + para_len) / max(1, sum(len(p) for p in paragraphs)) * target_duration

            checkpoints.append(PacingCheckpoint(
                label=label,
                word_range=[char_offset, char_offset + para_len],
                time_range=[round(time_start, 1), round(time_end, 1)],
                rule=self._get_rule_for_label(label),
                visual_action=self._extract_action(para),
                dialogue=self._extract_dialogue(para),
                emotion=self._infer_emotion(para),
                passed=True,
            ))

            char_offset += para_len

        return checkpoints

    def _infer_checkpoint(self, char_offset: int, para: str, target_duration: int) -> PacingLabel:
        """根据字数位置和内容推断属于哪个卡点"""
        # 前100字 → 3s_Hook
        if char_offset < 100:
            return PacingLabel.HOOK_3S
        # 300-500字 → 15s_Retention
        elif char_offset < 500:
            return PacingLabel.RETENTION_15S
        # 600-800字 → 30s_Explosion
        elif char_offset < 800:
            return PacingLabel.EXPLOSION_30S
        # 1000-1200字 → 60s_Satisfaction
        elif char_offset < 1200:
            return PacingLabel.SATISFACTION_60S
        # 1700+字 → 90s_Cliffhanger
        else:
            return PacingLabel.CLIFFHANGER_90S

    def _get_rule_for_label(self, label: PacingLabel) -> str:
        """获取卡点规则描述"""
        rules = {
            PacingLabel.HOOK_3S: "动词+特写开局。必须出现感官冲击",
            PacingLabel.RETENTION_15S: "爆出核心信息差",
            PacingLabel.EXPLOSION_30S: "视觉/物理冲击，必须有物理位移",
            PacingLabel.SATISFACTION_60S: "小赢——主角获得一个小胜利",
            PacingLabel.CLIFFHANGER_90S: "断崖钩子，植入未回答问题",
        }
        return rules.get(label, "")

    def _extract_action(self, para: str) -> str:
        """从段落中提取物理动作"""
        for word in PHYSICAL_ACTIONS:
            if word in para:
                # 返回包含该动作的句子
                for sent in re.split(r'[。！？\.\!\?]', para):
                    if word in sent:
                        return sent.strip()[:100]
        return ""

    def _extract_dialogue(self, para: str) -> str:
        """提取台词"""
        # 匹配引号内的对话
        matches = re.findall(r'["「](.*?)["」]', para)
        return matches[0] if matches else ""

    def _infer_emotion(self, para: str) -> str:
        """推断情绪标签"""
        emotion_keywords = {
            "愤怒": ["怒", "恨", "咬牙", "瞪", "摔", "砸"],
            "恐惧": ["怕", "抖", "颤", "冷汗", "退", "逃"],
            "震惊": ["愣", "呆", "不敢相信", "瞳孔", "惊"],
            "悲伤": ["哭", "泪", "痛", "苦", "伤"],
            "爽感": ["笑", "赢", "碾压", "打脸", "跪"],
            "悬念": ["？", "难道", "究竟", "秘密", "真相"],
        }
        for emotion, keywords in emotion_keywords.items():
            for kw in keywords:
                if kw in para:
                    return emotion
        return "中性"

    def _extract_cliffhanger(self, paragraphs: list[str]) -> Cliffhanger:
        """提取断崖钩子"""
        if not paragraphs:
            return Cliffhanger()

        last_para = paragraphs[-1]

        # 检测钩子类型
        if "？" in last_para or "?" in last_para:
            return Cliffhanger(
                type="question",
                line=last_para[-200:],
                unanswered_question=last_para.split("？")[-2] + "？" if "？" in last_para else "",
            )
        elif any(w in last_para for w in ["突然", "忽然", "猛地", "瞬间"]):
            return Cliffhanger(
                type="shock",
                line=last_para[-200:],
                unanswered_question="接下来会发生什么？",
            )
        else:
            return Cliffhanger(
                type="reveal",
                line=last_para[-200:],
                unanswered_question="这个发现意味着什么？",
            )

    def _build_visual_consistency(self, characters: list[dict]) -> list:
        """构建视觉一致性描述"""
        from .schema import VisualConsistency
        result = []
        for char in characters:
            result.append(VisualConsistency(
                character_name=char.get("name", ""),
                appearance=char.get("appearance", {}).get("description", ""),
                default_attire=char.get("appearance", {}).get("attire", ""),
                voice_tone=char.get("voice", ""),
            ))
        return result

    def _estimate_hook_density(self, paragraphs: list[str]) -> str:
        """估算钩子密度"""
        hook_count = 0
        for para in paragraphs:
            if any(w in para for w in ["突然", "忽然", "？", "!", "真相", "秘密"]):
                hook_count += 1
        ratio = hook_count / max(1, len(paragraphs))
        if ratio > 0.3:
            return "high"
        elif ratio > 0.15:
            return "medium"
        return "low"

    def _generate_shots(
        self,
        paragraphs: list[str],
        checkpoints: list[PacingCheckpoint],
        characters: list[dict] | None,
    ) -> list[Shot]:
        """
        根据段落和卡点生成镜头清单。
        每个卡点对应1-2个镜头。
        """
        shots = []
        shot_id = 1

        for cp in checkpoints:
            # 根据卡点类型选择景别
            shot_type = self._infer_shot_type(cp)
            camera_move = self._infer_camera_movement(cp)

            # 提取主体描述
            subject = self._build_subject_description(cp, characters)

            shot = Shot(
                shot_id=shot_id,
                shot_type=shot_type,
                camera_movement=camera_move,
                duration=self._estimate_shot_duration(cp),
                subject=subject,
                action=cp.visual_action or "",
                setting="",  # 由Scribe prompt填充
                lighting="",  # 由Scribe prompt填充
                mood=cp.emotion or "",
                emotion_tag=cp.emotion or "",
                pacing_label=cp.label.value if hasattr(cp.label, 'value') else cp.label,
                word_range=cp.word_range,
            )
            shots.append(shot)
            shot_id += 1

        return shots

    def _infer_shot_type(self, cp: PacingCheckpoint) -> ShotType:
        """根据卡点类型推断景别"""
        label = cp.label.value if hasattr(cp.label, 'value') else cp.label
        mapping = {
            "3s_Hook": ShotType.CU,         # 特写开局
            "15s_Retention": ShotType.MCU,   # 近景：表情+台词
            "30s_Explosion": ShotType.MS,    # 中景：动作+环境
            "60s_Satisfaction": ShotType.MCU, # 近景：主角反应
            "90s_Cliffhanger": ShotType.CU,  # 特写：悬念表情
        }
        return mapping.get(label, ShotType.MS)

    def _infer_camera_movement(self, cp: PacingCheckpoint) -> CameraMovement:
        """根据卡点类型推断运镜"""
        label = cp.label.value if hasattr(cp.label, 'value') else cp.label
        mapping = {
            "3s_Hook": CameraMovement.STATIC,       # 静止特写
            "15s_Retention": CameraMovement.PUSH,    # 缓推：聚焦信息
            "30s_Explosion": CameraMovement.HANDHELD, # 手持：冲击感
            "60s_Satisfaction": CameraMovement.PULL,  # 拉：展现全貌
            "90s_Cliffhanger": CameraMovement.PUSH,   # 急推：悬念
        }
        return mapping.get(label, CameraMovement.STATIC)

    def _estimate_shot_duration(self, cp: PacingCheckpoint) -> float:
        """估算镜头时长"""
        if cp.time_range and len(cp.time_range) >= 2:
            return round(cp.time_range[1] - cp.time_range[0], 1)
        return 3.0

    def _build_subject_description(
        self,
        cp: PacingCheckpoint,
        characters: list[dict] | None,
    ) -> str:
        """构建主体描述（角色外貌+服装）"""
        if not characters:
            return ""
        # 默认用第一个角色（通常是主角）
        char = characters[0]
        name = char.get("name", "")
        appearance = char.get("appearance", {})
        desc_parts = []
        if name:
            desc_parts.append(f"a young woman named {name}")
        if appearance.get("age"):
            desc_parts.append(f"age {appearance['age']}")
        if appearance.get("attire"):
            desc_parts.append(appearance["attire"])
        return ", ".join(desc_parts) if desc_parts else ""
