# R4h 结构性方案设计初稿（arch · 只设计不实施）

> 文档类别：方案设计初稿（DESIGN DRAFT）· 基于 data-r4g 阶段一归因定位的三个增长点
> 状态：待 R4h 裁决——所有参数数值留裁决，本稿只给改动位置/机制/预期/影响面/风险框架
> 基线：v2.0.37（R4e 引擎 + 归因映射修复，R4g 收尾态）

---

## 增长点①：方向闸补挡"cs 上升时放松"（EASE wrong 盲区）

**现状问题**：R4d 只加了收紧方向闸 `tighten_ok = (target_dir != "ease") or vix_stress > threshold*2.0`
（financial.py:78），挡住"cs 回落时收紧"（TIGHTEN wrong）。但反向盲区仍在：`target_dir=="tighten"`
（cs 上升、期望收紧）时，`ease_signal` 的普通分支（spread<250 / grv<0.25 中性线）仍可触发 EASE
→ 放松发生在应收紧的方向 → EASE wrong 残留（data：9→6 步）。

**改动位置**：`core/agents/financial.py` A2 `_decide_rules` —— `ease_signal` 计算处（约 L94-99），
对称补一个 `ease_ok` 方向闸（与 tighten_ok 镜像）。

**机制说明**：
- 语义：cs 上升（target_dir=="tighten"）时，EASE 属方向性错误，应挡死（除非极端豁免对称成立，或
  EASE 触发本身只依赖 level 线而非方向——二选一由裁决定，本稿不拍）。
- 与 R4d/R4e 方向 EASE 的关系：directional_ease（cs 回落时放宽 spread 350/grv 0.6 线）不受影响，
  只补"反向"这一侧。
- 风险点：`directional_ease` 现有逻辑在 layer-1 合成 ctx（无 cs_delta → neutral）下与 P0-2 逐字节
  同——补闸必须保持 neutral 分支行为不变，否则破坏 test_ease_layer1_ctx（1 断言）。

**预期效果**：EASE wrong 从 6 步方向继续收敛（目标 0 或接近 0）；n_active 保持（方向 EASE 转换
链不受影响）；credit consistency 潜在改善（错误放松不再稀释正确方向）。

**影响面**：仅 A2 规则层。测试影响预估：test_directional_ease（9）需补 1-2 条反向闸断言；
test_direction_gate（8）确认 target_dir=="tighten" 时 EASE 不再触发。断言数增不降。

**风险**：若对称极端豁免参数选择不当 → 过度挡 EASE → credit n_active 下降 → silence 超线复发
（R4d 前史）。需 R4h 裁决豁免口径。

---

## 增长点②：危机豁免 vix>1.0 常态化放行治理（TIGHTEN wrong 主源）

**现状问题**：TIGHTEN wrong 26 步全因豁免放行——`tighten_ok` 中 `vix_stress > threshold*2.0`
（vix>48）豁免在 vix bleed 下常态化触发。vix bleed（world_state.py:277-280）：sentiment<-0.5
连续 3 步 → vix += 2.0/步（max 20）→ vix 漂移最高达 168，豁免几乎恒真 → cs 回落时收紧不再被
方向闸约束 → TIGHTEN wrong 常态化。

**改动位置**：两层可选（裁决定）：
1. `core/agents/financial.py:78` tighten_ok 豁免条件（参数或触发前提）
2. `core/world_state.py:256-280` vix bleed 机制（阈值/步数/速率/max）

**机制说明**：
- 语义：极端豁免本意是"vix>48 真实危机时允许方向违规收紧"；但 vix bleed 是**内生正反馈**
  （sentiment 低 → vix 涨 → 豁免开 → 错误收紧 → sentiment 更低 → vix 再涨），豁免被自激放大。
- 治理方向（框架，数值留裁决）：① 收紧豁免的触发前提（如要求 vix 跳变/外生事件而非 bleed 累积）；
  ② 或限制 bleed 上限/速率；③ 或豁免加"非连续性"条件（仅 vix 单步大幅跳升时生效）。
- 与 growth ③联动：sentiment 回升（③）→ bleed 停止 → 豁免自然收敛，两方案可互为杠杆。

**预期效果**：TIGHTEN wrong 从 26 步大幅收敛；direction gate 语义恢复（cs 回落时收紧回到
"仅真危机"）；vix bleed 漂移上限收敛。

**影响面**：A2 规则层 + world_state 动力学（若动 bleed）。测试影响预估：test_direction_gate（8）
需补"豁免条件下仍挡"断言；world_state 无直接断言（bleed 由 run_probe 集成验证）。

**风险**：R4d 回退预案正是为防 directional_ease 触发率低 → silence 超线（0.57>0.50 前史）。
若豁免收得过紧 → 正确 TIGHTEN 也被挡 → silence 复发。必须与 ①③ 联动评估，避免单点收紧。

---

## 增长点③：sentiment 写者结构（grv_down 0.685 reverse 根因）

**现状问题**：A2 EASE_CREDIT 只写 bank_credit_tightening（-0.25）与 liquidity_premium（-0.08），
**不写 market_sentiment**（simulation.py:145-147）；而 TIGHTEN 写 sentiment -0.08（L141）、A3
SHORT 写 -0.18、A6 写 -0.15 → sentiment 负写者主导、宽松信号不传导情绪回升 → sentiment 长期
贴 floor → grv_down（sentiment 对 grv 下行的响应）reverse 0.685（负向反而更强）。

**改动位置**：`core/simulation.py` gm_resolve_rules EASE_CREDIT 分支（L144-147）——补写
market_sentiment 正向分量（幅度留裁决；需对称于 TIGHTEN 的 -0.08 或按宽松乘数）。

**机制说明**：
- 语义：EASE（信贷宽松）在现实语义上应传导情绪回升（资金面转松 → 风险偏好回升）。当前
  EASE 对 sentiment 零直接副作用（R4e 注释也明确此点），是"保守选择"而非设计必然。
- 与 ② 联动：sentiment 回升 → vix bleed 停止 → 危机豁免收敛（增长点②自然缓解）。
- 与 P0-2 幅度对称的关系：TIGHTEN 写 -0.08，EASE 补写 +0.08×乘数可保对称；但 EASE 触发率
  高于 TIGHTEN（directional_ease 放宽），乘数需防 sentiment 过冲。

**预期效果**：grv_down reverse 收敛（向正向或至少中性）；sentiment 不再恒贴 floor；
vix bleed 触发步数下降。

**影响面**：market_sentiment 动力学（所有依赖 sentiment 的 agent 决策、vix bleed、soul 层）。
测试影响预估：无直接单测断言 EASE 写 sentiment（gm_resolve_rules 无独立单测，集成验证）；
需在 run_probe 层观察 sentiment 分布/grv_down。断言数不变。

**风险**：sentiment 过冲 → A3/A6/A10 等 sentiment 驱动 agent 行为偏移 → merged p̂ 变化；
需 R4h 定乘数 + 5 seed 集成验证。与 ② 属同一根因链（sentiment 低 → bleed），建议联动裁决。

---

## 建议的 R4h 裁决顺序（框架）

1. ③ sentiment 写者（根因链上游：sentiment 低 → bleed → 豁免 → 错误收紧）先裁；
2. ② vix 豁免治理（依赖 ③ 效果，可先用 ③ 的集成数据验证 bleed 收敛再定豁免口径）；
3. ① 方向闸补挡（独立于 ②③，可并行，但需同批 5 seed 验收避免互相干扰）。

每项改动均需：bump CACHE_VERSION、同步相关断言、5 seed 独立验收（qa）、归因前后对比（data）。
