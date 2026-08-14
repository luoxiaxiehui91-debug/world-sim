import { CATEGORY_PALETTE } from '@/config/theme';

/**
 * 分类图层体系（单一事实来源）。
 *
 * 约定（对应设计稿 §8 共享知识 K1）：
 * - 类别**枚举与元数据**的唯一定义处就是本文件；新增图层类别只改这里。
 * - **色值常量**的唯一定义处是 `config/theme.ts` 的 `CATEGORY_PALETTE`；
 *   本文件只做引用，不自建 hex。`src/index.css` 的 `--ky-cat-*` 是 CSS 侧手工镜像。
 * - ❌ 任何 component 都不得硬编码类别色（如 `#facc15`），一律走 `categoryColor()`。
 *
 * 视觉双轴（决策 D1）：
 * - **色相 = 类别**（本文件）；
 * - **严重度 = 尺寸 + 光环脉冲**（`RiskPoint.weight`，见 `lib/mapData.ts`）。
 * 两轴正交，唯一例外是「数据缺失」这一元状态会覆盖类别色（决策 C2-A）。
 */

/** 图层类别枚举。新增图层类别的唯一登记处（单一事实来源）。 */
export type LayerCategory =
  // ── 既有数据的类别化（P0 就位，不新增数据）────────────
  | 'geo' // 地缘风险（GRV geographic 常驻维度）
  | 'event' // 气候 / 自然灾害事件（grv_latest.json events[]）
  // ── P0 新增 ────────────────────────────────────────
  | 'nuclear' // 核设施 / 辐射监测
  // ── P1 规划 ────────────────────────────────────────
  | 'news' // 地理化新闻
  | 'conflict' // 冲突事件
  | 'chokepoint' // 战略要地（前端硬编码地标）
  // ── P2 规划（后端 feed 门控）─────────────────────────
  | 'air' // 全球航线网（静态结构数据，OpenFlights）
  | 'aircraft' // 实时航班（OpenSky 快照，air 图层实时子层）
  | 'thermal' // 热异常
  | 'maritime' // 海上监视
  | 'space' // 太空活动
  | 'health' // 卫生监视
  | 'sdr'; // SDR 覆盖
// 注：'osint'（开源情报）已于 1.3.0 永久删除 —— 天枢合规否决（不做社媒抓取），
// 见 docs/DATA_CONTRACT.md §2.6 第 8 项。不得再加回。

/** 点位符号形状。P0 只实现 circle / diamond，其余为 P1+ 预留。
 *  'arrow' = 方向型渲染模式（08-14）：aircraft 实时航班——2D 只画航向旋转箭头、不画圆点圈（用户拍板）；
 *  'arc' = 弧线型（08-14）：air 全球航线网图例图标（图层本体是 RiskArc 弧，无点位）。 */
export type PointShape = 'circle' | 'diamond' | 'triangle' | 'square' | 'arrow' | 'arc';

/** 点位数据状态：ok=有数；missing=该点无有效数值（元状态，覆盖类别色）。 */
export type PointStatus = 'ok' | 'missing';

/** 落地阶段，仅用于图例分组与文档，不参与任何渲染数学。 */
export type LayerPhase = 'P0' | 'P1' | 'P2';

export interface LayerCategoryDef {
  key: LayerCategory;
  /** 中文显示名（图例 / 左树 / tooltip 共用） */
  label: string;
  /** 类别色（色相 = 类别，D1）。取自 theme.ts 的 CATEGORY_PALETTE */
  color: string;
  /** 默认符号形状 */
  shape: PointShape;
  /** 首次加载时是否可见（无 localStorage 记录时的默认值） */
  defaultVisible: boolean;
  /** 落地阶段，仅用于图例分组与文档 */
  phase: LayerPhase;
  /** 关联 feed 名（dataSources.FEEDS 的键）；null = 派生自既有 feed，无独立文件 */
  feed: string | null;
  /** 图例悬停说明 */
  desc: string;
}

