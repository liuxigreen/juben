"""
Bootstrapper — LLM驱动的项目初始化填充

核心铁律：
- Python层管确定性：生成prompt、验证schema、写入文件
- LLM管创造性：设计角色、推断世界观、生成意外变量
- 用户管决策权：review确认后才写入

流程：
1. juben bootstrap --dir ./my-story
   → 生成 bootstrap_prompt.md（含premise + 规则摘要 + 角色骨架 + 输出格式要求）
   → 用户把prompt喂给任意LLM

2. juben bootstrap --apply --dir ./my-story
   → 读取 bootstrap_response.json
   → schema验证
   → 显示摘要，用户确认
   → 写入 characters.json / world_rules.json / story_meta.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from juben.state.manager import StateManager
from juben.state.schema import (
    Appearance, Background, Abilities, Character, CharacterArc,
    CharacterRole, CharacterState, OCEAN, Personality,
    RelationshipGraph, Relationship, StoryMeta, WorldRules,
)

logger = logging.getLogger(__name__)

# ============================================================
# Prompt生成
# ============================================================

BOOTSTRAP_PROMPT_TEMPLATE = """\
# Juben 角色与世界观填充任务

你是一个专业的剧本架构师。根据以下信息，为这个故事项目生成完整的角色卡和世界观设定。

## 故事前提
{premise}

## 意外变量（核心金手指）
{disruption}

## 已有规则约束

### 因果约束（不可违反）
{causal_constraints}

### 反套路黑名单（禁止出现的情节）
{anti_cliche_blacklist}

### 核心原则
{rules}

## 算法卡点（每章必须遵循的节奏）
{pacing_cards}

---

## 你的任务

根据以上信息，生成一个JSON对象，包含以下字段：

```json
{{
  "characters": [
    {{
      "id": "char_pro",
      "name": "主角姓名",
      "aliases": ["别名1", "别名2"],
      "role": "protagonist",
      "appearance": {{
        "age": 0,
        "height": "",
        "build": "",
        "hair": "",
        "eyes": "",
        "distinguishing": "一个让人记住的特征",
        "clothing_default": ""
      }},
      "personality": {{
        "ocean": {{
          "openness": 5,
          "conscientiousness": 5,
          "extraversion": 5,
          "agreeableness": 5,
          "neuroticism": 5
        }},
        "speech_pattern": "说话风格描述",
        "habits": ["习惯1", "习惯2"],
        "fears": ["恐惧1"],
        "desires": "核心欲望"
      }},
      "background": {{
        "origin": "出身",
        "education": "教育",
        "key_event": "改变命运的关键事件",
        "secret": "隐藏的秘密"
      }},
      "abilities": {{
        "combat": "战斗能力",
        "knowledge": "知识技能",
        "special": "特殊能力（金手指）"
      }},
      "arc": {{
        "start": "故事开始时的状态",
        "midpoint": "中点转折",
        "end": "故事结束时的状态",
        "internal_conflict": "Want: X vs Need: Y"
      }},
      "state": {{
        "alive": true,
        "location": "",
        "health": "",
        "current_goal": ""
      }},
      "hidden_motivation": "不告诉主角的真实目的（NPC专用，主角可留空）",
      "personal_goal": "独立于主线剧情的自身诉求（如：想升职、想追某人、想还债）"
    }},
    {{
      "id": "char_ant",
      "name": "反派姓名",
      "role": "antagonist",
      "...": "同上结构"
    }},
    {{
      "id": "char_ally",
      "name": "盟友姓名",
      "role": "supporting",
      "...": "同上结构"
    }}
  ],
  "relationships": [
    {{
      "character_a": "char_pro",
      "character_b": "char_ant",
      "type": "enemy",
      "status": "描述当前关系状态",
      "trust_level": 10,
      "tension": "核心矛盾点"
    }}
  ],
  "world_rules_update": {{
    "world_name": "世界名称",
    "setting": {{
      "time_period": "",
      "geography": "",
      "technology_level": "",
      "social_structure": ""
    }},
    "power_system": {{
      "体系名称": "规则描述"
    }}
  }},
  "meta_update": {{
    "title": "建议标题",
    "logline": "一句话概括（50字以内）",
    "themes": ["主题1", "主题2", "主题3"],
    "disruption_variable": "如果用户没提供，你来设计一个有创意的意外变量"
  }},
  "plot_threads": [
    {{
      "id": "thread_1",
      "description": "主线伏笔描述",
      "importance": "major"
    }},
    {{
      "id": "thread_2",
      "description": "支线伏笔描述",
      "importance": "minor"
    }}
  ],
  "info_asymmetry": [
    {{
      "info_id": "info_1",
      "description": "这条信息是什么",
      "known_by": ["char_pro"],
      "is_protagonist_advantage": true
    }}
  ],
  "entity_anchors": {{
    "概念名称1": {{
      "anchor_prop": "具体物理道具名称（可拍摄）",
      "must_include_keywords": ["硬核关键词1", "硬核关键词2", "硬核关键词3"],
      "typical_action": "角色与道具交互的典型动作描写"
    }},
    "概念名称2": {{
      "anchor_prop": "具体物理道具名称",
      "must_include_keywords": ["关键词1", "关键词2", "关键词3"],
      "typical_action": "典型动作描写"
    }}
  }}
}}
```

