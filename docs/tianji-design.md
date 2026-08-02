# 天玑（Tianji）— 北斗第三星：验证层设计文档

> 状态：DRAFT v0.2（2026-07-24 初稿，2026-08-03 arch_review 更新）  
> 定位：北斗七星第三星，在天枢（macro-scan）+ 天璇（macro-sim）之上，对推演结果做事后验证和校准闭环。
>
> **2026-08-02 arch_review_20260802 裁定摘要**：
> - 天玑定位确认为**纯验证层**，不承担任何推演或采集职责
> - 玉衡（权重写回）**并入天玑 V2**，不独立成星（weight_matrix.py 移入天玑目录）
> - 天玑 V1 解锁前提：天璇 P0 hotfix 完成且 predictions 表有真实数据（非测试数据）
> - 详见 `docs/arch_review_20260802.md`

---

## 一、为什么需要天玑

天枢负责观测，天璇负责演化，但两者都缺一环：**结果验证**。

当前痛点：
1. macro-sim 输出概率路径树（3条路径），但没有系统性验证"上次预测对了吗"
2. 校准循环（前50步）依赖历史数据，但校准参数对未来预测的**准确率**从未量化
3. macro-scan 的推演报告（GRV告警→市场影响）完全没有回测框架
4. M3 开放量化区间的门槛（准确率≥60%，≥10条样本）没有自动计算机制

天玑 = **验证机**：收集预测、等待结果、自动评分、写回校准。

---

## 二、系统定位

```
天枢（macro-scan）── 每日观测 ──> 天璇（macro-sim）── 推演路径 ──> 天玑（macro-ji）
   ↑                                                                     |
   └───────────── 校准权重更新（N3 月度校验，2027-05-23解锁）─────────────┘
```

| 子系统 | 别称 | 定位 |
|--------|------|------|
| macro-scan | 天枢 | 观测层：采集信号、生成GRV |
| macro-sim | 天璇 | 仿真层：演化未来路径 |
| **macro-ji** | **天玑** | **验证层：事后验证、准确率追踪、校准闭环** |

> 天玑（北斗第三星）= 玑衡之机，古代测量仪器的关键构件，取"精密校准"之意。

---

## 三、核心功能设计

### 3.1 预测存档（Prediction Ledger）

每次 macro-sim 生成仿真报告后，天玑从报告中提取**可验证主张**并存入 SQLite：

```sql
CREATE TABLE predictions (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL,           -- 预测生成时间
    horizon     TEXT NOT NULL,           -- "2026-09"（预测的目标月份）
    source      TEXT NOT NULL,           -- "macro-sim" | "macro-scan-hypothesis"
    claim_type  TEXT NOT NULL,           -- "grv_direction" | "rate_cut" | "recession" | "conflict_escalation"
    claim_text  TEXT NOT NULL,           -- 自然语言描述（原报告摘录）
    direction   TEXT,                    -- "up" | "down" | "neutral"（适用于方向性预测）
    confidence  REAL,                    -- 0.0-1.0（路径概率 or 假说置信度）
    threshold   REAL,                    -- 验证阈值（如GRV变化>10则算正确）
    verified_at TEXT,                    -- 验证时间（NULL=待验证）
    outcome     TEXT,                    -- "correct" | "incorrect" | "ambiguous"
    actual_val  REAL,                    -- 实际观测值
    notes       TEXT                     -- 说明
);

CREATE TABLE accuracy_summary (
    updated_at   TEXT NOT NULL,
    claim_type   TEXT NOT NULL,
    total        INTEGER NOT NULL,
    correct      INTEGER NOT NULL,
    accuracy_pct REAL NOT NULL,
    PRIMARY KEY (updated_at, claim_type)
);
```

### 3.2 自动验证（Auto-Verify Worker）

每月1日运行，从 macro-scan 的历史数据对到期预测打分：

```python
class PredictionVerifier:
    """对到期预测自动评分"""

    def verify_grv_direction(self, pred, grv_history):
        """GRV方向性预测：用grv_history.jsonl实际值验证"""
        target_month = pred["horizon"]  # "2026-09"
        actual_grv = self._get_actual_grv(grv_history, target_month)
        baseline_grv = self._get_actual_grv(grv_history, pred["baseline_month"])
        if actual_grv is None:
            return "ambiguous"  # 数据缺失
        delta = actual_grv - baseline_grv
        if pred["direction"] == "up" and delta > pred["threshold"]:
            return "correct"
        elif pred["direction"] == "down" and delta < -pred["threshold"]:
            return "correct"
        elif pred["direction"] == "neutral" and abs(delta) <= pred["threshold"]:
            return "correct"
        return "incorrect"

    def verify_rate_cut(self, pred, fred_history):
        """美联储降息预测：用DFF.csv实际降息次数验证"""
        ...
```

