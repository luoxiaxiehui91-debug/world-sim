# 开阳 · 下个 Session 接手文档（HANDOFF）

> 更新：2026-08-16 ｜ 对应版本 **`VERSION = 1.11.27`** ｜ 维护：齐活林（主理人）
> **权威状态源**：`../.workbuddy/memory/MEMORY.md`（项目记忆，若与本文档冲突以 MEMORY.md 为准）
> 本文档是给**下一个 AI session / 接手者**的 60 秒快照，不是设计文档。深入细节请走 §6 的文件指针。

---

## 1. 一句话定位

**开阳（kaiyang）= 世界推演系统的前端操作面板**，展示 + 控制双职能：读侧只读天枢契约文件做可视化，写侧代表人类 operator 向自家后端下发操作指令（**只发令、后端执行**）。当前对标开源 crucix 展示大屏做复刻升级。

工作区：正式位置 world-sim monorepo 下的 `kaiyang`（与 macro-scan / macro-sim 平级）。

---

## 2. 当前进度一览

```
Wave1 ✅ 已完成（3D地球 + GRV + 经济 + 新闻 + 状态条）
   │
Wave2 ├─ 线 a：控制面 ──────── P0 ✅（T01-T03），A3a 真实 API 已接入（MOCK=false）
      ├─ 线 b：crucix 分类图层 ── P0 (①②) ✅ GO → P1 纯前端批 ✅ → 1.9.0 实时化 ✅
      ├─ 1.10.x ✅ 弹框/聚合/叙事桶（v1.10.5 事件弹框 → v1.10.8 聚合组）
      ├─ 1.11.x ✅ 08-16 大迭代（footer/Token UI/审查 B0-B4/卫生+新闻图层）
      └─ 剩余：P2 门控等数据（见 §4）
```

| 里程碑 | 版本 | 核心交付 | 测试 |
|--------|------|----------|:----:|
| 控制面 P0 | 1.1.0 | 右侧抽屉 + 天枢运维 Tab + Mock 自闭环 | tsc 零错 |
| crucix 分类图层 | 1.2.0 | RiskPoint.category 12 类 + 核设施图层 Nuclear Watch | 139/139 |
| 战略要地 + osint 删 | 1.3.0 | 8 种子要地琥珀星标 + osint 图层清除 | 160/6 files |
| 地区 Tab / KPI / 信号联动 | 1.4.0 | 6 区 Tab + 三 chip KPI + SelectionContext | 243/11 files |
| 左侧指标树 | 1.5.0 | LayerTreePanel 三态灯 + 计数 | 269/12 files |
| **§4.5 清扫 + news_geo 骨架 + 决策矩阵** | **1.6.0** | GrvPanel 修色 + P2 死代码 + news_geo 全链路 + DECISION_MATRIX | **297/13 files** |
| **BugFix + 2D 移除** | **1.7.0** | NaN 崩溃修复 + 控制抽屉关闭修复 + ErrorBoundary | unchanged |
| **MOCK 显式标注** | **1.7.1** | 控制抽屉顶部琥珀横幅 | 297 |
| **A3a 控制 API 接入** | **1.7.2** | MOCK_ENABLED=false，接入天枢 control_server REST :8900 | 基线 |
| **2D 地图 D3 重写 + 可拖拽布局** | **1.8.0** | FlatMapPanel D3 geoNaturalEarth1 + SVG；react-grid-layout 8 面板 | 基线 |
| **实时化收尾** | **1.9.0** | market_quotes 60s 轮询 + news_geo 上线 + 控制面真实链路 | 基线 |
| **事件弹框 → 聚合组** | **1.10.5 → 1.10.8** | 点击新闻点弹框 + 同地点聚合（bbox + 拼写变体合并） | 基线 |
| **08-16 大迭代** | **1.11.12 → 1.11.27** | 见 §3.9 版本链 | **364/20 files** |

> 测试基线说明：以当前代码基线为准（`src/` 下 **20 个测试文件**，364 例，`npm test` 全绿为验收标准）。

---

