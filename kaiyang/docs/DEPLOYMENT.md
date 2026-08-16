# 开阳（Kaiyang）部署规范

> 文档类别：实录（RECORD）· 部署红线聚合（2026-08-11 首次成文，源自历次部署事故教训）
> 适用范围：kaiyang 前端（vite 构建产物）的构建 / 部署 / 清理

## 1. 构建

- **禁在 SMB 挂载路径跑 vite 构建**（`EPERM`）。只能二选一：
  1. 本地（Windows）`npm run build`（`tsc --noEmit && vite build`）
  2. SSH 到 NAS 在非 SMB 挂载路径构建
- 构建前 `npm test` 必须全绿（基线 311+，只增不减）。
- **⛔ 构建必须带 `VITE_CONTROL_API_TOKEN`**（v1.11.15 起，控制台开箱即用）：
  ```bash
  VITE_CONTROL_API_TOKEN=<运行区 compose 的 CONTROL_TOKEN> npm run build
  ```
  - 不带此参数 → 产物无内置 token → 控制台 401（除非用户在浏览器 localStorage 手填）。
  - **token 轮换（P0-A）时必须同步更新此构建参数**。
  - 注入值**不进 git**（构建参数传入，`getEnvToken()` 优先于 localStorage 读取）。

## 2. 部署（nginx 静态托管）

- 目标目录：`/vol2/1000/software/kaiyang/dist`（nginx → `/usr/share/nginx/html`）。
- 部署方式：`scp` **原地覆盖** `index.html` + `assets/`。
  - **禁 `mv` 换 inode**（2026-08-11 嵌套挂载事故教训：mv 后 nginx/宿主机 inode 不一致导致挂载断链）。
  - 只覆盖、不整目录重建；**`dist` 内不得出现 `data/` 子目录**（public/data 旧快照会与 /data 挂载冲突，已删）。
- 覆盖后必须 `chmod -R a+rX /vol2/1000/software/kaiyang/dist`。

## 3. dist/assets 清理（2026-08-11 首版规则）

vite 产物带内容 hash，历史构建会在 `dist/assets/` 累积。清理规则：

1. **保留最近 3 版 bundle（js+css）供回滚**；更旧的才允许删。
2. **删除前必须动态核对**：`grep -o 'assets/index-[^"]*' /vol2/1000/software/kaiyang/dist/index.html`，
   确认待删文件**不在引用列表**中。**禁硬编码 hash、禁全量 `rm`**。
3. 只删「最旧且未被引用」的 js/css；`index.html` 只引用活动 bundle，删除不影响运行。
4. 删后验证：`index.html` 200 + 活动 bundle js/css 200 + 18/18 feed 200（`/data/*.json`）。

## 4. 数据目录（只读挂载）

- 前端数据全部走 nginx `/data/`（NAS `macro-scan/data` 只读挂载），前端不写数据。
- feed 清单（18 个）见 `src/config/dataSources.ts`；新 feed 上线需同步注册 + `refreshMs`。

## 5. 版本管理

- `VERSION` + `CHANGELOG.md` 同步 bump（SemVer）；每条 CHANGELOG 绑定 commit hash。
- 部署动作不单独 commit；**清理动作记入当期 CHANGELOG 条目备注**。
