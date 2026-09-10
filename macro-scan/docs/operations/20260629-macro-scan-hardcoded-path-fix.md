# 操作日志：硬编码路径修复

**日期**：2026-06-29  
**执行者**：Claude Code  
**项目**：macro-scan  
**版本**：3.5.17 → 3.5.18  

---

## 背景

审查核心代码中的路径和配置，发现两处硬编码会在 NAS 部署时埋下隐患：
- 一处是 fallback 块里写死了本机 IP，不走环境变量
- 一处是 NTFY_TOPIC 默认值写了真实频道名（其他文件均用空字符串）

NAS docker-compose.yml 已注入正确 env，生产路径不受影响，但属于防御性问题需修复。

---

## 修改内容

### Fix 1 — `核心代码/fetch_climate_signals.py` 第31行

`optim_config` import 失败时的 fallback 改为读环境变量：

```python
# 改前
CRUCIX_REMOTE_URL = "http://192.168.31.108:3117/api/data"

# 改后
CRUCIX_REMOTE_URL = os.environ.get("CRUCIX_REMOTE_URL", "http://192.168.31.108:3117/api/data")
```

**原因**：except 块原来写死 IP，若换 NAS 地址或迁移环境，此 fallback 失效。现在与 `optim_config.py` 的配置方式保持一致，也和其他模块的 fallback 风格对齐。

### Fix 2 — `核心代码/update_kb_numbers.py` 第26行

NTFY_TOPIC 默认值改为空字符串：

```python
# 改前
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "$NTFY_TOPIC")

# 改后
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
```

**原因**：`daily_narrative.py` / `situation_detector.py` / `weekly_synthesis.py` 的同名变量默认值均为 `""`（无环境变量时静默跳过推送）。此处写死真实频道名会导致未配置环境变量时静默推送到生产频道，行为不一致。

---

## 验证方法（NAS 部署后）

```bash
# 确认 CRUCIX_REMOTE_URL 走环境变量
docker exec macro-scan-macro-scan-1 env | grep CRUCIX_REMOTE_URL

# 确认 NTFY_TOPIC 走环境变量
docker exec macro-scan-macro-scan-1 env | grep NTFY_TOPIC
```

两者均应显示 docker-compose.yml 中注入的值，说明 fallback 代码从未触发。
