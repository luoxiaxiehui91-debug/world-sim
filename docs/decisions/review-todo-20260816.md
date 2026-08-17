# 复查遗留待办清单（2026-08-16 Recheck 残留 → 已处理/待办映射）

> 来源：`../reviews/code-review-recheck-20260816.md`（全量只读复查，对抗复核 6 条全过证伪）
> 结论定性：Critical/High 几乎全对症修好；残留 = Medium 尾巴 + LLM 配置平台化 3 条回归。
> 本清单为执行维度映射，销项方式同 `audit-todo-20260815.md`（commit 销项 + STATUS 待办节同步）。

## 1. 已处理（08-16 晚收尾批次）

| 项 | 处理 | 证据/commit |
|----|------|-------------|
| **死循环报告清理** | 源头 `docs/仿真报告/` 344 份 + 副本 `data/reports/` 302 份全部归档（备份 `macro-scan/backups/deadloop-reports-20260816-2215/`，343 份去重后），**保留现场样本 1 份** `2026-08-16_04-14_演化_L2_校准51.7.md`；`reports_index.json` 375 → 74 条（月度简报 28 / 宏观分析 28 / 演化仿真 9 / 假设推演 9） | 本批次 |
| **M08** Brier 窗口取反 | `macro-ji/tianji_verifier.py:273` `briers[-MIN_TRIGGER_N:]` → `briers[:MIN_TRIGGER_N]`（取最近 N 条；配合 :242 ORDER BY verified_at DESC 语义） | 天玑重建部署中 |
| **observability 宕机推绿** | `observability.py:322` alert 判定 `==0` → `<=0`（-1 = PG 连接/凭据异常也告警）；`:328` 拆两条提示（<0 不可读 / ==0 空表） | 已 rsync 部署运行区，次日 21:00 实测 |
| **kaiyang v1.11.28** | 报告中心全开/全关 + 近期过滤 [全部/近7天/近30天] + 今天高亮 | `19ba7c0c` |

## 2. 待办 P1（正确性 / 配置一致性，下一轮优先）

| ID | 位置 | 问题 | 建议修法 |
|----|------|------|---------|
| ✅ **LLM①③②** | `llm_usage.py` / `llm_client.py` | 静态默认失效 + 天璇缓存不失效 + 条件性错配 | `0a2a6ecb`：resolve 回落静态默认 / 60s TTL / 同源消除错配 |
| ✅ **M31** | `macro-sim/run.py:573/582`（geo 侧 :639/646 同） | archival uuid4 主键 + `ON CONFLICT(id)` 去重恒 no-op → 重跑同 scenario 插重复行 | `0a2a6ecb`：确定性哈希主键（scenario+路径+类型） |
| **LLM③** | `macro-sim/core/llm_client.py:98-110` `_usage_cache` + `:33-49` 导入期常量 + `:113-120` client 缓存 | 三处均无 TTL/mtime/信号失效，改配置须**重启天璇容器**；与天枢每次开文件热更行为不一致 | 配置缓存加 TTL（如 60s）或 mtime 比对，client 惰性重建 |
| **LLM①** | `llm_usage.py:196-200` `resolve()` | 静态默认平台/模型仅供前端展示，调用方 resolve 返 None 时回落 env——全新部署静默回落 env，静态值形同虚设 | resolve() 返 None 时回落静态默认 |
| **LLM②** | `hybrid_llm.py:204` 附近 | 仅当 `OPENAI_COMPAT_URL` 设了而 `OPENAI_COMPAT_MODEL` 未设的半配置态才 model=gpt-4o + base_url=MiMo 错配（条件性，非必然） | 配置校验：URL 与 MODEL 必须成对出现 |

## 3. 待办 P2（失败可感知性 / 结构性 / 文档）

| ID | 位置 | 问题 | 建议修法 |
|----|------|------|---------|
| ✅ **M11** | `weight_matrix.py:187-188` / `:394-395` | 两处 `except:pass` 吞掉权重/拒绝日志写失败，无 log 无告警 | `0a2a6ecb`：fail-loud 打印 |
| ✅ **M26** | `pg_read.py:130-141` | `exec_read()` 连接失败/查询失败/真空结果都返回 `[]`，下游无法区分 | `0a2a6ecb`：新增 `exec_read_checked` 返回 (rows, ok) |
| ✅ **L03** | `tianji_verifier.py:406` | 锐度标签印 "(>30%或<70%)" 恒 100%，实算 `p<0.3 or p>0.7` | `0a2a6ecb`：标签修正 |
| **tianji_db 分叉** | `macro-ji/tianji_db.py`（纯 PG） vs `macro-scan/核心代码/tianji_db.py`（SQLite 主写+PG 旁路过渡态） | 同名不同实现，改一份不传播 | 头部已加维护警示（`0a2a6ecb`）；物理合并风险>收益暂缓——生产走 _PG_ONLY 纯 PG 语义一致 |
| ✅ **doc-code 漂移** | `docs/tianji-design.md` | 仍写旧定义（气候基准 0.25 / 样本≥5），代码已更严（门控≥20） | `0a2a6ecb`：BSS 门控 ≥20 同步 |
| **C03 残留** | `control_server.py:504` | CORS 已收窄但仍 `host="0.0.0.0"` 绑全网卡；有 fail-closed token 兜底，单人家用 NAS 可接受 | 可选：绑回环 + 反代 |
| **前端 dangerouslySetInnerHTML** | `NewsPanel.tsx:63` / `SignalStreamPanel.tsx:212` | 安全依赖"抓取层 html.unescape + 渲染层 escapeHtml"隐式不变量；新抓取标题接进 trigger_titles 即成存储型 XSS | 文档化不变量或抓取/存储层转义 |

## 4. 待办 P3（触发式 / 门控 / 排期类）

| 项 | 触发条件 | 状态 |
|----|----------|------|
| P0-A 密钥轮换（.git/config PAT + tracked compose 明文 key + git 历史） | 仓库转公开/外部共享前（当前私有） | ⏸ |
| GED 数据决策（`data/ged/` 缺失 → geo_risk_vector GED 补强恒 None） | P2 门控（审计方 Q4） | ⬜ |
| H08/H11 剩余 ~30 处非原子写 | 已登记 P2 | ⬜ |
| 天璇控制台"只看不动"版（最近推演记录 + 参数 + 结果跳转） | 用户确认排期 | ⬜ |
| P2 门控自动化（每月 13 日检查 MIN_TRIGGER_N=8 触达） | 已设 automation | ✅ 已设 |

## 5. 备注（本次清理暴露的事实修正）

- **死循环规模 = 344 份源头 / 302 份副本，非早前记录的 26 份**（早前口径只统计了末尾时段）；文件名时间戳为 UTC，mtime 为本地 +08（`2026-08-16_12-34` 文件 mtime = 20:34）
- 死循环起止：本地 12:14（mtime 12:14 首份）→ 20:34（末份），触发字段清一色"（初始状态）"= sim_trigger 驱动，非 GRV 真实触发
- **报告源头链路**：天璇直写运行区 `macro-scan/docs/仿真报告`（bind 挂载）→ `generate_reports_index.py` 扫描复制到 `data/reports/` + 写索引 → 开阳 nginx 只读挂载。清理报告必须清**源头**（generate 自带"清理不在清单旧文件"逻辑，源头清了副本自动同步）
- git 树 `docs/仿真报告` 无死循环残留（rsync 无 --delete 未同步回）✅
