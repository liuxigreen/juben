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
        self.name_to_gender: dict[str, str] = {}  # 新增：gender映射
        self.gender_to_names: dict[str, set[str]] = {"male": set(), "female": set()}  # 新增：按gender分组

        if characters:
            self._build(characters)

    def _build(self, characters: list):
        for c in characters:
            names = {c.name}
            if hasattr(c, 'aliases'):
                names.update(c.aliases)
            role = c.role.value if hasattr(c.role, 'value') else str(c.role)
            gender = getattr(c, 'gender', '') or ''

            # 用主名作为代表（避免别名导致gender_to_names有重复条目）
            representative_name = c.name
            
            for name in names:
                self.all_names.add(name)
                self.name_to_role[name] = role
                self.name_to_gender[name] = gender
                if role == "protagonist":
                    self.protagonist_names.add(name)
            
            # 按gender分组（只用主名，避免别名重复）
            if gender in ("male", "female"):
                self.gender_to_names[gender].add(representative_name)

    def is_protagonist(self, text: str) -> bool:
        """判断一段文本是否包含主角名/别名"""
        return any(name in text for name in self.protagonist_names)

    def get_speaker(self, text: str) -> str | None:
        """尝试从文本中识别说话者"""
        for name in self.all_names:
            if name in text:
                return name
        return None

    def resolve_pronoun(self, pronoun: str, last_speaker: str | None = None, recent_speakers: list[str] | None = None) -> str | None:
        """
        代词消解：根据gender和交替状态机推断说话者
        
        Args:
            pronoun: "他" 或 "她"
            last_speaker: 上一个说话者（用于交替推断）
            recent_speakers: 最近出现过的说话者列表（用于优先选择）
        """
        target_gender = "male" if pronoun == "他" else "female" if pronoun == "她" else None
        if not target_gender:
            return None
        
        candidates = self.gender_to_names.get(target_gender, set())
        if not candidates:
            return None
        
        # 只有一个候选 → 直接返回
        if len(candidates) == 1:
            return next(iter(candidates))
        
        # 多个候选 → 优先策略：
        # 1. 优先选最近出现过的（最近5句）
        if recent_speakers:
            recent_candidates = [s for s in recent_speakers if s in candidates]
            if recent_candidates:
                return recent_candidates[0]
        
        # 2. 优先选protagonist（主角对话概率更高）
        protagonist_candidates = candidates & self.protagonist_names
        if protagonist_candidates:
            # 如果last_speaker是protagonist，选另一个（交替）
            if last_speaker in protagonist_candidates and len(protagonist_candidates) > 1:
                remaining = protagonist_candidates - {last_speaker}
                return next(iter(remaining))
            return next(iter(protagonist_candidates))
        
        # 3. 无protagonist → 用交替状态机排除last_speaker
        if last_speaker and last_speaker in candidates:
            remaining = candidates - {last_speaker}
            if len(remaining) == 1:
                return next(iter(remaining))
        
        # 无法消解 → 返回None（保守策略，不猜测）
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
    confidence: str = "high"  # 置信度：high/medium/low


