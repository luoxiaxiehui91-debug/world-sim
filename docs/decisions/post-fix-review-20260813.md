# 修复后回顾 — 漏洞清单（2026-08-13 22:4x）

> 性质：修复/迁移/改名全部落地后的系统性漏洞回顾（只查 + 记录，未修复）
> 触发：用户「回顾一下，想想有什么漏洞？」

## 一、实测验证的漏洞

### 🔴 V1 备份与源数据同盘（off-site 缺失）
- **实测**：`df -h` 显示 pgdata 与 backups 均在 `/vol2/1000`（同一 3.7T 卷）。
- **后果**：卷物理损坏 → 源数据 + 备份**一起丢**。备份形同虚设。
- **关联**：backup-pg.sh 挂了几周无人发现（backup.log 只有报错），正是「缺监控 + 同盘 + 无演练」三重叠加。

### 🔴 V2 备份从未做过 restore 演练
- 当前验证仅 `pg_restore -l`（列目录），证明**结构**可读，未证明**数据**能完整还原。
- 应定期 restore 到临时库/临时容器，验证条数一致（如 articles 32560）。

### 🟠 V3 forecast_tracker.db 写路径未切 PG-only（P6 前置未做）
- **实测**：`forecast_tracker.db` mtime 20:07:37（1.3M），narrative.db / tianji.db 为 **0 字节**（08-10 僵尸）。
- P4 只给 `news_db.py` 6 写函数加 PG-only 分支；`forecast_tracker.py` / `tianji_db.py` / `narrative_processor.py` 写路径**仍写 SQLite**。
- **后果**：P6 删 `forecast_tracker.db` 会被复生。narrative.db/tianji.db 0 字节（删了不复生）。
- 待确认：forecast 写路径归属哪个调度任务（scheduler 无独立 forecast 任务名，疑挂 daily_narrative/morning 链）。

### 🟠 V4 探针覆盖盲区
- **实测**：`silent_failure_probe.py` DUALWRITE_TABLES 仅 news 五表；**不监控** forecast/tianji/narrative 表。
- 且**不监控备份结果**（backups/ 里 worldsim-*.dump 的新鲜度）——backup-pg.sh 挂几周无人发现，探针也无兜底。

## 二、非实测、但存在的隐患

### 🟡 V5 历史文档残留旧路径
- `worldsim-rename-check.md` / `backup-pg-fix-20260813.md` 保留改名前的 `/vol2/1000/software/worldsim`（历史记录，合理但可能误导后来者）。运行时引用零残留（已验证）。

### 🟡 V6 worldsim_admin 免密
- `docker exec worldsim-pg psql -U worldsim_admin` 免密（deploy-pg.sh/backup-pg.sh 同款）→ 能 docker exec 者得 superuser。个人内网风险低，记录即可。

### 🟡 V7 P6 观察窗口覆盖不全
- 探针 I120（2h/轮），12-24h 仅 6-12 轮；且探针不覆盖 forecast（V4）→ 观察窗口「无异常」结论可信度打折。

## 三、建议优先级

| 序 | 动作 | 价值 | 风险 | 建议时机 |
|----|------|------|------|----------|
| 1 | 探针加「备份新鲜度」检查（backups/worldsim-*.dump 最新 mtime > 24h → WARN/CRIT） | 高（防 backup 再静默挂） | 低（纯新增检查） | 可立即 |
| 2 | forecast/tianji/narrative 写路径补 PG-only（P6 前置） | 高（P6 删库前提） | 中（改 3 模块写路径） | P6 前 |
| 3 | 备份异盘（第二块盘/另一台 NAS） | 高（数据安全兜底） | 低（配置） | 尽快 |
| 4 | restore 演练（restore 到临时库验证条数） | 中 | 低 | 周期性 |
| 5 | 探针扩展 forecast/tianji 表监控 | 中 | 低 | 择机 |
