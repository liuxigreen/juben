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
@click.option("--high-concept", "high_concept", is_flag=True,
              help="启用高概念模式 (推荐短剧/网文, bootstrap 时生成异常规则+核心画面+持续代价)")
@click.option("--no-high-concept", "no_high_concept", is_flag=True,
              help="显式关闭高概念模式 (即使模板默认启用)")
@click.option("--yes", "-y", is_flag=True, help="跳过确认，直接初始化")
def init(premise: str, template: str, dir: str, mixin: str, skeleton: str,
         timeline_skeleton: str, title: str, disruption: str,
         high_concept: bool, no_high_concept: bool,
         yes: bool):
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

    # === v1.1.2: 高概念模式 (CLI 入口) ===
    # --no-high-concept 显式关闭 > --high-concept 显式开启 > 模板默认
    if no_high_concept and hasattr(result["meta"], "high_concept"):
        result["meta"].high_concept.enabled = False
        console.print("[dim]⚪ 高概念模式已显式关闭[/dim]")
    elif high_concept and hasattr(result["meta"], "high_concept"):
        result["meta"].high_concept.enabled = True
        console.print("[cyan]🧠 高概念模式已启用[/cyan] — bootstrap 时将生成异常规则+核心画面+持续代价")

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

    # === v1.1.1: 自动生成 Stage 2/3 所需的 config/ 目录 ===
    # 若 config/ 已有内容, _init_stage23_config 会 raise (防污染) → 阻断 init
    try:
        _init_stage23_config(project_dir, result, project_name=title or result["meta"].title or "未命名")
    except FileExistsError as e:
        console.print(f"[red]✗ Config 隔离保护触发:[/red]\n{e}")
        sys.exit(1)

    console.print(Panel(
        f"[green]✓ 项目初始化完成[/green]\n\n"
        f"目录: {project_dir}\n"
        f"模板: {template}\n"
        f"主角: {result['characters'][0].name}\n"
        f"前提: {result['meta'].premise[:80]}...\n"
        f"高概念模式: {'🟢 启用 (bootstrap 将生成异常规则)' if getattr(result['meta'], 'high_concept', None) and result['meta'].high_concept.enabled else '⚪ 关闭'}\n\n"
        f"[yellow]下一步:[/yellow]\n"
        f"  1. juben bootstrap --dir {project_dir}  (生成LLM填充prompt)\n"
        f"  2. 把prompt喂给LLM，保存输出为 bootstrap_response.json\n"
        f"  3. juben bootstrap --apply --dir {project_dir}  (应用LLM输出)\n"
        f"  4. juben write 1 --dir {project_dir}  (开始写作)\n"
        f"  5. juben storyboard --dir {project_dir}  (Stage 2: 剧本→分镜)\n"
        f"  6. juben export-prompts --dir {project_dir}  (Stage 3: 分镜→Veo prompt)",
        title="🎬 剧本引擎",
    ))


