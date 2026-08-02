# 世界推演系统 — ROADMAP

> **此文件是项目内权威 todo 文件，随源代码同行。**  
> 跨项目视角的补充积压见：`S:\docs\backlog\world-deduction.md`  
> 运维 SOP 与部署规范见：`S:\world-sim\AGENTS.md`

---

## 时间门控任务

| 状态 | 完成/预计时间 | 任务 | 说明 |
|------|--------------|------|------|
| ✅ | 2026-07-10 | **C线切 Live + R07 启用** | C线由 mock 切换 Live 数据；R07（气候风险）信号 `enabled: true` |
| ✅ | 2026-07-25（v3.5.61） | **situation_detector 阈值 2.0→1.5** | 降低告警触发门槛，改善中度地缘压力下的信号灵敏度 |
| ✅ | 2026-07-25（v3.5.62） | **R09/R10 启用** | social_stress / cultural_friction 积累基线后正式 `enabled: true`；v3.5.62 修复相关 bug 后完成 |
| ⏳ | 待核实（原约2026-08-01已过期） | **R11/R12 开启** | 气候/多域信号积累基线后启用；前置条件：climate_risk 和跨域维度各积累 ≥3 周有效数据；**需 SSH 到 NAS 确认实际积累情况后更新此日期** |
| ⏳ | 2026-08-09 | **signal_synthesizer Staging→Live 切换** | `docker-compose.yml` 加 `STAGING_MODE=0` + `force-recreate`；切后 R09/R10 真正调 LLM + 推 ntfy；前置：signal_synthesizer 上线满 30 天（2026-07-10 起算，08-09 满足）；**注意：代码内有独立数据成熟度守门（news.db ≥30天），两层均需满足** |
| ⏳ | 2026-09-10 | **GDELT scale 校准** | 校准 `religious_conflict` / `regime_change` / `social_stress` / `cultural_friction` 的 scale 参数（含 2026-07-25 v3.5.62 新增两个维度，scale=200 为估算值需实测验证）；GDELT 信号量级与 GRV 其他维度对齐 |
| ⏳ | 约 2026-08-10 前 | **天枢叙事摄取真正跑通** | narrative_chunks 当前只有 3 行（3 个测试维度）；scheduler 任务 narrative_proc 调度是否实际写入需验证；目标：每日稳定产出 ≥50 条叙事块覆盖 ≥6 个维度 |
| ⏳ | 约 2026-08-10 前 | **慢变量 slow_variables.json 首次产出** | slow_variables.py 代码在容器，但 slow_variables.json 不存在（月度 cron 08-01 首次触发）；UCRI/GCI 需手工评估分数才能完整计算，需在 08-01 前准备 manual_scores |
| ⏳ | 约 2026-09-30 | **天玑 V1 启动** | 第一批 macro-sim 预测到期后，手动建 `prediction_ledger.db`，录入已有预测并完成首次评分；目前 predictions 表仅 1 条测试数据 |
| ⏳ | 2026-11-19 | **N2 新闻库第二阶段** | news.db 架构第二阶段；扩展信号采集覆盖范围，配套 synthesis_log 验证 |
| ⏳ | 2027-05-23 | **N3 信号月度校验** | 月度信号校验闭环全面激活；解锁天玑 V4 校准闭环 |
| ⏳ | 真实地缘事件发生后 | **M2-4 校准闭环激活** | 利用实际发生的重大地缘事件对 macro-sim M2-M4 校准参数做后验核查 |
| ⏳ | 推演后验准确率 ≥60% 且 ≥10 条样本后 | **M3 开放量化区间** | 天玑准确率面板达标后解锁；允许 macro-sim 对 GRV 方向性预测给出置信区间 |

---

## 新架构迁移状态（2026-07-30 SSH 实测）

> 基于 `S:\20260729\16_世界推演系统_架构总文档_v1.0.md` 定义的新架构，v3.7.0 部署后的真实状态。

