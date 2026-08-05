#!/usr/bin/env python3
"""
用 hermes (ark-code-latest) 给 juben 写章节。
读 projects/神算子算不到自己/outlines/prompt_NNN.md → 生成正文 → 写 chapters/NNN.md
"""
import subprocess
import sys
from pathlib import Path

PROJECT = Path("projects/神算子算不到自己")
PROMPT_DIR = PROJECT / "outlines"
CHAPTERS_DIR = PROJECT / "chapters"


def gen_with_hermes(prompt: str, max_tokens: int = 8000) -> str:
    """调 hermes CLI 生成正文"""
    result = subprocess.run(
        [
            "hermes",
            "--yolo",
            "-m", "ark-code-latest",
            "-z", prompt,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hermes failed: {result.stderr[:500]}")
    return result.stdout.strip()


def write_chapter(chapter_num: int) -> bool:
    """生成指定章节。返回是否成功。"""
    prompt_path = PROMPT_DIR / f"prompt_{chapter_num:03d}.md"
    chapter_path = CHAPTERS_DIR / f"{chapter_num:03d}.md"

    if not prompt_path.exists():
        print(f"  ❌ prompt 不存在: {prompt_path}")
        return False

    if chapter_path.exists() and chapter_path.stat().st_size > 2000:
        print(f"  ⏭️  章节已存在 ({chapter_path.stat().st_size}B), 跳过")
        return True

    print(f"  📖 读 prompt ({prompt_path.stat().st_size}B)...")
    full_prompt = prompt_path.read_text(encoding="utf-8")

    # 加一段收尾指令，让LLM直接输出正文（不要解释、不要分析）
    user_msg = full_prompt + "\n\n---\n\n请直接输出第{}章正文。**只输出正文**（章节标题+正文内容），不要输出任何解释、分析、元评论。中文，2000-3000字，开篇100字必须包含动词+感官细节，结尾必须用物理打断锁+视觉定格。".format(chapter_num)

    print(f"  🤖 调 hermes 生成...")
    try:
        body = gen_with_hermes(user_msg)
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        return False

    if len(body) < 1500:
        print(f"  ⚠️  生成太短 ({len(body)}字), 可能质量问题")
        # 仍然写盘, audit 之后再说

    chapter_path.write_text(body, encoding="utf-8")
    print(f"  ✅ 写盘: {chapter_path} ({len(body)}字)")
    return True


def main():
    if len(sys.argv) < 2:
        print("usage: write_chapter.py <start> [end]")
        sys.exit(1)
    start = int(sys.argv[1])
    end = int(sys.argv[2]) if len(sys.argv) > 2 else start

    print(f"🚀 写第 {start}-{end} 章")
    ok = 0
    fail = 0
    for n in range(start, end + 1):
        print(f"\n--- 第{n}章 ---")
        if write_chapter(n):
            ok += 1
        else:
            fail += 1
    print(f"\n📊 完成: {ok} 成功, {fail} 失败")


if __name__ == "__main__":
    main()
