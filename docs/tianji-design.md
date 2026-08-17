# 天玑（Tianji）— 北斗第三星：验证层设计文档

> 文档类别：意图（INTENT）· 设计
> 状态：**v1.0 现役版**（2026-08-04 独立容器上线 · 2026-08-06 config rw 修复后定稿）
> 定位：北斗七星第三星，天枢（macro-scan）+ 天璇（macro-sim）之上的**验证评估层**，对推演结果做事后验证、准确率追踪与校准反哺。
> 历史：旧 DRAFT v0.2（独立 verification.db / accuracy_dashboard 等设想）已废弃，仅存史 → `docs/archive/tianji-design-DRAFT-v0.2.md`
> **实施实录**（已实施变更的 commit hash + 版本记录，与本文档意图分离）：→ [`macro-ji/CHANGELOG.md`](../macro-ji/CHANGELOG.md)（v1.0.0 独立容器上线 2026-08-04；dom=1 触发笔误修复 6ba35ab 2026-08-06）

---

## 一、为什么需要天玑

天枢负责观测，天璇负责演化，但两者都缺一环：**结果验证**。

1. macro-sim 输出概率路径树，但没有系统性验证"上次预测对了吗"
2. 校准循环依赖历史数据，但校准参数对未来预测的**准确率**从未量化
3. 预测质量没有自动度量 → 权重反哺无从谈起

天玑 = **验证机**：收集预测、等待结果、自动评分（Brier）、触发权重反哺（玉衡）。

**定位裁定（arch_review_20260802）**：
- 天玑是**纯验证层**，不承担推演或采集职责
- 玉衡（权重写回）**并入天玑**，不独立成星（`weight_matrix.py` 同容器）
- 部署形态：**独立容器**（M1 已采纳，不挂 macro-sim 下）

## 二、系统定位与部署

```
天枢（macro-scan）── 每日观测 ──> 天璇（macro-sim）── 推演路径 ──> 天玑（macro-ji）
   ↑                                                                    │
   └────────── 校准权重更新（玉衡审批写回 grv_weights.yaml）──────────────┘
```

| 子系统 | 别称 | 定位 | 部署 | 端口 |
|--------|------|------|------|------|
| macro-scan | 天枢 | 观测层 | 热挂载 | :8899 |
| macro-sim | 天璇 | 仿真层 | COPY 容器 | — |
| **macro-ji** | **天玑** | **验证层** | **COPY 容器**（`macro-tianji:latest`，独立 compose） | 无 |
| （同容器） | 玉衡 | 权重矩阵 | weight_matrix.py | — |

- 容器：`macro-scan-tianji-1`（独立 compose `macro-ji/docker-compose.yml`，`restart: unless-stopped`，healthcheck 30s）
- **COPY 镜像模式**：容器内代码 ≡ 镜像烘焙 ≡ 仓库 `macro-ji/`（四文件 sha256 全等实测）；改码须 `docker compose build` + `up -d --force-recreate`
- 无端口暴露；由共享触发文件驱动（T2 机制）
- 依赖：仅 `pyyaml`（其余纯 stdlib）

## 三、架构与四件套

| 文件 | 职责 |
|------|------|
| `tianji_db.py` | DB schema + CRUD（8 张表，共享 forecast_tracker.db） |
| `tianji_verifier.py` | 验证运行器：`verify_quantitative()`（函数式）+ 地缘 ntfy 人工确认；Brier/BSS/锐度；反哺建议 |
| `weight_matrix.py` | 玉衡权重矩阵：双层 clip + Herfindahl 健康检查 + 连续方向警告；审批写回 |
| `verify_watchdog.py` | T2 触发 watchdog：3s 轮询 `tianji_trigger.json` |

### 3.1 数据模型（tianji_db.py，共享 DB）

数据库：**共享 `forecast_tracker.db`**（宿主 `/vol2/1000/software/macro-scan/data/forecast_tracker.db` ↔ 容器 `/app/macro_data/`，与天璇 macro-sim 共用同一 inode；WAL 模式三写者共存）。**非独立 verification.db**。

`predictions` 表（核心预测主张存档）：

```sql
CREATE TABLE predictions (
    id                    TEXT PRIMARY KEY,          -- 预测ID（uuid 文本，非自增整数）
    created_at            DATETIME NOT NULL,
    due_at                DATETIME NOT NULL,          -- 到期日（验证触发依据）
    scenario_id           TEXT,
    type                  TEXT NOT NULL CHECK(type IN ('quantitative','geopolitical')),
    prediction_target_type TEXT NOT NULL,             -- GRV维度/FRED序列/目标类型
    content               TEXT NOT NULL,              -- 预测主张自然语言描述
    outcome_definition    TEXT NOT NULL,              -- 预测时填写，不可修改
    target_metric         TEXT,                       -- FRED序列名 / GRV维度
    target_direction      TEXT,                       -- 'up'/'down'/'above'/'below'
    target_threshold      REAL,
    b_prob                REAL,                       -- B模块历史频率概率
    b_sample_count        INTEGER,
    b_max_similarity      REAL,
    llm_adj               REAL,                       -- A模块调整量
    final_prob            REAL,                       -- 最终概率（评分依据）
    prob_low / prob_high  REAL,                       -- NOVEL模式区间
    confidence_tier       TEXT CHECK(confidence_tier IN ('HIGH','LOW','VERY_LOW','NOVEL')),
    time_horizon          TEXT CHECK(time_horizon IN ('weekly','monthly','quarterly','yearly')),
    status                TEXT DEFAULT 'pending'
                              CHECK(status IN ('pending','verified','awaiting_human')),
    outcome_value         REAL,
    brier_score           REAL,
    brier_skill_score     REAL,
    verified_at           DATETIME,
    verified_by           TEXT                        -- 'auto' / 'human:<name>'
);
```

