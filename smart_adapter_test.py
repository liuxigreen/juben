"""
SmartAdapter v1 — 纯剧本→分镜 三阶段流水线

Stage 1: 场景提取（规则+正则）
Stage 2: 镜头设计（语义分析）
Stage 3: Episode JSON组装
"""
import json
import re
from pathlib import Path
from dataclasses import dataclass, field

# ============================================================
# Stage 1: 场景提取
# ============================================================

@dataclass
class SceneUnit:
    """一个场景单元"""
    text: str                    # 原始文本
    characters: list[str]        # 出场角色
    location: str                # 物理位置
    key_action: str              # 关键动作（可拍摄的）
    dialogues: list[dict]        # [{speaker, text}]
    emotion: str                 # 主导情绪
    has_cliffhanger: bool        # 是否包含钩子
    word_count: int = 0          # 字数
    scene_type: str = ""         # 对话/动作/情绪/悬念


def extract_scenes(
    chapter_text: str,
    characters_config: list[dict],
    locations_config: dict,
) -> list[SceneUnit]:
    """
    Stage 1: 从纯剧本提取场景单元。
    
    切割策略：
    1. 按空行分段
    2. 检测场景切换标记（时间/地点/人物变化）
    3. 合并相邻小段（<50字的段落并入前一段）
    4. 为每个场景提取元数据
    """
    # 加载角色名列表
    char_names = [c.get("name", "") for c in characters_config if c.get("name")]
    
    # 加载位置关键词（动态，从项目配置）
    location_keywords = _build_location_keywords(locations_config, chapter_text)
    
    # Step 1: 按空行分段
    raw_paragraphs = re.split(r'\n\s*\n', chapter_text.strip())
    paragraphs = [p.strip() for p in raw_paragraphs if p.strip() and not p.strip().startswith('#')]
    
    # Step 2: 检测场景切换点
    scene_breaks = _detect_scene_breaks(paragraphs, location_keywords, char_names)
    
    # Step 3: 按切换点分组为场景
    scenes = []
    current_group = []
    current_location = ""
    
    for i, para in enumerate(paragraphs):
        if i in scene_breaks and current_group:
            # 当前段是新场景的开始，先把之前的内容打包
            scene = _build_scene_unit(
                current_group, char_names, location_keywords, current_location
            )
            if scene.word_count >= 30:  # 过滤太短的
                scenes.append(scene)
            current_group = []
        
        # 更新位置
        loc = _detect_location(para, location_keywords)
        if loc:
            current_location = loc
        
        current_group.append(para)
    
    # 最后一组
    if current_group:
        scene = _build_scene_unit(
            current_group, char_names, location_keywords, current_location
        )
        if scene.word_count >= 30:
            scenes.append(scene)
    
    # Step 4: 合并小场景（<200字的场景并入相邻场景）
    scenes = _merge_small_scenes(scenes, min_size=200)
    
    return scenes


def _merge_small_scenes(scenes: list[SceneUnit], min_size: int = 200) -> list[SceneUnit]:
    """合并小场景到相邻场景"""
    if len(scenes) <= 1:
        return scenes
    
    merged = []
    buffer = None
    
    for scene in scenes:
        if buffer is None:
            buffer = scene
            continue
        
        if buffer.word_count < min_size:
            # 合并到当前场景
            buffer = SceneUnit(
                text=buffer.text + "\n\n" + scene.text,
                characters=list(set(buffer.characters + scene.characters)),
                location=scene.location or buffer.location,
                key_action=scene.key_action or buffer.key_action,
                dialogues=buffer.dialogues + scene.dialogues,
                emotion=scene.emotion if scene.emotion != "中性" else buffer.emotion,
                has_cliffhanger=scene.has_cliffhanger or buffer.has_cliffhanger,
                word_count=buffer.word_count + scene.word_count,
                scene_type=scene.scene_type if scene.scene_type != "中性" else buffer.scene_type,
            )
        else:
            merged.append(buffer)
            buffer = scene
    
    if buffer:
        if merged and buffer.word_count < min_size:
            # 最后一个小场景并入前一个
            last = merged[-1]
            merged[-1] = SceneUnit(
                text=last.text + "\n\n" + buffer.text,
                characters=list(set(last.characters + buffer.characters)),
                location=buffer.location or last.location,
                key_action=buffer.key_action or last.key_action,
                dialogues=last.dialogues + buffer.dialogues,
                emotion=buffer.emotion if buffer.emotion != "中性" else last.emotion,
                has_cliffhanger=buffer.has_cliffhanger or last.has_cliffhanger,
                word_count=last.word_count + buffer.word_count,
                scene_type=buffer.scene_type if buffer.scene_type != "中性" else last.scene_type,
            )
        else:
            merged.append(buffer)
    
    return merged


