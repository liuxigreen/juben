"""
MergeEngine — Mixins合并引擎

核心铁律：
- Python层永远是真相源，Mixins是结构化数据，不是LLM输出
- 合并策略：list字段去重追加，dict字段深度合并，scalar字段后覆盖前
- 冲突检测：同一条规则出现在多个mixin中，警告但不报错（去重即可）

使用方式：
    from juben.mixins.merge_engine import MergeEngine
    engine = MergeEngine()
    world_rules = engine.build_world_rules(["historical-base", "female-lead"])
    pacing_cards = engine.build_pacing_cards(["court-intrigue", "female-power"])
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from juben.state.schema import (
    PacingCard, StoryMeta, WorldRules, CliffhangerType,
)

logger = logging.getLogger(__name__)

# Mixins目录：相对于项目根目录
MIXINS_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "mixins"


class MixinNotFoundError(Exception):
    """Mixin文件不存在"""
    pass


class MixinLoadError(Exception):
    """Mixin文件解析失败"""
    pass


def _load_mixin(category: str, name: str) -> dict:
    """
    加载单个mixin YAML文件。

    Args:
        category: 子目录名 (genre / skeleton / community)
        name: mixin名（不含.yaml后缀）

    Returns:
        解析后的dict

    Raises:
        MixinNotFoundError: 文件不存在
        MixinLoadError: YAML解析失败
    """
    path = MIXINS_DIR / category / f"{name}.yaml"
    if not path.exists():
        raise MixinNotFoundError(
            f"Mixin不存在: {category}/{name} "
            f"(查找路径: {path})"
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise MixinLoadError(f"Mixin文件格式错误: {path}（顶层必须是dict）")
        return data
    except yaml.YAMLError as e:
        raise MixinLoadError(f"YAML解析失败: {path}: {e}")


def _deep_merge(base: dict, override: dict) -> dict:
    """
    深度合并两个dict。

    策略：
    - dict + dict → 递归合并
    - list + list → 去重追加
    - scalar + scalar → override覆盖base
    """
    result = base.copy()
    for key, value in override.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _deep_merge(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                # 去重追加：保持顺序，跳过已存在的项
                seen = set()
                merged = []
                for item in result[key] + value:
                    # 用字符串表示做去重key
                    key_str = str(item) if not isinstance(item, dict) else str(sorted(item.items()))
                    if key_str not in seen:
                        seen.add(key_str)
                        merged.append(item)
                result[key] = merged
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def _resolve_cliffhanger_type(raw: Optional[str]) -> Optional[CliffhangerType]:
    """将字符串转为CliffhangerType枚举"""
    if raw is None:
        return None
    mapping = {e.value: e for e in CliffhangerType}
    return mapping.get(raw)


class MergeEngine:
    """
    Mixins合并引擎。

    读取YAML格式的mixin文件，合并输出WorldRules和PacingCards。
    """

    def __init__(self, mixins_dir: Optional[Path] = None):
        self.mixins_dir = mixins_dir or MIXINS_DIR

    def list_available(self) -> dict[str, list[str]]:
        """列出所有可用的mixin，按category分组"""
        result = {}
        for category_dir in sorted(self.mixins_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            mixins = []
            for f in sorted(category_dir.glob("*.yaml")):
                mixins.append(f.stem)
            if mixins:
                result[category] = mixins
        return result

    def load_mixin(self, category: str, name: str) -> dict:
        """加载单个mixin（委托给模块级函数）"""
        return _load_mixin(category, name)

    def resolve_mixin_names(self, mixin_names: list[str]) -> list[tuple[str, str, dict]]:
        """
        解析mixin名称列表，自动查找category。

        支持两种格式：
        - "female-lead" → 自动在所有category中查找
        - "genre/female-lead" → 指定category

        Returns:
            [(category, name, data), ...]
        """
        resolved = []
        for name in mixin_names:
            if "/" in name:
                # 指定category
                category, mixin_name = name.split("/", 1)
                data = self.load_mixin(category, mixin_name)
                resolved.append((category, mixin_name, data))
            else:
                # 自动查找
                found = False
                for category_dir in self.mixins_dir.iterdir():
                    if not category_dir.is_dir():
                        continue
                    path = category_dir / f"{name}.yaml"
                    if path.exists():
                        data = self.load_mixin(category_dir.name, name)
                        resolved.append((category_dir.name, name, data))
                        found = True
                        break
                if not found:
                    available = self.list_available()
                    raise MixinNotFoundError(
                        f"找不到mixin: {name}。可用mixin: {available}"
                    )
        return resolved

    def build_world_rules(
        self,
        genre_mixins: list[str],
        extra_blacklist: Optional[list[str]] = None,
        extra_constraints: Optional[list[str]] = None,
    ) -> WorldRules:
        """
        从genre类型的mixin合并生成WorldRules。

        Args:
            genre_mixins: genre mixin名称列表
            extra_blacklist: 额外的反套路黑名单（用户自定义）
            extra_constraints: 额外的因果约束（用户自定义）

        Returns:
            合并后的WorldRules对象
        """
        merged: dict[str, Any] = {
            "world_name": "",
            "genre": "",
            "setting": {},
            "rules": [],
            "anti_cliche_blacklist": [],
            "causal_constraints": [],
        }

        for category, name, data in self.resolve_mixin_names(genre_mixins):
            if category != "genre":
                logger.warning(f"mixin {name} 不是genre类型，跳过world_rules合并")
                continue

            # 提取world_rules相关字段
            mixin_data = {}
            if "world_setting" in data:
                mixin_data["setting"] = data["world_setting"]
            if "causal_constraints" in data:
                mixin_data["causal_constraints"] = data["causal_constraints"]
            if "anti_cliche_blacklist" in data:
                mixin_data["anti_cliche_blacklist"] = data["anti_cliche_blacklist"]
            if "core_principles" in data:
                mixin_data["rules"] = data["core_principles"]

            merged = _deep_merge(merged, mixin_data)
            logger.info(f"已合并genre mixin: {name}")

        # 追加用户自定义
        if extra_blacklist:
            merged["anti_cliche_blacklist"].extend(extra_blacklist)
        if extra_constraints:
            merged["causal_constraints"].extend(extra_constraints)

        return WorldRules(**merged)

    def build_pacing_cards(
        self,
        skeleton_mixins: list[str],
    ) -> list[PacingCard]:
        """
        从skeleton类型的mixin生成PacingCards。

        如果多个skeleton都定义了同名label（如都有3s_Hook），
        最后一个mixin的规则覆盖前面的（因为PacingCard是按label匹配的）。

        Args:
            skeleton_mixins: skeleton mixin名称列表

        Returns:
            PacingCard列表
        """
        cards_by_label: dict[str, dict] = {}

        for category, name, data in self.resolve_mixin_names(skeleton_mixins):
            if category != "skeleton":
                logger.warning(f"mixin {name} 不是skeleton类型，跳过pacing_cards合并")
                continue

            for card_data in data.get("pacing_cards", []):
                label = card_data.get("label", "")
                if label in cards_by_label:
                    logger.info(f"PacingCard '{label}' 被 {name} 覆盖")
                cards_by_label[label] = card_data
            logger.info(f"已合并skeleton mixin: {name}")

        # 按原始顺序排列（保持骨架的时间顺序）
        cards = []
        for card_data in cards_by_label.values():
            ct = card_data.pop("cliffhanger_type", None)
            card = PacingCard(
                label=card_data["label"],
                word_range=card_data["word_range"],
                rule=card_data["rule"],
                emotion=card_data.get("emotion", ""),
                cliffhanger_type=_resolve_cliffhanger_type(ct),
            )
            cards.append(card)

        return cards

    def build_story_meta(
        self,
        premise: str,
        genre_mixins: list[str],
        skeleton_mixins: list[str],
        title: str = "",
        language: str = "zh-CN",
        disruption_variable: str = "",
    ) -> StoryMeta:
        """
        从mixins合并生成StoryMeta。

        这是最高层的合并函数，组合genre和skeleton的信息。
        """
        pacing_cards = self.build_pacing_cards(skeleton_mixins)

        # 从genre mixins推断genre和themes
        genre_parts = []
        themes = []
        for category, name, data in self.resolve_mixin_names(genre_mixins):
            if "description" in data:
                genre_parts.append(data["description"])
            if "core_principles" in data:
                themes.extend(data["core_principles"][:3])

        return StoryMeta(
            title=title or "未命名",
            genre=" + ".join(genre_parts) if genre_mixins else "",
            premise=premise,
            language=language,
            disruption_variable=disruption_variable,
            pacing_cards=pacing_cards,
            template="universal",
            narrative_skeleton="mixins:" + ",".join(skeleton_mixins),
            global_hook_density="high",
            themes=themes[:5],
        )

    def generate_init_report(
        self,
        genre_mixins: list[str],
        skeleton_mixins: list[str],
        world_rules: WorldRules,
        pacing_cards: list[PacingCard],
    ) -> str:
        """
        生成初始化报告，供用户review。

        返回人类可读的文本，展示合并结果。
        """
        lines = [
            "═" * 50,
            "  Juben Mixins 合并报告",
            "═" * 50,
            "",
            f"📦 Genre Mixins: {', '.join(genre_mixins) if genre_mixins else '(无)'}",
            f"📦 Skeleton Mixins: {', '.join(skeleton_mixins) if skeleton_mixins else '(无)'}",
            "",
            "── 世界观规则 ──",
            f"  世界名: {world_rules.world_name or '(待设定)'}",
            f"  因果约束: {len(world_rules.causal_constraints)} 条",
        ]
        for c in world_rules.causal_constraints:
            lines.append(f"    • {c}")

        lines.extend([
            "",
            f"  反套路黑名单: {len(world_rules.anti_cliche_blacklist)} 条",
        ])
        for b in world_rules.anti_cliche_blacklist:
            lines.append(f"    ✗ {b}")

        lines.extend([
            "",
            "── 算法卡点 ──",
        ])
        for card in pacing_cards:
            lines.append(
                f"  [{card.label}] {card.word_range[0]}-{card.word_range[1]}字: "
                f"{card.rule[:60]}..."
            )

        lines.extend([
            "",
            "═" * 50,
            f"  共 {len(world_rules.causal_constraints)} 条因果约束, "
            f"{len(world_rules.anti_cliche_blacklist)} 条反套路, "
            f"{len(pacing_cards)} 个算法卡点",
            "═" * 50,
        ])

        return "\n".join(lines)
