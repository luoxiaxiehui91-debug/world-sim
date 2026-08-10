# B1：crucix 能力整合进天枢（macro-scan）对照清单

> **用途**：本清单供 **D2（crucix 独立运行过渡节奏）** 决策使用。
> **作者**：pm-b1（许清楚 / Xu）
> **类型**：调研 / 对照类，零代码改动。
> **生成日期**：2026-07-31（基于世界推演系统 sprint0 现状）
> **状态复核（2026-08-10）**：crucix 现为**独立运行过渡期共存**——`crucix-crucix-1` 容器仍 healthy
> （08-06 治理实测 30/30 sweep 通过），未退场；本清单"可退场"= 能力等价性评估（天枢已有等价 fetcher），
> **不代表 crucix 已下线**。

---

## 0. 红线与数据来源声明

### 0.1 硬红线（不可逾越）
- **crucix = AGPL-3.0**：任何修改版经网络提供服务，均须开源完整对应源码。
- **严禁读取、复制、摘抄 crucix 源码**。天枢整合 crucix 的"信息收集能力"必须 **纯重写**，零代码继承。
- crucix 与天枢处于**独立运行过渡期共存**（2026-08-10 复核 `crucix-crucix-1` 仍 healthy，30/30 sweep 通过）；天枢（macro-scan）是 **唯一数据中枢**（采集 → 落盘契约 → 开阳只读）。

### 0.2 数据来源（基于实际代码实况，不凭记忆）
| 来源 | 用途 |
|------|------|
| `采集频率矩阵.md`（主矩阵，声明"代码实况核对"） | 天枢 24 个 fetcher 完整清单、频率、限额、状态 |
| `STATUS.md` | crucix=AGPL-3.0 边界、FIRMS 已完成、B1/B2 任务定义 |
| `世界推演系统天枢/世界推演系统_信息源完整手册_20260729.md` | crucix 公开能力描述（注入信号 gscpi/nuke/sdr/air）、实时源清单、ACLED 已放弃 |

> 注：天枢 `fetch_*.py` 代码部署在 NAS，按约束 **不触碰 NAS**，故以"采集频率矩阵.md（代码实况核对版）"为权威核实源。crucix 仅参照其 **公开能力描述**，未接触其源码。

---

## 1. 天枢（macro-scan）现有 fetcher 能力盘点（24 个）

来自 `采集频率矩阵.md` 主矩阵，按编号/频率/状态列示：

| # | fetcher（函数） | 数据源 | 频率档 | 状态 |
|---|----------------|--------|--------|------|
| 1 | `fetch_fred_history` | FRED（41 序列：DGS10/DGS3MO/T10Y3M/NFCI/T5YIE 等） | 日档 | ✅ 运行 |
| 2 | `fetch_gpr` | GPR 地缘政治风险指数 | 日档 | ✅ 运行 |
| 3 | `fetch_china_data` | 中国 FRED/OECD+WB | 日档 | ✅ 运行 |
| 4 | `fetch_world_macro` | World Bank + SotW | 日档 | ✅ 运行 |
| 5 | `fetch_fx` | Frankfurter/ECB 汇率 | 日档 | ✅ 运行 |
| 6 | `fetch_crypto` | CoinGecko | 日档 | ✅ 运行 |
| 7 | `fetch_crypto_extra` | Binance/Kraken（冗余） | 日档 | ✅ 运行 |
| 8 | `fetch_sanctions` | OpenSanctions（制裁 bulk） | 日档 | ✅ 运行 |
| 9 | `fetch_earthquake` | USGS 地震 | 事件档 I15 | ✅ 运行 |
| 10 | `fetch_energy` | UK Carbon/NESO/NREL/AEMet 能源电网 | 日档 | ✅ 运行 |
| 11 | `fetch_disaster_signals` | 灾害信号 | 事件档 I30 | ✅ 运行 |
| 12 | `fetch_news` | MarketAux/Currents/Sugra 新闻 | 日档 | ✅ 运行 |
| 13 | `fetch_hdx` | HDX CKAN 人道危机 | 日档/事件档 | ✅ 运行 |
| 14 | `fetch_bdi` | BDI 波罗的海干散货（本地 CSV 生成式） | 日档 | ✅ 运行 |
| 15 | `fetch_fao` | FAO 粮价 | 日档 | ✅ 运行 |
| 16 | `fetch_commodity_yahoo` | Yahoo 商品 | 日档 | ✅ 运行 |
| 17 | `fetch_airtraffic_opensky` | OpenSky 航空 | **日档（绝不可提频）** | ✅ 运行 |
| 18 | `fetch_energy_eia` | EIA 能源 | 日档 | ✅ 运行 |
| 19 | `fetch_china_meso` | AkShare 中国中观（PMI 等） | 日档 | ✅ 运行 |
| 20 | `fetch_climate_signals` | NOAA ONI/GISS + FIRMS 气候 | 日档 | ✅ 运行 |
| 21 | `fetch_defense_rss` | Al Jazeera/Defense One/WotR 防务 RSS | 日档 | ✅ 运行 |
| 22 | `fetch_sipri_backdrop` | SIPRI 背景（本地手工） | 日档 | ✅ 运行 |
| 23 | `fetch_rss_news` | 本地 RSSHub（192.168.31.108:12000）聚合 | 日档 | ✅ 运行 |
| 24 | `fetch_firms` | **直连 NASA FIRMS**（纯重写） | 日档 | ✅ **已完成替代 crucix** |

