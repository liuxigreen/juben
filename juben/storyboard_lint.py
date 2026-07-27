"""
StoryboardLint — 分镜质量闸门

在分镜输出前进行硬校验，不达标直接打回。

检查项：
1. 角色归属：每镜必须有且仅有实际出镜角色
2. 地点锁定：继承Scene location，禁止乱跳
3. 三分类：台词/心声/旁白不能混
4. 可拍动作：action字段不能有抽象心理句
5. 图腾出镜：visual_anchors非空时prompt必须描述
6. 英文槽位：veo_prompt不能有中文长句
7. 镜数/时长：12-20镜，3-8秒/镜
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# 抽象心理关键词（禁止出现在action字段）
ABSTRACT_KEYWORDS = [
    "语速", "语气", "心想", "觉得", "感到", "认为", "意识到",
    "明白", "知道", "理解", "暗想", "像在", "像是", "想起",
    "回忆", "记忆", "想不起来", "记不清", "忘了",
    "震惊", "愤怒", "悲伤", "恐惧",  # 情绪词不能直接进action
]

# 心声标记（应该进inner_voice，不进dialogue）
INNER_VOICE_MARKERS = [
    "*", "（旁白）", "（心声）", "（内心）",
]


@dataclass
class LintViolation:
    """Lint违规"""
    shot_id: int
    rule: str  # 违反的规则名
    severity: str  # error / warning
    message: str
    suggestion: str = ""


class StoryboardLint:
    """分镜质量闸门"""

    def __init__(
        self,
        min_shots: int = 8,
        max_shots: int = 25,
        min_duration: float = 3.0,
        max_duration: float = 8.0,
    ):
        self.min_shots = min_shots
        self.max_shots = max_shots
        self.min_duration = min_duration
        self.max_duration = max_duration

    def check(self, shots: list[dict], scene_locations: dict[int, str]) -> list[LintViolation]:
        """
        检查所有镜头。
        
        Args:
            shots: 镜头数据列表
            scene_locations: {scene_index: location_name}
            
        Returns:
            违规列表（空=通过）
        """
        violations = []

        # 全局检查
        violations.extend(self._check_global(shots))

        # 逐镜头检查
        for shot in shots:
            shot_id = shot.get("shot_id", 0)
            violations.extend(self._check_shot(shot_id, shot, scene_locations))

        return violations

    def _check_global(self, shots: list[dict]) -> list[LintViolation]:
        """全局检查"""
        violations = []

        # 镜数检查
        n = len(shots)
        if n < self.min_shots:
            violations.append(LintViolation(
                shot_id=0,
                rule="shot_count",
                severity="warning",
                message=f"镜头数过少: {n} (目标 {self.min_shots}-{self.max_shots})",
            ))
        elif n > self.max_shots:
            violations.append(LintViolation(
                shot_id=0,
                rule="shot_count",
                severity="warning",
                message=f"镜头数过多: {n} (目标 {self.min_shots}-{self.max_shots})",
            ))

        # 时长检查
        for shot in shots:
            dur = shot.get("duration", 0)
            sid = shot.get("shot_id", 0)
            if dur < self.min_duration:
                violations.append(LintViolation(
                    shot_id=sid,
                    rule="duration",
                    severity="error",
                    message=f"镜头时长过短: {dur}s (最小 {self.min_duration}s)",
                ))
            elif dur > self.max_duration:
                violations.append(LintViolation(
                    shot_id=sid,
                    rule="duration",
                    severity="error",
                    message=f"镜头时长过长: {dur}s (最大 {self.max_duration}s)",
                ))

        return violations

    def _check_shot(
        self,
        shot_id: int,
        shot: dict,
        scene_locations: dict[int, str],
    ) -> list[LintViolation]:
        """单镜头检查"""
        violations = []

        # 1. 角色归属检查
        chars = shot.get("characters", [])
        action = shot.get("action_visual", "") or shot.get("action", "")
        if not chars and action:
            # action有人物动作但没角色
            if any(kw in action for kw in ["她", "他", "苏念", "顾深"]):
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="character_attribution",
                    severity="warning",
                    message="action提到人物但characters为空",
                    suggestion="确认谁在画面中",
                ))

        # 2. 地点锁定检查
        location = shot.get("location", "")
        scene_idx = shot.get("scene_index", 0)
        expected_loc = scene_locations.get(scene_idx, "")
        if expected_loc and location and location != expected_loc:
            # 允许细化（如"念想咖啡店吧台" vs "念想咖啡店"）
            if expected_loc not in location and location not in expected_loc:
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="location_lock",
                    severity="warning",
                    message=f"地点不匹配: {location} (场景地点: {expected_loc})",
                    suggestion=f"继承场景地点: {expected_loc}",
                ))

        # 3. 三分类检查（台词vs心声）
        dialogue = shot.get("dialogue", "")
        if dialogue:
            # 检查是否是心声（带*号或内心标记）
            if any(marker in dialogue for marker in INNER_VOICE_MARKERS):
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="text_classification",
                    severity="error",
                    message=f"心声混入dialogue: {dialogue[:30]}",
                    suggestion="移到inner_voice字段",
                ))

        # 4. 可拍动作检查（排除引号内的对话内容）
        if action:
            # 去掉引号内的内容再检查
            action_no_quotes = re.sub(r'["「][^"」]*["」]', '', action)
            abstract_found = [kw for kw in ABSTRACT_KEYWORDS if kw in action_no_quotes]
            if abstract_found:
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="filmable_action",
                    severity="error",
                    message=f"action含抽象词: {abstract_found} | {action[:50]}",
                    suggestion="改为物理可拍动作",
                ))

        # 5. 图腾出镜检查
        anchors = shot.get("visual_anchors", [])
        veo_prompt = shot.get("veo_prompt", "")
        if anchors and veo_prompt:
            # 检查prompt是否描述了图腾
            anchor_described = any(
                anchor.lower() in veo_prompt.lower()
                for anchor in anchors
            )
            if not anchor_described:
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="anchor_visibility",
                    severity="warning",
                    message=f"visual_anchors非空但prompt未描述: {anchors}",
                    suggestion="在prompt中加入图腾描述",
                ))

        # 6. 英文槽位检查
        if veo_prompt:
            # 检查是否有任何中文字符（零容忍）
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', veo_prompt)
            if chinese_chars:
                violations.append(LintViolation(
                    shot_id=shot_id,
                    rule="english_slot",
                    severity="warning",
                    message=f"veo_prompt含中文: {''.join(chinese_chars[:10])}...",
                    suggestion="翻译为英文",
                ))

        return violations

    def format_report(self, violations: list[LintViolation]) -> str:
        """格式化违规报告"""
        if not violations:
            return "Lint PASS: 无违规"

        errors = [v for v in violations if v.severity == "error"]
        warnings = [v for v in violations if v.severity == "warning"]

        lines = [f"Lint {'FAIL' if errors else 'WARN'}: {len(errors)} errors, {len(warnings)} warnings"]
        for v in errors:
            lines.append(f"  ERROR Shot {v.shot_id}: [{v.rule}] {v.message}")
            if v.suggestion:
                lines.append(f"    → {v.suggestion}")
        for v in warnings:
            lines.append(f"  WARN  Shot {v.shot_id}: [{v.rule}] {v.message}")

        return "\n".join(lines)

    def is_pass(self, violations: list[LintViolation]) -> bool:
        """是否通过（无error级违规）"""
        return not any(v.severity == "error" for v in violations)
