"""
Guardian质量门卫 — 流式文本审查断言 v2

升级内容：
- 别名自动注入：从characters.json读取所有角色名+别名
- 违规片段定位：自动标记哪段对话是问题所在
- 信息倾倒密度：检测"一个人把背景讲完"的变相注水
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
    # 新增：违规片段定位
    offending_segments: list[dict] = field(default_factory=list)
    # 格式: [{"start_line": 10, "end_line": 15, "text": "...", "reason": "..."}]


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
# 别名管理
# ============================================================

class CharacterAliasMap:
    """角色别名映射 — 从characters.json自动构建"""

    def __init__(self, characters: list | None = None):
        self.protagonist_names: set[str] = set()
        self.all_names: set[str] = set()
        self.name_to_role: dict[str, str] = {}

        if characters:
            self._build(characters)

    def _build(self, characters: list):
        for c in characters:
            names = {c.name}
            if hasattr(c, 'aliases'):
                names.update(c.aliases)
            role = c.role.value if hasattr(c.role, 'value') else str(c.role)

            for name in names:
                self.all_names.add(name)
                self.name_to_role[name] = role
                if role == "protagonist":
                    self.protagonist_names.add(name)

    def is_protagonist(self, text: str) -> bool:
        """判断一段文本是否包含主角名/别名"""
        return any(name in text for name in self.protagonist_names)

    def get_speaker(self, text: str) -> str | None:
        """尝试从文本中识别说话者"""
        for name in self.all_names:
            if name in text:
                return name
        return None


# ============================================================
# 对话提取（增强版：带行号和归属）
# ============================================================

@dataclass
class DialogueLine:
    """一条对话"""
    text: str
    line_num: int
    speaker: str | None = None  # 说话者（通过上下文推断）
    is_protagonist: bool = False
    is_revelation: bool = False  # 是否是交代真相


def _extract_dialogues_with_context(text: str, alias_map: CharacterAliasMap) -> list[DialogueLine]:
    """提取对话并尝试归属说话者"""
    lines = text.split("\n")
    dialogues = []

    # 匹配引号内的对话
    dialogue_pattern = re.compile(r'[「""]([^」""]*)[」""]')

    for i, line in enumerate(lines):
        matches = dialogue_pattern.findall(line)
        for d_text in matches:
            if not d_text.strip():
                continue

            # 尝试从同行的叙述文字中找说话者
            speaker = None
            # 常见模式："XXX说/道/笑/怒/问/答"
            speaker_match = re.search(
                r'(\S{2,4})(?:说|道|笑|怒|问|答|喊|叫|低声道|冷笑道|淡淡地说)',
                line
            )
            if speaker_match:
                candidate = speaker_match.group(1)
                if alias_map.get_speaker(candidate):
                    speaker = alias_map.get_speaker(candidate)

            # 如果没找到，检查是否包含角色名
            if not speaker:
                speaker = alias_map.get_speaker(line)

            is_protag = alias_map.is_protagonist(line) if speaker else False

            dialogues.append(DialogueLine(
                text=d_text,
                line_num=i + 1,
                speaker=speaker,
                is_protagonist=is_protag,
                is_revelation=_is_revelation_dialogue(d_text),
            ))

    return dialogues


# ============================================================
# 断言1：Anti-Dialogue（升级版）
# ============================================================

def _is_revelation_dialogue(line: str) -> bool:
    """判断一段对话是否是'交代真相'式的嘴炮"""
    revelation_keywords = [
        "真相", "实话告诉你", "我告诉你", "告诉你", "其实",
        "八年前", "三年前", "当年", "那时候",
        "是我", "我做的", "我杀的", "我有罪",
        "秘密", "不能说", "瞒了", "藏了",
        "灭门", "灭口", "杀了", "死了",
        "证据", "账本", "账册",
        "答应过", "保护", "替你",
    ]
    return any(kw in line for kw in revelation_keywords)


def check_anti_dialogue(
    text: str,
    alias_map: CharacterAliasMap | None = None,
    protagonist_name: str = "",
) -> GuardianViolation | None:
    """
    检查单章中非主角的长段对话/交代真相是否过多。
    """
    # 如果没有alias_map，用简单模式
    if alias_map is None:
        alias_map = CharacterAliasMap()
        if protagonist_name:
            alias_map.protagonist_names.add(protagonist_name)

    dialogues = _extract_dialogues_with_context(text, alias_map)
    total_chars = len(text)

    if total_chars < 100:
        return None

    # 统计非主角对话
    non_protag_dialogues = [d for d in dialogues if not d.is_protagonist]
    revelation_dialogues = [d for d in dialogues if d.is_revelation and not d.is_protagonist]

    non_protag_chars = sum(len(d.text) for d in non_protag_dialogues)
    ratio = non_protag_chars / total_chars

    # 检查1：非主角对话占比
    if ratio > 0.35:
        # 定位违规片段
        offending = []
        for d in non_protag_dialogues:
            if len(d.text) > 50:  # 只标记长对话
                offending.append({
                    "line_num": d.line_num,
                    "speaker": d.speaker or "未知",
                    "text": d.text[:100] + ("..." if len(d.text) > 100 else ""),
                    "reason": f"非主角对话，{len(d.text)}字",
                })

        return GuardianViolation(
            rule="anti_dialogue_ratio",
            severity="critical",
            description=f"非主角对话占比{ratio:.0%}（超过35%），剧情靠嘴炮推进",
            suggestion="用动作、读心、潜伏、偷听等方式替代反派主动交代",
            offending_segments=offending,
        )
    elif ratio > 0.25:
        return GuardianViolation(
            rule="anti_dialogue_ratio",
            severity="warning",
            description=f"非主角对话占比{ratio:.0%}（超过25%），对话偏多",
            suggestion="考虑用Show Don't Tell替代部分对话",
        )

    # 检查2：交代真相的对话数量
    if len(revelation_dialogues) >= 3:
        offending = []
        for d in revelation_dialogues:
            offending.append({
                "line_num": d.line_num,
                "speaker": d.speaker or "未知",
                "text": d.text[:100],
                "reason": "交代真相对话",
            })

        return GuardianViolation(
            rule="anti_revelation_dump",
            severity="critical",
            description=f"单章中有{len(revelation_dialogues)}段'交代真相'式对话，NPC排队念白",
            suggestion="真相揭露应该分散在多章中，通过偷听/读心碎片/证据拼凑完成",
            offending_segments=offending,
        )

    # 检查3：单段对话长度
    for d in non_protag_dialogues:
        if len(d.text) > 200:
            return GuardianViolation(
                rule="anti_monologue",
                severity="warning",
                description=f"有一段非主角对话长达{len(d.text)}字，疑似NPC独白",
                suggestion="长段独白应该被打断——主角反问/环境干扰/情绪变化",
                offending_segments=[{
                    "line_num": d.line_num,
                    "speaker": d.speaker or "未知",
                    "text": d.text[:100] + "...",
                    "reason": f"独白{len(d.text)}字",
                }],
            )

    return None


# ============================================================
# 断言1.5：信息倾倒密度（新增）
# ============================================================

def check_info_dump(text: str, alias_map: CharacterAliasMap | None = None) -> GuardianViolation | None:
    """
    检测"信息倾倒"——非主角在短时间内密集输出背景/真相/设定。

    规则：
    - 非主角对话中，真相关键词+解释性句式的集中度超过阈值 → critical
    - 即使对话占比不超标，信息倾倒本身也该被抓
    """
    if alias_map is None:
        alias_map = CharacterAliasMap()

    dialogues = _extract_dialogues_with_context(text, alias_map)
    non_protag = [d for d in dialogues if not d.is_protagonist]

    if len(non_protag) < 2:
        return None

    # 解释性句式
    explanation_patterns = [
        "是因为", "原因是", "之所以", "换句话说", "也就是说",
        "你要知道", "事情是", "真相是", "其实", "实际上",
        "三年前", "八年前", "当年", "那时候", "后来",
        "第一", "第二", "第三", "首先", "然后", "最后",
    ]

    # 统计非主角对话中的解释性密度
    explanation_count = 0
    revelation_count = 0
    total_non_protag_chars = 0

    for d in non_protag:
        total_non_protag_chars += len(d.text)
        for pattern in explanation_patterns:
            explanation_count += d.text.count(pattern)
        if d.is_revelation:
            revelation_count += 1

    # 密度 = 解释性句式数 / 非主角对话段数
    if len(non_protag) > 0:
        density = explanation_count / len(non_protag)
    else:
        density = 0

    if density > 2.0 and revelation_count >= 2:
        # 找出信息倾倒最严重的段落
        worst = max(non_protag, key=lambda d: sum(1 for p in explanation_patterns if p in d.text))

        return GuardianViolation(
            rule="info_dump_density",
            severity="critical",
            description=f"信息倾倒密度{density:.1f}（阈值2.0），{revelation_count}段真相密集输出",
            suggestion="把背景信息拆散到多章中，用动作/物品/环境来暗示，不要一次性说完",
            offending_segments=[{
                "line_num": worst.line_num,
                "speaker": worst.speaker or "未知",
                "text": worst.text[:100] + "...",
                "reason": f"信息倾倒密度最高的段落",
            }],
        )

    return None


# ============================================================
# 断言2：Anti-Repetition（反复读）
# ============================================================

def _extract_ending(text: str, chars: int = 100) -> str:
    """提取章节结尾"""
    lines = text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("（"):
            return line[-chars:]
    return ""


def _similarity(a: str, b: str) -> float:
    """简单的字符级相似度"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def check_anti_repetition(chapter_endings: list[str]) -> GuardianViolation | None:
    """检查连续章节的结尾是否重复"""
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
# 断言3：高频词熔断
# ============================================================

