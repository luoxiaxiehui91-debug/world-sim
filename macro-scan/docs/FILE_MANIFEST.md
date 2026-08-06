# FILE_MANIFEST — 文件清单与职责说明

> 版本：v3.8.15 | 最后更新：2026-08-06
> 本文档描述 macro-scan 项目各文件的职责、挂载路径和修改影响。

---

## 根目录

| 文件 | 职责 | 修改影响 |
|:---|:---|:---|
| `VERSION` | 语义化版本号 | 无运行影响，每次修改源码后 bump |
| `TuiYan_CHANGELOG.md` | 变更日志（Keep a Changelog 格式） | 无运行影响，改前必读改后必追加 |
| `README.md` | 项目简介、快速启动 | 无运行影响 |
| `INDEX.md` | 系统状态索引（定时任务/数据管道/LLM链） | 无运行影响，只读 |
| `AGENTS.md` | Agent 工作指南（维护规则、联动矩阵） | 无运行影响 |
| `CLAUDE.md` | Claude Code thin wrapper（见 AGENTS.md） | 无运行影响 |
| `Dockerfile` | 容器镜像构建 | **需重建镜像** |
| `entrypoint.sh` | 容器启动脚本 | **需重建镜像**，必须无 UTF-8 BOM |
| `docker-compose.example.yml` | 部署模板（不含密钥） | 无运行影响，参考用 |
| `docker-compose.yml` | 实际部署配置（.gitignore中） | 改 env 后需 `up -d --force-recreate` |
| `requirements.txt` | Python 依赖 | **需重建镜像** |
| `system_prompt.md` | LLM 分析框架提示词 | 热挂载，直接编辑即时生效 |
| `crontab` | 容器内 cron 备用（主调度用 scheduler.py） | **需重建镜像** |
| `deploy.sh` | 部署辅助脚本 | 无运行影响 |
| `世界推演系统_人类说明文档.md` | 使用维护手册 | 无运行影响 |

---

## 核心代码/（容器内挂载为 /app）

> 当前 **93 个 .py 顶层文件**（96 含 `/app/tests/` 3 个测试文件）。所有 .py 文件**同级平铺**，不能分子目录。import 依赖同级路径，entrypoint.sh 以 `python3 xxx.py` 调用。

### 入口与调度

| 文件 | 职责 |
|:---|:---|
| `scheduler.py` | Python 定时调度器，管理全部 cron 任务，由 entrypoint.sh 启动 |
| `run_macro_analysis.py` | 主分析入口，8步流水线 + 假设推演分支 |
| `ntfy_listener.py` | 手机指令监听（ntfy），长驻进程 |
| `web_server.py` | Web UI 服务（:8899），长驻进程 |

### 数据采集

| 文件 | 职责 | 数据输出 |
|:---|:---|:---|
| `fetch_fred_history.py` | FRED 48个宏观序列（48 CSV + manifest.json；v3.8.13 恢复 DGS3MO/T10Y3M/T5YIE/NFCI symbol） | `data/fred_history/*.csv` |
| `fetch_gpr.py` | GPR 地缘风险指数（7系列） | `data/fred_history/gpr_*.csv` |
| `fetch_china_data.py` | 中国宏观数据（AkShare） | `data/china_history/` |
| `fetch_china_data_akshare.py` | AkShare 数据抓取工具函数 | 被 run_macro_analysis 调用 |
| `fetch_disaster_signals.py` | 灾难/极端天气信号 | `data/disaster_signals.json` |
| `fetch_climate_signals.py` | 气候变量 | 月度更新 |
| `fetch_rss_news.py` | RSS 新闻抓取 | 被 scan_weak_signals 调用 |
| `compute_fci.py` | L1 FCI 双轨（依赖 fred_fetch 刷新 fred_history；gate_ok=false 冻结不落库 fail-loud） | `data/fred_history/` + fred_gate_status.json（v3.8.13 源码重建） |
| `fred_freshness.py` | FRED 数据新鲜度监控 + 拉取一致性闸（stale>3交易日告警 / critical 连续2日 / FCI data_vintage 探针） | `data/fred_freshness.json`（v3.8.13 新建） |
| `fetch_spacetrack.py` | Space-Track 卫星统计（日频 06:15） | `data/spacetrack.json` |
| `market_quotes.py` | 市场行情快照整合（commodity+crypto，I15 事件档，v3.8.14 起 I15） | 整合行情输出（供开阳） |

