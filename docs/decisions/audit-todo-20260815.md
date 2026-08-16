# 审查遗留待办清单（Track A 79 条 → 已修/待办映射）

## 执行顺序规划（2026-08-16 确认，B0-B5）

> 排序原则：先清"无依赖确定性账"→ 修"影响核心产出的正确性"→ 修"显示/契约层"→ 前端体验 → 健壮性 → 等数据的 P2。数据时滞（MIN_TRIGGER_N=8 / 90 天到期）为硬约束。

| 批次 | 内容 | 依赖/时机 | 预计 |
|------|------|----------|------|
| B0 清账三件 ✅ | P6 删 SQLite（核查 narrative 写路径 → delete_sqlite_e0c.sh + 移除豁免，同步骤）/ P1-E causal_assumptions / H19 天璇 GRV null 守卫 | P6 观察窗 08-16 到点；其余零依赖 | 半天 |
| B1 天璇正确性 ✅ | H21 VIX 恐慌放大永不触发 + H22 MC 路径概率不归一 | 需读懂天璇仿真逻辑 | 1 天 |
| B2 契约一致性 ✅ | H18 sim_trigger 三端契约 + schema_version 统一（sdr/firms/safecast_nuke 缺字段 + airroutes/health_geo/spacelaunch 写 "1"） | 修完开阳 schema tile 告警清零 | 1 天 |
| B3 开阳前端 ✅ | H01 LAN randomUUID 崩 + H02 token 外泄 + token 配置 UI（用户当前被 401 卡住，已提前） | 需用户填 CONTROL_TOKEN | 半天 |
| B4 健壮性 ✅ | H08/H11 非原子写（GPR CSV / predictions_log） | 无依赖 | 半天 |
| B5 P2 门控 | 玉衡 V2 通数据 → Brier/BSS 真实样本 → 天权公式 → 新源/新 Agent/契约 schema 单一化 | MIN_TRIGGER_N=8 + 90 天到期 ≈ 3 个月（约 11 月中） | — |

穿插触发式待办：P0-A 密钥（仓库转公开前）/ GED 数据决策（P2 门控内）/ 中央知识库每周巡检。


- **关联**：`../reviews/code-review-20260815.md`（Track A 79 条）+ `../reviews/roadmap-recommendations-20260815.md`（Track B 规划）+ `20260815-p0p1-implementation.md`（已实施记录）
- **日期**：2026-08-15
- **性质**：执行清单（逐条销项用）。**中央权威 = STATUS.md「待做/已知遗留」节**，本文档为审查发现维度的完整映射。

## 1. 已修（79 条中已闭环）

| 审查项 | 修复 | commit |
|--------|------|--------|
| C01（GRV 常量崩溃） | P0-B 补 5 常量 | `0eb25d3` |
| C02（control fail-open） | P1-D fail-closed | `5136dc3` |
| C03/H15/H17（0.0.0.0+CORS*） | P1-D CORS 收窄 | `5136dc3` |
| H03/H04/H05（Brier 污染） | P1-A 去污染 | `d237aa7` |
| H09（探针盲区） | P0-C check_predictions_chain | `b876ad4`+`09419d5` |
| H12（set_alert_hook 零 caller） | P1-B 默认 ntfy 接线 | `7a13b98` |
| H13（articles 无 UNIQUE） | P1-C DDL 对齐（线上已有 news_uq_*） | `6159d0a` |
| H19（GRV null 算术） | ⚠ 部分：GRV 侧已修（C01），**天璇 world_state 侧未修**（见 §2） | — |
| H20（落表静默 no-op） | P0-D D1-D4 + D2 转 PG | `5e109f9`+`afe1311`+`f7cf689` |
| GED 静默退化 | P1-B check_ged_stale 暴露 | `7a13b98`+`510432a` |

## 2. 未修 High（优先处理）

| ID | 位置 | 问题 | 建议修法 | 关联 |
|----|------|------|---------|------|
| ✅ **H21** | `macro-sim/core/simulation.py:412` | `consecutive_negative_steps` 到 3 即归零 → VIX 恐慌放大规则结构性永不触发（尾部风险机制死） | 改归零逻辑（延后到 apply_bleed_rules 之后或累计不归零） | P2-1 前可修（天璇正确性） |
| ✅ **H22** | `macro-sim/core/bifurcation.py:431` | MC 路径概率不归一（小簇丢弃后概率质量消失，97%≠100%） | 保留簇 renormalize 或并入最近簇（docstring 声称合并但没实现） | 同上 |
| ✅ **H19** | `macro-sim/core/world_state.py:558-559,634` | GRV 维度 null 时 `dict.get(key, default)` 不兜底 → None 进算术崩 | 改用 `float(grv.get(k) or 0)`（同文件 :562 已有正确写法） | P0-B 联动，低风险可快修 |
| ✅ **H01** | `kaiyang/src/state/ControlContext.tsx:172` 等 6 处 | `crypto.randomUUID()` 在 LAN HTTP 不可用 → 控制面板点任意按钮崩 | 加 randomUUID polyfill 或改 uuid 生成 | 开阳控制面板 |
| ✅ **H02** | `kaiyang/src/config/controlConfig.ts:17` | localStorage 可覆盖 API base url + token 自动附带 = token 外泄通道 | base url 协议/主机白名单 | 开阳 |
| ✅ **H08** | `macro-scan/核心代码/fetch_gpr.py:113` | GPR CSV 非原子写空文件毁全史（无 rows==0 守卫/无 tmp+replace） | 复用 fetcher_base 原子写 + 保留良值 | P1-B 原子写 |
| ✅ **H11** | `macro-scan/核心代码/verify_predictions.py:348` | predictions_log.json 非原子写 + 裸 json.load → 一次崩溃永久断链 | 复用 prediction_logger tmp+os.replace + load 容错 | P1-B 原子写 |
| ✅ **H18** | `sim_trigger.json` 三端契约 | 天璇读后清空 vs 开阳当持久状态读 → JSON.parse('') 崩、badge 永不亮 | 统一契约（写=触发/读=一次性 or 持久二选一） | 用户 schema 专项 |
| **H14/H16/H07/M29/M32** | ntfy 1900 + compose/.env 明文 key | 密钥泄露面 | **P0-A 密钥轮换**（用户暂缓，GitHub 私有；触发=仓库转公开/外部共享前） | P0-A |