/**
 * 全部图层类别定义表。
 * 顺序即图例展示顺序；不影响绘制层叠顺序（层叠顺序见 K7，由 WorldPanel 的合并顺序决定）。
 */
export const LAYER_CATEGORIES: LayerCategoryDef[] = [
  {
    key: 'geo',
    label: '地缘风险',
    color: CATEGORY_PALETTE.geo,
    shape: 'circle',
    defaultVisible: true,
    phase: 'P0',
    feed: 'grv',
    desc: 'GRV 常驻地理维度（台海 / 南海 / 中东能源 …）',
  },
  {
    key: 'event',
    label: '气候/灾害事件',
    color: CATEGORY_PALETTE.event,
    shape: 'circle',
    defaultVisible: true,
    phase: 'P0',
    feed: 'grv',
    desc: '事件触发式告警柱，来自 grv_latest.json 的 events[]',
  },
  {
    key: 'nuclear',
    label: '核设施',
    color: CATEGORY_PALETTE.nuclear,
    shape: 'diamond',
    defaultVisible: true,
    phase: 'P0',
    feed: 'nuclearSites',
    desc: '核电站 / 辐射监测站；读数缺失时为灰色虚线菱形',
  },
  {
    key: 'news',
    label: '地理新闻',
    color: CATEGORY_PALETTE.news,
    shape: 'circle',
    defaultVisible: true,
    phase: 'P1',
    feed: 'news',
    desc: '地理化新闻点位（需后端为新闻补 lat/lng）',
  },
  {
    key: 'conflict',
    label: '冲突事件',
    color: CATEGORY_PALETTE.conflict,
    shape: 'circle',
    defaultVisible: true,
    phase: 'P1',
    feed: 'news_geo',
    desc: '武装冲突 / 伤亡事件（GDELT news_geo 事件，08-14 接入）',
  },
  {
    key: 'chokepoint',
    label: '战略要地',
    color: CATEGORY_PALETTE.chokepoint,
    shape: 'diamond',
    defaultVisible: true,
    phase: 'P1',
    feed: null,
    desc: '海峡 / 运河等咽喉点地标（前端硬编码）',
  },
  {
    key: 'air',
    label: '全球航线',
    color: CATEGORY_PALETTE.air,
    shape: 'arc',
    defaultVisible: false,
    phase: 'P2',
    feed: 'airroutes',
    desc: '全球主要航线走廊（OpenFlights 静态结构数据，08-14 替代实时点——无 ADS-B 覆盖盲区）',
  },
  {
    key: 'aircraft',
    label: '实时航班',
    color: CATEGORY_PALETTE.aircraft,
    shape: 'arrow',
    defaultVisible: false,
    phase: 'P2',
    feed: 'airtraffic',
    desc: 'OpenSky 众包 ADS-B 实时航班（非洲/中国/俄罗斯内陆接收器稀疏，不代表真实空情）',
  },
  {
    key: 'thermal',
    label: '热异常',
    color: CATEGORY_PALETTE.thermal,
    shape: 'circle',
    defaultVisible: false,
    phase: 'P2',
    feed: 'firms',
    desc: 'NASA FIRMS 火点（1° 网格后端预聚合，08-14 接入；火点密度 = 热异常活跃度）',
  },
  {
    key: 'maritime',
    label: '海上监视',
    color: CATEGORY_PALETTE.maritime,
    shape: 'circle',
    defaultVisible: false,
    phase: 'P2',
    feed: null,
    desc: '船舶与海上目标（需后端 feed）',
  },
  {
    key: 'space',
    label: '太空活动',
    color: CATEGORY_PALETTE.space,
    shape: 'triangle',
    defaultVisible: false,
    phase: 'P2',
    feed: null,
    desc: '发射场 / 在轨事件（需后端 feed）',
  },
  {
    key: 'health',
    label: '卫生监视',
    color: CATEGORY_PALETTE.health,
    shape: 'circle',
    defaultVisible: false,
    phase: 'P2',
    feed: null,
    desc: '疫情 / 公共卫生事件（需后端 feed）',
  },
  {
    key: 'sdr',
    label: 'SDR 覆盖',
    color: CATEGORY_PALETTE.sdr,
    shape: 'circle',
    defaultVisible: false,
    phase: 'P2',
    feed: 'sdr',
    desc: 'KiwiSDR 全球软件无线电接收器（851 个在线点，08-14 接入；覆盖可视化非风险）',
  },
];

