"""
AI味检测器 — 静态种子 + 正则模式匹配

核心思路：AI味是固定句式范式，不是统计频率。
用精确匹配 + 正则模式，零误杀。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# ============================================================
# 1. 精确匹配 — 已验证的AI味短语（27个）
# ============================================================

SEED_BLACKLIST = [
    # 嘴角系列
    "嘴角微微抽了一下",
    "嘴角微微上扬",
    "嘴角勾起一抹笑",
    "嘴角抽搐了一下",
    # 手指系列
    "手指在键盘上顿了顿",
    "手指悬停在",
    # 声音系列
    "低声说",
    "喃喃自语",
    # 判断系列
    "这不对劲",
    # 眼神系列
    "眼中闪过一丝光芒",
    "眼睛里闪过一丝光芒",
    # 情绪系列
    "战意升腾",
    "倒吸一口凉气",
    "瞳孔剧烈收缩",
    "瞳孔骤缩",
    # 副词系列
    "不禁",
    "竟然",
    "居然",
    "仿佛",
    "好像",
    "似乎",
    "一瞬间",
    "那一刻",
    "就这样",
    # 身体系列
    "感觉到自己的",
    "感觉到自己的血液在沸腾",
    "感觉到自己的战意在升腾",
    "感觉到自己的心跳在加速",
    # 表情系列
    "脸色变得苍白",
    "嘴巴张了张",
    "想说什么，但又说不出来",
    "他的眼睛亮了",
]


# ============================================================
# 2. 正则模式匹配 — AI味句式范式
# ============================================================

AI_PATTERNS = [
    # 眼神系列
    r"眼[中底神色]*闪过一[丝抹]",
    r"眼[中底神色]*涌起一[丝抹]",
    r"眼[中底神色]*掠过一[丝抹]",
    # 嘴角系列
    r"嘴角[微微]*[勾翘抬]起",
    r"嘴角[微微]*上扬",
    r"嘴角[微微]*抽[了搐]",
    # 心理活动（禁止直接描写）
    r"不禁|暗自|心中[想道思忖叹]",
    r"他心想|她心想|他感到|她感到",
    # 感觉系列
    r"感觉到自己的",
    r"感觉[到]一[阵股]",
    # 固定搭配
    r"倒吸.*凉气",
    r"战意.*升腾",
    r"瞳孔[剧烈]*[收骤][缩]",
    r"喃喃自语",
    # 概述性情绪
    r"[非常十分极其特别格外]的?[愤怒悲伤痛苦开心高兴]",
    r"[非常十分极其特别格外]地?[愤怒悲伤痛苦开心高兴]",
]


# ============================================================
# 3. 通用叙述白名单 — 保护常用物理动作
# ============================================================

STATIC_WHITELIST = {
    # 常用物理动作
    "看了一眼", "看了他一眼", "看了她一眼", "看了看",
    "深吸一口气", "叹了口气", "呼了一口气",
    "手机又震了", "手机响了", "手机震了一下",
    "推开门", "打开门", "关上门", "敲了敲门",
    "按下", "拿起", "放下", "走到", "站在", "坐在",
    "转过身", "回过头", "点了点头", "摇了摇头",
    # 常用连接词
    "就在这时", "突然", "忽然", "这时",
    # 常用感官
    "他看到", "她看到", "他听到", "她听到",
    "他感觉", "她感觉",
}


# ============================================================
# 4. 项目白名单 — 自动从配置提取
# ============================================================

def load_project_whitelist(project_dir: str | Path) -> set[str]:
    """从项目配置自动提取白名单（人名、地名等）"""
    project_dir = Path(project_dir)
    whitelist = set()

    # 从characters.json提取人名和别名
    chars_file = project_dir / "characters.json"
    if chars_file.exists():
        try:
            data = json.loads(chars_file.read_text(encoding="utf-8"))
            for char in data.get("characters", []):
                name = char.get("name", "")
                if name:
                    whitelist.add(name)
                aliases = char.get("aliases", [])
                whitelist.update(aliases)
        except Exception:
            pass

    # 从world_rules.json提取地名和设定
    world_file = project_dir / "world_rules.json"
    if world_file.exists():
        try:
            data = json.loads(world_file.read_text(encoding="utf-8"))
            setting = data.get("setting", {})
            for key, value in setting.items():
                if isinstance(value, str) and value:
                    whitelist.add(value)
            # 提取世界观规则中的关键词
            rules = data.get("rules", [])
            for rule in rules:
                if isinstance(rule, str):
                    # 提取引号内的内容
                    quoted = re.findall(r'[""](.*?)["""]', rule)
                    whitelist.update(quoted)
        except Exception:
            pass

    # 从concept_mapping.json提取
    mapping_file = project_dir / "concept_mapping.json"
    if mapping_file.exists():
        try:
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
            for group_name, group_elements in data.items():
                whitelist.add(group_name)
                whitelist.update(group_elements)
        except Exception:
            pass

    return whitelist


