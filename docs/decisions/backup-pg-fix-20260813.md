# backup-pg.sh 修复记录（P0-1 / P0-2 / P1-1~3 闭环）

> 日期：2026-08-13 22:2x（GMT+8）
> 依据：`worldsim-rename-check.md` 检查发现的 P0-1/P0-2/P1-1/P1-2/P1-3

## 修复内容

`/vol2/1000/software/worldsim/backup-pg.sh` 全文重写（旧版留档 `backup-pg.sh.broken-20260813`）：

| 问题 | 修复 |
|------|------|
| P0-1 line 8 `> ""` 重定向空名 → 备份 100% 失败 | `> "$OUT"` 正确重定向 |
| P0-2 硬编码失效密码 PGPASSWORD=ZvR0...（明文泄露面） | 删除；改用 `docker exec` 容器内 `worldsim_admin` 免密（deploy-pg.sh 同款），**脚本零密码** |
| P1-1 STAMP 硬编码 20260812-2048 + OUT 未拼时间戳 | `STAMP=$(date +%Y%m%d-%H%M)` + `OUT=.../worldsim-$STAMP.dump` |
| P1-2 `export PGPASSWORD_FILE=...` 非标准变量 | 删除（不再需要） |
| P1-3 `echo "backup done: ()"` 空变量 | `echo "backup done: $OUT ($(du -h "$OUT" | cut -f1))"` |

## 验证（容器内实测）

- `bash -n` 语法通过；手动执行 `bash backup-pg.sh` 成功 → `worldsim-20260813-2221.dump`（23M）
- `docker cp` 进容器 `pg_restore -l`：**TOC Entries 85 / Format CUSTOM / 19 个 TABLE DATA** / dbname=worldsim / 16.14 —— 完整可读
- 旧损坏 dump `worldsim-20260812-2049.dump`（2071B）已标记 `.broken` 保留审计
- 损坏 dump 验证姿势教训：`docker exec pg_restore -l /dev/stdin < file` 在**无 `-i`** 时 stdin 空（read 0），**有 `-i`** 时 magic 检测也不稳 → **一律 `docker cp` 进容器直读**最可靠

## 现状

- PG 每日 04:00 cron 备份已恢复可用（下次自然触发 08-14 04:00，届时 backup.log 应新增 `backup done:` 成功行）
- **worldsim 改名（worldsim → worldsim-pg）的 P0 阻断已解除**，可随时执行（见 rename-check.md 第四节的 7 步执行序）
- 遗留：备份脚本不在 git 树（P2-2，worldsim 目录无版本控制）——建议后续在 world-sim 仓库 `infra/pg/` 固化权威副本
