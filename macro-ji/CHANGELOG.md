# macro-ji CHANGELOG — 天玑（验证评估层）

> 文档类别：实录（RECORD）· CHANGELOG（每条绑定 commit hash，写后即验）
> 最后核对时间：2026-08-19（记录类文档随部署持续更新）
> 版本锚点：无 VERSION 文件，以镜像名（`macro-tianji:latest`）+ 上线时间计版本。
> 变更历史从 v1.0.0（独立容器上线）起。

---

## v1.0.9 — 2026-10-17 全量代码审查修复（天玑）

> CHG-20261017T030000。与天枢 v3.8.77 / 天璇 v2.0.54 同批全项目审查，仅收录已实证项。

### 修改

- `tianji_db.py`：修复排序比较元组的**第二项 dict** 所致潜在 `TypeError`。
  原 `scored.sort(reverse=True)` 对 `(float, dict)` 元组排序：当两个 score 相等时 Python 会继续比较 dict → 抛错。
  而 `hours_age = 999` 的异常兜底会让多条记录的 `score` **完全相同**（`exp(-999/tau)` 同值），故此路径真实可达，
  一旦命中将使整个检索流程失败。改为只按首元素排序：`scored.sort(key=lambda _it: _it[0], reverse=True)`

### 验收
- `ast.parse` 通过；`ruff` 无新增告警

### 遗留（本批未改）
- `llm_judge.py:183` `outcome=0` 自动落库分支与 `fetch_window_news(limit=40)` 自相矛盾（要求 window_total>=200）→ 该分支不可达
- `llm_judge.py:199` LLM 判「证据不足」写入 NULL，下月仍会被选中重判 → 成本无上限且无批次上限
- `tianji_verifier.py:374` Brier 降权方向**疑似反向**（保留 `group_mean <= 0.8×global_mean` 的**优组**并降权 15%），
  因涉及反哺语义的业务决策且结果只进人工审批闸，未擅自改，待用户确认意图后处理


## v1.0.8 — 2026-10-16 P3-3: LLM 调用补记账（verify_llm 写入 public.llm_token_usage）

### 修改

- `llm_judge.py`：新增 `_record_verify()`（复用 `tianji_db.get_connection()`，INSERT 显式带
  `public.` schema 前缀以兼容 `search_path=tianji,public`）；`_call_llm()` 在成功（token 取响应
  `usage` 真值）与异常（`ok=False` + err，随后原样 raise）两处记账
- 与天璇 v2.0.53 同批；未动 `llm_cfg.py`（P3① 后双容器字节一致的 G5 守卫项）

### 验收

- 容器内运行时探针：`verify_llm` 成功行（platform=siliconflow、total_tokens=11）+ 失败行（ok=False）
  均落账；自测行 3 条清理后残留 0；抽掉 `WORLDSIM_APP_PW` 静默不抛异常
- md5 真源 = `macro-scan-tianji-1` = `macro-scan-tianji-cron-1` 三处一致 `47f7a5ac…`

### 遗留

- P3④（回归核查）未做；账本归因现覆盖天枢 2 + 天璇 4 + 天玑 1 = 7 个使用点

## v1.0.7 — 2026-10-14 P3-1: 摘除 llm_cfg L4 env 模型名兜底

### 修改

- `llm_cfg.py`（与 `macro-sim/core/llm_cfg.py` G5 字节一致，新 md5 `1067b91050550db5d5402e59589d7b9f`）：
  - 删除常量 `_ENV_MODEL_KEY = {"verify_llm": "VERIFY_LLM_MODEL"}` 及其上行注释
    ——P2 同窗口已从本容器 `docker-compose.yml` 摘除 `VERIFY_LLM_MODEL` 注入，该兜底属死代码
  - `resolve()`：`model = u.get("model") or os.environ.get(_ENV_MODEL_KEY.get(usage_id, ""), "")`
    → `model = u.get("model") or ""`
  - 全链无 model 的 raise 措辞去掉「且无 env 兜底」；docstring 删 L4 行、「四层兜底链」→「三层兜底链」
- 取值链由 L1→L2→L3→L4 变为 **L1→L2→L3**（主配置 → `.bak` 快照 → git 模板）；
  `verify_llm` 仍由开阳控制台 `data/llm_config.json` 单点决定，行为不变

### 验收

- `resolve('verify_llm')` 正常返回且 `source=truth`；容器内 md5 == 真源；守卫复跑 EXIT=0
- CHG-20261014T231051（与天璇 v2.0.52 同批）

