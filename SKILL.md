# Juben 剧本引擎 Skill

> 从脑洞到可拍摄的工业级竖屏短剧分镜脚本

## 核心定位

Juben不是小说生成器，是**工业级竖屏短剧的视听指令单生成引擎**。

**核心能力：**
- 强一致性：世界观数据库 + 角色语言指纹 + 时间线锁
- 强原创性：Disruption Variable + Anti-Cliché Guard
- 强留存工程：算法时间轴卡点 + 5种钩子类型 + 节奏曲线

**输出两种格式：**
1. **叙事分镜**（中文）— 给编剧/导演审核剧情和节奏
2. **AI生成提示词**（英文）— 给Kling/Runway/Midjourney生成图片和视频

---

## 完整工作流程（5步法）

参考Coconah/AI-Short-Drama-Agent-Skill的多身份切换模式：

### 🟥 Step 0: 项目启动与脑洞重构

**身份**：资深策划

**触发条件**：用户提供碎片化灵感、概念或原始素材

**执行动作**：
1. 分析用户碎片化信息，进行情节发散
2. 补充欠缺的故事桥段
3. 设计最具冲突感的开场"钩子"
4. 推演全剧反转最高潮的设定
5. 向用户提出1-3个需要拍板的核心剧情问题

**输出**：需求梳理与脑洞补充延展文档

---

### 🟧 Step 1: 升级电影级故事大纲

**身份**：主编剧

**触发条件**：Step 0方向已确认

**执行动作**：
1. 生成3000字以上全局故事大纲
2. 设计经典四幕结构与钩子链
3. 拆解人物弧光轨迹
4. 规划全剧节奏波形（参考rhythm-curve.md）
5. 设计爽点矩阵（参考satisfaction-matrix.md）

**输出**：creative-plan.md

---

### 🟨 Step 2: 角色体系与反派设计

**身份**：主笔

**触发条件**：故事大纲已确认

**执行动作**：
1. 生成主要角色档案（姓名、外貌、性格、语言指纹）
2. 设计角色关系图
3. 设计四层反派体系（参考villain-design.md）：
   - 小反派（前期炮灰）
   - 中反派（中期主要对手）
   - 大反派（终极Boss）
   - 隐藏反派（反转用）
4. 设计反派台词风格

**输出**：characters.md, characters.json

---

### 🟩 Step 3: 分集规划与钩子设计

**身份**：节奏大师

**触发条件**：角色体系已确认

**执行动作**：
1. 生成全剧分集目录（每集一句话）
2. 为每集结尾设计钩子（参考hook-design.md）：
   - 悬念钩、反转钩、情绪钩、信息钩、危机钩
3. 标记关键剧情集（🔥）和付费卡点集（💰）
4. 规划开场模板（参考opening-rules.md）

**输出**：episode-directory.md

---

### 🟦 Step 4: 单集分镜脚本生成

**身份**：分镜导演

**触发条件**：分集规划完成

**执行动作**：
1. 生成Scribe Prompt（分镜导演版v2）
2. LLM生成带镜头标注的内容
3. Parser解析为结构化Episode
4. 五维评分（节奏/爽感/台词/格式/一致性）
5. 输出叙事分镜 + AI提示词

**节奏规范**：
- 每集120秒，8个镜头
- 节奏曲线：Hook(0-5s) → Setup(5-20s) → Rising(20-50s) → Storm(50-85s) → Satisfaction(85-100s) → Cliffhanger(100-120s)
- 每镜头必须有信息增量，禁止空镜

**输出**：
- 叙事分镜（中文，给编剧看）
- AI提示词（英文，给Kling/Runway用）
- 五维评分报告

---

### 🟦 Step 5: 剧本医生暴改精修

**身份**：终审剧本医生

**触发条件**：需要对单集初稿进行审阅润色

**执行动作**：
1. 网感降维打击：斩杀文绉绉和啰嗦的对白
2. 抹杀OOC：严格遵循人物身份阶层
3. 视听张力拉满：强化环境对抗描写
4. 结尾钩子强化：确保使用5种钩子类型之一

**输出**：精修后的最终剧本

---

## 参考资源（已集成）

### 核心参考（来自0xsline/short-drama）

| 文件 | 用途 | 加载时机 |
|------|------|---------|
| references/hook-design.md | 5种钩子类型 + 使用策略 | Step 3, Step 4 |
| references/rhythm-curve.md | 节奏曲线 + 单集微结构 | Step 1, Step 4 |
| references/villain-design.md | 4层反派体系设计 | Step 2 |
| references/satisfaction-matrix.md | 5大爽点类型矩阵 | Step 1, Step 4 |
| references/opening-rules.md | 开篇黄金法则 + 6种开场模板 | Step 3, Step 4 |

### 视觉风格预设（参考Micro-Drama-Skills）

位置：`.config/visual_styles.json`

10种电影级视觉风格：
1. Cinematic Film（电影质感）— 默认
2. Anime Classic（经典动漫）
3. Cyberpunk Neon（赛博朋克）
4. Chinese Ink Painting（水墨国风）
5. Korean Drama（韩剧氛围）
6. Dark Thriller（暗黑悬疑）
7. Vintage Hong Kong（港风复古）
8. Wuxia Epic（武侠大片）
9. Soft Romance（甜蜜恋爱）
10. Documentary Real（纪实写实）