def _init_stage23_config(project_dir: Path, result: dict, project_name: str,
                          force: bool = False):
    """
    v1.1.1: 自动生成 Stage 2/3 所需的 config/ 目录

    从 projects/_template/config/ 复制 5 个纯配置 (action_rules/beat_triggers/
    hook_templates/prompt_style/events), 并根据 result 中的 characters 自动生成
    正确格式的 characters.yaml (心声咖啡格式: name: {en:..., desc:...}) 和
    locations.yaml。 project_config.yaml 替换 project_name + default_location。

    隔离保证 (v1.1.1-hardened):
      - config/ 已有内容时, 默认 raise ConfigExistsError (防止 cp 错项目)
      - 强制覆盖需传 --force
      - 检测到 template 缺失的 4 个文件时 raise (防止 _template 被破坏)
    """
    import shutil
    import yaml as yaml_lib

    template_dir = Path(__file__).resolve().parent.parent / "projects" / "_template" / "config"
    config_dir = project_dir / "config"

    # === 防污染隔离检查 (v1.1.1-hardened) ===
    REQUIRED_TEMPLATE_FILES = [
        "action_rules.yaml", "beat_triggers.yaml", "hook_templates.yaml",
        "prompt_style.yaml", "events.yaml",
    ]
    missing_tpl = [f for f in REQUIRED_TEMPLATE_FILES if not (template_dir / f).exists()]
    if missing_tpl:
        raise FileNotFoundError(
            f"_template/config 缺失必备文件: {missing_tpl}\n"
            f"路径: {template_dir}\n"
            f"修复: git checkout main -- projects/_template/config/{missing_tpl[0]}"
        )

    if config_dir.exists() and any(config_dir.iterdir()):
        if not force:
            # 列出已有内容, 帮用户判断是否污染
            existing = sorted(p.name for p in config_dir.iterdir())
            raise FileExistsError(
                f"项目 config/ 已有内容 ({len(existing)} 个文件): {existing[:5]}"
                f"{'...' if len(existing) > 5 else ''}\n"
                f"为防污染, _init_stage23_config 默认拒绝覆盖.\n"
                f"强制重建: 传 force=True (CLI: juben init-config --force)"
            )
        console.print(f"[yellow]⚠ --force 模式: 将覆盖 {config_dir} 现有内容[/yellow]")

    config_dir.mkdir(parents=True, exist_ok=True)

    # 1. 复制 5 个纯配置文件 (无项目特异性)
    for fname in REQUIRED_TEMPLATE_FILES:
        src = template_dir / fname
        if src.exists():
            shutil.copy(src, config_dir / fname)

    # 2. 生成 project_config.yaml (替换 project_name + default_location)
    default_loc: str = project_name
    if result.get("characters"):
        char0 = result["characters"][0]
        # 优先用 state.location (Pydantic 对象, 取其 location 字段)
        if hasattr(char0, "state") and hasattr(char0.state, "location"):
            loc_str = char0.state.location
            if loc_str and isinstance(loc_str, str):
                default_loc = loc_str

    pc_template = template_dir / "project_config.yaml"
    if pc_template.exists():
        pc_content = pc_template.read_text(encoding="utf-8")
        pc_content = pc_content.replace("你的剧名", project_name)
        pc_content = pc_content.replace("剧集标题", project_name)
        pc_content = pc_content.replace("揽月阁", default_loc)
        (config_dir / "project_config.yaml").write_text(pc_content, encoding="utf-8")

    # 3. 生成 characters.yaml (心声咖啡格式: name: {en:..., desc:...})
    def _safe_str(v, default=""):
        """防 Pydantic 对象污染 YAML — 递归转 dict/str"""
        if v is None:
            return default
        if isinstance(v, str):
            return v
        # Pydantic BaseModel: dump to dict 然后转字符串描述
        if hasattr(v, "model_dump"):
            try:
                d = v.model_dump()
                # 转成易读的中文描述
                parts = []
                for k, val in d.items():
                    if val is None or val == "" or val == [] or val == {}:
                        continue
                    if isinstance(val, (str, int, float, bool)):
                        parts.append(f"{k}={val}")
                    elif isinstance(val, dict):
                        # 嵌套 dict 扁平化
                        for k2, v2 in val.items():
                            if isinstance(v2, (str, int, float, bool)):
                                parts.append(f"{k}.{k2}={v2}")
                    elif isinstance(val, list):
                        parts.append(f"{k}={','.join(str(x) for x in val)}")
                return "; ".join(parts) if parts else default
            except Exception:
                pass
        return str(v) if v else default

    chars_yaml = {}
    for i, c in enumerate(result.get("characters", [])):
        name = _safe_str(getattr(c, "name", f"角色{i+1}"), f"角色{i+1}")
        en_name = _to_english_name(name)
        role = getattr(c, "role", "supporting")
        # Pydantic enum (继承 str) 用 .value
        role_val = role.value if hasattr(role, "value") and hasattr(role, "_value_") else _safe_str(role, "supporting")
        chars_yaml[name] = {
            "en": en_name,
            "role": role_val,
            "appearance": _safe_str(getattr(c, "appearance", ""), "普通外貌"),
            "personality": _safe_str(getattr(c, "personality", ""), "普通性格"),
            "speech_style": _safe_str(getattr(c, "speech_style", ""), "说话正常"),
            "wardrobe": _safe_str(getattr(c, "wardrobe", ""), "日常服装"),
            "background": _safe_str(getattr(c, "background", ""), "普通背景"),
        }
    (config_dir / "characters.yaml").write_text(
        yaml_lib.dump({"characters": chars_yaml}, allow_unicode=True, sort_keys=False),
        encoding="utf-8"
    )

    # 4. 生成 locations.yaml (默认 1 个: 主角所在)
    loc_name = default_loc if default_loc else project_name
    loc_data = {"locations": {loc_name: {
        "type": "interior",
        "description": loc_name,
        "atmosphere": "日常",
        "props": [],
        "lighting": {"time": "day", "quality": "自然光", "mood": "neutral"},
    }}}
    (config_dir / "locations.yaml").write_text(
        yaml_lib.dump(loc_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8"
    )


# 简化的中→英文名映射 (Veo/Flow 英文名要求)
_EN_NAME_MAP = {
    "林越": "Lin Yue", "周昊": "Zhou Hao", "苏晴": "Su Qing", "陈叔": "Uncle Chen",
    "苏念": "Su Nian", "陈睿": "Chen Rui", "苏远": "Su Yuan", "顾深": "Gu Shen",
    "陆九": "Lu Jiu", "白无垢": "Bai Wugou", "瞎眼先生": "Blind Master",
    "奶奶": "Grandma", "主角": "Protagonist", "反派": "Antagonist", "女配": "Female Lead",
}


def _to_english_name(name: str) -> str:
    """中→英文名映射, 未知则用拼音占位 (Veo 友好)"""
    if name in _EN_NAME_MAP:
        return _EN_NAME_MAP[name]
    # 简单 fallback: 保留中文 + 拼音首字母
    return name


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

        # === v1.1.2: 高概念模式字段验证 ===
        # 启用了高概念模式但 LLM 没填 7 个核心字段 → 警告 (不阻断, 但强烈提示)
        try:
            meta = mgr.load_meta()
            hc = getattr(meta, "high_concept", None)
            if hc and getattr(hc, "enabled", False):
                missing = []
                for field in ["anomaly", "visual_core", "personal_cost", "why_new",
                              "visual_anchor_prop", "visual_anchor_keywords"]:
                    val = getattr(hc, field, None)
                    if not val or (isinstance(val, list) and len(val) == 0):
                        missing.append(field)
                if missing:
                    console.print(f"[yellow]⚠ 高概念模式已启用但 LLM 响应缺字段: {missing}[/yellow]")
                    console.print(f"[yellow]   可手动编辑 story_meta.json 的 high_concept 节点补全, 或重跑 bootstrap[/yellow]")
                else:
                    console.print(f"[green]🧠 高概念模式: 7 字段完整[/green]")
                    console.print(f"   异常: {hc.anomaly[:60]}...")
                    console.print(f"   视觉锚点: {hc.visual_anchor_prop} (关键词: {', '.join(hc.visual_anchor_keywords[:3])})")
        except Exception as e:
            # 验证失败不阻断主流程
            console.print(f"[dim]高概念验证跳过: {e}[/dim]")

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

    # === v1.0+ 可行性检查（防"故事已死但还在写"） ===
    from juben.budget import check_chapter_feasibility
    feasibility = check_chapter_feasibility(project_dir, chapter)
    if not feasibility.feasible:
        # RED: 拒绝生成
        console.print(Panel(
            feasibility.summary() + "\n\n[red]引擎拒绝继续。故事线已耗尽。[/red]",
            title="[red]❌ 第{}章不可行[/red]".format(chapter),
        ))
        sys.exit(1)
    elif feasibility.severity == "YELLOW":
        # YELLOW: 警告但继续
        console.print(f"[yellow]⚠ 可行性检查 - 警告:[/yellow]")
        for w in feasibility.warnings:
            console.print(f"  [yellow]- {w}[/yellow]")
        for s in feasibility.suggestions:
            console.print(f"  [dim]→ {s}[/dim]")

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

        # 加载 story_meta 的 high_concept（用于异常退化检测）
        story_meta_file = project_dir / "story_meta.json"
        high_concept = None
        if story_meta_file.exists():
            _meta = _json.loads(story_meta_file.read_text(encoding="utf-8"))
            high_concept = _meta.get("high_concept")

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
            high_concept=high_concept,
            recent_chapter_texts=previous_texts,
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


# ============================================================
# budget — 查看/管理项目级资源预算（v1.0+）
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--consume", "-c", default="", help="手动记录一次消费: '实体名 章节号'")
def budget(dir: str, consume: str):
    """查看/管理项目级资源预算（实体消耗、角色弧状态、世界符号库）"""
    from juben.budget import StoryBudget, ArcStateTracker, check_chapter_feasibility

    project_dir = Path(dir).resolve()

    if consume:
        # 模式: 手动消费
        parts = consume.split()
        if len(parts) != 2:
            console.print("[red]格式: --consume '实体名 章节号'[/red]")
            sys.exit(1)
        name, ch = parts[0], int(parts[1])
        budget_obj = StoryBudget(project_dir)
        result = budget_obj.consume(name, ch)
        if result["exhausted"]:
            console.print(f"[yellow]⚠ {result['warning']}[/yellow]")
        elif result["warning"]:
            console.print(f"[yellow]⚠ {result['warning']}[/yellow]")
        else:
            console.print(f"[green]✓ 记录消费: {name} 第{ch}章 (剩余{result['remaining']}次)[/green]")
        return

    # 模式: 查看状态
    budget_obj = StoryBudget(project_dir)
    entities = budget_obj.list_all()

    if entities:
        t = Table(title="📊 实体消费预算")
        t.add_column("实体", style="cyan")
        t.add_column("类型")
        t.add_column("配额", justify="right")
        t.add_column("已用", justify="right")
        t.add_column("剩余", justify="right")
        t.add_column("耗尽于")
        t.add_column("备注")

        for e in entities:
            remaining_style = "red" if e["remaining"] <= 0 else ("yellow" if e["remaining"] <= max(1, e["quota"] * 0.2) else "green")
            t.add_row(
                e["name"],
                e["type"],
                str(e["quota"]),
                str(e["consumed"]),
                f"[{remaining_style}]{e['remaining']}[/{remaining_style}]",
                str(e["exhausted_at"]) if e["exhausted_at"] else "-",
                e.get("note", "")[:30],
            )
        console.print(t)
    else:
        console.print("[dim]暂无实体预算数据。请在Curator/Commit时自动注册，或手动 --consume 添加[/dim]")

    # 角色弧状态
    arc_tracker = ArcStateTracker(project_dir)
    chars = arc_tracker._load_characters()
    if chars:
        t2 = Table(title="🎭 角色弧状态")
        t2.add_column("角色", style="cyan")
        t2.add_column("职能")
        t2.add_column("状态")
        t2.add_column("未完成事项", style="dim")
        t2.add_column("解决章节")

        for c in chars:
            arc = c.get("arc") or {}
            state = arc.get("state", "pending")
            state_style = {
                "pending": "dim",
                "active": "cyan",
                "climax": "yellow",
                "resolved": "green",
            }.get(state, "white")
            unfinished = arc.get("unfinished_business", [])
            t2.add_row(
                c.get("name", "?"),
                c.get("role", "?"),
                f"[{state_style}]{state}[/{state_style}]",
                ", ".join(unfinished[:2]) + ("..." if len(unfinished) > 2 else ""),
                str(arc.get("resolved_chapter", "-")),
            )
        console.print(t2)

    # 世界符号库
    try:
        from juben.budget import WorldInventory
        inv = WorldInventory(project_dir)
        all_inv = inv.list_all()
        if all_inv["locations"] or all_inv["symbols"] or all_inv["banned"]:
            t3 = Table(title="🌍 世界符号库")
            t3.add_column("类型", style="cyan")
            t3.add_column("名称")
            t3.add_column("含义/原因")
            t3.add_column("首现")
            for loc in all_inv["locations"]:
                t3.add_row("地点", loc["name"], loc.get("symbol", ""), str(loc.get("first_appear", "?")))
            for sym in all_inv["symbols"]:
                t3.add_row("符号", sym["name"], sym.get("meaning", ""), str(sym.get("first_appear", "?")))
            for b in all_inv["banned"]:
                t3.add_row("[red]禁用[/red]", b["name"], b.get("reason", ""), "-")
            console.print(t3)
    except Exception as e:
        logger.debug(f"world inventory加载失败: {e}")


# ============================================================
# trend — 查看质量趋势
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
def trend(dir: str):
    """查看跨章质量趋势（防"故事已死但单章还9.0"）"""
    from juben.guardian.trend import detect_trend_from_project, load_chapter_audit_history, _lexical_overlap

    project_dir = Path(dir).resolve()
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        console.print("[red]没有找到chapters目录[/red]")
        sys.exit(1)

    # 收集章节
    chapters = []
    for p in sorted(chapters_dir.glob("*.md")):
        try:
            num = int(p.stem)
            text = p.read_text(encoding="utf-8")
            chapters.append({"num": num, "text": text})
        except (ValueError, OSError):
            pass

    if not chapters:
        console.print("[yellow]还没有章节[/yellow]")
        return

    # 计算相邻章的重叠度
    overlap_data = []
    for i in range(1, len(chapters)):
        ov = _lexical_overlap(chapters[i]["text"], chapters[i-1]["text"])
        overlap_data.append((chapters[i]["num"], chapters[i-1]["num"], ov))

    # 趋势判定
    severity = detect_trend_from_project(project_dir)

    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}.get(severity, "white")
    console.print(Panel(
        f"[{color}]{severity}[/{color}] - "
        + {
            "GREEN": "质量正常",
            "YELLOW": "警告: 连续auto-fix或复读趋势",
            "RED": "危险: 故事线已耗尽,建议收尾",
        }.get(severity, ""),
        title="📈 质量趋势",
    ))

    # 显示最近5章的尾部重叠度
    if overlap_data:
        t = Table(title="相邻章尾部重叠度(越低越好)")
        t.add_column("本章", justify="right")
        t.add_column("上一章", justify="right")
        t.add_column("重叠度", justify="right")
        t.add_column("状态")
        for curr, prev, ov in overlap_data[-10:]:
            color_ov = "red" if ov > 0.35 else ("yellow" if ov > 0.30 else "green")
            t.add_row(
                str(curr), str(prev),
                f"[{color_ov}]{ov:.2%}[/{color_ov}]",
                "复读" if ov > 0.35 else ("注意" if ov > 0.30 else "正常"),
            )
        console.print(t)


