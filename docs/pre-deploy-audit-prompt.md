# world-sim 部署前全面排查

## 任务背景

world-sim 是一个三组件宏观推演系统（macro-scan 天枢 v3.8.6 / macro-sim 天璇 v2.0.17 / kaiyang 开阳 v1.7.2），运行在家用 NAS（192.168.31.108）的 Docker 容器中。

本次 session 是**部署前最后一次全面排查**，代码已在本地完成修改，尚未同步到 NAS。

**排查目标**：发现任何可能导致部署后系统行为不正确、静默失败、或难以调试的问题。范围是**整个代码库**，不限于最近修改——历史积累的代码同样可能存在问题。

优先级：
1. 会导致系统启动失败或关键功能断路的问题（P0）
2. 会导致仿真/预测结果不可信的逻辑错误（P0/P1）
3. 接口不匹配、数据格式问题（P1）
4. 设计意图与实现不一致，或文档与代码不符（P2）
5. 潜在的安全风险（P1）

---

## 必读文档（按顺序，每步完整读）

1. `AGENTS.md`（根目录）— 系统全貌与三子系统定位
2. `HANDOVER.md` — 当前状态、所有变更、已知问题、部署清单
3. `docs/arch_review_20260802.md` — 15个已确认设计缺陷，了解哪些已修（D1/D4/D7/D12）、哪些未修（D2/D3/D5/D6/D8-D15）
4. `macro-sim/CHANGELOG.md` 前150行 — 天璇完整变更历史
5. `macro-scan/TuiYan_CHANGELOG.md` 前150行 — 天枢完整变更历史
6. `ROADMAP.md` — 时间门控任务和已知积压问题

---

## 排查维度（多 agent 并行，≤15个请求）

请用**多 agent 并行**覆盖以下维度，每个维度独立、全量排查，不只看最近改动。

### 维度 A：天璇仿真引擎核心逻辑

全量排查 `macro-sim/core/` 下所有文件：`simulation.py` / `world_state.py` / `calibrator.py` / `bifurcation.py` / `agents/base.py` / `agents/financial.py` / `agents/geopolitical.py` / `agents/social.py`

排查要点（新增改动 + 历史积累）：
- **D1修复验证**：per-agent delta 是否覆盖所有12个 Agent 的所有行动分支？有没有某个行动还在直接写 `delta["key"] = ...` 而不走 `add()`？
- **D4修复验证**：`china_credit_impulse` 允许 [-1, 1] 负值，乘以 0.92 衰减后方向正确；`us_fiscal_pressure` 的 min/max 截断逻辑在衰减后是否仍然适用？
- **历史问题：D2/D3**（arch_review 确认未修）：校准循环 calibrator.py 的误差函数对象是外生变量（grv/credit_spread/t10y2y/dff），而 Agent 行动改变的是内生变量——这个校准逻辑是否会导致参数调整方向系统性错误？
- **历史问题：D6**（arch_review 确认未修）：校准结果是否在重启后丢失？calibration_state 文件是否存在？
- **历史问题：D8**（arch_review）：`bifurcation.py` 里固定 predict_steps=24，没有动态停止条件——这个硬编码对结果质量有什么影响？
- **历史问题：D10**（arch_review）：双峰检测 bug——`_detect_bifurcation()` 的分叉判断逻辑是否存在阈值问题导致漏检？
- `agents/base.py`：`decide_with_trace()` vs `decide()`——`simulation.py` 的 `step()` 调用的是哪个？causal_chains 字段在运行时是否真的为空？
- `run.py` 整体流程：daemon 模式读取 sim_trigger.json 的方式，inode 断链修复（目录挂载）是在 docker-compose 配置里还是代码里？

### 维度 B：天枢数据采集与信号管道

全量排查 `macro-scan/核心代码/` 核心模块：`scheduler.py` / `geo_risk_vector.py` / `slow_variables.py` / `grv_threshold.py` / `control_server.py` / `startup_checks.py` / `fetcher_base.py`

