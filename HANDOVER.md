# 世界推演系统 · 交接文档

> 每次维护后必须更新本文件（规则来自项目规范）。

---

## 当前状态（2026-08-04，by Claude）

| 子系统 | 版本 | 状态 |
|---|---|---|
| macro-scan（天枢）| v3.8.12 | ✅ **已部署 NAS，运行中**（:8899/:8900，Live 模式 STAGING_MODE=0）|
| macro-sim（天璇）| v2.0.23 | ✅ **已部署 NAS，运行中**（Sprint-2/慢变量/D6/天玑V1）|
| kaiyang（开阳）| v1.8.0 | ✅ **已部署 NAS，:8080 可访问**（D3 地图，无伪线）|

- 本地路径：`C:\Users\I327394\Desktop\S\world-sim\`
- Git 分支：`main`，最新 commit：`ad2e975`（天玑V1列名修正）
- NAS 路径：`/vol2/1000/software/world-sim/`

---

## 本次维护摘要（2026-08-04，by Claude）

### macro-scan（v3.8.7 → v3.8.12）

| 版本 | 内容 |
|---|---|
| v3.8.8 | ntfy_utils.py 拆分（push_markdown），解决循环导入；cmd_narrative/weekly/ask 改推 .md 附件 |
| v3.8.9 | 中国三大股市指数接入（上证综合/沪深300/深证成分），kaiyang INDEXES 区显示 |
| v3.8.10 | GED v26.1 接入 russia_europe/middle_east_energy（多 agent 辩论权重 GED×0.30+GDELT×0.70）|
| v3.8.11 | GDELT P95 改为运行时动态计算（样本<100 fallback 硬编码），修复 D9 归一化失真 |
| v3.8.12 | spaCy 3.8+zh_core_web_sm 镜像重建；news_geo_feed.py（07:15）NER 地名→坐标→news_geo.json |

- NAS 镜像：`macro-scan:v3.8.11`（含 spaCy 3.8.14）
- **STAGING_MODE=0**：news.db 时间跨度 53 天，已开启 Live 模式

### macro-sim（v2.0.21 → v2.0.23）

| 版本 | 内容 |
|---|---|
| v2.0.22 | Sprint-2：A2/A3/A6 soul_file 预位激活；慢变量 irp/ucri/gci 注入 MacroWorldState；D6 校准缓存（<7天跳过） |
| v2.0.23 | 天玑 V1 run_scoring() 接线；_send_ntfy_simple；DB 列名修正（final_prob/outcome_value）|

### kaiyang（v1.8.0，无变更）

P0 已完成：scp dist/ 并重启 nginx，:8080 返回 200，D3 地图正常。

---


## 本次维护摘要（2026-08-03，by Claude）

### macro-sim（v2.0.14 → v2.0.18）

| 修复 | 文件 | 内容 |
|---|---|---|
| D1 | simulation.py | per-agent delta 追踪，消除传导矩阵 N 倍放大 |
| D4 | world_state.py | apply_natural_decay 补4个遗漏变量月度衰减 |
| D7 | world_state.py | MacroWorldState 接入完整 13 维 GRV（含 social_stress/cultural_friction）；load_monthly_history/make_world_from_history_row 同步补齐，消除校准期与预测期输入空间不一致 |
| D12 | run.py | _archive_to_tianji content/target_metric 对齐至 global_composite |
| D14 | world_state.py | load_monthly_history 补读 ECBDFR/DEXCHUS；make_world_from_history_row 从历史行读取 ecb_rate/usd_cny，不再硬编码 |

### macro-scan（v3.8.1 → v3.8.7）

| 文件 | 内容 |
|---|---|
| `核心代码/startup_checks.py`（新建）| 天枢启动完整性校验，source_dimension_map 遗漏映射阻断启动 |
| `核心代码/brier_calc.py`（新建）| Brier/BSS/锐度计算，天玑 V1 调用 |
| `核心代码/control_server.py`（新建）| A3a 控制 API，端口 8900，8个端点 |
| `核心代码/geo_risk_vector.py` | social_stress/cultural_friction 从 gdelt_scores 聚合写入 grv_latest.json；WTI 油价接入 middle_east_energy（GDELT×0.45+WTI×0.40+Channel B）；energy_grid_risk 数据源修复（UK Carbon Intensity → 天然气期货价格 NG） |
| `核心代码/scheduler.py` | 每60s落盘状态；读 control_pause.json；startup_checks 接入；LOG_FILES 补 compute_probit |
| `核心代码/slow_variables.py` | 权重外部化；cron 幂等保护；manual_score 降级修复 |
| `核心代码/fetcher_base.py` | load_previous_good() 增加 48h staleness 上限 |
| `核心代码/control_server.py` | rerun 端点加白名单校验，防路径遍历；WORKDIR 修复（/app 而非 /workspace/核心代码）|
| `AGENTS.md` | FRED_API_KEY 明文替换为占位符 |
| `config/grv_weights.yaml` | 追加 slow_variables_weights 节 |
| `config/causal_assumptions.md`（大幅更新）| 补充 15 篇文献引用、玉衡禁止调整清单、双层衰减架构、social_stress/cultural_friction 参数化方案 |

### macro-sim 新增文档
| 文件 | 内容 |
|---|---|
| `macro-sim/docs/agent_taxonomy.md`（新建）| B+A/NOVEL 天璇 18 Agent 设计蓝图（A类8+B类4+C类6），soul 文件规范，地缘→金融完整传导链 |
| `docs/grv_datasource_fix.md`（新建）| GRV 数据源修复方案，P0-P3 优先级清单 |



### kaiyang（v1.7.2 → v1.8.0，by Claude，2026-08-04）

| 文件 | 内容 |
|---|---|
| `src/components/FlatMapPanel.tsx` | 完整重写：Leaflet → D3.js + geoNaturalEarth1 + 纯 SVG；球面几何由 D3 内置处理，Russia/Alaska 水平伪线根治 |
| `src/components/FlatMapPanel.css` | 移除 Leaflet 样式；新增 `.fm-arc`/`.fm-point-pulse`/`.fm-tooltip` |
| `src/App.tsx` | 底栏版本号更新为 v1.8.0 |
| `package.json` / `VERSION` | 版本号更新为 1.8.0 |

**技术要点**：点位/星标随 zoom 保持固定视觉尺寸（zoom handler 反向 scale(1/k)）；tooltip 改为 `position:absolute` + `getBoundingClientRect()` 坐标转换，规避 react-grid-layout CSS transform 偏移；弧线跨子午线打断用像素跳跃检测（dx/dy > 200px）。

**2D 地图未解问题（P0，下 session 处理）**：~~Leaflet 无法正确处理球面子午线跨越~~ → ✅ **已解决（v1.8.0）**

### 其他
- `docs/arch_review_20260802.md`（新建）：六角色三轮辩论架构裁定，15个设计缺陷
- `macro-scan/核心代码/generate_gci_anchors.py`（新建）：GCI 面效度历史锚点，PASS
- GED v26.1 ETL 首次运行，产物在 `data/ged/`（不进 git）

---

## NAS 专属操作清单（下次连上局域网时执行）

> 完整可执行提示词（含每步验证命令和停止条件）：**[`docs/nas-deploy-prompt.md`](docs/nas-deploy-prompt.md)**  
> SSH 地址：`TSX@192.168.31.108`  
> 执行顺序：本地 kaiyang build → NAS 预检 → macro-scan 重建 → macro-sim 重建 → kaiyang scp

### 步骤摘要

| 步骤 | 操作 | 备注 |
|---|---|---|
| 0 | 检查 macro-sim `.env` 是否存在 | `.env` 不存在则停止，需手动创建 |
| 1 | `git pull origin main` | 同步 entrypoint.sh 等本次修改 |
| 2 | macro-scan docker-compose.yml 补 8900 端口 + config 挂载 + image 版本 | 非交互式 sed 命令，见提示词文档 |
| 3 | macro-scan `docker build -t macro-scan:v3.8.6 . && docker compose up -d --force-recreate` | 重建镜像使 entrypoint.sh 生效 |
| 4 | macro-sim `bash deploy.sh macro-sim` + `docker compose up -d --force-recreate` | D1/D4/D7/D12 修复生效 |
| 5 | kaiyang `scp dist/ + docker restart kaiyang-nginx-1` | D3 地图 v1.8.0，无水平伪线 |



---

## 已知问题 / 技术债

| 优先级 | 问题 | 状态 |
|---|---|---|
| ~~**P0**~~ | ~~**kaiyang 2D 地图 Leaflet→D3 替换**~~ | ✅ **已完成（v1.8.0，2026-08-04）** D3 geoNaturalEarth1 + SVG，水平伪线根治 |
| ~~P1~~ | ~~signal_synthesizer Staging→Live 切换~~ | ✅ **已完成（2026-08-04）** news.db 53天 ≥30天，STAGING_MODE=0 已写入 docker-compose.yml |
| P1 | R11/R12 开启 | 待 NAS 确认 climate_risk 积累情况 |
| ~~P1~~ | ~~慢变量接入 MacroWorldState~~ | ✅ **已完成（v2.0.22）** irp/ucri/gci 字段注入，load_from_macro_scan 读 slow_variables.json |
| ~~P1~~ | ~~GRV 数据源 P1 修复（BDI→sanctions_risk / GDELT P95校准）~~ | ✅ **已完成** GED接入(v3.8.10) + P95动态(v3.8.11)；BDI→sanctions_risk 待做 |
| ~~P1~~ | ~~B+A/NOVEL Sprint-2~~ | ✅ **已完成（v2.0.22）** A2/A3/A6 soul_file 预位激活 |
| P2 | kaiyang 控制 API 端到端验证 | control_server.py 已部署，需在控制面板点「重跑」验证 |
| P2 | GRV 权重 grv_weights.yaml 无实证基础 | 等 macro-sim 首次产出后 2026-09 月度验证 |
| P2 | D2/D3：校准误差函数与Agent因果链断裂 | 已知缺陷，B+A/NOVEL 重写时处理 |
| ~~P2~~ | ~~D6：校准结果不持久化~~ | ✅ **已完成（v2.0.22）** calibration_cache.json，<7天跳过50步校准 |
| P2 | news_geo_feed：gdelt_geo_cache 需由 geo_risk_vector.py 顺带写入才能生效 | gdelt_geo_cache.json 目前尚未有写入逻辑，新闻坐标功能待数据积累 |
| P2 | 天玑 V1 Brier 异常值 | predictions.final_prob 可能存储原始概率×100，需核查 _archive_to_tianji 写入值域 |

---

## 架构说明（快速上手）

```
macro-scan（天枢）→ 落盘 data/*.json
    ├── scheduler.py — 46个调度任务，每60s落盘state，读pause标志
    │   └── startup_checks.run_all_checks() — 启动时校验
    ├── geo_risk_vector.py — 产出 grv_latest.json（13维 GRV）
    │   └── social_stress/cultural_friction 从 gdelt_scores 聚合透传
    ├── slow_variables.py — IRP/UCRI/GCI（月频，权重从grv_weights.yaml读取）
    ├── control_server.py — 控制 API :8900（A3a）
    └── web_server.py — 问答/状态 UI :8899

macro-sim（天璇）→ 轮询 /app/macro_data/sim_trigger.json
    └── core/simulation.py — D1 fix: per-agent delta 传导
    └── core/world_state.py — D4/D7 fix: 13维GRV + 4变量衰减

kaiyang（开阳）→ nginx :8080，控制面板连接 :8900
    └── MOCK_ENABLED=false（v1.8.0，D3 geoNaturalEarth1 地图，无水平伪线）

天玑（规划中）→ 月度验证层
    └── brier_calc.py — Brier/BSS/锐度计算已备好
```

---

## 已知坑

| 坑 | 说明 |
|---|---|
| sim_trigger.json inode 断链 | 单文件 bind mount + os.replace 原子写 = 容器内锁死旧 inode。修复 = 目录挂载（v2.0.14 已修，容器需 force-recreate）|
| entrypoint.sh 改动必须重建镜像 | 改 entrypoint.sh 后必须 `docker build` + `force-recreate`，仅 restart 不够 |
| kaiyang dist/ 在 .gitignore | NAS 须手动 npm run build + scp，不从 git 同步 |
| control_server 首次启动无状态 | scheduler_state.json 在 scheduler 启动 60s 后才生成，/fetchers 初始返回空列表属正常 |
| optim_config 无 FRED_PROXY | 须用 os.environ.get("FRED_PROXY", "") 而非直接 import，否则 ImportError |
| venv 在 Git Bash 下静默失效 | activate 看起来成功但 pip 仍走全局，用 which python 确认 |
| BAMLH0A0HYM2 PCA 窗口瓶颈 | 该序列仅 837 行，限制 FCI 双轨 PCA 的回溯窗口深度 |
| probit 禁直连 FRED | 只读落盘 CSV，系数固定为 Estrella-Trubin 2006，禁止在线 fitting |

---

## 关键架构决策

- **天璇 P0 hotfix 与 B+A/NOVEL 重写严禁捆绑**（arch_review 铁律第1条）
- **玉衡不独立成星**，weight_matrix.py 并入天玑 V2
- **A3a 采用 HTTP 方案**（FastAPI，端口 8900）
- **crucix = AGPL-3.0**，开阳复刻零代码继承，天枢整合须纯重写
- **天枢 = 唯一数据中枢**，开阳永不直连数据源
- **NAS SMB 挂载不可靠**，所有操作走 SSH + docker exec
- **agents.yaml 不是热挂载**，修改须 `bash deploy.sh macro-sim` 重建镜像
