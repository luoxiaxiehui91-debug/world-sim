# FILE_MANIFEST — 文件清单与职责说明

> 版本：v3.5.41 | 最后更新：2026-07-10
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

> 所有 .py 文件**同级平铺**，不能分子目录。import 依赖同级路径，entrypoint.sh 以 `python3 xxx.py` 调用。

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
| `fetch_fred_history.py` | FRED 29个宏观序列 | `data/fred_history/*.csv` |
| `fetch_gpr.py` | GPR 地缘风险指数（7系列） | `data/fred_history/gpr_*.csv` |
| `fetch_china_data.py` | 中国宏观数据（AkShare） | `data/china_history/` |
| `fetch_china_data_akshare.py` | AkShare 数据抓取工具函数 | 被 run_macro_analysis 调用 |
| `fetch_disaster_signals.py` | 灾难/极端天气信号 | `data/disaster_signals.json` |
| `fetch_climate_signals.py` | 气候变量 | 月度更新 |
| `fetch_rss_news.py` | RSS 新闻抓取 | 被 scan_weak_signals 调用 |

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
| `geo_risk_vector.py` | GRV 地缘风险向量聚合（8维：5地缘+climate+disaster+japan_monetary）；v3.5.41 修复 `compute_grv` NameError |
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
