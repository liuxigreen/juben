"""
Scribe Prompt Builder — 分镜导演版（v2）

整合Agent的Prompt设计 + 我的代码实现。
核心策略：4维度标签库 + Few-Shot示例 + 3道熔断锁。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


# 系统身份设定
SYSTEM_PERSONA = """你现在不再是传统的小说作者，而是"工业级竖屏短剧的视听导演与分镜师"。
你的核心任务是将抽象的剧情转化为极度具象的、视频大模型（Kling/Runway）可直接解析的物理执行帧。

**绝对客观视角**：你只能像一台冰冷的监控探头一样记录画面。
严禁输出任何"他心想"、"她感到无比绝望"等摄像机无法拍到的心理描写。
所有的情绪必须通过动作、表情特写或环境光影来外化（Show, Don't Tell）。"""

# 4维度视觉标签字典（只能用这些，不能自创）
VISUAL_ENUM = """
### 视觉标签字典（只能用这些，不能自创）

**景别 (Shot Size)**：
- [CU] 特写：情绪爆发、极致痛苦、微小关键道具展示（血珠、颤抖的睫毛、婚戒）
- [MCU] 近景：双人对决、拔剑/扇耳光等中幅度动作、日常对话
- [MS] 中景：腰部以上，动作+环境
- [WS] 全景：仅用于开场定场或宏大环境交代，极其克制使用

**运镜 (Camera Movement)**：
- [Static] 静止：特写开局、信息传递、稳定观察
- [Push] 推镜：镜头缓慢逼近。发现秘密、极度压迫感、杀意显露
- [Pull] 拉镜：镜头后退。展现身份反差、震惊全场、孤立无援
- [Handheld] 手持：战斗、逃亡、极度恐慌或慌乱的场景

**光影 (Lighting & Vibe)**：
- [Low key] 冷调：地牢、验尸房、阴谋、绝望
- [Warm] 暖光：功德金光、圣女降临、大反转、救赎
- [High contrast] 高对比：血腥杀戮、极致情绪爆发、强烈的明暗交界

**视角 (Camera Angle)**：
- [Low Angle] 仰视：镜头从下往上拍。赋予画面对象极强的权力感、压迫感和神性
- [High Angle] 俯视：镜头从上往下拍。制造被碾压感、蝼蚁感、极度无助
- [Eye Level] 平视：客观陈述，正常的视线交流

**规则**：
- 每个镜头必须从以上4个维度各选1个标签
- 竖屏短剧以[CU]和[MCU]为主（占70%+）
- 相邻镜头的运镜必须变化（不能连续两个Push）
"""

# Few-Shot优秀示例
FEW_SHOT_EXAMPLE = """
### 优秀示例（参考这个质量标准）

## 镜头 1 | 3s_Hook (0-3s)
- **【画面机位】**: [CU] + [Push] + [Low Angle]
- **【视觉动作】**: 漆黑的万魂幡被狠狠砸在木桌上，原本阴森的幡面瞬间爆发出刺眼的纯金光芒，照亮了整个暗室。
- **【场景光影】**: [Warm] + 沉闷的重低音轰鸣 (Sub bass drop)
- **【角色台词】**: 魔尊 (瞳孔剧烈收缩，手指发抖): "你...你管这叫魔器？！"

## 镜头 2 | 15s_Retention (10-20s)
- **【画面机位】**: [MCU] + [Pull] + [Eye Level]
- **【视觉动作】**: 少年从破旧的布袋里掏出一叠泛黄的劳动合同，整齐地摆在桌上，手指按在"甲方"签名处。
- **【场景光影】**: [High contrast] + 纸张翻动的沙沙声 + 远处传来锁链拖地的回响
- **【角色台词】**: 少年 (微笑，语气平静): "师尊，这是按劳动法超度出来的，您信吗？"
"""

# 4道熔断锁（含空镜禁令）
GUARDRAILS = """
### 工业级防踩坑军规（4道熔断锁）

**1. 视觉死帧禁令**：
如果连续2个镜头内，【视觉动作】没有发生任何物品位移、肢体冲突或极端的面部微表情变化（仅是站着说话），将被系统判定为废稿。必须用物理细节打断沉闷。

**2. 反水字数/反嘴炮机制**：
- 单个镜头内的【角色台词】绝对不能超过3句话
- 复杂的设定必须切碎，分配到多个穿插着动作和环境变化的镜头中去交代
- 【视觉动作】控制在15-40字，必须是摄像机能拍到的物理动作

**3. 悬念切断法则 (Cliffhanger Rule)**：
每个章节的最后一个镜头：
- 【视觉动作】必须卡在冲突爆发的前一秒（例如：刀锋距离脖子一寸、刚刚推开密室的门）
- 或者【角色台词】抛出一个极其反常的终极疑问
- 绝对禁止出现"一切归于平静"、"她闭上眼睛睡了"、"新世界开始了"等情绪升华与收尾句式

**4. 空镜禁令 (No Empty Shot Rule)**：
空镜 = 没有角色表演、纯环境/道具展示的镜头。
- 每集最多2个空镜
- 每个空镜≤3秒
- 空镜必须有剧情功能：转场（地点变化）/ 信息（证据特写）/ 情绪（暗示心情）
- 连续两个镜头不能都是空镜
- 开场（镜头1）和结尾（最后镜头）禁止使用空镜
- 纯风景展示（山水花鸟）= 废稿
"""