## 3. 已完成的重点（新 session 不用重新理解）

### 3.1 扩展体系（改代码前记住这三条）

- **加新 feed**：只在 `src/config/dataSources.ts` 的 `FEEDS` 登记一项 → `useFeed(feedName)` 自动生效
- **加新面板**：只在 `src/panels/registry.ts` 的 `panelRegistry` 加一项 → `App.tsx` 网格不动
- **加新类别**：只在 `src/config/layerCategories.ts` 加一项 + `theme.ts` 加色 → 图层体系自动继承

### 3.2 分类图层固化的关键约束

- **D1 颜色编码 = 方案 A（永久锁定）**：色相 = 类别，严重度 = 尺寸 + 光环脉冲
- `value`(0–100) 是唯一严重度数值，`weight`(0–1) 是唯一强度驱动源，`severity` 字符串**只是展示标签**
- `status==='missing'` / `value===null` ⇒ 强制灰 + 虚线，类别色不得覆盖（优先级最高）
- 渲染器保持只读：只读 `p.color / p.weight / p.shape / p.status`，换算全在 `src/lib/`
- 点位 id 命名空间：`${category}:${原始id}`（防撞车）
- 当前 **12 类**（osint 已于 1.3.0 因合规否决删除）

### 3.3 news_geo 已上线（1.9.0，不再等 feed）

- `src/config/dataSources.ts`：`news_geo` feed 已登记（`path: 'news_geo.json'`，`schemaVersion: '1.0'`）
- `src/lib/newsGeoAdapter.ts`：`adaptNewsGeo()` 兼容 `events[]` 与 `articles[]` 两种结构
- `src/components/WorldPanel.tsx`：`useFeed('news_geo')` + `adaptNewsGeo` 已接线
- 聚合入口：**实际消费是 `geoAggregate.ts` 的 `aggregateNewsGeo`**（事件走独立实现 `buildPointFromEvent`）——改 label/展示逻辑必须**两处同步**（1.11.19 改漏踩坑，见 CHANGELOG）
- 天枢 GDELT geo feed（news_geo_feed.py）已上线（scheduler 07:15 注册）

### 3.4 新闻标题三级取数（v1.11.21 → 1.11.23 定型）

- **数据源事实**：GDELT GKG events **无 title 字段**；DOC 2.0 API 有标题但 NAS IP 被 429 限流（实测，冷却后自动恢复）
- **预抓缓存**：天枢 `fetch_news_titles.py`（I120 2h 增量）→ `news_titles.json`（url→英文标题 + LLM 翻译中文 `titles_zh`）→ 前端读静态文件**秒开、零 API**
- **点击兜底**：控制 API `GET /news-title?url=`（天枢代理抓 `<title>`，SSRF 防护）——预抓未覆盖的极新事件才调
- **EventPopup 三级**：① `titleMap`（news_titles 静态，中文优先）→ ② localStorage → ③ API 兜底
- **翻译实现**：`hybrid_llm.call_openai_compat`（MiMo）逐条并发 4（批量 JSON 指令实测返回空 content，弃用）；失败保留英文

### 3.5 卫生图层（v1.11.16 → 1.11.18）

- 数据源 `health_geo.json`（天枢 fetch_health_geo.py，I60，GDELT GKG 卫生关键词 + 坐标）
- 事件含 `source_media`（媒体域名，历史回填 100%）+ `title`（DOC API 回填，限流时缺省）
- 前端 `DISEASE_ZH` 疾病中英映射（18 项）——label 中文疾病名兜底；点击弹框（health 已加入可弹框类别 v1.11.17）+ "查看新闻原文"
- **GKG CSV 无标题列**（实测纠错：08-15 旧分析误判 cols[4] 是标题——实为 URL）

### 3.6 控制面 = HTTP REST :8900（1.7.2 / 1.9.0 / 1.11.12+）

