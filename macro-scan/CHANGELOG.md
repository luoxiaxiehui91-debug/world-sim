## v3.8.78（2026-10-18）

**端口合并 S4：`/ask` 自 8899 迁入控制面 8900，走 token 鉴权** —— CHG-20261017T231000

### 背景
8899（`web_server.py`）此前唯一存活的功能是 `POST /ask`（LLM 问答）。该端点**无鉴权、只有限流**
（对照：8900 控制面返回 401）。为让 8899 可安全退役，先把 `/ask` 迁入控制面，
使其自动获得 Bearer Token 校验，再退役 8899 端口（S5 同批）。

### 改动（`核心代码/control_server.py`）
- 新增 `POST /api/v1/control/ask`，带 `_check_token`，逻辑自 `web_server.py:388-487` 迁入：
  限流 → 长度上限 → 上下文注入（GRV / 情境事件 / 弱信号 / 气候 / 灾害）→ `hybrid_llm.reason`
- **限流来源标识改为优先 `X-Real-IP`**，回退 `request.client.host`。
  原实现的 `request.client.host` 在反代后**恒为 kaiyang 容器 IP（172.29.0.4）**，
  会让所有用户共用一个限流桶（一人超限、全员被封）。
  **仍不采信 `X-Forwarded-For`**：nginx 的 `$proxy_add_x_forwarded_for` 是「追加」语义，
  客户端伪造的 XFF 会保留在左侧，取左仍可绕过；而 `X-Real-IP` 由 nginx 以 `$remote_addr`
  无条件覆盖，客户端无法伪造
- 端点用同步 `def` + Pydantic `AskPayload` 声明 body：同步端点无法 `await request.json()`；
  同步 `def` 会被 FastAPI 放入线程池，LLM 阻塞不会拖住其它端点的事件循环
- 保留原限流参数（60 秒 10 次）与 500 字上限，未放宽

### 验证
| 项 | 判据 | 结果 |
|---|---|---|
| 鉴权 | 无 token | 401 ✅ |
| 限流 | 60s 内第 11 次 | 429 ✅（前 10 次空问题 400，未进 LLM） |
| 伪造防护 | `X-Forwarded-For: 9.9.9.9` | 仍 429 ✅（XFF 未被采信） |
| 空问题 | `question: ""` | 400 ✅ |
| 端到端 | 经 8080 反代真实提问 | 200 / 8.7s ✅（答案含 GRV 台海 67.2、中东能源 70.8，上下文注入正常） |

### 遗留
- 8899 退役后，`web_server.py` 文件**保留不删**（仅停止启动），避免触发文件增删门禁；
  如需彻底移除，须同步 FILE_MANIFEST 并重建镜像。
- 限流桶为进程内存态，重启清零（与原实现一致，可接受）。

## v3.8.77（2026-10-17）

**全量代码审查修复：控制令牌止血 + Web 端点加固 + 日志轮转 + 静态扫描清零** —— CHG-20261017T030000

> 来源：全项目代码审查（604 文件 / 8 万行源码 + 配置 + 构建脚本 + 依赖清单）。
> 本批仅收录**已实证核实**的缺陷，未经核实的疑似项列入「遗留」，不入版本。

### 改动
- `核心代码/web_server.py`：**8899 端点零鉴权 + POST /ask 无限流**（实证：无凭证 curl `/health` `/status`
  `/grv` 均 200，对照组 8900 返回 401）——新增 `/ask` 来源级滑动窗口限流（60 秒 10 次）与提问长度上限 500 字符；
  刻意**不**采信 `X-Forwarded-For`（本端口无反向代理，该头可伪造绕过限流），改用 `request.client.host`。
  读端点保持开放以保证浏览器直连可用；注释中标明「若暴露到不可信网络须复用 `_check_token` fail-closed 鉴权」
- `entrypoint.sh`：**日志无轮转、无上界增长**（实证：`logs/` 102MB / 77 文件 / 0 个轮转产物，最大 26MB）。
  各进程输出以 `>>` 重定向到挂载卷文件，docker `json-file max-size` 对其无效。新增启动时轮转
  （>20MB 的 `.log` 后挪为 `.1`/`.2`，最多保留 2 代）；依托路由器每日 03:30 重启 ⇒ 近似每日生效。
  已在本地构造 1MB/25MB 日志连跑 4 个周期回归验证：小文件不受影响、大文件稳定保留 2 代
- `核心代码/run_macro_analysis.py`：`compute_feedback_sensitivity` 的 **def 行丢失**，函数体被并入上方
  `score_global_recession_risk` 末尾（该行因第 3193 行无条件 `return` 而不可达），导致 `--sensitivity`
  分支抛 `NameError`。补回 def 头后：`score_global_recession_risk` 正确止于 3193，新函数独立为 3200–3275
- `核心代码/geo_risk_vector.py:255`：except 分支误用未定义的裸 `logger`（模块仅提供 `_get_logger()`），
  使「本可优雅降级为 None」的计算失败二次抛 `NameError`
- `核心代码/fetch_{crypto,crypto_extra,earthquake,energy,fx,hdx,sanctions,world_macro}.py`：
  `from fetcher_base import FetcherBase` 原位于 try 块**之后**，而 `except ImportError` 分支却引用它 ⇒
  `optim_config` 不可用时降级路径抛 `NameError`。已将 import 前移至 try 之前（`fetcher_base` 仅依赖标准库，无环）

### 验收
- `ruff --select F821`：25 → **0**（25 处 undefined-name 分别对应上述三类问题）
- 全仓 `py_compile`：207 文件 **0 失败**
- `entrypoint.sh` `bash -n` 通过；轮转逻辑离线回归 4 周期行为符合预期

### 遗留（本批**未**改，待定）
- 8899/8900/8080 均绑定 `0.0.0.0`（含 IPv6），建议评估是否收窄到 `127.0.0.1` + 本地隧道（改动会中断局域网直连，需用户确认）
- `CONTROL_TOKEN` 曾以明文出现在前端 bundle（已在本批清除产物，但令牌本身过去可获取）——**是否轮换待用户确认**


## v3.8.76（2026-10-16）

**health_geo 事件单位改为「故事（story）」：修通稿转载致 count 虚高 43%** —— CHG-20261016T120806

### 改动
- `核心代码/fetch_health_geo.py`：
  - 新增 `_story_slug(url)`：URL path 为故事身份，只剔「年(19xx/20xx)+相邻月/日」与 ISO 日期段，**不剔纯数字故事 ID**（`story/9367686/…` 保留，避免不同故事被误合）
  - `_merge_events()` 增加 slug 级去重（原仅按 doc URL 去重，对通稿形同虚设）
  - `_aggregate_by_location()` 的 `count` 由「同 loc 的 raw 条数」改为「同 loc 的 distinct story 数」
  - 新增 `_is_aggregator_page()` + `AGGREGATOR_PATH_MARKS`（`/tag/` `/tags/` `/topics/` `around_the_web` `/author/`；**不含 `/category/`** —— 分类路径下有真文章）
  - 关键词匹配加左边界约束 `_KW_RE`（`(?<![a-z0-9])`）：杀 `vlassa|kis` / `sho|zika` 类嵌词巧合，保住 `outbreaks` 复数与连字符写法
- `tests/test_fetch_health_geo.py`：8 → **14 例**（新增嵌词不收录、复数/连字符仍收录、聚合页跳过、分类路径保留、slug 日期段剔除、merge slug 去重、count=distinct story）

### 验收
- 单测 14/14 PASS；`py_compile` 通过
- 存量清洗（容器内执行，备份 `_rollback/health-geo-syndication-20261016/`）：raw **944 → 570**（-40%）、聚合 **244 → 232 点**、合计 count **944 → 570**
- 用户可见修正：Macquarie Island 35 → **1**（该点 title 即"First bird flu detection on remote sub-Antarctic island"）、France 45 → 8、Australia 42 → 9、United States 41 → 21
- 剔聚合页 2 条 + 删嵌词误报 4 条（希腊银行新闻 `sho|zika` ×3、`vlassa|kis` ×1）；残留人工复核 1 条为**真事件**（newsroomamerica 长 ID 文章页，确为美国麻疹爆发）
- md5 真源 = 运行区 = 容器 `4419191d…`

### 遗留
- 代表事件地点串味（11/244 点主题国与地点国不相交）未修 —— 部分源于 GKG 自身地理抽取、部分源于通稿页面夹带本地内容，需另立项
- `title_zh` 覆盖 212/232（20 条未中译，既有状态）
- 未新增 `sources`（报道站点数）字段 —— 改 schema 需同步前端 `contracts.ts`，留待后续

## v3.8.75（2026-10-15）

**LLM 配置重构 P3②：`call_local` 的 base_url / api_key / 账本 platform 统一走配置链** —— CHG-20261015T232202

### 改动
- `核心代码/hybrid_llm.py`：新增 `_local_cfg()` —— model / base_url / api_key / platform 同源解析（api_key 依 ADR-0015 不落 `llm_config.json`，按 platform → env 变量名映射热读，最终回落 `_sf_key()`）；`_local_model()` 改为委托它；`_do_siliconflow_request()` 新增 `base_url` / `api_key` 可选参数（缺省回落 SiliconFlow 常量）；`call_local()` 前置检查改用 `_local_cfg()`，账本 `platform` 由硬编码 `siliconflow` 改为随配置（4 处）
- 修的是**潜伏缺陷**：控制台把 `call_local` 切到非 SiliconFlow 平台时，模型名会跟着配置变，但请求仍打到 `api.siliconflow.cn` 且用 SF 的 key ⇒ 401/404，账本 `platform` 归因也错

### 验收（2026-10-15 23:2x 实测）
- 当前配置 `platform=siliconflow` ⇒ base_url / api_key / model / platform 四项取值与改前**逐项等价**（零行为变化）
- 容器内运行时探针：`_local_cfg()` 四项与 `resolve("call_local")` 全 MATCH；monkeypatch 切到 `mimo_plan` 后 base_url 同步变为 `https://token-plan-cn.xiaomimimo.com/v1`（证明统一生效，非仅等价）；未打印 api_key 明文
- md5 真源 = 运行区 = 容器内 `fa47c6920551e651ec85ad7ffab35fe4`（三处一致）；`py_compile` 通过；行数 441 → 468
- 守卫 `scripts/check_llm_config.py` EXIT=0；24h 四容器 Traceback=0 / FALLBACK=0

### 遗留（不阻塞闭环）
- 本次**不 restart 容器**：`scheduler.py` 用 `subprocess.Popen` 拉起每个 job ⇒ 新进程自动加载新代码；常驻 `control_server` / `web_server` 于下次容器重启时加载新代码（改动等价，无差异）
- 运行区 `macro-scan/CHANGELOG.md` 副本停在 v3.8.68（deploy.sh 不同步 .md），本次未改；真源为权威

---

## v3.8.74（2026-10-13）

**修复 health_geo 关键词 haystack 混入 URL 域名段致域名碰撞误报** —— CHG-20261013T183000-health-geo-url-collision-fix

**缺陷现象**：开阳 health 图层 `lassa` 项大量噪声 —— 印度地方报纸域名 `www.sentinelassam.com`
含子串 `lassa`，其无关社会新闻（车祸/缉毒等）被批量收录。raw 存量 **157 条**
（逐日持续进库：10-10 22 / 10-11 37 / 10-12 57 / 10-13 41），聚合层 192 点中 **62 点（32%）**为该噪声占位。

**根因**：`fetch_health_geo.py:137` haystack = `cols[4]`(文档 URL 全串) + `cols[11]`(人名) + `cols[24]`(数量词)，
其中 **域名段与内容无关**（`www.sentine|lassa|m.com`），子串匹配引入「域名碰撞面」；
157 条 URL **path 段含 "lassa" 的为 0** ⇒ 100% 撞在域名段。

**修复**：新增 `_url_content()` —— haystack 中 URL 仅保留 **path+query**（剔除域名段）。

**为什么不是「剔除整个 URL」**（原解法候选）：抽样探针实测（8 slot / 2926 行）纯剔 URL
**会误杀真事件**（丢 12 条中 4 条真事件：UNGA 大流行宣言 / 菲律宾登革热 19.2 万例 /
印度 Nashik 81 例 / 欧盟沙门氏菌爆发 —— 它们靠 URL 路径段命中、内容列不含词）；
改为剔域名后同一实测 **零损失（23/23）**。域名=站点标识（剔），path/query=文章标识（留）。

**存量清洗**：raw 移除 157 条域名撞（判据与修复逻辑同源），682 → **525 条**；
备份 `_rollback/health-geo-url-collision-20261013/health_geo_raw.json.bak-20261013T1832-pre-clean`。

### 验收（2026-10-13 18:2x–19:0x）

- ✅ `tests/test_fetch_health_geo.py` **8 用例全过**（域名撞不收录 / 无 www 与大小写变体 / Amounts 真事件保留 / path 命中保留 / 域名撞+真词 kw 正确 / EXCLUDE 生效 / 无坐标跳过 / Persons 列现状保持）
- ✅ 现有 `test_fetch_*.py` 4 项仍全过（改动前基线 PASS）
- ✅ md5 三处一致 `388ee423f5dbc6400b99c56c6ac00d7e`（真源 = 运行区 = 容器 `/app`）
- ✅ 存量清洗复核：netloc 撞 = 0、events_count = 525、无误删警告（removed 中 title 含词 = 0）
- 运行时首轮复核：见 CHG-20261013T183000 Post-Change（I60 轮）

**教训**：haystack 不得混入 URL / 文件名等「站点标识」列——站点标识与内容无关，子串匹配必然引入碰撞面；
且「剔 URL」时要区分**域名段（无关，剔）与路径段（内容标识、含真事件 slug，留）**。

## v3.8.73（2026-10-13）

**修复 news_all 标题中译「缓存全命中时回填被跳过」的回归** —— CHG-20261013T114554

**缺陷现象**（11:41 收尾盘点实测）：`news_zh_titles.json` 缓存 31 条含中文 31/31，但 `news_all.json`
100 篇中 `title_zh` = **0**、31 条英文标题裸露 —— 第一轮部署后正确，**随后被后续轮次冲掉**。

**根因**：`news_exporter.py::_translate_zh()` 把「翻译」与「回填」写在同一函数，`if not todo: return`
提前返回，**漏掉回填循环**。`news_exporter` 调度 = **I15** ⇒ 第二轮起缓存全命中、`todo` 为空，
每轮都把 `title_zh` 冲掉。

**同族对照（证明是实现问题非设计问题）**：health 图层（CHG-20261013T080315）回填是独立一步
`_backfill_title_zh()`，在 `_translate_pending()` 之外调用 ⇒ 缓存全命中时仍回填，无此缺陷
（11:41 实测 `health_geo.json` 184 条中 70 条带 `title_zh`）。

**修复**（单点最小 diff，不改调用点 / 不改前端 / 不改缓存结构）：
把「无待翻项」从**提前 return** 改为**跳过翻译段、照常回填**；异常路径由 `return` 改 `zh = {}`。

### 验收（2026-10-13 11:47–11:52 实测）