### 分析引擎

| 文件 | 职责 |
|:---|:---|
| `regime_detector.py` | 宏观政策周期识别 |
| `monte_carlo_v2.py` | 蒙特卡洛情景模拟 |
| `hypothesis_engine.py` | 假设推演引擎（H0-H12，M0-M2流水线）；`run_hypothesis_simple()` 供 subprocess 调用的简化入口（v3.5.32 新增）|
| `verify_hypothesis.py` | 假设校准闭环 |
| `signal_synthesizer.py` | 信号综合评分 |
| `scan_weak_signals.py` | 弱信号扫描（GDELT + RSS，每6h） |
| `situation_detector.py` | 事件情势检测与分级 |
| `situation_tracker.py` | 持续情势追踪与状态机 |
| `geo_risk_vector.py` | GRV 地缘风险向量聚合（**16 风险维度 + 1 汇总 global_composite**：4 基础地缘 + 8 扩展 + 4 GDELT 国别推导）；v3.5.41 修复 `compute_grv` NameError |
| `grv_threshold.py` | GRV 阈值判断与告警 |
| `assess_structural_dimensions.py` | 结构性维度评估（L1-L4） |
| `sector_rotation.py` | 板块轮动分析 |
| `calibrate_mc.py` | 蒙特卡洛参数校准 |
| `adapter.py` | 预测日志格式适配器 |
| `daily_narrative.py` | 每日叙事摘要生成 |
| `weekly_synthesis.py` | 周度综合报告 |

### 数据库与工具

| 文件 | 职责 |
|:---|:---|
| `hybrid_llm.py` | LLM 调用层（MiniMax → MiMo → Qwen → 纯数据降级） |
| `optim_config.py` | **全局配置中枢**，所有路径/参数/KEY_INDICATORS（32条含EU/JP）从此读取 |
| `alert_config.py` | 弱信号配置（ALERT_KEYWORDS 13类 / _WATCH_COUNTRIES / _ACTOR_*），2026-06-27 从 scan_weak_signals 提取 |
| `hypothesis_config.py` | 假设推演类型映射（DIM_MAP），2026-06-27 从 hypothesis_engine 提取 |
| `news_db.py` | SQLite 新闻库；`prune_old_articles(days=90)` 月度清理（2026-06-27 新增）|
| `news_exporter.py` | macro-sim 数据桥；每日 07:05 导出近7天地缘/能源/金融/宏观/货币类文章至 `data/news_export.json` |
| `rag_engine.py` | ChromaDB 向量检索；`rag_query()` 统一入口（向量+TF-IDF fallback，2026-06-27 新增）|
| `forecast_tracker.py` | 预测记录追踪 |
| `prediction_logger.py` | 预测日志写入 |
| `verify_predictions.py` | 月度预测回测 |
| `update_kb_numbers.py` | 月度知识库数值更新 |

### 离线工具（不在自动调度中）

| 文件 | 职责 | 调用方式 |
|:---|:---|:---|
| `build_rag_index.py` | 重建 ChromaDB 向量索引 | docker exec ... python3 build_rag_index.py |
| `build_report_data.py` | 知识库数据采集 | 手动执行 |
| `diag_p0.py` | P0 阶段诊断工具 | 手动执行 |
| `check_doc_sync.py` | pre-commit 联动文档检查脚本 | 自动（pre-commit hook） |
| `check_doc_drift.py` | 文档漂移巡检，发现运行区 py 比 CHANGELOG 新则 ntfy 告警 | 自动（scheduler 每日 10:00） |
| `gen_docs.py` | 从代码生成 INDEX.md/FILE_MANIFEST.md 对应节 | python 核心代码/gen_docs.py --target all |

---

## 知识库/财经知识库/（容器内挂载为 /workspace/知识库）

> 人工维护内容，全部纳入 git。`_raw/` 子目录和 `_update_tmp/` 排除在 git 外。

