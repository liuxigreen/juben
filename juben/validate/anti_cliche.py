"""
反套路检查器 — 正则+关键词匹配，检测常见烂梗

与anti_cliche_blacklist配合：
1. 内置20个高频致命烂梗（硬编码）
2. 项目级blacklist（用户/LLM可扩展）
3. 匹配即熔断
"""
from __future__ import annotations

import re

from juben.state.schema import Severity, ValidationResult, Violation, ViolationType


# ============================================================
# 内置20个高频致命烂梗
# ============================================================

BUILTIN_CLICHES = [
    {
        "id": "cliche_001",
        "name": "属下下跪反转",
        "pattern": r"(属下|保镖|手下|黑衣人).{0,20}(跪|下跪|单膝).{0,10}(全场|众人|所有人)",
        "description": "被当众羞辱时属下赶到下跪来反转",
    },
    {
        "id": "cliche_002",
        "name": "令牌震惊",
        "pattern": r"(掏出|亮出|拿出).{0,10}(令牌|黑卡|龙王|虎符|玉佩).{0,20}(震惊|哗然|不敢相信|脸色大变)",
        "description": "主角掏出身份令牌让全场震惊",
    },
    {
        "id": "cliche_003",
        "name": "反派降智话多",
        "pattern": r"(反派|他|她).{0,10}(冷笑|得意|狂笑).{0,30}(告诉你|实话告诉你|死个明白)",
        "description": "反派死于话多，告诉主角关键信息",
    },
    {
        "id": "cliche_004",
        "name": "退婚打脸",
        "pattern": r"(退婚|解除婚约|配不上).{0,30}(震惊|后悔|刮目相看)",
        "description": "退婚流套路，对方后来后悔",
    },
    {
        "id": "cliche_005",
        "name": "废物觉醒",
        "pattern": r"(废物|垃圾|没用的东西).{0,20}(觉醒|崛起|突然爆发)",
        "description": "被叫废物然后突然觉醒变强",
    },
    {
        "id": "cliche_006",
        "name": "天降系统",
        "pattern": r"(叮|恭喜|检测到).{0,10}(系统|面板|任务).{0,10}(激活|绑定|开启)",
        "description": "系统突然出现没有任何铺垫",
    },
    {
        "id": "cliche_007",
        "name": "装逼被打脸-爽文公式",
        "pattern": r"(嘲笑|看不起|不自量力).{0,40}(打脸|碾压|秒杀|一拳)",
        "description": "被嘲笑→打脸的烂俗公式",
    },
    {
        "id": "cliche_008",
        "name": "巧合推进",
        "pattern": r"(恰好|刚好|正好|凑巧).{0,15}(听到|看到|遇到|撞见)",
        "description": "用巧合推进剧情而非角色行动",
    },
    {
        "id": "cliche_009",
        "name": "顿悟式转折",
        "pattern": r"(那一刻|这一瞬间|此时此刻).{0,10}(明白|顿悟|恍然大悟|一切都变了)",
        "description": "用顿悟代替具体的认知变化过程",
    },
    {
        "id": "cliche_010",
        "name": "死亡flag",
        "pattern": r"(打完这仗|等我回来|这次一定).{0,10}(就|回去|退休|结婚)",
        "description": "立flag然后马上死的套路",
    },
    {
        "id": "cliche_011",
        "name": "误会推动",
        "pattern": r"(误会|误解).{0,10}(不听解释|转身就走|摔门而去)",
        "description": "用误会而非真实冲突推动剧情",
    },
    {
        "id": "cliche_012",
        "name": "主角光环不死",
        "pattern": r"(致命|必死|无法逃脱).{0,20}(奇迹|突然|意外).{0,10}(活下来|幸存|被救)",
        "description": "必死局面靠光环存活",
    },
    {
        "id": "cliche_013",
        "name": "三段论解决",
        "pattern": r"(想通了|想明白了|终于懂了).{0,10}(于是|所以|因此).{0,10}(问题迎刃而解|一切都解决了)",
        "description": "想通→顿悟→解决，没有代价",
    },
    {
        "id": "cliche_014",
        "name": "旁白式内心",
        "pattern": r"(他的内心|她的心中|心中暗想).{0,5}(涌起|泛起|充满).{0,10}(复杂|感慨|万千)",
        "description": "用旁白代替展示内心活动",
    },
    {
        "id": "cliche_015",
        "name": "外貌描写模板",
        "pattern": r"(剑眉星目|面如冠玉|肤若凝脂|倾国倾城|英俊潇洒)",
        "description": "模板化外貌描写",
    },
    {
        "id": "cliche_016",
        "name": "震惊体",
        "pattern": r"(全场震惊|众人哗然|不敢相信自己的眼睛|这怎么可能)",
        "description": "用'震惊'代替具体反应",
    },
    {
        "id": "cliche_017",
        "name": "回忆杀拖时长",
        "pattern": r"(回忆|往事|曾经).{0,5}(涌上心头|浮现|闪过).{0,20}(那一年|那时候|当年)",
        "description": "用大段回忆填充字数",
    },
    {
        "id": "cliche_018",
        "name": "实力碾压公式",
        "pattern": r"(一个眼神|一根手指|轻轻一).{0,10}(秒杀|碾压|击败|弹飞)",
        "description": "毫无悬念的实力碾压，没有戏剧张力",
    },
    {
        "id": "cliche_019",
        "name": "女主工具人",
        "pattern": r"(女主|她).{0,10}(被|遭到|陷入危险).{0,10}(等待|期待).{0,10}(男主|他).{0,10}(来救|出现|赶到)",
        "description": "女主沦为等待被救的工具人",
    },
    {
        "id": "cliche_020",
        "name": "隐世高手",
        "pattern": r"(老头|老人|老者).{0,10}(不起眼|普通|邋遢).{0,20}(其实|真实身份|竟然是).{0,10}(高手|大师|隐世)",
        "description": "不起眼老人其实是隐世高手",
    },
]


class AntiClicheChecker:
    """反套路检查器 — 正则匹配 + 项目级黑名单"""

    def __init__(self, project_blacklist: list[str] | None = None):
        self.builtin = BUILTIN_CLICHES
        self.project_blacklist = project_blacklist or []

    def check(self, text: str) -> ValidationResult:
        violations = []

        # 1. 检查内置烂梗
        for cliche in self.builtin:
            match = re.search(cliche["pattern"], text)
            if match:
                violations.append(Violation(
                    type=ViolationType.CLICHE_DETECTED,
                    severity=Severity.CRITICAL,
                    description=f"触发烂梗 [{cliche['name']}]: {cliche['description']}",
                    location=f"匹配: '{match.group()[:50]}'",
                    suggestion="用角色行动和具体细节替代套路",
                ))

        # 2. 检查项目级黑名单（关键词匹配）
        for banned in self.project_blacklist:
            # 把黑名单条目当作关键词组，检查是否同时出现多个关键词
            keywords = banned.split("时") if "时" in banned else [banned]
            if all(any(kw in text for kw in [k.strip()]) for k in keywords if k.strip()):
                violations.append(Violation(
                    type=ViolationType.CLICHE_DETECTED,
                    severity=Severity.CRITICAL,
                    description=f"触发项目黑名单: {banned}",
                    suggestion="替换为非套路情节",
                ))

        passed = not any(v.severity == Severity.CRITICAL for v in violations)
        score = max(0, 10.0 - len(violations) * 3.0)

        return ValidationResult(
            passed=passed,
            violations=violations,
            score=min(10.0, score),
        )