## 设计要求

1. **角色必须有缺陷**：完美的主角没有故事。给主角一个真实的、影响剧情的弱点。
2. **反派必须有逻辑**：反派的动机不能是"天生坏"。给反派一个读者能理解（但不认同）的理由。
3. **关系必须有张力**：角色之间的关系不是静态的。标注出潜在的变化方向。
4. **信息差必须具体**：不要写"主角知道未来"，要写"主角知道某人在第X章会做某事"。
5. **符合已有的因果约束和反套路黑名单**：生成的内容不能违反上面列出的任何规则。
6. **实体锚点必须具体可拍**：每个核心抽象概念（如"经济压力"、"神秘威胁"、"职业身份"）都必须解构为一个可以在镜头前展示的物理道具/UI界面，并给出3个硬核关键词。禁止用抽象名词作为锚点。
7. **NPC必须有隐秘动机和个人目标**：每个非主角角色必须有`hidden_motivation`（不告诉主角的真实目的）和`personal_goal`（独立于主线的自身诉求）。这两个字段是NPC行为的锚点——没有它们，NPC就会退化成解说员。主角可以留空。

只输出JSON，不要输出任何其他文字。
"""


def generate_bootstrap_prompt(mgr: StateManager) -> str:
    """
    根据项目当前状态生成Bootstrapper prompt。

    如果项目目录下有research/目录的调研报告，会自动注入。

    Args:
        mgr: StateManager实例

    Returns:
        完整的prompt文本
    """
    meta = mgr.load_meta()
    world = mgr.load_world_rules()

    # 尝试注入调研结果
    research_context = ""
    try:
        from juben.research import compile_research_for_bootstrap
        research_context = compile_research_for_bootstrap(mgr.project_dir)
    except Exception:
        pass

    # 填充模板
    prompt = BOOTSTRAP_PROMPT_TEMPLATE.format(
        premise=meta.premise or "(未设定)",
        disruption=meta.disruption_variable or "(未设定——请自行设计一个有创意的意外变量)",
        causal_constraints="\n".join(f"- {c}" for c in world.causal_constraints) or "(无)",
        anti_cliche_blacklist="\n".join(f"- {b}" for b in world.anti_cliche_blacklist) or "(无)",
        rules="\n".join(f"- {r}" for r in world.rules) or "(无)",
        pacing_cards="\n".join(
            f"- [{c.label}] {c.word_range[0]}-{c.word_range[1]}字: {c.rule}"
            for c in meta.pacing_cards
        ) or "(无)",
    )

    # 如果有调研结果，插入到prompt末尾
    if research_context:
        prompt += "\n\n---\n\n" + research_context

    return prompt


def save_bootstrap_prompt(mgr: StateManager) -> Path:
    """生成并保存prompt到项目目录"""
    prompt = generate_bootstrap_prompt(mgr)
    path = mgr.project_dir / "bootstrap_prompt.md"
    path.write_text(prompt, encoding="utf-8")
    return path


# ============================================================
# 响应验证与写入
# ============================================================

class ValidationError(Exception):
    """schema验证失败"""
    pass


def _validate_character(data: dict) -> Character:
    """验证单个角色数据"""
    try:
        return Character.model_validate(data)
    except Exception as e:
        name = data.get("name", data.get("id", "unknown"))
        raise ValidationError(f"角色 '{name}' 验证失败: {e}")


def _validate_response(data: dict) -> dict:
    """
    验证LLM输出的完整响应。

    Returns:
        验证后的数据dict

    Raises:
        ValidationError: 验证失败
    """
    if not isinstance(data, dict):
        raise ValidationError("响应必须是JSON对象")

    # 验证characters
    chars_data = data.get("characters", [])
    if not chars_data:
        raise ValidationError("缺少 characters 字段")

    characters = []
    has_protagonist = False
    for c in chars_data:
        char = _validate_character(c)
        if char.role == CharacterRole.PROTAGONIST:
            has_protagonist = True
        characters.append(char)

    if not has_protagonist:
        raise ValidationError("至少需要一个 protagonist 角色")

    # 验证relationships（可选）
    relationships = []
    for r in data.get("relationships", []):
        try:
            relationships.append(Relationship.model_validate(r))
        except Exception as e:
            logger.warning(f"关系数据验证失败，跳过: {e}")

    # 验证world_rules_update（可选，部分更新）
    world_update = data.get("world_rules_update", {})

    # 验证meta_update（可选，部分更新）
    meta_update = data.get("meta_update", {})

    # 验证plot_threads（可选）
    plot_threads = data.get("plot_threads", [])

    # 验证info_asymmetry（可选）
    info_asymmetry = data.get("info_asymmetry", [])

    return {
        "characters": characters,
        "relationships": relationships,
        "world_rules_update": world_update,
        "meta_update": meta_update,
        "plot_threads": plot_threads,
        "info_asymmetry": info_asymmetry,
    }


def apply_bootstrap_response(mgr: StateManager, response_data: dict) -> dict:
    """
    验证并应用LLM的Bootstrap响应。

    Args:
        mgr: StateManager
        response_data: LLM输出的JSON

    Returns:
        应用结果摘要

    Raises:
        ValidationError: 验证失败
    """
    validated = _validate_response(response_data)

    changes = []

    # 1. 写入characters
    mgr.save_characters(validated["characters"])
    changes.append(f"角色: {len(validated['characters'])} 个")

    # 2. 更新world_rules（部分更新）
    if validated["world_rules_update"]:
        world = mgr.load_world_rules()
        update = validated["world_rules_update"]
        if "world_name" in update:
            world.world_name = update["world_name"]
        if "setting" in update:
            world.setting.update(update["setting"])
        if "power_system" in update:
            world.power_system.update(update["power_system"])
        if "factions" in update:
            world.factions = update["factions"]
        mgr._write_json("world_rules.json", world.model_dump())
        changes.append(f"世界观: 已更新")

    # 3. 更新story_meta（部分更新）
    if validated["meta_update"]:
        meta = mgr.load_meta()
        update = validated["meta_update"]
        if "title" in update:
            meta.title = update["title"]
        if "logline" in update:
            meta.logline = update["logline"]
        if "themes" in update:
            meta.themes = update["themes"]
        if "disruption_variable" in update and not meta.disruption_variable:
            meta.disruption_variable = update["disruption_variable"]
        mgr.save_meta(meta)
        changes.append(f"元数据: 已更新")

    # 4. 写入relationships
    if validated["relationships"]:
        graph = RelationshipGraph(
            relationships=validated["relationships"],
            info_asymmetry=[],
        )
        # 保留已有的info_asymmetry
        if validated["info_asymmetry"]:
            from juben.state.schema import InfoAsymmetryEntry
            for info_data in validated["info_asymmetry"]:
                try:
                    graph.info_asymmetry.append(
                        InfoAsymmetryEntry.model_validate(info_data)
                    )
                except Exception as e:
                    logger.warning(f"info_asymmetry条目验证失败: {e}")
        mgr.save_relationships(graph)
        changes.append(f"关系: {len(validated['relationships'])} 条")

    # 5. 写入plot_threads
    if validated["plot_threads"]:
        from juben.state.schema import PlotThread, PlotThreadTracker
        tracker = PlotThreadTracker(threads=[])
        for pt_data in validated["plot_threads"]:
            try:
                tracker.threads.append(PlotThread.model_validate(pt_data))
            except Exception as e:
                logger.warning(f"伏笔条目验证失败: {e}")
        mgr.save_plot_threads(tracker)
        changes.append(f"伏笔: {len(tracker.threads)} 条")

    return {
        "applied": changes,
        "character_count": len(validated["characters"]),
        "character_names": [c.name for c in validated["characters"]],
    }

