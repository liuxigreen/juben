"""
P0-2: 代价表现锁（Cost Anchor Lock）

解决问题：记忆消失"写虚"——只写"想不起来"却没有可拍的物理痕迹变化。
核心规则：记忆类代价必须伴随可拍痕迹/道具变化。

检测逻辑：
- 扫描章节文本，检测记忆缺失关键词
- 检查同段是否有可拍痕迹/道具变化
- 缺失则触发warning
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# 记忆缺失关键词（触发检测）
MEMORY_LOSS_KEYWORDS = [
    "想不起来", "记不清", "忘了", "忘记", "不记得", "记忆模糊",
    "记不起", "想不起", "回忆不起来", "印象模糊", "好像忘了",
    "突然想不起来", "怎么也想不起", "怎么都想不起",
]

# 可拍痕迹/道具关键词（必须至少出现一个）
ANCHOR_KEYWORDS = [
    # 痕迹变化
    "淡了", "消失", "没了", "不见了", "模糊了", "变浅", "变淡",
    "少了一笔", "缺了一角", "褪色", "消散",
    # 道具特写
    "便签", "字迹", "疤痕", "手背", "左手", "照片", "杯子",
    "杯壁", "茶水", "钥匙", "手机屏幕", "镜子", "猫",
    # 身体反应
    "发抖", "颤抖", "冰凉", "发麻", "刺痛", "疼",
    "心跳", "呼吸", "瞳孔",
    # 环境变化
    "灯闪", "灭了", "暗了", "响了", "震了", "碎了",
]

# 变化动词（必须搭配道具才算合规）
CHANGE_VERBS = [
    "淡了", "消失了", "没了", "不见了", "模糊了", "变浅", "变淡",
    "少了一笔", "缺了一角", "褪色", "光滑", "干净",
    "还在", "消失了", "模糊", "淡了一个",
]


@dataclass
class CostAnchorViolation:
    """代价表现违规"""
    chapter_num: int
    paragraph_index: int
    memory_keyword: str
    paragraph_text: str
    has_anchor: bool


class CostAnchorChecker:
    """
    代价表现检查器。
    
    规则：
    1. 出现记忆缺失关键词时，同段必须有可拍痕迹/道具变化
    2. 禁止只写"她想不起来"没有物理载体
    """

    def check_chapter(self, chapter_num: int, text: str) -> list[CostAnchorViolation]:
        """检查整章"""
        violations = []
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

        for i, para in enumerate(paragraphs):
            # 检测记忆缺失关键词
            memory_kws = [kw for kw in MEMORY_LOSS_KEYWORDS if kw in para]
            if not memory_kws:
                continue

            # 检查同段是否有「变化动词 + 道具」才算合规
            # 只提及道具不算，必须有物理变化
            has_anchor = False
            for anchor_kw in ANCHOR_KEYWORDS:
                if anchor_kw in para:
                    # 检查该道具附近是否有变化动词
                    anchor_idx = para.find(anchor_kw)
                    context = para[max(0, anchor_idx-20):anchor_idx+len(anchor_kw)+20]
                    if any(v in context for v in CHANGE_VERBS):
                        has_anchor = True
                        break

            if not has_anchor:
                violations.append(CostAnchorViolation(
                    chapter_num=chapter_num,
                    paragraph_index=i,
                    memory_keyword=memory_kws[0],
                    paragraph_text=para[:100],
                    has_anchor=False,
                ))

        return violations

    def get_injection_text(self, chapter_num: int) -> str:
        """生成代价表现锁注入文本"""
        return """### 代价表现锁（强制）

**核心规则**：凡是涉及记忆消失/模糊的描写，**必须同时出现可拍的物理痕迹或道具变化**。

**正确示范**：
- 她想不起来那只猫叫什么名字了（记忆）→ 她低头看左手手背，疤痕还在，但旁边的痣不见了（可拍痕迹）
- 便签上的字迹淡了一个笔画（道具变化）→ 她盯着那个笔画，确定刚才还在（记忆确认）

**禁止的写法**：
- 只写"她想不起来"没有物理载体
- 只写"记忆模糊了"没有对应的痕迹/道具变化
- 纯内心独白式的记忆缺失

**自检公式**：如果本章出现"想不起来/记不清/忘了"，检查同段是否有便签/疤痕/字迹/照片/杯壁等具体道具的视觉变化。没有 = 违规。
"""

    def format_violations(self, violations: list[CostAnchorViolation]) -> str:
        """格式化违规报告"""
        if not violations:
            return ""
        lines = ["代价表现违规:"]
        for v in violations:
            lines.append(
                f"  段落{v.paragraph_index}: 「{v.memory_keyword}」"
                f"缺少可拍痕迹 | {v.paragraph_text}"
            )
        return "\n".join(lines)
