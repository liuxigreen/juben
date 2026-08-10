# CHANGELOG

## [1.1.2] - 2026-08-10

### 核心：防污染隔离硬化 + 死代码清理

v1.1.1 解决了"init 自动建 config"，但留下 3 个污染风险：
- `_init_stage23_config` 已有 config 时**静默跳过**（不报错）— cp 错项目不会被发现
- 跨项目 cp 错 config 后无 lint 工具检测
- archive/ + 一次性规划 + 硬编码神算子路径的脚本长期堆积

本版做 3 件事：(1) 强制隔离 (2) 加 lint (3) 删死代码。

### 新增

#### 2 条新 CLI 命令

```bash
juben lint-config --dir <project>            # 防污染检查 (cp 错项目立即 ERROR + exit 1)
juben lint-config --dir <project> --strict   # 警告也当错误
juben init-config --dir <project>            # 独立重建 config/ (默认拒绝覆盖)
juben init-config --dir <project> --force    # 强制清空重建
```

#### `_init_stage23_config` 隔离保护

- **已有 config/ 时 raise FileExistsError**（不再静默跳过）— 阻断 init 防污染
- **检测 _template 5 个必备文件缺失时 raise FileNotFoundError** — 防止 _template 被破坏后静默失败
- 强制覆盖需 `--force`（CLI 或函数参数）
- init 主流程接住 FileExistsError，sys.exit(1) + 打印原因

#### `lint-config` 5 项检查

1. `characters.json` 存在性（项目 bootstrap 完成）
2. `config/characters.yaml` 角色 ⊆ `characters.json` 角色（含 aliases）— **错项目 cp 立即 ERROR**
3. `config/characters.yaml` 主名 ⊆ `characters.json` 主名 — 缺主名 WARN
4. `_template/config/` 5 个必备文件 — 缺文件 ERROR
5. 退出码：0=OK, 1=ERROR, 2=WARN(strict)

### 修复 (v1.1.1 残留)

- `juben init-config` 模拟 StateManager 的 result 格式，正确还原 characters/meta
- `juben lint-config` 兼容 yaml 两种格式：`{name: ...}` 和 `{characters: {name: ...}}`
- missing 检查改用主名（不含 aliases），消除误报

### 删除 (死代码)

- `archive/export_pro_prompts.py` `archive/generate_script.py` `archive/pipeline_v3.py` `archive/smart_adapter_test.py`
- `refactor_plan.md` (一次性规划)
- `scripts/auto_chapter.py` (硬编码神算子路径，违反零硬编码)
- `scripts/write_chapter.py` `scripts/gen_demo.py` (重复/无引用)

### 已知遗留

- 早期项目 (v1.0 时期) 的 `v3_storyboard/ch*_shots.json` 可能是用错项目 characters 生成的，**chapters/ 文本本身不受影响**。彻底修复需重跑 `juben storyboard -c 0`（会触发 LLM）
- 用户的真实项目不随 juben skill 仓库发布 — `projects/` 只含 `_template/`，新项目由 `juben init` 创建

## [1.1.1] - 2026-08-08

### 核心：Stage 2/3 一键化 + 工程化坑修复

v1.1.0 已完成项目级资源预算。本版聚焦"init 后跑通全链路"的工程化补完——
让用户**一条命令完成剧本→分镜→Veo prompt**，并把 v1.0 期间反复踩的 Pydantic/YAML 坑固化为防御代码。

### 新增

#### 2 条新 CLI 命令

```bash
juben storyboard --dir <project>              # Stage 2: 剧本→分镜
juben storyboard --dir <project> --chapter 5  # 仅处理单章
juben export-prompts --dir <project>          # Stage 3: 分镜→Veo prompt
juben export-prompts --dir <project> --chapter 5
```

Stage 1 (`juben init`) 现已自动创建 `config/` 目录含 5 个模板 + 2 个项目特异文件 (characters/locations/project_config)，
Stage 2/3 不再因"找不到 config"而失败。

#### init 自动生成 config/ 目录

- 5 个纯配置从 `projects/_template/config/` 复制（无项目特异性）：
  `action_rules.yaml` / `beat_triggers.yaml` / `hook_templates.yaml` / `prompt_style.yaml` / `events.yaml`
- `project_config.yaml` 自动替换 `project_name` + `default_location`（主角 location）
- `characters.yaml` 从 Pydantic result 生成，格式: `name: {en, role, appearance, personality, speech_style, wardrobe, background}`
- `locations.yaml` 用 `state.location` 作为 key（取自主角 state）
- 中→英文名映射（13 条）：林越→Lin Yue、苏念→Su Nian、白无垢→Bai Wugou 等

### 修复

#### 3 个 Pydantic→YAML 陷阱

1. **Pydantic 对象污染** — `appearance: !!python/object:...` 污染 YAML
   → `_safe_str()` 递归展开 `model_dump()` 为 `key=val; key.sub=val` 易读字符串

2. **CharacterRole 枚举未继承 str** — `role.value` 在 `Enum` 上挂掉
   → 检测 `hasattr(role, 'value') and hasattr(role, '_value_')` 双保险取值

3. **state.location 类型判断** — 主角 location 有时是 str 有时是 Pydantic
   → `isinstance(loc_str, str)` 严格校验后再用

#### pipeline.py 跳过已定稿章节

- 跳过 `chapters/NNN.md.locked`（内容已定稿，不应重转分镜）
- 单章模式 `--chapter N` 仅处理指定章
- 最大章节数从 `config.max_chapter` 读，无则扫描 `chapters/*.md` 实际文件名

#### export_pro_prompts.py 修复 characters 格式 + 扫描真实章节

- 旧版假设 characters.yaml 是 `name: info` 格式，实际是 `{characters: {name: info}}` 嵌套
- 旧版硬编码 1-20 章，现在扫描 `v3_storyboard/ch*_shots.json` 实际文件

### 验证

- 新项目 init: ✅ 8 个 config 文件全部生成，characters/locations YAML 正确
- pipeline .locked 跳过: ✅ 19/20 done (ch001 被 lock 跳过)
- CLI help: ✅ `juben storyboard --help` / `juben export-prompts --help` 可用

---

## [1.0.0] - 2026-08-07

### 核心突破：从"章节原子"升级到"项目级资源预算"

长篇项目 (30+ 章) 复盘证明: 引擎能保证"这章写好"，但**无法回答"这故事还能不能继续"**。
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

长篇项目 (30+ 章) 真实数据回放测试:

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
