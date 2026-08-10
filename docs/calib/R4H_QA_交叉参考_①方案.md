# R4h ① 方案交叉参考意见（qa-r4h2，2026-08-09）

> 对象：C:\tmp\r4h_data2\R4h_①_方案设计.md（arch-r4h2）
> 性质：方案审阅（可证伪性裁决 + 是否建议放行实施），非正式验收（部署后执行）
> 基线：v2.0.39（② 终版）；对照：C:\tmp\r4h_data\R4H_QA验收清单_①②③.md
>
> ⚠ **假复现更正（2026-08-10）**：本文多处数字（p̂ 0.5709 / CI 0.4864 / S2 0.632 / M6 14 / act_prob 0.78 / cap18+0.80 等）基于 arch 本地实测（A3 soul 缺失环境：config 放 /tmp → load_agents soul 路径 dirname(config)/../souls 解析失败 → A3 soul={} 回退旧决策），容器真实部署不可复现。权威结论见 C:\tmp\r4h_data2\R4h_Part4_前后对比.md §5。**容器实测（v2.0.40/CACHE 14/v2033）：EASE correct 16 / M6 13 / silence 4/5 超（median 0.531，seed123 0.633 最差）/ credit 未回池 / p̂ 0.4894（CI 0.4063）/ S2 0.636 / consistency 0.750。** 且 p̂ 的 0.5709（本文）与 0.5729（验收清单/Runbook）互斥 = 假复现自证。

---

## 一、可证伪性裁决（team-lead 点 1）

### ease_ok 守卫可证伪性：✅ 可证伪

`ease_ok = (target_dir != "tighten") or vix_stress > p.threshold * 2.0`

单测可锁 3 态：
1. cs_delta>+2.5（target_dir=="tighten"）∧ vix_stress 低 → ease_signal=False（EASE 被挡）
2. cs_delta>+2.5 ∧ vix_stress>threshold*2.0 → ease_ok=True（极端豁免对称成立，放行）
3. cs_delta≤+2.5（target_dir!="tighten"）→ ease_ok=True（正常 EASE 不受影响）

arch 承诺 ≥4 项单测（ease_ok 方向闸 2 + act_prob/cap 组合回归 1 + M4 保持 1）——按承诺核验。

### wrong 步转 HOLD 还是 TIGHTEN：转 HOLD（合理，非伪治理）

- arch 解释成立：EASE wrong 步在 EASE 冷却期内（7/8 步前两步是 EASE_CREDIT），TIGHTEN 被冷却挡（防 flip-flop，M4 硬闸 0）→ ease_ok 挡后自然转 HOLD（冷却递减）
- **关键推论**：wrong 8 步转 HOLD → EASE 决策步数减少（total 23→15），EASE correct 15 必须保持不降
- **防伪治理核验线**：EASE correct ≥15（不降）∧ EASE wrong ==0 → ①-A 真治理（决策质量提升）；若 correct 降 → "一刀切禁 EASE"伪治理 FAIL

### 两线冲突（silence 升）是否被 act_prob 0.78 充分补偿：✅ 可证伪，实测净抵消——⚠ 0.78 为扫描中间值，最终定稿 0.76

- ease_ok 挡 8 步转 HOLD → S 类 +8（silence 升压力）；act_prob 0.78 → activation_gate S 类降（seed42 12→7）→ silence 0.510→0.490——⚠ 基于假复现；容器实测 silence 4/5 超（median 0.531），未出现净抵消
- **注意**：+8 vs -5 数值上不完全对等，净 silence 降说明 act_prob 的激活补偿 > ease_ok 的 S 类新增（部分被挡步本来在行动态，转 HOLD 的沉默增量被 act_prob 释放的步抵消）
- 可证伪：部署后实测 activation_gate 占比下降 + silence median ≤0.50（4/5）→ 补偿充分——⚠ 容器实测未满足（4/5 超）

## 二、silence 传导路径预期（team-lead 点 2）

### arch 给了可证伪预期：✅ 满足我要求——⚠ 预期值基于假复现，容器实测未满足

