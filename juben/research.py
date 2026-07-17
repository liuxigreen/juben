"""
Research模块 — Exa驱动的题材调研

核心逻辑：
- 搜索题材相关的爆款分析、观众反馈、市场趋势
- 提取关键洞察（什么元素火、什么元素烂）
- 保存为结构化报告，供bootstrap prompt注入

依赖：
- Exa API (EXA_API_KEY环境变量)
- 如果Exa不可用，降级为纯LLM推断（不阻断流程）
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _exa_search(query: str, num_results: int = 8) -> list[dict]:
    """
    调用Exa API搜索。

    Returns:
        [{"title": "", "url": "", "text": ""}, ...]

    失败时返回空列表（不抛异常）。
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        logger.warning("EXA_API_KEY未设置，跳过联网搜索")
        return []

    try:
        # 尝试import exa-py SDK
        from exa_py import Exa
        client = Exa(api_key=api_key)
        response = client.search(
            query,
            num_results=num_results,
            contents={"highlights": True},
        )
        results = []
        for r in (response.results or []):
            highlights = r.highlights or []
            results.append({
                "title": r.title or "",
                "url": r.url or "",
                "text": " ".join(highlights) if highlights else "",
            })
        return results
    except ImportError:
        # SDK没装，降级为curl
        pass
    except Exception as e:
        logger.warning(f"Exa SDK调用失败: {e}，尝试curl降级")
        pass

    # curl降级
    try:
        cmd = [
            "curl", "-s", "https://api.exa.ai/search",
            "-H", f"x-api-key: {api_key}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "query": query,
                "numResults": num_results,
                "type": "auto",
            }),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            logger.warning(f"Exa curl失败: {proc.stderr}")
            return []
        data = json.loads(proc.stdout)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "text": r.get("text", "")[:500],
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        logger.warning(f"Exa curl降级失败: {e}")
        return []


def _exa_fetch_contents(urls: list[str], max_chars: int = 8000) -> list[dict]:
    """抓取URL的完整内容"""
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key or not urls:
        return []

    try:
        from exa_py import Exa
        client = Exa(api_key=api_key)
        response = client.get_contents(urls[:4], text=True)  # Exa限制每次最多4个
        return [
            {
                "url": r.url or "",
                "title": r.title or "",
                "content": (r.text or "")[:max_chars],
            }
            for r in (response.results or [])
        ]
    except Exception as e:
        logger.warning(f"Exa内容抓取失败: {e}")
        return []


def research_genre(
    query: str,
    project_dir: Optional[Path] = None,
    fetch_top_n: int = 2,
) -> dict:
    """
    执行题材调研。

    Args:
        query: 搜索查询（如 "天命女相 抖音短剧 爆款元素"）
        project_dir: 项目目录（用于保存报告）
        fetch_top_n: 抓取前N条结果的完整内容

    Returns:
        {
            "query": str,
            "results": [...],
            "fetched": [...],
            "report_path": str or None,
        }
    """
    # Step 1: 搜索
    results = _exa_search(query)

    # Step 2: 抓取top N的完整内容
    fetched = []
    if results and fetch_top_n > 0:
        top_urls = [r["url"] for r in results[:fetch_top_n] if r.get("url")]
        fetched = _exa_fetch_contents(top_urls)

    # Step 3: 保存报告
    report_path = None
    if project_dir:
        report_dir = project_dir / "research"
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = query.replace(" ", "_")[:30]
        filename = f"{timestamp}_{safe_query}.json"
        report_path = report_dir / filename

        report = {
            "query": query,
            "timestamp": timestamp,
            "search_results": results,
            "fetched_contents": fetched,
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"调研报告已保存: {report_path}")

    return {
        "query": query,
        "results": results,
        "fetched": fetched,
        "report_path": str(report_path) if report_path else None,
    }


def format_research_report(research: dict) -> str:
    """将调研结果格式化为人类可读的报告"""
    lines = [
        "═" * 50,
        f"  调研报告: {research['query']}",
        "═" * 50,
        "",
    ]

    results = research.get("results", [])
    if not results:
        lines.append("⚠️ 未找到搜索结果（Exa API可能未配置）")
        return "\n".join(lines)

    lines.append(f"📊 搜索结果: {len(results)} 条\n")

    for i, r in enumerate(results, 1):
        lines.append(f"  {i}. 【{r.get('title', '无标题')}】")
        lines.append(f"     {r.get('url', '')}")
        text = r.get('text', '')
        if text:
            lines.append(f"     {text[:200]}...")
        lines.append("")

    fetched = research.get("fetched", [])
    if fetched:
        lines.append(f"\n📖 深度抓取: {len(fetched)} 篇\n")
        for f in fetched:
            lines.append(f"  【{f.get('title', '')}】")
            content = f.get('content', '')[:500]
            lines.append(f"  {content}...")
            lines.append("")

    if research.get("report_path"):
        lines.append(f"\n💾 完整报告: {research['report_path']}")

    return "\n".join(lines)


def compile_research_for_bootstrap(project_dir: Path) -> str:
    """
    将项目目录下的所有调研报告编译为一段文本，
    供bootstrap prompt注入。

    Returns:
        格式化的文本，可直接嵌入prompt
    """
    research_dir = project_dir / "research"
    if not research_dir.exists():
        return ""

    insights = []
    for f in sorted(research_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            query = data.get("query", "")
            results = data.get("search_results", [])

            insight = f"## 调研: {query}\n"
            for r in results[:5]:
                title = r.get("title", "")
                text = r.get("text", "")
                if title or text:
                    insight += f"- 【{title}】{text[:150]}\n"

            # 也加入深度抓取的摘要
            for fc in data.get("fetched_contents", [])[:2]:
                content = fc.get("content", "")
                if content:
                    # 取前300字作为摘要
                    insight += f"\n### {fc.get('title', '')} 摘要:\n{content[:300]}...\n"

            insights.append(insight)
        except Exception as e:
            logger.warning(f"读取调研报告失败 {f}: {e}")

    if not insights:
        return ""

    return (
        "## 市场调研结果（来自Exa联网搜索）\n\n"
        "以下是从真实市场数据中提取的洞察，请在设计角色和世界观时参考：\n\n"
        + "\n---\n\n".join(insights)
    )