def _build_location_keywords(locations_config: dict, chapter_text: str) -> dict:
    """
    从locations.json构建位置关键词映射。
    
    支持两种格式：
    1. 简单列表: {"locations": ["咖啡店", "吧台", ...]}
    2. 关键词映射: {"咖啡店": ["吧台", "磨豆", ...], "面馆": ["面", "筷子", ...]}
    """
    keywords = {}
    
    if not locations_config:
        return keywords
    
    # 检测格式
    if "locations" in locations_config and isinstance(locations_config["locations"], list):
        # 简单列表格式 → 每个位置名就是自己的关键词
        for loc_name in locations_config["locations"]:
            keywords[loc_name] = [loc_name]
            # 为常见位置添加别名
            if "咖啡" in loc_name:
                keywords[loc_name].extend(["吧台", "咖啡", "磨豆", "杯", "杯壁", "红茶", "茶水", "便签"])
            elif "面馆" in loc_name:
                keywords[loc_name].extend(["面碗", "面汤", "筷子", "排风扇", "油烟", "铁锅", "灶台"])
            elif "巷子" in loc_name:
                keywords[loc_name].extend(["巷", "青石板", "月光", "路灯", "影子", "墙壁"])
            elif "公寓" in loc_name or "家" in loc_name:
                keywords[loc_name].extend(["家里", "卧室", "床", "门框"])
            elif "写字楼" in loc_name:
                keywords[loc_name].extend(["旋转门", "玻璃幕墙", "电梯"])
    else:
        # 关键词映射格式
        for loc_name, loc_data in locations_config.items():
            if isinstance(loc_data, list):
                keywords[loc_name] = loc_data
            elif isinstance(loc_data, dict):
                keywords[loc_name] = loc_data.get("keywords", [])
    
    # 通用位置检测（兜底）
    generic = {
        "室内": ["屋里", "房间", "室内", "里面"],
        "室外": ["外面", "街上", "路上", "户外"],
    }
    for loc, kws in generic.items():
        if loc not in keywords:
            keywords[loc] = kws
    
    return keywords


def _detect_scene_breaks(
    paragraphs: list[str],
    location_keywords: dict,
    char_names: list[str],
) -> set[int]:
    """
    检测场景切换点。
    
    核心原则：只在真正换地点时才切场景。
    角色"站起来""转身走"不算切换——除非检测到新地点关键词。
    
    切换信号：
    1. 位置变化（出现新的位置关键词，且与当前不同）
    2. 明确的时空跳跃标记（"第二天""几小时后""回到""来到"）
    3. 距离跳跃（段落间距大+新地点出现）
    """
    breaks = set()
    prev_location = ""
    
    for i, para in enumerate(paragraphs):
        # 检测当前位置
        loc = _detect_location(para, location_keywords)
        
        # 只有检测到新位置且与前一个不同时才算切换
        if loc and loc != prev_location and i > 0:
            # 额外验证：确认不是偶然匹配
            # 检查前一段是否也在新位置（如果是，不算切换）
            prev_loc = _detect_location(paragraphs[i-1], location_keywords) if i > 0 else ""
            if loc != prev_loc:
                breaks.add(i)
                prev_location = loc
        elif loc:
            prev_location = loc
        
        # 明确的时空跳跃标记（必须是段落开头，且伴随位置变化）
        time_markers = ["第二天", "几小时后", "傍晚", "清晨", "回到", "来到", "走到", "走进"]
        if any(para.strip().startswith(marker) for marker in time_markers):
            if i > 0 and loc:  # 必须有位置信息
                breaks.add(i)
                if loc:
                    prev_location = loc
    
    return breaks


