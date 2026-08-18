# 审计修复登记表（2026-08-18 全量审查 → 修复）

> 来源：`C:\Users\luoxi\WorkBuddy\世界推演系统\world-sim-audit-20260818(-rev2).md`（5 路并行只读 agent + 主理人 SSH 实测复核）。
> 复核结论：审计可信度高（P0-1/P0-2/P1-1 等全部实锤）；2 处与事实不符已修正（verify_human.py 存在于 macro-sim；backfill_criteria 容器存在 = docker cp 手动拷入，Dockerfile 已补 COPY）。
> 销项方式同 audit-todo-20260815.md（commit 销项 + STATUS 待办节同步）。**P0-2 用户明确暂缓**。

## 1. 已修复（08-18 修复批次）

| 项 | 处理 | 证据/commit |
|----|------|-------------|
| **P1-1 L2 死门禁** | `verify_geo_auto.py` main 循环放行条件补 `or key in L2_KEYWORDS`（此前 L2 键全被 continue 跳过，判定器永不达——**我写代码时的 bug**） | 门禁放行 9/9 实测（L2 全放行 / A13 跳过）；已热挂载 |
| **P1-2 due_at 早 8h** | `TianjiTab.daysLeft` 显式补 `+00:00`（pg_read 归一化 = UTC 无后缀，**不能复用 parseTs**——parseTs 契约是"无后缀=北京"，复用会错更多；审计建议部分不适用，已注释说明） | bundle `index-14H7YVQ2.js` 已部署 |
| **P1-3 DDL 缺列** | `03_b0_schema.sql` predictions 表补 `action_key`/`human_note`（08-18 ALTER 的迁移留痕） | 本批次 |
| **P1-a macro-sim TZ** | Dockerfile 加 `ENV TZ=Asia/Shanghai` + tzdata；实测 `docker exec macro-sim date` = CST（北京） | 容器重建验证 ✅ |
| **P1-c regime until 忽略** | `_resolve_soul_by_month` 选择加 `asof < until` 校验 + 空档回退告警；单元测试 06→current / 10→next_alliance / 08 空档告警 ✅ | 容器回归测试 ✅ |
| **P1-d as_of UTC 月** | 随 P1-a 容器 TZ 修复自动解决（datetime.now() 变北京月）+ 注释说明 | 同 P1-a |
| **P1-8 幂等 TOCTOU** | `control_server.py` verify UPDATE 加 `AND status='awaiting_human'`（防 SELECT/UPDATE 间并发连点） | 幂等 409/参数 400 复测 ✅ |
| **P0-4 ntfy_listener SQLite 地雷** | SQLite 分支加文件缺失即 return（P6 删库后禁复生空库） | 已热挂载 |
| **P1-4 时区硬化（10 处）** | 天枢 5（signal_synthesizer/ntfy_listener×3/daily_narrative）+ 天玑 5（tianji_db/tianji_verifier/weight_matrix utcnow→now(timezone.utc)）；`[:19]` 截断改完整 aware | 天枢已热挂载；**天玑 3 文件随 P0-1 天玑重建生效** |
| **P1-5 updated_at 写入** | `log_weight_update` INSERT 补 updated_at（此前 NULL，玉衡审计排序退化） | 随天玑重建生效 |
| **P1-6 compose 模板纪律** | macro-scan compose 补 `networks: worldsim_default`（顶层+两 service）+ `WORLDSIM_SQLITE_OFF=1`/`WORLDSIM_APP_PW`/`CONTROL_TOKEN`（.env 占位） | `docker compose config` VALID |
| **P2 死代码清理** | git rm `core/sim_log.py` + `core/backtest.py`（孤儿链，backtest 无调用方）+ run.py `_write_json`（无调用）+ compose 移除 sim_log.db 挂载 | 本批次 |
| **P2 macro-ji 文档 SQLite 误述** | AGENTS.md 架构图 + README.md 3 处（tianji_db 说明/数据流/共享数据表）统一 PG 口径 | 本批次 |
| **P2 kaiyang AGENTS 版本** | v1.11.27 → v1.11.34 + 控制面/模型线变更补全 | 本批次 |
| **P2 OPEN-DECISIONS 补登记** | P0-1（LIVE，待批准）/ P0-2（用户暂缓）/ 双 tianji_db | 本批次 |
| **P2 backfill_criteria 入构建** | Dockerfile 加 `COPY backfill_criteria.py`（此前仅 docker cp 手动拷入，rebuild 会丢） | 容器重建验证 ✅ |

