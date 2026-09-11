# 世界推演系统 — NAS 部署说明

> **AI 工作入口**：见 [`AGENTS.md`](AGENTS.md)（含操作约束、联动矩阵、阅读路径）。  
> **Monorepo 根目录**：`<仓库根>\`，统一部署脚本见根目录 `deploy.sh`。

## 目录结构

```
<部署目录>/macro-scan/   （NAS 内部路径）
<仓库根>\macro-scan\           （本机源码路径，SMB 挂载 software 共享为 S:）
├── 核心代码/        ← Python 脚本（Docker 容器 /app，热挂载）
│   ├── run_macro_analysis.py       主入口（8步分析+假设推演分支）
│   ├── hypothesis_engine.py        假设推演引擎（M0+P0+M1+M2）
│   ├── hypothesis_config.py        推演类型映射常量（DIM_MAP，2026-06-27新增）
│   ├── scheduler.py                Python定时调度器（替代cron）
│   ├── alert_config.py             弱信号配置常量（ALERT_KEYWORDS等，2026-06-27新增）
│   ├── rag_engine.py               pgvector向量检索+TF-IDF fallback统一入口
│   ├── geo_risk_vector.py          GRV地缘风险向量聚合（M1-2）
│   ├── grv_threshold.py            GRV阈值监控（B线，fcntl原子化）
│   ├── signal_synthesizer.py       信号共振推演（C线）
│   ├── fetch_gpr.py                GPR地缘风险指数下载（M1-1）
│   ├── verify_hypothesis.py        校准闭环工具（M2-4）
│   └── ... (共48个.py + 5个.yaml)
├── 知识库/
│   └── 财经知识库/
│       ├── 02_核心变量因果链/
│       │   └── 历史情景_量化指标.csv  （41条，含地缘/社会/气候/灾害案例）
│       └── 04_分析框架/
│           ├── propagation_paths.yaml  （20条传导路径库）
│           └── ...
├── config/                 ← 权重矩阵/信源映射/prior（v3.7.0新增，必须挂载 volume）
│   ├── grv_weights.yaml        GRV信源×事件权重矩阵 + slow_variables_weights节（v3.8.3新增）
│   ├── source_dimension_map.yaml  数据源→GRV维度映射（天枢启动时校验完整性）
│   └── causal_assumptions.md   因果假设说明
├── data/
│   ├── fred_history/               FRED历史数据（32条序列含EU/JP）
│   ├── grv_latest.json             GRV地缘风险向量（每日06:10更新）
│   ├── gdelt_scores.json           GDELT地缘信号（每6h更新）
│   ├── （RAG 向量索引已迁 worldsim-pg.rag.embeddings，chroma_db 已退役 2026-08-13）
│   └── news.db                     新闻库（月度90天滚动清理）
├── docs/
├── logs/
├── Dockerfile
├── docker-compose.yml              当前镜像：macro-scan:v7
├── entrypoint.sh                   ⚠️ 改动需重建镜像，文件必须无BOM
├── requirements.txt
├── system_prompt.md                AI分析框架（热挂载，直接编辑）
├── CHANGELOG.md                    变更日志（v3.8.25 起；改前必读，改后必追加）
├── TuiYan_CHANGELOG.md             历史归档（v3.8.24 及更早）
```

## NAS Docker 启动

```bash
ssh TSX@<主机地址>   # 密码见 <你的密钥文件>

cd <部署目录>/macro-scan
docker compose up -d
```

> 首次启动会立即拉取一次 FRED + 中国数据（约5-10分钟）。正常情况下无需 `--build`，代码热挂载无需重建镜像。

## 查看状态

```bash
# 容器是否在线
docker ps

# scheduler 定时任务日志
docker exec macro-scan-macro-scan-1 tail -20 /var/log/macro-scan/scheduler.log

# 最新 GRV 地缘风险值
docker exec macro-scan-macro-scan-1 cat /workspace/data/grv_latest.json

# 分析日志
docker exec macro-scan-macro-scan-1 tail -50 /var/log/macro-scan/us_daily.log
```

## 定时任务（北京时间）

| 时间 | 任务 |
|:-----|:-----|
| 05:25 | `fetch_disaster_signals.py`（USGS实时地震） |
| 05:30 | `fetch_fred_history.py`（FRED 36个序列含小麦/玉米/青年失业率） |
| 05:40 | `fetch_gpr.py`（GPR地缘风险指数，7系列）|
| 05:45 | `fetch_china_data.py`（中国7个宏观指标） |
| 00/06/12/18 | `scan_weak_signals.py`（弱信号扫描，8路由RSS+Crucix） |
| 06:10 | `geo_risk_vector.py`（GRV向量聚合） |
| 06:1x | `fetch_gdelt_geo.py --incremental`（GDELT地理事件点，每15分，v3.8.1新增） |
| 06:30 | `situation_detector.py`（情境话题检测） |
| 07:00 | `daily_narrative.py`（今日世界摘要推送） |
| 工作日 07:30 | 中美全球快速报告 |
| 工作日 20:00/20:15 | 美国/中国深度报告 |
| 周五 20:00 | `weekly_synthesis.py`（周报） |
| 每日 21:00 | `observability.py daily_health_push`（三数字健康摘要推送，v3.8.3新增） |
| 每月1日 09:00-09:20 | 预测校验 / KB更新 / 气候 / 假设校准 / news.db清理 |

## 假设推演快速上手

```bash
ssh TSX@<主机地址>

docker exec macro-scan-macro-scan-1 python3 /app/run_macro_analysis.py \
  --hypothesis "台海军事冲突升级" --hypothesis-severity L2
```

报告保存至 `docs/分析报告/[假设]_*.md`，同时推送手机。

## SSH 连接说明

```bash
ssh -i ~/.ssh/id_ed25519 TSX@<主机地址>
# 密码备用：见 <你的密钥文件>
```

## 注意事项

- 代码热挂载：直接编辑 `<仓库根>\macro-scan\核心代码\` 下的 .py 文件，容器内即时生效，无需重建镜像
- GPR下载较慢：matteoiacoviello.com 官网服务器响应慢，timeout=300s，属正常现象
- GRV更新依赖：须先有 GPR CSV（05:40）和 GDELT 扫描（06:00），才能在 06:10 生成 GRV
- entrypoint.sh：必须无 UTF-8 BOM，改动后需 `docker build` 重建镜像

