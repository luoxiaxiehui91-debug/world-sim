# R4h E 项补做：A2=0.80+A3=0.80 容器复现验证 + 分叉根因锁定（data-r4h3，2026-08-10）

> 触发：team-lead E 项补做——容器内临时 A2=0.80+A3=0.80 跑 5-seed，核对 arch 声称"完整复现方案预期（p̂ 0.5729 / CI 0.4877 / credit 回池 / EASE 18 / M6 12 / sil 2/5 超 / reverse 0.529）"；并定位 A3 分叉（SHORT vs INCREASE_RISK）是环境差异还是代码版本差异。
> 结论先行：**arch 声称的"容器复现 0.5729"是假复现**——其 verify 脚本将 config 置于 /tmp，导致 A3 soul 加载路径解析到不存在的 /souls，A3 soul 缺失（空 {}）回退旧决策逻辑。**容器真实部署（/app/config/agents.yaml，soul 正常加载）下，A2=0.80+A3=0.80 实测 p̂=0.4626，credit 未回池**；定稿 A2=0.76+A3=0.75 实测 p̂=0.4894（Part 4 结论正确）。

---

## 1. E 项执行记录

### 1.1 操作（容器 NAS docker macro-sim）
1. 备份：`/tmp/agents_v2033_backup.yaml`（md5 5048c4fd，A2=0.76/A3=0.75 定稿）
2. sed 临时改 `/app/config/agents.yaml`：L40 0.76→0.80、L58 0.75→0.80（md5 baec47df→归一化 17bba346）
3. 生成 `probe_a80.py`（probe_v2033.py 变体，OUT/PROBE_PREFIX 改 a80）跑 5-seed
4. 上传 arch 复现脚本 `verify_full_a80.py` 并跑（它自建 `/tmp/cfg_a80a80.yaml`）
5. 上传 arch 工件 calib_probe_seed*_v2032.json，容器内同函数重算
6. 多组隔离实验（monkeypatch / random.seed / config 路径）
7. **恢复 config 到定稿**：`cp /tmp/agents_v2033_backup.yaml /app/config/agents.yaml`（md5 5048c4fd 确认）

### 1.2 关键实测矩阵（全部容器内、同一 run_probe 引擎、CACHE 14）
| 组 | config 路径 | A2/A3 实际 | A3 soul | p_hat | CI | pool | sil 逐 seed | EASE | M6 T_wrong |
|---|---|---|---|---|---|---|---|---|---|
| arch 工件重算 | /tmp/arch_seed*.json（本地 rpa 产物） | 0.80/0.80 | ? | 0.5729 | 0.4877 | 3变量回池 | 0.469/0.51/0.531/0.49/0.49 | 18 | 12 |
| verify_full_a80.py | /tmp/cfg_a80a80.yaml | 0.80/0.80 | **空 {}（/souls 不存在）** | **0.5729** | 0.4877 | 3变量回池 | 0.469/0.51/0.531/0.49/0.49 | 18 | 12 |
| path_iso B（同逻辑读 /tmp） | /tmp/cfg_a80a80.yaml | 0.80/0.80 | 空 {} | 0.5729 | 0.4877 | 3变量回池 | 0.469/0.51/0.531/0.49/0.49 | — | — |
| path_iso A（同逻辑读 /app） | /app/config/agents.yaml（=cfg_a80a80 内容，md5 相同） | 0.80/0.80 | **完整 faction** | **0.4626** | 0.3808 | 2变量出池 | 0.469/0.531/0.551/0.429/0.51 | — | — |
| probe_v2033.py（sed 后 /app） | /app/config/agents.yaml | 0.80/0.80 | 完整 faction | 0.4626 | 0.3808 | 2变量出池 | 0.469/0.531/0.551/0.429/0.51 | 15 | 20 |
| 定稿 probe_v2033.py | /app/config/agents.yaml | 0.76/0.75 | 完整 faction | 0.4894 | 0.4063 | 2变量出池 | 0.531/0.551/0.633/0.49/0.51 | 16 | 13 |

