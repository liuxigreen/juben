"""
Episode Schema — 短剧单集数据结构（v3 超写实版）

定义 Episode / Shot / PacingCheckpoint 核心模型。
输出两件套：剧本文档 + 分镜提示词包。

新增：
- RenderStyle 枚举（超写实漫剧 / 沙雕真人剧）
- Shot.final_render_prompt（最终渲染prompt）
- Shot.character_tags（角色材质标签）
- Shot.style_suffix（风格后缀）
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================

class RenderStyle(str, Enum):
    """渲染风格"""
    REALISTIC = "realistic"    # 超写实漫剧（Kling/Runway）
    COMEDY = "comedy"          # 沙雕真人剧（图文分镜/配音）


class ShotType(str, Enum):
    """景别"""
    ECU = "ECU"          # 大特写（眼睛、手部细节）
    CU = "CU"            # 特写（面部表情）
    MCU = "MCU"          # 近景（胸部以上）
    MS = "MS"            # 中景（腰部以上）
    FS = "FS"            # 全景（全身）
    EWS = "EWS"          # 远景（环境+人物）


class CameraMovement(str, Enum):
    """运镜"""
    STATIC = "static"        # 静止
    PUSH = "push"            # 推（缓推/急推）
    PULL = "pull"            # 拉
    PAN = "pan"              # 横摇
    TILT = "tilt"            # 俯仰
    DOLLY = "dolly"          # 移轨
    TRACKING = "tracking"    # 跟拍
    CRANE = "crane"          # 升降
    HANDHELD = "handheld"    # 手持
    ZOOM = "zoom"            # 变焦


class CameraAngle(str, Enum):
    """机位角度"""
    EYE_LEVEL = "eye-level"  # 平视
    LOW = "low"              # 仰拍
    HIGH = "high"            # 俯拍
    DUTCH = "Dutch"          # 倾斜
    OVERHEAD = "overhead"    # 正俯


class Composition(str, Enum):
    """构图规则"""
    RULE_OF_THIRDS = "rule-of-thirds"
    GOLDEN_RATIO = "golden-ratio"
    SYMMETRY = "symmetry"
    LEADING_LINES = "leading-lines"
    FRAME_WITHIN = "frame-within"
    DIAGONAL = "diagonal"


class PacingLabel(str, Enum):
    """节奏卡点标签
    爆款对齐：从5点扩到9点——抖音/红果留存铁律是"15秒一个钩子、30秒一个反转"，
    任何15秒无新信息即划走；旧表 30s→60s→90s 之间的长直道是中段信息真空。
    字数轴按 90 秒 ≈ 500-900 字台词本体校准（见 docs/hit-drama-alignment-plan.md 闸门6）。
    """
    HOOK_3S = "3s_Hook"                      # 0-3秒：感官冲击+主钩子画面
    CONFLICT_15S = "15s_Conflict"            # 12-18秒：第一冲突升级（立场交锋）
    RETENTION_30S = "30s_Retention"          # 25-35秒：信息差炸弹+第一次小反转
    ESCALATE_45S = "45s_Escalation"          # 40-50秒：打脸前蓄力/施辱者加码
    EXPLOSION_60S = "60s_Explosion"          # 55-65秒：爆点（打脸/揭露/物理冲击）
    SATISFACTION_75S = "75s_Satisfaction"    # 70-78秒：爽点兑现+反应镜头
    TWIST_82S = "82s_Twist"                  # 78-85秒：新变量插入（第二次反转）
    CLIFFHANGER_90S = "90s_Cliffhanger"     # 85-90秒：断崖钩子（卡在最后一口气）
    # 兼容旧标签名（映射到新刻度）
    RETENTION_15S = "15s_Retention"          # 旧名，语义并入 CONFLICT_15S
    EXPLOSION_30S = "30s_Explosion"          # 旧名，语义并入 RETENTION_30S
    SATISFACTION_60S = "60s_Satisfaction"    # 旧名，语义并入 EXPLOSION_60S


# ============================================================
# 风格后缀常量
# ============================================================

# 超写实漫剧风格后缀
REALISTIC_SUFFIX = (
    "(Photorealistic, hyper-detailed, cinematic lighting, "
    "8k resolution, shot on 35mm lens, shallow depth of field, "
    "dramatic shadows, film grain, anamorphic lens flare)"
)

# 沙雕真人剧风格后缀
COMEDY_SUFFIX = (
    "(Bright colorful lighting, slightly exaggerated expressions, "
    "4K resolution, clean sharp focus, sitcom-style framing, "
    "warm inviting atmosphere, high saturation)"
)


# ============================================================
# 核心模型
# ============================================================

class Shot(BaseModel):
    """单个镜头"""
    shot_id: int
    shot_type: ShotType
    camera_movement: CameraMovement = CameraMovement.STATIC
    camera_angle: CameraAngle = CameraAngle.EYE_LEVEL
    duration: float = Field(ge=3.0, le=8.0, description="秒（AI视频模型物理限制 3-8s）")
    composition: Composition = Composition.RULE_OF_THIRDS

    # 6组件Prompt（英文，可直接喂Kling/Runway/Veo）
    subject: str = ""           # 主体描述（角色外貌+服装）
    action: str = ""            # 动作（具体行为）
    setting: str = ""           # 场景环境
    lighting: str = ""          # 光影
    mood: str = ""              # 情绪/色彩
    style: str = "cinematic, 4K"  # 风格锚点

    # 角色材质标签（从characters.json查表注入）
    character_tags: str = ""    # "1boy, realistic young asian man, hyper-detailed skin texture..."
    visual_anchors: list[str] = Field(default_factory=list)  # 物理图腾（杯沿唇印、疤痕等关键道具）

    # 风格后缀（根据RenderStyle自动注入）
    style_suffix: str = ""

    # 最终渲染prompt = character_tags + visual_prompt + style_suffix
    final_render_prompt: str = ""

    # 音频
    audio_prompt: str = ""      # 音效/SFX描述
    dialogue: str = ""          # 台词（如有）

    # 元数据
    emotion_tag: str = ""       # 情绪标签
    pacing_label: str = ""      # 对应的节奏卡点
    word_range: list[int] = Field(default_factory=list)  # 对应字数区间
    location: str = ""          # 物理位置（用于时空折叠检测）
    characters_present: list[str] = Field(default_factory=list)  # 出场角色

    def to_visual_prompt(self) -> str:
        """生成完整的视觉Prompt（英文，可直接喂视频模型）"""
        parts = []
        # 景别+运镜开头
        shot_desc = f"{self.shot_type.value} {self.camera_movement.value}"
        if self.camera_movement != CameraMovement.STATIC:
            shot_desc += f" {self.camera_movement.value}"
        parts.append(shot_desc)

        if self.subject:
            parts.append(self.subject)
        if self.action:
            parts.append(self.action)
        if self.setting:
            parts.append(self.setting)
        if self.lighting:
            parts.append(self.lighting)
        if self.mood:
            parts.append(self.mood)
        parts.append(self.style)

        return ", ".join(parts)

    def to_audio_prompt(self) -> str:
        """生成音频Prompt"""
        parts = []
        if self.audio_prompt:
            parts.append(self.audio_prompt)
        if self.dialogue:
            parts.append(f'dialogue: "{self.dialogue}"')
        return ", ".join(parts) if parts else ""

    def build_final_render_prompt(self, render_style: RenderStyle = RenderStyle.REALISTIC) -> str:
        """构建最终渲染prompt（character_tags + visual + style_suffix）"""
        visual = self.to_visual_prompt()

        # 角色材质标签
        char_part = self.character_tags if self.character_tags else ""

        # 风格后缀
        suffix = self.style_suffix
        if not suffix:
            suffix = REALISTIC_SUFFIX if render_style == RenderStyle.REALISTIC else COMEDY_SUFFIX

        # 组装
        parts = [p for p in [char_part, visual, suffix] if p]
        self.final_render_prompt = ", ".join(parts)
        return self.final_render_prompt


class PacingCheckpoint(BaseModel):
    """节奏卡点"""
    label: PacingLabel
    word_range: list[int]       # 字数区间
    time_range: list[float]     # 秒数区间
    rule: str                   # 规则描述
    visual_action: str = ""     # 画面动作
    dialogue: str = ""          # 台词/旁白
    emotion: str = ""           # 情绪标签
    passed: bool = True         # 双轴校验结果


class Cliffhanger(BaseModel):
    """断崖钩子"""
    type: str = "reveal"        # reveal/question/action/shock
    line: str = ""              # 钩子台词/画面描述
    unanswered_question: str = ""  # 未回答的问题


class VisualConsistency(BaseModel):
    """角色视觉一致性（跨镜头保持）"""
    character_name: str
    appearance: str = ""        # 外貌描述（发型、体型、特征）
    default_attire: str = ""    # 默认服装
    voice_tone: str = ""        # 声线描述（供TTS）
    visual_tags: str = ""       # 英文材质标签（注入prompt）
    reference_images: list[str] = Field(default_factory=list)  # 参考图路径


class Episode(BaseModel):
    """短剧单集"""
    episode_number: int
    title: str = ""
    render_style: RenderStyle = RenderStyle.REALISTIC  # 渲染风格
    duration_estimate_seconds: int = Field(ge=10, le=300, description="目标时长（秒）")
    word_count_estimate: int = Field(ge=500, le=10000, description="目标字数")

    # 节奏卡点（双轴校验）
    pacing_checkpoints: list[PacingCheckpoint] = Field(default_factory=list)

    # 镜头清单
    shots: list[Shot] = Field(default_factory=list)

    # 断崖
    cliffhanger: Cliffhanger = Field(default_factory=Cliffhanger)

    # 角色视觉一致性
    visual_consistency: list[VisualConsistency] = Field(default_factory=list)

    # 元数据
    hook_density: str = "high"      # high/medium/low
    scene_count: int = 0
    characters_involved: list[str] = Field(default_factory=list)

    # 输出
    script_text: str = ""           # 剧本文档（纯文本）
    shot_prompts: list[dict] = Field(default_factory=list)  # 分镜提示词包

    def get_total_shot_duration(self) -> float:
        """所有镜头总时长"""
        return sum(s.duration for s in self.shots)

    def validate_duration(self) -> bool:
        """校验镜头总时长是否在目标范围内"""
        total = self.get_total_shot_duration()
        return abs(total - self.duration_estimate_seconds) <= 10

    def build_all_final_prompts(self) -> list[dict]:
        """为所有镜头构建最终渲染prompt"""
        results = []
        for shot in self.shots:
            prompt = shot.build_final_render_prompt(self.render_style)
            results.append({
                "shot_id": shot.shot_id,
                "final_render_prompt": prompt,
                "duration": shot.duration,
                "shot_type": shot.shot_type.value,
                "location": shot.location,
            })
        return results


class BeatSheet(BaseModel):
    """结构化动作指令集（timeline.json用）"""
    chapter: int
    beats: list[dict] = Field(default_factory=list)
    # 每个beat: {"beat": "0-20%", "action": "...", "location": "...", "characters": [...]}


class LocationJump(BaseModel):
    """位置跳跃检测结果"""
    from_location: str
    to_location: str
    paragraph_index: int
    is_valid: bool = True
    reason: str = ""
