"""
Scribe Constraint Injector — Scribe生成前强制动态注入

核心思想：事前熔断 > 事后检查
在Scribe生成prompt之前，强制注入：
1. 动态黑名单（近期高频短语）
2. 本章必须完成的大厂元素清单
3. 身体状态检查（代价累积）
4. 禁止结构模板列表
5. 短剧节奏硬指标
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .validate.dynamic_blacklist import (
    build_dynamic_blacklist,
    scan_chapter_for_blacklist,
    load_blacklist,
    save_blacklist,
    SEED_BLACKLIST,
)

logger = logging.getLogger(__name__)


class ConstraintInjector:
    """Scribe约束注入器"""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.blacklist_path = self.project_dir / "dynamic_blacklist.txt"
        self.curator_state_path = self.project_dir / "curator_state.json"
        self.concept_mapping_path = self.project_dir / "concept_mapping.json"
        self.cost_history_path = self.project_dir / "cost_history.json"

    def build_injection_block(
        self,
        chapter_num: int,
        previous_chapters: list[str] | None = None,
    ) -> str:
        """
        构建约束注入文本块，用于插入Scribe prompt。

        Returns:
            格式化的约束文本
        """
        blocks = []

        # 1. 动态黑名单
        blacklist = self._get_dynamic_blacklist(previous_chapters)
        if blacklist:
            blacklist_text = self._format_blacklist(blacklist)
            blocks.append(blacklist_text)

        # 2. 大厂元素清单
        setting_injection = self._build_setting_injection(chapter_num)
        if setting_injection:
            blocks.append(setting_injection)

        # 3. 身体状态检查
        body_state = self._build_body_state_injection(chapter_num)
        if body_state:
            blocks.append(body_state)

        # 4. 禁止结构模板
        structure_ban = self._build_structure_ban(chapter_num)
        if structure_ban:
            blocks.append(structure_ban)

        # 5. 短剧节奏硬指标
        rhythm_requirements = self._build_rhythm_requirements(chapter_num)
        if rhythm_requirements:
            blocks.append(rhythm_requirements)

        return "\n\n".join(blocks)

    def _get_dynamic_blacklist(self, previous_chapters: list[str] | None = None) -> list[str]:
        """获取动态黑名单"""
        # 尝试从文件加载
        if self.blacklist_path.exists():
            return load_blacklist(self.blacklist_path)

        # 如果有历史章节，动态生成
        if previous_chapters:
            blacklist = build_dynamic_blacklist(previous_chapters)
            save_blacklist(blacklist, self.blacklist_path)
            return blacklist

        # 使用种子黑名单
        return SEED_BLACKLIST.copy()

    def _format_blacklist(self, blacklist: list[str]) -> str:
        """格式化黑名单为prompt注入文本"""
        # 只取前30个，避免prompt过长
        top_phrases = blacklist[:30]
        phrases_str = "、".join(f'"{p}"' for p in top_phrases)

        return f"""### 🚫 动态禁用词库（检测到即判定任务失败）

以下短语已被系统标记为高频AI味词汇，绝对禁止在本章中使用：
{phrases_str}

