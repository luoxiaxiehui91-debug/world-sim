# macro-ji — 天玑（验证评估层）

> 北斗七星第三星 · 独立容器 · V1 现役
> 架构文档：[`docs/tianji-design.md`](../docs/tianji-design.md) · 接手指引：[`AGENTS.md`](AGENTS.md) · 变更历史：[`CHANGELOG.md`](CHANGELOG.md)

---

## 一、项目定位

天枢观测、天璇演化，但两者都缺一环：**结果验证**。天玑补上这个闭环——收集预测、等待结果、自动评分、触发权重反哺。

- **天玑（验证层）**：`tianji_db.py` + `tianji_verifier.py` + `verify_watchdog.py`，事后验证与准确率追踪
- **玉衡（权重矩阵）**：`weight_matrix.py`，同一容器内的权重管理模块，审批后写回 `config/grv_weights.yaml`

M1 已采纳：**独立容器、独立 compose，不挂 macro-sim 下**。天玑的启动/停止/重建独立于天璇。

## 二、四件套架构

| 文件 | 职责 |
|------|------|
| `tianji_db.py` | DB schema + CRUD。8 张表：`predictions` / `reasoning_trace` / `narrative_chunks` / `weight_update_log` / `forecasts` / `actuals` / `evaluations` / `narrative_density_flags`。与天璇共用同一 SQLite（`forecast_tracker.db`） |
| `tianji_verifier.py` | 函数式验证：`verify_quantitative()`（自动拉 FRED/GRV 实际值转二值 outcome）+ 地缘预测 ntfy 人工确认；Brier Score / BSS / 锐度计算；反哺检查生成 `pending_weight_adjustments.json` + ntfy 推送 |
| `weight_matrix.py` | 玉衡权重矩阵：双层 clip（±25% 变化速率 + [0.05, 5.0] 绝对范围）+ Herfindahl 健康检查 + 连续 4 次同方向警告；审批后写回 `config/grv_weights.yaml` |
| `verify_watchdog.py` | T2 触发 watchdog：3s 轮询共享触发文件 `tianji_trigger.json`（原子写 tmp→rename / batch_id 幂等键 / processed 标记），检出即执行验证 |

## 三、T2 触发数据流

```
天枢 scheduler 09:42 tianji_trigger job（每日，dom=1-7）
  → write_tianji_trigger.py 写 tianji_trigger.json
      （tmp → os.rename 原子写；batch_id=日期幂等键；已有未处理同批 trigger 则跳过）
  → 天玑 verify_watchdog.py 3s 轮询检出未处理 trigger
  → 执行 tianji_verifier.py（量化自动验证 / 地缘 ntfy 人工确认 + 反哺检查）
  → 写回共享 forecast_tracker.db（status=verified / awaiting_human + Brier 分）
  → trigger 置 processed=true + last_result 原地回写
```

关键契约：
- 触发文件必须走**目录挂载 + tmp rename 原子写**（禁单文件 bind mount）
- 幂等：同一 batch_id 只处理一次，processed 后不重复执行

## 四、共享数据

| 数据 | 宿主路径 | 容器路径 | 说明 |
|------|---------|---------|------|
| 共享 DB | `/vol2/1000/software/macro-scan/data/forecast_tracker.db` | `/app/macro_data/forecast_tracker.db` | 与天璇 macro-sim 共用同一 inode（同卷不同容器，WAL 模式三写者共存） |
| 触发文件 | `/vol2/1000/software/macro-scan/data/tianji_trigger.json` | `/app/macro_data/tianji_trigger.json` | 天枢写、天玑消费 |
| config 卷 | `/vol2/1000/software/macro-scan/config/` | `/app/config/` | `grv_weights.yaml`（玉衡读+写回）/ `prior.yaml`（缺失，见已知缺口） |
| FRED 历史 | `/vol2/1000/software/macro-scan/data/fred_history/` | `/app/macro_data/fred_history/` | 定量验证取数（`_fetch_fred_value`） |
| GRV 历史 | `/vol2/1000/software/macro-scan/data/grv_history.jsonl` | `/app/macro_data/grv_history.jsonl` | 定量验证取数（`_fetch_grv_value`） |

> 玉衡写回（`apply_weight_adjustment` → `grv_weights.yaml`）依赖 config 卷 **rw** 挂载。

## 五、运行状态（08-06 实测）

- 容器：`macro-scan-tianji-1`（image `macro-tianji:latest`，`restart: unless-stopped`，**healthy**），2026-08-04 22:37 上线
- 代码：四文件 sha256 ≡ 仓库 `macro-ji/`（镜像烘焙 COPY 模式，改码须重建镜像）
- 依赖：仅 `pyyaml>=6.0`（requirements.txt）
- 推送：ntfy（`NTFY_URL=https://ntfy.sh/macro-tsx-9005`）
- 版本锚点：无 VERSION 文件；以镜像名 + 上线时间计版本（v1.0.0，2026-08-04）

DB 实测计数：

| 表 | 行数 | 说明 |
|----|------|------|
| `narrative_chunks` | 181 | 叙事预处理存储 |
| `forecasts` | 289 | 天璇仿真写（动态增长） |
| `predictions` | 1 | 仅测试预测：GRV `global_composite` 上升，Brier 0.4225，08-01 `auto` verified |
| `reasoning_trace` | 1 | 与测试预测关联 |
| `weight_update_log` / `actuals` / `evaluations` | 0 | 反哺样本不足（`MIN_TRIGGER_N=8`，当前 predictions=1）为正常 |

## 六、已知缺口

1. **`prior.yaml` 缺失**：`config/prior.yaml` 不存在 → `weight_matrix.init_weights_from_prior()` 不可用。`grv_weights.yaml` 已存在（48KB，08-03 生成）；需人工维护或补 prior.yaml 后走初始化。
2. **V1 未正式投用**：`predictions` 仅 1 条测试预测（08-01 测试写入），待天璇 `run_scoring()` 落真实预测后验证闭环才正式运转。
3. **无 accuracy_dashboard / verify_result.json**：准确率展示由 CLI 替代（`tianji_verifier.py --report`）。