DEFAULT_WORD_BLACKLIST = [
    "月亮很亮", "闭上眼睛，睡了", "闭上眼睛睡了",
    "甜甜的", "暖暖的", "淡淡的", "静静的", "深深的",
    "轻轻的", "缓缓的", "微微的",
    "不禁", "竟然", "居然", "仿佛", "好像", "似乎",
    "不知不觉", "一瞬间", "那一刻", "就这样", "不知不觉中",
]


def check_word_frequency(
    text: str,
    blacklist: list[str] | None = None,
    threshold: int = 3,
) -> GuardianViolation | None:
    """检查高频词"""
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
    characters: list | None = None,
) -> GuardianResult:
    """
    Guardian统一审查入口（v2：支持别名注入）
    """
    result = GuardianResult()

    # 构建别名映射
    alias_map = CharacterAliasMap(characters)

    # 1. Anti-Dialogue（带别名）
    v = check_anti_dialogue(chapter_text, alias_map, protagonist_name)
    if v:
        result.add(v)

    # 1.5 信息倾倒密度（新增）
    v = check_info_dump(chapter_text, alias_map)
    if v:
        result.add(v)

    # 2. Anti-Repetition
    if chapter_endings and len(chapter_endings) >= 2:
        v = check_anti_repetition(chapter_endings)
        if v:
            result.add(v)

    # 3. 高频词熔断
    v = check_word_frequency(chapter_text, word_blacklist)
    if v:
        result.add(v)

    return result
