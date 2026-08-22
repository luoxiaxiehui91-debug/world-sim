# macro-ji CHANGELOG — 天玑（验证评估层）

> 文档类别：实录（RECORD）· CHANGELOG（每条绑定 commit hash，写后即验）
> 最后核对时间：2026-08-19（记录类文档随部署持续更新）
> 版本锚点：无 VERSION 文件，以镜像名（`macro-tianji:latest`）+ 上线时间计版本。
> 变更历史从 v1.0.0（独立容器上线）起。

---

## v1.0.2 — 2026-08-22 L2 新闻自动判定并入验证器（commit 3ed3ffcd7）

**事故/修复**：P1-1「L2 验证死门禁」——L2 geo 预测（awaiting_human）的自动验证器 verify_geo_auto.py 位于 macro-scan 树（天枢），从未进天玑镜像/从未被调度（孤儿脚本），L2 判定逻辑从未实际运行。本版并入现役验证器。

### 修改

- **tianji_verifier.py 并入 L2 新闻判定**：L2_KEYWORDS（21 键）+ _judge_l2_news（新闻窗口关键词判定，命中→发生确认 1.0 / 未命中→None 留人工）；geo 分支先自动判定、未命中再推 ntfy 人工兜底；**存量回收段**（已到期 awaiting_human 的 L2 键自动判定）。
- **tianji_db.py**：update_prediction_verified 加 human_note 参数（记录【自动-L2】判定依据）。

## v1.0.1 — 2026-08-18 校准器 scale 语义修正（commit `8c2ddc4c`）

**事故**：v1 的 `_compute_dim_scales` 用"归一化分数 P95 反推原始计数 P95 当归一化分母"——
P95 = 常态水平，当分母 → **常态即 95% 的日子分数 ≥95 分顶格**。8/14 接入后 gdelt_scores
全线虚高 9-28 倍（military scale 135000→12960、tension 220000→7920），推导维度
south_china_sea 25→93、korean_peninsula 53→89 进红线误触发区（天璇 8/14 后无仿真，
红线未被消费——影响面可控）。根因链：① scale 语义错误 ② gdelt_history.jsonl 8/14
前后口径断裂（P95 反推不可收敛，统一口径后 double 反推）。

**修复（version 2）**：
- `_compute_dim_scales` 直接透传 `SCALE_REF`（"2022-02-24 俄乌开战峰值/0.9"≈ 极端事件
  基准，8/14 前系统一直用此语义正常：常态 0-20 分、俄乌级极端 ≈100 分）
- tone_base / hotspot_p95 保持数据驱动（不受 scale 语义影响）
- 运行区数据（gdelt_history/gdelt_scores/gdelt_calib）口径统一重算由天枢侧执行
- 实测恢复：8/18 military USA 100→9.6、scs 93→22.3、kor 89→49.5

**验证**：08-19 冷启动 gdelt_scores military USA=10.6（scan_weak_signals 重算后口径保持）；
天玑容器 healthy + get_connection→predictions 正常。

**提交**：`8c2ddc4c`（tianji_calibrator.py + 设计文档 §3.5）

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