- arch §3.3 明确预期：③-A 2/5 超 → ② 4/5 超 → **① 1/5 超（seed7 0.510）**——满足我的判据"≤2/5 或全过"——⚠ 容器实测 **① 后 4/5 超**（median 0.531，seed123 0.633 最差），预期未兑现

### seed7 0.510 超 0.01 裁决：**边界噪声豁免（有条件）**——⚠ 容器实测超出豁免条件

- 依据：扫描 5 组合（act_prob 0.75-0.80）下超线 seed 在 42/7/777 间漂移（±1 S 类步 = ±0.02）；0.510 vs 0.50 差 0.01 在噪声带内；追求 5 seed 全过会牺牲 M6（cap18+0.80 → wrong 19 FAIL，无全绿解）——⚠ cap18+0.80 为已弃扫描组合（容器实测 0.80 时 M6 20 更差）
- **有条件豁免**：部署后实测 seed7 silence 若 ≤0.52（超线 ≤0.02，噪声带内）→ 豁免；若 >0.52（超噪声带）→ 升级 P1 需 arch 解释——⚠ 容器实测 4/5 超、seed123 达 0.633，远超噪声带 → 升级 P1，silence 治理挂起
- 严格 FAIL 的代价：拒绝 ① = 回到 ②（4/5 超线更差）——无全绿解下 ① 的 1/5 超是 Pareto 最优——⚠ 容器实测 ① 与 ② 同为 4/5 超，该 Pareto 假设未成立

## 三、EASE wrong 承诺目标（team-lead 点 3）

- arch 承诺 8→0（全消失），强于我判据 ≤4/rate≥0.75——**按承诺核验**（部署后 EASE wrong ==0 全 seed）
- **加防伪核验**：EASE correct ≥15 不降 + rate = correct/(correct+wrong)（wrong=0 → rate 1.0 ≥0.75）
- 测量口径陷阱警示：EASE wrong 0 必须伴随 correct 保持，否则是"减少 EASE 决策"而非"消除错误决策"

## 四、M6 余量（team-lead 点 4）

### 余量 3 偏薄（14 vs 17），风险可控但需实测确认——⚠ "14" 为假复现，容器实测 M6 13

- act_prob 0.78 提高行动概率 → TIGHTEN 步可能增多 → wrong（cs<-2.5 时 TIGHTEN）可能增——⚠ 0.78 为扫描中间值，最终定稿 0.76
- cap 17 对冲：vix 峰值 53.3→51.3 → vix_stress>1.0 豁免窗口更窄 → wrong 步更少
- arch 实测 wrong 16→14（cap 17 的 wrong 减少 > act_prob 的 wrong 增加）——**但这是本地实测（假复现）**；容器实测 M6 **13**（≤17 达标）
- **独立判断**：部署后 wrong 若在 14±2（12-16）→ 达标；若 >17 → ① FAIL（cap 17 未达预期，单行回退 19）——⚠ 容器实测 **13** 落达标区间；假复现的 12/14 互斥
- 裁决闸严格执行 ≤17，不因"余量 3"放松

## 五、p̂ 口径统计裁决（team-lead 点 5）

### 裁决：**按 p̂ partial 点估验收（0.5709 过 0.55）+ CI 0.4864 作 advisory 观察项**——⚠ 已撤销，容器实测 p̂ 0.4894 未过 0.55

理由（⚠ 以下基于假复现工件，容器实测全部不成立）：
1. **partial 线设计为点估**（≥0.616 accept / ≥0.55 partial / <0.55 未过）——0.5709 落 partial 档——⚠ 容器实测 0.4894 <0.55，未过
2. **CI 未过是结构性非 ① 范围**：sentiment consistency 0.53 + lp 0.42 拖累（③/S2 后续工作），与 data Part 1 预测一致（CI 下限不可达，最高 0.4995）
3. **credit 回池恢复测量完整性**：eligible 池 3→2→3（① 修复 ② 的 credit 出池问题），N 恢复 → p̂ 比较口径一致——⚠ 容器实测 credit 未回池（2 变量），该项不成立
4. **与 ② 验收的本质区别**：② 时 p̂ 0.4948 <0.55 且 CI 0.4118 <0.55（双 FAIL）——② 未过 p̂ 点估；① 后 0.5709 已过点估线，仅 CI 未过（统计不确定性）——⚠ 容器实测 ① 后 p̂ 0.4894，与 ② 同为未过，无本质区别
5. 严格 CI 验收 = ① 永远不可达（需 sentiment/lp 提升，超出 ① 范围）——无意义

