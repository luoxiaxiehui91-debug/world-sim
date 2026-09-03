# macro-ji — AI 工作入口（天玑验证评估层）

> 容器：`macro-scan-tianji-1` · 镜像：`macro-tianji:latest` · 版本：v1.0.6（2026-09-03 dryrun 守卫注入；v1.0.1–v1.0.5 见 CHANGELOG.md）
> 代码目录：`/vol2/1000/software/world-sim/macro-ji/`（NAS 仓库）

> **跨项目知识库入口**：中央知识库 = `S:\docs\`（NAS 侧 `/vol2/1000/software/docs/`）；规则真源 = `S:\docs\AGENTS.md`（问题流程 / CHG 变更日志 / 文档写作规范）。改代码 / 部署后**必须按文末「七、中央知识库同步（CHG 五步）」同步中央知识库**（2026-08-30 CHG 体系）。

---

## 一、系统定位

天玑是北斗七星第三星，**纯验证层**：在天枢（macro-scan）+ 天璇（macro-sim）之上做推演结果的事后验证与校准闭环。

```
              天枢 scheduler 09:42 tianji_trigger job
                     │ write_tianji_trigger.py
                     ▼
        ┌─────────────────────────────────┐
        │  tianji_trigger.json（共享 data 卷） │
        │  batch_id 幂等键 · processed 标记    │
        └────────────┬────────────────────┘
                     │ 3s 轮询（verify_watchdog.py）
                     ▼
        ┌───────────────────────────┐
        │      macro-scan-tianji-1    │
        │  ┌─────────────────────┐  │
        │  │ verify_watchdog.py  │  │  触发 watchdog
        │  └─────────┬───────────┘  │
        │            ▼              │
        │  tianji_verifier.py       │  验证 + 反哺（Brier/BSS/锐度）
        │                          │  v1.0.2：L2 新闻自动判定已并入（原 verify_geo_auto.py 孤儿逻辑，含存量回收）
        │  tianji_db.py             │  PG CRUD（08-18 P2 口径统一）
        │  weight_matrix.py         │  玉衡：双层 clip + 审批写回
        │  config/grv_weights.yaml  │  权重矩阵（config 卷）
        └────────────┬──────────────┘
                     │ 写回（08-18 修订：P6 删 SQLite 后全走 PG）
                     ▼
        worldsim-pg tianji schema（predictions/reasoning_trace/weight_update_log）
```

## 二、接手指引

```bash
# SSH 进 NAS
ssh nas

# 容器状态 / 日志
docker ps --filter name=macro-scan-tianji-1
docker logs macro-scan-tianji-1 --tail 100

# 进容器
docker exec -it macro-scan-tianji-1 bash

# 查看代码布局（容器内 /app）
docker exec macro-scan-tianji-1 ls -la /app/

