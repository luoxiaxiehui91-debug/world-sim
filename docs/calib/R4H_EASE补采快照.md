# R4h 统一口径 EASE 方向补采快照（data-r4h，2026-08-09）

## RoleVerdict（qa-r4g 补采请求）
- verdict: **PASS**（统一口径补采完成：EASE c/w/n = 15/9/0，rate_cw 0.625，与 qa 预期完全一致；TIGHTEN c/w/n = 21/17/15，rate_cw 0.553 一并交付）
- advisory: arch 尚未落盘 step_record.a2_action（容器内 calibrator.py grep 无此字段）；本补采用 monkeypatch 捕获 snapshot["actions"]["A2"]（= 决策级 action，与落盘字段等价），arch 落盘后可用 step_record.a2_action 复核（预期数值不变）
- evidence: 容器内 /tmp/r4h_ease_unified.json（md5 58caff7e…，含逐步 EASE 决策明细）；本地 C:\tmp\r4h_data\r4h_ease_unified.json

---

## 统一口径（qa-r4g 定稿，方向规则已固化 docs/r4h-acceptance-criteria.md §M1/§8）
- EASE = a2_action == "EASE_CREDIT"（A2 决策级，snapshot["actions"]["A2"]，非 net d<0）
- **方向 = 动作相关规则（务必区分动作，避免用错）**：
  - EASE 的 correct = t<0、wrong = t>0
  - TIGHTEN 的 correct = t>0、wrong = t<0
  - 即「EASE c=t<0 / TIGHTEN c=t>0」——若把 EASE 规则误用到 TIGHTEN，c/w 会对调（17/21）
- 方向判据 = 内生 target t 符号（per_var bank_credit_tightening.t）：correct/wrong 按上规则；neutral = |t|<EPS_TGT(0.03)，neutral 不计 rate
- 验证：credit_t vs cs_delta 62/62 同号（方向判据无歧义，qa 已确认）
- 范围：主探针 49 条 delta 步（i=1..49，对齐 main_cap[j+1]）
- **③ 后对比：按上述「EASE c=t<0 / TIGHTEN c=t>0」同一规则出数，保证同口径**

## 逐 seed 结果

| seed | EASE c/w/n | EASE rate_cw | TIGHTEN c/w/n | TIGHTEN rate_cw |
|------|------------|--------------|----------------|-----------------|
| 42   | 2/2/0      | 0.500        | 4/4/4          | 0.500           |
| 7    | 3/1/0      | 0.750        | 5/3/3          | 0.625           |
| 123  | 2/3/0      | 0.400        | 4/4/5          | 0.500           |
| 2024 | 3/1/0      | 0.750        | 4/5/3          | 0.444           |
| 777  | 5/2/0      | 0.714        | 4/1/0          | 0.800           |
| **合计** | **15/9/0** | **0.625** | **21/17/15** | **0.553** |

- EASE 决策总步数 n_ease=24；全部落在 |cs_delta|>2.5 方向区（无 neutral）
- EASE 逐步明细（审计用）：seed42 i=6/11 correct、i=13/15 wrong；seed7 i=9/11/16 correct、i=13 wrong；seed123 i=6/12 correct、i=8/10/15 wrong；seed2024 i=9/11/16 correct、i=13 wrong；seed777 i=6/12/14/17/26 correct、i=8/10 wrong

## vix 口径复用（② 前后对比）
- 容器探针已落盘每步决策时 vix_stress（step_record.vix_stress，主探针窗口）
- TIGHTEN wrong（cs_delta<-2.5 ∧ A2==TIGHTEN）= 4/3/4/5/1 = **17 步，100% 因 vix_stress>1.0 豁免放行**（M6 硬闸基线，qa 已确认）
- vix_stress>1.0 步数：25/38/23/24/23（median 24）——可直接复用做 ② 前后对比

## 复核状态（qa-r4g，2026-08-09）
- **qa 独立复核通过**：EASE 15/9/0 rate 0.625 ✅、TIGHTEN 21/17/15 rate 0.553 ✅（逐 seed 全吻合，证据 md5 一致）
- credit_t vs cs_delta 62/62 同号 ✅（方向判据无歧义）
- M6 17 步/100% 豁免 + vix>1.0 median 24 ✅（qa 已从 R4e 工件独立复算一致）
- 此基线已锁定为 ③ 前基线（docs/r4h-acceptance-criteria.md §M1/§8）

## 交付文件
- 容器内：/tmp/r4h_ease_unified.json（per_seed_rows 全量，含逐步 a2/credit_t/cs_delta）
- 本地：C:\tmp\r4h_data\r4h_ease_unified.json、C:\tmp\r4h_data\r4h_ease_unified.py（补采脚本）
