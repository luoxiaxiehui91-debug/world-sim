# macro-scan（天枢）— Agent 工作指南

## 项目概览

世界推演系统观测层（天枢）：全球宏观情报自动采集 + LLM分析推演 + 地缘风险向量引擎，运行在 NAS Docker 容器中。

**当前版本**：v3.8.15（2026-08-05）
**主要变更**：
- v3.8.15（08-05）：开阳全链路时间审计 6 修复（FRED manifest 孤儿复活 / news 假时刻 / FCI 拉取闸 / sim_trigger `triggered` 字段 / news_geo `updated` 契约 / freshness `fresh`+`lag_days` 语义）
- v3.8.14（08-05）：`market_quotes` 0630 日频 → I15（整合导出提频，零外部请求）；kaiyang 前端 parseTs/fmtRelative 时区语义修复
- v3.8.13（08-04）：**天玑三内核（tianji_db/tianji_verifier/weight_matrix）迁出 macro-ji 独立容器**（macro-scan-tianji-1，镜像 macro-tianji:latest）；`control_server.py` :8900 上线（A3a HTTP REST）；`fred_freshness.py`/`write_tianji_trigger.py` 新建；scheduler 删 tianji_verify/weight_health job，新增 11 job（compute_fci 0535 / fred_freshness 0540 / compute_probit 0540 / tianji_trigger 0942 / firms 0908 / narrative_proc 0710 / defense_rss 0712 / news_geo_feed 0715 / slow_vars 0935 / spacetrack 0615 / market_quotes I15）；FRED 恢复至 48 CSV + manifest.json；compute_fci.py 源码重建（pycdc 反编译）
**运维参考**：`世界推演系统_人类说明文档.md`  
**变更日志**：`TuiYan_CHANGELOG.md`（改前必读，改后必追加）

**AI 阅读路径（按需读取）：**

| 文件 | 内容 | 何时读 |
|:-----|:-----|:-------|
| `TuiYan_CHANGELOG.md` | 所有变更历史 | **每次 session 必读**（了解最新状态）|
| `INDEX.md` | 运行状态：调度任务/数据管道/LLM链/ntfy指令/路线图 | 需要查运行细节时 |
| `世界推演系统_人类说明文档.md` | 使用与维护手册 | 需要了解操作流程时 |
| `docs/FILE_MANIFEST.md` | 各 py 文件职责 + 挂载路径 + 修改影响 | 不确定改哪个文件时 |
| `docs/采集频率矩阵.md` | 逐源频率决策矩阵（安全水位50%、tier定义） | 涉及调度频率调整时 |
| `docs/archive/a3a_control_api_design.md` | A3a 控制 API 协议（**现役 HTTP REST :8900**，v0.2：契约/白名单/健康探测） | 涉及控制API改动时 |
| `docs/a3a_system_design.md` | A3a 系统设计（❌ 未采纳：文件投递替代 HTTP，未实施，仅历史参考） | 参考历史决策时 |
| `docs/archive/知识库扩展方案.md` | 知识库扩展方案（v1+v2合并版，已实施完成）| 涉及知识库改动时（历史参考）|
| `docs/archive/社会信号扩展方案.md` | 信号扩展设计（R07/R09/R10，已实施完成）| 涉及弱信号/规则改动时（历史参考）|
| `docs/archive/假设推演功能设计方案.md` | 假设推演完整设计（H0-H12工作流，已实施完成）| 涉及假设推演改动时（历史参考）|
| `docs/archive/地缘推演增强方案.md` | GRV向量格式与地缘推演设计（已实施完成）| 涉及 GRV / geo_risk_vector.py 改动时（历史参考）|

---

## 目录结构

