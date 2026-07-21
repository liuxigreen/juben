"""章节结构多样性检测 — 防止LLM复读机死循环"""
from __future__ import annotations
import re
from collections import Counter


def extract_event_fingerprint(text: str) -> list[str]:
    """提取章节的事件序列指纹
    
    将章节内容简化为事件类型序列，用于结构比较。
    """
    events = []
    
    # 对话事件
    dialogue_count = len(re.findall(r'[""「][^""」]*[""」]', text))
    if dialogue_count > 3:
        events.append("dialogue_heavy")
    elif dialogue_count > 0:
        events.append("dialogue")
    
    # 战斗事件
    combat_keywords = ["剑", "攻击", "战斗", "出手", "冲去", "招式", "灵气爆发", "突破"]
    combat_count = sum(text.count(kw) for kw in combat_keywords)
    if combat_count >= 3:
        events.append("combat")
    
    # 对峙事件
    confrontation_keywords = ["你是谁", "让我看看", "你以为", "来吧", "指着", "冷笑"]
    confront_count = sum(text.count(kw) for kw in confrontation_keywords)
    if confront_count >= 2:
        events.append("confrontation")
    
    # 觉醒/突破事件
    breakthrough_keywords = ["突破", "觉醒", "修为提升", "境界", "力量暴涨"]
    break_count = sum(text.count(kw) for kw in breakthrough_keywords)
    if break_count >= 2:
        events.append("breakthrough")
    
    # 发现/揭示事件
    reveal_keywords = ["发现", "原来", "真相", "秘密", "没想到", "竟然是"]
    reveal_count = sum(text.count(kw) for kw in reveal_keywords)
    if reveal_count >= 2:
        events.append("reveal")
    
    # 逃跑/追逐事件
    chase_keywords = ["逃跑", "追", "逃", "躲避", "追踪"]
    chase_count = sum(text.count(kw) for kw in chase_keywords)
    if chase_count >= 2:
        events.append("chase")
    
    # 日常/职场事件
    daily_keywords = ["代码", "加班", "会议", "需求", "工位", "办公室", "电脑", "键盘"]
    daily_count = sum(text.count(kw) for kw in daily_keywords)
    if daily_count >= 2:
        events.append("workplace")
    
    # 情感事件
    emotion_keywords = ["流泪", "哭", "感动", "拥抱", "心疼", "愤怒", "杀意"]
    emotion_count = sum(text.count(kw) for kw in emotion_keywords)
    if emotion_count >= 2:
        events.append("emotion")
    
    return events


def fingerprint_similarity(fp1: list[str], fp2: list[str]) -> float:
    """计算两个事件指纹的相似度 (0-1)"""
    if not fp1 and not fp2:
        return 1.0
    if not fp1 or not fp2:
        return 0.0
    
    set1, set2 = set(fp1), set(fp2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def check_structure_diversity(
    current_text: str,
    previous_text: str | None = None,
    previous_fingerprints: list[list[str]] | None = None,
    similarity_threshold: float = 0.7,
) -> dict | None:
    """检查章节结构多样性
    
    Args:
        current_text: 当前章节文本
        previous_text: 上一章文本（可选）
        previous_fingerprints: 前几章的指纹列表（可选）
        similarity_threshold: 相似度阈值，超过则判定为重复
    
    Returns:
        None if passed, or dict with violation info
    """
    current_fp = extract_event_fingerprint(current_text)
    
    # 与上一章比较
    if previous_text:
        prev_fp = extract_event_fingerprint(previous_text)
        sim = fingerprint_similarity(current_fp, prev_fp)
        
        if sim >= similarity_threshold:
            return {
                "rule": "structure_diversity",
                "severity": "critical" if sim >= 0.85 else "warning",
                "description": f"章节结构与上一章高度相似（{sim:.0%}），事件序列几乎相同",
                "current_events": current_fp,
                "previous_events": prev_fp,
                "suggestion": "本章必须采用不同的核心事件类型（如上章是战斗，本章应是谈判/潜入/情感/日常）",
            }
    
    # 与前几章指纹比较（防止3章以上的循环）
    if previous_fingerprints and len(previous_fingerprints) >= 2:
        recent_fps = previous_fingerprints[-3:]  # 最近3章
        similarities = [fingerprint_similarity(current_fp, fp) for fp in recent_fps]
        avg_sim = sum(similarities) / len(similarities)
        
        if avg_sim >= 0.6:
            return {
                "rule": "structure_diversity_batch",
                "severity": "critical",
                "description": f"章节结构与最近3章平均相似度{avg_sim:.0%}，疑似LLM进入复读循环",
                "current_events": current_fp,
                "recent_similarities": [f"{s:.0%}" for s in similarities],
                "suggestion": "必须彻底改变本章的核心事件类型，打破循环模式",
            }
    
    return None


def get_banned_phrases(text: str, min_count: int = 2) -> list[str]:
    """从文本中提取高频短语，作为下一章的禁用列表"""
    # 需要检测的AI味高频短语
    ai_phrases = [
        "喃喃自语", "嘴角勾起一抹笑", "眼睛里闪过一丝光芒",
        "感觉到自己的血液在沸腾", "感觉到自己的战意在升腾",
        "两人的剑光在空中交错", "发出耀眼的光芒",
        "你果然有仙帝的风范", "我突破了",
        "他的眼睛亮了", "他感觉到自己的心跳在加速",
        "脸色变得苍白", "脸色变得铁青",
        "嘴巴张了张，想说什么，但又说不出来",
        "点点头", "摇摇头", "挥挥手",
        "深吸一口气", "嘴角勾起",
    ]
    
    banned = []
    for phrase in ai_phrases:
        count = text.count(phrase)
        if count >= min_count:
            banned.append(phrase)
    
    return banned