# ============================================================
# world — 管理世界符号库（注册地点/符号，禁用未建立的）
# ============================================================

@main.group()
def world():
    """管理世界符号库（地理/视觉符号的中央登记簿）"""
    pass


@world.command("register")
@click.argument("kind", type=click.Choice(["location", "symbol"]))
@click.argument("name")
@click.option("--meaning", "-m", default="", help="象征意义")
@click.option("--chapter", "-c", default=0, type=int, help="首现章节")
@click.option("--quota", "-q", default=3, type=int, help="使用配额(仅symbol)")
@click.option("--dir", "-d", default=".", help="项目目录")
def world_register(kind: str, name: str, meaning: str, chapter: int,
                   quota: int, dir: str):
    """注册一个新地点或符号"""
    from juben.budget import WorldInventory
    project_dir = Path(dir).resolve()
    inv = WorldInventory(project_dir)

    if kind == "location":
        inv.register_location(name, symbol_meaning=meaning, first_chapter=chapter)
        console.print(f"[green]✓ 注册地点: {name} (含义: {meaning or '无'})[/green]")
    else:
        inv.register_symbol(name, meaning=meaning, first_chapter=chapter, usage_quota=quota)
        console.print(f"[green]✓ 注册符号: {name} (含义: {meaning or '无'}, 配额: {quota})[/green]")


