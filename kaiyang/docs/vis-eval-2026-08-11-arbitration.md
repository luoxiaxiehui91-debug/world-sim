# 开阳视觉评估 · 仲裁决策（2026-08-11 10:30）

> 主理人（lead）仲裁记录。背景：两名评估 worker 并行产出两份报告，且 vis-fe-2 将报告写入同一路径覆盖了 vis-fe 版本（原版全文已在 lead 上下文留档）。本文件 = 最终执行依据。

## 1. 两份报告收敛结论（互证，采信）

| # | 结论 | vis-fe | vis-fe-2 | 证据 |
|---|------|--------|----------|------|
| 1 | HIGHLIGHT_THRESHOLD 55→70 | 282→150 点 | 281→~110 点 | mapData.ts:77 + 实测 news_geo.json |
| 2 | 3D ring 过大（比 2D 外环大 1.5×） | 环 7–14px(H=360) | 环 20–40px(H=480) | GlobePanel.tsx:333 |
| 3 | 2D 三层叠环占位大 | 覆盖 ~27° 地理跨度 | （未量化） | FlatMapPanel.tsx:424,459-473 |
| 4 | 常驻标签互相遮挡是「乱」主视觉 | 282 标签铺满半球 | 281 标签云 | 3D 截图互证 |
| 5 | 同地点无聚合（611→212 桶） | California 25 / Tehran 20 / Washington 19 | Washington 34 / California 25 / Tehran 21 | 实测 news_geo.json（快照时间差所致，方向一致） |
| 6 | P2 占位图层默认开是长期隐患 | 6 项 0 点但 defaultVisible | （未强调） | layerCategories.ts |

## 2. 差异点与仲裁

| 分歧 | vis-fe | vis-fe-2 | 仲裁 | 理由 |
|------|--------|----------|------|------|
| 默认关 news+conflict 图层 | 否（保留，仅关 6 空层） | 是（634→21 点） | **不采纳为默认** | 开阳核心 = 新闻地理可视化，默认视图无新闻点 = 打开看不到主数据；「乱」根因是标签密度非点数（点本身 1–3px），Top-80+阈值已解决。降为 OPEN 决策，可做「极简模式」可选开关 |
| 3D ring 数值 | (1.9/1.2)+1.1w | (1.8/1.0)+1.0w | 取 vis-fe 值 | 其配套调整传播速度(L335)保持视觉一致性，方案更完整 |
| 2D 聚焦环下限 | 8 | 10 | 取 8 | 降噪目标下更小更优 |

## 3. 最终执行清单（第一步 · 10 项 · 全部带 现值→新值）

1. `src/components/FlatMapPanel.tsx:424`：`Math.min(7.2, Math.max(2.4, 2.4+p.weight*4.8))` → `Math.min(4.6, Math.max(1.6, 1.6+p.weight*3.0))`
2. `src/components/FlatMapPanel.tsx:460`：`core*1.8` → `core*1.5`
3. `src/components/FlatMapPanel.tsx:470`：`core*1.35` → `core*1.2`
4. `src/components/FlatMapPanel.tsx:571`：`Math.max(core*2.4, 12)` → `Math.max(core*2.0, 8)`
5. `src/components/GlobePanel.tsx:293`：`0.32+p.weight*0.2` → `0.22+p.weight*0.14`（缺失值对应 0.18）
6. `src/components/GlobePanel.tsx:333`：`(isFocus(p)?2.8:1.76)+p.weight*1.76` → `(isFocus(p)?1.9:1.2)+p.weight*1.1`
7. `src/components/GlobePanel.tsx:335`：`(isFocus(p)?1.8:1.0)+p.weight*1.2` → `(isFocus(p)?1.5:0.8)+p.weight*0.8`
8. `src/lib/mapData.ts:77`：HIGHLIGHT_THRESHOLD `55` → `70`
9. `src/components/GlobePanel.tsx:374-387`：常驻标签按 intensity 降序截断 Top 80（useMemo sort+slice，保留悬停 tooltip）
10. `src/config/layerCategories.ts`：air/thermal/maritime/space/health/sdr 六项 `defaultVisible: false`；**news/conflict 保持 true**；LayerTreePanel「全开」默认可见集合同步为 geo/event/nuclear/news/conflict/chokepoint

行号为索引，实施以实际代码为准。

## 4. OPEN 决策（不阻塞实施，等用户一句话）

| 项 | 内容 | 当前倾向 | 触发条件 |
|----|------|----------|----------|
| O-1 | 「极简模式」：默认关 news+conflict（634→21 点）作为图层面板可选开关而非默认 | 做可选开关，不做默认 | 用户确认需要 |
| O-2 | 第二步同地点聚合粒度：location_name 主键 + country fallback + 0.5° 网格兜底（611→~212 点，−65%） | 按此粒度执行 | 第一步验收通过后 |

## 5. 事故记录（防重踩）

- 两 worker 并行写同一报告路径导致覆盖。教训：并行评估 worker 必须分配独立输出路径（`vis-eval-2026-08-11-{worker}.md`）。
- 未进 git 的 untracked 文件无版本历史，覆盖即丢；重要评估产物应尽早 commit 或分配独立文件名。
