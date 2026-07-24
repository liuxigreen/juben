"""
CLI入口 — juben命令行工具

命令：
  juben init <premise>     初始化项目
  juben outline            生成大纲prompt
  juben write <N>          生成第N章的prompt
  juben audit [chapter]    审校（检查已有章节）
  juben info               查看项目状态
  juben mixins             列出所有可用mixin
"""
from __future__ import annotations

import json
import sys
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from juben.state.manager import StateManager
from juben.state.schema import ChapterReport
from juben.extract import ContextExtractor
from juben.generate.scribe import Scribe
from juben.validate.anti_ai import AntiAIChecker
from juben.validate.anti_cliche import AntiClicheChecker
from juben.validate.cliffhanger import CliffhangerValidator
from juben.validate.info_asymmetry import InfoAsymmetryValidator

console = Console()
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.3.0")
def main():
    """剧本引擎 — AI剧本/小说创作引擎"""
    pass


# ============================================================
# mixins — 列出可用mixin
# ============================================================

@main.command()
def mixins():
    """列出所有可用的mixin规则包"""
    from juben.mixins.merge_engine import MergeEngine

    engine = MergeEngine()
    available = engine.list_available()

    for category, names in available.items():
        table = Table(title=f"📦 {category}/")
        table.add_column("名称", style="cyan")
        table.add_column("说明")

        for name in names:
            try:
                data = engine.load_mixin(category, name)
                desc = data.get("description", "")
                table.add_row(name, desc)
            except Exception as e:
                table.add_row(name, f"[red]加载失败: {e}[/red]")

        console.print(table)
        console.print()


# ============================================================
# research — 题材调研
# ============================================================

@main.command()
@click.argument("query")
@click.option("--dir", "-d", default=".", help="项目目录（用于保存报告）")
@click.option("--fetch", "-f", "fetch_n", default=2, type=int, help="抓取前N条结果的完整内容")
def research(query: str, dir: str, fetch_n: int):
    """联网搜索题材趋势、爆款元素、市场数据"""
    from juben.research import research_genre, format_research_report

    project_dir = Path(dir).resolve()

    console.print(f"[cyan]正在调研: {query}[/cyan]")

    result = research_genre(
        query=query,
        project_dir=project_dir,
        fetch_top_n=fetch_n,
    )

    report = format_research_report(result)
    console.print(report)

    if result.get("report_path"):
        console.print(f"\n[green]报告已保存到 {result['report_path']}[/green]")
        console.print("[dim]下次 juben bootstrap 时会自动注入这些调研结果[/dim]")


# ============================================================
# init — 初始化项目
# ============================================================

