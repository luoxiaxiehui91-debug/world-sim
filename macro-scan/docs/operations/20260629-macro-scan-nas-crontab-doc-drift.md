# NAS crontab 新增：推演系统文档漂移巡检

**日期**：2026-06-29  
**操作者**：Claude Code  
**项目**：macro-scan  

---

## 操作内容

在 NAS 宿主机（TSX@192.168.31.108）crontab 新增一条定时任务：

```
# 推演系统文档漂移巡检
0 10 * * * NTFY_TOPIC=***REMOVED*** python3 /vol2/1000/software/macro-scan/核心代码/check_doc_drift.py >> /vol2/1000/software/macro-scan/logs/doc_drift.log 2>&1
```

## 原因

NAS Docker 不允许单文件 volume 挂载，`check_doc_drift.py` 在容器内无法访问 `TuiYan_CHANGELOG.md`（在项目根目录，未挂载进容器）。改由宿主机直接运行，路径天然可用。

## 脚本位置

- 脚本：`/vol2/1000/software/macro-scan/核心代码/check_doc_drift.py`
- 源码：`S:\macro-scan-src\核心代码\check_doc_drift.py`（在 git 里）
- 日志：`/vol2/1000/software/macro-scan/logs/doc_drift.log`

## 清理方式

如需删除，SSH 进 NAS 执行：

```bash
ssh TSX@192.168.31.108
crontab -e
# 删除含 check_doc_drift.py 的两行
```

## 验证

```bash
ssh TSX@192.168.31.108 "crontab -l | grep doc_drift"
```
