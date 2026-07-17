"""
Rewriter v2 — 精准重写prompt生成

升级内容：
- 自动定位违规片段（从Guardian的offending_segments获取）
- 针对不同违规类型生成不同的重写策略
- 注入角色别名和语言指纹
- 动态调整重写强度（根据Guardian分数）
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from juben.guardian import guardian_check, _extract_ending, CharacterAliasMap
from juben.state.manager import StateManager


def _segment_rewriting_strategy(violation_rule: str) -> str:
    """根据违规类型返回具体的重写策略"""
    strategies = {
        "anti_dialogue_ratio": """
### 重写策略：拆解对话，注入动作

问题：非主角对话占比过高，剧情靠嘴炮推进。

具体改法：
1. **找到最长的1-2段非主角对话**，把它们拆成：
   - 短对话（每段不超过2句）
   - 说话者的动作描写（手势、表情、身体语言）
   - 主角的内心反应（读心碎片/情绪波动/判断）
   - 环境描写（光线、声音、气味、温度）
2. **用"Show Don't Tell"替代直接交代**：
   - 不写"他说三年前发生了什么"，写"他的手指在桌上敲了三下，目光移向窗外"
   - 不写"她解释了真相"，写"她从袖子里摸出一样东西，放在桌上"
3. **保持信息量不变**——不是删信息，是换一种传递方式
""",
        "anti_revelation_dump": """
### 重写策略：分散真相，碎片化传递

问题：NPC排队念白交代真相。

具体改法：
1. **把真相拆成碎片**，分散到多个场景中传递
2. **用偷听/读心/证据替代直接对话**：
   - 角色A对角色B说的话 → 主角在门外偷听到片段
   - 角色主动交代 → 主角通过读心碎片拼凑
   - 一次性说完 → 分三次，每次只透露一个碎片
3. **每个碎片之间插入动作/情绪/环境**
""",
        "info_dump_density": """
### 重写策略：降低信息密度，用隐喻替代直说

问题：非主角在短时间内密集输出背景/真相/设定。

具体改法：
1. **把解释性内容转化为动作/物品/环境**：
   - "三年前发生了什么" → 一个旧物件、一道疤、一段沉默
   - "真相是" → 一个眼神、一个回避的动作、一句没说完的话
2. **让主角自己推理**，而不是被告知
3. **留白**——不是所有真相都需要说出口
""",
        "anti_repetition_ending": """
### 重写策略：换一种结尾方式

问题：连续章节结尾高度相似，疑似LLM复读。

具体改法：
1. **换意象**：如果上一章结尾用了"月亮"，这章用"风"、"声音"、"触感"
2. **换情绪**：如果上一章结尾是"冷"，这章用"空"、"痛"、"静"
3. **换结构**：如果上一章结尾是景物描写，这章用对话或动作收尾
4. **每章结尾必须有独特的钩子**——一个未回答的问题或一个微妙的变化
""",
        "word_frequency_warning": """
### 重写策略：替换高频词

问题：使用了过多通用套话。

