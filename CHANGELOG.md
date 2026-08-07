# CHANGELOG

## [1.0.0] - 2026-08-07

### 核心突破：从"章节原子"升级到"项目级资源预算"

神算子30章复盘证明: 引擎能保证"这章写好"，但**无法回答"这故事还能不能继续"**。
v1.0 引入**项目级资源预算层**，让引擎像 git 追踪代码变更一样追踪故事资源。

### 新增

#### 4 个核心模块

- **`juben/budget/StoryBudget`** — 实体/符号消费配额追踪
  - 防止"故事线跑光"（ch18-30把神女/奶奶/瞎眼先生/白豆/12算筹全部用完）
  - 数据文件: `<project>/story_budget.json`
  - API: `register_entity()`, `consume()`, `list_all()`, `get_exhausted_entities()`

- **`juben/budget/ArcStateTracker`** — 角色弧状态机
  - 解决"主角已完结但引擎不知道"（陆九ch30已resolved，引擎却给ch31写"面临选择"）
  - 状态流转: `pending → active → climax → resolved`
  - API: `get_arc_state()`, `set_arc_state()`, `all_arcs_resolved()`

- **`juben/budget/WorldInventory`** — 地理+视觉符号中央登记簿
  - 防止 LLM 在 prompt 里随口编新地名/新符号
  - 数据文件: `<project>/world_inventory.json`
  - 包含 locations / symbols / banned 三类

- **`juben/guardian/trend.py`** — 跨章质量趋势检测
  - 解决"ch28=9.4 → ch29=9.6 → ch30=9.8 → ch31靠auto-fix → ch32 14万字复读"
  - 三档判定: GREEN / YELLOW / RED
  - 检测指标: 词汇重叠度、auto-fix 连击、分数持续下降

#### 4 条新 CLI 命令

```bash
juben budget                      # 实体预算/角色弧/世界符号
juben budget --consume 神女 28    # 手动记录消费
juben trend                       # 跨章质量趋势（相邻章尾部重叠度）
juben feasibility 31              # 写第31章前综合检查
juben world register symbol 神女 --meaning "上界神女转世" --chapter 18 --quota 5
juben world ban 天灵盖 --reason "未建立"
juben world unban 天灵盖
juben world list
```

#### 集成点

- `juben write N` **现在写 prompt 前自动调用 `check_chapter_feasibility()`**:
  - **RED**: 拒绝生成（exit 1），提示"故事已完结"
  - **YELLOW**: 警告但继续，输出建议
  - **GREEN**: 静默继续

### 改动

- **`juben/state/schema.py`**: `CharacterArc` 新增 4 个字段
  - `state: Literal["pending", "active", "climax", "resolved"]`
  - `unfinished_business: list[str]`
  - `activation_chapter: Optional[int]`
  - `resolved_chapter: Optional[int]`
  - **向后兼容**：所有新字段都有默认值，老 characters.json 无需迁移

- **`juben/cli.py`**: +270 行（4 个新命令 + write 集成 feasibility）

- **`juben/__init__.py`**: 版本号 `0.3.2 → 1.0.0`

### 验证

神算子 30 章真实数据回放测试:

```
=== 实体消费预算 ===
  奶奶: 13/3 (耗尽于 20)
  瞎眼先生: 13/3 (耗尽于 20)
  白无垢: 13/4 (耗尽于 21)
  神女: 13/5 (耗尽于 22)
  陆九: 13/6 (耗尽于 23)

=== 主角 arc ===
  陆九: state=resolved, resolved_chapter=30, unfinished_business=[]

=== 第31章可行性检查 ===
  可行: False, 严重度: RED
  错误: 主角'陆九'的arc在第30章已resolved,故事应已完结
  建议: 考虑开新项目,或在changelog里标记完结
```

**结论**: v0.3.2 时代 ch31-ch32 翻车时**没有**的预警，v1.0 在 ch30 已能自动给出。

### 升级指南

从 v0.3.x 升级到 v1.0:

```bash
git pull origin main
pip install -e .  # 如果有新依赖
```

**无需数据迁移**：
- `characters.json` 老数据继续可用（新字段有默认值）
- `world_inventory.json` 首次需要 `juben world register` 手动注册
- `story_budget.json` 首次为空，建议 `juben budget --consume <实体> <章节号>` 补录

### 完整 CLI 流程（v1.0）

```bash
# 1. 初始化（v0.3+）
juben init -t universal --premise "你的故事"
juben bootstrap           # 生成 LLM prompt
juben bootstrap --apply   # 应用 LLM 输出

# 2. 注册世界符号（v1.0 新增）
juben world register location 算卦山 --meaning "起点/命" --chapter 1
juben world register symbol 神女 --meaning "上界神女转世" --chapter 18 --quota 5
juben world ban 秦淮河 --reason "未建立"

# 3. 写作（v1.0 write 前自动 feasibility 检查）
juben feasibility 1     # 先查可行性
juben write 1           # RED 时直接拒绝
juben audit 1
juben commit 1

# 4. 任何时候查看项目状态
juben budget            # 实体预算/角色弧/世界符号
juben trend             # 质量趋势
```

---

## [0.3.2] - 2026-08-03 (历史)

- 之前版本，详见 git log
