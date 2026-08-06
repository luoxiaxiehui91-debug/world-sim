# macro-ji CHANGELOG — 天玑（验证评估层）

> 版本锚点：无 VERSION 文件，以镜像名（`macro-tianji:latest`）+ 上线时间计版本。
> 变更历史从 v1.0.0（独立容器上线）起。

---

## v1.0.0 — 2026-08-04 22:37 上线（独立容器）

**里程碑**：天玑从"天枢热挂载模块（v3.7.0 引入）"升级为**独立容器**，P0-B（结构性缺失）与 P0-C（镜像烘焙）同批解决。

- 新建 `macro-ji/` 子项目：四件套内核 + 精简 `optim_config.py` + 独立 compose/Dockerfile
- 三内核：
  - `tianji_db.py` — 8 张表 schema + CRUD（predictions / reasoning_trace / narrative_chunks / weight_update_log / forecasts / actuals / evaluations / narrative_density_flags），共享 `forecast_tracker.db`
  - `tianji_verifier.py` — 函数式验证（quantitative / geopolitical 两型），Brier/BSS/锐度，反哺建议 → `pending_weight_adjustments.json` + ntfy
  - `weight_matrix.py` — 玉衡权重矩阵：双层 clip + Herfindahl 健康检查 + 连续方向警告，审批后写回 `config/grv_weights.yaml`
- 新增 `verify_watchdog.py` — T2 触发 watchdog，3s 轮询共享 `tianji_trigger.json`
- 天璇 `run.py` 删除内联 `_TIANJI_DDL` + `run_scoring()`；天枢 scheduler 删除 `tianji_verify`/`weight_health` job，新增 `tianji_trigger(0942)` + `write_tianji_trigger.py`
- 踩坑修复：`tianji_db.py` 原用 `OPENCLAW_WORKSPACE` 推导落镜像内空 DB（P0-C 同款）→ 补 `TIANJI_DATA_DIR` env 显式指向挂载卷
- 验证：trigger→watchdog→verifier 全链路 exit=0；容器 healthy

**提交**：`7635837`（batch3，08-04 22:39）；依赖批 `d076100`/`07d4646`/`283485e`（batch2）

---

## 2026-08-06 — config 卷 :ro→:rw 修复 + 容器重建

**问题**：`docker-compose.yml` 中 config 卷挂载为 `:ro`，玉衡写回（`weight_matrix.apply_weight_adjustment()` → `grv_weights.yaml`）与 `pending_weight_adjustments.json` 审批流程实际无法落盘。

**修复**：
- `docker-compose.yml` config 挂载 `:ro` → `:rw`（改前已 `cp .bak-20260806`）
- `docker compose up -d --force-recreate` 重建容器生效
- 重建后实测：`config -> /app/config (rw)`，容器 healthy

**验证**：`docker inspect macro-scan-tianji-1` 挂载 Mode=rw；healthcheck 通过。

---

## 2026-08-06 — 联动修复（非本目录代码，配套记录）

- `deploy.sh`（仓库根）：`rsync --delete` 移除（deploy_scan / deploy_sim 两处）——防 rsync 误删远端新文件
- `sim_log.db`（macro-sim/）：仓库残留清理（git 未跟踪，0 字节；`.gitignore` 已含排除项）
- 天玑重建历史：天璇/天玑 rebuild 因 deploy.sh 内部 ssh 密码验证失败，改**手动 `docker build` + compose up**
