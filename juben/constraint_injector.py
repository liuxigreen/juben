"""
Scribe Constraint Injector — Scribe生成前强制动态注入（v3根本改造版）

核心思想：事前熔断 > 事后检查
在Scribe生成prompt之前，强制注入：
1. 动态黑名单（静态种子+正则模式）
2. 动态环境注入（地点+动态元素+物理压力）
3. 结构轮换（禁止连续dialogue_heavy）
4. 物理打断锁（Cliffhanger强制物理动作中断）
5. 对话比例硬指标（对话≤25%）
6. 设定元素配额（必须以动作呈现）
7. 代价轮盘（CostRoulette）
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from .validate.dynamic_blacklist import (
    check_ai_flavor,
    scan_chapter_for_blacklist,
    load_blacklist,
    save_blacklist,
    SEED_BLACKLIST,
)

logger = logging.getLogger(__name__)


# ============================================================
# 结构类型定义
# ============================================================

STRUCTURE_TYPES = [
    "action_heavy",      # 动作≥50%，对话≤25%
    "investigation",     # 调查/发现/探索
    "confrontation",     # 对峙/冲突
    "reveal",            # 揭示真相/信息炸弹
    "chase",             # 追逐/逃跑/紧迫感
    "suspense",          # 悬疑/压迫/环境恐惧
]

# 每种结构的具体要求
STRUCTURE_REQUIREMENTS = {
    "action_heavy": {
        "dialogue_max": 0.25,
        "action_min": 0.50,
        "description": "动作主导：物理动作≥50%，对话≤25%",
        "forbidden": ["纯对话推进", "概述性动作"],
    },
    "investigation": {
        "dialogue_max": 0.30,
        "action_min": 0.35,
        "description": "调查发现：主角主动探索、发现线索、拼凑信息",
        "required_elements": ["发现", "观察", "推理"],
    },
    "confrontation": {
        "dialogue_max": 0.35,
        "action_min": 0.30,
        "description": "对峙冲突：角色间直接冲突，情绪张力拉满",
        "required_elements": ["威胁", "反击", "对视"],
    },
    "reveal": {
        "dialogue_max": 0.30,
        "action_min": 0.35,
        "description": "真相揭示：信息炸弹，颠覆认知",
        "required_elements": ["真相", "意外", "反转"],
    },
    "chase": {
        "dialogue_max": 0.15,
        "action_min": 0.60,
        "description": "追逐紧迫：高速节奏，物理动作密集",
        "required_elements": ["跑", "追", "躲", "逃"],
    },
    "suspense": {
        "dialogue_max": 0.25,
        "action_min": 0.40,
        "description": "悬疑压迫：环境恐惧，感官放大",
        "required_elements": ["异响", "阴影", "不安"],
    },
}


# ============================================================
# 代价轮盘
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
        self.history: list[dict] = []

    def pick(self, chapter_num: int, pool: list[str] | None = None) -> str:
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
        return [h["cost"] for h in self.history[-n:]]


# ============================================================
# 四段式Beat模板
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
# 概念映射
# ============================================================

DEFAULT_CONCEPT_MAPPING: dict[str, list[str]] = {}


def load_concept_mapping(project_dir: Path) -> dict[str, list[str]]:
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
    import re
    mapping: dict[str, list[str]] = {}
    setting = world.get("setting", {})
    for key, value in setting.items():
        if isinstance(value, str) and value:
            keywords = _extract_keywords_from_text(value)
            if keywords:
                mapping[key] = keywords
    return mapping


def _extract_keywords_from_text(text: str) -> list[str]:
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
    stop_words = {"的", "了", "是", "在", "和", "有", "不", "人", "这", "中"}
    seen = set()
    result = []
    for w in keywords:
        if w not in stop_words and w not in seen:
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
# 主注入器（v3根本改造版）
# ============================================================

class ConstraintInjector:
    """Scribe约束注入器（v3根本改造版）"""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.blacklist_path = self.project_dir / "dynamic_blacklist.txt"
        self.curator_state_path = self.project_dir / "curator_state.json"
        self.concept_mapping_path = self.project_dir / "concept_mapping.json"
        self.cost_history_path = self.project_dir / "cost_history.json"
        self.structure_history_path = self.project_dir / "structure_history.json"

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

        # 2. 结构轮换（强制本章结构类型）
        structure_injection = self._build_structure_rotation(chapter_num)
        if structure_injection:
            blocks.append(structure_injection)

        # 3. 对话比例硬指标
        dialogue_ratio = self._build_dialogue_ratio_requirement(chapter_num)
        if dialogue_ratio:
            blocks.append(dialogue_ratio)

        # 4. 设定元素配额
        setting_injection = self._build_setting_quota(chapter_num)
        if setting_injection:
            blocks.append(setting_injection)

        # 5. 代价轮盘
        cost_injection = self._build_cost_injection(chapter_num)
        if cost_injection:
            blocks.append(cost_injection)

        # 6. 四段式beat + 物理打断锁
        beat_text = get_beat_prompt(chapter_num)
        if beat_text:
            blocks.append(beat_text)

        # 7. 物理打断锁（Cliffhanger强制）
        cliffhanger_lock = self._build_cliffhanger_lock(chapter_num)
        if cliffhanger_lock:
            blocks.append(cliffhanger_lock)

        # 8. 短剧节奏硬指标（含视觉铁律）
        rhythm_requirements = self._build_rhythm_requirements(chapter_num)
        if rhythm_requirements:
            blocks.append(rhythm_requirements)

        return "\n\n".join(blocks)

    def _get_dynamic_blacklist(self, previous_chapters: list[str] | None = None) -> list[str]:
        """获取黑名单 — 只使用静态种子，不自动生成"""
        if self.blacklist_path.exists():
            return load_blacklist(self.blacklist_path)
        return SEED_BLACKLIST.copy()

    def _format_blacklist(self, blacklist: list[str]) -> str:
        top_phrases = blacklist[:30]
        phrases_str = "、".join(f'"{p}"' for p in top_phrases)
        return f"""### 🚫 动态禁用词库（检测到即判定任务失败）

