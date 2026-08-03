# world-sim NAS 部署执行提示词 v3.8.6

本文档指导将 world-sim monorepo（macro-scan v3.8.6 / macro-sim latest / kaiyang v1.7.2）部署到 NAS (192.168.31.108)。  
执行顺序严格为：**本地 kaiyang 构建 → NAS 预检 → macro-scan 重建 → macro-sim 重建 → kaiyang 分发**。

> **阅读说明**：每个步骤末尾有"预期"描述，不符合预期时停止并向用户报告，不继续执行。

---

## 一、本地准备（Windows Git Bash，连 NAS 前完成）

### 1.1 构建 kaiyang

```bash
cd /c/Users/I327394/Desktop/S/world-sim/kaiyang
ls node_modules > /dev/null 2>&1 || npm install
npm run build
```

**验证：**
```bash
ls dist/index.html
```
预期：文件存在，无报错。若 `tsc --noEmit` 输出类型错误，停止并报告错误全文。

---

## 二、NAS 预检

### 2.1 连通性确认

```bash
ssh TSX@192.168.31.108 'echo OK && docker --version'
```
预期：输出 `OK` + Docker 版本号。

### 2.2 读取 macro-scan docker-compose.yml

```bash
ssh TSX@192.168.31.108 'cat /vol2/1000/software/macro-scan/docker-compose.yml'
```
记录以下字段当前值，供后续步骤判断：
- `image:` 字段（期望修改为 `macro-scan:v3.8.6`）
- `ports:` 段是否含 `8900:8900`
- `volumes:` 段是否含 `./config:/workspace/config`

### 2.3 确认容器实际名称

```bash
ssh TSX@192.168.31.108 'docker ps --format "{{.Names}}" | grep macro'
```
记录实际名称。后续命令假定 `macro-scan-macro-scan-1`，若不同则全局替换。

### 2.4 macro-sim 前置条件检查

```bash
ssh TSX@192.168.31.108 'ls -la /vol2/1000/software/macro-sim/.env'
ssh TSX@192.168.31.108 'ls -la /vol2/1000/software/macro-sim/sim_log.db'
ssh TSX@192.168.31.108 'ls -ld /vol2/1000/software/macro-scan/data'
ssh TSX@192.168.31.108 'ls -ld /vol2/1000/software/macro-sim/output'
```

判断规则：
- `.env` 不存在 → **停止**，通知用户手动创建 `.env` 并填写 `SILICONFLOW_API_KEY` 和 `MINIMAX_API_KEY`
- `sim_log.db` 是目录（`drwx`）→ 步骤 4.0 必须修复
- `macro-scan/data` 不存在 → macro-sim 部署须等 macro-scan 先完整运行后才能继续
- `output` 不存在 → 步骤 4.0 创建

---

## 三、macro-scan 重建

### 3.1 git pull

```bash
ssh TSX@192.168.31.108 "cd /vol2/1000/software/world-sim && git pull origin main"
```
预期：`Already up to date` 或含 `macro-scan/entrypoint.sh` 的更新列表。若报 merge conflict，停止并报告。

### 3.2 修改 docker-compose.yml

**3.2a 添加 8900 端口（按步骤 2.2 结果判断，已有则跳过）**

```bash
ssh TSX@192.168.31.108 "grep '8900' /vol2/1000/software/macro-scan/docker-compose.yml"
```
若无输出：
```bash
ssh TSX@192.168.31.108 "sed -i \"/8899:8899/a\\      - '8900:8900'\" /vol2/1000/software/macro-scan/docker-compose.yml"
```
验证：
```bash
ssh TSX@192.168.31.108 "grep -A8 'ports:' /vol2/1000/software/macro-scan/docker-compose.yml"
```
预期：同时含 `8899:8899` 和 `8900:8900`。

**3.2b 添加 config/ volume 挂载（按步骤 2.2 结果判断，已有则跳过）**