- ✅ 连续两轮实跑（缓存全命中、`todo=0`，无「标题中译」日志）：`news_all.json` 均 **31 条 title_zh**、**仍英文无 zh = 0**
- ✅ 缓存条目恒 31（未重复翻译）
- ✅ `news_export.json` 字段集仍 5 键、无 `title_zh` ⇒ 信号流未误伤
- ✅ 真源 = 运行区 = 容器 `/app` md5 一致 `41f837cc64cdc0f90c65fefe44d12047`；`py_compile` 通过
- ✅ 前端未改，`deploy.sh` 无需重建；产物 `title_zh` 仍命中 2 处

**教训**：把「读缓存 → 缺则翻译 → 回填」写成单函数时，**早退路径必须覆盖回填**；
或按 health 既有范式拆成「翻译」与「回填」两步（红线 #43：项目内既有正解优先）。

## v3.8.72（2026-10-13）

**news_all 英文标题中译（FT / BBC 官方源）** —— CHG-20261013T093037

背景（09:26 实测）：`news_all.json` 100 篇中 **31 篇英文标题**，全部来自 **FT（16）+ BBC World（15）**；
中文源（财新 / 第一财经 / 华尔街见闻）标题正常。根因 = `news_exporter.py::export_all_news()` 直出 PG `news.articles`，无翻译逻辑。

范围判定（关键）：**只翻 `news_all.json`**（开阳「全量新闻」面板，人看）；
`news_export.json`（`export_news_for_sim()` 产出、喂 macro-sim AI 推演的信号流）**明确不翻** —— 原文对推演更准，避免误伤下游。

改动：
- **`核心代码/news_exporter.py`**：新增 `ZH_CACHE_FILE="news_zh_titles.json"`（url→中文缓存）/ `ZH_BATCH=50` / `ZH_CACHE_MAX=5000`；新增 `_load_zh_cache` / `_save_zh_cache` / `_translate_zh`；`export_all_news()` 组装后中译，article 带 `title_zh`
- 翻译复用 `fetch_news_titles._translate_titles`（同一 `usage=translate_titles` 配置链），**不新增硬编码模型名**（守 G1）
- 缓存必要性：`news_exporter` = **I15**，不缓存则每轮重翻 ≈ 2880 次/天
- **开阳**：`NewsPanel.tsx` 标题改 `title_zh ?? title ?? indicator`；`contracts.ts` `NewsItem` 补 `title_zh?`（版本 1.11.46）

### 验收（2026-10-13 09:31–09:42 实测）

- ✅ 容器内实跑 `news_exporter.py` → `标题中译 31/31`（与实测英文标题数精确吻合）
- ✅ `news_zh_titles.json` 31 条，含中文 31/31；`news_all.json` 100 篇中 31 篇带 `title_zh`，**仍为英文且无 title_zh = 0**
- ✅ `news_export.json` 字段集仍为 5 键 `[category, date, source, title, url]`，**无 title_zh ⇒ 信号流未误伤**
- ✅ 英文 `title` 字段零丢失
- ✅ 真源 / 运行区 / 容器 md5 一致 `acdc50fae4e677f0c067c7ef01a7c819`
- ✅ 开阳 373 单测全过；`deploy.sh` 构建 + `chmod -R a+rX` + HTTP 复验 `index-DWTganDz.js` 200；产物 `title_zh` 命中 2 处

## v3.8.71（2026-10-13）

**health 图层标题中译（卫生事件弹框标题英→中）** —— CHG-20261013T080315

背景（08:00 实测）：`health_geo.json` 聚合 188 条、含 `title` 175 条，**中文占比 0%**；
同期 GDELT 新闻图层 252/252 全有中文。根因 = 全仓仅 `fetch_news_titles.py` 一处实现翻译
（`grep -c "translate|翻译"`：`fetch_health_geo.py` / `fetch_rss_news.py` / `fetch_news.py` **均为 0**）
⇒ 卫生图层**从未接入翻译链路**，非故障。同期排除两条假设：① **非风控**（无 403 / 内容拒绝；
`rateLimit` 16993 次命中实为正常日志行 `status=200 ... rateLimit_remain=N/A`）；
② **非现网连接失败**（`翻译失败` 261 条全部集中在 08-17~08-31，09-01 至今 0 条）。

改动：
- **`核心代码/fetch_health_geo.py`**：新增 `ZH_CACHE_FILE`（`health_titles_zh.json`，doc URL→中文缓存）/ `ZH_BATCH=30` / `ZH_CACHE_MAX=2000`；新增 `_load_zh_cache` / `_save_zh_cache` / `_translate_pending` / `_backfill_title_zh`；`collect()` 两条路径在 `_backfill_titles` 后接中译；`_aggregate_by_location` 代表事件带 `title_zh`
- 翻译**复用既有正解** `fetch_news_titles._translate_titles`（同一条 `usage=translate_titles` 配置链，模型 / 平台 / 密钥控制台可改）⇒ **不新增硬编码模型名**（守 G1）
- **开阳**：`healthAdapter.ts` 弹框标题改 `title_zh ?? title` 优先；`contracts.ts` 补 `title_zh?`（版本 1.11.45）

### 验收（2026-10-13 08:03–08:09 实测）

- ✅ 真源 / 运行区 / 容器三处 `fetch_health_geo.py` md5 一致 `3f5964fff0c802405396ba82869fc79d`
- ✅ 容器内实跑 `python3 fetch_health_geo.py` → `status=ok`，30 条中译全部 `status=200`（单条 0.5–1.2s）
- ✅ `health_titles_zh.json` 30 条，含中文 30/30；`health_geo.json` 聚合 185 条中 18 条带 `title_zh`（全部含中文），**英文 `title` 零丢失**
- ✅ 开阳 373 个单测全过（含 `healthAdapter.test.ts` 8 项）；`deploy.sh` 构建 + `chmod a+rX` + HTTP 复验 `index.html` / `index-CJEo0YYE.js` 均 200
- ⏳ 存量补齐（173 条英文标题，30 条/轮 ≈ 6 轮）待完整调度周期后复查（I60）

## v3.8.70（2026-10-10）

**三份低频结构文档内容刷新（v3.8.54 → v3.8.69）** —— CHG-20261010T235013（遗留 ②，P2 完成后用户拍板安排）

改动（只改事实性内容，不改文档结构、不动历史记录段）：
- **`macro-scan/世界推演系统_人类说明文档.md`**：版本头 V3.8.54→**V3.8.69**；GRV **11 维 → 17 维**（16 风险维度 + global_composite）；知识库 **558 → 594** .md（运行区实测）；「文档同步保障」改 pre-commit 第 3 关（`check_doc_sync.py`）+ 每日 08:10 配置巡检九项；架构图移除已退场的 crucix 容器、补天玑 cron / 开阳 / worldsim-pg、天枢端口补 :8900；云端 LLM 清单改配置驱动口径；故障排查表旧模型名改配置口径；第九节补 v3.8.55~v3.8.69 六条里程碑
- **`docs/overview.md`**：版本行统一（天璇 **v2.0.51**、开阳 **v1.11.44** —— 原文首行与架构图**自相矛盾**）；调度任务 49 → **62**；部署命令按部署型重写（原 `/s/world-sim/deploy.sh` 路径**已不存在**）；路线图引用 `ROADMAP.md` → `docs/roadmap.md`；新增「六、模型配置」节
- **`macro-scan/INDEX.md`**：头部版本与生成时间；活跃容器表补天璇 / 天玑 cron / 开阳 / worldsim-pg、镜像 `macro-scan:v7`→**v8**；定时任务 50 → **62**；知识库 558 → **594**；新闻库 crucix 标注退场；**LLM 调用链整段重写**（9 使用点 + 四层兜底 + G1/G2/G4/G5 巡检九项）；关键文件表补 `llm_usage.py` / `check_llm_config.py` / `llm_cfg.py`；维护铁律第 2 条补 pre-commit 第 3 关
- **运行区副本同步**：`/vol2/1000/software/macro-scan/世界推演系统_人类说明文档.md` 原停在 **V3.8.53**（真源 V3.8.54），刷新后与真源字节一致

### 验收（2026-10-10 实测）

- ✅ 全部数字来自实测命令（`cat VERSION` / `cat macro-sim/VERSION` / `grep version kaiyang/package.json` / 容器内 `len(scheduler.JOBS)`=62 / `find 知识库 -name "*.md"`=594 / `SELECT count(*) FROM rag.embeddings`=4156 / 读 `grv_latest.json`=17 键 / `docker ps` 镜像 tag），无一项凭印象
- ✅ 34 处替换全部 `expect==actual` 断言通过（写盘前断言，零损伤）+ 回读验证
- ✅ 断链复扫：3 条相对链接 **0 断链**
- ✅ 旧值残留扫描：当前态旧值（V3.8.54 / v2.0.40 / v1.10.8 / 49 个 / 558 / 11维 GRV / MiMo v2.5-pro / macro-scan:v7 / 50 条）**全部清零**；「11维叙事桶」「4156 块（558 .md）」属**叙事桶维度与 2026-06-30 历史记录行**，按红线 #29 保留不改
- ✅ 运行区副本 md5 == 真源

## v3.8.69（2026-10-10）

**LLM 模型配置重构 P2：天璇 / 天玑接上统一配置链（修 F-1 / F-2）** —— CHG-20261010T231251（承接 question 20261009-llm-usage-static-model-list-stale 的 P2 段；定时任务 b0be59e2 无人值守执行）

准入闸门先过：P1 观察期**覆盖核查**（非唯时长）全绿 —— 守卫 RC=0；账本窗口内 `translate_titles` 412 次 / `general_llm` 4 次（含 10-09 20:00 20:05 20:17 工作日晚间重载 + 10-10 07:00 每日链路）且 `err` 0 行；6 容器 Up 且 RestartCount=0；全日志 `[FALLBACK]` 0 命中；10-10 08:10 新版守卫首次 cron 通过。

改动：
- **新增 `macro-sim/core/llm_cfg.py` + `macro-ji/llm_cfg.py`（字节一致）**：天璇/天玑侧统一取值链 = L1 主配置 `/app/macro_data/llm_config.json` → L2 快照 `.bak` → L3 git 模板 → L4 env（过渡）→ 全链无解则 raise（单次调用失败，不崩溃）；60s TTL 保留原热更行为；回落时打印 `[llm_cfg] ⚠️` 并返回 `source`。**代码中零模型名字面量**
- **`core/llm_client.py`**：删除 4 个模型名常量（`SILICONFLOW_MODEL_GLM/QWEN/NARRATIVE/MODEL`）；`_apply_llm_config` + `_load_usage_cfg` 两条私有链合并为 `llm_cfg.resolve()`；`_resolve_client(usage_id)` 按平台映射取 key（配置永不带 key）；`test_connection()` 改测 `sim_mc`/`sim_narrative` 两个在用使用点。**`QWEN` 常量删除**（实测仅 `__main__` CLI 基准对比用途，无对应配置使用点），顺带修掉原 `max_tokens` 未定义的 NameError
- **`core/chronicler.py` / `core/readable_report.py`**：`_resolve_chronicle()` / `_resolve_readable()` 改走链 ⇒ **F-2 前半/后半修好**；`generate_chronicle` 解析失败即跳过、`generate_readable` 解析失败降级机械模板（永远有产出）
- **`macro-ji/llm_judge.py`**：`MODEL = os.environ.get("VERIFY_LLM_MODEL", …)` 删除，改 `llm_cfg.resolve_endpoint("verify_llm")` ⇒ **F-1 修好**（控制台改 `verify_llm` 终于生效）
- **`macro-ji/docker-compose.yml`**：删 `VERIFY_LLM_MODEL` 注入（原属 P3，与 P2 同窗口 recreate 零边际成本故合并）；**`macro-ji/Dockerfile`** COPY 行补 `llm_cfg.py`
- **`macro-sim/docker-compose.yml`**：补 `${MACRO_SCAN_DIR}/config:/app/shared_config:ro` —— ⚠️ **挂载点必须是 shared_config 不能是 /app/config**：镜像内 `/app/config/agents.yaml`（`run.py:31/135/973` 依赖）会被宿主 config 目录覆盖导致天璇启动即崩（方案原文写的 `/app/config` 与代码现实不符，属机械适配已就地修正）
- **`scripts/check_llm_config.py`**：G1 扫描范围 `macro-scan/` → **全仓**（实测覆盖 190 个 .py）；新增检查项 9 **G5 跨容器副本字节一致**（防 `llm_cfg.py` 两份改一处漏另一处，红线 #81）

### 验收（2026-10-10 实测）

- ✅ **特征值探针实跑**：临时把 5 个使用点改成 `P2PROBE/*` → 天玑主容器与 cron 容器实跑 `llm_judge._call_llm`（urlopen 打桩不花钱不发请求），捕获外发请求体 `model=P2PROBE/verify-llm`；天璇 `_resolve_chronicle/_resolve_readable/_resolve_client` 四个使用点全部返回对应特征值。还原后 `md5` 与改前**完全一致**（`RESTORE_OK`）
- ✅ 容器内 md5 == 真源：`llm_cfg/llm_client/chronicler/readable_report` × 天璇、`llm_cfg/llm_judge` × 天玑（主 + cron）**6/6 SAME**
- ✅ `StartedAt`（天璇 23:20:22、天玑 23:21:18 CST）晚于真源码落盘时间（23:16:25 / 23:17:27 CST）；6 容器 RestartCount=0
- ✅ `/api/v1/control/llm-usage` 9 使用点仍全 `config_source=truth`；控制端 health 200
- ✅ `check_llm_config.py` RC=0（真源=模板=git；G1 全仓 0 命中；G2=truth；G4 哨兵；G5 一致）
- ✅ **守卫实效阳性对照**：人为注入一处模型字面量 → G1 命中 1；破坏 `llm_cfg.py` 一份 → G5 命中 1，还原后 0（证明守卫不是空转）

### 遗留（不阻塞闭环）

- **P3**：`_local_model` base_url/key 深度统一评估；`llm_cfg` 的 L4 env 兜底（`VERIFY_LLM_MODEL`）待摘除
- **②**：3 份低频结构文档内容刷新（仍 v3.8.54）—— 评估时点已到（P2 完成）

## v3.8.68（2026-10-09）

**死防线清理 ①③：移除孤儿脚本 `check_doc_drift.py` + 运行区 `AGENTS.md` 旧副本** —— CHG-20261009T231536（承接 question 20261009-doc-sync-guard-dead 遗留段）

改动：
- **`核心代码/check_doc_drift.py` 删除**（真源 `git rm` + 运行区 `rm`）：三项证据确认孤儿死脚本 —— crontab 0 命中、`scheduler.JOBS` 0 命中、`logs/doc_drift.log` 末次记录 2026-07-01（约 100 天零执行）；判据过时（比对已停更的 `TuiYan_CHANGELOG.md`，只比 mtime 不看内容，2026-08-28 full-audit LOW 项已定性）。备份 `_rollback/doc-sync-cleanup-20261009/`
- **`核心代码/gen_docs.py`**：`OFFLINE_TOOLS` 移除 check_doc_drift 条目 → `python3 核心代码/gen_docs.py --target manifest` 再生 `docs/FILE_MANIFEST.md`（离线工具表 6 → 5 条）
- **`docs/operations/runbooks/doc-sync-install-uninstall.md`**：勘误段「未激活/保留待定」→「已移除（2026-10-09）」；组件表行 + 组件说明行同步标注
- **运行区 `AGENTS.md` 旧副本删除**（Sep-12 版，28 KB；运行区非 git 工作区、无任何工具读取）：真源 `world-sim/macro-scan/AGENTS.md` **不动**