以下短语已被系统标记为高频AI味词汇，绝对禁止在本章中使用：
{phrases_str}

**惩罚机制**：如果本章出现以上任何短语，系统将自动判定任务失败，需要重新生成。
请用具体的、独特的、符合场景的描写替代这些通用表达。"""

    # ============================================================
    # 新增：结构轮换
    # ============================================================

    def _build_structure_rotation(self, chapter_num: int) -> str:
        """强制本章结构类型，禁止连续dialogue_heavy"""
        # 读取结构历史
        history = self._load_structure_history()

        # 确定本章结构类型
        structure_type = self._pick_structure_type(chapter_num, history)

        # 保存到历史
        history.append({"chapter": chapter_num, "type": structure_type})
        self._save_structure_history(history)

        # 获取结构要求
        req = STRUCTURE_REQUIREMENTS.get(structure_type, {})

        return f"""### 🎭 本章结构类型（强制）

**本章必须是：{structure_type}**
{req.get('description', '')}

**硬性要求**：
- 对话占比 ≤ {int(req.get('dialogue_max', 0.30) * 100)}%
- 动作/环境描写占比 ≥ {int(req.get('action_min', 0.35) * 100)}%

**禁止**：
- 纯对话推进剧情
- 两人面对面干聊
- 概述性动作描写（"他很愤怒" → 必须用具体动作替代）

**必须**：
- 每2句对话后插入1段物理动作/环境变化
- 角色的注意力必须在"对方"和"环境"之间频繁切换
- 引入"第三物理介质"（手机屏幕/门后异响/倒计时/环境异常）"""

    def _pick_structure_type(self, chapter_num: int, history: list[dict]) -> str:
        """选择本章结构类型，避免连续重复"""
        recent_types = [h["type"] for h in history[-2:]]  # 最近2章的类型

        # 过滤掉最近使用过的类型
        available = [t for t in STRUCTURE_TYPES if t not in recent_types]

        if not available:
            available = STRUCTURE_TYPES

        # 根据章节号轮转，加入随机性
        idx = (chapter_num + random.randint(0, 1)) % len(available)
        return available[idx]

    def _load_structure_history(self) -> list[dict]:
        if self.structure_history_path.exists():
            try:
                return json.loads(self.structure_history_path.read_text(encoding='utf-8'))
            except Exception:
                pass
        return []

    def _save_structure_history(self, history: list[dict]):
        self.structure_history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    # ============================================================
    # 新增：对话比例硬指标
    # ============================================================

    def _build_dialogue_ratio_requirement(self, chapter_num: int) -> str:
        """强制对话比例限制"""
        return """### 📊 对话比例硬指标（违反即熔断）

**规则**：
- 对话总字数 ≤ 全文字数的 25%
- 每出现一句对话（<15字），必须跟随至少 2 段关于"环境观察"或"手部/足部物理微动作"的描写
- 禁止连续3句以上纯对话（必须插入动作/环境/感官）

**为什么**：
对话过多 = 结构单调 = Guardian扣分
动作/环境描写 = 视觉密度 = 可拍摄性 = 高分

