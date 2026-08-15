# world-sim 审查复核意见（审计方对 code-review-response 的再复核）

- **对象**：`S:\world-sim`
- **日期**：2026-08-15
- **作者**：审计方（Track A/B 出具方），对主理人侧 `code-review-response-20260815.md` 做独立源码级再复核
- **性质**：只读产出。仅新增本文件，未修改任何项目代码/配置/数据；所有核对均为只读（`git show/diff/log`、`grep`、`sed` 读取）。
- **方法**：对回复中最有杠杆的 5 处论断做独立源码级交叉验证 → 4 处完全通过、1 处数字需更正 → 逐条回答回复 §6 的 4 个开放问题。

> ⚠️ 与前序文档同一硬约束：本文件位于会 `git push` 到 GitHub 的仓库内。在密钥全部轮换作废（P0-A）之前请勿推送本仓库。

---

## 0. 总评

主理人侧的回复把 Track B 标注为"强制前置"的**运行容器只读复核**真正执行了，且比原静态审查更深（够到了容器运行时证据：`ImportError`、verifier exit code、db mtime、git pickaxe）。审计方对其 5 处关键论断做了独立源码级核对：**4 处完全通过，1 处（GED "14 个月"）数字与 git 时间线矛盾、需更正，但其核心结论成立**。

---

## 1. 独立核实通过的 4 处（附证据行）

| 论断 | 审计方核对证据 | 结论 |
|---|---|---|
| **C01 是 08-14 回归，非镜像不一致** | `git show af752ea`（**2026-08-14 08:33:47 +0800**，"GDELT 校准器落地"）diff 中 5 个常量定义全被删除（`-_CONFLICT_FLOOR = {` / `-_CONFLICT_FLOOR_MIN_ARTICLES = 5` / `-_GED_P95_ANCHOR = 3570.0` / `-_GED_REGION_MAP = {` / `-_GED_STALE_MONTHS = 18`）；当前 `geo_risk_vector.py` 仅剩引用行（106/118/160/276/296），无任何定义行；提交信息确认改读 `gdelt_calib.json` | ✅ **原"镜像不一致"假设被正确推翻**；P0-B 复核前置可删，直接修复 |
| **P6 守卫加错了文件** | `macro-ji/tianji_db.py:118` `get_connection()` → `:120` 直接 `sqlite3.connect(DB_PATH)`，**无 `_PG_ONLY`、无 exists 检查**；守卫只在 `macro-scan/核心代码/tianji_db.py:123/159/161`；`git show 271a761 --stat` 只改动核心代码那一份；`:161` 确为 `if not os.path.exists(DB_PATH)`（只挡"文件不存在"，挡不住已存在的空库） | ✅ 完全属实 |
| **修复后首日假告警链机制** | `grv_threshold.py:111` `delta = cur_val - prev_val`、`:112` `if delta >= GRV_DELTA_THRESHOLD`、`:168-173` `GRV_DRY_RUN` 抑制（提前 return 不写 trigger、回滚冷却日志）、`:223` 主线程同步 `_write_sim_trigger(..., level=3)` 通知 macro-sim daemon | ✅ 机制确认。注：`:110` 的 None 守卫（`prev_val = _prev if _prev is not None else cur_val`）只在"无历史"时令 delta=0，**挡不住"陈旧但存在"的历史值** → 佐证首日 `GRV_DRY_RUN` 抑制的必要性。**幅度"≥6.0"为估计值**（依赖停更时的实际 GRV 值，静态不可算），机制成立、量级待实测 |
| **target_metric 已对齐（D12 已修）** | `run.py:552` = `"global_composite"`，注释明写 `# D12 fix: target_metric 与 content/outcome_definition 一致`；存档 except 在 `:621` 只 `print` 不 `raise`（吞错） | ✅ 佐证 Track B §7"M33 误挂、真问题是 D12"的判断，且 D12 已在源码修复 |

---

## 2. 审计方采纳的、对原 Track A/B 的修正

1. **P0-B 的 0.5 天容器复核前置可删**——已证实是 `af752ea`（08-14 08:33）引入的近期回归，非镜像不一致，直接进入止血修复。
2. **P0-A："history 重写 = 修复"是原报告的措辞错误**。PAT 已 push 到 github.com，旧提交留在远端服务器，`git filter-repo` 只降低泄露面，**立即 rotate 才是唯一正确动作**。补充：`--replace-text` 须覆盖已跟踪的 `macro-scan/docker-compose.yml` + `macro-ji/docker-compose.yml`（`.gitignore` 对已跟踪文件无效，Track A H16 已确认）、`b0/news-forecast-pg` 分支同样含 key、`.git/config` 的 PAT 不在历史须单独 `git remote set-url`——这些接受。
3. **P0-D 从 PLAUSIBLE 升为部分实锤**：天玑 verifier 连续 2 天 `no such table: predictions`、`forecast_tracker.db` 为 4096 字节空库、P6 守卫加错文件——接受，H20 的严重度上调有据。

---

## 3. 一处需更正的数字（facts-vs-assumptions）

回复 §2.2 附注称"**GED 补强已静默退化 14 个月（2025-06 起权重即 0）**"——**此数字不成立**：

- `git show -s f6142dd`（GED v26.1 接入，v3.8.10）提交日期为 **2026-08-04**，即今日往前 **11 天**。一个 11 天前才引入的特性不可能"退化 14 个月"。
- 陈旧逻辑（`geo_risk_vector.py:118` `cutoff_ym = now - _GED_STALE_MONTHS*30 天` ≈ 2025-02；`:150-152` `if latest_ym < cutoff_ym: return None`）意味着：**接入当天（08-04）`latest_ym=2024-12 < cutoff=2025-02` 即已 return None**。GED v26.1 数据冻结在 2024-12，出生即超出 18 个月窗口。

