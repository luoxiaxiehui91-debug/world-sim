# 开阳 Wave 1 · 数据契约（DATA_CONTRACT）

> 世界推演系统「开阳」是**纯展示层**：只读契约文件，**永不**调用任何数据源 / 爬虫 / 外部 API。
> 本文件是后续扩展（天璇 D.hypothesis / macro-sim D.sim / 天玑 D.verification）接入的**权威标准**。

---

## 0. 数据根（DATA_BASE_URL）

所有读取均基于可配置的数据根，默认 `./data/`（相对构建产物）。可通过以下方式覆盖：

| 方式 | 变量 / 字段 | 说明 |
| --- | --- | --- |
| 构建期环境变量 | `VITE_DATA_BASE_URL` | 如 `VITE_DATA_BASE_URL=/mnt/tianshu-data/ npm run build` |
| 运行时全局 | `window.__KAIYANG_DATA_BASE_URL__` | 部署时在 `index.html` 前置 `<script>` 注入，便于 NAS 只读挂载 |
| 默认 | `./data/` | 开发 / 通用静态托管 |

读取层会确保结尾带 `/`，再拼接待 `path`。

---

## 1. Feed 注册表

| feed 名 | 文件（相对 DATA_BASE_URL） | 类型 | schema_version | 说明 |
| --- | --- | --- | --- | --- |
| `grv` | `grv_latest.json` | json | `1.0` | GRV 11 维风险状态 |
| `news` | `news_export.json` | json | `1.0` | 新闻 / 叙事导出 |
| `simTrigger` | `sim_trigger.json` | json | `1.0` | 推演触发状态（**可选**） |
| `fred` | `fred_history/manifest.json` | json | `1.0` | FRED 序列清单（再按 manifest 取各 CSV） |

> 新增 feed：仅在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项，读取层（`useFeed` / `readLayer`）**无需改动**。

---

## 2. 字段定义

### 2.1 `grv_latest.json`（对象）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | 当前 `1.0` |
| `updated` | string(ISO) | ✅ | 数据时间戳（状态条显示） |
| `gdelt_updated` | string(ISO) | ⬜ | GDELT 来源时间戳 |
| `source_quality` | string | ⬜ | 来源质量标签 |
| `*_risk` / 维度键 | number \| null | ⬜ | 各维度数值；`null` 表示缺失 |
| `global_composite` | number | ⬜ | 综合指数（0–100） |

**11 维内部锚点**（见 `src/config/grvDimensions.ts`，上游无坐标时使用）：
台海、南海、美中战略、中东能源、俄乌/东欧、朝鲜半岛、印太、全球综合、气候风险、自然灾害、全球南方。

> ⚠ **Wave1 实际偏差**：上游 `grv_latest.json` 仅含 `taiwan_strait / us_china_strategic / russia_europe / middle_east_energy / global_composite / disaster_risk` 等键，且**无 lat/lng、无不确定区间字段**。适配层（`src/lib/grvAdapter.ts`）会：
> - 缺失维度 → `status:'missing'`，地球点位显示灰色、GRV 面板显示「数据缺失」、状态条记录告警；
> - 不确定区间 → 按数值 8% 估算并标记 `uncertaintyEstimated:true`（后续上游提供该字段后自动采用真实值）。

### 2.2 `news_export.json`（对象，含数组）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `1.0` |
| `updated` | string | ⬜ | 导出时间 |
| `items` | NewsItem[] | ✅ | 新闻 / 叙事条目 |

**NewsItem（字段宽松，缺失即降级）**：`date, source, indicator, series_id, title, category, level, direction, alert_type, current, baseline, ratio, z_score, details, risk_note, trigger_titles[]`。

> ⚠ **Wave1 实际偏差**：上游实际文件名为 `latest_news.json`（纯数组）。本仓库快照已包装为 `{schema_version, updated, items}` 以统一契约；读取层兼容「纯数组」与「包装对象」两种形态。

### 2.3 `sim_trigger.json`（对象，**可选**）
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | ✅ | `1.0` |
| `triggered` | boolean | ⬜ | 是否触发推演 |
| `level` | string | ⬜ | 触发等级 |
| `reason` | string | ⬜ | 触发原因 |
| `updated` | string | ⬜ | 时间戳 |

> 文件缺失不报错，状态条显示「推演未触发」。

### 2.4 `fred_history/manifest.json` + `*.csv`
| manifest 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | `1.0` |
| `updated` | string | 导出时间 |
| `series[]` | FredSeriesMeta[] | 序列清单 |

**FredSeriesMeta**：`id, label, unit?, file(相对 DATA_BASE_URL), color?, category?`。
**CSV 格式**：首行表头 `date,value`，其后每行一条观测；末列为数值列。

> 新增 FRED 序列：仅在 `manifest.json` 的 `series` 增加一项并放入对应 CSV，经济面板**无需改动**。

---

## 3. 扩展标准（用户硬性要求，已预埋）

1. **统一读取层** `useFeed(feedName)`：`src/hooks/useFeed.ts` + `src/lib/readLayer.ts`。所有数据经此层；新增 feed 不改读取层。
2. **面板注册表** `panelRegistry`：`src/panels/registry.ts`。每面板 = 组件 + 注册项（`id/title/feed/order/visible/className`）；新增面板只加注册项，布局（App.tsx 网格）无需改动。
3. **字段容错**：缺失字段降级渲染（「数据缺失」占位，不白屏/不崩），缺失项记入顶部状态条。
4. **schema 版本**：每个 feed JSON 带 `schema_version`（Wave1 = `1.0`）；breaking change 须 bump，读取层会比对并告警。
5. **本文件** `DATA_CONTRACT.md`：各 feed 文件名 / 路径 / 字段 / schema_version 的权威标准。

---

## 4. NAS 部署说明

开阳为纯静态站点，`vite build` 产出 `dist/`。

1. **构建**：`npm install && npm run build` → 生成 `dist/`。
2. **数据挂盘**：将天枢 `data/` 目录以**只读**方式挂载到容器某路径（如 `/mnt/tianshu-data/`）。
3. **serve dist**：任意静态服务器（nginx / caddy / `npx serve dist`）服务 `dist/`。
4. **注入数据根**：在 `dist/index.html` 顶部 `<div id="root">` 前加入：
   ```html
   <script>window.__KAIYANG_DATA_BASE_URL__ = "/mnt/tianshu-data/";</script>
   ```
   或将 `DATA_BASE_URL` 指向挂载路径。
5. **定时刷新**：数据由天枢侧更新；开阳无需后端，浏览器按 `fetch` 拉取最新快照（可配合 CDN/缓存策略）。

> SSE / 实时推送等留待后续 Wave；Wave1 为静态 + 前端加载。

---

## 5. 本地开发预览

```bash
npm install
npm run dev        # http://localhost:5173 ，开箱即跑（已内置 public/data 快照）
npm run build      # 产出 dist/
npm run preview    # 预览构建产物
```