### 验收（2026-10-09 实测）

- ✅ 活动引用清零：`gen_docs.py` / `FILE_MANIFEST.md` / 运行区 `核心代码/` 中 `grep -c check_doc_drift` = **0**（历史文档中的记载属历史记录，未改动）
- ✅ pre-commit 第 3 关双演练：**删 `核心代码/*.py` 且缺联动文档 → 拦截 RC=1**（精确报缺 CHANGELOG+VERSION+FILE_MANIFEST）；**补齐 → 放行 RC=0**；本批真实提交过门
- ✅ 真源＝运行区 md5 一致（gen_docs.py / FILE_MANIFEST.md / runbook / CHANGELOG / VERSION）；运行区 `check_doc_drift.py`、`AGENTS.md` 已不存在

### 遗留（不阻塞闭环）

- 3 份低频结构文档内容刷新（错过 11 个版本）—— **评估时点：10-10 P2 任务完成后**

## v3.8.67（2026-10-09）

**文档同步防线修复 + 文档治理校准** —— CHG-20261009T183228（question 20261009-doc-sync-guard-dead）

目标：修复 2026-06-29 建立的「文档同步保障机制」全线失效（check_doc_sync 判据停在旧仓库结构且未接入现役 hook、check_doc_drift 无任何调度、死框架配置残留），并校准文档条款与现实的偏差。

改动：
- **`核心代码/check_doc_sync.py`（重写）**：判据适配 monorepo（`macro-scan/核心代码/`）；收敛为「底线矩阵」＝ ★ `核心代码/*.py` 变更须同步 `CHANGELOG.md` + `VERSION`、★ 新增/删除 .py 须同步 `docs/FILE_MANIFEST.md`；`compute_missing()` 纯函数化（可单测）
- **`.githooks/pre-commit`**：新增「第 3 关：联动文档同步」（调用 check_doc_sync；解释器或脚本缺失时跳过不拦，防环境差异误拦）
- **`AGENTS.md`（治理校准）**：CHG 命名示例 `-macro-scan.md` → `-world-deduction.md`（×2）；任务粒度「每个文件一条」→「按工作块分组（≥5 个文件合并）」；「pre-commit 会自动拦截」宣称准确化（★ 标记＝自动拦截项，其余为人工 checklist）；3 份低频结构文档（人类说明文档 / docs/overview.md / macro-scan INDEX.md）条款降级为「结构/对外能力实质变化时」；首次接手指引改 `git config core.hooksPath .gethooks`
- **`.pre-commit-config.yaml` 删除**（与 hooksPath 冲突的死框架配置）；运行区同名副本一并清理
- **`docs/operations/runbooks/doc-sync-install-uninstall.md`**：头部加「2026-10-09 现状勘误」段
- **`gen_docs.py` + `docs/FILE_MANIFEST.md`**：`check_doc_drift.py` 描述改「未激活」（原称 automatic 与实际不符）；`check_doc_sync.py` 改「自动（.gethooks/pre-commit 第 3 关）」

### 验收（2026-10-09 实测）

- ✅ 单测：`check_doc_sync.py` 判据 6 用例全过（正反例 + 边界）
- ✅ 集成演练：staged 缺 `CHANGELOG.md`/`VERSION` → 第 3 关拦截并精确报缺；带齐 → 放行（本批真实提交过门）
- ✅ `sh -n .gethooks/pre-commit` 语法通过；真源＝运行区 md5 一致

### 遗留（不阻塞闭环）

- `check_doc_drift.py` 未激活（判据待适配；修复激活 or 移除待定）
- 3 份低频结构文档内容刷新（错过 11 个版本）待单独立项
- 运行区 `AGENTS.md` 长期未同步（Sep-12 旧版）——处置方案待定

## v3.8.66（2026-10-09）

**LLM 模型配置重构 P1：模型名单点化 + 四层兜底 + 防漂移守卫** —— CHG-20261009T124233（question 20261009-llm-usage-static-model-list-stale）

目标：消灭「模型名真源 13 处、升级漏改必漂移」的结构性缺陷。P1 范围＝天枢侧 + 守卫（天璇/天玑接配置 = P2、compose 余项 = P3）。

改动：
- **`核心代码/llm_usage.py`（重构核心）**：
  - 新增 `_FALLBACK_MODELS` / `_FALLBACK_EMBED_MODEL` —— **全仓唯一模型字面量区**（职责＝「别崩」非「用最新」）；`PLATFORMS.models` 静态清单清空（下拉走实时 `/models`）
  - 使用点 **7 → 9**（新增 `call_local` / `readable`；`translate_titles` 静态平台校正为 siliconflow）；`LLM_USAGES.default_model` 统一 None
  - `load_config()` → **四层兜底**（L1 配置 → L2 `.bak` 快照 → L3 模板 → L4 代码兜底），回落打印 `[FALLBACK]`，新增 `get_config_source()`
  - `save_config()` 写前**自动轮转 `.bak` 快照**（last-known-working；顺序＝候选写 tmp → 轮转 → replace）
  - `_regen_default_template()` 加**再生前校验**（usage 集合不缩水 + platform/model 合法）——坏值不许污染模板
  - `set_usage()` 加**写入前预检**（目标模型须在平台实时 `/models`；`LLM_PREFLIGHT=enforce/warn/off`，拉取失败/空列表放行）
- **`核心代码/hybrid_llm.py`**：删 `SILICONFLOW_MODEL` env 私有链，`call_local` 模型改 `resolve("call_local")` + fallback；`reason(mode="local")` 记账统一 `usage="call_local"`
- **`核心代码/rag_engine.py`**：删 `EMBED_MODEL` env 私有链，兜底改 `fallback_embedding_model()`
- **`核心代码/control_server.py`**：`/llm-usage` 返回加 `config_source`；PUT 走线程池（防预检网络 I/O 阻塞事件循环）
- **`scripts/check_llm_config.py`（守卫升级）**：`STALE_PATTERNS` 补 `mimo-v2.5`；新增 **G1** 代码字面量对拍（ast+tokenize，不依赖硬编码名单）/ **G2** 配置来源报警 / **G4** 模型可用性哨兵
- **compose × 3 + `.env.example`**：删 `SILICONFLOW_MODEL`（D2=C：模型名不再经 env；地址/密钥类不动）
- 文案收尾（G1/G3 上线即抓）：`build_rag_index.py` / `run_macro_analysis.py` / `kaiyang/docs/NEXT_SESSION_HANDOFF.md` 去完整模型 ID

### 验收（2026-10-09 实测，6 条全过）

- ✅ 字面量收敛：`macro-scan/` 内 .py 仅 `llm_usage._FALLBACK_*` 区含模型名（G1 复扫 0 命中）
- ✅ `/llm-usage`：9 使用点全 `config_source=truth`
- ✅ `check_llm_config.py` RC=0（真源=模板=git；G1/G2/G4 全过）
- ✅ 兜底演练：主配置改名 → `[FALLBACK]` 回落 snapshot → 恢复 truth（端到端 `_local_model()` 验证）
- ✅ 快照轮转演练：改一次使用点 → `.bak` 精确保留旧值（双向 diff）
- ✅ 污染防护：缩水 usage 集合 → 模板再生被拒（hash 不变）+ 写入预检拦截无效模型

### 遗留（P2/P3）

- 天璇 `llm_client.py` / `chronicler.py` / `readable_report.py`、天玑 `llm_judge.py` 仍硬编码/仅读 env（F-1 待修）→ P2 接配置
- 天玑 compose `VERIFY_LLM_MODEL` 待删、天璇补 config 挂载 → P2；`_local_model` base_url/key 深度统一 → P3 评估

## v3.8.65（2026-10-02）

**`news_geo.jsonl` 保留窗口灰度第一步：30 天（选项 A 一次性截断）** —— CHG-20261002T004002

实测：**502.9 MB / 1,053,598 行 → 265.0 MB / 549,892 行（−47.3%）**，本轮裁剪 **503,994 行**。

改动（`核心代码/fetch_gdelt_geo.py`）：
- 新增 `NEWS_GEO_RETENTION_DAYS`（默认 **30**，`0` = 禁用），**不复用** `NEWS_GEO_WINDOW_HOURS`（=24 h，管派生）
- **模块级硬约束**：`RETENTION_DAYS * 24 >= WINDOW_HOURS * 2`，不满足直接 `RuntimeError` 启动失败
  （防止保留窗口小于派生窗口导致 `news_geo.json` 丢事件）
- 新增 `_in_retention()`，**只在写入侧生效**；`_seen_slot_ts()` 返回 `None` → **保守保留**
- ⚠️ **`after` 语义不变**（仍 `= before + added`）；新增 `written`（实际落盘行数）/ `dropped`（被裁行数）；
  `state.total_events_persisted` 改用 `written` 以反映真实存量
- 新增 INFO 日志 `[retention] 保留窗口 N 天：写入 X 行（裁剪 Y 行）`

数据安全：实施前 `gzip` 备份 → `_rollback/news_geo.jsonl.gz-2026-10-02T004002`
（62.6 MB，**1,053,598 行**，`gzip -t` 完整性通过）。

### 验收

- ✅ **A/B 同基准比对 PASS**：用**备份（裁剪前全量）**按**同一时刻**的 24 h 窗口重建事件集（715 id），
  与裁剪后 `news_geo.json`（719 id）比对 ⇒ **MISSING = 0**，EXTRA = 4（新增增量）
- ✅ 行数 549,892 与观测 `keep30`（549,892）偏差 **0.00%**；`no_ts` 仍 **0/0**
- ⚠️ **原判据曾报 MISSING=6，已定位为判据缺陷（非实施缺陷）**：
  原判据拿 00:34 快照（721 id）直接比 01:04 结果，跨了 30 分钟 —— 该 6 个 id **全部仍在 jsonl（未被裁）**、
  `age = 24.36 h` 已超出 24 h 派生窗口 ⇒ 属**派生窗口自然滑动**淘汰。
  佐证：00:48 轮（旧代码、**未裁剪**）条数已是 **715 < 721**。
  ⇒ 判据修正为「备份按同一时刻重建」的 A/B 比对（见上）。
- 📌 派生文件条数本就在 702–721 间随 24 h 窗口自然波动，逐 id 比对必须**同基准**。

### 遗留

- ⚠️ **无新增轮次不裁剪**：`need_write` 依赖 `new_events`，GDELT 全失败（本次 00:45/00:48 两轮 `all_failed`）
  时不重写文件 ⇒ 该轮不裁剪。属正常（下一轮抓取成功即裁），但意味着**裁剪依赖抓取成功**。
- 备份点为 00:40 快照，00:40 之后新增的行（数百行）不在备份内。
- 灰度第二步 **14 天**：观察 ≥ 24 h 后改 `NEWS_GEO_RETENTION_DAYS=14`。

## v3.8.64（2026-10-02）

**`news_geo.jsonl` 保留窗口：只读观测埋点（不改写入行为）** —— CHG-20261002T000220

背景：jsonl 无界增长（实测 **502.8 MB / 1,052,986 行**，最老行 61.3 天），治本需保留窗口。
主理人拍板 **灰度终点 14 天**，实施前先观测。

改动（`核心代码/fetch_gdelt_geo.py`）：
- 新增开关 `NEWS_GEO_RETENTION_PROBE`（默认 1，`=0` 关闭）与档位 `NEWS_GEO_RETENTION_PROBE_DAYS`（默认 `30,14,7,3`）
- `_merge_jsonl` 内加 O(1) 计数器 `_probe_tally()`：各档存活行数/字节、`seen_slot` 解析失败数
  （**存量 `old` 与新增 `new` 分开统计**）、最老行年龄；返回值新增 `probe` 子键
  （**既有键 `before/added/after/deduped/rows` 语义不变**）
- 调用点落盘 `data/news_geo_window_probe.json`（原子写）+ INFO 日志一行；落盘失败不阻断主流程

⚠️ **本阶段只统计、不过滤、不删除**：写入路径与写入内容逐字不变（`fout.write` 仍写全量行）。

实测（2026-10-02 00:07–00:19 CST，全量扫描 1,052,986 行，`bad_json=0`）：

| 保留窗口 | 行数 | 估算大小 | 占比 |
|:--|--:|--:|--:|
| 现状 | 1,052,986 | 502.8 MB | 100% |
| 30 天 | 549,997 | 265.0 MB | 52.2% |
| **14 天（灰度终点）** | **259,561** | **125.0 MB** | **24.7%** |
| 7 天 | 128,318 | 61.9 MB | 12.2% |
| 3 天 | 64,102 | 30.9 MB | 6.1% |

- 🔑 **关键：`no_ts` = 0（0.00%）** —— 存量与新增行**全部**能由 `seen_slot` / `fetched_at` 解析出时间戳
  ⇒ 过滤阶段**无误删风险**；窗口键沿用 `_seen_slot_ts()`（`sql_date` 仍禁用，09-29 已证伪会丢事件）
- 容器内首轮（00:19）产出：`scanned old=1052986 new=263 | no_ts old=0 new=0 | keep14=259561行/125.0MB | oldest=61.32d`
- 主流程未受影响：`status ok`、`total_after_dedup=1053249`、`news_geo.json` 写出 702 条

## v3.8.63（2026-10-01）

**gdelt_geo 增量合并改流式：单次 RSS 峰值 2437 MB → 181 MB（不删任何数据）** —— CHG-20261001T143514

起因：天枢容器每 15 分钟跑一次 `fetch_gdelt_geo.py --incremental`，进程 RSS 峰值 **2.4 GB**、容器
`memory.peak` **3.6 GB**、主机 swap 已用 2 GiB。根因两层：`data/news_geo.jsonl` 无界增长至
**499 MB / 104 万行**（无条数上限、无时间窗口、无分片），且 `_merge_jsonl()` 每次把整个文件**全量
`json.loads()` 进内存**构建 `rows`（list[dict]，约占 2268 MB）+ `seen`（set，约 51 MB）。

改动（`核心代码/fetch_gdelt_geo.py`）：
- `_merge_jsonl` 改**流式**：新增 `window_start` / `force_write` 参数，边读边写 tmp，
  只在 `rows_window` 中保留派生 `news_geo.json` 所需的**窗口内行**（默认 24 h，`NEWS_GEO_WINDOW_HOURS` 可配）
- **`after` 语义保持** = `before + added`（总行数，`state.TOTAL_EVENTS` 依赖），
  **不是** `rows` 长度；`rows` 由"全量"收窄为"窗口内"，因下游 `_build_news_geo_events` 本就按同一窗口过滤（幂等）
- 空批次（`new_events` 为空）**不重写 476 MB 盘**，仍流式扫描取窗口行供派生
- 调用点 `run_incremental` 传 `window_start`；Route A 注释同步更新

实测（容器内实跑一次，采样 `VmRSS` 373 点）：
- 进程 RSS 峰值 **2436.8 → 181.1 MB（−92.6%）**，结束 RSS 43.6 MB
- 单轮耗时 **149.5 s**（历史 max 墙钟 756 s）
- `news_geo.json` 逐 `id` 比对：实施前 627 / 实施后 628，**missing = 0**、extra = 1（真实新事件），
  字段结构 10 个字段零差集，`schema_version` 仍 1.0
