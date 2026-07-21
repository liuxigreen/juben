"""
动态约束管理器 — 跨章节状态追踪

职责：
1. 维护动态禁用短语列表（从最近N章提取）
2. 维护突破代价轮盘（防止代价重复）
3. 追踪大厂/设定元素使用情况
4. 提供四段式beat模板
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Optional


# ============================================================
# 代价轮盘（题材无关，通用）
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
            # 池子用完了，重置
            available = pool

        chosen = random.choice(available)
        self.history.append({"chapter": chapter_num, "cost": chosen})
        return chosen

    def get_recent(self, n: int = 5) -> list[str]:
        """获取最近n个已用代价"""
        return [h["cost"] for h in self.history[-n:]]


# ============================================================
# 动态禁用短语管理
# ============================================================

# 基础黑名单（题材无关的AI味高频词）
BASE_BLACKLIST = [
    "喃喃自语", "嘴角勾起一抹笑", "眼睛里闪过一丝光芒",
    "感觉到自己的血液在沸腾", "感觉到自己的战意在升腾",
    "两人的剑光在空中交错", "发出耀眼的光芒",
    "你果然有仙帝的风范", "他的眼睛亮了",
    "感觉到自己的心跳在加速", "脸色变得苍白",
    "嘴巴张了张，想说什么，但又说不出来",
    "嘴角动了动", "有意思", "嘴角微微上扬",
    "嘴角勾起", "嘴角扬起",
]


def extract_high_frequency_phrases(
    text: str,
    min_count: int = 2,
    extra_phrases: list[str] | None = None,
) -> list[str]:
    """从文本中提取高频短语"""
    phrases = list(BASE_BLACKLIST)
    if extra_phrases:
        phrases.extend(extra_phrases)

    found = []
    for phrase in phrases:
        count = text.count(phrase)
        if count >= min_count:
            found.append(phrase)
    return found


def build_dynamic_banlist(
    chapters_dir: Path,
    current_chapter: int,
    lookback: int = 3,
    extra_phrases: list[str] | None = None,
) -> list[str]:
    """从最近N章构建动态禁用短语列表"""
    all_banned = set()

    for i in range(max(1, current_chapter - lookback), current_chapter):
        chapter_file = chapters_dir / f"{i:03d}.md"
        if chapter_file.exists():
            text = chapter_file.read_text(encoding="utf-8")
            banned = extract_high_frequency_phrases(text, min_count=1, extra_phrases=extra_phrases)
            all_banned.update(banned)

    return sorted(all_banned)


# ============================================================
# 四段式Beat模板（题材无关）
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
# 设定元素追踪
# ============================================================

def check_setting_elements(
    text: str,
    required_elements: list[str],
    concept_mapping: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[str]]:
    """检查文本中是否包含必需的设定元素
    
    使用模糊匹配：元素的核心词出现在文本中即可。
    如果提供了concept_mapping，检查所有组——任意1组有命中即算通过。
    
    Returns:
        (found_elements, missing_elements)
    """
    found = []
    missing = []
    text_lower = text.lower()
    
    # 如果有concept_mapping，按组检查（更宽松）
    if concept_mapping:
        matched_groups = 0
        total_groups = len(concept_mapping)
        for group_name, group_elements in concept_mapping.items():
            group_found = False
            for elem in group_elements:
                core_words = _extract_core_words(elem)
                if any(cw.lower() in text_lower for cw in core_words):
                    group_found = True
                    found.append(elem)
                    break
            if not group_found:
                missing.append(group_name)
            else:
                matched_groups += 1
        return found, missing
    
    # 没有concept_mapping时，用required_elements精确检查
    for elem in required_elements:
        core_words = _extract_core_words(elem)
        matched = any(cw.lower() in text_lower for cw in core_words)
        if matched:
            found.append(elem)
        else:
            missing.append(elem)
    return found, missing


def _extract_core_words(element: str) -> list[str]:
    """从设定元素中提取核心匹配词
    
    策略：
    1. 整个元素本身
    2. 按/分割的每个部分
    3. 去掉"器/机/库/架构/协议"等后缀的词根
    """
    cores = [element]
    
    # 按常见分隔符分割
    for sep in ["/", "、", ",", " "]:
        if sep in element:
            cores.extend(element.split(sep))
    
    # 提取词根（去掉常见后缀）
    suffixes = ["信号源", "编译器", "服务器", "机柜", "代码库", "算法架构", 
                "报警", "隧道", "协议", "流水线", "分析", "规则", "抓包",
                "扫描", "嗅探", "文档", "过载", "断网", "查岗", "审查"]
    for suffix in suffixes:
        if element.endswith(suffix):
            root = element[:-len(suffix)]
            if len(root) >= 2:
                cores.append(root)
    
    # 对于中文，也取前2-3个字作为核心词
    if len(element) >= 3:
        cores.append(element[:2])
        cores.append(element[:3])
    
    return list(set(cores))


# ============================================================
# 概念映射字典（通用模板，每个项目可自定义）
# ============================================================

DEFAULT_CONCEPT_MAPPING: dict[str, list[str]] = {}


def load_concept_mapping(project_dir: Path) -> dict[str, list[str]]:
    """从项目配置加载概念映射字典"""
    mapping_file = project_dir / "concept_mapping.json"
    if mapping_file.exists():
        with open(mapping_file, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONCEPT_MAPPING


def get_required_elements_for_chapter(
    mapping: dict[str, list[str]],
    chapter_num: int,
    min_count: int = 2,
) -> list[str]:
    """为本章选择必须出现的设定元素
    
    策略：随机选min_count个概念组，每组取1个元素。
    这样检查点少但覆盖面广，减少误报。
    """
    if not mapping:
        return []

    # 随机选min_count个概念组
    groups = list(mapping.keys())
    selected_groups = random.sample(groups, min(min_count, len(groups)))
    
    selected = []
    for group in selected_groups:
        modern_list = mapping[group]
        if modern_list:
            selected.append(random.choice(modern_list))

    return selected