- **A3a 控制面真实协议 = HTTP REST**（天枢 `control_server.py`，FastAPI :8900），**非文件投递**
- 默认 API 地址 `http://192.168.31.108:8900/api/v1/control/`（`src/config/controlConfig.ts`）
- `MOCK_ENABLED=false`；开发调试用 `VITE_CONTROL_MOCK=true` 恢复 mock
- **Token 配置 UI（v1.11.12）**：`control/TokenSetup.tsx`（折叠式输入/保存/清除）+ 401 错误态内联重试 + `useFetchers` 依赖 token 自动重拉
- **内置 token（v1.11.15）**：构建时注入 `VITE_CONTROL_API_TOKEN`（**不进 git**），`getEnvToken()` 优先；**构建必须带此参数**（见 DEPLOYMENT.md §1）
- **H02 信任校验（v1.11.14）**：`buildHeaders()` 仅对 `192.168.31.108 / localhost / 127.0.0.1` 附带 Bearer token（防 localStorage 注入恶意 URL 外泄）

### 3.7 地图交互关键约束（v1.11.24/25 踩坑沉淀）

- **背景取消**：`FlatMapPanel` svg `click.background` + `GlobePanel` `world.onClick` → `handleBackgroundClick`（selectSignal(null,null) + setPopupPoint(null)）；EventPopup onClose 复用同一 handler
- **⛔ d3 事件 + React 重渲染冲突**：点位 click handler **必须 `event.stopPropagation()`**——选点触发 setState → 点位 group 重建 → 冒泡到 svg 的 background handler 时 target 是 detached 旧 circle，closest 返回 null 误判背景 → 立即取消选中（v1.11.24 回归实测）
- **playwright 验证纪律**：真实鼠标序列（mouse.down/up）+ 等 2 拍查状态；`dispatchEvent` 会假通过（React 异步重建时序差异）；`querySelector('svg')` 会拿到 starfield 的 svg 不是地图的

### 3.8 LLM 统一配置体系（v1.11.26-27）

- **后端 `macro-scan/核心代码/llm_usage.py`**：6 使用点静态清单（translate_titles / openai_compat / rag_embedding / sim_mc / sim_narrative / sim_minimax）× 4 平台（mimo / siliconflow / minimax / openai）+ `data/llm_config.json`（v2.0 schema，原子写，**base_url 落盘展开**——天璇等跨容器消费者无需平台清单）；`resolve(usage_id)` 返回 (base_url, api_key, model)，`resolve_embedding()` 拼 `/embeddings` 路径
- **接入**：`hybrid_llm.call_openai_compat(usage=...)`（翻译走 `translate_titles`）；`rag_engine._get_embeddings_batch` 走 `resolve_embedding`（bge-m3）；天璇 `llm_client._resolve_client`（配置覆盖 → 动态 OpenAI 兼容客户端，缓存 by url+key；**改 llm_client.py 代码后必须重建容器**——COPY 模式）
- **控制 API**：`GET /api/v1/control/llm-usage`（usages + platforms，**key 脱敏 sk-***abcd**）、`PUT /api/v1/control/llm-usage/{id}`（{platform, model, api_key?}，key 缺省保留原值，空模型/未知平台拒绝）
- **前端 `control/LlmConfig.tsx`**：平台下拉 + 模型 datalist 可手输 + key password 输入 + 保存（TokenSetup 下方）
- **⛔ 部署纪律**：改 `llm_usage.py`/`hybrid_llm.py`/`control_server.py` 后**必须重启 control_server 并 curl 验证**（kill 循环可能不匹配 → 旧进程服务旧代码假象；用 python os.kill 指定 PID + curl 新路由验证）
- **Claude 已移除**（08-16）：call_claude 是历史分支（无 ANTHROPIC key），使用点清单和平台都不含

### 3.9 08-16 大迭代版本链（1.11.12 → 1.11.27）