**正确示范**：
```
"你是谁？"陈默问。他的手指不自觉地摸了一下右手食指的伤疤。
窗外传来救护车的鸣笛声，由远及近，又渐渐远去。
"王建国。"那个人伸出手。他的左手无名指戴着一枚旧式金戒指，在走廊的灯光下反射出一道暗淡的光。
```"""

    # ============================================================
    # 新增：设定元素配额
    # ============================================================

    def _build_setting_quota(self, chapter_num: int) -> str:
        """强制设定元素配额，必须以动作呈现"""
        concept_mapping = load_concept_mapping(self.project_dir)
        if not concept_mapping:
            return ""

        required = get_required_elements_for_chapter(concept_mapping, chapter_num, min_count=3)
        if not required:
            return ""

        lines = ["### 🏢 设定元素配额（必须完成，否则Guardian熔断）"]
        lines.append("")
        lines.append("**本章必须出现以下设定元素（至少命中2个）：**")
        for elem in required:
            lines.append(f"- **{elem}**")
        lines.append("")
        lines.append("**呈现规则**：")
        lines.append("- ❌ 禁止解释性叙述：\"他是个老练的外卖员\"")
        lines.append("- ✅ 必须通过物理动作/环境互动体现：\"他把电动车停在监控死角，习惯性抬头看了眼摄像头角度\"")
        lines.append("- 设定元素必须成为剧情推进的物理载体，不是背景板")
        return "\n".join(lines)

    # ============================================================
    # 新增：物理打断锁（Cliffhanger强制）
    # ============================================================

    def _build_cliffhanger_lock(self, chapter_num: int) -> str:
        """强制Cliffhanger使用物理打断，禁止纯问句结尾"""
        return """### 🔒 物理打断锁（Cliffhanger强制 — 违反即熔断）

**结尾强制范式**：
`[主角即将完成某个动作] + [外界物理异象瞬间爆发/强行打断] + [视觉定格]`

**禁止**：
- ❌ 纯问句结尾：\"难道凶手是他？\"
- ❌ 概述性结尾：\"他不知道该怎么办\"
- ❌ 平淡收尾：\"他走进雨里\"

**必须**：
- ✅ 物理动作被打断：\"他伸手按向门铃，指尖还没碰到按钮——\"
- ✅ 突发物理异象：\"门缝里突然渗出一股粘稠的血水\"
- ✅ 感官冲击定格：\"隔壁的电梯井里，传来一声铁链剧烈拉扯的巨响\"

**正确示范**：
```
陈默伸手按向404室的门铃。指尖还没碰到按钮，门缝里突然渗出一股粘稠的血水，缓缓漫过了他的脚面。
隔壁的电梯井里，传来一声铁链剧烈拉扯的巨响——
```

**核心原则**：结尾必须让读者的身体产生反应（心跳加速/屏息/寒毛竖起），不能只是让读者\"思考\"。"""

    # ============================================================
    # 原有：代价轮盘
    # ============================================================

    def _build_cost_injection(self, chapter_num: int) -> str:
        cost_history = []
        if self.cost_history_path.exists():
            try:
                cost_history = json.loads(self.cost_history_path.read_text(encoding='utf-8'))
            except Exception:
                pass

        roulette = CostRoulette(cooldown=3)
        roulette.history = [{"chapter": h["chapter"], "cost": h["cost"]} for h in cost_history]
        chosen_cost = roulette.pick(chapter_num, DEFAULT_COST_POOL)

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

    # ============================================================
    # 原有：禁止结构模板（已废弃，用结构轮换替代）
    # ============================================================

    def _build_structure_ban(self, chapter_num: int) -> str:
        """已废弃，保留兼容性"""
        return ""

    # ============================================================
    # 原有：短剧节奏硬指标（含视觉铁律）
    # ============================================================

    def _build_rhythm_requirements(self, chapter_num: int) -> str:
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
- 必须使用「物理打断锁」（见上方规则）
- 禁止：一切归于平静、她闭上眼睛、新世界开始了

**4. 视觉密度要求**：
- 纯叙述（无法拍摄的文字）占比不超过30%
- 每个场景必须有至少1个物理动作描写
- 对话不能连续超过2句不插入动作或环境变化

**5. 视觉铁律（违反即熔断）**：
- ❌ 禁止纯心理描写："他心想"、"她感到绝望"、"他意识到" → 必须用动作/表情/环境外化情绪
- ❌ 禁止概述性长句："她非常愤怒" → 用具体动作替代（"她的指甲陷进掌心，血珠渗出"）"""


def build_constrained_scribe_prompt(
    chapter_num: int,
    project_dir: str | Path,
    base_prompt: str,
    previous_chapters: list[str] | None = None,
) -> str:
    """构建带约束注入的Scribe prompt"""
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
