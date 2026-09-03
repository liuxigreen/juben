"""
重生复仇题材模板 — 最刁钻的测试靶子

特点：
- 前世记忆+当前时间线双轨
- 角色关系有时间差（主角知道背叛，对方还不知道主角知道）
- 信息对称性矩阵极其复杂
- AI味最容易在复仇情绪中暴露
"""
from __future__ import annotations

from juben.genre_templates.registry import register
from juben.state.schema import (
    Abilities, Appearance, Background, Character, CharacterArc,
    CharacterRole, CharacterState, HighConcept, OCEAN, PacingCard, Personality,
    RelationshipGraph, Relationship, StoryMeta, WorldRules,
    CliffhangerType,
)


@register("rebirth-revenge")
def init_rebirth_revenge(premise: str = "", language: str = "zh-CN") -> dict:
    """
    初始化重生复仇项目。
    返回 dict: {"meta": StoryMeta, "characters": list[Character], "world_rules": WorldRules}
    """
    default_premise = (
        "主角被最信任的合伙人和未婚妻联手背叛，"
        "公司被夺、身败名裂、坠楼身亡。"
        "重生回到三年前创业初期，"
        "这一次他要守护失去的一切，并让背叛者付出代价。"
    )

    meta = StoryMeta(
        title="逆流",
        genre="rebirth-revenge",
        sub_genres=["identity-fall", "business"],
        premise=premise or default_premise,
        logline="被合伙人和未婚妻联手背叛坠楼的创业者，重生回三年前，用前世记忆逐一拆解背叛者的棋局",
        target_chapters=50,
        target_word_count_per_chapter=900,  # 爆款对齐：90秒单集台词本体
        pov="third_person_limited",
        language=language,
        # === 意外变量 ===
        # 爆款对齐：重生文的核心爽感是"先知确定性"——记忆 100% 灵验、步步踩点。
        # 代价改从"使用金手指本身有副作用"出，而不是让金手指失准（失准=把爽剧写成悬疑）。
        disruption_variable=(
            "主角重生回三年前，前世记忆 100% 灵验——股价、赛事、背叛的时间点全部踩得中。"
            "金手指的代价是【记忆回溯反噬】：每动用一次前世记忆做重大决策，"
            "就会经历一次前世坠楼瞬间的闪回剧痛，且动用越多越容易被同样重生/知情的人察觉。"
            "在这个先知外挂之上，叠加主角顶级产品经理的操盘能力作为第二层优势。"
        ),
        # === v1.1.0: 高概念模式默认开 (防退化核心) ===
        high_concept=HighConcept(
            enabled=True,
            anomaly=(
                "主角重生后前世记忆100%灵验，但每次动用先知都要承受坠楼闪回剧痛，"
                "且用得越多越容易被'同样记得上一世的人'察觉"
            ),
            visual_core=(
                "会议室白板上贴满便签，每张写一个背叛者的'用户画像'，"
                "中间用箭头连成'信任衰减曲线'"
            ),
            personal_cost=(
                "每用一次产品思维拆解一个人，主角就会梦到自己前世坠楼的瞬间"
            ),
            why_new=(
                "先知确定性的爽+每次开挂都有可见代价；'同样重生者'的存在让金手指始终有对手"
            ),
            banned_patterns=[
                "前世记忆失准/蝴蝶效应稀释金手指（禁止削弱先知确定性）",
                "靠系统签到获得无敌奖励",
                "主角真实身份是隐退兵王/隐藏首富",
                "金手指无代价（每次开挂必须有反噬或暴露风险）",
            ],
            visual_anchor_prop="白板便签",
            visual_anchor_keywords=["便签", "白板", "用户画像", "A/B测试"],
        ),
        # === 算法时间轴卡点 ===
        pacing_cards=[
            PacingCard(
                label="3s_Hook",
                word_range=[0, 100],
                rule="动词+特写开局。禁止背景铺垫。必须在前100字内出现一个具体的感官冲击（坠落感/疼痛/重生的眩晕）",
                emotion="震惊/恐惧",
            ),
            PacingCard(
                label="15s_Retention",
                word_range=[300, 500],
                rule="爆出核心信息差——主角知道但其他人不知道的关键事实。这是留住读者的炸弹",
                emotion="掌控感/暗爽",
            ),
            PacingCard(
                label="Mini_Tension",
                word_range=[600, 800],
                rule="一次小规模紧张对峙或试探，主角不能暴露自己知道太多",
                emotion="紧张/压抑",
            ),
            PacingCard(
                label="Emotion_Dip",
                word_range=[1000, 1200],
                rule="情绪下压——回忆前世的痛苦/看到还活着的已故亲人/意识到代价",
                emotion="心痛/愤怒",
            ),
            PacingCard(
                label="50s_Cliffhanger",
                word_range=[1700, 2000],
                rule="断崖。必须在最后一句植入一个具体的未回答问题",
                cliffhanger_type=CliffhangerType.REVEAL,
                emotion="悬念/紧迫",
            ),
        ],
        template="rebirth-revenge",
        narrative_skeleton="命运逆转+身份落差",
        global_hook_density="high",
        themes=["复仇", "信任", "信息差", "代价"],
    )

    # === 角色卡 ===
    characters = [
        Character(
            id="char_pro",
            name="林越",
            aliases=["林总", "越哥"],
            role=CharacterRole.PROTAGONIST,
            appearance=Appearance(
                age=28, height="180cm", build="偏瘦但结实",
                hair="黑色短发，略有凌乱", eyes="深棕色，目光锐利",
                distinguishing="右手无名指有一道浅疤（前世割伤留下的，重生后还在）",
                clothing_default="白衬衫+黑色西裤，袖口总是卷到小臂",
            ),
            personality=Personality(
                ocean=OCEAN(openness=8, conscientiousness=9, extraversion=6,
                           agreeableness=4, neuroticism=3),
                speech_pattern="说话简短精准，喜欢用数据和逻辑。偶尔冒出互联网黑话（'这个需求优先级不高'）。前世的他话多热情，重生后变得克制",
                habits=["手指无意识敲桌面（像在敲键盘）", "看到人时习惯性分析对方的微表情"],
                fears=["再次被信任的人背叛", "改变太多导致蝴蝶效应害到无辜的人"],
                desires="保护这一世还在的人，让背叛者付出代价，但不想变成和他们一样的人",
            ),
            background=Background(
                origin="普通家庭，父母开小餐馆",
                education="985本科+MBA",
                key_event="前世：和大学室友周昊一起创业，公司估值过亿时被周昊和未婚妻苏晴联手架空",
                secret="重生者。拥有未来三年的记忆，但不确定蝴蝶效应会改变多少",
            ),
            abilities=Abilities(
                combat="普通人，不会打架",
                knowledge="顶级产品经理，擅长用户分析、商业模式设计、数据驱动决策",
                special="前世记忆（但随着蝴蝶效应会逐渐失准）",
            ),
            arc=CharacterArc(
                start="冷静克制，用产品经理思维分析每个变量。表面云淡风轻，内心充满对背叛者的恨意",
                midpoint="发现蝴蝶效应让很多事不再按前世剧本走，开始怀疑自己的记忆是否还可靠",
                end="学会了真正的信任，不再把所有人当用户画像分析。复仇不再是目的，守护才是",
                internal_conflict="Want: 让背叛者付出代价 vs Need: 不在复仇中迷失自己",
            ),
            state=CharacterState(
                alive=True, location="出租屋（创业初期的办公室兼住所）",
                health="健康但失眠（重生后反复梦到坠楼）",
                current_goal="确认重生时间节点，找到第一个可以利用的信息差",
            ),
        ),
        Character(
            id="char_ant",
            name="周昊",
            aliases=["昊哥", "周总"],
            role=CharacterRole.ANTAGONIST,
            appearance=Appearance(
                age=28, height="178cm", build="健壮",
                hair="黑色，打理得很整齐", eyes="棕色，笑起来很温和",
                distinguishing="左手戴一块浪琴表（前世是林越送的生日礼物）",
                clothing_default="休闲西装，永远干净得体",
            ),
            personality=Personality(
                ocean=OCEAN(openness=7, conscientiousness=8, extraversion=8,
                           agreeableness=3, neuroticism=4),
                speech_pattern="说话温和有理有据，擅长让人觉得他是站在你这边的。口头禅'咱们是一起的'",
                habits=["递名片时双手递", "和人握手时会多握一秒"],
                fears=["被人看穿真实目的", "失去已经到手的东西"],
                desires="绝对的控制权。不是为了钱，是为了证明自己比林越强",
            ),
            background=Background(
                origin="商人家庭，父亲生意失败后家道中落",
                education="985本科（和林越同班）",
                key_event="大三时父亲自杀，从此学会隐藏真实情绪，表面阳光内心阴暗",
                secret="从大三开始就在布局——和林越交好是为了利用他的产品能力",
            ),
            abilities=Abilities(
                combat="普通人",
                knowledge="擅长资本运作、人脉经营、政商关系",
                special="极强的情绪控制能力，能在任何场合表现出最合适的表情",
            ),
            arc=CharacterArc(
                start="表面是林越最好的兄弟和合伙人，暗中已经开始布局",
                midpoint="发现林越某些决策诡异精准，开始怀疑",
                end="被林越一步步拆解棋局，最终败露",
            ),
            state=CharacterState(
                alive=True, location="公司（和林越合租的创业办公室）",
                health="健康",
                current_goal="暗中接触林越的未婚妻苏晴，同时寻找投资方准备架空林越",
            ),
        ),
        Character(
            id="char_fem",
            name="苏晴",
            aliases=["晴晴", "苏小姐"],
            role=CharacterRole.ANTAGONIST,
            appearance=Appearance(
                age=26, height="168cm", build="纤细",
                hair="长发，常扎马尾", eyes="杏眼，笑起来弯弯的",
                distinguishing="右手腕一条细细的银手链（周昊送的，林越前世不知道）",
                clothing_default="简约风格，偏爱白色",
            ),
            personality=Personality(
                ocean=OCEAN(openness=6, conscientiousness=7, extraversion=7,
                           agreeableness=6, neuroticism=5),
                speech_pattern="说话温柔但有主见。不会直接反对，但会用'我觉得可以再想想'来表达异议",
                habits=["紧张时会摸手腕上的银手链"],
                fears=["被揭穿两面派", "失去现有的生活"],
                desires="安全感。选择周昊不是因为爱，是因为周昊给她的感觉更'稳'",
            ),
            arc=CharacterArc(
                start="林越的未婚妻，温柔体贴",
                midpoint="和周昊的秘密关系被林越发现",
                end="成为林越复仇计划中的关键变量",
            ),
            state=CharacterState(
                alive=True, location="自己的公寓",
                health="健康",
                current_goal="在林越和周昊之间维持平衡",
            ),
        ),
        Character(
            id="char_ally",
            name="陈叔",
            aliases=["陈叔", "老陈"],
            role=CharacterRole.SUPPORTING,
            appearance=Appearance(
                age=55, height="172cm", build="微胖",
                hair="花白", eyes="浑浊但精明",
                distinguishing="总是叼着一根没点的烟",
            ),
            personality=Personality(
                speech_pattern="说话直接粗犷，带点江湖气。'小子，你听叔一句'",
                habits=["思考时会把没点的烟转来转去"],
            ),
            background=Background(
                origin="林越父亲的老战友，做建材生意",
                key_event="前世在林越落难时借了50万，是唯一帮他的人",
            ),
            arc=CharacterArc(
                start="林越父亲的朋友，对林越有长辈式的关心",
                midpoint="发现林越的能力远超他的年龄应有的水平",
                end="成为林越最坚定的盟友",
            ),
            state=CharacterState(
                alive=True, location="建材城店铺",
                current_goal="经营生意",
            ),
        ),
    ]

    # === 世界观规则 ===
    world_rules = WorldRules(
        world_name="现代都市",
        genre="rebirth-revenge",
        setting={
            "time_period": "2023年（重生前）→ 2020年（重生后）",
            "geography": "一线城市，科技园区",
            "technology_level": "当代科技，无超自然元素",
        },
        rules=[
            "重生只携带记忆，不携带任何物理外挂（没有系统、没有异能）",
            "前世记忆 100% 灵验：关键节点（股价/赛事/背叛）全部可以踩点，先知确定性是本剧的爽感根基",
            "动用先知的代价：坠楼闪回剧痛 + 被同样重生/知情者察觉的风险，代价随使用次数递增",
            "信息差是最大武器，暴露重生者身份等于自杀——身份揭露型爽点靠'让对方自己撞上来'",
            "商业规则真实可信：融资、股权、对赌协议等必须符合现实逻辑",
        ],
        # === 因果律断言 ===
        causal_constraints=[
            "主角没有超能力，不能做普通人做不到的事（先知记忆除外）",
            "商业决策必须有合理的逻辑链，不能凭空变出资源",
            "角色的背叛动机必须有前因，不能'突然变坏'",
            "时间线必须自洽：2020年的事件不能引用2021年才发生的事",
        ],
        # === 反套路黑名单（只留执行类烂梗；市场验证的爽点镜头由 anti_cliche 预算制管理）===
        anti_cliche_blacklist=[
            "反派死于话多，主动告诉主角关键信息",
            "用巧合（恰好听到/恰好遇到）推进剧情",
            "顿悟式转折——'那一刻一切都变了'",
            "误会推动——不听解释转身就走",
            "隐世老人其实是绝世高手",
            "用大段回忆填充字数",
            "旁白式内心——'他的心中涌起万千感慨'",
        ],
    )

    return {
        "meta": meta,
        "characters": characters,
        "world_rules": world_rules,
    }