| 版本 | 内容 | 关联审查项 |
|------|------|-----------|
| 1.11.12 | footer 滚动盖层修复 + 控制台 Token 配置 UI | 用户报障 |
| 1.11.13 | H18 sim_trigger 三端契约（读取失败清零）+ schema_version 统一 | B2 |
| 1.11.14 | H01 randomUUID LAN 崩溃 + H02 token 外泄通道 | B3 |
| 1.11.15 | 内置 CONTROL_TOKEN（构建注入，开箱即用） | 用户报障 |
| 1.11.16 | 卫生图层关联新闻（source_media 媒体名） | 用户需求 |
| 1.11.17 | 卫生点点击弹框显示新闻（health 加入可弹框类别） | 用户需求 |
| 1.11.18 | 卫生弹框标题中文化（DISEASE_ZH 映射 + DOC API 回填） | 用户需求 |
| 1.11.19 | 地区新闻弹框 label 改写（URL slug 伪标题）⚠ 改错路径 | 用户需求 |
| 1.11.20 | 聚合路径 buildPointFromEvent 同步（v1.11.19 修漏） | 用户反馈 |
| 1.11.21 | **真实标题按需抓取**（后端 /news-title 端点）+ label 回退地点名 | 用户反馈 |
| 1.11.22 | 新闻标题预抓缓存（fetch_news_titles.py I120）秒开零 API | 用户建议 |
| 1.11.23 | 新闻标题中文化（LLM 翻译 titles_zh 优先） | 用户需求 |
| 1.11.24 | 点击空白/关闭弹框取消选中 ⚠ 引入回归 | 用户需求 |
| 1.11.25 | **回归修复：点位 click 阻断冒泡**（detached target 误判背景） | 用户反馈 |
| 1.11.26 | **LLM 使用点统一配置面板**（6 使用点清单 + 控制台改模型）+ 翻译模型 mimo-v2.5 | 用户需求 |
| 1.11.27 | **LLM 配置平台化**（平台/模型/API key 统一切换；移除 Claude + 补 rag_embedding 嵌入使用点） | 用户需求 |

---

## 4. 待办与决策点（新 session 从这里接）

### 4.1 审查批次状态（audit-todo-20260815.md 权威）

```
P0: A 密钥轮换待办 / B ✅ / C ✅ / D ✅      P1: A-E 全 ✅      P6: ✅ SQLite 清零
B0 ✅  B1 ✅  B2 ✅  B3 ✅  B4 ✅（审查 High 全部清完）
探针 31 项全绿      git 干净
```

- **P0-A 密钥轮换**：触发条件 = 仓库转公开/外部共享前（GitHub PAT + FRED/LLM/EIA/ntfy；轮换时同步更新 `VITE_CONTROL_API_TOKEN` 构建参数）
- **P2 门控（自动化）**：每月 13 日 09:00（2026-11-13 起）检查天璇预测 90 天到期 → MIN_TRIGGER_N=8 → 玉衡 V2 启动（automation 已设）
- **Medium 置顶**：M33（bifurcation n_clusters==1 强拆 3 簇）、M09（Herfindahl 恒 1.0 恒不告警）——天璇侧，非开阳
- **GED 数据决策**（P2 门控内）：跑 ETL + 裁决"冻结禁作当前信号"冲突

### 4.2 P1 / P2 图层与后端依赖（开阳侧）

| 优先级 | 图层 / 功能 | 状态 |
|:--:|---|:--:|
| **P1** | 冲突事件图层 | ⏸ 等 ACLED feed（天枢无授权无 fetcher；ACLED 已放弃 → UCDP 评估中） |
| **P2** | 空域 / 热异常 / 海上 / SDR | ⏸ 等后端新建 feed（④空域⑤热异常天枢已有基础可优先） |
| **P2** | 信号流 sweep delta | ⏸ 等后端算好推送 |
| **P2** | 聚类标签（Ukraine 71 式） | ⚠ 待定 D2（见 §4.3） |
| **P2** | 地区新闻中文概要（事件类型标签） | 未做——用户问过，可选项；标题保持原文/LLM 翻译 |

### 4.3 决策矩阵现状（已文档化）

> 详见 [`DECISION_MATRIX.md`](./DECISION_MATRIX.md)。D2-D5 均已给出主理人推荐。