@world.command("ban")
@click.argument("name")
@click.option("--reason", "-r", default="", help="禁用原因")
@click.option("--dir", "-d", default=".", help="项目目录")
def world_ban(name: str, reason: str, dir: str):
    """禁用一个名称(防止LLM使用)"""
    from juben.budget import WorldInventory
    project_dir = Path(dir).resolve()
    inv = WorldInventory(project_dir)
    inv.ban(name, reason=reason)
    console.print(f"[yellow]✓ 已禁用: {name} (原因: {reason or '未提供'})[/yellow]")


@world.command("unban")
@click.argument("name")
@click.option("--dir", "-d", default=".", help="项目目录")
def world_unban(name: str, dir: str):
    """解除禁用"""
    from juben.budget import WorldInventory
    project_dir = Path(dir).resolve()
    inv = WorldInventory(project_dir)
    inv.unban(name)
    console.print(f"[green]✓ 已解除禁用: {name}[/green]")


@world.command("list")
@click.option("--dir", "-d", default=".", help="项目目录")
def world_list(dir: str):
    """列出所有注册的地点/符号/禁用项"""
    from juben.budget import WorldInventory
    project_dir = Path(dir).resolve()
    inv = WorldInventory(project_dir)
    all_inv = inv.list_all()

    for loc in all_inv["locations"]:
        console.print(f"  📍 [cyan]{loc['name']}[/cyan] - {loc.get('symbol', '')} (ch{loc.get('first_appear', '?')})")
    for sym in all_inv["symbols"]:
        console.print(f"  🔮 [cyan]{sym['name']}[/cyan] - {sym.get('meaning', '')} (ch{sym.get('first_appear', '?')}, 配额{sym.get('usage_quota', '?')})")
    for b in all_inv["banned"]:
        console.print(f"  [red]🚫 {b['name']}[/red] - {b.get('reason', '')}")
    if not (all_inv["locations"] or all_inv["symbols"] or all_inv["banned"]):
        console.print("[dim]空[/dim]")


