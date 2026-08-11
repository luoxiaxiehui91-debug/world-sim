# crucix 退场论证 · Round 1 四视角产出交叉检查终稿（含 R2 复核）

> 日期：2026-08-10
> 团队：crucix-retire-arg（data-review / arch-review / qa-review / devops-review）
> 状态：**round 1 全部交卷 + R2 复核闭合**（arch v1.2 / qa R2 / data §7-9 / devops 终版）
> 性质：只读论证，未改动任何代码/配置/数据（四成员均声明）

---

## 一、产出清单（NAS，均已 scp 确认落盘）

| 视角 | 文档 | 核心内容 |
|------|------|----------|
| QA | `docs/arg-round1-qa-2026-08-10.md`（**R2，223 行**） | AC-D1-01~D6-04 + **AC-D1-05~09 新增** + 门禁 G0-G8（**G1 改**）+ 回归 M1-M9 + 风险 RSK-1~9 + OB-SDR-01~03 |
| 架构 | `docs/arg-round1-arch-2026-08-10.md`（**v1.2**） | **ADR-01~10 完整** + P0-P4 摘除顺序 + 风险矩阵 + sdr 区域规则定稿（§4.1 + ADR-10） |
| 数据 | `docs/arg-round1-data-2026-08-10.md`（**442 行，§7-9**） | 全实测替代性结论 + 基线快照 §0 + nuke 读数 §7 + sdr 接入 §8 + **SafeCast 复刻 §9** |
| 运维 | `docs/arg-round1-devops-2026-08-10.md` | 4 阶段停用方案 + 回滚 + 10 项风险 |

## 二、交叉一致性检查结果

### ✅ 一致项（多视角互证，可放心采信）

| 结论 | 互证来源 |
|------|---------|
| gscpi 是唯一"实时硬依赖"；替代源 = **NY Fed 官方 xlsx**（FRED API 实测**无** GSCPI 序列，任务书假设作废） | arch + data 独立实测互证 |
| D3（crucix 叙事映射）= **死配置**：narrative_chunks 实库 0 条 crucix_*，从未有数据流，删除对 GRV 零影响 | arch + qa 互证 |
| climate（D6）08-01 后停摆是**既有故障**（last_ok=false / climate_signals.json 停更），摘除前置 = 先恢复 job，否则误报"摘除故障" | qa G0 + devops 兜底消费证据 |
| news 链路已独立覆盖：news.db 31,039 篇无 crucix source 标记，近 30 天 13,175 篇主力全来自独立链路（fetch_rss_news 8 路由 + fetch_defense_rss 3 源 + fetch_news 3 源） | data 实测 + qa 回归方案 |
| `docker stop` = 最小风险下线：scan.log:11474（07-05）3117 Connection refused → 跳过新闻扫描 → 后续任务照常；数据全在 NAS 持久卷（14 项 rw bind mount → /vol2/1000/software/Crucix/），rm 不丢数据、秒级回滚 | devops |
| 3117 唯一消费方 = 天枢；无 crontab/systemd/其他容器引用；7890 是 NAS 出站代理非 crucix 端口 | devops |

### ⚠️ 冲突 → 已解决（arch v1.1 复核）

**1. sdr 语义（重大）→ 已定案：接入（用户拍板，arch v1.2 + ADR-04/10）**
- v1.0 arch 方案：「删映射、依赖 opensanctions」——**推断**（基于键名 crucix_sdr→sanctions_risk 映射猜测），无实证
- data 实测：sdr = **KiwiSDR 无线电接收器网络**（{total:780, online:780, zones:8 区}），不是 IMF 特别提款权、也不是制裁相关；原任务书"FRED/World Bank 替代"路线作废
- arch 复核结论：GRV **无任何维度消费 sdr 键**（sanctions_risk 由 fetch_sanctions.py / OpenSanctions 独立供给 L606-619）；sdr 唯一消费点 = data_fetcher L741 注入 + D3 死映射（实库 0 条）
- **最终形态（用户拍板采纳 arch 版）**：**接入为 narrative 弱信号**——fetch_kiwisdr.py + 独立产物 `data/sdr_summary.json`（与 `_crucix` 完全脱钩）+ json_sources/source_map 接线；**不做 GRV 数值维度**（8 区小样本噪声压倒信号，会污染 grv_history 基线）；GRV/regime/data_fetcher 零改动；独立增强项，不进 G0-G8（qa OB-SDR-01~03 观察建议）
- **sdr 区域规则定稿（ADR-10，以天枢语义为准）**：Taiwan Strait/South China Sea→taiwan_strait、Ukraine/Baltic→russia_europe、Middle East/Iran→middle_east_energy、Korean Peninsula→us_china_strategic、Sahel→global_composite 兜底；loc 关键词 + gps bbox 双层判定；验收基线 = 全局 total/online 对齐（crucix 780 / KiwiSDR 839），不要求 zone 内计数一致（crucix 边界未知）

