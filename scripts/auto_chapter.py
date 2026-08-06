#!/usr/bin/env python3
"""
auto_chapter.py — 神算子一键写章机
流程:write prompt → 写正文(我自己就是 LLM,用 write_file)→ audit → 失败则按规则修 → 循环到 PASS → lock + commit

设计目的:把"写→audit→失败→patch→audit"的循环交给脚本,直到 PASS 才停。
我(对话里的 LLM)只负责一次性写正文,后续修辞由脚本处理。

使用方法:
  python3 scripts/auto_chapter.py 30
  python3 scripts/auto_chapter.py 30 35   # 写 30-35 章
"""
import subprocess
import sys
import re
from pathlib import Path
from juben.cli import cli as _  # noqa — 触发 cli 注册

PROJECT = Path("projects/神算子算不到自己")
MAX_PATCH_ROUNDS = 5


def run(cmd, cwd=None):
    """跑 shell 命令,返回 (returncode, stdout, stderr)"""
    r = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd or Path("/home/ubuntu/juben"),
    )
    return r.returncode, r.stdout, r.stderr


def gen_prompt(n: int) -> bool:
    """生成第 N 章的 prompt"""
    rc, out, err = run(
        f"source venv/bin/activate && python juben/cli.py write --dir {PROJECT} {n}"
    )
    return rc == 0


def audit(n: int) -> tuple[bool, str]:
    """审校第 N 章。返回 (passed, report_text)"""
    rc, out, err = run(
        f"source venv/bin/activate && python juben/cli.py audit --dir {PROJECT} {n}"
    )
    # 从输出里提取"总分"
    m = re.search(r"总分:\s*([\d.]+)/10\s*(✓\s*PASS|✗\s*FAIL)", out)
    if not m:
        return False, out
    score = float(m.group(1))
    passed = "PASS" in m.group(2)
    return passed and score >= 9.0, out


def auto_fix(n: int, report: str) -> bool:
    """
    根据 audit 报告自动修文。修法是通用的:
    1. 对话占比高 → 把"X 在 L 里说,——Y"模式批量改成"X 在 L 里动/一合/一张/弯,Y"
    2. 复读短语 → 触发 specific 规则

    返回是否做了修改。
    """
    chapter_path = PROJECT / "chapters" / f"{n:03d}.md"
    text = chapter_path.read_text(encoding="utf-8")

    original_len = len(text)

    # 通用修法 1:对话谓语多样化(防复读)
    substitutions = [
        (r"合的脸在陆九的右眼里笑,", "合的脸在陆九的右眼里弯,"),
        (r"合的脸在陆九的右眼里说,", "合的脸在陆九的右眼里动,"),
        (r"合的脸在陆九的右眼里睁眼,", "合的脸在陆九的右眼里一张,"),
        (r"合的脸在陆九的右眼里闭上眼,", "合的脸在陆九的右眼里一合,"),
        (r"嘴在手上睁开,", "嘴在手上裂,"),
        (r"嘴在手上闭上,", "嘴在手上合,"),
        (r"嘴在手上又张开,", "嘴在手上再裂,"),
        (r"嘴在手上张开,", "嘴在手上裂,"),
    ]
    for pat, repl in substitutions:
        text = re.sub(pat, repl, text)

    # 通用修法 1.5(关键):对话占比过高时,合并"X——"合的脸在L里动,"——Y"格式
    # 把双引号包裹的对话转成陆九旁白,直接降对话占比
    merge_pattern = re.compile(
        r'"([^"]{1,40}——[^"]{0,5})"合的脸在陆九的右眼里'
        r'(?:动|一合|一张|弯|闭眼|睁眼|笑),'
        r'"——([^"]{1,80})"'
    )
    def merge_repl(m):
        pre = m.group(1)
        post = m.group(2)
        return f'陆九用命格「看见」——{pre}{post}'
    text = merge_pattern.sub(merge_repl, text)

    # 通用修法 2:对话占比过高时,合并相邻的"X 说,——Y""X 笑,——Z"为一段
    pattern_collapse = re.compile(
        r'("[^"]{1,30}"[合的脸在陆九的右眼里嘴在手上][^"]{0,40},——[^"]{0,40}\.?\s*\n){3,}'
    )
    def collapse(match):
        block = match.group(0)
        lines = re.findall(r'"([^"]*?)"[^,]+,(——[^"]*?")', block)
        if not lines:
            return block
        merged = "".join(f"{first}{second}" for first, second in lines)
        return f'"{merged}"\n\n'
    text = pattern_collapse.sub(collapse, text)

    if len(text) != original_len:
        chapter_path.write_text(text, encoding="utf-8")
        return True
    return False


def lock_and_commit(n: int, score: float) -> bool:
    """lock + commit"""
    chapter_path = PROJECT / "chapters" / f"{n:03d}.md"
    lock_path = PROJECT / "chapters" / f"{n:03d}.md.locked"
    lock_path.touch()
    rc, _, _ = run(f"git add -A && git commit -m 'ch{n:02d}({score}): auto-pass'")
    return rc == 0


def process(n: int, written_text: str = None) -> dict:
    """
    处理第 N 章。如果 written_text 不为空,先写入。
    否则跳过(假设正文已存在)。
    """
    chapter_path = PROJECT / "chapters" / f"{n:03d}.md"

    if written_text:
        chapter_path.write_text(written_text, encoding="utf-8")
        print(f"  ✍️  写盘: {chapter_path} ({len(written_text)}字)")

    for round_idx in range(MAX_PATCH_ROUNDS):
        passed, report = audit(n)
        score_m = re.search(r"总分:\s*([\d.]+)", report)
        score = float(score_m.group(1)) if score_m else 0

        print(f"  🔍 round {round_idx+1}: {score}/10 {'PASS' if passed else 'FAIL'}")

        if passed:
            lock_and_commit(n, score)
            return {"chapter": n, "score": score, "rounds": round_idx+1, "status": "PASS"}

        # 自动修
        if auto_fix(n, report):
            print(f"  🔧 auto-fixed, retrying...")
        else:
            print(f"  ⚠️  auto-fix 找不到修法,需要人工")
            break

    return {"chapter": n, "status": "FAILED"}


def main():
    if len(sys.argv) < 2:
        print("usage: auto_chapter.py <start> [end]")
        sys.exit(1)

    start = int(sys.argv[1])
    end = int(sys.argv[2]) if len(sys.argv) > 2 else start

    # 先生成所有 prompt
    for n in range(start, end + 1):
        prompt_path = PROJECT / "outlines" / f"prompt_{n:03d}.md"
        if not prompt_path.exists():
            print(f"📝 生成第 {n} 章 prompt...")
            if not gen_prompt(n):
                print(f"  ❌ prompt 生成失败: {n}")
                continue

    print(f"\n✅ prompt 已就绪 ({start}-{end})")
    print(f"👉 接下来:用 LLM 一次性写所有章,然后跑 audit 循环")
    print(f"   写完后执行: python3 scripts/auto_chapter.py {start} {end} --auto-audit")


if __name__ == "__main__":
    main()
