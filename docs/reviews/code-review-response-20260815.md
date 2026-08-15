# world-sim 审查复核回复（对 Track A / Track B 的复核 + 多 Agent 两轮讨论收敛）

- **对象**：`S:\world-sim`
- **日期**：2026-08-15 17:1x
- **回复方**：主理人侧（世界推演系统运维/开发），含两轮多 Agent 研究讨论（3 个独立研究者并行 → 1 个对抗 skeptic 质询）
- **回复对象**：Track A（`code-review-20260815.md`，79 条发现）+ Track B（`roadmap-recommendations-20260815.md`，P0-P2 规划）
- **性质**：只读复核。本文件仅新增本文件，未修改任何项目代码/配置/数据；所有容器查询均为只读（python 只读 SELECT / ls / git 只读）。

> ⚠️ 与 Track A/B 同一硬约束：本文件位于会 `git push` 到 GitHub 的仓库内，在密钥轮换完成（P0-A）之前请勿推送本仓库。

---

## 0. 摘要

对 Track A 的 79 条发现与 Track B 的 P0 规划做了源码级复核 + 运行容器只读实证 + 多 Agent 对抗讨论。结论：

1. **C01 已完成 Track B 要求的容器复核**，结果**推翻"镜像与磁盘源码不一致"假设**——实为 08-14 引入的回归，**P0-B 的 0.5 天复核前置可消除**，直接进入止血修复。
2. **P0 四件的独立性判断需要修正**：Track B 称"基本独立可并行"，对抗分析结论为**强依赖链**，建议顺序 **P0-D → P0-B → P0-C → P0-A**（详见 §2.1）。
3. **P0-D 从 PLAUSIBLE 升级为部分实锤**：天玑 verifier 已连续 2 天因 `no such table: predictions` 崩溃；且发现 **P6 守卫 271a761 加错了文件**（详见 §3）。
4. **GED 补强已静默退化 14 个月**（2025-06 起权重即 0），与 C01 独立、需单独登记监控（详见 §2.2 附注）。

---

## 1. C01 容器复核完成（对接 Track B P0-B 强制前置）

Track B §P0-B 以 `arch_review(08-02)「GRV 每日稳定产出」` 与 `Track A(08-15)「每日崩溃」` 的矛盾，推断"线上镜像与磁盘源码可能不一致"，要求先容器复核再决定改法。

**复核结果（只读，2026-08-15 16:1x-16:2x）**：

| 检查 | 结果 |
|---|---|
| 运行区 vs git 真源 `geo_risk_vector.py` md5 | **完全一致**（`23690e355b0abddc907933493ba75e84`）→ 非镜像不一致 |
| 容器内 `from geo_risk_vector import _GED_REGION_MAP` | **ImportError**（`/app/geo_risk_vector.py`）→ 运行容器确在崩 |
| `grv_latest.json` mtime | **停在 08-14 06:10** → 08-15 06:10 任务已失败未产出 |
| 探针阈值（`silent_failure_probe.py:61`）| grv 30h WARN / 40h CRIT；复核时 34h 处于 WARN 无人注意 |

**根因定位（git pickaxe）**：commit `af752ea`（**08-14 08:33**「GDELT 校准器落地」）重构 `geo_risk_vector.py`（99 行改动），删除 5 个模块常量定义（`_GED_REGION_MAP` / `_GED_STALE_MONTHS` / `_GED_P95_ANCHOR` / `_CONFLICT_FLOOR` / `_CONFLICT_FLOOR_MIN_ARTICLES`）但未清理引用（`line 106/118/160/276/296` 仍引用；`line 106/276` 在 try 之外、`main():869` 无兜底）。

**"矛盾"由时间线解释**：08-02 arch_review 时代码正常 → 08-14 08:33 引入回归 → 08-14 06:10 为最后一次成功（旧代码）→ 08-15 06:10 首次崩溃。**非镜像不一致，是近期回归**。P0-B 无需再复核，直接进入修复。

---

## 2. P0 规划的三处修正

### 2.1 P0 顺序：P0-D → P0-B → P0-C → P0-A（推翻"四件独立可并行"）

Track B 称 P0 四件"互相基本独立可并行"。对抗分析发现强依赖：