```
macro-scan/               ← 本地工作目录（S:\world-sim\macro-scan\，git 仓库子目录）
├── 核心代码/                 ← Python 源码（容器内挂载为 /app）
├── 知识库/财经知识库/         ← 人工维护的分析框架、历史案例、知识库文档
├── docs/                     ← 文档（设计方案、操作日志、runbooks；分析报告不在git里）
├── Dockerfile                ← 改动需重建镜像
├── entrypoint.sh             ← 改动需重建镜像，必须无 BOM
├── docker-compose.example.yml ← 模板；docker-compose.yml 在 .gitignore 中
├── requirements.txt
├── system_prompt.md          ← LLM 分析框架（热挂载，直接编辑即生效）
├── crontab                   ← 容器内 cron（备用；主调度用 scheduler.py）
├── TuiYan_CHANGELOG.md       ← 变更日志
├── INDEX.md                  ← 系统状态/任务/数据管道索引（只读）
└── VERSION                   ← 语义化版本号 (MAJOR.MINOR.PATCH)
```

**不在 git 里的运行时目录**（.gitignore 排除）：
- `data/` — FRED历史/（RAG向量索引已迁 worldsim-pg，chroma_db 已退役）/news.db 等运行时数据（E0-C 起读全 PG，news.db 冻结待 P6 删）
- `logs/` — 各任务日志
- `docs/分析报告/` — 容器每日自动生成
- `docs/新闻库/` — 容器每日自动生成

---

## 路径架构（关键约束）

容器内路径通过 `OPENCLAW_WORKSPACE=/workspace` 统一解析：

| 宿主机路径 | 容器内路径 | 说明 |
|:---|:---|:---|
| `核心代码/` | `/app` | 源码热挂载，entrypoint.sh cd /app 执行 |
| `data/` | `/workspace/data` | 运行时数据 |
| `docs/` | `/workspace/docs` | 报告输出 |
| `logs/` | `/var/log/macro-scan` | 日志 |
| `知识库/` | `/workspace/知识库` | 知识库只读 |
| `config/` | `/workspace/config` | 权重矩阵/信源映射/prior（v3.7.0新增） |

**红线**：
1. `核心代码/` 里的 .py 文件全部同级平铺——不能分子目录，所有 `import` 和 subprocess 调用都依赖同级路径
2. `核心代码/scorer.py` 的 `CRISIS_CSV` 常量硬编码了 `02_核心变量因果链/历史情景_量化指标.csv`——改该目录名时必须同步修改此常量
3. docker-compose 的5条 volume 挂载不能少（v3.7.0 新增 config/ 挂载）
4. 配置只从 `optim_config.py` 读取——`KEY_INDICATORS`/路径常量/阈值均在此，不在其他模块重复定义
5. 弱信号配置只从 `alert_config.py` 读取——`ALERT_KEYWORDS`/`_WATCH_COUNTRIES`/`_ACTOR_*` 在此，不在 `scan_weak_signals.py` 定义
6. 推演类型映射只从 `hypothesis_config.py` 读取——`DIM_MAP` 在此，不在 `hypothesis_engine.py` 函数内定义

---

## 修改工作流

### 修改源码（核心代码/*.py）

```bash
# 直接编辑 S:\world-sim\macro-scan\核心代码\xxx.py（热挂载，容器内即时生效）
# 改完后追加 CHANGELOG，bump VERSION（PATCH）
```

### 修改需要重建镜像的文件

只有 `Dockerfile` 和 `entrypoint.sh` 需要重建：

```bash
ssh TSX@192.168.31.108
cd /vol2/1000/software/macro-scan
docker build -t macro-scan:v<新版本> .
# 更新 docker-compose.yml image 字段
docker compose up -d
```

### 修改环境变量

```bash
# 编辑 /vol2/1000/software/macro-scan/docker-compose.yml（NAS上，不在git里）
docker compose up -d --force-recreate  # restart 不重新注入 env
```

### push 到 GitHub

```bash
# 走 NAS 代理（在源码区 S:\world-sim\macro-scan\ 执行）
git -C /s/world-sim -c http.proxy=http://192.168.31.108:7890 push origin main
# 或 NAS 上直接 push（token 在 /vol2/1000/software/KEY/github token.txt）
```

