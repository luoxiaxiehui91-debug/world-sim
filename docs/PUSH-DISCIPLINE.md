# Git Push 纪律

> 本文件是仓库内的 push/push 安全规范，面向维护者与贡献者。
> 配套实现：`.githooks/pre-commit`（提交前）、`.githooks/pre-push`（推送前）。

---

## 1. 为什么需要这套纪律

**push 是单向闸门。** 本地 commit 可以随便改（`amend`、`rebase`、`reset`），一旦 push 到公开仓库就是覆水难收 —— 而且公开仓库的 push 事件会被自动化程序在**几分钟内**爬取。

**最关键的一条认知**：如果凭证被推了上去，**"删掉文件再提交一次"是无效的**。Git 历史不可变，那条记录永远都在。唯一有效的解药是**吊销/轮换该凭证** —— 让历史里那串字符变成废纸。

所以纪律的目标不是"永不泄露"，而是：**分层拦截，且泄露后影响可控**。

---

## 2. 三层防护模型

| 层 | 位置 | 拦什么 | 能否被绕过 |
|:--|:--|:--|:--|
| **L1 本地提交** | `.githooks/pre-commit` | 本次 staged 的敏感文件名 + 敏感形态 | 能（`--no-verify`） |
| **L2 本地推送** | `.githooks/pre-push` | `origin/main..HEAD` 全区间的历史 | 能（`--no-verify`） |
| **L3 CI** | GitHub Actions | 全历史密扫（需另建，见 §6 待办） | 需仓库权限 |
| **L4 服务端** | GitHub Push protection | 已知 200+ 凭证格式 | **不能**（bypass 需留审计记录） |

任何一层都不单独可靠 —— 本地层能被 `--no-verify` 绕过，所以**必须有服务端层兜底**；服务端层只认已知格式，所以**本地层的形态扫描仍然必要**。

### 为什么 pre-push 不能被 pre-commit 取代

- `pre-commit` 只看 **staged** 的改动
- `push` 推的是 **`origin/main..HEAD` 的全部历史**

一次 push 可能带 20 个 commit，其中第 3 个夹了密钥 —— 那次提交时 hook 可能没装、没开，或被 `--no-verify` 跳过了。到 push 时它已经在历史里了。**所以必须在 push 这一跳再拦一次，且要扫整个区间。**

---

## 3. 安装（每台机器一次）

```bash
git config core.hooksPath .githooks
```

验证：

```bash
git config core.hooksPath        # 应输出 .githooks
git ls-files -s .githooks/       # 模式位应为 100755
```

> ⚠️ 设置 `core.hooksPath` 后，`.git/hooks/` 下的钩子**不再生效**。本仓库已把 pre-commit 一并迁入 `.githooks/`，不会丢失原有的 `.env` 拦截。

---

## 4. 每次 push 前 30 秒自检

```bash
# ① 改动面：有没有意料之外的文件
git diff origin/main..HEAD --stat

# ② 敏感形态扫描
git diff origin/main..HEAD | grep -nE 'sk-[A-Za-z0-9]{20,}|ghp_|AKIA[0-9A-Z]{16}|PRIVATE KEY'

# ③ 确认远端与分支（别推错仓库）
git remote -v && git branch --show-current

# ④ 确认领先几条
git log origin/main..HEAD --oneline
```

任意一条有命中 —— 停下来查清楚再推。

---

## 5. Force push 纪律

本仓库历史上因清理敏感数据（filter-repo）多次强制推送过。**转 public 后必须停止。**

| 规则 | 说明 |
|:--|:--|
| 共享分支（main）禁 force push | 由 GitHub 分支保护兜底 |
| 必须时用 `--force-with-lease` | 带租约校验：若远端已被他人更新则拒绝。**不是 `--force`** |
| 先 `git fetch` 再推 | `--force-with-lease` 依赖本地记录的远端 hash；长期不 fetch 会退化成 `--force` |
| 历史错误优先 `git revert` | 保留审计轨迹，而不是 `reset` + 强推抹掉事件线索 |

---

## 6. 待办（本仓库尚未完成）

- [ ] **L3**：CI 增加 gitleaks job（需 `fetch-depth: 0`，否则只看最新 commit，中间 commit 的密钥会漏）
- [ ] **L4**：转 public 后开启 GitHub Secret scanning + Push protection，并为 main 开启分支保护（禁 force push）
- [ ] **转 public 前**：跑一次**全历史**扫描，而不只是工作树
- [ ] 决策：历史提交中的作者邮箱是否暴露（转 public 后任何人可见）

---

## 7. 事故响应（顺序不能错）

| 时间 | 动作 |
|:--|:--|
| 0–5 min | 确认泄露类型与影响面；确认仓库公私状态 |
| **5–15 min** | **吊销 / 轮换凭证 —— 先做这一步** |
| 之后 | 视需要用 `git filter-repo` 清理历史（破坏性，需强推 + 全员 re-clone） |
| 之后 | 查服务方审计日志，确认泄露期间有无异常使用 |

**第 2 步不能省，也不能往后放。** 清理历史是"消疤"，吊销才是"治疗"。

---

## 8. 误报处理

门禁用的是**形态判据**（高熵 / 已知前缀正则），不是文件名黑名单 —— 因为后者拦不住写在 `.py`、`.ts` 里的硬编码凭证。

已内置降噪：扫描时跳过常见注释行（`#`、`//`、`*`、`<!--` 开头），并排除 `.githooks/` 自身。

若仍误报：

1. 确认是否真的只是文档/示例 —— 若是，优先改成不含真实形态的占位描述
2. 确需放行：加入 `.gitleaksignore`
3. 紧急绕过：`git commit --no-verify` / `git push --no-verify`（会被 CI 与 Push protection 再拦）