/** 全部类别键（供图例遍历、开关初始化）。顺序与 LAYER_CATEGORIES 一致。 */
export const ALL_CATEGORIES: LayerCategory[] = LAYER_CATEGORIES.map((d) => d.key);

/** 无 localStorage 记录时默认可见的类别。 */
export const DEFAULT_VISIBLE_CATEGORIES: LayerCategory[] = LAYER_CATEGORIES.filter(
  (d) => d.defaultVisible,
).map((d) => d.key);

const BY_KEY: ReadonlyMap<LayerCategory, LayerCategoryDef> = new Map(
  LAYER_CATEGORIES.map((d) => [d.key, d]),
);

/** 未知类别的兜底类别（旧数据 / 脏数据不炸）。 */
export const FALLBACK_CATEGORY: LayerCategory = 'geo';

/** 数据缺失灰（元状态色，覆盖任何类别色）。 */
export const MISSING_COLOR: string = CATEGORY_PALETTE.missing;

/**
 * 单图层点位数量护栏（设计稿 §10-N5 预埋）。
 * 超过此数的图层会被截断并在控制台告警，避免某个 feed 突然打爆帧率。
 */
export const MAX_POINTS_PER_LAYER = 2000;

/**
 * 不受单图层护栏限制的类别（08-14 用户拍板：aircraft 实时航班全量显示，截断后缺一部分没意义）。
 * 其余图层仍受 MAX_POINTS_PER_LAYER 护栏保护（防 feed 突发膨胀打死帧率）。
 * （thermal 曾加入，08-14 19:5x 移除：MIN_THERMAL_COUNT=50 等级筛选后仅 ~500 格，
 *  远低于护栏；保留护栏兜底防火点爆炸。）
 */
export const UNCAPPED_LAYERS: ReadonlySet<LayerCategory> = new Set(['aircraft']);

/** 类别 → 定义；未知类别返回 undefined（调用方自行降级为 FALLBACK_CATEGORY）。 */
export function categoryDef(category: LayerCategory | undefined): LayerCategoryDef | undefined {
  if (!category) return undefined;
  return BY_KEY.get(category);
}

/**
 * 类别 → 色。
 *
 * 第一道分支就是「缺失覆盖类别色」（决策 C2-A）：
 * `status==='missing'` 一律返回灰，不被任何类别色覆盖。
 */
export function categoryColor(
  category: LayerCategory | undefined,
  status: PointStatus = 'ok',
): string {
  if (status === 'missing') return MISSING_COLOR;
  return categoryDef(category)?.color ?? CATEGORY_PALETTE[FALLBACK_CATEGORY];
}

/** 类别 → 默认符号形状；未知类别退回 'circle'。 */
export function categoryShape(category: LayerCategory | undefined): PointShape {
  return categoryDef(category)?.shape ?? 'circle';
}

/** 类别 → 中文标签；未知类别返回原始键（便于排障），完全缺省时返回 '未分类'。 */
export function categoryLabel(category: LayerCategory | undefined): string {
  return categoryDef(category)?.label ?? (category ?? '未分类');
}

/**
 * 元状态判定（决策 C2-A 的唯一入口）：
 * 上游标记为 missing、或数值缺失 / 非有限数，一律视为「数据缺失」。
 */