**2. nuke 拆层 → 已翻案：SafeCast 复刻保留（data §9 + arch ADR-03/09 + qa AC-D1-04~09）**
- arch v1.0「接受空输入」→ data 实测拆两层 → 原判"6 站点辐射 CPM 无低成本开源源"作废
- **数据源挖出**：crucix 源码 `apis/sources/safecast.mjs` → SafeCast 公开 API（CC0、无 key、直连 200），容器内复刻 6 站全 MATCH → **A 层改 fetch_safecast_nuke.py 保留信号**，下游消费独立键 `snapshot["_safecast"]["nuke"]`（与 `_crucix` 解耦，P3 无二次拆除）；B 层（台海地缘）已由 GPRC_TWN + defense_rss 双重覆盖，删死映射
- **两个必知坑**：TLS 间歇证书错误（≥4 次重试+退避，RSK-8 归因判据）；**历史归档均值非实时流**（Chernobyl anom=true 是 2023-07 长期背景，latest_captured_at 必填、不作实时性断言，RSK-9）

### 📌 差异标注（不影响结论）

- crucix gscpi 现值：qa 报 1.249/0.79（历史缓存值）、data 报 **null**（08-10 实时直连）。两者均 <1.5 阈值，gscpi_warn 零触发结论不变；null 反而强化"替换 = 恢复信号"论点（crucix 侧已失效）
- 现存 bug（与 D3 独立）：`narrative_processor.ingest_from_news_db` 因 articles 表无 summary 列**恒报错**（articles 实表列：id,url,content_hash,title,source,published_at,ingested_at,country_tag,ingest_ctx_id,pub_ctx_id，SELECT summary 实测 no such column）→ news.db 31,039 篇从未进叙事桶。**arch 建议登记 ADR-08 独立待修，不随 D3 删除**（混在一起污染变更边界）；修复需 qa 补 news.db→narrative_chunks 回归用例

## 三、依赖点处置矩阵（round 1 终稿）

| 依赖点 | 定性 | 处置 | GRV 影响 | 归属阶段 |
|--------|------|------|----------|----------|
| D1/D2 gscpi | 唯一实时硬依赖 | 新增 fetch_gscpi.py（NY Fed xlsx → data/fred_history/GSCPI.csv，复用 GPR 读取模式 data_fetcher L712-725）；regime_detector 改读 indicators["GSCPI"]；阈值 1.5（标准差语义同构）沿用 | 恢复信号（现 null） | P0 双轨 / P2 切换 |
| D3 crucix 叙事映射 ×4 | 死配置（0 数据流） | 删映射 | 零 | P3 |
| D3' crucix_context prompt 注入 | 第三入口 | run_macro_analysis.py L2649-2682 删 | 零 | P2 |
| D4/D5 news 软依赖 | 独立链路已覆盖 | 随 D1-D3 摘除（RSS-only） | 小 | P1 |
| D6 climate 0910 兜底 | 既有故障 + 兜底 | 删兜底；前置恢复 climate job（QA G0 硬门禁） | 需回归 | P1 |
| sdr（KiwiSDR 无线电网络） | **用户拍板：接入**（narrative 弱信号，独立增强项） | fetch_kiwisdr.py → data/sdr_summary.json → json_sources/source_map 接线（与 `_crucix` 脱钩）；GRV/regime/data_fetcher 零改动；区域规则 ADR-10 定稿 | 零（不进 GRV） | P1 并行 / P4 后上线 |
| nuke 辐射 + 台海映射 | **SafeCast 公开 API 可复刻（CC0，无 key）** | **A 层 fetch_safecast_nuke.py 保留信号**（6 站 1:1 MATCH，独立键 `_safecast.nuke`）；B 层删死映射（已双重覆盖） | **保留**（历史归档均值，latest_captured_at 防误导） | P1（fetcher）/ P2（改读）/ P3（删死映射） |
| air 消费 | OpenSky 语义不等价 | 删消费，不强顶替 | 小 | P1 |

> **08-10 15:5x 数据实证更新（data-review §9）**：crucix nuke 数据源 = SafeCast 公开 API（`api.safecast.org/measurements.json?latitude=..&longitude=..&distance=..&limit=10`，CC0 public domain，无 auth、无 rate-limit 迹象）。容器内复刻 6 站全 MATCH（Zaporizhzhia 38.28/n25、Chernobyl 123.96/n25/anom=true、Fukushima 28.53/n25、Dimona 29.52/n25、Bushehr/Yongbyon 源空数组 null/n0）。**round1"nuke 空输入+降级登记"结论作废**。两个必知坑：① ~50% 请求间歇性 TLS 证书错误（api.safecast.org 多 IP、部分 IP 证书不匹配）→ fetcher 必须 ≥4 次重试+退避；② 数据是**历史归档均值非实时流**（captured_at：Zaporizhzhia 2023-06、Chernobyl 2023-07、Fukushima 2016、Dimona 2018）→ Chernobyl anom=true 是长期背景而非突发，输出必须保留 latest_captured_at 防误导。调度 15-60min 对齐 crucix sweep；出网直连优先 + OUTBOUND_PROXY 防御性回退。

