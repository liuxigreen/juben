"""
反AI味检查器 — 纯Python实现，不依赖LLM

检查项：
1. 禁用词扫描
2. 禁用句式正则匹配
3. Show/Tell比例估算
4. 感官密度检查
5. 对话指纹区分度
"""
from __future__ import annotations

import re
from collections import Counter

from juben.state.schema import Severity, ValidationResult, Violation, ViolationType


# ============================================================
# 禁用词表
# ============================================================

BANNED_WORDS = {
    # 绝对禁用
    "quietly", "deeply", "fundamentally", "remarkably", "arguably",
    "delve", "certainly", "utilize", "leverage", "robust", "streamline", "harness",
    "tapestry", "landscape", "paradigm", "synergy", "ecosystem", "framework",
    # 中文AI味词汇
    "值得注意的是", "不得不说", "事实上", "归根结底", "总而言之",
    "令人惊讶的是", "毫无疑问", "显而易见", "众所周知",
    "仿佛置身于", "如同一幅画卷", "宛如", "恰似",
}

BANNED_PATTERNS_EN = [
    r"It'?s not\s+\w+\s*[-—–]\s*it'?s\s+\w+",
    r"It wasn'?t just\s+\w+.*it was\s+\w+",
    r"Here'?s the thing:",
    r"The truth is:",
    r"The reality is:",
    r"Little did \w+ know",
    r"In that moment, everything changed",
    r"At the end of the day",
    r"It'?s worth noting",
    r"Needless to say",
]

BANNED_PATTERNS_ZH = [
    r"不是.{1,10}[，,]而是",
    r"事实上[，,]",
    r"不得不说[，,]",
    r"那一刻[，,]一切都变了",
    r"她不知道的是[，,]",
    r"他不知道的是[，,]",
    r"故事还要从",
    r"这一切都要从",
]

# ============================================================
# 感官词库
# ============================================================

SENSORY_WORDS = {
    "visual": [
        "看", "见", "望", "盯", "瞪", "瞄", "瞅", "瞥",
        "红", "白", "黑", "金", "银", "暗", "亮", "光",
        "色", "影", "形", "圆", "尖", "弯", "直",
        "刺眼", "昏暗", "耀眼", "朦胧", "模糊", "清晰",
    ],
    "auditory": [
        "听", "响", "声", "音", "吼", "喊", "叫", "哭", "笑",
        "轰", "砰", "啪", "嘶", "嗡", "滴", "嗒",
        "安静", "寂静", "喧闹", "嘈杂", "沉寂",
    ],
    "tactile": [
        "摸", "触", "碰", "握", "抓", "捏", "掐", "挠",
        "热", "冷", "凉", "烫", "冰", "温",
        "痛", "痒", "麻", "酸", "胀",
        "硬", "软", "滑", "粗", "涩",
    ],
    "olfactory": [
        "闻", "香", "臭", "腥", "酸", "呛",
        "气味", "味道", "气息",
    ],
    "gustatory": [
        "尝", "吃", "喝", "甜", "苦", "辣", "咸", "涩",
        "吞", "咽", "嚼", "咬",
    ],
}


