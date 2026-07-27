"""
Curator状态追踪器 — 跨章节状态管理

职责：
1. 追踪主角身体状态（累积突破代价、承受极限）
2. 追踪每章设定元素使用情况
3. 自动更新动态禁用短语
4. 追踪伏笔埋设/回收
5. 境界进度锁
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from collections import Counter

from juben.constraints import extract_high_frequency_phrases, BASE_BLACKLIST


@dataclass
class ChapterState:
    """单章状态快照"""
    chapter_num: int
    body_costs: list[str] = field(default_factory=list)  # 本章使用的代价
    setting_elements_used: list[str] = field(default_factory=list)  # 本章使用的设定元素
    new_banned_phrases: list[str] = field(default_factory=list)  # 本章新增的禁用短语
    realm_change: str = ""  # 本章境界变化
    foreshadow_planted: list[str] = field(default_factory=list)  # 本章埋的伏笔
    foreshadow_resolved: list[str] = field(default_factory=list)  # 本章收的伏笔


@dataclass
class CuratorState:
    """全局Curator状态"""
    project_dir: Path
    chapters: list[ChapterState] = field(default_factory=list)
    accumulated_costs: list[str] = field(default_factory=list)  # 所有代价历史
    accumulated_banned: list[str] = field(default_factory=list)  # 累积禁用短语
    current_realm: str = ""  # 当前境界
    realm_progress: dict[str, int] = field(default_factory=dict)  # 境界进度追踪

    STATE_FILE = "curator_state.json"

    def save(self):
        """保存状态到JSON"""
        path = self.project_dir / self.STATE_FILE
        data = {
            "chapters": [
                {
                    "chapter_num": c.chapter_num,
                    "body_costs": c.body_costs,
                    "setting_elements_used": c.setting_elements_used,
                    "new_banned_phrases": c.new_banned_phrases,
                    "realm_change": c.realm_change,
                    "foreshadow_planted": c.foreshadow_planted,
                    "foreshadow_resolved": c.foreshadow_resolved,
                }
                for c in self.chapters
            ],
            "accumulated_costs": self.accumulated_costs,
            "accumulated_banned": self.accumulated_banned,
            "current_realm": self.current_realm,
            "realm_progress": self.realm_progress,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, project_dir: Path) -> "CuratorState":
        """从JSON加载状态"""
        path = project_dir / cls.STATE_FILE
        state = cls(project_dir=project_dir)

        if not path.exists():
            return state

        data = json.loads(path.read_text(encoding="utf-8"))
        state.accumulated_costs = data.get("accumulated_costs", [])
        state.accumulated_banned = data.get("accumulated_banned", [])
        state.current_realm = data.get("current_realm", "")
        state.realm_progress = data.get("realm_progress", {})

        for ch_data in data.get("chapters", []):
            state.chapters.append(ChapterState(
                chapter_num=ch_data["chapter_num"],
                body_costs=ch_data.get("body_costs", []),
                setting_elements_used=ch_data.get("setting_elements_used", []),
                new_banned_phrases=ch_data.get("new_banned_phrases", []),
                realm_change=ch_data.get("realm_change", ""),
                foreshadow_planted=ch_data.get("foreshadow_planted", []),
                foreshadow_resolved=ch_data.get("foreshadow_resolved", []),
            ))

        return state

    def update_chapter(self, chapter_num: int, text: str, concept_mapping: dict | None = None):
        """章节写完后更新状态"""
        from juben.constraints import check_setting_elements

        ch_state = ChapterState(chapter_num=chapter_num)

        # 1. 提取本章高频词作为下轮禁用短语
        new_banned = extract_high_frequency_phrases(text, min_count=1)
        ch_state.new_banned_phrases = new_banned
        self.accumulated_banned = list(set(self.accumulated_banned + new_banned))

        # 2. 追踪设定元素使用
        if concept_mapping:
            found, _ = check_setting_elements(text, [], concept_mapping=concept_mapping)
            ch_state.setting_elements_used = found

        # 3. 追踪代价使用（通用代价池，适用于任何题材）
        _PAST_CONTEXT = ["回忆", "想起", "记得", "当时", "那时候", "当年",
                         "三年前", "五年前", "十年前", "十五年前", "八年前",
                         "上次", "以前", "过去", "曾经", "提到", "说起"]
        cost_pool = [
            # 疼痛/身体损伤
            "疼痛", "发麻", "抽搐", "痉挛", "发抖", "颤抖",
            "吐血", "咳血", "鼻血", "伤口", "骨折", "扭伤",
            # 感官异常
            "耳鸣", "视线模糊", "视野发红", "短暂失聪", "失明",
            "嗅觉", "味觉", "触觉", "幻觉", "幻听",
            # 心理/精神
            "心跳紊乱", "呼吸困难", "胸闷", "窒息", "头晕", "恶心",
            "恐惧", "焦虑", "绝望", "崩溃", "失忆", "记忆闪回",
            # 衰老/超自然代价
            "老年斑", "白发", "皱纹", "衰老", "寿命", "代价",
            # 通用
            "出血", "昏迷", "休克", "中毒", "感染",
        ]
        for cost in cost_pool:
            # 检查代价是否在当前发生（非回忆/提及）
            if cost in text:
                import re as _re
                is_past = False
                for m in _re.finditer(_re.escape(cost), text):
                    start = max(0, m.start() - 10)
                    prefix = text[start:m.start()]
                    if any(kw in prefix for kw in _PAST_CONTEXT):
                        is_past = True
                        break
                if not is_past:
                    ch_state.body_costs.append(cost)
                    self.accumulated_costs.append(cost)

        # 4. 追踪阶段/状态变化（从项目world_rules.json加载，兼容任何题材）
        # 默认的通用阶段关键词（悬疑/现代/现实题材）
        realm_keywords = {
            "第一幕": "入局", "第二幕": "升级", "第三幕": "高潮", "第四幕": "收尾",
            "转折": "转折", "危机": "危机", "觉醒": "觉醒", "突破": "突破",
        }
        # 尝试从项目world_rules加载自定义阶段
        try:
            world_rules_path = self.project_dir / "world_rules.json"
            if world_rules_path.exists():
                import json as _json
                world_rules = _json.loads(world_rules_path.read_text(encoding="utf-8"))
                custom_realms = world_rules.get("realm_keywords", {})
                if custom_realms:
                    realm_keywords = custom_realms
        except Exception:
            pass  # 使用默认值

        for keyword, realm in realm_keywords.items():
            if keyword in text and realm != self.current_realm:
                ch_state.realm_change = f"{self.current_realm} → {realm}"
                self.current_realm = realm
                self.realm_progress[realm] = self.realm_progress.get(realm, 0) + 1

        # 5. 更新health状态（通用：代价累积越多，状态越差）
        if ch_state.body_costs:
            total_costs = len(self.accumulated_costs)
            unique_costs = len(set(self.accumulated_costs))
            if total_costs >= 10 or unique_costs >= 6:
                ch_state.realm_change += " [身体接近极限]"
            elif total_costs >= 5 or unique_costs >= 3:
                ch_state.realm_change += " [身体负担中等]"

        # 去重：如果已有同chapter_num的记录，替换而非追加
        existing_idx = None
        for i, ch in enumerate(self.chapters):
            if ch.chapter_num == chapter_num:
                existing_idx = i
                break
        if existing_idx is not None:
            self.chapters[existing_idx] = ch_state
        else:
            self.chapters.append(ch_state)
        self.save()

    def get_cost_history(self, lookback: int = 3) -> list[str]:
        """获取最近N章的代价历史"""
        if not self.chapters:
            return []
        recent = self.chapters[-lookback:]
        costs = []
        for ch in recent:
            costs.extend(ch.body_costs)
        return costs

    def get_banned_phrases(self, lookback: int = 3) -> list[str]:
        """获取最近N章的禁用短语"""
        if not self.chapters:
            return []
        recent = self.chapters[-lookback:]
        banned = set()
        for ch in recent:
            banned.update(ch.new_banned_phrases)
        return sorted(banned)

    def get_realm_lock(self, max_realm_per_chapter: int = 1) -> Optional[str]:
        """检查境界进度是否过快"""
        if not self.chapters:
            return None

        # 检查最近3章是否有境界跳跃
        recent = self.chapters[-3:]
        realm_jumps = sum(1 for ch in recent if ch.realm_change)

        if realm_jumps > max_realm_per_chapter:
            return f"境界提升过快：最近3章有{realm_jumps}次境界变化，限制为{max_realm_per_chapter}次"

        return None

    def get_setting_coverage(self, lookback: int = 3) -> dict:
        """获取最近N章的设定元素覆盖情况"""
        if not self.chapters:
            return {"covered": [], "total_groups": 0, "coverage_ratio": 0}

        recent = self.chapters[-lookback:]
        all_used = set()
        for ch in recent:
            all_used.update(ch.setting_elements_used)

        return {
            "covered": sorted(all_used),
            "count": len(all_used),
        }

    def get_health_report(self) -> str:
        """生成主角健康报告"""
        if not self.chapters:
            return "无状态数据"

        total_costs = len(self.accumulated_costs)
        recent_costs = self.get_cost_history(5)
        unique_costs = len(set(self.accumulated_costs))

        lines = [
            f"当前境界: {self.current_realm or '未设定'}",
            f"累积代价次数: {total_costs}",
            f"不同代价种类: {unique_costs}",
            f"最近5章代价: {', '.join(recent_costs) or '无'}",
            f"禁用短语数: {len(self.accumulated_banned)}",
        ]

        if total_costs >= 10:
            lines.append("⚠️ 身体接近极限，后续突破需更强代价或恢复期")
        elif total_costs >= 5:
            lines.append("⚡ 身体负担中等，注意代价多样性")

        return "\n".join(lines)


# ============================================================
# 新增：叙事范式追踪器（防止描写复读）
# ============================================================

# 定义描写范式关键词
NARRATIVE_MOTIFS = {
    "ear_bleeding": {
        "keywords": ["耳朵听不见", "耳鸣", "耳朵流血", "左耳", "听力"],
        "description": "耳朵出血/听力丧失",
    },
    "nosebleed": {
        "keywords": ["流鼻血", "鼻血", "鼻孔涌出", "鼻子出血"],
        "description": "流鼻血",
    },
    "hand_pain": {
        "keywords": ["手背刺痛", "手背发麻", "手背疼痛", "右手背", "老年斑扩散"],
        "description": "手背疼痛/老年斑",
    },
    "file_list_recite": {
        "keywords": ["第一页施工日志", "第二页监理签字表", "第三页材料检测报告", "第八页36人名单"],
        "description": "文件清单罗列",
    },
    "visit_and_leave": {
        "keywords": ["走到", "看了一眼", "转身离开", "走开", "离开了"],
        "description": "访问后离开",
    },
    "blood_dripping": {
        "keywords": ["血从", "渗出来", "滴下来", "沾着血", "血腥味"],
        "description": "血液滴落",
    },
}


class NarrativeMotifTracker:
    """叙事范式追踪器 — 防止描写复读"""

    def __init__(self, cooldown: int = 3):
        self.cooldown = cooldown
        self.history: list[dict] = []

    def detect_motifs(self, text: str) -> list[str]:
        """检测文本中的描写范式"""
        detected = []
        for motif_id, motif_info in NARRATIVE_MOTIFS.items():
            keywords = motif_info["keywords"]
            count = sum(text.count(kw) for kw in keywords)
            if count >= 2:  # 至少出现2次才算
                detected.append(motif_id)
        return detected

    def record_chapter(self, chapter_num: int, text: str):
        """记录章节的描写范式"""
        motifs = self.detect_motifs(text)
        self.history.append({
            "chapter": chapter_num,
            "motifs": motifs,
        })

    def get_banned_motifs(self, chapter_num: int) -> list[str]:
        """获取本章禁用的描写范式"""
        recent = [
            h for h in self.history
            if h["chapter"] > chapter_num - self.cooldown
        ]
        banned = set()
        for h in recent:
            banned.update(h["motifs"])
        return sorted(banned)

    def get_injection_text(self, chapter_num: int) -> str:
        """生成描写范式禁用注入文本"""
        banned = self.get_banned_motifs(chapter_num)
        if not banned:
            return ""

        banned_descriptions = []
        for motif_id in banned:
            if motif_id in NARRATIVE_MOTIFS:
                banned_descriptions.append(NARRATIVE_MOTIFS[motif_id]["description"])

        if not banned_descriptions:
            return ""

        ban_list = "、".join(banned_descriptions)
        return f"""### 🚫 描写范式冷却（强制）

