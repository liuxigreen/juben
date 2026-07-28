#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《心声咖啡》Flow提示词使用指南单文件网页。
数据源：v3_storyboard/ch*_shots.json（带口型/音轨控制的最新输出）。
工作流：先在 Flow 建 6 个角色(Ingredient) → 每镜头复制 veo_prompt 并选中对应角色 → 剪映拼接配中文字幕/配音。
打开 index.html 即可，无需服务器。"""
import json, html, os, yaml

BASE = os.path.dirname(os.path.abspath(__file__))
SB_DIR = os.path.join(BASE, "v3_storyboard")
CHAR_YAML = os.path.join(BASE, "config", "characters.yaml")
OUT = os.path.join(BASE, "index.html")

# ---------- 人物定妆（flow_portrait） ----------
with open(CHAR_YAML, encoding="utf-8") as f:
    chars = yaml.safe_load(f)

# ---------- 每章镜头（JSON） ----------
def load_chapter(i):
    p = os.path.join(SB_DIR, f"ch{i:03d}_shots.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        shots = json.load(f)
    # 只收录已用新流程(含口型/音轨控制)生产的章节；旧版无此标记，跳过
    joined = " ".join(s.get("veo_prompt", "") for s in shots)
    if "no music" not in joined and "lips closed" not in joined:
        return None
    return shots

chapters = []
for i in range(1, 21):
    shots = load_chapter(i)
    if shots:
        chapters.append({"num": i, "shots": shots})

total_shots = sum(len(c["shots"]) for c in chapters)

# ---------- HTML 构建 ----------
def esc(s): return html.escape(str(s or ""))

# Flow 时长只有 4/6/8 秒三档，把剧情时长吸附到最近档
def snap_dur(d):
    try: d = float(d)
    except: return "8"
    return "4" if d <= 5 else ("6" if d <= 7 else "8")

VOICE_BADGE = {
    "onscreen":   ("🗣 说英文台词", "vspeak"),
    "inner_voice":("🧠 心声·英文旁白", "vinner"),
    "none":       ("🤐 无台词·锁嘴", "vnone"),
}

SIZE_CN = {"ECU":"大特写","CU":"特写","MCU":"中近景","MS":"中景","WS":"远景"}

role_cn = {"protagonist": "主角", "antagonist": "反派", "supporting": "配角",
           "supporting_antagonist": "反派", "": ""}

# --- 角色卡 ---
char_cards = ""
for name, info in chars.items():
    if not isinstance(info, dict):
        continue
    en = info.get("en", "")
    portrait = info.get("flow_portrait", "") or info.get("short", "")
    voice = info.get("flow_voice", "")
    role = role_cn.get(info.get("role", ""), info.get("role", ""))
    voice_block = f"""
      <div class="vlabel">🔊 声音描述（填进 Flow「自定义声音效果」）</div>
      <div class="prow">
        <pre>{esc(voice)}</pre>
        <button class="copy" onclick="cp(this, this.previousElementSibling.textContent)">📋 复制声音</button>
      </div>""" if voice else ""
    char_cards += f"""<div class="ccard">
      <div class="chead">
        <span class="cn">{esc(name)}</span>
        <span class="cen">🎬 Flow 命名：<b>{esc(en)}</b></span>
        <span class="badge">{esc(role)}</span>
      </div>
      <div class="vlabel">🎨 定妆提示词（生成角色参考图）</div>
      <div class="prow">
        <pre id="c_{esc(en).replace(' ','_')}">{esc(portrait)}</pre>
        <button class="copy" onclick="cp(this, this.previousElementSibling.textContent)">📋 复制定妆</button>
      </div>{voice_block}
    </div>"""

nav = "".join(f'<a href="#ch{c["num"]}">第{c["num"]}章</a>' for c in chapters)

# --- 章节镜头 ---
ch_html = ""
for c in chapters:
    rows = ""
    for s in c["shots"]:
        sid = s.get("shot_id")
        size = s.get("shot_type", "")
        dur = s.get("duration", "")
        fdur = snap_dur(dur)
        emo = s.get("emotion", "")
        vt = s.get("voice_type", "none")
        vbadge, vcls = VOICE_BADGE.get(vt, VOICE_BADGE["none"])
        chars_in = "、".join(s.get("characters", []))
        au = s.get("audio", {})
        dlg_zh = au.get("dialogue_zh", "")
        vo_zh = au.get("voiceover_zh", "")
        line_en = au.get("line_en", "")
        spk = au.get("dialogue_speaker", "")
        line_html = ""
        if line_en:
            tag_cn = "🇬🇧 英文台词" if dlg_zh else "🇬🇧 英文旁白"
            line_html += f'<div class="dlg en">{tag_cn}（{esc(spk)}）：{esc(line_en)}</div>'
        if dlg_zh:
            line_html += f'<div class="dlg">🀄 中文原台词：{esc(dlg_zh)}</div>'
        if vo_zh:
            line_html += f'<div class="dlg vo">🀄 中文原心声：{esc(vo_zh)}</div>'
        char_html = f'<span class="tag ch">🎭 {esc(chars_in)}</span>' if chars_in else ""
        pid = f'p{c["num"]}_{sid}'
        rows += f"""<div class="shot">
      <div class="shead">
        <span class="snum">Shot {sid}</span>
        <span class="tag size">{esc(size)} {SIZE_CN.get(size,'')}</span>
        <span class="tag fdur">⏱ {fdur}s档</span>
        <span class="tag emo">{esc(emo)}</span>
        <span class="tag {vcls}">{vbadge}</span>
        {char_html}
      </div>
      {line_html}
      <div class="prow">
        <pre id="{pid}">{esc(s.get('veo_prompt',''))}</pre>
        <button class="copy" onclick="cp(this, document.getElementById('{pid}').textContent)">📋 复制</button>
      </div>
    </div>"""
    ch_html += f"""<section id="ch{c['num']}" class="chapter">
      <h2>第 {c['num']} 章 <span class="cmeta">{len(c['shots'])} 个镜头</span></h2>
      {rows}
    </section>"""

page = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>《心声咖啡》Flow提示词使用指南</title>
<style>
  :root {{ --bg:#0f1115; --card:#1a1d24; --line:#2a2e38; --txt:#e6e8ec; --dim:#9aa0aa; --acc:#e0a86a; --acc2:#6ab0e0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--txt); line-height:1.6; }}
  header {{ padding:28px 20px; background:linear-gradient(135deg,#1a1d24,#22262f); border-bottom:1px solid var(--line); }}
  h1 {{ margin:0 0 6px; font-size:24px; }}
  .sub {{ color:var(--dim); font-size:14px; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:20px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px; margin:16px 0; }}
  h2 {{ font-size:20px; border-left:4px solid var(--acc); padding-left:10px; margin:28px 0 14px; }}
  h3 {{ font-size:16px; color:var(--acc2); }}
  .cmeta {{ font-size:13px; color:var(--dim); font-weight:normal; }}
  ol.steps {{ padding-left:20px; }}
  ol.steps li {{ margin:10px 0; }}
  .kbd {{ background:#000; border:1px solid var(--line); border-radius:5px; padding:1px 7px; font-size:13px; color:var(--acc); }}
  .ccard {{ background:#14171d; border:1px solid var(--line); border-radius:10px; padding:14px; margin:12px 0; }}
  .chead {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:8px; }}
  .cn {{ font-weight:bold; font-size:16px; }}
  .cen {{ color:var(--dim); font-size:13px; }}
  .cen b {{ color:var(--acc); }}
  .badge {{ background:#2a2e38; border-radius:20px; padding:2px 10px; font-size:12px; color:var(--acc); }}
  .vlabel {{ font-size:12px; color:var(--dim); margin:10px 0 4px; }}
  nav {{ position:sticky; top:0; background:rgba(15,17,21,.95); backdrop-filter:blur(8px); border-bottom:1px solid var(--line); padding:10px; z-index:10; overflow-x:auto; white-space:nowrap; }}
  nav a {{ color:var(--dim); text-decoration:none; padding:4px 9px; font-size:13px; border-radius:6px; }}
  nav a:hover {{ background:var(--card); color:var(--acc); }}
  .shot {{ background:#14171d; border:1px solid var(--line); border-radius:10px; padding:14px; margin:12px 0; }}
  .shead {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }}
  .snum {{ font-weight:bold; color:var(--acc); margin-right:4px; }}
  .tag {{ background:#22262f; border-radius:5px; padding:2px 8px; font-size:12px; color:var(--dim); }}
  .tag.size {{ background:#2d2416; color:var(--acc); }}
  .tag.fdur {{ background:#1a2b1a; color:#8fd18f; }}
  .tag.emo {{ background:#162a2d; color:var(--acc2); }}
  .tag.ch {{ background:#2a1d2d; color:#d0a0e0; }}
  .tag.vspeak {{ background:#2d2416; color:#e0c060; }}
  .tag.vinner {{ background:#1d1d2d; color:#9090e0; }}
  .tag.vnone {{ background:#22262f; color:var(--dim); }}
  .dlg {{ background:#1e2530; border-left:3px solid var(--acc2); padding:6px 10px; border-radius:5px; font-size:14px; margin-bottom:8px; }}
  .dlg.vo {{ border-left-color:#9090e0; }}
  .dlg.en {{ background:#1a2a1e; border-left-color:#5fd18f; color:#d8f0e0; font-weight:500; }}
  .prow {{ position:relative; }}
  pre {{ background:#0b0d11; border:1px solid var(--line); border-radius:8px; padding:12px 14px; padding-right:80px; white-space:pre-wrap; word-break:break-word; font-size:13px; margin:0; font-family:ui-monospace,Menlo,Consolas,monospace; color:#cdd3db; }}
  .copy {{ position:absolute; top:8px; right:8px; background:var(--acc); color:#000; border:none; border-radius:6px; padding:6px 10px; font-size:12px; cursor:pointer; font-weight:bold; }}
  .copy:hover {{ opacity:.85; }}
  .copy.done {{ background:#4caf50; color:#fff; }}
  .warn {{ background:#2a2216; border:1px solid #4a3a1e; border-radius:8px; padding:12px 14px; font-size:14px; }}
  .info {{ background:#16242a; border:1px solid #1e3a44; border-radius:8px; padding:12px 14px; font-size:14px; margin-top:12px; }}
  .top {{ position:fixed; bottom:20px; right:20px; background:var(--acc); color:#000; border:none; border-radius:50%; width:46px; height:46px; font-size:20px; cursor:pointer; box-shadow:0 4px 12px rgba(0,0,0,.4); }}
</style>
</head>
<body>
<header>
  <div class="wrap" style="padding:0">
    <h1>☕ 《心声咖啡》Flow 提示词使用指南</h1>
    <div class="sub">竖屏短剧 · {len(chapters)}章 · 共 {total_shots} 个镜头 · Google Veo 3.1 (Flow 网页版)</div>
  </div>
</header>

<nav><a href="#howto">📖 怎么用</a><a href="#chars">🎭 先建角色</a>{nav}</nav>

<div class="wrap">

<section id="howto" class="card">
  <h2>📖 怎么用（重要！先看这里）</h2>
  <ol class="steps">
    <li><b>第一步 · 建角色（只做一次）</b>：打开 <span class="kbd">Google Flow</span>（labs.google/flow），在 <b>Ingredients / 角色</b> 里为 6 个角色各建一个，粘贴下面「🎭 先建角色」区的<b>定妆提示词</b>生成参考图，命名用<b>英文名</b>（Su Nian、Gu Shen…，<b>必须一字不差</b>）。</li>
    <li><b>第二步 · 逐镜头生成</b>：找到章节里的镜头，点 <span class="kbd">📋 复制</span> 复制提示词，粘贴到 Flow，<b>选中该镜头出现的角色 Ingredient</b>，模型选 <b>Veo 3.1</b>、比例 <b>9:16 竖屏</b>、时长按镜头上的 <span class="kbd">⏱ x秒档</span>，生成。</li>
    <li><b>第三步 · 后期</b>：镜头导入 <b>剪映</b> 按顺序拼接。英文语音 Veo 已生成好，<b>无需再配音</b>；只需加 <b>英文字幕</b>（SRT 在 <span class="kbd">srt_subtitles/</span>，用于 YouTube CC）+ 音乐/音效。想做中文版就另配中文音轨。</li>
  </ol>
  <div class="warn">
    <b>🌍 出海模式：Veo 直接出美式英文配音</b><br>
    这是英文出海版，<b>Veo 3.1 直接生成角色的英文语音+精准口型</b>（这是它最强的能力），提示词里已按镜头写好台词和口型：<br>
    • <span class="tag vspeak">🗣 说英文台词</span>角色开口说提示词里的英文台词，口型自动对齐（美式口音）；双人镜头只让说话者开口，另一个闭嘴听；<br>
    • <span class="tag vinner">🧠 心声·英文旁白</span>读心镜头，嘴<b>不动</b>（世界骤静），英文台词作为画外音旁白；<br>
    • <span class="tag vnone">🤐 无台词·锁嘴</span>没人说话，嘴<b>不动</b>。<br>
    <b>建角色时记得填「声音描述」</b>（自定义声音效果），美式口音，声线见剧本设定。生成后如果语音不满意，重 roll 几次或微调台词。
  </div>
  <div class="info">
    <b>💡 时长档</b>：Flow 每段只能生成 4/6/8 秒。镜头上的 <span class="tag fdur">⏱ x秒档</span> 已按剧情吸附到最近档，照着选即可。台词长的镜头选大一档留出说话时间。需要更长连续镜头用 <b>Extend</b>；换机位就新建镜头。
  </div>
</section>

<section id="chars" class="card">
  <h2>🎭 先建角色（第一步 · 定妆图 + 声音）</h2>
  <p class="sub">在 Flow 的 Ingredients/角色里各建一个，粘贴定妆提示词生成参考图，用英文名命名，并填「声音描述」（美式口音）。之后每个镜头选中对应角色即可保持长相+声线一致——镜头提示词里<b>只写角色名</b>，不重复长相。</p>
  {char_cards}
</section>

{ch_html}

</div>
<button class="top" onclick="scrollTo(0,0)">↑</button>
<script>
function cp(btn, text) {{
  navigator.clipboard.writeText(text).then(function() {{
    var old = btn.textContent;
    btn.textContent = '✓ 已复制'; btn.classList.add('done');
    setTimeout(function() {{ btn.textContent = old; btn.classList.remove('done'); }}, 1400);
  }});
}}
</script>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(page)
print(f"OK -> {OUT}")

# 同步到 GitHub Pages 目录（英文路径，避免中文 URL 404）
DOCS = os.path.join(BASE, "..", "..", "docs", "xinsheng-coffee")
os.makedirs(DOCS, exist_ok=True)
with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
    f.write(page)
print(f"Pages -> docs/xinsheng-coffee/index.html")
print(f"章节: {len(chapters)}  总镜头: {total_shots}  角色: {sum(1 for v in chars.values() if isinstance(v,dict))}")
