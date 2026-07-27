---
name: short-drama-pipeline
description: AI短剧全流程制作系统 - 从剧本到视频的工业级pipeline
version: 2.0
author: juben-team
tags: [short-drama, storyboard, video-generation, ai-video, veo, flow]
---

# AI短剧全流程制作系统

## 概述

从创意到成片的完整短剧制作pipeline，支持任意题材、任意AI视频平台。

```
创意 → 剧本 → 分镜 → 提示词 → 视频生成 → 后期合成
Stage1   Stage2   Stage2    Stage3      Stage3       Stage4
```

## 快速开始

### 1. 创建新项目

```bash
# 复制通用模板
cp -r projects/_template projects/你的剧名

# 编辑项目配置
vi projects/你的剧名/config/project_config.yaml
```

### 2. 配置文件说明

| 文件 | 用途 | 必须修改 |
|------|------|----------|
| `project_config.yaml` | 项目主配置（标题、章节数、时长） | ✅ |
| `characters.yaml` | 角色定义（名字、外貌、性格） | ✅ |
| `locations.yaml` | 场景定义（地点、氛围、道具） | ✅ |
| `events.yaml` | 事件类型（读心、闪回、冲突） | 按需 |
| `action_rules.yaml` | 动作规则（可拍性检查） | 可选 |
| `beat_triggers.yaml` | Beat触发规则 | 可选 |
| `hook_templates.yaml` | 钩子模板 | 可选 |
| `prompt_style.yaml` | 提示词风格配置 | 可选 |

### 3. 运行pipeline

```bash
# Stage 1: 剧本生成（需LLM）
python3 pipeline.py --stage 1 --project 你的剧名

# Stage 2: 分镜生成（纯算法）
python3 pipeline.py --stage 2 --project 你的剧名

# Stage 3: 提示词生成（纯算法）
python3 generate_pro_prompts.py --project 你的剧名
```

## 架构设计

### 核心原则

1. **引擎与配置分离** — `pipeline.py`是通用引擎，项目数据在`config/`目录
2. **换项目只改配置** — 不动代码，只修改YAML文件
3. **LLM做语义，代码做计算** — 确定性逻辑用代码，创意内容用LLM

### 目录结构

```
juben/
├── pipeline.py                    # 通用分镜引擎（核心）
├── generate_pro_prompts.py        # 专业提示词生成器
├── export_flow_prompts.py         # Flow提示词导出
├── skills/
│   └── short-drama-pipeline/      # 本skill
│       └── SKILL.md
├── projects/
│   ├── _template/                 # 项目模板
│   │   └── config/                # 配置模板
│   └── 你的剧名/
│       ├── config/                # 项目配置（8个YAML）
│       ├── chapters/              # Stage1输出：剧本
│       ├── v3_storyboard/         # Stage2输出：分镜
│       │   ├── ch001_beats.json   # Beat数据
│       │   └── ch001_shots.json   # Shot数据
│       ├── flow_prompts_pro/      # Stage3输出：专业提示词
│       │   └── ch001_pro_prompts.md
│       ├── srt_subtitles/         # 字幕文件
│       ├── voice_data.json        # 配音数据
│       └── voice_direction.txt    # 配音手册
└── config/
    └── references/                # 参考资料
        ├── veo3-prompting-guide.md
        ├── facial-expression-skill.md
        └── ...
```

## Stage 1: 剧本生成

### 输入
- 创意大纲（用户提供）
- `project_config.yaml`（章节结构）
- `characters.yaml`（角色设定）

### 输出
- `chapters/ch001.md` ~ `ch020.md`（20章剧本）

### 剧本格式要求

```markdown
## 第一章：标题

### 场景1：咖啡店 - 下午

苏念在吧台后擦拭杯子，第三次看向门口。

**顾深**走进来，灰色西装，径直坐下。

**苏念**：（微笑）美式？

**顾深**：（点头，手指敲桌）

苏念转身磨豆，[注意到顾深的敲击有规律]。

---

### 场景2：巷子 - 晚上

...
```

### 关键约束
- 每章3-5个场景
- 每场景有明确的时间/地点
- 动作必须是**物理可拍**的（不能写"回忆起过去"）
- 对话要口语化（15字以内）

## Stage 2: 分镜生成

### 输入
- 剧本文件
- 项目配置

### 输出
- `v3_storyboard/ch001_beats.json` — Beat结构
- `v3_storyboard/ch001_shots.json` — 镜头列表

### 分镜数据结构

```json
{
  "chapter": 1,
  "title": "第一章标题",
  "shots": [
    {
      "shot_id": 1,
      "type": "scene",
      "duration_sec": 4,
      "camera": {
        "shot_type": "MCU",
        "movement": "static",
        "angle": "eye-level"
      },
      "description": "苏念在吧台后擦拭杯子",
      "characters": ["苏念"],
      "props": ["杯子", "吧台"],
      "veo_prompt": "Medium close-up of a young Chinese woman wiping a cup behind a coffee counter..."
    }
  ]
}
```

