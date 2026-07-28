#!/usr/bin/env python3
"""从 characters.yaml 生成 Flow 角色定妆卡（动漫仿真人风格）。风格改了就重跑。"""
import yaml
import os

BASE = os.path.dirname(os.path.abspath(__file__))
d = yaml.safe_load(open(os.path.join(BASE, "config/characters.yaml"), encoding="utf-8"))

lines = [
    "# 心声咖啡 — Flow 角色定妆卡（动漫仿真人风格）",
    "",
    "> **风格统一：现代动漫 / 2.5D 仿真人 / cel-shaded。** 绕开真人审核，风格更适合短剧。",
    "> 用法：把每个角色的定妆提示词丢进 Flow 的 **Ingredients/角色**，生成参考图并用**英文名**命名。",
    "",
    "---",
    "",
]
for zh, info in d.items():
    if not isinstance(info, dict) or "flow_portrait" not in info:
        continue
    en = info.get("en", "")
    role = info.get("role", "")
    portrait = " ".join(info["flow_portrait"].split())
    voice = info.get("flow_voice", "")
    lines += [
        f"## {zh}（{en}）  `{role}`",
        "",
        "**定妆提示词（生成参考图）：**",
        "```",
        portrait,
        "```",
        "",
        f"**声音描述：** {voice}",
        "",
        "---",
        "",
    ]
open(os.path.join(BASE, "FLOW角色定妆卡.md"), "w", encoding="utf-8").write("\n".join(lines))
print("定妆卡已更新为动漫风")
