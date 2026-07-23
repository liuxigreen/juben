"""
Pydantic数据模型 — 所有状态文件的结构化定义

铁律：LLM输出必须通过这些schema验证才能写入JSON。
Python层永远是真相源，LLM只能提议变更。
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# 通用枚举
# ============================================================

class CharacterRole(str, Enum):
    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    MINOR = "minor"


class PlotThreadStatus(str, Enum):
    OPEN = "open"
    PLANTED = "planted"
    PAYOFF = "payoff"
    ABANDONED = "abandoned"


class CliffhangerType(str, Enum):
    REVEAL = "Reveal"
    DECISION = "Decision"
    TURN = "Turn"
    MID_CRISIS = "Mid-Crisis Cut"
    TICKING_CLOCK = "Ticking Clock"


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class ViolationType(str, Enum):
    CHARACTER_INCONSISTENCY = "character_inconsistency"
    TIMELINE_CONTRADICTION = "timeline_contradiction"
    WORLD_RULE_VIOLATION = "world_rule_violation"
    RELATIONSHIP_ERROR = "relationship_error"
    DEATH_ERROR = "death_error"
    FORESHADOW_ERROR = "foreshadow_error"
    CLICHE_DETECTED = "cliche_detected"
    CLIFFHANGER_WEAK = "cliffhanger_weak"
    INFO_ASYMMETRY_VIOLATION = "info_asymmetry_violation"


# ============================================================
# 故事元数据 (story_meta.json)
# ============================================================

class PacingCard(BaseModel):
    """算法时间轴卡点 — 每个分镜的物理数学公式"""
    label: str = Field(..., description="标签: 3s_Hook / 15s_Retention / 50s_Cliffhanger")
    word_range: list[int] = Field(..., description="字数范围 [start, end]")
    rule: str = Field(..., description="强制规则")
    emotion: str = Field(default="", description="情绪要求")
    cliffhanger_type: Optional[CliffhangerType] = Field(
        default=None, description="如果是断崖卡点，指定类型"
    )


class StoryMeta(BaseModel):
    """故事元数据 — 包含意外变量和算法卡点"""
    title: str = ""
    genre: str = ""
    sub_genres: list[str] = Field(default_factory=list)
    premise: str = Field(default="", description="一句话核心前提")
    logline: str = ""
    target_chapters: int = 50
    target_word_count_per_chapter: int = 2000
    pov: str = "third_person_limited"
    language: str = "zh-CN"
    last_chapter_written: int = 0

    # === 硬核增强1: 意外变量 ===
    disruption_variable: str = Field(
        default="",
        description="强制注入的原创扰动源，Architect必须以此为核心金手指"
    )

    # === 硬核增强3: 算法时间轴卡点 ===
    pacing_cards: list[PacingCard] = Field(default_factory=list)

    template: str = ""
    narrative_skeleton: str = ""
    global_hook_density: str = "high"
    themes: list[str] = Field(default_factory=list)
    target_audience: dict = Field(default_factory=dict)


# ============================================================
# 角色卡 (characters.json)
# ============================================================

class Appearance(BaseModel):
    age: int = 0
    height: str = ""
    build: str = ""
    hair: str = ""
    eyes: str = ""
    distinguishing: str = ""
    clothing_default: str = ""


class OCEAN(BaseModel):
    openness: int = Field(default=5, ge=1, le=10)
    conscientiousness: int = Field(default=5, ge=1, le=10)
    extraversion: int = Field(default=5, ge=1, le=10)
    agreeableness: int = Field(default=5, ge=1, le=10)
    neuroticism: int = Field(default=5, ge=1, le=10)


class Personality(BaseModel):
    ocean: OCEAN = Field(default_factory=OCEAN)
    speech_pattern: str = ""
    habits: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    desires: str = ""


class Background(BaseModel):
    origin: str = ""
    family: str = ""
    education: str = ""
    key_event: str = ""
    secret: str = ""


class Abilities(BaseModel):
    combat: str = ""
    knowledge: str = ""
    special: str = ""


class CharacterArc(BaseModel):
    start: str = ""
    midpoint: str = ""
    end: str = ""
    internal_conflict: str = ""


class CharacterState(BaseModel):
    """动态状态 — 每章写完后由Curator更新"""
    alive: bool = True
    location: str = ""
    health: str = "健康"
    current_goal: str = ""
    last_appeared: Optional[int] = None
    last_state_change: Optional[int] = None


class Character(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    role: CharacterRole = CharacterRole.SUPPORTING
    appearance: Appearance = Field(default_factory=Appearance)
    personality: Personality = Field(default_factory=Personality)
    background: Background = Field(default_factory=Background)
    abilities: Abilities = Field(default_factory=Abilities)
    relationships: dict[str, str] = Field(default_factory=dict)
    arc: CharacterArc = Field(default_factory=CharacterArc)
    state: CharacterState = Field(default_factory=CharacterState)
    hidden_motivation: str = ""  # NPC隐秘动机：不告诉主角的真实目的
    personal_goal: str = ""  # NPC个人目标：独立于剧情的自身诉求


# ============================================================
# 世界观规则 (world_rules.json)
# ============================================================

class WorldRules(BaseModel):
    world_name: str = ""
    genre: str = ""
    setting: dict = Field(default_factory=dict)
    power_system: dict = Field(default_factory=dict)
    factions: list[dict] = Field(default_factory=list)
    resources: dict = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)

    # === 硬核增强2: 反套路黑名单 ===
    anti_cliche_blacklist: list[str] = Field(
        default_factory=list,
        description="铁血黑名单——Guardian校验时触发即熔断重跑"
    )
    # 因果限制：世界规则的硬性约束
    causal_constraints: list[str] = Field(
        default_factory=list,
        description="因果律断言，如'金丹以下无法飞行'"
    )
    # 硬约束：违反即熔断的设定锚定规则
    hard_constraints: list[str] = Field(
        default_factory=list,
        description="硬约束——违反即熔断，用于锚定核心设定不被抛弃"
    )


# ============================================================
# 时间线 (timeline.json)
# ============================================================

class TimelineEvent(BaseModel):
    id: str
    chapter: int
    timestamp: str = ""
    description: str = ""
    characters_involved: list[str] = Field(default_factory=list)
    location: str = ""
    impact: str = ""
    type: str = ""


class Timeline(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)


# ============================================================
# 关系图 (relationships.json) — 含信息对称性矩阵
# ============================================================

class InfoAsymmetryEntry(BaseModel):
    """信息对称性条目 — 谁知道什么"""
    info_id: str = Field(..., description="信息唯一ID")
    description: str = Field(..., description="这条信息是什么")
    known_by: list[str] = Field(
        default_factory=list,
        description="知道这条信息的角色ID列表"
    )
    chapter_revealed: int = Field(
        default=0, description="在哪一章被揭示的"
    )
    is_protagonist_advantage: bool = Field(
        default=False,
        description="是否为主角的先知优势（重生/穿越带来的信息差）"
    )


class RelationshipEvolution(BaseModel):
    chapter: int
    change: str = ""
    trust_delta: int = 0


class Relationship(BaseModel):
    character_a: str
    character_b: str
    type: str = "ally"
    status: str = ""
    trust_level: int = 50
    history: str = ""
    tension: str = ""
    evolution: list[RelationshipEvolution] = Field(default_factory=list)


class RelationshipGraph(BaseModel):
    relationships: list[Relationship] = Field(default_factory=list)
    # === 硬核增强4: 信息对称性矩阵 ===
    info_asymmetry: list[InfoAsymmetryEntry] = Field(
        default_factory=list,
        description="信息对称性矩阵——防吃书的核心武器"
    )


# ============================================================
# 伏笔追踪 (plot_threads.json)
# ============================================================

class PlotThread(BaseModel):
    id: str
    description: str = ""
    planted_chapter: int = 0
    payoff_chapter: Optional[int] = None
    status: PlotThreadStatus = PlotThreadStatus.OPEN
    characters_involved: list[str] = Field(default_factory=list)
    importance: str = "major"
    resolution: Optional[str] = None


class PlotThreadTracker(BaseModel):
    threads: list[PlotThread] = Field(default_factory=list)


# ============================================================
# 状态变更提案（Curator输出 → Python验证后才写入）
# ============================================================

class StateChange(BaseModel):
    """
    Curator的输出格式——LLM只能提议变更，Python验证后才写入。
    这是防Curator投毒的核心防线。
    """
    entity_type: str = Field(
        default="character",
        description="变更对象类型: character / relationship / plot_thread / timeline"
    )
    entity_id: str = ""
    field_path: str = Field(
        default="",
        description="变更路径，如 state.location"
    )
    old_value: str = ""
    new_value: str = ""
    chapter: int = 0
    machine_verifiable: bool = Field(
        default=False,
        description="可机器验证的变更（位置/生死/数值）才写入硬约束"
    )
    reason: str = ""


class CuratorProposal(BaseModel):
    """Curator提交的完整变更提案"""
    chapter: int
    changes: list[StateChange] = Field(default_factory=list)
    new_events: list[dict] = Field(default_factory=list)
    new_plot_threads: list[dict] = Field(default_factory=list)
    plot_thread_updates: list[dict] = Field(default_factory=list)
    info_asymmetry_updates: list[dict] = Field(
        default_factory=list,
        description="信息对称性变更（谁知道了什么新信息）"
    )


# ============================================================
# 校验结果
# ============================================================

class Violation(BaseModel):
    type: ViolationType
    severity: Severity
    description: str
    location: str = ""
    suggestion: str = ""


class ValidationResult(BaseModel):
    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=10.0)

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)


# ============================================================
# 分镜细纲 (Architect输出)
# ============================================================

class Scene(BaseModel):
    scene_id: int
    location: str = ""
    time: str = ""
    characters_present: list[str] = Field(default_factory=list)
    conflict: str = ""
    emotion_start: str = ""
    emotion_end: str = ""
    key_action: str = ""
    sensory_details: list[str] = Field(default_factory=list)
    pacing_label: str = Field(default="", description="算法卡点标签")
    word_range: list[int] = Field(default_factory=list)


class ChapterHook(BaseModel):
    type: CliffhangerType = CliffhangerType.REVEAL
    line: str = ""
    unanswered_question: str = ""


class ChapterOutline(BaseModel):
    chapter_num: int
    chapter_goal: str = ""
    scenes: list[Scene] = Field(default_factory=list)
    chapter_hook: ChapterHook = Field(default_factory=ChapterHook)
    foreshadowing: dict = Field(default_factory=dict)
    emotion_beats: list[str] = Field(default_factory=list)
    characters_involved: list[str] = Field(default_factory=list)


# ============================================================
# 章节质量报告
# ============================================================

class ChapterReport(BaseModel):
    chapter_num: int
    word_count: int = 0
    continuity: ValidationResult = Field(
        default_factory=lambda: ValidationResult(passed=True))
    anti_ai: ValidationResult = Field(
        default_factory=lambda: ValidationResult(passed=True))
    cliffhanger: ValidationResult = Field(
        default_factory=lambda: ValidationResult(passed=True))
    pacing: ValidationResult = Field(
        default_factory=lambda: ValidationResult(passed=True))
    anti_cliche: ValidationResult = Field(
        default_factory=lambda: ValidationResult(passed=True))
    overall_score: float = 0.0
    passed: bool = True
