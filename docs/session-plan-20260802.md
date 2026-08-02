# 今晚作业方针（2026-08-02 夜间 → 2026-08-03 早晨）

> 约束：本地 Claude Code 作业，今晚到明早。代码写完提交本地 git，之后由接手方（Hermes/NAS 部署者）拉取部署验证。
> 原则：能写完的都写完，留给接手方的是可运行代码而非待办事项。

---

## 背景：为什么现在改这些

2026-08-02 完成了两件独立工作：
1. **arch_review_20260802.md** — 六角色三轮辩论，裁定15个已确认设计缺陷+五条铁律
2. **设计意图vs实现对照分析** — 51条逐一核查，得出18%已实现/31%部分/51%未落地

核心结论：系统最大问题是 **D1-D6 六个 P0 代码缺陷**，让已实现的功能也产出不可信数值。
在这些修复之前，任何扩展都是沙基建楼。

---

## 今晚作业范围（按优先级）

### Tier 1：今晚必须完成（P0 hotfix + P1 运营基础设施）

| # | 任务 | 文件 | 工期估计 | 状态 |
|---|------|------|---------|------|
| 1 | **D12 修复**：target_metric 字段与 content 描述不匹配 | `macro-sim/run.py` | 30min | ⬜ |
| 2 | **D4 修复**：`apply_natural_decay` 遗漏 4 个内生变量（无均值回归导致单调漂移） | `macro-sim/core/world_state.py` | 20min | ⬜ |
| 3 | **D1 修复**：传导矩阵全量 delta 叠加 → 改为 per-agent delta 追踪 | `macro-sim/core/simulation.py` | 60min | ⬜ |
| 4 | **grv_weights.yaml 外部化**：慢变量权重从硬编码提取为 YAML 配置 | `macro-scan/核心代码/slow_variables.py` + 新建 `macro-scan/config/grv_weights.yaml` | 40min | ⬜ |
| 5 | **慢变量 cron 幂等保护**：`compute_all()` 加 last_updated 时间戳，同月跳过重算 | `macro-scan/核心代码/slow_variables.py` | 20min | ⬜ |
| 6 | **source_dimension_map.yaml 启动校验**：天枢启动时检验映射完整性，遗漏即报错 | `macro-scan/核心代码/` 新建 `startup_checks.py` | 30min | ⬜ |
| 7 | **Brier/BSS 计算逻辑**：从字段预留变为可运行代码 | 新建 `macro-scan/核心代码/brier_calc.py` | 60min | ⬜ |
| 8 | **_load_manual_score 降级修复**：未输入时读上月值而非 default，输出标注 `[手工评估待更新]` | `macro-scan/核心代码/slow_variables.py` | 20min | ⬜ |

### Tier 2：时间允许则做（P0 hotfix 续）

| # | 任务 | 文件 | 工期估计 | 状态 |
|---|------|------|---------|------|
| 9 | **D7 修复**：MacroWorldState + world_state.py 接入 6 个新 GRV 维度（russia_europe/taiwan_strait/social_stress 等） | `macro-sim/core/world_state.py` | 45min | ⬜ |
| 10 | **月度验证 cron 骨架**：新建 `macro-scan/核心代码/verify_predictions.py`，FRED 自动拉取 + Brier 计算 + ntfy 推送 | 新建文件 | 60min | ⬜ |

### Tier 3：如果还有时间

| # | 任务 | 备注 |
|---|------|------|
| 11 | D6 修复：校准结果持久化到 `calibration_state.json`，重启后继续而非重置 | calibrator.py |
| 12 | D5 修复：台海触发阈值 68 → 改为相对阈值（us_china_grv > baseline × 1.3） | simulation.py |

---

## 不做的事（明确排除）

- B+A/NOVEL 重写范畴（Agent 架构、4批次执行、三层激活）— 等 D1-D6 修完后另起 Sprint
- 分类治理（玉衡/prior.yaml/冻结期）— arch_review 已裁定永久搁置
- 非英语叙事处理 — 阶段三项目
- 57 个预测目标子类型 — 天玑 V1 跑通后再做

---

## 给接手方的部署流程

完成作业后 `git add -A && git commit`，接手方执行：

```bash
# NAS
cd /vol2/1000/software/world-sim
git pull

# macro-scan（含 slow_variables.py 改动）
docker restart macro-scan-macro-scan-1

# macro-sim（含 simulation.py / world_state.py / run.py 改动）
docker compose up --force-recreate

# 验证
docker exec macro-sim python -c "from core.simulation import gm_resolve_rules; print('D1 fix OK')"
docker exec macro-sim python -c "from core.world_state import apply_natural_decay; print('D4 fix OK')"
docker exec macro-scan python 核心代码/slow_variables.py  # 观察是否跳过本月重算
```

---

## 关键背景（接手方必读）

### D1 修复说明
原代码的传导矩阵把「所有 Agent 的累积 delta」再乘以传导系数叠加，导致 N 个 Agent 激活时传导强度 = 单 Agent 的 N 倍。
修复方案：每个 Agent 产出自己的 per-agent delta，传导矩阵只传该 Agent 自己的 delta（不跨 Agent 叠加）。

### D4 修复说明
`apply_natural_decay` 遗漏了 4 个内生变量衰减：`fund_risk_appetite`、`em_capital_outflow`、`china_credit_impulse`、`us_fiscal_pressure`。这 4 个变量会单调漂移到边界并锁死。

### D12 修复说明
`_archive_to_tianji` 中 GRV 预测的 `content` 字段写的是 "台海" 情景，但 `target_metric` 写的是 `global_composite`（全局合成值）。验证时实际测量的是 `global_composite`，与预测描述不一致，导致 Brier 分评的是错误变量。
修复：`target_metric` 改为 `taiwan_strait`，或 `content` 改为明确引用 `global_composite`。

### grv_weights.yaml 说明
新建 `macro-scan/config/grv_weights.yaml`，将 GCI/UCRI/IRP 中的硬编码权重（0.40/0.35/0.25 等）全部迁移到该文件。`slow_variables.py` 启动时读取，天玑 V2 写回权重时直接修改该文件。

### source_dimension_map.yaml 校验说明
`startup_checks.py` 新建函数 `check_source_dimension_map()`，读取 `source_dimension_map.yaml`，对照 `geo_risk_vector.py` 已知的 11 个 GRV 维度，遗漏则 `raise RuntimeError` 阻断启动。
天枢 `scheduler.py` 在启动处调用此函数。

### Brier 计算说明
新建 `brier_calc.py`：
- `compute_brier_score(predicted_prob, outcome)` → Brier Score
- `compute_bss(brier_score, climatology_prob)` → BSS = 1 - BS/BS_climatology
- `compute_sharpness(prob_list)` → 锐度（预测在30%-70%以外比例）
climatology_prob 默认用 0.5（最大熵基准），可在调用时传入历史频率。

---

## 完成后 HANDOVER.md 更新要点

- 标注已修复的缺陷编号（D1/D4/D7/D12 等）
- 新增文件列表（brier_calc.py / startup_checks.py / grv_weights.yaml）
- 更新「待部署操作清单」
- 标注「接手方需手动验证的项目」