排查要点：
- **新问题：control_server.py 安全性**：`rerun` 端点接受 `fetcher_ids` 列表，直接拼接 `f"{fid}.py"` 作为脚本路径，是否做了白名单校验防止路径遍历？
- **新问题：geo_risk_vector social_stress 空字典**：`scan_weak_signals.py` 写出的 social_stress 是 `{country: score}` 字典，只含 score≥20 的国家；当天所有国家都低于20时字典为空——`geo_risk_vector.py` 聚合时 `sum(ss.values()) / len(ss)` 会抛 ZeroDivisionError 还是返回 0？
- **新问题：startup_checks.py 误报风险**：`KNOWN_GRV_DIMENSIONS` 包含 social_stress/cultural_friction（13个），但 source_dimension_map.yaml 的 primary 字段只有11个原始维度，social_stress/cultural_friction 不在映射文件里——校验逻辑会不会把这两个当作"未知维度"误报 ERROR？
- **历史问题：grv_threshold.py**：GRV 触发天璇的阈值逻辑，台海阈值68是绝对值还是相对值？D5（arch_review 未修）指出这个阈值在正常 GRV 范围内可能永远触达不到。
- **历史问题：scheduler.py 30秒主循环**：JOBS 里有 I15（每15分钟）和日档（固定时间）混合，30秒循环间隔对 I15 任务是否足够精确？有没有任务被跳过的风险？
- **历史问题：各 fetcher 的降级逻辑**：fetcher_base 的 `load_previous_good()` 在数据不可用时保留旧值——旧值最老能有多旧？有没有 staleness 上限保护？

### 维度 C：接口契约与数据流完整性

全量排查数据流的每个关键节点：

`geo_risk_vector.py` 产出 → `grv_latest.json` → `world_state.load_from_macro_scan()` → `MacroWorldState`
`scheduler.py` → `sim_trigger.json` → `run.py --daemon`
`macro-sim` → `forecast_tracker.db` → 天玑

排查要点：
- **schema_version 不一致**：geo_risk_vector.py 写出 grv_latest.json 时用的字段名是 `_schema_version` 还是 `schema_version`？`load_from_macro_scan()` 验证时用的是哪个？两边不匹配会抛 RuntimeError 阻断仿真。
- **接口契约文档声称13维**，实际 grv_latest.json 中有多少个字段是真正被天璇 MacroWorldState 消费的？有没有字段写出了但从未被读？
- **predictions 表写入**：`_archive_to_tianji()` 写入时字段数量与 DDL 是否一致？有没有新增字段但 INSERT 语句未更新的情况？
- **sim_trigger.json 格式**：grv_threshold.py 写出的格式，与 run.py daemon 模式读取时的解析逻辑是否匹配？有没有字段缺失导致 KeyError？
- **历史问题：news_export.json schema**：macro-sim `load_from_macro_scan()` 读取 news_export.json 时验证 schema_version，但 news_export.py 产出时是否每次都写入正确的 schema_version？

### 维度 D：kaiyang 前端全量排查

全量排查 `kaiyang/src/` 关键组件：`App.tsx` / `components/WorldPanel.tsx` / `FlatMapPanel.tsx` / `GlobePanel.tsx` / `hooks/useFeed.ts` / `lib/controlApi.ts` / `lib/grvAdapter.ts`

