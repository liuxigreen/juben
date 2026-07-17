"""
上下文提取器 — 从JSON状态中切出第N章需要的上下文片段

核心职责：
1. 只提取本章出场角色的当前状态（不是全部角色）
2. 只提取本章适用的世界规则
3. 提取前章结局和未解决伏笔
4. 提取信息对称性矩阵（谁知道什么）
5. 拼装成高压prompt给LLM
"""
from __future__ import annotations

import json
from typing import Optional

from juben.state.manager import StateManager
from juben.state.schema import (
    Character, CharacterRole, ChapterOutline, PlotThreadStatus,
    StoryMeta, WorldRules,
)


class ContextExtractor:
    """从状态文件中提取第N章的上下文切片"""

    def __init__(self, manager: StateManager):
        self.mgr = manager

    def extract_chapter_context(
        self,
        chapter_num: int,
        character_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        提取第chapter_num章的完整上下文。

        Args:
            chapter_num: 章节序号
            character_ids: 出场角色ID列表。None则自动推断。

        Returns:
            dict，包含所有注入LLM的硬事实
        """
        meta = self.mgr.load_meta()
        characters = self.mgr.load_characters()
        world = self.mgr.load_world_rules()
        timeline = self.mgr.load_timeline()
        relationships = self.mgr.load_relationships()
        plot_threads = self.mgr.load_plot_threads()

        # 确定出场角色
        if character_ids is None:
            relevant_chars = self._infer_characters(chapter_num, characters, plot_threads.threads)
        else:
            relevant_chars = [c for c in characters if c.id in character_ids]

        # 角色卡（只给当前状态，不给全量）
        char_cards = []
        for c in relevant_chars:
            char_cards.append({
                "id": c.id,
                "name": c.name,
                "role": c.role.value,
                "personality": {
                    "speech_pattern": c.personality.speech_pattern,
                    "habits": c.personality.habits,
                    "fears": c.personality.fears,
                    "desires": c.personality.desires,
                },
                "abilities_special": c.abilities.special,
                "state": c.state.model_dump(),
                "arc_current": self._get_arc_phase(c, chapter_num, meta.target_chapters),
            })

        # 前章结局
        prev_ending = self._get_prev_chapter_ending(chapter_num)

        # 未解决伏笔
        open_threads = [
            {
                "id": t.id,
                "description": t.description,
                "planted_chapter": t.planted_chapter,
                "importance": t.importance,
            }
            for t in plot_threads.threads
            if t.status in (PlotThreadStatus.OPEN, PlotThreadStatus.PLANTED)
        ]

        # 信息对称性（本章出场角色知道什么）
        char_ids_here = {c.id for c in relevant_chars}
        info_matrix = [
            {
                "info": info.description,
                "known_by": [cid for cid in info.known_by if cid in char_ids_here],
                "unknown_to": [cid for cid in char_ids_here if cid not in info.known_by],
                "is_protagonist_advantage": info.is_protagonist_advantage,
            }
            for info in relationships.info_asymmetry
            if any(cid in char_ids_here for cid in info.known_by)
        ]

        # 世界观规则（只给相关的）
        relevant_rules = self._filter_relevant_rules(world, meta.genre, chapter_num)

        # 反套路黑名单
        anti_cliche = world.anti_cliche_blacklist

        # 因果限制
        causal = world.causal_constraints

        # 算法时间轴卡点
        pacing = [pc.model_dump() for pc in meta.pacing_cards]

        return {
            "chapter_num": chapter_num,
            "premise": meta.premise,
            "genre": meta.genre,
            "disruption_variable": meta.disruption_variable,
            "narrative_skeleton": meta.narrative_skeleton,
            "pov": meta.pov,
            "target_word_count": meta.target_word_count_per_chapter,
            "character_cards": char_cards,
            "world_rules": relevant_rules,
            "causal_constraints": causal,
            "anti_cliche_blacklist": anti_cliche,
            "prev_chapter_ending": prev_ending,
            "open_plot_threads": open_threads,
            "info_asymmetry": info_matrix,
            "pacing_cards": pacing,
            "timeline_recent": self._get_recent_events(timeline, chapter_num, limit=5),
        }

    def build_scribe_prompt(self, context: dict, outline: Optional[ChapterOutline] = None) -> str:
        """
        把上下文切片拼装成Scribe的高压prompt。
        这是整个系统的核心拼装逻辑。
        """
        ctx = context
        ch = ctx["chapter_num"]

        parts = []

        # === 系统角色 ===
        parts.append(
            "你是一个专业的小说作者。基于以下Python注入的硬事实，撰写第"
            f"{ch}章正文。所有违反硬事实的内容都会被Guardian无情熔断。\n"
        )

        # === 硬事实区（Python层，不可违反）===
        parts.append("## 硬事实（100%不可违反）\n")

        parts.append(f"### 故事前提\n{ctx['premise']}\n")

        if ctx["disruption_variable"]:
            parts.append(
                f"### 意外变量（必须作为核心金手指使用）\n"
                f"{ctx['disruption_variable']}\n"
            )

        # 角色卡
        parts.append("### 出场角色当前状态")
        for card in ctx["character_cards"]:
            parts.append(f"\n**{card['name']}**（{card['id']}，{card['role']}）")
            parts.append(f"- 状态: {json.dumps(card['state'], ensure_ascii=False)}")
            parts.append(f"- 语言指纹: {card['personality']['speech_pattern']}")
            parts.append(f"- 当前弧线: {card['arc_current']}")
            if card["abilities_special"]:
                parts.append(f"- 特殊能力: {card['abilities_special']}")

        # 信息对称性
        if ctx["info_asymmetry"]:
            parts.append("\n### 信息对称性矩阵（谁能说什么不能说什么）")
            for info in ctx["info_asymmetry"]:
                know = ", ".join(info["known_by"]) or "无"
                unk = ", ".join(info["unknown_to"]) or "无"
                adv = " ⚡主角先知优势" if info["is_protagonist_advantage"] else ""
                parts.append(f"- 【{info['info']}】知道: {know} | 不知道: {unk}{adv}")

        # 世界观规则
        if ctx["world_rules"]:
            parts.append("\n### 世界观规则")
            for r in ctx["world_rules"]:
                parts.append(f"- {r}")

        # 因果限制
        if ctx["causal_constraints"]:
            parts.append("\n### 因果律断言（绝对不可违反）")
            for c in ctx["causal_constraints"]:
                parts.append(f"- ⛔ {c}")

        # 前章结局
        if ctx["prev_chapter_ending"]:
            parts.append(f"\n### 前章最后一段（衔接用）\n{ctx['prev_chapter_ending']}")

        # 未解决伏笔
        if ctx["open_plot_threads"]:
            parts.append("\n### 未解决伏笔（可选择在本章推进）")
            for t in ctx["open_plot_threads"]:
                parts.append(f"- [{t['id']}] {t['description']}（第{t['planted_chapter']}章埋下）")

        # === 创作纪律 ===
        parts.append("\n## 创作纪律（违反即熔断）\n")
        parts.append("1. 严禁概述性长句。所有冲突和情绪必须通过具体对白和特写动作表现（Show, Don't Tell）。")
        parts.append("2. 第一句话立刻切入核心冲突，禁止大段背景铺垫。前100字必须包含动词+特写感官细节。")
        parts.append("3. 每400字经历一次[情绪下压→动作反弹]的小闭环。")
        parts.append(
            "4. 绝对禁用词: quietly, deeply, delve, tapestry, serves as, "
            "\"It's not X — it's Y\", \"little did she know\""
        )
        parts.append("5. 每个场景至少包含3种感官描写（视觉/听觉/触觉/嗅觉）。")
        parts.append("6. 对话必须反映角色个性（参考上方语言指纹）。")
        parts.append(f"7. 保持{ctx['pov']}视角一致。")

        # === 负面模板（告诉你什么是错的）===
        parts.append("\n## ⛔ 负面模板（以下是错误示例，绝对不要这样写）\n")
        parts.append("""
### ❌ 错误1：NPC嘴炮式对话
沈渡说："三年前，你姐姐查的那个案子，牵扯到了太子。"
沈渡又说："当时证人翻供，是因为有人威胁了他的家人。"
沈渡继续说："而那个威胁的人，就是我安排的。"

→ 问题：一个NPC连续说3句以上，每句都是"告诉你一个信息"。这是解说员，不是角色。
→ 正确：把信息拆碎，嵌入动作/冲突/感官细节中。沈渡不应该"告诉你"，而应该"在某个动作中不小心透露"。

### ❌ 错误2：结尾复读"继续查"
"她收起证据，转身往外走。案子还没完，还得继续查。"
"她把报告放回抽屉。真相还没浮出水面，她得继续查下去。"

→ 问题：两章结尾都是"继续查"，情绪和动作完全重复。
→ 正确：每章结尾必须有一个独特的感官意象（一个声音/一个画面/一个触觉），让读者记住这一章。

### ❌ 错误3：信息倾倒式独白
"'三年前...'沈渡的声音很轻。'太子在东宫设宴...席间有人中毒...'"
"'后来呢？'顾昭追问。"
"'后来证人翻供。'沈渡说。'因为有人威胁了他的家人。'"

→ 问题：连续4段都是对话推进，没有任何动作/环境/感官描写。像在读剧本。
→ 正确：每2段对话后必须插入1段动作/环境/感官描写。对话是手段，不是目的。

### ❌ 错误4：时间平移（跳过已知信息）
"三年前的那个夜晚，东宫灯火通明..."
"案发当天，顾昭正在值夜..."

→ 问题：用"三年前"开头，直接跳到过去。这是偷懒的写法。
→ 正确：如果必须回忆，用"沈渡的手指停在某一行"这种具体动作触发，而不是直接跳时间。

### ❌ 错误5：概述性情绪描写
"顾昭感到一阵心痛。"
"沈渡的眼中闪过一丝复杂的情绪。"

→ 问题：告诉读者"他很难过"，而不是展示。
→ 正确："顾昭的手指在案卷边缘收紧，指甲陷进纸里。" — 用动作暗示情绪。
""")


        # === 反套路黑名单 ===
        if ctx["anti_cliche_blacklist"]:
            parts.append("\n## ⛔ 反套路黑名单（触发即判定失败）")
            for i, c in enumerate(ctx["anti_cliche_blacklist"], 1):
                parts.append(f"{i}. {c}")

        # === 算法时间轴卡点 ===
        if ctx["pacing_cards"]:
            parts.append("\n## 算法时间轴卡点（必须严格遵守）")
            for card in ctx["pacing_cards"]:
                parts.append(
                    f"- [{card['label']}] 第{card['word_range'][0]}-{card['word_range'][1]}字: "
                    f"{card['rule']}"
                )

        # === 分镜细纲（如果有）===
        if outline:
            parts.append("\n## 分镜细纲（按此结构创作）")
            for scene in outline.scenes:
                parts.append(
                    f"\n### 分镜{scene.scene_id} [{scene.pacing_label}] "
                    f"({scene.word_range[0]}-{scene.word_range[1]}字)"
                )
                parts.append(f"- 地点: {scene.location} | 时间: {scene.time}")
                parts.append(f"- 冲突: {scene.conflict}")
                parts.append(f"- 情绪: {scene.emotion_start} → {scene.emotion_end}")
                parts.append(f"- 关键动作: {scene.key_action}")
                parts.append(f"- 感官细节: {', '.join(scene.sensory_details)}")

            parts.append(f"\n### 断崖")
            parts.append(f"- 类型: {outline.chapter_hook.type.value}")
            parts.append(f"- 未回答问题: {outline.chapter_hook.unanswered_question}")

        # === 输出要求 ===
        parts.append(f"\n## 输出\n直接输出正文，目标字数: {ctx['target_word_count']}字。不要包含任何元数据。")

        return "\n".join(parts)

    # ============================================================
    # 内部方法
    # ============================================================

    def _infer_characters(self, chapter_num, characters, plot_threads):
        """推断本章可能出场的角色"""
        # 主角+反派必定出场
        core = [
            c for c in characters
            if c.role in (CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST)
        ]
        # 最近出场过的角色
        recent = [
            c for c in characters
            if c.state.last_appeared and c.state.last_appeared >= chapter_num - 3
        ]
        # 合并去重
        seen = set()
        result = []
        for c in core + recent:
            if c.id not in seen:
                seen.add(c.id)
                result.append(c)
        return result

    def _get_arc_phase(self, char: Character, chapter_num: int, total: int) -> str:
        """判断角色当前处于弧线的哪个阶段"""
        if total == 0:
            return char.arc.start
        ratio = chapter_num / total
        if ratio < 0.33:
            return char.arc.start
        elif ratio < 0.66:
            return char.arc.midpoint
        else:
            return char.arc.end

    def _get_prev_chapter_ending(self, chapter_num: int) -> str:
        """读取前一章的最后200字"""
        if chapter_num <= 1:
            return ""
        prev_path = self.mgr.project_dir / "chapters" / f"{chapter_num - 1:03d}.md"
        if not prev_path.exists():
            return ""
        text = prev_path.read_text(encoding="utf-8")
        # 取最后200字
        lines = text.strip().split("\n")
        # 跳过元数据行（以-开头的）
        content_lines = []
        for line in reversed(lines):
            if line.startswith("-") or line.startswith("<!--") or line.startswith("#"):
                break
            content_lines.insert(0, line)
        ending = "\n".join(content_lines)
        if len(ending) > 200:
            ending = ending[-200:]
        return ending

    def _filter_relevant_rules(self, world: WorldRules, genre: str, chapter_num: int) -> list[str]:
        """过滤出本章相关的世界规则"""
        rules = list(world.rules)
        # 加入setting中的关键信息
        if world.setting:
            for k, v in world.setting.items():
                if isinstance(v, str) and v:
                    rules.append(f"{k}: {v}")
        # 加入力量体系规则
        if world.power_system and "rules" in world.power_system:
            rules.extend(world.power_system["rules"])
        return rules

    def _get_recent_events(self, timeline, chapter_num: int, limit: int = 5) -> list[dict]:
        """获取最近的事件"""
        events = [
            e for e in timeline.events
            if e.chapter < chapter_num
        ]
        events.sort(key=lambda e: e.chapter, reverse=True)
        return [
            {
                "chapter": e.chapter,
                "description": e.description,
                "type": e.type,
            }
            for e in events[:limit]
        ]
