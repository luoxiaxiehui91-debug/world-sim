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
| **L2 本地推送** | `.githooks/pre-push` | **本次推送的实际 ref/sha**（逐 ref 解析）+ 提交身份白名单 | 能（`--no-verify`） |
| **L3 CI** | GitHub Actions | 全历史密扫（需另建，见 §6 待办） | 需仓库权限 |
| **L4 服务端** | GitHub Push protection | 已知 200+ 凭证格式 | **不能**（bypass 需留审计记录） |

任何一层都不单独可靠 —— 本地层能被 `--no-verify` 绕过，所以**必须有服务端层兜底**；服务端层只认已知格式，所以**本地层的形态扫描仍然必要**。

### 为什么 pre-push 不能被 pre-commit 取代

- `pre-commit` 只看 **staged** 的改动
- `push` 推的是**本次推送的每个 ref 所指的全部历史**（不是「本地领先 main 的那部分」）

一次 push 可能带 20 个 commit，其中第 3 个夹了密钥 —— 那次提交时 hook 可能没装、没开，或被 `--no-verify` 跳过了。到 push 时它已经在历史里了。**所以必须在 push 这一跳再拦一次，且要扫整个区间。**

### 扫描区间的来源：stdin 而非 `origin/main`

`git push` 会把**本次实际要推的 ref/sha** 通过 stdin 交给 `pre-push`（每行 `<local ref> <local sha> <remote ref> <remote sha>`）。门禁**逐 ref** 解析它并据此计算区间：

| 情形 | 扫描区间 |
|:--|:--|
| 远端已有该 ref | `remote_sha..local_sha`（只扫本次新增） |
| 新分支（远端 ref 不存在，remote_sha 全零） | 与**空树**比较 → 扫该 ref 的全部历史 |
| 删除 ref（local_sha 全零） | 跳过（没有内容要扫） |
| stdin 为空（异常调用） | 退化为**全部历史**扫描（宁可多扫，不可漏扫） |

> 早期版本把区间硬编码为 `origin/main..HEAD`。那是「本地领先 main 的量」，与「本次推出去的东西」是**两个语义** ——
> 推非 HEAD 分支、`git push --all`、一次推多个 ref 时，区间会算错甚至为空，导致密钥密扫与敏感文件名检查**一起静默失效**。
> 改用 stdin 的真实推送对象后，这类漏扫被根除。

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

> ⚠️ **身份前置**：`pre-push` 会校验 `git config user.email` 是否落在邮箱白名单内（见 §9）。新 clone 的机器若未配置，推送会被拦下并打印修复命令 —— 这是**期望行为**，不是故障。

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

> 说明：上面的 `origin/main..HEAD` 表示「本地领先 main 的量」，此处以「推 main」为例；
> 推其它分支或一次推多个 ref 时，请把 `origin/main` 换成对应的远端 ref。
> 门禁本身**不依赖**这个区间（它从 stdin 解析真实推送对象，见 §2），这里仅作人工复核参考。

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
  - ⚠️ 这几项能力在**私有仓免费版不可用**（设置页会提示需升级）；其中 Secret scanning 与账户级 Push protection 在转 public 后**自动生效**，Dependabot alerts / Private vulnerability reporting / 分支保护需手动开启。正确顺序 = 先转 public，再（几分钟内）点完手动项
- [ ] **转 public 前**：跑一次**全历史**扫描，而不只是工作树
- [x] **转 public 前**：跑一次**全历史**扫描，而不只是工作树 —— 2026-09-13 完成（commit 邮箱全历史重写 + 全 refs 复扫）
- [x] 决策：历史提交中的作者邮箱是否暴露 —— 已决策**不暴露**，全历史 author/committer 已重写为 GitHub noreply
  - 详见 `operations/CHG-20260913T124409-world-deduction.md` 与 `decisions/world-deduction/0017-history-rewrite-discipline.md`

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

---

## 9. pre-push 的邮箱白名单与环境变量

`pre-push` 的第 3 关（提交身份）与第 4 关（本地身份静态自检）会**拦截**白名单之外的提交身份 ——
目的是防止个人邮箱随公开历史泄露（commit 的 author 与 committer 两个字段都会随公开历史可见）。

**内置白名单**：`*@users.noreply.github.com`（GitHub 隐私地址）、`*@local`（本地匿名占位）。

| 环境变量 | 默认 | 作用 |
|:--|:--|:--|
| `WORLDSIM_EMAIL_ALLOWLIST` | 空 | 追加放行的邮箱 glob（空格分隔），叠加在内置白名单之上 |
| `WORLDSIM_LOCAL_FEATURE_SCAN` | `1` | 是否同时扫描本项目私有部署特征（内网网段 / 私有部署根路径 / 运维账号形态）。**开源给外部使用时应设为 `0`** |

被拦时的修复：

```bash
git config user.email "<你的 *@users.noreply.github.com 地址>"
```

该地址可在 GitHub 设置页（Settings → Emails → Keep my email addresses private）查到。

若确有正当理由保留其它地址（例如开源后贡献者使用工作邮箱），显式放行：

```bash
export WORLDSIM_EMAIL_ALLOWLIST="someone@example.com"
```