具体改法：
1. 找到高频词，逐个替换为具体的、独特的描写
2. "月亮很亮" → "月光把影子切成两半"
3. "甜甜的" → 具体是什么甜？桂花的甜？蜜糖的甜？记忆里的甜？
""",
    }
    return strategies.get(violation_rule, "请根据违规描述改写。")


def generate_rewrite_prompt(
    mgr: StateManager,
    chapter_num: int,
    extra_context: str = "",
) -> str:
    """
    为一个Guardian低分章节生成精准重写prompt。
    """
    project_dir = mgr.project_dir
    chapter_path = project_dir / "chapters" / f"{chapter_num:03d}.md"

    if not chapter_path.exists():
        raise FileNotFoundError(f"找不到第{chapter_num}章: {chapter_path}")

    # 1. 读取原文
    original_text = chapter_path.read_text(encoding="utf-8")

    # 2. 构建别名映射
    characters = mgr.load_characters()
    alias_map = CharacterAliasMap(characters)
    protagonist = next((c for c in characters if c.role.value == "protagonist"), None)
    protagonist_name = protagonist.name if protagonist else ""

    # 收集角色语言指纹
    speech_patterns = []
    for c in characters:
        if c.personality and c.personality.speech_pattern:
            speech_patterns.append(f"- {c.name}: {c.personality.speech_pattern}")

    # 3. 跑Guardian（带别名和角色信息）
    chapter_dir = project_dir / "chapters"
    all_endings = []
    for p in sorted(chapter_dir.glob("*.md")):
        t = p.read_text(encoding="utf-8")
        all_endings.append(_extract_ending(t))

    guardian_result = guardian_check(
        chapter_text=original_text,
        chapter_num=chapter_num,
        protagonist_name=protagonist_name,
        chapter_endings=all_endings[:chapter_num],
        characters=characters,
    )

    # 4. 读取前一章结尾
    prev_ending = ""
    if chapter_num > 1:
        prev_path = chapter_dir / f"{chapter_num-1:03d}.md"
        if prev_path.exists():
            prev_text = prev_path.read_text(encoding="utf-8")
            prev_ending = _extract_ending(prev_text)

    # 5. 组装违规详情（带片段定位）
    violations_detail = []
    rewrite_strategies = []
    for v in guardian_result.violations:
        sev = v.severity if isinstance(v.severity, str) else v.severity.value
        violations_detail.append(f"[{sev.upper()}] {v.rule}: {v.description}")

        # 添加违规片段定位
        if v.offending_segments:
            violations_detail.append("  违规片段:")
            for seg in v.offending_segments[:3]:  # 最多显示3段
                violations_detail.append(
                    f"    第{seg.get('line_num', '?')}行 "
                    f"[{seg.get('speaker', '?')}]: "
                    f"\"{seg.get('text', '')}\""
                )
                violations_detail.append(f"    原因: {seg.get('reason', '')}")

        # 收集重写策略
        strategy = _segment_rewriting_strategy(v.rule)
        if strategy:
            rewrite_strategies.append(strategy)

    # 6. 动态调整重写强度
    if guardian_result.score <= 4:
        intensity = "严格"
        extra_rules = """
## ⚠️ 严格模式（Guardian ≤4分）

本次重写必须：
1. 非主角对话占比降到20%以下
2. 所有解释性内容必须用动作/物品/环境替代
3. 每个场景至少包含2种感官描写
4. 句子长度必须有变化（极短句+中等句交替）
"""
    elif guardian_result.score <= 7:
        intensity = "标准"
        extra_rules = """
## 标准模式（Guardian 5-7分）

本次重写重点修复违规项，保持原文的节奏和氛围。
"""
    else:
        intensity = "微调"
        extra_rules = """
## 微调模式（Guardian >7分）

只需要小幅调整，不要大幅改动原文结构。
"""

    # 7. 生成prompt
    prompt = f"""# 第{chapter_num}章精准重写任务

你是一个专业的小说作者。下面的章节未通过质量审核，需要针对性重写。

## 审核结果

Guardian评分: {guardian_result.score}/10（{intensity}模式）
状态: {'PASS' if guardian_result.passed else 'FAIL'}

### 违规详情
{chr(10).join(violations_detail) if violations_detail else '(无违规)'}

{extra_rules}

## 原文（需要重写的章节）

```
{original_text}
```

## 上下文

### 前一章结尾（用于衔接）
```
{prev_ending if prev_ending else '(第一章，无前文)'}
```

### 角色语言指纹
{chr(10).join(speech_patterns) if speech_patterns else '(无)'}

{f'### 额外上下文{chr(10)}{extra_context}' if extra_context else ''}

## 针对性重写策略

{chr(10).join(rewrite_strategies) if rewrite_strategies else '请根据违规描述改写。'}

## 重写铁律

1. **保留原文的核心剧情和信息量**——不是重写故事，是重写表达方式
2. **修复所有违规项**——上面列出的每个违规都必须解决
3. **保持角色语言指纹**——每个角色说话方式不同
4. **句子长度要有变化**——极短的爆破句（2-5字）和中等长度的叙述句交替
5. **不要滑向情绪升华**——保持冷峻，不要写"她知道自己自由了"之类的伪文艺结尾
6. **结尾必须有独特钩子**——不要和前一章结尾相似

## 输出

直接输出重写后的正文。目标字数和原文相近。不要包含任何元数据。
"""
    return prompt


def save_rewrite_prompt(
    mgr: StateManager,
    chapter_num: int,
    extra_context: str = "",
) -> Path:
    """生成并保存重写prompt到项目目录"""
    prompt = generate_rewrite_prompt(mgr, chapter_num, extra_context)

    rewrite_dir = mgr.project_dir / "rewrites"
    rewrite_dir.mkdir(parents=True, exist_ok=True)

    path = rewrite_dir / f"rewrite_prompt_{chapter_num:03d}.md"
    path.write_text(prompt, encoding="utf-8")
    return path
