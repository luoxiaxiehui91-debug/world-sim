# scripts/dev — 开发与运维脚本（作者环境专用）

本目录脚本面向**特定部署环境**（自建 NAS + 私有网络），开源使用者通常**不需要**它们。
保留是为了记录本项目的实际部署方式，可作为自建部署的参考。

| 脚本 | 用途 | 前置环境变量 |
|---|---|---|
| `deploy-to-nas.sh` | 把仓库源码 rsync 到 NAS 运行区并重启容器 | `NAS_HOST`（必填，`user@host`）、`NAS_DIR`（可选） |
| `deploy-scan-legacy.sh` | 天枢单项目部署（**旧版**，已被上者取代，保留参考） | `NAS_HOST`、`NAS_REPO_DIR`、`NAS_RUNTIME_DIR` |

## 通用基础设施脚本（不在此目录）

`infra/pg/` 下的 `backup-pg.sh` / `deploy-pg.sh` 是通用的 PostgreSQL 备份与部署脚本，
开源使用者自建数据库时同样适用，已参数化为：

- `WORLDSIM_PG_DIR` — PG 数据目录（默认 `/opt/worldsim-pg`）
- `DATA_DIR` — 天枢数据目录（默认 `/opt/macro-scan/data`）

## 用法示例

```bash
NAS_HOST=user@your-host ./scripts/dev/deploy-to-nas.sh
NAS_HOST=user@your-host NAS_DIR=/srv/macro-scan ./scripts/dev/deploy-to-nas.sh
```