```bash
ssh TSX@192.168.31.108 "grep './config' /vol2/1000/software/macro-scan/docker-compose.yml"
```
若无输出：
```bash
ssh TSX@192.168.31.108 "sed -i '/知识库.*workspace/a\      - .\/config:\/workspace\/config' /vol2/1000/software/macro-scan/docker-compose.yml"
```
验证：
```bash
ssh TSX@192.168.31.108 "grep 'config' /vol2/1000/software/macro-scan/docker-compose.yml"
```
预期：含 `./config:/workspace/config`。

**3.2c 更新 image 字段**

```bash
ssh TSX@192.168.31.108 "grep 'image:' /vol2/1000/software/macro-scan/docker-compose.yml"
```
若不是 `macro-scan:v3.8.6`：
```bash
ssh TSX@192.168.31.108 "sed -i 's|image: macro-scan:.*|image: macro-scan:v3.8.6|' /vol2/1000/software/macro-scan/docker-compose.yml"
```
验证：
```bash
ssh TSX@192.168.31.108 "grep 'image:' /vol2/1000/software/macro-scan/docker-compose.yml"
```
预期：`image: macro-scan:v3.8.6`。

**3.2d 最终确认**
```bash
ssh TSX@192.168.31.108 'cat /vol2/1000/software/macro-scan/docker-compose.yml'
```
三条均满足才继续：含 `8900:8900`、含 `./config:/workspace/config`、`image: macro-scan:v3.8.6`。

### 3.3 重建镜像

```bash
ssh TSX@192.168.31.108 "cd /vol2/1000/software/macro-scan && docker build -t macro-scan:v3.8.6 ."
```
预期：最后一行含 `Successfully built` 或 `naming to ... macro-scan:v3.8.6`。  
若失败：
```bash
ssh TSX@192.168.31.108 "cd /vol2/1000/software/macro-scan && docker build -t macro-scan:v3.8.6 . 2>&1 | tail -80"
```
输出最后 80 行并停止。

### 3.4 部署（force-recreate）

```bash
ssh TSX@192.168.31.108 "cd /vol2/1000/software/macro-scan && docker compose up -d --force-recreate"
```
预期：含 `Started` 或 `Recreated`，无 `Error`。

### 3.5 验证 macro-scan

```bash
# 容器存活
ssh TSX@192.168.31.108 "docker ps | grep macro-scan"
```
预期：STATUS 含 `Up`，不含 `Restarting`。若含 `Restarting`，查日志并停止：
```bash
ssh TSX@192.168.31.108 "docker logs macro-scan-macro-scan-1 2>&1 | tail -50"
```

```bash
# 8900 端口映射
ssh TSX@192.168.31.108 "docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep macro-scan"
```
预期：含 `0.0.0.0:8900->8900/tcp`。

```bash
# control_server 进程
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 ps aux | grep control_server"
```
预期：含 `python3` + `control_server.py`。

```bash
# control.log 无致命错误
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 tail -30 /var/log/macro-scan/control.log 2>/dev/null"
```
预期：无 `ImportError`、`Address already in use`、`FileNotFoundError`。

```bash
# WORKDIR 容器内值
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 python3 -c 'import sys; sys.path.insert(0,\"/app\"); from control_server import WORKDIR; print(WORKDIR)'"
```
预期：输出 `/app`。若含 `/workspace`，重启容器后重试：
```bash
ssh TSX@192.168.31.108 "docker restart macro-scan-macro-scan-1"
```

```bash
# control API 健康检查
curl -s http://192.168.31.108:8900/api/v1/control/health
```
预期：HTTP 200 + JSON。若 404，改用进程检查替代（见遗留项 D）。

```bash
# startup_checks
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 python3 核心代码/startup_checks.py"
```
预期：输出含 ✅，无 RuntimeError。

```bash
# scheduler_state.json（等 65s）
sleep 65
curl -s http://192.168.31.108:8900/api/v1/control/fetchers
```
预期：返回非空 JSON 数组。若仍空，再等 30s 重试一次；若超时仍空，记录并继续（不阻断）。

