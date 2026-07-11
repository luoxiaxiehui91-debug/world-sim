# 宏观演化仿真系统 (macro-sim)

macro-scan 发现信号之后，这里负责**演化未来**：把当前世界状态和 12 个宏观角色放进去，让它们按各自逻辑互动，结果从演化中涌现出来。

**当前版本**：v2.0.2

---

## 这是什么

macro-sim 是一个 **ABM（Agent-Based Model）演化仿真器**，不是推理机。

- **macro-scan** = 推理机：拿已知数据沿逻辑链推一步，预测下一周
- **macro-sim** = 模拟机：把世界放进去跑，看未来 24 个月如何演化

两者互补，不重叠。

---

## 工作原理

```
前 50 个月历史数据（校准期）
    ↓ 逐月拟合，LLM 自动调整 Agent 参数
校准质量评分（0~100）
    ↓
当前真实状态（GRV / 利率 / 利差）
    ↓ Monte Carlo × 100，初始状态加随机扰动
100 条演化路径 → 聚类 → 路径树（最多3条，概率 ≥5%）
    ↓ 每条路径：传导链 + LLM 叙事（情景定性 / 核心传导链 / 投资影响）
Markdown 报告写入 macro-scan/docs/仿真报告/
ntfy 推送手机
```

---

## 12 个宏观 Agent

| ID | 角色 | 信息延迟 | 主要行为 |
|---|---|---|---|
| A1 | 美联储 | 4个月 | 加息/降息/口头干预 |
| A2 | 商业银行 | 2个月 | 收紧/放松信贷 |
| A3 | 对冲基金 | 即时 | 做空/做多/降险 |
| A4 | 能源国(OPEC+) | 5个月 | 减产/增产 |
| A5 | 机构投资者 | 2个月 | 增/降风险敞口 |
| A6 | 媒体/舆论 | 1个月 | 放大恐慌/中性报道 |
| A7 | 新兴市场央行 | 3个月 | 资本管制/加息 |
| A8 | 中国央行/财政 | 3个月 | 降准/刺激/汇率干预 |
| A9 | 美国财政部 | 4个月 | 财政刺激/债务上限 |
| A10 | 散户/羊群 | 即时 | 跟风抛售/追涨 |
| A11 | 欧洲央行 | 4个月 | 利率/QE政策 |
| A12 | 日本央行 | 4个月 | YCC调整（触发套息危机）|

每个 Agent 感知到其他 Agent **延迟后**的行动——对冲基金即时看到媒体报道，但美联储要 3 个月后才看到对冲基金的做空信号。

---

## 报告示例

```markdown
# 宏观演化仿真报告 — 2026-07-09
**触发**：GRV告警 | **级别**：L2 | **预测范围**：未来 24 个月 | **校准**：71/100 ✅

## 一、核心结论
GRV 当前 80.2（高压区），信用利差 155bp

| 维度 | 路径A（98%） |
|---|---|
| GRV 24个月后 | 82.1 →（高压区） |
| 市场情绪 | -0.57（深度压力） |
| 信用利差 | 279bp ↑ |
| 主要驱动 | 对冲基金做空、商业银行收紧信贷 |

## 二、路径详情
传导链：
  第1个月    对冲基金大规模做空（99%）
  第2个月  ↳ 散户恐慌性抛售（49%）← 对冲基金大规模做空
  第3个月  ↳ 媒体放大恐慌情绪（49%）

情景定性：慢性高压风险传导路径
核心传导链：对冲基金因 GRV 超阈值做空 → 信贷收紧 → 散户/媒体负反馈
对你的影响：警惕信用利差走阔（+124bp），债券流动性风险上升
```

---

## 运行方式

```bash
# 守护模式（默认，等待 macro-scan 触发）
python run.py --daemon

# 手动完整仿真（校准 + 预测）
python run.py --run --level 2 --event "手动测试"

# 快速预测（跳过校准，用默认参数）
python run.py --predict-only --level 2 --event "快速测试"
```

---

## 触发机制

macro-scan 检测到 GRV 告警时，自动写 `data/sim_trigger.json`，macro-sim daemon 检测到后运行仿真（延迟 ≤1 分钟）。

也可手动写触发文件：

```bash
echo '{"level":3,"event":"手动触发"}' > \
  /vol2/1000/software/macro-scan/data/sim_trigger.json
```

---

## 部署（NAS）

```bash
# 首次部署
touch /vol2/1000/software/macro-sim/sim_log.db
mkdir -p /vol2/1000/software/macro-scan/docs/仿真报告
touch /vol2/1000/software/macro-scan/data/sim_trigger.json

# 同步代码 + rebuild
rsync -av --exclude='.git' --exclude='output/' --exclude='sim_log.db' \
  macro-sim-src/ /vol2/1000/software/macro-sim/
cd /vol2/1000/software/macro-sim
docker build -t macro-sim:latest .
docker compose up -d
```

---

## 文档

| 文件 | 用途 |
|---|---|
| `macro-sim_人类说明文档.md` | **人类使用手册**：原理/触发/报告/运维/已知问题 |
| `AGENTS.md` | AI session 入口：目录结构、约束、工作流 |
| `CHANGELOG.md` | 版本变更记录 |
| `docs/design_v2.md` | v2 架构设计（已确认） |
| `docs/PROGRESS.md` | 开发进度 |
| `config/agents.yaml` | 12个 Agent 配置（热更新，新增角色只加配置）|
