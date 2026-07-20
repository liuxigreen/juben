"""
Dead Frame Detector — 死帧检测

100-200字镜头内，物理动作<2个 → 死帧 → FAIL
物理动作：掏出/打翻/推/拉/握/砸/转身/跪/站/走/跑/颤抖/瞳孔收缩
非物理：感到/觉得/认为/意识到/心中暗想
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# 物理动作词库
PHYSICAL_ACTIONS = {
    # 中文
    "掏出", "打翻", "推", "拉", "握", "砸", "转身", "跪", "站", "走", "跑",
    "颤抖", "瞳孔收缩", "泼", "摔", "踢", "扇", "掐", "按", "拔", "抽出",
    "冲", "扑", "跌", "爬", "跳", "闪", "躲", "挡", "砍", "刺", "射",
    "抓", "扔", "丢", "捡", "撕", "拆", "关", "开", "举", "放", "抱",
    "吻", "碰", "触", "摸", "敲", "捶", "踩", "踏", "跨", "弯",
    # 英文
    "tremble", "slam", "push", "pull", "grab", "throw", "fall", "run",
    "stand", "kneel", "turn", "reach", "hold", "drop", "break", "shatter",
    "punch", "kick", "slap", "stab", "shoot", "dodge", "block", "catch",
    "pick", "toss", "slam", "grip", "squeeze", "touch", "stroke",
}

# 非物理动作（镜头拍不出来的抽象心理）
NON_PHYSICAL = {
    "感到", "觉得", "认为", "意识到", "明白", "知道", "理解",
    "心中暗想", "不禁感叹", "突然意识到", "内心", "暗自", "想起",
    "回忆", "思考", "考虑", "判断", "推测", "猜测",
    "feel", "think", "realize", "understand", "know", "remember",
}


@dataclass
class DeadFrameResult:
    """死帧检测结果"""
    passed: bool
    physical_count: int
    non_physical_count: int
    segment_text: str
    suggestion: str = ""


def detect_dead_frames(
    text: str,
    min_physical_actions: int = 2,
    segment_size: int = 200,
) -> list[DeadFrameResult]:
    """
    检测文本中的死帧。

    Args:
        text: 要检测的文本
        min_physical_actions: 每个片段最少物理动作数
        segment_size: 每个片段的字数（100-200）

    Returns:
        每个片段的检测结果列表
    """
    results = []

    # 按段落切割
    paragraphs = re.split(r'\n\s*\n', text.strip())

    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 20:
            continue

        # 统计物理动作
        physical_count = 0
        for word in PHYSICAL_ACTIONS:
            physical_count += len(re.findall(re.escape(word), para))

        # 统计非物理动作
        non_physical_count = 0
        for word in NON_PHYSICAL:
            non_physical_count += len(re.findall(re.escape(word), para))

        # 判定
        passed = physical_count >= min_physical_actions

        # 生成建议
        suggestion = ""
        if not passed:
            if non_physical_count > physical_count:
                suggestion = (
                    f"非物理动作过多（{non_physical_count}个），"
                    f"镜头拍不出来。建议改为具体动作：用'手指发白'替代'感到紧张'，"
                    f"用'茶杯摔碎'替代'非常愤怒'"
                )
            else:
                suggestion = (
                    f"物理动作不足（{physical_count}个），"
                    f"画面空洞。建议加入：打翻道具、肢体冲突、环境打断"
                )

        results.append(DeadFrameResult(
            passed=passed,
            physical_count=physical_count,
            non_physical_count=non_physical_count,
            segment_text=para[:200],
            suggestion=suggestion,
        ))

    return results


def detect_dead_frame_summary(text: str) -> dict:
    """
    死帧检测摘要。

    Returns:
        {
            "passed": bool,
            "total_segments": int,
            "dead_frames": int,
            "pass_rate": float,
            "details": list[DeadFrameResult]
        }
    """
    results = detect_dead_frames(text)
    dead_frames = [r for r in results if not r.passed]

    return {
        "passed": len(dead_frames) == 0,
        "total_segments": len(results),
        "dead_frames": len(dead_frames),
        "pass_rate": round((len(results) - len(dead_frames)) / max(1, len(results)), 2),
        "details": results,
    }
