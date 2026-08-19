# OPEN-DECISIONS — world-sim 待决项总索引

> 本项目有两份**子系统级** OPEN-DECISIONS 登记册 + 一份**总册**，范围不同、非重复拷贝（2026-08-12 全量审计 F6 建立本索引）。
>
> | 层级 | 登记册路径 | 记录范围 |
> |------|-----------|----------|
> | 总册 | [`docs/decisions/OPEN-DECISIONS.md`](docs/decisions/OPEN-DECISIONS.md) | 全量检查/审查遗留 + 08-18 事故/决策登记（P0-2 密钥 / 双 tianji_db / reconcile 守卫 / daily_narrative PG 化 / market 进 PG） |
> | 天枢（macro-scan） | [`macro-scan/docs/decisions/OPEN-DECISIONS.md`](macro-scan/docs/decisions/OPEN-DECISIONS.md) | 时区类 OPEN-01 / OPEN-02 / OPEN-03（news.db 展示层 / grv-history 边界 / 纯日期键） |
> | 天璇（macro-sim） | [`macro-sim/docs/decisions/OPEN-DECISIONS.md`](macro-sim/docs/decisions/OPEN-DECISIONS.md) | 校准类（liquidity_premium 死变量 / EASE 探针 FAIL / 接受线未达加权一致率<60% / clamp 对称化） |
>
> **新增待决项归属**：时区/采集层问题 → 写天枢册；校准/引擎问题 → 写天璇册。两份册格式不一致（天枢散文、天璇表格）为历史遗留，新增条目沿用各册现有格式即可。
>
> 架构决策（ADR）以 git commit 形式记录（单人研究系统，未单列 ADR 文档）；STATUS「关键决策」节 + `docs/calib/` 为设计评审权威。
