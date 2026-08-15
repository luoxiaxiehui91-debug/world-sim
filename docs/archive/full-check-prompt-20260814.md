# world-sim 全量健康检查（独立执行，只读）

你是 world-sim（世界推演系统）的独立审查员。对这个系统做一次**全量健康检查，只读——不落码、不改文件、不重启容器、不删任何东西、不推 ntfy（探针一律 alert=False）**。发现问题记录成报告，修复决策留给用户拍板。

## 冷启动材料

1. 先读项目记忆：`C:\Users\luoxi\WorkBuddy\世界推演系统\.workbuddy\memory\MEMORY.md`（部署拓扑 / 防重踩红线 / 架构决策）
2. SSH 到 NAS：**必须用 Git 自带 ssh**（Windows OpenSSH 已坏），别名 `nas` = `TSX@192.168.31.108`，命令形如 `ssh nas "..."`。所有 NAS 操作走 SSH + docker exec，**禁止信任 SMB 挂载**（会显示过期幻影）。
3. 项目权威文档（git 树 `/vol2/1000/software/world-sim/`）：`STATUS.md`（实时状态，先读）→ `AGENTS.md`（规则）→ `docs/decisions/`（ADR-001~003、E0-C-operation-log.md、audit-2026-08-13-risk-register.md、backup-pg-fix-20260813.md、gdelt-calibrator-design-20260814.md、post-fix-review-20260813.md）
4. **双源码真相**：git 真源 `/vol2/1000/software/world-sim/macro-scan/核心代码` vs 运行区 `/vol2/1000/software/macro-scan/核心代码`（bind → 容器 `/app`）。你只读，但**两边都要看**（对比漂移）。

## 背景（为什么检查）

08-13~08-14 连续大改动：P0 三修复（双写静默丢数 / forecast 时区 +8h / 自动推演停摆）→ E0-C P1-P6（读路径统一 worldsim-pg、PG-only 写、**08-14 已删 4 个 SQLite**）→ GDELT 分数校准器（天玑 tianji_calibrator + scan/GRV 改读配置）→ market 链路修复（I15 刷新 / change_pct / spark5）→ backup-pg.sh 重写 + worldsim→worldsim-pg 目录改名。主理人视角可能有盲区，**你的结论独立，矛盾以实测为准**。

## 检查范围（每项 PASS/FAIL/WARN + 证据=实际命令输出，别只说结论）

### A. 部署与拓扑
1. 容器状态：`docker ps --format "{{.Names}} {{.Status}}"` 应含 macro-scan-macro-scan-1 / worldsim-pg / macro-scan-tianji-1 全 Up
2. 双源码漂移：diff git 真源 vs 运行区 核心代码（应一致；docker-compose.yml 等被 rsync exclude 属预期）
3. git 状态：`cd /vol2/1000/software/world-sim && git status --short && git log @{u}..HEAD --oneline`（应无未推 commit）
4. 旧路径残留：`grep -rn "software/worldsim" --include="*.py" --include="*.sh" --include="*.yml" --include="*.md" /vol2/1000/software/world-sim /vol2/1000/software/macro-scan/核心代码 2>/dev/null | grep -v "worldsim-pg"`（应为空或仅历史记录文档）

### B. PG-only 状态（P6 删库后）
5. env：`docker exec macro-scan-macro-scan-1 printenv WORLDSIM_SQLITE_OFF` 应为 1
6. marker：`ls /vol2/1000/software/macro-scan/data/.sqlite_frozen_at` 存在
7. **SQLite 零残留**：`ls /vol2/1000/software/macro-scan/data/*.db` **必须无输出**（删了就不该有；任何 0 字节文件=某代码复活了它，是 P0）
8. 代码 SQLite 引用扫描：`cd /vol2/1000/software/macro-scan/核心代码 && grep -rn "sqlite3.connect" --include="*.py" .`——读路径残留（pg_read/校验工具/历史备份脚本除外）是 FAIL；写路径引用须确认都有 PG-only 分支