---

## 四、macro-sim 重建

### 4.0 修复前置条件（按步骤 2.4 结果执行）

**若 sim_log.db 是目录或不存在：**
```bash
ssh TSX@192.168.31.108 "rm -rf /vol2/1000/software/macro-sim/sim_log.db && touch /vol2/1000/software/macro-sim/sim_log.db"
```
验证：
```bash
ssh TSX@192.168.31.108 "ls -la /vol2/1000/software/macro-sim/sim_log.db"
```
预期：`-rw`（文件），不是 `drwx`（目录）。

**若 output 不存在：**
```bash
ssh TSX@192.168.31.108 "mkdir -p /vol2/1000/software/macro-sim/output"
```

### 4.1 同步代码到 NAS（本地 Git Bash）

```bash
cd /c/Users/I327394/Desktop/S/world-sim
bash deploy.sh macro-sim
```
预期：rsync 完成，无报错，`.env` 不在同步列表中（`--exclude='.env'` 已加）。

### 4.2 确认 macro-sim docker-compose.yml

```bash
ssh TSX@192.168.31.108 'cat /vol2/1000/software/macro-sim/docker-compose.yml'
```
确认三点：
- `sim_log.db` 为单文件 bind mount（`./sim_log.db:/app/sim_log.db`）
- 含 `/vol2/1000/software/macro-scan/data:/app/macro_data:rw`
- environment 段含 `SILICONFLOW_API_KEY` 和 `MINIMAX_API_KEY`（从 `.env` 注入）

### 4.3 重建并启动

```bash
ssh TSX@192.168.31.108 "cd /vol2/1000/software/macro-sim && docker build -t macro-sim:latest . && docker compose up -d --force-recreate"
```
预期：build 成功 + 容器 Recreated/Started，无 Error。

### 4.4 验证 macro-sim

```bash
# 容器存活
ssh TSX@192.168.31.108 "docker ps | grep macro-sim"
```
预期：STATUS 含 `Up`，不含 `Restarting`。

```bash
# 启动日志
ssh TSX@192.168.31.108 "docker logs macro-sim --tail 30 2>&1"
```
预期：含守护模式启动消息，无 Python traceback，无 `FileNotFoundError`。

```bash
# sim_log.db 挂载类型
ssh TSX@192.168.31.108 "docker exec macro-sim ls -la /app/sim_log.db"
```
预期：`-rw`（文件）。若为 `drwx`（目录），停止并报告，按步骤 4.0 修复后重新 force-recreate。

```bash
# API key 注入
ssh TSX@192.168.31.108 "docker exec macro-sim env | grep -E 'SILICONFLOW|MINIMAX'"
```
预期：两行均有非空值。若任一为空，停止并报告，需用户检查 `.env` 文件。

```bash
# D1 修复验证
ssh TSX@192.168.31.108 "docker exec macro-sim python3 -c 'from core.simulation import gm_resolve_rules; print(\"D1 OK\")'"
```
预期：输出 `D1 OK`。

```bash
# D4 修复验证
ssh TSX@192.168.31.108 "docker exec macro-sim python3 -c 'from core.world_state import apply_natural_decay; print(\"D4 OK\")'"
```
预期：输出 `D4 OK`。

```bash
# load_monthly_history 扩展维度
ssh TSX@192.168.31.108 "docker exec macro-sim python3 -c \"
from core.world_state import load_monthly_history
rows = load_monthly_history()
if rows:
    extra = [k for k in rows[0] if k not in ('date','grv','grv_energy','grv_military','grv_trade','us_china_grv','t10y2y','credit_spread','dff')]
    print('扩展维度:', extra)
else:
    print('WARNING: 无历史数据行，grv_history.jsonl 可能为空')
\""
```
预期：输出扩展维度列表，含 `climate_risk`、`social_stress` 等8个字段。

---

## 五、kaiyang 分发

### 5.1 确认目标目录

