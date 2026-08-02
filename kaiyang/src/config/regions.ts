/**
 * 地区（Region）常量与判定（R-P1-02 · 纯前端，零依赖）。
 *
 * 唯一职责：给「地区 Tab」提供 6 个 bbox 常量 + 点位归属判定 + 相机取景参数。
 * 纯常量 + 纯函数，不依赖 React / d3 / globe.gl，可在任意层调用（含 globe.gl 回调）。
 *
 * ⚠ N6 边界（设计稿 §10-N6）三个已知坑，本文件的处置：
 * 1. **跨 180° 经线**：所有 bbox 一律满足 `minLng < maxLng`，亚太东界钉死在 180 且不含白令海回绕，
 *    因此 `fitExtent` 不会出现反向拉伸。`assertNoAntimeridianWrap` 的契约由 regions.test.ts 钉死。
 * 2. **极区变形**：等距圆柱投影下高纬会被严重拉长，故所有 bbox 的纬度上下界都收在 ±75° 内，
 *    不做「含极点」的地区（南极/北极不属于任何地区，`regionOf` 返回 null）。
 * 3. **3D/2D 相机语义不对齐**：2D 走 `fitExtent(bbox 矩形)`，3D 走 `pointOfView(bbox 中心 + 估算高度)`，
 *    两者本就不可能像素级对齐；此处只保证「中心一致 + 跨度单调」，由 `regionCamera` 单点收敛换算公式。
 */

/** 地区键。`world` 是「不过滤」的显式选择，不是任何点位的归属地。 */
export type RegionKey = 'world' | 'americas' | 'europe' | 'mid_east' | 'asia_pacific' | 'africa';

/** 经纬包围盒：`[minLng, minLat, maxLng, maxLat]`（WGS84 度）。 */
export type RegionBbox = [number, number, number, number];

export interface RegionDef {
  key: RegionKey;
  /** 中文标签（UI 全中文） */
  label: string;
  /** 包围盒；`null` 表示「全球 / 不过滤」 */
  bbox: RegionBbox | null;
}

/**
 * 6 大区定义。**数组顺序即 Tab 顺序，也是 `regionOf` 的重叠消歧顺序**（落入多个取第一个匹配）。
 *
 * ⚠ bbox 之间**天然重叠**（如苏伊士运河同时落在「中东」与「非洲」框内）——这是地理事实，
 * 不是 bug。UI 过滤走 `inRegion`（一个点可同时出现在两个地区视图里，符合直觉），
 * 只有需要「唯一归属」时才用 `regionOf`。
 */
export const REGIONS: readonly RegionDef[] = [
  { key: 'world', label: '全球', bbox: null },
  { key: 'americas', label: '美洲', bbox: [-170, -60, -30, 75] },
  { key: 'europe', label: '欧洲', bbox: [-25, 34, 45, 72] },
  { key: 'mid_east', label: '中东', bbox: [25, 12, 63, 42] },
  // 东界钉死 180：不含白令海回绕，避免 fitExtent 反向拉伸（N6-①）
  { key: 'asia_pacific', label: '亚太', bbox: [70, -50, 180, 60] },
  { key: 'africa', label: '非洲', bbox: [-20, -38, 52, 38] },
] as const;

/** 地区记忆键（设计稿 §K8 已登记）。 */
export const REGION_STORAGE_KEY = 'kaiyang.region';

/** 默认地区（首访 / 解析失败一律回落）。 */
export const DEFAULT_REGION: RegionKey = 'world';

const REGION_BY_KEY: ReadonlyMap<RegionKey, RegionDef> = new Map(REGIONS.map((r) => [r.key, r]));

/** 取地区定义；未知键返回 undefined。 */
export function regionDef(key: RegionKey): RegionDef | undefined {
  return REGION_BY_KEY.get(key);
}

/** 取地区 bbox；`world` 与未知键均返回 null（= 不过滤 / 不取景）。 */
export function regionBbox(key: RegionKey): RegionBbox | null {
  return REGION_BY_KEY.get(key)?.bbox ?? null;
}

/**
 * localStorage 原文 → 合法 RegionKey。
 * 键不在 REGIONS 中（含 null / 空串 / 历史脏值）一律回落 `world`，绝不抛异常。
 */
export function toRegionKey(raw: string | null | undefined): RegionKey {
  if (typeof raw !== 'string') return DEFAULT_REGION;
  const hit = REGIONS.find((r) => r.key === raw);
  return hit ? hit.key : DEFAULT_REGION;
}

/** 坐标是否为有限数值（脏数据护栏：NaN / Infinity / 越界一律判假）。 */
function validCoord(lat: number, lng: number): boolean {
  return (
    Number.isFinite(lat) && Number.isFinite(lng) && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180
  );
}