# ============================================================
# check — 写下一章前的可行性检查（也可直接调用 feasibility）
# ============================================================

@main.command()
@click.argument("chapter", type=int)
@click.option("--dir", "-d", default=".", help="项目目录")
def feasibility(chapter: int, dir: str):
    """写第N章前调用: 综合检查资源预算/角色弧/质量趋势"""
    from juben.budget import check_chapter_feasibility

    project_dir = Path(dir).resolve()
    result = check_chapter_feasibility(project_dir, chapter)

    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}.get(result.severity, "white")
    console.print(Panel(
        result.summary(),
        title=f"[{color}]📋 第{chapter}章可行性检查[/{color}]",
    ))

    if not result.feasible:
        sys.exit(1)


# ============================================================
# storyboard — Stage 2: 剧本 → 分镜 (v1.1.1)
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--chapter", "-c", type=int, default=0, help="指定单章处理 (0=全部)")
def storyboard(dir: str, chapter: int):
    """Stage 2: 将剧本章节转为分镜 (v3_storyboard/chN_shots.json)"""
    from juben.pipeline import run_pipeline

    project_dir = Path(dir).resolve()
    if not (project_dir / "chapters").exists():
        console.print(f"[red]目录 {project_dir} 没有 chapters/ — 不是有效项目[/red]")
        sys.exit(1)

    console.print(f"[cyan]▶ Stage 2: 剧本 → 分镜[/cyan]  项目: {project_dir.name}")
    run_pipeline(project_dir, only_chapter=chapter if chapter > 0 else None)
    console.print(f"[green]✓ 分镜完成 → {project_dir}/v3_storyboard/[/green]")
    console.print(f"[yellow]下一步:[/yellow] juben export-prompts --dir {project_dir}")


