"""
Cliffhanger验证器 — 检查章节结尾是否构成有效的翻页理由

核心区分：场景切割 ≠ Cliffhanger
- ❌ 场景切割：只是画面结束，读者脑中没有具体问题
- ✅ 真Cliffhanger：读者必须带着一个具体的未回答问题离开

5种公式：Reveal / Decision / Turn / Mid-Crisis Cut / Ticking Clock
"""
from __future__ import annotations

import re

from juben.state.schema import (
    CliffhangerType, Severity, ValidationResult, Violation, ViolationType,
)


# 弱Cliffhanger的信号
WEAK_SIGNALS = [
    (r"故事还在继续", "太模糊"),
    (r"他不知道接下来会发生什么", "叙述而非展示"),
    (r"她不知道接下来会怎样", "叙述而非展示"),
    (r"门关上了。?$", "纯场景结束"),
    (r"天黑了。?$", "纯场景结束"),
    (r"他转身离开了。?$", "纯场景结束"),
    (r"一切归于平静。?$", "纯场景结束"),
    (r"就这样。?$", "太模糊"),
    (r"未完待续", "廉价悬念"),
    (r"且听下回分解", "廉价悬念"),
]

# 强Cliffhanger的信号
STRONG_SIGNALS = {
    CliffhangerType.REVEAL: [
        r"(原来|竟然|没想到|居然是|落款|署名|真相)",
        r"(她.{0,5}看到|他.{0,5}发现|打开|揭开).{0,20}(信|照片|文件|真相|秘密)",
    ],
    CliffhangerType.DECISION: [
        r"(必须.{0,5}选择|两个.{0,5}只能选|答应还是|答应吗|答应他吗)",
        r"(握着|拿着|举起).{0,10}(枪|刀|钥匙|合同).{0,10}(对准|指向)",
    ],
    CliffhangerType.TURN: [
        r"(站着的|出现的|等在那里的).{0,10}(竟然是|不是|而是|正是)",
        r"(原来|其实).{0,10}(一直|从一开始)",
    ],
    CliffhangerType.MID_CRISIS: [
        r"(刀|剑|子弹|拳|掌).{0,5}(距离|离|逼近|飞向).{0,10}(喉咙|心脏|脸|头)",
        r"(——|…|\.{3}|。$)",
    ],
    CliffhangerType.TICKING_CLOCK: [
        r"(\d+[:：]\d+|倒计时|最后.{0,5}秒|还剩)",
        r"(来不及|没时间|只剩)",
    ],
}


class CliffhangerValidator:
    """Cliffhanger验证器"""

    def check(self, text: str, expected_type: CliffhangerType | None = None) -> ValidationResult:
        """
        检查文本末尾是否构成有效Cliffhanger。

        Args:
            text: 章节全文
            expected_type: 期望的Cliffhanger类型（可选）
        """
        violations = []

        # 提取最后300字
        last_300 = text[-300:] if len(text) > 300 else text
        last_100 = text[-100:] if len(text) > 100 else text

        # 1. 检查弱Cliffhanger信号
        for pattern, reason in WEAK_SIGNALS:
            if re.search(pattern, last_100):
                violations.append(Violation(
                    type=ViolationType.CLIFFHANGER_WEAK,
                    severity=Severity.CRITICAL,
                    description=f"弱Cliffhanger: {reason}",
                    location=f"结尾匹配: '{pattern}'",
                    suggestion="用具体的未回答问题替代模糊结束",
                ))

        # 2. 检查强Cliffhanger信号
        detected_type = None
        for ctype, patterns in STRONG_SIGNALS.items():
            for pattern in patterns:
                if re.search(pattern, last_300):
                    detected_type = ctype
                    break
            if detected_type:
                break

        if detected_type is None:
            violations.append(Violation(
                type=ViolationType.CLIFFHANGER_WEAK,
                severity=Severity.WARNING,
                description="未检测到明确的Cliffhanger信号",
                suggestion="在结尾植入一个具体的未回答问题",
            ))

        # 3. 如果指定了类型，检查是否匹配
        if expected_type and detected_type and detected_type != expected_type:
            violations.append(Violation(
                type=ViolationType.CLIFFHANGER_WEAK,
                severity=Severity.INFO,
                description=f"Cliffhanger类型不匹配: 期望{expected_type.value}，实际检测到{detected_type.value}",
            ))

        # 4. 检查结尾是否包含问号（最简单的悬念信号）
        has_question = bool(re.search(r'[？?]$', last_100.strip()))
        if not has_question and detected_type is None:
            violations.append(Violation(
                type=ViolationType.CLIFFHANGER_WEAK,
                severity=Severity.WARNING,
                description="结尾没有问句，也没有检测到Cliffhanger模式",
                suggestion="考虑在最后一句植入悬念性问句",
            ))

        passed = not any(v.severity == Severity.CRITICAL for v in violations)
        score = 10.0 if (passed and detected_type) else max(0, 10.0 - len(violations) * 2.5)

        return ValidationResult(
            passed=passed,
            violations=violations,
            score=min(10.0, score),
        )
