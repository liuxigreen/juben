#!/usr/bin/env python3
"""
Stage 1: 剧本生成器

使用LLM从创意大纲生成完整剧本。
输出格式：每章一个Markdown文件，符合Stage 2输入要求。

使用方法：
    python3 generate_script.py --project 心声咖啡 --chapters 1-5
    python3 generate_script.py --project 心声咖啡 --all
"""

import json
import argparse
from pathlib import Path
from typing import Optional


def load_config(project_dir: Path) -> dict:
    """加载项目配置"""
    config = {}
    
    # 加载主配置
    main_config = project_dir / "config" / "project_config.yaml"
    if main_config.exists():
        import yaml
        with open(main_config) as f:
            config["project"] = yaml.safe_load(f)
    
    # 加载角色配置
    chars_file = project_dir / "config" / "characters.yaml"
    if chars_file.exists():
        import yaml
        with open(chars_file) as f:
            config["characters"] = yaml.safe_load(f)
    
    # 加载场景配置
    locs_file = project_dir / "config" / "locations.yaml"
    if locs_file.exists():
        import yaml
        with open(locs_file) as f:
            config["locations"] = yaml.safe_load(f)
    
    # 加载事件配置
    events_file = project_dir / "config" / "events.yaml"
    if events_file.exists():
        import yaml
        with open(events_file) as f:
            config["events"] = yaml.safe_load(f)
    
    return config


def build_chapter_prompt(
    chapter_num: int,
    total_chapters: int,
    config: dict,
    prev_summary: str = "",
    next_outline: str = "",
) -> str:
    """
    构建单章剧本的生成提示词。
    
    Args:
        chapter_num: 当前章节号
        total_chapters: 总章节数
        config: 项目配置
        prev_summary: 前一章摘要
        next_outline: 下一章大纲
    """
    project = config.get("project", {})
    characters = config.get("characters", {})
    locations = config.get("locations", {})
    events = config.get("events", {})
    
    # 构建角色描述
    char_desc = ""
    for char in characters.get("characters", []):
        char_desc += f"""
### {char['name']}
- 年龄: {char.get('age', '未知')}
- 原型: {char.get('archetype', '未定义')}
- 外貌: {json.dumps(char.get('appearance', {}), ensure_ascii=False)}
- 性格: {', '.join(char.get('personality', []))}
- 说话风格: {char.get('speech_style', '正常')}
"""
    
    # 构建场景描述
    loc_desc = ""
    for loc in locations.get("locations", []):
        loc_desc += f"""
### {loc['name']}
- 类型: {loc.get('type', 'interior')}
- 描述: {loc.get('description', '')}
- 氛围: {loc.get('atmosphere', '')}
- 道具: {', '.join(loc.get('props', []))}
"""
    
    # 构建事件描述
    event_desc = ""
    events_list = events.get("events", [])
    if isinstance(events_list, list):
        for event in events_list:
            event_type = event.get("type", "unknown")
            triggers = event.get("triggers", [])
            event_desc += f"""
- {event_type}: 触发词={', '.join(triggers[:3])}...
"""
    elif isinstance(events_list, dict):
        for event_name, event_data in events_list.items():
            if event_data.get("enabled", False):
                event_desc += f"""
- {event_data.get('name', event_name)}: 视觉提示={event_data.get('visual_cue', '无')}, 时长={event_data.get('duration_range', [3,6])}秒
"""
    
    # 三幕结构
    structure = project.get("structure", {}).get("three_act", {})
    act1 = structure.get("act1_setup", [1, 5])
    act2 = structure.get("act2_confrontation", [6, 15])
    act3 = structure.get("act3_resolution", [16, 20])
    
    if chapter_num <= act1[1]:
        act_name = "第一幕：建置"
        act_desc = "建立世界观、角色关系、核心冲突"
    elif chapter_num <= act2[1]:
        act_name = "第二幕：对抗"
        act_desc = "冲突升级、关系变化、秘密揭露"
    else:
        act_name = "第三幕：解决"
        act_desc = "高潮对决、冲突解决、结局收束"
    
    prompt = f"""你是一位专业的短剧编剧。请为以下剧集撰写第{chapter_num}章剧本。

# 剧集信息

- 标题: {project.get('title', '未命名')}
- 题材: {project.get('genre', '未定义')}
- 总章节: {total_chapters}
- 当前章节: {chapter_num}/{total_chapters}
- 当前幕: {act_name}
- 幕任务: {act_desc}

# 角色设定

{char_desc}

# 场景设定

{loc_desc}

# 特殊事件（如有）

{event_desc}

# 前情摘要

{prev_summary if prev_summary else "（第一章，无前情）"}

# 本章大纲

{next_outline if next_outline else "请根据三幕结构和当前幕任务，设计本章情节。"}

# 输出要求

请按以下格式输出剧本：

```markdown
# 第{chapter_num}章 [章节标题]

[场景描述和动作描写]

**角色名**：（括号内写表演指示）对话内容

[更多场景...]
```

## 写作规则

1. **每章3-5个场景**，用空行分隔
2. **动作必须是物理可拍的**
   - ❌ "她回忆起过去" → ✅ "她盯着墙上的老照片，手指颤抖"
   - ❌ "他感到愤怒" → ✅ "他的拳头砸在桌上，杯子弹起"
3. **对话要口语化**，每句15字以内
4. **每章结尾必须有钩子**（悬念、反转、新信息）
5. **场景切换要明确**（时间/地点变化时写清楚）
6. **总字数控制在1500-2500字**

请开始写作：
"""
    return prompt


