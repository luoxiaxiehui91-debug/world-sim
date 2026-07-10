# Runbook：文档同步保障机制 安装 & 卸载

**建立时间**：2026-06-29  
**版本**：v3.5.25  
**适用项目**：macro-scan  

---

## 概览

本机制由两条路线组成，防止多 agent 协作时文档漂移：

| 路线 | 触发时机 | 覆盖场景 |
|:---|:---|:---|
| pre-commit 联动拦截 | `git commit` 时 | 走 git 流程但漏更新文档 |
| watchdog 巡检 | 每日 10:00（NAS crontab） | 直接改 NAS 运行区绕过 git |

**涉及的组件**：

| 组件 | 位置 | 是否在 git |
|:---|:---|:---|
| `check_doc_sync.py` | `S:\macro-scan-src\核心代码\` | ✅ |
| `check_doc_drift.py` | `S:\macro-scan-src\核心代码\` | ✅ |
| `gen_docs.py` | `S:\macro-scan-src\核心代码\` | ✅ |
| `.pre-commit-config.yaml` | `S:\macro-scan-src\` | ✅ |
| pre-commit hook | `S:\macro-scan-src\.git\hooks\pre-commit` | ❌（本地）|
| NAS crontab 条目 | TSX@192.168.31.108 | ❌（宿主机）|

---

## 安装

### 1. 建立源码区（首次）

```bash
# 从 GitHub clone
git clone https://github.com/luoxiaxiehui91-debug/macro-scan.git S:\macro-scan-src
```

### 2. 安装 pre-commit hook

在源码区执行一次（每台机器/每个 agent 首次接手时）：

```bash
pip install pre-commit
python -m pre_commit install   # Git Bash 下 pre-commit 命令可能权限受限，用此方式
```

验证：
```bash
python -m pre_commit run --all-files
```

### 3. 添加 NAS crontab

```bash
ssh TSX@192.168.31.108
crontab -e
```

加入以下两行：
```
# 推演系统文档漂移巡检（macro-scan v3.5.25，2026-06-29）
0 10 * * * NTFY_TOPIC=***REMOVED*** python3 /vol2/1000/software/macro-scan/核心代码/check_doc_drift.py >> /vol2/1000/software/macro-scan/logs/doc_drift.log 2>&1
```

验证：
```bash
NTFY_TOPIC=***REMOVED*** python3 /vol2/1000/software/macro-scan/核心代码/check_doc_drift.py
```

---

## 日常使用

### 改代码的标准流程

```bash
# 1. 改代码
# 2. 如果改了 scheduler.py / ntfy_listener.py，先刷新对应文档
python 核心代码/gen_docs.py --target scheduler   # 刷新 INDEX.md 定时任务表
python 核心代码/gen_docs.py --target ntfy         # 刷新 INDEX.md ntfy指令表
python 核心代码/gen_docs.py --target manifest     # 刷新 FILE_MANIFEST.md 离线工具节
# 3. git add 代码 + 联动文档
# 4. git commit → hook 自动检查，漏了会报错告诉你缺哪个
# 5. 验证后 scp 推 NAS + git push GitHub
```

### 联动矩阵（改了左边必须同时 staged 右边）

见 `AGENTS.md` 维护铁律节。

### 收到 ntfy 漂移告警后

1. 确认哪些文件被直接改了 NAS
2. 回源码区 `S:\macro-scan-src\` 补齐 CHANGELOG + VERSION
3. 走正常 `git commit` → 推 NAS 流程

---

## 卸载

### 卸载 pre-commit hook

在源码区执行：
```bash
python -m pre_commit uninstall
```

或直接删除：
```bash
rm S:\macro-scan-src\.git\hooks\pre-commit
```

### 删除 NAS crontab 条目

```bash
ssh TSX@192.168.31.108 "crontab -l"   # 先确认当前内容
ssh TSX@192.168.31.108
crontab -e
# 删除含 check_doc_drift.py 的两行（注释行 + 命令行）
```

验证已删除：
```bash
ssh TSX@192.168.31.108 "crontab -l | grep doc_drift"
# 无输出则已删除
```

### 删除 NAS 上的遗留软链接（如果存在）

```bash
ssh TSX@192.168.31.108 "ls -la /vol2/1000/software/macro-scan/核心代码/TuiYan_CHANGELOG.md"
# 如果是软链接（lrwxrwxrwx）则删除：
ssh TSX@192.168.31.108 "rm /vol2/1000/software/macro-scan/核心代码/TuiYan_CHANGELOG.md"
```

### 彻底移除源码区（可选）

```bash
rm -rf S:\macro-scan-src\
```

### 移除代码文件（保留运行区不变）

如果只想删掉这套机制的三个脚本，不动其他代码：

```bash
cd S:\macro-scan-src
git rm 核心代码/check_doc_sync.py 核心代码/check_doc_drift.py 核心代码/gen_docs.py .pre-commit-config.yaml
git commit -m "chore: 移除文档同步保障机制"
# 然后推 NAS
ssh TSX@192.168.31.108 "rm /vol2/1000/software/macro-scan/核心代码/check_doc_sync.py /vol2/1000/software/macro-scan/核心代码/check_doc_drift.py /vol2/1000/software/macro-scan/核心代码/gen_docs.py"
```

---

## 相关文档

- `AGENTS.md` — 联动矩阵完整规则
- `docs/operations/20260629-macro-scan-nas-crontab-doc-drift.md` — NAS crontab 操作日志
- `核心代码/check_doc_sync.py` — pre-commit 检查逻辑
- `核心代码/check_doc_drift.py` — 漂移巡检逻辑
- `核心代码/gen_docs.py` — 文档自动生成工具
