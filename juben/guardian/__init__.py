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
import logging
from collections import Counter
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
    is_evidence: bool = False  # 是否是物证内容（短信/屏幕/文件等）
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
    
    # 物证上下文关键词（短信/屏幕/文件/录音等）
    EVIDENCE_KEYWORDS = [
        "短信", "彩信", "微信", "消息", "信息",
        "手机屏幕", "屏幕显示", "屏幕亮起", "屏幕弹出",
        "录音", "播放", "音频", "视频",
        "文件", "照片", "截图", "图片",
        "案卷", "卷宗", "档案", "报告",
        "笔记本", "日记", "信件", "信封",
        "U盘", "硬盘", "存储卡",
    ]
    # 物证动作关键词（展示/播放/打开等）
    EVIDENCE_ACTIONS = [
        "展示", "甩出", "拍在", "放在", "递出", "拿出", "掏出", "打开",
        "播放", "按下", "插入", "连接", "显示", "投射", "投影",
        "砸在", "扔在", "丢在", "摆在", "亮出", "出示",
        "翻出", "调出", "点开", "划开",
    ]
    
    def _is_evidence_context(line_idx: int) -> bool:
        """检查当前行及上下2行是否有物证关键词"""
        for offset in range(-2, 3):
            idx = line_idx + offset
            if 0 <= idx < len(lines):
                line_text = lines[idx]
                # 检查物证关键词
                if any(kw in line_text for kw in EVIDENCE_KEYWORDS):
                    return True
                # 检查物证动作
                if any(kw in line_text for kw in EVIDENCE_ACTIONS):
                    return True
        return False
    
    # 交替发言状态机
    last_speaker: str | None = None
    last_speaker_role: str | None = None  # "protagonist" / "npc"
    recent_speakers: list[str] = []  # 最近5句的说话者
    
    for i, line in enumerate(lines):
        # 找到所有对话及其位置
        matches = list(dialogue_pattern.finditer(line))
        if not matches:
            continue
        
        # 检查当前行是否是物证上下文
        is_evidence_line = _is_evidence_context(i)
        
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
                is_evidence=is_evidence_line,
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
    
    # 核心揭露关键词（必须是主动交代真相，不是提及真相）
    core_revelation_keywords = [
        "实话告诉你", "我告诉你", "告诉你真相",
        "是我做的", "我杀的", "我有罪",
        "灭门", "灭口", "杀了人", "死了人",
        "替你死", "替你挡",
    ]
    
    # 次级揭露关键词（需要结合上下文判断）
    secondary_keywords = [
        "真相", "告诉你", "其实",
        "八年前", "三年前", "当年", "那时候",
        "秘密", "不能说", "瞒了", "藏了",
        "证据", "账本", "账册",
        "答应过",
    ]
    
    # 检查核心揭露关键词
    if any(kw in line for kw in core_revelation_keywords):
        return True
    
    # 检查次级揭露关键词（需要至少2个才判定）
    secondary_count = sum(1 for kw in secondary_keywords if kw in line)
    if secondary_count >= 2:
        return True
    
    return False


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
    elif ratio > 0.30:
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

