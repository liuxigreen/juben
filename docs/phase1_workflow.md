# Juben 剧本引擎 - 第一阶段流程文档

## 概述

Juben是一个AI剧本生成引擎，从创意到成稿的完整流水线。

## 核心模块

### 1. 高概念引擎 (High-Concept Engine)
**位置**：`story_meta.json` → `high_concept`字段
**作用**：决定"写什么"，提供爆款基因
**输入**：用户创意灵感
**输出**：高概念配置（anomaly、visual_core、personal_cost等）

### 2. 张力预算器 (Tension & Rhythm Budgeter)
**位置**：`timeline.json` → `tension_budget` + `chapters`
**作用**：控制节奏，解决"没有呼吸感"问题
**输入**：总章数、剧情阶段
**输出**：每章的张力分(1-10)和节奏类型(6种)

### 3. 实体关系锁 (Entity Graph Lock)
**位置**：`entity_graph.json`
**作用**：防止人物设定漂移
**输入**：角色关系定义
**输出**：硬规则和禁止组合

### 4. 描写范式冷却轮盘 (Motif & Pattern Roulette)
**位置**：`curator.py` → `NarrativeMotifTracker`
**作用**：防止机械复读
**输入**：章节文本
**输出**：禁用范式列表

### 5. 阶段自适应Guardian (Phase-Aware Guardian)
**位置**：`guardian/__init__.py`
**作用**：防止误杀和误判
**输入**：章节号、总章数
**输出**：动态阈值

### 6. 约束注入器 (Constraint Injector)
**位置**：`constraint_injector.py`
**作用**：将所有约束注入Prompt
**输入**：章节号、项目目录
**输出**：约束注入文本块

### 7. Guardian审计系统
**位置**：`guardian/__init__.py`
**作用**：事后质量检查
**输入**：章节文本
**输出**：审计报告（分数、违规、建议）

## 完整流程

```
1. 用户提供创意灵感
   ↓
2. 高概念引擎生成配置（story_meta.json）
   ↓
3. 大纲生成（AI辅助，人工把关）
   ↓
4. 张力预算分配（timeline.json）
   ↓
5. 实体关系定义（entity_graph.json）
   ↓
6. 章节生成循环：
   a. 约束注入器构建Prompt
      - 高概念注入
      - 张力预算注入
      - 实体关系锁注入
      - 描写范式冷却注入
      - 其他约束（对话比例、结构轮换等）
   b. LLM生成章节
   c. Guardian审计
   d. 如果PASS → 保存章节
   e. 如果FAIL → 重新生成（最多3次）
   ↓
7. 人工审核（可选）
   ↓
8. 输出完整剧本
```

## 文件结构

```
projects/
└── {项目名}/
    ├── story_meta.json          # 高概念配置
    ├── timeline.json            # 张力预算
    ├── entity_graph.json        # 实体关系锁
    ├── entity_anchors.json      # 实体锚点（可选）
    ├── characters.json          # 角色定义
    ├── world_rules.json         # 世界规则
    ├── curator_state.json       # Curator状态
    ├── motif_history.json       # 描写范式历史
    ├── structure_history.json   # 结构历史
    ├── chapters/                # 章节文件
    │   ├── 001.md
    │   ├── 002.md
    │   └── ...
    └── reports/                 # 审计报告
        ├── chapter_001.json
        ├── chapter_002.json
        └── ...
```

## 节奏类型说明

| 类型 | 张力分 | 对话占比 | 说明 |
|------|--------|----------|------|
| Discovery | 3-6 | ≤30% | 发现阶段，逐步揭示规则 |
| Investigation | 5-7 | ≤35% | 调查阶段，追查真相 |
| Confrontation | 7-9 | ≤40% | 对峙阶段，正面冲突 |
| Storm_Climax | 9-10 | ≤25% | 风暴高潮，物理危机 |
| Cooldown_Breathing | 3-4 | ≤45% | 喘息复盘，情感铺垫 |
| Resolution_Arc | 2-5 | ≤40% | 落幕收网，命运归宿 |

## 使用示例

### 1. 创建新项目
```bash
mkdir -p projects/我的剧本/chapters
```

### 2. 配置高概念
创建 `story_meta.json`，参考《死亡指数》的格式。

### 3. 配置张力预算
创建 `timeline.json`，定义每章的张力分和节奏类型。

### 4. 配置实体关系
创建 `entity_graph.json`，定义角色关系和禁止组合。

### 5. 生成章节
```python
from juben.constraint_injector import ConstraintInjector
from juben.guardian import check_entity_consistency

injector = ConstraintInjector('projects/我的剧本')
block = injector.build_injection_block(chapter_num=1)
```

### 6. 审计章节
```python
from juben.guardian import Guardian

guardian = Guardian('projects/我的剧本')
result = guardian.audit_chapter(chapter_num=1)
```

## 注意事项

1. **高概念必须独特**：禁止使用"隐退兵王"、"失忆刑警"等陈腐套路
2. **张力预算必须合理**：高潮后必须有喘息，结局必须有收束
3. **实体关系必须锁定**：一旦定义，不能在写作中改变
4. **描写范式必须轮换**：连续3章不能使用相同的描写套路
5. **节奏类型必须遵守**：每种类型有独立的要求，不能混淆

## 常见问题

### Q: 为什么我的剧本被Guardian判定为FAIL？
A: 检查以下几点：
- 对话占比是否超标
- 结尾是否与前几章重复
- 是否违反实体关系锁
- 是否重复使用禁用的描写范式

### Q: 如何调整张力预算？
A: 修改 `timeline.json` 中对应章节的 `tension` 和 `rhythm` 字段。

### Q: 如何添加新的节奏类型？
A: 修改 `constraint_injector.py` 中的 `_get_rhythm_guidance` 方法。

## 版本历史

- v1.0 (2026-07-26): 初始版本，完成4步重构
  - Step 1: 实体关系锁 ✅
  - Step 2: 张力预算器 ✅
  - Step 3: 描写范式冷却轮盘 ✅
  - Step 4: 阶段自适应Guardian ✅
