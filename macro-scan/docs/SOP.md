# SOP.md — 齐活林交付流程（world-sim 适用版）

> 本文件把「交付总监」角色流程固化，避免只活在会话上下文里。最后更新：2026-07-31

## 角色与成员
> **当前运行模式：单人类总监 + 多角色 agent 辅助（常态启用，非"单 agent 闷头干"）。**
> - **人类总监唯一**：你（luoxi）是唯一的决策者与验收人，负责拍板与 review，**不写代码**。
> - **agent 端多角色分工**：PM / 架构 / 工程 / QA 由 agent 扮演，常态启用，目的是给项目**多视角复核**（动手前架构审、落码后 QA 回归），弥补单体 agent 的盲点。
> - **单人 ≠ 单 agent**：「单人」约束的是人类 headcount；「多角色 agent 辅助」是执行端的多视角，两者不冲突，不可因"单人"而撤销团队辅助。

- **主理人**：齐活林（Qi）· 交付总监（= 当前会话主 agent，代表你做协调/编排/汇编，**不代写专业产出**，各角色产出由对应 agent 执行）
- 产品经理 许清楚（Xu） / 架构师 高见远（Gao） / 工程师 寇豆码（Kou） / QA 工程师 严过关（Yan）

## 铁律（不可违反）
1. 团队创建（TeamCreate）只能主理人做，严禁委派成员。
2. 严禁主理人代写成员专业产出（PRD / 架构 / 代码 / 测试）。
3. 严禁跳过前序阶段（快速模式 / BugFix 快捷路径除外）。
4. 允许角色间直接交接产物（如 QA 断言直递工程），但主理人保留编排权（谁先谁后/能否开工）、用户保留最终审批权（准不准交付）。（2026-07-31 评审修订，原「严禁互连」已废）
5. **子任务命名**：调度成员时 `name` 与 `subagent_type` 必须传相同 Agent ID（`software-architect` / `software-engineer` / `software-product-manager` / `software-qa-engineer`），禁止中文名。

## 工作流路由（先判断再开工）
- ⚡ **快速模式**（单页 / 小工具 / ≤10 文件）→ TeamCreate → 工程师 → QA
- 🔧 **BugFix** → TeamCreate → 工程师定位修复 → QA 回归
- 🏗️ **标准 SOP**（中大型）→ PM(PRD) → 架构师(设计+任务分解) → 工程师(代码) → QA(测试)
- 📋 **部分工作流**（仅 PRD / 仅架构 / 仅测试 / 市场调研）

## ⭐ 上下文连续性协议（本次新增，针对长项目）
**问题**：会话上下文易碎（过长截断 / 新会话丢失历史）。解决方案——把「下一步指引」写到持久文件，不依赖对话历史。

1. **三层持久记忆**：
   - **T1 设计权威**：`worldsim-review-synthesis.md`（决策变更才改，不要每会话重写）
   - **T2 实时状态**：`STATUS.md`（每次会话结束更新，**冷启动必读**，几屏看懂）
   - **T3 流水日志**：`.workbuddy/memory/2026-MM-DD.md`（append-only 叙事）
2. **任务切片**：一个会话 = 一个自包含任务；每任务从 STATUS.md + 方案相关段落即可冷恢复，不需完整对话历史。
3. **结束仪式（停手前必做）**：
   - 更新 STATUS.md（done / next / blocked）
   - 标记方案任务表 ✅/🔲
   - 确认 NAS 代码处于一致状态（不是写了一半）
   - STATUS.md 顶部写一行「冷启动做 X」
4. **冷启动协议（会话开头）**：读 STATUS.md → 只读相关方案段落 → 按需读 memory → 执行下一步。

## 默认技术栈
- 前端：Vite + React + MUI + Tailwind CSS
- world-sim 后端：Python（numpy / scipy / pandas + fredapi），部署于 NAS Docker 容器，代码热挂载
- NAS 操作一律走 SSH + docker exec，**禁止信任 SMB 挂载的读/写**

## 交付卡点 / 并发安全（2026-07-31 四角评审固化）
> 评审最大共识风险 = 多 agent 改同一 NAS 代码库会无锁静默覆盖。以下为硬卡点，每次交付必过。

### 并发安全三件套（硬卡点）
1. **部署通道统一（禁混用）**：默认 `scp` 单文件 + 基线校验（sha256/md5 比对 + .bak + compileall + import smoke + `DATA_DIR==/workspace/data` 断言）；`rsync` 整目录仅限 lead 在合并改动后受控执行一次。各 agent 禁止随手 rsync 整目录（会静默回滚他人改动）。
2. **核心文件独占令牌**：`scheduler.py` / `fetcher_base.py` 由 lead 发令牌，同一时段仅一个 agent 可改，其余 agent 只准新增文件、不碰核心文件。
3. **数据源真相 = GitHub 单仓库**：world-sim 源码已在 `/vol2/1000/software/world-sim/.git`（含 macro-scan + macro-sim），部署是仓库产物的运行副本。**不在 NAS 另起 git**；唯一纪律：**部署须对应一个已知 commit**（改动先在仓库 commit，再部署）。

### 两道静态闸（交付卡点，强制 · ⑤ 用户 2026-07-31 20:58 批准固化）
- **闸一 · import 白名单**：全仓 grep import，仅允许白名单（DATA_DIR / WORKSPACE / CRUCIX_REMOTE_URL 等）。专防 `optim_config` 缺变量（如 FRED_PROXY）致 ImportError 走 fallback、DATA_DIR 落到非持久卷 `/data` 的坑。
- **闸二 · 单文件 bind mount 扫描**：扫 compose，发现文件级 volume 映射即拦下，强制目录挂载。专防 `sim_trigger` 单文件挂载 + `os.replace` 原子写 = 静默断链（P0）。

### QA 影子跑（④ 接受）
- 支持 `DATA_DIR` 环境变量覆盖；QA 在 `/workspace/qa_shadow` 隔离目录跑同一份代码，产出与生产 diff 比对，不污染生产数据。

### 总监闸门命名（⑦ 批准）
- 总监拍板闸门 = **D1/D2**（原 G2/G3 同名不同义，已改名）；G1 保留为 probit 代码内口径断言（非闸门）。