def _extract_dialogues_with_context(text: str, alias_map: CharacterAliasMap) -> list[DialogueLine]:
    """
    提取对话并归属说话者 — 三级识别 + 交替发言状态机
    
    Level 1: 显式人名匹配 "陈默说" / "王建国冷笑道"
    Level 2: 代词匹配 "他说" / "她问" → 根据gender消解
    Level 3: 无主语动词 "冷笑道" / "沉声道" → 根据交替状态机推断
    """
    lines = text.split("\n")
    dialogues = []
    
    # 匹配引号内的对话（支持「」""""多种引号）
    dialogue_pattern = re.compile(r'[「"\u201c]([^」"\u201d]*)[」"\u201d]')
    
    # 说话动词列表
    SPEECH_VERBS = r'说|道|问|答|喊|叫|嚷|吼|怒|笑|冷笑|苦笑|微笑|叹|叹道|低声道|沉声道|淡淡地说|轻声道|厉声道|高声道|尖声|喃喃|呵斥|质问|追问|反问|回应|嘟囔|嘀咕|插嘴|反驳|解释|补充|强调|低声|厉声|大声|小声'
    
    # 交替发言状态机
    last_speaker: str | None = None
    last_speaker_role: str | None = None  # "protagonist" / "npc"
    recent_speakers: list[str] = []  # 最近5句的说话者
    
    for i, line in enumerate(lines):
        # 找到所有对话及其位置
        matches = list(dialogue_pattern.finditer(line))
        if not matches:
            continue
        
        for match in matches:
            d_text = match.group(1)
            if not d_text.strip():
                continue
            
            # 获取对话前后的叙述文字
            before = line[:match.start()].strip()
            after = line[match.end():].strip()
            
            speaker = None
            speaker_role = None
            confidence = "high"  # 默认高置信度
            
            # === Level 1: 显式人名匹配 ===
            # 检查对话前的引导语
            name_pattern = re.compile(rf'(\S{{2,6}})(?:{SPEECH_VERBS})')
            name_match = name_pattern.search(before)
            if name_match:
                candidate = name_match.group(1)
                resolved = alias_map.get_speaker(candidate)
                if resolved:
                    speaker = resolved
                    speaker_role = alias_map.name_to_role.get(resolved, '')
                    confidence = "high"  # Level 1: 显式人名，高置信度
            
            # 检查对话后的引导语（少见但存在）
            if not speaker:
                name_match = name_pattern.search(after)
                if name_match:
                    candidate = name_match.group(1)
                    resolved = alias_map.get_speaker(candidate)
                    if resolved:
                        speaker = resolved
                        speaker_role = alias_map.name_to_role.get(resolved, '')
                        confidence = "high"  # Level 1: 显式人名，高置信度
            
            # === Level 2: 代词匹配 ===
            if not speaker:
                pronoun_pattern = re.compile(rf'(他|她)(?:{SPEECH_VERBS})')
                # 检查对话前
                pronoun_match = pronoun_pattern.search(before)
                if not pronoun_match:
                    # 检查对话后
                    pronoun_match = pronoun_pattern.search(after)
                if pronoun_match:
                    pronoun = pronoun_match.group(1)
                    # 代词消解：结合gender和交替状态机
                    resolved = alias_map.resolve_pronoun(pronoun, last_speaker, recent_speakers)
                    if resolved:
                        speaker = resolved
                        speaker_role = alias_map.name_to_role.get(resolved, '')
                        confidence = "medium"  # Level 2: 代词匹配，中置信度
            
            # === Level 3: 无主语动词 或 纯对话（无引导语）===
            if not speaker:
                bare_verb_pattern = re.compile(rf'(?:{SPEECH_VERBS})')
                has_verb = bare_verb_pattern.search(before) or bare_verb_pattern.search(after)
                # 纯对话（before和after都很短，无引导语）
                is_bare_dialogue = (len(before) < 3 and len(after) < 3)
                
                if has_verb or is_bare_dialogue:
                    # 交替状态机
                    # 上一个是非主角（antagonist/supporting/minor）→ 这个可能是主角
                    if last_speaker_role and last_speaker_role != 'protagonist' and alias_map.protagonist_names:
                        speaker = next(iter(alias_map.protagonist_names))
                        speaker_role = 'protagonist'
                        confidence = "low"  # Level 3: 交替状态机，低置信度
                    # 上一个是主角 → 这个可能是NPC（找一个非主角）
                    elif last_speaker_role == 'protagonist':
                        for name in alias_map.all_names:
                            if name not in alias_map.protagonist_names:
                                speaker = name
                                speaker_role = alias_map.name_to_role.get(name, '')
                                confidence = "low"  # Level 3: 交替状态机，低置信度
                                break
            
            # === 兜底：检查整行是否包含角色名 ===
            if not speaker:
                resolved = alias_map.get_speaker(line)
                if resolved:
                    speaker = resolved
                    speaker_role = alias_map.name_to_role.get(resolved, '')
                    confidence = "medium"  # 兜底：整行匹配，中置信度
            
            # 确定是否是主角
            is_protag = (speaker_role == 'protagonist') if speaker else False
            
            # 更新状态机
            if speaker:
                last_speaker = speaker
                last_speaker_role = speaker_role
                # 更新最近说话者列表（保留最近5句）
                recent_speakers.append(speaker)
                if len(recent_speakers) > 5:
                    recent_speakers.pop(0)
            
            dialogues.append(DialogueLine(
                text=d_text,
                line_num=i + 1,
                speaker=speaker,
                is_protagonist=is_protag,
                is_revelation=_is_revelation_dialogue(d_text),
                confidence=confidence,
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
    1. NPC连续3句以上纯对话（同一行或相邻行无叙述打断）
    2. NPC主动交代秘密（reveal关键词）
    """
    if alias_map is None:
        alias_map = CharacterAliasMap(characters)

    dialogues = _extract_dialogues_with_context(text, alias_map)
    non_protag = [d for d in dialogues if not d.is_protagonist]

    if len(non_protag) < 2:
        return None

    # 检测1：连续NPC对话无叙述打断
    # 核心改进：不只看对话列表的连续性，还要检查对话之间是否有叙述文字
    # 同一行的多句对话算连续；不同行之间如果有叙述文字则算有打断
    consecutive_npc = 0
    max_consecutive = 0
    prev_line = -1
    lines = text.split("\n")

    # 构建通用说话引导语剥离正则（方案一+方案二组合）
    # 方案一：从characters动态加载人名
    char_names = []
    if characters:
        for c in characters:
            name = c.name if hasattr(c, 'name') else c.get('name', '')
            if name:
                char_names.append(name)
            aliases = c.aliases if hasattr(c, 'aliases') else c.get('aliases', [])
            if aliases:
                char_names.extend(aliases)
    # 方案二：通用说话动词范式
    speech_verbs = r"说|道|问|答|喊|叫|笑|怒|冷笑道|低声道|淡淡地说|喃喃|叹道|呵斥|回应|插话|追问|嘟囔"
    # 拼接：人名 + 可选微动作(0-4字) + 说话动词
    if char_names:
        names_pattern = "|".join(re.escape(n) for n in char_names)
        speech_tag_re = re.compile(
            rf"(?:{names_pattern})(?:[\u4e00-\u9fff]{{0,4}})?(?:{speech_verbs})[：:，,]?"
        )
    else:
        # 兜底：2-6字中文 + 说话动词（不依赖人名）
        speech_tag_re = re.compile(
            rf"[\u4e00-\u9fa5]{{2,6}}(?:{speech_verbs})[：:，,]?"
        )

    for d in dialogues:
        if not d.is_protagonist:
            # 检查与前一句NPC对话之间是否有叙述文字
            if prev_line >= 0 and d.line_num > prev_line:
                # 检查prev_line和d.line_num之间的行是否有叙述文字
                has_narrative = False
                for ln in range(prev_line, min(d.line_num, len(lines))):
                    line_text = lines[ln].strip()
                    # 跳过空行
                    if not line_text:
                        continue
                    # 去掉对话内容
                    stripped = re.sub(r'[「""].*?[」""]', '', line_text)
                    # 去掉说话引导语（动态人名+通用动词）
                    stripped = speech_tag_re.sub('', stripped)
                    stripped = stripped.strip().rstrip('。，！？,.!?')
                    if not stripped:
                        continue
                    # 有非对话文字 = 叙述打断
                    has_narrative = True
                    break
                if has_narrative:
                    consecutive_npc = 1  # 有叙述打断，重置为1（当前这句）
                else:
                    consecutive_npc += 1
            else:
                consecutive_npc += 1
            prev_line = d.line_num - 1  # 0-indexed
            max_consecutive = max(max_consecutive, consecutive_npc)
        else:
            consecutive_npc = 0
            prev_line = d.line_num - 1

    if max_consecutive >= 4:
        return GuardianViolation(
            rule="npc_consecutive_dialogue",
            severity="critical",
            description=f"NPC连续{max_consecutive}句对话无叙述打断，退化为解说员模式",
            suggestion="NPC说话超过2句时必须插入动作/环境/感官描写打断",
        )

    # 检测2：NPC主动交代秘密密度
    # 豁免：如果NPC的揭露对话周围有物证关键词（录音/文件/照片/视频/短信/案卷），算"物证触发"不算"嘴炮"
    evidence_keywords = [
        "录音", "文件", "照片", "视频", "U盘", "笔记本", "短信", "彩信",
        "案卷", "监控", "截图", "证据", "报告", "手机屏幕", "屏幕",
        "翻盖手机", "信封", "名片", "卡片",
    ]
    lines = text.split("\n")

    def _has_evidence_context(dialogue: DialogueLine) -> bool:
        """检查对话所在行及上下2行是否有物证关键词"""
        line_idx = dialogue.line_num - 1  # 0-indexed
        for offset in range(-2, 3):
            idx = line_idx + offset
            if 0 <= idx < len(lines):
                if any(kw in lines[idx] for kw in evidence_keywords):
                    return True
        return False

    # 只统计没有物证上下文的NPC揭露对话
    active_reveals = [d for d in non_protag if d.is_revelation and not _has_evidence_context(d)]
    reveal_count = len(active_reveals)
    if reveal_count >= 2:
        return GuardianViolation(
            rule="npc_secret_dump",
            severity="critical",
            description=f"{reveal_count}段NPC对话主动交代秘密/真相（非物证触发），解说员模式",
            suggestion="真相揭露应通过偷听、物证、推理拼凑完成，不能NPC主动开口说",
            offending_segments=[{
                "line_num": d.line_num,
                "speaker": d.speaker or "未知",
                "text": d.text[:80],
                "reason": "NPC主动交代秘密",
            } for d in active_reveals][:3],
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
    
    与check_physical_interruption_lock()的关系：
    - 本函数：检测是否有钩子元素（warning级）
    - check_physical_interruption_lock()：检测是否使用了弱结尾模式（critical级）
    """
    lines = [l.strip() for l in chapter_text.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("-")]
    if not lines:
        return None

    # 取最后一段
    last_para = lines[-1]

    # 钩子元素（与check_physical_interruption_lock()统一）
    hook_indicators = [
        "？", "?",  # 反问
        "——",  # 破折号（暗示未完成）
        "...", "……",  # 省略号（暗示未尽之意）
        "突然", "忽然", "猛地", "骤然",  # 突发事件
        "转头", "转身", "回头",  # 动作暗示后续
        "发现", "看见", "注意到",  # 发现新信息
        "不对", "有问题", "奇怪",  # 悬念词
        "还没", "正要", "即将", "准备",  # 未完成动作
        "渗出", "传来", "响起", "炸开",  # 物理异象
    ]

    # 感官冲击词（与check_physical_interruption_lock()统一）
    sensory_hooks = [
        "冰冷", "滚烫", "血腥", "腐臭", "刺鼻",
        "嗡", "咔", "砰", "咚", "轰",  # 声音
        "黑", "红", "白", "暗",  # 颜色冲击
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
    # 从项目配置加载事件指纹关键词
    event_fps = None
    if project_dir:
        from juben.validate.structure_diversity import load_event_fingerprints_from_project
        event_fps = load_event_fingerprints_from_project(Path(project_dir))
    
    v = check_structure_diversity(
        current_text=chapter_text,
        previous_text=previous_chapter_text,
        previous_fingerprints=previous_fingerprints,
        event_fingerprints=event_fps,
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
