# 《心声咖啡》Stage 3 操作手册
# Google Flow 网页版 · 手动生成视频流程

---

## 第一步：创建角色（Characters）

在Flow中创建角色，保持跨镜头一致性。

### 苏念 (Su Nian) — 女主角

**创建方式：** Character → Custom Prompt

**角色创建提示词：**
```
A 26-year-old Chinese woman with a round face and shoulder-length black hair. She has a small burn scar on her left ring finger. She wears a simple brown apron over a white t-shirt. Natural look, no heavy makeup. Warm but tired eyes. Barista at a small coffee shop. Realistic, cinematic style, soft natural lighting.
```

**角色卡（多角度）：**
```
Character sheet of a 26-year-old Chinese woman: front view, side view, 3/4 view, back view. Round face, shoulder-length black hair, small burn scar on left ring finger. Wearing brown apron over white t-shirt. Clean background, full body, consistent appearance. Cinematic, photorealistic.
```

**声音描述：**
```
Young Chinese woman, soft voice, speaks concisely, uses coffee metaphors. When nervous, her voice gets quieter. Gentle but determined tone.
```

---

### 顾深 (Gu Shen) — 男主角

**角色创建提示词：**
```
A 30-year-old Chinese man, tall and lean, wearing silver-framed glasses and a dark navy suit. He has a callus on his right index finger from years of writing. Sharp jawline, serious expression but kind eyes. Corporate investor who visits a small coffee shop. Realistic, cinematic style.
```

**角色卡：**
```
Character sheet of a 30-year-old Chinese man: front view, side view, 3/4 view. Tall, silver-framed glasses, dark navy suit, callus on right index finger. Clean background, full body. Cinematic, photorealistic.
```

**声音描述：**
```
Deep calm Chinese male voice, speaks slowly and precisely, never wastes words. When angry, becomes quieter not louder. Measured, deliberate delivery.
```

---

### 林可 (Lin Ke) — 女配角

**角色创建提示词：**
```
A 25-year-old Chinese woman with a ponytail and colorful painted nails. She carries a large bag full of art supplies. Casual artistic style, expressive eyes. Best friend of the coffee shop owner. Realistic, cinematic.
```

---

### 陈锐 (Chen Rui) — 反派

**角色创建提示词：**
```
A 32-year-old Chinese man with a square jaw and short hair. Wears casual clothes but an expensive watch. Crow's feet when smiling. Former coffee shop owner turned corporate investor. Realistic, cinematic.
```

---

## 第二步：创建场景参考（Ingredients）

### 念想咖啡店 — 主场景

**场景参考图提示词：**
```
Interior of a small cozy Chinese coffee shop. Wooden counter, vintage espresso machine, wall covered with yellowed sticky notes with handwriting. Warm amber lighting, afternoon sun through window. A few small tables, potted plants. Nostalgic, intimate atmosphere. Cinematic, photorealistic, 9:16 vertical.
```

**使用方式：** 生成后保存为Ingredient，每次在咖啡店场景时引用。

---

### 面馆 — 第9章场景

**场景参考图提示词：**
```
Interior of a small Chinese noodle shop. Fluorescent lighting, steam from kitchen, wooden tables, vinegar bottles on table. Noisy, crowded atmosphere. Cinematic, photorealistic.
```

---

### 巷子 — 多章场景

**场景参考图提示词：**
```
A narrow old Chinese alley at night. Blue stone pavement, dim moonlight between buildings, old brick walls. A single street light. Quiet, atmospheric. Cinematic, photorealistic.
```

---

## 第三步：生成视频（逐镜头）

### 操作流程

```
1. 选择模式: Ingredients to Video (Veo 2) 或 Text to Video (Veo 3)
2. 添加Ingredients: 角色参考图 + 场景参考图（最多3个）
3. 输入提示词: 使用下面的逐镜头提示词
4. 选择时长: 5-8秒
5. 选择镜头运动: 使用Flow内置camera controls
6. 生成 → 检查 → 不满意就重新生成
7. 满意后 → Add to Scene（加入Scene Builder）
8. 使用Jump To连接下一镜头（保持角色连续性）
```

### 角色一致性的关键技巧

```
1. 每次都引用同一个Character（@Su_Nian）
2. 每次都引用同一个场景Ingredient
3. 使用Jump To连接相邻镜头（自动保持最后一帧连续）
4. 如果角色变了，回到原始角色参考图重新生成
5. 描述中始终包含外貌关键词（round face, shoulder-length hair, apron）
```

---

## 第四步：逐镜头提示词

### 第1章 口红印

**Shot 1 [WS] 6s — 咖啡店日常**
```
@Su_Nian wipes the coffee shop counter with a rag, glancing at the entrance for the third time. An old man dozes by the window, a girl frowns at her laptop in the corner. Afternoon light, warm amber tones. Wide shot, static camera, 9:16 vertical.
```
Camera: Static

**Shot 2 [MS] 5s — 顾深进场**
```
A man in a grey suit @Gu_Shen walks in through the door, the doorbell chimes. He sits at the counter without looking at the menu, pulls out his phone and places it face-down. Medium shot, slow dolly forward, 9:16.
```
Camera: Slow dolly forward

**Shot 3 [MCU] 5s — 点单**
```
@Gu_Shen says: "Americano, hot." @Su_Nian nods, turns around and grinds coffee beans. The man taps his fingers rhythmically on the counter. Medium close-up, static, 9:16.
```
Camera: Static
Audio: "美式，热的。"

