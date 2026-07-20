"""
Five-Dimension Review — 五维评分系统
参考0xsline/short-drama的/review五维打分

5个维度，每个10分，满分50分：
1. 节奏（Rhythm）：场景节奏、信息密度、前30秒、结尾钩子
2. 爽感（Satisfaction）：爽感元素密度、情绪高潮
3. 台词（Dialogue）：角色语言特征、记忆点台词
4. 格式（Format）：标准化镜头标注、音效标注、场景标题
5. 一致性（Consistency）：角色设定对齐、剧情连续性、伏笔
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DimensionScore:
    """单维度评分"""
    name: str
    name_en: str
    score: float  # 0-10
    max_score: float = 10.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    """五维评分结果"""
    rhythm: DimensionScore
    satisfaction: DimensionScore
    dialogue: DimensionScore
    format_score: DimensionScore
    consistency: DimensionScore
    total_score: float = 0.0
    grade: str = ""
    passed: bool = False

    def __post_init__(self):
        self.total_score = (
            self.rhythm.score +
            self.satisfaction.score +
            self.dialogue.score +
            self.format_score.score +
            self.consistency.score
        )
        if self.total_score >= 45:
            self.grade = "优秀"
            self.passed = True
        elif self.total_score >= 38:
            self.grade = "良好"
            self.passed = True
        elif self.total_score >= 30:
            self.grade = "及格"
            self.passed = True
        else:
            self.grade = "不及格"
            self.passed = False


class FiveDimensionReviewer:
    """五维评分器"""

    def review(self, text: str, episode_number: int = 1) -> ReviewResult:
        """
        对文本进行五维评分。
        """
        rhythm = self._check_rhythm(text)
        satisfaction = self._check_satisfaction(text)
        dialogue = self._check_dialogue(text)
        format_score = self._check_format(text)
        consistency = self._check_consistency(text)

        return ReviewResult(
            rhythm=rhythm,
            satisfaction=satisfaction,
            dialogue=dialogue,
            format_score=format_score,
            consistency=consistency,
        )

    def _check_rhythm(self, text: str) -> DimensionScore:
        """检查节奏"""
        score = 10.0
        issues = []
        suggestions = []

        # 检查是否有5个镜头块
        shot_count = text.count("## 镜头")
        if shot_count < 5:
            score -= 2.0
            issues.append(f"镜头块不足5个（当前{shot_count}个）")
            suggestions.append("确保每个节奏卡点都有对应的镜头块")

        # 检查是否有感官冲击（前100字）
        first_100 = text[:100]
        sensory_words = ["血", "碎", "砸", "刺", "疼", "冷", "热", "黑", "亮", "响"]
        if not any(w in first_100 for w in sensory_words):
            score -= 1.5
            issues.append("前100字缺少感官冲击")
            suggestions.append("开局用具体感官词（血/碎/砸/刺）")

        # 检查是否有断崖钩子（最后一段）
        last_200 = text[-200:]
        cliffhanger_words = ["？", "突然", "猛地", "秘密", "真相", "最后一"]
        if not any(w in last_200 for w in cliffhanger_words):
            score -= 1.5
            issues.append("结尾缺少断崖钩子")
            suggestions.append("最后一个镜头必须卡在冲突前一秒")

        return DimensionScore(
            name="节奏",
            name_en="Rhythm",
            score=max(0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _check_satisfaction(self, text: str) -> DimensionScore:
        """检查爽感"""
        score = 10.0
        issues = []
        suggestions = []

        # 检查爽感元素
        satisfaction_words = ["打脸", "碾压", "逆袭", "跪", "求", "震惊", "愣住", "不敢相信"]
        satisfaction_count = sum(1 for w in satisfaction_words if w in text)
        if satisfaction_count < 2:
            score -= 2.0
            issues.append(f"爽感元素不足（当前{satisfaction_count}个）")
            suggestions.append("增加打脸/碾压/逆袭等爽感场景")

        # 检查情绪高潮
        emotion_words = ["怒", "恨", "怕", "哭", "笑", "惊", "冷", "热"]
        emotion_count = sum(1 for w in emotion_words if w in text)
        if emotion_count < 3:
            score -= 1.5
            issues.append("情绪高潮不足")
            suggestions.append("增加情绪爆发点")

        return DimensionScore(
            name="爽感",
            name_en="Satisfaction",
            score=max(0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _check_dialogue(self, text: str) -> DimensionScore:
        """检查台词"""
        score = 10.0
        issues = []
        suggestions = []

        # 检查台词数量
        import re
        dialogue_count = len(re.findall(r'["「](.*?)["」]', text))
        if dialogue_count < 3:
            score -= 1.5
            issues.append(f"台词不足（当前{dialogue_count}句）")
            suggestions.append("每个镜头块至少1句台词")

        # 检查台词是否超过3句/镜头
        shot_blocks = text.split("## 镜头")
        for i, block in enumerate(shot_blocks[1:], 1):
            block_dialogue = len(re.findall(r'["「](.*?)["」]', block))
            if block_dialogue > 3:
                score -= 1.0
                issues.append(f"镜头{i}台词过多（{block_dialogue}句）")
                suggestions.append(f"镜头{i}台词应≤3句")

        # 检查是否有记忆点台词
        memorable_patterns = ["……", "！", "？", "你以为", "其实", "真相是"]
        if not any(p in text for p in memorable_patterns):
            score -= 1.0
            issues.append("缺少记忆点台词")
            suggestions.append("增加有冲击力的台词（反问/惊叹/揭秘）")

        return DimensionScore(
            name="台词",
            name_en="Dialogue",
            score=max(0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _check_format(self, text: str) -> DimensionScore:
        """检查格式"""
        score = 10.0
        issues = []
        suggestions = []

        # 检查镜头标注格式
        import re
        shot_pattern = r'## 镜头 \d+ \| \w+'
        if not re.search(shot_pattern, text):
            score -= 3.0
            issues.append("缺少标准镜头标注格式")
            suggestions.append("使用 ## 镜头 N | 标签 格式")

        # 检查4维度标签
        required_fields = ["画面机位", "视觉动作", "场景光影", "角色台词"]
        for field in required_fields:
            if f"【{field}】" not in text:
                score -= 1.5
                issues.append(f"缺少【{field}】字段")
                suggestions.append(f"每个镜头块必须包含【{field}】")

        # 检查景别标签
        shot_types = ["[CU]", "[MCU]", "[MS]", "[WS]"]
        if not any(st in text for st in shot_types):
            score -= 1.0
            issues.append("缺少景别标签")
            suggestions.append("使用[CU]/[MCU]/[MS]/[WS]标签")

        return DimensionScore(
            name="格式",
            name_en="Format",
            score=max(0, score),
            issues=issues,
            suggestions=suggestions,
        )

    def _check_consistency(self, text: str) -> DimensionScore:
        """检查一致性"""
        score = 10.0
        issues = []
        suggestions = []

        # 检查是否有心理描写（非物理动作）
        psychology_words = ["感到", "觉得", "认为", "意识到", "心中暗想", "内心"]
        psychology_count = sum(1 for w in psychology_words if w in text)
        if psychology_count > 0:
            score -= 1.0 * psychology_count
            issues.append(f"发现{psychology_count}处心理描写（镜头拍不出来）")
            suggestions.append("用物理动作替代心理描写")

        # 检查是否有收尾句式
        ending_words = ["一切归于平静", "闭上眼睛睡了", "新世界开始了", "她终于可以休息了"]
        for w in ending_words:
            if w in text:
                score -= 2.0
                issues.append(f"发现禁止的收尾句式：{w}")
                suggestions.append("禁止使用情绪升华与收尾句式")

        return DimensionScore(
            name="一致性",
            name_en="Consistency",
            score=max(0, score),
            issues=issues,
            suggestions=suggestions,
        )
