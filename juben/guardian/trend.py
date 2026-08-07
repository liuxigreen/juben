"""
Quality Trend Detector — 跨章质量趋势检测（v1）

目的: 解决"单章质量有gate但跨章衰减无预警"问题。
30章神算子证明: 单章9.0+掩盖了ch28→ch29→ch30→ch31的衰减趋势,
直到ch32 14万字复读才暴露。

输入: 最近N章的 {num, text, audit_score, auto_fix} 列表
输出: 'GREEN' | 'YELLOW' | 'RED'

规则(可调):
  GREEN: 正常
  YELLOW: 任意一条:
    - 连续3章 audit_score 下降
    - 连续3章 auto_fix=True
    - 最近2章 lexical_overlap(最后200字) > 0.30
  RED: 任意一条:
    - 连续2章 lexical_overlap > 0.35
    - 连续5章 auto_fix=True
    - auto_fix=True章节占比 >= 60% (近5章)
"""
from __future__ import annotations

import re
import json
import logging
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)


def _lexical_overlap(text1: str, text2: str, n: int = 50) -> float:
    """
    两段文本的词汇重叠度。提取最后N个字符,比较top词频的重叠率。
    """
    def get_words(t: str) -> Counter:
        # 简单分词: 中文字符按2字切分,英文按空格
        words = re.findall(r'[\u4e00-\u9fff]{2,}', t[-200:])
        words += re.findall(r'[a-zA-Z]+', t[-200:])
        return Counter(words)

    w1 = get_words(text1)
    w2 = get_words(text2)
    if not w1 or not w2:
        return 0.0
    common = sum((w1 & w2).values())
    total = sum(w1.values()) + sum(w2.values())
    return 2 * common / total if total else 0.0


def detect_quality_trend(
    chapters: list[dict],
    overlap_window: int = 200,
    yellow_overlap: float = 0.30,
    red_overlap: float = 0.35,
) -> str:
    """
    输入: chapters = [{"num": 1, "text": "...", "score": 9.5, "auto_fix": False}, ...]
    返回: "GREEN" / "YELLOW" / "RED"
    """
    if not chapters:
        return "GREEN"

    n = len(chapters)
    severity = "GREEN"

    # === 规则1: 连续auto_fix ===
    auto_fix_streak = 0
    max_auto_fix_streak = 0
    for c in chapters:
        if c.get("auto_fix", False):
            auto_fix_streak += 1
            max_auto_fix_streak = max(max_auto_fix_streak, auto_fix_streak)
        else:
            auto_fix_streak = 0
    if max_auto_fix_streak >= 5:
        return "RED"
    if max_auto_fix_streak >= 3:
        severity = "YELLOW"

    # === 规则2: auto_fix占比(近5章) ===
    recent5 = chapters[-5:]
    if len(recent5) >= 3:
        af_ratio = sum(1 for c in recent5 if c.get("auto_fix", False)) / len(recent5)
        if af_ratio >= 0.6:
            return "RED"

    # === 规则3: 词汇重叠度(复读检测) ===
    if n >= 2:
        # 比较最近两章的尾部
        recent_pair_overlap = _lexical_overlap(
            chapters[-1].get("text", ""),
            chapters[-2].get("text", ""),
        )
        if recent_pair_overlap > red_overlap:
            return "RED"
        if recent_pair_overlap > yellow_overlap and severity == "GREEN":
            severity = "YELLOW"

        # 比较最近3章的连续重叠(3章循环复读)
        if n >= 3:
            for i in range(n - 2):
                ov = _lexical_overlap(
                    chapters[i].get("text", ""),
                    chapters[i + 1].get("text", ""),
                )
                if ov > red_overlap:
                    return "RED"

    # === 规则4: score持续下降 ===
    scores = [c.get("score") for c in chapters if c.get("score") is not None]
    if len(scores) >= 4:
        # 检查最近4章是否单调下降
        declining = all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))
        if declining and scores[0] is not None and scores[-1] is not None and scores[-1] < scores[0] - 0.5:
            severity = "YELLOW" if severity == "GREEN" else severity

    return severity


def load_chapter_audit_history(project_dir: Path) -> list[dict]:
    """
    从项目的 reports/ 目录加载历史audit分数。
    格式: reports/chapter_XXX_audit.json 或 reports/audit_summary.json
    """
    project_dir = Path(project_dir)
    history = []

    # 方法1: 读取每个chapters/*.md的commit记录
    # 简单方案: 读取curator_state.json
    curator_file = project_dir / "curator_state.json"
    if curator_file.exists():
        try:
            data = json.loads(curator_file.read_text(encoding="utf-8"))
            for ch in data.get("chapters", []):
                history.append({
                    "num": ch.get("chapter_num"),
                    "text": "",  # curator不存原文
                    "auto_fix": False,
                })
        except Exception as e:
            logger.debug(f"读取curator_state.json失败: {e}")

    # 方法2: 直接从reports加载
    reports_dir = project_dir / "reports"
    if reports_dir.exists():
        for p in sorted(reports_dir.glob("ch*_audit.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                history.append({
                    "num": data.get("chapter_num"),
                    "score": data.get("overall_score"),
                    "auto_fix": data.get("auto_fix", False),
                    "text": "",
                })
            except Exception:
                pass

    return history


def detect_trend_from_project(project_dir: Path) -> str:
    """
    一站式: 从项目目录直接检测趋势。
    自动加载chapters/*.md的文本 + reports的audit分数。
    """
    project_dir = Path(project_dir)
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        return "GREEN"

    chapters = []
    for p in sorted(chapters_dir.glob("*.md")):
        try:
            num = int(p.stem)
            text = p.read_text(encoding="utf-8")
            chapters.append({
                "num": num,
                "text": text,
                "score": None,
                "auto_fix": False,
            })
        except (ValueError, OSError):
            pass

    # 尝试从reports加载分数
    audit_history = load_chapter_audit_history(project_dir)
    score_map = {h["num"]: h.get("score") for h in audit_history if h.get("score") is not None}
    for c in chapters:
        if c["num"] in score_map:
            c["score"] = score_map[c["num"]]

    return detect_quality_trend(chapters)
