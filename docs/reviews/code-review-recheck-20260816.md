# world-sim 修复复查报告（Recheck，只读）

- **对象**：`S:\world-sim`（北斗七星：天枢 macro-scan / 天璇 macro-sim / 开阳 kaiyang / 天玑 macro-ji + 玉衡 / 数据层 PG）
- **日期**：2026-08-16
- **触发**：项目方在 `code-review-20260815.md`（Track A，79 条发现）基础上实施了一批修复后，要求做一次**全量只读复查**——确认哪些真修好、哪些不全、哪些未动、以及本轮新代码是否引入新问题。
- **方式**：主 Agent 亲核安全/控制面簇 + 8 个只读 Agent 并行核各修复簇 + 3 个对抗式证伪 Agent 复核推理型结论。全程 Workflow 编排，≤12 并发。
- **性质**：**只读产出**。本报告仅新增本文件，未修改任何项目代码/配置/数据。所有 `file:line` 均来自本轮工具输出的源码/`git show`，未臆造对象名。
- **前序文档**：`code-review-20260815.md`（Track A 审查）、`roadmap-recommendations-20260815.md`（Track B 规划）、`code-review-response-20260815.md`（项目方容器复核回复）、`code-review-response-review-20260815.md`（对回复的审阅）。

> ⚠️ **密钥硬约束（仍在）**：本文件位于会 `git push` 的仓库内。项目方已确认 **GitHub 仓库当前私有、故暂不轮换密钥**（见 §5）。本报告不含任何明文密钥值。若仓库将来转公开，务必先轮换 `.git/config` 内嵌 PAT + tracked compose 明文 key 再推送。

---

## 0. 总纲

这批修复**质量高、命中准**——Critical/High 的核心断路点几乎全部对症修好。但存在两个系统性倾向：

1. **"Medium 尾巴"漏修** —— 大修复顺带牵出的 Medium（M08/M11/M26/M31）多数未收。其中 M08 是会让 Brier 算错的真 bug、M31 会积累重复行。
2. **本轮新写的 LLM 配置平台化代码引入功能性回归** —— 静态默认失效、天璇缓存不失效需重启等 3 条经对抗复核确认成立。

结论定性：**不是"改坏了"，是"改到约 80% 停手 + 新功能有毛刺"**。Critical/High 可放心；下一轮应收 Medium 尾巴 + 修 LLM 配置回归。

---

## 1. 真修好了（FIXED，源码已核）

| Track A | 项 | 证据（file:line） |
|---|---|---|
| **C01** | GRV 五常量崩溃 | `macro-scan/核心代码/geo_risk_vector.py:95-112` 五常量全恢复，引用点 126/138/180/296/316 有着落 |
| **C02** | 控制面 fail-open | `control_server.py:79-84` 改 fail-closed（未配 token → 503，不再跳过鉴权）|
| **H02** | token 外泄通道 | `kaiyang/src/lib/controlApi.ts:182-210` 加信任 host 白名单，非信任来源不附带 token |
| **H01** | LAN randomUUID 崩溃 | 新增 `safeUuid()`，`crypto.randomUUID()` 非安全上下文抛错时 fallback，7 处调用点替换 |
| **H18** | sim_trigger.json 空文件崩前端 | daemon 改写合法"已消费"JSON + `schema_version`，三端契约对齐（`run.py:773` 侧）|
| **H19** | GRV 维 None 守卫 | `macro-sim/core/world_state.py:556-562` `grv.get(k) or 默认`，兜住"键在值 None"（C01 联动）|
| **H21** | VIX 恐慌 counter 即触发即归零 | `simulation.py:414` 改上升沿检测，bleed 结构不再永不触发 |
| **H22** | bifurcation 小簇丢弃致概率<100% | `bifurcation.py:175` 改合并到最近簇 + 归一，带 B1 回归测试 |
| **H13** | PG 缺 UNIQUE | `sql/03_b0_schema.sql:36-37` `news.articles` 补 content_hash/url partial UNIQUE，与源侧一致 |
| — | pg_synced_at schema 漂移 | 6 表 DDL 双份回写（`03_b0_schema.sql` + `b0_migrate.py`），代码 INSERT 字段 ⊆ DDL 列 |
| **P0-D** | 天璇 predictions 落表 | H20 去静默（`run.py:666-681` fail-loud ntfy）+ D12 target_metric 对齐（`:595`）+ 原子写（单 try/commit + rollback）；真实推演数据落 PG |
| **P0-D2** | 天玑 SQLite 复活 | `macro-ji/tianji_db.py:43-62` 整体重写纯 PG，psycopg/密码缺失硬 raise，无 SQLite 回退 |
| **P1-A** | Brier 去污染（核心三项）| `macro-ji/tianji_verifier.py`：H03 观测 base-rate（:113-132）/ H04 未决样本隔离返回 None（:187-191）/ H05 结论门控≥20（:397）|
| **H08/H11** | 非原子写 | `fetch_gpr.py` / `verify_predictions.py` 改 `tmp + os.replace`（**仅覆盖 3 点**，见 §3）|
| — | health 口径纠偏 | `observability.py` + `silent_failure_probe.py:357-413` 均对齐 PG `tianji.predictions`，**行数增量检查已补**（14d WARN/30d CRIT）——正是"数月空转无人察觉"的根因 |
| **H12** | 静默失败告警（功能等效）| PG 双写失败经 `pg_write_collection.py:81-115` 模块级默认 hook 自动 ntfy（5min 去抖）；GED 陈旧新增 `check_ged_stale` 探针 |
| — | news-title XSS 收口 | 外部标题在唯一渲染层 `kaiyang/src/lib/mapData.ts:198 escapeHtml` 收口，不流入 raw-HTML sink |

