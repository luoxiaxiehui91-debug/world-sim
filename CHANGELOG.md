# Changelog（仓库级）

本文件**只记录跨子系统 / 仓库级**的变更：构建与部署方式、目录调整、开源准备、多子系统联动的改造等。

各子系统的功能变更请查阅它们各自的 CHANGELOG —— **本文件不会复制它们的内容**（复制只会产生第二个必然漂移的真相源）：

| 子系统 | 版本 | 变更记录 |
|:--|:--|:--|
| 天枢 `macro-scan`（观测采集 / 分析调度） | [`VERSION`](macro-scan/VERSION) | [`CHANGELOG.md`](macro-scan/CHANGELOG.md) |
| 天璇 `macro-sim`（演化仿真） | [`VERSION`](macro-sim/VERSION) | [`CHANGELOG.md`](macro-sim/CHANGELOG.md) |
| 天玑 `macro-ji`（校准验证） | 以镜像 tag 计 | [`CHANGELOG.md`](macro-ji/CHANGELOG.md) |
| 开阳 `kaiyang`（可视化前端） | [`VERSION`](kaiyang/VERSION) | [`CHANGELOG.md`](kaiyang/CHANGELOG.md) |

仓库级变更**不单独发版本号**，条目以日期归档。

---

## [Unreleased]

### Added

- **Git push 纪律（本地两层门禁）**：新增 `.githooks/pre-commit` 与 `.githooks/pre-push`，纳入版本控制随仓库分发，启用方式 `git config core.hooksPath .githooks`。
  - `pre-commit`：判据由「文件名黑名单」升级为「形态判据」，可拦截硬编码凭证与内网地址；保留原有 `.env` 文件拦截。
  - `pre-push`（新增）：扫**本次推送的实际 ref/sha** 全区间 —— 补上 `pre-commit` 只检查 staged 的盲区（push 推的是全部历史，不只是最新改动）。区间来源与身份校验的后续加固见下方 `### Changed`。
  - 零硬依赖：优先调用 gitleaks，未安装时回退内建正则，保证任何机器上都生效。
- **规范文档**：新增 [`docs/PUSH-DISCIPLINE.md`](docs/PUSH-DISCIPLINE.md)，含三层防护模型、push 前自检清单、force push 纪律与泄露事故响应；`CONTRIBUTING.md` 提交约定段同步。

### Changed

- 旧门禁仅存在于 `.git/hooks/`（**不随仓库分发，clone 后即失效**），已迁入 `.githooks/`。
- **脱敏**：`macro-scan/TuiYan_CHANGELOG.md` 中一处 `EIA_API_KEY` 明文值替换为占位符。该 key 无权限差异、所涉数据全公开，且经核查 EIA 无 key 管理/吊销入口（官方仅 register 与 forgot-key，后者为「重发原值」）→ 定级 P2。**边界**：历史中 3 个 commit 仍携带该明文，属 `filter-repo` 重写范畴，本次未做。

- **提交邮箱隐私治理（全历史重写）**：仓库全部历史提交的 author（577 条）与 committer（576 条）邮箱由个人 gmail 改写为 GitHub noreply 地址，消除转 public 后邮箱被爬虫索引、跨平台身份关联的暴露面。
  - 重写后 3 个分支全部强推：`main` / `b0/news-forecast-pg` / `test/regression-suite-and-ci`；本地 `git config user.email` 同步改为 noreply，切断后续新提交的再污染源。
  - **验证**：tree hash 全集对拍完全一致（仅元数据变更、文件树零改动）；GitHub 服务端 `GH007`（push 时强制校验全历史邮箱）未报错；容器挂载目录 `macro-sim/output` 指纹与重写前一致（14 文件 / 662603 字节）。
  - **副作用修复**：`filter-repo` 会自动删除 `origin` remote 与分支 upstream 配置，已重建。
  - **边界**：工作树中 6 处引用旧 commit hash 的文档已同步为新 hash；另有 1 处（`macro-scan/CHANGELOG.md` 中 `HEAD=94bc47e`）系 2026-09-11 上次重写遗留的 dangling commit，不在本次映射表内，保持原样。

- **【修复】`pre-push` 门禁的扫描区间错配与身份盲区**（2026-09-13）：扫描区间改为**逐 ref 解析 git 经 stdin 传入的真实推送对象**，不再硬编码 `origin/main..HEAD`。后者是「本地领先 main 的量」，与「本次推出去的东西」是两个语义 —— 推非 HEAD 分支 / `git push --all` / 一次推多个 ref 时区间会算错甚至为空，导致密钥形态扫描与敏感文件名检查**一起静默失效**（原缺陷实测：含明文密钥的非 HEAD 分支被放行）。
  - 新区间规则：远端已有该 ref → `remote_sha..local_sha`；新分支（remote_sha 全零）→ 与**空树**比较（扫该 ref 全部历史）；删除 ref → 跳过；**stdin 为空 → 退化为全历史扫描**（宁可多扫，不可漏扫）。
  - 提交身份由「提示」升级为**硬拦截**：author 与 committer **双字段**并集对邮箱白名单校验，越界即拒绝推送。
  - 新增**本地身份静态自检**（`git config user.email`），与「当前有无待推提交」解耦，无需提交即可预警。
  - 新增环境变量：`WORLDSIM_EMAIL_ALLOWLIST`（追加放行邮箱 glob）、`WORLDSIM_LOCAL_FEATURE_SCAN`（是否扫描本项目私有部署特征，默认 `1`；开源给外部使用时应设为 `0`）。
  - 同步修正 `refs/remotes/origin/*` 与真实远端的脱钩（历史重写遗留）—— `git status` 不再显示 `ahead 580, behind 572` 之类的假领先。



---

## [2026-09-11] 开源准备

为把仓库从私有内网项目转为可公开的形态所做的一批改造。目标：**开源框架与逻辑，数据与配置完全外置**，让任何人能从零 clone 后自行搭建。

### Added

- **配置全面外置**：所有密钥、口令、主题名改为 `${VAR}` 注入，不再出现在代码或编排文件中；三个子系统各自提供 `.env.example`（区分必需 / 可选）。
- **路径参数化**：知识库根目录改为 `KB_ROOT` 可配置，不再写死私有路径。
- **知识库外置**：知识库数据不再随仓库分发，新增 `scripts/init_kb.py` 生成骨架目录；知识库缺失时系统优雅降级而非崩溃。
- **Quick Start**：`README.md` 重写为 8 步上手流程，新增 `scripts/init_db.sh` 与 Dockerfile 构建参数，覆盖「从零 clone」场景。
- **社区文件**：新增 [`CONTRIBUTING.md`](CONTRIBUTING.md)（含部署模型差异、中文编码、测试命令）、[`SECURITY.md`](SECURITY.md)（私有报告渠道、部署者须知）、本文件。

### Changed

- **从零 clone 实测**：在干净环境完成 build + config + 镜像内冒烟验证，并据此修正了 pip 源不可达、端口占用等问题。

### Removed

- **历史清理**：剔除体积较大的知识库目录；对全部已跟踪文件做明文凭证扫描，**结果为 0 命中**。
- **移除版本断言**：`README.md` 不再写死具体版本号（避免文档与代码版本漂移）。

### 说明

- 本条目只记录仓库级动作，**不包含各子系统的功能变更** —— 那部分一直在各自的 CHANGELOG 里，未做迁移。
- 46 MB 的中文 NLP 模型 wheel（`macro-scan/wheels/`）**保留**：它是离线构建依赖，被 Dockerfile / requirements / CI 通过 `--find-links` 引用，移除会改变构建行为，故单独立项评估。