- jsonl 行数 1,044,396 → **1,044,663（+267，只增不减）**；无 `.tmp` 残留

⚠️ **未删任何一行数据**。根因第 2 层（全量加载放大器）已解决；第 1 层（数据无界增长，约 2 万条/天）
**仍在**，保留窗口另行立项（须按 `seen_slot` 而非 `sql_date`，后者已证伪会丢事件）。

配套：本次已 gzip 备份 `_rollback/news_geo.jsonl.gz-20261001T143514`（60 MB）与旧代码
`fetch_gdelt_geo.py.bak-20261001T143514`。

## v3.8.62（2026-09-26）

- fix(hybrid_llm): **降级路径成本归因** —— `call_local` 增加 `usage: str | None = None` 参数；`reason()` 的 `mode="local"` 分支传 `usage="local"`、auto 降级分支传 `usage="general_llm"`；`call_local` 内 **4 处**埋点的 `usage_id=None` 统一改为 `usage_id=usage`。此前 auto 链降级到 SiliconFlow 的调用在账本里记 NULL（只能靠 `platform=siliconflow` 间接区分），现归入 `general_llm` 并可经 platform 区分实际平台；直接调用 `call_local` 不传 usage 时行为不变（向后兼容）。
  ⚠️ **过程修正**：首轮替换**漏了成功路径埋点**——该处写作多行格式（`_log_token_usage(` 与 `usage_id=None` 不在同一行），与其余 3 处单行格式不同，替换断言 `count==3` 通过**未能暴露漏项**；实跑降级路径发现账本仍记 NULL 后反查容器内文件才定位，已补齐并复验（`usage_id=None` 全文件残留归 0）。**教训**：同语义代码存在多种排版格式时，锚点须覆盖全部格式；`count==N` 通过不等于覆盖完整，应以「改后全文残留判据」+「每条路径实跑」终检。
- docs(llm-usage): **使用点数量更正** —— `LLM_USAGES` 实际为 **7 个**（translate_titles / general_llm / rag_embedding / verify_llm / chronicle / sim_mc / sim_narrative），4 处文档仍写「5 使用点」：`macro-scan/AGENTS.md`（兜底模板须一致的使用点数）、`kaiyang/AGENTS.md`（面板说明）、`kaiyang/docs/DATA_CONTRACT.md`（清单标题 + 补 `verify_llm`/`chronicle` 两行）、`llm_usage.py` 预填充注释。历史条目（`NEXT_SESSION_HANDOFF` v1.11.26、`ROADMAP`）保持原样。
- chore(docs): **内网 IP 清理** —— `macro-scan/AGENTS.md` 的 Ollama 停用说明去除内网 IP 字面量；**活跃文档零命中**，剩余 6 处全在历史/归档文档（`TuiYan_CHANGELOG.md`×5、`macro-sim/docs/archive/design.md`×1），按「历史陈述冻结」原则有意保留。CHG-20260926T091845-world-deduction


## v3.8.61（2026-09-26）

- refactor(llm-usage): **使用点 `openai_compat` → `general_llm` 改名**（消除命名误导）—— 该使用点名为「OpenAI 兼容」但**实际指向小米 MiMo**（`token-plan-cn.xiaomimimo.com`，日志统计 2107 次调用），与 OpenAI 账户无关；09-26 该名字曾导致一次真实误判（据名以为「从未使用」）。改动：①代码 7 处（`llm_usage.py` 的 id/name/注释、`hybrid_llm.py` 的 `llm_usage_get_model` 默认值与 auto 链 `usage=`、`silent_failure_probe.py` 注释）；②配置 3 处（运行区 `data/llm_config.json` 的 `usages` 键、真源+运行区 `config/llm_config.default.json` 键与 `_note`）；③文档 4 处（总仓/`macro-scan` AGENTS.md 使用点清单、`kaiyang/docs/NEXT_SESSION_HANDOFF.md`、`kaiyang/docs/DATA_CONTRACT.md` 表格行并顺带更新模型至 v2.6-pro）。
  **未改**：函数名 `call_openai_compat`（改名无收益、改动面大）、env `OPENAI_COMPAT_URL`/`OPENAI_COMPAT_KEY`（注入层，ADR-0013/0015 管辖）、platform `mimo_plan`、CHANGELOG/TuiYan/audit 历史条目、v3.8.27 历史陈述、历史账本既有 `usage_id='openai_compat'` 行（用量流水保留原真）。
  **验证**：`resolve("general_llm")` → mimo_plan/mimo-v2.6-pro ✔；`resolve("openai_compat")` → **None**（`llm_usage.py:327` 未知 id 返 None ⇒ 调用方 fallback env，**降级而非崩溃**，这是本次的安全网）✔；`reason(mode="auto")` 200 且账本记 `general_llm` ✔；`GET /api/v1/control/llm-usage` 的 usages 含 general_llm、不含 openai_compat ✔；**运行区零残留**，真源剩余 5 处均为有意保留（3 处改名说明 + 2 处 v3.8.27 历史条目）✔。
  ⚠️ `llm_usage.py` 被 `control_server` 引用，改动**需重启容器**生效。附带发现（未处理）：`LLM_USAGES` 实际已 7 个使用点（另有 `verify_llm`/`chronicle`），多份文档仍写「5 使用点」，属既有文档滞后。CHG-20260926T085749-world-deduction


## v3.8.60（2026-09-26）

- feat(llm): **模型升级 `mimo-v2.5-pro` → `mimo-v2.6-pro`** —— `openai_compat` 使用点三处同步：运行时 `data/llm_config.json`、默认模板 `config/llm_config.default.json`（真源+运行区，git 跟踪，`data/` 不跟踪时靠它兜底）、`llm_usage.py` 注释。升级前已实测两模型均可用（v2.6 → 200/3.8s）；升级后 `resolve("openai_compat")` 返回 v2.6、`call_openai_compat` 与 `reason(auto)` 均 200。⚠️ 次日需观察 morning/us_daily/china_daily 报告质量。
- fix(hybrid_llm): **重调用成本可归因** —— `reason(mode="auto")` 的 `_auto_chain()` 调 `call_openai_compat` 时**未传 `usage`**，导致账本 `usage_id` 为空（占 8.2 万 tokens 的大头无法归因）。现显式传 `usage="openai_compat"`（对齐既有使用点，未新建）。已澄清：`openai_compat` 是**历史遗留命名**，实际指向小米 MiMo（`token-plan-cn.xiaomimimo.com`，日志统计 2107 次调用），与 OpenAI 账户无关；且 env `OPENAI_COMPAT_URL` 与配置的 `base_url` 完全一致（39 字符），传 usage 前后**端点未变**。
- feat(scheduler): **LLM 用量巡检随项目分发** —— 脚本由 `scripts/check_llm_usage.py` 迁入 `核心代码/llm_usage_check.py` 并注册进 `scheduler.py` JOBS（每日 2110）+ 日志映射。原 `scripts/` 未被 compose 挂载（volumes 仅 `核心代码`、`data`、`entrypoint.sh`），容器内不可见，且 NAS crontab 侧无 `WORLDSIM_APP_PW` ⇒ **挂 NAS crontab 等于本机私货，开源用户无此功能**。迁入后随项目走，clone 即自带；`scripts/` 版已删除。⚠️ `scheduler.py` 改动需重启容器；`GET /api/v1/control/fetchers` 只列 fetcher 类 job，判断 job 是否注册应以 `scheduler.JOBS`（现 62 个）为准。CHG-20260926T084449-world-deduction


## v3.8.59（2026-09-26）

- feat(llm-usage): **token 用量消费侧** —— ①视图 `public.llm_token_usage_daily`，按「北京时间日界 + usage_id + platform + model」聚合 calls/tokens/avg_ms/failures（基表 ts 为 UTC，日界须 `AT TIME ZONE 'Asia/Shanghai'`，直接 `::date` 会错日）；②只读端点 `GET /api/v1/control/llm-token-stats?days=N`，`_check_token` 鉴权（实测无 token/错 token/错头均 401，正确 Bearer 200），返回 total + by_day + by_usage；③告警脚本 `scripts/check_llm_usage.py`，今日用量 > 前 7 日日均 ×2.0 则 ntfy 告警并 exit 1，同日冷却防刷屏，支持 `--heartbeat`。⚠️ 端点生效**需重启容器**（`control_server.py` 无 reload）。
- fix(hybrid_llm): 补 **失败调用记账**（此前 `ok=false` 恒 0，算不出失败率）——在 `call_openai_compat` 的 ValueError/RequestException 最终失败、`call_local` 重试耗尽与**不可重试错误直接抛出**共 4 处记账；重试中间不记（避免重复计数），实测注入不可达地址后入库 `ok=false` 且重试多次只记 1 条。同时修正误导性日志：`ntfy_utils.push_text` 内部吞异常且无返回值，原「已推送」会给出假的送达确认，改为「已发起（送达与否以实际收到为准）」。
- chore: `call_local` 埋点首次验证成功（此前无样本），入库 model=DeepSeek-V4-Flash。⚠️ 附带发现：`usage_id=(none)` 的 14 次调用占 8.2 万 tokens（天璇推演类，单次重），而 translate_titles 703 次仅 4.9 万 ⇒ 成本大头**无法归因**（调用方未传 usage 参数），建议在 `reason()` 链路补 `usage_id`。CHG-20260926T001031-world-deduction


## v3.8.58（2026-09-24）

- feat(hybrid_llm + fetch_crypto_extra): **LLM token 用量账本 + 代理日志噪音消除** —— ①新增 `public.llm_token_usage` 表（ts/usage_id/platform/model/prompt_tokens/completion_tokens/total_tokens/call_ms/ok/err），在 `hybrid_llm.py` 的 `call_openai_compat` 与 `call_local` 两处**非侵入埋点**：从响应 `usage` 字段取**接口返回的真实 token 数**（此前日志里的 `prompt_tokens` 只是 `_estimate_tokens()` 估算），记账逻辑整体 try/except 包裹，**失败只打一行提示、绝不中断 LLM 主流程**；容器内经 `WORLDSIM_APP_PW` + `psycopg`(v3) 建可写连接（`pg_read` 为只读，不可复用）。②`fetch_crypto_extra.py` 取数顺序由「先直连、失败后设代理」反转为「**先走代理、失败后退回直连兜底**」——原顺序下境外站点（binance/kraken）直连必然不可达，每次请求都先留下 1 条 ERROR，形成每日约 280 条的**确定性日志噪音**并淹没真实故障；实测代理对 binance/kraken/google 均返回 200，反转后本次实跑 **新增 ERROR = 0** 且 `status=ok, binance=8 kraken=3` 数据不变。⚠️ 同时订正旧记录「出网代理覆盖不全」：**代理配置完好**（4 个代理变量全部有值、30+ fetcher 使用），真实问题是 failover 顺序导致的日志噪音，非故障、非代理缺失。其余 10 余个同构 failover 文件本次未动（噪音量级集中在 crypto_extra）。CHG-20260924T002608-world-deduction


## v3.8.57（2026-09-22）

- fix(narrative_processor + fetch_hdx): 叙事预处理源列表**接线错位 + 静默失效 + HDX 维度接入** —— `narrative_processor.py` 的 `json_sources` 列表中 `energy.json` / `hdx_latest.json` 两条指向**不存在的文件**（实际产出为 `energy_eia.json` / `hdx_risk.json`；`git log -S` 证这两个文件名从未被任何 fetcher 产出，属建表即错），且 `ingest_from_json_file` 缺文件时**静默 `return 0`**、不打日志 ⇒ 失效长期不可见。DB 实证 `tianji.narrative_chunks` 中 opensanctions / energy_eia / gdacs / hdx / climate_signals **五维全 0 条**，6 条源仅 `sdr_summary` 一条生效。本次：①两处文件名改对；②两处静默 `return 0` 改 `[WARN]` 日志（文件不存在 / 解析失败），`articles` 为空加 `[INFO]` 留痕（语义失配可见化）；③`fetch_hdx.py` 修 naive/aware datetime 缺陷（`if dt >= cutoff:` 位于内层 try 之外，naive 串与 aware cutoff 比较抛 `TypeError` → 每日降级占位），比较前补 `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`；④成功态由 `recent[:10]` 派生 `articles`（纯增量，既有键语义与取值不变），落地源列表里 `source_id="hdx"` 的既有设计意图。实测：`fetch_hdx.py` 由恒 `status=unavailable/parse_error` 转 `status=ok activity=100 updated_30d=25`、`articles=10`；`narrative_processor.py` 实跑 `JSON12条` 且**无「文件不存在」类 WARN**；`tianji.narrative_chunks` 的 `hdx` 来源 **0 → 9 条**。副作用：`disaster_risk` 触发一次密度突增标记（冷启动一次性，仅影响天璇推演该维度 token 预算 2000→3000，**无通知外溢**）。未完成另立：sanctions_risk / disaster_signals / climate_signals 三源的叙事化转换（数值型，属新功能）。CHG-20260922T063404-world-deduction


## v3.8.56（2026-09-19）

- fix(control_server): 开阳地理新闻弹框标题**「点击即翻」** —— `/news-title` 抓到英文 `<title>` 后复用 `hybrid_llm.call_openai_compat(usage=translate_titles)` **即时翻译为中文**返回；已是中文（含 CJK 正则 `[\u4e00-\u9fff]`）原样返回；翻译失败/超时（12s 硬超时）**回退英文**（不阻塞）；新增**有界进程内缓存**（url→中文，上限 500，FIFO）。实测：`record-bee.com`（原英文）→「特朗普政府开始在德克萨斯州的大弯（Big Bend）地区建设边境墙」、`tucson.com` →「缅怀马丁·路德·金 Jr. 对图森的访问」；`indiankanoon.org`（HTTP 403）仍返回空（由前端占位提示兜底）。因 `control_server.py` 无 reload，**重启容器**生效（:8900 约 10s 中断）。CHG-20260919T151618-world-deduction


## v3.8.55（2026-09-19）

- fix(news_titles): 开阳地理新闻层标题中文化覆盖率修复 —— `fetch_news_titles.py` 每轮抓取上限 `NEW_MAX` 40→600（去掉人为截断，一轮补齐全部未覆盖 URL）+ 抓取并发 `CONCURRENCY` 4→8。实测覆盖率 23%（78/340）→ **83.8%（284/339）**，翻译 208/208 无失败、无硅基流动限流，单轮耗时 2m17s（I120 2h 内）。CHG-20260919T142130-world-deduction


## [3.8.52] - 2026-09-12

## v3.8.54（2026-09-12）

- fix(gdelt): DOC 拉取加固（realtime 提案 R1）—— `_fetch_gdelt_recent` 48 请求零 sleep 背靠背（违反 GDELT ≤1 req/2s）、429/503 无重试静默丢数、窗口语义误导。现：请求间 sleep(2) + 429/503 指数退避（2/4s 至多 3 次尝试）+ 窗口语义诚实化（48 文件=12h）+ 成功/失败/重试计数摘要。mock 状态机验证全过。CHG-20260912T184954


## v3.8.53（2026-09-12）