# ============================================================
# export-prompts — Stage 3: 分镜 → Veo prompt (v1.1.1)
# ============================================================

@main.command()
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--chapter", "-c", type=int, default=0, help="指定单章导出 (0=全部)")
def export_prompts(dir: str, chapter: int):
    """Stage 3: 将分镜转为 Veo 3.1 专业提示词 (flow_prompts_pro/chN_pro_prompts.md)"""
    from juben.export_pro_prompts import export_professional_prompts

    project_dir = Path(dir).resolve()
    if not (project_dir / "v3_storyboard").exists():
        console.print(f"[red]目录 {project_dir} 没有 v3_storyboard/ — 请先跑 storyboard[/red]")
        sys.exit(1)

    console.print(f"[cyan]▶ Stage 3: 分镜 → Veo prompt[/cyan]  项目: {project_dir.name}")
    export_professional_prompts(project_dir, only_chapter=chapter if chapter > 0 else None)
    console.print(f"[green]✓ Veo prompt 完成 → {project_dir}/flow_prompts_pro/[/green]")
    console.print(f"[yellow]下一步:[/yellow] 把 chNN_pro_prompts.md 喂给 Veo/Flow 生成视频")


# ============================================================
# init-config — 独立重建/校验 config/ (v1.1.1-hardened)
# ============================================================

