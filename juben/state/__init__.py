"""Layer 1: 状态管理 — Python事实源，LLM只能提议变更，不能直接写入"""
from juben.state.manager import StateManager
from juben.state.schema import (
    Character, StoryMeta, WorldRules, Timeline, Relationship, PlotThread,
    StateChange, ValidationResult,
)

__all__ = [
    "StateManager", "Character", "StoryMeta", "WorldRules",
    "Timeline", "Relationship", "PlotThread", "StateChange", "ValidationResult",
]
