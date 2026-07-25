# macro-sim 开发进度

> 最后更新：2026-07-25  
> 当前版本：v2.0.10

---

## 当前状态：v2 已部署，正式运行

系统已完成从 v1（废弃）到 v2（正式）的重设计，部署在 NAS，daemon 模式运行中。

---

## v2 架构（已完成）

### 核心设计

- **每步 = 1个月**，前50步校准历史，后24步预测未来
- **12个 Agent**，按信息延迟分层（0~5个月），互相可见
- **三参数接口**：sensitivity / threshold / magnitude，校准期 LLM 自动调整
- **概率路径树**：Monte Carlo × 100，聚类出最多3条主路径（≥5%概率）
- **报告结构**：核心结论对比表 → 路径传导链（含因果箭头）→ LLM叙事（情景定性/传导链/投资影响）→ 校准说明

### 已完成模块

| 模块 | 文件 | 状态 |
|---|---|---|
| Agent 基类 + 三参数接口 | `core/agents/base.py` | ✅ |
| 12个 Agent 实现 | `core/agents/financial/geopolitical/social.py` | ✅ |
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
- 改进方向：对 GRV 历史做 3个月移动平均平滑，降低噪声
- LLM 调参没有全局视角，参数在50步内反复横跳——改进方向：给 LLM 提供最近5步误差趋势

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
| v2.0.5 | 2026-07-14 | 月度演化进度条：PathResult 加逐月字段，报告新增月度时间轴节 |
| v2.0.4 | 2026-07-13 | 文档修正：新 session 阅读路径统一（AGENTS.md 第167行） |
| v2.0.3 | 2026-07-09 | 叙事格式改进，传导链因果标注，路径起点GRV修正 |
| v2.0.2 | 2026-07-09 | 报告格式重设计，LLM叙事三段结构 |
| v2.0.1 | 2026-07-09 | FRED单位换算修复（%→bp），路径分叉调参 |
| v2.0.0 | 2026-07-09 | 完整重设计：12 Agent，校准+预测双循环，路径树 |
| v0.5.x | 2026-07-08 | daemon模式，报告生成，触发机制（已废弃） |
| v0.4.x | 2026-07-08 | P4校准占位符，接口版本化 |
| v0.1~0.3 | 2026-07-07 | P0-P3基础框架（已废弃，v2完全重写）|
