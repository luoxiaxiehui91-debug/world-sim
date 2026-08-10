# R4h ① 三批合并验收执行 Runbook（qa-r4h3，工作副本）

> 状态：**待部署**（team-lead 通知含 commit hash 后执行）
> 验收对象：v2.0.40 / CACHE 14 / ARTIFACT_TAG v2033 / 断言 124（ease_ok + act_prob 0.76 + cap 17）
>
> ⚠ **假复现更正（2026-08-10）**：本文"① v2.0.40 预期"列（M6 12 / EASE correct 18 / silence 2/5 超 / M5 0.789 / S2 0.529 / credit 回池 / p̂ 0.5729 / CI 0.4877）基于 A3 soul 缺失环境（config 放 /tmp → load_agents soul 路径 dirname(config)/../souls 解析失败 → A3 soul={} 回退旧决策），容器真实部署不可复现。权威结论见 C:\tmp\r4h_data2\R4h_Part4_前后对比.md §5。**容器实测（v2.0.40/CACHE 14/v2033）：EASE correct 16 / M6 13 / silence 4/5 超（median 0.531，seed123 0.633 最差）/ credit 未回池 / p̂ 0.4894（CI 0.4063）/ S2 0.636 / consistency 0.750。** 下述"① 预期"列已全部替换为容器实测值。
> 基线：v2.0.39（② 终版，commit bc32f9d，qa-r4h2 实测）
> 环境：SSH nas + docker exec macro-sim（COPY 模式，代码 /app/）；宿主 repo /vol2/1000/software/world-sim/macro-sim
> 铁律：禁 TaskOutput；前台同步；--read-only 判定；探针只写 /tmp；禁 calibration_cache；禁 skip/.only

---

## 部署前基线锚点（已确认 2026-08-10）

| 锚点 | 部署前值（② 终版） | ① 后应变为 |
|------|-------------------|-----------|
| 容器 VERSION | v2.0.39 | v2.0.40 |
| CACHE_VERSION（calibrator.py L134） | 13 | **14** |
| ARTIFACT_TAG（rpa L69） | v2032 | **v2033** |
| financial.py A2 | 有 tighten_ok、**无 ease_ok** | 加 ease_ok 方向闸（与 tighten_ok 镜像） |
| agents.yaml A2 activation_prob | 0.70 | **0.76** |
| world_state.py vix_yen_carry_bleed_max | 19.0 | **17.0** |
| world_state.py vix 均值回归 | 0.80/0.20（L351） | 保留（② 不回退） |
| simulation.py EASE +0.08×m | L148（③ 保留） | 保留（③ 不回退） |
| calibrator.py a2_action 落盘 | L738 | 保留存在 |
| 测试断言 | 120（guards 108 + narrative 12） | **≥124**（① 新增 ≥4） |

---

## 执行顺序

### Step 1 — git show 核验 arch 改动（commit hash 由 team-lead 通知）

```bash
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && git show <HASH> --stat"
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && git show <HASH> -- core/agents/financial.py config/agents.yaml core/world_state.py core/simulation.py core/calibrator.py scripts/run_probe_acceptance.py tests/ VERSION"
```

核验清单：
- [ ] **ease_ok 方向闸**（financial.py EASE 分支）：`ease_ok = (target_dir != "tighten") or vix_stress > p.threshold * 2.0`，`and ease_ok` 加入 ease_signal —— 与 tighten_ok 镜像对称
- [ ] **P0 阻断**：`grep -rn "sentiment" core/ | grep -- "-0.3"` → **空**（发现即 FAIL）
- [ ] act_prob 0.76（config/agents.yaml，**非 0.78**）
- [ ] cap 17.0（world_state.py vix_yen_carry_bleed_max）
- [ ] CACHE=14 / VERSION=v2.0.40 / ARTIFACT_TAG=v2033
- [ ] ③ EASE +0.08×m 保留（simulation.py）；② vix 均值回归 0.80/0.20 保留（world_state.py）
- [ ] 被挡步分支：ease_ok=False 后转 HOLD（冷却递减，financial.py 分支3/4）——单测锁 3 态 + 抽步人工核对
- [ ] a2_action 落盘仍在（calibrator.py）
- [ ] 断言 ≥124 新增（ease_ok 方向闸 2 + act_prob/cap 组合回归 1 + M4 保持 1）
- [ ] **② P2 修复**：CACHE 注释参数（0.80/0.20、cap17、ease_ok、act_prob 0.76）；registry 变更 8 commit message 修正（+0.061→+0.020）

### Step 2 — 反作弊门

```bash
# 测试文件删除检测（应空）
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && git diff --name-status HEAD~1 -- tests/ | grep '^D'"
# skip/.only 新增检测
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && grep -n '@pytest.mark.skip\|@unittest.skip\|pytest.skip(\|\.only\|xfail\|focus' tests/*.py"
# 断言数对比（≥124，不降）
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && grep -rh 'assert ' tests/*.py | wc -l"
# 容器 CACHE 生效（grep 镜像内）
ssh nas "docker exec macro-sim sh -c 'grep -n \"CACHE_VERSION = \" /app/core/calibrator.py; grep -n \"ARTIFACT_TAG = \" /app/scripts/run_probe_acceptance.py; cat /app/VERSION'"
# P0 sentiment>-0.3（容器双查）
ssh nas "docker exec macro-sim sh -c 'grep -rn \"sentiment\" /app/core/ | grep -- \"-0.3\"'"
# 禁 calibration_cache：确认 CACHE=14 全新探针（无 v13 缓存复用）
# EPS_TGT=0.03 / weighted 0.60 冻结确认
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && grep -rn 'EPS_TGT' core/ tests/ | head; grep -n '0.60' core/calibrator.py | head"
```

