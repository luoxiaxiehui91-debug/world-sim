# Sprint-0 编排评审综合裁决

> 四角评审（PM 许清楚 / QA 严过关 / 架构 高见远 / 工程 口）结论一致：**原编排基本合理，无需重做，微调即可**。最大共识风险 = **并发/落地安全**（无锁读改写 + rsync 整目录回滚 = 静默覆盖）。

---

## 一、已裁决采纳的修正（无需再议）

| # | 修正 | 依据 |
|---|------|------|
| 1 | **P0 更名为「止血线」**，并设常设「天璇 predictions 进度周报」（演示光环不得掩盖天璇 0%） | PM① |
| 2 | **总监闸门 G2/G3 → 改名 D1/D2**，避免与 §7.4 的 G1/G2/G3 撞义；**G1 保留**为 probit 口径断言并写进任务卡代码 | PM② |
| 3 | **I1 提级为独立横切契约件**，先于 probit 定稿；schema_version 与 model_ver 拆两字段，回补 FCI(fci-1.1) | 架构①、PM⑥、QA③ |
| 4 | **A1 让位排 probit 之后**；fetcher_base 改动收敛为「新文件 mixin + 原文件 1 行调用」；retry 默认 opt-in 先 1–2 fetcher 试 | PM③、工程、架构③ |
| 5 | **A2 砍掉 Brier 校准**（无 predictions 做不了；BAMLH0A0HYM2 仅 837 行，burn-in504 后样本不足，先算功效）；只交付 ETL+聚合+三闸门 | PM④、架构③ |
| 6 | **A3 拆 A3a / A3b**：A3a（命令信封/鉴权/JOBS 外置设计）现在起；A3b（天璇端点）等 D2 拍板。JOBS 外置避免控制面改源码 | PM⑤、架构②、QA⑤ |
| 7 | **并发/落地安全三件套**（硬卡点，固化 SOP）：① 部署通道统一（禁 scp patch 与 deploy.sh rsync 混用）；② 核心文件独占令牌（scheduler.py / fetcher_base.py 由 lead 发令牌，同期单 agent 可改，其余只新增）；③ NAS 代码目录 git init + 落地闸（基线 sha256/md5 + .bak + compileall + import smoke + `DATA_DIR==/workspace/data` 断言） | 架构③、工程、QA①② |
| 8 | **QA 前置 + 静态闸**：QA 先出验收断言清单交工程 → 落码 → 独立回归；两道静态闸（import 白名单仅 DATA_DIR/WORKSPACE/CRUCIX_REMOTE_URL；单文件 bind mount 扫描）为交付卡点 | QA①④ |
| 9 | **probit 实现约束**：读 `fred_history/T10Y3M.csv`，禁直连 FRED（避坑⑥）；只算 Φ 不拟合；ffill limit=5 禁 fillna(0)；不 import compute_fci 只复用写盘/vintage 模式 | 工程、PM③ |

---

## 二、修正后的编排骨架（重排）

```
阶段0（横切，先定稿）
  I1  Pydantic 契约（extra=forbid + 非平凡哨兵 + schema_version/model_ver 拆分）
      → 回补 FCI schema_version；QA 先出断言用例（spec-first）

阶段1（独占令牌 · 一次 restart）
  P0  probit 止血线（读落盘 CSV，只算 Φ，G1 代码断言写进任务卡）

阶段2（独占令牌）
  A1  回填 retry-on-missing（fetcher_base = mixin+1行；retry 默认 opt-in）

并行线（纯新文件 · 全程并行）
  A2  GED ETL（只 ETL+聚合+三闸门；Brier 校准移出）
  B1  crucix 字段级对照表（禁摘代码，AGPL 传染）
  B2  OpenSky 限额核对（并入 B1，不占独立轨）

常设（独立于演示轨）
  天璇 predictions 进度周报

A3a  命令信封/鉴权/JOBS 外置设计（现在起，不等闸门）
A3b  天璇端点（等 D2 拍板）
```

**重启风险**：I15/I30 是当日分钟取模+桶去重，restart 丢内存桶 → 可能重复/漏触发。建议**合并改动一次 restart**，窗口避开 :00/:15/:30/:45 与 0530/0535/0908/0910 槽。

---

## 三、给总监（luoxi）的拍板清单

以下为有取舍、需你定夺的项（强共识项已在上文直接采纳）：

1. **天璇本 Sprint 是否起轨？** 若不起，是否确认「单独周报」机制即视为达标？（PM①）
2. **部署通道具体选哪个？** 统一为「scp 单文件 + 基线校验」还是「deploy.sh rsync 已变更文件 + 基线校验」？核心：禁混用。（工程）
3. **NAS 代码目录 git init 是否接受？**（架构③ / 工程）
4. **DATA_DIR 环境变量可覆盖 + 允许建 `/workspace/qa_shadow` 影子目录是否接受？**（QA 影子跑前置，并入 I1）
5. **两道静态闸（import 白名单 / 单文件挂载扫描）是否固化进 SOP 交付卡点？**（QA）
6. **SOP 铁律4「成员信息流经主理人」与当前 agent 互连模式冲突，以哪条为准？**（PM⑥）
7. **总监闸门改名 D1/D2 是否确认？**（默认采纳，列此备查）

---

## 四、四角评审原始结论速览

- **PM**：6 处修正（2/3 必改）+ 5 项拍板；强调主线叫法错、G 编号撞名最危险。
- **QA**：3 项微调；核心=独立 QA 必须有环境级断言（DATA_DIR 落点 / inode 一致性 / 字段非平凡哨兵），影子跑隔离，QA 前置出验收清单。
- **架构**：并发静默覆盖是真风险；I1 放错层、A3 过度串联、schema_version/model_ver 须拆、BAMLH0A0HYM2 功效先算。
- **工程**：量化工时（probit 0.5 人日、A1 0.5–1、A2 2–3、A3 ≥1–2）；并发踩踏（无锁读改写 + rsync 回滚）；probit 别直连 FRED。