@main.command("init-config")
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--force", is_flag=True, help="覆盖已有 config/ (会清空再重建)")
def init_config(dir: str, force: bool):
    """独立重建/校验项目的 config/ 目录 (从 _template 复制 + 用 characters.json 填充)

    默认拒绝覆盖已有 config/, 防 cp 错项目污染。 --force 才覆盖。

    防污染: 若 _template/config 缺失必备文件, raise。
    """
    project_dir = Path(dir).resolve()
    if not (project_dir / "characters.json").exists():
        console.print(f"[red]目录 {project_dir} 没有 characters.json — 不是有效项目[/red]")
        sys.exit(1)

    # 读 characters.json 还原 init 时的 result 格式
    with open(project_dir / "characters.json", encoding="utf-8") as f:
        chars_data = json.load(f)
    meta_data = {}
    if (project_dir / "story_meta.json").exists():
        with open(project_dir / "story_meta.json", encoding="utf-8") as f:
            meta_data = json.load(f)

    # 模拟 init 时的 result 格式 (StateManager 风格)
    class _Wrap:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
    characters = [_Wrap(c) for c in chars_data.get("characters", [])]
    project_name = meta_data.get("title", project_dir.name)
    result = {
        "meta": _Wrap(meta_data),
        "characters": characters,
    }

    if force and (project_dir / "config").exists():
        import shutil
        shutil.rmtree(project_dir / "config")
        console.print(f"[yellow]⚠ --force: 已清空 {project_dir / 'config'}[/yellow]")

    try:
        _init_stage23_config(project_dir, result, project_name=project_name, force=force)
    except FileExistsError as e:
        console.print(f"[red]✗ Config 隔离保护触发:[/red]\n{e}")
        sys.exit(1)

    console.print(f"[green]✓ config/ 已生成[/green]  路径: {project_dir / 'config'}")
    console.print(f"[yellow]下一步:[/yellow] juben storyboard --dir {project_dir}")


# ============================================================
# lint-config — 防污染检查 (v1.1.1-hardened)
# ============================================================