**决定性证据**：`/app/config/agents.yaml` 与 `/tmp/cfg_a80a80.yaml` **md5 完全相同（17bba346）**，但读 /app 得 0.4626、读 /tmp 得 0.5729。差异仅在 config 所在目录 → load_agents 的 soul 加载路径 `os.path.dirname(config_path)/../souls`：
- /app/config → /app/souls/A3_hedge_fund.yaml → **soul 完整加载**（internal_factions 含 risk_off/contrarian 等）
- /tmp/cfg → /souls（不存在）→ **A3 soul={} 空，回退旧 if-else 决策**（无 45% 超卖反弹派系）

### 1.3 分叉定位结论（team-lead 追问的"环境差异 vs 代码版本差异"）
- **不是代码版本差异**：agents.py/financial.py 等 hash 无异常（容器内 md5 稳定）
- **不是纯随机分叉**：隔离实验证明 monkeypatch、random.seed 前置均不影响结果（iso3/iso4 均 0.5729 复现）
- **是 config 路径导致的 soul 加载差异**：arch verify 脚本把 config 放 /tmp → A3 soul 丢失 → 决策链回退 → "复现"了 arch 本地 rpa（同样 soul 缺失环境）的数值
- A3 动作分叉（arch=SHORT_MARKET vs 容器=INCREASE_RISK）根源：soul 中 contrarian 派系（超卖反弹 INCREASE_RISK，旧 OVERSOLD_BOUNCE_PROB 结构化）缺失后行为不同

---

## 2. E 项六项核对（容器真实部署口径）
| 项 | arch 声称 | 容器真实（/app config） | 判定 |
|---|---|---|---|
| p̂ | 0.5729 | **0.4626**（0.80）/ **0.4894**（0.76 定稿） | ❌ 未复现 |
| CI | 0.4877 | **0.3808** / **0.4063** | ❌ |
| credit 回池 | 3 变量 | **2 变量出池**（两配置均） | ❌ |
| EASE correct | 18 | **15**（0.80）/ **16**（0.76） | ❌（EASE wrong 0 一致 ✅） |
| M6 T_wrong | 12 | **20**（0.80）/ **13**（0.76） | ❌ |
| sil 超线 | 2/5 | **4/5**（0.80）/ **4/5**（0.76） | ❌ |

**结论：arch 声称的"完整复现方案预期"仅在 A3 soul 缺失环境成立（/tmp config 或本地 rpa 同缺陷），不代表容器真实部署行为。容器真实行为下，即使 A2=0.80+A3=0.80，credit 也不回池、p̂ 不过 partial。**

---

## 3. 对 Part 4 结论的最终确认
- **Part 4 定稿实测（A2=0.76/A3=0.75）正确**：p̂ 0.4894 / CI 0.4063 / 2 变量出池 / EASE 16/0/0 / M6 13 / sil 4/5 超 0.531 / reverse 0.636 —— probe_v2033 与 verify076（读 /app）两脚本一致，可复现
- **① 机制层成立（两环境一致）**：ease_ok 方向闸 EASE wrong 8→0、cap17 vix peak 51.3、M4 flip 0
- **验收数值层不成立**：credit 回池 / p̂ 0.5729 依赖 A3 soul 缺失环境，容器真实环境不可复现

---

## 4. evidence / 留痕
- 容器内：`/tmp/r4h_v2033_all.json`（定稿 0.76）、`/tmp/r4h_v2033_a80_all.json`（0.80 探针）、`/tmp/probe_a80a80_seed*.json`（verify 假复现）、`/tmp/cfg_a80a80.yaml`、`/tmp/agents_v2033_backup.yaml`、`/tmp/arch_seed*.json`、`/tmp/path_iso*.json`、iso2/iso3/iso4 系列
- 容器内 probe 逻辑隔离脚本：verify_full_a80.py、path_iso.py、r4h_iso2/3/4.py
- 本地：`C:\tmp\r4h_data2\R4h_Part4_前后对比.md`、`r4h_v2033_all.json`、`probe_v2033.py`、本文件
- 容器当前状态：config md5 5048c4fd（定稿 A2=0.76/A3=0.75）、CACHE 14、VERSION v2.0.40 ✅ 已恢复到 v2033 定稿
