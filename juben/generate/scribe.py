"""
Scribe — 正文生成器

MVP阶段：把拼装好的prompt输出到stdout或文件，让用户手动投喂LLM。
后续：接入API直接调用。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from juben.extract import ContextExtractor
from juben.state.manager import StateManager
from juben.state.schema import ChapterOutline


class Scribe:
    """正文生成器 — 拼装prompt，输出到文件"""

    def __init__(self, manager: StateManager):
        self.mgr = manager
        self.extractor = ContextExtractor(manager)

    def generate_prompt(
        self,
        chapter_num: int,
        outline: Optional[ChapterOutline] = None,
        character_ids: Optional[list[str]] = None,
    ) -> str:
        """
        生成Scribe的完整prompt。

        Args:
            chapter_num: 章节序号
            outline: 分镜细纲（可选，Architect的输出）
            character_ids: 出场角色ID（可选，自动推断）

        Returns:
            完整prompt字符串，可直接投喂给任何LLM
        """
        context = self.extractor.extract_chapter_context(
            chapter_num, character_ids
        )
        return self.extractor.build_scribe_prompt(context, outline)

    def save_prompt(self, chapter_num: int, prompt: str) -> Path:
        """保存prompt到outlines目录"""
        prompt_dir = self.mgr.project_dir / "outlines"
        prompt_dir.mkdir(exist_ok=True)
        path = prompt_dir / f"prompt_{chapter_num:03d}.md"
        path.write_text(prompt, encoding="utf-8")
        return path

    def save_chapter(self, chapter_num: int, text: str) -> Path:
        """保存生成的章节到chapters目录"""
        chapter_dir = self.mgr.project_dir / "chapters"
        chapter_dir.mkdir(exist_ok=True)
        path = chapter_dir / f"{chapter_num:03d}.md"
        path.write_text(text, encoding="utf-8")
        return path