@main.command("lint-config")
@click.option("--dir", "-d", default=".", help="项目目录")
@click.option("--strict", is_flag=True, help="把警告也当错误退出")
def lint_config(dir: str, strict: bool):
    """检查项目 config/ 是否与 characters.json 角色一致, 是否存在跨项目污染

    检查项 (v1.1.1-hardened):
      1. config/characters.yaml 的角色名 ⊆ characters.json 的角色名 (中文)
      2. config/locations.yaml 的场景名不在 characters.json 里 (说明是别的项目漏的)
      3. config/characters.yaml 的 en 字段映射合规
      4. _template/config 5 个必备文件全在

    退出码: 0=OK, 1=有错误, 2=有警告 (--strict 时)
    """
    import yaml as yaml_lib

    project_dir = Path(dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    # 1. characters.json 是事实源
    chars_json_path = project_dir / "characters.json"
    valid_names: set[str] = set()  # 提前初始化, 防止 unbound 警告
    json_main_names: set[str] = set()  # 仅主名 (不含 aliases) — 用于 missing 判断
    if not chars_json_path.exists():
        errors.append(f"缺少 characters.json (项目未 bootstrap 完成)")
    else:
        with open(chars_json_path, encoding="utf-8") as f:
            chars_json = json.load(f)
        json_main_names = {c["name"] for c in chars_json.get("characters", [])}
        valid_names = set(json_main_names)
        # 也接受 aliases
        for c in chars_json.get("characters", []):
            for alias in c.get("aliases", []):
                valid_names.add(alias)

    # 2. config/characters.yaml 检查
    chars_yaml_path = project_dir / "config" / "characters.yaml"
    if not chars_yaml_path.exists():
        errors.append(f"缺少 {chars_yaml_path} (Stage 2 找不到角色映射)")
    else:
        with open(chars_yaml_path, encoding="utf-8") as f:
            chars_yaml = yaml_lib.safe_load(f) or {}
        # 支持两种格式: {name: {...}} 或 {characters: {name: {...}}}
        if "characters" in chars_yaml and isinstance(chars_yaml["characters"], dict):
            yaml_chars = chars_yaml["characters"]
        else:
            yaml_chars = chars_yaml
        yaml_names = set(yaml_chars.keys())

        if chars_json_path.exists():
            # yaml 里的角色必须都在 characters.json 里 (主名 + aliases)
            extra = yaml_names - valid_names
            if extra:
                errors.append(
                    f"config/characters.yaml 含 characters.json 外的角色: {sorted(extra)}\n"
                    f"   极可能是 cp 错项目 (心声咖啡污染神算子就是这个症状)\n"
                    f"   修复: juben init-config --dir {project_dir} --force"
                )
            # missing 只检查主名 (aliases 未必进 yaml, 不算缺)
            missing = json_main_names - yaml_names
            if missing:
                warnings.append(
                    f"characters.json 有但 config/characters.yaml 缺主名: {sorted(missing)}\n"
                    f"   修复: juben init-config --dir {project_dir} --force"
                )

    # 3. _template 必备文件检查
    template_dir = project_dir.parent / "_template" / "config"
    if not template_dir.exists():
        errors.append(f"_template/config 不存在: {template_dir}")
    else:
        for fname in ["action_rules.yaml", "beat_triggers.yaml", "hook_templates.yaml",
                      "prompt_style.yaml", "events.yaml"]:
            if not (template_dir / fname).exists():
                errors.append(f"_template/config 缺 {fname} (init 会失败)")

    # 4. 输出
    if errors:
        for e in errors:
            console.print(f"[red]✗ {e}[/red]")
    if warnings:
        for w in warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

    if errors:
        console.print(f"\n[red]FAIL: {len(errors)} 错误, {len(warnings)} 警告[/red]")
        sys.exit(1)
    if warnings and strict:
        console.print(f"\n[yellow]WARN (strict): {len(warnings)} 警告[/yellow]")
        sys.exit(2)
    console.print(f"[green]✓ config lint OK ({len(warnings)} 警告)[/green]")


if __name__ == "__main__":
    main()