## 3. 未修 Medium（精选，随规划项处理）

| ID | 位置 | 问题 | 归属 |
|----|------|------|------|
| M01/M03/M05/M06 | kaiyang 控制面板 | 轮询挂载依赖 / relativeTime 时区 / token 明文存储 / 硬编码 IP | 开阳面板收尾 |
| M07 | `kaiyang/nginx/default.conf:23` | nginx /data/ 暴露整个运行数据目录 | 开阳部署 |
| M08 | `tianji_verifier.py:265` | reweight 窗口反序（取最旧 N 而非最新） | P1-A 延续 |
| M09/M10/M11 | weight_matrix | Herfindahl no-op / clip 逐次绕过 / 审计日志吞错 | P2 反馈前置 |
| M12 | verify_watchdog | 幂等竞态（stale trigger 重写） | 天玑 |
| M13/M15 | scan_weak_signals/geo_risk | GDELT 部分抓取覆盖分数 / GRV 消费无新鲜度 | P1-B 延续 |
| M14 | fetch_rss_news | feedparser 无 timeout（挂起阻塞） | P1-B 延续 |
| M16 | grv_threshold | _write_sim_trigger 幂等承诺未兑现 | sim_trigger 专项 |
| M19 | hybrid_llm | reason() 返回原始 prompt 占位串 | LLM 层 |
| M22 | verify_predictions | dry_run 未生效（--dry-run 也写文件） | P1-B 延续 |
| M24 | 天枢 tianji_db | get_narrative_chunks staleness 死（_norm 后） | 天枢 |
| M25 | signal_synthesizer | synthesis_log.triggered_at naive 写 timestamptz | 时区收尾 |
| M26 | pg_read | 无法区分 PG 宕机 vs 无数据（[]/None） | P0-C/P1-B 延续 |
| M27/M28 | control_server | get_logs 路径穿越 / fetcher_id 无白名单 | P1-D 延续 |
| M31 | run.py | archival uuid4 主键 INSERT OR IGNORE 永不 dedupe | P0-D 延续 |
| M33 | bifurcation | n_clusters==1 强拆 3 簇 | 天璇正确性（与 H22 同批） |
| M34 | agents/base | soul 文件缺失静默降级 | 天璇 |

## 4. 宏观待办（决策/运维类）

| 项 | 内容 | 前置/触发 | 状态 |
|----|------|----------|------|
| **P0-A 密钥轮换** | GitHub PAT（.git/config）+ FRED/SiliconFlow/MiniMax/EIA key（git 历史）+ ntfy 1900；filter-repo 清两份 tracked compose + b0 分支 + set-url | 用户暂缓（仓库私有）；触发=转公开/外部共享前 | ⏸ |
| **P6 删 SQLite** | 删 forecast_tracker.db + 移除 `_SQLITE_GONE_EXEMPT`（同步骤）；前置：确认天枢 narrative 写路径被 _PG_ONLY 守卫挡死 | 观察 1-2 天无复生（08-15 起） | ⬜ |
| **P1-E causal_assumptions** | 补全所有经验假设标注（天权公式输入） | 无 | ⬜ |
| **GED 数据决策** | 跑 etl_ged.py 生成产物 / 裁决"禁作当前信号"冲突 / 是否刷数据调窗 | P2 门控 | ⬜ |
| **sim_trigger 三端契约** | 统一写/读语义（H18+M04+L09+用户 schema 专项） | 用户确认方案 | ⬜ |
| **schema_version 统一** | sdr/firms/safecast_nuke 补字段 + airroutes/health/spacelaunch 改 "1.0" + 双命名债 | 用户 schema 专项 | ⬜ |
| **开阳控制 token** | 面板填 CONTROL_TOKEN（P1-D fail-closed 后） | 用户操作 | ⬜ |
| **P2 全部** | 闭环验收门 → 玉衡 V2 通数据 → 天权公式（门控 P2-1）→ 新数据源/新 Agent/契约 schema 单一化 | MIN_TRIGGER_N=8 触达（≈3 个月数据积累） | 🔒 门控 |
| **中央知识库巡检** | INDEX 每周校准 | 每周 | 例行 |

## 5. 销项方式

- High 修复 → 对应 commit + 本文档标 ✅ + STATUS 待办节更新
- Medium → 随所属规划项（P1-B/P1-D/开阳收尾等）处理，处理后销项
- 本文档不设"全部清空"目标——审查遗留是 backlog，按风险与窗口排期
