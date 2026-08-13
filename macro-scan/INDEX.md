# 世界推演系统 INDEX

> 生成时间：2026-08-06 | 版本：v3.8.15 | **只读索引，修改请更新 CHANGELOG**

---

## 活跃容器

| 容器 | 镜像 | 端口 | 验证命令 | 备注 |
|:---|:---|:---|:---|:---|
| macro-scan-macro-scan-1 | macro-scan:v7 | 8899 (Web UI) / 8900 (Control API) | `docker ps --filter name=macro-scan --format '{{.Image}} {{.Status}}'` | 主容器，代码热挂载 S:盘；:8900 = control_server.py（A3a HTTP REST） |
| macro-scan-tianji-1 | macro-tianji:latest | 无端口 | `docker ps --filter name=tianji --format '{{.Image}} {{.Status}}'` | 天玑独立容器（v3.8.13 起）：tianji_db/tianji_verifier/weight_matrix 已迁出；触发 = T2 共享触发文件 |

---

## 定时任务（scheduler.py）

> 来源：`scheduler.py` JOBS 列表（共 50 条，唯一任务名 47，weak_signal×4）。所有时间 = 北京时间 (Asia/Shanghai)。
> 档位说明：**I15/I30 = 事件档**（每 15/30 分钟触发，非每日定点）；其余为定点时间（HH:MM）。v3.8.13 起新增 11 job，`tianji_trigger`/`fao`/`china_meso`/`verify`/`kb_update`/`climate`/`verify_auto`/`slow_vars`/`news_prune` 为每月 1 日。

| 任务 | 时间 | 频率 | 命令 | 状态 |
|:---|:---|:---|:---|:---|
| disaster | I30 | 事件档·每30分 | `fetch_disaster_signals.py` | ✅ |
| fred_fetch | 05:30 | 每日 | `fetch_fred_history.py` | ✅ |
| compute_fci | 05:35 | 每日 | `compute_fci.py` | ✅ |
| fred_freshness | 05:40 | 每日 | `fred_freshness.py` | ✅ |
| compute_probit | 05:40 | 每日 | `compute_probit.py` | ✅ |
| tianji_trigger | 09:42 | 每月1日 | `write_tianji_trigger.py` | ✅ |
| gpr_fetch | 05:40 | 每日 | `fetch_gpr.py` | ✅ |
| china_fetch | 05:45 | 每日 | `fetch_china_data.py` | ✅ |
| world_macro | 05:50 | 每日 | `fetch_world_macro.py` | ✅ |
| fx_fetch | 05:55 | 每日 | `fetch_fx.py` | ✅ |
| crypto | I15 | 事件档·每15分 | `fetch_crypto.py` | ✅ |
| weak_signal | 00:00 | 每日 | `scan_weak_signals.py` | ✅ |
| weak_signal | 06:00 | 每日 | `scan_weak_signals.py` | ✅ |
| weak_signal | 12:00 | 每日 | `scan_weak_signals.py` | ✅ |
| weak_signal | 18:00 | 每日 | `scan_weak_signals.py` | ✅ |
| sanctions | 06:05 | 每日 | `fetch_sanctions.py` | ✅ |
| earthquake | I15 | 事件档·每15分 | `fetch_earthquake.py` | ✅ |
| gdelt_geo | I15 | 事件档·每15分 | `fetch_gdelt_geo.py` | ✅ |
| energy | 06:08 | 每日 | `fetch_energy.py` | ✅ |
| crypto_extra | I15 | 事件档·每15分 | `fetch_crypto_extra.py` | ✅ |
| news | 06:16 | 每日 | `fetch_news.py` | ✅ |
| hdx | 06:20 | 每日 | `fetch_hdx.py` | ✅ |
| bdi | 06:25 | 每日 | `fetch_bdi.py` | ✅ |
| fao | 09:25 | 每月1日 | `fetch_fao.py` | ✅ |
| commodity_yahoo | 06:26 | 每日 | `fetch_commodity_yahoo.py` | ✅ |
| airtraffic_opensky | 06:28 | 每日 | `fetch_airtraffic_opensky.py` | ✅ |
| energy_eia | 06:30 | 每日 | `fetch_energy_eia.py` | ✅ |
| china_meso | 09:30 | 每月1日 | `fetch_china_meso.py` | ✅ |
| grv_update | 06:10 | 每日 | `geo_risk_vector.py` | ✅ |
| morning | 07:30 | 工作日 | `run_macro_analysis.py` | ✅ |
| us_daily | 20:00 | 工作日 | `run_macro_analysis.py` | ✅ |
| china_daily | 20:15 | 工作日 | `run_macro_analysis.py` | ✅ |
| verify | 09:00 | 每月1日 | `verify_predictions.py` | ✅ |
| kb_update | 09:05 | 每月1日 | `update_kb_numbers.py` | ✅ |
| firms | 09:08 | 每日 | `fetch_firms.py` | ✅ |
| climate | 09:10 | 每月1日 | `fetch_climate_signals.py` | ✅ |
| daily_narrative | 07:00 | 每日 | `daily_narrative.py` | ✅ |
| news_export | 07:05 | 每日 | `news_exporter.py` | ✅ |
| narrative_proc | 07:10 | 每日 | `narrative_processor.py` | ✅ |
| defense_rss | 07:12 | 每日 | `fetch_defense_rss.py` | ✅ |
| news_geo_feed | 07:15 | 每日 | `news_geo_feed.py` | ✅ |
| situation_detect | 06:30 | 每日 | `situation_detector.py` | ✅ |
| weekly_synthesis | 20:00 | 周五 | `weekly_synthesis.py` | ✅ |
| dashboard | 20:30 | 工作日 | `dashboard.py` | ✅ |
| health_push | 21:00 | 每日 | `python -c "from observability import daily_health_push; daily_health_push()"` | ✅ |
| verify_auto | 09:15 | 每月1日 | `verify_hypothesis.py` | ✅ |
| slow_vars | 09:35 | 每月1日 | `slow_variables.py` | ✅ |
| spacetrack | 06:15 | 每日 | `fetch_spacetrack.py` | ✅ |
| market_quotes | I15 | 事件档·每15分 | `market_quotes.py` | ✅ |
| news_prune | 09:20 | 每月1日 | `python -c "import news_db; news_db.prune_old_articles(DATA_DIR/news.db, 90)"` | ✅ |

