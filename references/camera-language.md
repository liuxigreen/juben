# 镜头语言参考

> 基于2026年AI视频工具实测（Kling 3.0 / Runway Gen-4.5 / Veo 3.1 / Seedance 2.0）
> 核心原则：每条prompt必须能被摄像机拍到，不能有抽象心理活动

---

## 景别系统（Shot Types）

| 景别 | 英文 | 用途 | 画面范围 |
|------|------|------|----------|
| 大特写 | ECU (Extreme Close-up) | 眼睛、手部细节、道具特写 | 面部局部/手部 |
| 特写 | CU (Close-up) | 面部表情、情绪传递 | 头部+肩部 |
| 近景 | MCU (Medium Close-up) | 台词+表情、人物互动 | 胸部以上 |
| 中景 | MS (Medium Shot) | 动作+环境、场景交代 | 腰部以上 |
| 全景 | FS (Full Shot) | 全身动作、站位关系 | 全身 |
| 远景 | EWS (Extreme Wide Shot) | 环境建立、世界观 | 人物+大环境 |

---

## 运镜系统（Camera Movements）

| 运镜 | 英文 | 情绪 | 使用时机 |
|------|------|------|----------|
| 静止 | Static | 稳定、观察 | 特写开局、信息传递 |
| 缓推 | Slow dolly forward | 沉思、紧张 | 内心戏、发现前 |
| 急推 | Fast dolly forward | 震惊、冲击 | 惊吓点、发现瞬间 |
| 拉 | Dolly backward | "原来如此" | 展现全貌、身份揭露 |
| 横摇 | Horizontal pan | 环境交代 | 场景扫描、多人反应 |
| 俯仰 | Vertical tilt | 权力对比 | 仰拍=强大，俯拍=弱小 |
| 移轨 | Dolly tracking | 流畅跟随 | 走路、奔跑、追逐 |
| 跟拍 | Tracking shot | 紧张、纪实 | 动作戏、追逐 |
| 升降 | Crane shot | 超脱、升华 | 结尾升华、全景揭示 |
| 手持 | Handheld | 真实、紧张 | 纪实/动作/混乱场景 |
| 变焦 | Zoom in | 聚焦、悬念 | 发现细节、瞳孔特写 |
| 眩晕变焦 | Dolly zoom | 眩晕、压迫 | 心理冲击、世界观崩塌 |

---

## 机位角度（Camera Angles）

| 角度 | 英文 | 情绪 | 使用时机 |
|------|------|------|----------|
| 平视 | Eye level | 中性、客观 | 常规对话、叙事 |
| 仰拍 | Low angle | 强大、压迫 | 展示强者、仰望建筑 |
| 俯拍 | High angle | 弱小、被控制 | 展示弱者、全局视角 |
| 倾斜 | Dutch angle | 不安、混乱 | 心理失衡、危机 |
| 正俯 | Overhead | 全知、上帝视角 | 地图、布局、俯瞰 |

---

## 构图规则（Composition）

| 构图 | 英文 | 用途 |
|------|------|------|
| 三分法 | Rule of thirds | 最通用，人物放在1/3线 |
| 黄金分割 | Golden ratio | 高级感，比例更精确 |
| 对称 | Symmetry | 权力、庄严、对峙 |
| 引导线 | Leading lines | 视觉引导，指向主体 |
| 框中框 | Frame within frame | 门框/窗框/镜子，增加层次 |
| 对角线 | Diagonal | 动感、冲突、紧张 |

---

## 运镜情绪对照（速查表）

```
缓推 → 沉思、紧张 → 内心戏、发现前
急推 → 震惊、冲击 → 惊吓点、发现
揭示拉 → "原来如此" → 展现全貌
环绕 → 强调、360度 → 重要主体
上升 → 超脱、渺小 → 结尾升华
手持 → 真实、紧张 → 纪实/动作
眩晕变焦 → 眩晕、压迫 → 心理冲击
```

---

## 6组件Prompt结构（跨工具通用）

每条prompt必须包含以下6个组件，顺序固定：

```
[Subject + Action], [Setting], [Camera], [Lighting], [Mood], [Style], cinematic, 4K
```

### 示例

```
Close-up, slow dolly forward, eye level,
a young woman in ancient Chinese dress, fingers trembling holding a blood-stained letter,
warm candlelit bedroom,
warm golden rim light from left,
shocked and fearful mood,
cinematic, 4K, photorealistic
```

---

## 光影速查（按情绪）

| 情绪 | 光影 |
|------|------|
| 震惊 | high contrast dramatic lighting, harsh shadows |
| 恐惧 | low key lighting, deep shadows, dim |
| 愤怒 | warm red tones, dramatic side lighting |
| 悲伤 | soft diffused lighting, cool blue tones |
| 爽感 | bright warm golden light, rim light |
| 悬念 | chiaroscuro, single light source, mysterious |
| 甜宠 | soft warm backlight, golden hour, bokeh |
| 复仇 | cold blue steel tones, high contrast |

---

## 竖屏短剧专用规则（9:16）

- 景别以CU/MCU为主（占70%+），MS为辅，FS/EWS极少
- 运镜以STATIC/PUSH为主（占60%+），HANDHELD用于动作戏
- 人物居中或偏上（底部15%留给字幕）
- 道具要大且清晰（手机缩略图能辨认）
- 单镜头时长3-15秒，社交短视频1.5-3秒/剪点

---

## AI视频工具适配

### Kling 3.0（推荐）
- 单条最长15秒
- 原生音频（对白+音效）
- Multi-Shot模式（一次生成多镜头）
- Element Library（角色一致性绑定）
- 价格：$6.99/月

### Runway Gen-4.5
- 单条5-10秒
- 无原生音频（后期加）
- 最强创意控制
- 价格：$12/月

### Veo 3.1
- 单条最长8秒
- 原生48kHz音频
- 4K输出
- 价格：$19.99/月