**须 advisory 标注**：p̂ 0.5709 点估 partial 达成，CI 0.4864 未过 0.55（95% 置信无法排除 <0.55）——记录为"partial 达成（点估）"，**不记 accept（0.616 未达）**——⚠ **撤销**：容器实测 p̂ **0.4894** / CI **0.4063**，未过 0.55，不记 partial/accept。0.5709（本文）与 0.5729（验收清单/Runbook）互斥 = 假复现自证。

---

## 六、综合裁决：**建议放行实施（有条件）**——⚠ 基于假复现数据，已按容器实测更正：收编 EASE wrong 治理，credit 回池/p̂/S2 不通过（见 R4h_Part4_前后对比.md §5）

### blocking（放行前提，部署后验收必须核）
1. **EASE wrong ==0 且 EASE correct ≥15 不降**（防伪治理核验，①-A 核心）——容器实测 correct 16、wrong 0 ✅
2. **M6 wrong ≤17**（余量 3 偏薄，部署后实测 14±2 达标；>17 → ① FAIL 回退 cap 19）——容器实测 M6 **13** ✅；假复现 14±2 已失效
3. **绝对 silence ≤2/5 超线**（arch 预期 1/5；seed7 ≤0.52 边界豁免，>0.52 升级 P1）——容器实测 **4/5 超**（median 0.531，seed123 0.633）❌ 未达，升级 P1，silence 治理挂起
4. **M4 flip ==0**（ease_ok 挡 EASE 后转 HOLD 不得引入 EASE→TIGHTEN 2 步内 flip）——容器验证 flip=0 ✅
5. **② P2 修复确认**：CACHE 注释参数更新为最终值（0.80/0.20 + cap17 + ease_ok + act_prob **0.76**）、registry 变更 8 回填 commit message 数字——⚠ 0.78 为扫描中间值，最终定稿 0.76

### advisory（放行但标注）——⚠ 数字基于假复现，已行内更正
1. **p̂ 0.5709 partial 点估达成 + CI 0.4864 未过**——⚠ 撤销：容器实测 p̂ **0.4894** / CI **0.4063**，未过 0.55，p̂ 项不通过
2. **seed7 silence 0.510 边界噪声豁免**（±0.01 噪声带，1/5 超线是最大改善）——⚠ 容器实测 4/5 超，豁免不成立
3. **weighted seed123 0.476 <0.50**（闸④ FAIL，基线既有非 ① 引入）
4. **M6 余量 3 偏薄**——cap 17 为 Pareto 最优点，后续若动 act_prob 需重新扫描
5. ③ 交互：ease_ok 挡 8 步的 sentiment +0.08 正写消失（错误方向正写，挡掉合理，S2 0.682→0.632 改善佐证）——⚠ 容器实测 S2 **0.636**（warn 档，未达 ≤0.60）

### 需 arch 澄清 1 点（部署前）
ease_ok=False 后被挡步的精确分支：确认转 HOLD（冷却递减）而非其他路径——部署后单测 M4 保持 + 抽步人工核对（我验收时做）

---

## 七、evidence

- arch 方案：C:\tmp\r4h_data2\R4h_①_方案设计.md
- 本意见：C:\tmp\r4h_data\R4H_QA_交叉参考_①方案.md
- 验收判据：C:\tmp\r4h_data\R4H_QA验收清单_①②③.md
- ② 终版：C:\tmp\r4h_data\R4H_QA_RoleVerdict_②A.md