# watchdog 进程确认
docker exec macro-scan-tianji-1 ps aux | grep verify_watchdog
```

## 三、常用命令

| 目标 | 命令 |
|------|------|
| 查看共享 DB 表结构与计数 | `docker exec macro-scan-tianji-1 python3 -c "import sqlite3;c=sqlite3.connect('/app/macro_data/forecast_tracker.db');[print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]) for t in [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]]"` |
| 看预测状态 | `docker exec macro-scan-tianji-1 python3 -c "import sqlite3;c=sqlite3.connect('/app/macro_data/forecast_tracker.db');[print(r) for r in c.execute('SELECT id,type,status,brier_score,verified_by FROM predictions')]"` |
| 看触发文件 | `cat /vol2/1000/software/macro-scan/data/tianji_trigger.json` |
| 看验证日志 | `docker logs macro-scan-tianji-1 --tail 50` |
| 准确率报告 | `docker exec macro-scan-tianji-1 python3 tianji_verifier.py --report` |
| 待验证数 | `docker exec macro-scan-tianji-1 python3 tianji_verifier.py --status` |
| 手动跑一次验证 | `docker exec macro-scan-tianji-1 python3 tianji_verifier.py` |
| 玉衡健康检查 | `docker exec macro-scan-tianji-1 python3 weight_matrix.py --health` |
| 玉衡待审批列表 | `docker exec macro-scan-tianji-1 python3 weight_matrix.py --pending` |
| 人工确认地缘预测 | `docker exec macro-scan-tianji-1 python3 tianji_verifier.py --confirm <PRED_ID> 1`（1=发生 / 0=未发生） |

## 四、架构红线（不可违反）

| 红线 | 说明 |
|------|------|
| **共享 DB 只经 `tianji_db.py` 访问** | `forecast_tracker.db` 与天璇共用同一 inode（WAL 三写者共存）。任何读写必须走 `tianji_db.py` 的 `get_connection()`（WAL + foreign_keys ON），禁裸 sqlite3 直连、禁锁库、禁删除重建 |
| **config 写回须经玉衡审批** | `grv_weights.yaml` 写回只允许 `weight_matrix.apply_weight_adjustment()`（双层 clip 强制）；生成建议走 `tianji_verifier.check_and_generate_reweight_suggestions()` → `pending_weight_adjustments.json` → 人工审批 `approve_adjustment()`。禁止绕过约束直接改 yaml |
| **T2 触发协议勿改** | 调度链路（天枢 scheduler `tianji_trigger` 0942 job → `write_tianji_trigger.py` → watchdog 轮询）是既定契约。batch_id 幂等键、processed 标记、`last_result` 回写字段结构不可随意变更；改协议须同步天枢侧（`macro-scan/核心代码/`） |
| **触发文件勿动 inode 契约** | `tianji_trigger.json` 必须走**目录挂载 + tmp → os.rename 原子写**（防半写），禁单文件 bind mount、禁直接 overwrite 既有 inode；watchdog 侧同样遵守 |
| **改码须重建镜像** | COPY 模式：容器内代码 ≡ 镜像烘焙 ≡ 仓库。改 `macro-ji/*.py` 后必须 `docker compose build && up -d --force-recreate`（在 `/vol2/1000/software/world-sim/macro-ji/`），否则运行态与仓库脱节 |

## 五、部署 / 重建

```bash
# 重建镜像 + 重建容器（在 NAS 上，macro-ji 目录下）
cd /vol2/1000/software/world-sim/macro-ji
docker compose build
docker compose up -d --force-recreate

# 健康检查（healthcheck 30s 间隔）
docker ps --filter name=macro-scan-tianji-1   # 期待 (healthy)
```

> 注意：config 卷挂载为宿主 `/vol2/1000/software/macro-scan/config`（**非**仓库内 `macro-scan/config/`），重建容器不丢数据。

## 六、文件职责速查

| 文件 | 入口函数 | CLI |
|------|---------|-----|
| `tianji_db.py` | `get_connection()` / `run_migration()` / `save_prediction()` / `get_pending_predictions()` / `update_prediction_verified()` / `log_weight_update()` | `python3 tianji_db.py`（migrate） |
| `tianji_verifier.py` | `run_monthly_verification()` / `verify_quantitative()` / `check_and_generate_reweight_suggestions()` / `confirm_geopolitical()` | `--report` / `--status` / `--confirm ID 0\|1` |
| `weight_matrix.py` | `init_weights_from_prior()` / `get_weight()` / `apply_weight_adjustment()` / `run_health_check()` / `approve_adjustment()` | `--init` / `--health` / `--pending` |
| `verify_watchdog.py` | `main()`（3s 轮询循环） | 容器 CMD |

## 七、中央知识库同步（CHG 五步，2026-08-30 起）

任何非只读变更（改代码 / 改配置 / 部署 / 归档 / 文档修改）都要走中央 CHG 生命周期（格式真源 = `S:\docs\AGENTS.md` §operations/ 系统日志）：

1. **实施前**：建 `S:\docs\operations\CHG-<YYYYMMDDTHHmmss>-macro-ji.md`（9 字段 frontmatter + `## Pre-Change` 写完冻结）
2. **实施**：改代码 + 按版本同步清单更新（macro-ji 清单 = `VERSION` + `CHANGELOG.md` + 本文件顶部版本号 + `S:\docs\INDEX.md` 版本状态表）
3. **同步**：更新 `S:\docs\INDEX.md` 版本状态行（版本号 + 日期 + 一行摘要）+ `S:\docs\questions\world-deduction\` 相关 question 状态
4. **收尾**：CHG 追加 `## Post-Change`（完成时间 / 实施摘要 / 验证），frontmatter status 改 `completed`
5. **边界**：纯报问题建档（question doc + INDEX 加行）**不建 CHG**——CHG 只覆盖实施变更，不覆盖记录「发现」

NAS 侧路径等价：`/vol2/1000/software/docs/`。问题归属统一建在 `questions/world-deduction/`。
