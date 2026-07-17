"""
通用模板（Universal）— Mixins驱动的万能题材模板

铁律：
- Python层管确定性（schema验证、合并逻辑、文件IO）
- LLM管创造性（角色设计、情节生成、对白打磨）
- Mixins管规则（反套路黑名单、因果约束、算法卡点）

使用方式：
    juben init -t universal --premise "古装女频：盲眼女相师收回神力碎片"
    juben init -t universal --premise "..." --mixin historical-base,female-lead --skeleton female-power
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from juben.genre_templates.registry import register
from juben.mixins.merge_engine import MergeEngine
from juben.state.schema import (
    Appearance, Background, Abilities, Character, CharacterArc,
    CharacterRole, CharacterState, OCEAN, Personality,
    RelationshipGraph, StoryMeta, WorldRules,
)


def _default_protagonist() -> Character:
    """生成一个空的主角卡骨架，供用户/LLM填充"""
    return Character(
        id="char_pro",
        name="(待设定)",
        role=CharacterRole.PROTAGONIST,
        appearance=Appearance(),
        personality=Personality(
            ocean=OCEAN(openness=5, conscientiousness=5, extraversion=5,
                        agreeableness=5, neuroticism=5),
        ),
        background=Background(),
        abilities=Abilities(),
        arc=CharacterArc(),
        state=CharacterState(alive=True),
    )


def _default_antagonist() -> Character:
    """生成一个空的反派卡骨架"""
    return Character(
        id="char_ant",
        name="(待设定)",
        role=CharacterRole.ANTAGONIST,
        appearance=Appearance(),
        personality=Personality(
            ocean=OCEAN(openness=5, conscientiousness=5, extraversion=5,
                        agreeableness=3, neuroticism=5),
        ),
        background=Background(),
        abilities=Abilities(),
        arc=CharacterArc(),
        state=CharacterState(alive=True),
    )


@register("universal")
def init_universal(
    premise: str = "",
    language: str = "zh-CN",
    mixins: Optional[list[str]] = None,
    skeletons: Optional[list[str]] = None,
    title: str = "",
    disruption_variable: str = "",
) -> dict:
    """
    初始化通用项目。

    Args:
        premise: 一句话核心前提
        language: 语言
        mixins: genre mixin名称列表（如 ["historical-base", "female-lead"]）
        skeletons: skeleton mixin名称列表（如 ["court-intrigue", "female-power"]）
        title: 标题（可选，为空时用premise前20字）
        disruption_variable: 意外变量（可选）

    Returns:
        {"meta": StoryMeta, "characters": list[Character], "world_rules": WorldRules}
    """
    engine = MergeEngine()

    # 默认mixin
    genre_mixins = mixins or []
    skeleton_mixins = skeletons or []

    # 如果没指定任何mixin，给一个空壳（纯靠premise）
    if not genre_mixins and not skeleton_mixins:
        # 不报错，只是没有预设规则
        pass

    # 合并world_rules
    world_rules = engine.build_world_rules(genre_mixins)

    # 合并story_meta（含pacing_cards）
    meta = engine.build_story_meta(
        premise=premise,
        genre_mixins=genre_mixins,
        skeleton_mixins=skeleton_mixins,
        title=title or (premise[:20] if premise else "未命名"),
        language=language,
        disruption_variable=disruption_variable,
    )

    # 生成骨架角色卡（空壳，等LLM填充）
    characters = [_default_protagonist(), _default_antagonist()]

    return {
        "meta": meta,
        "characters": characters,
        "world_rules": world_rules,
    }
