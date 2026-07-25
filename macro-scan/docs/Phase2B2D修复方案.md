# social_stress / cultural_friction 修复方案（Phase 2B/2D）

> 编写：Claude | 2026-07-25  
> 版本：v3.5.61 时调查，目标 v3.5.62  
> 状态：待实施

---

## 一、问题根因（调查结论）

代码**已全部写好**，bug 在归一化参数，不是功能缺失。

### social_stress — 始终为空 {}

**代码位置**：`scan_weak_signals.py` `_compute_gdelt_scores()` 约第820-848行

**根因**：用 `GoldsteinScale` 均值作社会情绪代理，但计算范围是**全部 GDELT 事件**（合作/外交/军事均含）。合作类事件（CAMEO root 0x/1x/2x）占绝对多数，把均值持续拉到正区间，触发条件 `mean_tone >= 0 → 返回0.0` 永远成立。

**验证**：`gdelt_scores.json` 中 `social_stress` 字段始终为 `{}`，自 R07 上线至今从未有值。

**正确做法**：只对 `_CAMEO_PROTEST | _CAMEO_TENSION | _CAMEO_MILITARY` 这些冲突类事件计算 Goldstein 均值，排除合作类事件的干扰。

### cultural_friction — scale 严重高估，永远不触发

**代码位置**：`scan_weak_signals.py` 第861行 `_norm(cultural, 3000)`

**根因**：`scale=3000` 是拍脑袋的估算值，但实测 USA 当前最高分仅 3.2（mentions 累加约 96），scale=3000 对应的满分基准是约 93750 mentions，远超实际峰值。

**验证**：
```
cultural_friction 实测值：USA=3.2, IND=1.2, NGA=0.7 ...（全部 < 5）
R10 gdelt_threshold=20 → 需要国家分值 ≥ 20 才触发
当前分值比门槛低 6x+，规则永不触发
```

**正确做法**：重新校准 scale，使实际高风险情境（如新疆棉花事件级别）能达到 40-60 分。根据 `_ACTOR_CULTURE = {EDU, MED, IGO, NGO}` 参与的制裁/紧张事件，保守估算峰值 mentions 约 150-300，建议 `scale=200`。

---

## 二、改动清单（仅改 scan_weak_signals.py，共2处）

### 改动1：social_stress 计算逻辑（约第820-848行）

**改前**（有问题的版本）：
```python
# Phase 2B：社会情绪 — 用 GoldsteinScale 作 Tone 代理（负值=冲突）
tone_sum[c] += goldstein * mentions
tone_cnt[c] += mentions
```
以上在 `for c in countries:` 循环的**无条件累加**，把所有事件都算进去。

**改后**：
```python
# Phase 2B：社会情绪 — 只对冲突类事件计算 Goldstein 均值（排除合作事件干扰）
if root in (_CAMEO_MILITARY | _CAMEO_TENSION | _CAMEO_PROTEST):
    tone_sum[c] += goldstein * mentions
    tone_cnt[c] += mentions
```
加一个 root 过滤条件，只统计冲突/紧张/抗议类事件的情绪均值。

---

### 改动2：cultural_friction 归一化 scale（第861行）

**改前**：
```python
"cultural_friction":  _norm(cultural,   3000),  # Phase 2D：文化摩擦
```

**改后**：
```python
"cultural_friction":  _norm(cultural,    200),   # Phase 2D：文化摩擦（实测校准，原3000严重高估）
```

scale 从 3000 → 200，使当前 USA=3.2 的原始 mentions 归一化到约 1.6 分（仍属低风险），
但若 EDU/MED/NGO 参与的摩擦事件增至 400+ mentions，可达 20 分触发 R10 告警。

---

## 三、预期效果

| 维度 | 改前 | 改后 |
|:---|:---|:---|
| `social_stress` | 始终 `{}` | 高冲突日（如战争爆发、大规模抗议）相关国家出现分值 |
| `cultural_friction` USA | 3.2 → R10 永不触发 | 3.2 → 约 1.6；真实文化摩擦升温时可达 R10 门槛 20 |
| R09 规则 | 永不触发（无 social_stress 数据）| 多国同步高冲突情绪时可触发 |
| R10 规则 | 永不触发（分值比门槛低 6x）| 缩小至合理距离，真实事件可触发 |

---

## 四、实施步骤

仅改源码区，热挂载生效，无需重建镜像。

```
1. 编辑 S:\world-sim\macro-scan\核心代码\scan_weak_signals.py
   - 改动1：约第822行，加 root 过滤条件
   - 改动2：约第861行，scale 3000 → 200
2. 下次 weak_signal 任务运行后（00:00/06:00/12:00/18:00）
   检查 gdelt_scores.json 是否出现 social_stress 非空条目
3. 若 cultural_friction 分值合理（USA 在 1-5 之间），将 R09/R10 enabled: true
4. 追加 CHANGELOG + bump VERSION（3.5.62）
```

验收命令：
```bash
docker exec macro-scan-macro-scan-1 python3 -c "
import json
d = json.load(open('/workspace/data/gdelt_scores.json'))
sc = d['scores']
print('social_stress:', sc.get('social_stress', {}))
print('cultural_friction:', sc.get('cultural_friction', {}))
"
```

---

## 五、注意事项

### scale=200 仍是估算值

改后第一周建议观察 `gdelt_history.jsonl` 中 `cultural_friction` 各国峰值，
若 USA 持续在 5 以下（正常无事件状态），scale 可进一步调低至 100；
若某日因重大文化冲突事件出现 50+ 分，说明 scale 已合理。

### social_stress 与 R09 门槛的关系

`R09 gdelt_threshold=35`，改后需真实高强度冲突事件（如多国同日爆发大规模抗议）
才会触发。正常状态下预计每月 0-2 次，符合设计意图。

### R09/R10 启用时机

不要在代码改完后立即启用，先观察 **3-5 天**的 gdelt_scores.json 输出，
确认分值区间合理再把 `enabled: false` 改为 `true`。