- **P0-B 首日假告警链**：修复后首跑（06:10 或手动）`grv_threshold.py:110` `delta = cur - prev` 中 `prev` 读停更 34h+ 的 `grv_latest.json` → delta 跳变 ≥6.0 → 写 `sim_trigger.json` → **天璇 daemon 无人值守自动跑 100 MC 全量仿真 + LLM 调用**（烧额度、且 P0-D 未修时空转零产出）。
- **P0-D 不依赖 P0-B**：`macro-sim/run.py` 读 `grv_latest.json` 现有值即可跑可落表，陈旧 GRV 不阻塞落表修复。
- 因此 **先 P0-D 后 P0-B**：即便 P0-B 首日假告警踢起天璇自动仿真，落表已修好 → 仿真至少存档不白烧。
- **P0-C 观测目标取决于 P0-D 落表目标**（落 SQLite 指 SQLite / 落 PG 指 PG），不应等 P1-C 定稿；**P1-A 最小门控（拒绝无阈值/无方向预测进表）须先于 P0-D 落表**，否则每月 1 日验证器将无方向预测算成 `outcome=0.5` 永久污染 Brier（Track A H04）。

**建议顺序**：P0-D → P0-B（带抑制）→ P0-C → P0-A。

### 2.2 P0-B 三步绑定（修复 + 首日抑制 + 手动验收）

修复本体（方案 A 最小补丁）确认可行：按 `f6142dd` 版在 `geo_risk_vector.py` line 93-94 间补回 5 个常量定义：

```python
_CONFLICT_FLOOR = {"russia_europe": 35.0}
_CONFLICT_FLOOR_MIN_ARTICLES = 5
_GED_P95_ANCHOR = 3570.0
_GED_REGION_MAP = {"russia_europe": "Europe", "middle_east_energy": "Middle East"}
_GED_STALE_MONTHS = 18
```

5 处引用零改动。方案 B（迁移到 gdelt_calib.json）**无迁移目标**——校准器 schema（`sample_count/scales/tone_base/hotspot_p95`）无 GED/conflict 字段，GED 从不在校准器范围；"纯删除失误"为连带误删（diff 实证常量块 20 行紧贴被重写函数）。

但 **"风险：无"不成立**，P0-B 必须是同一变更三步绑定：
1. 补回常量；
2. **首日抑制**：`GRV_DRY_RUN=1`（`grv_threshold.py:168` 提前 return 不写 trigger）或重置 prev 使 delta=0——防假告警链；
3. **手动验收**：手动跑 `compute_grv` 验证 `grv_latest.json` 更新 + 探针恢复。

> ⚠ 附注（独立发现，建议登记 P1/P2；量级经审计方更正）：**GED 补强从未真正贡献过权重**。GED v26.1 数据冻结至 2024-12，`_GED_STALE_MONTHS=18` 窗口（cutoff≈2025-02）下 `geo_risk_vector.py:150` 立即 return None；且 GED 接入 commit `f6142dd` 为 **2026-08-04**（11 天前）——即接入当天起即超窗 return None，**从未产生过有效权重**（原"退化 14 个月 / 2025-06 起"表述不成立，按审计方更正）。补回常量只是复活一条立即退化的死路径；真正待办是"GED 死亡无监控"。审计方拆两件：(a) 陈旧告警 → P1-B 静默失败主题；(b) 刷数据/调窗 → P2 门控；**P0-B 只补常量 + 加告警，不刷数据**。

### 2.3 P0-A：PAT 已在 GitHub 远端，rotate 是唯一解

- `git remote -v` 实证 remote URL 内嵌 `ghp_` PAT **且已 push 到 github.com**。force push 只改远端指针，**旧提交留在 GitHub 服务器** → `git filter-repo` 只是降低泄露面，**立即 rotate 是唯一正确动作**（同意 Track B P0-A 优先级，但"history 重写 = 修复"的预期需修正）。
- 补充：filter-repo 需 `--replace-text` 覆盖**已跟踪**的 `macro-scan/docker-compose.yml` + `macro-ji/docker-compose.yml`（.gitignore 对已跟踪文件无效，Track A H16 已确认）；`b0/news-forecast-pg` 分支（local+origin 均存在）同样含 key 须重写；`.git/config` 的 PAT 不在历史，单独 `git remote set-url`。
- 审查产物（`code-review-20260815.md` / `roadmap-recommendations-20260815.md` / 本文件）经全文扫描已确认密钥脱敏（`ghp_****` / `<*_REDACTED>`），可保留。

---

## 3. P0-D 升级为部分实锤（容器只读复核，2026-08-15 16:3x）

Track A H20 为 PLAUSIBLE，Track B 要求 P0-D 前容器复核。复核结果：

