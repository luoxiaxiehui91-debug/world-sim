# GDELT 分数体系全链路审计（2026-08-14）

> 触发：用户发现开阳面板"新闻风险值都好高"（social_stress USA 60/RUS 63…）
> 方法：只读审计（scan_weak_signals 归一化逻辑 + gdelt_history.jsonl 407 条实测分布 + 下游消费链）
> 结论：**9 维度归一化整体失准**——1 个虚高（social_stress）+ 7 个压扁（military 等），校准参数需修正

## 一、9 维度分数分布（gdelt_history.jsonl 407 条实测）

| 维度 | 中位 | p90 | max | 历史峰值 | 判定 |
|------|------|-----|-----|---------|------|
| social_stress | **51.3** | 81.5 | 86.9 | — | 🔴 **虚高**（53% 时间 >50）|
| military | 1.3 | 1.9 | 2.7 | 17.1 | 🟠 **压扁** |
| tension | 0.1 | 0.1 | 0.2 | — | 🟠 **压扁** |
| protest | 0.4 | 0.6 | 0.9 | 5.2 | 🟠 **压扁** |
| sanction | 1.3 | 2.0 | 3.1 | 26.7 | 🟠 **压扁** |
| coop | 1.0 | 1.4 | 1.6 | — | 🟠 **压扁** |
| religious_conflict | 0.1 | 0.2 | 0.4 | — | 🟠 **压扁** |
| regime_change | 0.2 | 0.3 | 0.8 | — | 🟠 **压扁** |
| cultural_friction | 1.1 | 17.2 | 47.0 | 47.0 | 🟡 偶发冲高（USA 65 当前值）|

## 二、根因

### A. social_stress 虚高（基准线校准 bug）
`scan_weak_signals.py`：
```python
_TONE_BASE = -7.0   # 注释自写「低张力时期冲突事件典型均值，实测约 -7.97」
score = (mean_tone - BASE) / (-10 - BASE) * 100
```
- 实测基线 -7.97 被算成 `(-7.97+7)/(-3)×100 = 32 分`
- 典型冲突状态=32 分起跳，稍紧张即 60+ → **全系虚高 ~30 分**
- 国家级中位数：UKR 73 / EGY 71 / CHN 70 / FRA 69 / RUS 64 / PAK 62…（正常应为 0 附近）

### B. military 等 7 维度压扁（scale 估算过大）
- scale 设计意图"峰值事件=100"，但 12h 窗口实际计数远达不到：
  - military scale=135000，历史峰值分才 17.1（实际计数 ~23000）
  - sanction scale=45000，历史峰值 26.7
- 结果：平时 0-3 分、峰值 <27 分，**告警阈值 35/60 永远达不到，维度形同虚设**
- 注：scale 全是估算（注释明示"运行 3 个月后校准"），gdelt_history.jsonl 已积累 407 条可校准

## 三、链路影响

| 消费方 | 路径 | 影响 |
|--------|------|------|
| GRV 区域维度（台海/中美/俄欧/中东） | gdelt_scores 的 military+sanction 组合分 → **P95 动态归一化**（2026-08-04 P1-C 已修） | ✅ 相对合理 |
| GRV social_stress / cultural_friction | **直接透传** gdelt_scores（不重新归一化） | 🔴 虚高传染到 grv_latest.json（social_stress: 53.1）|
| GRV 推导维度（南海/朝鲜/印太/全球南方） | 压扁的 military/sanction × scale | 🟠 绝对值偏低（相对排序不变）|
| 告警（STRESS_WARN 35 / ALERT 60） | scan_weak_signals 自身 | 🔴 8 国长期告警 = 噪音 |
| 天璇 MC 调制 | run_macro_analysis 用 mc_engine 事件矩阵，**不直接读 gdelt_scores** | ⚪ 间接（告警→信号→推演）|

## 四、校准建议（待批准后落码）

1. **social_stress**：`_TONE_BASE -7.0 → -7.97`（一行，按注释实测值）
2. **military/tension/protest/sanction/coop/religious/regime 7 维度**：scale 改为 gdelt_history.jsonl **实测 P95**（复用 GRV 的 _GDELT_P95 思路）——平时 0-30、峰值 70-100，恢复区分度
3. **cultural_friction**：暂不动（中位 1.1 偏保守但偶发冲高可用；scale=200 已修过一次）

## 五、校准影响面与风险

- 面板显示：social_stress 从 51 中位回落到 0 附近（真压力才升高）✓ 用户诉求
- GRV social_stress：从 53.1 回落（grv_latest 变合理）
- 告警：8 国长期告警消失（噪音减少），真压力才触发
- 推导维度（南海等）：military/sanction 分数分布变化 → 推导值变化，需验证 GRV 输出合理性
- 风险：校准是参数改动，影响 GRV/告警/面板三处；落码后需重跑 scan_weak_signals + GRV 验证分布

## 六、结论

- 9 维度归一化参数**全部是估算值且整体失准**（1 虚高 + 7 压扁），只有 GRV 区域维度提前用了 P95 动态归一化（P1-C 先例）
- 校准方向明确（P95 实测驱动），无设计分歧 → 轻量 SOP 足够，落码后逐项验证
- 待用户批准后执行校准（改动 2 处：基准线 + 7 维度 scale 机制）
