"""
导出Google Flow逐镜头提示词
从分镜数据生成可直接粘贴到Flow的提示词
"""
import json
from pathlib import Path

# 角色名→Flow引用名
CHAR_REF = {
    "Su Nian": "@Su_Nian",
    "Gu Shen": "@Gu_Shen",
    "Lin Ke": "@Lin_Ke",
    "Chen Rui": "@Chen_Rui",
    "Su Yuan": "@Su_Yuan",
    "grandmother": "@Grandmother",
}

# 景别→Flow camera
CAMERA_MAP = {
    "static": "static camera",
    "push": "slow dolly forward",
    "pull": "slow dolly backward",
    "rapid_push": "rapid push-in",
    "handheld": "handheld camera",
}

def export_flow_prompts(project_dir: Path):
    d = project_dir / "v3_storyboard"
    out_dir = project_dir / "flow_prompts"
    out_dir.mkdir(exist_ok=True)
    
    for ch in range(1, 21):
        shots_file = d / f"ch{ch:03d}_shots.json"
        if not shots_file.exists():
            continue
        
        shots = json.loads(shots_file.read_text(encoding="utf-8"))
        lines = []
        lines.append(f"# 第{ch}章 — Google Flow提示词")
        lines.append(f"# 共{len(shots)}个镜头，{sum(s['duration'] for s in shots):.0f}秒")
        lines.append("")
        lines.append("## 操作顺序")
        lines.append("1. 创建/引用角色（@Su_Nian, @Gu_Shen等）")
        lines.append("2. 添加场景Ingredient（咖啡店/面馆/巷子）")
        lines.append("3. 逐镜头生成，满意后Add to Scene")
        lines.append("4. 用Jump To连接相邻镜头")
        lines.append("5. 下载Scene")
        lines.append("")
        
        for s in shots:
            sid = s["shot_id"]
            st = s.get("shot_type", "MS")
            dur = s["duration"]
            cam = CAMERA_MAP.get(s.get("camera_movement", "static"), "static camera")
            action = s.get("action_visual", "")
            chars = s.get("characters", [])
            focus = s.get("focus_object", "")
            emotion = s.get("emotion", "Neutral")
            audio = s.get("audio", {})
            dlg = audio.get("dialogue_zh", "")
            voice = audio.get("voiceover_zh", "")
            
            # 构建Flow提示词
            char_refs = " ".join(CHAR_REF.get(c, c) for c in chars)
            
            prompt_parts = []
            # 景别+运镜
            shot_en = {"ECU": "extreme close-up", "CU": "close-up", "MCU": "medium close-up",
                       "MS": "medium shot", "WS": "wide shot"}.get(st, "medium shot")
            prompt_parts.append(f"{shot_en}")
            # 动作
            if action:
                prompt_parts.append(action)
            # 角色
            if char_refs:
                prompt_parts.append(f"featuring {char_refs}")
            # 焦点物
            if focus:
                prompt_parts.append(f"detail on {focus}")
            # 场景
            prompt_parts.append("in Nianxiang coffee shop, 9:16 vertical, cinematic")
            
            flow_prompt = ", ".join(prompt_parts)
            
            lines.append(f"--- Shot {sid} [{st}] {dur}s ---")
            lines.append(f"Camera: {cam}")
            lines.append(f"Prompt:")
            lines.append(f"  {flow_prompt}")
            if dlg:
                lines.append(f"Audio (dialogue): {dlg}")
            if voice:
                lines.append(f"Audio (voiceover): {voice}")
            lines.append("")
        
        # 写文件
        (out_dir / f"ch{ch:03d}_flow_prompts.md").write_text(
            "\n".join(lines), encoding="utf-8")
    
    print(f"Exported to {out_dir}")


if __name__ == "__main__":
    export_flow_prompts(Path.home() / "juben/projects/心声咖啡")