- fix(hypothesis): 模板页脚占位符发送前填充（realtime 提案 R6）—— `system_prompt_hypothesis.md` 页脚 `{date}/{score}/{signal}` 原样透传给 LLM；现于 `hypothesis_engine` 读取点以实际值填充（conf 兜底 N/A）。实测报告输出零污染（`{date}` 0 命中），属模板契约卫生修正。CHG-20260912T144128


### Fixed（fetcher_base 日志目录硬编码致非 root 环境不可用，CHG-20260912T111307-world-deduction）

- `核心代码/fetcher_base.py` 的 `LOG_DIR` 由**硬编码绝对路径** `/var/log/macro-scan` 改为
  `os.environ.get("MACRO_SCAN_LOG_DIR", "/var/log/macro-scan")`（**可配置**，默认值不变）。
- 新增 `resolve_log_dir(data_dir)` 与 `_probe_writable()`：写入前做**可写性探测**，不可写则按
  `LOG_DIR → <data_dir>/logs → <tmp>/macro-scan-logs` 依次回退，**回退时输出 WARNING 留痕**
  （项目红线「任何兜底必须留痕」）；全部不可写时返回 `LOG_DIR`，由 `FileHandler` 显式抛出，**不静默吞掉**。
- **问题背景**：`FetcherBase.__init__` 无条件调用 `_get_logger()`，而 `_get_logger()` 无条件
  `os.makedirs(LOG_DIR, exist_ok=True)` → 非 root 环境下该创建被拒 → 实例化任一天枢 fetcher 即
  `PermissionError`。CI（非 root runner、无该目录）因此 **7 个测试失败**
  （airtraffic×2 / bdi×3 / fao×2）；生产容器（root + `Dockerfile:41` 预建目录）**把缺陷完全掩盖**。
- **影响面**：不止 CI —— **开源后任何非 root 环境**（使用者本机直跑 / 非 root 容器 / 其他 CI 平台）
  都会崩。属**生产代码可移植性缺陷**，非 CI 配置问题。
- 同时恢复基类自述的「失败降级、不抛、不阻断调度」契约在该路径上的成立。

### 验收

- **非 root（uid 1000）+ `/var/log/macro-scan` 不可写** → 回退 `<data_dir>/logs` 并输出 WARNING，不抛异常
- **root（生产等价）** → 仍解析为 `/var/log/macro-scan`，**行为与改动前逐字一致**（无 WARNING）
- **`MACRO_SCAN_LOG_DIR` 覆盖** → 直接采用该目录
- **非 root 跑全目录 pytest（CI 等价）** → **`8 passed, 8 xfailed`（0 failed）**；
  修复前为 `7 failed, 1 passed, 8 xfailed`
- 改动仅 `fetcher_base.py`；`py_compile` 通过；rsync 至运行区后 md5 一致；
  `.py` 由 scheduler 每次新起进程生效，**无需 restart**

## [3.8.51] - 2026-09-12

### Fixed（删除密钥守卫的失效规则 1，CHG-20260912T101550-world-deduction）

- `tests/test_audit_scan_secrets_guard.py` 的规则 1（`_LEAKED_SECRET_LITERALS` 已知泄露字面量黑名单）**已删除**。原因：该黑名单实际存放的是脱敏后遗留的**占位符**（`REDACTED_SPACETRACK_ID` 等），而非真实凭证；而真实凭证与占位符恒不相等、也不含 `REDACTED` 子串 → 该规则**对未来任何真实凭证命中概率为 0**（属「把占位符当秘密」的范畴错误）。
- **触发本次修复的假阳性**：规则 1 对**含注释的整份文件文本**做 `if secret in src` 子串匹配，命中了 `核心代码/fetch_spacetrack.py:4` **注释**里的同名字面量 → CI `macro-scan (pytest)` 长期红。**真实凭证泄露 = 0**，该文件真实代码 L41-42 为干净的 `os.environ.get("SPACETRACK_ID")`（无硬编码默认值）。
- **凭证防护未削弱**：规则 2（`os.environ.get` 非空硬编码默认值）与规则 3（顶层明文赋值）**保留不动**，凭证防护由其承担。
- 原处留注释说明删除理由与溯源，便于后人检索该变量去向。

### 验收

- `pytest tests/test_audit_scan_secrets_guard.py -q` → **`1 passed`**（修复前 `1 failed`）
- 规则 2/3 完好（`_CRED_ENV_NAMES`、顶层明文明文赋值正则均在场）；`py_compile` 通过（`.pyc` 输出至 /tmp，未污染真源）
- 改动仅在 `tests/`，不进运行时路径 → 生产零影响（无 rsync / 无 restart / 无 rebuild）
- 版本联动：`VERSION` + 本 CHANGELOG + `AGENTS.md` + `macro-scan/INDEX.md` + `docs/overview.md` + `世界推演系统_人类说明文档.md` + 中央 `docs/INDEX.md` 版本状态行

## [3.8.50] - 2026-09-12

### Fixed（entrypoint.sh 补可执行位，从零 clone `up -d` 必失败，CHG-20260912T004907-world-deduction）

- `macro-scan/entrypoint.sh` 的 **git 索引模式位** 由 `100644` 改为 `100755`。**文件内容一字未改**（md5 `0507e1fc87b66d6a28c546ee404562a4`）。
- 根因链：`docker-compose.yml` L15 使用**单文件 bind mount** `./entrypoint.sh:/entrypoint.sh` —— 宿主机权限位会**覆盖**镜像内 Dockerfile L44 的 `RUN chmod +x`；而仓库里该文件的模式位是 `100644` → 干净 clone 后 `docker compose up -d` 必报 `exec: "/entrypoint.sh": permission denied`。
- **能潜伏至今的机制**：仓库 `core.fileMode = false`（local 配置），git **不跟踪**工作区模式位变化 —— 真源工作区文件实际是 `755`（本地 chmod 过），但 `git status` 永远干净，改动进不了仓库。这解释了「生产正常、从零 clone 必挂」的分裂现象。
- **已证伪的原假设**：曾推测「`deploy.sh` 的 `rsync -a`（`-a` 含 `-p`）会把真源 644 同步到运行区、覆写运行区 755，致生产下次重启起不来」。实测真源工作区本就是 **755**，`rsync -a` 落盘亦为 755 → **生产侧无此隐患**。该假设作废，留档以免后人重复排查。
- 波及面：全仓另有 69 个「`100644` + shebang」文件，但绝大多数在容器内以 `python3 xxx.py` 调用、不需要 `+x`。按红线「不确定该不该改的，改了比不改更坏」，**本次只改有实测证据的这一个**，其余列入 backlog 待核实。

### 验收

- 仓库层：`git archive HEAD~1` 检出 `-rw-rw-r--`（644）／`git archive HEAD` 检出 `-rwxrwxr-x`（755）—— 前后对照成立
- 干净 clone：`umask 022` 下 `git clone --depth 1` → `ls -l` = `-rwxr-xr-x`，`[ -x ]` = **EXEC_OK**，md5 未变
- 容器 bind mount **双边复现**（生产镜像 `macro-scan:v8`，`--rm --entrypoint sh`，不启服务）：挂 755 副本 → `EXEC_OK`；挂强制 644 副本 → `EXEC_FAIL`，故障机制在容器内实证
- 生产复核：改动前后 17 容器集合一致、8899/8080 均 200、运行区 `entrypoint.sh` 仍 755
- `git diff --cached --stat` = `1 file changed, 0 insertions(+), 0 deletions(-)`（仅模式位）
- 已 push：`f562f07..5722fe6`

## [3.8.49] - 2026-09-11

### Fixed（静默探针预测链 state 写入失败留痕，CHG-20260911T140226-world-deduction）

- `check_predictions_chain` 写基线 state 的 `except Exception: pass` 改为**失败时 append WARN** —— 原写法违反项目红线「**任何兜底必须留痕**」：state 写不进去时探针会持续沿用过期基线且毫无提示，排查时无法区分「真无新增」与「基线没写进去」。
- 同函数**读取** state 处的 `except Exception: pass` **保持不动**：首次运行文件不存在属预期路径，为其告警会制造噪声。
- **独立 CHG，不并入已闭环的 A+B**（`CHG-20260911T111143`）—— 每次变更可独立溯源，避免事后分不清是哪次改的。

### 验收

- 正常路径：容器内完整探针 `PROBE verdict=INFO checks=34 bad=0`，与 v3.8.48 一致 → **留痕未自造告警**
- 失败路径：monkeypatch `os.replace` 抛 `OSError` → `WARN 预测链: 基线 state 写入失败（模拟写入失败），本次基线未持久化，下次将重新判定`
- 测试残留已清理；生产 state 未被污染，仍为 `{"count": 442, "max_created": "2026-09-08T22:12:08.590419+00:00"}`
- 补丁匹配数 `1 == 1` 才写入，`py_compile` 通过

## [3.8.48] - 2026-09-11

### Fixed（静默探针预测链判据修正，CHG-20260911T111143-world-deduction）

- `silent_failure_probe.check_predictions_chain` 判定维度由「绝对行数增量」改为「**行数增长 或 `MAX(created_at)` 前进**」任一成立即刷新基线。原判据 `cnt > last_cnt` 在行数因迁移/清理/去重**回退**后恒为假（实测基线 state 停在 2797 行、`tianji.predictions` 实际仅 442 行）→ `changed_at` 永久冻结 → ntfy 每 2h 推 p4「预测链 20/21 天无新增（442 行）」误报，并将于约 09-20 越过 30 天阈值升级 CRIT。
- 状态文件 `.probe_pred_count.json` 增记 `max_created` 字段；旧 state 无该字段时按**首次基线初始化**处理 —— 本次上线即自愈式重置基线，无需手工改 state 文件。
- 预测链本体健康（天璇 09-08 落 9 条、天玑 09-11 09:30 `verify_geo_auto` rc=0、近 30 天 11 天有写入），告警为误报。**监控能力未削弱**：行数与 `created_at` 均长期不变时 `days` 仍正常累加并在 14/30 天告警。

### 验收

- 容器内连跑两次 `check_predictions_chain()`：首次 `OK 预测链: 基线初始化 predictions 442 行，created_at 2026-09-08T22:12:08.590419+00:00`；第二次 `OK 预测链: 442 行，0 天无新增（正常窗口）`
- 状态文件由 `{"count": 2797, "changed_at": 1787313615}` → `{"count": 442, "changed_at": 1789096540, "max_created": "2026-09-08T22:12:08.590419+00:00"}`
- 改动文件 `py_compile` 通过；探针只读 PG（`SELECT COUNT(*), MAX(created_at)`），不碰采集/分析/写入逻辑
- 已 rsync 进运行区并 md5 复核；探针由 scheduler 每 2h 新起进程，无需 restart 容器

### 附带闭环

- 补同步 v3.8.47 未进运行区的 `核心代码/fetch_bdi.py`、`核心代码/fetch_spacetrack.py`、`VERSION`、`CHANGELOG.md`（md5 已与 git 真源一致）

### 已知限制

- C 项（state 写入 `except Exception: pass` 静默兜底违反「任何兜底必须留痕」）**未做**，待用户评估是否一并处理

## [3.8.47] - 2026-09-11

### Changed（开源收尾，全量检查发现项清理，CHG-20260911T104000-world-deduction）