| 模块 | 声称状态 | 实测状态 | 关键缺口 |
|------|---------|---------|---------|
| 天枢调度（GRV/FRED/GDELT/新闻） | Live | ✅ 真实运行，今日22 job 正常触发 | — |
| narrative_chunks 叙事摄取 | 骨架已接入 | ⚠️ 只有 3 行，未稳定产出 | scheduler 任务是否真正写入待验证 |
| slow_variables（IRP/UCRI/GCI） | IRP 已上线 | ❌ slow_variables.json 不存在 | 月度 cron 08-01 首触发；UCRI/GCI 手工评估节点未准备 |
| predictions / reasoning_trace | 天玑已测试 | ⚠️ 各 1 条测试数据（pending） | 未真正运转 |
| weight_update_log | — | ❌ 0 行 | 玉衡未运转 |
| narrative_density_flags | — | ❌ 0 行，json 不存在 | — |
| sim_trigger.json | GRV 告警自动触发天璇 | ❌ 空文件 | 路径A从未触发 |
| 天璇 macro-sim | v2.0.13 运行 | ⚠️ 旧版 Monte Carlo，新架构 B+A/Agent 体系未重写 | 最大空白 |
| grv_weights.yaml | 19 源 1254 条 | ✅ 1281 行，正常 | — |
| source_dimension_map.yaml | 完整性校验 | ✅ 2157 bytes，存在 | 启动校验逻辑是否真正执行待查 |

---

## 天玑（macro-ji）实施路线图

> 天玑 = 验证层，在天枢（macro-scan）+ 天璇（macro-sim）之上，对推演结果做事后验证和校准闭环。  
> 详细设计见：`S:\world-sim\docs\tianji-design.md`

```
天枢（macro-scan）── 每日观测 ──> 天璇（macro-sim）── 推演路径 ──> 天玑（macro-ji）
   ↑                                                                     |
   └───────────── 校准权重更新（N3 月度校验，2027-05-23 解锁）─────────────┘
```

| 阶段 | 解锁条件 | 核心内容 | 预估工作量 |
|------|---------|---------|-----------|
| **V1 手动存档** | 建议 2026-09-30（首批预测到期） | 建 `prediction_ledger.db`；手动从历史仿真报告录入可验证预测主张；对 GRV 方向性预测用 `grv_history.jsonl` 评分；输出第一份准确率报告 | 2-3h |
| **V2 自动提取** | V1 稳定后 | LLM 自动解析 macro-sim 报告，提取可验证主张写入 ledger；无需人工逐条录入 | 约 1 天 |
| **V3 自动验证** | 2026-09+ | 月度 cron 自动对到期预测评分；生成准确率面板（port 8899 新增 `/accuracy` 路由，或独立 8900 端口） | 约 1 天 |
| **V4 校准闭环** | N3 解锁（2027-05-23） | `suggested_weight_adjustments` 写回 macro-scan 信号权重；系统形成自我进化闭环 | 约 2 天 |

---

## macro-sim 待改进（按优先级）

| 优先级 | 项目 | 说明 |
|--------|------|------|
| Low | **校准参数/预测参数分离** | 当前 M1（校准阶段，前50步）和 M2（预测阶段）共用部分参数，应明确隔离，便于天玑 V4 写回时精准作用 |
| Low | **路径多样性** | 高 GRV 下多路径收束属正常系统现象；暂缓处理，待天玑 V3 积累准确率数据后再评估是否需要干预 |

---

## 活跃问题

