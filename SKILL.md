---
name: juben-write
version: 1.1.2
description: |
  写剧本/小说 skill — 从一句话前提到完整章节正文。
  Python 控世界观 + LLM 写正文, 防吃书/防AI味/防复读, 每章带 cliffhanger。
  包含项目级资源预算层, 写第N章前自动检查"故事还能不能继续"。
  **v1.1.2 防污染隔离硬化**: init 自动建 config + lint-config 拦截错项目 cp + init-config 独立重建。
triggers:
  - "写剧本"
  - "写小说"
  - "创作故事"
  - "screenwriting"
  - "novel writing"
  - "story engine"
  - "写章节"
  - "大纲生成"
platforms:
  - hermes
  - claude-code
  - codex
  - opencode
  - any CLI agent
requires:
  python: ">=3.10"
  pip packages: ["click", "pydantic", "rich", "pyyaml"]
entry_point: juben.cli:main
---

# juben-write — AI 剧本/小说创作 Skill

## 这是什么

`juben` 是一个 Python 控世界观 + LLM 写正文的剧本引擎。v1.1.0 新增**项目级资源预算层**, v1.1.1 新增 **Stage 2/3 一键化** (init 自动生成 config + storyboard/export-prompts CLI + 跳过 .locked)。
让引擎在故事线耗尽时主动拒绝继续生成(实证: 长篇项目在 30 章左右触发资源预算告警)。

## 必走流程 (3 步)

```bash
# 第 1 步: 初始化 (选择模板 + premise)
juben init "你的故事前提" --title "标题"
# 可选: --template rebirth-revenge | universal
# 可选: --mixin xianxia-base,female-lead --skeleton power-fantasy

# 第 2 步: LLM 填充角色和世界观
juben bootstrap            # 生成 LLM prompt → 喂给任意 LLM
# 保存 LLM 输出为 bootstrap_response.json
juben bootstrap --apply    # 应用 LLM 输出

# 第 3 步: 循环写章节
for n in 1 2 3 4 5; do
  juben write $n           # 生成 Scribe prompt (RED 时自动拒绝)
  # 喂 LLM → 保存为 chapters/00n.md
  juben audit $n           # 5 项校验
  juben commit $n          # 锁定 + Curator 状态更新
done
```

## 完整命令清单 (11 条)

| 命令 | 用途 | 必走 |
|---|---|---|
| `juben init` | 初始化项目 | ✅ |
| `juben bootstrap` | LLM 填充角色/世界观 | ✅ |
| `juben write N` | 生成第 N 章 prompt (含可行性检查) | ✅ |
| `juben audit N` | 5 项质量校验 | ✅ |
| `juben commit N` | 锁定章节 + Curator 状态更新 | ✅ |
| `juben info` | 查看项目状态 | 可选 |
| `juben budget` | 实体预算/角色弧/世界符号 | 可选 (推荐) |
| `juben feasibility N` | 写第 N 章前综合检查 | 可选 (写前调用) |
| `juben trend` | 跨章质量趋势 | 可选 |
| `juben world register/ban/list` | 管理世界符号 | 可选 |
| `juben mixins` | 列出可用 mixin | 可选 |

## 题材模板 (2 个完整 + 14 个 mixin)

完整模板:
- `rebirth-revenge` — 重生复仇 (长篇项目验证)
- `universal` — Mixin 驱动的通用模板

Mixin (可组合):
- genre: `female-lead` / `male-lead` / `historical-base` / `modern` / `horror` / `urban-revenge`
- skeleton: `power-fantasy` / `rebirth-revenge` / `female-power` / `court-intrigue` / `vertical-drama`
- visual: `visual-styles`

使用示例:
```bash
juben init -t universal --premise "废材逆袭,被未婚妻退婚,发现自己是隐世大能" \
  --mixin male-lead,modern,urban-revenge \
  --skeleton power-fantasy \
  --title "都市逆袭"
```

## 项目结构

```
my-story/
├── story_meta.json        元数据 + 意外变量 + 高概念 + 算法卡点
├── characters.json        角色卡 (含 arc state machine)
├── world_rules.json       世界观 + 反套路黑名单
├── timeline.json          时间线
├── relationships.json     关系图 + 信息对称性
├── plot_threads.json      伏笔追踪
├── story_budget.json      【v1.0+】实体消费配额
├── world_inventory.json   【v1.0+】地理/符号中央登记
├── chapters/              章节正文
├── outlines/              大纲
├── reports/               质量报告
└── curator/               跨章状态追踪
```

