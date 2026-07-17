"""
Committer — 章节锁定 + Curator状态更新

核心逻辑：
- 验证章节已通过audit
- 锁定章节（标记为committed）
- 生成Curator状态更新提案（角色状态、伏笔、信息差、时间线）
- 应用提案（带确认）

使用方式：
    from juben.committer import commit_chapter
    result = commit_chapter(mgr, chapter_num=7)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from juben.guardian import guardian_check, _extract_ending
from juben.state.manager import StateManager
from juben.state.schema import (
    CharacterState, CuratorProposal, InfoAsymmetryEntry,
    PlotThread, PlotThreadTracker, RelationshipGraph,
    StateChange, TimelineEvent,
)

logger = logging.getLogger(__name__)


class CommitResult:
    """提交结果"""

    def __init__(self):
        self.chapter_num: int = 0
        self.audit_passed: bool = False
        self.audit_score: float = 0.0
        self.locked: bool = False
        self.curator_proposal: Optional[dict] = None
        self.curator_applied: list[str] = []
        self.error: str = ""


def _run_audit(mgr: StateManager, chapter_num: int) -> tuple[bool, float]:
    """快速跑一次audit，返回(passed, score)"""
    chapter_path = mgr.project_dir / "chapters" / f"{chapter_num:03d}.md"
    if not chapter_path.exists():
        return False, 0.0

    text = chapter_path.read_text(encoding="utf-8")

    characters = mgr.load_characters()
    protagonist = next((c for c in characters if c.role.value == "protagonist"), None)
    protagonist_name = protagonist.name if protagonist else ""

    chapter_dir = mgr.project_dir / "chapters"
    all_endings = []
    for p in sorted(chapter_dir.glob("*.md")):
        t = p.read_text(encoding="utf-8")
        all_endings.append(_extract_ending(t))

    guardian_result = guardian_check(
        chapter_text=text,
        chapter_num=chapter_num,
        protagonist_name=protagonist_name,
        chapter_endings=all_endings[:chapter_num],
    )

    return guardian_result.passed, guardian_result.score


def _generate_curator_prompt(mgr: StateManager, chapter_num: int) -> str:
    """生成Curator的状态更新prompt（供LLM使用）"""
    chapter_path = mgr.project_dir / "chapters" / f"{chapter_num:03d}.md"
    text = chapter_path.read_text(encoding="utf-8")

    characters = mgr.load_characters()
    meta = mgr.load_meta()
    plot_threads = mgr.load_plot_threads()
    relationships = mgr.load_relationships()

    # 当前角色状态
    char_info = []
    for c in characters:
        char_info.append(
            f"- {c.id} ({c.name}, {c.role.value}): "
            f"location={c.state.location}, health={c.state.health}, "
            f"goal={c.state.current_goal}"
        )

    # 未解决的伏笔
    open_threads = [
        f"- {t.id}: {t.description} (status={t.status.value})"
        for t in plot_threads.threads
        if t.status.value in ("open", "planted")
    ]

    # 信息对称性
    info_entries = [
        f"- {e.info_id}: {e.description} (known_by={e.known_by})"
        for e in relationships.info_asymmetry
    ]

    prompt = f"""# Curator状态更新任务 — 第{chapter_num}章

你是一个剧本状态管理员。根据第{chapter_num}章的正文，生成状态变更提案。

## 第{chapter_num}章正文

```
{text}
```

## 当前角色状态

{chr(10).join(char_info)}

## 未解决的伏笔

{chr(10).join(open_threads) if open_threads else '(无)'}

## 信息对称性矩阵

{chr(10).join(info_entries) if info_entries else '(无)'}

## 你的任务

生成一个JSON对象，包含以下变更提案：

```json
{{
  "changes": [
    {{
      "entity_type": "character",
      "entity_id": "char_xxx",
      "field_path": "state.location",
      "old_value": "旧值",
      "new_value": "新值",
      "chapter": {chapter_num},
      "machine_verifiable": true,
      "reason": "变更原因"
    }}
  ],
  "new_events": [
    {{
      "id": "evt_xxx",
      "chapter": {chapter_num},
      "timestamp": "故事内时间",
      "description": "事件描述",
      "characters_involved": ["char_xxx"],
      "location": "地点",
      "impact": "影响",
      "type": "事件类型"
    }}
  ],
  "new_plot_threads": [
    {{
      "id": "thread_xxx",
      "description": "新伏笔描述",
      "planted_chapter": {chapter_num},
      "importance": "major/minor"
    }}
  ],
  "plot_thread_updates": [
    {{
      "id": "thread_xxx",
      "status": "payoff",
      "payoff_chapter": {chapter_num},
      "resolution": "如何收束"
    }}
  ],
  "info_asymmetry_updates": [
    {{
      "info_id": "info_xxx",
      "description": "新信息描述",
      "known_by": ["char_xxx"],
      "chapter_revealed": {chapter_num},
      "is_protagonist_advantage": true/false
    }}
  ]
}}
```

