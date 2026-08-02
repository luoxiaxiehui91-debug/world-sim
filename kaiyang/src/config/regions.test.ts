import { describe, it, expect } from 'vitest';
import {
  DEFAULT_REGION,
  REGIONS,
  REGION_STORAGE_KEY,
  WORLD_CAMERA,
  inRegion,
  regionBbox,
  regionCamera,
  regionDef,
  regionOf,
  regionPolygon,
  toRegionKey,
  type RegionKey,
} from '@/config/regions';
import { STRATEGIC_SITES } from '@/data/strategicSites';

/**
 * 地区 bbox 的**静态验证**（设计稿 §10-N6 要求：先验证 6 个 bbox 常量再接 UI）。
 * 覆盖：枚举完整性、跨 180° 回绕、极区收敛、6 个已知要地归属、world 不过滤、脏数据降级、
 * 相机换算单调性、fitExtent 多边形形状。
 */

/** 按 id 取战略要地坐标（用项目自己的权威坐标做归属断言，避免测试里另抄一份） */
function site(id: string): { lat: number; lng: number } {
  const s = STRATEGIC_SITES.find((x) => x.id === id);
  if (!s) throw new Error(`测试基准要地缺失：${id}`);
  return { lat: s.lat, lng: s.lng };
}

/* ------------------------------------------------------------------ */
/* 枚举完整性                                                          */
/* ------------------------------------------------------------------ */
describe('regions: 枚举完整性', () => {
  it('共 6 个地区，键两两唯一，顺序为 全球/美洲/欧洲/中东/亚太/非洲', () => {
    expect(REGIONS).toHaveLength(6);
    const keys = REGIONS.map((r) => r.key);
    expect(new Set(keys).size).toBe(6);
    expect(keys).toEqual(['world', 'americas', 'europe', 'mid_east', 'asia_pacific', 'africa']);
  });

  it('标签全中文且两两唯一', () => {
    const labels = REGIONS.map((r) => r.label);
    expect(labels).toEqual(['全球', '美洲', '欧洲', '中东', '亚太', '非洲']);
    expect(new Set(labels).size).toBe(6);
    for (const l of labels) expect(l).toMatch(/^[\u4e00-\u9fa5]+$/);
  });

  it('只有 world 的 bbox 为 null，其余 5 个都有 bbox', () => {
    expect(regionBbox('world')).toBeNull();
    for (const r of REGIONS.filter((x) => x.key !== 'world')) {
      expect(r.bbox).not.toBeNull();
      expect(r.bbox).toHaveLength(4);
    }
  });

  it('regionDef 能取到每个键；storage 键与设计稿登记一致', () => {
    for (const r of REGIONS) expect(regionDef(r.key)?.label).toBe(r.label);
    expect(REGION_STORAGE_KEY).toBe('kaiyang.region');
    expect(DEFAULT_REGION).toBe('world');
  });
});

