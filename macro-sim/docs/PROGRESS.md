# macro-sim 开发进度

> 最后更新：2026-08-07  
> 当前版本：v2.0.24

---

## 当前状态：v2.0.24 已部署 + A 类主权 Agent 激活（08-07）

系统已完成从 v1（废弃）到 v2（正式）的重设计，部署在 NAS，daemon 模式运行中。08-07 激活 A 类主权 Agent（S1-S5，soul 驱动派系决策），并修复 calibrator 新旧代码覆盖（D2/D3 fix 恢复生效 + _self_check）。**下一步：天璇 v3 soul 化重构**（设计文档 `docs/tianxuan-v3-soul-redesign.md` v1.3，待拍板后按三阶段实施）。

---

## v2 架构（已完成）

### 核心设计

- **每步 = 1个月**，前50步校准历史，后24步预测未来
- **17个 Agent**（12 金融 + 5 主权 S1-S5），按信息延迟分层（0~5个月，S 类试点 0），互相可见
- **三参数接口**：sensitivity / threshold / magnitude，校准期 LLM 自动调整
- **概率路径树**：Monte Carlo × 100，聚类出最多3条主路径（≥5%概率）
- **报告结构**：核心结论对比表 → 路径传导链（含因果箭头）→ LLM叙事（情景定性/传导链/投资影响）→ 校准说明

### 已完成模块

| 模块 | 文件 | 状态 |
|---|---|---|
| Agent 基类 + 三参数接口 | `core/agents/base.py` | ✅ |
| 12个 Agent 实现（金融层） | `core/agents/financial/geopolitical/social.py` | ✅ |
| 5 个主权 Agent（A 类激活） | `core/agents/sovereign.py` + `souls/S1-S5` | ✅（08-07） |
| Agent 配置热更新 | `config/agents.yaml` | ✅ |
| 世界状态（含新内生变量）| `core/world_state.py` | ✅ |
| 主仿真调度（action_history）| `core/simulation.py` | ✅ |
| 月度历史数据加载 | `core/world_state.load_monthly_history()` | ✅ |
| 校准循环 | `core/calibrator.py` | ✅ |
| 路径分叉检测 | `core/bifurcation.py` | ✅ |
| 报告生成 | `run.py._write_report()` | ✅ |
| LLM 叙事（三段结构）| `core/bifurcation._generate_narrative()` | ✅ |
| daemon 守护模式 | `run.py --daemon` | ✅ |
| ntfy 推送 | `run.py._send_ntfy()` | ✅ |
| sim_log.db 记录 | `core/sim_log.py` | ✅ |

---

## 已知问题 / 待改进

### 校准质量（优先级：中）

- 校准评分约 70/100，主要原因：GRV 历史数据在 2022-2026 间剧烈波动（月度±30），仿真难以追随
- ✅ v2.0.10 已实施：GRV 历史 3 个月移动平均平滑；LLM 调参附带最近5步误差趋势
- ✅ v2.0.20 已实施：误差目标改为内生变量（市场情绪/信贷紧缩/流动性溢价/资本外流），调参方向与因果链对齐

### 路径多样性（优先级：低）

- 98% 的路径在高 GRV 起点下走向压力区，路径B 概率仅5%
- 根本原因：GRV=80 的高压环境下大多数 Agent 倾向做空/收紧，没有明显分歧
- 现状可接受——这反映了当前宏观环境的真实特征

### 校准参数和预测参数分离（优先级：低）

- 校准期调参过于激进，导致预测时系统更保守，路径多样性下降
- 改进方向：校准参数作为参考，预测时用初始值和校准值的加权平均

---

## 运行命令速查

```bash
# 守护模式（NAS 容器默认）
python run.py --daemon

# 完整仿真（校准 + 预测）
python run.py --run --level 2 --event "GRV告警"

# 快速预测（跳过校准）
python run.py --predict-only --level 2 --event "测试"

# 手动触发（NAS SSH 后执行）
echo '{"level":3,"event":"手动触发"}' > \
  /vol2/1000/software/macro-scan/data/sim_trigger.json
```

---

## 版本历史

| 版本 | 日期 | 主要变化 |
|---|---|---|
| v2.0.23 | 2026-08-04 | 天玑 V1 验证链路迁移：删除 run_scoring()/_TIANJI_DDL（天玑独立容器 macro-ji v1.0.0 接管验证），保留 _archive_to_tianji 归档；标注 _write_json/_send_ntfy_simple 孤儿代码；sim_log.db 目录→文件修复 |
| v2.0.22 | 2026-08-04 | B+A/NOVEL Sprint-2：A2/A3/A6 soul 文件预位激活；慢变量 irp/ucri/gci 注入 MacroWorldState；D6 校准缓存（<7天跳过50步）|
| v2.0.21 | 2026-08-03 | B+A/NOVEL Sprint-1：SovereignAgent 基类 + Board 关系矩阵 + EnergyGovSovereignAgent（A4）+ 3 个主权 soul 文件 |
| v2.0.20 | 2026-08-03 | arch_review D2/D3：校准误差改为**内生变量**权重（market_sentiment×0.35+bank_credit_tightening×0.30+liquidity_premium×0.20+em_capital_outflow×0.15）；软目标推导 + 方向惩罚 + Teacher Forcing 只注入外生变量 |
| v2.0.19 | 2026-08-03 | soul 文件机制：A4 激活 A4_gulf_opec.yaml（doctrine/red_lines/factions）；A1_usa.yaml 预位 |
| v2.0.18 | 2026-08-03 | D14 fix：ecb_rate/usd_cny 从历史行读取（不再硬编码 3.0/7.1）|
| v2.0.17 | 2026-08-03 | D7 fix 续：social_stress/cultural_friction 接入（geo_risk_vector 透传）|
| v2.0.16 | 2026-08-03 | D7 fix：MacroWorldState 接入 6 个新 GRV 维度（当前 GRV 全集 16+1 维）|
| v2.0.15 | 2026-08-02 | P0 hotfix：_archive_to_tianji 改用 sqlite3 直写，修复 DB 路径，predictions 表首次真实写入 |
| v2.0.14 | 2026-07-31 | P0 修复：sim_trigger 单文件 bind mount inode 断链 |
| v2.0.13 | 2026-07-28 | 叙事美化逻辑抽取为 core/narrative_format.py 纯函数 |
| v2.0.4 | 2026-07-13 | 文档修正：新 session 阅读路径统一（AGENTS.md 第167行） |
| v2.0.3 | 2026-07-09 | 叙事格式改进，传导链因果标注，路径起点GRV修正 |
| v2.0.2 | 2026-07-09 | 报告格式重设计，LLM叙事三段结构 |
| v2.0.1 | 2026-07-09 | FRED单位换算修复（%→bp），路径分叉调参 |
| v2.0.0 | 2026-07-09 | 完整重设计：12 Agent，校准+预测双循环，路径树 |
| v0.5.x | 2026-07-08 | daemon模式，报告生成，触发机制（已废弃） |
| v0.4.x | 2026-07-08 | P4校准占位符，接口版本化 |
| v0.1~0.3 | 2026-07-07 | P0-P3基础框架（已废弃，v2完全重写）|
