# R4h ③-A 独立验收 RoleVerdict（qa-r4h2，2026-08-09）

> 验收对象：macro-sim v2.0.38（R4h ③-A：EASE 补写 sentiment +0.08 对称 + a2_action 落盘）
> commit: aa29f6b（+745a701 docs 回填）；CACHE_VERSION=12；ARTIFACT_TAG=v2031；断言 113
> 环境：SSH nas + docker exec macro-sim（f938f4032ba5），前台同步；探针落盘 /tmp/r4h_qa_v2031（**未污染 repo output/**）
> 反作弊：判定只读（--read-only 同源口径）；/app/data 不存在 → 无 v11 缓存可复用；无 skip/.only 新增；断言 113 独立重跑全绿

## RoleVerdict

- **verdict: FAIL**
- 一句话：**③-A 未引入回归（M2/M4/M5/S1/M1/P1 全 PASS），但 M6 残差 +1（18>17 硬闸 FAIL）+ S2 仅 warn 未达 ≤0.60 达标线 + merged p̂ 0.5094 未过 partial 线（0.55）→ 整体未过**
- **p̂ 落档：未过（0.5094 < 0.55 partial 线）**

## 一、五闸逐 seed 表（③-A v2.0.38 vs 基线 v2.0.37）

| seed | silence 基→③ | n_active 基→③ | act 基→③ | consistency 基→③ | weighted 基→③ |
|------|------------|-------------|---------|-----------------|--------------|
| 42 | 0.490→0.490 | 16→16 | 0.327→0.327 | 0.562→**0.500** | 0.456→0.449 |
| 7 | 0.531→0.531 | 14→14 | 0.286→0.286 | 0.714→0.714 | 0.534→0.529 |
| 123 | 0.531→0.531 | 14→14 | 0.286→0.286 | 0.500→0.500 | 0.481→0.467 |
| 2024 | 0.469→0.469 | 17→17 | 0.347→0.347 | 0.471→0.471 | 0.540→0.540 |
| 777 | 0.490→0.490 | 16→16 | 0.327→0.327 | 0.688→0.688 | 0.478→0.486 |
| **median** | **0.490→0.490** | 16→16 | 0.327→0.327 | **0.562→0.500** | 0.481→0.486 |

- **merged p̂=0.5094**（基线 0.5152，**-0.006**）；Wilson CI 下限 **0.4330**（基线 0.4387）；N=161.55（eligible 池=3 变量）
- 闸① silence：seed7/123 = 0.531 > 0.50 → FAIL（**基线既有**，M2 diff=0 非 ③ 回归）
- 闸② CI 0.4330 < 0.55 → FAIL；闸③ p̂ 0.5094 < 0.60 → FAIL；闸④ per-seed weighted 全 <0.50 → FAIL（基线既有：42/123/777 本就 <0.50）
- 闸⑤ 回退线 5 条：credit_consistency **warn**(0.5, target 0.60)｜grv_down **warn**(0.318, target 0.40)｜merged_p **warn**(0.5094, target 0.55)｜credit_n_active **warn**(16, target 18)｜credit_silence **met**(0.4898 ≤0.50)

## 二、硬闸判定（R4h §5）

| 闸 | 口径 | 基线 | ③ 后 | 判定 |
|----|------|------|-------|------|
| **M2** silence diff | 逐 seed Δ | 42:0.490/7:0.531/123:0.531/2024:0.469/777:0.490 | 全 0.000 diff | ✅ **PASS** |
| **M4** flip | EASE 后 2 步内 TIGHTEN（a2_action 决策级） | — | **0（全 seed）** | ✅ **PASS** |
| **M5** credit consistency | median | 0.562 | **0.500**（seed42 0.562→0.500，其余不变） | ✅ **PASS**（≥0.45；seed42 -0.062 观察） |
| **M6** TIGHTEN wrong | 合计（cs<-2.5 ∧ a2_action==TIGHTEN） | 17（4/3/4/5/1，100% 豁免） | **18（5/3/4/5/1）**，100% 豁免 | ❌ **FAIL（18>17，seed42 +1 残差）** |
| **S2** grv_down reverse | median | **0.727** | **0.682**（42:-0.045/7:0/123:0/2024:0/777:-0.013） | ⚠️ **未触发 FAIL（<0.727）但未达 ≤0.60 达标线 → warn 档** |

- S2 逐 seed reverse（consistency_grv_down 口径 1−cons）：42:0.682(cons 0.318)/7:0.591(0.409)/123:0.762(0.238)/2024:0.619(0.381)/777:0.714(0.286)
- **M6 残差明细**：seed42 新增 1 步（i=27/34/36/42/47，全部 vix_stress>1.0 豁免）；其余 seed 与基线逐值一致

## 三、观察项（M1/M3/S1/M7）

| 项 | 基线 | ③ 后 | 结论 |
|----|------|-------|------|
| **M1** EASE wrong（A2 决策级 c/w/n） | 15/9/0（rate 0.625） | **15/9/0（rate median 0.714）** | ✅ 持平（wrong=9 不变） |
| **M3** rate_limit 双口径（credit S 类） | 0.417-0.692 | 42:0.5/7:0.692/123:0.692/2024:0.652/777:0.417 | 区间内；seed42 act_gate 0.375→0.5（见 P2） |
| **S1** sentiment 桶（主探针） | floor_frac 0.694 / mean -0.880 / clamp 0.388-0.653 | floor_frac **0.66** / mean **-0.859** / clamp 0.571 / n_active **43**(16→) / act 0.878 / silence 0.02 | 抬离 floor 但**幅度小**；**无 ≥0.5 尖峰**（max<0.22） |
| **M7** A1/A3 分布 | A1 CUT 6-7 步、A3 INC/SHORT 均衡 | A1 CUT 5-6 步、A3 分布同基线 | ✅ 无实质变化（A1 HIKE 仍 ≤1 步） |
| **M7** vix 存量 | vix_stress>1.0 23-38 步、峰值 162-238 | 23-38 步、峰值 162-238、**vix_last=vix_max（无 decay）** | ⚠️ 存量不回吐确认（② 部分收敛证据） |

## 四、③ 专项 3 项（② 裁决输入）

1. **① M6 残差 = 18 > 17 → ② 仍需裁决**（③ 未完全收敛 vix 豁免问题：seed42 新增 1 步 wrong 且 100% 豁免）。按简报"残差 ≤17 → ② 可轻量或不做；>17 → ② 候选三选一单独裁决"——**本残差指向 ② 候选仍需要（vix decay / 豁免非连续前提 / bleed 上限 三选一）**
2. **② M2 silence diff = 全 0.000 → PASS**（豁免未关闭重演 R4d 沉默的担忧解除；③ 未恶化 credit 沉默）
3. **③ S1 sentiment 桶**：抬离 floor 但幅度微弱（floor_frac -0.034、mean +0.021、n_active 16→43 S→T 转移成功）；**主探针无 ≥0.5 尖峰**（42:0.049/7:-0.137/123:0.218/2024:0.023/777:0.042，ge05=0）→ ✅ 方向正确无过冲。⚠️ ease 子探针（合成宽松场景，非验收口径）seed7 max=0.995/ge05=40——合成场景极端，非真实数据路径

## 五、前置检查（P1-P4）

- **P1 a2_acted**：✅ 机读交叉表（5 seed）：HOLD→rate_limit/activation_gate/tighten_signal_false，**HOLD 从不归 acted_other**；tsf 非零（2/4/3/4/5）；人工抽步 6 步核对通过（HOLD/EASE/TIGHTEN 各 2 步，a2_action 与 a2_state 语义一致）
- **P2 归因双报**：S 类口径（acceptance s_class_table）+ 完整 steps 口径（a2_state_dist）双表已核。**seed42 归因微变**（act_gate 0.375→0.5、rate_limit 0.625→0.5；完整 steps act_gate 13→15/rate_limit 18→17/acted_other 16→15），其余 seed 与基线逐值一致（7/123/2024/777 完全不变）
- **P3 反作弊**：✅ --read-only 同源判定；CACHE_VERSION=12 容器 grep 生效；/app/data 不存在无 v11 缓存；断言 113 独立重跑全绿（guards 24 组/101 assert + narrative 11 组/12 assert）；无 skip/.only 新增；output/ 无 v2031 落盘
- **P4 v2031 落盘**：✅ /tmp/r4h_qa_v2031/calib_probe_seed{seed}_v2031.json 5 个 + acceptance_v2031.json（VERDICT:FAIL 同源）；确定性验证：seed42 weighted=0.448629 与 arch 探针 0.4486 完全一致

## 六、arch 改动核验（git show aa29f6b 逐行，trust but verify）

- ✅ simulation.py L148-152 EASE 分支补写 `add("A2","market_sentiment",0.08*m)`——与 TIGHTEN L141 `-0.08*m` **完全镜像**（K=1.0，±0.08×m）
- ✅ calibrator.py L735 step_record 加 `"a2_action": snapshot.get("actions",{}).get("A2","HOLD")`——纯测量层（只读 snapshot），不污染行为
- ✅ CACHE_VERSION 11→12（L131），bump 理由充分（引擎动力学变更防 <7 天命中 v11 缓存自证）
- ✅ VERSION 文件 v2.0.37→v2.0.38；ARTIFACT_TAG v2030c→v2031（L69）+ acceptance_v2031.json
- ✅ tests +42 新增 3 项（writes_sentiment/symmetry/t_class）均实质断言（非空/非硬编码/非 skip），assert 计数 101+12=113 与声明一致
- ✅ financial.py L90 仅注释更新（无行为改动）；8 文件 +144/-8 与声明一致

## 七、特别标注（③ 核心目标）

1. **S2 reverse 是否达标**：**未达 ≤0.60 达标线（median 0.682，warn 档）**。③ 核心目标"grv_down reverse ≤0.60"未达成——改善幅度 -0.045 远小于 arch 预估（0.52-0.62）。根因：EASE 步数太少（median 4 步/seed，每步 +0.0275 传导）不足以把 sentiment 抬离 floor 到改变 grv_down 方向一致率的程度；seed42/777 有改善（-0.045/-0.013），seed7/123/2024 完全不变
2. **M6 残差**：18 > 17 → **② 裁决输入：③ 未完全收敛，vix 豁免问题仍存在**（seed42 新增 1 步 TIGHTEN wrong 且 100% vix_stress>1.0 豁免）——M6 天然成为 ② 必要性证据（未达"残差 ≤17 → ② 轻量或不做"的豁免条件）
3. **M2 silence 是否超线**：**未超线（全 0.000 diff）**——方向闸/豁免问题未重演 R4d 沉默回归

## 八、advisory（供 team-lead 裁决）

- [1] **③-A 结构性效果确认但强度不足**：S→T 转移成功（sentiment n_active 16→43、act 0.878、silence 0.02），但 floor 抬离微弱（floor_frac 仅 -0.034）→ S2 未达达标线。EASE 写者频率（4 步/seed）是瓶颈，非幅度 K
- [2] **p̂ 0.5152→0.5094 下降的结构解释**：sentiment 活性提升使低一致率 sentiment 样本（consistency 0.44-0.63，seed42 0.442）大量入 eligible 池 → merged p̂ 结构性稀释。**非 ③ 引入的行为回归，是测量口径结构性变化**（与简报 §3 "S→T 转移 → merged p̂ 结构变化"预期一致）
- [3] **seed42 consistency 0.562→0.500（-0.062）**：唯一受 ③ 影响的 credit 一致率下降（M5 仍 PASS）。归因 act_gate 0.375→0.5 同步变化——sentiment 抬升改变了 A2 决策上下文，seed42 特有
- [4] **ease 子探针 seed7 尖峰 0.995**（合成宽松场景）：非真实数据路径，不构成 ③ 过冲证据；但 ② 若引入 vix decay 需复核 ease 场景交互
- [5] **CACHE/工件洁净**：全程未写 repo output/（v2031 工件在 /tmp/r4h_qa_v2031）；断言独立重跑在本地 repo（容器为生产镜像无 pytest/tests）——与 arch 声明（113 全绿）一致

## 九、evidence

- 容器：/tmp/r4h_qa_v2031/{calib_probe_seed{42,7,123,2024,777}_v2031.json, acceptance_v2031.json}；/tmp/r4h_qa_result.txt；/tmp/r4h_qa_sent2_result.json；/tmp/r4h_qa_analyze.py
- 本地：C:\tmp\r4h_data\R4H_QA验收清单.md（本文件同目录）；C:\tmp\r4h_data\R4H_QA_RoleVerdict_③A.md
- 基线对照：C:\tmp\r4h_data\R4H_基线快照.md（data-r4h v2.0.37）；r4h_sent_detail.json（data 模拟预测）
- 代码核验：git show aa29f6b（simulation.py/calibrator.py/run_probe_acceptance.py/tests/VERSION）
