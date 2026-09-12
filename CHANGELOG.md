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
  - `pre-push`（新增）：扫 `origin/main..HEAD` **全区间** —— 补上 `pre-commit` 只检查 staged 的盲区（push 推的是全部历史，不只是最新改动）。
  - 零硬依赖：优先调用 gitleaks，未安装时回退内建正则，保证任何机器上都生效。
- **规范文档**：新增 [`docs/PUSH-DISCIPLINE.md`](docs/PUSH-DISCIPLINE.md)，含三层防护模型、push 前自检清单、force push 纪律与泄露事故响应；`CONTRIBUTING.md` 提交约定段同步。

### Changed

- 旧门禁仅存在于 `.git/hooks/`（**不随仓库分发，clone 后即失效**），已迁入 `.githooks/`。


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