| # | 决策 | 主理人推荐 | 状态 |
|---|------|-----------|:--:|
| D2 | 聚类：前端 bbox vs 后端预聚合 | 折中：后端预留 reader + 前端 1°×1° bbox 兜底 (<200点) | 待触发（点位超阈值时） |
| D3 | feed 粒度：每类一文件 vs 聚合 | 每类一文件（已写进契约） | ✅ 已隐含采纳 |
| D4 | SSE 实时推送 | 不做（日/周频无意义） | ✅ 已隐含采纳 |
| D5 | 解锁 Leaflet / MapLibre 新依赖 | 不解锁（D3 geoNaturalEarth1 方案） | ✅ 已定案 |

---

## 5. 新 session 开场话术

> **「继续开阳。VERSION 1.11.27，20 个测试文件 364 例全绿。08-16 大迭代完成：审查 B0-B4 全清（H18 sim_trigger 契约 + schema_version 统一 / H01 randomUUID / H02 token 外泄 / H08+H11 原子写），卫生+地区新闻图层功能链齐（source_media / 中文疾病名 / 新闻标题预抓+LLM 翻译 / 弹框），地图交互补背景取消（v1.11.24→25 回归已修）。控制台内置 token（构建必须带 VITE_CONTROL_API_TOKEN）。剩 P2 等数据（自动化每月 13 日检查）+ P0-A 密钥轮换待触发。LLM 配置体系（llm_usage + 控制台面板）已就位，见 §3.8。」**

---

## 6. 关键文件指针

### 6.1 必读（新 session 前五分钟）

| 文件 | 作用 |
|------|------|
| `../.workbuddy/memory/MEMORY.md` | **权威状态源**，比本文档更全 |
| [`DESIGN.md`](./DESIGN.md) | 设计总纲 §2.1 进度表 |
| [`DATA_CONTRACT.md`](./DATA_CONTRACT.md) | 数据契约（§1 注册表 / §2.7 news_geo / §2.11 health_geo / §2.12 news_titles） |
| [`A3a-控制API-开阳对接文档.md`](./A3a-控制API-开阳对接文档.md) | 控制 API 端点（含 news-title） |
| [`DEPLOYMENT.md`](./DEPLOYMENT.md) | 部署规范（**构建必须带 VITE_CONTROL_API_TOKEN**） |
| [`../AGENTS.md`](../AGENTS.md) | AI session 入口，硬约束 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 变更记录 |
| `../../docs/decisions/audit-todo-20260815.md` | 审查批次状态（B0-B5 + Medium） |

### 6.2 代码扩展锚点

| 路径 | 做什么 |
|------|--------|
| `src/config/dataSources.ts` | **加 feed 只改这里** |
| `src/config/layerCategories.ts` | 图层类别唯一真源（12 类） |
| `src/config/theme.ts` | 色值唯一真源 |
| `src/panels/registry.ts` | **加面板只加一项** |
| `src/lib/` | 数据→渲染换算层（渲染器只读）——**newsGeoAdapter.ts 与 geoAggregate.ts 双实现须同步改** |
| `src/hooks/useFeed.ts` | 统一读取层（一般不用改） |
| `src/config/controlConfig.ts` | 控制 API Base URL + MOCK_ENABLED 开关 |
| `src/components/FlatMapPanel.tsx` | 平面地图（svg 背景点击 click.background + 点位 click stopPropagation 约束） |
| `src/components/EventPopup.tsx` | 事件弹框（标题三级取数 + sourceUrl 原文链接） |

---

## 7. 关键 gotcha

### 7.1 ⛔ three 版本钉死

```jsonc
"three": "0.185.1",           // 精确版本，不要 ^
"@types/three": "0.185.1",    // 精确版本，不要 ^
"globe.gl": "^2.46.1"
```
`three` 过旧 ⇒ `Matrix4.determinantAffine()` 缺失 ⇒ 地球渲染空白（React 静默吞错）。**绝对不要降 three 或留 `^`**。

### 7.2 ⛔ 铁律三条