**准确表述**：GED 补强自 **2026-08-04** 接入起就一直返回 None（数据 2024-12 超窗），**从未真正贡献过权重**（约 11 天，非 14 个月；"2025-06"无来源）。

**核心结论仍成立**：补回常量只是复活一条立即退化的死路径；真正待办是"GED 死亡无监控"，归入 P1-B 静默失败主题（详见 §4 Q4）。仅"14 个月 / 2025-06"的量级建议删除/更正。

---

## 4. 对回复 §6 四个开放问题的回答

### Q1　P6 快照 `e0c-p6-20260814-083910` 能否恢复 08-13 的 3 条预测？

技术上取决于快照是否含删库前的 `forecast_tracker.db`（需主理人侧在容器/备份卷核实，审计方从只读挂载无法确认快照内容）。**但不在关键路径上**：这 3 条为 08-13 单场景（`sim_20260813_2229`）测试期数据，`MIN_TRIGGER_N=8` 下即使捞回也触发不了玉衡权重反馈。属考古价值，不阻塞 P0。真正的修复是 D1-D4 让**未来**预测稳定落表。

### Q2　P0-D2（天璇→PG）与 E0-C 终态 PG 裁定冲突吗？

**不冲突，反而对齐**——E0-C 终态权威库即 PG。把 `run.py:533` 的 INSERT 改走 `worldsim-pg tianji.predictions`（表已存在、含 7 条历史）是**根因修复**，直接消除"天璇写 SQLite ↔ 天枢 P6 删库"这对矛盾，优于 D1（给注定退役的 SQLite 补幂等 DDL）。

- **建议 D2 为主、D1 仅作过渡**。
- 若采纳：① **P0-C 观测口径即锁定 PG**（解决 Track B"权威库待 P1-C 定稿"的悬置）；② P1-C"删双写死路径"窗口可随之提前。
- **唯一须先确认**：PG 侧除 `tianji.predictions` 外，`reasoning_trace` 表（`run.py:571` `INSERT INTO reasoning_trace`）是否也已建好，否则 D2 会半截失败。

### Q3　P0 顺序 P0-D → P0-B → P0-C → P0-A 有异议吗？

运行时依赖链认同（**D → B → C**）。**唯一微调：P0-A 不应排在最后，应并行/立即启动**——它与运行时链正交（不争资源），却是唯一的 push 阻塞项、且暴露面最大（live PAT 已在公网 GitHub）。

- 审计方建议顺序：**{P0-A 并行、立即} + {P0-D → P0-B（带 `GRV_DRY_RUN` 首日抑制）→ P0-C}**。
- 认同回复补充的 gate：**P1-A 最小门控（拒绝无阈值/无方向预测进表）须先于 P0-D 落表**，否则每月验证器将无方向预测算成 `outcome=0.5` 永久污染 Brier（Track A H04）。

### Q4　GED 退化 14 个月建议归入哪个规划项？

拆成两件独立事项：

- **(a) 监控缺失（GED 静默死亡）→ P1-B 静默失败主题**：加陈旧告警，让"GED 权重降 0"这类静默退化可感知。
- **(b) 是否刷新 GED v26.1 数据 / 调整 `_GED_STALE_MONTHS` → P2 / backlog 的数据决策**：属能力决策，应门控到闭环跑通后。

**P0-B 阶段只补常量 + 加陈旧告警，不要顺手刷数据**（刷数据是 (b)，不应混进止血）。

---

## 5. 修订后的 P0 共识（审计方 + 主理人侧收敛）

1. **P0-A（并行、立即）**：rotate 全部 key（GitHub PAT 唯一解）+ `filter-repo --replace-text` 清 tracked compose + `b0` 分支 + `.git/config` `set-url`。解除 push 封印。
2. **P0-D（先）**：**D2 走 PG 为主**（先确认 `reasoning_trace` 表存在）+ D1 过渡 + D3 守卫落 `macro-ji/tianji_db.py` 副本（改 raise，不靠 exists 判断）+ D4 去静默（`run.py:620-622` except 在 archived=0 时发 ntfy）。P1-A 最小门控先行。
3. **P0-B（次）**：补回 5 常量（按 `f6142dd` 版）+ `GRV_DRY_RUN=1` 首日抑制 + 手动验收；**同时加 GED 陈旧告警**（不刷数据）。
4. **P0-C（后）**：观测口径锁定 PG（对齐 D2）+ 预测链探针补齐（约 2h，同意 arch P0-2 估）。
5. **新增登记**：GED 死亡无监控（P1-B）；三容器 `tianji_db.py` 多副本纪律（改守卫/DDL 前须确认容器实际 COPY/挂载的是哪一份）。

---

## 6. 诚实性声明

- 本文件结论基于：`git show/diff/log/pickaxe`、`grep`、`sed` 只读读取 `S:\world-sim` 挂载盘源码 + git 历史，交叉引用 Track A/B 与主理人侧回复。
- 审计方**无法**独立复现容器运行时证据（`/app` 内 `ImportError`、verifier exit code、db mtime）——这些以主理人侧容器只读复核为准；审计方核对的是与之一致的**源码/git 侧证据**。
- 推断点均显式标注：首日告警"≥6.0"幅度为估计值（机制已确认、量级待实测）；GED "14 个月"经 git 时间线判定不成立并给出更正。引用值（常量、commit hash、日期、file:line）均来自实际命令输出。

*本文件为只读产出，未修改任何项目代码/配置/数据。*
