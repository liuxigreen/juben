"""
Story Budget — 项目级资源消费追踪（防"故事线跑光"）

核心问题: 30章神算子证明,引擎能保证"这章写好",但无法回答"这故事还能不能继续"。
本模块提供三个核心能力:
  1. StoryBudget: 实体/符号消费配额追踪
  2. ArcStateTracker: 角色弧状态机
  3. check_chapter_feasibility(): 写下一章前的可行性检查

数据文件: <project>/story_budget.json
          <project>/world_inventory.json
          <project>/character_arcs.json (从characters.json的arc字段提取,不重复存储)

集成点:
  - juben write N → 写prompt前调用 check_chapter_feasibility()
  - juben commit N → commit后调用 StoryBudget.consume() / ArcStateTracker.update()
  - juben budget → CLI命令,查看资源消耗表
  - juben world register/ban → CLI命令,管理world_inventory
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


# ============================================================
# 1. Story Budget — 实体/符号消费配额
# ============================================================

class StoryBudget:
    """
    项目级资源消费追踪器。

    实体配额概念:
      - first_appear: 该实体首次出现的章节
      - quota: 计划总使用次数
      - consumed: 已使用次数
      - exhausted_at: 配额耗尽的章节
    """

    STATE_FILE = "story_budget.json"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.state_file = self.project_dir / self.STATE_FILE
        self.data = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {"entities": {}, "version": "1.0"}

    def save(self):
        self.state_file.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_entity(self, name: str, quota: int, first_appear: int = 0,
                        entity_type: str = "symbol", note: str = ""):
        """注册一个实体并设置配额。"""
        if name not in self.data["entities"]:
            self.data["entities"][name] = {
                "type": entity_type,
                "first_appear": first_appear,
                "quota": quota,
                "consumed": 0,
                "exhausted_at": None,
                "consume_history": [],
                "note": note,
            }
            self.save()

    def consume(self, name: str, chapter: int, count: int = 1) -> dict:
        """
        记录一次消费。返回 {"ok": bool, "exhausted": bool, "remaining": int, "warning": str}
        """
        if name not in self.data["entities"]:
            # 自动注册,默认配额5
            self.register_entity(name, quota=5, first_appear=chapter)

        ent = self.data["entities"][name]
        ent["consumed"] += count
        ent["consume_history"].append({"chapter": chapter, "count": count})
        remaining = ent["quota"] - ent["consumed"]

        warning = ""
        exhausted = False
        if remaining <= 0 and ent["exhausted_at"] is None:
            ent["exhausted_at"] = chapter
            exhausted = True
            warning = f"实体'{name}'配额耗尽(用{ent['consumed']}/{ent['quota']}次)"
        elif remaining <= max(1, ent["quota"] * 0.2):
            warning = f"实体'{name}'配额紧张(剩{remaining}/{ent['quota']}次)"

        self.save()
        return {
            "ok": True,
            "exhausted": exhausted,
            "remaining": remaining,
            "warning": warning,
        }

    def get_status(self, name: str) -> dict | None:
        return self.data["entities"].get(name)

    def list_all(self) -> list[dict]:
        """返回所有实体状态,按耗尽程度排序。"""
        result = []
        for name, ent in self.data["entities"].items():
            result.append({
                "name": name,
                "type": ent.get("type", "symbol"),
                "quota": ent["quota"],
                "consumed": ent["consumed"],
                "remaining": ent["quota"] - ent["consumed"],
                "exhausted_at": ent.get("exhausted_at"),
                "note": ent.get("note", ""),
            })
        # 按剩余配额升序(最紧张的最先)
        result.sort(key=lambda x: x["remaining"])
        return result

    def get_exhausted_entities(self) -> list[str]:
        return [name for name, ent in self.data["entities"].items()
                if ent.get("exhausted_at") is not None]


# ============================================================
# 2. Character Arc State Machine — 角色弧状态机
# ============================================================

ArcState = Literal["pending", "active", "climax", "resolved"]


class ArcStateTracker:
    """
    追踪每个角色的arc状态。

    状态流转:
      pending → active → climax → resolved
        ↑          ↓
        └──────────┘ (midpoint回到pending表示revisit)

    关键判断:
      - 如果主角arc.state == "resolved" → 故事应已结束
      - 如果主角arc.unfinished_business == [] 且 state != "resolved"
        → 引擎警告"主角无未完成事项,可能漏设或故事该收尾"
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self._characters_cache = None

    def _load_characters(self) -> list[dict]:
        """从characters.json加载,自动合并arc运行时状态。"""
        if self._characters_cache is not None:
            return self._characters_cache
        path = self.project_dir / "characters.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        self._characters_cache = data if isinstance(data, list) else data.get("characters", [])
        return self._characters_cache

    def get_arc_state(self, char_id: str) -> dict:
        """获取指定角色的arc状态。"""
        for c in self._load_characters():
            if c.get("id") == char_id:
                arc = c.get("arc", {}) or {}
                return {
                    "id": c["id"],
                    "name": c.get("name", ""),
                    "state": arc.get("state", "pending"),
                    "unfinished_business": arc.get("unfinished_business", []),
                    "resolved_chapter": arc.get("resolved_chapter"),
                    "activation_chapter": arc.get("activation_chapter"),
                    "role": c.get("role", "supporting"),
                }
        return {}

    def set_arc_state(self, char_id: str, state: ArcState,
                      chapter: int | None = None,
                      unresolved_business: list[str] | None = None):
        """
        修改characters.json中的arc状态(直接写入,运行时必须谨慎)。
        通常由Curator在commit时调用,不应在前台user prompt流程手动调用。
        """
        path = self.project_dir / "characters.json"
        if not path.exists():
            raise FileNotFoundError(f"找不到{path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        chars = data if isinstance(data, list) else data.get("characters", [])
        for c in chars:
            if c.get("id") == char_id:
                c.setdefault("arc", {})
                c["arc"]["state"] = state
                if chapter is not None:
                    if state == "active" and "activation_chapter" not in c["arc"]:
                        c["arc"]["activation_chapter"] = chapter
                    if state == "resolved":
                        c["arc"]["resolved_chapter"] = chapter
                if unresolved_business is not None:
                    c["arc"]["unfinished_business"] = unresolved_business
                break
        # 写回(保持原结构)
        if isinstance(data, list):
            path.write_text(json.dumps(chars, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            data["characters"] = chars
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._characters_cache = chars

    def get_protagonist_arc(self) -> dict:
        """获取主角的arc状态。"""
        for c in self._load_characters():
            if c.get("role") == "protagonist":
                return self.get_arc_state(c["id"])
        return {}

    def all_arcs_resolved(self) -> bool:
        """检查是否所有角色的arc都已resolved。"""
        chars = self._load_characters()
        if not chars:
            return False
        for c in chars:
            arc = c.get("arc", {}) or {}
            if arc.get("state") != "resolved":
                return False
        return True


# ============================================================
# 3. World Inventory — 地理+视觉符号库
# ============================================================

class WorldInventory:
    """
    世界符号中央登记簿。

    解决问题: 防止LLM在prompt里随口编新地名/新符号,这些未注册的
    元素没有视觉根基,读者立即出戏。

    规则:
      - 章节里出现未注册的location/symbol = 违规
      - banned列表里的元素 = 硬禁用
    """

    STATE_FILE = "world_inventory.json"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.state_file = self.project_dir / self.STATE_FILE
        self.data = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {
            "locations": [],
            "symbols": [],
            "banned": [],
            "version": "1.0",
        }

    def save(self):
        self.state_file.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_location(self, name: str, symbol_meaning: str = "",
                           first_chapter: int = 0):
        """注册一个新地点。"""
        for loc in self.data["locations"]:
            if loc["name"] == name:
                return  # 已存在
        self.data["locations"].append({
            "name": name,
            "symbol": symbol_meaning,
            "first_appear": first_chapter,
        })
        self.save()

    def register_symbol(self, name: str, meaning: str = "",
                        first_chapter: int = 0, usage_quota: int = 3):
        """注册一个新视觉符号。"""
        for sym in self.data["symbols"]:
            if sym["name"] == name:
                return
        self.data["symbols"].append({
            "name": name,
            "meaning": meaning,
            "first_appear": first_chapter,
            "usage_quota": usage_quota,
        })
        self.save()

    def ban(self, name: str, reason: str = ""):
        """禁用一个名称(地理或符号)。"""
        for b in self.data["banned"]:
            if b["name"] == name:
                return
        self.data["banned"].append({"name": name, "reason": reason})
        self.save()

    def unban(self, name: str):
        self.data["banned"] = [b for b in self.data["banned"] if b["name"] != name]
        self.save()

    def is_registered(self, name: str) -> bool:
        for loc in self.data["locations"]:
            if loc["name"] == name:
                return True
        for sym in self.data["symbols"]:
            if sym["name"] == name:
                return True
        return False

    def is_banned(self, name: str) -> bool:
        return any(b["name"] == name for b in self.data["banned"])

    def get_registered_names(self) -> set[str]:
        names = set()
        for loc in self.data["locations"]:
            names.add(loc["name"])
        for sym in self.data["symbols"]:
            names.add(sym["name"])
        return names

    def get_banned_names(self) -> set[str]:
        return {b["name"] for b in self.data["banned"]}

    def list_all(self) -> dict:
        return {
            "locations": list(self.data["locations"]),
            "symbols": list(self.data["symbols"]),
            "banned": list(self.data["banned"]),
        }

    def auto_register_from_text(self, text: str, chapter: int,
                                 known_terms: set[str] | None = None):
        """
        启发式: 从文本中自动发现新地点/符号。
        规则: 已知terms里的不算,其它长度>=2且不在banned里的
        出现>=2次的专有名词自动加入symbols。
        """
        import re
        known = known_terms or set()
        # 找中文专有名词(2-6字,且不出现在常用词)
        candidates = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
        counter = {}
        for c in candidates:
            if c in known:
                continue
            counter[c] = counter.get(c, 0) + 1
        # 出现>=3次的作为符号候选
        for name, cnt in counter.items():
            if cnt >= 3 and not self.is_banned(name):
                # 仅在未注册时加入
                already = any(s["name"] == name for s in self.data["symbols"])
                if not already:
                    self.register_symbol(name, first_chapter=chapter)


# ============================================================
# 4. Feasibility Check — 写下一章前的综合检查
# ============================================================

@dataclass
class FeasibilityResult:
    """写下一章前的可行性检查结果。"""
    feasible: bool
    severity: str = "GREEN"  # GREEN/YELLOW/RED
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "severity": self.severity,
            "warnings": self.warnings,
            "errors": self.errors,
            "suggestions": self.suggestions,
        }

    def summary(self) -> str:
        lines = [f"[{self.severity}] 可行性: {'✓' if self.feasible else '✗'}"]
        if self.warnings:
            lines.append("⚠ 警告:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.errors:
            lines.append("✗ 错误:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.suggestions:
            lines.append("→ 建议:")
            for s in self.suggestions:
                lines.append(f"  - {s}")
        return "\n".join(lines)


def check_chapter_feasibility(project_dir: Path, next_chapter: int) -> FeasibilityResult:
    """
    写第N章前的综合可行性检查。集成:
      1. StoryBudget: 实体/符号配额
      2. ArcStateTracker: 角色弧状态
      3. WorldInventory: 地理/符号注册
      4. QualityTrend: 质量趋势(若可用)
    """
    result = FeasibilityResult(feasible=True, severity="GREEN")
    project_dir = Path(project_dir)

    # === 1. 角色弧状态 ===
    arc_tracker = ArcStateTracker(project_dir)
    protag = arc_tracker.get_protagonist_arc()
    if protag:
        if protag["state"] == "resolved":
            result.severity = "RED"
            result.feasible = False
            result.errors.append(
                f"主角'{protag['name']}'的arc在第{protag.get('resolved_chapter', '?')}章已resolved,故事应已完结"
            )
            result.suggestions.append("考虑开新项目,或在changelog里标记完结")
        elif protag["state"] == "active" and not protag["unfinished_business"]:
            result.warnings.append(
                f"主角'{protag['name']}'的unfinished_business为空,确认是否漏设驱动负债"
            )

    # 统计所有角色的resolved情况
    all_chars = arc_tracker._load_characters()
    resolved_count = sum(
        1 for c in all_chars
        if (c.get("arc") or {}).get("state") == "resolved"
    )
    total_chars = len([c for c in all_chars if c.get("role") in ("protagonist", "antagonist", "supporting")])
    if total_chars > 0 and resolved_count == total_chars and total_chars >= 3:
        result.severity = "RED"
        result.feasible = False
        result.errors.append(
            f"所有{total_chars}个核心角色arc都已resolved,故事无新角色可推进"
        )
        result.suggestions.append("建议完结,或引入新角色(新支线)")

    # === 2. StoryBudget 实体消耗 ===
    budget = StoryBudget(project_dir)
    exhausted = budget.get_exhausted_entities()
    if len(exhausted) >= 3:
        result.severity = max(result.severity, "YELLOW", key=["GREEN", "YELLOW", "RED"].index)
        result.warnings.append(
            f"已有{len(exhausted)}个实体耗尽配额: {', '.join(exhausted[:5])}"
        )
        result.suggestions.append("检查剩余可用实体,或考虑完结")
    elif exhausted:
        result.warnings.append(
            f"已耗尽实体: {', '.join(exhausted)} (剩余配额紧张)"
        )

    # === 3. 质量趋势 ===
    try:
        from juben.guardian.trend import detect_quality_trend
        from juben.state.manager import StateManager
        mgr = StateManager(project_dir)
        chapters = []
        for p in sorted((project_dir / "chapters").glob("*.md")):
            try:
                num = int(p.stem)
                chapters.append({"num": num, "text": p.read_text(encoding="utf-8")})
            except ValueError:
                pass
        if chapters:
            trend = detect_quality_trend(chapters)
            if trend == "RED":
                result.severity = "RED"
                result.feasible = False
                result.errors.append("质量趋势: 连续多章复读,引擎拒绝继续")
                result.suggestions.append("故事线已耗尽,建议完结")
            elif trend == "YELLOW":
                result.severity = max(result.severity, "YELLOW", key=["GREEN", "YELLOW", "RED"].index)
                result.warnings.append("质量趋势: 连续多章auto-fix,处于警告状态")
                result.suggestions.append("考虑收尾或换新方向")
    except ImportError:
        pass  # trend模块未加载,跳过
    except Exception as e:
        logger.debug(f"质量趋势检测失败: {e}")

    return result