@main.command()
@click.argument("premise", default="")
@click.option("--template", "-t", default="rebirth-revenge", help="题材模板 (rebirth-revenge / universal)")
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--mixin", "-m", default="", help="Genre mixin列表，逗号分隔 (仅universal模板)")
@click.option("--skeleton", "-s", default="", help="Skeleton mixin列表，逗号分隔 (仅universal模板)")
@click.option("--timeline-skeleton", "-ts", default="50chap-standard", help="Timeline Lock骨架类型 (20chap-fast/50chap-standard/100chap-epic)")
@click.option("--title", default="", help="故事标题")
@click.option("--disruption", default="", help="意外变量")
@click.option("--yes", "-y", is_flag=True, help="跳过确认，直接初始化")
def init(premise: str, template: str, dir: str, mixin: str, skeleton: str,
         timeline_skeleton: str, title: str, disruption: str, yes: bool):
    """初始化一个新故事项目"""
    from juben.genre_templates import get_template, list_templates

    tpl_fn = get_template(template)
    if tpl_fn is None:
        console.print(f"[red]未知模板: {template}[/red]")
        console.print(f"可用模板: {', '.join(list_templates())}")
        sys.exit(1)

    project_dir = Path(dir).resolve()
    if project_dir.exists() and any(project_dir.glob("*.json")):
        if not click.confirm(f"目录 {project_dir} 已有项目文件，继续？"):
            sys.exit(0)

    # 解析mixin参数
    mixin_list = [m.strip() for m in mixin.split(",") if m.strip()] if mixin else None
    skeleton_list = [s.strip() for s in skeleton.split(",") if s.strip()] if skeleton else None

    # universal模板：显示合并报告并确认
    if template == "universal" and (mixin_list or skeleton_list):
        from juben.mixins.merge_engine import MergeEngine

        engine = MergeEngine()

        try:
            world_rules = engine.build_world_rules(mixin_list or [])
            pacing_cards = engine.build_pacing_cards(skeleton_list or [])
        except Exception as e:
            console.print(f"[red]Mixin加载失败: {e}[/red]")
            sys.exit(1)

        # 显示合并报告
        report = engine.generate_init_report(
            genre_mixins=mixin_list or [],
            skeleton_mixins=skeleton_list or [],
            world_rules=world_rules,
            pacing_cards=pacing_cards,
        )
        console.print(report)

        if not yes:
            console.print("\n[yellow]以上是将要写入项目的规则。[/yellow]")
            console.print("[yellow]你可以手动编辑 templates/mixins/ 中的YAML文件后再确认。[/yellow]")
            if not click.confirm("确认使用这些规则初始化项目？"):
                console.print("已取消。修改mixin后重新运行即可。")
                sys.exit(0)

    # 调用模板初始化
    if template == "universal":
        result = tpl_fn(
            premise=premise,
            mixins=mixin_list,
            skeletons=skeleton_list,
            title=title,
            disruption_variable=disruption,
        )
    else:
        result = tpl_fn(premise=premise)

    mgr = StateManager(project_dir)
    mgr.init_project(
        meta=result["meta"],
        characters=result["characters"],
        world_rules=result["world_rules"],
    )
    
    # 保存Timeline Lock骨架配置
    timeline_lock_config = {
        "skeleton_type": timeline_skeleton,
        "description": f"Timeline Lock骨架类型: {timeline_skeleton}"
    }
    mgr._write_json("timeline_lock_config.json", timeline_lock_config)

    console.print(Panel(
        f"[green]✓ 项目初始化完成[/green]\n\n"
        f"目录: {project_dir}\n"
        f"模板: {template}\n"
        f"主角: {result['characters'][0].name}\n"
        f"前提: {result['meta'].premise[:80]}...\n\n"
        f"[yellow]下一步:[/yellow]\n"
        f"  1. juben bootstrap --dir {project_dir}  (生成LLM填充prompt)\n"
        f"  2. 把prompt喂给LLM，保存输出为 bootstrap_response.json\n"
        f"  3. juben bootstrap --apply --dir {project_dir}  (应用LLM输出)\n"
        f"  4. juben write 1 --dir {project_dir}  (开始写作)",
        title="🎬 剧本引擎",
    ))


# ============================================================
# bootstrap — LLM驱动的角色/世界观填充
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--apply", "do_apply", is_flag=True, help="应用bootstrap_response.json到项目")
@click.option("--response", "-r", default="", help="指定响应文件路径 (默认 bootstrap_response.json)")
def bootstrap(dir: str, do_apply: bool, response: str):
    """生成LLM填充prompt，或将LLM输出应用到项目"""
    from juben.bootstrapper import (
        save_bootstrap_prompt, apply_bootstrap_response, ValidationError,
    )

    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)

    if not do_apply:
        # 模式1：生成prompt
        try:
            mgr.load_meta()
        except Exception:
            console.print("[red]找不到项目文件，请先运行 juben init[/red]")
            sys.exit(1)

        path = save_bootstrap_prompt(mgr)
        console.print(Panel(
            f"[green]✓ Bootstrap prompt已生成[/green]\n\n"
            f"文件: {path}\n\n"
            f"[yellow]使用方法:[/yellow]\n"
            f"1. 把 {path.name} 的内容投喂给任意LLM（ChatGPT/Claude/Agent）\n"
            f"2. 让LLM输出JSON，保存为 bootstrap_response.json\n"
            f"3. 运行 [cyan]juben bootstrap --apply --dir {project_dir}[/cyan]\n\n"
            f"[dim]提示：也可以用 juben bootstrap --apply -r my_response.json 指定文件[/dim]",
            title="📝 Bootstrap Prompt",
        ))
    else:
        # 模式2：应用响应
        response_path = project_dir / (response or "bootstrap_response.json")
        if not response_path.exists():
            console.print(f"[red]找不到响应文件: {response_path}[/red]")
            sys.exit(1)

        try:
            with open(response_path, "r", encoding="utf-8") as f:
                # 支持LLM输出中包含markdown代码块的情况
                content = f.read().strip()
                if content.startswith("```"):
                    # 提取代码块中的JSON
                    lines = content.split("\n")
                    json_lines = []
                    in_block = False
                    for line in lines:
                        if line.strip().startswith("```") and not in_block:
                            in_block = True
                            continue
                        elif line.strip() == "```" and in_block:
                            break
                        elif in_block:
                            json_lines.append(line)
                    content = "\n".join(json_lines)

                response_data = json.loads(content)
        except json.JSONDecodeError as e:
            console.print(f"[red]JSON解析失败: {e}[/red]")
            console.print("[yellow]提示：确保LLM输出的是纯JSON（可以包含在```代码块中）[/yellow]")
            sys.exit(1)

        try:
            result = apply_bootstrap_response(mgr, response_data)
        except ValidationError as e:
            console.print(f"[red]验证失败: {e}[/red]")
            sys.exit(1)

        # 显示结果
        table = Table(title="🎬 Bootstrap 应用结果")
        table.add_column("项目", style="cyan")
        table.add_column("值")
        for change in result["applied"]:
            table.add_row("✓", change)
        table.add_row("角色", ", ".join(result["character_names"]))
        console.print(table)

        console.print(Panel(
            f"[green]✓ 项目已填充完成[/green]\n\n"
            f"[yellow]下一步:[/yellow]\n"
            f"  1. juben info --dir {project_dir}  (查看项目状态)\n"
            f"  2. juben write 1 --dir {project_dir}  (开始写作)",
            title="🎬 剧本引擎",
        ))


