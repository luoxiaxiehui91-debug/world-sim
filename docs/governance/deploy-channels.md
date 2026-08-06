# 部署通道决策表 — world-sim 四容器唯一部署通道

> 文档类别：意图（INTENT）· 规则类（本文件为规则本身；落地校验靠方向 C 巡检）
> 状态：已实施（2026-08-06）
> 依据：四方向治理论证（docs/governance/四方向治理论证.md）· 方向 D「部署通道收敛」P0
> 实施实录：S:\docs\questions\world-deduction\20260806-world-deduction-four-direction-governance.md（方向 D）
> 联动：方向 A 仲裁表（漂移 = 未走唯一通道 → 判违规回滚，取代逐案仲裁）；方向 C 验证命令绑定 channel 来源

---

## 1. 四容器单通道决策表

| 子系统 | 容器 | 唯一通道 | 授权 | 部署前验证 | 部署后验证 |
|--------|------|----------|------|------------|------------|
| 天枢 | macro-scan | SSH 直改运行区 py（热挂载即生效）；scheduler.py 等长驻进程改动 → `docker compose restart` | 开发者 + 变更记录；rsync 整目录仅 lead | `compileall` + import smoke | `DATA_DIR==/workspace/data` 断言 |
| 天璇 | macro-sim | deploy.sh 仓库直构（运行区归档） | lead | 仓库 sha256 基线 + 构建成功 | 容器 image ID == 构建 ID + health |
| 天玑 | macro-ji（tianji） | 仓库 `docker build -t macro-tianji:latest` → `docker compose up -d --build` | lead | 构建成功 | 容器运行 + compose healthcheck 通过 |
| 开阳 | kaiyang（nginx） | scp dist → `chmod -R a+rX` → `docker restart kaiyang`（只覆盖不清理） | lead | 本地 build（禁 SMB 构建） | HTTP 200 + dist/index.html 实际引用 bundle 存在 |

---

## 2. 每通道细则

### 2.1 天枢（macro-scan）— SSH 直改热挂载

- **通道**：运行区 `/vol2/1000/software/macro-scan/核心代码/`（容器内 `/app` 热挂载，改 py 即生效）。单文件改动走 SSH 直改；scheduler.py 等长驻进程改动后必须 `docker compose restart` 才生效。
- **授权**：开发者 + 变更记录（记入 CHANGELOG/operations）；批量/整目录同步走 rsync，仅 lead 授权。
- **部署前验证**：`python3 -m compileall <改动的 py>` + import smoke（`docker exec macro-scan python3 -c "import <module>"`）。
- **部署后验证**：断言 `DATA_DIR == /workspace/data`（防 `__file__` 推非持久路径，案例 4 已修）；scheduler 改动后确认 trigger 按预期写入。
- **实例**：案例 2 根因（scheduler.py L48 `dom=1` 笔误）即经此通道修复闭环（commit 6ba35ab）——改 scheduler.py → restart → 复验 trigger 次日写入。

### 2.2 天璇（macro-sim）— deploy.sh 仓库直构（收敛目标，见第 4 节）

- **通道**：`bash deploy.sh macro-sim`（当前实现 = rsync 仓库 → 宿主运行区 → 运行区 `docker build -t macro-sim:latest .` → `docker compose up -d --force-recreate`，deploy.sh L34-42；rsync 无 `--delete`，commit 18d3962 实修）。
- **授权**：仅 lead 执行 deploy.sh。
- **部署前验证**：仓库 sha256 基线（改动文件与运行区/上一镜像 diff 一致）+ 构建成功。
- **部署后验证**：容器 image ID == 本次构建 ID + health（`docker inspect macro-sim --format '{{.Image}}'` 对比 `docker images -q macro-sim:latest`）。

### 2.3 天玑（macro-ji / tianji）— 仓库直构 compose up

- **通道**：在仓库 `macro-ji/` 目录 `docker build -t macro-tianji:latest .`（Dockerfile COPY 模式，镜像内代码即部署态）→ `docker compose up -d --build`。
- **授权**：仅 lead。
- **部署前验证**：构建成功（compose 已含 build context）。
- **部署后验证**：容器运行 + compose healthcheck 通过（`import tianji_verifier, tianji_db, weight_matrix`）。
- **注**：天玑无 VERSION 文件，镜像标签 `macro-tianji:latest` 即版本锚点；版本追溯以构建 commit 为准。

### 2.4 开阳（kaiyang / nginx）— scp dist + chmod + restart

- **通道**：本地构建 dist → scp 到 `/vol2/1000/software/kaiyang/dist/` → `chmod -R a+rX`（nginx uid 101 读不了 640）→ `docker restart kaiyang`。**只覆盖不清理**：清旧 bundle 动态取自 dist/index.html 实际引用，禁按文件名猜测清理。
- **授权**：仅 lead。
- **部署前验证**：本地 build 成功（禁 SMB 构建；NAS 侧一切操作走 SSH）。
- **部署后验证**：`curl -s -o /dev/null -w '%{http_code}' http://<host>:8080` == 200 + dist/index.html 引用的每个 bundle 文件存在（`docker exec kaiyang ls` 校验）。

---

## 3. 通用红线（所有容器一致）

1. **禁 mv 原目录**：目录挂载断链前车之鉴；部署产物一律原地覆盖，或部署后 `docker restart` 生效。
2. **NAS 仅 SSH + docker exec**：SMB 挂载读/写均不可信（案例 8），永不参与部署或仲裁。
3. **rsync 整目录仅 lead 授权**：非 lead 的改动走单文件通道（天枢 SSH 直改 / 其余提 PR 由 lead 部署）。
4. **不符即回滚**：部署后验证任一失败 → 立即回滚上一版本镜像/产物（保留 7 天），并记漂移事件走方向 A 仲裁。

---

## 4. 天璇双通道收敛（现状 + 待用户选型）

- **现状（08-06 实测）**：当前实际走**中转模式**——deploy.sh deploy_sim 把仓库 `macro-sim/` rsync 到宿主运行区 `/vol2/1000/software/macro-sim/`，再在运行区 docker build + compose up（deploy.sh L34-42；rsync 无 `--delete`，commit 18d3962 实修）。即「仓库 → 中转运行区 → 构建」双拷贝链路。
- **建议收敛方向（二选一，待用户选型）**：
  - **方案 A（推荐）仓库直构，运行区归档**：以仓库为唯一真源，构建/部署全部从仓库出发；宿主运行区降为只读归档，彻底消灭「仓库 vs 运行区」双源漂移面（与方向 A 仲裁表第 4 行「repo/容器赢，宿主运行区为僵尸副本」一致）。
  - **方案 B 维持中转统一标签**：保留 rsync 中转链路，但统一镜像标签 + 构建脚本唯一化；代价是双份拷贝仍存在漂移面，需依赖 C 巡检持续校验两侧一致。
- **状态**：⏳ **待用户选型**（本文件不选型、不部署、不重启）。

---

## 5. 变更记录

| 日期 | 变更内容 | 原因 |
|------|----------|------|
| 2026-08-06 | 初版：四容器单通道决策表 + 每通道细则 + 通用红线 + 天璇收敛现状标注 | 方向 D P0 落地（四方向治理论证 · 部署通道收敛） |