def _detect_location(para: str, location_keywords: dict) -> str:
    """检测段落中的物理位置"""
    for loc_name, keywords in location_keywords.items():
        if any(kw in para for kw in keywords):
            return loc_name
    return ""


def _build_scene_unit(
    paragraphs: list[str],
    char_names: list[str],
    location_keywords: dict,
    fallback_location: str,
) -> SceneUnit:
    """从段落组构建场景单元"""
    text = "\n".join(paragraphs)
    
    # 提取角色
    characters = []
    for name in char_names:
        if name in text:
            characters.append(name)
    
    # 提取位置
    location = fallback_location
    for para in paragraphs:
        loc = _detect_location(para, location_keywords)
        if loc:
            location = loc
            break
    
    # 提取对话
    dialogues = _extract_dialogues(text, char_names)
    
    # 提取关键动作
    key_action = _extract_key_action(text)
    
    # 推断情绪
    emotion = _infer_emotion(text)
    
    # 检测钩子
    has_cliffhanger = _detect_cliffhanger(text)
    
    # 推断场景类型
    scene_type = _infer_scene_type(text, dialogues, key_action)
    
    return SceneUnit(
        text=text,
        characters=characters,
        location=location,
        key_action=key_action,
        dialogues=dialogues,
        emotion=emotion,
        has_cliffhanger=has_cliffhanger,
        word_count=len(text),
        scene_type=scene_type,
    )