- **3 处 Windows 路径注释脱敏**（阶段 2/4 路径参数化的遗漏）：`fetch_bdi.py:16` `S:\world-sim\macro-scan\data\` → `<仓库根>/macro-scan/data/`；`fetch_spacetrack.py:4,40` `S:\KEY\Space-Track*.txt` → `<你的密钥文件>`。**后两处暴露密钥文件存放位置**，优先级最高。
- `docs/check-doc-links.py` 的 `S:\docs\INDEX.md` **保留不改** —— 它属 `BAD_TOKENS` 坏链接检测规则本身，非路径引用，改动会使脚本失效；且不含用户名与凭证。
- 删除阶段 5「从零 clone 实测」目录 `_fresh_clone_test`（133 MB）—— 其中 3 份 `.env` 在步骤 8 注入了**生产真实凭证**（未入库、未进历史，但属散落的凭证副本，与「凭证唯一来源」纪律相悖）。

### 验收

- `git grep` HEAD 代码/配置中 Windows 路径与内网信息命中：改前 **4 处** → 改后 **1 处**（仅上述检测规则）
- 两个改动文件 `py_compile` 通过；**注释级改动，无逻辑变化**，不影响运行区（该目录为 git 真源，运行区经 rsync 同步，本次无需同步）
- 测试目录已删，磁盘回收 133 MB

### 已知限制

- **`.git` 130.67 MiB 未 gc**：force push 后 `git fetch` 将旧历史对象一并拉回本地（2 个 pack / 10640 对象），gc 可回收约 66 MB，但会失去本地旧历史副本。**刻意保留** —— 回滚仍有 `_backup_worldsim_20260911T093827`（552 MB）整仓备份兜底。

## [3.8.46] - 2026-09-11

### Fixed（从零 clone 实测，开源实施计划 阶段 5，CHG-20260911T081125-world-deduction）

- **`macro-scan/Dockerfile` pip 源 tuna → aliyun**：`mirrors.tuna.tsinghua.edu.cn` 在本网络不可达，`requests==2.33.1` 报 `No matching distribution found`，导致 `docker build macro-scan/` 必然失败（同批 macro-ji / macro-sim 用 aliyun 源均成功，容器内已装 2.33.1、PyPI 官方源亦有）。`ARG PIP_INDEX_URL` 默认值形式不变，海外仍可 `--build-arg` 覆盖。
- **补两处 compose 插值变量到 `.env.example`**：`macro-scan` 补 `SILICONFLOW_API_KEY`，`macro-ji` 补 `KAIYANG_ORIGIN`。修复前 `compose config` 报 2 条 `variable is not set`，会让从零使用者误判配置错误。
- 根 `README.md`：补 pip 源 / 基础镜像覆盖说明与实测环境提示。

### 验收（干净目录从零 clone 实测，目录 `_fresh_clone_test/world-sim`，HEAD=94bc47e）

| 步骤 | 结果 |
|---|---|
| clone 盘点 | 21 个关键文件到位；`.env` / `知识库/` / `data/` / `kaiyang/dist` 均不存在（阶段 3 隔离性生效） |
| 2 知识库骨架 | `scripts/init_kb.py` ✅ 14 文件 |
| 3 环境变量 | 三份 `.env` 生成；生产有值键 20 个、`.env.example` 覆盖 19，`MACRO_SCAN_DIR` 仅 macro-ji 需要且已在其 example 中，**非缺口** |
| 4 数据库 | `scripts/init_db.sh` 退出 0，21 张表，`vector 0.8.2` |
| 5 前端构建 | `npm ci` 42s + build 96s，dist 11 文件 6.2M（需把 node 所在目录加入 PATH，属本机环境问题） |
| 6 镜像构建 | macro-ji ✅ / macro-sim ✅ / **macro-scan ✅（本次修复后复验通过）**，`requests 2.33.1` 装上 |
| 7 compose config | 三份 exit 0 且 **0 警告**（修复前 2 条 `variable is not set`） |
| 8 启动 | 依赖冒烟 DEPS OK；Web 控制台 200、Control API `/docs` 200、uvicorn 启动完成 |

### 已知限制

- 步骤 8 用 `!override` 改隔离端口 18999/18900 且**只起 web/control、未启 scheduler**（生产占用 8899/8900，起第二份 scheduler 会重复跑定时任务并写生产库）→ 「完整 `docker compose up -d` + 跑一次采集/分析」尚未实测。
- 注入层不完整（55/77 变量未在 compose `environment:` 声明）仍为独立 backlog，改 `env_file` 属行为变更，待单独评估。
- 46 MB wheel `zh_core_web_sm-3.8.0` 仍在仓库；知识库 618 文件与研报仍在 git 历史中 → 阶段 6（filter-repo）待拍板。

## [3.8.45] - 2026-09-11

### Added（可运行性，开源实施计划 阶段 4，CHG-20260911T004121-world-deduction）

- **新增 `scripts/init_db.sh`**：数据库初始化统一入口。一条命令完成：创建 Docker 网络 → 启动 `pgvector/pgvector:pg16` → 建库与角色 → 按序执行 4 个建表 SQL（覆盖 `public` / `news` / `forecast` / `tianji` / `rag` 五个 schema）→ 校验。幂等，不覆盖已有密钥文件；应用密码唯一来源为 `macro-scan/.env`。

### Changed

- **根 `README.md` 重写为开源版**：项目简介 / 能力表 / 组件表 / 架构图（mermaid）/ **8 步 Quick Start** / 配置参考 / 知识库说明 / 文档导航 / 免责声明。移除全部私有环境信息（内网 IP、NAS 绝对路径、Windows 路径、`private` 标注，实测命中 0）；版本号不再硬编码。
- **3 个 Dockerfile 参数化**：新增 `ARG BASE_IMAGE`（默认 `docker.1ms.run/library/python:3.11-slim`）与 `ARG PIP_INDEX_URL`（默认国内加速源），**默认值不变**；海外使用者可用 `--build-arg` 切回官方源。
- **补 3 份 `.env.example` 缺失的 compose 插值变量**：`macro-scan` 加 `KAIYANG_DIR`，`macro-ji` / `macro-sim` 加 `MACRO_SCAN_DIR`（阶段 2 参数化 compose 时遗漏说明，会导致从零 clone 启动失败）。
- 子项目 `README.md` ×4 与 `docs/overview.md` 的私有环境信息通用化（26 处 → `<主机地址>` / `<部署目录>` / `<仓库根>` / `<你的密钥文件>`）。

### 验收（实测）

- 根 README 私有信息命中 **0**；引用的 8 个文件全部存在；mermaid 块闭合
- `init_db.sh` `bash -n` 通过，行尾 LF
- Dockerfile 复验：3 个文件的 `ARG` 声明与变量引用齐全，未参数化的 pip 行 **0**；实测 `docker build macro-ji/` 成功
- 全仓库代码/配置（`*.py` / `*.sh` / `*.yml` / `*.ts` / `*.tsx`）内网信息命中 **0**（保持阶段 2 成果）

### 已知限制

- `docs/` 与子项目的历史文档（CHANGELOG / 审查 / 决策记录，共 70 个文件）仍含内网事实，属审计链原貌，未改动。
- 天玑容器内的 `verify_hypothesis.py` 为 `docker cp` 注入，未持久化进镜像（默认路径不变，功能正常）。
- 本版本 Quick Start 尚未经「从零 clone」实测（属阶段 5），可能存在与实际不符的步骤。

## [3.8.44] - 2026-09-10

### Changed（知识库外置，开源实施计划 阶段 3，CHG-20260910T234442-world-deduction）

- **知识库移出 git 追踪**（617 文件 / 22 MB）。原因：内含 4 个文件为券商研报全文（16 家机构、含免责声明与「未经授权不得复制或引用」条款），属第三方版权内容。`git rm -r --cached` + `.gitignore`，**磁盘文件完整保留**（实测 617 个仍在，运行区 702 个未受影响）。
- **12 处 KB 路径支持 `KB_ROOT` 环境变量**：形式为 `os.environ.get("KB_ROOT") or <原默认表达式>`，未设时取值与改造前**完全一致**。涉及 `build_rag_index` / `mc_engine` / `optim_config` / `run_macro_analysis` / `scorer` / `update_kb_numbers` / `assess_structural_dimensions` / `calibrate_mc` / `monte_carlo_v2` / `daily_narrative` / `weekly_synthesis` / `macro-ji·verify_hypothesis`。
- **缺失引导**：`build_rag_index.py` 与 `assess_structural_dimensions.py` 的缺失分支由静默降级升级为明确提示（指向 bootstrap 脚本与文档）。
- **新增 `scripts/init_kb.py`**：生成知识库骨架（14 个示例文件，**零第三方内容**），支持 `--dest` / `--force` / `--list`。
- **新增 `docs/KB_SETUP.md`**：目录约定、各文件格式要求（含 CSV 21 列顺序）、`KB_ROOT` 用法、RAG 索引构建、缺失降级说明。
- `macro-scan/.env.example` 补 `KB_ROOT` 与 `OPENCLAW_WORKSPACE` 说明。
- `tests/test_audit_scan_secrets_guard.py`：对知识库内文件加存在性跳过（未初始化知识库时属预期情况，不再判失败）。

### 验收（实测）

- `git ls-files` 中知识库命中 **0**；磁盘 617 文件、运行区 702 文件均完好
- 容器内默认路径解析 = `/workspace/知识库/财经知识库`，目录与文件均存在
- **功能零退化**：`mc_engine._load_vol_calibration()` 读到 11 个条目；`scorer.CRISIS_CSV` 读到 41 行
- `KB_ROOT` 覆盖生效；指向不存在路径时输出 bootstrap 引导并以退出码 **1** 结束
- `init_kb.py` 生成 14 文件；CSV 21 列、JSON/YAML 均可解析；8 个 `.md` 可进 RAG 索引
- `py_compile` **14/14** 通过

### 已知限制

- **git 历史中仍有知识库内容**，需 filter-repo 清理（另行 CHG）。
- 天玑（macro-ji）容器内 `verify_hypothesis.py` 未同步（默认路径不变，功能正常），下次重建时生效。
- 知识库自身存在新旧编号目录并存（8 对目录内容高度重叠），属使用者个人资产整理，不在本次范围。

## [3.8.43] - 2026-09-10

### Changed（路径参数化，开源实施计划 阶段 2，CHG-20260910T232600-world-deduction）

- **compose 挂载去硬编码**：同目录挂载改相对路径 `./`（Docker 以 compose 文件所在目录为基准，与原绝对路径**等价**，外部使用者 clone 后零配置即可）；跨项目引用改 `${MACRO_SCAN_DIR}` / `${KAIYANG_DIR}`；`RSSHUB_URL` / `OUTBOUND_PROXY` 由字面量改 `${VAR}`。
- **代理默认值去内网**（19 处）：`PROXY_URL` / `NAS_PROXY_URL` / `GDELT_PROXY` 的默认值 `http://192.168.x.x:7890` → 空串（含 5 处 `os.environ.get` 与 18 处 `except ImportError` 降级表）。真值改由运行区 `.env` 提供，并补齐 compose 注入（此前这些变量**未在 environment 段声明**，配了 `.env` 也进不去容器）。
- **代码路径常量**：`etl_ged` / `ged_analysis`（GED CSV 路径）、`llm_usage`（数据目录）、`macro-sim/llm_client`（key 文件）、`scripts/check_llm_config`（仓库/运行区定位）、`verify_data` / `delete_sqlite_e0c.sh` / `ged_codebook_extract`（含 `C:/Users` 本机路径）。
- **开阳前端**：`DEFAULT_API_BASE_URL` 由写死内网 IP 改为按当前访问主机推导；**信任来源白名单机制保留**（仍为 Set 白名单，仅将静态内网 IP 改为动态取当前 hostname，未退化为通配）。
- **部署脚本归置**：作者环境专用脚本（含 NAS 地址与 `ssh nas`）移入 `scripts/dev/` 并参数化；通用基础设施脚本（`infra/pg/`）参数化后保留原位。

### 验收（实测）

- 非知识库的代码/配置内 `/vol2/1000`、`192.168.31.108`、`C:/Users`、`S:/2026` 命中 **0**（知识库内 10 处随阶段 3 数据外置一并消失）
- 容器 `up -d --force-recreate` 后：挂载 **5/5 实证生效**（容器内可见宿主文件）、control API / web server / 开阳面板均 **HTTP 200**、`py_compile` 与 `bash -n` 全通过
- 代理链路保持（真值落入运行区 `.env` 并成功注入容器）

### 已知限制

- `MACRO_SCAN_DIR` / `KAIYANG_DIR` 仅用于 compose 的 volumes 插值，**不注入容器**（属正常，非缺陷）。
- 发现仍有 **55 个变量代码读取但 compose 未注入**（本阶段只补齐代理类 4 个），属独立的注入层完整性问题，另行处理。

## [3.8.42] - 2026-09-10

### Security（ntfy 主题名轮换 + 注入层环境变量化，开源前置，CHG-20260910T181638-world-deduction）

- **ntfy 两个主题名轮换为 32 位随机串**（告警 / 命令频道各一个）。原主题名长期硬编码在 6 个被跟踪文件中，且代码走 `https://ntfy.sh/` 公共服（匿名可读可写，实测匿名 GET 即返回真实推送正文）→ 主题名一旦随开源公开，任何人可订阅告警、可向命令频道发指令。轮换后旧名自动作废。
- **主题名改为环境变量注入**：`NTFY_TOPIC` / `NTFY_CMD_TOPIC` / `NTFY_URL` 三个 compose 项由字面量改为 `${VAR}`，真值落运行区 untracked `.env`（600）→ **新主题名零字符入库**（提交前 `git grep -lF` 校验命中 0）。与既有 `NTFY_CMD_SECRET` 的注入方式对齐。
- **去掉 5 个 .py 中的硬编码默认值**：`macro-scan/核心代码/observability.py`、`macro-scan/核心代码/weight_matrix.py`、`macro-ji/tianji_verifier.py`、`macro-ji/weight_matrix.py` 的 `os.environ.get("NTFY_URL", "https://ntfy.sh/<旧名>")` → 默认空串；`macro-sim/run.py` 的纯字面量赋值 → `os.environ.get("NTFY_URL", "")`。并给 `macro-sim/docker-compose.yml` 补 `NTFY_URL=${NTFY_URL}` 注入（该文件原本既无 env_file 也无该变量，否则改造后天璇推送为空值）。
- **16 个 md/html 文档中的旧主题名 → `$NTFY_TOPIC` / `$NTFY_CMD_TOPIC` 占位符**（合计 34 处）：文档只描述机制，不再含具体频道名。
- **`.env.example` 补 `NTFY_TOPIC=` / `NTFY_CMD_TOPIC=` 空值模板**。

### 实测

- 运行区 `.env` 写入后复核 3 处全 OK（权限 600）；`docker compose up -d --force-recreate` 后容器内 `NTFY_TOPIC` / `NTFY_CMD_TOPIC` / `NTFY_URL` 均为新值（非旧名）。
- 双频道直连 POST 均 HTTP 200（`event=message`），告警频道 GET 可读。
- ⚠️ **代理对 ntfy.sh 的 HTTPS 不稳定**：经 `192.168.31.108:7890` 的 POST/GET 实测返回 000（`SSL_ERROR_SYSCALL`），直连正常 —— 与 `ntfy_listener.py` 既有注释一致，非本次引入。

### 已知限制

- 手机端 ntfy App 需手动删除旧频道、订阅新告警频道；命令频道改为向新频道发送。
- `macro-sim`（天璇）为 COPY 型部署，**本次未重建镜像**，其 `run.py` 改动待下次自然重建方生效；当前容器内仍是旧代码（纯硬编码）→ 天璇 ntfy 推送暂用旧主题名（旧名仍可用，不中断）。

## [3.8.41] - 2026-09-09

### Fixed（展望简报索引刷新遗漏，v3.8.40 晨间首验发现，CHG-20260909T080058-macro-scan）

- **展望简报落盘后就近刷新开阳报告索引**。v3.8.29 引入的「报告落盘后就近触发 `generate_reports_index.py`」机制（修 07:35 索引抢跑导致当日报告空窗）**原本只覆盖 `save_report`（宏观分析报告）**；而展望简报在主流程中于 `save_report` **之后**才落盘，落盘后无任何刷新动作 → 当日简报最长卡在 **07:35 → 20:35 约 13 小时空窗**、开阳报告中心「30天展望」分组看不到当天份。
- 修法：把该机制抽成模块级函数 `_refresh_kaiyang_reports_index()`（行为不变：subprocess 调 `generate_reports_index.py`、`timeout=180`、失败仅 WARN 不阻断），`save_report` 与**展望简报落盘后**两处共用（DRY）。
- 实测：`reports_index.json` 175 → **176** 条，类型 `30天展望` 65 → **66**，今日 `30天展望简报_20260909_both.md` 即时入库；import 模块无副作用（函数体正确缩进，未退化为模块级执行）。

### 晨间首验（v3.8.40 上线后第一个调度周期）

- 03:10 `reports_ttl_cleanup` 首次真实调度跑通：`分析报告 130 份 / 仿真报告 43 份，超期 0`，无异常（90 天窗口内本就不会删，首次真实删除预计 2026-11 中下旬）。
- 07:30 晨间宏观分析产出 `30天展望简报_20260909_both.md`，新命名生效，源目录旧名残留 **0**。
- 近 12 小时 macro-scan 日志**零** traceback / ERROR / fail；容器 RestartCount **0**。
## [3.8.40] - 2026-09-08

### Added（P3 / question monthly-outlook-daily-and-no-ttl 方案C「改名 + 报告TTL」，CHG-20260908T232303-macro-scan）

- **新增 `reports_ttl_cleanup.py`：报告文件 TTL 清理**。扫**源目录** `docs/分析报告` + `docs/仿真报告`，删除超期 `.md`，默认保留 **90 天**（与 news TTL 同口径，`REPORTS_TTL_DAYS` 可覆盖），支持 `--dry-run`；日期判定「文件名日期优先（`YYYY-MM-DD` / 紧凑 `YYYYMMDD`）→ mtime 兜底」，异常仅记日志不阻断。调度每日 **03:10**（错开 `news_ttl_cleanup` 03:00）。副本 `data/reports/` 与 `reports_index.json` 由既有 `reports_index` 任务（0735/2035）自行同步，TTL 脚本不重复负责。

### Changed

- **「月度简报」改名「30天展望简报」**（`月度简报_{YYYYMMDD}_{country}.md` → `30天展望简报_{YYYYMMDD}_{country}.md`）：产物语义本就是滚动 30 天展望（警戒级别 / 指标快照 / 反馈回路 TOP3 / 地缘快照 / 阈值红绿灯 / 30 天观察日历），但生成动作挂在每次宏观分析末尾（每工作日 3 次：07:30 both / 20:00 us / 20:15 china），「月度」命名与日频×3 的实际严重错配。改动点：`run_macro_analysis.py`（文件名模板 + 日志标签 + 正文 H1）、`generate_reports_index.py`（类型改 `30天展望`，关键词保留 `月度简报` 兜底）、`dashboard.py`（glob pattern + 卡片标题）。
- **一次性数据迁移：历史 65 份 `月度简报_*` 重命名为 `30天展望简报_*`**（脚本执行，残留旧名 0，副本由 `generate_reports_index` 同步清理）。历史文件**正文不改**（保留原貌，随 TTL 自然淘汰）。

