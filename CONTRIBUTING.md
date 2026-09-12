# 贡献指南

感谢你对 world-sim 感兴趣。开始之前，请先了解这个项目的定位：

> **这是一个个人研究性质的宏观风险推演系统**，不是面向通用场景的产品。
> 因此：需求优先级由维护者决定，**提交不保证被合并**；较大的改动请先开 issue 讨论再动手，避免白做。

---

## 环境前置

| 工具 | 版本 | 用途 |
|:--|:--|:--|
| Docker + Docker Compose | 2.20+ | 运行全部服务（推荐方式） |
| Python | 3.12 | 本地跑测试 / 脚本 |
| Node.js | 20 | 开阳（前端）开发 |
| PostgreSQL | 16 + pgvector | 预测与指标存储 |

首次搭建请直接照根 [`README.md`](README.md) 的 **Quick Start（8 步）** 走，本文不重复。

---

## 仓库结构（monorepo）

本仓库是一个中文命名的 monorepo，四个子系统分别对应一套职责：

| 目录 | 代号 | 职责 |
|:--|:--|:--|
| `macro-scan/` | 天枢 | 观测采集与分析调度（数据源接入、指标落盘、报告生成） |
| `macro-sim/` | 天璇 | 演化仿真（蒙特卡洛推演、叙事生成） |
| `macro-ji/` | 天玑 | 校准验证层（对推演结果做事后校验与评分） |
| `kaiyang/` | 开阳 | 可视化前端 |

辅助目录：`sql/`（建表脚本）、`scripts/`（`init_db.sh` 初始化数据库、`init_kb.py` 生成知识库骨架）、`docs/`（设计与评审文档）、`infra/`（基础设施配置）。

---

## 开发时最容易踩的三件事

### 1. 改码后不一定生效 —— 两种部署模型

这是新人最常浪费时间的地方：

| 子系统 | 代码进入容器的方式 | 改完代码后 |
|:--|:--|:--|
| `macro-scan`（天枢） | **volume 挂载** | 改完即生效。由调度器拉起的一次性脚本无需重启；改动 `scheduler.py` 则需 `docker restart` |
| `macro-sim`（天璇） | **COPY 进镜像** | **必须重建镜像**，否则改动完全不生效 |
| `macro-ji`（天玑） | **COPY 进镜像** | **必须重建镜像**，同上 |

如果你改了天璇/天玑的代码却没看到任何变化，先确认镜像是不是没重建。

### 2. 知识库不随仓库分发

本仓库**不包含知识库数据**（历史语料、规则库等），这是刻意的外置设计。

克隆后需要自行构建骨架：

```bash
python scripts/init_kb.py --root <你的知识库目录>
```

然后把知识库根目录配到环境变量 `KB_ROOT`。缺失知识库时系统应**优雅降级**（跳过相关分析而非崩溃）—— 如果你发现它直接崩了，那是个 bug，欢迎报告。

### 3. 中文输出需要 UTF-8

源码和测试里有大量中文日志与断言消息。在非 UTF-8 locale 的环境下（尤其是 Windows / 精简容器），会因编码错误挂起或崩溃。

本地跑测试前请设置：

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
```

CI 里已全局设置这两个变量。

---

## 本地跑测试

CI 定义在 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)，四个 job 分别对应四个子系统。本地等价命令：

```bash
# 天枢（观测采集）
cd macro-scan && python -m pytest

# 天璇（演化仿真）
cd macro-sim && python -m pytest

# 天玑（验证层）
cd macro-ji && python -m pytest

# 开阳（前端）
cd kaiyang && npm ci && npm run test
```

---

## 配置与密钥

- 三个子系统**各自读取自己的 `.env`**，请分别从各自的 `.env.example` 复制后填写。
- **`.env` 已被 `.gitignore` 覆盖，绝不要提交真值**，也不要把真值写进 `.example` 文件。
- `.env` 是 docker compose 的注入源，改动后需 `docker compose up -d --force-recreate` 才生效 —— **`restart` 不会重读 `.env`**。
- 注意：本项目原部署在内网环境，部分默认值（如代理地址）指向私有网络。在你自己的环境里需要覆盖，或留空走直连。

---

## 提交约定

- **一个逻辑变更 = 一个 commit**，不要把无关改动混在一起（便于事后回溯是哪次改的）。
- 提交前 `git status` 确认干净，且 `.env` 未被纳入版本控制。
- commit message 中英文均可，首行请说清「改了什么 + 为什么」。
- **改了代码就要同步文档**（`README.md`、`docs/`、对应子系统的 `CHANGELOG.md`）。
- 涉及部署的改动，建议在独立分支验证后再合并。

- **推送前确认没有把密钥、内网地址或私有路径带进历史**。仓库内置两道本地门禁：
  `.githooks/pre-commit`（提交前）与 `.githooks/pre-push`（推送前，扫 `origin/main..HEAD` 全区间）。
  完整规范见 [`docs/PUSH-DISCIPLINE.md`](docs/PUSH-DISCIPLINE.md)。

  首次 clone 后启用一次即可：

  ```bash
  git config core.hooksPath .githooks
  ```

- **不要 force push 共享分支**（main）。确有必要时用 `--force-with-lease`，且先 `git fetch` ——
  长期不 fetch 会让 lease 校验退化成无条件的 `--force`。

> 维护者内部开发另有一套「变更记录（CHG）」流程，托管在外部知识库，**外部贡献者无需遵守**；
> PR 描述里写清「改了什么 / 怎么验证的」即可。

---

## 不会接受的改动

- **弱化或删除「任何兜底必须留痕」的约束**（例如把异常处理改回 `except: pass`）。这是历史事故换来的教训：静默失败会让故障长期不被发现。
- **把密钥、内网地址、私有主机别名写回代码或文档**。
- **引入 AGPL 等强传染性许可的依赖**。本项目为 MIT 许可，历史上曾主动替换掉 AGPL 组件以保持许可兼容。

---

## 问题反馈

- Bug / 需求：开 issue，请附上复现步骤与环境信息。
- **安全问题：请不要开公开 issue**，参见 [`SECURITY.md`](SECURITY.md)。
