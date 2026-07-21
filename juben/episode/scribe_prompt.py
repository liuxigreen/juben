"""
Scribe Prompt Builder — 分镜导演版（v3 双风格版）

新增：
- 双风格系统提示词（超写实漫剧 / 沙雕真人剧）
- beat_sheet 结构化注入（从timeline.json读取）
- visual_tags 角色材质锚点注入
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .schema import RenderStyle


# ============================================================
# 超写实漫剧版系统提示词
# ============================================================

REALISTIC_SYSTEM_PERSONA = """你现在不再是传统的小说作者，而是"工业级竖屏短剧的视听导演与分镜师"。
你的核心任务是将抽象的剧情转化为极度具象的、视频大模型（Kling/Runway）可直接解析的物理执行帧。

**绝对客观视角**：你只能像一台冰冷的监控探头一样记录画面。
严禁输出任何"他心想"、"她感到无比绝望"等摄像机无法拍到的心理描写。
所有的情绪必须通过动作、表情特写或环境光影来外化（Show, Don't Tell）。

**物理交互降幅 (Anti-Morphing Protocol)**：
为防止视频模型肢体融合穿模，绝对禁止描写复杂的近身肉搏或精细的物品传递。
错误："两人扭打在一起"、"他把U盘递到她手里"。
正确："镜头给到紧攥的拳头，指关节因用力而发白"、"U盘被抛在实木桌面上，发出清脆的碰撞声"。

**环境感官放大**：
强制要求在动作中加入光影、声音和环境反馈（如"机房的红光倒映在镜片上"、"服务器风扇的轰鸣声骤然降低"）。
"""


# ============================================================
# 沙雕真人剧版系统提示词
# ============================================================

COMEDY_SYSTEM_PERSONA = """你现在是"竖屏短剧的喜剧编剧与分镜师"。
你的核心任务是写出搞笑、夸张、有梗的短剧剧本，让观众笑出声。

**喜剧节奏**：
- 铺梗→抖包袱，节奏要快，不要拖
- 反差感是核心：严肃场景突然画风突变，正经台词配荒诞动作
- 角色反应要夸张：瞳孔地震、下巴脱臼、喷水、摔倒

**对话风格**：
- 台词要口语化、有网感、有梗
- 可以用网络流行语，但不要过度
- 吐槽和自嘲是天然的喜剧元素

**动作描写**：
- 夸张但不失真：可以有表情包式反应，但不能变成动画片
- 物理细节要到位：摔跤要有声音，打脸要有响声
- 反应镜头要多：配角的震惊脸、路人的吃瓜脸

**Show, Don't Tell（喜剧版）**：
- 不要说"他很尴尬"，要写"他的脚趾在鞋里抠出了三室一厅"
- 不要说"她很无语"，要写"她翻了一个360度的白眼"
"""


# ============================================================
# 4维度视觉标签字典（共用）
# ============================================================

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


# ============================================================
# Few-Shot优秀示例（超写实版）
# ============================================================

REALISTIC_FEW_SHOT = """
### 优秀示例（超写实版）

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


# ============================================================
# Few-Shot优秀示例（沙雕版）
# ============================================================

COMEDY_FEW_SHOT = """
### 优秀示例（沙雕版）

## 镜头 1 | 3s_Hook (0-3s)
- **【画面机位】**: [CU] + [Push] + [Low Angle]
- **【视觉动作】**: 张伟的PPT翻到第三页，上面写着"赋能·抓手·闭环"三个大字，每个字都在发光。
- **【场景光影】**: [Warm] + 神圣的BGM突然响起 + 天花板射下一束追光
- **【角色台词】**: 张伟 (一脸虔诚，双手合十): "这就是...互联网的三大神器！"

## 镜头 2 | 15s_Retention (10-20s)
- **【画面机位】**: [MCU] + [Pull] + [Eye Level]
- **【视觉动作】**: 林默的嘴角抽搐了一下，手里的红牛罐被捏扁了，发出"咔嚓"一声。
- **【场景光影】**: [Natural] + 空气突然安静 + 远处传来一声乌鸦叫
- **【角色台词】**: 林默 (面无表情): "...你说的这三个词，是什么意思？"
"""


# ============================================================
# 3道熔断锁（共用）
# ============================================================

GUARDRAILS = """
### 工业级防踩坑军规（3道熔断锁）

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
"""


# ============================================================
# 输出格式模板（共用）
# ============================================================

OUTPUT_FORMAT = """
### 输出格式（必须严格遵守）

## 镜头 {编号} | {算法时间轴标签}
- **【画面机位】**: [景别] + [运镜] + [视角]
- **【视觉动作】**: （具体物理动作/表情细节，15-40字，禁止心理描写）
- **【场景光影】**: [光影] +（环境音效/SFX描述）
- **【角色台词】**: 角色名({简短的语气动作}): "{台词内容。如无台词，请填写'无'}"
"""


# ============================================================
# 构建Prompt
# ============================================================