| 检查 | 实测 |
|---|---|
| `macro-sim/run.py:487-494` `_tianji_conn()` | **不建表**（仅 connect + PRAGMA WAL），机制与 H20 描述一致 |
| `macro-sim/run.py:620-622` 宽 except | 只 print + traceback，**吞错不抛** |
| 宿主 `forecast_tracker.db` | **4096 字节空库，TABLES: []**，predictions/reasoning_trace 均不存在（mtime 08-15 09:42） |
| 天玑 verifier | **连续 2 天（08-14、08-15）`sqlite3.OperationalError: no such table: predictions`，exit=1** |
| 天璇最近仿真 | 08-13 22:29 最后一次，日志 `✅ 存档 3 条预测`（scenario `sim_20260813_2229`，当时表存在）→ 完整事故链未发生，但**玉衡反馈链已实际断裂** |
| 数据去向 | 08-13 的 3 条预测**既不在 SQLite 也不在 PG**（PG `tianji.predictions` 仅 7 条：7/29×1 + 8/6×6） |
| target_metric | `run.py:552` 已是 `global_composite` → **D12 已对齐，无需再改**（Track B §7 的 M33 误挂确认） |

**关键新实锤——P6 守卫加错了文件**：
- commit `271a761` 的 P6 守卫加在 `macro-scan/核心代码/tianji_db.py`（热挂载生效），但**天玑容器 COPY 的是 `macro-ji/tianji_db.py`（纯 sqlite、无 `_PG_ONLY` 守卫）**——P6 删库后 `macro-ji/tianji_db.py:118-124` `get_connection()` 仍直接 `sqlite3.connect` 重建空库（空库 mtime 08-15 09:42 即 verifier 触发时重建），verifier 随后崩 `no such table`。
- 且守卫逻辑 `if not os.path.exists(DB_PATH)` **只挡"文件不存在"，挡不住"已存在的空库"**（当前 4096 空库已存在，守卫照样连空库）。
- 已排除 watchdog 反复重试风险：`verify_watchdog.py:57-60` 对 exit=1 也无条件 `_mark_processed`，每 trigger 只跑一次。

**P0-D 修订建议（file:line 级）**：
- **P0-D1**：`macro-sim/run.py:487-494` `_tianji_conn()` 补幂等 DDL（`CREATE TABLE IF NOT EXISTS`，对齐 `macro-ji/tianji_db.py:27-115`），或容器启动调 `run_migration()`；
- **P0-D2（根因）**：天璇写 SQLite 与天枢 P6 删库矛盾 → `run.py:533` INSERT 改走 worldsim-pg `tianji.predictions`（PG 表已存在），或至少双写；**不并入 P0-C**（D=写路径、C=观测口径，合并增大爆炸半径）；
- **P0-D3**：**守卫落到 `macro-ji/tianji_db.py` 副本**（`_PG_ONLY` 时 raise 而非重建空库），并改为"容器启动调 run_migration()"而非文件存在性判断；
- **P0-D4（去静默）**：`run.py:620-622` except 分支在 archived=0 时发 ntfy 告警；`_tianji_conn()` 加 `PRAGMA busy_timeout`；
- **数据恢复**：08-13 的 3 条预测可能从 P6 提交自带快照 `e0c-p6-20260814-083910` 恢复（若含删库前 db），**可恢复性待核**——建议审计方确认快照内容。

---

## 4. 对 Track A 的补充确认与存疑

- **确认 H12**（PG-only 下双写安全网 inert、`set_alert_hook` 全仓零 caller）：与 08-13 E0-C 闭环时观察一致，`set_alert_hook` 接线确认为 P1-B 最高 ROI 项，同意。
- **确认 H18**（sim_trigger 三端契约冲突）：与本侧在开阳 schema tile 观察到的"读取失败:sim_trigger.json"一致——天璇读后 `write_text("")` 清空 → 开阳 `JSON.parse('')` 崩。三端（写=触发 / 天璇=一次性队列 / 开阳=持久状态）语义冲突属实，建议与 L09（缺 `_schema_version`、`level` 写 int）、M04（`reason` 字段名）合并为单一契约治理项。
- **存疑 H06**（WAL SQLite 在 NAS 共享挂载不安全）：容器为 bind mount 宿主本地卷（非 NFS/SMB 网络文件系统），WAL 跨进程共享内存协调在本地卷成立；**前提存疑，严重度建议下调**——但"无 busy_timeout"属实（已被 P0-D4 吸收）。
- **同意 §7.3 未上线组件就绪度**：玉衡"代码就绪数据未通"、瑶光"口径错位"、天权"文档先行代码零实现"三者互为因果的判断，与 P0-D/P0-C 修正后的执行顺序一致。

---

## 5. 修订后 P0 执行清单（已与审计方收敛，2026-08-15 再复核后）

> 顺序：**{P0-A 并行、立即启动} + {P0-D → P0-B → P0-C}**。P0-A 与运行时链正交，但为唯一 push 阻塞项、暴露面最大（live PAT 已在公网 GitHub），故并行立即。