| 子目录 | 内容 | 是否在 git |
|:---|:---|:---|
| `00_快速参考/` | 全球核心指标速查表 | ✅ |
| `01_宏观经济指标/` | 各经济指标 README、解读、数据摘要 | ✅（raw_*.json 除外）|
| `02_核心变量因果链/` | 传导机制文档、量化参数 CSV | ✅ |
| `04_分析框架/` | 分析框架文档、`propagation_paths.yaml` | ✅ |
| `03_按经济体/` | 各国经济全景文档 | ✅（_raw/ 除外）|
| `13_历史危机情景/` | 历史危机案例分析 | ✅ |
| `12_历史案例/` | 历史案例复盘 | ✅ |
| `19_数据字典/` | 数据字典 | ✅ |
| `07_方法论/` | 分析方法论文档 | ✅ |
| `17_反馈回路参数/` | 反馈回路量化参数 | ✅ |
| `16_经济日历/` | 经济日历 | ✅ |
| `09_预测模型/` | 蒙特卡洛推导文档 | ✅ |
| `07_分析报告/` | 自动生成的分析报告镜像 | ❌（.gitignore）|
| `10_宏观理论体系/` | 宏观理论文档（18篇）| ✅ |
| `14_地缘政治/` | 地缘政治专题 | ✅ |
| `21_专题报告/` | 23篇专题深度报告 | ✅ |
| `中国/日本/美国/...` | 各经济体深度分析 | ✅ |
| `_update_tmp/` | kb 更新临时 JSON | ❌（.gitignore）|
| `political_calendar.yaml` | 政治日历（daily_narrative 读取）| ✅ |

---

## 运行时目录（不在 git 中）

| 路径 | 内容 | 清空影响 |
|:---|:---|:---|
| `data/fred_history/` | FRED CSV 历史数据 | 下次 fetch 自动重建，RAG 索引暂不可用 |
| `data/chroma_db/` | ChromaDB 向量索引（4156块，BAAI/bge-m3）| 需重新运行 build_rag_index.py |
| `data/news.db` | SQLite 新闻库 | 新闻历史丢失 |
| `data/situations.yaml` | 当前事件情势状态 | 情势追踪重置 |
| `data/grv_latest.json` | 最新 GRV 向量 | 下次 06:10 任务自动更新 |
| `logs/` | 各任务日志 | 无功能影响 |
| `docs/分析报告/` | 分析报告输出 | 历史报告丢失，不影响运行 |

---

## 增量补录（v3.6.x ～ v3.8.1）

> 以下文件在 v3.5.41 之后新增，补录至本清单。

### 数据采集（v3.6.x 新增）

| 文件 | 职责 | 数据输出 |
|:---|:---|:---|
| `fetch_bdi.py` | 波罗的海干散货指数（本地 CSV 生成式，实时拉取不可达时读预置历史） | `data/bdi_history.csv` |
| `fetch_fao.py` | FAO 粮价指数（月档，每月 1 日触发） | `data/fao_ffpi.json` |
| `fetch_commodity_yahoo.py` | Yahoo 商品期货（WTI/Brent/铜等） | `data/commodity_yahoo.json` |
| `fetch_airtraffic_opensky.py` | OpenSky 航空流量（日档，**绝不可提频**，匿名 400 credits/日，全局请求 4 credits/次） | `data/airtraffic.json` |
| `fetch_china_meso.py` | AkShare 中国中观（PMI/PPI/工业增加值等，月档） | `data/china_meso.json` |
| `fetch_crypto.py` | CoinGecko 加密货币行情（I15 事件档） | `data/crypto.json` |
| `fetch_crypto_extra.py` | Binance/Kraken 冗余行情（I15 事件档） | `data/crypto_extra.json` |
| `fetch_earthquake.py` | USGS 地震数据（I15 事件档，喂 seismic_risk） | `data/earthquake.json` |
| `fetch_energy.py` | UK Carbon/NESO/NREL 能源电网（日档，喂 energy_grid_risk） | `data/energy.json` |
| `fetch_energy_eia.py` | EIA 能源数据（日档） | `data/energy_eia.json` |
| `fetch_hdx.py` | HDX 人道危机数据（日档/事件档） | `data/hdx.json` |
| `fetch_sanctions.py` | OpenSanctions 制裁名单 bulk（日档） | `data/sanctions.json` |
| `fetch_fx.py` | Frankfurter/ECB 汇率（日档） | `data/fx.json` |
| `fetch_world_macro.py` | World Bank + SotW 宏观数据（日档） | `data/world_macro.json` |
| `fetch_gdelt_geo.py` | GDELT 地理事件点 feed（I15 增量拉取，产出 news_geo.jsonl + news_geo_clusters.json，**v3.8.0 新增**）| `data/news_geo.jsonl`, `data/news_geo_clusters.json` |
| `fetch_defense_rss.py` | 防务/军事 RSS（Al Jazeera/Defense One/WotR，日档，喂 narrative_chunks） | 写 narrative_chunks 表 |
| `fetch_firms.py` | NASA FIRMS 火点数据（日档，**直连替代 crucix**） | `data/firms_fire.json` |
| `fetch_news.py` | MarketAux/Currents/Sugra 金融新闻 API（日档，需 API Key） | `data/news_risk.json` |

