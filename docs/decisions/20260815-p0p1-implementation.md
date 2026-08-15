# 2026-08-15 审查 P0/P1 实施记录

- **关联**：`../reviews/`（Track A 审查 + Track B 规划 + 主理人回复 + 审计方再复核）
- **日期**：2026-08-15（审查闭环 → P0 止血 → P1 打通）
- **性质**：实施记录（决策见各 commit；本文档为状态快照与 commit 链）

## 实施总览

| 项 | 内容 | commit | 状态 |
|----|------|--------|:--:|
| **P0-B** | C01 GRV 止血：补回 af752ea 误删的 5 个模块常量 + GRV_DRY_RUN 首日抑制实证拦截假告警 | `0eb25d3` | ✅ |
| **P0-D D1-D4** | 预测落表链路：D1 幂等建表 / D3 天玑守卫 / D4 去静默（天璇/天玑重建） | `5e109f9` | ✅ |
| **P0-C** | 观测口径纠偏（SQLite→PG 双读期）+ 预测链探针 check_predictions_chain + sqlite_gone 过渡豁免 | `b876ad4` `09419d5` | ✅ |
| **P0-D2** | 预测链转 PG：天璇/天玑 psycopg 直连 tianji + 天枢观测切 PG + A1 缓存连接自愈 | `afe1311` `f7cf689` | ✅ |
| **P1-A** | Brier/BSS 去污染：H03 气候学基准率 / H04 无阈值跳过 / H05 样本门控 | `d237aa7` | ✅ |
| **P1-B** | 静默失败 fail-loud：set_alert_hook 默认 ntfy 接线 + GED 陈旧告警（check_ged_stale） | `7a13b98` `510432a` | ✅ |
| **P1-C** | 迁移收尾：DDL 回写 pg_synced_at（6 表）+ articles UNIQUE 对齐（H13） | `6159d0a` | ✅ |
| **P1-D** | 控制面收敛：CONTROL_TOKEN fail-closed + CORS 收窄 | `5136dc3` | ✅ |
| **P0-A** | 密钥轮换（GitHub PAT / FRED / LLM / EIA / ntfy 1900） | — | ⏸ 待办（用户暂缓，仓库私有） |
| **P1-E** | causal_assumptions.md 补全（纯文档，P2 天权前置） | — | ⬜ 未做 |
| **P6** | 删 SQLite forecast_tracker.db + 移除 sqlite_gone 豁免 | — | ⬜ 观察窗后 |

commit 链：`0eb25d3 → 5e109f9 → b876ad4 → 09419d5 → afe1311 → f7cf689 → d237aa7 → 7a13b98 → 510432a → 5136dc3 → 6159d0a`（main，全部推送）

## 关键决策记录

1. **C01 为 08-14 回归非镜像不一致**：md5 验证运行区=git 真源、容器 import ImportError、grv_latest.json 停 08-14 06:10、pickaxe 定位 af752ea（08-14 08:33）删常量未清引用 → 时间线解释 arch(08-02) vs Track A(08-15) 矛盾。
2. **GED 数据链从未走完**：原始 261MB 快照已下载（S:/20260729/data/），etl_ged.py 就绪，但 ETL 从未跑 → ged_agg_country_month.csv 从未生成 → GED 补强从未生效；且 2024-12 冻结超 18 个月窗即使补跑也不生效。补数据 = P2 决策。
3. **P0-D2 转 PG 线上库三自增表缺序列**：narrative_chunks/reasoning_trace/weight_update_log id 无默认值 → worldsim_admin 补序列 + `GRANT USAGE ON SEQUENCE ... TO worldsim_app`（新序列必须授权，否则 permission denied）。
4. **P6 守卫 271a761 曾加错文件**（macro-scan 副本 vs macro-ji 副本）→ 教训：三容器 tianji_db.py 多副本，改守卫/DDL 须确认容器实际用的那份。
5. **运行区 compose 必须显式含 networks + WORLDSIM env**：手动 docker network connect 在 compose up -d recreate 后即丢（PG 解析失败实测）；WORLDSIM_APP_PW/WORLDSIM_SQLITE_OFF 曾丢失导致 SQLite 双写纪律回归——现全部显式写入，printenv 验证。
6. **H13 线上其实已有 UNIQUE**：news_uq_articles_hash/url（b0_migrate 迁移时建）——Track A 基于 DDL 文件的判断方向相反；DDL 文件已回写对齐。

## 探针状态

- silent_failure_probe 31 项全绿（verdict=INFO bad=0）：dualwrite / heartbeat / artifacts / backup / fred_lag / news_risk / sqlite_gone（豁免 forecast_tracker.db）/ feed_fresh / predictions_chain / ged_stale
- observability daily_health_push 数字3 = PG tianji.predictions 行数（10）

## 待办

- **P0-A 密钥轮换**（触发条件=仓库转公开/外部共享前；含 filter-repo 清 tracked compose + b0 分支 + set-url）
- **P6 删 SQLite**：观察 1-2 天无复生 → `delete_sqlite_e0c.sh` + 移除 `_SQLITE_GONE_EXEMPT`（同一步骤）
- **P1-E causal_assumptions 补全**（约 1 天，P2 天权公式输入）
- **P2 全部**（门控：预测链闭环跑通，MIN_TRIGGER_N=8 触达约需 3 个月数据积累）：玉衡 V2 通数据 / 天权公式 / 新数据源 / 新 Agent / 契约 schema 单一化 / GED 数据决策