---

## 维护铁律

1. **改前必读** `TuiYan_CHANGELOG.md`（了解最新状态）
2. **改后必追加** `TuiYan_CHANGELOG.md` → bump `VERSION` → 按联动矩阵更新对应文档 → 版本变更时同步更新 `S:\docs\INDEX.md` 版本状态行
3. **绝对不要** `git rm`（不加 `--cached`）知识库或 data 下的文件
4. **绝对不要** 把 `核心代码/` 内的 .py 分子目录
5. **ntfy 推送强制直连**，不走代理
6. `entrypoint.sh` 必须无 UTF-8 BOM
7. **只在源码区改代码**（`S:\world-sim\macro-scan\`），改完验证后再推 NAS 和 GitHub

### 改代码后必须同步的文档

> **任务开始时**：用 TodoWrite 逐项列出本次涉及的每个文档更新目标（每个文件一条），不在收尾时回想。

**（改了左边 → 必须同时更新右边）**

| 改了什么 | 必须同时更新 |
|:---|:---|
| 任何 `核心代码/*.py` | `TuiYan_CHANGELOG.md` + `VERSION` |
| `VERSION` 变更时（无论何种改动触发）| `S:\docs\INDEX.md` 版本状态行（版本号 + 日期 + 一行摘要）|
| `VERSION` 变更时（无论何种改动触发）| `世界推演系统_人类说明文档.md`（文件头版本号 + 第一节"当前能力"节 + 九、当前状态表）|
| `VERSION` 变更时（无论何种改动触发）| `S:\world-sim\docs\overview.md` 头部版本行（`macro-scan vX.Y.Z`）+ 架构图版本号 |
| `VERSION` 变更时（无论何种改动触发）| `macro-scan/INDEX.md` 头部版本号 |
| `核心代码/scheduler.py` | + `INDEX.md`（运行 `gen_docs.py --target scheduler` 刷新）|
| `核心代码/hybrid_llm.py` | + `INDEX.md`（LLM调用链表手动更新）|
| `核心代码/ntfy_listener.py` | + `INDEX.md`（运行 `gen_docs.py --target ntfy` 刷新）|
| `核心代码/geo_risk_vector.py` | + `docs/archive/地缘推演增强方案.md`（GRV向量格式节，历史参考）+ `世界推演系统_人类说明文档.md` |
| `核心代码/regime_detector.py` | + `INDEX.md`（宏观体制判断规则表）|
| `核心代码/hypothesis_engine.py` 或 `hypothesis_config.py` | + `docs/archive/假设推演功能设计方案.md`（假设推演工作流节，历史参考）|
| `核心代码/scorer.py` | + `AGENTS.md`（路径架构节 CRISIS_CSV 常量）|
| `核心代码/situation_tracker.py` 或 `situation_detector.py` | + `世界推演系统_人类说明文档.md` |
| 新增或删除 `核心代码/*.py` | + `FILE_MANIFEST.md`（运行 `gen_docs.py --target manifest` 刷新）|
| `Dockerfile` 或 `entrypoint.sh` | + `INDEX.md`（活跃容器表）|
| `README.md`（路径/版本/结构变更）| + `世界推演系统_人类说明文档.md`（五、文件位置表）|


**pre-commit 会自动拦截**：commit 时如果改了代码但联动文档未 staged，会打印具体提示并阻止提交。

### 首次接手项目

```bash
pip install pre-commit
pre-commit install   # 在源码区 S:\world-sim\macro-scan\ 执行一次即可
```

---

## 版本号规范

`MAJOR.MINOR.PATCH`
- PATCH：bug fix、配置调整、文档更新
- MINOR：新增功能模块、新数据源
- MAJOR：架构重大变更

打 tag：`git tag -a vX.Y.Z -m '说明'` → push `--tags`

---

## 新 session 快速继续

> 如在 monorepo 中工作，先读根目录 `../AGENTS.md`（系统全貌 + 阅读路径入口）。

```
读 AGENTS.md（本文件）→ 读 TuiYan_CHANGELOG.md（最新变更）→ 按需读 INDEX.md（运行状态）
→ 告知当前版本和最新状态，然后开始工作。
```

---

## 部署服务（NAS 192.168.31.108）

| 服务 | 地址 | 说明 |
|:-----|:-----|:-----|
| macro-scan 主容器 | :8899 (Web UI) / :8900 (Control API) | Python 3.11-slim；镜像 macro-scan:v7；:8900 由 `control_server.py` 提供（A3a HTTP REST，白名单限 fetcher 名防路径遍历） |
| tianji（macro-ji） | 无端口 | 天玑独立容器 `macro-scan-tianji-1`（镜像 macro-tianji:latest）；tianji_db/tianji_verifier/weight_matrix 已迁出；触发机制 = T2 共享触发文件（scheduler 写 trigger → watchdog 轮询） |
| mihomo | :7890/:9090 | 出站代理，**仅 FRED 使用**；ntfy/akshare 强制直连 |
| crucix | :3117 | ~~英文地缘新闻+多源情报（FIRMS/EIA/GDELT等30源）~~ **已退场（08-12 G1 停容器）**，仅历史参考 |
| rsshub | :12000 | 中文财经 RSS（财新/第一财经/华尔街见闻/东方财富研报）|

> ⚠️ Ollama（192.168.31.56）已停用。LLM 降级链：MiniMax-M3 → MiMo v2.5 Pro → SiliconFlow Qwen3.5-27B → 纯数据报告
> **08-16 LLM 统一配置**：`核心代码/llm_usage.py` 静态清单 6 使用点（translate_titles / openai_compat / rag_embedding / sim_mc / sim_narrative / sim_minimax）× 4 平台（mimo / siliconflow / minimax / openai），运行时配置 `data/llm_config.json`（开阳控制台「LLM 配置」面板读写，`GET/PUT /api/v1/control/llm-usage`）。**配置优先于 env/常量**；天璇读共享文件。翻译模型 mimo-v2.5（`fetch_news_titles.py` 走 `usage="translate_titles"`）；RAG 嵌入 `rag_engine.py` 走 `resolve_embedding()`（bge-m3）。改 `llm_usage.py`/`hybrid_llm.py` 后须重启 control_server（:8900）并 curl 验证新路由生效。

---

## 环境变量（docker-compose.yml，NAS上）

```
FRED_API_KEY=<见 S:\macro-scan\key.txt>
OUTBOUND_PROXY=http://192.168.31.108:7890    # 仅FRED使用
NTFY_TOPIC=***REMOVED***
NTFY_CMD_TOPIC=***REMOVED***
NTFY_CMD_SECRET=1900
RSSHUB_URL=http://192.168.31.108:12000
OPENCLAW_WORKSPACE=/workspace
TZ=Asia/Shanghai
RUN_ON_START=true
USE_EXTERNAL_LLM=1                            # 0=直接调SiliconFlow
OPENAI_COMPAT_URL=https://token-plan-cn.xiaomimimo.com/v1  # MiMo端点
# OPENAI_COMPAT_KEY / OPENAI_COMPAT_MODEL / SILICONFLOW_API_KEY 在 S:\macro-scan\key.txt
# MINIMAX_API_KEY / MINIMAX_BASE_URL 同上
CRUCIX_APIKEY=...                             # key.txt
```

---

## 与 macro-sim 的数据接口契约

macro-scan 是写入方，macro-sim 是只读消费方。容器内挂载路径：`/vol2/1000/software/macro-scan/data` → `/app/macro_data:ro`。

**格式变更规则：任何人改动下列文件的字段或枚举，必须同时更新 macro-scan/AGENTS.md 和 macro-sim/AGENTS.md 的本契约节。**

**接口变更三步走：**
1. 同时改两个 AGENTS.md 的本节（含版本兼容表）
2. 两个项目 CHANGELOG 各追加一条（注明接口 schema 版本号变化）
3. 部署顺序：**先升 macro-scan** → 验证 `data/grv_latest.json` 和 `data/news_export.json` 输出 → **再升 macro-sim**

**版本兼容表：**

| macro-scan | macro-sim | 接口 schema |
|:-----------|:----------|:------------|
| v3.8.5+   | v2.0.17+   | grv v1.0 / news v1.0 |

---

### `data/grv_latest.json`

由 `核心代码/geo_risk_vector.py` 每日 06:10 写入（原子写，先写 `.tmp` 再 `os.replace`）。

⚠️ **v3.6.4 起新增 sanctions_risk / seismic_risk / energy_grid_risk，v3.7.0 起 social_stress / cultural_friction，v3.8.x 起 4 个 GDELT 国别推导维度（south_china_sea / korean_peninsula / india_pacific / global_south）。GRV 现为 16 风险维度 + 1 汇总（global_composite）。**

```json
{
  "_schema_version":    "1.0",
  "taiwan_strait":      52.7,
  "us_china_strategic": 48.0,
  "russia_europe":      41.9,
  "middle_east_energy": 64.0,
  "global_composite":   75.4,
  "climate_risk":       0.0,
  "disaster_risk":      37.0,
  "sanctions_risk":     82.7,
  "seismic_risk":       100.0,
  "energy_grid_risk":   6.2,
  "japan_monetary":     48.5,
  "updated":            "2026-07-29T10:53:01",
  "gdelt_updated":      "2026-07-28T22:07:22",
  "gpr_twn_raw":        0.18,
  "gpr_twn_date":       "2026-06-01",
  "source_quality":     "gdelt+gpr"
}
```

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| `_schema_version` | string | 接口版本号，当前 `"1.0"`。macro-sim 启动时校验此字段，不一致则拒绝启动 |
| `taiwan_strait` / `us_china_strategic` / `russia_europe` / `middle_east_energy` | float 0–100 | GRV 基础四维度，必须字段，null 表示数据源暂缺 |
| `global_composite` | float 0–100 | **汇总维度**（GPR×0.85 + japan_monetary×0.15），macro-sim 主读字段 |
| `climate_risk` / `disaster_risk` / `sanctions_risk` / `seismic_risk` / `energy_grid_risk` / `japan_monetary` / `social_stress` / `cultural_friction` | float 0–100 \| null | 扩展维度。`sanctions_risk`=OpenSanctions 国别暴露聚合；`seismic_risk`=USGS 地震压力；`energy_grid_risk`=commodity_yahoo 能源价（NG2-8 / Brent/WTI 50-110）优先，降级 UK Carbon Intensity；`japan_monetary`=USD/JPY×0.5+JGB 3M收益率变速×0.5；`social_stress`/`cultural_friction`=gdelt_scores 聚合（公式见 `config/causal_assumptions.md`）|
| `south_china_sea` / `korean_peninsula` / `india_pacific` / `global_south` | float 0–100 \| null | 推导维度（无 GPR 数据源，GDELT 国别分数加权聚合，置信度有限）|
| `updated` | ISO 8601 字符串 | 本次计算时间戳 |
| `source_quality` | `"gdelt+gpr"` \| `"gdelt_only"` \| `"gpr_only"` \| `"stub"` | 数据来源质量标记 |

macro-sim 读取字段：`global_composite`（映射为仿真 `grv`）、`middle_east_energy` + `taiwan_strait`（合成 `grv_energy`）、`russia_europe` + `taiwan_strait`（合成 `grv_military`）、`us_china_strategic`（映射为 `grv_trade`）。

---

### `data/grv_history.jsonl`

由 `geo_risk_vector.py` 每日 06:10 追加（日期去重，同天只写一条）。每行格式与 `grv_latest.json` 相同（含 `japan_monetary`）。macro-sim 读取时按时间戳回溯 6 个月作为 baseline（注意：2026-07 前为月频，2026-07 起为日频，应用日期范围而非行偏移查找基线）。

---

### `data/fred_history/*.csv`

由 `核心代码/fetch_fred_history.py` 每日 05:30 更新。格式：

```
date,value
2026-06-01,18.3
2026-06-02,.
```

- `value` 字段可为 `.`（FRED 缺失值标记），读取时需跳过
- macro-sim 读取的系列：`T10Y2Y.csv`、`BAA10Y.csv`、`DFF.csv`

---

### `data/news_export.json`

由 `核心代码/news_exporter.py` 每日 07:05 写入。

```json
{
  "_schema_version": "1.0",
  "exported_at": "2026-07-08T07:05:00",
  "articles": [
    {
      "title":    "Oil prices surge on Strait of Hormuz tensions",
      "category": "energy",
      "date":     "2026-07-08"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| `_schema_version` | string | 接口版本号，当前 `"1.0"`。macro-sim 读取时校验此字段 |
| `exported_at` | ISO 8601 字符串 | 导出时间戳 |
| `articles[].title` | string | 文章标题 |
| `articles[].category` | string | 枚举见下表，**不在枚举内的类别不会出现** |
| `articles[].date` | `YYYY-MM-DD` | 从 `published_at` 规范化，兼容 ISO 和 RFC 格式 |

**category 枚举（来自 `news_exporter.py` CATEGORY_MAP）：**

| 枚举值 | 对应 DB 类别 |
|:-------|:------------|
| `geopolitics` | 地缘升级、社会政治危机、宗教族群冲突、文化贸易摩擦 |
| `energy` | 能源政治 |
| `trade` | 战略矿产、科技竞争 |
| `finance` | 信用风险、流动性危机 |
| `macro` | 衰退信号、通胀失控、自然灾害 |
| `monetary` | 日元套利 |

**注意**：macro-sim `load_from_macro_scan()` 的 news.db fallback 路径过滤的 category 列表不含 `trade`，直读 DB 时会漏掉战略矿产/科技竞争类新闻。macro-sim v0.3.1 已在 fallback SQL 补充 `trade`，两条路径现在枚举一致。

最多 40 条，7 天窗口，按 `published_at` 倒序。

---

### `data/news.db`（SQLite，macro-sim 直读 fallback）
> ⚠ E0-C（08-13）后 news.db 冻结（天枢读全 PG / 写 PG-only）。macro-sim 此 fallback 若触发将读到冻结旧数据——主路径 news_export.json（由 PG 产出）不受影响；天璇侧 fallback 迁 PG 列入 P6 后待办。

macro-sim 在 `news_export.json` 不存在时 fallback 直读，查询：

```sql
SELECT a.title
FROM articles a
JOIN article_categories ac ON a.id = ac.article_id
WHERE a.published_at > datetime('now', '-7 days')
  AND ac.category IN ('geopolitics','finance','macro','energy','monetary','trade')
GROUP BY a.id
ORDER BY a.published_at DESC
LIMIT 40
```

category 字段存储英文标签（与 news_export.json 枚举一致）。

---

### `data/sim_trigger.json`（v3.5.34 已实现）

macro-scan 在 `grv_threshold.py` 检测到 GRV 告警时（台海 ≥68 或单日涨幅 ≥6）写入，触发 macro-sim daemon 执行一次仿真（`_write_sim_trigger()` 原子写入）。

**格式：**
```json
{
  "level": 3,
  "event": "GRV告警",
  "triggered_at": "2026-07-13T08:00:00+00:00"
}
```

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| `level` | int 1–3 | 风险等级：1=低/2=中/3=高 |
| `event` | string | 触发摘要（最多200字符） |
| `triggered_at` | string | ISO 8601 UTC 时间戳，写入时刻（`datetime.now(timezone.utc).isoformat()`） |

macro-sim daemon 每分钟轮询此文件，检测到后立即启动仿真，完成后删除该文件。
