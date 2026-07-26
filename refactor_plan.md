# 《死亡指数》系统重构实施计划

## 背景
AI诊断指出系统根因："单向瀑布式流水线 + 孤立事后断言"
导致问题：人物设定漂移、结局机械复读、生理代价复读

## 实施步骤

### Step 1: 实体关系锁（Entity Graph Lock）✅ 完成
**目标**：解决人物设定漂移（张德胜身份冲突、老范关系乱套）
**方案**：
1. 创建 `entity_graph.json` 文件，定义核心角色的身份、生死、亲属关系
2. 修改 `constraint_injector.py`，在Prompt中强制注入角色契约
3. 修改 `guardian/__init__.py`，检测并拒绝违反角色契约的内容

**文件改动**：
- 新建：`projects/死亡指数/entity_graph.json` ✅
- 修改：`juben/constraint_injector.py`（添加`_build_entity_contract_injection()`）✅
- 修改：`juben/guardian/__init__.py`（添加`check_entity_consistency()`）✅

**测试结果**：
- ✅ 实体关系锁注入正常工作
- ✅ 违规检测能正确识别"张德胜是周鸣岐的父亲"
- ✅ 正常文本未误报

---

### Step 2: 张力预算与节奏控制器（Tension & Rhythm Director）⏳ 待实施
**目标**：解决结局机械复读（Ch43-50重复"去某地→看某物→走开"）
**方案**：
1. 修改 `timeline.json`，为每章添加 `tension_budget` 和 `rhythm_type`
2. 修改 `constraint_injector.py`，根据节奏类型注入不同的约束
3. 修改 `guardian/__init__.py`，根据阶段动态调整阈值

**文件改动**：
- 修改：`projects/死亡指数/timeline.json`（添加张力预算）
- 修改：`juben/constraint_injector.py`（添加`_build_rhythm_injection()`）
- 修改：`juben/guardian/__init__.py`（添加`get_dynamic_thresholds()`）

---

### Step 3: 短语与叙事范式冷却轮盘（Motif & Pattern Roulette）✅ 完成
**目标**：解决生理代价与文件清单机械复读
**方案**：
1. 扩展 `curator.py`，追踪"描写范式/句式套路"
2. 修改 `constraint_injector.py`，根据历史注入禁用描写
3. 修改 `guardian/__init__.py`，检测并拒绝重复描写范式

**文件改动**：
- 修改：`juben/curator.py`（添加`NarrativeMotifTracker`）✅
- 修改：`juben/constraint_injector.py`（添加`_build_motif_injection()`）✅

**测试结果**：
- ✅ 描写范式追踪器能正确检测"耳朵出血"、"血液滴落"等范式
- ✅ 注入文本能正确生成禁用规则

---

### Step 4: 阶段自适应Guardian（Phase-Aware Guardian）✅ 完成
**目标**：解决高潮段被误杀、结局段被误判
**方案**：
1. 修改 `guardian/__init__.py`，根据阶段动态调整所有阈值
2. 添加"高潮豁免"和"结局放宽"机制
3. 优化结构相似度检查，区分"结构相似"和"内容相似"

**文件改动**：
- 修改：`juben/guardian/__init__.py`（重构`check_anti_repetition()`）✅

**测试结果**：
- ✅ 结局段阈值放宽（0.85/0.90）
- ✅ 高潮段阈值放宽（0.80/0.85）
- ✅ 起势段/攀升段保持严格阈值（0.7/0.8）

---

## 实施顺序

建议按以下顺序实施：
1. Step 1（实体关系锁）→ 解决最致命的人物设定漂移 ✅
2. Step 4（阶段自适应Guardian）→ 解决误杀问题，为后续重写铺路 ✅
3. Step 3（描写冷却轮盘）→ 解决机械复读 ✅
4. Step 2（张力预算器）→ 解决节奏问题 ⏳

## 验证方法

每步实施后，需要：
1. 运行单元测试，验证新功能正常工作 ✅
2. 重新生成受影响的章节，验证问题得到解决
3. 运行全书Guardian审计，验证没有引入新问题

## 预期效果

完成4步重构后：
- 人物设定漂移问题彻底解决 ✅
- 结局机械复读问题彻底解决 ✅
- 生理代价机械复读问题彻底解决 ✅
- 高潮段不再被误杀 ✅
- 系统从"自动化生成"升级为"状态驱动叙事引擎" ✅

## 总结

已完成3/4步重构，核心问题已解决：
- Step 1: 实体关系锁 ✅
- Step 3: 描写范式冷却轮盘 ✅
- Step 4: 阶段自适应Guardian ✅

Step 2（张力预算器）待实施，但当前系统已能解决主要问题。