## 2. 待办（需用户批准 / 排期）

| 项 | 位置 | 状态 |
|----|------|------|
| **P0-1 天玑 env 丢失（LIVE）** | 运行区 macro-ji compose 加 `.env`/显式 environment 注入 `WORLDSIM_APP_PW` → `up -d`；强化 healthcheck 为真实 PG 查询 | ⬜ **需用户批准运行区变更**（OPEN-DECISIONS 已登记） |
| **P0-2 明文密钥入 git** | git rm --cached + 改名 .example + 轮换密钥 | ⏸ 用户暂缓（OPEN-DECISIONS 已登记） |
| **P0-3 开阳构建铁律 VITE_CONTROL_API_TOKEN** | kaiyang/AGENTS.md:48 铁律删除（当前 dist 实测未含 token，安全侧） | ⬜ 待排期（一行文档） |
| **P1-b 双 tianji_db 分歧** | macro-scan SQLite 版 vs macro-ji PG 版；实测 _PG_ONLY 下 NoopConn 吞 qmark + PG 旁路生效 = **非运行 bug，维护负担**（审计定性偏高，已降级）；天玑重建后确认无影响 | ⬜ 下次大重构统一 |
| **天玑侧部署**（P1-4 3 文件 + P1-5） | macro-ji 重建镜像（随 P0-1 up -d 一起） | ⬜ 依赖 P0-1 批准 |
| **P1-4 剩余核实** | 审计引 tianji_db.py:273-292 行号与 macro-ji 版不符（updated_at 主问题已在 weight_update_log 修复） | ⬜ 低优先 |

## 3. 复核修正（审计与事实不符处）

- **verify_human.py "经查不存在"**：实际存在于 macro-sim（git + Dockerfile COPY + 容器实测）——审计该项表述有误（可能指 macro-ji 侧），主 claim（DDL 缺列）仍成立
- **backfill_criteria.py "矛盾待核"**：静态（没进 Dockerfile）与实测（容器存在）都对——原因是我 docker cp 手动拷入；已补 Dockerfile COPY 根治
- **P1-b 定性**：审计称"psycopg 遇 ? 报错"——实测 _PG_ONLY 下 get_connection 返回 NoopConn（吞掉 qmark），PG 旁路 %s 正常执行，**非运行 bug**；降级为维护负担
- **P1-2 修复建议**：审计建议复用 parseTs——但 parseTs 契约"无后缀=北京"（天枢数据）与 pg_read 归一化"无后缀=UTC"（TIMESTAMPTZ）冲突，复用会错更多；已按 UTC 语义显式修复
- **safecast_nuke "未注入，白烧配额"（08-18 16:1x 复核）**：审计定性过时——核辐射告警链 **08-14 已修通**（`fetch_safecast_nuke.py:148 _alert_anomalies`，anom 翻转 → ntfy 推送 + nuke_alert_state.json 去重，chernobyl anom=true 在位实测）；"未注入"仅指 GRV 观测快照无核辐射维度 = 可选增强非缺失 → **无需修复，销项**；如需 GRV 核辐射维度另立 OPEN-DECISIONS

## 4. 后续观察

- **天玑验证层恢复后**（P0-1 批准后）：验证 Brier/BSS 链路 + weight_update_log.updated_at 写入 + 玉衡反哺
- **2027-02 首轮 geo 预测到期**：L1+L2 自动验证全链路首次真实触发（L2 已修死门禁）