def _extract_dialogues(text: str, char_names: list[str]) -> list[dict]:
    """提取对话（三级匹配）"""
    dialogues = []
    
    # Level 1: 带说话者的引号对话
    # 格式: "XXX"XXX说 / XXX说"XXX" / XXX(动作)"XXX"
    pattern1 = re.findall(
        r'(?:(\w{2,4})(?:说|道|问|答|喊|叫|冷笑|叹|低声|开口|声音|语气))[^"]*["「]([^"」]+)["」]',
        text
    )
    for speaker, line in pattern1:
        if speaker in char_names:
            dialogues.append({"speaker": speaker, "text": line})
    
    # Level 2: 纯引号对话（无明确说话者）
    pattern2 = re.findall(r'["「]([^"」]{2,})["」]', text)
    for line in pattern2:
        # 过滤：声效拟声词、过短的非对话
        if len(line) <= 2:
            continue
        if re.match(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$', line):
            continue
        # 检查是否已被Level 1捕获
        if not any(line in d["text"] for d in dialogues):
            dialogues.append({"speaker": "", "text": line})
    
    return dialogues


def _extract_key_action(text: str) -> str:
    """提取关键可拍摄动作（排除心理描写）"""
    action_patterns = [
        # 物理动作句子
        r'[^。！？]*(?:端起|放下|转身|站起来|推开门|靠在|攥紧|掏出|摸到|按|拨|打开|关上|走|跑|坐下|站起来)[^。！？]*[。！？]',
        # 感官细节
        r'[^。！？]*(?:灯闪|灭了|亮了|震了一下|响了|溅起|滴|渗|冒|碎|裂|断|掉)[^。！？]*[。！？]',
        # 微表情/微动作
        r'[^。！？]*(?:眼神|瞳孔|嘴唇|手指|拳头|额头|汗|泪|颤抖|发抖|僵)[^。！？]*[。！？]',
    ]
    
    for pattern in action_patterns:
        matches = re.findall(pattern, text)
        if matches:
            # 取最有张力的那个（通常是最短的、包含冲突的）
            return min(matches, key=len).strip()[:80]
    
    return ""


def _infer_emotion(text: str) -> str:
    """推断主导情绪"""
    emotion_signals = {
        "紧张": ["攥紧", "心跳", "发抖", "冰凉", "手指", "钥匙", "齿痕", "掌心", "紧张"],
        "震惊": ["愣", "呆", "瞳孔", "不敢相信", "猛地", "突然", "灭了", "闪了"],
        "暧昧": ["月光", "影子", "眼睛", "想起", "不同", "靠近", "心跳"],
        "悬疑": ["想不起来", "模糊", "淡了", "消失", "听不清", "黑暗", "声音"],
        "悲伤": ["泪", "哭", "痛", "苦", "冷", "空荡荡", "消失"],
        "愤怒": ["怒", "恨", "咬牙", "瞪", "摔", "砸", "攥紧拳头"],
        "日常": ["吃面", "喝", "筷子", "碗", "面汤", "排风扇"],
    }
    
    scores = {}
    for emotion, keywords in emotion_signals.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[emotion] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "中性"


def _detect_cliffhanger(text: str) -> bool:
    """检测是否包含钩子"""
    # 结尾的悬念标记
    last_200 = text[-200:]
    cliffhanger_signals = [
        "？", "呢", "听不清", "消失", "没了", "灭了", "黑暗",
        "突然", "忽然", "猛地", "转身", "走了", "淡了",
        "想不起来", "不确定", "不知道",
    ]
    return any(sig in last_200 for sig in cliffhanger_signals)


def _infer_scene_type(text: str, dialogues: list[dict], key_action: str) -> str:
    """推断场景类型"""
    dialogue_ratio = sum(len(d["text"]) for d in dialogues) / max(1, len(text))
    
    if dialogue_ratio > 0.3:
        return "对话"
    elif key_action and any(kw in text for kw in ["追", "跑", "打", "摔", "砸", "冲"]):
        return "动作"
    elif any(kw in text for kw in ["想不起来", "模糊", "闪", "灭了", "黑暗", "声音"]):
        return "悬念"
    else:
        return "情绪"


# ============================================================
# Stage 2: 镜头设计
# ============================================================

@dataclass
class ShotDesign:
    """镜头设计"""
    shot_id: int
    scene_index: int           # 来自哪个场景
    shot_type: str             # CU/MCU/MS/WS
    camera_movement: str       # Static/Push/Pull/Handheld
    camera_angle: str          # Eye Level/Low Angle/High Angle
    lighting: str              # Low key/Warm/High contrast/Natural
    duration: float            # 秒
    visual_action: str         # 画面动作描述（15-40字）
    dialogue: str              # 台词
    emotion: str               # 情绪标签
    pacing_label: str          # 节奏卡点
    location: str              # 位置
    characters: list[str]      # 出场角色
    audio_hint: str            # 音效提示


def design_shots(
    scenes: list[SceneUnit],
    target_duration: int = 90,
    target_shots: int = 5,
) -> list[ShotDesign]:
    """
    Stage 2: 从场景单元设计镜头。
    
    设计逻辑：
    1. 场景→镜头映射（每个场景1-2个镜头，关键场景可拆3个）
    2. 根据内容选景别（情绪→CU，对话→MCU，环境→MS）
    3. 根据叙事位置选运镜（开头→Static，冲突→Push，反应→Pull）
    4. 根据内容密度分配时长
    5. 分配节奏卡点标签
    """
    all_shots = []
    shot_id = 1
    
    # 分配节奏卡点
    pacing_labels = _assign_pacing_labels(scenes, target_shots)
    
    for i, scene in enumerate(scenes):
        # 决定这个场景拆几个镜头
        n_shots = _decide_shot_count(scene)
        
        # 拆分场景文本为镜头段落
        shot_segments = _split_scene_to_segments(scene.text, n_shots)
        
        for j, segment in enumerate(shot_segments):
            # 选景别
            shot_type = _choose_shot_type(scene, j, n_shots)
            
            # 选运镜
            camera_move = _choose_camera(scene, j, n_shots, i, len(scenes))
            
            # 选视角
            angle = _choose_angle(scene, j, n_shots)
            
            # 选光影
            lighting = _choose_lighting(scene)
            
            # 估算时长
            duration = _estimate_duration(segment, scene, target_duration, target_shots)
            
            # 提取画面动作
            visual_action = _extract_visual_action(segment)
            
            # 提取台词
            dialogue = _extract_dialogue_from_segment(segment, scene.characters)
            
            # 节奏卡点
            pacing = pacing_labels[i] if i < len(pacing_labels) else "30s_Explosion"
            
            # 音效提示
            audio = _infer_audio(segment, scene)
            
            shot = ShotDesign(
                shot_id=shot_id,
                scene_index=i,
                shot_type=shot_type,
                camera_movement=camera_move,
                camera_angle=angle,
                lighting=lighting,
                duration=duration,
                visual_action=visual_action,
                dialogue=dialogue,
                emotion=scene.emotion,
                pacing_label=pacing,
                location=scene.location,
                characters=scene.characters,
                audio_hint=audio,
            )
            all_shots.append(shot)
            shot_id += 1
    
    # 修正总时长
    _adjust_durations(all_shots, target_duration)
    
    return all_shots


def _assign_pacing_labels(scenes: list[SceneUnit], target_shots: int) -> list[str]:
    """根据场景的叙事位置分配节奏卡点"""
    n = len(scenes)
    labels = []
    
    for i, scene in enumerate(scenes):
        ratio = i / max(1, n - 1)
        
        if ratio <= 0.15:
            labels.append("3s_Hook")
        elif ratio <= 0.35:
            labels.append("15s_Retention")
        elif ratio <= 0.55:
            labels.append("30s_Explosion")
        elif ratio <= 0.75:
            labels.append("60s_Satisfaction")
        else:
            labels.append("90s_Cliffhanger")
    
    # 确保最后一个场景是Cliffhanger
    if scenes and scenes[-1].has_cliffhanger:
        labels[-1] = "90s_Cliffhanger"
    
    return labels


def _decide_shot_count(scene: SceneUnit) -> int:
    """决定场景拆几个镜头"""
    # 关键场景（有钩子、情绪强、字数多）拆更多镜头
    if scene.has_cliffhanger and scene.word_count > 500:
        return 2
    if scene.scene_type == "动作" and scene.word_count > 300:
        return 2
    if scene.word_count > 800:
        return 2
    return 1


def _split_scene_to_segments(text: str, n_shots: int) -> list[str]:
    """将场景文本拆分为镜头段落"""
    if n_shots <= 1:
        return [text]
    
    # 按段落分
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    if len(paragraphs) <= 1:
        # 只有一段，按句子拆
        sentences = re.split(r'(?<=[。！？])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        mid = len(sentences) // 2
        return [
            "".join(sentences[:mid]),
            "".join(sentences[mid:]),
        ]
    
    # 多段，按段落中点拆
    mid = len(paragraphs) // 2
    return [
        "\n".join(paragraphs[:mid]),
        "\n".join(paragraphs[mid:]),
    ]


def _choose_shot_type(scene: SceneUnit, shot_index: int, total_shots: int) -> str:
    """根据场景内容选景别"""
    # 情绪爆发→特写
    if scene.emotion in ["震惊", "愤怒", "悲伤"]:
        return "CU"
    # 悬念→特写
    if scene.scene_type == "悬念":
        return "CU"
    # 对话→近景
    if scene.scene_type == "对话":
        return "MCU"
    # 动作→中景
    if scene.scene_type == "动作":
        return "MS"
    # 环境描写→全景
    if any(kw in scene.text for kw in ["巷子", "街", "楼", "门", "窗", "月光"]):
        return "MS" if shot_index == 0 else "MCU"
    # 默认近景
    return "MCU"


def _choose_camera(
    scene: SceneUnit, shot_index: int, total_shots: int,
    scene_index: int, total_scenes: int,
) -> str:
    """选运镜"""
    # 开头场景→Static
    if scene_index == 0 and shot_index == 0:
        return "Static"
    
    # 冲突/悬念→Push
    if scene.scene_type in ["悬念", "动作"] or scene.emotion in ["震惊", "愤怒"]:
        return "Push"
    
    # 反应/情绪→Pull
    if scene.emotion in ["悲伤", "暧昧"]:
        return "Pull"
    
    # 对话→Static或Push
    if scene.scene_type == "对话":
        return "Push" if shot_index > 0 else "Static"
    
    # 结尾→Push（悬念感）
    if scene_index == total_scenes - 1:
        return "Push"
    
    return "Static"


def _choose_angle(scene: SceneUnit, shot_index: int, total_shots: int) -> str:
    """选视角"""
    # 权力/压迫→仰拍
    if scene.emotion == "愤怒":
        return "Low Angle"
    # 无助/渺小→俯拍
    if scene.emotion in ["悲伤", "恐惧"]:
        return "High Angle"
    # 默认平视
    return "Eye Level"


def _choose_lighting(scene: SceneUnit) -> str:
    """选光影"""
    lighting_map = {
        "紧张": "High contrast",
        "震惊": "High contrast",
        "暧昧": "Warm",
        "悬疑": "Low key",
        "悲伤": "Low key",
        "愤怒": "High contrast",
        "日常": "Natural",
        "中性": "Natural",
    }
    return lighting_map.get(scene.emotion, "Natural")


def _estimate_duration(
    segment: str, scene: SceneUnit,
    target_duration: int, target_shots: int,
) -> float:
    """估算镜头时长（基于内容密度）"""
    word_count = len(segment)
    
    # 基础时长 = 总时长 / 总镜头数
    base = target_duration / max(1, target_shots)
    
    # 按内容密度调整
    if word_count < 50:
        return max(3.0, base * 0.5)   # 很短→短镜头
    elif word_count < 150:
        return base * 0.8
    elif word_count > 400:
        return base * 1.3              # 很长→长镜头
    return base


def _extract_visual_action(segment: str) -> str:
    """提取可拍摄的视觉动作（15-40字）"""
    # 不可拍的抽象描述黑名单
    abstract_patterns = [
        "语速", "语气", "声音", "心想", "觉得", "感到", "认为", "意识到",
        "明白", "知道", "理解", "暗想", "感叹", "像在", "像是",
    ]
    
    # 优先找物理动作句子
    action_patterns = [
        r'[^。\n]*(?:端起|放下|转身|站起来|推开门|靠在|攥紧|掏出|摸到|走过来|走过去|坐下|站起来|推开)[^。]*。',
        r'[^。\n]*(?:灯闪|灭了|亮了|震了|响了|溅起|滴|渗|冒|碎|裂|断|掉|消失)[^。]*。',
        r'[^。\n]*(?:眼神|瞳孔|嘴唇|手指|拳头|额头|汗|泪|颤抖|发抖|僵|攥|捏|按|摸)[^。]*。',
        r'[^。\n]*(?:筷子|杯子|碗|面|茶|灯|门|窗|钥匙|手机|纸巾|便签)[^。]*。',
    ]
    
    for pattern in action_patterns:
        matches = re.findall(pattern, segment)
        if matches:
            # 过滤抽象描述
            for m in matches:
                m = m.strip()
                if any(abs_kw in m for abs_kw in abstract_patterns):
                    continue
                if len(m) > 40:
                    m = m[:40] + "……"
                if len(m) >= 10:
                    return m
    
    # 兜底：取第一句有具体道具/身体部位的
    sentences = re.split(r'[。！？\n]', segment)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 10 or len(sent) > 60:
            continue
        # 有具体可拍元素
        if any(kw in sent for kw in [
            "手", "眼", "脸", "头", "杯", "灯", "门", "窗", "影", "光", 
            "暗", "筷子", "碗", "面", "茶", "钥匙", "手机", "围裙",
        ]):
            if not any(abs_kw in sent for abs_kw in abstract_patterns):
                return sent[:40]
    
    # 最后兜底：取最短的非空句子
    for sent in sentences:
        sent = sent.strip()
        if 10 <= len(sent) <= 40:
            return sent
    
    return segment[:40] if segment else ""


def _extract_dialogue_from_segment(segment: str, characters: list[str]) -> str:
    """从镜头段落中提取关键台词（过滤声效）"""
    matches = re.findall(r'["「]([^"」]+)["」]', segment)
    # 过滤声效和过短的
    filtered = []
    for m in matches:
        if len(m) <= 2:
            continue
        if re.match(r'^[嗒咣嘭咔嚓嘶嗡吱咚啪噗嗤]+$', m):
            continue
        filtered.append(m)
    
    if filtered:
        # 取最有张力的台词（最短的通常最有力）
        return min(filtered, key=len)
    return ""


def _infer_audio(segment: str, scene: SceneUnit) -> str:
    """推断音效"""
    audio_keywords = {
        "嗡嗡": "electrical hum",
        "咣": "metal clang",
        "嗒嗒": "rhythmic tapping",
        "震": "phone vibration",
        "响": "notification sound",
        "脚步": "footsteps on stone",
        "排风扇": "ventilation fan whirring",
        "灭了": "light flickering off",
        "亮了": "light flickering on",
        "水": "liquid pouring",
        "溅": "liquid splashing",
        "碎": "glass shattering",
    }
    
    for kw, audio in audio_keywords.items():
        if kw in segment:
            return audio
    
    # 根据场景类型推断
    if scene.scene_type == "对话":
        return "ambient conversation noise"
    if scene.scene_type == "悬念":
        return "silence, subtle tension"
    return "ambient room tone"


def _adjust_durations(shots: list[ShotDesign], target_duration: int):
    """修正总时长，使其接近目标"""
    if not shots:
        return
    
    current_total = sum(s.duration for s in shots)
    if abs(current_total - target_duration) < 5:
        return
    
    # 按比例缩放
    ratio = target_duration / current_total
    for shot in shots:
        shot.duration = round(max(2.0, shot.duration * ratio), 1)


# ============================================================
# Stage 3: 组装 + 输出
# ============================================================

def build_episode_from_shots(
    shots: list[ShotDesign],
    chapter_num: int,
    chapter_text: str,
    characters_config: list[dict],
) -> dict:
    """从镜头设计组装Episode JSON"""
    
    # 构建shots列表
    shot_dicts = []
    for shot in shots:
        shot_dicts.append({
            "shot_id": shot.shot_id,
            "shot_type": shot.shot_type,
            "camera_movement": shot.camera_movement,
            "camera_angle": shot.camera_angle,
            "duration": shot.duration,
            "visual_action": shot.visual_action,
            "dialogue": shot.dialogue,
            "emotion": shot.emotion,
            "pacing_label": shot.pacing_label,
            "location": shot.location,
            "characters_present": shot.characters,
            "lighting": shot.lighting,
            "audio_hint": shot.audio_hint,
        })
    
    # 构建pacing_checkpoints
    checkpoints = []
    for shot in shots:
        checkpoints.append({
            "label": shot.pacing_label,
            "time_range": [0, shot.duration],  # 粗略
            "visual_action": shot.visual_action,
            "dialogue": shot.dialogue,
            "emotion": shot.emotion,
        })
    
    # 提取cliffhanger（最后一个镜头）
    last_shot = shots[-1] if shots else None
    cliffhanger = {
        "type": "shock" if last_shot and last_shot.emotion in ["震惊", "悬疑"] else "reveal",
        "line": last_shot.visual_action if last_shot else "",
        "unanswered_question": "接下来会发生什么？",
    }
    
    total_duration = sum(s.duration for s in shots)
    
    return {
        "episode_number": chapter_num,
        "duration_estimate_seconds": round(total_duration),
        "word_count_estimate": len(chapter_text),
        "pacing_checkpoints": checkpoints,
        "shots": shot_dicts,
        "cliffhanger": cliffhanger,
        "hook_density": "high" if any(s.emotion in ["震惊", "悬疑"] for s in shots) else "medium",
        "scene_count": len(set(s.scene_index for s in shots)),
        "characters_involved": list(set(c for s in shots for c in s.characters)),
    }


# ============================================================
# 测试入口
# ============================================================

def run_test(chapter_num: int, project_dir: str):
    """测试SmartAdapter"""
    project_dir = Path(project_dir)
    
    # 读取章节
    chapter_file = project_dir / "chapters" / f"{chapter_num:03d}.md"
    if not chapter_file.exists():
        chapter_file = project_dir / "story" / f"{chapter_num:03d}.md"
    chapter_text = chapter_file.read_text()
    
    # 读取角色配置
    chars_file = project_dir / "characters.json"
    characters_config = []
    if chars_file.exists():
        data = json.loads(chars_file.read_text())
        characters_config = data.get("characters", [])
    
    # 读取位置配置
    locs_file = project_dir / "locations.json"
    locations_config = {}
    if locs_file.exists():
        locations_config = json.loads(locs_file.read_text())
    
    print(f"=== SmartAdapter Test: Ch{chapter_num} ===")
    print(f"原文长度: {len(chapter_text)} 字")
    print(f"角色: {[c.get('name','') for c in characters_config]}")
    print(f"位置配置: {list(locations_config.keys())[:10]}")
    print()
    
    # Stage 1: 场景提取
    scenes = extract_scenes(chapter_text, characters_config, locations_config)
    print(f"--- Stage 1: 场景提取 ({len(scenes)}个场景) ---")
    for i, scene in enumerate(scenes):
        print(f"  场景{i+1}: [{scene.scene_type}] {scene.location or '未知位置'} "
              f"| 角色: {scene.characters} | 情绪: {scene.emotion} "
              f"| {scene.word_count}字 | 钩子: {scene.has_cliffhanger}")
        print(f"    关键动作: {scene.key_action[:60]}")
        print(f"    对话数: {len(scene.dialogues)}")
        if scene.dialogues:
            print(f"    首句台词: {scene.dialogues[0]['text'][:40]}")
        print()
    
    # Stage 2: 镜头设计
    shots = design_shots(scenes, target_duration=90, target_shots=5)
    print(f"--- Stage 2: 镜头设计 ({len(shots)}个镜头) ---")
    for shot in shots:
        print(f"  镜头{shot.shot_id}: [{shot.shot_type}] [{shot.camera_movement}] "
              f"[{shot.camera_angle}] [{shot.lighting}] | {shot.duration}s")
        print(f"    画面: {shot.visual_action[:60]}")
        print(f"    台词: {shot.dialogue[:40] if shot.dialogue else '无'}")
        print(f"    音效: {shot.audio_hint}")
        print(f"    位置: {shot.location} | 角色: {shot.characters}")
        print()
    
    # Stage 3: 组装
    episode = build_episode_from_shots(shots, chapter_num, chapter_text, characters_config)
    
    total_duration = sum(s.duration for s in shots)
    print(f"--- Stage 3: Episode摘要 ---")
    print(f"  总镜头: {len(shots)}")
    print(f"  总时长: {total_duration:.1f}s")
    print(f"  角色: {episode['characters_involved']}")
    print(f"  钩子: {episode['cliffhanger']['type']}")
    
    # 保存
    output_dir = project_dir / "smart_adapter_output"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"ch{chapter_num:03d}_episode.json"
    output_file.write_text(json.dumps(episode, ensure_ascii=False, indent=2))
    print(f"\n  已保存: {output_file}")
    
    # 生成可读的分镜脚本
    script_file = output_dir / f"ch{chapter_num:03d}_storyboard.md"
    script_file.write_text(_generate_storyboard_md(episode, chapter_num))
    print(f"  分镜脚本: {script_file}")
    
    return episode


def _generate_storyboard_md(episode: dict, chapter_num: int) -> str:
    """生成可读的分镜脚本Markdown"""
    lines = [f"# 第{chapter_num}章 分镜脚本\n"]
    lines.append(f"**总时长**: {episode['duration_estimate_seconds']}s | "
                 f"**镜头数**: {len(episode['shots'])} | "
                 f"**钩子类型**: {episode['cliffhanger']['type']}\n")
    
    for shot in episode["shots"]:
        lines.append(f"## 镜头 {shot['shot_id']} | {shot['pacing_label']}")
        lines.append(f"- **【画面机位】**: [{shot['shot_type']}] + [{shot['camera_movement']}] + [{shot['camera_angle']}]")
        lines.append(f"- **【视觉动作】**: {shot['visual_action']}")
        lines.append(f"- **【场景光影】**: [{shot['lighting']}] + {shot['audio_hint']}")
        if shot['dialogue']:
            lines.append(f"- **【角色台词】**: {shot['dialogue']}")
        lines.append(f"- **【时长】**: {shot['duration']}s")
        lines.append(f"- **【位置】**: {shot['location'] or '未标注'}")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    run_test(9, str(Path.home() / "juben/projects/心声咖啡"))