```bash
ssh TSX@192.168.31.108 "mkdir -p /vol2/1000/software/kaiyang/dist"
```

### 5.2 scp dist/

```bash
scp -r /c/Users/I327394/Desktop/S/world-sim/kaiyang/dist/ TSX@192.168.31.108:/vol2/1000/software/kaiyang/dist/
```
注意：`dist/` 末尾保留斜杠，拷贝内容而非目录本身。

### 5.3 确认 nginx 容器名并重启

```bash
ssh TSX@192.168.31.108 "docker ps --filter name=kaiyang --format '{{.Names}}'"
```
若为 `kaiyang-nginx-1`：
```bash
ssh TSX@192.168.31.108 "docker restart kaiyang-nginx-1"
```

### 5.4 验证 kaiyang

```bash
curl -s -o /dev/null -w "%{http_code}" http://192.168.31.108:8080/
```
预期：`200`。

---

## 六、遗留确认项（不阻断主流程，部署后处理）

**A. FRED API key 是否已入 git history**
```bash
ssh TSX@192.168.31.108 "git -C /vol2/1000/software/world-sim log --all -S 'FRED_API_KEY=a3f1dc8' --oneline | head"
```
若有输出：报告用户，建议在 FRED 官网申请新 key 并更新 NAS docker-compose.yml 中 `FRED_API_KEY`。

**B. kaiyang package.json version 字段**
```bash
grep '"version"' /c/Users/I327394/Desktop/S/world-sim/kaiyang/package.json
```
若仍为 `1.7.1`（而非 `1.7.2`），下次 build 前更新此字段。

**C. CONTROL_TOKEN 安全性**  
当前 control_server 无鉴权（内网可用）。若 NAS 暴露公网，执行：
```bash
TOKEN=$(openssl rand -hex 16)
ssh TSX@192.168.31.108 "sed -i '/environment:/a\      - CONTROL_TOKEN=${TOKEN}' /vol2/1000/software/macro-scan/docker-compose.yml"
echo "CONTROL_TOKEN=${TOKEN} — 保存此值，同步到 kaiyang localStorage"
ssh TSX@192.168.31.108 "cd /vol2/1000/software/macro-scan && docker compose up -d --force-recreate"
```

**D. /health 端点 404 的替代验证**  
若步骤 3.5 中 health 返回 404，改用：
```bash
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 ps aux | grep control_server | grep -v grep"
```
预期：含 `python3` + `control_server.py`。进程存在即为正常。

**E. news_export.json schema_version 字段名确认**
```bash
ssh TSX@192.168.31.108 "grep -n 'schema_version' /vol2/1000/software/macro-scan/核心代码/news_exporter.py 2>/dev/null | head -5"
```
预期：含 `_schema_version`（带下划线）。若含无下划线的 `schema_version`，向用户报告：天璇加载 news_export.json 时 schema 验证会失败。

**F. R11/R12 开启条件**
```bash
ssh TSX@192.168.31.108 "docker exec macro-scan-macro-scan-1 python3 -c \"
import json, os
p = '/workspace/data/grv_latest.json'
if os.path.exists(p):
    d = json.load(open(p))
    print('climate_risk:', d.get('climate_risk'))
    print('updated:', d.get('updated'))
else:
    print('grv_latest.json 不存在')
\""
```
若 climate_risk 有非零值且积累超过3周，可考虑开启 R11/R12（ROADMAP.md 中的时间门控任务）。

---

## 停止条件

遇到以下任一情况，立即停止全部操作并向用户报告：

- SSH 连接失败（步骤 2.1）
- git pull 报 merge conflict（步骤 3.1）
- docker build 失败（步骤 3.3 或 4.3）
- macro-sim `.env` 文件不存在（步骤 2.4）
- macro-sim API key 注入后为空（步骤 4.4）
- sim_log.db 修复后仍为目录（步骤 4.0 验证）
- macro-scan 容器持续 Restarting（步骤 3.5）
