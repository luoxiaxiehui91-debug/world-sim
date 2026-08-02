# 对标 CRUCIX MONITOR 升级 —— 需知清单 / 待明确事项

> 背景：用户贴出 **CRUCIX MONITOR** 界面截图（战略态势大屏：2D 暗色地图 + 10 类实时指标 + 信号流 + 底部行情带）。
> 目标：评估开阳（kaiyang）是否/如何向该形态升级。本文档列出**升级前必须澄清的所有未知数**，
> 供新开的 crucix 分析团队作为调研大纲。
>
> 重要区分：截图里的 "CRUCIX MONITOR" 与开阳当前 `source:"Crucix新闻"` 不是同一物——
> 后者只是后端关键词叙事信号（文字卡片），前者是完整地理空间监视大屏。二者命名撞车，需先定性。

---

## A. CRUCIX 身份与归属（最关键，先定）

- [ ] 截图中的 "CRUCIX MONITOR" 是**咱们后端 Crucix 模块**的产出，还是**外部竞品 / 概念参考图**？
- [ ] 若是竞品 / 参考：是否允许借鉴其图层与交互设计？（个人内部研究系统，商用授权不构成约束，但设计抄袭需用户拍板）
- [ ] 若是自家系统：由哪个子系统产出？（天枢 macro-scan / 天璇 macro-sim / 天玑 / 玉衡 / Crucix）
- [ ] 截图来源是否可公开引用？能否获取更高清原图或更完整说明？

## B. 10 类指标的 data 来源（逐类核对）

对每类需回答：现有后端有无对应 fetcher？没有则谁新增？数据精度/频率/历史？

| 指标 | 截图计数 | 现有后端对应？ | 待确认数据源 |
|------|----------|----------------|--------------|
| Air Activity（空域活动） | 604 / 10 theaters | ? | ADS-B? 开源航迹? |
| Thermal Spikes（热异常） | 3,786 | ? | 卫星红外? VIIRS? |
| SDR Coverage（软件定义雷达） | 780 | ? | 自研? |
| Maritime Watch（海上监视） | 9 chokepoints | ? | AIS? |
| **Nuclear Sites（核设施）** | 6 monitors | ? | IAEA? 开源卫星? |
| Conflict Events（冲突事件） | 0 fatalities | ? | ACLED? GDELT? |
| Health Watch（卫生监视） | 0 WHO alerts | ? | WHO? |
| World News RSS（地理新闻） | 50 geolocated | Crucix新闻近似? | RSS + geocode? |
| OSINT Feed（开源情报） | 0 urgent | ? | 爬虫? |
| Space Activity（太空活动） | 24 / 435 new | ? | 发射目录? |

## C. 核设施 / Nuclear Watch（用户最关心的"核"）

- [ ] Nuclear Sites 6 monitors 数据源？辐射读数（Zaporizhzhia / Chernobyl / Fukushima 等）实时还是日更？
- [ ] 这与用户记忆的"核指数新闻"是**同一数据源**还是不同系统？
- [ ] 开阳要上核设施图层，后端谁提供坐标 + 读数？是否需要新增 fetcher？
- [ ] 合规：核设施/辐射数据是否涉及敏感出口？（个人研究系统，但数据源本身可用性需实测）

## D. 地图可视化方向

- [ ] CRUCIX 用 **2D 暗色底图**；开阳现用 **3D globe.gl**。升级是改 2D、增强 globe、还是双视图并存？
- [ ] 多图层叠加 + 颜色图例 + 聚类标签（如 `Ukraine 71` / `Middle East 178`）如何实现？
- [ ] 战略要地（Bosphorus / Suez / Hormuz / Gibraltar）硬编码 vs 数据驱动？
- [ ] 弧段连线（航线/轨迹）的数据模型？

## E. 信号流 / 告警

- [ ] 右侧 SIGNAL 排序与 severity 算法？与开阳现有 `SignalStreamPanel` 如何对齐？
- [ ] 告警是否可点开联动地图定位？

## F. 底部信息带

- [ ] 市场行情（S&P / NASDAQ / 杠杆 / 互换）数据源？开阳已有 FRED 面板能否扩展？
- [ ] 新闻滚动条与 World News RSS 的关系？

## G. 范围、阶段与优先级

- [ ] 全量对标（Wave3/4 大屏重构）还是先做最小可用（如先加 Nuclear Sites 图层 + 新闻 geocode）？
- [ ] 与 Wave2 控制面是否冲突？优先级如何排？
- [ ] 是否引入新的前端依赖（地图库如 Leaflet/MapLibre）？与 globe.gl 并存策略？

## H. 数据与契约（按开阳扩展标准）

- [ ] 新增 feed 在 `config/dataSources.ts` 登记 + `docs/DATA_CONTRACT.md` 更新 + `schema_version` 规则如何适用？
- [ ] 哪些 feed 需要 `lat` / `lng` 坐标字段？共用到哪种精度？
- [ ] 降级渲染（字段缺失不白屏）如何延伸到现在 10 类指标？

---

## 当前已知事实（作为分析锚点）

1. 开阳现已实现：3D globe（GRV 地理维度 + 事件柱）、NewsPanel（Crucix新闻文字卡片，无坐标）、FRED 经济面板、Wave2 控制抽屉（天枢运维，mock 模式）。
2. 开阳**当前没有任何**核设施 / Nuclear Watch / 多图层 / 战略要地聚类能力。
3. Crucix 在开阳里仅以 `source:"Crucix新闻"` 出现，6 条关键词信号全为 [警报] 级，无核类条目。
4. 已写 `docs/开阳Crucix新闻地理坐标需求-给后端.md`：请求后端给 Crucix 新闻加可选 `lat/lng`，使 [警报] 级新闻未来可上图（**未实现**）。
5. 技术栈钉死：React+Vite+TS+Tailwind+globe.gl^2.46.1+ECharts；three 0.185.1。新增地图库需用户批准。
