/**
 * 开阳视觉主题（单一事实来源）。
 * 所有面板 / 地球 / 平面地图统一从这里取色，避免散落硬编码色值。
 * 约束：纯常量 + 纯函数，不依赖 React，可在任意层（含 globe.gl 回调）使用。
 */

/** 基础调色板（深空 + 青绿科技感 + 琥珀/红预警）。 */
export const PALETTE = {
  /** 主青（高亮、强调） */
  cyan: '#22d3ee',
  /** 主青绿（正文强调、低风险） */
  teal: '#5eead4',
  /** 深青（渐变收尾） */
  tealDeep: '#0d9488',
  /** 中风险琥珀 */
  amber: '#fbbf24',
  /** 高风险预警红 */
  red: '#f87171',
  /** 数据缺失灰 */
  slate: '#64748b',
  /** 深空背景 */
  space: '#0a0e1a',
  /** 更深的背景（径向渐变外圈） */
  spaceDeep: '#04070f',
  /** 玻璃面板底色 */
  glass: 'rgba(255,255,255,0.05)',
  /** 玻璃面板描边 */
  glassBorder: 'rgba(255,255,255,0.10)',
  /** 正文文字 */
  text: '#d7e3ea',
  /** 次级文字 */
  textDim: 'rgba(215,227,234,0.55)',
  /** 坐标轴与参考线中性色 */
  axis: '#cbd5e1',
} as const;

/** 严重度阈值（0-100）。低 < mid <= 中 < high <= 高。 */
export const SEVERITY_THRESHOLD = {
  mid: 40,
  high: 66,
} as const;

export type SeverityLevel = 'missing' | 'low' | 'mid' | 'high';

/** 数值 → 严重度等级（null / 非有限值 = 缺失）。 */
export function severityLevel(value: number | null | undefined): SeverityLevel {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'missing';
  if (value >= SEVERITY_THRESHOLD.high) return 'high';
  if (value >= SEVERITY_THRESHOLD.mid) return 'mid';
  return 'low';
}

const LEVEL_COLOR: Record<SeverityLevel, string> = {
  missing: PALETTE.slate,
  low: PALETTE.teal,
  mid: PALETTE.amber,
  high: PALETTE.red,
};

const LEVEL_LABEL: Record<SeverityLevel, string> = {
  missing: '缺失',
  low: '低',
  mid: '中',
  high: '高',
};

/** 数值 → 严重度颜色（青 → 琥珀 → 红，缺失为灰）。 */
export function severityColor(value: number | null | undefined): string {
  return LEVEL_COLOR[severityLevel(value)];
}

/** 数值 → 中文严重度标签。 */
export function severityLabel(value: number | null | undefined): string {
  return LEVEL_LABEL[severityLevel(value)];
}

/** 十六进制色 + 透明度 → rgba() 字符串。非法输入原样返回。 */
export function withAlpha(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const int = parseInt(m[1], 16);
  const r = (int >> 16) & 255;
  const g = (int >> 8) & 255;
  const b = int & 255;
  const a = Math.min(1, Math.max(0, alpha));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/** 严重度对应的发光阴影（用于小卡 / 平面地图点位）。 */
export function severityGlow(value: number | null | undefined, strength = 0.55): string {
  const c = severityColor(value);
  return `0 0 10px ${withAlpha(c, strength)}, 0 0 22px ${withAlpha(c, strength * 0.45)}`;
}

/** 3D 地球 / 平面地图共用的视觉参数。 */
export const MAP_THEME = {
  /** 星空背景贴图（已本地化到 public/assets，离线可用） */
  starFieldUrl: './assets/night-sky.png',
  /** 地球昼面纹理（本地） */
  earthTextureUrl: './assets/earth-blue-marble.jpg',
  /** 地形凹凸（本地） */
  earthBumpUrl: './assets/earth-topology.png',
  /** 大气辉光主色 */
  atmosphereColor: PALETTE.teal,
  /** 大气厚度（加厚以贴近 crucix 观感） */
  atmosphereAltitude: 0.22,
  /** 经纬网格线色 */
  graticuleColor: withAlpha(PALETTE.cyan, 0.18),
  /** 弧线粗细 */
  arcStroke: 0.75,
  /** 弧线抬升比例 */
  arcAltitudeAutoScale: 0.55,
  /** 平面地图陆地填充 */
  flatLandFill: '#0f1b2c',
  /** 平面地图国界描边 */
  flatLandStroke: withAlpha(PALETTE.teal, 0.22),
  /** 平面地图海洋填充 */
  flatOceanFill: '#060b16',
  /** 平面地图经纬网格 */
  flatGraticule: withAlpha(PALETTE.cyan, 0.1),
} as const;

/** 图例项（3D / 平面共用）。 */
export const SEVERITY_LEGEND: Array<{ level: SeverityLevel; label: string; color: string }> = [
  { level: 'low', label: '低', color: LEVEL_COLOR.low },
  { level: 'mid', label: '中', color: LEVEL_COLOR.mid },
  { level: 'high', label: '高', color: LEVEL_COLOR.high },
  { level: 'missing', label: '缺失', color: LEVEL_COLOR.missing },
];

/* ═══════════════════════════════════════════════════════════════════════
   分类图层色板（大屏升级 Wave · 1.2.0 新增，只追加不改既有导出）
   ═══════════════════════════════════════════════════════════════════════

   两条正交的视觉轴，互不覆盖（决策 D1）：
     · 色相轴 = 图层类别 → CATEGORY_PALETTE（本段）
     · 强度轴 = 严重度   → SEVERITY_THRESHOLD / severityColor（上方，未改动）

   唯一例外：数据缺失是「元状态」，优先级高于类别（决策 C2-A），
   由 layerCategories.categoryColor() 强制取 CATEGORY_PALETTE.missing。 */

/**
 * 图层类别色（色相 = 类别）。
 * 12 个类别色两两不同（由 layerCategories.test.ts 断言），
 * 与既有 PALETTE 同源的 4 项直接引用 PALETTE，避免同一颜色出现两个真相。
 */
export const CATEGORY_PALETTE = {
  /** 地缘风险 · 青绿 teal（品牌主色） */
  geo: PALETTE.teal,
  /** 气候 / 灾害事件 · 琥珀 amber */
  event: PALETTE.amber,
  /** 核设施 / 辐射监测 · 明黄（靠菱形与 event 琥珀区分） */
  nuclear: '#facc15',
  /** 地理化新闻 · 青 cyan */
  news: PALETTE.cyan,
  /** 冲突事件 · 红 */
  conflict: PALETTE.red,
  /** 战略要地 · 近白 */
  chokepoint: '#e2e8f0',
  /** 空域活动 · 翡翠绿 */
  air: '#34d399',
  /** 热异常 · 橙（C3-A：由红改橙，避开 conflict 红） */
  thermal: '#fb923c',
  /** 海上监视 · 紫 */
  maritime: '#c084fc',
  /** 太空活动 · 靛紫（C3-A：由紫改靛紫，避开 maritime 紫） */
  space: '#818cf8',
  /** 卫生监视 · 黄绿 lime（C3-A：由绿改黄绿，避开 air 翡翠绿） */
  health: '#a3e635',
  /** SDR 覆盖 · 蓝 */
  sdr: '#60a5fa',
  /** 元状态：数据缺失灰（覆盖任何类别色，C2-A）；不进类别图例，只进状态图例 */
  missing: PALETTE.slate,
} as const;
