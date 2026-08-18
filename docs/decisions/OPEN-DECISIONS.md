# OPEN-DECISIONS 登记册

> 规则：只追加 + 就地关闭（OPEN → RESOLVED，补 Resolution 字段）。每次 Phase 开始时把未决项复现到工作上下文最前面。
> 固定 slug：waiting-on-external-condition / design-decision-to-evaluate / existing-design-boundary

| Date | Source | Open Item | Related Constraints | Current Leaning | Blocked By | Resolves When | Status |
|------|--------|-----------|---------------------|-----------------|------------|---------------|--------|
| 2026-08-18 | 审计 world-sim-audit-20260818 | **P0-1 天玑容器 env 丢失（LIVE）**：macro-scan-tianji-1 `WORLDSIM_APP_PW` 空 → `get_connection()` raise → 天玑验证层静默停摆（容器 healthy 假象） | 08-17 force-recreate 时运行区 macro-ji compose `${WORLDSIM_APP_PW}` 未被 shell 注入 | 运行区 macro-ji compose 旁加 `.env` 或显式 environment 注入 → up -d；强化 healthcheck 为真实 PG 查询 | **用户批准运行区变更** | 用户批准后 | OPEN |
| 2026-08-18 | 审计 world-sim-audit-20260818 | P0-2 明文密钥入 git（macro-scan/docker-compose.yml 6 处，git 历史含） | 用户暂缓（GitHub 私有）；git rm --cached 不够（历史仍含），需轮换受影响密钥 | 仓库转公开/外部共享前处理 | 用户暂缓 | 转公开/共享前 | OPEN |
| 2026-08-18 | 审计 world-sim-audit-20260818 | 双 tianji_db 实现分歧（macro-scan SQLite 版 vs macro-ji PG 版） | 生产 _PG_ONLY 下 SQLite 版 NoopConn 吞 qmark（无运行 bug），维护负担 | 确认 macro-scan 版调用方路径后统一或归档 | P2 窗口 | 下次大重构时 | OPEN |
| 2026-08-14 | 全量检查 P0 修复后遗留 | reconcile_synthesis.py:37 / reconcile_backfill.py:23 手动工具仍无条件 `sqlite3.connect(news.db)`，无 PG-only 守卫、无 mode=ro | P6 后 news.db 已删，触发即 FileNotFoundError 或复活空库；非调度仅人工触发 | 补 mode=ro + PG-only 早退（参照 verify_reads_e0c.py 已修模式） | P2 修复窗口 | 下次接触对账工具时 | OPEN |
| 2026-08-14 | QA advisory 3 | daily_narrative.py:25 以 news.db 存在性作 PG 读开关，缺失时 `_query_top_news` 直接 return [] 不读 PG → 功能静默降级 | SQLite 已删后该功能静默失效（不复活文件，但天玑叙事少数据源） | 改为直连 PG（去存在性依赖），与 _check_data_maturity 修复同源 | 用户确认 daily_narrative 是否仍需保留 | 用户拍板后 | OPEN |
| 2026-08-14 | 检查8 修复前时间线 | P6 删库 08:39 前 news.db 以完整 27MB 存在（e0c-p6 快照与昨日 21:38 快照字节一致）——判定为删库前正常状态（07:23 弱信号打开已存在文件），非复生痕迹 | 已由 git log 1ba002a（E0-C P6 删库闭环 commit）证实为团队主动文档化操作 | 销项 | 无 | 已关闭 | RESOLVED |

## 已关闭项

### 2026-08-14 · e0c-p6-20260814-083910 疑点
- Resolution: git log 1ba002a 证实 08:39 归档是团队主动 P6 删库闭环（快照 + 删 4 db + 观察无复生/探针 OK），非 SQLite 复活痕迹。QA advisory 第 1 条销项。