### C. 数据健康
9. PG 五表 + 增长：`docker exec worldsim-pg psql -U worldsim_admin -d worldsim -tAc "SELECT (SELECT COUNT(*) FROM news.articles) a,(SELECT COUNT(*) FROM news.scan_contexts) c,(SELECT COUNT(*) FROM news.signal_episodes) e,(SELECT COUNT(*) FROM forecast.forecasts) f,(SELECT COUNT(*) FROM tianji.predictions) p"`——articles 应 ≥ 32600 且持续增长
10. 时区契约抽查（P0-2 家族）：`SELECT count(*) FROM forecast.forecasts WHERE created_at::text NOT LIKE '%+%'`（naive 应为 0）；synthesis_log 今日统计按北京 00:00 起算
11. 探针：`docker exec macro-scan-macro-scan-1 python -c "import sys;sys.path.insert(0,'/app');from silent_failure_probe import run_probe;v,rs=run_probe(alert=False);print(v,sum(1 for l,_ in rs if l!='OK'))"` 应为 `OK 0`
12. 备份：`.last_pg_backup` marker < 25h；最新 dump 23M+ 且可读（`docker cp` 进 worldsim-pg 后 `pg_restore -l`）

### D. 链路抽查（重点怀疑区——主理人改得最密集）
13. market 链路：`commodity_yahoo.json` 每 15 分钟刷新（I15）？change_pct 抽查（csi300 应为负值 -0.5% 级别，与公开行情对比；若显示 +2.98% 是旧 bug 复发）；`market_quotes.json` macro 非空；crypto 有值
14. GDELT 校准链路：`gdelt_calib.json` 新鲜（< 24h）；`grep "_scales.get" scan_weak_signals.py`（确认读 calib）；GRV P95 来源：`docker exec macro-scan-macro-scan-1 python -c "import sys;sys.path.insert(0,'/app');from geo_risk_vector import _compute_gdelt_p95_dynamic as f;print(f())"` 应 ≠ 硬编码 fallback 1.243（1.243 说明读配置失败）
15. 天玑校准器接线：`docker exec macro-scan-tianji-1 grep -n "run_calibration" /app/tianji_verifier.py`（应有调用）
16. news_exporter（喂天璇）：`news_export.json` 新鲜 + articles 40

### E. 日志与运行
17. 容器日志 12h 错误：`docker logs macro-scan-macro-scan-1 --since 720m 2>&1 | grep -iE "traceback|error" | grep -viE "pg_write_collection|非阻断|PG dual-write|silent_failure"`（应空）
18. 心跳：`.scheduler_heartbeat` < 5min
19. 天玑 watchdog 活着：`docker exec macro-scan-tianji-1 sh -c "ps aux | grep -c verify_watchdog; ls /app/macro_data/ | head"`

### F. 验收工具可信度（主理人刚改过）
20. `docker exec macro-scan-macro-scan-1 python /app/final_acceptance_e0c.py 2>&1 | grep -vE "\[probe\] INFO" | tail -5` → FINAL pass=14 fail=0
21. `docker exec macro-scan-macro-scan-1 python /app/verify_reads_e0c.py 2>&1 | tail -4` → SQLite 退役模式 pass=26 gap=0 fail=0，**且跑完后复查第 7 项 .db 未复生**（防"验收工具复活 SQLite"复发）

### G. 文档一致性（独立判断）
22. STATUS.md：E0-C 应写"P1-P6 全闭环"；无"待删/待观察/可启动"过时说法
23. AGENTS.md "数据架构现状（E0-C）"节 vs 实际：读全 PG / 写 PG-only / SQLite 已删
24. 探针覆盖 vs 新现实：探针检查项有无引用已删文件的死检查（如 check_dualwrite 在 PG-only 分支对文件不存在的处理）

## 输出

结构化报告：每项 `PASS/FAIL/WARN + 证据（命令实际输出）+ 一句说明`。FAIL/WARN 汇总段按严重度排序（P0/P1/P2）。**不修任何东西**——发现问题列出，修复等用户拍板。报告追加到 `C:\Users\luoxi\WorkBuddy\世界推演系统\.workbuddy\memory\2026-08-14.md`（append-only），回复里给摘要。

## 红线

- 只读：不落码、不改文件、不重启容器、不删任何东西、不推 ntfy（探针一律 alert=False）
- 不信任"应该没问题"的说法——每项必须实测出证据
- 你的结论独立于主理人之前的判断；发现矛盾以实测为准