---

## 2. 明确未修（真残留，建议纳入下一轮）

以下结论中 **M08 / observability 两条经对抗式证伪 Agent 复核，反驳失败，确认为真**（见 §4）。

| Track A | 位置 | 后果 | 定性 |
|---|---|---|---|
| **M08** Brier 窗口取反 | `tianji_verifier.py:242`（`ORDER BY verified_at DESC`）+ `:273`（`briers[-8:]`）| 取的是**最旧 8 条**非"最近 8 条"，正确应为 `briers[:8]` | **真 bug、live；但受 `:271` 的 ≥8 守卫 + "恰好 8 条时无差别"限制 ⇒ 仅当某 group 严格 >8 条已验证 brier 才咬人。当前样本≈0-1 → 潜伏未发作** |
| **M31** uuid4 主键 + `ON CONFLICT(id)` 去重恒 no-op | `macro-sim/run.py:573/582`（geo 侧 :639/646 同）| 重跑同一 scenario 插重复行 | 真残留（项目自标"P0-D 延续/延后"）|
| **M11** weight_matrix 两处 `except:pass` | `weight_matrix.py:187-188` / `:394-395` | 权重/拒绝日志写失败被完全吞掉，无 log 无告警 | 真残留，未接任何 hook |
| **M26** pg_read 宕机/空混同 | `pg_read.py:130-141` | `exec_read()` 连接失败/查询失败/真空结果都返回 `[]`，下游无法区分 | 真残留 |
| **observability 宕机推绿** | `observability.py:306/315`（-1 赋值）+ `:319`（alert 只判 `==0`）| PG 断/密码缺时每天 21:00 推 🟢 default，**数据链断了却报健康** | **CONFIRMED（旧账，本轮未改）**；建议把 `<0` 纳入 alert |
| **L03** 锐度标签写反 | `tianji_verifier.py:406` | 印"(>30%或<70%)"恒 100%，实算 `p<0.3 or p>0.7` | 真残留（纯标签，无功能影响）|
| **doc-code 漂移** | `tianji-design.md` | 仍写旧定义（气候基准 0.25 / 样本≥5），代码已更严未同步 | 建议同步文档 |

> **P1-A 实证缺口**：去污染代码**对**，但当前 `predictions` 仅约 10 行、verified 样本≈0-1，远不够 ≥5/≥20 门控，**运行期还无从实证**——报告路径此刻只走"样本<5"早退。玉衡 reweight 那把锁（`MIN_TRIGGER_N=8` + 90 天到期，在 `macro-ji/tianji_verifier.py:42`）是独立的**数据时滞门**（约 3 个月），非写表锁。

---

## 3. 修了但不全（PARTIAL / 残留）

- **C03** —— CORS 已从 `*` 收窄到具体来源（`control_server.py:63-70`），**但 :504 仍 `host="0.0.0.0"`** 绑全网卡。有 fail-closed token 兜底，从"零凭证可控"降为"需 token"，但未做 roadmap 建议的绑回环。
- **内置 CONTROL_TOKEN**（668f3835）—— 构建期经 `VITE_CONTROL_API_TOKEN` 烤进前端 JS bundle（`.env` 未 tracked，**没进 git** ✅），但 LAN 上任何能加载前端者可从 bundle 提取该 token → 配合 :8900 仍绑 0.0.0.0 理论可调用。**单人家用 NAS 威胁模型下属可接受取舍，低残留**。
- **macro-scan/核心代码/tianji_db.py** —— 仍 `os.path.exists`（:161）只挡"文件不存在"不挡空库；`_PG_ONLY`（:123）模块加载时固化（热重载失效）。靠 `WORLDSIM_SQLITE_OFF=1` 生产生效兜底，风险收敛但边角残留。
- **双写死路径** —— `signal_synthesizer.py` / `ntfy_listener.py` 仍以 `WORLDSIM_SQLITE_OFF=="1"` env 门禁保留 SQLite 分支，PG-only 下不可达但源码未物理清除（docstring 仍写"双写"）。
- **H08/H11 只覆盖 3 个点** —— 项目方自陈仓内还有**约 30 处非原子写**登记 P2 未动。

---

## 4. 本轮新代码引入的问题（回归审查 + 对抗复核）

### 4.1 LLM 配置平台化（密钥面干净：`llm_config.json` 已 gitignore，运行时 key 不进 git）

经对抗式证伪 Agent 复核，逐条判定：

