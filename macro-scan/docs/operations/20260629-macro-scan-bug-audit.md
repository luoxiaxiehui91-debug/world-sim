# 操作日志：全系统 Bug 审查与修复

**日期**：2026-06-29  
**操作者**：Claude Code  
**版本变更**：v3.5.18 → v3.5.21  
**类型**：Bug 修复（无功能变更，无需重建镜像）

---

## 背景

对 47 个 Python 源文件进行全面 bug 审查（3 个并行 Agent，覆盖推演引擎逻辑、配置一致性、并发安全三个维度），随后人工逐行复核，撤销 6 项误报，修复 25 项真实问题，分 3 个版本提交。

---

## v3.5.19 修复内容

### hypothesis_engine.py（7项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| HYP-1 | `"conf" in dir()` 改为 `conf = None` 初始化 | 消除 CPython 行为歧义 |
| HYP-2 | `_compile_wiki_entry` 接受外部 conf，不再空参重算 | wiki 置信度元数据从无意义值改为真实推演值 |
| HYP-3 | `_conf_summary` 中重复 `signal=` 改为 `freshness=` | 消除 d3 维度得分与顶层信号灯语义混淆 |
| HYP-4 | wiki 追加写入加 `threading.Lock()` | 防止并发推演条目交错损坏 |
| HYP-5 | `build_hypothesis_prompt` 接受外部 matched_paths/conf | 消除重复计算、消除报告内外置信度数值不一致 |
| HYP-6 | 信号灯两个 `elif` 分支合并 | 逻辑清晰，注明永不输出🟢 |
| CON-5 | wiki 编译线程从 `daemon=True` 改为 `daemon=False` | 防止 Docker SIGTERM 时 wiki 写入被截断 |

### hypothesis_config.py（2项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| CFG-2 | CULTURAL 维度从不存在的 `cultural_friction` 改为 `global_composite` | 消除 KeyError 风险 |
| CFG-9 | RELIGIOUS 维度从 `middle_east_energy` 改为 `global_composite` | 宗教冲突不再错误拉高中东能源风险分 |

### geo_risk_vector.py（1项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| CFG-1 | `middle_east_energy` 合成从错用 `gpr_global` 改为纯 GDELT | 消除与 `global_composite` 的虚假相关性 |

### regime_detector.py（2项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| CFG-4 | `gscpi_warn` 死代码改为 `signals += 1`，`max_signals` 从 7 更新为 8 | GSCPI 供应链压力信号正式纳入体制检测 |
| CFG-7 | `_compute_zscore` 加 `sd_floor` 保护 | 防止冷启动期 std→0 时 Z-score 爆炸 |

### hybrid_llm.py（2项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| CON-2 | `call_minimax` 加 `msg.content` 空列表检查 | 防止 content policy 拒绝时 IndexError |
| CON-3 | `reason()` auto 模式加 `ThreadPoolExecutor + future.result(timeout=300s)` | 降级链最坏情况从 725s 降到 300s |

### scorer.py（3项）
| 问题ID | 描述 | 影响 |
|:-------|:-----|:-----|
| HYP-7 | 泰勒规则 LPR 从硬编码 3.10 改为从 `indicators["cn_lpr"]` 动态读取 | 支持 LPR 调整后实时反映 |
| HYP-8 | `match_crisis` 低失业率增加反向接近度逻辑 | 不再漏检"繁荣期埋雷"型危机初期 |
| HYP-9 | `score_inflation_risk` 信号计数去 `min(n,6)` 截断 | n>6 时显式返回"极端" |

---

## v3.5.20 修复内容

### regime_detector.py（2项）
| 问题ID | 描述 |
|:-------|:-----|
| CFG-5 | 新增 `REGIME_COEFFICIENTS["crisis"]` 专属条目（rate_gdp_impact=-1.50，credit_multiplier=4.0）；`get_coefficients()` 去掉 crisis→stress 静默借用 |
| CFG-8 | `NBER_RECESSIONS` 加最后更新日期注释（2026-06-29，截止 2020Q2） |

