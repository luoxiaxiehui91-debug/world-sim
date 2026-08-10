# 天枢 ↔ crucix 依赖全景分析（2026-08-10）

> 触发：用户"我记得基于 crucix 做了不少东西，新闻库什么的"——对 b1 对照清单"等价覆盖"结论的复核。
> 方法：天枢核心代码全量 grep crucix 引用 + news.db 数据实证（容器内实测）。
> **结论先行**：天枢 6 个模块**实时消费 crucix API**（gscpi/nuke/sdr/air 信号 + 新闻 + 火点兜底），并非 b1 清单"等价覆盖后可随时退场"那么简单。"过渡期共存"是现状依赖而非选择；crucix 下线前须完成 6 项依赖摘除（硬依赖 3 项优先）。

---

## 1. 依赖点全量清单（代码实证）

| # | 模块 | 文件:行 | 消费内容 | 失败行为 | 强度 |
|---|------|---------|----------|----------|------|
| D1 | 指标快照 | `data_fetcher.py` L732-754 | GET crucix API → `snapshot["_crucix"]` = gscpi / nuke / sdr / air / markets.vix | `_crucix={}` 静默降级 | 🔴 硬 |
| D2 | regime 检测 | `regime_detector.py` L278-333 | `_crucix.gscpi.value` → `gscpi_warn = value > 1.5`（供应链压力 regime） | gscpi_warn 恒 0（信号静默丢失） | 🔴 硬 |
| D3 | 叙事处理 | `narrative_processor.py` L66-70 | crucix_gscpi→global_composite（tau 48）/ crucix_nuke+crucix_air→taiwan_strait（tau 24）/ crucix_sdr→sanctions_risk（tau 24） | 4 个叙事桶输入为空 | 🔴 硬 |
| D4 | 新闻库 | `news_db.py` L7 + `scan_weak_signals.py` L1517 | 全量归档 crucix 文章（url / content_hash 去重） | 少一路新闻源 | 🟡 软 |
| D5 | 弱信号新闻频率 | `scan_weak_signals.py` L1178 `fetch_crucix_news(days=90)` | 直拉 crucix 新闻 feed 做关键词频率预警 | 新闻频率降级（少一源） | 🟡 软 |
| D6 | 气候火点兜底 | `fetch_climate_signals.py` L100-147 | FIRMS 直连失败 → crucix thermal（字段 det/hc）兜底 | 直连主路径已独立，兜底丢失 | 🟢 软 |

**其他引用**：`run_macro_analysis.py` L613/L778（`crucix_context` 拼进 LLM 分析 prompt）｜`dashboard.py` L364（数据源标注）｜`optim_config.py` L110（`CRUCIX_REMOTE_URL = http://192.168.31.108:3117/api/data`）｜`fetch_rss_news.py` L3（返回与 crucix 文章格式兼容 dict）｜`scheduler.py`（无直接调用，弱信号 job 间接触发）。

---

## 2. 数据实证（news.db，容器内 08-10 实测）

- **articles 31,039 篇**，24 个 source：第一财经 10,830 / 华尔街见闻 5,760 / 36氪 3,253 / Al Jazeera 2,886 / Euronews 1,252 / France 24 1,141 / NYT 1,056 / Indian Express 860 / 东方财富研报 811 / BBC 672 / …（其余 14 源 <500）
- signal_episodes **1,824** 条 / scan_contexts **375** 次 / article_categories **2,679** 条
- **crucix 文章无独立 source 标记**：crucix 是新闻聚合者，归档后保持原始来源名（第一财经/NYT/BBC 等），无法直接统计 crucix 增量占比；代码路径存在（fetch_crucix_news → news_db 入库去重）
- data/ 无 crucix 落盘文件（crucix 数据全部实时 API 拉取，未做快照）

---

## 3. 依赖强度分级

- 🔴 **硬依赖**（crucix 下线即功能缺失）：**D1/D2/D3** —— gscpi / nuke / sdr / air 是唯一来源，且 crucix_nuke/air 直接映射 taiwan_strait 叙事桶（地缘维度输入）
- 🟡 **软依赖**（降级可运行）：**D4/D5** —— 新闻多一路源，少了只影响频率分析精度
- 🟢 **可摘**（已有主路径）：**D6** —— FIRMS 直连主路径已独立，crucix thermal 仅兜底

---

## 4. "移植/退场"真实缺口（6 项摘除动作）

| 依赖 | 摘除动作 | 替代 / 风险 |
|------|----------|-------------|
| D1+D2（gscpi） | 新增 `fetch_gscpi`（NY Fed 公开序列，月度） | gscpi_warn 失效风险；月度粒度 vs 当前实时 |
| D1（nuke） | 无现成开源源；SIPRI + Defense RSS 间接代理 | 核态势专信号语义丢失 |
| D1（sdr） | FRED / World Bank 宏观代理（优先级低） | 低风险（sdr 消费量小） |
| D3（叙事 4 映射） | 改映射到替代源或接受空桶 | global_composite / taiwan_strait / sanctions_risk 三个 GRV 维度输入变化，需重验 GRV 一致性 |
| D4+D5（新闻） | 摘 `fetch_crucix_news`，news_db 去 crucix 归档 | RSS 三源（fetch_news/fetch_rss_news/fetch_defense_rss）已独立，影响小 |
| D6（climate 兜底） | 删 crucix thermal 回退分支 | 依赖 `fetch_firms` 直连 CSV 下载慢问题修复（已知待办） |

---

## 5. 结论

1. **crucix 真实角色 = 天枢 6 模块的实时信号供给方**（gscpi/nuke/sdr/air + 新闻 feed + thermal 兜底），b1 清单"等价覆盖"定性过于乐观——`fetch_*` 覆盖的是**数据源**，而 gscpi/nuke/sdr 是 **crucix 计算产出的信号**，天枢无对等生产者，只是 API 消费者。
2. **"还差什么"修正**：不是"3 个弱信号要不要补 fetcher"（D2 决策），而是 **6 个消费点要不要摘除**（D1-D3 硬依赖摘除优先，D4-D6 可后置）。
3. 弱信号扫描（scan_weak_signals ×4/日 + signal_synthesizer 共振）是**天枢独立实现**（FRED Z-score + 新闻频率 + 地缘共振），非 crucix 移植；但其新闻频率分析消费 crucix 新闻（D5）。
4. 新闻库（news.db 31k 篇 / 1.8k 信号事件）为天枢自建，crucix 只是其中一路来源——用户记忆"基于 crucix 做了不少东西"准确：D1-D5 五条链路都在 crucix 之上。

---

## 6. 建议下一步

- 优先立项 **D1-D3 摘除**（gscpi 补 NY Fed fetch / nuke 定代理方案 / 叙事映射改源），完成后 crucix 可进入真实退场评估
- D4-D6 随主链路完善顺手摘除
- 本分析同步更新 `b1_crucix_integration.md`（依赖点补注 + ⚠️ 定性修正）