---

## 核心模块

### 1. Scribe Prompt生成器

位置：`juben/episode/scribe_prompt.py`

功能：
- 生成分镜导演版Prompt（v2）
- 注入4维度视觉标签库（景别/运镜/光影/视角）
- 注入5种钩子类型
- 注入反派台词风格
- 注入4道熔断锁（死帧禁令/反嘴炮/悬念切断/空镜禁令）

### 2. Parser解析器

位置：`juben/episode/parser.py`

功能：
- 解析LLM生成的带镜头标注内容
- 输出结构化Episode JSON
- 提取景别、运镜、光影、视角4维度标签

### 3. Shot Prompt生成器

位置：`juben/episode/shot_prompt.py`

功能：
- 从Episode生成可直接喂给Kling/Runway的提示词
- 6组件结构：Subject + Action + Setting + Camera + Lighting + Mood
- 支持10种视觉风格预设
- 支持Kling Multi-Shot格式
- 支持Seedance任务格式（含@文件名引用）

### 4. 五维评分系统

位置：`juben/validate/five_dimension.py`

评分维度：
- 节奏（10分）：镜头切换流畅度、信息密度
- 爽感（10分）：爽点密度、情绪高潮
- 台词（10分）：角色辨识度、金句感
- 格式（10分）：镜头标注规范、节奏卡点对齐
- 一致性（10分）：角色行为逻辑、世界观遵守

### 5. 死帧检测器

位置：`juben/validate/dead_frame.py`

功能：
- 检测连续镜头是否有物理变化
- 检测空镜比例
- 检测台词密度

---

## 与其他工具的集成

### 上游：yt-drama-ops（选题）

```
yt-drama-ops蒸馏数据 → 选题/题材参考 → juben创作
```

### 下游：AI生成

```
juben叙事分镜 → shot_prompt.py生成提示词 → Midjourney/FLUX出图 → Kling/Runway出视频
```

### 下游：发布

```
juben剧本+视频 → yt-drama-ops标题/封面/标签 → YouTube发布
```

---

## 项目结构

```
juben/
├── SKILL.md                          # 本文档
├── .config/
│   └── visual_styles.json            # 视觉风格预设
├── references/                       # 参考资源
│   ├── hook-design.md                # 钩子设计手册
│   ├── rhythm-curve.md               # 节奏曲线设计
│   ├── villain-design.md             # 反派设计体系
│   ├── satisfaction-matrix.md        # 爽点矩阵
│   └── opening-rules.md              # 开篇黄金法则
├── juben/
│   ├── episode/
│   │   ├── schema.py                 # Episode/Shot数据模型
│   │   ├── scribe_prompt.py          # Scribe Prompt生成器
│   │   ├── parser.py                 # Parser解析器
│   │   ├── shot_prompt.py            # Shot Prompt生成器
│   │   ├── rhythm.py                 # 双轴节奏校验器
│   │   └── adapter.py                # 章节→单集适配器
│   ├── validate/
│   │   ├── five_dimension.py         # 五维评分
│   │   └── dead_frame.py             # 死帧检测
│   └── ...
└── projects/                         # 项目目录
    └── {项目名}/
        ├── metadata.json
        ├── characters.json
        ├── world_rules.json
        ├── episodes/
        │   ├── EP01/
        │   │   ├── dialogue.md
        │   │   ├── storyboard_config.json
        │   │   └── shot_prompts.json
        │   └── ...
        └── creative-plan.md
```

---

## 常见问题

### Q: 空镜太多会怎样？
A: 观众会觉得注水，划走。每集最多2个空镜，每个≤3秒。

### Q: 镜头太密集会不会累？
A: 不会。短剧观众习惯快节奏。关键是每个镜头有信息增量，不是单纯堆砌。

### Q: 120秒一集，60分钟剧需要多少集？
A: 60分钟 = 3600秒 ÷ 120秒 = 30集。90分钟 = 45集。

### Q: 什么时候用WS全景？
A: 几乎不用。只有开场定场（如皇宫全貌）才用，且≤3秒。

### Q: 运镜可以连续用Push吗？
A: 不可以。相邻镜头运镜必须变化。Push→Pull→Static→Handheld。

### Q: 如何保证角色一致性？
A: 使用角色参考图 + 视觉风格预设 +shot_prompt.py的6组件结构。

---

## 版本历史

- v0.4.0 (2026-07-21): 集成开源参考，新增钩子类型、反派体系、视觉风格预设
- v0.3.2 (2026-07-20): Scribe Prompt v2，4维度标签库
- v0.3.0 (2026-07-19): Episode适配层，Parser解析器
- v0.2.0 (2026-07-18): 世界观数据库，多Agent系统
- v0.1.0 (2026-07-17): 初始版本

---

*版本：v0.4.0 | 更新日期：2026-07-21*
*参考项目：0xsline/short-drama, Coconah/AI-Short-Drama-Agent-Skill, zhaihao118/Micro-Drama-Skills*
