# Juben 角色与世界观填充任务

你是一个专业的剧本架构师。根据以下信息，为这个故事项目生成完整的角色卡和世界观设定。

## 故事前提
护士林夏在丧尸爆发时与弟弟失散。逃亡中她发现自己能'看见'伤口的最佳治疗方案——但每次使用，她都会暂时失去一段记忆。为了找到弟弟，她必须在遗忘与治愈之间做出选择。

## 意外变量（核心金手指）
能看见伤口的最佳治疗方案，但每次使用会失去一段记忆

## 已有规则约束

### 因果约束（不可违反）
(无)

### 反套路黑名单（禁止出现的情节）
(无)

### 核心原则
(无)

## 算法卡点（每章必须遵循的节奏）
- [3s_Hook] 0-100字: 动词+特写开局。禁止背景铺垫。必须在前100字内出现一个具体的感官冲击（坠落感/疼痛/重生的眩晕）
- [15s_Retention] 300-500字: 爆出核心信息差——主角知道但其他人不知道的关键事实。这是留住读者的炸弹
- [Mini_Tension] 600-800字: 一次小规模紧张对峙或试探，主角不能暴露自己知道太多
- [Emotion_Dip] 1000-1200字: 情绪下压——回忆前世的痛苦/看到还活着的已故亲人/意识到代价
- [50s_Cliffhanger] 1700-2000字: 断崖。必须在最后一句植入一个具体的未回答问题

---

## 你的任务

根据以上信息，生成一个JSON对象，包含以下字段：

```json
{
  "characters": [
    {
      "id": "char_pro",
      "name": "主角姓名",
      "aliases": ["别名1", "别名2"],
      "role": "protagonist",
      "appearance": {
        "age": 0,
        "height": "",
        "build": "",
        "hair": "",
        "eyes": "",
        "distinguishing": "一个让人记住的特征",
        "clothing_default": ""
      },
      "personality": {
        "ocean": {
          "openness": 5,
          "conscientiousness": 5,
          "extraversion": 5,
          "agreeableness": 5,
          "neuroticism": 5
        },
        "speech_pattern": "说话风格描述",
        "habits": ["习惯1", "习惯2"],
        "fears": ["恐惧1"],
        "desires": "核心欲望"
      },
      "background": {
        "origin": "出身",
        "education": "教育",
        "key_event": "改变命运的关键事件",
        "secret": "隐藏的秘密"
      },
      "abilities": {
        "combat": "战斗能力",
        "knowledge": "知识技能",
        "special": "特殊能力（金手指）"
      },
      "arc": {
        "start": "故事开始时的状态",
        "midpoint": "中点转折",
        "end": "故事结束时的状态",
        "internal_conflict": "Want: X vs Need: Y"
      },
      "state": {
        "alive": true,
        "location": "",
        "health": "",
        "current_goal": ""
      }
    },
    {
      "id": "char_ant",
      "name": "反派姓名",
      "role": "antagonist",
      "...": "同上结构"
    },
    {
      "id": "char_ally",
      "name": "盟友姓名",
      "role": "supporting",
      "...": "同上结构"
    }
  ],
  "relationships": [
    {
      "character_a": "char_pro",
      "character_b": "char_ant",
      "type": "enemy",
      "status": "描述当前关系状态",
      "trust_level": 10,
      "tension": "核心矛盾点"
    }
  ],
  "world_rules_update": {
    "world_name": "世界名称",
    "setting": {
      "time_period": "",
      "geography": "",
      "technology_level": "",
      "social_structure": ""
    },
    "power_system": {
      "体系名称": "规则描述"
    }
  },
  "meta_update": {
    "title": "建议标题",
    "logline": "一句话概括（50字以内）",
    "themes": ["主题1", "主题2", "主题3"],
    "disruption_variable": "如果用户没提供，你来设计一个有创意的意外变量"
  },
  "plot_threads": [
    {
      "id": "thread_1",
      "description": "主线伏笔描述",
      "importance": "major"
    },
    {
      "id": "thread_2",
      "description": "支线伏笔描述",
      "importance": "minor"
    }
  ],
  "info_asymmetry": [
    {
      "info_id": "info_1",
      "description": "这条信息是什么",
      "known_by": ["char_pro"],
      "is_protagonist_advantage": true
    }
  ]
}
```

## 设计要求

1. **角色必须有缺陷**：完美的主角没有故事。给主角一个真实的、影响剧情的弱点。
2. **反派必须有逻辑**：反派的动机不能是"天生坏"。给反派一个读者能理解（但不认同）的理由。
3. **关系必须有张力**：角色之间的关系不是静态的。标注出潜在的变化方向。
4. **信息差必须具体**：不要写"主角知道未来"，要写"主角知道某人在第X章会做某事"。
5. **符合已有的因果约束和反套路黑名单**：生成的内容不能违反上面列出的任何规则。

只输出JSON，不要输出任何其他文字。