## 四、摘除顺序与门禁衔接（round 1 终稿）

```
P0 新增 fetch_gscpi 双轨并存（crucix 与 NY Fed 并行）
P1 并行新增 3 fetcher：fetch_gscpi（P0）+ fetch_safecast_nuke + fetch_kiwisdr（同类并行）；软依赖：D6 兜底删（先恢复 climate job，QA G0）/ D5 RSS-only / air 删消费
P2 gscpi 切换（门禁重定义后，见下）+ nuke 段改读 _safecast.nuke + air 段删除
P3 死配置清理：D3 映射 / D3' crucix_context prompt / crucix 残留注入（_crucix 键整体删除，nuke/sdr 已独立无二次拆除）
P4 停用容器（devops A 观测基线 → B 摘除后观察窗 ≥48h 建议 72h → C docker stop + ≥24h 观察 → D rm + 资源回收，镜像延后 ≥1 月；B/C 硬门禁）
```

**QA 门禁**：G0 climate job 恢复硬前置 / **G1 连续 5 天替代源完整（nuke 由 safecast_nuke.json 供给：6 站结构完整+fetched_at 当日+无连续失败；sdr 已显式剔除）** / G2 gscpi_warn 桩回归（1.6→True / 1.4→False / None→False）/ G3 news 日增量 ≥300 / G4 无 _crucix 降级日志 / G5 GRV 漂移 ≤±15% / G6 weak_signal 产出 / G7 climate_signals 当日产出 / G8 全链路 last_ok。

**ADR 现状（arch v1.2，01-10 完整）**：ADR-01 GSCPI 源 / ADR-02 D3 死配置 / ADR-03 nuke 两层（v1.2：SafeCast 复刻）/ ADR-04 sdr 接入（v1.2：用户拍板 narrative 弱信号）/ ADR-05 air 删除 / ADR-06 firms 加固 / ADR-07 双轨并存 / ADR-08 summary bug 独立待修 / **ADR-09 SafeCast 复刻 nuke** / **ADR-10 sdr 区域规则**。

**gscpi 切换门禁（arch 重定义，因 crucix 侧 null 无可比对象）**：
1. GSCPI.csv 尾行 = 2026-07-31, 0.805 与官方一致
2. snapshot["GSCPI"] 形态正确
3. 阈值边界回放：2026-05=1.81 > 1.5 应触发 / 2026-07=0.805 不触发
4. 观察 1-2 周无 regime 突变（双轨窗口可缩短，原"≥1 月度周期"条件因 NY Fed 已有 2026 年 1-7 月数据而放宽）

## 五、遗留事项（需用户决策或下一轮处理）

1. **ingest_from_news_db summary bug**（ADR-08）：独立待修项，修复 = summary→COALESCE 或改现有列；需 qa 补 news.db→narrative_chunks 回归用例。**待用户拍板：修 or 挂起**（不影响退场主流程）。
2. ~~nuke 降级登记~~ → **已翻案**：SafeCast 可复刻，nuke 信号保留（ADR-09），无此决策了。
3. ~~sdr 是否接入~~ → **已拍板：接入**（narrative 弱信号，ADR-04/10 定稿）。唯一残留：**arch 请 qa 补两条验收基线**——① safecast_nuke.json 6 站与 crucix 快照 MATCH（qa AC-D1-05/07 已覆盖）；② sdr_summary.json 全局计数对齐 780/839（qa OB-SDR-01 已提 total±10%，可视为覆盖，最终以 qa 确认口径为准）。
4. **下一轮候选**：a) data 出 fetch_gscpi.py + fetch_safecast_nuke.py 落地探针（验证 NY Fed xlsx 与 SafeCast 在容器内真实可跑）→ b) 直接进入实施 P0-P4 排期 → c) qa 补 G1/G2 门禁可执行脚本细化。

## 六、风险登记摘要（RSK-1~9 + devops 10 项）

- RSK-1~7（qa）：替代源问题 vs 摘除实现问题判定判据 / climate job 停摆误报（G0 化解）/ 7890 vs 3117 端口混淆 / claude-config-backup 手动命令（R4）等
- **RSK-8（新增）**：TLS 失败归因——重试 ≤4 次失败=实现问题；重试 ≥5 次仍连续 ≥2 轮失败=替代源问题（api.safecast.org 多 IP 证书恶化），降级登记非回滚
- **RSK-9（新增）**："nuke 实时告警"误读防护——历史归档语义下 Chernobyl anom=true 是长期背景非突发，任何"当日新鲜度/实时告警"断言判据无效，不构成回滚理由
- **M9（新增）**：回归窗观测 safecast_nuke.json fetched_at 当日 / 6 站不缺 / 无连续 ≥2 轮失败
