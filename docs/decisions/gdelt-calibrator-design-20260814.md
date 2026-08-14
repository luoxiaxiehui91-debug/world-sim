# GDELT 分数校准器设计（tianji_calibrator.py）

> 日期：2026-08-14 · 状态：待用户过目批准 · 关联：task #81（GDELT 分数体系全链路审计 + 校准）
> 前置审计：`docs/decisions/gdelt-scores-audit-20260814.md`（9 维度归一化整体失准）

## 1. 背景

审计确认 GDELT 分数体系 9 维度归一化整体失准：
- **social_stress 虚高 ~30 分**：`scan_weak_signals.py:840` `_TONE_BASE = -7.0`，注释自写"实测校准值"，但实测 tone 基准是 **-7.97** → 普通冲突状态被算成 32 分起跳，国家级中位 UKR 73 / CHN 70 / RUS 64
- **7 个计数维度压扁**（military/tension/protest/sanction/coop/religious/regime）：scale 按"2022-02-24 俄乌开战日绝对峰值 /0.9"估算，但 12h 窗口实际计数只有估算的 1/6~1/20 → 分数永远 0-3，告警阈值 35/60 永远达不到，维度实际"死"的
- **GRV 侧已有半成品**：`geo_risk_vector.py:_compute_gdelt_p95_dynamic`（58-126 行）已在从 gdelt_history.jsonl 动态算热点组合 P95（样本 <100 fallback 硬编码）——思路对但只覆盖 GRV 自身热点组合，与 scan 的 scale 两套逻辑并存

**归因错位**（用户指出）：归一化校准本质是"验证 + 反哺"，属**天玑职责域**（tianji_verifier 干的是同一类活），现状却硬编码在天枢。本次方案 B = 把校准机制建到天玑，形成"采集 → 验证 → 反哺"闭环。

## 2. 目标

1. 新增天玑校准器 `tianji_calibrator.py`：读 `gdelt_history.jsonl` → 算校准配置 → 写 `gdelt_calib.json`
2. 天枢消费改造：`scan_weak_signals.py` + `geo_risk_vector.py` 统一读 `gdelt_calib.json`（fallback 硬编码），退役 GRV 内嵌的 P95 半成品
3. 触发：复用 watchdog → tianji_verifier 顺带调用（函数级独立，可拆独立 trigger）

## 3. 模块设计（tianji_calibrator.py，天玑容器 /app）

**放置**：git 树 `macro-ji/tianji_calibrator.py` → 重建天玑镜像（COPY 模式）进 `/app`。

**输入**：`/app/macro_data/gdelt_history.jsonl`（天玑已挂载天枢 data，rw，零障碍；记录结构 `{"date": "...", "scores": {"military": {"USA": 8.9, ...}, ...}}`）

**计算逻辑**（三个独立函数，均纯只读）：

```
run_calibration()                  # 入口：跑全部，写 gdelt_calib.json
├── _compute_dim_scales(records)   # ① 9 维度 P95
│     对每维度：收集全部 国家×日期 的值 → 排序 → P95（95 分位）
│     输出 {dim: p95}，sample_count 记录参与样本
├── _compute_tone_base(records)    # ② social_stress tone 基准
│     对每维度 social_stress：该维度分数是 tone 均值派生，
│     需复现 mean_tone 反推：base = 使历史 social_stress 中位≈0 的 tone 值
│     （简化：直接用 history 里冲突事件 tone 均值分布的 P50，实测 -7.97）
└── _compute_hotspot_p95(records)  # ③ GRV 热点组合 P95（从 GRV 搬迁逻辑）
      热点组合定义 = GRV 的 _gdelt_country_score（mil+sanc 等组合，逐国）
      对每个热点（taiwan_strait/us_china_strategic/...）：算组合分 → P95
```

**输出**：`/app/macro_data/gdelt_calib.json`（= 天枢 `data/gdelt_calib.json`，同一挂载）

## 4. 配置格式 gdelt_calib.json

```json
{
  "generated_at": "2026-08-14T08:30:00+00:00",
  "sample_count": 407,
  "min_sample": 100,
  "scales": {
    "military": 35.2, "tension": 18.4, "protest": 12.1,
    "sanction": 22.7, "coop": 900.0, "religious_conflict": 4.2,
    "regime_change": 3.1, "cultural_friction": 1.9
  },
  "tone_base": -7.97,
  "hotspot_p95": {
    "taiwan_strait": 12.4, "us_china_strategic": 8.9,
    "russia_europe": 15.2, "middle_east_energy": 11.7, "...": 0.0
  },
  "source": "gdelt_history.jsonl",
  "version": 1
}
```