### 质量检查

```bash
# 自动检查
python3 pipeline.py --audit --project 你的剧名

# 检查项
# - 动作可拍性（无抽象词）
# - 时长合理性（3-8秒/镜头）
# - 角色一致性
# - 场景连续性
```

## Stage 3: 视频生成

### 方案A: Google Flow（推荐，无API）

#### 3.1 角色定妆

在Flow中创建Character，使用以下模板：

```
[外貌描述] + [服装] + [标志性特征] + [气质关键词]

示例：
Young Chinese woman, 26 years old, round face, shoulder-length black hair.
Wearing a brown apron over white t-shirt.
Small burn scar on left ring finger.
Warm, observant, slightly anxious demeanor.
```

#### 3.2 场景参考

创建Ingredient，使用以下模板：

```
[地点类型] + [关键道具] + [光线] + [氛围]

示例：
Intimate Chinese coffee shop interior.
Wooden counter with yellowed sticky notes, espresso machine, warm amber lighting.
Afternoon sunlight through window, dust motes floating.
Cozy, slightly melancholic atmosphere.
```

#### 3.3 镜头生成

从`flow_prompts_pro/ch001_pro_prompts.md`复制提示词：

```
[Cinematography] + [Subject] + [Action+Performance] + [Context] + [Style]

示例：
Medium close-up, slow dolly forward, slight low angle, 50mm lens, f/2.8.
26yo Chinese woman, round face, shoulder-length hair, apron, burn scar on ring finger —
Su Nian freezes, breath catching. eyes: gaze darts then locks, pupils dilate.
Inside a small intimate Chinese coffee shop, late afternoon, long shadows.
Photorealistic Chinese short drama, anamorphic lens, shallow DOF, film grain.
Duration: 4s. Aspect ratio: 9:16 vertical.
```

#### 3.4 Scene Builder

1. 生成Shot 1 → 满意 → Add to Scene
2. 选中Shot 1 → Jump To → 生成Shot 2
3. 重复直到全章完成
4. 下载Scene

### 方案B: Veo API（自动化）

```python
# 使用pipeline直接调用
python3 pipeline.py --stage 3 --project 你的剧名 --api veo
```

## Stage 4: 后期合成

### 4.1 字幕

```bash
# SRT文件已生成在 srt_subtitles/
# 导入剪映：设置 → 字幕 → 导入SRT
```

### 4.2 配音

```bash
# 参考 voice_direction.txt 录制配音
# 或使用AI配音工具
```

### 4.3 合成

```bash
# 使用ffmpeg合成
ffmpeg -i video.mp4 -i audio.mp3 -i subtitle.srt \
  -c:v copy -c:a aac -c:s mov_text \
  output.mp4
```

## 换题材指南

### 最小修改（同类型）

只改3个文件：
1. `project_config.yaml` — 标题、简介
2. `characters.yaml` — 角色名、外貌
3. `locations.yaml` — 场景名、描述

### 完全换题材

1. 复制模板：`cp -r projects/_template projects/新剧名`
2. 编辑所有config文件
3. 重新运行pipeline

### 配置示例：悬疑剧 → 甜宠剧

```yaml
# characters.yaml
characters:
  - name: 苏念
    archetype: 坚韧女主      # 改为：甜美女主
    personality: 敏感、压抑   # 改为：活泼、开朗
    
# events.yaml
events:
  mind_reading:              # 删除或改为：
    enabled: false           #   甜蜜互动
  sweet_moment:              #   enabled: true
    enabled: true
```

## 常见问题

### Q: 提示词太简单怎么办？
A: 使用`generate_pro_prompts.py`生成5-Part专业提示词，包含镜头语言、人物表演、环境氛围。

### Q: 角色一致性怎么保证？
A: 三重保障：@角色名 + 参考图(Ingredient) + Jump To连接相邻镜头。

### Q: 换视频平台怎么办？
A: 修改`prompt_style.yaml`中的renderer配置，pipeline会自动适配不同平台的提示词格式。

### Q: 分镜质量怎么检查？
A: 运行`python3 pipeline.py --audit`，会检查动作可拍性、时长合理性、角色一致性等。

## 参考资料

- `config/references/veo3-prompting-guide.md` — Veo 3专业提示指南
- `config/references/facial-expression-skill.md` — 人物表演框架
- `config/references/full-video-framework.md` — 完整视频框架
- `config/references/performance-recipes.md` — 表演配方

## 版本历史

- **v2.0** (2026-07) — 配置分层、事件类型化、专业提示词
- **v1.0** (2026-07) — 初始版本、通用pipeline
