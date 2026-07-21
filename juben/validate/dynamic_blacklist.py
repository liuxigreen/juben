"""
Dynamic Blacklist — 动态黑名单自动提取

从已生成章节中自动提取高频短语，注入下一章的禁用列表。
核心思想：事后检查 → 事前熔断。
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


# 需要检测的短语长度范围
MIN_PHRASE_LEN = 3
MAX_PHRASE_LEN = 12

# 高频阈值：出现N次以上视为高频
DEFAULT_FREQ_THRESHOLD = 2

# 已知的AI味句式（静态黑名单，作为种子）
SEED_BLACKLIST = [
    "嘴角微微抽了一下",
    "嘴角微微上扬",
    "嘴角勾起一抹笑",
    "嘴角抽搐了一下",
    "手指在键盘上顿了顿",
    "手指悬停在",
    "低声说",
    "喃喃自语",
    "这不对劲",
    "眼中闪过一丝光芒",
    "战意升腾",
    "倒吸一口凉气",
    "瞳孔剧烈收缩",
    "瞳孔骤缩",
    "不禁",
    "竟然",
    "居然",
    "仿佛",
    "好像",
    "似乎",
    "一瞬间",
    "那一刻",
    "就这样",
    "感觉到自己的",
    "脸色变得苍白",
    "嘴巴张了张",
    "想说什么，但又说不出来",
]


def extract_ngrams(text: str, n_range: tuple[int, int] = (3, 12)) -> list[str]:
    """
    从文本中提取n-gram短语。
    基于标点符号分句，然后提取滑动窗口短语。
    """
    # 按标点分句
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= n_range[0]]

    phrases = []
    for sent in sentences:
        # 滑动窗口提取
        for n in range(n_range[0], min(n_range[1] + 1, len(sent) + 1)):
            for i in range(len(sent) - n + 1):
                phrase = sent[i:i+n]
                # 过滤：必须包含中文，不能全是标点
                if re.search(r'[\u4e00-\u9fff]', phrase) and not re.match(r'^[^\w]+$', phrase):
                    phrases.append(phrase)

    return phrases


def analyze_chapters(
    chapter_texts: list[str],
    freq_threshold: int = DEFAULT_FREQ_THRESHOLD,
    n_range: tuple[int, int] = (MIN_PHRASE_LEN, MAX_PHRASE_LEN),
) -> dict[str, int]:
    """
    分析多章文本，提取高频短语。

    Returns:
        {phrase: count} 按频率降序排列
    """
    all_phrases = []
    for text in chapter_texts:
        phrases = extract_ngrams(text, n_range)
        all_phrases.extend(phrases)

    # 统计频率
    counter = Counter(all_phrases)

    # 过滤：只保留超过阈值的
    high_freq = {p: c for p, c in counter.items() if c >= freq_threshold}

    # 按频率降序
    sorted_phrases = dict(sorted(high_freq.items(), key=lambda x: -x[1]))

    return sorted_phrases


def build_dynamic_blacklist(
    chapter_texts: list[str],
    freq_threshold: int = DEFAULT_FREQ_THRESHOLD,
    include_seeds: bool = True,
) -> list[str]:
    """
    构建动态黑名单。

    Args:
        chapter_texts: 已生成章节的文本列表
        freq_threshold: 频率阈值
        include_seeds: 是否包含种子黑名单

    Returns:
        禁用短语列表
    """
    # 从文本中提取高频词
    high_freq = analyze_chapters(chapter_texts, freq_threshold)

    # 过滤掉太短的（可能是误匹配）
    dynamic_list = [p for p in high_freq.keys() if len(p) >= MIN_PHRASE_LEN]

    # 合并种子黑名单
    if include_seeds:
        combined = list(set(SEED_BLACKLIST + dynamic_list))
    else:
        combined = dynamic_list

    return combined


def scan_chapter_for_blacklist(
    chapter_text: str,
    blacklist: list[str],
) -> list[dict]:
    """
    扫描单章文本，检测黑名单短语。

    Returns:
        [{phrase, count, lines}] 违规列表
    """
    violations = []
    lines = chapter_text.split('\n')

    for phrase in blacklist:
        count = chapter_text.count(phrase)
        if count > 0:
            # 找出所在行
            found_lines = []
            for i, line in enumerate(lines, 1):
                if phrase in line:
                    found_lines.append(i)

            violations.append({
                "phrase": phrase,
                "count": count,
                "lines": found_lines[:5],  # 最多显示5行
            })

    return violations


def save_blacklist(blacklist: list[str], path: str | Path):
    """保存黑名单到文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(blacklist), encoding='utf-8')


def load_blacklist(path: str | Path) -> list[str]:
    """从文件加载黑名单"""
    path = Path(path)
    if not path.exists():
        return SEED_BLACKLIST.copy()
    return [line.strip() for line in path.read_text(encoding='utf-8').split('\n') if line.strip()]


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python dynamic_blacklist.py <project_dir> [--threshold N]")
        sys.exit(1)

    project_dir = Path(sys.argv[1])
    threshold = DEFAULT_FREQ_THRESHOLD

    if "--threshold" in sys.argv:
        idx = sys.argv.index("--threshold")
        threshold = int(sys.argv[idx + 1])

    # 读取所有章节
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        print(f"Error: {chapters_dir} not found")
        sys.exit(1)

    chapter_texts = []
    for f in sorted(chapters_dir.glob("ch*.txt")):
        chapter_texts.append(f.read_text(encoding='utf-8'))

    print(f"分析 {len(chapter_texts)} 个章节...")

    # 构建动态黑名单
    blacklist = build_dynamic_blacklist(chapter_texts, threshold)
    print(f"动态黑名单: {len(blacklist)} 个短语")

    # 显示高频词
    high_freq = analyze_chapters(chapter_texts, threshold)
    print(f"\n高频短语 (阈值>={threshold}):")
    for phrase, count in list(high_freq.items())[:20]:
        print(f"  '{phrase}': {count}次")

    # 保存
    output_path = project_dir / "dynamic_blacklist.txt"
    save_blacklist(blacklist, output_path)
    print(f"\n已保存到: {output_path}")
