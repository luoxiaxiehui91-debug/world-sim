# OPEN-DECISIONS — 天璇未决项登记册

> 规范：只追加 + 就地关闭（OPEN → RESOLVED 补 Resolution）。每次 Phase 开始把未决项复现到工作上下文最前面。

| Date | Source | Open Item | Related Constraints | Current Leaning | Blocked By | Resolves When | Status |
|------|--------|-----------|---------------------|-----------------|------------|---------------|--------|
| 2026-08-08 | 探针（v2.0.28 C1-1a/C3-3a 50步标定探针） | liquidity_premium 死变量：m_v=0.0（50步 median\|delta\|=0），active_rate=0.327，探针标记 dead=True | C1-1a 探针机制：m_v<δ_min(0.002) → 死变量走 C3 不标定；但 C3-3a 刚移除 outflow，liquidity 又死，需判定是引擎无驱动还是clamp/scale 压制 | 倾向：先查引擎驱动链（A2/A3/A5/A10/A11/A12 对 liquidity 的写 + natural_decay ×0.93 是否把 delta 压到 <0.005），再决定走 C3 移除还是放大驱动 | 需人工复核引擎 liquidity 驱动链 | 引擎驱动链复核后 | OPEN |
| 2026-08-08 | arch-review R4 | clamp 对称化连带 c)（阻尼锁区 \|level\|>0.7 重标）核实：三个核心文件无独立阻尼锁区检测，仅有 world_state.py:259 yen_carry_bleed_threshold=0.7（出血规则非锁区）——连带 c 实际不适用 | 评审基于假设，代码核实推翻 | 不实施连带 c | 无 | 已核实 | RESOLVED（不适用） |
| 2026-08-08 | 探针（v2.0.28 50步） | 一致率全部 <60%（sentiment 0.44/credit 0.48/liquidity 0.50）→ 决策树指向禁动 compute_error 查假收敛/阻尼，而非调权重 | data R4 决策树：新一致率也<60% → 禁动 compute_error | 下一步按决策树查假收敛/阻尼（可能 clamp 对称化后 GM 负向写入生效改变行为） | 需人工跑诊断对比 | 查假收敛/阻尼后 | OPEN |
