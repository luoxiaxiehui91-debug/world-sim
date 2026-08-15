# RSS 源可信度分级（tiering）落地规格 v0.1 · DRAFT

> **状态**：设计草稿（待代码 diff 审批后实施）。落库规则：定稿后移入 `S:\world-sim\macro-scan\docs\proposals\`。
> **来源参照**：worldmonitor `shared/source-tiers.json`（AGPL-3.0）——**只借鉴 tier 模型结构 + 源名/国家映射，禁复制任何代码**（copyleft 红线）。
> **动机**：当前 `narrative_processor` 的叙事桶聚合对同桶内所有源**等权**——一个 T4 小号发一条，和路透发一条推力相同。tiering 让 T4 单条几乎撬不动信号、T1 多家共振才真正抬升，直接治「新闻压力≠真实冲突」噪音病。

---

## 1. 现状（实测）

`macro-scan/核心代码/narrative_processor.py:38` 的 `SOURCE_META`：

```python
# 格式：source_id -> {primary_dimension, secondary_dimension, staleness_tau, source_type}
"rsshub_reuters":  {"primary": "global_composite", "tau": 72, "type": "financial_news"},
"defense_one":     {"primary": "taiwan_strait",    "tau": 120,"type": "defense_media"},
...
"crucix_gscpi":    {"primary": "global_composite", "tau": 48, "type": "osint"},   # ← 死条目（crucix 已退场 08-12）
"crucix_nuke":     {"primary": "taiwan_strait",    "tau": 24, "type": "osint"},   # ← 死条目
"crucix_air":      {"primary": "taiwan_strait",    "tau": 24, "type": "osint"},   # ← 死条目
"crucix_sdr":      {"primary": "sanctions_risk",   "tau": 24, "type": "osint"},   # ← 死条目
```

- 有 `type`（chinese_media / financial_news / news / defense_media / osint / official_data / humanitarian / official_statement）和 `staleness_tau`，**无 tier / weight 字段**。
- 聚合逻辑（`get_narrative_chunks_for_dimension` 及其调用方）未对源做可信度加权。

---

## 2. 设计

### 2.1 新增 `source_tiers.json`（天枢 核心代码/ 或 DATA_DIR/）
```json
{
  "rsshub_reuters":  {"tier": 1, "country": "US", "weight": 1.00},
  "rsshub_bbc":      {"tier": 2, "country": "UK", "weight": 0.70},
  "defense_one":     {"tier": 3, "country": "US", "weight": 0.40},
  "rsshub_eastmoney":{"tier": 3, "country": "CN", "weight": 0.40},
  "some_blog":       {"tier": 4, "country": "—",  "weight": 0.15}
}
```

**weight 默认映射（可调，集中在一处常量）**：
| Tier | 定义 | 默认 weight |
|---|---|---|
| T1 | 通讯社 / 官方政府源 | 1.00 |
| T2 | 主流成熟媒体 | 0.70 |
| T3 | 专业 / 小众 / 区域 | 0.40 |
| T4 | 聚合器 / 博客 / 未核实 | 0.15 |

### 2.2 `narrative_processor.py` 改动
1. 模块加载时 `json.load(source_tiers.json)` → `TIER_MAP`（缺失文件/条目不崩，走 fallback）。
2. `add_chunk` / 聚合处：每条 chunk 的有效贡献 = `base_score * weight(source_id)`。
3. **fallback 规则**（向后兼容）：`source_tiers.json` 未覆盖的 source_id → 按 `type` 给默认 weight（如 `osint=0.3`、`official_data=0.8`、`news=0.5`），避免新源突然 0 权重。
4. 删除 `SOURCE_META` 中 `crucix_*` 4 条死条目（crucix 已退场，无写入者）。

### 2.3 种子数据来源
- 从 worldmonitor `shared/source-tiers.json` 提取 **284 源的 {源名, 国家隶属, tier}**，映射到我们 `SOURCE_META` 的 `source_id`（按 URL/host 匹配）。
- **只搬数据（tier + country），不搬任何处理逻辑代码**。
- 我们自采 RSS 的 `source_id`（rsshub_*/aljazeera/defense_one/war_on_rocks/...）逐个对齐 tier。

---

## 3. 影响面 / 风险

- **改动范围**：新增 1 文件 + `narrative_processor.py` 加权逻辑 + 删 4 死条目。**结构性改动 → 按 08-12 纪律先给 diff 再动**。
- **不碰**：推演内核、GRV 公式（GRV 成熟度是阶段3 CII 的事，本规格只解决「信源加权」这一层）。
- **回归风险**：权重改变会影响所有叙事桶的归一化输出 → 实施后用 `daily_narrative` 跑一天对比 before/after 桶强度，确认 T4 噪音被压、T1 信号保真。
- **热挂载生效**：天枢是热挂载，改 `narrative_processor.py` + 加 `source_tiers.json` 即生效，但需 `docker restart` 仅当 scheduler 引用变更（本改动在运行区，按热挂载规则无需 restart，除非 scheduler 重新 import）。

---

## 4. 验收
- [ ] `source_tiers.json` 落盘，覆盖现有 `SOURCE_META` 全部活跃 `source_id`
- [ ] 单测：T1 源 3 条共振 > T4 源 10 条单发 的桶强度
- [ ] 运行一天 `daily_narrative`，对比桶强度分布，T4 噪音下降、T1 信号不丢
- [ ] crucix_* 死条目已从 `SOURCE_META` 删除，无残留引用（`grep crucix_ 核心代码/` 仅剩 DEPRECATED 注释）
