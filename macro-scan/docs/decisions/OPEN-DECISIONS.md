# OPEN-DECISIONS — 待决事项登记

> 本文件登记已确认但暂不处理（或需跨模块决策）的开放事项。
> 每条记录含：背景、影响、当前状态。解决后移入 `docs/` 正文或标记 `[CLOSED]`。
> 最近更新：2026-08-10（commit `a7c6e42`，落盘时间戳显式时区后缀统一修复后审计）

---

## OPEN-01：news.db 内部时间字段展示层未统一（ingested_at / last_scan）

- **背景**：本次统一了所有前端直读的落盘 JSON 时间戳（UTC→`Z`、本地→`+08:00`），但 news.db 内部字段仍为 UTC-naive 写盘：
  - `news_articles.ingested_at`、`articles.last_scan`
  - `narrative_chunks.timestamp`
- **影响**：`web_server` `/status` 的 `last_scan` 原样展示 UTC naive 字符串，前端若按「无后缀=北京时间」契约解析会差 8h（与本次 GRV GDELT 同款 bug）。
- **当前状态**：**OPEN**。DB 字段为内部消费，改动涉及 migration / 读取端对齐，列为后续专门任务。改前需先梳理 news.db 全部读写点与前端对 `/status` 的消费方式。

## OPEN-02：web_server.py:530 `/grv-history` 本地↔UTC 日期混合比较边界差 8h

- **背景**：`web_server.py` 约 530 行的 `/grv-history` 接口在过滤/比较时混合使用本地日期与 UTC 日期，边界（UTC 0 点 = 北京 08:00）附近可能把「今天」的 UTC 记录归入「昨天」区间，或反之。
- **影响**：GRV 历史曲线的按日划分在每天 UTC 0:00–08:00（北京 08:00–16:00）期间与本地直觉差一天。
- **当前状态**：**OPEN**。本次只统一了写盘格式，未触碰 web_server 的读端比较逻辑。需单独评审该接口的日期边界语义（建议统一以 UTC 或本地其一为准，并显式带时区比较）。

## OPEN-03：gdelt_history.date / situations 纯日期键维持 UTC 语义，未来若展示需转换

- **背景**：`gdelt_history.jsonl` 的 `date`（`YYYY-MM-DD`，来自 `datetime.now(timezone.utc).isoformat()[:10]`）与 situations 的 `started`/`last_updated`（`%Y-%m-%d`）为纯日期键，本次**明确不改**（无时刻分量，改格式会破坏下游按日聚合）。
- **影响**：这些日期本质是 **UTC 日期**。当前仅作内部时序聚合/键值，无展示；未来若前端直接展示或与本地日期混排，需显式转换（UTC 日 → 本地日）。
- **当前状态**：**OPEN**。维持现状（UTC 语义），仅在出现展示需求时做转换。建议后续在消费端（如 `/grv-history` 按日线、situations 卡片）加一行注释或转换函数，避免再次误读。

## OPEN-04：crucix 退场 G0 PASS + D1(gascpi) wiring 完成，nuke/sdr/vix 零消费无需 wiring（RESOLVED）

- **背景**：G0（2026-08-12）执行受控切断（`docker pause crucix-crucix-1`）验证天枢对 crucix 不可达的降级行为。结果：天枢优雅降级（`_crucix`=EMPTY、不崩溃），回滚后完全恢复（`_crucix`=POPULATED，gscpi=0.79/nuke=6/sdr=True）。验证报告见 `docs/crucix-g0-verification-report.md`。
- **影响**：D1-D3（gscpi/nuke/sdr）替代源 `fetch_gscpi.py`(NY Fed) / `fetch_safecast_nuke.py` 已存在且已调度，但**未接入 `_crucix` 管线**。crucix 彻底关停后，gscpi/nuke/sdr/vix 信号将静默丢失（regime_detector / narrative_processor 降级分支生效但信号空）。
- **当前状态**：**RESOLVED（D1 完成，08-12）**。wiring 实测修正：下游真消费 `_crucix` 仅 gscpi（regime_detector 取 `.value`）；nuke/sdr/vix 在 `_crucix` 为孤儿字段、narrative 桶未接、零消费。故 D1(gascpi) 接 NY Fed CSV 唯一源（commit f30bd2d，删 :3117 分支），nuke/sdr/vix 无需 wiring。crucix 退场可推进 teardown（G1=08-15 停容器）。新闻与 crucix 零关联。