## 规则

1. 只报告本章实际发生的变更，不要推测未来
2. machine_verifiable=true 的变更才写入硬约束（位置、生死、数值变化）
3. 角色的情感变化、态度变化标记为 machine_verifiable=false（软状态）
4. 伏笔状态：open→planted（埋下）→payoff（收束）→abandoned（放弃）
5. 信息差更新：谁在本章知道了什么新信息

只输出JSON，不要输出其他文字。
"""
    return prompt


def commit_chapter(
    mgr: StateManager,
    chapter_num: int,
    skip_audit: bool = False,
    auto_apply: bool = False,
) -> CommitResult:
    """
    提交一个章节：audit + 锁定 + Curator状态更新。

    Args:
        mgr: StateManager
        chapter_num: 章节号
        skip_audit: 是否跳过audit（用于手动确认过的章节）
        auto_apply: 是否自动应用Curator提案（默认False，需要用户确认）

    Returns:
        CommitResult
    """
    result = CommitResult()
    result.chapter_num = chapter_num

    chapter_path = mgr.project_dir / "chapters" / f"{chapter_num:03d}.md"
    if not chapter_path.exists():
        result.error = f"找不到第{chapter_num}章: {chapter_path}"
        return result

    # 1. Audit检查
    if not skip_audit:
        passed, score = _run_audit(mgr, chapter_num)
        result.audit_passed = passed
        result.audit_score = score

        if not passed:
            result.error = f"第{chapter_num}章audit未通过（Guardian {score}/10）。请先修复再commit。"
            return result

    # 2. 锁定章节
    lock_path = mgr.project_dir / "chapters" / f"{chapter_num:03d}.md.locked"
    # 写入锁定标记文件（不移动原文件，保持兼容性）
    lock_data = {
        "chapter": chapter_num,
        "committed_at": datetime.now().isoformat(),
        "audit_score": result.audit_score,
    }
    lock_path.write_text(json.dumps(lock_data, ensure_ascii=False, indent=2), encoding="utf-8")
    result.locked = True

    # 3. 生成Curator prompt
    curator_prompt = _generate_curator_prompt(mgr, chapter_num)
    curator_dir = mgr.project_dir / "curator"
    curator_dir.mkdir(parents=True, exist_ok=True)
    curator_path = curator_dir / f"curator_prompt_{chapter_num:03d}.md"
    curator_path.write_text(curator_prompt, encoding="utf-8")

    result.curator_proposal = {"prompt_path": str(curator_path)}

    return result


def apply_curator_response(
    mgr: StateManager,
    chapter_num: int,
    response_path: Optional[str] = None,
) -> list[str]:
    """
    应用Curator的响应。

    Args:
        mgr: StateManager
        chapter_num: 章节号
        response_path: 响应文件路径（默认 curator/curator_response_NNN.json）

    Returns:
        应用的变更列表
    """
    curator_dir = mgr.project_dir / "curator"

    if response_path:
        resp_path = Path(response_path)
    else:
        resp_path = curator_dir / f"curator_response_{chapter_num:03d}.json"

    if not resp_path.exists():
        raise FileNotFoundError(f"找不到Curator响应: {resp_path}")

    with open(resp_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        # 支持markdown代码块
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip() == "```" and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        response_data = json.loads(content)

    # 构建CuratorProposal
    proposal = CuratorProposal(
        chapter=chapter_num,
        changes=[StateChange(**c) for c in response_data.get("changes", [])],
        new_events=response_data.get("new_events", []),
        new_plot_threads=response_data.get("new_plot_threads", []),
        plot_thread_updates=response_data.get("plot_thread_updates", []),
        info_asymmetry_updates=response_data.get("info_asymmetry_updates", []),
    )

    # 应用
    applied = mgr.apply_curator_proposal(proposal)
    return applied