### 3.3 准确率面板（Accuracy Dashboard）

轻量 HTML 面板（port 8899 扩展，或独立 8900），显示：

| 预测类型 | 总数 | 正确 | 准确率 | M3解锁进度 |
|---------|------|------|--------|-----------|
| GRV方向 | 8 | 5 | 62.5% | ✅ 已解锁 |
| 降息时机 | 4 | 2 | 50% | 待积累 |
| 衰退信号 | 3 | 1 | 33% | 待积累 |

### 3.4 校准闭环（Calibration Feedback）

验证结果自动写入 `verify_result.json`，供 macro-scan 的 `verify_hypothesis.py` 读取：

```json
{
  "updated": "2026-09-10",
  "accuracy_by_type": {
    "grv_direction": {"total": 8, "correct": 5, "accuracy_pct": 62.5},
    "rate_cut":      {"total": 4, "correct": 2, "accuracy_pct": 50.0}
  },
  "m3_unlock_status": {
    "grv_direction": true,
    "rate_cut": false
  },
  "suggested_weight_adjustments": [
    {"dim": "us_federal_reserve", "current_weight": 1.0, "suggested": 0.85,
     "reason": "降息预测持续偏早，阈值调高"}
  ]
}
```

---

## 四、与现有系统的接口

### 输入
- `S:\world-sim\macro-scan\data\grv_history.jsonl` — GRV 历史（验证基准）
- `S:\world-sim\macro-scan\data\fred_history\*.csv` — FRED 历史（DFF/T10Y2Y实际值）
- `S:\world-sim\macro-scan\docs\仿真报告\*.md` — macro-sim 报告（提取预测主张）
- `S:\world-sim\macro-scan\docs\假说分析\*.md` — macro-scan 假说报告（提取预测主张）

### 输出
- `verify_result.json` → macro-scan `verify_hypothesis.py` 读取（N2解锁后激活）
- `accuracy_dashboard.html` → 8900 端口可视化
- `prediction_ledger.db` → SQLite，持久化所有预测记录

---

## 五、分阶段实施计划

| 阶段 | 解锁时间 | 内容 | 工作量 |
|------|---------|------|--------|
| **V1：手动存档** | 立即可做 | 建 prediction_ledger.db，手动从历史报告录入已有预测，验证已到期预测 | 2-3h |
| **V2：自动提取** | V1稳定后 | LLM 解析 macro-sim 报告提取可验证主张，写入 ledger | 1天 |
| **V3：自动验证** | 2026-09 | 月度 cron 自动对到期预测评分，生成准确率面板 | 1天 |
| **V4：校准闭环** | N3（2027-05-23） | `suggested_weight_adjustments` 写回 macro-scan 信号权重 | 2天 |

---

## 六、技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 存储 | SQLite（`verification.db`） | 轻量，与 macro-scan news.db 同架构模式 |
| 调度 | macro-scan scheduler.py 新增 cron | 复用现有调度，无需新容器 |
| 面板 | 复用 macro-scan Web UI（port 8899） | 加一个 `/accuracy` 路由即可 |
| 部署 | macro-scan 热挂载区新增 `verification/` 模块 | 无需 rebuild 镜像 |

---

## 七、V1 快速原型步骤

> **前置条件**（2026-08-03 更新）：天璇 P0 hotfix 完成（inode 修复 + predictions 表写入正常）且首批真实预测已落表，预计最早 2026-09。在此之前本节不可执行。

1. 在 `macro-scan/核心代码/` 建 `verification.py`（建库+录入+验证）
2. 从现有 `docs/仿真报告/` 里人工识别已到期预测，手动录入
3. 对 GRV 方向性预测用 `grv_history.jsonl` 自动评分，调用 `brier_calc.py`（v3.8.3 新增）
4. 输出第一份准确率报告

---

*天玑是系统形成闭环的关键。天枢看见世界，天璇推演未来，天玑衡量误差——三星协作，系统才有自我进化能力。*