# 钩子类型说明（结尾必须使用）
HOOK_TYPES = """
### 结尾钩子类型（必须选择一种）

**悬念钩**：抛出关键疑问，答案留到下一集
- 子模式：身份悬念、结果悬念、选择悬念、来者悬念、发现悬念
- 示例："她打开抽屉，瞳孔骤缩——"

**反转钩**：最后一刻颠覆观众预期
- 子模式：身份反转、局势反转、关系反转、时间反转、动机反转
- 示例："DNA报告上写着——亲缘关系：父女"

**情绪钩**：情绪推到最高点然后切断
- 子模式：甜蜜中断、心碎中断、误会引爆、决绝中断、重逢中断
- 示例："他凑近，呼吸交缠——手机响了"

**信息钩**：透露改变全局的关键信息，只说一半
- 子模式：证据揭露、秘密泄露、记忆闪回、文件发现、线索串联
- 示例："监控录像里那个身影——穿着和他一模一样的衣服"

**危机钩**：突发重大危机，主角来不及反应
- 子模式：突袭、背刺、暴露、倒计时、绝境
- 示例："她接过他递来的水，喝了一口——他笑了"
"""

# 反派台词风格
VILLAIN_DIALOGUE = """
### 反派台词风格指南

**小反派台词**：嚣张直白
- "你也配？" "一个穷鬼也敢……"
- 被打脸后：结巴/求饶/面色煞白

**中反派台词**：阴险含蓄
- "你以为赢了？天真。" "识时务者为俊杰"
- 被击败后：不甘心/威胁/暗示更大的势力

**大反派台词**：从容自信
- "你很有意思，可惜……" "你还不够格"
- 被击败后：不服/揭露更多真相/悲壮

**隐藏反派台词**：
- 揭露前：温柔可靠的"好人"台词
- 揭露时："你真的以为这一切是巧合？"
- 揭露后：语气和用词180度反转
"""

# 输出格式模板
OUTPUT_FORMAT = """
### 输出格式（必须严格遵守）

## 镜头 {编号} | {算法时间轴标签}
- **【画面机位】**: [景别] + [运镜] + [视角]
- **【视觉动作】**: （具体物理动作/表情细节，15-40字，禁止心理描写）
- **【场景光影】**: [光影] +（环境音效/SFX描述）
- **【角色台词】**: {角色名} ({简短的语气动作}): "{台词内容。如无台词，请填写'无'}"
- **【钩子类型】**: （仅最后镜头填写，从5种钩子类型中选择）
"""


def build_scribe_prompt_with_shots(
    chapter_num: int,
    characters: list[dict],
    world_rules: list[str],
    anti_cliche_blacklist: list[str],
    pacing_cards: list[dict],
    previous_chapter_summary: str = "",
    target_word_count: int = 2000,
) -> str:
    """
    构建带镜头标注的Scribe Prompt（分镜导演版v2）。
    """
    # 角色语言指纹
    character_fingerprints = _build_character_fingerprints(characters)

    # 节奏卡点结构
    pacing_structure = _build_pacing_structure(pacing_cards)

    prompt = f"""{SYSTEM_PERSONA}

---

## 第{chapter_num}章 创作任务

### 角色语言指纹
{character_fingerprints}

### 世界观约束
{chr(10).join(f'- {rule}' for rule in world_rules)}

### 反套路黑名单（禁止出现）
{chr(10).join(f'- {item}' for item in anti_cliche_blacklist)}

### 上一章回顾
{previous_chapter_summary if previous_chapter_summary else "（第一章，无上文）"}

---

{VISUAL_ENUM}

{FEW_SHOT_EXAMPLE}

{HOOK_TYPES}

{VILLAIN_DIALOGUE}

{OUTPUT_FORMAT}

{pacing_structure}

{GUARDRAILS}

---

## 开始写作

请严格按照上述格式输出第{chapter_num}章。目标字数：{target_word_count}字。

**关键要求：**
1. 最后一个镜头必须使用钩子类型（悬念/反转/情绪/信息/危机）
2. 反派台词必须符合其层级风格
3. 每个镜头必须有信息增量，禁止空镜
"""
    return prompt