def check_info_dump(text: str, alias_map: CharacterAliasMap | None = None, structure_type: str | None = None) -> GuardianViolation | None:
    """
    检测"信息倾倒"——非主角在短时间内密集输出背景/真相/设定。

    规则：
    - 非主角对话中，真相关键词+解释性句式的集中度超过阈值 → critical
    - 即使对话占比不超标，信息倾倒本身也该被抓
    
    动态阈值（按结构类型）：
    - action_heavy / chase: ≤ 1.0（极度严苛）
    - confrontation / suspense: ≤ 1.5（标准）
    - investigation / reveal: ≤ 2.2（允许高密度事实与证据交代）
    """
    if alias_map is None:
        alias_map = CharacterAliasMap()

    dialogues = _extract_dialogues_with_context(text, alias_map)
    # 过滤掉物证内容（短信/屏幕/文件等），这些不算NPC主动说话
    non_protag = [d for d in dialogues if not d.is_protagonist and not d.is_evidence]

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

    # 动态阈值：按结构类型设置不同上限
    INFO_DUMP_CAPS = {
        "action_heavy": 1.0,
        "chase": 1.0,
        "suspense": 1.5,
        "confrontation": 1.5,
        "investigation": 2.2,
        "reveal": 2.2,
    }
    
    # 获取本章的信息倾倒上限
    cap = INFO_DUMP_CAPS.get(structure_type or "", 1.5)  # 默认1.5

    if density > cap and revelation_count >= 2:
        # 找出信息倾倒最严重的段落
        worst = max(non_protag, key=lambda d: sum(1 for p in explanation_patterns if p in d.text))

        return GuardianViolation(
            rule="info_dump_density",
            severity="critical",
            description=f"信息倾倒密度{density:.1f}（阈值{cap}，结构类型: {structure_type or '未知'}），{revelation_count}段真相密集输出",
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
    # 过滤掉物证内容（短信/屏幕/文件等），这些不算NPC主动说话
    non_protag = [d for d in dialogues if not d.is_protagonist and not d.is_evidence]

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
        if not d.is_protagonist and not d.is_evidence:
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
    # 使用DialogueLine.is_evidence标记豁免物证内容（短信/屏幕/文件等）
    # 只统计非物证的NPC揭露对话
    active_reveals = [d for d in non_protag if d.is_revelation]
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


def check_anti_repetition(chapter_endings: list[str], chapter_num: int = 0, total_chapters: int = 50) -> GuardianViolation | None:
    """检查连续章节的结尾是否重复（只检查最近10章）"""
    if len(chapter_endings) < 2:
        return None

    # 只检查最近10章，避免历史章节的旧问题干扰当前审计
    recent = chapter_endings[-10:] if len(chapter_endings) > 10 else chapter_endings
    offset = len(chapter_endings) - len(recent)

    # 动态阈值：结局段放宽阈值，允许收尾叙事的自然结构相似
    ratio = chapter_num / total_chapters if total_chapters > 0 else 0.5
    if ratio > 0.80:  # 结局段（最后20%）
        threshold_3ch = 0.85  # 放宽连续3章阈值
        threshold_2ch = 0.90  # 放宽连续2章阈值
    elif ratio > 0.45:  # 风暴段
        threshold_3ch = 0.80
        threshold_2ch = 0.85
    else:  # 起势段/攀升段
        threshold_3ch = 0.7
        threshold_2ch = 0.8

    # 检查连续3章（从最近的开始往前查）
    for i in range(len(recent) - 3, -1, -1):
        a, b, c = recent[i], recent[i+1], recent[i+2]
        ab_sim = _similarity(a, b)
        bc_sim = _similarity(b, c)
        ac_sim = _similarity(a, c)

        avg_sim = (ab_sim + bc_sim + ac_sim) / 3
        if avg_sim > threshold_3ch:
            return GuardianViolation(
                rule="anti_repetition_ending",
                severity="critical",
                description=f"第{offset+i+1}-{offset+i+3}章结尾高度相似（平均相似度{avg_sim:.0%}），疑似LLM复读",
                suggestion="每章结尾必须有不同的意象/情绪/悬念，禁止重复句式",
            )

    # 检查连续2章（从最近的开始往前查）
    for i in range(len(recent) - 2, -1, -1):
        sim = _similarity(recent[i], recent[i+1])
        if sim > threshold_2ch:
            return GuardianViolation(
                rule="anti_repetition_ending",
                severity="warning",
                description=f"第{offset+i+1}-{offset+i+2}章结尾高度相似（相似度{sim:.0%}）",
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
    entity_anchors: dict | None = None,
) -> GuardianViolation | None:
    """检查高频词（自动豁免entity_anchors关键词）"""
    if blacklist is None:
        blacklist = DEFAULT_WORD_BLACKLIST

    # 动态构建本章的豁免词库（道具锚点词不计入频次惩罚）
    anchor_keywords = set()
    if entity_anchors:
        for anchor in entity_anchors.values():
            keywords = anchor.get("must_include_keywords", [])
            anchor_keywords.update(keywords)

    hits = {}
    for word in blacklist:
        # 跳过锚点词（锚点词允许高频出现）
        if word in anchor_keywords:
            continue
        count = text.count(word)
        if count >= threshold:
            hits[word] = count

    if not hits:
        return None

    total_hits = sum(hits.values())
    hit_words = ", ".join(f"'{w}'×{c}" for w, c in hits.items())

    # 升级条件：单个短语出现5次以上也升级为critical
    max_single_count = max(hits.values()) if hits else 0
    
    if len(hits) >= 3 or total_hits >= 8 or max_single_count >= 5:
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

# 代价检测辅助：过滤"回忆/提及"场景
_PAST_CONTEXT_KEYWORDS = [
    "回忆", "想起", "记得", "当时", "那时候", "当年",
    "三年前", "五年前", "十年前", "十五年前", "八年前",
    "上次", "以前", "过去", "曾经", "早就不", "已经不",
    "提到", "说起", "谈起", "聊起", "想到",
]

def _is_past_mention(text: str, cost: str) -> bool:
    """检查代价词是否出现在回忆/提及上下文中（前10字有过去时态标记）"""
    for m in re.finditer(re.escape(cost), text):
        start = max(0, m.start() - 10)
        prefix = text[start:m.start()]
        if any(kw in prefix for kw in _PAST_CONTEXT_KEYWORDS):
            return True
    return False

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
    high_concept: dict | None = None,
    recent_chapter_texts: list[str] | None = None,
) -> GuardianResult:
    """
    Guardian统一审查入口（v3：硬门禁升级）
    """
    result = GuardianResult()

    # 构建别名映射
    alias_map = CharacterAliasMap(characters)
    
    # 提前加载结构类型（用于动态阈值）
    structure_type = None
    if project_dir:
        structure_history_path = Path(project_dir) / "structure_history.json"
        if structure_history_path.exists():
            try:
                history = json.loads(structure_history_path.read_text(encoding="utf-8"))
                for entry in history:
                    if entry.get("chapter") == chapter_num:
                        structure_type = entry.get("type")
                        break
            except Exception as e:
                logger.warning(f"加载structure_history.json失败: {e}")

    # 1. Anti-Dialogue（带别名）
    v = check_anti_dialogue(chapter_text, alias_map, protagonist_name)
    if v:
        result.add(v)

    # 1.5 信息倾倒密度（动态阈值）
    v = check_info_dump(chapter_text, alias_map, structure_type)
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

    # 3. 高频词熔断（自动豁免entity_anchors关键词）
    # 从项目配置加载entity_anchors
    entity_anchors = None
    if project_dir:
        anchors_path = Path(project_dir) / "entity_anchors.json"
        if anchors_path.exists():
            try:
                entity_anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"加载entity_anchors.json失败: {e}")
    
    v = check_word_frequency(chapter_text, word_blacklist, entity_anchors=entity_anchors)
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
    
    # 获取总章数（用于动态阈值）
    total_chapters = 50  # 默认值
    if project_dir:
        meta_path = Path(project_dir) / "story_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                total_chapters = meta.get("target_chapters", 50)
            except Exception:
                pass
    
    v = check_structure_diversity(
        current_text=chapter_text,
        previous_text=previous_chapter_text,
        previous_fingerprints=previous_fingerprints,
        event_fingerprints=event_fps,
        chapter_num=chapter_num,
        total_chapters=total_chapters,
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

    # 6.5 段落重复检测（防复读机死循环）
    repetition_violation = check_paragraph_repetition(chapter_text)
    if repetition_violation:
        result.add(repetition_violation)

    # 7. 设定漂移检测（warning：auto-generated关键词不可靠，仅作提醒）
    if concept_mapping:
        found_elems, missing_groups = check_setting_elements(
            chapter_text, [], concept_mapping=concept_mapping
        )
        if len(found_elems) == 0:
            result.add(GuardianViolation(
                rule="setting_drift",
                severity="info",
                description=f"设定漂移：本章未命中任何概念映射组。未命中组: {', '.join(missing_groups[:5])}",
                suggestion="考虑在正文中自然融入至少1个核心设定元素",
            ))
        elif len(missing_groups) > len(concept_mapping) * 0.7:
            result.add(GuardianViolation(
                rule="setting_drift_weak",
                severity="info",
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
        # 过滤掉"回忆/提及"场景 — 只算当前发生的代价
        repeated = [c for c in recent_costs
                     if c in chapter_text and not _is_past_mention(chapter_text, c)]
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

    # 12. 对话比例检查（动态阈值）
    v = check_dialogue_ratio(chapter_text, structure_type)
    if v:
        result.add(v)

    # 13. 物理打断锁检查（Cliffhanger强化版）
    v = check_physical_interruption_lock(chapter_text)
    if v:
        result.add(v)

    # 14. 高概念退化检测
    if project_dir or high_concept:
        degradation_violation = check_high_concept_degradation(
            chapter_text=chapter_text,
            project_dir=Path(project_dir) if project_dir else Path("."),
            high_concept=high_concept,
            recent_chapter_texts=recent_chapter_texts,
            chapter_num=chapter_num,
        )
        if degradation_violation:
            result.add(degradation_violation)

    # 15. 机械短句循环检测
    v = check_mechanical_short_sentences(
        chapter_text=chapter_text,
        recent_chapter_texts=recent_chapter_texts,
    )
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

def _detect_dialogue_content_type(chapter_text: str) -> list[str]:
    """检测章节中的对话内容类型（对峙/揭露/调查等），用于动态调整对话上限"""
    types = []

    # 对峙指标：角色间直接冲突、情绪对抗
    confrontation_indicators = [
        "杀了", "死了", "代价", "自首", "报仇", "恨", "原谅",
        "你骗", "你知道", "我告诉你", "真相", "秘密",
        "我老伴", "我妻子", "我丈夫", "我孩子",
        "遗体", "遗骨", "墙壁里", "封在", "活埋",
        "你跑了", "你没救", "你选择", "赎罪",
        "选择了", "不改", "改了会死",
    ]
    if sum(1 for w in confrontation_indicators if w in chapter_text) >= 3:
        types.append("confrontation")

    # 揭露指标：信息炸弹、真相揭示
    reveal_indicators = [
        "遗书", "日记", "报告", "名单", "证据", "档案",
        "十五年前", "坍塌事故", "偷工减料", "封在墙壁",
        "死亡指数", "结构性死亡概率", "事故调查", "竣工",
    ]
    if sum(1 for w in reveal_indicators if w in chapter_text) >= 3:
        types.append("reveal")

    return types


def check_dialogue_ratio(chapter_text: str, structure_type: str | None = None) -> GuardianViolation | None:
    """检查对话占比是否超标（动态阈值，混合结构自适应）"""
    import re
    
    # 提取对话内容（引号内的文字）
    dialogue_pattern = re.compile(r'[「\\\"\"](.*?)[」\\\"\"]')
    dialogues = dialogue_pattern.findall(chapter_text)
    
    # 计算对话字数
    dialogue_chars = sum(len(d) for d in dialogues)
    total_chars = len(chapter_text)
    
    if total_chars < 100:
        return None
    
    ratio = dialogue_chars / total_chars
    
    # 基础阈值：按结构类型设置不同上限
    # Guardian熔断红线（与constraint_injector.GUARDIAN_DIALOGUE_CAPS保持一致）
    DIALOGUE_CAPS = {
        "action_heavy": 0.25,
        "chase": 0.28,
        "suspense": 0.30,
        "investigation": 0.35,
        "confrontation": 0.40,
        "reveal": 0.40,
    }
    
    # 获取本章的基础对话比例上限
    base_cap = DIALOGUE_CAPS.get(structure_type or "", 0.35)

    # 混合结构自适应：检测章节实际内容，如果包含对峙/揭露元素则放宽上限
    content_types = _detect_dialogue_content_type(chapter_text)
    if content_types:
        # 取所有匹配内容类型的上限中的最大值
        content_caps = [DIALOGUE_CAPS.get(ct, 0.35) for ct in content_types]
        blended_cap = max(base_cap, max(content_caps))
        # 对混合结构给予额外5%容忍度（因为章节既有动作又有对峙）
        cap = min(blended_cap + 0.05, 0.45)  # 绝对上限45%
    else:
        cap = base_cap
    
    # 物证豁免：confrontation/reveal章节，35%-40%之间给予warning而非critical
    if ratio > cap:
        severity = "critical"
        # confrontation/reveal或混合结构的弹性容忍
        if (structure_type in ("confrontation", "reveal") or content_types) and ratio <= 0.45:
            severity = "warning"
        
        return GuardianViolation(
            rule="dialogue_ratio_critical",
            severity=severity,
            description=f"对话占比{ratio:.0%}（超过{cap:.0%}上限，结构类型: {structure_type or '未知'}{'+' + '+'.join(content_types) if content_types else ''}），剧情靠嘴炮推进",
            suggestion="用动作、读心、潜伏、偷听等方式替代直接对话。每2句对话后插入1段物理动作/环境变化。",
        )
    elif ratio > 0.30 and not content_types:
        # 只有纯动作/追逐章节才在30%时给warning
        return GuardianViolation(
            rule="dialogue_ratio_warning",
            severity="warning",
            description=f"对话占比{ratio:.0%}（超过30%），对话偏多",
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
        "震动", "颤抖", "摇晃", "崩塌",
        "断裂", "裂开", "碎了", "掉下来",
        "亮了", "灭了", "黑了", "闪了",
        "停了", "断了", "消失了", "出现了",
        "——", "……", "...",
    ]
    
    # 感官冲击元素
    sensory_indicators = [
        "血", "冰冷", "滚烫", "血腥",
        "嗡", "咔", "砰", "咚", "轰",
        "黑", "红", "白", "暗",
        "冰凉", "发麻", "刺痛", "发紧",
        "闷响", "巨响", "吱呀", "嘎吱",
        "气味", "味道", "铁锈", "霉味",
        "发抖", "颤抖", "攥紧", "松开",
    ]
    
    # 弱结尾模式（禁止）
    weak_endings = [
        "他不知道", "她不知道", "他想", "她想",
        "他沉默了", "她沉默了", "他看着", "她看着",
        "走进雨里", "走进黑暗", "走进夜色",
        "一切归于平静", "新世界开始了", "她闭上眼睛",
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


def check_paragraph_repetition(chapter_text: str) -> GuardianViolation | None:
    """
    检测段落级重复（防复读机死循环）
    
    检测逻辑：
    1. 将文本按段落分割
    2. 检测连续段落的相似度
    3. 检测同一句话出现次数
    4. 检测同一动作模式循环
    """
    import re
    
    # 按空行分割段落
    paragraphs = [p.strip() for p in chapter_text.split('\n\n') if p.strip()]
    
    if len(paragraphs) < 3:
        return None
    
    # 检测1：连续段落相似度（使用简化的n-gram比较）
    def get_ngrams(text: str, n: int = 3) -> set:
        """提取n-gram"""
        words = re.findall(r'[\u4e00-\u9fff]', text)
        return set(''.join(words[i:i+n]) for i in range(len(words)-n+1))
    
    def similarity(text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        ngrams1 = get_ngrams(text1)
        ngrams2 = get_ngrams(text2)
        if not ngrams1 or not ngrams2:
            return 0.0
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        return intersection / union if union > 0 else 0.0
    
    # 检测连续3个段落的相似度
    for i in range(len(paragraphs) - 2):
        sim1 = similarity(paragraphs[i], paragraphs[i+1])
        sim2 = similarity(paragraphs[i+1], paragraphs[i+2])
        
        if sim1 > 0.7 and sim2 > 0.7:
            return GuardianViolation(
                rule="paragraph_repetition_loop",
                severity="critical",
                description=f"检测到段落重复循环（位置{i}-{i+2}）：连续3段相似度>{70}%",
                suggestion="每200字必须有新信息推进，禁止原地打转。改变动作/对话/场景，推进剧情。",
            )
    
    # 检测2：同一句话出现次数
    sentences = re.split(r'[。！？]', chapter_text)
    sentence_counts = {}
    for sent in sentences:
        sent = sent.strip()
        if len(sent) > 10:  # 只检测较长的句子
            sentence_counts[sent] = sentence_counts.get(sent, 0) + 1
    
    for sent, count in sentence_counts.items():
        if count >= 3:
            return GuardianViolation(
                rule="sentence_repetition",
                severity="critical",
                description=f"检测到句子重复{count}次：'{sent[:30]}...'",
                suggestion="禁止复读同一句话。用不同的表达方式传达相同信息，或推进到新的剧情。",
            )
    
    # 检测3：高频短语重复（同一章内）
    phrase_patterns = [
        r'脸色变得苍白',
        r'手在发抖',
        r'他的手在发抖',
        r'王建国看着',
        r'陈默看着',
        r'你——',
    ]
    
    for pattern in phrase_patterns:
        count = len(re.findall(pattern, chapter_text))
        if count >= 4:
            return GuardianViolation(
                rule="phrase_repetition_critical",
                severity="critical",
                description=f"检测到高频短语重复：'{pattern}'出现{count}次",
                suggestion="替换为多样化的描写。同一个情绪/动作用不同的物理细节表达。",
            )
    
    return None


# ============================================================
# 14. 异常退化检测 (Anomaly Degradation Check)
# ============================================================

# 通用退化关键词（旧版兼容 + 扩展）
DEGRADATION_KEYWORDS = [
    "隐藏身份", "前刑警", "前兵王", "隐世神医", "隐藏首富", "卧底",
    "车祸失忆", "意外失忆", "系统开挂", "签到无敌", "天选之人", "天赋异禀",
]

# 异常被"解释回普通"的退化模式
ANOMALY_DEGRADATION_PATTERNS = [
    (r"原来只?是[一]?[个]?(?:幻觉|错觉|做梦|梦|心理作用|精神问题)", "异常被解释为幻觉/心理问题"),
    (r"不过是[一]?[个]?(?:幻觉|错觉|巧合)", "异常被解释为幻觉/巧合"),
    (r"其实(?:是|就是)(?:一种|某个|某种)?(?:科学|技术|算法|程序|传感器|监控)", "异常被降维为科技设备"),
    (r"不过是[一]?[个]?(?:传感器|监控|程序|系统)而?已", "异常被降维为普通设备"),
    (r"(?:原来|不过)[是就].*?(?:谋杀|凶杀|事故|案件)", "异常被降维为普通案件"),
    (r"并没有什么特别", "异常被否定"),
    (r"根本不存在", "异常被否定"),
    (r"(?:一切|所有).*?(?:正常|普通|平常)", "异常被正常化"),
]


def check_high_concept_degradation(
    chapter_text: str,
    project_dir: Path,
    high_concept: dict | None = None,
    recent_chapter_texts: list[str] | None = None,
    chapter_num: int = 0,
) -> GuardianViolation | None:
    """
    检测高概念退化（升级版 v2）。

    四层检查：
    1. 通用退化关键词 — 隐藏身份/失忆/系统开挂等俗套
    2. 异常退化话术 — "原来是幻觉/传感器/巧合"等解释回普通
    3. 视觉锚点存续 — 异常的可视化元素是否还在使用
    4. banned_patterns 违反
    """
    # 优先用传入的 high_concept，否则从文件加载
    if not high_concept and project_dir:
        meta_path = Path(project_dir) / "story_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                high_concept = meta.get("high_concept", {})
            except Exception:
                pass

    if not high_concept:
        return None

    anomaly = high_concept.get("anomaly", "")
    visual_anchor_keywords = high_concept.get("visual_anchor_keywords", [])
    banned_patterns = high_concept.get("banned_patterns", [])
    violations = []

    # === 1. 通用退化关键词 ===
    found_kw = [kw for kw in DEGRADATION_KEYWORDS if kw in chapter_text]
    if found_kw:
        violations.append(f"退化关键词: {', '.join(found_kw[:3])}")

    # === 2. 异常退化话术 ===
    for pattern, reason in ANOMALY_DEGRADATION_PATTERNS:
        matches = re.findall(pattern, chapter_text)
        if matches:
            violations.append(f"退化话术: '{matches[0]}' ({reason})")

    # === 3. 视觉锚点存续 ===
    if visual_anchor_keywords and chapter_num >= 5 and recent_chapter_texts:
        has_visual_anchor = any(kw in chapter_text for kw in visual_anchor_keywords)
        if not has_visual_anchor:
            recent_has_anchor = any(
                any(kw in text for kw in visual_anchor_keywords)
                for text in recent_chapter_texts[-5:]
            )
            if not recent_has_anchor:
                violations.append(
                    f"视觉锚点消失: 最近5章未出现 {visual_anchor_keywords}"
                )

    # === 4. banned_patterns ===
    for pattern in banned_patterns:
        if pattern in chapter_text:
            violations.append(f"违反banned_pattern: '{pattern}'")

    if not violations:
        return None

    has_degradation = any("退化话术" in v or "退化关键词" in v for v in violations)
    severity = "critical" if has_degradation else "warning"

    return GuardianViolation(
        rule="anomaly_degradation",
        severity=severity,
        description=f"异常退化检测({len(violations)}项): {'; '.join(violations[:3])}",
        suggestion=(
            f"本剧核心异常是「{anomaly}」。"
            "禁止解释回普通（幻觉/巧合/传感器/普通案件）。"
            "保持异常的不可名状性，只能揭示'规则'不能揭示'本质'。"
        ),
    )


# ============================================================
# 15. 机械短句循环检测
# ============================================================

def check_mechanical_short_sentences(
    chapter_text: str,
    recent_chapter_texts: list[str] | None = None,
) -> GuardianViolation | None:
    """
    检测结尾机械短句循环（"嗯/好/你骗我/我知道"类）。

    规则：
    - 结尾5行内，连续3+句≤3字 → WARNING
    - 连续2章结尾都是短句循环 → FAIL
    """
    lines = [l.strip() for l in chapter_text.split("\n") if l.strip() and not l.startswith("#")]
    if not lines:
        return None

    last_lines = lines[-5:]
    consecutive_short = 0
    max_consecutive = 0
    for line in last_lines:
        clean = re.sub(r"[^\w]", "", line)
        if 0 < len(clean) <= 3:
            consecutive_short += 1
            max_consecutive = max(max_consecutive, consecutive_short)
        else:
            consecutive_short = 0

    if max_consecutive >= 3:
        if recent_chapter_texts:
            prev_short_too = False
            for prev_text in recent_chapter_texts[-2:]:
                prev_lines = [l.strip() for l in prev_text.split("\n") if l.strip() and not l.startswith("#")]
                prev_last = prev_lines[-5:] if prev_lines else []
                prev_consecutive = 0
                prev_max = 0
                for line in prev_last:
                    clean = re.sub(r"[^\w]", "", line)
                    if 0 < len(clean) <= 3:
                        prev_consecutive += 1
                        prev_max = max(prev_max, prev_consecutive)
                    else:
                        prev_consecutive = 0
                if prev_max >= 3:
                    prev_short_too = True
                    break
            if prev_short_too:
                return GuardianViolation(
                    rule="mechanical_short_sentences",
                    severity="critical",
                    description=f"连续多章结尾使用机械短句循环（连续{max_consecutive}句≤3字）",
                    suggestion="结尾需要具体的感官画面或未回答的问题，不能用'嗯/好/你骗我'等短句循环撑篇幅",
                )

        return GuardianViolation(
            rule="mechanical_short_sentences",
            severity="warning",
            description=f"结尾出现{max_consecutive}句连续短句（≤3字）",
            suggestion="用具体感官画面或物理打断替代短句循环",
        )

    return None


# ============================================================
# 新增：实体关系一致性检查（防止人物设定漂移）
# ============================================================

def check_entity_consistency(
    chapter_text: str,
    project_dir: str | Path,
) -> GuardianViolation | None:
    """检查章节内容是否违反实体关系锁"""
    entity_graph_path = Path(project_dir) / "entity_graph.json"
    if not entity_graph_path.exists():
        return None

    try:
        entity_graph = json.loads(entity_graph_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"加载entity_graph.json失败: {e}")
        return None

    # 检查禁止的组合
    forbidden_combinations = entity_graph.get("forbidden_combinations", [])
    for combo in forbidden_combinations:
        for entity, forbidden_relation in combo.items():
            # 检查实体是否存在
            if entity in chapter_text:
                # 检查是否包含禁止的关系描述
                # 构建检测模式
                patterns = [
                    f"{entity}.*{forbidden_relation}",
                    f"{forbidden_relation}.*{entity}",
                    f"{entity}是{forbidden_relation}",
                    f"{forbidden_relation}是{entity}",
                    f"{entity}的{forbidden_relation}",
                    f"{forbidden_relation}的{entity}",
                ]

                for pattern in patterns:
                    if re.search(pattern, chapter_text):
                        return GuardianViolation(
                            rule="entity_consistency",
                            severity="critical",
                            description=f"实体关系冲突：检测到「{entity}」与「{forbidden_relation}」的非法组合",
                            suggestion=f"根据entity_graph.json的设定，「{entity}」不能是「{forbidden_relation}」。请修正人物关系。",
                        )

    # 检查硬规则
    hard_rules = entity_graph.get("hard_rules", [])
    for rule in hard_rules:
        # 从规则中提取关键信息
        # 例如："严禁将张德胜描述为周鸣岐的父亲！周鸣岐的父亲是周建国（工号037）"
        if "严禁" in rule and "！" in rule:
            # 提取禁止的内容
            parts = rule.split("！")
            if len(parts) >= 2:
                forbidden_part = parts[0].replace("严禁", "").strip()
                # 检查是否违反
                if forbidden_part in chapter_text:
                    return GuardianViolation(
                        rule="entity_consistency",
                        severity="critical",
                        description=f"实体关系冲突：违反硬规则「{rule}」",
                        suggestion=f"请严格遵守entity_graph.json中的硬规则。",
                    )

    return None