/** 点是否落在 bbox 内（闭区间，含边界）。 */
function bboxContains(bbox: RegionBbox, lat: number, lng: number): boolean {
  const [minLng, minLat, maxLng, maxLat] = bbox;
  return lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
}

/**
 * 点位的**唯一归属地区**（重叠时按 REGIONS 顺序取首个匹配）。
 *
 * - `world` 永不返回：它是「不过滤」的显式选择，不是兜底归属。
 * - 不落入任何地区 bbox（南极 / 太平洋中部 / 高纬北极等）时返回 `null` ——
 *   诚实表达「无归属」，不硬塞给某个地区（K5 降级红线：宁可给 null，不许编数据）。
 * - 坐标非法（NaN / 越界）同样返回 `null`，不抛异常。
 */
export function regionOf(lat: number, lng: number): RegionKey | null {
  if (!validCoord(lat, lng)) return null;
  for (const r of REGIONS) {
    if (!r.bbox) continue; // 跳过 world
    if (bboxContains(r.bbox, lat, lng)) return r.key;
  }
  return null;
}

/**
 * 点是否应在该地区视图中显示（UI 过滤的唯一入口）。
 * - `world`（或未知键）恒 `true`：全球视图不过滤任何点。
 * - 其他地区按 bbox 判定；坐标非法判 `false`（宁可少画一个点，也不让脏坐标飞到画面外）。
 *
 * 与 `regionOf` 的区别：本函数**允许一点属于多个地区**（苏伊士在「中东」和「非洲」两个 Tab 下都可见），
 * 这是符合直觉的过滤语义；`regionOf` 才做唯一归属消歧。
 */
export function inRegion(p: { lat: number; lng: number } | null | undefined, key: RegionKey): boolean {
  const bbox = regionBbox(key);
  if (!bbox) return true; // world / 未知键 => 不过滤
  if (!p) return false;
  if (!validCoord(p.lat, p.lng)) return false;
  return bboxContains(bbox, p.lat, p.lng);
}

/** 3D 地球的相机取景参数（lat/lng = bbox 中心，altitude 由跨度估算）。 */
export interface RegionCamera {
  lat: number;
  lng: number;
  altitude: number;
}

/** 全球默认视角（与 GlobePanel 初始化保持一致，避免两处漂移）。 */
export const WORLD_CAMERA: RegionCamera = { lat: 22, lng: 70, altitude: 2.4 };

/** 地区视角高度区间（经验值：0.45 ≈ 中东那种小区，2.5 ≈ 接近整球）。 */
const MIN_ALTITUDE = 0.45;
const MAX_ALTITUDE = 2.5;
/** 跨度 → 高度的换算基准：约 45° 跨度对应 altitude 1.0。 */
const SPAN_PER_ALTITUDE = 45;

/**
 * 地区 → 3D 相机取景。`world` 返回 `WORLD_CAMERA`（默认视角）。
 * 高度按 bbox 的经纬跨度取大者估算，并夹在 [0.45, 2.5]，避免贴脸或退到看不清。
 */
export function regionCamera(key: RegionKey): RegionCamera {
  const bbox = regionBbox(key);
  if (!bbox) return WORLD_CAMERA;
  const [minLng, minLat, maxLng, maxLat] = bbox;
  const span = Math.max(maxLng - minLng, maxLat - minLat);
  const altitude = Math.min(MAX_ALTITUDE, Math.max(MIN_ALTITUDE, span / SPAN_PER_ALTITUDE));
  return {
    lat: (minLat + maxLat) / 2,
    lng: (minLng + maxLng) / 2,
    altitude: Number(altitude.toFixed(3)),
  };
}

/** bbox 的 GeoJSON 多边形环（顺时针闭合），供 d3-geo `fitExtent` 使用。 */
export interface BboxPolygon {
  type: 'Polygon';
  coordinates: [number, number][][];
}

/**
 * bbox → GeoJSON Polygon（d3-geo `projection.fitExtent` 的标准入参形态）。
 * `world` 返回 `null`，调用方改用整球 `{type:'Sphere'}`。
 */
export function regionPolygon(key: RegionKey): BboxPolygon | null {
  const bbox = regionBbox(key);
  if (!bbox) return null;
  const [minLng, minLat, maxLng, maxLat] = bbox;
  return {
    type: 'Polygon',
    coordinates: [
      [
        [minLng, minLat],
        [maxLng, minLat],
        [maxLng, maxLat],
        [minLng, maxLat],
        [minLng, minLat],
      ],
    ],
  };
}
