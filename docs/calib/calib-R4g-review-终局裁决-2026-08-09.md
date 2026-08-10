# 校准引擎 R4g 评审终局裁决

> 日期：2026-08-09
> 评审团：arch-r4g（架构）/ qa-r4g（测试）/ data-r4g（数据）三方独立评审 + 阶段一归因修正 + 阶段二实施证伪 + 收尾 revert
> 评审对象：天璇 macro-sim 校准引擎 A2 商业银行行为（EPS 校准，一致率评分体系）
> 评审议题：R4g 归因可验证性修正（阶段一）+ 冷却修复实证（阶段二）
> 上游：R4f 终局裁决（三案否决，转 R4g 结构性修 silence，第一嫌疑=2 步冷却）
> 状态：**归因修正成立（净成果）· 冷却修复证伪并回滚（v2.0.37）· R4h 立项结构性方案**

---

## 0. 一句话裁决

**R4g 阶段一归因修正成立：R4f 的 rate_limit 主导归因是 S 类子集口径伪影（高估 +0.264），且 rule_hold 字段根本不存在、tighten_signal_false 是 classify 死代码——修正后真实归因=激活机制（冷却+概率）占 S 类 92%。阶段二按此实施冷却修复（HOLD 不锁步 + EASE 冷却 2→1）被实证证伪：silence 只是转移未消除（超线 seed 从 7/123 换成 42/2024）、consistency 降（0.5625→0.500）、p̂ 微降（0.5152→0.5115）、flip-flop 实证出现——「放宽换活性损质量」二次重演。引擎实验已回滚（v2.0.37），保留归因映射修复（纯测量层）。R4g 无过闸方案，产出=归因修正 + 映射修复 + R4h 结构性方案设计输入。**

---

## 1. 阶段一：归因可验证性修正（净成果，三方交叉验证一致）

### 1.1 R4f 归因三大伪影实锤（qa + arch + data 三方独立确认）

| 伪影 | 证据 | 修正 |
|------|------|------|
| **rate_limit 高估 +0.264** | S 类口径 0.652 vs 完整 steps 口径 0.388（data 复算）——R4f 的 62.5-69.2% 是 S 类子集占比，非全步占比 | 口径双报：S 类 + 完整 steps |
| **rule_hold 字段不存在** | arch 全库 grep 0 命中；落盘 step_record 只有 a2_state 三分类 + acted_other（calibrator.py L723-731）——R4f 终裁"rule_hold 主导→升级"的收敛判据基于幻影字段 | 按 a2_state 实际字段读取 |
| **tighten_signal_false 死代码** | simulation.py L521 actions 只滤 NO_ACTION 保留 HOLD → calibrator.py L698-700 a2_acted=bool(actions["A2"]) 对 HOLD 判 True → classify 顺序永远先命中 acted_other，tighten_signal_false 分支结构性不可达（5 seed 恒 0.0 的原因，非"方向闸零贡献"） | a2_acted 排除 HOLD（calibrator.py:704 修复） |

### 1.2 修正后真实归因（credit S 类，合并 5 seed，N=123）

| 归因 | 占比 | 结论 |
|------|------|------|
| rate_limit（激活冷却 activation_countdown） | 61.8%（76 步） | **主因** |
| activation_gate（随机门 activation_prob=0.70） | 30.1%（37 步） | 次因 |
| rule_hold（规则层 HOLD：方向闸/grv 高压/ease 条件） | 8.1%（10 步） | 非主因 |
| tighten_signal_false | 恒 0.0（死代码） | 修正后暴露 |

- **激活机制（冷却+概率）占 92%，方向闸/规则层仅 8%**——与 R4f"方向闸代价"假设相反
- rule_hold 细分：grv≥0.6 双锁死 6 步（dominant）、tightening_ge_05 挡 EASE 1 步、_ease_cooldown 1 步、异常 HOLD 2 步（待 arch 复核，占比 1.6% 不改变主结论）
- EASE wrong 9 步全部在 cs_delta>0（target_dir=tighten）时被普通 ease_signal 触发——方向闸盲区（只挡"cs 回落时收紧"不挡"cs 上升时放松"）
- TIGHTEN wrong 17 步全部 vix_stress>1.0（危机豁免常态化放行，vix bleed 漂移可达 6.83）
- R4d 豁免交互：豁免（vix>1.0）与挡死（vix≤1.0）两组落到冷却/激活门的比例几乎相同（68.3% vs 66.7%）→ **R4d 收窄豁免没有显著增加冷却负担**