def _build_character_fingerprints(characters: list[dict]) -> str:
    """构建角色语言指纹"""
    if not characters:
        return "（无角色信息）"

    lines = []
    for char in characters[:5]:
        name = char.get("name", "未知")
        role = char.get("role", "配角")
        speech = char.get("speech_pattern", "")
        if speech:
            lines.append(f"- **{name}**（{role}）：{speech}")
        else:
            lines.append(f"- **{name}**（{role}）：无特定语言指纹")

    return "\n".join(lines)


def _build_pacing_structure(pacing_cards: list[dict]) -> str:
    """构建节奏卡点结构模板"""
    if not pacing_cards:
        pacing_cards = [
            {"label": "3s_Hook", "word_range": [0, 100], "time_range": [0, 3], "rule": "动词+特写开局，感官冲击"},
            {"label": "15s_Retention", "word_range": [300, 500], "time_range": [10, 20], "rule": "核心信息差炸弹"},
            {"label": "30s_Explosion", "word_range": [600, 800], "time_range": [25, 35], "rule": "视觉/物理冲击"},
            {"label": "60s_Satisfaction", "word_range": [1000, 1200], "time_range": [50, 65], "rule": "小赢"},
            {"label": "90s_Cliffhanger", "word_range": [1700, 2000], "time_range": [80, 95], "rule": "断崖钩子"},
        ]

    lines = ["### 节奏卡点结构（每个卡点输出一个镜头块）\n"]

    for i, card in enumerate(pacing_cards, 1):
        label = card.get("label", f"checkpoint_{i}")
        word_range = card.get("word_range", [0, 100])
        time_range = card.get("time_range", [0, 3])
        rule = card.get("rule", "")

        lines.append(f"""## 镜头 {i} | {label} ({time_range[0]}-{time_range[1]}s)
- **【画面机位】**: [景别] + [运镜] + [视角]
- **【视觉动作】**: （15-40字，禁止心理描写）
- **【场景光影】**: [光影] + 音效/SFX
- **【角色台词】**: 角色名(语气): "台词"
""")

    return "\n".join(lines)


def build_episode_prompt(
    episode_number: int,
    project_dir: str | Path,
    previous_summary: str = "",
) -> str:
    """
    从项目目录构建完整的Episode Scribe Prompt。
    """
    project_dir = Path(project_dir)

    # 读取角色
    characters_file = project_dir / "characters.json"
    characters = []
    if characters_file.exists():
        import json
        data = json.loads(characters_file.read_text())
        characters = data.get("characters", [])

    # 读取世界观
    world_rules_file = project_dir / "world_rules.json"
    world_rules = []
    if world_rules_file.exists():
        import json
        data = json.loads(world_rules_file.read_text())
        world_rules = data.get("rules", [])

    # 反套路黑名单
    anti_cliche = [
        "女主被陷害时只会哭和等男主来救",
        "男主在千钧一发之际从天而降",
        "女主明明有证据却不拿出来",
        "反派当众揭发女主，女主三句话反杀",
        "误会推动感情：不听解释转身就走",
        "女主摔倒必被男主接住",
        "一切归于平静",
        "她闭上眼睛睡了",
    ]

    # 节奏卡点（120秒/集，8镜头）
    # 参考0xsline节奏曲线：Rising 15% → Climbing 30% → Storm 35% → Final 20%
    pacing_cards = [
        {"label": "Hook", "word_range": [0, 80], "time_range": [0, 5], "rule": "动词+特写开局，感官冲击，必须有物理动作"},
        {"label": "Setup", "word_range": [80, 200], "time_range": [5, 20], "rule": "人物/场景建立，信息差炸弹"},
        {"label": "Rising_1", "word_range": [200, 350], "time_range": [20, 35], "rule": "第一个冲突点，悬念铺设"},
        {"label": "Rising_2", "word_range": [350, 500], "time_range": [35, 50], "rule": "冲突升级，人物关系揭示"},
        {"label": "Storm_1", "word_range": [500, 700], "time_range": [50, 70], "rule": "高潮风暴开始，视觉/物理冲击"},
        {"label": "Storm_2", "word_range": [700, 900], "time_range": [70, 85], "rule": "情绪爆发，关键反转"},
        {"label": "Satisfaction", "word_range": [900, 1100], "time_range": [85, 100], "rule": "小赢/爽感释放"},
        {"label": "Cliffhanger", "word_range": [1100, 1400], "time_range": [100, 120], "rule": "断崖钩子，卡在冲突前一秒"},
    ]

    return build_scribe_prompt_with_shots(
        chapter_num=episode_number,
        characters=characters,
        world_rules=world_rules,
        anti_cliche_blacklist=anti_cliche,
        pacing_cards=pacing_cards,
        previous_chapter_summary=previous_summary,
    )