---

## v1.0.6 — 2026-09-03 修复: verify_predictions.py dry-run 假实现（commit 01c08df）

### 修复
- `run_verification(dry_run)` 此前零消费 dry_run 变量（grep 仅签名/docstring/调用处），docstring 声称「只打印不写文件」实际照常写盘——写回段（tmp+os.replace 原子写）无条件执行
- 暴露实证：2026-09-03 P4 对账手动补跑 `--dry-run`（07:23）即改 43 条生产数据（verified_at 07:23:00~07:24:31），实跑（07:25）幂等空转「无到期预测」
- 修复：`id_map` 写回前插 `if dry_run:` 守卫——打印 results 预览（id/status/outcome/note）后直接 return，predictions_log.json 不变；argparse `--dry-run` 补 help 文本
- 同族核查结论：`verify_geo_auto.py` dry-run 守卫已完整（判定循环内 `if args.dry_run: continue` 跳过 conn.execute 写库 + 结尾 dry-run 标识），无需改；`verify_hypothesis.py` 无 `--dry-run` 参数（无假实现问题，预览能力属增强未在本次范围）
- 关联：question `20260903-world-deduction-verify-predictions-dryrun-noop.md`（⚠️ → ✅ resolved）

---

## v1.0.5 — 2026-08-28 P1: Calibration version tracking

### 新增
- PG 表 `calibration_versions`（id SERIAL PK, version_tag TEXT UNIQUE, params_snapshot JSONB, is_active BOOLEAN DEFAULT FALSE；partial unique index WHERE is_active=TRUE）
- `predictions.calibration_version_id` FK 列；415 条历史预测回填至 `v0-baseline`（id=1）
- `tianji_db.py`：`get_active_calibration_version_id()` / `create_calibration_version()` / `activate_calibration_version()`（含 rowcount=0 回滚保护）
- `save_prediction()`：每条新预测自动打 calibration_version_id（显式传入 > 活跃版本 > NULL）
- `weight_matrix.py`：`finalize_calibration_version()` + `--finalize-version` CLI 旗标
- 迁移脚本：`migrate_p1_calibration_versions.py`

## v1.0.4 — 2026-08-28 P0: 验证器 Bug A 修复 + reasoning_trace 去重约束

### 修复
- `tianji_verifier.py`：LEFT JOIN `reasoning_trace` 导致 join fan-out（同一预测多条推理行→Brier 重复计入）→ 改为两步独立查询（先取 pred_rows，再按 pred_ids 列表取 trace_rows，Python dict 合并）；同时修复 L348 变量名残留 bug（`rows` → `pred_rows`）
- `reasoning_trace`：新增 UNIQUE(prediction_id) 约束，防止重复推理行写入
- 迁移脚本：`migrate_p0_unique_trace.py`（去重 139 行、无重复、约束落地）

## v1.0.3 — 2026-08-24 optim_config 追加验证域收编常量（commit 75927fd45）

**背景**：验证域存量收编二期立项——verify_predictions 自天枢迁入的前置条件。该脚本 `from optim_config import PREDICTIONS_LOG, FRED_MAX_LAG_DAYS, GDP/UNRATE/CPI_HIT_TOLERANCE`，精简版缺这些属性直迁即 ImportError。

### 修改
- optim_config.py 追加：PREDICTIONS_LOG（DATA_DIR 同卷挂载路径）、FRED_MAX_LAG_DAYS=45、GDP/UNRATE/CPI_HIT_TOLERANCE=1.5/0.5/0.8（数值对齐天枢版 L120-125）。
- 保持天玑精简哲学：只加迁入脚本实际 import 的常量，不引入天枢全量配置。
- rebuild macro-tianji:latest + force-recreate；容器内六常量导入全 OK、predictions_log.json 挂载卷实存。
- 同日收编实施（commits 71fa88082/ece64f2bb）：verify_geo_auto/hypothesis/predictions 三脚本自天枢 cp 入库；新增 tianji_verify_cron.py 定时器（每日 geo_auto 0930 / 月度 predictions 0900·hypothesis 0915）；Dockerfile COPY 清单追加；compose 加知识库只读挂载 + verify-cron 第二 service + /app/data:ro（WIKI_FILE 兼容）；requirements.txt 补 fredapi。
- 实跑验证：三脚本 EXIT=0（geo_auto 幂等空转/predictions 无到期/hypothesis 完整写 calibration.json）；cron 定向冒烟通过（now+2min 准时 FIRING→DONE rc=0→产物落盘）。

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