### 1.3 结构性上限（决定修复空间）

- act≈p/(2-p+d·p)=0.70/(2-0.70+0.70)=**0.35**（p=1 时 0.5）——与实测 credit act_frac 0.327 吻合
- credit per-seed n_active 全 seed <20（16/14/14/17/16）→ 闸④下 credit 全 seed 不入池，per-seed weighted 实际只含 sentiment+lp
- **信息：仅 EASE 冷却 2→1 无法抬 n_active≥20，须动 info_delay 或 activation（触碰 test_a2_info_delay_r4b，规格变更）**

---

## 2. 阶段二：冷却修复实施与证伪（v2.0.36，已回滚）

### 2.1 实施内容（commit e1d1832，arch 交付，qa 独立核验）

| # | 改动 | 位置 | 预期 |
|---|------|------|------|
| ① | 归因映射修复：a2_acted 排除 HOLD | calibrator.py:704 | tighten_signal_false 恒 0 → ≈8% |
| ② | activation_countdown 条件化：HOLD 不锁步 | simulation.py:492-494 | rate_limit 下降（直击 61.8% 主因） |
| ③ | EASE 冷却 2→1 | financial.py:111 | TIGHTEN 挡期缩短 1 步 |
| ④ | CACHE_VERSION 10→11 / VERSION v2.0.36 | calibrator.py:126-128 | 缓存失效防自证 |

测试同步：断言 102 → 110（+8 新增，禁 skip/.only），重验分支测试全绿。

### 2.2 验收 FAIL（qa 独立验收 + data 复算一致，硬 FAIL 闸①）

| seed | n_active | act | silence(≤0.50) | consistency |
|------|----------|-----|----------------|-------------|
| 42 | 16→13↓ | 0.33→0.27 | 0.49→**0.551 FAIL** | 0.562→0.692 |
| 7 | 14→21↑ | 0.29→0.43 | 0.531→0.388 ✓ | 0.714→**0.429** |
| 123 | 14→16 | 0.29→0.33 | 0.531→0.49 ✓ | 0.500→0.438 |
| 2024 | 17→14↓ | 0.35→0.29 | 0.469→**0.531 FAIL** | 0.471→0.500 |
| 777 | 16→16 | 0.33→0.33 | 0.49→0.49 ✓ | 0.688→0.688 |
| **merged** | **median 16→16** | **0.327→0.327** | **median 0.49→0.49** | **0.5625→0.500** |

- p̂：0.5152 → **0.5115（降）**；CI 下限：0.4387 → **0.4344（降）**
- **silence 超线只是转移未消除**：修好 7/123，爆 42/2024（0.551/0.531）——fail-fast 闸①依旧 FAIL
- **「放宽换活性损质量」二次重演**（R4e：grv 放宽 consistency 0.643→0.562；R4g：冷却放宽 consistency 0.5625→0.500）
- **flip-flop 实证出现**（M4）：EASE 后 1 步内 TIGHTEN 相邻振荡 2-4 次/seed（R4e 时 EASE 后 2 步挡 TIGHTEN 不会出现）——EASE 冷却 2→1 的直接代价
- 改动①验证成功：tighten_signal_false 从恒 0 → 完整口径 0.041-0.163（median 0.082），S 类 0.105-0.296（median 0.154）——HOLD 映射 bug 实锤且修复

### 2.3 证伪结论

**「改冷却解 silence」假设被证伪**：冷却修复只转移 silence 未消除（激活机制 91.9%→82.5%，仍主因），且引入 flip-flop + consistency 下滑，触发「放宽换活性损质量」红牌。下一轮修激活机制边际收益递减（seed42/2024 恶化证明单纯放激活会引入更多规则层 HOLD 与反向 TIGHTEN）。修正归因显示完整口径 rule_hold 0.041-0.163 高于阶段一估计，ease-block 显示 tightening_ge_05 挡 EASE 是部分 seed 主因（seed42 0.773）、方向闸 tighten_fail 上升（seed7 3→7）——**证据指向"方向闸+规则层挡 EASE"与冷却的联合作用，非纯冷却**。