### 新架构核心模块（v3.7.0 天玑层，v3.8.0 契约层）

| 文件 | 职责 |
|:---|:---|
| `tianji_db.py` | 天玑数据库 schema + CRUD（predictions/reasoning_trace/narrative_chunks/weight_update_log 四张表）⚠️ **v3.8.13 已迁出 macro-ji**（`macro-ji/tianji_db.py`，容器 macro-scan-tianji-1） |
| `narrative_processor.py` | 叙事预处理：11维叙事桶，staleness 衰减，天璇取用接口 |
| `slow_variables.py` | 三个慢变量（IRP/UCRI/GCI），月频计算；v3.8.3 新增：权重从 grv_weights.yaml 读取、cron 幂等保护、manual_score 降级修复 |
| `startup_checks.py` | 天枢启动完整性校验（v3.8.3 新增）：source_dimension_map 遗漏映射阻断启动；scheduler.py main() 第一行调用 |
| `brier_calc.py` | Brier Score / BSS / 锐度计算（v3.8.3 新增）：供天玑 V1 月度验证调用；含 score_grv_prediction() GRV 方向预测专用验证 |
| `tianji_verifier.py` | 月度验证运行器：Brier/BSS/锐度三指标 ⚠️ **v3.8.13 已迁出 macro-ji**（`macro-ji/tianji_verifier.py`，容器 macro-scan-tianji-1） |
| `weight_matrix.py` | GRV 权重矩阵读写（grv_weights.yaml），玉衡审批，双层 clip 约束 ⚠️ **v3.8.13 已迁出 macro-ji**（`macro-ji/weight_matrix.py`，容器 macro-scan-tianji-1） |
| `observability.py` | 调度器健康心跳（每30秒写 `.scheduler_heartbeat`，任务计数写 observability_*.json）|
| `contracts.py` | **I1 Pydantic 数据契约**（v3.8.0 新增）：ValueStatus 枚举、IndicatorPoint/IndicatorEnvelope、UsagePolicy 白名单、39 个 selftest 断言 |
| `compute_probit.py` | L3 衰退概率：Estrella-Trubin 2006 固定系数 probit，T10Y3M 口径（v3.8.0 新增）|
| `gdelt_country_map.py` | GDELT FIPS→ISO 国家码映射，从 fetch_gdelt_geo 拆出（v3.8.0 新增）|
| `write_tianji_trigger.py` | 天玑 T2 触发文件写入（原子写 tmp→rename，幂等 batch_id；scheduler 0942 每月1日执行）（v3.8.13 新建）|
| `news_geo_feed.py` | P3-A 新闻坐标（spaCy NER + gdelt_geo_cache，07:15 执行；输出含顶层 `updated` 契约）（v3.8.1 新增，v3.8.15 契约对齐）|
| `control_server.py` | **A3a 控制面板**：HTTP REST :8900（FastAPI + uvicorn），rerun 白名单限 fetcher 名防路径遍历，`_scheduler_alive()` 真实健康探测（mtime+heartbeat+/proc）（v3.8.13 上线）|

### GED 数据管道（v3.8.0 新增）

| 文件 | 职责 |
|:---|:---|
| `ged_analysis.py` | UCDP GED 武装冲突数据分析（country×year×type 聚合）|
| `ged_codebook_extract.py` | UCDP GED codebook PDF 解析提取器（依赖 pypdf）|
| `etl_ged.py` | GED ETL 管道：清洗→聚合→三质量闸门（年度冻结快照，硬禁止被日更路径读取）|

### 配置文件（v3.7.0 新增）

| 文件 | 职责 |
|:---|:---|
| `config/grv_weights.yaml` | GRV 权重矩阵（14源×68情景），Claude 初始值，月度 Brier 验证后自动反哺 |
| `config/source_dimension_map.yaml` | 数据源→GRV维度映射（narrative_processor.py 读取）|

