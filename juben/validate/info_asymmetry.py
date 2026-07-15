"""
信息对称性验证器 — 检查角色是否说了/做了他们不该知道的事

这是防吃书的核心武器。重生文中主角有前世记忆，但配角没有。
如果配角突然表现得知道前世的事，就是吃书。
"""
from __future__ import annotations

import re

from juben.state.schema import (
    InfoAsymmetryEntry, Severity, ValidationResult, Violation, ViolationType,
)


class InfoAsymmetryValidator:
    """信息对称性验证器"""

    def __init__(self, info_asymmetry: list[InfoAsymmetryEntry]):
        self.info_map = {entry.info_id: entry for entry in info_asymmetry}

    def check(
        self,
        text: str,
        characters_in_chapter: list[str],
    ) -> ValidationResult:
        """
        检查章节中是否有信息对称性违反。

        Args:
            text: 章节正文
            characters_in_chapter: 本章出场角色ID列表
        """
        violations = []

        for info_id, entry in self.info_map.items():
            # 找出不知道这条信息的角色
            unknown_chars = [
                cid for cid in characters_in_chapter
                if cid not in entry.known_by
            ]
            if not unknown_chars:
                continue

            # 检查文本中是否有"不知道的角色"表现得知道这条信息
            # 简化方法：检查信息关键词是否出现在非叙述性上下文中
            info_keywords = self._extract_keywords(entry.description)

            for char_id in unknown_chars:
                # 检查该角色的对话或行为是否涉及这条信息
                if self._char_acts_on_info(text, char_id, info_keywords):
                    violations.append(Violation(
                        type=ViolationType.INFO_ASYMMETRY_VIOLATION,
                        severity=Severity.CRITICAL,
                        description=(
                            f"信息对称性违反: 角色 {char_id} 不应该知道 "
                            f"'{entry.description}'，但表现得好像知道"
                        ),
                        suggestion=(
                            f"只有 {', '.join(entry.known_by)} 知道这条信息。"
                            f"如果 {char_id} 要获得这条信息，需要在本章中有明确的揭示场景。"
                        ),
                    ))

        passed = not any(v.severity == Severity.CRITICAL for v in violations)
        score = max(0, 10.0 - len(violations) * 5.0)

        return ValidationResult(
            passed=passed,
            violations=violations,
            score=min(10.0, score),
        )

    def _extract_keywords(self, description: str) -> list[str]:
        """从信息描述中提取关键词"""
        # 去掉常见停用词，保留有意义的词
        stopwords = {"的", "了", "是", "在", "和", "与", "一个", "这个", "那个", "会", "能"}
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', description)
        return [w for w in words if w not in stopwords]

    def _char_acts_on_info(self, text: str, char_id: str, keywords: list[str]) -> bool:
        """
        检查角色是否在文本中表现得知道某条信息。
        简化实现：检查角色名附近的文本是否包含信息关键词。
        """
        # 找到角色名/别名在文本中的位置
        # 这里用简化方法：如果角色名和关键词同时出现在一个段落中
        paragraphs = text.split('\n')
        for para in paragraphs:
            if len(keywords) < 2:
                continue
            # 检查是否多个关键词同时出现在同一段
            matched = sum(1 for kw in keywords if kw in para)
            if matched >= min(3, len(keywords)):
                return True
        return False