### 已知限制

- 90 天窗口内不会出现实际删除（现有报告最早 2026-08-10），首次真实清理预计 2026-11 中下旬触发。
- 历史简报正文 H1 仍为「月度宏观简报（Executive Briefing）」（新产出已改为「30天展望简报（Executive Briefing）」）；dashboard 卡片标题与正文 H1 重复属既存行为，本次未改。
## [3.8.39] - 2026-09-08

### Added（P2 / question fred-japan-jgb-lag-probe-spam 解法A「MOF 日频源治本」，CHG-20260908T203337-macro-scan）

- **新增 `fetch_mof_jgb.py`：日本 10Y 国债日频源（日本财务省 MOF）**。FRED 上 `IRLTLT01JPM156N` 仅有 OECD 月/季/年系列（无日频版本，2026-09-03 频率筛选已核实），官方最新长期滞留在 `2026-06-01`（滞后约 99 天）。MOF 提供**公开无鉴权** CSV：`jgbcme.csv`（Current，仅当月）+ `historical/jgbcme_all.csv`（1974~，全量日频 1.2MB / 13k 行）。**每次两源都拉并取并集**（同日期 current 覆盖 all），规避 current 月度文件跨月重置导致的丢数风险。解析按表头名定位 `10Y`（不硬编码列下标）、日期 `YYYY/M/D` 补零规整、跳过休市空行与 `-` 值。
- **写入范围只补本地末行之后**：既有 450 行 FRED 月度历史（1989~2026-06）保持不变，MOF 仅追加 `2026-06-02` 起的新日期 —— 避免把月频历史改写为日频而污染回测与窗口语义。**口径切换点 = `2026-06-02`**（此前 OECD/FRED 月频，此后 MOF 日频，口径略有差异，跨期对比需注明）。
- **失败语义（沿用 spacetrack 教训）**：HTTP/解析失败 → 单源失败降级继续（另一源仍可用）、双源均失败 `raise` 并非零退出，**保留上次成功值、不写 0**；写前自动备份 `IRLTLT01JPM156N.csv.bak-<时间戳>`，按 date 去重（keep=last）+ 排序 + `tmp → os.replace` 原子写回。
- **调度**：`scheduler.py` JOBS 新增 `mof_jgb` 日档 **05:38**（排在 `fred_fetch` 05:30 之后、`fred_freshness` 05:40 与每 2h 的 `silent_probe` 之前）。
- **探针条目**：`silent_failure_probe.FRED_LAG_WATCH` 日债条目备注 `日债 10Y(月)` → `日债 10Y(MOF日频)`，`max_lag` **90 → 10**（保留 90 会让「数据又停滞 3 个月」再次静默 3 个月才告警 —— 这正是本次要治的病）。

### 验收

- 语法 + 容器内实跑：`450 → 518 行`，新增 68 行（`2026-06-02` ~ `2026-09-07`，末值 `2.935`）；**二次连跑 0 新增**（去重生效，行数不变）
- 失败态（容器内 mock）：单源坏 → 降级由另一源完成；双源坏 → `BOTH_FAIL_RAISE_OK`，CSV 行数与末行**不变**（519 / `2026-09-07`），不写 0
- 探针 dry：`[OK] fred 日债 10Y(MOF日频): 最新 2026-09-07，滞后 1 天（阈值 10）`（切换前为滞后 99 天告警）
- 部署：commit `0675631` → rsync → md5 真源=运行区一致（`ad739cae…` / `df4d2746…`）→ `docker restart` → Up；`JOBS` 含 `mof_jgb`（05:38），`OUTBOUND_PROXY` 未丢

### 注意

- 每日拉全量 1.2MB（低频、无鉴权），对 MOF 无实质压力；容器内**直连即通**（代理仅作回退兜底）。
- `scan_weak_signals.scan_japan_carry_risk` 仍**实时调 FRED**（第 578 行，不读本地 CSV），本次换源后该信号仍用 OECD 滞后值 → 转 backlog（改动需评估月频+日频混合序列下 `vals[-4]` 的「3 个月」窗口语义漂移）。

## [3.8.38] - 2026-09-08

### Fixed（P2 / backlog「fetch_spacetrack 登录校验与失败态（开阳清零掩盖层）」，CHG-20260908T192626-macro-scan）

- **`_get_session` 登录校验响应体**：Space-Track 对错误凭证返回 **HTTP 200 + `{"Login":"Failed"}`**（非 4xx），旧逻辑仅判断 `status_code != 200` 会误判登录成功，错误推迟到下游查询才以 401 暴露——这正是开阳宇宙监视静默清零 10 天 / 40 次 401 零告警的直接掩盖层。现增加响应体校验：body 解析为 JSON 且含 `Login` 键即 `raise RuntimeError` 并附 body 前 200 字符。登录成功时 body 为空串，不受影响。
- **`collect()` 失败态（禁止粉饰）**：`"status"` 由硬编码 `Status.OK` 改为按查询结果判定——核心查询 `all_active is None` → `Status.UNAVAILABLE`；核心成功但子查询有 `None` → `Status.PARTIAL`；全部成功 → `Status.OK`。新增 `error` 字段记录失败摘要；**非 OK 时沿用上次成功值**（读旧 JSON 的数值字段），避免面板显示 0 造成"清零"式误导；无旧文件时才写 0。
- **`limit` 截断修正（数值口径变化）**：实测 `all_active` 原 `limit=30000` 返回恰好 30000（= limit，截断）、`starlink` 原 `limit=10000` 返回恰好 10000（截断），OneWeb 654 未触顶。现 `all_active` → `limit=100000`（`_query` 新增 `timeout` 参数，该调用设 120s）、`starlink`/`oneweb` → `limit=30000`。**面板数值修正为真实值：`total_active` 30000 → 35048、`starlink` 10000 → 11083**（`by_type` 与 `military_large_payload` 同步变化）。
- **探针新增 `check_feed_status`**：独立复核 `data/spacetrack.json` 的 `status` 字段，`unavailable` → CRIT、其余非 ok → WARN，并进 ntfy。**复用 `check_fred_lag` 的 notified-state 冷却**（同一 state 文件、key 前缀 `feed:`），状态指纹未变则降级 INFO 不重复推送，恢复 ok 后自动清标记。已注册进 `run_probe`。

### 验收

- `python3 -m py_compile fetch_spacetrack.py silent_failure_probe.py` → `SYNTAX_OK`
- **登录校验（容器内 mock）**：HTTP 200 + `{"Login":"Failed"}` → `raise`（旧代码会误判成功）；HTTP 200 + 空 body / `{}` → 正常通过未误伤；HTTP 500 → 仍拦截
- **探针冷却（隔离环境）**：`status=unavailable` 三连跑 → `CRIT` / `INFO`（已通知过，状态未变）/ `INFO`；置回 `ok` → `OK` 且 state 键清除；`status=partial` → `WARN`
- **生产实跑 `fetch_spacetrack.py`**：`写入 ... active=35048`，落盘 `status=ok` / `error=null` / `starlink=11083` / `oneweb=654` / `payload=19434` / `debris=12521`（对比备份旧值 `active=30000` / `starlink=10000`）
- **探针 dry**：新增 `feed 开阳宇宙监视(spacetrack): status=ok`，`checks=34`（新增 1 项）
- **部署**：commit `ab117e0`（改码）→ rsync → md5 真源=运行区一致（`540d3912…` / `36bc5c80…`）→ `docker restart` → Up

### 注意（数值口径）

本次为**修正为真实值**，非故障：`total_active`、`starlink` 及派生的 `by_type`、`military_large_payload` 均会上升，开阳宇宙监视面板数字将出现一次性跳变。

## [3.8.37] - 2026-09-08

### Fixed（P2 / question kaiyang-spacewatch-spacetrack-zeroed，CHG-20260908T130113-macro-scan）

- **Space-Track 凭证转义污染修正（开阳「宇宙监视」清零根因）**：`macro-scan/.env` 第 11 行 `SPACETRACK_PASS` 实际值为 16 字符，比 `S:\KEY\Space-Track KEY.txt` 正确值**多一个反斜杠** —— 写入时 `!` 被转义为 `\!`。该错误值经 compose 注入容器，导致自 2026-08-30 起连续 10 天（40 次）SATCAT 查询返回 401，开阳面板全 0。**修正**：Python 精确替换（不经 shell）+ 备份 `.env.bak-20260908T130113`（600）+ `docker compose up -d --force-recreate` 重新注入 env。
- 根因更正：此前判断的「Space-Track 外部账号/凭证失效」**不成立**，Space-Track 账号与本地 KEY 均有效，纯属我方配置写入污染。

### 验收

- 三方非明文对拍：本地 KEY `len=15 sha16=6b8ad45ee4b93922` vs `.env` `len=16 sha16=ff500d0f24c6a028`；字符类别序列定位到 index 2 多插入一个符号
- 实测两套凭证：`LOCAL_KEY` 登录 body=`""` → 查询 HTTP **200**；`.env` 登录 body=`{"Login":"Failed"}` → 查询 HTTP **401**
- 修正后容器内 `printenv SPACETRACK_PASS` → `len=15`；关键 env 抽查 `WORLDSIM_APP_PW`/`CONTROL_TOKEN`/`FIRMS_MAP_KEY` 3/3 未丢
- 实跑 `fetch_spacetrack.py`：首次 `Read timed out`（容器刚 force-recreate 网络未稳，偶发），重试两次均成功 `active=30000 payload=14837 debris=12321 starlink=10000 new30d=268`，与 08-29 末次成功值吻合
- 落盘 `data/spacetrack.json`：`total_active=30000`、`updated=2026-09-08T05:05:29Z`、`status="ok"`

### 遗留

- 脚本健壮性缺陷**未修**：`_get_session` 只校验 HTTP 状态码、不校验登录响应体（Space-Track 对错误凭证返回 200 + `{"Login":"Failed"}`）；`collect()` 查询失败仍写 `status:"ok"` + 全 0。二者叠加使本次配置错误**静默 10 天无告警**，已转 backlog 待另立 CHG。
- Starlink `limit=10000` 截断精度 bug 仍在（本次实测 `starlink=10000` 即上限值）。

## [3.8.36] - 2026-09-08

### Fixed（P2 / question fred-japan-jgb-lag-probe-spam 解法B，CHG-20260908T111550-macro-scan）

- **静默失败探针 FRED 滞后告警冷却**：`silent_failure_probe.check_fred_lag` 新增 notified-state（`.probe_fredlag_notified`，机制严格参照既有 `GED_NOTIFY_STATE`）——WARN/CRIT 以「序列 + 末行日期」为指纹，指纹未变则降级 INFO 不重复推送。修复日债 `IRLTLT01JPM156N` 滞后期间 ntfy 每 2h 刷屏（09-03~09-08 累计约 60 条）；末行日期前进或恢复健康后自动清标记并恢复推送能力。
- **FRED 增量写入去重**：`fetch_fred_history.save_series` 增量路径（mode="a"）改为「读旧 CSV → 合并 → 按 date 去重（keep=last）→ 排序 → tmp+os.replace 全量写回」。根因：FRED 在 `observation_start=last+1` 无新数据时仍返回末行观测，旧逻辑无去重地 append，导致日债累计 155 行同日重复（696 行 vs 官方 450 行）。读旧 CSV 失败时回退原追加语义。
- **数据清理**：`data/fred_history/IRLTLT01JPM156N.csv` 一次性去重（先备份 `.bak`），696 → 450 行，与 FRED 官方 450 数据行完全吻合，末行真值 `2026-06-01,2.67` 保留。

### 验收

- 容器内连跑两次 `silent_failure_probe.py --dry`：首次 `WARN`（推送）、第二次 `INFO`（已通知过，不重复告警），state 文件 `data/.probe_fredlag_notified` 正确落盘
- 容器内 `save_series` 去重冒烟：同一行 3 次增量追加 + 1 条新值 → 结果仅 2 行数据，表头与排序正确
- 清理后 CSV 450 数据行 = FRED 官方 450 数据行；改动文件 rsync 后 md5 真源=运行区一致（1ffd9b41… / bce0e88f…）
- commit `b7045ad`；容器 restart 后状态 Up 正常

## [3.8.35] - 2026-09-03

### Added（P2 / question llm-key-ui-write-path + llm-config-doc-drift Enforcement，CHG-20260903T164000，ADR-0015）

- **密钥控制台 write-only 通道**（恢复 v3.8.28 误删的 UI 填写，且不明文入库）：`llm_usage.py` 新增 `get_secret`（mtime 缓存热读取）/`set_platform_secret`（原子写 `config/.env` 0600）/`secret_status`（掩码+来源）；`control_server.py` 新增 `POST /control/llm-secret`（write-only）+ `GET /control/llm-secrets`（掩码）；key 解析次序统一「config/.env 优先 → 进程 env 兜底」，**保存即热生效免 recreate**；存量密钥服务端迁入 `config/.env`（untracked + `**/.env` 双 gitignore）
- **兜底模板自动再生钩子**：`set_usage` 成功路径自动再生 `config/llm_config.default.json`——UI 改模型后模板结构性不可能漂移（五联第②联自动化）
- **巡检脚本 `scripts/check_llm_config.py`**：五检查（真源=模板 / 运行区模板=git 模板 / 活跃文档旧模型名[历史叙述+archive+CHANGELOG 豁免] / .env 安全面 / pre-commit hook），TSX crontab 每日 08:10 + 周一 08:20 心跳，失败 ntfy 告警（内容无密钥值）；SSH 手改真源等钩子盲区由此兜底
- **pre-commit hook**：拒绝任何 `.env` 入库（防密钥上 GitHub 末道闸）
- **开阳前端 v1.11.37**：`LlmConfig.tsx` 恢复密钥框（password write-only + 掩码状态展示）；`controlApi.ts` `getLlmSecrets`/`setLlmSecret`；`control.ts` `LlmSecretStatus`

### Fixed（Enforcement 首跑揪出）

- `hybrid_llm.py` 残留 `os.environ.get("OPENAI_COMPAT_MODEL")` 死兜底删除（compose 已删该变量，杜绝双源复活）
- `llm_usage.py` L98 注释措辞更新（去旧 env 引用）；AGENTS.md compose 示例块密钥指引 key.txt → config/.env
- 巡检脚本自修复：archive 目录名级跳过（原 `docs/archive` 前缀不匹配 `macro-scan/docs/archive`）、TuiYan_CHANGELOG 前缀豁免、git 侧 check-ignore 改 repo 内路径、脚本不扫自身

### 验收

- 容器冒烟：get_secret 热生效 / 写后掩码 / 0600 / 模板再生一致；密钥值 grep 无 git 跟踪命中
- 巡检脚本 EXIT 0 全绿；模板运行区=git 真源 md5 一致；开阳 tsc+vite build 通过 + dist 同步 8080 就绪
## [3.8.34] - 2026-09-03

### Fixed（P1 / question llm-config-doc-drift，CHG-20260903T151756，用户路由清扫）

