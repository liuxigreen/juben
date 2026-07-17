"""
Guardian质量门卫 — 流式文本审查断言

核心断言：
1. Anti-Dialogue：单章中非主角的长段独白/交代真相台词占比不能超过30%
2. Anti-Repetition：连续3章出现相同/相似的结尾句式，触发熔断
3. Anti-Monologue：反派不能在单章内一次性交代超过3条关键信息
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class GuardianViolation:
    """单条违规"""
    rule: str
    severity: str  # critical / warning / info
    description: str
    suggestion: str = ""


@dataclass
class GuardianResult:
    """Guardian审查结果"""
    passed: bool = True
    violations: list[GuardianViolation] = field(default_factory=list)
    score: float = 10.0

    def add(self, violation: GuardianViolation):
        self.violations.append(violation)
        if violation.severity == "critical":
            self.passed = False
            self.score = max(0, self.score - 3.0)
        elif violation.severity == "warning":
            self.score = max(0, self.score - 1.0)


# ============================================================
# 断言1：Anti-Dialogue（反嘴炮）
# ============================================================

def _extract_dialogue(text: str) -> list[str]:
    """提取所有对话内容（引号内的文字）"""
    # 匹配中文引号和英文引号
    patterns = [
        r'[「""]([^」""]*)[」""]',  # 中文引号
        r'"([^"]*)"',                  # 英文引号
    ]
    dialogues = []
    for pattern in patterns:
        dialogues.extend(re.findall(pattern, text))
    return dialogues


def _is_revelation_dialogue(line: str) -> bool:
    """判断一段对话是否是"交代真相"式的嘴炮"""
    revelation_keywords = [
        "真相", "实话告诉你", "我告诉你", "告诉你", "其实",
        "八年前", "三年前", "当年", "那时候",
        "是我", "我做的", "我杀的", "我有罪",
        "秘密", "不能说", "瞒了", "藏了",
        "灭门", "灭口", "杀了", "死了",
        "证据", "账本", "账册",
    ]
    return any(kw in line for kw in revelation_keywords)


def check_anti_dialogue(text: str, protagonist_name: str = "") -> GuardianViolation | None:
    """
    检查单章中非主角的长段对话/交代真相是否过多。

    规则：
    - 非主角的对话总字数超过全章30% → warning
    - 非主角的"交代真相"对话超过3段 → critical
    - 单段对话超过200字 → warning（可能是嘴炮念白）
    """
    dialogues = _extract_dialogue(text)
    total_chars = len(text)

    if total_chars < 100:
        return None

    # 统计非主角对话
    non_protag_dialogues = []
    revelation_count = 0

    for d in dialogues:
        # 简单判断：如果对话中出现了主角名字，可能是主角在说话
        if protagonist_name and protagonist_name in d:
            continue
        non_protag_dialogues.append(d)
        if _is_revelation_dialogue(d):
            revelation_count += 1

    non_protag_chars = sum(len(d) for d in non_protag_dialogues)
    ratio = non_protag_chars / total_chars

    # 检查1：非主角对话占比
    if ratio > 0.35:
        return GuardianViolation(
            rule="anti_dialogue_ratio",
            severity="critical",
            description=f"非主角对话占比{ratio:.0%}（超过35%），剧情靠嘴炮推进",
            suggestion="用动作、读心、潜伏、偷听等方式替代反派主动交代",
        )
    elif ratio > 0.25:
        return GuardianViolation(
            rule="anti_dialogue_ratio",
            severity="warning",
            description=f"非主角对话占比{ratio:.0%}（超过25%），对话偏多",
            suggestion="考虑用Show Don't Tell替代部分对话",
        )

    # 检查2：交代真相的对话数量
    if revelation_count >= 3:
        return GuardianViolation(
            rule="anti_revelation_dump",
            severity="critical",
            description=f"单章中有{revelation_count}段'交代真相'式对话，NPC排队念白",
            suggestion="真相揭露应该分散在多章中，通过偷听/读心碎片/证据拼凑完成",
        )

    # 检查3：单段对话长度
    for d in non_protag_dialogues:
        if len(d) > 200:
            return GuardianViolation(
                rule="anti_monologue",
                severity="warning",
                description=f"有一段非主角对话长达{len(d)}字，疑似NPC独白",
                suggestion="长段独白应该被打断——主角反问/环境干扰/情绪变化",
            )

    return None


# ============================================================
# 断言2：Anti-Repetition（反复读）
# ============================================================

def _extract_ending(text: str, chars: int = 100) -> str:
    """提取章节结尾"""
    lines = text.strip().split("\n")
    # 取最后非空行
    for line in reversed(lines):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("（"):
            return line[-chars:]
    return ""


def _similarity(a: str, b: str) -> float:
    """简单的字符级相似度"""
    if not a or not b:
        return 0.0
    # 用字符集合的Jaccard相似度
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def check_anti_repetition(chapter_endings: list[str]) -> GuardianViolation | None:
    """
    检查连续章节的结尾是否重复。

    规则：
    - 连续3章结尾相似度超过0.7 → critical
    - 连续2章结尾相似度超过0.8 → warning
    """
    if len(chapter_endings) < 2:
        return None

    # 检查连续3章
    for i in range(len(chapter_endings) - 2):
        a, b, c = chapter_endings[i], chapter_endings[i+1], chapter_endings[i+2]
        ab_sim = _similarity(a, b)
        bc_sim = _similarity(b, c)
        ac_sim = _similarity(a, c)

        avg_sim = (ab_sim + bc_sim + ac_sim) / 3
        if avg_sim > 0.7:
            return GuardianViolation(
                rule="anti_repetition_ending",
                severity="critical",
                description=f"第{i+1}-{i+3}章结尾高度相似（平均相似度{avg_sim:.0%}），疑似LLM复读",
                suggestion="每章结尾必须有不同的意象/情绪/悬念，禁止重复句式",
            )

    # 检查连续2章
    for i in range(len(chapter_endings) - 1):
        sim = _similarity(chapter_endings[i], chapter_endings[i+1])
        if sim > 0.8:
            return GuardianViolation(
                rule="anti_repetition_ending",
                severity="warning",
                description=f"第{i+1}-{i+2}章结尾高度相似（相似度{sim:.0%}）",
                suggestion="考虑换一种结尾方式",
            )

    return None


# ============================================================
# 断言3：高频词熔断（词频惩罚）
# ============================================================

# 默认黑名单 — LLM在温情/收尾语境下的高频垃圾词
DEFAULT_WORD_BLACKLIST = [
    "月亮很亮",
    "闭上眼睛，睡了",
    "闭上眼睛睡了",
    "甜甜的",
    "暖暖的",
    "淡淡的",
    "静静的",
    "深深的",
    "轻轻的",
    "缓缓的",
    "微微的",
    "不禁",
    "竟然",
    "居然",
    "仿佛",
    "好像",
    "似乎",
    "不知不觉",
    "一瞬间",
    "那一刻",
    "就这样",
    "不知不觉中",
]


def check_word_frequency(
    text: str,
    blacklist: list[str] | None = None,
    threshold: int = 3,
) -> GuardianViolation | None:
    """
    检查文本中黑名单词汇的出现频率。

    规则：
    - 同一个黑名单词在全章出现超过threshold次 → warning
    - 多个黑名单词同时高频出现 → critical
    """
    if blacklist is None:
        blacklist = DEFAULT_WORD_BLACKLIST

    hits = {}
    for word in blacklist:
        count = text.count(word)
        if count >= threshold:
            hits[word] = count

    if not hits:
        return None

    total_hits = sum(hits.values())
    hit_words = ", ".join(f"'{w}'×{c}" for w, c in hits.items())

    if len(hits) >= 3 or total_hits >= 8:
        return GuardianViolation(
            rule="word_frequency_critical",
            severity="critical",
            description=f"高频词熔断: {hit_words}",
            suggestion="替换为具体的、独特的描写，禁止使用通用套话",
        )
    else:
        return GuardianViolation(
            rule="word_frequency_warning",
            severity="warning",
            description=f"高频词警告: {hit_words}",
            suggestion="考虑换一种表达方式",
        )


# ============================================================
# 统一入口
# ============================================================

def guardian_check(
    chapter_text: str,
    chapter_num: int,
    protagonist_name: str = "",
    chapter_endings: list[str] | None = None,
    word_blacklist: list[str] | None = None,
) -> GuardianResult:
    """
    Guardian统一审查入口。

    Args:
        chapter_text: 本章正文
        chapter_num: 章节号
        protagonist_name: 主角名字（用于区分主角/非主角对话）
        chapter_endings: 截至本章的所有章节结尾（用于检测复读）
        word_blacklist: 自定义高频词黑名单

    Returns:
        GuardianResult
    """
    result = GuardianResult()

    # 1. Anti-Dialogue
    v = check_anti_dialogue(chapter_text, protagonist_name)
    if v:
        result.add(v)

    # 2. Anti-Repetition（需要至少2章的结尾）
    if chapter_endings and len(chapter_endings) >= 2:
        v = check_anti_repetition(chapter_endings)
        if v:
            result.add(v)

    # 3. 高频词熔断
    v = check_word_frequency(chapter_text, word_blacklist)
    if v:
        result.add(v)

    return result