### alert_config.py（1项）
| 问题ID | 描述 |
|:-------|:-----|
| CFG-6 | docstring 补充类别↔推演维度对照表，说明"文化贸易摩擦/战略矿产/科技竞争"归入 TRADE 维度 |

### scheduler.py（1项）
| 问题ID | 描述 |
|:-------|:-----|
| CON-6 | docstring 补全任务隐式依赖关系表，说明时间间隔保证的执行顺序 |

---

## v3.5.21 修复内容

### hybrid_llm.py（1项）
| 问题ID | 描述 |
|:-------|:-----|
| CON-3 再修 | `with ThreadPoolExecutor` 写法中 `__exit__` 调用 `shutdown(wait=True)` 使超时实际无效；改为不用 `with`，超时后显式 `shutdown(wait=False, cancel_futures=True)` |

### optim_config.py（1项）
| 问题ID | 描述 |
|:-------|:-----|
| CFG-3 | 删除 `PUSH_ENDPOINT` / `CRUCIX_ENDPOINT` 两个死常量（OpenClaw 时代遗留，无任何调用者） |

### fetch_china_data_akshare.py + fetch_china_data.py + data_fetcher.py + run_macro_analysis.py（1项）
| 问题ID | 描述 |
|:-------|:-----|
| HYP-7 完整 | `fetch_china_data_akshare.py` 加 `_fetch_cn_lpr()` 函数和 `_DISPATCH["cn_lpr"]`；`fetch_china_data.py` 的 `_AK_YEARLY_SERIES` 加入 `cn_lpr`；`data_fetcher.py` 的 `CHINA_INDICATORS` 加入 `cn_lpr` 条目；`run_macro_analysis.py` 第1611行硬编码同步修正 |

---

## 撤销的误报（6项）

| 误报ID | 误判描述 | 实际情况 |
|:-------|:---------|:---------|
| HYP-2(原) | `stdev` 崩溃 | `len(spx_nums)<2` 时走 `d4=0.5` 分支，不调 stdev |
| HYP-3(原) | `_bd` 未定义 | 第901行已有 `_bd = _conf["breakdown"]` |
| HYP-6(原) | `grv_val=None` TypeError | 第589行已有 `if grv_val is None` 判断 |
| CON-1 | SQLite 无 WAL | `news_db.py` 第128行 `_conn()` 已有 WAL + busy_timeout |
| CON-4 | ntfy 监听阻塞 | 所有命令处理函数均已用 `threading.Thread` 异步执行 |
| CON-7 | R08 依赖 asset_prices.json | R08 直接读 `fred_history/*.csv`，该文件名在代码库中根本不存在 |

---

## 无需重建镜像的确认

本次所有修改均为 `核心代码/*.py` 热挂载文件，docker-compose.yml、Dockerfile、entrypoint.sh 均未变更，**无需重建镜像，无需 `up -d`，容器内即时生效**。

## 验证建议（推送 NAS 后）

```bash
# 1. 确认 wiki 并发安全（触发两次推演后检查文件完整性）
docker exec macro-scan-macro-scan-1 python3 /app/verify_hypothesis.py

# 2. 确认 LPR 采集成功（次日 05:45 china_fetch 运行后）
docker exec macro-scan-macro-scan-1 cat /workspace/data/china_history/cn_lpr.csv | tail -3

# 3. 确认 GRV 中东能源维度独立于 global_composite
docker exec macro-scan-macro-scan-1 python3 -c "
import json
d = json.load(open('/workspace/data/grv_latest.json'))
print('中东能源:', d.get('middle_east_energy'))
print('全球综合:', d.get('global_composite'))
print('两者相同?', d.get('middle_east_energy') == d.get('global_composite'))
"

# 4. 确认 MiniMax 空响应不崩溃（需 mock 测试）
docker exec macro-scan-macro-scan-1 python3 -c "
from hybrid_llm import call_minimax
# 正常路径测试（若 KEY 有效）
print('hybrid_llm 导入正常')
"
```