- **LLM 配置/文档漂移清扫（ADR-0010 未落地实证）**：运行区 `data/llm_config.json`（09-02 固化）为唯一真源，但默认模板 + 13 份文档/代码 docstring 停留在收敛前旧栈（MiniMax-M3 / Qwen3.5-27B 叙事 / mimo-v2.5），全量扫描后逐一同步：
  - 默认模板 `config/llm_config.default.json` 5 使用点对齐运行区（translate→Hunyuan-MT-7B / sim_narrative→DeepSeek-V4-Flash / openai_compat→mimo_plan+mimo-v2.5-pro / 删 sim_minimax / platform `mimo`→`mimo_plan`）
  - `docker-compose.yml` 移除残留 `OPENAI_COMPAT_MODEL=mimo-v2.5`（与 v3.8.27 声明一致，消除错误模型兜底）；`docker-compose.example.yml` 清 `MINIMAX_*`、改 `SILICONFLOW_MODEL`→DeepSeek-V4-Flash
  - 文档同步：macro-scan AGENTS.md / INDEX.md / FILE_MANIFEST.md / 世界推演系统_人类说明文档.md / 根 AGENTS.md / STATUS.md / kaiyang AGENTS.md / DATA_CONTRACT.md / NEXT_SESSION_HANDOFF.md / macro-sim_人类说明文档.md — 降级链统一为 MiMo v2.5-pro → DeepSeek-V4-Flash → 纯数据报告；翻译 Hunyuan-MT-7B
  - 代码 docstring/静态清单：`hybrid_llm.py` / `run_macro_analysis.py` 降级链；`llm_usage.py` PLATFORMS 模型列表 + LLM_USAGES 默认（translate→siliconflow/Hunyuan-MT-7B）/`fetch_news_titles.py` 翻译注释
- **加固 ADR-0010 Enforcement**：macro-scan/AGENTS.md 补「模型变更五联同步」强制 checklist（运行区配置 + 默认模板 + compose + 文档 + 代码静态清单），杜绝换模型只更 1 处的再次漂移
- **验收**：默认模板 diff 与运行区一致；grep 全仓无活跃 MiniMax-M3 / Qwen3.5-27B / 非 pro `mimo-v2.5` / `OPENAI_COMPAT_MODEL=mimo-v2.5`；历史文档（CHANGELOG/archive/reviews/ROADMAP）未改动

### 关联
- questions/world-deduction/20260903-world-deduction-llm-config-doc-drift.md（⚠️→✅ resolved 待归档）
- operations/CHG-20260903T151756-world-deduction.md
- decisions/world-deduction/0010（ADR-0010 文档漂移治理，本次补 Enforcement）

## [3.8.33] - 2026-09-03

### Added（P3-3 / question l4-tail-scenario-modeling，方案 C 降级折中版，用户拍板）

- **L4 极端尾部烈度建模**：hypothesis_templates.yaml severity_params 新增 L4 节「崩坏/极端尾部」（vix_mult 2.5 / lambda_mult 6.0 / sigma_mult 3.5 / regime_force stress；calibration: expert-assumption 显式标注专家情景假设非历史校准；keywords 全多字词防误判——核战争/全球大流行/小行星撞击等）
- **历史类比禁用于 L4**：hypothesis_engine.get_historical_analogies 对 severity=="L4" 不做 percentile 系数外推（L4 无历史样本，外推属伪精确），改返回固定情景假设区间（spx -60/-45/-30、vix_delta 50/70/90、gdp -30/-20/-10），source 标注「L4情景假设（非历史校准）」；L1-L3 逻辑不变（整体收进 else）
- **永不升格🟢覆盖 L4**：置信度信号 no_green_triggers 分支 `sev == "L3"` → `in ("L3", "L4")`
- **ntfy 推演通道放行 L4**：ntfy_listener.py 烈度白名单 ("L1","L2","L3","L4") + sev_label 加「崩坏/极端尾部」
- **验证（容器内冒烟，零 LLM 调用）**：py_compile 过；parse「核战争/全球大流行」→L4、「台海紧张」→L2 不误判；L4 impacts=情景假设区间+标注；L3 source 仍=历史类比；三方 md5 一致（git 真源/运行区/容器）+ docker restart
- **后续完整版入 backlog**：概率型/情景型分组推演（L4 走独立情景分析模式，hermes-systemic 9.5 原方向）——用户拍板「早晚要完善，记的加进后续计划里」

### 关联
- questions/world-deduction/20260903-world-deduction-l4-tail-scenario-modeling.md（⚠️→✅→归档）
- decisions/world-deduction/0014-l4-tail-severity-modeling.md（ADR-0014）
- operations/CHG-20260903T125000-macro-scan.md

# macro-scan CHANGELOG — 天枢（数据采集/分析层）

> 文档类别：实录（RECORD）· CHANGELOG
> 版本锚点：`S:/world-sim/macro-scan/VERSION`

## [3.8.32] - 2026-09-03

### Fixed（P2-5 / question calibration-score-no-decay + 前置阻塞 bug）

- **propagation_paths.yaml 解析修复**：`atomic_paths:` 映射键打断顶层 list 致 ParserError，被 `_load_propagation_paths()` 的 `except Exception` 静默吞掉——25 条传导路径（20 主 + 5 原子）从未加载，维度2 恒兜底 0.2。现原子路径并入顶层 list（键无代码消费），实测加载 25 条
- **置信度时间衰减**：20 条主路径按 data_quality 历史锚点补 `last_verified`（12 条），`hypothesis_engine._cal_decay()` 应用 `max(0.5, 0.98^年数)` 衰减因子于维度2 加权（L563 avg_cal）；无锚不衰减。参数可调
- 注意：修复后维度2 从恒 0.2 变为真实计算，推演概率输出将变化（预期修复效果）；完整推演回归交由下次常规调度验证
- CHANGELOG: v3.8.24 停更的 TuiYan_CHANGELOG.md 已废弃（AGENTS 导航待更新，另案）

## v3.8.31 — 2026-09-03 天枢 news_ttl_cleanup 功能批次入库：PG news.articles 90 天 TTL 清理（08-30 已部署，本次补 git 记录）

### 变更
- 【commit c94978c — question 20260903-world-deduction-ttl-cleanup-uncommitted（P2）收编，用户拍板「按顺序来吧」】
  - 入库 “核心代码/news_ttl_cleanup.py”（3121B，08-30 建）：PG news.articles TTL 清理，保留 90 天（NEWS_TTL_DAYS env 参数化），更早行 DELETE
  - 入库 “核心代码/scheduler.py” +2：JOBS 注册 news_ttl_cleanup（每日 03:00，“1-7”）+ LOG_FILES 注册 news_ttl_cleanup.log
  - VERSION 3.8.30 → 3.8.31（git 真源 + 运行区双端；该文件经 grep 实证无代码消费、容器不挂载，属纯文档锚点）
  - ⚠️ 本次为补记录而非新部署：git 真源 / 运行区 / 容器三方 md5 全同（2afc1122…）实证功能 08-30 起已在运行，此前仅缺 git 记录（“部署先于入库”第三次，同 kaiyang D3 08-06 先例）

### 关联
- questions/world-deduction/20260903-world-deduction-ttl-cleanup-uncommitted.md（⚠️ → ✅ → 归档）

---
## v3.8.30 — 2026-09-03 P5 退役：天枢 verify 域三旧脚本退役（验证功能 2026-08-24 已迁天玑收编）

### 变更
- 【commit ea518a9 — question 20260824-world-deduction-verify-domain-consolidation / 20260823-world-deduction-verify-ownership-misplacement（P5 收尾，用户拍板执行）】
  - 删除 “核心代码/verify_geo_auto.py” / “verify_hypothesis.py” / “verify_predictions.py”（git 真源 + 运行区双端）——现行调度已在天玑 tianji_verify_cron（geo_auto 每日 09:30 / predictions 每月 1 日 09:00 / hypothesis 每月 1 日 09:15），天枢三文件为 2026-08-24 存量收编后的旧残留；宿主/容器 crontab、scheduler JOBS、ntfy 指令通道全入口 grep 核查无引用后删除
  - “核心代码/ntfy_listener.py”：退役 cmd_verify 指令通道（函数块/路由分支/help 行三处），防删文件后 ntfy verify 指令断链；py_compile 通过；运行区 md5 双端一致（b339f74f…）
  - “verify_reads_e0c.py” 保留（E0 审阅域与验证域独立）
  - VERSION 3.8.29 → 3.8.30
  - 已知过时待后续：tests/test_audit_scan_scheduler_verify.py 断言 scheduler JOBS 应含 verify_predictions（审计 #13 xfail 回归设计），随本退役语义反转，建议改为“JOBS 不应含”（不在本次范围）

### 关联
- questions/world-deduction/20260824-world-deduction-verify-domain-consolidation.md（⏸ → ✅ → 归档）
- questions/world-deduction/20260823-world-deduction-verify-ownership-misplacement.md（母题，归档）
- 背景：P4 月度对账（09-01 窗口 verify 两任务首次自动触发 + 43 条补跑）全维度通过后执行既定 P5 收尾

---
## v3.8.29 — 2026-09-03 开阳报告索引时序竞态修复：save_report() 落盘后就近刷新开阳数据源

### 变更
- 【commit 113410b — question 20260902-kaiyang-report-index-race（P2）修复，用户拍板方案 A】
  - “核心代码/run_macro_analysis.py” “save_report()”：ntfy 推送后、return 前新增 REINDEX 段——报告写盘成功后 subprocess 调同目录 “generate_reports_index.py”（timeout 180s），即写即刷新 “data/reports_index.json” + “data/reports/”，解耦索引重建与调度时序；触发失败仅 [WARN] 打印，不阻塞报告保存/ntfy 推送
  - “scheduler.py” 07:35（工作日）/20:35（每天）定时重建保留作幂等兜底（不删）
  - VERSION 3.8.28 → 3.8.29

### 关联
- question “questions/world-deduction/20260902-world-deduction-kaiyang-report-index-race.md”（⚠️ 已定位待修复 → 修复完成）
- CHG-20260903T072540-world-deduction（Pre/Post 闭环）
- 背景：晨报 07:30 cron 启动、LLM ~07:36 完稿；scheduler 07:35 索引重建抢跑 → 报告落 07:36~20:35 空窗（ntfy 已推、开阳不显示）

---
：控制台 api_key 写入通道封死（密钥只走 .env，ADR-0013）

### 变更
- 【commit 94939af — question 20260902-llm-config-key-plaintext（P1）修复】
  - “核心代码/llm_usage.py” “set_usage”：非空 api_key 硬拒 → (False, “密钥禁止经控制台写入：请配置于 NAS macro-scan/.env …”)；entry.pop(“api_key”) 清历史残留——config 持久化永不带 key（docstring 同步）
  - “核心代码/control_server.py” PUT /api/v1/control/llm-usage/{usage_id}：docstring 更新（key 禁走此路，set_usage 兜底拒收并返回明确错误）；body 透传保留
  - 前端配套（kaiyang v1.11.36）：LlmConfig.tsx 删 key 输入框 + controlApi.ts updateLlmUsage 去 apiKey

### 关联
- question “questions/world-deduction/20260902-world-deduction-llm-config-key-plaintext.md” → ✅ resolved 归档
- ADR-0013 secret-injection-normalization（密钥只走 .env）
- 与 “20260822-llm-keys-plaintext-in-git”（compose 明文进 git）同源不同面，共同闭合 world-deduction 密钥注入规范

---

## v3.8.27 — 2026-09-02 LLM 平台收敛：mimo_plan/mimo_api 拆分 + openai_compat 模型固化 config + 移除预置 OpenAI 平台

### 变更
- 【commit eb47031 — mimo 平台拆分：mimo→mimo_plan + 新增 mimo_api】
  - `核心代码/llm_usage.py`：`PLATFORMS` 的 `mimo` 重命名 `mimo_plan`（显示名“小米 MiMo Plan”，token-plan 端点与 `OPENAI_COMPAT_KEY` 映射不变）；新增 `mimo_api`（显示名“小米 MiMo API”，base_url `https://api.xiaomimimo.com/v1`，env `MIMO_API_KEY`）；LLM_USAGES 引用 `platform:"mimo"` 的 3 处默认值同步 → `mimo_plan`；`env_name` 表同步 + 新增 `mimo_api→MIMO_API_KEY`
  - `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 同步（`mimo_plan`）+ 新增 `mimo_api→MIMO_API_KEY`
  - `data/llm_config.json`（运行态）：`openai_compat.platform` `mimo`→`mimo_plan`
  - `docker-compose.yml`：env 段新增 `MIMO_API_KEY=${MIMO_API_KEY}`（`config --quiet` 通过）；`.env` 加 `MIMO_API_KEY=` 占位（待用户填 `ak-` key 后 `docker compose up -d` 生效）
- 【commit 368e3d6 — openai_compat 模型固化 config + 移除预置 OpenAI 平台】
- `data/llm_config.json`：`usages.openai_compat.model` 固化 `mimo-v2.5-pro`（原经 env `OPENAI_COMPAT_MODEL` 注入、开阳仅显示"（env 默认）"不可见不可改）→ 开阳 effective_models 直接显示真实生效模型、下拉可改
- `docker-compose.yml`：移除 env `OPENAI_COMPAT_MODEL=mimo-v2.5-pro`（隐藏开关，与 config 双源易漂移；`OPENAI_COMPAT_URL` 保留——`reason()` 无 usage 路径依赖它定 base_url）
- `核心代码/llm_usage.py`：`PLATFORMS` 移除预置 `openai`（api.openai.com，从未被任何 usage 引用、未配 key，初始脚手架残留）；`env_name` 表同步删除
- `核心代码/hybrid_llm.py`：`_PLATFORM_ENV_KEYS` 移除 `openai` 行（`reason()` 的 `mode=="openai"` 分支与 CLI `--reasoning` choices 保留——其语义为 OpenAI 兼容协议指向 MiMo，与 api.openai.com 平台无关）

### 关联
- 命名决议（用户拍板）与实施规划见 `decisions/world-deduction/20260902-world-deduction-add-mimo-api-provider.md`（status: planning → implemented）
- `morning.log`/`us_daily.log` 实证宏观分析经 `reason("auto")` → `call_openai_compat`（无 usage）→ env URL + config model 生效路径

---

## v3.8.26 — 2026-08-28 P2: PG news.articles TTL 清理

### 新增
- `核心代码/news_ttl_cleanup.py`：每日清理 `news.articles` 中超过 TTL_DAYS（默认 90 天）的行；timedelta 参数化、dry-run 计数先行、VACUUM ANALYZE 后置（失败不阻断）
- `scheduler.py`：`JOBS` 加 `news_ttl_cleanup`（每日 0300）+ `LOG_FILES` 对应条目

### 备注
pg_dump 备份已由 `/vol2/1000/software/worldsim-pg/backup-pg.sh`（每日 0400，保留 14 天）独立覆盖，无需重复注册。

---

## v3.8.25 — 2026-08-27 F1 commit 2: 天璇 GRV 轨迹 feed 导出

### 新增
- `核心代码/tianxuan_grv_export.py`：扫 `docs/仿真报告/*_grv_traj.json`，按 `generated_at` 幂等导出最新轨迹到 `data/tianxuan_grv.json`；M4 版本护栏、保留旧 feed + 告警（不静默写空）、M6 幂等跳过重写
- `scheduler.py`：`JOBS` 加 `tianxuan_grv`（I30）+ `LOG_FILES` 对应条目
- `silent_failure_probe.py`：新增 `check_tianxuan_grv()`（内容 `generated_at` 判据，非 mtime）
