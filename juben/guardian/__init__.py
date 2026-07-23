"""
Guardian质量门卫 — 流式文本审查断言 v2

升级内容：
- 别名自动注入：从characters.json读取所有角色名+别名
- 违规片段定位：自动标记哪段对话是问题所在
- 信息倾倒密度：检测"一个人把背景讲完"的变相注水
"""
from __future__ import annotations

import re
import json
from collections import Counter
from pathlib import Path
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
    # 最少4个字符，避免"三年前"这种短片段误判
    if len(line.strip()) < 4:
        return False
    revelation_keywords = [
        "真相", "实话告诉你", "我告诉你", "告诉你", "其实",
        "八年前", "三年前", "当年", "那时候",
        "是我做的", "我杀的", "我有罪",
        "秘密", "不能说", "瞒了", "藏了",
        "灭门", "灭口", "杀了人", "死了人",
        "证据", "账本", "账册",
        "答应过", "替你死", "替你挡",
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

    if density > 1.5 and revelation_count >= 2:
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
# 断言1.6：NPC行为校验（动机驱动 + 反解说员）
# ============================================================

def check_npc_behavior(
    text: str,
    characters: list[dict] | None = None,
    alias_map: CharacterAliasMap | None = None,
) -> GuardianViolation | None:
    """
    检测NPC是否退化为解说员：
    1. NPC连续3句以上纯对话（无动作打断）
    2. NPC主动交代秘密（reveal关键词）
    3. NPC对话中无习惯动作锚定
    """
    if alias_map is None:
        alias_map = CharacterAliasMap()

    dialogues = _extract_dialogues_with_context(text, alias_map)
    non_protag = [d for d in dialogues if not d.is_protagonist]

    if len(non_protag) < 2:
        return None

    # 检测1：连续NPC对话无打断
    consecutive_npc = 0
    max_consecutive = 0
    for d in dialogues:
        if not d.is_protagonist:
            consecutive_npc += 1
            max_consecutive = max(max_consecutive, consecutive_npc)
        else:
            consecutive_npc = 0

    if max_consecutive >= 4:
        return GuardianViolation(
            rule="npc_consecutive_dialogue",
            severity="critical",
            description=f"NPC连续{max_consecutive}句对话无主角打断，退化为解说员模式",
            suggestion="NPC说话超过2句时必须被主角反问/环境异响/物理动作打断",
        )

    # 检测2：NPC主动交代秘密密度
    reveal_count = sum(1 for d in non_protag if d.is_revelation)
    if reveal_count >= 2:
        return GuardianViolation(
            rule="npc_secret_dump",
            severity="critical",
            description=f"{reveal_count}段NPC对话直接交代秘密/真相，解说员模式",
            suggestion="真相揭露应通过偷听、物证、推理拼凑完成，不能NPC主动说",
            offending_segments=[{
                "line_num": d.line_num,
                "speaker": d.speaker or "未知",
                "text": d.text[:80],
                "reason": "NPC主动交代秘密",
            } for d in non_protag if d.is_revelation][:3],
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
    # AI味高频短语（新增）
    "喃喃自语", "嘴角勾起一抹笑", "眼睛里闪过一丝光芒",
    "感觉到自己的血液在沸腾", "感觉到自己的战意在升腾",
    "两人的剑光在空中交错", "发出耀眼的光芒",
    "你果然有仙帝的风范", "他的眼睛亮了",
    "感觉到自己的心跳在加速", "脸色变得苍白",
    "嘴巴张了张，想说什么，但又说不出来",
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
# 钩子密度检测
# ============================================================

def check_hook_density(chapter_text: str, chapter_num: int) -> GuardianViolation | None:
    """
    检测章节结尾是否有悬念钩子。

    规则：
    - 最后一段必须包含钩子元素（悬念/反问/感官冲击/未完成动作）
    - 不能是平淡的叙述收尾
    """
    lines = [l.strip() for l in chapter_text.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("-")]
    if not lines:
        return None

    # 取最后一段
    last_para = lines[-1]

    # 钩子元素
    hook_indicators = [
        "？", "?",  # 反问
        "——",  # 破折号（暗示未完成）
        "...", "……",  # 省略号（暗示未尽之意）
        "突然", "忽然",  # 突发事件
        "转头", "转身", "回头",  # 动作暗示后续
        "发现", "看见", "注意到",  # 发现新信息
        "不对", "有问题", "奇怪",  # 悬念词
    ]

    # 感官冲击词
    sensory_hooks = [
        "冰冷", "滚烫", "血腥", "腐臭", "刺鼻",
        "嗡", "咔", "砰", "咚",  # 声音
        "黑", "红", "白",  # 颜色冲击
    ]

    has_hook = any(indicator in last_para for indicator in hook_indicators + sensory_hooks)

    # 检查是否是平淡收尾（常见的复读模式）
    boring_endings = [
        "继续查", "还得查", "还没完", "还没结束",
        "转身离开", "走出门", "回到房间",
        "深吸一口气", "叹了口气",
    ]

    is_boring = any(ending in last_para for ending in boring_endings)

    if not has_hook or is_boring:
        # 截取最后50字作为证据
        evidence = last_para[:50] + "..." if len(last_para) > 50 else last_para
        return GuardianViolation(
            rule="hook_density",
            severity="warning",
            description=f"章节结尾缺少悬念钩子。最后一段: '{evidence}'",
            suggestion="在结尾加入一个反问/感官冲击/未完成动作/悬念词，让读者想看下一章",
            offending_segments=[{"text": last_para[:80], "reason": "缺少钩子元素或使用平淡收尾"}],
        )

    return None


# ============================================================
# ============================================================
# 统一入口
# ============================================================
from juben.validate.structure_diversity import check_structure_diversity, get_banned_phrases
from juben.constraints import check_setting_elements, DEFAULT_COST_POOL


def guardian_check(
    chapter_text: str,
    chapter_num: int,
    protagonist_name: str = "",
    chapter_endings: list[str] | None = None,
    word_blacklist: list[str] | None = None,
    characters: list | None = None,
    previous_chapter_text: str | None = None,
    previous_fingerprints: list[list[str]] | None = None,
    banned_phrases: list[str] | None = None,
    required_setting_elements: list[str] | None = None,
    cost_history: list[str] | None = None,
    concept_mapping: dict | None = None,
    dynamic_blacklist: list[str] | None = None,
    project_dir: str | Path | None = None,
) -> GuardianResult:
    """
    Guardian统一审查入口（v3：硬门禁升级）
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

    # 1.6 NPC行为校验（反解说员 + 动机驱动）
    v = check_npc_behavior(chapter_text, characters, alias_map)
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

    # 4. 钩子密度检测（新增）
    v = check_hook_density(chapter_text, chapter_num)
    if v:
        result.add(v)

    # 5. 章节结构多样性检测（升级为hard fail）
    v = check_structure_diversity(
        current_text=chapter_text,
        previous_text=previous_chapter_text,
        previous_fingerprints=previous_fingerprints,
    )
    if v:
        # 升级：结构相似度>70%直接critical，不再只是warning
        severity = v.get("severity", "warning")
        if severity == "warning":
            severity = "critical"  # 升级为hard fail
        result.add(GuardianViolation(
            rule=v["rule"],
            severity=severity,
            description=v["description"],
            suggestion=v["suggestion"],
        ))

    # 6. 禁用短语检测（新增 — 跨章反重复）
    if banned_phrases:
        found = []
        for phrase in banned_phrases:
            count = chapter_text.count(phrase)
            if count > 0:
                found.append(f"'{phrase}'×{count}")
        if found:
            result.add(GuardianViolation(
                rule="banned_phrases",
                severity="critical",  # 硬门禁：出现即fail
                description=f"检测到禁用短语: {', '.join(found)}",
                suggestion="替换为具体的、独特的描写，禁止复用高频表达",
            ))

    # 7. 设定漂移检测（warning：auto-generated关键词不可靠，仅作提醒）
    if concept_mapping:
        found_elems, missing_groups = check_setting_elements(
            chapter_text, [], concept_mapping=concept_mapping
        )
        if len(found_elems) == 0:
            result.add(GuardianViolation(
                rule="setting_drift",
                severity="warning",
                description=f"设定漂移：本章未命中任何概念映射组。未命中组: {', '.join(missing_groups[:5])}",
                suggestion="考虑在正文中自然融入至少1个核心设定元素",
            ))
        elif len(missing_groups) > len(concept_mapping) * 0.7:
            result.add(GuardianViolation(
                rule="setting_drift_weak",
                severity="warning",
                description=f"设定元素覆盖不足：命中{len(found_elems)}个，未命中{len(missing_groups)}组",
                suggestion="建议增加更多设定元素的自然出现",
            ))

    # 7.5 实体锚点落地检测（warning级）
    if project_dir:
        from pathlib import Path as _Path2
        _anchors_path = _Path2(project_dir) / "entity_anchors.json"
        if _anchors_path.exists():
            try:
                _anchors = json.loads(_anchors_path.read_text(encoding="utf-8"))
                for _concept, _anchor in _anchors.items():
                    _keywords = _anchor.get("must_include_keywords", [])
                    if _keywords:
                        _found = any(kw in chapter_text for kw in _keywords)
                        if not _found:
                            result.add(GuardianViolation(
                                rule="anchor_miss",
                                severity="warning",
                                description=f"实体锚点未落地：本章涉及【{_concept}】但未出现锚点关键词: {', '.join(_keywords[:3])}",
                                suggestion=f"在正文中通过物理道具呈现【{_concept}】，使用锚点关键词",
                            ))
            except Exception:
                pass

    # 8. 代价重复检测 + 闪回硬限
    if cost_history:
        # 检测本章文本中是否包含最近5章用过的代价
        recent_costs = cost_history[-5:]  # 最近5章
        repeated = [c for c in recent_costs if c in chapter_text]
        if repeated:
            result.add(GuardianViolation(
                rule="cost_repetition",
                severity="critical",
                description=f"代价重复：本章使用了近期已用过的代价: {', '.join(repeated)}",
                suggestion="每次突破的代价必须不同，参考代价轮盘选择新代价",
            ))

        # 闪回硬限检测
        from juben.constraint_injector import CostRoulette
        flashback_count = sum(
            1 for c in cost_history if c in CostRoulette.FLASHBACK_COSTS
        )
        if flashback_count >= CostRoulette.FLASHBACK_HARD_LIMIT:
            # 检查本章是否使用了闪回
            flashback_in_text = any(kw in chapter_text for kw in CostRoulette.FLASHBACK_COSTS)
            if flashback_in_text:
                result.add(GuardianViolation(
                    rule="flashback_limit",
                    severity="critical",
                    description=f"闪回超限：全剧已使用{flashback_count}次闪回，上限{CostRoulette.FLASHBACK_HARD_LIMIT}次",
                    suggestion="本章禁止使用任何形式的闪回/记忆回溯，必须用当前场景的动作和对话推进剧情",
                ))

    # 9. 时空折叠检测（物理位置跳跃 + 位移介质锁）
    from juben.guardian.location_tracker import LocationTracker
    _proj_dir = Path(project_dir) if project_dir else None
    tracker = LocationTracker(project_dir=_proj_dir)
    paragraphs = [p.strip() for p in chapter_text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        jumps = tracker.detect_jumps(paragraphs, max_jump_distance=2)
        critical_jumps = [j for j in jumps if j.severity == "critical"]
        if critical_jumps:
            jump_desc = "; ".join(j.reason for j in critical_jumps[:3])
            result.add(GuardianViolation(
                rule="location_fold",
                severity="critical",
                description=f"时空折叠：检测到{len(critical_jumps)}处物理位置无逻辑跳跃。{jump_desc}",
                suggestion="场景切换需要过渡描写（走路/坐电梯/开门等），不能瞬间跳跃",
                offending_segments=[
                    {"start_line": j.from_para, "end_line": j.to_para,
                     "text": f"{j.from_location} → {j.to_location}", "reason": j.reason}
                    for j in critical_jumps[:3]
                ],
            ))

    # 10. 视觉密度检查（纯叙述占比）
    visual_density = _check_visual_density(chapter_text)
    if visual_density:
        result.add(visual_density)

    # 11. 动态黑名单检查（从已生成章节提取的高频词）
    if dynamic_blacklist:
        found = []
        for phrase in dynamic_blacklist:
            count = chapter_text.count(phrase)
            if count > 0:
                found.append(f"'{phrase}'×{count}")
        if found:
            result.add(GuardianViolation(
                rule="dynamic_blacklist",
                severity="critical",
                description=f"检测到动态黑名单词汇: {', '.join(found[:5])}",
                suggestion="这些是近期章节中泛滥的高频表达，请用独特的描写替代",
            ))

    # 12. 对话比例检查（新增）
    v = check_dialogue_ratio(chapter_text)
    if v:
        result.add(v)

    # 13. 物理打断锁检查（Cliffhanger强化版）
    v = check_physical_interruption_lock(chapter_text)
    if v:
        result.add(v)

    return result


def _check_visual_density(chapter_text: str) -> GuardianViolation | None:
    """
    检测视觉密度（纯叙述占比）。

    规则：
    - 可拍摄的动作描写占比不能低于60%
    - 纯叙述（心理描写、背景交代、抽象描述）占比不能超过40%
    """
    import re

    # 按段落分割
    paragraphs = [p.strip() for p in chapter_text.split('\n') if p.strip() and not p.startswith('#') and not p.startswith('-')]
    if not paragraphs:
        return None

    total_chars = 0
    visual_chars = 0

    # 物理动作关键词（可拍摄）
    action_keywords = [
        '站', '坐', '走', '跑', '跳', '推', '拉', '握', '抓', '扔', '打', '踢',
        '转', '抬', '低', '看', '盯', '瞪', '眨', '笑', '哭', '喊', '说',
        '拿', '放', '开', '关', '按', '点', '敲', '滑', '拖', '拉',
        '瞳孔', '手指', '拳头', '肩膀', '膝盖', '眼睛', '嘴唇',
        '屏幕', '键盘', '鼠标', '手机', '杯子', '桌子', '椅子',
        '红', '蓝', '绿', '白', '黑', '亮', '暗', '闪',
        '嗡', '咔', '砰', '咚', '滴', '响',
    ]

    for para in paragraphs:
        para_len = len(para)
        total_chars += para_len

        # 检查是否包含物理动作
        has_action = any(kw in para for kw in action_keywords)
        if has_action:
            visual_chars += para_len

    if total_chars == 0:
        return None

    visual_ratio = visual_chars / total_chars

    # 视觉密度低于60% → warning
    if visual_ratio < 0.6:
        return GuardianViolation(
            rule="visual_density",
            severity="warning",
            description=f"视觉密度不足：可拍摄动作占比{visual_ratio:.0%}（要求≥60%）",
            suggestion="增加更多物理动作描写、环境光影变化、道具特写，减少纯叙述和心理描写",
        )

    return None
from .location_tracker import LocationTracker, LocationJumpResult, LocationRecord


# ============================================================
# 新增：对话比例检查
# ============================================================

def check_dialogue_ratio(chapter_text: str) -> GuardianViolation | None:
    """检查对话占比是否超标"""
    import re
    
    # 提取对话内容（引号内的文字）
    dialogue_pattern = re.compile(r'[「"\"](.*?)[」\""]')
    dialogues = dialogue_pattern.findall(chapter_text)
    
    # 计算对话字数
    dialogue_chars = sum(len(d) for d in dialogues)
    total_chars = len(chapter_text)
    
    if total_chars < 100:
        return None
    
    ratio = dialogue_chars / total_chars
    
    if ratio > 0.35:
        return GuardianViolation(
            rule="dialogue_ratio_critical",
            severity="critical",
            description=f"对话占比{ratio:.0%}（超过35%），剧情靠嘴炮推进",
            suggestion="用动作、读心、潜伏、偷听等方式替代直接对话。每2句对话后插入1段物理动作/环境变化。",
        )
    elif ratio > 0.25:
        return GuardianViolation(
            rule="dialogue_ratio_warning",
            severity="warning",
            description=f"对话占比{ratio:.0%}（超过25%），对话偏多",
            suggestion="考虑用Show Don't Tell替代部分对话。",
        )
    
    return None


# ============================================================
# 新增：物理打断锁检查（Cliffhanger强化版）
# ============================================================

def check_physical_interruption_lock(chapter_text: str) -> GuardianViolation | None:
    """检查结尾是否使用了物理打断锁"""
    lines = [l.strip() for l in chapter_text.split("\n") if l.strip() and not l.startswith("#")]
    if not lines:
        return None
    
    # 取最后3行
    last_lines = lines[-3:]
    last_text = "\n".join(last_lines)
    
    # 物理打断元素
    interruption_indicators = [
        "突然", "忽然", "猛地", "骤然",
        "还没", "正要", "即将", "准备",
        "渗出", "传来", "响起", "炸开",
        "——", "……", "...",
    ]
    
    # 感官冲击元素
    sensory_indicators = [
        "血", "冰冷", "滚烫", "血腥",
        "嗡", "咔", "砰", "咚", "轰",
        "黑", "红", "白", "暗",
    ]
    
    # 弱结尾模式（禁止）
    weak_endings = [
        "他不知道", "她不知道", "他想", "她想",
        "他沉默了", "她沉默了", "他看着", "她看着",
        "走进雨里", "走进黑暗", "走进夜色",
    ]
    
    has_interruption = any(indicator in last_text for indicator in interruption_indicators)
    has_sensory = any(indicator in last_text for indicator in sensory_indicators)
    is_weak = any(ending in last_text for ending in weak_endings)
    
    if is_weak:
        return GuardianViolation(
            rule="physical_interruption_lock_weak",
            severity="critical",
            description=f"结尾使用了弱收尾模式: '{last_text[:50]}...'",
            suggestion="使用物理打断锁：[动作被打断] + [物理异常] + [感官定格]",
        )
    
    if not has_interruption and not has_sensory:
        return GuardianViolation(
            rule="physical_interruption_lock_missing",
            severity="warning",
            description=f"结尾缺少物理打断元素: '{last_text[:50]}...'",
            suggestion="在结尾加入突发物理异象或感官冲击。",
        )
    
    return None