1. **P0-A（并行、立即）**：rotate 全部 key（GitHub PAT 唯一解）+ filter-repo `--replace-text` 清 tracked compose（macro-scan + macro-ji 两份）+ b0 分支 + `.git/config` `set-url`。解除 push 封印。
2. **P0-D（先）**：**D2 走 PG 为主**（`tianji.predictions` + `reasoning_trace` 两表均已实测存在，D2 主路径无障碍）+ D1 仅作过渡 + D3 守卫落 `macro-ji/tianji_db.py` 副本（改 raise，不靠 exists 判断）+ D4 去静默（archived=0 发 ntfy）；P1-A 最小门控（拒无阈值/无方向预测进表）先行。8/13 的 3 条预测 = 考古价值，不阻塞 P0（审计方 Q1 答复）。
3. **P0-B（次）**：补 5 常量（`f6142dd` 版）+ `GRV_DRY_RUN=1` 首日抑制 + 手动验收；**同时加 GED 陈旧告警**（不刷数据）。
4. **P0-C（后）**：观测口径**锁定 PG**（对齐 D2）+ 预测链探针补齐（约 2h，同意 arch P0-2 估）。
5. **新增登记**：GED 死亡无监控（拆两件：陈旧告警→P1-B / 刷数据调窗→P2 门控）；三容器 `tianji_db.py` 多副本纪律（改守卫/DDL 须确认容器实际用的那份）。

---

## 6. 请审计方复核/确认的开放问题

1. P6 快照 `e0c-p6-20260814-083910` 是否含删库前 `forecast_tracker.db`？能否恢复 08-13 的 3 条预测？
2. P0-D2（天璇转 PG）是否与 E0-C 终态权威库（PG）裁定冲突？若同意，P0-C 观测口径即指 PG，P1-C 的"删双写死路径"时间窗是否随之提前？
3. P0 顺序修订（P0-D → P0-B → P0-C → P0-A）是否有异议？
4. GED 退化 14 个月建议归入哪个规划项？（倾向 P1-B 静默失败主题或 P2 反馈前置）

---

## 7. 诚实性声明

- 本文件全部结论基于：源码只读（git show/diff/pickaxe、grep、AST）、运行容器只读查询（python 只读 SELECT、ls、mtime）、Track A/B 报告交叉引用。
- 所有容器查询未写入任何数据、未重启/重建任何容器、未修改任何配置。
- 多 Agent 讨论中已识别的推断点均显式标注（如"连带误删"为 diff 推断、快照可恢复性待核）；引用值（常量定义、阈值、mtime、commit hash）均来自实际输出。

*本文件为只读产出。*

---

## 8. 审计方再复核结论（code-review-response-review-20260815.md）采纳记录（2026-08-15 17:4x）

审计方对上一版回复做了独立源码级再复核：**4 处完全通过 + 1 处数字更正 + 4 个开放问题全部答复**，双方收敛出 §5 共识版执行清单。采纳/实测要点：

- ✅ **通过 4 处**：C01 为 08-14 回归（`git show af752ea` 5 常量删除行全对上）；P6 守卫加错文件（`macro-ji/tianji_db.py:118-120` 无守卫、`271a761` 只改核心代码那份）；首日假告警机制（`grv_threshold.py:110-112/168-173/223`，幅度 ≥6.0 为估计待实测）；D12 已修（`run.py:552` `global_composite`）。
- ✏️ **更正 1 处**：GED "退化 14 个月"不成立——`f6142dd`（GED 接入）为 08-04 提交，GED 出生即超窗（数据 2024-12 < cutoff 2025-02）、**从未贡献过权重**（约 11 天）。已修正 §2.2 附注；核心结论（死路径 + 需监控）不变。
- 📐 **顺序修正**：P0-A 从"最后"改为**并行立即**（正交 + 唯一 push 阻塞 + 暴露面最大），接受并已写入 §5。
- 🔎 **实测补充（本回复方）**：PG `tianji` schema 5 表齐备（`narrative_chunks` / `narrative_density_flags` / `predictions` / **`reasoning_trace`** / `weight_update_log`），`predictions` 27 列——**审计方 Q2 的"须先确认 reasoning_trace 表"已确认存在**，P0-D2 主路径无障碍。
- 📦 **Q1 采纳**：8/13 三条预测 = 考古价值（`MIN_TRIGGER_N=8` 下捞回也触发不了），不阻塞 P0，不再追。
- 📊 **Q4 采纳**：GED 拆两件（a 陈旧告警→P1-B / b 刷数据调窗→P2 门控），P0-B 只补常量 + 告警、不刷数据。

*本节为对审计方再复核的采纳记录，仅追加本文件。*