| 指控 | 判定 | 位置 / 说明 |
|---|---|---|
| ① 静态默认平台/模型形同虚设 | **CONFIRMED** | `llm_usage.py:196-200` `resolve()` 只读运行时配置；静态 `platform/default_model` 仅供 `effective_models()`（:271-288，前端展示）消费；调用方（`hybrid_llm.py:204`）在 resolve 返 None 时回落 env 而非静态值。全新部署静默回落 env |
| ② translate_titles 发错模型 | **PARTIAL（原表述夸大）** | model 与 base_url 出自同一套 env；仅当 `OPENAI_COMPAT_URL` 设了而 `OPENAI_COMPAT_MODEL` 未设的半配置状态才 model=gpt-4o + base_url=MiMo 错配；URL 全空时 `raise` 快速失败、保留英文标题**不会错发**。故**条件性错配，非必然** |
| ③ 天璇配置缓存永不失效 | **CONFIRMED** | `macro-sim/core/llm_client.py:98-110` `_usage_cache` 懒加载只读一次 + `:33-49` 导入期常量 + `:113-120` client 缓存，三处均无 TTL/mtime/信号失效。改配置须**重启天璇容器**才生效；天枢每次开文件读（热更），**两容器行为不一致** |

- ✅ **一处自我修正（正面）** —— `fe99c96b` 移除了同轮 `eb83d645` 误引入的 anthropic 平台选项（协议不兼容 `/messages` vs `/chat/completions`），本轮内闭环。

### 4.2 其它新问题

- **两个 tianji_db.py 已彻底分叉**（NEW-ISSUE，维护陷阱）—— `macro-ji/tianji_db.py` 纯 PG，`macro-scan/核心代码/tianji_db.py` 仍"SQLite 主写 + PG 旁路双写"过渡态。同名不同实现，改一份不传播到另一份。
- **前端两处 `dangerouslySetInnerHTML`**（Low，隐式不变量）—— `NewsPanel.tsx:63` / `SignalStreamPanel.tsx:212`（旧代码，喂内部 `trigger_titles`）。安全依赖"抓取层 `html.unescape` + 渲染层 `escapeHtml`"的隐式不变量；若将来把新抓取标题接进 `trigger_titles` 即成存储型 XSS。建议在抓取/存储层转义或显式文档化该不变量。
- **hotfix-on-hotfix 两条链**（流程信号，非 bug）——
  - slug 伪标题链：v1.11.19（slug 还原标题）→ v1.11.20（聚合路径同步）→ **v1.11.21 彻底放弃**（`geoAggregate.ts:103-106` 注"slug 与真实标题对不上，实测无意义"）。改两版才发现方法本身错。
  - 点选回归链：v1.11.24（点空白取消选中）→ **v1.11.25（`c2e01393` 修 v1.11.24 引入的事件冒泡回归）**。
  - 提示个别改动未先定位根因即动手。（对比：health 标题因 NAS 出口 IP 持续 429 改抓 doc 页 `<title>`，根因已诊断清楚，属合理切换。）

---

## 5. 关于 P0-A（密钥）

项目方确认 **GitHub 仓库当前私有，故暂不轮换密钥**。据此本报告把 P0-A 从"活跃公开泄露 / 立即轮换"**降级为"私有仓凭证卫生项"**，不催办。

保留一条备注：`.git/config` 内嵌明文 PAT + 两个 tracked compose（`macro-scan/docker-compose.yml`、`macro-ji/docker-compose.yml`）的明文 key，对任何有 NAS 共享读权限者仍可见——**私有 ≠ 零暴露面**。仓库转公开前务必先轮换全部 key + 重写 git 历史清除历史泄露。

---

## 6. 复查方法与可信度

- **覆盖**：安全/控制面簇（主 Agent 亲核）+ P0-D/P0-D2/P1-A/P1-B/P1-C/H 系列（各一只读 Agent）+ 本轮新代码 LLM 配置 / news-title+health（各一）+ 推理型结论 3 簇（M08 / LLM 配置 / observability）对抗式证伪。
- **对抗复核结果**：6 条推理型结论过证伪——**4 条纹丝不动确认为真**（M08、observability、LLM①、LLM③），**1 条（M08）确认但标"当前潜伏"**，**1 条（LLM②）承认原表述夸大、收窄为"条件性错配"**。**无一条被推翻**。
- **一眼定论的直读事实**（M31/M11/M26/L03/C01/C02/H 系列 等）未重复证伪——均为白纸黑字的源码/git 事实。
- **可信度声明**：本报告仅新增本文件，未触碰任何现有代码/配置/数据；未执行 push/build/deploy；所有 `file:line`、字段、函数名均来自本轮工具输出，未臆造。工作量与"当前是否发作"等涉及运行时数据的判断已显式标注为需实证。

---

*本报告为只读产出。修复批次整体质量高；建议下一轮优先收 M08（潜伏 Brier bug）/ M31（重复行）/ observability 宕机推绿 / LLM 配置③（天璇缓存），并统一 M11/M26 的失败可感知性。*