- 开阳**永不自连**第三方数据源 / 爬虫（FRED/GDELT/Yahoo 等）——唯一例外：`/news-title` 走**自家后端**抓取（隔离铁律允许"向自家后端发指令"）
- 严禁硬编码 NAS/SMB 绝对路径（部署靠外部挂载 + 改 `DATA_BASE_URL`）
- 数据缺失一律降级，**不白屏**（空数组是合法业务态）

### 7.3 ⚠ 语义约束（容易被后来者破坏）

- `severity` 字符串只是展示标签，禁止参与着色/数学
- 缺失态优先级最高（`status==='missing'` 强制灰+虚线）
- 渲染器只读 `p.color/p.weight/p.shape/p.status`，不 import layerCategories

### 7.4 ⚠ 改后必做

1. bump `VERSION` + `package.json` version
2. `CHANGELOG.md` 追加（改了什么 / 为什么 / **明确没改什么**）
3. 同步 `docs/DESIGN.md` + `docs/DATA_CONTRACT.md`
4. `npm run build` 绿（**带 VITE_CONTROL_API_TOKEN**）+ `npm test` 全绿（基线 = `src/` 下 20 个测试文件）

### 7.5 ⚠ CHANGELOG 承诺 ≠ 代码实际落盘

每次 bump CHANGELOG 时逐条确认变更在源码实际存在，不凭计划/意图预设。

### 7.6 ⚠ d3 事件 + React 重渲染（v1.11.25 血泪）

- 在 d3 元素上挂事件、handler 里触发 React setState → **父级重渲染会重建 d3 节点** → 事件冒泡到祖先时 target 已 detached → 祖先 handler 基于脏 DOM 误判
- **通用解法**：子元素 handler 若有副作用（setState），必须 `event.stopPropagation()`
- **验证**：真实鼠标序列（mouse.down/up），不可只信 dispatchEvent

---

## 8. 版本速查

| 版本 | 内容 | 测试数 |
|------|------|:----:|
| 1.1.0 | 控制面 P0 | tsc 零错 |
| 1.2.0 | crucix P0 分类图层+核设施 | 139 |
| 1.3.0 | 战略要地标签 + osint 删除 | 160 |
| 1.4.0 | 地区 Tab + KPI + 信号联动 | 243 |
| 1.5.0 | 左侧指标树 | 269 |
| 1.6.0 | §4.5 清扫 + news_geo 骨架 + 决策矩阵 | 297 |
| 1.7.0 | BugFix + ErrorBoundary + 2D 移除 | unchanged |
| 1.7.1 | MOCK 显式标注横幅 | 297 |
| 1.7.2 | A3a 控制 API 接入（HTTP REST :8900） | 基线 |
| 1.8.0 | 2D 地图 D3 重写 + react-grid-layout | 基线 |
| 1.9.0 | 实时化（market_quotes + news_geo + 控制面） | 基线 |
| 1.10.5→1.10.8 | 事件弹框 + 同地点聚合 | 基线 |
| **1.11.12** | footer 盖层 + Token 配置 UI | 352 |
| **1.11.13** | H18 sim_trigger 契约 + schema_version 统一 | 352 |
| **1.11.14** | H01 randomUUID + H02 token 外泄 | 352 |
| **1.11.15** | 内置 CONTROL_TOKEN | 352 |
| **1.11.16** | 卫生图层 source_media | 352 |
| **1.11.17** | 卫生点弹框（health 可弹框类别） | 352 |
| **1.11.18** | 卫生标题中文（DISEASE_ZH + DOC 回填） | 354 |
| **1.11.19** | 新闻 label slug（改错路径） | 366 |
| **1.11.20** | 聚合路径同步（1.11.19 修漏） | 367 |
| **1.11.21** | 真实标题按需抓取 + label 回退地点 | 364 |
| **1.11.22** | 新闻标题预抓缓存 | 364 |
| **1.11.23** | LLM 翻译中文标题 | 364 |
| **1.11.24** | 背景取消选中（引入回归） | 364 |
| **1.11.25** | 回归修复（点位 click stopPropagation） | **364** |
