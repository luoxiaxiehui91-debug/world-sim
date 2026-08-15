# crucix 退场 G0 切断验证报告

> G0 判定日：2026-08-12（crucix 退场观察窗第 0 天）
> 执行方式：受控切断（docker pause）→ 降级观测 → 回滚 → 恢复验证
> 结论：**GO** — 天枢对 crucix 不可达优雅降级、不崩溃；回滚后完全恢复。但 D1-D3 信号 wiring 未完成，切断期间 gscpi/nuke/sdr/vix 静默丢失，详见「残留风险」。

---

## 1. 方法（含用户实测勘误 H1-H4）

计划原稿（`crucix-g0-verification-plan.md`）经用户容器实测勘误后采用：

| 勘误 | 原计划 | 实测修正 |
|------|--------|---------|
| H1 | 容器内 `iptables -A OUTPUT -d ... -j DROP` | 容器无 iptables / 无 NET_ADMIN → 改 `docker pause crucix-crucix-1`（crucix 不删，开阳不依赖 crucix，pause 安全） |
| H2 | 读 `.scheduler_heartbeat` | 实际心跳在 `scheduler_state.json` 的 `heartbeat` 字段 |
| H3 | `GSCPI.csv` 在 `data/` 根 | 实际在 `data/fred_history/GSCPI.csv` |
| H4 | 函数名 `get_macro_snapshot` | 实际 `get_current_snapshot` |

切断窗口 ≤ 1 调度周期，切前留基线，必回滚，不动生产配置。

---

## 2. 基线快照（步骤 0-2，只读）

- crucix 服务：`crucix-crucix-1`，`Up`（healthy），宿主 `*:3117` LISTEN。
- grv_latest.json mtime `06:10`；scheduler_state.json heartbeat `1786507878.9`（存活）。
- `_crucix` = **POPULATED**，keys=[gscpi, nuke, sdr, markets]，gscpi=0.79 / nuke=6 / sdr=True。
- 静态复核：`data_fetcher.py:732-752`（注入 `_crucix`）、`regime_detector.py:278-341`（gscpi）、`narrative_processor.py:67-70`（4 桶）、`run_macro_analysis.py`（crucix_context 注入报告）仍在消费 crucix；D4/D5/D6/air 已摘除（注释实证）。
- 替代源落盘均存活：`GSCPI.csv`(08-10) / `safecast_nuke.json`(12:00) / `sdr_summary.json`(06:02)，**但未接入 `_crucix` 管线**。

---

## 3. 切断与恢复结果（步骤 3-7）

| 步骤 | 动作 | 结果 |
|------|------|------|
| 3 | `docker pause crucix-crucix-1` | crucix → Paused；天枢容器 `Up 30 hours` 未受波及 |
| 4a | 天枢触发快照 | `[SKIP] Crucix: Read timed out (read timeout=8)`；`_crucix` = **EMPTY**，keys=[]；快照跑完无异常（优雅降级） |
| 4b | 容器存活 + 日志 | `Up 30 hours`，日志无崩溃；heartbeat `1786509860` 较基线 +1981s（调度器仍跳动） |
| 5 | 独立产物存活 | `GSCPI.csv`/`safecast_nuke.json`/`sdr_summary.json` 均在盘，与 crucix 无关，切断不影响 |
| 6 | `docker unpause crucix-crucix-1` | crucix → Up（unhealthy 瞬时，探针间隔未到） |
| 7 | 恢复验证 | 重触发快照 `[OK] Crucix: gscpi=0.79, nuke=6, sdr=True`；`_crucix` 回 **POPULATED**；复测 crucix → `healthy`（已恢复服务） |

---

## 4. 关键修正（避免误读）

- **`regime: None` 不是切断症状**：手动 `get_current_snapshot` 在切断前/后均返回 `regime=None`（regime 由 scheduler 的 `run_macro_analysis` 计算，不走此调用路径）。故「regime 丢失」不计入 crucix 切断代价。
- **新闻与 crucix 零关联**：天枢新闻自采 RSS（`fetch_rss_news` 8 路由 + `defense_rss`），`scan_weak_signals.py:5` 注释「不再拉取 crucix 新闻」；单一 `news.db` 在共享卷，crucix 从没写入。切 `:3117` 不影响新闻。已顺手修正 `news_db.py:7` 过时注释（commit `3485a38`）。

---

## 5. 残留风险（GO 但需跟进）

- **D1-D3 信号 wiring 未完成**：`fetch_gscpi.py`(NY Fed) / `fetch_safecast_nuke.py` 已存在且已调度，但未接入 `_crucix` 管线。crucix 彻底关停后，gscpi/nuke/sdr 信号将**静默丢失**（regime_detector / narrative_processor 降级分支生效，但信号空）。
- **处置建议**：在最终 teardown crucix 前，完成 D1-D3 wiring（将替代源注入 `_crucix`），使退场后信号连续；或明确接受「gscpi/nuke/sdr 退场即弃」并在 STATUS 标注信号口径变化。
- **G1 判定日 08-15**：届时按本验证结论 + D1-D3 wiring 进度，决定是否正式停止 crucix 容器。

---

## 6. 待决项

→ 详见 `macro-scan/docs/decisions/OPEN-DECISIONS.md` **OPEN-04**（crucix 退场 G0 验证 PASS + D1-D3 wiring 待完成）。
