"""
心声咖啡 分镜重生成 driver（agent-as-LLM 语义版）

架构：
    beats_src/chNNN.json  (主agent语义提取的干净beats)
        ↓
    ShotCompiler   (景别/运镜/光影/时长, pipeline.py)
        ↓
    PromptRenderer (英文槽位化prompt, pipeline.py)
        ↓
    StoryboardLint (7项质量门禁, storyboard_lint.py)
        ↓
    v3_storyboard/chNNN_shots.json + chNNN_beats.json
    srt_subtitles/chNNN.srt

为什么用 agent-as-LLM 语义 beats：
    pipeline.py 原生 BeatExtractor 用正则+代词匹配，导致 3 个 bug：
      ① 代词"他/她"全匹配 → 同性别角色串场
      ② 读心/心声正则去重不足 → 同章重复镜头
      ③ 无"回忆/提及"过滤 → 被提及的角色(如外婆)误判在场
    语义 beats 由主 agent 逐章阅读原文产出，characters_present 精确到
    "谁真的在画面里"，从源头消除 bug。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "juben"))
from juben.pipeline import load_config, ShotCompiler, PromptRenderer, HookManager, generate_srt
from juben.storyboard_lint import StoryboardLint

PROJECT_DIR = Path.home() / "juben/projects/心声咖啡"


def run(project_dir: Path = PROJECT_DIR, chapters: range = range(1, 21)):
    cfg = load_config(project_dir)
    compiler = ShotCompiler(cfg)
    renderer = PromptRenderer(cfg)
    hook = HookManager(cfg)
    lint = StoryboardLint()

    default_loc = cfg.get("default_location", "")
    loc_map = cfg.get("locations", {})
    if isinstance(loc_map, dict):
        loc_map = {k: v for k, v in loc_map.items() if isinstance(v, str)}

    src_dir = project_dir / "beats_src"
    out = project_dir / "v3_storyboard"
    srt_dir = project_dir / "srt_subtitles"
    out.mkdir(exist_ok=True)
    srt_dir.mkdir(exist_ok=True)

    char_cfg = cfg.get("characters", {})
    # 允许 beats 里用中文名或英文名；统一转英文
    zh_to_en = {zh: info.get("en", zh) for zh, info in char_cfg.items() if isinstance(info, dict)}

    results = []
    for ch in chapters:
        src_file = src_dir / f"ch{ch:03d}.json"
        if not src_file.exists():
            continue
        beats = json.loads(src_file.read_text(encoding="utf-8"))

        # 场景位置检测（从 beats 的 location 字段或默认）
        loc = beats[0].get("location", default_loc) if beats else default_loc

        # 规范化：characters_present / primary_char / dialogue_speaker 统一转英文
        for b in beats:
            b["characters_present"] = [zh_to_en.get(c, c) for c in b.get("characters_present", [])]
            if b.get("primary_char"):
                b["primary_char"] = zh_to_en.get(b["primary_char"], b["primary_char"])
            if b.get("dialogue_speaker"):
                b["dialogue_speaker"] = zh_to_en.get(b["dialogue_speaker"], b["dialogue_speaker"])

        shots = compiler.compile(beats, 90, loc)
        renderer.reset()
        for shot in shots:
            bd = beats[shot["shot_id"] - 1] if shot["shot_id"] <= len(beats) else {}
            # per-shot location: 多场景章节(面馆/巷子/公园)从beat读，否则用章节默认
            shot_loc = bd.get("location", loc)
            shot["location"] = shot_loc
            # characters 已是英文（来自 beats_src），PromptRenderer 直接用
            # voice_type 供渲染器做口型/音轨控制（onscreen嘴动/inner_voice锁嘴/none锁嘴）
            shot["voice_type"] = bd.get("voice_type", "none")
            shot["dialogue_speaker"] = bd.get("dialogue_speaker", "")
            # 英文台词(出海配音)：onscreen取line_en，inner_voice取inner_voice_en
            vt = bd.get("voice_type", "none")
            if vt == "inner_voice":
                shot["line_en"] = bd.get("inner_voice_en", "")
            else:
                shot["line_en"] = bd.get("line_en", "")
            shot["veo_prompt"] = renderer.render(shot, shot_loc)
            shot["audio"] = {
                "dialogue_zh": bd.get("spoken_dialogue", ""),
                "dialogue_speaker": bd.get("dialogue_speaker", ""),
                "voiceover_zh": bd.get("inner_voice", ""),
                "line_en": shot["line_en"],
                "voice_type": bd.get("voice_type", "none"),
                "subtitle": bd.get("inner_voice", "")[:30] if bd.get("inner_voice") else "",
                "emotion_tag": compiler.voice_emotion.get(shot.get("emotion", "Neutral"), "calm"),
                "duration_hint": f"{shot['duration']:.1f}s",
            }
        hook.apply(shots)

        # 质量门禁（多场景章节：用每个镜头自己的 location 校验，避免误报）
        scene_locations = {i: shots[i].get("location", loc) for i in range(len(shots))}
        violations = lint.check(shots, scene_locations)
        errors = [v for v in violations if v.severity == "error"]
        warns = [v for v in violations if v.severity == "warning"]

        (out / f"ch{ch:03d}_shots.json").write_text(
            json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / f"ch{ch:03d}_beats.json").write_text(
            json.dumps(beats, ensure_ascii=False, indent=2), encoding="utf-8")
        generate_srt(shots, srt_dir / f"ch{ch:03d}.srt")

        td = sum(s["duration"] for s in shots)
        status = "FAIL" if errors else ("WARN" if warns else "PASS")
        results.append((ch, len(shots), round(td), status, len(errors), len(warns)))
        print(f"Ch{ch:>2}: {len(shots):>2}S {td:>3.0f}s  Lint:{status} (E:{len(errors)} W:{len(warns)})", flush=True)
        if errors:
            for v in errors:
                print(f"       ERROR Shot{v.shot_id} [{v.rule}] {v.message}", flush=True)

    n = len(results)
    if n:
        print("=" * 56)
        passed = sum(1 for r in results if r[3] == "PASS")
        print(f"{n} chapters | {sum(r[1] for r in results)} shots | Lint PASS: {passed}/{n}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        chs = range(int(args[0]), int(args[1]) + 1) if len(args) == 2 else range(int(args[0]), int(args[0]) + 1)
        run(chapters=chs)
    else:
        run()