- `scales`：scan 计数类维度归一化 scale（P95 替代"估算峰值/0.9"）
- `tone_base`：scan social_stress 基准线（替代硬编码 -7.0）
- `hotspot_p95`：GRV 热点组合归一化（替代 GRV 进程内自算）
- `min_sample`：样本 <100 时消费方 fallback 硬编码（与 GRV 现有规则一致）

## 5. 天枢消费改造（热挂载，rsync 即生效）

### 5.1 scan_weak_signals.py
| 位置 | 现状 | 改后 |
|------|------|------|
| `_TONE_BASE`（840 行） | 硬编码 -7.0 | `calib.get("tone_base", -7.0)` |
| 计数维度 scale（858 行附近） | 俄乌日峰值/0.9 估算 | `calib.get("scales", {}).get(dim, fallback)` |
| 加载 | 无 | 模块级 `_load_calib()`（读 data/gdelt_calib.json，缺失/解析失败 fallback 常量） |

### 5.2 geo_risk_vector.py
| 位置 | 现状 | 改后 |
|------|------|------|
| `_compute_gdelt_p95_dynamic`（58 行） | 进程内读 history.jsonl 自算（半成品） | **退役**，改 `_load_gdelt_p95()` 读 calib.hotspot_p95 |
| `_GDELT_P95_FALLBACK`（47 行） | 硬编码 fallback | 保留（calib 缺失时兜底） |

## 6. 触发方式（用户拍板：verifier 顺带跑）

`tianji_verifier.py` `__main__`（475 行）在验证流程后追加一行：

```python
try:
    from tianji_calibrator import run_calibration
    run_calibration()
except Exception as e:
    print(f"[CALIB] 校准器失败（非阻断）: {e}")
```

- watchdog 触发 verifier 时顺带刷新校准配置（verifier 触发频率 ≈ 校准刷新频率，对慢变量足够）
- **函数级独立**：将来要拆独立 trigger 只加一行调用，不结构性绑定
- 校准器失败不阻断 verifier（打印 + 走 watchdog 日志通道）

## 7. 部署步骤

```
1. git 树 macro-ji/tianji_calibrator.py 落码（py_compile 验）
2. 重建天玑镜像：macro-ji 下 docker compose build + up -d（几分钟，天玑容器重启）
3. 手动跑一次校准器：docker exec macro-scan-tianji-1 python /app/tianji_calibrator.py
   → 验证 gdelt_calib.json 生成（数值 vs 审计报告 P95 对照）
4. 天枢消费改造（scan + GRV）→ rsync 热挂载 → py_compile
5. 重跑 scan_weak_signals.py + geo_risk_vector.py → 验证分数分布：
   - social_stress 国家级中位回落（UKR 73 → ~0 附近，符合设计意图）
   - military 等维度恢复区分度（0-30 常态、真峰值 70-100）
6. 双读校验台 + 探针复跑（不应有回归）
7. git commit + push
```

## 8. 验证方案（验收标准）

| 项 | 标准 |
|----|------|
| 校准器输出 | gdelt_calib.json 生成，scales/tone_base/hotspot_p95 与审计实测对照一致（P95 容差 ±5%） |
| scan 重跑 | social_stress 中位回到 ~0；计数维度 max 落在 70-100 区间；8 国告警数减少（仅真压力触发） |
| GRV 重跑 | grv_latest.json 的 social_stress 透传值回落；区域维度（台海/中美）数值连续无跳变 |
| 探针/harness | 全绿，无回归 |
| 行为影响确认 | 告警阈值 35/60 语义变化（更严=只报真压力）→ 用户确认接受 |

## 9. 回滚

- **瞬时回滚**：删除/改名 `data/gdelt_calib.json` → 消费方 fallback 硬编码自动生效（原行为），零代码回滚
- **代码回滚**：git revert 天枢两文件（热挂载恢复）；天玑校准器是新增文件不涉及回滚（不调用即无副作用）
- 校准器幂等：每次重跑覆盖配置，无累积状态

## 10. 风险与权衡

| 风险 | 缓解 |
|------|------|
| 校准后告警行为变化（某些国家降阈值下，告警变少） | 校准方向 = 修正系统性虚高，属预期；落码前用户已确认接受 |
| GRV 热点 P95 从"进程内自算"变"读配置"，新鲜度依赖校准器触发 | verifier 顺带跑保证每次验证刷新；fallback 兜底 |
| 天玑重建镜像窗口天玑短暂不可用 | 天玑非实时链路（验证/校准慢任务），分钟级窗口无影响 |
| calib 样本变化导致分数体系漂移 | min_sample=100 门控 + generated_at 记录，异常分布可追溯 |