最近{self.cooldown}章已使用过以下描写范式，本章**绝对禁止**再用：
**禁用范式**：{ban_list}

**替代方案**：
- 耳朵出血 → 换用"视野偏色"、"肌肉痉挛"、"发冷"
- 流鼻血 → 换用"视线模糊"、"心跳紊乱"、"呼吸困难"
- 手背刺痛 → 换用"视野发红"、"短暂失聪"、"口中血腥味"
- 文件清单罗列 → 换用"那份泛黄的C25偷工减料卷宗"一笔带过
- 访问后离开 → 换用"对话被打断"、"新危机出现"、"时间倒计时"

**惩罚机制**：如果本章重复使用禁用范式，系统将自动判定任务失败。"""


# ============================================================
# P0-3: Behavior Sequence Cooling
# ============================================================

BEHAVIOR_TEMPLATES = {
    "ability_trigger": {
        "steps": [
            ["端起", "拿起", "接过", "举杯"],
            ["闭眼", "闭上眼", "合上眼"],
            ["安静", "消失了", "声音都", "世界安静"],
            ["听到", "心声", "声音", "脑海里"],
            ["放下", "杯子放下", "睁开眼"],
        ],
        "description": "端杯-闭眼-世界安静-听心声-放下杯",
        "cooldown": 3,
    },
    "discovery_visit": {
        "steps": [
            ["走到", "来到", "走进"],
            ["看到", "发现", "注意到"],
            ["转身离开", "走开", "离开了"],
        ],
        "description": "走到某处-看到某物-转身离开",
        "cooldown": 2,
    },
    "cost_reaction": {
        "steps": [
            ["疼痛", "刺痛", "发麻", "发抖"],
            ["低头看", "看向自己的", "摸了摸"],
            ["发现", "注意到", "看到"],
        ],
        "description": "身体疼痛-低头查看-发现异常",
        "cooldown": 2,
    },
}


class BehaviorSequenceTracker:
    HISTORY_FILE = "behavior_sequence_history.json"

    def __init__(self, project_dir):
        from pathlib import Path as _Path
        self.project_dir = _Path(project_dir)
        self.history_path = self.project_dir / self.HISTORY_FILE
        self.history = self._load_history()

    def _load_history(self):
        import json
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history(self):
        import json
        self.history_path.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def detect_sequences(self, text):
        detected = []
        for seq_id, seq_info in BEHAVIOR_TEMPLATES.items():
            steps = seq_info["steps"]
            matched = 0
            for step_keywords in steps:
                if any(kw in text for kw in step_keywords):
                    matched += 1
            if matched >= len(steps) - 1:
                detected.append(seq_id)
        return detected

    def record_chapter(self, chapter_num, text):
        sequences = self.detect_sequences(text)
        if sequences:
            self.history.append({"chapter": chapter_num, "sequences": sequences})
            self._save_history()

    def get_banned_sequences(self, chapter_num):
        banned = set()
        for seq_id, seq_info in BEHAVIOR_TEMPLATES.items():
            cooldown = seq_info["cooldown"]
            recent = [
                h for h in self.history
                if h["chapter"] > chapter_num - cooldown
                and seq_id in h.get("sequences", [])
            ]
            if recent:
                banned.add(seq_id)
        return sorted(banned)

    def get_injection_text(self, chapter_num):
        banned = self.get_banned_sequences(chapter_num)
        if not banned:
            return ""

        lines = ["### 行为序列冷却 (enforced)\n"]
        lines.append("Recent chapters used these action templates. This chapter MUST NOT repeat:\n")
        for seq_id in banned:
            if seq_id in BEHAVIOR_TEMPLATES:
                tmpl = BEHAVIOR_TEMPLATES[seq_id]
                lines.append(f"- BANNED: {tmpl['description']}")

        lines.append("")
        lines.append("Alternatives:")
        lines.append("- Ability trigger -> use peripheral vision detail, steam sound, liquid ripple")
        lines.append("- Discovery+leave -> use interruption, new crisis, character follows")
        lines.append("- Pain reaction -> use environment change first (light flicker), then discover")
        lines.append("")
        lines.append("Violation = task failure.")

        return "\n".join(lines)
