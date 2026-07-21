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

        # 3. 追踪代价使用
        cost_pool = [
            "鼻血", "耳鸣", "视线模糊", "手脚发麻", "记忆闪回",
            "灵气失控", "指甲断裂", "吐血", "太阳穴剧痛", "肌肉痉挛",
            "呼吸困难", "心跳紊乱", "短暂失聪", "视野发红", "口中血腥味",
        ]
        for cost in cost_pool:
            if cost in text:
                ch_state.body_costs.append(cost)
                self.accumulated_costs.append(cost)

        # 4. 追踪境界变化
        realm_keywords = {
            "筑基": "筑基", "金丹": "金丹", "元婴": "元婴", "化神": "化神",
            "渡劫": "渡劫", "大乘": "大乘", "飞升": "飞升",
        }
        for keyword, realm in realm_keywords.items():
            if keyword in text and realm != self.current_realm:
                ch_state.realm_change = f"{self.current_realm} → {realm}"
                self.current_realm = realm
                self.realm_progress[realm] = self.realm_progress.get(realm, 0) + 1

        # 5. 更新health状态
        if ch_state.body_costs:
            # 累积代价越多，health越差
            total_costs = len(self.accumulated_costs)
            if total_costs >= 10:
                ch_state.realm_change += " [身体接近极限]"

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