def generate_chapter(
    chapter_num: int,
    total_chapters: int,
    config: dict,
    prev_summary: str = "",
    next_outline: str = "",
    llm_caller=None,
) -> str:
    """
    生成单章剧本。
    
    Args:
        chapter_num: 章节号
        total_chapters: 总章节数
        config: 项目配置
        prev_summary: 前一章摘要
        next_outline: 本章大纲
        llm_caller: LLM调用函数 (prompt: str) -> str
    
    Returns:
        剧本Markdown文本
    """
    prompt = build_chapter_prompt(
        chapter_num, total_chapters, config, prev_summary, next_outline
    )
    
    if llm_caller is None:
        # 默认使用print输出prompt，让用户手动调用LLM
        print("=" * 60)
        print(f"第{chapter_num}章生成提示词：")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        print("请将上述提示词发送给LLM，然后将输出保存到：")
        print(f"  chapters/{chapter_num:03d}.md")
        return ""
    
    return llm_caller(prompt)


def save_chapter(project_dir: Path, chapter_num: int, content: str):
    """保存章节到文件"""
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    
    filepath = chapters_dir / f"{chapter_num:03d}.md"
    filepath.write_text(content, encoding="utf-8")
    print(f"已保存: {filepath}")


def get_prev_summary(project_dir: Path, chapter_num: int) -> str:
    """获取前一章摘要"""
    if chapter_num <= 1:
        return ""
    
    prev_file = project_dir / "chapters" / f"{chapter_num-1:03d}.md"
    if not prev_file.exists():
        return ""
    
    content = prev_file.read_text(encoding="utf-8")
    
    # 提取最后200字作为摘要
    lines = content.strip().split("\n")
    summary_lines = []
    word_count = 0
    for line in reversed(lines):
        if line.strip():
            summary_lines.insert(0, line)
            word_count += len(line)
            if word_count > 200:
                break
    
    return "\n".join(summary_lines)


def main():
    parser = argparse.ArgumentParser(description="Stage 1: 剧本生成器")
    parser.add_argument("--project", required=True, help="项目名称")
    parser.add_argument("--chapters", help="章节范围，如 1-5 或 1,3,5")
    parser.add_argument("--all", action="store_true", help="生成所有章节")
    parser.add_argument("--prompt-only", action="store_true", help="只输出提示词，不调用LLM")
    
    args = parser.parse_args()
    
    # 项目目录
    project_dir = Path("projects") / args.project
    if not project_dir.exists():
        print(f"错误: 项目目录不存在 {project_dir}")
        return
    
    # 加载配置
    config = load_config(project_dir)
    total_chapters = config.get("project", {}).get("project", {}).get("total_chapters", 20)
    
    # 确定要生成的章节
    if args.all:
        chapters = list(range(1, total_chapters + 1))
    elif args.chapters:
        if "-" in args.chapters:
            start, end = args.chapters.split("-")
            chapters = list(range(int(start), int(end) + 1))
        else:
            chapters = [int(x) for x in args.chapters.split(",")]
    else:
        print("错误: 请指定 --chapters 或 --all")
        return
    
    print(f"项目: {args.project}")
    print(f"章节数: {len(chapters)}")
    print(f"模式: {'仅提示词' if args.prompt_only else '完整生成'}")
    print()
    
    # 逐章生成
    for chapter_num in chapters:
        print(f"\n{'='*60}")
        print(f"处理第{chapter_num}章...")
        print(f"{'='*60}")
        
        # 获取前情摘要
        prev_summary = get_prev_summary(project_dir, chapter_num)
        
        if args.prompt_only:
            # 只输出提示词
            prompt = build_chapter_prompt(
                chapter_num, total_chapters, config, prev_summary
            )
            prompt_file = project_dir / "chapters" / f"{chapter_num:03d}_prompt.txt"
            prompt_file.parent.mkdir(exist_ok=True)
            prompt_file.write_text(prompt, encoding="utf-8")
            print(f"提示词已保存: {prompt_file}")
        else:
            # 调用LLM生成（需要实现llm_caller）
            print("提示: 需要实现llm_caller函数来调用LLM")
            print("或者使用 --prompt-only 模式获取提示词后手动调用")
    
    print(f"\n{'='*60}")
    print("完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
