"""
Scribe Constraint Injector — Scribe生成前强制动态注入（v2统一版）

核心思想：事前熔断 > 事后检查
在Scribe生成prompt之前，强制注入：
1. 动态黑名单（近期高频短语，n-gram分析）
2. 本章必须完成的设定元素清单（概念映射）
3. 身体状态检查（代价累积，CostRoulette）
4. 禁止结构模板列表
5. 四段式beat节奏模板
6. 短剧节奏硬指标（视觉密度、钩子、断崖）
"""
from __future__ import annotations

import json
import logging
import random
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


# ============================================================
# 代价轮盘（从constraints.py合并）
# ============================================================

DEFAULT_COST_POOL = [
    "鼻血", "耳鸣", "视线模糊", "手脚发麻", "记忆闪回",
    "灵气失控", "指甲断裂", "吐血", "太阳穴剧痛", "肌肉痉挛",
    "呼吸困难", "心跳紊乱", "短暂失聪", "视野发红", "口中血腥味",
]


class CostRoulette:
    """突破代价轮盘 — 确保3章内不重复"""

    def __init__(self, cooldown: int = 3):
        self.cooldown = cooldown
        self.history: list[dict] = []  # [{"chapter": N, "cost": "..."}]

    def pick(self, chapter_num: int, pool: list[str] | None = None) -> str:
        """为本章随机选一个代价，排除最近cooldown章内用过的"""
        if pool is None:
            pool = DEFAULT_COST_POOL

        recent_costs = {
            h["cost"] for h in self.history
            if h["chapter"] > chapter_num - self.cooldown
        }
        available = [c for c in pool if c not in recent_costs]
        if not available:
            available = pool

        chosen = random.choice(available)
        self.history.append({"chapter": chapter_num, "cost": chosen})
        return chosen

    def get_recent(self, n: int = 5) -> list[str]:
        """获取最近n个已用代价"""
        return [h["cost"] for h in self.history[-n:]]


# ============================================================
# 四段式Beat模板（从constraints.py合并）
# ============================================================

DEFAULT_BEATS = [
    {
        "label": "钩子",
        "range": [0, 10],
        "unit": "%",
        "rule": "第一句话立刻切入核心冲突或悬念。禁止背景铺垫。必须有动词+感官细节。",
    },
    {
        "label": "阻碍",
        "range": [10, 40],
        "unit": "%",
        "rule": "反派/环境/内心制造情绪压力。通过具体对白和动作展现，禁止概述。",
    },
    {
        "label": "破局",
        "range": [40, 80],
        "unit": "%",
        "rule": "主角利用核心能力降维打击。必须有具体的操作过程，不是一句'他赢了'。",
    },
    {
        "label": "代价与悬念",
        "range": [80, 100],
        "unit": "%",
        "rule": "突破/胜利必须伴随物理代价。结尾必须有断崖式悬念（未完成动作/新危机/反问）。",
    },
]


def get_beat_prompt(chapter_num: int, beats: list[dict] | None = None) -> str:
    """生成四段式beat的prompt注入文本"""
    if beats is None:
        beats = DEFAULT_BEATS

    lines = ["## 四段式节拍（必须严格遵守）\n"]
    for beat in beats:
        label = beat["label"]
        r = beat["range"]
        rule = beat["rule"]
        lines.append(f"- **{label}**（{r[0]}%-{r[1]}%）: {rule}")

    lines.append("\n→ 每一段必须有具体的对白/动作/感官描写，禁止概述性长句。")
    return "\n".join(lines)


# ============================================================
# 概念映射（从constraints.py合并）
# ============================================================

DEFAULT_CONCEPT_MAPPING: dict[str, list[str]] = {}


def load_concept_mapping(project_dir: Path) -> dict[str, list[str]]:
    """从项目配置加载概念映射字典"""
    mapping_file = project_dir / "concept_mapping.json"
    if mapping_file.exists():
        with open(mapping_file, encoding="utf-8") as f:
            return json.load(f)

    world_file = project_dir / "world_rules.json"
    if world_file.exists():
        with open(world_file, encoding="utf-8") as f:
            world = json.load(f)
        return _auto_generate_mapping(world)

    return DEFAULT_CONCEPT_MAPPING


def _auto_generate_mapping(world: dict) -> dict[str, list[str]]:
    """从world_rules自动生成概念映射"""
    import re
    mapping: dict[str, list[str]] = {}

    setting = world.get("setting", {})
    for key, value in setting.items():
        if isinstance(value, str) and value:
            keywords = _extract_keywords_from_text(value)
            if keywords:
                mapping[key] = keywords

    power = world.get("power_system", {})
    if isinstance(power, dict):
        for key, value in power.items():
            if isinstance(value, str) and value:
                keywords = _extract_keywords_from_text(value)
                if keywords:
                    mapping[f"力量体系.{key}"] = keywords
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        keywords = _extract_keywords_from_text(item)
                        if keywords:
                            mapping[f"力量体系.{key}"] = keywords

    rules = world.get("rules", [])
    for i, rule in enumerate(rules):
        if isinstance(rule, str) and len(rule) > 5:
            keywords = _extract_keywords_from_text(rule)
            if keywords:
                mapping[f"规则{i+1}"] = keywords

    return mapping


