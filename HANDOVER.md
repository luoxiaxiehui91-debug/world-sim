# 世界推演系统 · 交接文档

> 每次维护后必须更新本文件（规则来自项目规范）。

---

## 当前状态（2026-08-02）

### 系统版本
| 子系统 | 版本 | 状态 |
|---|---|---|
| macro-scan（天枢）| v3.8.1 | ✅ 本地代码完整，待部署到 NAS |
| macro-sim（天璇）| v2.0.14 | ⚠️ 代码合并完整，NAS 容器需 force-recreate（P0 inode 断链修复未部署）|
| kaiyang（开阳）| v1.7.0 (Wave-2) | ✅ 本地已构建 dist/，待部署到 NAS |

### 本地路径
- 代码：`C:\Users\I327394\Desktop\S\world-sim\`
- Git 分支：`main`，最新 commit：`5c93fc6`
- NAS 路径（待同步）：`/vol2/1000/software/world-sim/`

---

## 本次维护内容（2026-08-02，by Claude）

### 新系统设计成果合并（v3.8.0）
来源：`Desktop/S/世界推演系统/` 设计副本 → 合并进 `world-sim/`

**新增到 macro-scan/核心代码/：**
- `contracts.py` — Pydantic v2 I1 接口契约（ValueStatus/UsagePolicy/39个selftest）
- `compute_probit.py` — Estrella-Trubin 2006 衰退概率，T10Y3M 口径
- `ged_analysis.py` / `ged_codebook_extract.py` / `etl_ged.py` — UCDP GED 武装冲突数据管道
- `gdelt_country_map.py` — GDELT FIPS→ISO 国家码映射（从 fetch_gdelt_geo 拆出）
- `fetch_gdelt_geo.py` — GDELT 地理事件点 feed（增量拉取 + 聚合）

**新增到 macro-scan/tests/：**
- `static_gate_check.py`、`test_fetch_airtraffic_opensky.py`、`test_fetch_bdi.py`、`test_fetch_commodity_yahoo.py`、`test_fetch_fao.py` + fixtures/

**requirements.txt：** 新增 `pydantic>=2.0.0`、`pypdf>=4.0.0`

### scheduler.py 补全（v3.8.1）
- JOBS 新增 `gdelt_geo`（I15 事件档，`--incremental`，插在 earthquake 之后）
- LOG_PATHS 同步新增 `gdelt_geo`

### kaiyang Wave-2 升级（v3.8.1）
- Wave-1 (v1.0.3) → Wave-2 (v1.7.0)
- 新增控制面板：`control/` 目录（ControlDrawer/FetcherCard/TianshuTab 等）
- 新增组件：NuclearWatchPanel/LayerLegend/LayerTreePanel/RegionTabs
- 新增 hooks：useControlApi/useOperationPolling
- 新增 lib：controlApi/layerContract/newsGeoAdapter/nuclearData/operationLog
- dist/ 已在本地构建完成（vite 5.4.21，1117 模块）

### docker-compose.yml（macro-scan/）
- 新增 `kaiyang` 服务（nginx:alpine，:8080），挂载 dist/ 只读 + macro-scan/data/ 只读
- **注意：该文件在 .gitignore 里，需手动 scp 或编辑 NAS 上的文件**

### 清理
- 删除旧 kaiyang.bak_20260730_220325
- .gitignore 补充 *.bak、NDH6SA~M、qa_result.txt、.hermes_task.md

---

## 待部署操作清单

> 部署时按此顺序执行：

- [ ] `git pull` on NAS（`/vol2/1000/software/world-sim/`）
- [ ] NAS macro-scan：`docker restart macro-scan-macro-scan-1`（scheduler.py 改动需重启）
- [ ] NAS macro-sim：`docker compose up --force-recreate`（P0 inode 断链修复，v2.0.14）
- [ ] NAS kaiyang：新容器首次启动，或手动 `npm run build` + 复制 dist/
- [ ] 手动更新 NAS 上的 `macro-scan/docker-compose.yml`（新增 kaiyang 服务）
- [ ] 验证：`docker exec macro-sim cat /app/data/sim_trigger.json` 确认 inode 修复生效

---

## 已知问题 / 技术债

| 优先级 | 问题 | 状态 |
|---|---|---|
| P0 | macro-sim inode 断链（sim_trigger.json 持续 0 字节，天璇从未触发）| 代码已修复 v2.0.14，**容器未重建** |
| P1 | kaiyang 控制抽屉 `MOCK_ENABLED=true`（A3a 控制 API 天枢侧未实现）| 设计文档完整（T01-T05），代码待写 |
| P2 | GRV 权重 grv_weights.yaml 无实证基础（Claude 初始值，首次 Brier 验证待运行）| 等 macro-sim 首次产出后 2026-09-01 月度触发 |
| P3 | gscpi 供应链压力 / nuke 核态势无专用 fetcher | 暂由 FAO/能源/HDX 间接覆盖，待决策是否新增 |

---

## 架构说明（快速上手）

```
macro-scan（天枢）→ 落盘 data/*.json
    ├── scheduler.py 驱动 46 个调度任务（I15/I30/日档/月档）
    ├── geo_risk_vector.py 产出 grv_latest.json（11维 GRV）
    ├── run_macro_analysis.py 产出 LLM 分析报告 + ntfy 推送
    └── grv_threshold.py 写 sim_trigger.json → 触发天璇

macro-sim（天璇）→ 读 sim_trigger.json，产出仿真报告
    └── run.py --daemon 轮询触发
        └── core/simulation.py → 12 Agent Monte Carlo × 100

kaiyang（开阳）→ 只读 data/*.json，展示 + 控制面板
    └── dist/ 静态站，nginx serve，端口 8080
        └── control/ 抽屉（MOCK_ENABLED=true，等 A3a 实现）
```

**数据流**：天枢 → `data/` 目录 ← nginx 挂载 ← 开阳读取（单向只读）

---

## 下一步开发建议

1. **部署到 NAS**（最高优先）— 参见上方待部署操作清单
2. **验证 macro-sim inode 修复**：force-recreate 后等 GRV 触发，确认 predictions 表有写入
3. **A3a 控制 API 实现**：设计文档已完整（T01-T05），开阳控制面板即可真正工作
4. **世界推演系统/ 设计副本**：已全部合并，可以归档或清理该目录

---

## 关键架构决策（来自 Sprint-0，by 用户）

- **天璇本 Sprint 不建预测引擎**，延后（2026-07-31 拍板）
- **crucix = AGPL-3.0**：开阳复刻零代码继承，天枢整合须纯重写，crucix 容器最终退场
- **天枢 = 唯一数据中枢**：开阳永不直连数据源，只读契约文件
- **采集频率 ≤50% rate-limit 红线**：任何新 fetcher 加入前必须审核频率
- **部署 = scp 单文件 + 基线校验**，禁止 scp/rsync 混用
- **NAS SMB 挂载不可靠**，所有操作走 SSH + docker exec

> 详细决策背景见 `docs/archive/worldsim-review-synthesis.md`

---

## 已知坑（踩过的，下次别再踩）

| 坑 | 说明 |
|---|---|
| sim_trigger.json inode 断链 | 单文件 bind mount + `os.replace` 原子写 = 容器内永久锁死旧 inode，天璇静默收不到信号。修复 = 改为目录挂载（v2.0.14 已修，容器需 force-recreate）|
| optim_config 无 FRED_PROXY | 须用 `os.environ.get("FRED_PROXY", "")` 取代直接 import，否则 ImportError |
| venv 在 Git Bash 下静默失效 | Windows Git Bash 里 activate 看起来成功但 pip 仍走全局，用 `which python` 确认 |
| BAMLH0A0HYM2 PCA 窗口瓶颈 | 该序列仅 837 行，限制了 FCI 双轨 PCA 的回溯窗口深度 |
| probit 禁直连 FRED | 只读落盘 CSV，系数固定为 Estrella-Trubin 2006，禁止在线 fitting |

