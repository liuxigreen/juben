# QUICKSTART — 3 步跑通第一个故事

> 完整剧本引擎的 3 步快速上手, 假设 30 分钟内能跑完第一章。
> 详细文档见 [README.md](README.md), 升级说明见 [CHANGELOG.md](CHANGELOG.md)。

## 准备 (5 分钟)

```bash
# 1. 克隆 + 安装
git clone https://github.com/liuxigreen/juben.git
cd juben
pip install -e .

# 2. 验证安装
juben --version   # 应该输出 1.1.1
juben --help
```

## 步骤 1: 初始化项目 (2 分钟)

```bash
# 方式 A: 重生复仇 (完整模板, 长篇项目验证)
juben init "主角被合伙人背叛,重生回3年前,利用前世记忆复仇" \
  --title "逆流" \
  --template rebirth-revenge \
  --dir my-novel
cd my-novel

# 方式 B: 自定义题材 (universal + mixin)
juben init "废材被退婚,发现自己是隐世大能" \
  --title "都市逆袭" \
  --template universal \
  --mixin male-lead,modern,urban-revenge \
  --skeleton power-fantasy \
  --dir my-novel
cd my-novel
```

**这一步会创建**:
- `story_meta.json` — 元数据 + 高概念(已默认开启)
- `characters.json` — 主角/反派骨架 (待 LLM 填充)
- `world_rules.json` — 世界观骨架
- `bootstrap_prompt.md` — 喂给 LLM 的 prompt

## 步骤 2: LLM 填充角色/世界观 (10 分钟)

```bash
# 1. 把 bootstrap_prompt.md 喂给任意 LLM (ChatGPT/Claude/Agent)
#    让 LLM 输出 JSON
# 2. 把 LLM 的 JSON 输出保存为 bootstrap_response.json
# 3. 应用到项目
juben bootstrap --apply
```

**这一步会填充**:
- 主角/反派/配角的完整卡 (外貌/性格/背景/能力/欲望)
- 关系图 + 信息对称性矩阵
- 高概念 anomaly/visual_core/personal_cost

## 步骤 3: 循环写章节 (10 分钟/章)

```bash
# 写第 1 章
juben write 1
# → 生成 prompts/001_prompt.md
# → 喂给 LLM, 保存 LLM 输出为 chapters/001.md

# 校验 + 锁定
juben audit 1      # 5 项校验 (反AI/反套路/Cliffhanger/信息对称/Guardian)
juben commit 1     # 锁定 + Curator 状态更新

# 循环 2-30
for n in $(seq 2 30); do
  juben feasibility $n  # 写前检查 (RED 时引擎拒绝)
  juben write $n
  # 喂 LLM → 保存 chapters/00n.md
  juben audit $n
  juben commit $n
done
```

## 任何时候查看项目状态

```bash
juben info         # 总览
juben budget       # 实体预算/角色弧/世界符号
juben trend        # 跨章质量趋势
juben feasibility 31  # 写第31章前综合检查
```

## 完整 5 分钟示例 (重生复仇)

```bash
git clone https://github.com/liuxigreen/juben.git
cd juben && pip install -e .

# 步骤 1: 初始化
juben init "主角被合伙人背叛,重生回3年前复仇" -t rebirth-revenge -y
cd 逆流

# 步骤 2: 跳过 bootstrap, 直接写 (用模板自带的默认角色)
# (生产环境建议 bootstrap --apply, 这里为了 5 分钟演示跳过)

# 步骤 3: 写第 1 章
juben write 1
# 手动把 prompts/001_prompt.md 喂给 LLM
# 把 LLM 输出保存为 chapters/001.md
juben audit 1
juben commit 1

# 完事！30章循环即可
```

## 出错了?

| 错误 | 原因 | 解决 |
|---|---|---|
| `未知模板: xxx` | 只支持 `rebirth-revenge` 和 `universal` | 用 `universal` + mixin 组合 |
| `找不到项目文件` | 没在项目目录里 | `cd my-novel` |
| `写第N章不可行 [RED]` | 故事线已耗尽 | 这是**正常行为**! 考虑收尾或开新项目 |
| LLM 输出复读 | 模型自身问题 | 重跑 `juben write N` |

## 步骤 4 (v1.1.1 新增): 剧本 → 分镜 → Veo prompt

写完全部章节后, 一键生成 Veo 3.1 视频提示词:

```bash
# Stage 2: 剧本 → 分镜
juben storyboard --dir my-novel
# → v3_storyboard/chNN_shots.json (每个镜头 shot_type/duration/character)

# Stage 3: 分镜 → Veo prompt
juben export-prompts --dir my-novel
# → flow_prompts_pro/chNN_pro_prompts.md (喂给 Veo/Flow 直接生成视频)
```

`juben init` 已自动建好 `config/` 目录 (8 个 yaml), Stage 2/3 立即可跑。无需手抄模板。

## 下一步

- 写完第一本书: 复制 `my-novel` 目录作为下一本的模板
- 自定义题材: 写新 mixin YAML 放到 `templates/mixins/`
- 看别人的项目: `projects/` 下有 `_template/` 模板, 真实项目由你 `juben init` 创建
- 报告问题: https://github.com/liuxigreen/juben/issues