其余 7 张表：`reasoning_trace`（推理溯源，与 predictions 一对一）、`narrative_chunks`（叙事块，staleness 衰减）、`weight_update_log`（权重变更日志）、`forecasts` / `actuals` / `evaluations`（天璇仿真写）、`narrative_density_flags`（叙事密度监测）。

### 3.2 验证运行器（tianji_verifier.py）

**两型预测验证**：

| 类型 | 验证方式 | 流程 |
|------|---------|------|
| `quantitative` | **自动** | `verify_quantitative(pred)`：按 `target_metric` 从 FRED（`fred_history/{metric}.csv`）或 GRV（`grv_history.jsonl`，11 个 GRV 维度）取 `due_at` 时实际值 → 按 `target_direction`+`target_threshold` 转二值 outcome（1.0/0.0）→ `_compute_brier_score(prob, outcome)` → `update_prediction_verified(status='verified', verified_by='auto')` |
| `geopolitical` | **人工** | 状态置 `awaiting_human` → ntfy 推送确认请求（含 `verify <ID> 1/0` 回复格式）→ 维护者 `--confirm <ID> 1|0` 回调 `confirm_geopolitical()` 写入 outcome + Brier（verified_by='human'） |

**评分指标**（`_compute_*` 函数式）：

- **Brier Score** = `(final_prob − outcome)²`，单条越低越好（随机猜 = 0.25）
- **BSS（Brier Skill Score）** = `1 − BS_mean / BS_climatology`，气候基准 `bs_clim=0.25`（全部押 0.5）；**样本 ≥ 20 才给结论性趋势**（H05 门控，08-15 收紧），5-19 仅展示数值不判趋势；`>0` 表示有增量价值
- **锐度（Sharpness）** = `final_prob < 0.3 或 > 0.7` 的预测占比，目标 `>40%`

**反哺检查**（`check_and_generate_reweight_suggestions`）：
- 触发：已验证样本 ≥ `MIN_TRIGGER_N=8`，且同 `(signal_source, target_type)` 分组最近 8 条 Brier 均值 < 全体均值 × 80%（差于全体均值才触发降权）
- 产出：`pending_weight_adjustments.json`（去重：同 signal+target 只保留最新）+ ntfy 推送"玉衡权重调整建议"
- 建议权重：`weight_after = max(0.05, current × 0.85)`（降权 15%）

### 3.3 权重矩阵（weight_matrix.py，玉衡）

- 权重存储：`config/grv_weights.yaml`（宿主 `/vol2/1000/software/macro-scan/config/` ↔ 容器 `/app/config/`，**rw 挂载**，08-06 修复）
- 初始化：`init_weights_from_prior()` 从 `prior.yaml` 建矩阵（**prior.yaml 当前缺失**，初始化不可用 → 已知缺口）
- **双层 clip 约束**（`apply_weight_adjustment` 强制）：
  - 层1：单次变化速率 ≤ 当前值 ±25%（`MAX_CHANGE_RATE=0.25`）
  - 层2：绝对值范围 `[0.05, 5.0]`（`WEIGHT_MIN/MAX`）
- **健康检查**（`run_health_check`）：① 每预测目标有效信源数（weight>0.1）≥ 2；② Herfindahl 集中度超过初始基线 3 倍 → 警告；③ 有效信源占比 < 30% → 信源萎缩警告；level=critical 时 ntfy 告警
- **连续方向警告**（`_check_consecutive_direction`）：同一 (signal,target) 连续 4 次同方向调整输出 ⚠️ 警告（不阻止操作，建议填 notes）
- **审批流**：`list_pending_adjustments()` / `approve_adjustment(index)`（写入 + 记 weight_update_log + 移除条目）/ `reject_adjustment(index)`（记拒绝日志后移除）

### 3.4 触发 watchdog（verify_watchdog.py，T2）

**调度方式：不是 scheduler cron 直接跑验证，而是 T2 共享触发文件 + watchdog 轮询。**

```
天枢 scheduler 09:42 tianji_trigger job（dom=1-7）
  → write_tianji_trigger.py（macro-scan/核心代码/）：
      tmp → os.rename 原子写 tianji_trigger.json
      {batch_id: 日期, date, triggered_at, source, processed: false}
      幂等：同批未处理则不覆盖
  → 天玑 verify_watchdog.py 3s 轮询：
      检出未 processed → 执行 tianji_verifier.py（subprocess，600s 超时）
      → trigger["last_result"]={exit, ts} + processed=true 原地回写（tmp→rename）
```

