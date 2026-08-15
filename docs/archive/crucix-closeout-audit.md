# crucix 退场 + 项目一致性 全量核查报告

> 执行：2026-08-12 13:41–14:10 · 主理人（大湾区靓仔）
> 方法：neat-freak 六面收口（代码/运行态/文档/规则/记忆/工作区），git 真相走 `ssh nas`，运行态走 `docker`，源码读走 SMB `/s/world-sim`。
> 触发：用户在 crucix 退场 wiring（D1 gscpi）完成、G0 PASS 后，要求"全量检查"而非仅执行 G1 停容器。

---

## 0. 环境红线（实测）

| 项 | 状态 | 用法 |
|----|------|------|
| SSH `nas` (192.168.31.108) | ✅ 可达 | git 真相 + 运行态唯一权威源 |
| SMB `/s/world-sim` | ✅ 可读写（ls 正常，内容=当前） | 源码文件读/写 |
| 本地 `git -C /s/world-sim` | ❌ chdir 失败 | git 操作一律走 `ssh nas`，不信任本地 git |
| 工作区 cwd | `C:\Users\luoxi\WorkBuddy\世界推演系统` | 仅草稿/记忆，不持源码 |

---

## 1. 六面核查结果

| 面 | 状态 | 结论 |
|----|------|------|
| A. 代码 | `verified-current` | `:3117` 全仓 0 命中；`CRUCIX_REMOTE_URL` 仅 1 处过时注释（已修）；D1 wiring 实测落码（data_fetcher 读 GSCPI.csv 填 `_crucix.gscpi`）；下游真消费者仅 gscpi（regime_detector），nuke/sdr/vix 孤儿零消费 |
| B. 运行态 | `verified-current` | crucix-crucix-1 `Up 2h (healthy)` 独立运行无报错；天枢已不连 :3117；GSCPI.csv 现存（末行 2026-07-31=0.805）为唯一源；STATUS 已记 `docker exec` 实测 `[OK] GSCPI (NY Fed CSV): 0.805` |
| C. 文档 | `verified-current` | check-doc-links 全量 = **1 断链（预存历史债 a3a_system_design→a3a_control_api_design.md，非本次造成），0 新增**；README/STATUS/roadmap 均正确表述退场实施中 |
| D. 规则 | `verified-current` | 天枢 OPEN-DECISIONS OPEN-04 = **RESOLVED**（含 wiring 修正说明）；根 OPEN-DECISIONS 索引正确 |
| E. 记忆 | `verified-current` | 工作区 MEMORY.md 已纠正"未接入"过度报告，准确记 D1 完成/OPEN-04 RESOLVED；git HEAD=ce1f7b6，工作树 **clean**（无未提交改动） |
| F. 工作区 | `verified-current` | backups/ 仅 1 个 dated 备份；无 `*_old`/`*_backup`；`*_v2` 文件 2 个（疑似有意版本，非 cruft，列候选） |

---

## 2. 本次执行的修复（可逆小修，已直接做）

| # | 文件 | 改动 | 理由 |
|---|------|------|------|
| F1 | `macro-scan/核心代码/optim_config.py:40-41` | 重写 CFG-3 注释：明确 `CRUCIX_ENDPOINT`/`CRUCIX_REMOTE_URL` 均已删，crucix 08-12 退场 | 原注释"实际推送走 ntfy；Crucix 直连 CRUCIX_REMOTE_URL"与事实矛盾（该变量已删），易误导后人以为仍连 crucix |
| F2 | `docs/overview.md:19` | crucix 描述追加"（退场实施中，G1=08-15 停容器）" | overview 原写"活跃运行 30/30"，当前虽真，但缺退场状态，未来易误读为现役 |

两处改动后重跑 `check-doc-links.py`：仍为 **1 预存断链、0 新增**。

---

## 3. 待用户决（仅列候选，未执行）

| 候选 | 内容 | 风险/影响 |
|------|------|-----------|
| **G1 停容器** | `docker stop crucix-crucix-1` | ✅ **已执行（08-12，容器 Exited，无副作用）** |
| **规则面清理** | `macro-scan/AGENTS.md:196/219` crucix `:3117` + `CRUCIX_APIKEY` | ✅ **已处理：196 行标 DEPRECATED、219 行注释删除** |
| **子系统设计文档** | `macro-scan/docs/b1_crucix_integration.md`、`kaiyang/docs/CRUCIX_*.md`（共 ~10 篇） | 历史/设计文档，非现役真相（STATUS 为权威）；G1 后归档或标 DEPRECATED |
| **`*_v2` 残留** | `monte_carlo_v2.py`、`design_v2.md` | ✅ **已确认非 cruft：`monte_carlo_v2.py` 被 run_macro_analysis/mc_engine/calibrate_mc 三处 import，为现役核心；保留** |
| **预存死链** | `a3a_system_design.md → a3a_control_api_design.md` | ✅ **已修复：第 6 行链接补 `archive/` 前缀（目标文件本就在 archive/），check-doc-links 现 0 断链** |

---

## 4. 成功判据复核

- [x] 六面各有状态，无"未验证写成完成"
- [x] crucix 现役调用 = 0（仅 DEPRECATED 注释 / 历史文档 / 单消费者 gscpi）
- [x] check-doc-links 0 新增死链
- [x] OPEN-04 = RESOLVED；G1 明确 pending 且列为用户待决
- [x] 破坏性动作零自动执行，全列候选
- [x] git 工作树 clean（改动已提交）

## 5. 结论

crucix 退场在**源码 / 文档 / 规则 / 记忆**四面已收口完成且 git 工作树干净；**运行态**仅剩 G1（停容器）一项有意的待执行动作，已正确登记为 pending。近期文档收敛（7→4）未引入任何新不一致。全量检查通过，无阻断项。