---

## 数据管道

| 管道 | 输入 | 输出 | 验证命令 | 备注 |
|:---|:---|:---|:---|:---|
| FRED | api.stlouisfed.org (48序列 CSV + manifest.json) | `data/fred_history/*.csv` | `docker exec macro-scan-macro-scan-1 ls /workspace/data/fred_history/ \| wc -l` | 走 mihomo 代理；`fred_freshness.py` 0540 新鲜度闸 |
| GPR | matteoiacoviello.com (7系列) | `data/fred_history/gpr_*.csv` | `docker exec macro-scan-macro-scan-1 ls /workspace/data/fred_history/ \| grep gpr \| wc -l` | timeout=300s |
| AkShare（中国） | akshare API | `data/china_history.jsonl` | `docker exec macro-scan-macro-scan-1 wc -l /workspace/data/china_history.jsonl` | 8 指标（含 LPR） |
| GDELT 弱信号 | api.gdeltproject.org | `data/gdelt_scores.json` + `weak_signal_log.json` | `docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/gdelt_scores.json')); print(list(d.keys()))"` | 每 6h 更新 |
| GRV 地缘向量 | GDELT + GPR 聚合 + japan_monetary + sanctions_risk + seismic_risk + energy_grid_risk + social_stress + cultural_friction + 4 GDELT 国别推导 | `data/grv_latest.json` | `docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/grv_latest.json')); print({k:round(v,1) for k,v in d.items() if isinstance(v,(int,float))})"` | 16 风险维度 + 1 汇总（global_composite），每日 06:10 原子写入 |
| 地震风险 | USGS Earthquake API（直连免key） | `data/earthquake_risk.json` | `docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/earthquake_risk.json')); print(d)"` | seismic_risk → GRV 非阻断读取 |
| 能源风险 | UK Carbon Intensity API（直连免key） | `data/energy_risk.json` | `docker exec macro-scan-macro-scan-1 python3 -c "import json; d=json.load(open('/workspace/data/energy_risk.json')); print(d)"` | grid_carbon_risk → GRV 非阻断读取 |
| 加密交叉验证 | Binance / Kraken API（直连免key） | `data/crypto_extra_*.json` | `docker exec macro-scan-macro-scan-1 ls /workspace/data/ \| grep crypto_extra` | 波动率交叉验证，落盘 |
| 新闻情绪 | MarketAux / Currents / Sugra（需key降级） | `data/news_*.json` | `docker exec macro-scan-macro-scan-1 ls /workspace/data/ \| grep news_` | 市场情绪，落盘 |
| 人道风险 | HDX CKAN API（直连限流） | `data/hdx_*.json` | `docker exec macro-scan-macro-scan-1 ls /workspace/data/ \| grep hdx` | humanitarian_risk，落盘 |
| pgvector 向量库 | `知识库/` (558 .md) | worldsim-pg.rag.embeddings (4156块) | `docker exec worldsim-pg psql -U worldsim_app -d worldsim -c "SELECT COUNT(*) FROM rag.embeddings WHERE collection_name='macro_kb'"` | BAAI/bge-m3 嵌入（E0-B 退役 chroma） |
| 新闻库 | RSSHub + Crucix | `data/news.db` + `latest_news.json` | `docker exec macro-scan-macro-scan-1 python3 -c "import sqlite3; c=sqlite3.connect('/workspace/data/news.db'); print(c.execute('SELECT COUNT(*) FROM articles').fetchone()[0])"` | 双源 |
| ntfy 推送 | `run_macro_analysis.py` | ntfy.sh/***REMOVED*** | `curl -s ntfy.sh/***REMOVED***/json?poll=1` | 强制直连 |

---

## LLM 调用链

> Embedding 走硅基流动 BAAI/bge-m3（Ollama 已于 v3.5.25 移除）

| 层级 | 模型 | API 端点 | 验证命令 | 状态 |
|:---|:---|:---|:---|:---|
| 主力 | MiniMax-M3 | api.minimaxi.com/anthropic | `grep -c "call_minimax" S:\macro-scan\核心代码\hybrid_llm.py` | ✅ |
| 降级1 | MiMo v2.5 Pro | token-plan-cn.xiaomimimo.com/v1 | `docker exec macro-scan-macro-scan-1 env \| grep OPENAI_COMPAT` | ✅ |
| 降级2 | SiliconFlow Qwen3.5-27B | api.siliconflow.cn/v1 | `docker exec macro-scan-macro-scan-1 env \| grep SILICONFLOW` | ✅ |
| 兜底 | 纯数据报告 | N/A | N/A | ✅ |

---

## 关键文件路径

| 文件 | 路径 | 用途 |
|:---|:---|:---|
| VERSION | `VERSION` | 语义化版本号 |
| CHANGELOG | `TuiYan_CHANGELOG.md` | 变更日志（Keep a Changelog） |
| 人类说明文档 | `世界推演系统_人类说明文档.md` | 使用维护手册 |
| 系统 Prompt | `system_prompt.md` | LLM 分析框架 |
| scheduler | `核心代码/scheduler.py` | Python 定时调度 |
| 主入口 | `核心代码/run_macro_analysis.py` | 宏观分析主流水线 |
| LLM 引擎 | `核心代码/hybrid_llm.py` | LLM 调用 + 降级链 |
| 假设引擎 | `核心代码/hypothesis_engine.py` | 假设推演（H0-H12，详见 `docs/假设推演功能设计方案.md`） |
| docker-compose | `docker-compose.yml` | 容器编排 |
| entrypoint | `entrypoint.sh` | 容器启动脚本（改后需重建镜像） |
| observability | `核心代码/observability.py` | 可观测性模块：心跳 + 任务计数（T1-2，v3.6.5） |
| **tianji_db** | `核心代码/tianji_db.py` | **天玑**数据库schema+CRUD（predictions/reasoning_trace/narrative_chunks/weight_update_log）⚠️ **v3.8.13 已迁出 macro-ji 独立容器**（macro-scan-tianji-1），天枢不再运行 |
| **narrative_processor** | `核心代码/narrative_processor.py` | **叙事预处理**：11维叙事桶、staleness衰减、路径B密度监测 (v3.7.0) |
| **slow_variables** | `核心代码/slow_variables.py` | **慢变量**计算：IRP/UCRI/GCI三个慢变量（月频）(v3.7.0) |
| **tianji_verifier** | `核心代码/tianji_verifier.py` | **天玑月度验证**：Brier/BSS/锐度评分+反哺降权建议 ⚠️ **v3.8.13 已迁出 macro-ji 独立容器**（macro-scan-tianji-1），天枢不再运行 |
| **weight_matrix** | `核心代码/weight_matrix.py` | **玉衡权重矩阵**：读写+审批+双层clip约束+月度健康检查 ⚠️ **v3.8.13 已迁出 macro-ji 独立容器**（macro-scan-tianji-1），天枢不再运行 |
| **fetch_defense_rss** | `核心代码/fetch_defense_rss.py` | **防务RSS**：Al Jazeera/Defense One/War on the Rocks (v3.7.0) |
| **fetch_sipri_backdrop** | `核心代码/fetch_sipri_backdrop.py` | **SIPRI军事背景卡片**：年度静态数据，天璇推演时注入 (v3.7.0) |
| **control_server** | `核心代码/control_server.py` | **A3a 控制面板**：HTTP REST :8900（契约/白名单/健康探测），v3.8.13 上线 |
| **compute_fci** | `核心代码/compute_fci.py` | **L1 FCI 双轨**：依赖 fred_fetch 刷新 fred_history，05:35 执行 |
| **fred_freshness** | `核心代码/fred_freshness.py` | **FRED 新鲜度闸**：stale 告警 + FCI data_vintage 探针，05:40 执行（v3.8.13） |
| **write_tianji_trigger** | `核心代码/write_tianji_trigger.py` | **天玑 T2 触发文件**：scheduler 0942（每月1日）写 trigger → macro-ji watchdog 轮询（v3.8.13） |
| **news_geo_feed** | `核心代码/news_geo_feed.py` | **P3-A 新闻坐标**：spaCy NER + gdelt_geo_cache，07:15 执行 |
| **market_quotes** | `核心代码/market_quotes.py` | **市场行情快照整合**：commodity+crypto，I15 事件档 |
| **fetch_spacetrack** | `核心代码/fetch_spacetrack.py` | **Space-Track 卫星统计**：日频 06:15 |
| **fetch_firms** | `核心代码/fetch_firms.py` | **NASA FIRMS 火点**：日频 09:08，crucix 退场前置 |

---

## 关键约束（维护铁律）

1. 修改前：读 `TuiYan_CHANGELOG.md`（了解最新变更）
2. 修改后：追加 `TuiYan_CHANGELOG.md` → bump `VERSION`（PATCH） → 更新对应文档
3. 每次里程碑：打 zip 存 `备份/`
4. ntfy 推送**强制直连**，不走代理（OUTBOUND_PROXY 仅给 FRED）
5. `entrypoint.sh` 变更需重建镜像，文件必须无 BOM
6. docker-compose.yml 改 env 后需 `up -d --force-recreate`（`restart` 不重新注入）
7. 代码热挂载：改 `S:\macro-scan\核心代码\*.py` → 容器内 `/app/` 即时生效
8. `/workspace/` 本身不挂载，只有子目录挂载

---

## 快速诊断

```bash
# 容器状态
docker ps --filter name=macro-scan