/* ------------------------------------------------------------------ */
/* N6-① 跨 180° 回绕 / N6-② 极区变形                                   */
/* ------------------------------------------------------------------ */
describe('regions: N6 边界静态验证', () => {
  it('N6-①：所有 bbox 满足 minLng < maxLng（无跨 180° 回绕，fitExtent 不会反向拉伸）', () => {
    for (const r of REGIONS) {
      if (!r.bbox) continue;
      const [minLng, , maxLng] = r.bbox;
      expect(minLng, `${r.label} 西界应小于东界`).toBeLessThan(maxLng);
    }
  });

  it('N6-①：亚太东界恰为 180，不含白令海回绕段', () => {
    const ap = regionBbox('asia_pacific');
    expect(ap).not.toBeNull();
    expect(ap![2]).toBe(180);
    // 白令海峡（65.8N / -169W）属美洲侧，不应被亚太框住
    expect(inRegion({ lat: 65.8, lng: -169 }, 'asia_pacific')).toBe(false);
  });

  it('N6-②：所有 bbox 纬度收在 ±75° 内（不含极点，规避等距圆柱高纬拉伸）', () => {
    for (const r of REGIONS) {
      if (!r.bbox) continue;
      const [, minLat, , maxLat] = r.bbox;
      expect(minLat).toBeLessThan(maxLat);
      expect(Math.abs(minLat), `${r.label} 南界不应进极区`).toBeLessThanOrEqual(75);
      expect(Math.abs(maxLat), `${r.label} 北界不应进极区`).toBeLessThanOrEqual(75);
    }
  });

  it('N6-②：南北极点不归属任何地区（regionOf 返回 null，不硬塞）', () => {
    expect(regionOf(89.9, 0)).toBeNull();
    expect(regionOf(-89.9, 0)).toBeNull();
  });

  it('所有 bbox 经纬度在合法值域内', () => {
    for (const r of REGIONS) {
      if (!r.bbox) continue;
      const [minLng, minLat, maxLng, maxLat] = r.bbox;
      for (const lng of [minLng, maxLng]) expect(Math.abs(lng)).toBeLessThanOrEqual(180);
      for (const lat of [minLat, maxLat]) expect(Math.abs(lat)).toBeLessThanOrEqual(90);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6 个已知要地的归属                                                  */
/* ------------------------------------------------------------------ */
describe('regions: 6 个已知要地归属（对齐 data/strategicSites 权威坐标）', () => {
  it('霍尔木兹海峡 → 中东', () => {
    const p = site('hormuz');
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('mid_east');
    expect(inRegion(p, 'mid_east')).toBe(true);
  });

  it('马六甲海峡 → 亚太', () => {
    const p = site('malacca');
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('asia_pacific');
    expect(inRegion(p, 'asia_pacific')).toBe(true);
  });

  it('巴拿马运河 → 美洲', () => {
    const p = site('panama');
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('americas');
    expect(inRegion(p, 'americas')).toBe(true);
  });

  it('好望角 → 非洲', () => {
    const p = site('good-hope');
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('africa');
    expect(inRegion(p, 'africa')).toBe(true);
  });

  it('直布罗陀海峡 → 欧洲（西经 5.6°，不落入美洲框）', () => {
    const p = site('gibraltar');
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('europe');
    expect(inRegion(p, 'americas')).toBe(false);
  });

  /**
   * ⚠ N6 重叠情形（已知且刻意保留）：
   * 苏伊士运河（30.42N / 32.35E）**同时**落在「中东」[25,12,63,42] 与「非洲」[-20,-38,52,38] 两个 bbox 内。
   * - UI 过滤走 `inRegion`：中东 Tab 与非洲 Tab 下**都能看到**苏伊士 —— 这才是用户要的语义。
   * - 唯一归属 `regionOf` 按 REGIONS 顺序取首个匹配 ⇒ 'mid_east'（中东在非洲之前）。
   * 若日后要把唯一归属改判非洲，正解是收窄中东西界到 34°E，而不是给 regionOf 加特例。
   */
  it('苏伊士运河：中东/非洲两框皆含（inRegion 双真），唯一归属按顺序取中东', () => {
    const p = site('suez');
    expect(inRegion(p, 'africa')).toBe(true);
    expect(inRegion(p, 'mid_east')).toBe(true);
    expect(regionOf(p.lat, p.lng)).toBe<RegionKey>('mid_east');
  });

  it('曼德海峡（12.58N/43.33E）落在中东框内（红海南口，地理事实）', () => {
    const p = site('bab-el-mandeb');
    expect(inRegion(p, 'mid_east')).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* inRegion：world 不过滤 + 边界闭区间 + 脏数据降级                     */
/* ------------------------------------------------------------------ */
describe('regions: inRegion 过滤语义', () => {
  it('world 恒真：任何点（含南极、跨日界线）都不过滤', () => {
    expect(inRegion({ lat: 0, lng: 0 }, 'world')).toBe(true);
    expect(inRegion({ lat: -89, lng: 179 }, 'world')).toBe(true);
    expect(inRegion({ lat: 51.5, lng: -0.12 }, 'world')).toBe(true);
  });

  it('world 对非法坐标也返回 true（不过滤 = 不判定）', () => {
    expect(inRegion({ lat: Number.NaN, lng: Number.NaN }, 'world')).toBe(true);
    expect(inRegion(null, 'world')).toBe(true);
  });

  it('bbox 四条边为闭区间（边界点算命中）', () => {
    const [minLng, minLat, maxLng, maxLat] = regionBbox('mid_east')!;
    expect(inRegion({ lat: minLat, lng: minLng }, 'mid_east')).toBe(true);
    expect(inRegion({ lat: maxLat, lng: maxLng }, 'mid_east')).toBe(true);
    expect(inRegion({ lat: minLat - 0.01, lng: minLng }, 'mid_east')).toBe(false);
    expect(inRegion({ lat: maxLat, lng: maxLng + 0.01 }, 'mid_east')).toBe(false);
  });

  it('非法坐标 / 空对象在具体地区下判 false，且不抛异常', () => {
    expect(() => inRegion({ lat: Number.NaN, lng: 10 }, 'europe')).not.toThrow();
    expect(inRegion({ lat: Number.NaN, lng: 10 }, 'europe')).toBe(false);
    expect(inRegion({ lat: 10, lng: Number.POSITIVE_INFINITY }, 'europe')).toBe(false);
    expect(inRegion({ lat: 200, lng: 10 }, 'europe')).toBe(false);
    expect(inRegion(null, 'europe')).toBe(false);
    expect(inRegion(undefined, 'africa')).toBe(false);
  });

  it('未知地区键（脏值强转）按 world 处理，不抛异常', () => {
    const bogus = 'atlantis' as RegionKey;
    expect(() => inRegion({ lat: 0, lng: 0 }, bogus)).not.toThrow();
    expect(inRegion({ lat: 0, lng: 0 }, bogus)).toBe(true);
    expect(regionBbox(bogus)).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* regionOf：无归属与非法输入                                          */
/* ------------------------------------------------------------------ */
describe('regions: regionOf 归属判定', () => {
  it('永不返回 world', () => {
    const samples: [number, number][] = [
      [26.57, 56.25],
      [2.5, 101.3],
      [9.08, -79.68],
      [-34.36, 18.47],
      [35.95, -5.6],
      [0, 0],
      [89, 10],
    ];
    for (const [lat, lng] of samples) expect(regionOf(lat, lng)).not.toBe('world');
  });

  it('中大西洋（0N/28W）与南大洋（55S/100E）不属任何地区 → null', () => {
    // 美洲东界 -30、非洲西界 -20，中间这条大西洋缝隙刻意留空（无归属好过错归属）
    expect(regionOf(0, -28)).toBeNull();
    // 亚太南界 -50，再往南是南大洋
    expect(regionOf(-55, 100)).toBeNull();
  });

  it('非法坐标返回 null 且不抛异常', () => {
    expect(() => regionOf(Number.NaN, 0)).not.toThrow();
    expect(regionOf(Number.NaN, 0)).toBeNull();
    expect(regionOf(0, Number.NaN)).toBeNull();
    expect(regionOf(91, 0)).toBeNull();
    expect(regionOf(0, 181)).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* toRegionKey：localStorage 容错                                      */
/* ------------------------------------------------------------------ */
describe('regions: toRegionKey 持久化容错', () => {
  it('合法键原样返回', () => {
    for (const r of REGIONS) expect(toRegionKey(r.key)).toBe(r.key);
  });

  it('null / undefined / 空串 / 未知键 / 大小写不符一律回落 world', () => {
    expect(toRegionKey(null)).toBe('world');
    expect(toRegionKey(undefined)).toBe('world');
    expect(toRegionKey('')).toBe('world');
    expect(toRegionKey('atlantis')).toBe('world');
    expect(toRegionKey('EUROPE')).toBe('world');
    expect(toRegionKey('{"key":"europe"}')).toBe('world');
  });
});

/* ------------------------------------------------------------------ */
/* 相机取景与 fitExtent 多边形                                          */
/* ------------------------------------------------------------------ */
describe('regions: regionCamera 相机换算', () => {
  it('world 返回默认全球视角', () => {
    expect(regionCamera('world')).toEqual(WORLD_CAMERA);
  });

  it('地区视角落在 bbox 中心', () => {
    for (const r of REGIONS) {
      if (!r.bbox) continue;
      const [minLng, minLat, maxLng, maxLat] = r.bbox;
      const cam = regionCamera(r.key);
      expect(cam.lat).toBeCloseTo((minLat + maxLat) / 2, 6);
      expect(cam.lng).toBeCloseTo((minLng + maxLng) / 2, 6);
    }
  });

  it('altitude 恒在 [0.45, 2.5]，且跨度越大越高（中东 < 亚太）', () => {
    for (const r of REGIONS) {
      const { altitude } = regionCamera(r.key);
      expect(altitude).toBeGreaterThanOrEqual(0.45);
      expect(altitude).toBeLessThanOrEqual(2.5);
    }
    expect(regionCamera('mid_east').altitude).toBeLessThan(regionCamera('asia_pacific').altitude);
  });
});

describe('regions: regionPolygon（d3-geo fitExtent 入参）', () => {
  it('world 返回 null（调用方改用整球 Sphere）', () => {
    expect(regionPolygon('world')).toBeNull();
  });

  it('地区返回闭合的矩形环（5 点，首尾相同，经度单调不回绕）', () => {
    for (const r of REGIONS) {
      if (!r.bbox) continue;
      const poly = regionPolygon(r.key)!;
      expect(poly.type).toBe('Polygon');
      const ring = poly.coordinates[0];
      expect(ring).toHaveLength(5);
      expect(ring[0]).toEqual(ring[4]);
      const lngs = ring.map((c) => c[0]);
      expect(Math.min(...lngs)).toBe(r.bbox[0]);
      expect(Math.max(...lngs)).toBe(r.bbox[2]);
      const lats = ring.map((c) => c[1]);
      expect(Math.min(...lats)).toBe(r.bbox[1]);
      expect(Math.max(...lats)).toBe(r.bbox[3]);
    }
  });
});
