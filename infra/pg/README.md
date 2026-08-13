# infra/pg — worldsim-pg 基础设施脚本权威副本

> 创建：2026-08-13 22:4x（P2-2 收口：worldsim-pg 目录本身无 git，脚本改动无审计）

## 本目录内容（权威副本）

| 文件 | 作用 | 执行位置 |
|------|------|----------|
| `deploy-pg.sh` | worldsim-pg 容器部署/重建（幂等；数据卷挂载、角色、pg_hba ACL、网络互联） | `worldsim-pg/deploy-pg.sh`（NAS 本机执行） |
| `backup-pg.sh` | PG 每日逻辑备份（custom format）+ 保留 14 天；crontab 每日 04:00 调用 | `worldsim-pg/backup-pg.sh`（NAS 本机执行） |

## 同步纪律（权威 = 本目录，执行 = worldsim-pg/）

```
改 infra/pg/*.sh（git 树，有审计）──cp──▶ /vol2/1000/software/worldsim-pg/*.sh（执行位置）
```

1. **修改只在本目录做**（改完 git commit + push 留审计）
2. 改完**必须 cp 到执行位置**才能生效：
   ```bash
   cp infra/pg/deploy-pg.sh /vol2/1000/software/worldsim-pg/
   cp infra/pg/backup-pg.sh /vol2/1000/software/worldsim-pg/
   ```
3. 同步后 `md5sum` 两处应一致（部署/备份前可自检）
4. **禁止直接改 worldsim-pg/ 里的副本**（改了就是无审计漂移）

## 密钥文件（不入 git）

`connection.env`（WORLDSIM_APP_PW / WORLDSIM_RO_PW / DSN）与 `.env`（POSTGRES_*，docker 初始化用）**含密码，只存在于执行位置** `/vol2/1000/software/worldsim-pg/`，禁止拷贝进本目录或任何 git 树。

## 相关文档

- 部署/备份行为说明：`docs/decisions/worldsim-rename-check.md`（改名执行记录）
- 备份修复记录（P0-1/P0-2/P1×3）：`docs/decisions/backup-pg-fix-20260813.md`
