import { describe, it, expect } from 'vitest';
import {
  STRATEGIC_SITES,
  STRATEGIC_SITES_DEFAULT_VISIBLE,
  STRATEGIC_SITES_STORAGE_KEY,
  STRATEGIC_SITE_COLOR,
  STRATEGIC_SITE_TYPE_LABEL,
  siteScale,
  siteTooltipText,
  validStrategicSites,
  type StrategicSite,
  type StrategicSiteType,
} from '@/data/strategicSites';
import { CATEGORY_PALETTE } from '@/config/theme';

/**
 * 战略要地叠加层（P1 第一刀）的数据契约测试。
 * 覆盖：坐标合法区间、必填字段齐全、id 唯一、类型枚举闭合、
 * 独立于类别色轴（D1）、以及脏数据 / 空数组的降级红线（K5）。
 */

const TYPES: StrategicSiteType[] = ['chokepoint', 'canal', 'strait', 'cape'];

/* ------------------------------------------------------------------ */
/* 种子数据完整性                                                       */
/* ------------------------------------------------------------------ */
describe('STRATEGIC_SITES 种子数据', () => {
  it('初始种子非空（首刀 8 个要地）', () => {
    expect(STRATEGIC_SITES.length).toBe(8);
  });

  it('lat 恒落在 [-90, 90] 且为有限数', () => {
    for (const s of STRATEGIC_SITES) {
      expect(Number.isFinite(s.lat), `${s.id} lat 非有限数`).toBe(true);
      expect(s.lat).toBeGreaterThanOrEqual(-90);
      expect(s.lat).toBeLessThanOrEqual(90);
    }
  });

  it('lng 恒落在 [-180, 180] 且为有限数', () => {
    for (const s of STRATEGIC_SITES) {
      expect(Number.isFinite(s.lng), `${s.id} lng 非有限数`).toBe(true);
      expect(s.lng).toBeGreaterThanOrEqual(-180);
      expect(s.lng).toBeLessThanOrEqual(180);
    }
  });

  it('必填字段齐全（id / name / type / importance）', () => {
    for (const s of STRATEGIC_SITES) {
      expect(typeof s.id).toBe('string');
      expect(s.id.length).toBeGreaterThan(0);
      expect(typeof s.name).toBe('string');
      expect(s.name.length).toBeGreaterThan(0);
      expect(TYPES).toContain(s.type);
      expect([1, 2, 3]).toContain(s.importance);
    }
  });

  it('id 两两唯一（渲染 key 不撞车）', () => {
    const ids = STRATEGIC_SITES.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('name 两两唯一（同名标签会在地图上叠字）', () => {
    const names = STRATEGIC_SITES.map((s) => s.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it('每个 type 都有中文标签，无遗漏', () => {
    for (const t of TYPES) {
      expect(STRATEGIC_SITE_TYPE_LABEL[t]).toBeTruthy();
    }
    expect(Object.keys(STRATEGIC_SITE_TYPE_LABEL).sort()).toEqual([...TYPES].sort());
  });

  it('note 若存在则为非空字符串', () => {
    for (const s of STRATEGIC_SITES) {
      if (s.note !== undefined) {
        expect(typeof s.note).toBe('string');
        expect(s.note.length).toBeGreaterThan(0);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 独立于类别色轴（D1）                                                 */
/* ------------------------------------------------------------------ */
describe('本层色值独立于 CATEGORY_PALETTE 类别轴（D1）', () => {
  it('固定琥珀金 #fbbf24', () => {
    expect(STRATEGIC_SITE_COLOR).toBe('#fbbf24');
  });

  it('不新增类别键：CATEGORY_PALETTE 中没有 strategic / site 之类的条目', () => {
    expect(CATEGORY_PALETTE).not.toHaveProperty('strategic');
    expect(CATEGORY_PALETTE).not.toHaveProperty('strategicSite');
  });
});

/* ------------------------------------------------------------------ */
/* 显隐持久化常量                                                       */
/* ------------------------------------------------------------------ */
describe('显隐开关常量', () => {
  it('storage 键位独立登记，且默认开启', () => {
    expect(STRATEGIC_SITES_STORAGE_KEY).toBe('kaiyang.strategicSitesVisible');
    expect(STRATEGIC_SITES_DEFAULT_VISIBLE).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* validStrategicSites：降级红线（K5）                                  */
/* ------------------------------------------------------------------ */
describe('validStrategicSites: 脏数据降级不抛异常', () => {
  it('缺省入参即校验内置种子，全部通过', () => {
    expect(validStrategicSites()).toHaveLength(STRATEGIC_SITES.length);
  });

  it('空数组 / null → 空数组（不白屏）', () => {
    expect(validStrategicSites([])).toEqual([]);
    expect(validStrategicSites(null)).toEqual([]);
  });

  it('显式传 undefined 等价于缺省，回落内置种子（默认参数语义）', () => {
    expect(validStrategicSites(undefined)).toHaveLength(STRATEGIC_SITES.length);
  });

  it('坐标越界 / 非有限数的项被跳过，其余项照常上图', () => {
    const dirty = [
      { id: 'ok', name: '正常', lat: 10, lng: 10, type: 'strait', importance: 1 },
      { id: 'lat-over', name: '纬度越界', lat: 91, lng: 10, type: 'strait', importance: 1 },
      { id: 'lat-under', name: '纬度越界负', lat: -91, lng: 10, type: 'strait', importance: 1 },
      { id: 'lng-over', name: '经度越界', lat: 10, lng: 181, type: 'strait', importance: 1 },
      { id: 'lng-under', name: '经度越界负', lat: 10, lng: -181, type: 'strait', importance: 1 },
      { id: 'nan', name: 'NaN', lat: NaN, lng: 10, type: 'strait', importance: 1 },
      { id: 'inf', name: 'Infinity', lat: 10, lng: Infinity, type: 'strait', importance: 1 },
      { id: 'str', name: '字符串坐标', lat: '10', lng: 10, type: 'strait', importance: 1 },
    ] as unknown as StrategicSite[];
    const out = validStrategicSites(dirty);
    expect(out.map((s) => s.id)).toEqual(['ok']);
  });

  it('必填字段缺失（无 id / 无 name / 空串）的项被跳过', () => {
    const dirty = [
      { name: '无 id', lat: 1, lng: 1, type: 'strait', importance: 1 },
      { id: '', name: '空 id', lat: 1, lng: 1, type: 'strait', importance: 1 },
      { id: 'no-name', lat: 1, lng: 1, type: 'strait', importance: 1 },
      { id: 'empty-name', name: '', lat: 1, lng: 1, type: 'strait', importance: 1 },
      null,
      undefined,
    ] as unknown as StrategicSite[];
    expect(() => validStrategicSites(dirty)).not.toThrow();
    expect(validStrategicSites(dirty)).toEqual([]);
  });

  it('重复 id 只保留首次出现的一项', () => {
    const dup = [
      { id: 'x', name: '甲', lat: 1, lng: 1, type: 'strait', importance: 1 },
      { id: 'x', name: '乙', lat: 2, lng: 2, type: 'canal', importance: 3 },
    ] as StrategicSite[];
    const out = validStrategicSites(dup);
    expect(out).toHaveLength(1);
    expect(out[0].name).toBe('甲');
  });

  it('非法 type 回落 chokepoint，非法 importance 回落 1', () => {
    const weird = [
      { id: 'w', name: '怪', lat: 1, lng: 1, type: 'nope', importance: 9 },
    ] as unknown as StrategicSite[];
    const out = validStrategicSites(weird);
    expect(out[0].type).toBe('chokepoint');
    expect(out[0].importance).toBe(1);
  });

  it('输出恒满足坐标合法区间（渲染层可直接投影）', () => {
    for (const s of validStrategicSites()) {
      expect(Number.isFinite(s.lat)).toBe(true);
      expect(Number.isFinite(s.lng)).toBe(true);
      expect(Math.abs(s.lat)).toBeLessThanOrEqual(90);
      expect(Math.abs(s.lng)).toBeLessThanOrEqual(180);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 展示辅助                                                             */
/* ------------------------------------------------------------------ */
describe('siteScale / siteTooltipText', () => {
  it('siteScale 随重要度单调递增，非法输入回落 1', () => {
    expect(siteScale(1)).toBe(1);
    expect(siteScale(2)).toBeGreaterThan(siteScale(1));
    expect(siteScale(3)).toBeGreaterThan(siteScale(2));
    expect(siteScale(undefined)).toBe(1);
    expect(siteScale(NaN)).toBe(1);
  });

  it('siteTooltipText 全中文，含名称 / 类型 / 重要度，note 存在时追加', () => {
    const withNote = siteTooltipText(STRATEGIC_SITES[0]);
    expect(withNote).toContain(STRATEGIC_SITES[0].name);
    expect(withNote).toContain('海峡');
    expect(withNote).toContain('重要度');

    const noNote = siteTooltipText({
      id: 'n',
      name: '无备注要地',
      lat: 0,
      lng: 0,
      type: 'cape',
      importance: 1,
    });
    expect(noNote).toBe('无备注要地 · 海角 · 重要度 1');
  });
});