---

## 2. crucix 能力维度 × 天枢对应 fetcher 对照清单

> 图例：✅ = 天枢已有等价 fetcher（crucix 对应维度已可独立运行，过渡期共存）｜⚠️ = 部分覆盖（间接/无专用 fetcher，需决策）｜❌ = 缺口（天枢无对应）

### 2.1 新闻 / 信号聚合
| crucix 维度 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| 新闻 Feed 聚合 | `fetch_news` (#12) + `fetch_rss_news` (#23 RSSHub) + `fetch_defense_rss` (#21) | ✅ | 三源覆盖通用新闻 + 路由聚合 + 防务垂直；crucix 新闻 Feed 维度已由天枢等价覆盖（过渡期共存） |

### 2.2 金融信号
| crucix 维度 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| 利率 / 宏观序列 | `fetch_fred_history` (#1) | ✅ | 覆盖国债收益率曲线、NFCI、通胀预期等 |
| 汇率 | `fetch_fx` (#5) | ✅ | Frankfurter/ECB，无限额顾虑 |
| 加密资产 | `fetch_crypto` (#6) + `fetch_crypto_extra` (#7) | ✅ | CoinGecko + Binance/Kraken 双冗余 |
| 商品价格 | `fetch_commodity_yahoo` (#16) + `fetch_fao` (#15) + `fetch_bdi` (#14) | ✅ | 覆盖大宗商品 / 粮价 / 航运运价 |
| 制裁名单 | `fetch_sanctions` (#8) | ✅ | OpenSanctions bulk |
| 地缘政治风险指数 (GPR) | `fetch_gpr` (#2) | ✅ | 专用 GPR 指数 |
| 能源 / 电网 | `fetch_energy` (#10) + `fetch_energy_eia` (#18) | ✅ | 含 EIA（与 crucix 内部 EIA 同源，✅ 已等价） |

### 2.3 地理 / 气候 / 灾害
| crucix 维度 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| 地震 | `fetch_earthquake` (#9, USGS) | ✅ | 事件档 I15 |
| 灾害信号 | `fetch_disaster_signals` (#11) | ✅ | 事件档 I30（GDACS 类） |
| **火点 FIRMS** | `fetch_firms` (#24) | ✅ | **清单首项锚点：纯重写直连 NASA FIRMS 已落地，crucix 退为过渡兜底** |
| 人道危机 | `fetch_hdx` (#13, HDX CKAN) | ✅ | |
| 粮价 | `fetch_fao` (#15) | ✅ | |
| 气候 / ONI 厄尔尼诺 | `fetch_climate_signals` (#20, NOAA) | ✅ | |

### 2.4 地缘政治 / 安全风险（文本 / 事件）
| crucix 维度 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| GPR 指数 | `fetch_gpr` (#2) | ✅ | 专用指数 |
| 防务 / 冲突新闻 | `fetch_defense_rss` (#21) | ✅ | Al Jazeera/Defense One/WotR |
| 军备背景 (SIPRI) | `fetch_sipri_backdrop` (#22) | ✅ | 本地手工维护 |
| GDELT 全球事件 | `fetch_gdelt_geo`（独立 fetcher，08-06 落地） | ✅ | **独立 fetcher 已落地**（scheduler 注册 gdelt_geo I15 事件档，产出 news_geo.jsonl + news_geo_clusters.json），与 RSSHub 路由互为补充 |

### 2.5 航运 / 航空
| crucix 维度 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| 航空流量 (OpenSky) | `fetch_airtraffic_opensky` (#17) | ✅ | **见 §3 B2 限额约束：绝不可提频** |
| 航运运价 (BDI) | `fetch_bdi` (#14) | ✅ | 本地 CSV 生成式，无外部限额 |

### 2.6 crucix 专有注入信号（来自信息源手册 #97-101）
| crucix 信号 | 天枢对应 | 状态 | 备注 / 独立运行动作 |
|------------|---------|------|---------------|
| `gscpi`（供应链压力） | 无专用 fetcher | ⚠️ | 部分可由 `fetch_fao`(粮供应链) + `fetch_energy`/`fetch_energy_eia`(能源供应) + `fetch_hdx`(中断) + GDELT/Defense RSS(事件) **间接覆盖**；无独立 gscpi 序列。需决策：新增 `fetch_gscpi` 或接受间接代理 |
| `nuke`（军事 / 核） | `fetch_sipri_backdrop`(#22) + `fetch_defense_rss`(#21) | ⚠️ | 部分覆盖军备/核态势；crucix `nuke` 信号无对等专用 fetcher |
| `sdr` | 无独立信号，相关宏观由 #1/#3/#4 覆盖 | ⚠️ | 特殊提款权类信号无专用 fetcher；可由 FRED/World Bank 宏观代理 |
| `air`（航空） | `fetch_airtraffic_opensky` (#17) | ✅ | 等价，受 §3 限额约束 |
| 内部 EIA / FIRMS | #18 / #24 | ✅ | 同源已等价，FIRMS 已完成替代 |
| ACLED（冲突事件） | 无 | — | **crucix 自身已放弃**（需 edu/org/gov 授权）；天枢亦无，但 **非独立运行阻塞项、非缺口** |

---

## 3. B2：OpenSky 限额核对并入（结论：绝不可提频）

> 来源：OpenSky Network API 官方文档（WebFetch 核实，2 次成功）

### 3.1 官方限额（修正粒度）
- **匿名用户：400 credits / 日**（按端点桶独立：`/states/*`、`/tracks/*`、`/flights/*`）。
- **单次信用成本**（全局 `/api/states/all`）：
  - 全局请求（无边界框）= **4 credits / 次**
  - >400 平方度 = 4｜100–400 = 3｜25–100 = 2｜≤25 或 serial-only = 1
- **时间分辨率**：匿名 10s 仅当前数据；认证用户 5s 可回溯 1h。
- **其他档位**：标准注册 4000/日｜活跃提供方 8000/日｜授权用户 14400/小时。

### 3.2 天枢现状与结论
- 天枢 `fetch_airtraffic_opensky` 使用 **全局 `/api/states/all` = 4 credits/次**。
- 当前 **日档 1 次/日 = 4 credits/日**，安全水位 ≪ 1%（远低于 400）。
- ⚠️ **若提频至事件档**（如 96 次/日）→ 384 credits/日，**逼近 400 限额 → 触发封禁风险**。
- ✅ **结论：绝不可提频。** 维持日档。
- 📌 **修正**：原"匿名 ~400 次/日"表述不准确，实为 **400 credits/日，全局请求 4 credits/次**；天枢日频 1 次仅耗 4 credits，余量极大，但提频即触顶。

### 3.3 行动项
- 采集频率矩阵 #17 维持 **日档**，标注"**绝不可提频**"（已在 §五 B 确认）。
- 频率矩阵备注补充：credits 语义（非次数），全局 `/states/all` 4 credits/次。
- 该结论并入本清单，作为 crucix 过渡期共存期间航空维度"已等价但受限额锁定"的依据。

---

## 4. 整合状态汇总

### 4.1 分档统计
- ✅ **已有等价 fetcher（crucix 对应维度可独立运行）**：新闻、利率、汇率、加密、商品、制裁、GPR、能源/EIA、地震、灾害、FIRMS(锚点)、GDELT geo、HDX、FAO、气候/ONI、GPR、防务 RSS、SIPRI、BDI、OpenSky(限频)、air
- ⚠️ **部分覆盖（需 D2 决策）**：`gscpi` 供应链压力、`nuke` 军事/核、`sdr`（GDELT 已于 08-06 独立 fetcher 落地，移出部分覆盖）
- — **非缺口非阻塞**：ACLED（crucix 已放弃）

### 4.2 关键缺口 / 部分覆盖项（供 D2 重点讨论）
| 项 | 状态 | 建议 |
|----|------|------|
| `gscpi` 供应链压力 | ⚠️ | 评估新增 `fetch_gscpi`（NY Fed 公开序列）或接受 FAO/能源/HDX/GDELT 间接代理 |
| `nuke` 军事/核 | ⚠️ | SIPRI + Defense RSS 已部分覆盖；如世界推演需核态势专信号，评估新增源 |
| GDELT 独立 fetcher | ✅ 08-06 已落地 | `fetch_gdelt_geo.py`（I15 事件档，news_geo.jsonl + news_geo_clusters.json；天枢 fetcher 实况核对） |
| `sdr` 特殊提款权 | ⚠️ | 可由 FRED/World Bank 宏观代理，优先级低 |

---

## 5. 独立运行过渡建议（供 D2 决策）

1. **FIRMS（已完成）**：`fetch_firms` 纯重写直连已落地，crucix 火点维度退为过渡兜底，可率先独立运行。
2. **新闻 / 金融 / 灾害 / 气候**：天枢已全覆盖且有等价 fetcher，**crucix 对应维度独立运行无阻塞**。
3. **航空（OpenSky）**：天枢已等价，但受匿名 400 credits/日限额锁定为日档（绝不可提频）——独立运行无影响，因天枢已独立且频率本就日档。
4. **部分覆盖项（gscpi / nuke / sdr）**：D2 需拍板是否新增专用 fetcher，或接受间接代理。若接受间接代理，则 crucix 对应维度可完全由天枢承接；若要求专用信号，则先行补齐再承接。
5. **ACLED**：非阻塞，忽略。

> **总体判断**：crucix 绝大多数"信息收集能力"天枢已通过 27 个 fetcher（实况核对）等价或覆盖；仅 `gscpi`/`nuke`/`sdr` 为部分覆盖，不构成独立运行的硬阻塞。当前 crucix 与天枢**过渡期共存**（`crucix-crucix-1` healthy，30/30 sweep 通过），D2 可按"各维度逐步独立、部分覆盖项接受间接代理"推进，或视世界推演精度需求择机补齐。