### Step 3 — 断言 124 独立重跑

```bash
# 容器内为生产镜像（无 pytest）→ 在宿主 repo 同 commit 重跑
ssh nas "cd /vol2/1000/software/world-sim/macro-sim && python tests/test_calibrator_guards.py && python tests/test_narrative_format.py"
# 期望：0 fail 0 error；断言 ≥124（guards 108+①新增 + narrative 12）
```

### Step 4 — run_probe_acceptance 5 seed 正式验收（v2033 落盘 /tmp）

```bash
ssh nas "docker exec macro-sim sh -c 'cd /app && python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2033 --data-root /app/macro_data'"
ssh nas "docker exec macro-sim sh -c 'cd /app && python scripts/run_probe_acceptance.py --out-dir /tmp/r4h_qa_v2033 --data-root /app/macro_data --read-only'"
```

---

## 五闸 + 硬闸判定（① v2.0.40 容器实测 vs ② v2.0.39 基线）

### M6 裁决闸（TIGHTEN wrong ≤17，容器实测 13）
| seed | ② 基线 | ① 容器实测 |
|------|--------|--------|
| 42 | 4 | 4 |
| 7 | 5 | 3 |
| 123 | 3 | 2 |
| 2024 | 3 | 3 |
| 777 | 1 | 1 |
| **合计** | 16 | **13 ≤17** |

> >17 → **① FAIL 单行回退 cap19**；容器实测 **13** ≤17 达标（假复现预期曾为 12/14±2）

### EASE wrong 闸（==0 ∧ correct ≥15 不降，容器实测 16/0）
- ② 基线：EASE wrong 8 / correct 15（rate 0.652）
- ① 容器实测：wrong **0**、correct **16**（不降反升；假复现预期曾为 18）
- **防伪治理线**：correct 降 → 一刀切禁 EASE 伪治理 FAIL

### M2 silence diff ≤+0.05（vs v2.0.39 ② 基线；容器实测）
| seed | ② silence | ① 容器实测 silence | diff |
|------|-----------|----------------|------|
| 42 | 0.510 | 0.469 | -0.041 |
| 7 | 0.571 | 0.510 | -0.061 |
| 123 | 0.551 | 0.633 | +0.082 |
| 2024 | 0.510 | 0.510 | 0.000 |
| 777 | 0.490 | 0.490 | 0.000 |
> 容器实测：M2 相对 diff 有 1 seed（seed123 +0.082）> +0.05；绝对线 4/5 超

### 绝对 silence 超线（容器实测 4/5 超：median 0.531，seed123 0.633 最差）
- 42:0.469 ≤0.50 ✅；777:0.490 ≤0.50 ✅
- seed7 0.510 / seed2024 0.510 / seed123 0.633 >0.50 → 超线（假复现预期曾为 2/5：seed7+seed123）
- 容器实测未达 ≤2/5 目标；credit 因 silence 超线未回池

### M4 flip == 0（EASE 后 2 步内 TIGHTEN 决策，a2_action 决策级）
- ease_ok 转 HOLD 不得引入 flip

### M5 credit consistency ≥0.45（容器实测 0.750，② 0.538；假复现预期曾为 0.789）

### S2 grv_down reverse ≤0.60 达标（容器实测 0.636，② 0.682 warn；假复现预期曾为 0.529）
- 0.60-0.727 warn；≥0.727 FAIL——容器实测 0.636 落 warn 档，未达 ≤0.60

### credit 回池（容器实测未回池；假复现预期曾为 3 变量回池）
- ② 后 credit 出池（eligible 2 变量，N=135）；① 后容器实测 **仍未回池**（credit silence median 0.531 >0.50）——该项不通过，挂起转后续 silence 治理

### p̂ 落档
- 容器实测 0.4894 点估 **<0.55 未过 partial**（假复现预期曾为 0.5729 partial 达标）
- CI 0.4063 advisory（N 口径见 Part4 §5）——记录"未过 0.55"，不记 partial/accept

---

## ③② 回归确认（① 不得破坏 ③② 已达成状态）

| 项 | ② 基线 | ① 后应保持 | 判定 |
|----|--------|-----------|------|
| S1 无 ≥0.5 尖峰 | ge05 全 0 | ge05 全 0 | ✅ |
| A1 HIKE ≤1 | A1 CUT 5-6 步 | 不破坏 | ✅ |
| tsf 非零 | 4/3/5/6/5 | 非零 | ✅ |
| a2_action 落盘 | L738 | 保留 2 处 | ✅ |
| EASE +0.08×m | simulation.py L148 | 保留 | ✅ |
| yen_carry cap | 19.0 | **17.0**（①-C 生效） | ✅ |
| vix 均值回归 | 0.80/0.20 | vix_last<vix_max 生效 | ✅ |

## ② P2 修复确认
- [ ] CACHE 注释参数已更新（0.80/0.20、cap17、ease_ok、act_prob 0.76）
- [ ] registry 变更 8 回填 commit message 修正（+0.061→+0.020）

---

## 输出（回传 team-lead）

RoleVerdict：verdict（pass/fail）+ 五闸逐 seed 表 + M1-M7 观测 + ③② 回归确认表 + p̂ 落档 + "① 是否清 EASE wrong 闸"+"M6 闸"+"S2 达标"三判定 + 反作弊门核验