幂等键：`batch_id`（=日期）；`processed` 标记保证同一批次只执行一次；JSON 损坏时跳过等下一轮。

## 四、数据流与共享数据

```
                    ┌── 天枢 ──┐      ┌── 天璇 macro-sim ──┐
                    │ scheduler │      │ 仿真写入 forecasts/  │
                    └─────┬────┘      │ evaluations/actuals  │
                          │           └─────────┬────────────┘
                 tianji_trigger.json             │
                          │                      ▼
                          ▼            ┌─────────────────────┐
              ┌─────────────────┐       │ forecast_tracker.db │
              │ macro-ji 容器    │──────▶│ （共享，同一 inode）   │
              │ watchdog→verifier│ 写回  └─────────────────────┘
              └─────────────────┘
```

| 数据 | 宿主路径 | 容器路径 | 说明 |
|------|---------|---------|------|
| 共享 DB | `/vol2/1000/software/macro-scan/data/forecast_tracker.db` | `/app/macro_data/forecast_tracker.db` | 天枢/天璇/天玑三写者，WAL |
| 触发文件 | `/vol2/1000/software/macro-scan/data/tianji_trigger.json` | `/app/macro_data/tianji_trigger.json` | 天枢写、天玑消费 |
| config 卷 | `/vol2/1000/software/macro-scan/config/` | `/app/config/`（rw） | grv_weights.yaml / prior.yaml |
| FRED 历史 | `/vol2/1000/software/macro-scan/data/fred_history/` | `/app/macro_data/fred_history/` | 定量验证取数 |
| GRV 历史 | `/vol2/1000/software/macro-scan/data/grv_history.jsonl` | `/app/macro_data/grv_history.jsonl` | 定量验证取数 |
| 待审批建议 | `/vol2/1000/software/macro-scan/data/pending_weight_adjustments.json` | `/app/macro_data/pending_weight_adjustments.json` | 玉衡审批队列 |

## 五、输出与展示

- **无 accuracy_dashboard / verify_result.json**（v0.2 设想已废弃）
- 准确率展示 = CLI：`tianji_verifier.py --report`（总预测数/待验证/已验证/人工确认中 + Brier 均值 + BSS + 锐度，已验证 <5 时提示样本不足）
- ntfy 推送（`NTFY_URL=https://ntfy.sh/***REMOVED***`）：地缘人工确认请求、玉衡反哺建议、玉衡健康检查告警

## 六、运行状态与已知缺口（08-06 实测）

**运行状态**：
- 容器 healthy（08-04 22:37 上线；08-06 config rw 修复后重建生效）
- 代码四文件 sha256 ≡ 仓库；依赖仅 pyyaml；无 VERSION 文件（镜像名+时间=版本锚点）
- DB：`narrative_chunks=181`、`forecasts=289`（天璇仿真动态增长）、`predictions=1`（测试预测 GRV global_composite 上升，Brier 0.4225，08-01 auto verified）、`weight_update_log/actuals/evaluations=0`

**人工验证渠道（08-17 补齐，此前"待人工"无入口）**：
- 地缘事件预测（`status=awaiting_human`，geopolitical 类型）设计上等人工判断，脚本：
  ```bash
  docker exec macro-sim python3 verify_human.py --list                 # 列出全部待人工（含剩余天数）
  docker exec macro-sim python3 verify_human.py --verify <id> \
      --outcome 0|1|0.5 [--note "备注"]   # 0=未发生 1=发生 0.5=部分/不确定
  ```
- 验证后 `status=verified, verified_by=human`（与自动验证 `verified_by=auto` 区分）、
  `brier=(final_prob−outcome)²`、备注存 `human_note` 列（08-17 ALTER TABLE 新增）；
  幂等：已 verified 拒绝重复验证
- 开阳界面化（天玑 tab 点选验证）＝ 控制面二期待办

**已知缺口**：
1. `prior.yaml` 缺失 → `init_weights_from_prior()` 不可用（grv_weights.yaml 已存在，需人工维护）
2. V1 未正式投用：predictions 仅 1 条测试预测，待天璇 run_scoring() 落真实预测
3. 反哺触发需 ≥8 条已验证样本，当前不触发（设计如此）

## 七、运维速查

```bash
docker ps --filter name=macro-scan-tianji-1                 # 状态
docker logs macro-scan-tianji-1 --tail 50                   # watchdog/验证日志
cat /vol2/1000/software/macro-scan/data/tianji_trigger.json # 触发文件（processed?）
docker exec macro-scan-tianji-1 python3 tianji_verifier.py --report   # 准确率
docker exec macro-scan-tianji-1 python3 weight_matrix.py --health     # 玉衡健康
docker exec macro-scan-tianji-1 python3 tianji_verifier.py --confirm <ID> 1  # 人工确认
```

详细接手指引与红线 → `macro-ji/AGENTS.md`。
