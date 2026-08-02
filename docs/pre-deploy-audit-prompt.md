# world-sim 部署前全面排查

## 任务背景

world-sim 是一个三组件宏观推演系统（macro-scan 天枢 v3.8.6 / macro-sim 天璇 v2.0.17 / kaiyang 开阳 v1.7.2），运行在家用 NAS（192.168.31.108）的 Docker 容器中。

本次 session 是**部署前最后一次全面排查**，代码已在本地完成修改，尚未同步到 NAS。

**排查目标**：发现任何可能导致部署后系统行为不正确、静默失败、或难以调试的问题，优先级：
1. 会导致系统启动失败或关键功能断路的问题（P0）
2. 会导致仿真/预测结果不可信的逻辑错误（P0/P1）
3. 接口不匹配、数据格式问题（P1）
4. 设计意图与实现不一致（P2）

---

## 必读文档（按顺序，每步完整读）

1. `AGENTS.md`（根目录）— 系统全貌
2. `HANDOVER.md` — 今晚所有变更和已知问题
3. `docs/arch_review_20260802.md` — 15个已确认设计缺陷（其中 D1/D4/D7/D12 今晚已修）
4. `macro-sim/CHANGELOG.md` 前100行 — 天璇所有变更
5. `macro-scan/TuiYan_CHANGELOG.md` 前100行 — 天枢所有变更

---

## 排查维度（多 agent 并行，≤15个请求）

请用**多 agent 并行**覆盖以下维度，每个维度独立执行，结果汇总后交叉验证：

### 维度 A：天璇仿真引擎（macro-sim）

重点文件：`macro-sim/core/simulation.py` / `world_state.py` / `calibrator.py` / `bifurcation.py` / `run.py`

排查要点：
- D1 修复后的传导矩阵：per-agent delta 路径是否完整覆盖所有 12 个 Agent？有没有遗漏某个 Agent 的行动没用 `add()` 函数？
- D4 修复后：`apply_natural_decay` 里4个新增变量的衰减系数是否合理？`china_credit_impulse` 允许负值，衰减方向是否正确？
- D7 修复后：`load_from_macro_scan()` 读取的13个 GRV 字段，有没有哪个用了 `or 0.0` 但实际上 None 和 0.0 语义不同？
- D12 修复后：`_archive_to_tianji` 中 content/target_metric/outcome_definition 三者现在对齐了吗？验证逻辑是否还存在其他 content≠metric 的情况？
- `calibrator.py`：校准参数调整的是 AgentParams 还是 causal_chain.confidence？哪个才是设计预期？（D2/D3 缺陷的延续）
- `run.py`：`--daemon` 模式下轮询 sim_trigger.json 的读取方式，修复 inode 问题后是否真的用目录挂载而非单文件？

### 维度 B：天枢数据管道（macro-scan）

重点文件：`macro-scan/核心代码/scheduler.py` / `geo_risk_vector.py` / `slow_variables.py` / `control_server.py` / `startup_checks.py`

排查要点：
- `scheduler.py`：`_dump_state()` 每60秒落盘，`_load_paused()` 每轮读取——在高频 I15 任务（每15分钟）下，文件读写会不会成为瓶颈？
- `control_server.py`：`rerun` 端点用 `subprocess.Popen` 执行 fetcher，`fetcher_id` 直接拼接脚本路径——有没有路径遍历风险？fetcher_id 是否做了白名单校验？
- `geo_risk_vector.py`：social_stress 是 `{country: score}` 字典，聚合取均值——如果字典为空（GDELT 当天没有高于20分的国家），均值计算会不会产生 None 而不是 0？
- `startup_checks.py`：KNOWN_GRV_DIMENSIONS 里有13个维度，但 source_dimension_map.yaml 的 primary 字段只有11个原始维度。social_stress/cultural_friction 不在 source_dimension_map 里——校验会不会误报这两个维度为"未知映射"？
- `slow_variables.py`：cron 幂等保护用 `updated_at[:7]` 比较月份，如果服务器时区和 UTC 差了一天会不会本月第一天就被跳过？

### 维度 C：天璇与天枢接口（数据契约）

重点文件：`macro-sim/core/world_state.py` / `macro-scan/核心代码/geo_risk_vector.py` / `macro-scan/AGENTS.md` 接口契约节

排查要点：
- grv_latest.json 的 `_schema_version` 字段：`load_from_macro_scan()` 验证版本号，但 geo_risk_vector.py 写出时用的 key 是 `_schema_version` 还是 `schema_version`（有没有下划线）？
- 新增的 social_stress/cultural_friction 字段：geo_risk_vector.py 写出时值可能为 None（gdelt_scores 不存在时），load_from_macro_scan 用 `or 0.0` 处理——但 None or 0.0 = 0.0，float(None or 0.0) = 0.0，这条路径是否真的安全？
- 接口契约文档写 GRV 是"13维"，但 grv_latest.json 实际产出字段数量——有没有维度缺失或多出？

### 维度 D：kaiyang 前端（开阳）

重点文件：`kaiyang/src/components/WorldPanel.tsx` / `FlatMapPanel.tsx` / `src/config/controlConfig.ts`

排查要点：
- 2D 平面地图修复：FlatMapPanel 现在正确渲染了吗？`mode === 'flat'` 时 FlatMapPanel 是 visible 而 GlobePanel 是 `pointer-events-none invisible`，顺序是否正确？
- localStorage 持久化：`readInitialMode()` 读 localStorage，如果用户上次用的是 'flat' 模式，刷新后会恢复到 flat——但这时 Leaflet 地图容器可能还没初始化，有没有时序问题？
- control_server 端点：`API_BASE_URL` 指向 `192.168.31.108:8900`，在本地开发环境（localhost）下会 CORS 失败——开发时是否需要 mock？`MOCK_ENABLED` 默认 false，开发时怎么切换？

### 维度 E：部署脚本与容器配置

重点文件：`deploy.sh` / `macro-scan/docker-compose.yml`（如存在）/ `macro-sim/` Dockerfile 相关

排查要点：
- `entrypoint.sh` 是否已经包含 control_server.py 的启动行？（HANDOVER 里说需要手动追加）
- macro-sim 的 `config/agents.yaml` 是热挂载还是 COPY？CHANGELOG 里有矛盾记录（今晚已修，确认修复后版本）
- `deploy.sh macro-scan` 做的是 rsync + restart，`deploy.sh macro-sim` 做的是 rsync + rebuild + restart——GED 产物 `data/ged/` 不进 git，部署时会不会被 rsync 误删？

---

## 输出要求

每个排查维度产出一份报告，格式：

```
## 维度 X 排查报告

### ✅ 验证通过
- 条目：具体证据（文件:行号）

### ⚠️ 疑问/风险（需人工确认）
- 条目：描述 + 建议

### ❌ 确认问题（建议修复）
- 条目：问题描述 + 根因 + 修复建议
```

最后汇总一份**部署风险清单**，按 P0/P1/P2 分级，P0 项在部署前必须修复。

---

## 约束

- 请求总数 ≤15个（包含所有 agent 的工具调用）
- 不修改任何代码，只读+报告
- 对不确定的地方明确标注"需人工确认"，不要猜测
- 优先深读核心修改文件（今晚 diff 的部分），不要泛读