**Shot 4 [ECU] 5s — 手指敲击**
```
Extreme close-up of @Gu_Shen fingers tapping on the wooden counter — index, middle, ring, repeating. His suit cuff has a small ink stain. Shallow depth of field, 9:16.
```
Camera: Static

**Shot 5 [MCU] 5s — 咖啡端上**
```
@Su_Nian places the americano in front of @Gu_Shen. He takes a sip, sets the cup down. A clean arc-shaped mark appears on the rim from condensation. Medium close-up, static, 9:16.
```
Camera: Static

**Shot 6 [CU] 5s — 注意到异常**
```
@Su_Nian turns to wipe a second table. She pauses, noticing the man's cup is still steaming but he has already set it down. Close-up on her face, slight frown. 9:16.
```
Camera: Slow push

**Shot 7 [MCU] 6s — 端起杯子（读心触发）**
```
@Su_Nian walks back to the counter, picks up the americano. The cup is hot to the touch. She closes her eyes and takes a sip. Medium close-up, slow push, 9:16.
```
Camera: Slow push

**Shot 8 [CU] 6s — 读心（世界安静）**
```
Close-up of @Su_Nian with eyes closed, eyelashes trembling. Background figures freeze mid-motion, steam from cups hangs motionless in the air. Everything goes silent. Dreamlike, desaturated blue tones, surreal vignette. 9:16.
```
Camera: Rapid push-in

**Shot 9 [ECU] 5s — 心声内容**
```
Extreme close-up of a cup rim, ripples in the coffee surface forming patterns. A low voice emerges, muffled. Ethereal, mysterious lighting. 9:16.
```
Camera: Static
Audio (VO): "这个月KPI又完不成了……那家店……合同都准备好了……"

**Shot 10 [CU] 5s — 睁眼**
```
@Su_Nian eyes snap open. All ambient sounds return — the old man shifts, keyboard clacks. Her expression is shocked, breath catches. Close-up, 9:16.
```
Camera: Static

**Shot 11 [ECU] 6s — 疤痕特写**
```
Extreme close-up of @Su_Nian left hand, ring finger. The old burn scar is still there. Beside it, a faint new mark she doesn't recognize. She traces her finger across it. 9:16.
```
Camera: Slow push

**Shot 12 [MS] 5s — 顾深离开**
```
@Gu_Shen stands up, types on his phone without looking up. He asks "How much?" @Su_Nian answers. He scans QR code, turns and leaves. Medium shot, 9:16.
```
Camera: Static
Audio: "多少钱？" / "二十八。"

**Shot 13 [CU] 5s — 看向门外**
```
@Su_Nian watches through the window as @Gu_Shen walks into the revolving door of the office building across the street. Close-up, slow push, 9:16.
```
Camera: Slow push

**Shot 14 [ECU] 6s — 口红印发现**
```
Extreme close-up of the americano cup. On the rim, a faint lipstick mark — not hers, she hasn't worn lipstick today. The mark is mysterious, unexplained. 9:16.
```
Camera: Static

**Shot 15 [MS] 5s — 冲洗杯子**
```
@Su_Nian places the cup in the sink, turns on hot water. The stream rinses away the lipstick mark, the condensation, everything. Medium shot, 9:16.
```
Camera: Static

**Shot 16 [CU] 5s — 疤痕回看**
```
@Su_Nian dries her hands, looks down at her left ring finger. The scar remains. But something feels different — something is missing. Close-up, contemplative, 9:16.
```
Camera: Static

**Shot 17 [CU] 5s — 章末钩子**
```
@Su_Nian stares at the cup in the sink, coffee surface trembling with an unseen vibration. Her expression is haunted, uncertain. Close-up, low key lighting, 9:16.
```
Camera: Static

---

## 第五步：Scene Builder拼接

```
1. 每生成一个满意clip → Add to Scene
2. 相邻镜头用Jump To连接（自动保持角色连续性）
3. 如果Jump To效果不好 → 用Frames to Video，手动选上一clip最后一帧
4. 用Extend延长好的片段
5. 用Trim裁剪多余部分
6. 全部拼完 → Download Scene
```

## 第六步：后期处理

```
1. 下载的视频导入剪映
2. 导入srt_subtitles/ch001_labeled.srt（带说话人标注的字幕）
3. 按voice_direction.txt录制配音
4. 配音对齐voice_data.json的时间码
5. 心声部分用画外音轨道（不覆盖画面原声）
6. 导出成片
```

---

## 每章生成顺序建议

| 优先级 | 章节 | 原因 |
|--------|------|------|
| 先做 | Ch1 | 建立角色+场景基准 |
| 再做 | Ch7 | 简单章节（只有8个beat），练手 |
| 然后 | Ch9 | 对峙场景，测试对话 |
| 然后 | Ch15 | 情感高潮，测试心声 |
| 最后 | 其余章节 | 按顺序做 |

---

## 重要提示

1. **每次生成前都引用@角色名** — 保持一致性
2. **场景参考图每次都要加** — 保持地点一致
3. **用Jump To连接相邻镜头** — 这是保持连续性的最佳方式
4. **不满意就重新生成** — Flow允许无限重试
5. **先做好角色参考图** — 这是一切的基础
6. **Veo 3支持对话** — 可以让角色说台词
7. **保存好的clip为Ingredient** — 后续可复用