## v1.1.1 新增 (Stage 2/3 一键化 + Pydantic→YAML 防御)

**核心问题**: v1.0 后用户仍需手抄 `config/` 目录 + 手动维护 `characters.yaml` 格式。Stage 2/3 因"找不到 config"反复失败。Pydantic 对象在 YAML dump 时反复污染（`!!python/object:` 错误、Enum 挂掉、location 类型不一致）。

### 2 条新 CLI

```bash
# Stage 2: 剧本 → 分镜
juben storyboard --dir projects/<your-project>
juben storyboard --dir projects/<your-project> --chapter 5   # 单章模式

# Stage 3: 分镜 → Veo prompt
juben export-prompts --dir projects/<your-project>
juben export-prompts --dir projects/<your-project> --chapter 5
```

### init 自动生成 config/

`juben init` 自动建 8 个文件：5 模板 (action_rules/beat_triggers/hook_templates/prompt_style/events) + 3 项目特异 (project_config/characters/locations)。Stage 2/3 立即可跑。

### 3 个 Pydantic→YAML 防御

- `_safe_str()` 递归展开 Pydantic `model_dump()` 为 `key=val; key.sub=val` 字符串
- `CharacterRole` 枚举双保险: `hasattr(role, 'value') and hasattr(role, '_value_')`
- `state.location` 用 `isinstance(loc_str, str)` 严格校验

### pipeline.py 跳过 .locked

```bash
touch chapters/001.md.locked   # 标记已定稿
juben storyboard --dir projects/foo   # 自动跳过 001
```

## v1.1.0 新增 (项目级资源预算)

真实项目长篇运行翻车的 4 根因 (见 docs/project-retrospective.md):

| 翻车样本 | 根因 | v1.1.0 解决 |
|---|---|---|
| 实体全部用完 | 实体-事件无消费预算 | `StoryBudget` |
| 主角已完结但引擎仍写"面临选择" | 角色弧无"已完成"标记 | `ArcStateTracker` |
| 凭空编造新地名 | 地理-符号库未建模 | `WorldInventory` |
| 单章 9.0+ 但 ch32 直接复读 | 跨章质量趋势无预警 | `QualityTrend` |

`juben write N` 现自动 feasibility 检查: **RED 直接拒绝 (exit 1)**。

## 已知限制

- **6 个题材模板虚标** (system-leveling / apocalypse-survival / ceo-romance / xianxia-cultivation / werewolf-supernatural / mystery-thriller / comedy-satire / historical-court / cross-world) — 暂未实现,请用 `universal` + mixin 组合
- **写章节靠 LLM** — 需要用户自行接入 ChatGPT/Claude/Agent,引擎不内置 LLM 调用
- **仅重生复仇和 universal 模板端到端验证过** — 其他题材组合需用户测试

## 快速示例 (3 分钟跑通)

```bash
# 1. 初始化
juben init "主角重生回 5 年前,利用前世记忆复仇背叛者" -t rebirth-revenge -y
cd my-project

# 2. LLM 填充 (用 ChatGPT 跑 bootstrap_prompt.md, 保存为 bootstrap_response.json)
juben bootstrap
# [把 bootstrap_prompt.md 喂给 LLM]
juben bootstrap --apply

# 3. 写第 1 章
juben write 1
# [把生成 prompt/001_prompt.md 喂给 LLM]
# [把 LLM 输出保存为 chapters/001.md]
juben audit 1
juben commit 1

# 4. 循环 2-30
for n in $(seq 2 30); do
  juben feasibility $n  # 写前检查
  juben write $n
  # 喂 LLM → 保存 chapters/00n.md
  juben audit $n
  juben commit $n
done

# 5. 任何时候查看项目状态
juben budget    # 实体消耗 + 角色弧
juben trend     # 质量趋势
juben info      # 总览
```

## 安装

```bash
git clone https://github.com/liuxigreen/juben.git
cd juben
pip install -e .

# 验证
juben --version  # 应该输出 1.1.1
juben --help
```

## 更多信息

- 完整文档: [README.md](https://github.com/liuxigreen/juben/blob/main/README.md)
- 升级指南: [CHANGELOG.md](https://github.com/liuxigreen/juben/blob/main/CHANGELOG.md)
- 问题反馈: [GitHub Issues](https://github.com/liuxigreen/juben/issues)

## License

MIT