来源：`S:\docs\questions\world-deduction\`

> **编号约定**：表格「编号」列 P2 / P3 / P4 为**顺序问题编号**（沿用 question 文档命名，相当于工单号），**并非优先级等级**。优先级档位另见 `S:\docs\backlog\world-sim-optimization-proposal.md`（P0=阻塞 … P3=暂缓，共 4 档）。勿将「P4 编号」误读为「最低优先级」。

| 编号 | 状态 | 问题 | 来源文件 | 说明 |
|------|------|------|---------|------|
| P3 | ✅ 已修复 | **报告叙事分隔符脆弱（B1）** | `20260718-world-deduction-report-narrative-separator-fragile.md` | v2.0.12 归一化+prompt 诚实化；v2.0.13 抽 format_narrative 纯函数+11 用例回归测试；2026-07-28 部署验证通过 |
| P4 | ⏸ 观察（降级） | **GDELT 全0信号（疑似）** | `20260627-world-deduction-gdelt-normalization-zero.md` | 2026-07-28 抽 NAS 实测 GDELT 当前**非全0**（管线健康），原「本期立项」假设失效；防御补全并入 2026-09-10 GDELT scale 校准任务，不单独占本期。实际严重度低（观测层低风险增强），编号 P4 为工单号非优先级 |
| P2 | ⏸ 暂缓 | **路径多样性低** | `20260714-world-deduction-low-path-diversity-high-grv.md` | 高 GRV 下路径多样性下降为正常系统特征；待天玑积累数据后重新评估是否真实问题 |
| G5a | ✅ 已完成（2026-07-28） | **联动矩阵补 README.md** | macro-sim/AGENTS.md | 天璇 macro-sim 联动矩阵补充同步目标 macro-sim/README.md；零代码风险，防版本漏同步（B1 收尾曾漏改 README）；已落 NAS，VERSION 不 bump |

---

## 积压（无时间门控）

以下为已识别但暂未排期的架构级改进：

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P2 | **置信度衰减机制** | 假说置信度应随时间衰减（无新信号支撑则降低），当前为静态累积 |
| P2 | **多路径交叉干扰** | 多条推演路径共享部分中间态时，路径间干扰未建模，可能导致概率分布失真 |
| P3 | **非洲/南亚传导路径** | 当前 GRV 维度对非洲次大陆和南亚次区域的传导路径覆盖不足 |
| P3 | **L4 极端尾部场景** | 极低概率高影响事件（核威慑升级、全球性金融危机）缺乏独立建模路径 |
| P3 | **假阳性率回测框架** | 对历史 GRV 告警做回测，量化假阳性率；为调整 situation_detector 阈值提供数据依据 |
| P2 | **月度调用配额计数器** | fetcher_base.py 加 `monthly_call_limit` 类属性 + `data/fetch_quota.json` 计数，超限返回 SKIPPED；子类声明上限即可（如 CoinGecko 免费版月限10000的50% = 5000）。现有防线仅靠调度频率，无数值验证 |
| P2 | **IRP 扩充历史标注期** | 补充朝鲜战争通胀（1950-06/1951-12）、越战通胀（1966-01/1970-12）、金融危机前后（2003-01/2009-12），样本从~170条增至~450条；同时补 DFII10 近似中性利率差特征 |
| P2 | **仿真引入历史 VAR 基准轨道** | Agent 轨道（定性方向）+ VAR 轨道（历史统计量级）并行，Agent 只提供相对基准的偏离量；适合 B+A/NOVEL 重写 Sprint 一并处理 |
| P2 | **天枢 MC 与天璇 Agent 仿真协同** | 目前两套完全独立：天枢统计 MC 出"衰退概率35%"、天璇 Agent 出"情绪崩溃路径"，无法互相校准。改进方向：天璇启动时从天枢 mc_engine 结果读取基准轨道（GDP/通胀/利率的统计期望路径），Agent 冲击叠加在此基准上而非凭空生成绝对数值；两套输出进入同一个 predictions 表对比 |
| P2 | **清理 mc_engine.py 废代码** | `mc_engine.run_monte_carlo()` 原版函数已无调用方（全部切到 monte_carlo_v2），保留只会误导维护者；清理后 mc_engine 职责变为：中国路径封装 + 压力测试 + 情景比较，定位清晰 |
| P1 | **hypothesis_engine / signal_synthesizer 从 Staging 切 Live** | 两层独立守门均需满足：①docker-compose.yml 加 STAGING_MODE=0；②news.db 数据成熟度 ≥30天（_check_data_maturity）；按2026-07-10起算，**最早 2026-08-09 执行**；切换前确认 NAS 容器内 news.db 实际积累天数 |
| P2 | **GM 规则量级实证校准** | 用 FRED+历史事件数据做事件研究，对每条 GM 规则（如 CUT_50BP→sentiment+0.35）验证量级合理性，写回 agents.yaml 的 magnitude |
| P1 | **慢变量接入 MacroWorldState** | world_state.py 加 irp/ucri/gci 三字段，load_from_macro_scan() 读取 slow_variables.json 注入；Agent _decide_rules() 据此调整阈值；"转型期置信区间扩宽1.5倍"真正落地 |

---

## 较大工程（需外部资源）

| 项目 | 前置条件 | 说明 |
|------|---------|------|
| **ACLED 武装冲突数据接入** | 申请 `acleddata.com` API key | ACLED 提供实时武装冲突事件数据；GED v26.1 年度快照已接入（`etl_ged.py` 产物在 `data/ged/`，含 GCI 历史锚点），ACLED 用于提升实时信号质量 |
| **天玑 GCI 面效度验证函数** | GED 锚点已生成（`data/ged/gci_anchors.json`，PASS） | 实现 `check_gci_validity()`，月度对比当前 GCI 分数与历史锚点的相关性；预计天玑 V1 周期实施 |

