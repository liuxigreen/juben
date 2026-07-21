"""Episode模块 — 短剧单集适配器（v3 双风格版）"""
from .schema import (
    CameraAngle,
    CameraMovement,
    Cliffhanger,
    Composition,
    Episode,
    PacingCheckpoint,
    PacingLabel,
    RenderStyle,
    Shot,
    ShotType,
    VisualConsistency,
    BeatSheet,
    LocationJump,
    REALISTIC_SUFFIX,
    COMEDY_SUFFIX,
)
from .rhythm import RhythmValidator
from .adapter import EpisodeAdapter
from .shot_prompt import ShotPromptGenerator, load_character_visual_tags

from .scribe_prompt import (
    build_scribe_prompt_with_shots,
    build_episode_prompt,
    REALISTIC_SYSTEM_PERSONA,
    COMEDY_SYSTEM_PERSONA,
)
from .parser import EpisodeParser

__all__ = [
    "CameraAngle",
    "CameraMovement",
    "Cliffhanger",
    "Composition",
    "Episode",
    "EpisodeAdapter",
    "EpisodeParser",
    "PacingCheckpoint",
    "PacingLabel",
    "RenderStyle",
    "RhythmValidator",
    "Shot",
    "ShotPromptGenerator",
    "ShotType",
    "VisualConsistency",
    "BeatSheet",
    "LocationJump",
    "REALISTIC_SUFFIX",
    "COMEDY_SUFFIX",
    "REALISTIC_SYSTEM_PERSONA",
    "COMEDY_SYSTEM_PERSONA",
    "build_scribe_prompt_with_shots",
    "build_episode_prompt",
    "load_character_visual_tags",
]