# ============================================================
# rewrite — Guardian低分章节重写prompt
# ============================================================

@main.command()
@click.argument("chapter", type=int)
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--context", "-c", default="", help="额外上下文")
def rewrite(chapter: int, dir: str, context: str):
    """为Guardian低分章节生成重写prompt"""
    from juben.rewriter import save_rewrite_prompt

    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)

    try:
        path = save_rewrite_prompt(mgr, chapter, extra_context=context)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[green]✓ 重写prompt已生成[/green]\n\n"
        f"文件: {path}\n\n"
        f"[yellow]使用方法:[/yellow]\n"
        f"1. 把 {path.name} 的内容投喂给LLM\n"
        f"2. 把LLM输出保存到 rewrites/chapter_{chapter:03d}_v2.md\n"
        f"3. 满意后替换 chapters/{chapter:03d}.md\n"
        f"4. 运行 [cyan]juben commit {chapter} --dir {project_dir}[/cyan]",
        title=f"🔄 第{chapter}章重写Prompt",
    ))


# ============================================================
# commit — 章节锁定 + Curator状态更新
# ============================================================

@main.command()
@click.argument("chapter", type=int)
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--skip-audit", is_flag=True, help="跳过audit检查")
@click.option("--apply-curator", is_flag=True, help="自动应用Curator提案")
def commit(chapter: int, dir: str, skip_audit: bool, apply_curator: bool):
    """锁定已通过audit的章节，生成Curator状态更新prompt"""
    from juben.committer import commit_chapter, apply_curator_response

    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)

    result = commit_chapter(mgr, chapter, skip_audit=skip_audit)

    if result.error:
        console.print(f"[red]✗ {result.error}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[green]✓ 第{chapter}章已锁定[/green]\n\n"
        f"Audit分数: {result.audit_score}/10\n"
        f"Curator prompt: {result.curator_proposal.get('prompt_path', 'N/A')}\n\n"
        f"[yellow]下一步:[/yellow]\n"
        f"1. 把Curator prompt喂给LLM\n"
        f"2. 保存LLM输出到 curator/curator_response_{chapter:03d}.json\n"
        f"3. 运行 [cyan]juben commit {chapter} --apply-curator --dir {project_dir}[/cyan]\n"
        f"   或 [cyan]juben curator-apply {chapter} --dir {project_dir}[/cyan]",
        title="🔒 章节锁定",
    ))

    # 如果指定了--apply-curator，尝试应用已有的响应
    if apply_curator:
        try:
            applied = apply_curator_response(mgr, chapter)
            if applied:
                console.print(f"\n[green]✓ Curator状态已更新:[/green]")
                for a in applied:
                    console.print(f"  ✓ {a}")
            else:
                console.print(f"\n[yellow]没有找到Curator响应文件[/yellow]")
        except FileNotFoundError:
            console.print(f"\n[yellow]Curator响应文件不存在，请先生成[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Curator应用失败: {e}[/red]")


