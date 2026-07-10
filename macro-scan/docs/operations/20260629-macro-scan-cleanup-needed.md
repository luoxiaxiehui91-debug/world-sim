# 现况说明：2026-06-29 文档同步机制引入后的混乱状态

**记录时间**：2026-06-29 晚  
**记录者**：Claude Code  
**状态**：需要在新 session 整理

---

## 功能层面（已完成，代码是对的）

新增了三个文件，功能均已验证：

| 文件 | 功能 | 状态 |
|:---|:---|:---|
| `核心代码/check_doc_sync.py` | pre-commit hook，commit 时按联动矩阵检查文档 | ✅ 测试通过 |
| `核心代码/check_doc_drift.py` | 文档漂移巡检，NAS crontab 每日 10:00 跑 | ✅ 测试通过 |
| `核心代码/gen_docs.py` | 从代码生成 INDEX.md/FILE_MANIFEST.md 对应节 | ✅ 测试通过 |
| `.pre-commit-config.yaml` | pre-commit 框架配置 | ✅ |
| `deploy.sh` | 新增 `--sync` 全量 rsync 同步 | ✅ |

NAS crontab 已新增：
```
0 10 * * * NTFY_TOPIC=***REMOVED*** python3 /vol2/1000/software/macro-scan/核心代码/check_doc_drift.py >> /vol2/1000/software/macro-scan/logs/doc_drift.log 2>&1
```

---

## 混乱的地方

### 1. 版本号乱

今天从 v3.5.21 飙到 v3.5.27，共 9 个 commit，其中：
- `test: 故意不更新文档`（4bc1373）也被推上了 GitHub，不应该在主分支
- 3.5.26 和 3.5.27 是同一件事（deploy.sh LF 修复），拆成了两个版本
- 部分 commit 的 CHANGELOG/VERSION 是补打的，不在同一个 commit 里

### 2. commit 历史不干净

```
f19b531 fix: deploy.sh 转 LF v3.5.27           ← 和 3.5.26 应该合并
94adef1 docs: bump VERSION 3.5.26 + CHANGELOG   ← 补打，不规范
1ee6280 fix: deploy.sh 加入 --sync v3.5.26
c0194bf docs: 文档同步机制完整 runbook v3.5.25
41ec389 docs: NAS crontab 运维日志 v3.5.25
8c22276 fix: doc_drift 改由 NAS crontab v3.5.25
ad8d889 fix: check_doc_drift.py 路径修复 v3.5.24
3324f98 feat: watchdog 文档漂移巡检 v3.5.23
551b8f0 fix: check_doc_sync.py 中文路径解码
4bc1373 test: 故意不更新文档                    ← ⚠️ 不该在主分支
bd60685 feat: 文档同步保障机制 v3.5.22
a65558a chore: 对齐本地最新版本 v3.5.21         ← 你重构后的干净起点
```

### 3. 源码区建立过程有遗留

- NAS 上有一个遗留软链接（可能）：`/vol2/1000/software/macro-scan/核心代码/TuiYan_CHANGELOG.md`，建了但没用，需要确认是否还在

---

## 建议新 session 做的事

1. **确认软链接是否还在**，在的话删掉
   ```bash
   ssh TSX@192.168.31.108 "ls -la /vol2/1000/software/macro-scan/核心代码/TuiYan_CHANGELOG.md"
   ```

2. **squash 整理 commit 历史**：把 a65558a 之后今天的 9 个 commit 压成 2 个干净的：
   - `feat: 文档同步保障机制（pre-commit + watchdog + gen_docs）vX.X.X`
   - `chore: deploy.sh 全量 rsync 同步 vX.X.X`

3. **VERSION 定到一个合理的号**，比如 3.5.22（今天实际就加了这一件功能）

4. **force push 清理 GitHub**（需要你授权）

---

## 不需要动的

- NAS 运行区代码是对的（v3.5.27 内容正确）
- NAS crontab 已正确配置
- pre-commit hook 已安装，功能正常
- 三个新脚本功能均已验证