export function resolvePointStatus(
  status: PointStatus | undefined,
  value: number | null | undefined,
): PointStatus {
  if (status === 'missing') return 'missing';
  if (value === null || value === undefined || !Number.isFinite(value)) return 'missing';
  return 'ok';
}

/** 任意输入 → 合法类别键；不合法时返回 undefined。 */
export function toLayerCategory(input: unknown): LayerCategory | undefined {
  if (typeof input !== 'string') return undefined;
  return BY_KEY.has(input as LayerCategory) ? (input as LayerCategory) : undefined;
}

/* ------------------------------------------------------------------ */
/* 图层可见性持久化（K8 localStorage 键位登记 + 前向兼容）              */
/* ------------------------------------------------------------------ */

/** 图层可见性的 localStorage 键（K8 登记）。 */
export const LAYER_VISIBILITY_STORAGE_KEY = 'kaiyang.layerVisibility';

/**
 * 持久化载荷。
 * `known` 记录**写入当时已存在的全部类别**，用于区分
 * 「用户主动关掉的类别」与「本次版本才新增、老快照里根本没有的类别」——
 * 后者必须按 `defaultVisible` 补入，否则新图层对老用户永久不可见（K8 隐蔽 bug）。
 * 同时兼容早期的纯数组形态（只有 visible，无 known）。
 */
interface LayerVisibilityPayload {
  visible: string[];
  known: string[];
}

/** 序列化可见类别集合（写入 localStorage 的字符串）。 */
export function serializeLayerVisibility(visible: Iterable<LayerCategory>): string {
  const set = new Set<LayerCategory>(visible);
  const payload: LayerVisibilityPayload = {
    visible: ALL_CATEGORIES.filter((k) => set.has(k)),
    known: [...ALL_CATEGORIES],
  };
  return JSON.stringify(payload);
}

/**
 * 解析 localStorage 快照 → 可见类别列表。
 *
 * - 非法 / 空输入 → 全部默认可见类别；
 * - 未知类别键 → 丢弃（`ALL_CATEGORIES` 过滤）；
 * - 对象形态：快照 `known` 里没有登记的**新类别**按 `defaultVisible` 补入（K8 前向兼容）；
 * - 纯数组形态（防御性兼容，无 `known` 信息）：原样尊重，不做任何补入，
 *   以免把用户主动关掉的类别又打开。
 */
export function parseLayerVisibility(raw: string | null | undefined): LayerCategory[] {
  if (!raw) return [...DEFAULT_VISIBLE_CATEGORIES];

  let parsed: unknown = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [...DEFAULT_VISIBLE_CATEGORIES];
  }

  let visibleRaw: unknown[];
  let knownRaw: unknown[] | null;

  if (Array.isArray(parsed)) {
    visibleRaw = parsed;
    knownRaw = null;
  } else if (parsed !== null && typeof parsed === 'object') {
    const obj = parsed as Partial<LayerVisibilityPayload>;
    if (!Array.isArray(obj.visible)) return [...DEFAULT_VISIBLE_CATEGORIES];
    visibleRaw = obj.visible;
    knownRaw = Array.isArray(obj.known) ? obj.known : null;
  } else {
    return [...DEFAULT_VISIBLE_CATEGORIES];
  }

  const visible = new Set<LayerCategory>();
  for (const v of visibleRaw) {
    const key = toLayerCategory(v);
    if (key) visible.add(key);
  }

  // 前向兼容：写入快照时还不存在的类别，按 defaultVisible 补入
  if (knownRaw !== null) {
    const known = new Set<LayerCategory>();
    for (const k of knownRaw) {
      const key = toLayerCategory(k);
      if (key) known.add(key);
    }
    for (const def of LAYER_CATEGORIES) {
      if (!known.has(def.key) && def.defaultVisible) visible.add(def.key);
    }
  }

  return ALL_CATEGORIES.filter((k) => visible.has(k));
}