# scheduler 最新日志
docker exec macro-scan-macro-scan-1 tail -20 /var/log/macro-scan/scheduler.log

# 心跳存活检查（v3.6.5）
docker exec macro-scan-macro-scan-1 cat /workspace/data/.scheduler_heartbeat

# 可观测性统计（v3.6.5）
docker exec macro-scan-macro-scan-1 cat /workspace/data/observability_$(date +%Y-%m-%d).json

# 最新 GRV
docker exec macro-scan-macro-scan-1 cat /workspace/data/grv_latest.json

# 最近推送
curl -s "https://ntfy.sh/***REMOVED***/json?poll=1&since=1h"

# 所有状态一键 (Web UI)
curl -s http://192.168.31.108:8899/api/data | python3 -m json.tool | head -30
```

---

## ntfy 指令速查

向 `***REMOVED***` 发消息，格式 `1900 <指令>`：

| 指令 | 效果 |
|:-----|:-----|
| `1900 analysis` | 触发宏观分析报告生成（异步执行，立即返回不阻塞轮询循环） |
| `1900 status` | 推送容器运行时间、最新报告文件名、news.db 文章数、定时任务计划等系统状态摘要 |
| `1900 last` | 以文件附件形式重新推送最新分析报告，args[0] 可指定 china/us/both 过滤 |
| `1900 news` | 触发新闻弱信号扫描（异步执行，立即返回不阻塞轮询循环） |
| `1900 verify` | 触发预测校验（异步执行，立即返回不阻塞轮询循环） |
| `1900 hypothesis` | 触发假设推演 |
| `1900 ask` | 自由提问 |
| `1900 situations` | 列出当前追踪的所有事件状态 |
| `1900 confirm_situation` | 确认追踪自动检测的新情况，去掉 needs_review 标记 |
| `1900 dismiss_situation` | 忽略并归档自动检测的情况（话题再次升温会自动恢复） |
| `1900 narrative` | 立即生成并推送今日世界摘要（不等待07:00定时任务） |
| `1900 weekly` | 立即生成并推送本周综合报告 |
| `1900 help` | 推送所有可用指令列表（含语法示例）到 ntfy |
| `1900 synthesize` | 手动触发指定 synthesis 规则（跳过冷却检查） |
| `1900 silence` | 静默指定 synthesis 规则 N 天（写入虚拟冷却记录） |

---

## 路线图（时间门控）

| 解锁时间 | 任务 |
|:---------|:-----|
| ~~**2026-07-10**（C线上线30天后）~~ ✅ **已执行**（2026-07-10）| C线切Live：`STAGING_MODE=0` 已写入 docker-compose.yml；R07 `enabled: true`（religious_conflict 近14天 58/63条有效）|
| 2026-09-10（GDELT运行3个月）| 校准 religious_conflict/regime_change 的 scale 参数 |
| 2026-11-19（N1上线180天）| N2 反向查询（宏观快照→历史新闻分布） |
| 2027-05-23（N1上线1年）| N3 信号月度校验 |
| 真实地缘事件发生后 | M2-4 校准闭环激活（见 `docs/假设推演功能设计方案.md` §校准闭环命令） |

---

## 宏观体制（regime）判断規則

> 来源：`核心代码/regime_detector.py`。改此文件后必须同步本节。

| 指标 | risk-on | risk-off/stress |
|:-----|:--------|:----------------|
| VIX | <15 → +1 | >25 → -1；>35 → stress直触 |
| T10Y2Y | >0 → +1 | <-50bp → -1 |
| BAA10Y | <1.8% → +1 | >3.5% → -1；>4.5% → stress |
| DFF | <2% → +1 | 月环比>25bp → -1 |

**三档体制**（`regime_detector.py` 返回全小写）：

| 体制 | 触发条件 | 关键系数 |
|:-----|:---------|:---------|
| `normal` | 无压力信号 | rate_gdp_impact=-0.30，credit_multiplier=1.2 |
| `stress` | 连续2季度触发 Z-score 压力阈值 | rate_gdp_impact=-0.80，credit_multiplier=2.5 |
| `crisis` | NBER 衰退期 + VIX/BAA Z-score>1.5 | rate_gdp_impact=-1.50，credit_multiplier=4.0 |

> 压力信号计数（满分8）：VIX_z / BAA_z / T10_z / unrate_3m / PPI>7% / CPI>3.5% / WTI>90 / GSCPI>1.5

 
