# 知识库搭建指南（KB_SETUP）

> 本仓库开源的是**框架与逻辑**：数据采集、指标计算、RAG 检索、蒙特卡洛推演、报告生成。
> **知识库（研究内容）不在仓库内**，需要你自己建立——本指南说明怎么建。

## 一、为什么要自己建知识库

这套系统的价值来自「框架 + 知识库」的结合：

| 部分 | 内容 | 是否开源 |
|---|---|---|
| **框架** | 采集/计算/检索/推演/生成的代码 | ✅ 仓库内 |
| **知识库** | 指标体系、因果链、历史案例、分析框架、专题研究 | ❌ 需自建 |

知识库外置有三个理由：

1. **版权清晰**——第三方内容（研报、付费数据）不会随仓库分发
2. **内容自适**——你的研究关注点与别人不同，各建各库
3. **仓库轻量**——避免把 GB 级数据塞进 git 历史

## 二、快速开始

```bash
# 在仓库根目录执行，生成示例骨架
python3 scripts/init_kb.py

# 查看将生成哪些文件（不实际写入）
python3 scripts/init_kb.py --list

# 生成到其他位置
python3 scripts/init_kb.py --dest /path/to/my_kb
```

生成后按第三、四节替换为你自己的内容。

**⚠️ 生成的全部是示例/占位内容，请勿直接用于生产判断。**

## 三、目录约定

```
知识库/
├── political_calendar.yaml            # 政治/宏观日历
└── 财经知识库/                         # ← RAG 索引范围
    ├── 02_核心变量因果链/               # 因果链、历史情景、校准参数
    ├── 04_分析框架/                     # 分析框架、传导路径
    ├── 专题报告/                        # 专题研究（RAG 主要来源）
    ├── 15_国际形势/                     # 国际形势观察
    ├── 04_跨国联动矩阵/                 # 跨国传导系数
    └── 中国/                            # 分经济体研究
```

`财经知识库/` 下的子目录**可按需增减**；代码按「文件名约定」而非目录名读取，只有少数文件是硬约定的（见下表）。

## 四、文件格式要求

### 4.1 数据文件（被代码直接读取）

| 文件 | 读取方 | 格式要求 |
|---|---|---|
| `political_calendar.yaml` | `daily_narrative.py`、`weekly_synthesis.py` | `events:` 列表，每项含 `date`(YYYY-MM-DD 或 YYYY-MM-xx) / `name` / `category` / `importance` / `notes` |
| `财经知识库/02_核心变量因果链/历史情景_量化指标.csv` | `scorer.py`、`calibrate_mc.py` | **21 列，列顺序不可变**（按位置读取）。首行表头，其后每行一个历史情景 |
| `财经知识库/02_核心变量因果链/波动率校准参数.json` | `mc_engine.py`、`monte_carlo_v2.py` | 形如 `{"<FRED代码>": {name, type, full_sample_vol, full_mean_annual, normal_vol, crisis_vol, crisis_vol_ratio, current_vol, current_vol_pct}, "_mc_calibration": {...}}` |
| `财经知识库/02_核心变量因果链/地缘事件日志.json` | `run_macro_analysis.py`、`optim_config.py` | `{"meta": {...}, "schema": {...}, "events": [{id, date, event, summary, key_signals, risk_impact, transmission_paths, active}]}` |
| `财经知识库/04_分析框架/propagation_paths.yaml` | `hypothesis_engine.py`（天玑） | 列表，每项含 `id` / `scenario_type` / `subtype` / `label` / `calibration_score` / `data_quality` / `causal_chain`（步骤含 `step`/`event`/`lag_days`/`magnitude`/`confidence`） |

CSV 的 21 列顺序（**不可改动**）：

```
crisis, start_date, end_date, type, severity, gdp_peak_trough_pct, unemp_peak_pct,
sp500_drawdown_pct, pct_10y_trough, policy_key_rate_cut, policy_qe, recovery_years,
oil_price_change_pct, inflation_peak_pct, credit_spread_peak_bp, yield_curve_min_pct,
policy_response_months, key_lessons, crisis_category, taiwan_strait_relevance, vix_peak
```

### 4.2 研究文档（被 RAG 索引）

**只有 `.md` 文件会进入向量索引**（`rag_engine.py`）。索引时跳过：

- 文件名：`README.md`、`数据字典.md`
- 文件名前缀：`00_知识库`、`00_快速参考`、`README`
- 目录：`_update_tmp`、`__pycache__`、`_raw`、`07_分析报告`

所以：**把研究结论写进 `.md`，用 README 做目录说明。**

## 五、指定知识库位置

默认路径是 `<项目根>/知识库`（容器内即 `/workspace/知识库`）。若放在别处，设置环境变量：

```bash
# .env
KB_ROOT=/mnt/my_knowledge_base
```

代码读取顺序：`KB_ROOT` 环境变量 → 默认路径。

## 六、构建 RAG 索引

知识库内容就绪后，建立向量索引（需要 `SILICONFLOW_API_KEY`，使用 `BAAI/bge-m3` 嵌入模型）：

```bash
docker exec macro-scan-macro-scan-1 python3 build_rag_index.py
```

- 索引存放在 PostgreSQL 的 `rag.embeddings` 表（需 pgvector 扩展）
- 脚本会先清空再原子重建，可重复执行
- 知识库有较大更新后重跑即可，**无需重启容器**

## 七、知识库缺失时会怎样

代码对知识库缺失做了降级处理，**不会崩溃**，但相关能力下降：

| 缺失内容 | 影响 |
|---|---|
| 全部知识库 | RAG 检索返回空 → LLM 分析缺少背景资料；历史危机匹配跳过；波动率校准回退默认参数 |
| `political_calendar.yaml` | 叙事报告中的政治日历段落为空 |
| `propagation_paths.yaml` | 天玑的假设评估缺少传导路径注入 |

判定某个功能是否降级，看对应日志是否有「未找到 / 不存在 / fallback」字样。

## 八、维护建议

- **不要提交知识库到 git**——`.gitignore` 已排除 `macro-scan/知识库/`
- **版本管理自己做**——知识库是研究资产，建议用独立仓库或快照工具管理
- **定期校准确认**——`波动率校准参数.json`、`历史情景_量化指标.csv` 会直接影响推演结果，数据更新后应重新标定

## 九、相关文件

| 文件 | 说明 |
|---|---|
| `scripts/init_kb.py` | 骨架生成脚本 |
| `macro-scan/核心代码/rag_engine.py` | RAG 索引与检索实现 |
| `macro-scan/核心代码/build_rag_index.py` | 索引构建入口 |
| `macro-scan/核心代码/scorer.py` | 历史情景匹配（读 CSV） |
