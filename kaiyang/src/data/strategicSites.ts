import { PALETTE } from '@/config/theme';

/**
 * 战略要地（前端内置地标）· P1 纯前端叠加层。
 *
 * 定位（重要）：
 * - 本层**不是** RiskPoint，也**不占用** `CATEGORY_PALETTE` 的 12 个类别色（决策 D1）。
 *   它是一层「常驻地理参照物」，用**固定琥珀金 + 星形符号 + 常驻中文标签**表达，
 *   与任何风险类别（圆点 / 菱形 + 类别色）在形状与语义上都可一眼区分。
 * - 无后端 feed、无风险数值：这里只放**国际公认的地理咽喉点**（海峡 / 运河 / 海角），
 *   不含任何政治属性、归属判断或风险评分。前端不编造数据。
 *
 * 扩展方式：往 `STRATEGIC_SITES` 追加一项即可，渲染层与开关无需改动。
 * 坐标约定：小数 2~4 位的**公开百科级近似坐标**（≈1km 内），足够上图，不作权威。
 */

/** 要地类型（纯地理形态分类，无政治含义）。 */
export type StrategicSiteType = 'chokepoint' | 'canal' | 'strait' | 'cape';

export interface StrategicSite {
  /** 稳定唯一 id（渲染 key 与去重依据） */
  id: string;
  /** 中文显示名（地图常驻标签文案） */
  name: string;
  /** 纬度，必须落在 [-90, 90] */
  lat: number;
  /** 经度，必须落在 [-180, 180] */
  lng: number;
  /** 地理形态分类 */
  type: StrategicSiteType;
  /** 重要度 1~3，仅驱动符号尺寸，不参与任何风险数学 */
  importance: 1 | 2 | 3;
  /** 可选补充说明（tooltip 展示） */
  note?: string;
}

/**
 * 本层固定色：琥珀金。
 * 引用 `PALETTE.amber`（`#fbbf24`）而非另写一份 hex，保持色值单一事实来源（K1）；
 * 与风险类别色的区分靠**星形符号 + 常驻标签**，而非靠色相（本层不进类别色轴）。
 */
export const STRATEGIC_SITE_COLOR: string = PALETTE.amber;

/** 要地类型 → 中文标签（tooltip / 图例共用，避免各处自己写 map）。 */
export const STRATEGIC_SITE_TYPE_LABEL: Record<StrategicSiteType, string> = {
  chokepoint: '咽喉点',
  canal: '运河',
  strait: '海峡',
  cape: '海角',
};

/** 本层显隐的 localStorage 键（与 `kaiyang.layerVisibility` 分开存，互不影响）。 */
export const STRATEGIC_SITES_STORAGE_KEY = 'kaiyang.strategicSitesVisible';

/** 无 localStorage 记录时是否显示本层。 */
export const STRATEGIC_SITES_DEFAULT_VISIBLE = true;

/**
 * 初始种子（8 个国际公认地理要地）。
 * 只收录全球航运语境下的通用地名，不涉及任何主权 / 政治敏感表述。
 */
export const STRATEGIC_SITES: StrategicSite[] = [
  {
    id: 'hormuz',
    name: '霍尔木兹海峡',
    lat: 26.57,
    lng: 56.25,
    type: 'strait',
    importance: 3,
    note: '波斯湾唯一出海通道',
  },
  {
    id: 'suez',
    name: '苏伊士运河',
    lat: 30.42,
    lng: 32.35,
    type: 'canal',
    importance: 3,
    note: '连接地中海与红海',
  },
  {
    id: 'bosporus',
    name: '博斯普鲁斯海峡',
    lat: 41.12,
    lng: 29.07,
    type: 'strait',
    importance: 2,
    note: '黑海通往地中海的通道',
  },
  {
    id: 'gibraltar',
    name: '直布罗陀海峡',
    lat: 35.95,
    lng: -5.6,
    type: 'strait',
    importance: 2,
    note: '地中海与大西洋的西口',
  },
  {
    id: 'malacca',
    name: '马六甲海峡',
    lat: 2.5,
    lng: 101.3,
    type: 'strait',
    importance: 3,
    note: '印度洋与太平洋间的主航道',
  },
  {
    id: 'panama',
    name: '巴拿马运河',
    lat: 9.08,
    lng: -79.68,
    type: 'canal',
    importance: 2,
    note: '连接大西洋与太平洋',
  },
  {
    id: 'good-hope',
    name: '好望角',
    lat: -34.36,
    lng: 18.47,
    type: 'cape',
    importance: 2,
    note: '绕行非洲南端的替代航线',
  },
  {
    id: 'bab-el-mandeb',
    name: '曼德海峡',
    lat: 12.58,
    lng: 43.33,
    type: 'strait',
    importance: 3,
    note: '红海南端出入口',
  },
];

const VALID_TYPES: ReadonlySet<string> = new Set<StrategicSiteType>([
  'chokepoint',
  'canal',
  'strait',
  'cape',
]);

/** importance 归一到 1|2|3；缺失 / 越界 / 非整数一律回落 1（最小符号，不放大噪声）。 */
function normalizeImportance(value: unknown): 1 | 2 | 3 {
  if (value === 2) return 2;
  if (value === 3) return 3;
  return 1;
}

/**
 * 过滤出「可安全上图」的要地（K5 降级红线：任何输入都不抛异常、不白屏）。
 *
 * 逐项校验并**跳过**不合格项，而不是整层丢弃：
 * - id / name 必须是非空字符串；
 * - lat / lng 必须是有限数且落在合法区间（否则会被投影成 NaN 或画到 (0,0)）；
 * - type 非法时回落 'chokepoint'；importance 非法时回落 1；
 * - id 重复时只保留首次出现的一项（渲染 key 唯一）。
 */
export function validStrategicSites(
  sites: readonly (StrategicSite | null | undefined)[] | null | undefined = STRATEGIC_SITES,
): StrategicSite[] {
  if (!sites || sites.length === 0) return [];
  const seen = new Set<string>();
  const out: StrategicSite[] = [];
  for (const s of sites) {
    if (!s || typeof s !== 'object') continue;
    if (typeof s.id !== 'string' || s.id.length === 0) continue;
    if (typeof s.name !== 'string' || s.name.length === 0) continue;
    if (typeof s.lat !== 'number' || !Number.isFinite(s.lat)) continue;
    if (typeof s.lng !== 'number' || !Number.isFinite(s.lng)) continue;
    if (s.lat < -90 || s.lat > 90) continue;
    if (s.lng < -180 || s.lng > 180) continue;
    if (seen.has(s.id)) continue;
    seen.add(s.id);
    out.push({
      id: s.id,
      name: s.name,
      lat: s.lat,
      lng: s.lng,
      type: VALID_TYPES.has(s.type) ? s.type : 'chokepoint',
      importance: normalizeImportance(s.importance),
      note: typeof s.note === 'string' && s.note.length > 0 ? s.note : undefined,
    });
  }
  return out;
}

/** 符号半径（像素 / 3D 尺度共用的相对系数）：importance 1→1.0，2→1.25，3→1.5。 */
export function siteScale(importance: number | undefined): number {
  if (importance === 3) return 1.5;
  if (importance === 2) return 1.25;
  return 1;
}

/** 统一的要地提示文案（3D 与 2D 共用，保证两视图口径一致）。 */
export function siteTooltipText(site: StrategicSite): string {
  const type = STRATEGIC_SITE_TYPE_LABEL[site.type] ?? '要地';
  const base = `${site.name} · ${type} · 重要度 ${site.importance}`;
  return site.note ? `${base} · ${site.note}` : base;
}