---

## 3. 收尾（用户裁决，v2.0.37）

**裁决：revert ②③（引擎实验），保留①（归因映射修复）。**

| 项目 | 内容 |
|------|------|
| commit | 8180a8a（revert 引擎实验，3 files +3/-11）；173d6ac（规格变更登记追加变更5）；b93e24f（R4h 设计初稿） |
| 版本 | v2.0.37（只前进不后退；语义=引擎行为回 R4e 基线 + 测量层修复） |
| revert 验证 | silence/n_active/act_frac/consistency/weighted 逐 seed 与 R4e 基线**逐位一致**（qa 抽查 seed7/2024 独立确认）；tighten_signal_false 保持非零（seed7 0.038/123 0.115/2024 0.13/777 0.125）——"引擎回滚但测量修复保留"直接证据 |
| 断言 | 110 条全绿（+8 为 calibrator 侧语义锁定，与回滚无关） |
| 反作弊 | 断言数不降、禁 skip/.only、CACHE_VERSION 11、--read-only、禁 calibration_cache 自证——全绿 |
| 待办 | ARTIFACT_TAG 未 bump（v2030c 复用），R4e 工件已备份 output/r4e_backup_v2030c/，后续 R 轮次 bump tag 防 era 混淆 |

---

## 4. R4g 产出

1. **归因修正成立**（净成果）：R4f 归因伪影实锤（rate_limit 高估 +0.264 / rule_hold 幻影字段 / tighten_signal_false 死代码），修正后真实归因=激活机制 92%（冷却 61.8% + 概率 30.1%），规则层 8.1%
2. **归因映射修复保留**（纯测量层，零引擎副作用）：calibrator.py:704，独立验收成功（tighten_signal_false 可测）
3. **冷却修复证伪并回滚**（科学结论）：改冷却只转移 silence、降 quality，非解药——避免继续在错误方向浪费轮次
4. **R4h 结构性方案设计输入**（docs/r4h-design-draft.md，commit b93e24f）

---

## 5. R4h 立项建议（结构性方案，参数留裁决）

**裁决顺序：③→②→①（根因链上游先行）**

| # | 方案 | 机制 | 预期 | 风险 |
|---|------|------|------|------|
| ③ | sentiment 写者结构 | A2 EASE 只写 credit/lp 不写 sentiment（simulation.py:145-147），TIGHTEN 却写 -0.08 → 负写者主导 → grv_down reverse 0.685；补写正向分量（幅度留裁决，需对称 TIGHTEN -0.08 或按宽松乘数） | sentiment 回升 → vix bleed 停 → ②自然收敛 | 需与②联动，防 sentiment 过冲 |
| ② | 危机豁免 vix>1.0 常态化治理 | tighten_ok 豁免被 vix bleed 自激放大（sentiment 低→vix +2/步→豁免恒真→错误收紧→sentiment 更低）；治理=收紧触发前提/限 bleed/非连续性条件 | TIGHTEN wrong 26 步收敛 | R4d 回退预案失效→silence 超线，需与③联动 |
| ① | 方向闸补挡"cs 上升时放松" | financial.py ease_signal 处补 ease_ok 镜像闸（与 tighten_ok 对称） | EASE wrong 6→0 | 过度挡 EASE→n_active 降→silence 复发（R4d 前史） |

每项均需：bump CACHE_VERSION + 同步断言 + 5 seed 独立验收 + 归因前后对比。评审期 weighted 0.60 冻结、裁决机读落盘、不得调门槛。

---

## 6. 变更记录

| 日期 | 变更 | 原因 | 影响 |
|------|------|------|------|
| 2026-08-09 | R4g 阶段一归因修正 | R4f 归因伪影实锤 | 归因框架修正 |
| 2026-08-09 | R4g 阶段二 v2.0.36 实施 | 冷却修复假设 | 验收 FAIL |
| 2026-08-09 | R4g 收尾 v2.0.37 revert ②③保留① | 用户裁决 + 证伪证据 | 引擎回 R4e 基线 |
| 2026-08-09 | R4h 立项（③→②→①） | 结构性方案 | 待裁决参数 |