@main.command()
@click.argument("chapter", type=int)
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--response", "-r", default="", help="指定响应文件路径")
def curator_apply(chapter: int, dir: str, response: str):
    """应用Curator的状态更新响应"""
    from juben.committer import apply_curator_response

    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)

    try:
        resp_path = response if response else None
        applied = apply_curator_response(mgr, chapter, resp_path)
        if applied:
            console.print(f"[green]✓ Curator状态已更新:[/green]")
            for a in applied:
                console.print(f"  ✓ {a}")
        else:
            console.print(f"[yellow]没有变更[/yellow]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]应用失败: {e}[/red]")
        sys.exit(1)


# ============================================================
# write — 生成章节prompt
# ============================================================

@main.command()
@click.argument("chapter", type=int)
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--chars", "-c", default="", help="出场角色ID，逗号分隔")
def write(chapter: int, dir: str, chars: str):
    """生成第N章的Scribe prompt（投喂给LLM生成正文）"""
    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)
    scribe = Scribe(mgr)

    char_ids = [c.strip() for c in chars.split(",") if c.strip()] if chars else None

    console.print(f"[cyan]正在为第{chapter}章生成prompt...[/cyan]")

    # === 使用统一约束注入器（v2）===
    from juben.constraint_injector import ConstraintInjector, build_constrained_scribe_prompt

    # 生成基础prompt
    base_prompt = scribe.generate_prompt(chapter, character_ids=char_ids)

    # 读取已有章节用于动态黑名单
    chapters_dir = project_dir / "chapters"
    previous_texts = []
    for i in range(max(1, chapter - 3), chapter):
        ch_file = chapters_dir / f"{i:03d}.md"
        if ch_file.exists():
            previous_texts.append(ch_file.read_text(encoding="utf-8"))

    # 注入所有约束
    prompt = build_constrained_scribe_prompt(
        chapter_num=chapter,
        project_dir=project_dir,
        base_prompt=base_prompt,
        previous_chapters=previous_texts,
    )

    path = scribe.save_prompt(chapter, prompt)

    # 统计
    word_count = len(prompt)
    console.print(Panel(
        f"[green]✓ Prompt已生成[/green]\n\n"
        f"文件: {path}\n"
        f"长度: {word_count} 字符\n\n"
        f"[yellow]使用方法:[/yellow]\n"
        f"1. 把 {path} 的内容投喂给LLM\n"
        f"2. 把LLM输出保存到 chapters/{chapter:03d}.md\n"
        f"3. 运行 [cyan]juben audit {chapter}[/cyan] 校验质量",
        title=f"📝 第{chapter}章 Prompt",
    ))


# ============================================================
# audit — 审校章节
# ============================================================