排查要点：
- **2D/3D 切换时序**：WorldPanel 切换到 flat 时，FlatMapPanel 从 `invisible` 变为 visible，但 Leaflet 地图容器在 invisible 时 `clientWidth/Height = 0`，切换后需要调用 `invalidateSize()`——FlatMapPanel 的 `active` prop 变化时是否已处理这个时序问题？
- **useFeed 重复请求**：多个组件调用 `useFeed('grv')` 会各自发一次请求，没有去重——实际运行时有多少个组件在消费 grv？会不会造成频繁请求？
- **control API 错误处理**：`controlApi.ts` 的 `apiFetch()` 在网络错误时抛异常，但 control_server 可能还没启动——UI 层有没有 try-catch 防止控制面板崩溃？
- **grv_latest.json 缺失字段降级**：`grvAdapter.ts` 读取 GRV 数据时，如果某个维度字段缺失（值为 null 或不存在），降级逻辑是什么？会不会导致 NaN 传入渲染层？
- **历史问题：GRV 数据时效性警告**：kaiyang 顶部状态栏显示 GRV 更新时间，如果 GRV 超过24小时未更新是否有视觉告警？用户是否能发现数据已过期？

### 维度 E：系统整体：配置/部署/安全/可观测性

排查 `deploy.sh` / `macro-scan/docker-compose.yml` / `macro-sim/config/agents.yaml` / `macro-scan/核心代码/observability.py` / `HANDOVER.md` 部署清单

排查要点：
- **entrypoint.sh 缺失 control_server**：HANDOVER 明确说"需手动追加 control_server.py 启动行"——这是部署阻塞项，当前 entrypoint.sh 内容是什么？追加后是否需要重建镜像？
- **agents.yaml 挂载方式**：macro-sim 的 docker-compose 里 agents.yaml 是 volume mount（热更新）还是 COPY 进镜像（需 rebuild）？CHANGELOG 有历史矛盾记录，当前实际配置是什么？
- **data/ged/ rsync 风险**：GED 产物不进 git，deploy.sh macro-scan 使用 rsync——如果 rsync 命令包含 `--delete` 标志，NAS 上的 `data/ged/` 会被删除；如果没有 `--delete`，则 NAS 上的旧数据文件也不会被清除。实际 deploy.sh 怎么写的？
- **历史问题：D11**（arch_review 未修）：`situation_level` 参数在 run.py 里被传入但 simulation.py 不使用——这个参数现在走哪条代码路径？是真的无效还是有隐式效果？
- **observability.py 三数字推送**：daily_health_push 推送的是 GRV时间戳/降级fetcher数/predictions行数——predictions 行数取自哪个数据库路径？路径是否与 `_TIANJI_DB_PATH` 一致？
- **credentials 暴露**：macro-scan/AGENTS.md 里明文写了 `FRED_API_KEY=REDACTED_FRED_KEY`——虽然 FRED key 是公共低风险的，但其他配置文件（optim_config.py, docker-compose.yml）是否有更敏感的 key 明文存在？这些文件是否在 .gitignore 中？

---

## 输出要求

五个维度分别产出报告，格式：

```
## 维度 X 排查报告

### ✅ 验证通过
- 条目：具体证据（文件路径:行号 或 代码片段）

### ⚠️ 疑问/风险（需人工确认）
- 条目：描述 + 为什么不确定 + 建议确认方式

### ❌ 确认问题（建议修复）
- 条目：问题描述 + 根因 + 影响范围 + 修复建议
```

五个报告完成后，输出一份**部署风险清单**：

```
## 部署风险清单

### P0（部署前必须修复）
- [问题] [来源维度] [修复方案]

### P1（建议修复，可部署但风险已知）
- [问题] [来源维度] [影响]

### P2（文档/设计问题，不阻断部署）
- [问题] [来源维度]

### 部署前人工确认项
- [ ] 条目（需要在 NAS 上确认）
```

---

## 约束

- Claude agent 请求总数 ≤15个
- **全量排查，不限于最近改动**——历史代码同样可能有问题
- 不修改任何代码，只读+报告
- 对不确定的地方明确标注"需人工确认"，不要猜测
- 发现问题时给出具体文件路径和行号，不要泛泛而谈
- 如果某个问题在 arch_review_20260802.md 里已被记录为已知缺陷，标注"已知缺陷 Dxx"而不是重复描述
