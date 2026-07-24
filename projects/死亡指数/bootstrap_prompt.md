# Juben 角色与世界观填充任务

你是一个专业的剧本架构师。根据以下信息，为这个故事项目生成完整的角色卡和世界观设定。

## 故事前提
外卖员深夜送餐时发现每栋楼都有一个'死亡指数'，只有他能看到

## 意外变量（核心金手指）
(未设定——请自行设计一个有创意的意外变量)

## 已有规则约束

### 因果约束（不可违反）
(无)

### 反套路黑名单（禁止出现的情节）
(无)

### 核心原则
(无)

## 算法卡点（每章必须遵循的节奏）
(无)

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
      },
      "hidden_motivation": "不告诉主角的真实目的（NPC专用，主角可留空）",
      "personal_goal": "独立于主线剧情的自身诉求（如：想升职、想追某人、想还债）"
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
  ],
  "entity_anchors": {
    "概念名称1": {
      "anchor_prop": "具体物理道具名称（可拍摄）",
      "must_include_keywords": ["硬核关键词1", "硬核关键词2", "硬核关键词3"],
      "typical_action": "角色与道具交互的典型动作描写"
    },
    "概念名称2": {
      "anchor_prop": "具体物理道具名称",
      "must_include_keywords": ["关键词1", "关键词2", "关键词3"],
      "typical_action": "典型动作描写"
    }
  }
}
```

## 设计要求

1. **角色必须有缺陷**：完美的主角没有故事。给主角一个真实的、影响剧情的弱点。
2. **反派必须有逻辑**：反派的动机不能是"天生坏"。给反派一个读者能理解（但不认同）的理由。
3. **关系必须有张力**：角色之间的关系不是静态的。标注出潜在的变化方向。
4. **信息差必须具体**：不要写"主角知道未来"，要写"主角知道某人在第X章会做某事"。
5. **符合已有的因果约束和反套路黑名单**：生成的内容不能违反上面列出的任何规则。
6. **实体锚点必须具体可拍**：每个核心抽象概念（如"经济压力"、"神秘威胁"、"职业身份"）都必须解构为一个可以在镜头前展示的物理道具/UI界面，并给出3个硬核关键词。禁止用抽象名词作为锚点。
7. **NPC必须有隐秘动机和个人目标**：每个非主角角色必须有`hidden_motivation`（不告诉主角的真实目的）和`personal_goal`（独立于主线的自身诉求）。这两个字段是NPC行为的锚点——没有它们，NPC就会退化成解说员。主角可以留空。

## 高概念模式（必须生成）

### 核心要求
你的任务是为这个故事设计一个**足够新颖的核心异常**，让这个故事不同于常见的短剧套路。

### 生成策略（并行思考3-5个候选）
请从以下角度思考候选：
1. **机制异象**：这个世界多了一条什么异常规则？（如：死者生前最后12分钟的视野会投射到凶手的手机上）
2. **工具异变**：一个日常物品成为了唯一线索/武器/诅咒载体？（如：外卖软件自动派发"发往空屋的无名订单"）
3. **信息特权反转**：只有最底层的人能看见真实规则？（如：只有外卖员能看到每栋楼的"死亡指数"）
4. **因果倒置**：结果先发生，原因被系统性地隐瞒？（如：死者在死前7天就开始给自己送花）

### 俗套黑名单（严禁使用）
以下套路已被市场严重滥用，**禁止使用**：
1. 禁止"主角真实身份是隐退兵王/前刑警/隐世神医/隐藏首富"
2. 禁止"主角因为车祸/意外失忆"
3. 禁止"靠系统打卡/签到直接获得无敌奖励"
4. 禁止"重生后利用前世记忆碾压所有人"
5. 禁止"主角是天选之人，天赋异禀"

### 每个候选必须同时输出
```json
{
  "anomaly": "这个世界多出来的那条异常规则（一句话）",
  "visual_core": "一个能拍下来的画面",
  "personal_cost": "主角必须持续付出的代价",
  "why_new": "为什么它不像常见短剧",
  "visual_anchor_prop": "从异常中长出的视觉锚点道具",
  "visual_anchor_keywords": ["关键词1", "关键词2", "关键词3"]
}
```

### 筛选标准（按优先级）
1. **新颖度**：是否容易被预测成已知模板？
2. **可视觉化**：能否用一个镜头讲清？
3. **可持续**：能否支撑10章以上，而不是一次性梗？
4. **个人代价清晰**：必须有身体/关系/时间上的持续损耗

### 输出格式
从你的候选中选出最好的1个，填入JSON的`high_concept`字段：
```json
{
  "high_concept": {
    "enabled": true,
    "anomaly": "你选出的异常规则",
    "visual_core": "你选出的核心画面",
    "personal_cost": "主角的持续代价",
    "why_new": "为什么新颖",
    "banned_patterns": ["禁止的故事结构1", "禁止的故事结构2"],
    "visual_anchor_prop": "视觉锚点道具",
    "visual_anchor_keywords": ["关键词1", "关键词2", "关键词3"]
  }
}
```

**重要**：选出后，这个异常将成为全剧的核心，后续所有剧情都必须围绕它展开，不能退化成普通故事。

只输出JSON，不要输出任何其他文字。
