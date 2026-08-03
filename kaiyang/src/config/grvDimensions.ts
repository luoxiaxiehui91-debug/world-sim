/**
 * GRV 11 维风险点定义（内置默认坐标映射）。
 * 若上游 grv_latest.json 不含 lat/lng，则使用此处预设锚点（扩展标准：坐标容错）。
 *
 * 维度分类（Wave1 视觉增强新增）：
 * - kind='geographic'：有真实地理锚点，绘制在 3D 地球 / 平面地图上。
 * - kind='composite' ：全球综合类指数，没有地理位置意义（原先被硬塞到撒哈拉/南美，
 *   造成"非洲孤点"怪象）。此类维度不上地图，改由 GRV 面板头条数字 + 顶部状态条展示。
 */
export type GrvDimKind = 'geographic' | 'composite';

export interface GrvDimDef {
  id: string;
  label: string;
  group: string;
  /** 维度类别：地理点 or 全球综合 */
  kind: GrvDimKind;
  /** 地理锚点纬度（composite 维度为 undefined） */
  lat?: number;
  /** 地理锚点经度（composite 维度为 undefined） */
  lng?: number;
  /** 对应 grv_latest.json 的字段名；缺失则降级为「数据缺失」 */
  sourceKey?: string;
  /** 面板中的补充说明（可选） */
  note?: string;
  /**
   * 是否在地图上渲染常驻柱状图（默认 true）。
   * 设为 false 的维度保留地理锚点（供 GRV_ARCS 弧线使用），但不画常驻柱；
   * 其地图呈现改由事件触发式告警柱（grv_latest.json 的 events[]）承担。
   */
  renderBar?: boolean;
  /**
   * 是否为推导维度（来自 GDELT 国别分数聚合，无 GPR 校准基线）。
   * true = 前端显示「推导值」徽章 + 虚线边框 + confidence tooltip。
   * confidence 在运行时从 grv_latest.json 的 _derived_meta 注入。
   */
  isDerived?: boolean;
}

export const GRV_DIMENSIONS: GrvDimDef[] = [
  { id: 'taiwan_strait', label: '台海', group: '地缘', kind: 'geographic', lat: 24.5, lng: 120.5, sourceKey: 'taiwan_strait' },
  { id: 'south_china_sea', label: '南海', group: '地缘', kind: 'geographic', lat: 13.0, lng: 114.0 },
  { id: 'us_china_strategic', label: '美中战略', group: '地缘', kind: 'geographic', lat: 39.0, lng: -98.0, sourceKey: 'us_china_strategic' },
  { id: 'middle_east_energy', label: '中东能源', group: '能源', kind: 'geographic', lat: 26.0, lng: 45.0, sourceKey: 'middle_east_energy' },
  { id: 'russia_europe', label: '俄乌/东欧', group: '地缘', kind: 'geographic', lat: 49.0, lng: 32.0, sourceKey: 'russia_europe' },
  { id: 'korean_peninsula', label: '朝鲜半岛', group: '地缘', kind: 'geographic', lat: 38.0, lng: 127.0 },
  { id: 'india_pacific', label: '印太', group: '地缘', kind: 'geographic', lat: 1.3, lng: 103.8 },
  {
    id: 'global_composite',
    label: '全球综合',
    group: '综合',
    kind: 'composite',
    sourceKey: 'global_composite',
    note: '全球综合风险指数，无地理位置，不投影到地图',
  },
  { id: 'climate_risk', label: '气候风险', group: '非传统', kind: 'geographic', lat: 74.0, lng: 10.0, sourceKey: 'climate_risk', note: '锚点：北极圈（气候变化最敏感区）；不画常驻柱，改为事件触发式告警柱', renderBar: false },
  { id: 'disaster_risk', label: '自然灾害', group: '非传统', kind: 'geographic', lat: -2.0, lng: -80.0, sourceKey: 'disaster_risk', note: '锚点：环太平洋地震带；不画常驻柱，改为事件触发式告警柱', renderBar: false },
  { id: 'global_south',
    label: '全球南方不稳定性',
    group: '综合',
    kind: 'composite',
    isDerived: true,
    note: '推导值：IND/NGA/EGY/TUR政治不稳定性聚合（confidence≤0.60）。⚠ 不代表全球南方外交团结或战略能力。',
  },
  // ── 推导地缘维度（无 GPR 数据源，来自 GDELT 国别分数加权聚合）──────────
  // 多角色论证（地缘政治/数据科学/怀疑者/工程师）裁定，2026-08-03
  // 设计原则：正交性优先——刻意选择与实测维度不重叠的 GDELT 字段
  { id: 'south_china_sea',
    label: '南海',
    group: '地缘',
    kind: 'geographic',
    lat: 13.0, lng: 114.0,
    sourceKey: 'south_china_sea',
    isDerived: true,
    note: '推导值：CHN maritime(tension,不含sanction) + USA/JPN外部回应。置信度0.50（VNM/PHL/IDN缺失）。',
  },
  { id: 'korean_peninsula',
    label: '朝鲜半岛',
    group: '地缘',
    kind: 'geographic',
    lat: 38.0, lng: 127.5,
    sourceKey: 'korean_peninsula',
    isDerived: true,
    note: '推导值：PRK发射活动(稀疏，EMA平滑) + JPN区域响应 + USA前沿存在代理KOR。置信度0.65（KOR缺失）。',
  },
  { id: 'india_pacific',
    label: '印太',
    group: '地缘',
    kind: 'geographic',
    lat: 5.0, lng: 108.0,
    sourceKey: 'india_pacific',
    isDerived: true,
    note: '推导值：CHN外交/文化摩擦(非军事，与us_china正交) + IND边境 + JPN东海 + PAK南亚。置信度0.70（AUS/IDN缺失）。',
  },
];

/** 按 id 查维度定义。 */
export function getDimDef(id: string): GrvDimDef | undefined {
  return GRV_DIMENSIONS.find((d) => d.id === id);
}

/**
 * 地缘联动弧线（仅在 geographic 维度之间）。
 * composite 维度不参与连线（否则会在地图上引出一个虚构坐标）。
 * 渲染层仍会再做一次坐标存在性校验，缺坐标即跳过。
 */
export const GRV_ARCS: Array<[string, string]> = [
  ['taiwan_strait', 'us_china_strategic'],
  ['taiwan_strait', 'south_china_sea'],
  ['south_china_sea', 'india_pacific'],
  ['us_china_strategic', 'korean_peninsula'],
  ['middle_east_energy', 'india_pacific'],
  ['middle_east_energy', 'russia_europe'],
  ['us_china_strategic', 'middle_east_energy'],
  ['russia_europe', 'taiwan_strait'],
  ['climate_risk', 'russia_europe'],
  ['disaster_risk', 'india_pacific'],
];
