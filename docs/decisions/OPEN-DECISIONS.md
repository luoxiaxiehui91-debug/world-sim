# OPEN-DECISIONS 登记册

> 规则：只追加 + 就地关闭（OPEN → RESOLVED，补 Resolution 字段）。每次 Phase 开始时把未决项复现到工作上下文最前面。
> 固定 slug：waiting-on-external-condition / design-decision-to-evaluate / existing-design-boundary

| Date | Source | Open Item | Related Constraints | Current Leaning | Blocked By | Resolves When | Status |
|------|--------|-----------|---------------------|-----------------|------------|---------------|--------|
| 2026-08-18 | 审计 world-sim-audit-20260818 | ~~P0-1 天玑容器 env 丢失（LIVE）~~ | ~~08-17 force-recreate 时 compose `${WORLDSIM_APP_PW}` 未注入~~ | ~~macro-ji/.env + healthcheck 真 PG 查询~~ | — | — | **RESOLVED** `d2feccf6`（08-18 已修：.env 注入 + PW_len=32 + get_connection→73 条实测） |
| 2026-08-18 | 任务 #77 复查（08-18 16:5x） | global_composite 实时性改进：现 GPR 月频 85% + japan_monetary 15% 近静态 → 月频阶梯，对日/周级地缘事件无响应 | **改公式影响面大**：global_composite 是天璇红线（GRV 实测 p90 校准）与告警（GRV≥68）依赖的主维度；改后分布漂移须重校准红线 | 旁路先算 30 天假想序列对比分布 → p90 漂移 >5 则同步校准红线 → 上线 | 用户拍板"改 GRV 公式" | 用户批准后 | OPEN |
| 2026-08-18 | 任务 #80 复查（08-18 16:5x） | market 数据进 worldsim-pg：market_quotes.json（I15 整合 commodity+crypto）仍落 flat-file | public.indicators（11 列）是模型指标表（195 行），不适合市场快照；方案 B=新表 `market_quotes(key,as_of,price,change_pct,unit,spark5 jsonb)` 映射现 JSON | 方案 B 已收敛；触发条件=天璇要消费市场信号（当前金融 agent 用 FRED/GRV 不消费 market） | 触发条件未到 | 天璇接入市场信号时（约半小时工作量） | OPEN |
| 2026-08-18 | 审计 world-sim-audit-20260818 | P0-2 明文密钥入 git（macro-scan/docker-compose.yml 6 处，git 历史含） | 用户暂缓（GitHub 私有）；git rm --cached 不够（历史仍含），需轮换受影响密钥 | 仓库转公开/外部共享前处理 | 用户暂缓 | 转公开/共享前 | OPEN |
| 2026-08-18 | 审计 world-sim-audit-20260818 | 双 tianji_db 实现分歧（macro-scan SQLite 版 vs macro-ji PG 版） | 生产 _PG_ONLY 下 SQLite 版 NoopConn 吞 qmark（无运行 bug），维护负担 | 确认 macro-scan 版调用方路径后统一或归档 | P2 窗口 | 下次大重构时 | OPEN |
| 2026-08-14 | 全量检查 P0 修复后遗留 | reconcile_synthesis.py:37 / reconcile_backfill.py:23 手动工具仍无条件 `sqlite3.connect(news.db)`，无 PG-only 守卫、无 mode=ro | P6 后 news.db 已删，触发即 FileNotFoundError 或复活空库；非调度仅人工触发 | 补 mode=ro + PG-only 早退（参照 verify_reads_e0c.py 已修模式） | P2 修复窗口 | 下次接触对账工具时 | OPEN |
| 2026-08-14 | QA advisory 3 | daily_narrative.py:25 以 news.db 存在性作 PG 读开关，缺失时 `_query_top_news` 直接 return [] 不读 PG → 功能静默降级 | SQLite 已删后该功能静默失效（不复活文件，但天玑叙事少数据源） | 改为直连 PG（去存在性依赖），与 _check_data_maturity 修复同源 | 用户确认 daily_narrative 是否仍需保留 | 用户拍板后 | OPEN |
| 2026-08-14 | 检查8 修复前时间线 | P6 删库 08:39 前 news.db 以完整 27MB 存在（e0c-p6 快照与昨日 21:38 快照字节一致）——判定为删库前正常状态（07:23 弱信号打开已存在文件），非复生痕迹 | 已由 git log 1ba002a（E0-C P6 删库闭环 commit）证实为团队主动文档化操作 | 销项 | 无 | 已关闭 | RESOLVED |

## 已关闭项

### 2026-08-14 · e0c-p6-20260814-083910 疑点
- Resolution: git log 1ba002a 证实 08:39 归档是团队主动 P6 删库闭环（快照 + 删 4 db + 观察无复生/探针 OK），非 SQLite 复活痕迹。QA advisory 第 1 条销项。
