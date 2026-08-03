# 剧本引擎 (Juben) — AI剧本/小说创作引擎

> Python控世界观 + LLM写正文，防吃书、防AI味、每章带Cliffhanger

## 核心哲学

**Python只提供确定性结构数据，LLM负责逻辑推理和正文生成。**

| 层 | 职责 | 谁管 |
|---|---|---|
| **Python层** | 世界观锚点（角色卡、时间线、力量体系、伏笔追踪） | 代码 |
| **LLM层** | 血肉创作者（分镜细化、正文生成、对白打磨） | Agent |
| **校验层** | 质量门卫（连续性检查、反AI味、反套路、Cliffhanger验证） | Python + LLM |

## 架构

```
┌─────────────────────────────────────────────────┐
│                  用户（作者）                      │
│  前提设定 → 选题材 → 生成大纲 → 逐章创作 → 审核    │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Layer 1: 世界观数据库 (Python)        │
│  characters.json   ← 角色卡（外貌/性格/欲望/恐惧）  │
│  world_rules.json  ← 力量体系/魔法规则/社会结构     │
│  timeline.json     ← 时间线事件                     │
│  relationships.json← 角色关系图                     │
│  plot_threads.json ← 伏笔/悬念/未解决线索           │
│  story_meta.json   ← 元数据（题材/骨架/语种/目标）   │
│                     + 意外变量(disruption_variable)  │
│                     + 算法时间轴卡点                 │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Layer 2: LLM创作引擎                  │
│  Agent 1: Architect  — 大纲/分镜设计              │
│  Agent 2: Scribe     — 正文生成                   │
│  Agent 3: Editor     — 文字打磨/反AI味            │
│  Agent 4: Guardian   — 连续性校验                 │
│  Agent 5: Curator    — 世界观更新                 │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Layer 3: 输出层                       │
│  chapters/         ← 成品章节（Markdown）          │
│  outlines/         ← 大纲/分镜                    │
│  reports/          ← 质量报告                     │
└─────────────────────────────────────────────────┘
```

## 三大硬核增强

### 1. 意外变量 (Disruption Variable)
在 `story_meta.json` 中注入原创扰动源，强制Architect把非套路元素作为核心金手指。

### 2. 反套路拦截 (Anti-Cliché Guard)
在 `world_rules.json` 中维护烂梗黑名单，Scribe下笔前受压、Guardian校验时无情熔断。

### 3. 算法时间轴卡点 (Timeline Alignment)
3秒钩子(前100字) → 15秒留存炸弹(400字处) → 50秒断崖(Cliffhanger)，写入分镜的物理数学公式。

## 🧠 高概念脑洞模式 (v0.8.0+) — 反退化的核心防线

**问题**:传统AI写大纲容易"平庸化/套路化",LLM在长篇中会**渐渐退化**为常见模板(身份碾压/系统开挂/失忆觉醒),哪怕前期种子再好。

**解决**:在 `story_meta.json` 中显式定义**高概念核心**,约束每章prompt必须围绕它展开。

### 启用方式

在 `story_meta.json` 中设 `high_concept.enabled: true`,并填写:
- `anomaly`: 这个世界**多出来的一条异常规则**(一句话)
- `visual_core`: 一个**能拍下来的核心画面**
- `personal_cost`: 主角**持续付出的代价**
- `why_new`: 为什么它**不像常见短剧**
- `banned_patterns`: **禁止的故事结构**清单(防退化)
- `visual_anchor_prop`: 从异常中**长出的视觉锚点道具**
- `visual_anchor_keywords`: 锚点关键词(每3-5章必出现)

### 注入机制

`constraint_injector._build_high_concept_injection()` 在 Scribe prompt **最前面**注入(权重最高),每章必须:
1. 推进异常规则的暴露或代价的加深
2. 不得偏离异常规则的核心吸引力
3. 不得触发 banned_patterns 任何一条

### 4种生成策略 (LLM生成 anomaly 时使用)
1. **机制异象**:世界多了一条异常规则
2. **工具异变**:一个日常物品成为关键线索/武器
3. **信息特权反转**:只有最底层的人能看见真实规则
4. **因果倒置**:结果先发生,原因被系统隐瞒

### 俗套黑名单 (5条默认)
1. 禁止"主角真实身份是隐退兵王/前刑警/隐世神医/隐藏首富"
2. 禁止"主角因为车祸/意外失忆"
3. 禁止"靠系统打卡/签到直接获得无敌奖励"
4. 禁止"重生后利用前世记忆碾压所有人"
5. 禁止"主角是天选之人,天赋异禀"

⚠️ **新项目必须启用高概念模式**。已通过audit的章节不重写,但后续章节必须围绕高概念展开。

## 快速开始

```bash
# 安装
pip install -e .

# 初始化项目
juben init "末世重生+系统流：主角被最信任的人背叛后死亡，重生回末世降临前一天"

# 生成大纲
juben outline --chapters 30

# 写第1章
juben write 1

# 批量写1-10章
juben write 1-10

# 审核全书
juben audit
```

## 项目结构

```
story-project/
├── story_meta.json        ← 元数据 + 意外变量 + 算法卡点
├── characters.json        ← 角色卡库（动态状态）
├── world_rules.json       ← 世界观规则 + 反套路黑名单
├── timeline.json          ← 时间线
├── relationships.json     ← 关系图
├── plot_threads.json      ← 伏笔追踪
├── chapters/              ← 成品章节
├── outlines/              ← 大纲/分镜
├── reports/               ← 质量报告
└── .storylock             ← 项目锁定文件
```

## 题材模板

| 模板 | 骨架 | 适用场景 |
|---|---|---|
| `rebirth-revenge` | 身份落差+命运逆转 | 重生复仇文 |
| `system-leveling` | 能力反差+系统升级 | 系统流/LitRPG |
| `apocalypse-survival` | 命运逆转+生存 | 末世文 |
| `ceo-romance` | 身份落差+契约关系 | 霸总言情 |
| `xianxia-cultivation` | 能力反差+境界突破 | 修仙玄幻 |
| `werewolf-supernatural` | 身份逆转变+超自然 | 狼人/吸血鬼 |
| `mystery-thriller` | 悬念+反转 | 推理/惊悚 |
| `comedy-satire` | 反套路+荒诞 | 沙雕/搞笑 |
| `historical-court` | 权谋+宫斗 | 古代宫廷 |
| `cross-world` | 穿越+异世界 | 穿越文 |

## License

MIT
