# 世界推演系统 · 交接文档

> 每次维护后必须更新本文件（规则来自项目规范）。

---

## 当前状态（2026-08-03，by Claude）

| 子系统 | 版本 | 状态 |
|---|---|---|
| macro-scan（天枢）| v3.8.7 | ✅ **已部署 NAS，运行中**（:8899/:8900）|
| macro-sim（天璇）| v2.0.21 | ✅ **已部署 NAS，运行中**（D2/D3/D14/SovereignAgent）|
| kaiyang（开阳）| v1.7.2 | ✅ **已部署 NAS，:8080 可访问** |

- 本地路径：`C:\Users\I327394\Desktop\S\world-sim\`
- Git 分支：`main`，最新 commit：`9296602`（GED ETL + GCI 锚点）
- NAS 路径：`/vol2/1000/software/world-sim/`

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



### kaiyang（v1.7.0 → v1.7.2）

| 文件 | 内容 |
|---|---|
| `src/config/controlConfig.ts` | API base URL 指向 :8900；MOCK_ENABLED 默认 false |
| `src/components/FlatMapPanel.tsx` | 2D平面地图恢复；底图改为 world-atlas GeoJSON 离线 |
| `src/components/StatusBar.tsx` | Stamp 组件加时效性检测：超 24h 变橙色显示 ⚠ |
| `src/App.tsx` | 底栏版本号更新为 v1.7.2 |

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
| 5 | kaiyang `scp dist/ + docker restart kaiyang-nginx-1` | StatusBar 时效性告警、版本号 v1.7.2 |



---

## 已知问题 / 技术债

| 优先级 | 问题 | 状态 |
|---|---|---|
| P0 | macro-sim inode 断链（sim_trigger.json 0字节，天璇从未自动触发）| 代码已修复 v2.0.14，**容器未重建**，本次部署须 force-recreate |
| P1 | signal_synthesizer Staging→Live 切换 | **最早 2026-08-09**（STAGING_MODE=0 + news.db ≥30天双重守门）|
| P1 | R11/R12 开启 | 待 NAS 确认 climate_risk 积累情况 |
| P1 | 慢变量接入 MacroWorldState | world_state.py 加 irp/ucri/gci 三字段，从 slow_variables.json 读取注入 |
| P1 | **GRV 数据源 P0 修复（约1天）** | commodity_yahoo→middle_east_energy / fetch_fx→world_state.py / energy_grid_risk 数据源错误；详见 `docs/grv_datasource_fix.md` |
| P1 | **B+A/NOVEL 天璇重写启动条件** | 先读 `macro-sim/docs/agent_taxonomy.md`（18 Agent 设计蓝图）确认边界，再动代码 |
| P2 | kaiyang 控制 API 端到端验证 | control_server.py 首次部署，部署后在控制面板点「重跑」验证 |
| P2 | GRV 权重 grv_weights.yaml 无实证基础 | 等 macro-sim 首次产出后 2026-09 月度验证；理论依据已在 `macro-scan/config/causal_assumptions.md` |
| P2 | D2/D3：校准误差函数与Agent因果链断裂 | 已知缺陷，不阻断部署，B+A/NOVEL 重写时处理 |
| P2 | D6：校准结果不持久化 | 已知缺陷，每次重跑完整校准，B+A/NOVEL 重写时处理 |

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
    └── MOCK_ENABLED=false（v1.7.2，连接真实 control API）

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
