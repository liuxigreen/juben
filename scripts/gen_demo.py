#!/usr/bin/env python3
"""
生成重生复仇demo数据 — 用于验证和测试
"""
import json
import sys
from pathlib import Path

# 把项目根目录加入path
sys.path.insert(0, str(Path(__file__).parent.parent))

from juben.genre_templates.rebirth_revenge import init_rebirth_revenge


def main():
    result = init_rebirth_revenge()
    demo_dir = Path(__file__).parent / "rebirth_demo"
    demo_dir.mkdir(exist_ok=True)

    for sub in ["chapters", "outlines", "reports"]:
        (demo_dir / sub).mkdir(exist_ok=True)

    # 保存story_meta.json
    meta = result["meta"]
    (demo_dir / "story_meta.json").write_text(
        json.dumps(meta.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存characters.json
    chars = result["characters"]
    (demo_dir / "characters.json").write_text(
        json.dumps({"characters": [c.model_dump() for c in chars]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存world_rules.json
    world = result["world_rules"]
    (demo_dir / "world_rules.json").write_text(
        json.dumps(world.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存空的timeline/relationships/plot_threads
    (demo_dir / "timeline.json").write_text(
        json.dumps({"events": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (demo_dir / "relationships.json").write_text(
        json.dumps({"relationships": [], "info_asymmetry": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (demo_dir / "plot_threads.json").write_text(
        json.dumps({"threads": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✓ Demo数据已生成到 {demo_dir}")
    print(f"  主角: {chars[0].name}")
    print(f"  反派: {chars[1].name}")
    print(f"  意外变量: {meta.disruption_variable[:60]}...")
    print(f"  算法卡点: {len(meta.pacing_cards)}个")
    print(f"  反套路黑名单: {len(world.anti_cliche_blacklist)}条")


if __name__ == "__main__":
    main()