class AntiAIChecker:
    """反AI味检查器 — 纯Python，不调LLM"""

    def check(self, text: str) -> ValidationResult:
        violations = []

        # 1. 禁用词
        violations.extend(self._check_banned_words(text))

        # 2. 禁用句式
        violations.extend(self._check_banned_patterns(text))

        # 3. Show/Tell比例
        violations.extend(self._check_show_tell(text))

        # 4. 感官密度
        violations.extend(self._check_sensory_density(text))

        # 5. 句式变化
        violations.extend(self._check_sentence_variety(text))

        passed = not any(v.severity == Severity.CRITICAL for v in violations)
        score = max(0, 10.0 - len(violations) * 1.5)

        return ValidationResult(
            passed=passed,
            violations=violations,
            score=min(10.0, score),
        )

    def _check_banned_words(self, text: str) -> list[Violation]:
        violations = []
        text_lower = text.lower()
        for word in BANNED_WORDS:
            if word.lower() in text_lower:
                violations.append(Violation(
                    type=ViolationType.CHARACTER_INCONSISTENCY,
                    severity=Severity.WARNING,
                    description=f"检测到禁用词: '{word}'",
                    suggestion=f"用具体动作/细节替换抽象词汇",
                ))
        return violations

    def _check_banned_patterns(self, text: str) -> list[Violation]:
        violations = []
        all_patterns = BANNED_PATTERNS_EN + BANNED_PATTERNS_ZH
        for pattern in all_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                violations.append(Violation(
                    type=ViolationType.CHARACTER_INCONSISTENCY,
                    severity=Severity.WARNING,
                    description=f"检测到禁用句式: '{match.group()}'",
                    suggestion="用情节转折代替句式套路",
                ))
        return violations

    def _check_show_tell(self, text: str) -> list[Violation]:
        """
        Show/Tell比例估算。
        简化方法：统计"告诉"性动词和"展示"性描写的比率。
        """
        violations = []

        # "告诉"性词汇（叙述而非展示）
        tell_markers = [
            "感到", "觉得", "认为", "意识到", "明白", "知道",
            "非常", "十分", "极其", "特别", "格外",
            "突然意识到", "不禁感叹", "心中暗想",
        ]
        # "展示"性词汇（动作/感官/对白）
        show_markers = [
            "说", "喊", "叫", "笑", "哭", "握", "看",
            "站", "坐", "走", "跑", "转", "推", "拉",
            "「", "」", "\"", "\"",  # 对话标记
        ]

        tell_count = sum(text.count(m) for m in tell_markers)
        show_count = sum(text.count(m) for m in show_markers)

        total = tell_count + show_count
        if total > 0:
            show_ratio = show_count / total
            if show_ratio < 0.5:
                violations.append(Violation(
                    type=ViolationType.CHARACTER_INCONSISTENCY,
                    severity=Severity.CRITICAL,
                    description=f"Show/Tell比例过低: {show_ratio:.0%}（目标>70%）",
                    suggestion="把叙述性描写改为具体动作和对白",
                ))
            elif show_ratio < 0.7:
                violations.append(Violation(
                    type=ViolationType.CHARACTER_INCONSISTENCY,
                    severity=Severity.WARNING,
                    description=f"Show/Tell比例偏低: {show_ratio:.0%}（目标>70%）",
                    suggestion="增加具体动作和感官细节",
                ))

        return violations

    def _check_sensory_density(self, text: str) -> list[Violation]:
        """检查每1000字是否包含足够多的感官描写"""
        violations = []

        # 统计各类感官词出现次数
        found_senses = set()
        for sense_type, words in SENSORY_WORDS.items():
            for word in words:
                if word in text:
                    found_senses.add(sense_type)

        if len(found_senses) < 3:
            violations.append(Violation(
                type=ViolationType.CHARACTER_INCONSISTENCY,
                severity=Severity.WARNING,
                description=f"感官描写不足: 仅涉及{len(found_senses)}种感官（目标≥3种）",
                suggestion=f"缺少: {', '.join(set(SENSORY_WORDS.keys()) - found_senses)}",
            ))

        return violations

    def _check_sentence_variety(self, text: str) -> list[Violation]:
        """检查句子长度是否有变化（避免全是长句或全是短句）"""
        violations = []

        # 按中文句号/问号/感叹号分句
        sentences = re.split(r'[。！？!?]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 2]

        if len(sentences) < 3:
            return violations

        lengths = [len(s) for s in sentences]
        avg = sum(lengths) / len(lengths)
        # 如果平均长度>80且标准差<15，说明句式单调
        if avg > 80:
            std = (sum((l - avg) ** 2 for l in lengths) / len(lengths)) ** 0.5
            if std < 15:
                violations.append(Violation(
                    type=ViolationType.CHARACTER_INCONSISTENCY,
                    severity=Severity.INFO,
                    description=f"句式变化不足: 平均{avg:.0f}字/句，标准差{std:.0f}",
                    suggestion="穿插短句（3-10字）打破节奏",
                ))

        return violations
