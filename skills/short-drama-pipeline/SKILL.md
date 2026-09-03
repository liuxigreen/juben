---
name: short-drama-pipeline
description: AI短剧全流程制作系统 - 选题→剧本→分镜→Veo提示词，当前窗口（Agent/LLM）驱动
version: 3.0
author: juben-team
tags: [short-drama, storyboard, video-generation, ai-video, veo, flow]
---

# AI短剧全流程制作系统（Agent 驱动版）

## 概述

从选题到可投喂视频平台的完整 pipeline。**工作方式：CLI 生成确定性结构与 prompt，
你在当前对话窗口里扮演 Architect/Scribe 完成创作，产物存回项目目录，CLI 负责校验与分镜。**

```
选题(topics) → 初始化(init) → 大纲(outline) → 写剧本(write→当前窗口写→audit循环)
→ 分镜(storyboard) → 参考图+Veo提示词(ref-sheets+export-prompts) → 视频平台生成 → 合成
   CLI        CLI+窗口        CLI+窗口         窗口+CLI               CLI            外部
```

## 标准作业流程（照此执行，全部命令真实存在）

### 第 0 步：选题（可选，爆款对齐）
```bash
juben topics -n 5                # 语料驱动选题：钩子×题材×换皮槽位，按市场配比采样
juben topics -n 3 -g 霸总,复仇    # 指定题材
```
选中一个 premise 后记住它的**两个换皮槽位**（如 职业=鉴宝师 + 物件=奶奶的菜谱）。

### 第 1 步：初始化项目
```bash
juben init "<premise>" -t universal --high-concept -y -d projects/你的剧名
```
然后**手工编辑** `story_meta.json`：
- `novelty_slots`: 填入选定的 2 个换皮槽位（缺失会在后续步骤告警）
- `hook_types` / `opening_rule` / `rhythm_curve`：按 `references/hook-taxonomy.md` 填
- `high_concept`：anomaly 设计成"AI 才拍得出"的奇观（见 `references/novelty-slots.md` 槽位 6）

### 第 2 步：大纲（Architect = 当前窗口的你）
```bash
juben outline -d projects/你的剧名        # 生成 outlines/architect_prompt.md
```
把 `architect_prompt.md` 的内容当指令，在当前窗口输出全剧分集拍子表，保存为
`outlines/episodes.md`。自检：每集有钩子/3次反转/爽点星级/断崖；同款反转不得连用两集；
第 6-10 集有付费卡点。

### 第 3 步：逐集写剧本（Scribe 循环 = 核心工作）
```bash
juben write 1 -d projects/你的剧名        # 生成第1章 Scribe prompt（含全部硬约束）
```
1. 读 prompt，在当前窗口按约束写正文（台词每秒1句、内心OS、断崖结尾）
2. 存为 `chapters/001.md`（**注意是 001.md 不是 ch001.md**）
3. 校验：运行 `juben audit 1 -d projects/你的剧名`
4. audit 不过 → `juben rewrite 1 -d ...` 生成重写 prompt → 回到第 1 步（最多 2 轮）
5. 通过后 `juben commit 1 -d ...` 锁章，写下一集

### 第 4 步：分镜（纯算法）
```bash
juben storyboard -d projects/你的剧名     # chapters/*.md → v3_storyboard/chNNN_shots.json
```
自检输出：每集 shots 数、末镜是否 cliffhanger、quality 汇总。⚠ 0 shots = 剧本格式问题，
看日志里的 ⚠ 警告行。

### 第 5 步：参考图 + Veo 提示词
```bash
juben ref-sheets -d projects/你的剧名     # 每个角色的参考图提示词 → flow_prompts_pro/character_sheets.md
juben export-prompts -d projects/你的剧名 # 分镜 → flow_prompts_pro/chNNN_pro_prompts.md
```
**先按 character_sheets.md 在即梦/可灵生成每个角色的标准参考图（主体参考）**，
再逐镜用 pro_prompts 生成视频片段——挂参考图是解决跨镜头长相漂移的唯一可靠手段。

### 第 6 步：成片（外部工具）
- 逐镜生成视频片段（即梦 Seedance 口型好→台词镜头；可灵画面强→空镜）
- TTS 配音：`voice_data.json`（每镜台词+情感标签）；字幕：`srt_subtitles/chNNN.srt`
- 剪辑合成：剪映/FFmpeg，按 shots 的 duration 排布

## 硬性规则（爆款对齐，违反必平庸）

1. **台词密度**：每分钟 380-460 字（约每秒 1 句、单句≤15字）；单集 90s = 500-900 字台词本体
2. **钩子**：25 秒内落地主钩子（语料中位 25s）；钩子类型按 hook-taxonomy.md 市场占比选
3. **反转**：每集 ≥2 次（中位 3），同款方式不得连用两集
4. **断崖**：每集 85-90s 处断崖，卡在"就差一口气"的位置
5. **换皮**：每剧 2 个新颖槽位（novelty_slots），情绪公式照旧
6. **付费卡点**：第 6-10 集首个，之后每 5-10 集一个

## 目录结构（init 自动生成）

```
projects/你的剧名/
├── story_meta.json          # 元数据+金手指+novelty_slots+高概念
├── characters.json          # 世界观角色卡（bootstrap 后）
├── config/                  # 8 个 YAML（characters.yaml 要填！）
├── outlines/                # architect_prompt.md / episodes.md
├── chapters/                # 001.md 002.md ...（Scribe 产物）
├── v3_storyboard/           # chNNN_shots.json / chNNN_beats.json
├── flow_prompts_pro/        # chNNN_pro_prompts.md / character_sheets.md
├── srt_subtitles/           # chNNN.srt
└── voice_data.json          # 配音数据
```

## 常见坑（已修复，留意）

- 章节文件名：引擎认 `001.md`，也兼容 `ch001.md`；0 shots 时看 ⚠ 警告
- characters.yaml 必须填真实角色（含 appearance/wardrobe），占位符会让提示词变 "a character"
- `config/` 子目录和项目根的 project_config.yaml 都能被识别
- audit 熔断 ≠ 重写整个故事：先看 rewrite prompt，通常只改出错的字段