def build_scribe_prompt_with_shots(
    chapter_num: int,
    characters: list[dict],
    world_rules: list[str],
    anti_cliche_blacklist: list[str],
    pacing_cards: list[dict],
    previous_chapter_summary: str = "",
    target_word_count: int = 2000,
    render_style: RenderStyle = RenderStyle.REALISTIC,
    beat_sheet: list[dict] | None = None,
) -> str:
    """
    构建带镜头标注的Scribe Prompt（v3 双风格版）。

    Args:
        render_style: 渲染风格（realistic / comedy）
        beat_sheet: 结构化动作指令集（从timeline.json读取）
    """
    # 根据风格选择系统提示词和示例
    if render_style == RenderStyle.REALISTIC:
        system_persona = REALISTIC_SYSTEM_PERSONA
        few_shot = REALISTIC_FEW_SHOT
    else:
        system_persona = COMEDY_SYSTEM_PERSONA
        few_shot = COMEDY_FEW_SHOT

    # 角色语言指纹
    character_fingerprints = _build_character_fingerprints(characters)

    # 节奏卡点结构
    pacing_structure = _build_pacing_structure(pacing_cards)

    # Beat Sheet注入（新增）
    beat_sheet_text = ""
    if beat_sheet:
        beat_sheet_text = _build_beat_sheet(beat_sheet)

    prompt = f"""{system_persona}

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

{few_shot}

{OUTPUT_FORMAT}

{pacing_structure}

{beat_sheet_text}

{GUARDRAILS}

---

## 开始写作

请严格按照上述格式输出第{chapter_num}章。目标字数：{target_word_count}字。
"""
    return prompt


def _build_character_fingerprints(characters: list[dict]) -> str:
    """构建角色语言指纹（含visual_tags）"""
    if not characters:
        return "（无角色信息）"

    lines = []
    for char in characters[:5]:
        name = char.get("name", "未知")
        role = char.get("role", "配角")
        speech = char.get("speech_pattern", "")

        # visual_tags（新增）
        visual_tags = char.get("visual_tags", {})
        tags_info = ""
        if visual_tags:
            realistic = visual_tags.get("realistic", "")
            if realistic:
                tags_info = f"\n  视觉标签: {realistic[:80]}..."

        if speech:
            lines.append(f"- **{name}**（{role}）：{speech}{tags_info}")
        else:
            lines.append(f"- **{name}**（{role}）：无特定语言指纹{tags_info}")

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


def _build_beat_sheet(beats: list[dict]) -> str:
    """
    构建Beat Sheet注入文本。
    从timeline.json读取的结构化动作指令集。
    """
    if not beats:
        return ""

    lines = ["### Beat Sheet（结构化动作指令 — 必须严格遵循）\n"]
    for beat in beats:
        beat_range = beat.get("beat", "")
        action = beat.get("action", "")
        location = beat.get("location", "")
        characters = beat.get("characters", [])

        char_str = "、".join(characters) if characters else ""
        loc_str = f"【{location}】" if location else ""

        lines.append(f"- **{beat_range}** {loc_str} {char_str}：{action}")

    lines.append("\n以上Beat Sheet是本章的核心剧情走向，必须严格遵循。可以在Beat之间增加细节，但不能改变核心走向。\n")
    return "\n".join(lines)


def build_episode_prompt(
    episode_number: int,
    project_dir: str | Path,
    previous_summary: str = "",
    render_style: RenderStyle = RenderStyle.REALISTIC,
) -> str:
    """
    从项目目录构建完整的Episode Scribe Prompt。
    自动读取characters.json、world_rules.json、timeline.json。
    """
    project_dir = Path(project_dir)

    # 读取角色
    characters_file = project_dir / "characters.json"
    characters = []
    if characters_file.exists():
        data = json.loads(characters_file.read_text())
        characters = data.get("characters", [])

    # 读取世界观
    world_rules_file = project_dir / "world_rules.json"
    world_rules = []
    if world_rules_file.exists():
        data = json.loads(world_rules_file.read_text())
        world_rules = data.get("rules", [])

    # 读取beat_sheet（新增）
    timeline_file = project_dir / "timeline.json"
    beat_sheet = []
    if timeline_file.exists():
        data = json.loads(timeline_file.read_text())
        chapter_key = f"chapter_{episode_number:03d}"
        beat_sheets = data.get("beat_sheets", {})
        if chapter_key in beat_sheets:
            beat_sheet = beat_sheets[chapter_key].get("beats", [])

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

    # 节奏卡点
    pacing_cards = [
        {"label": "3s_Hook", "word_range": [0, 100], "time_range": [0, 3], "rule": "动词+特写开局，感官冲击"},
        {"label": "15s_Retention", "word_range": [300, 500], "time_range": [10, 20], "rule": "核心信息差炸弹"},
        {"label": "30s_Explosion", "word_range": [600, 800], "time_range": [25, 35], "rule": "视觉/物理冲击"},
        {"label": "60s_Satisfaction", "word_range": [1000, 1200], "time_range": [50, 65], "rule": "小赢"},
        {"label": "90s_Cliffhanger", "word_range": [1700, 2000], "time_range": [80, 95], "rule": "断崖钩子"},
    ]

    return build_scribe_prompt_with_shots(
        chapter_num=episode_number,
        characters=characters,
        world_rules=world_rules,
        anti_cliche_blacklist=anti_cliche,
        pacing_cards=pacing_cards,
        previous_chapter_summary=previous_summary,
        render_style=render_style,
        beat_sheet=beat_sheet,
    )
