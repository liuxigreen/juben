# 《心声咖啡》项目复盘

## 项目概览

| 项目 | 详情 |
|------|------|
| 剧名 | 心声咖啡 |
| 题材 | 悬疑+读心+都市 |
| 集数 | 20章 |
| 总镜头 | 420个 |
| 总时长 | ~30分钟 |
| 制作周期 | 2天 |

## 交付物清单

### Stage 1: 剧本

| 文件 | 数量 | 说明 |
|------|------|------|
| `chapters/ch*.md` | 20个 | 完整剧本 |

### Stage 2: 分镜

| 文件 | 数量 | 说明 |
|------|------|------|
| `v3_storyboard/ch*_beats.json` | 20个 | Beat结构 |
| `v3_storyboard/ch*_shots.json` | 20个 | 镜头列表 |
| `srt_subtitles/*.srt` | 40个 | 字幕文件（含标注版） |
| `voice_data.json` | 1个 | 配音结构化数据（147条） |
| `voice_direction.txt` | 1个 | 配音导演手册 |

### Stage 3: 提示词

| 文件 | 数量 | 说明 |
|------|------|------|
| `flow_prompts_pro/ch*_pro_prompts.md` | 20个 | 专业提示词（420镜头） |
| `config/references/*.md` | 6个 | 参考资料 |

### 通用架构

| 文件 | 说明 |
|------|------|
| `pipeline.py` | 通用分镜引擎 |
| `generate_pro_prompts.py` | 专业提示词生成器 |
| `skills/short-drama-pipeline/SKILL.md` | 标准skill文档 |
| `projects/_template/` | 项目模板 |

## 架构演进

```
v1.0 初始版本
  └── 硬编码，只能做一个剧

v1.5 SmartAdapter v3
  └── 读心三镜、音频轨道、动作清洗

v2.0 通用架构（当前版本）
  ├── 引擎与配置分离
  ├── 8个YAML配置文件
  ├── 事件类型化
  ├── 钩子冷却（LRU）
  └── 质量评分（5项指标）

v2.1 专业提示词
  ├── 5-Part Formula
  ├── 人物表演框架（4维度×6情绪）
  └── Flow操作手册
```

## 核心设计决策

### 1. 引擎与配置分离

**问题**：v1.0代码和项目数据耦合，换题材要改代码。

**方案**：
- `pipeline.py`只包含通用逻辑
- 所有项目数据在`config/*.yaml`
- 换题材只改配置，不动代码

### 2. LLM做语义，代码做计算

**问题**：全部用LLM不稳定，全部用代码没创意。

**方案**：
- 剧本创意 → LLM
- 分镜结构 → 代码（确定性）
- 提示词生成 → 代码（模板化）

### 3. 事件类型化

**问题**："读心"是这个剧的特殊能力，换个剧就没用了。

**方案**：
```yaml
# events.yaml
mind_reading:
  enabled: true  # 这个剧用
flashback:
  enabled: false # 这个剧不用
```

### 4. 专业提示词5-Part Formula

**问题**：简单提示词生成的视频质量差。

**方案**：
```
[Cinematography] + [Subject] + [Action+Performance] + [Context] + [Style]
镜头语言           人物        动作+表演            环境        风格
```

## 质量指标

### 分镜质量

| 指标 | 目标 | 实际 |
|------|------|------|
| 总镜头数 | 400-500 | 420 ✅ |
| 平均时长 | 4-5秒 | 4.3秒 ✅ |
| 动作可拍性 | 100% | 100% ✅ |
| 角色一致性 | 100% | 100% ✅ |

### 提示词质量

| 指标 | 说明 |
|------|------|
| 5-Part完整度 | 100% |
| 人物表演维度 | 4维（眼睛/呼吸/微表情/肢体） |
| 镜头语言 | 专业级（景别+运镜+角度+镜头） |

## 换题材验证

### 最小改动测试

只需修改3个文件即可换题材：

```yaml
# 1. project_config.yaml
project:
  name: "甜蜜暴击"
  genre: "甜宠"

# 2. characters.yaml
characters:
  - name: 林小鹿
    archetype: 甜美女主
    personality: ["活泼", "开朗", "迷糊"]

# 3. locations.yaml
locations:
  - name: 甜品店
    description: "粉色装饰，阳光充足"
```

### 完全换题材

```bash
# 1. 复制模板
cp -r projects/_template projects/新剧名

# 2. 编辑配置
vi projects/新剧名/config/*.yaml

# 3. 运行pipeline
python3 pipeline.py --project 新剧名
```

## 待优化项

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P1 | Veo API集成 | 自动化生成，不需要手动操作Flow |
| P1 | 多renderer测试 | Kling/Runway适配 |
| P2 | Shot Graph | 镜头依赖图，自动排序 |
| P2 | Continuity状态 | 跨镜头状态追踪 |
| P3 | 语音合成集成 | 自动配音 |

## Git提交历史

```
320c773 添加标准skill: short-drama-pipeline + 项目模板
aad84e1 专业提示词生成器: 5-Part Formula + 人物表演框架
9a8c7dc Stage 3设计: Flow操作手册+逐镜头提示词导出
a6f197c P1: 多renderer支持（Veo/Kling/Flow/Runway）
8f4225a 配音文件: 指导手册+结构化数据+标注SRT
1afee06 v2.0: 配置分层 + 事件类型化 + 钩子冷却 + 质量评分
68aab3a 通用pipeline质量优化: 0问题
cba006c 架构重构: 通用pipeline + 配置驱动
aeba054 v3.1: 读心三镜+音频轨道+动作清洗+dialogue互斥
756b72b add: storyboard review txt for external review
9e07046 fix: SmartAdapter v3 分镜pipeline重构
```

## 使用其他AI测试

### 测试流程

1. **克隆仓库**
   ```bash
   git clone https://github.com/liuxigreen/juben.git
   ```

2. **阅读skill文档**
   ```bash
   cat skills/short-drama-pipeline/SKILL.md
   ```

3. **复制模板创建新项目**
   ```bash
   cp -r projects/_template projects/test-drama
   ```

4. **修改配置**
   ```bash
   vi projects/test-drama/config/*.yaml
   ```

5. **运行pipeline**
   ```bash
   python3 pipeline.py --project test-drama
   ```

6. **检查输出**
   ```bash
   ls projects/test-drama/v3_storyboard/
   ls projects/test-drama/flow_prompts_pro/
   ```

### 测试要点

- [ ] 换题材是否只改配置？
- [ ] 分镜质量是否达标？
- [ ] 提示词是否专业？
- [ ] 角色一致性是否保证？
- [ ] 字幕/配音数据是否完整？

---

**最后更新**: 2026-07-28
**版本**: v2.1