@main.command()
@click.argument("chapter", type=int, default=0)
@click.option("--dir", "-d", default=".", help="项目目录")
def audit(chapter: int, dir: str):
    """审校已有章节（0=全部）"""
    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)
    chapter_dir = project_dir / "chapters"

    if not chapter_dir.exists():
        console.print("[red]没有找到chapters目录[/red]")
        sys.exit(1)

    chapters = []
    if chapter > 0:
        p = chapter_dir / f"{chapter:03d}.md"
        if p.exists():
            chapters.append((chapter, p))
        else:
            console.print(f"[red]找不到第{chapter}章[/red]")
            sys.exit(1)
    else:
        for p in sorted(chapter_dir.glob("*.md")):
            num = int(p.stem)
            chapters.append((num, p))

    if not chapters:
        console.print("[red]chapters目录为空[/red]")
        sys.exit(1)

    # 加载反套路黑名单
    world = mgr.load_world_rules()
    anti_cliche = AntiClicheChecker(world.anti_cliche_blacklist)
    anti_ai = AntiAIChecker()
    cliffhanger = CliffhangerValidator()

    # 加载信息对称性
    rels = mgr.load_relationships()
    info_validator = InfoAsymmetryValidator(rels.info_asymmetry)

    # 加载角色
    characters = mgr.load_characters()
    protagonist = next((c for c in characters if c.role.value == "protagonist"), None)
    protagonist_name = protagonist.name if protagonist else ""

    # 加载Timeline Lock（从项目的timeline_lock_config.json读取skeleton类型）
    from juben.timeline_lock import TimelineLock
    tl_config_path = project_dir / "timeline_lock.json"
    tl_skeleton_config_path = project_dir / "timeline_lock_config.json"
    
    if tl_config_path.exists():
        # 优先使用timeline_lock.json（项目自定义配置）
        timeline_lock = TimelineLock.from_config(tl_config_path)
    elif tl_skeleton_config_path.exists():
        # 从timeline_lock_config.json读取skeleton类型
        try:
            with open(tl_skeleton_config_path, "r", encoding="utf-8") as f:
                tl_skeleton_config = json.load(f)
            skeleton_type = tl_skeleton_config.get("skeleton_type", "50chap-standard")
            timeline_lock = TimelineLock.from_skeleton(skeleton_type)
        except Exception as e:
            logger.warning(f"加载timeline_lock_config.json失败: {e}，使用默认50chap-standard")
            timeline_lock = TimelineLock.from_skeleton("50chap-standard")
    else:
        # 默认使用50chap-standard
        timeline_lock = TimelineLock.from_skeleton("50chap-standard")

    # 收集所有章节结尾（用于Anti-Repetition检测）
    all_endings = []
    for p in sorted(chapter_dir.glob("*.md")):
        t = p.read_text(encoding="utf-8")
        from juben.guardian import _extract_ending
        all_endings.append(_extract_ending(t))

    # 自动推断已完成的节点：扫描目录中所有章节文件
    all_chapter_files = set()
    for p in chapter_dir.glob("*.md"):
        try:
            all_chapter_files.add(int(p.stem))
        except ValueError:
            pass
    completed_nodes = []
    for node in timeline_lock._sorted_nodes:
        node_start, node_end = node.chapter_range
        node_chapters = set(range(node_start, node_end + 1))
        if node_chapters.issubset(all_chapter_files):
            completed_nodes.append(node.node_id)

    for ch_num, ch_path in chapters:
        text = ch_path.read_text(encoding="utf-8")
        console.print(f"\n[bold]═══ 第{ch_num}章审校 ═══[/bold]")

        # 1. 反AI味
        ai_result = anti_ai.check(text)
        _print_validation("反AI味", ai_result)

        # 2. 反套路
        cliche_result = anti_cliche.check(text)
        _print_validation("反套路", cliche_result)

        # 3. Cliffhanger
        ch_result = cliffhanger.check(text)
        _print_validation("Cliffhanger", ch_result)

        # 4. 信息对称性
        char_ids = [c.id for c in characters]
        info_result = info_validator.check(text, char_ids)
        _print_validation("信息对称性", info_result)

        # 5. Guardian（Anti-Dialogue + Anti-Repetition + 高频词 + 信息倾倒）
        from juben.guardian import guardian_check
        from juben.constraint_injector import (
            ConstraintInjector, load_concept_mapping,
            get_required_elements_for_chapter, CostRoulette,
        )
        from juben.validate.dynamic_blacklist import scan_chapter_for_blacklist, SEED_BLACKLIST
        import json as _json

        endings_up_to_ch = all_endings[:ch_num]

        # 加载约束注入器
        injector = ConstraintInjector(project_dir)
        
        # 读取最近3章用于动态黑名单
        previous_texts = []
        for i in range(max(1, ch_num - 3), ch_num):
            ch_file = chapter_dir / f"{i:03d}.md"
            if ch_file.exists():
                previous_texts.append(ch_file.read_text(encoding="utf-8"))
        
        # 获取动态黑名单
        banned = injector._get_dynamic_blacklist(previous_texts if previous_texts else None)
        concept_mapping = load_concept_mapping(project_dir)
        required_elems = get_required_elements_for_chapter(concept_mapping, ch_num, min_count=2)

        # 加载代价历史
        cost_state_file = project_dir / "cost_history.json"
        if cost_state_file.exists():
            with open(cost_state_file) as f:
                cost_history_data = _json.load(f)
            cost_history = [h["cost"] for h in cost_history_data]
        else:
            cost_history = []

        # 收集前几章指纹
        previous_fps = []
        for p in sorted(chapter_dir.glob("*.md")):
            num = int(p.stem)
            if num < ch_num:
                from juben.validate.structure_diversity import extract_event_fingerprint
                t = p.read_text(encoding="utf-8")
                previous_fps.append(extract_event_fingerprint(t))

        guardian_result = guardian_check(
            chapter_text=text,
            chapter_num=ch_num,
            protagonist_name=protagonist_name,
            chapter_endings=endings_up_to_ch,
            characters=characters,
            banned_phrases=banned,
            required_setting_elements=required_elems,
            cost_history=cost_history,
            concept_mapping=concept_mapping,
            previous_fingerprints=previous_fps,
            project_dir=str(project_dir),
        )
        _print_validation("Guardian", guardian_result)

        # 5.1 动态黑名单扫描（显示具体违规）
        from juben.validate.dynamic_blacklist import check_ai_flavor
        blacklist_violations = check_ai_flavor(text, project_dir)
        if blacklist_violations:
            console.print(f"  [yellow]⚠ AI味检测: {len(blacklist_violations)}个违规[/yellow]")
            for v in blacklist_violations[:5]:  # 最多显示5个
                console.print(f"    [dim][{v['type']}] 第{v['line']}行: \"{v['match']}\"[/dim]")

        # 5.5 Curator状态更新
        from juben.curator import CuratorState
        curator = CuratorState.load(project_dir)
        curator.update_chapter(ch_num, text, concept_mapping=concept_mapping)

        # 6. Timeline Lock
        tl_result = timeline_lock.validate_chapter(ch_num, text, completed_nodes)
        if tl_result.passed:
            console.print(f"  [green]✓ Timeline Lock: PASS[/green]")
        else:
            console.print(f"  [red]✗ Timeline Lock: FAIL[/red]")
            for v in tl_result.violations:
                sev_color = "red" if v["severity"] == "critical" else "yellow"
                console.print(f"    [{sev_color}][{v['severity']}] {v['description']}[/]")

        # 总分（6项）
        total = (
            ai_result.score + cliche_result.score +
            ch_result.score + info_result.score +
            guardian_result.score
        ) / 5
        passed = (ai_result.passed and cliche_result.passed and
                  ch_result.passed and guardian_result.passed and tl_result.passed)

        color = "green" if passed else "red"
        console.print(f"\n[{color}]总分: {total:.1f}/10 {'✓ PASS' if passed else '✗ FAIL'}[/{color}]")

    # Curator全局报告
    curator = CuratorState.load(project_dir)
    if curator.chapters:
        console.print(f"\n[bold]═══ Curator状态报告 ═══[/bold]")
        console.print(curator.get_health_report())

        # 保存报告
        report = ChapterReport(
            chapter_num=ch_num,
            word_count=len(text),
            anti_ai=ai_result,
            anti_cliche=cliche_result,
            cliffhanger=ch_result,
            overall_score=total,
            passed=passed,
        )
        report_dir = project_dir / "reports"
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"chapter_{ch_num:03d}.json"
        report_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        console.print(f"  报告: {report_path}")