def _extract_keywords_from_text(text: str) -> list[str]:
    """从文本中提取关键词"""
    import re
    segments = re.split(r'[,，。、；：\s]+', text)
    keywords = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) < 2:
            continue
        zh_words = re.findall(r'[\u4e00-\u9fff]{2,6}', seg)
        en_words = re.findall(r'[a-zA-Z]{2,}', seg)
        for w in zh_words + en_words:
            if len(w) >= 2:
                keywords.append(w)

    stop_words = {"的", "了", "是", "在", "和", "有", "不", "人", "这", "中",
                  "大", "为", "上", "个", "到", "说", "会", "从", "对", "也",
                  "可以", "通过", "进行", "使用", "需要", "已经", "正在",
                  "the", "and", "for", "that", "this", "with", "from", "are",
                  "can", "use", "has", "have", "been", "being"}

    seen = set()
    result = []
    for w in keywords:
        w_lower = w.lower()
        if w_lower not in stop_words and w not in seen:
            seen.add(w)
            result.append(w)
        if len(result) >= 5:
            break
    return result


def get_required_elements_for_chapter(
    mapping: dict[str, list[str]],
    chapter_num: int,
    min_count: int = 2,
) -> list[str]:
    """为本章选择必须出现的设定元素"""
    if not mapping:
        return []

    groups = list(mapping.keys())
    selected_groups = random.sample(groups, min(min_count, len(groups)))

    selected = []
    for group in selected_groups:
        modern_list = mapping[group]
        if modern_list:
            selected.append(random.choice(modern_list))
    return selected


# ============================================================
# 主注入器
# ============================================================

class ConstraintInjector:
    """Scribe约束注入器（v2统一版）"""

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
        """构建约束注入文本块，用于插入Scribe prompt"""
        blocks = []

        # 1. 动态黑名单
        blacklist = self._get_dynamic_blacklist(previous_chapters)
        if blacklist:
            blacklist_text = self._format_blacklist(blacklist)
            blocks.append(blacklist_text)

        # 2. 设定元素清单
        setting_injection = self._build_setting_injection(chapter_num)
        if setting_injection:
            blocks.append(setting_injection)

        # 3. 代价轮盘
        cost_injection = self._build_cost_injection(chapter_num)
        if cost_injection:
            blocks.append(cost_injection)

        # 4. 四段式beat
        beat_text = get_beat_prompt(chapter_num)
        if beat_text:
            blocks.append(beat_text)

        # 5. 禁止结构模板
        structure_ban = self._build_structure_ban(chapter_num)
        if structure_ban:
            blocks.append(structure_ban)

        # 6. 短剧节奏硬指标
        rhythm_requirements = self._build_rhythm_requirements(chapter_num)
        if rhythm_requirements:
            blocks.append(rhythm_requirements)

        return "\n\n".join(blocks)

    def _get_dynamic_blacklist(self, previous_chapters: list[str] | None = None) -> list[str]:
        """获取动态黑名单"""
        if self.blacklist_path.exists():
            return load_blacklist(self.blacklist_path)

        if previous_chapters:
            blacklist = build_dynamic_blacklist(previous_chapters)
            save_blacklist(blacklist, self.blacklist_path)
            return blacklist

        return SEED_BLACKLIST.copy()

    def _format_blacklist(self, blacklist: list[str]) -> str:
        """格式化黑名单为prompt注入文本"""
        top_phrases = blacklist[:30]
        phrases_str = "、".join(f'"{p}"' for p in top_phrases)

        return f"""### 🚫 动态禁用词库（检测到即判定任务失败）

以下短语已被系统标记为高频AI味词汇，绝对禁止在本章中使用：
{phrases_str}

**惩罚机制**：如果本章出现以上任何短语，系统将自动判定任务失败，需要重新生成。
请用具体的、独特的、符合场景的描写替代这些通用表达。"""

    def _build_setting_injection(self, chapter_num: int) -> str:
        """构建设定元素强制注入"""
        concept_mapping = load_concept_mapping(self.project_dir)
        if not concept_mapping:
            return ""

        required = get_required_elements_for_chapter(concept_mapping, chapter_num, min_count=2)
        if not required:
            return ""

        lines = ["### 🏢 本章必须出现的设定元素（至少命中1个）"]
        lines.append("")
        for elem in required:
            lines.append(f"- 必须出现: **{elem}**")
        lines.append("")
        lines.append("以上元素必须自然融入剧情，不能生硬插入。")
        return "\n".join(lines)

    def _build_cost_injection(self, chapter_num: int) -> str:
        """构建代价轮盘注入"""
        # 读取代价历史
        cost_history = []
        if self.cost_history_path.exists():
            try:
                cost_history = json.loads(self.cost_history_path.read_text(encoding='utf-8'))
            except Exception:
                pass

        # 构建轮盘
        roulette = CostRoulette(cooldown=3)
        roulette.history = [{"chapter": h["chapter"], "cost": h["cost"]} for h in cost_history]

        # 选择本章代价
        chosen_cost = roulette.pick(chapter_num, DEFAULT_COST_POOL)

        # 保存代价历史
        cost_history.append({"chapter": chapter_num, "cost": chosen_cost})
        self.cost_history_path.write_text(
            json.dumps(cost_history, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        recent_costs = roulette.get_recent(3)
        recent_str = "、".join(recent_costs) if recent_costs else "无"

        return f"""### 🩺 突破代价规则

本章如果涉及突破/觉醒/力量提升，代价必须是：**{chosen_cost}**
最近已用过的代价（禁止重复）：{recent_str}

→ 代价必须通过具体的生理反应描写展现，不能只写"他付出了代价"。"""

    def _build_structure_ban(self, chapter_num: int) -> str:
        """构建禁止结构模板"""
        banned_patterns = [
            "对峙→揭示→突破→代价",
            "任务→执行→成功→奖励",
            "危机→觉醒→碾压→装逼",
            "日常→被打脸→反击→打脸成功",
        ]

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
        return base_prompt + "\n\n" + injection_block