**惩罚机制**：如果本章出现以上任何短语，系统将自动判定任务失败，需要重新生成。
请用具体的、独特的、符合场景的描写替代这些通用表达。"""

    def _build_setting_injection(self, chapter_num: int) -> str:
        """构建大厂元素强制注入"""
        # 读取concept_mapping
        if not self.concept_mapping_path.exists():
            return ""

        try:
            mapping = json.loads(self.concept_mapping_path.read_text(encoding='utf-8'))
        except Exception:
            return ""

        # 提取核心概念组
        concept_groups = mapping.get("concept_groups", mapping.get("groups", []))
        if not concept_groups:
            return ""

        # 根据章节选择必须出现的概念（轮转）
        required_groups = []
        for i, group in enumerate(concept_groups):
            if (chapter_num + i) % 3 == 0:  # 每3章轮转一次
                group_name = group.get("name", "")
                keywords = group.get("keywords", [])
                if group_name and keywords:
                    required_groups.append((group_name, keywords[:5]))

        if not required_groups:
            return ""

        lines = ["### 🏢 本章必须出现的大厂元素（至少命中1组）"]
        lines.append("")
        for name, keywords in required_groups:
            kw_str = "、".join(keywords)
            lines.append(f"- **{name}**：{kw_str}")

        lines.append("")
        lines.append("以上元素必须自然融入剧情，不能生硬插入。可以通过对话、动作、环境描写等方式体现。")

        return "\n".join(lines)

    def _build_body_state_injection(self, chapter_num: int) -> str:
        """构建身体状态注入"""
        # 读取curator_state
        if not self.curator_state_path.exists():
            return ""

        try:
            state = json.loads(self.curator_state_path.read_text(encoding='utf-8'))
        except Exception:
            return ""

        body_state = state.get("body_state", {})
        if not body_state:
            return ""

        # 提取当前状态
        current_cost = body_state.get("current_cost", "")
        cost_history = body_state.get("cost_history", [])
        health_status = body_state.get("health_status", "")
        abilities_used = body_state.get("abilities_used", [])

        lines = ["### 🩺 身体状态检查（必须体现在剧情中）"]
        lines.append("")

        if health_status:
            lines.append(f"- **当前健康状态**：{health_status}")

        if current_cost:
            lines.append(f"- **当前代价**：{current_cost}")

        if cost_history:
            recent_costs = cost_history[-3:]  # 最近3章的代价
            costs_str = "、".join(recent_costs)
            lines.append(f"- **近期代价累积**：{costs_str}")
            lines.append("- **注意**：连续使用相同代价会导致身体崩溃，请选择不同的代价")

        if abilities_used:
            abilities_str = "、".join(abilities_used[-3:])
            lines.append(f"- **近期使用能力**：{abilities_str}")

        lines.append("")
        lines.append("以上身体状态必须在本章中有所体现（动作描写、环境反馈、他人反应等）。")

        return "\n".join(lines)

    def _build_structure_ban(self, chapter_num: int) -> str:
        """构建禁止结构模板"""
        # 常见的结构模板（需要避免重复）
        banned_patterns = [
            "对峙→揭示→突破→代价",
            "任务→执行→成功→奖励",
            "危机→觉醒→碾压→装逼",
            "日常→被打脸→反击→打脸成功",
        ]

        # 根据章节号选择不同的禁止模式
        banned_idx = chapter_num % len(banned_patterns)
        banned = banned_patterns[banned_idx]

        return f"""### 🚫 禁止结构模板（本章不能使用）

本章禁止使用以下结构模板：
**{banned}**

请使用更丰富的剧情结构，避免套路化。可以尝试：
- 多线并行（同时推进2-3个冲突）
- 反转再反转（看似解决的问题其实是更大的陷阱）
- 情感驱动（用角色情感变化推动剧情，而非事件驱动）
- 日常中的异常（在平凡场景中发现不平凡的线索）"""

    def _build_rhythm_requirements(self, chapter_num: int) -> str:
        """构建短剧节奏硬指标"""
        return f"""### 📺 短剧节奏硬指标（必须满足）

本章作为第{chapter_num}集短剧，必须满足以下节奏要求：

**1. 开头钩子（前100字）**：
- 必须在前100字内抛出一个悬念、冲突或感官冲击
- 禁止用背景铺垫开头
- 好的例子：一个异常现象、一句反常对话、一个意外发现

**2. 中段冲突升级（300-800字）**：
- 必须有至少一个物理冲突或信息炸弹
- 不能全是对话推进，必须有动作和环境变化
- 视觉密度：每100字至少1个可拍摄的物理动作

**3. 结尾断崖（最后100字）**：
- 必须在冲突爆发的前一秒截断
- 或者抛出一个未回答的问题
- 禁止：一切归于平静、她闭上眼睛、新世界开始了

**4. 视觉密度要求**：
- 纯叙述（无法拍摄的文字）占比不超过30%
- 每个镜头块必须有至少1个物理动作描写
- 对话不能连续超过2句不插入动作或环境变化"""


def build_constrained_scribe_prompt(
    chapter_num: int,
    project_dir: str | Path,
    base_prompt: str,
    previous_chapters: list[str] | None = None,
) -> str:
    """
    构建带约束注入的Scribe prompt。

    Args:
        chapter_num: 章节号
        project_dir: 项目目录
        base_prompt: 基础prompt（从scribe_prompt.py生成）
        previous_chapters: 历史章节文本（用于动态黑名单）

    Returns:
        注入约束后的完整prompt
    """
    injector = ConstraintInjector(project_dir)
    injection_block = injector.build_injection_block(chapter_num, previous_chapters)

    if not injection_block:
        return base_prompt

    # 在prompt的"开始写作"之前插入约束
    marker = "## 开始写作"
    if marker in base_prompt:
        parts = base_prompt.split(marker)
        return parts[0] + injection_block + "\n\n" + marker + parts[1]
    else:
        # 如果没有找到标记，在末尾追加
        return base_prompt + "\n\n" + injection_block
