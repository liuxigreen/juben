import json
import random
from pathlib import Path


# ============================================================
# P0-1: 信息获取通道轮换（InfoChannelRoulette）
# ============================================================
# 解决问题：中段"喝一杯→读心→掉痕迹"循环同质化
# 核心思想：把"信息怎么来"做成和结构类型一样的轮换维度

INFO_CHANNELS = {
    "ability_use": {
        "description": "主动使用高概念能力获取信息",
        "example": "端起对方的杯子，闭眼，听到心声",
        "max_consecutive": 2,
    },
    "refuse_or_fail": {
        "description": "想用能力但没用成（被打断/拒绝/失败）",
        "example": "刚端起杯子，被对方按住手腕",
    },
    "residue": {
        "description": "通过遗物/便签/照片/别人转述获取信息",
        "example": "翻到外婆的旧便签，发现字迹在变淡",
    },
    "being_seen": {
        "description": "对方察觉主角在读心/有异常能力",
        "example": "顾深注意到她喝完后表情变了",
    },
    "body_warning": {
        "description": "能力未使用就先掉痕迹/出现预兆",
        "example": "还没喝咖啡，左手疤痕就淡了一截",
    },
    "external_pressure": {
        "description": "外部事件推动信息暴露（非主角主动）",
        "example": "收到拆迁通知，所有秘密被迫浮出水面",
    },
}


class InfoChannelRoulette:
    """信息获取通道轮盘 — 防止中段同质化"""

    HISTORY_FILE = "info_channel_history.json"

    def __init__(self, project_dir: Path, cooldown: int = 4):
        self.project_dir = project_dir
        self.cooldown = cooldown
        self.history_path = project_dir / self.HISTORY_FILE
        self.history: list[dict] = self._load_history()

    def _load_history(self) -> list[dict]:
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_history(self):
        self.history_path.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def pick_channel(self, chapter_num: int) -> str:
        """为本章选择信息获取通道"""
        recent = [
            h for h in self.history
            if h["chapter"] > chapter_num - self.cooldown
        ]

        # 检查ability_use连续次数
        ability_streak = 0
        for h in reversed(self.history):
            if h.get("channel") == "ability_use":
                ability_streak += 1
            else:
                break

        # 检查最近N章是否全为ability
        recent_ability_only = all(
            h.get("channel") == "ability_use" for h in recent
        ) if recent else False

        # 决策逻辑
        if ability_streak >= 2:
            # 连续2次ability，强制换通道
            non_ability = [ch for ch in INFO_CHANNELS if ch != "ability_use"]
            chosen = random.choice(non_ability)
        elif recent_ability_only and len(recent) >= self.cooldown:
            # 连续N章都是ability，强制换通道
            non_ability = [ch for ch in INFO_CHANNELS if ch != "ability_use"]
            chosen = random.choice(non_ability)
        else:
            # 正常轮换（ability_use权重略高但不垄断）
            weights = [3 if ch == "ability_use" else 1 for ch in INFO_CHANNELS]
            channels = list(INFO_CHANNELS.keys())
            chosen = random.choices(channels, weights=weights, k=1)[0]

        # 记录
        self.history.append({"chapter": chapter_num, "channel": chosen})
        self._save_history()

        return chosen

    def get_injection_text(self, chapter_num: int) -> str:
        """生成信息通道注入文本"""
        chosen = self.pick_channel(chapter_num)
        channel_info = INFO_CHANNELS[chosen]

        # 检查连续ability警告
        ability_streak = 0
        for h in reversed(self.history[:-1]):
            if h.get("channel") == "ability_use":
                ability_streak += 1
            else:
                break

        warning = ""
        if ability_streak >= 2:
            warning = (
                "\n\n**连续警告**：最近已连续使用「喝咖啡读心」推进剧情，"
                "本章**必须**换用其他信息获取方式！"
            )

        return (
            f"### 信息获取通道（强制轮换）\n\n"
            f"**本章必须使用的信息获取方式**：{channel_info['description']}\n"
            f"**示例**：{channel_info['example']}{warning}\n\n"
            f"**轮换规则**：\n"
            f"- 主动使用能力连续不超过2章\n"
            f"- 每4章至少出现1次非能力通道\n"
            f"- 信息获取方式必须体现在场景的具体动作中，不能只靠旁白交代\n"
        )