def _print_validation(name: str, result):
    """打印校验结果"""
    color = "green" if result.passed else "red"
    icon = "✓" if result.passed else "✗"
    console.print(f"  [{color}]{icon} {name}: {result.score:.1f}/10[/{color}]")
    for v in result.violations:
        sev = v.severity.value if hasattr(v.severity, 'value') else v.severity
        sev_color = {"critical": "red", "warning": "yellow", "info": "dim"}.get(sev, "white")
        console.print(f"    [{sev_color}][{sev}] {v.description}[/{sev_color}]")
        if v.suggestion:
            console.print(f"           → {v.suggestion}")


# ============================================================
# info — 查看项目状态
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
def info(dir: str):
    """查看项目状态"""
    project_dir = Path(dir).resolve()
    mgr = StateManager(project_dir)

    try:
        meta = mgr.load_meta()
    except Exception:
        console.print("[red]找不到项目文件，请先运行 juben init[/red]")
        sys.exit(1)

    characters = mgr.load_characters()
    threads = mgr.load_plot_threads()
    timeline = mgr.load_timeline()

    table = Table(title="🎬 项目状态")
    table.add_column("项目", style="cyan")
    table.add_column("值")

    table.add_row("标题", meta.title)
    table.add_row("题材", meta.genre)
    table.add_row("前提", meta.premise[:60] + "...")
    table.add_row("意外变量", meta.disruption_variable[:60] + "..." if meta.disruption_variable else "未设置")
    table.add_row("目标章节", str(meta.target_chapters))
    table.add_row("已写章节", str(meta.last_chapter_written))
    table.add_row("角色数", str(len(characters)))
    table.add_row("伏笔数", str(len(threads.threads)))
    table.add_row("时间线事件", str(len(timeline.events)))
    table.add_row("算法卡点", str(len(meta.pacing_cards)) + "个")

    console.print(table)

    # 角色列表
    if characters:
        t2 = Table(title="角色")
        t2.add_column("ID")
        t2.add_column("名字")
        t2.add_column("角色")
        t2.add_column("状态")
        for c in characters:
            t2.add_row(c.id, c.name, c.role.value, "✓" if c.state.alive else "✗")
        console.print(t2)


if __name__ == "__main__":
    main()
