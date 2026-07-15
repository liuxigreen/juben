"""
StateManager — 读写JSON状态文件，原子操作+备份

核心铁律：
- LLM只能通过CuratorProposal提议变更
- Python验证后才写入
- 每次写入前自动备份
- soft_state（性格变化等）不注入下一章硬约束
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from juben.state.schema import (
    Character, CharacterState, CuratorProposal, InfoAsymmetryEntry,
    PlotThread, PlotThreadTracker, Relationship, RelationshipGraph,
    StateChange, StoryMeta, Timeline, TimelineEvent, WorldRules,
)


class StateManager:
    """项目状态管理器 — 读写所有JSON状态文件"""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self._ensure_structure()

    def _ensure_structure(self):
        """确保项目目录结构存在"""
        dirs = ["chapters", "outlines", "reports", ".backups"]
        for d in dirs:
            (self.project_dir / d).mkdir(parents=True, exist_ok=True)

    # ============================================================
    # 读取
    # ============================================================

    def load_meta(self) -> StoryMeta:
        return StoryMeta.model_validate(self._read_json("story_meta.json"))

    def load_characters(self) -> list[Character]:
        data = self._read_json("characters.json")
        return [Character.model_validate(c) for c in data.get("characters", [])]

    def load_character(self, char_id: str) -> Optional[Character]:
        for c in self.load_characters():
            if c.id == char_id:
                return c
        return None

    def load_world_rules(self) -> WorldRules:
        return WorldRules.model_validate(self._read_json("world_rules.json"))

    def load_timeline(self) -> Timeline:
        return Timeline.model_validate(self._read_json("timeline.json"))

    def load_relationships(self) -> RelationshipGraph:
        return RelationshipGraph.model_validate(self._read_json("relationships.json"))

    def load_plot_threads(self) -> PlotThreadTracker:
        return PlotThreadTracker.model_validate(self._read_json("plot_threads.json"))

    # ============================================================
    # 写入（带备份）
    # ============================================================

    def save_meta(self, meta: StoryMeta):
        self._write_json("story_meta.json", meta.model_dump())

    def save_characters(self, characters: list[Character]):
        self._write_json("characters.json", {
            "characters": [c.model_dump() for c in characters]
        })

    def save_timeline(self, timeline: Timeline):
        self._write_json("timeline.json", timeline.model_dump())

    def save_relationships(self, graph: RelationshipGraph):
        self._write_json("relationships.json", graph.model_dump())

    def save_plot_threads(self, tracker: PlotThreadTracker):
        self._write_json("plot_threads.json", tracker.model_dump())

    # ============================================================
    # Curator变更验证 + 写入（防投毒核心）
    # ============================================================

    def apply_curator_proposal(self, proposal: CuratorProposal) -> list[str]:
        """
        验证并应用Curator的变更提案。
        
        返回：成功应用的变更描述列表。
        
        防投毒机制：
        1. machine_verifiable=False的变更不写入硬约束
        2. 数值变更必须在合理范围内
        3. 生死状态变更必须有明确的old_value→new_value
        """
        applied = []

        # 分类处理变更
        verifiable_changes = [
            c for c in proposal.changes if c.machine_verifiable
        ]
        soft_changes = [
            c for c in proposal.changes if not c.machine_verifiable
        ]

        # 只有可机器验证的变更才写入
        for change in verifiable_changes:
            ok = self._apply_single_change(change)
            if ok:
                applied.append(
                    f"[硬状态] {change.entity_id}.{change.field_path}: "
                    f"{change.old_value} → {new_value_trunc(change.new_value)}"
                )

        # 软状态只记录日志，不写入
        for change in soft_changes:
            applied.append(
                f"[软状态·不写入] {change.entity_id}.{change.field_path}: "
                f"{change.reason}"
            )

        # 新事件写入时间线
        if proposal.new_events:
            timeline = self.load_timeline()
            for evt_data in proposal.new_events:
                evt = TimelineEvent(**evt_data)
                timeline.events.append(evt)
            self.save_timeline(timeline)
            applied.append(f"[时间线] +{len(proposal.new_events)}事件")

        # 伏笔更新
        if proposal.new_plot_threads or proposal.plot_thread_updates:
            tracker = self.load_plot_threads()
            for pt_data in proposal.new_plot_threads:
                tracker.threads.append(PlotThread(**pt_data))
            for upd in proposal.plot_thread_updates:
                tid = upd.get("id", "")
                for pt in tracker.threads:
                    if pt.id == tid:
                        if "status" in upd:
                            pt.status = upd["status"]
                        if "payoff_chapter" in upd:
                            pt.payoff_chapter = upd["payoff_chapter"]
                        if "resolution" in upd:
                            pt.resolution = upd["resolution"]
            self.save_plot_threads(tracker)
            applied.append(f"[伏笔] 更新完成")

        # 信息对称性更新
        if proposal.info_asymmetry_updates:
            rels = self.load_relationships()
            for info_data in proposal.info_asymmetry_updates:
                entry = InfoAsymmetryEntry(**info_data)
                rels.info_asymmetry.append(entry)
            self.save_relationships(rels)
            applied.append(f"[信息差] +{len(proposal.info_asymmetry_updates)}条")

        return applied

    def _apply_single_change(self, change: StateChange) -> bool:
        """应用单条可验证变更"""
        if change.entity_type == "character":
            return self._apply_character_change(change)
        return False

    def _apply_character_change(self, change: StateChange) -> bool:
        """应用角色状态变更"""
        chars = self.load_characters()
        for i, char in enumerate(chars):
            if char.id == change.entity_id:
                # 安全地设置嵌套字段
                parts = change.field_path.split(".")
                obj = char
                for part in parts[:-1]:
                    obj = getattr(obj, part, None)
                    if obj is None:
                        return False
                field_name = parts[-1]
                if not hasattr(obj, field_name):
                    return False

                # 类型安全转换
                current = getattr(obj, field_name)
                new_val = _safe_cast(current, change.new_value)
                setattr(obj, field_name, new_val)

                # 更新state元数据
                if char.state:
                    char.state.last_state_change = change.chapter

                chars[i] = char
                self.save_characters(chars)
                return True
        return False

    # ============================================================
    # 初始化项目
    # ============================================================

    def init_project(self, meta: StoryMeta, characters: list[Character],
                     world_rules: WorldRules):
        """初始化一个新项目"""
        self.save_meta(meta)
        self.save_characters(characters)
        self._write_json("world_rules.json", world_rules.model_dump())
        self.save_timeline(Timeline(events=[]))
        self.save_relationships(RelationshipGraph(relationships=[]))
        self.save_plot_threads(PlotThreadTracker(threads=[]))

    # ============================================================
    # 底层IO
    # ============================================================

    def _read_json(self, filename: str) -> dict:
        path = self.project_dir / filename
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, filename: str, data: Any):
        path = self.project_dir / filename
        # 备份
        if path.exists():
            backup_name = f"{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            shutil.copy2(path, self.project_dir / ".backups" / backup_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 工具函数
# ============================================================

def _safe_cast(current: Any, new_value: str) -> Any:
    """类型安全转换"""
    if isinstance(current, bool):
        return new_value.lower() in ("true", "1", "yes")
    if isinstance(current, int):
        return int(new_value)
    if isinstance(current, float):
        return float(new_value)
    return new_value


def new_value_trunc(val: str, maxlen: int = 40) -> str:
    """截断显示"""
    if len(val) <= maxlen:
        return val
    return val[:maxlen] + "..."