# ============================================================
# 5. 核心检测函数
# ============================================================

def check_ai_flavor(
    text: str,
    project_dir: str | Path | None = None,
) -> list[dict]:
    """
    检测文本中的AI味表达。

    Returns:
        [{"type": "exact"|"pattern", "match": "...", "line": N, "context": "..."}]
    """
    violations = []
    lines = text.split("\n")

    # 加载白名单
    whitelist = STATIC_WHITELIST.copy()
    if project_dir:
        whitelist |= load_project_whitelist(project_dir)

    # 1. 精确匹配
    for phrase in SEED_BLACKLIST:
        if phrase in whitelist:
            continue
        for i, line in enumerate(lines, 1):
            if phrase in line:
                violations.append({
                    "type": "exact",
                    "match": phrase,
                    "line": i,
                    "context": line.strip()[:80],
                })

    # 2. 正则模式匹配
    for pattern in AI_PATTERNS:
        regex = re.compile(pattern)
        for i, line in enumerate(lines, 1):
            matches = regex.findall(line)
            for match in matches:
                # 检查是否在白名单中
                if match in whitelist:
                    continue
                violations.append({
                    "type": "pattern",
                    "match": match,
                    "line": i,
                    "context": line.strip()[:80],
                    "pattern": pattern,
                })

    return violations


def scan_chapter_for_blacklist(
    chapter_text: str,
    blacklist: list[str] | None = None,
    project_dir: str | Path | None = None,
) -> list[dict]:
    """
    扫描单章文本，检测AI味表达。

    兼容旧接口，内部使用新的check_ai_flavor。
    """
    # 使用新的检测逻辑
    violations = check_ai_flavor(chapter_text, project_dir)

    # 转换为旧格式（兼容）
    result = []
    for v in violations:
        result.append({
            "phrase": v["match"],
            "count": 1,
            "lines": [v["line"]],
            "type": v["type"],
            "context": v.get("context", ""),
        })

    return result


def load_blacklist(path: str | Path) -> list[str]:
    """从文件加载黑名单"""
    path = Path(path)
    if not path.exists():
        return SEED_BLACKLIST.copy()
    return [line.strip() for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def save_blacklist(blacklist: list[str], path: str | Path):
    """保存黑名单到文件"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blacklist), encoding="utf-8")


# ============================================================
# 6. 命令行入口
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python dynamic_blacklist.py <chapter_file> [--project-dir DIR]")
        sys.exit(1)

    chapter_file = Path(sys.argv[1])
    project_dir = None

    if "--project-dir" in sys.argv:
        idx = sys.argv.index("--project-dir")
        project_dir = Path(sys.argv[idx + 1])

    text = chapter_file.read_text(encoding="utf-8")
    violations = check_ai_flavor(text, project_dir)

    if violations:
        print(f"发现 {len(violations)} 个AI味表达：")
        for v in violations:
            print(f"  [{v['type']}] 第{v['line']}行: \"{v['match']}\"")
            print(f"         上下文: {v['context']}")
    else:
        print("✓ 未发现AI味表达")
