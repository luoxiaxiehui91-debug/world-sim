import { describe, it, expect } from 'vitest';
import {
  mergeNuclear,
  readingToValue,
  buildNuclearPoints,
  formatReading,
  NUCLEAR_LEVEL_LABEL,
} from '@/lib/nuclearData';
import type { NuclearRow } from '@/lib/nuclearData';
import { NUCLEAR_SEED } from '@/config/nuclearSites';
import { CATEGORY_PALETTE } from '@/config/theme';
import type { NuclearSitesRaw } from '@/types/contracts';

/* ------------------------------------------------------------------ */
/* 静态种子：坐标契约（K4 四位小数 + 有限数）                            */
/* ------------------------------------------------------------------ */
describe('NUCLEAR_SEED: 6 站种子契约', () => {
  it('恰好 6 站，id 唯一', () => {
    expect(NUCLEAR_SEED).toHaveLength(6);
    expect(new Set(NUCLEAR_SEED.map((s) => s.id)).size).toBe(6);
  });

  it('坐标为有限数且在地理范围内，小数不超过 4 位（K4）', () => {
    for (const s of NUCLEAR_SEED) {
      expect(Number.isFinite(s.lat)).toBe(true);
      expect(Number.isFinite(s.lng)).toBe(true);
      expect(s.lat).toBeGreaterThanOrEqual(-90);
      expect(s.lat).toBeLessThanOrEqual(90);
      expect(s.lng).toBeGreaterThanOrEqual(-180);
      expect(s.lng).toBeLessThanOrEqual(180);
      expect(s.lat).toBe(Number(s.lat.toFixed(4)));
      expect(s.lng).toBe(Number(s.lng.toFixed(4)));
    }
  });

  it('每站都有中文名与国家，type 取值合法', () => {
    for (const s of NUCLEAR_SEED) {
      expect(s.name.length).toBeGreaterThan(0);
      expect(s.country.length).toBeGreaterThan(0);
      expect(['npp', 'monitor', 'legacy', undefined]).toContain(s.type);
    }
  });

  it('种子不含任何读数字段（读数只能来自后端，前端不编造）', () => {
    for (const s of NUCLEAR_SEED) {
      expect(s).not.toHaveProperty('reading');
      expect(s).not.toHaveProperty('level');
    }
  });
});

/* ------------------------------------------------------------------ */
/* readingToValue：归一化（§3.4）                                       */
/* ------------------------------------------------------------------ */
describe('readingToValue: 读数归一化到 0~100', () => {
  it('后端 level 优先：normal=20 / elevated=55 / alert=85', () => {
    expect(readingToValue({ reading: null, baseline: null, level: 'normal' })).toBe(20);
    expect(readingToValue({ reading: null, baseline: null, level: 'elevated' })).toBe(55);
    expect(readingToValue({ reading: null, baseline: null, level: 'alert' })).toBe(85);
  });

  it('后端 level 覆盖 reading/baseline 推断结果', () => {
    // 倍数推断本会得到 20 + (10-1)*40 = 380 → 夹到 100；但 level 优先，取 20
    expect(readingToValue({ reading: 1, baseline: 0.1, level: 'normal' })).toBe(20);
  });

  it('level=unknown 时回落 reading/baseline 推断', () => {
    // ratio = 1 → 20 + 0 = 20
    expect(readingToValue({ reading: 0.1, baseline: 0.1, level: 'unknown' })).toBe(20);
    // ratio = 2 → 20 + 40 = 60
    expect(readingToValue({ reading: 0.2, baseline: 0.1, level: 'unknown' })).toBe(60);
  });

  it('推断结果夹取到 [0,100]', () => {
    expect(readingToValue({ reading: 100, baseline: 0.1, level: 'unknown' })).toBe(100);
    expect(readingToValue({ reading: 0, baseline: 1, level: 'unknown' })).toBe(0);
  });

  it('仅有 reading 无 baseline → null（不瞎猜，走缺失灰）', () => {
    expect(readingToValue({ reading: 0.12, baseline: null, level: 'unknown' })).toBeNull();
  });

  it('baseline <= 0 → null（不做除零）', () => {
    expect(readingToValue({ reading: 0.12, baseline: 0, level: 'unknown' })).toBeNull();
    expect(readingToValue({ reading: 0.12, baseline: -1, level: 'unknown' })).toBeNull();
  });

  it('什么都没有 / 入参 nullish → null，且不抛异常', () => {
    expect(readingToValue({ reading: null, baseline: null, level: 'unknown' })).toBeNull();
    expect(readingToValue(null)).toBeNull();
    expect(readingToValue(undefined)).toBeNull();
  });

  it('非有限读数（NaN / Infinity）→ null', () => {
    expect(readingToValue({ reading: NaN, baseline: 1, level: 'unknown' })).toBeNull();
    expect(readingToValue({ reading: 1, baseline: Infinity, level: 'unknown' })).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* mergeNuclear：四级降级矩阵（K5）                                     */
/* ------------------------------------------------------------------ */
describe('mergeNuclear: feed 覆盖种子 + 缺失降级', () => {
  it('raw=null（文件缺失） → 回落 6 站种子，读数全 null', () => {
    const rows = mergeNuclear(null);
    expect(rows).toHaveLength(6);
    expect(rows.every((r) => r.reading === null)).toBe(true);
    expect(rows.every((r) => r.value === null)).toBe(true);
    expect(rows.every((r) => r.level === 'unknown')).toBe(true);
  });

  it('raw=undefined → 同样回落种子，不抛异常', () => {
    expect(() => mergeNuclear(undefined)).not.toThrow();
    expect(mergeNuclear(undefined)).toHaveLength(6);
  });

  it('sites 为空数组 → 回落种子（空是合法业务态）', () => {
    const rows = mergeNuclear({ sites: [], readings: [] });
    expect(rows).toHaveLength(6);
    expect(rows[0].site.id).toBe(NUCLEAR_SEED[0].id);
  });

  it('sites 非空 → 完全覆盖种子（后端为准）', () => {
    const raw: NuclearSitesRaw = {
      sites: [{ id: 'x-1', name: '测试站', country: '测试国', lat: 1.2345, lng: 2.3456 }],
    };
    const rows = mergeNuclear(raw);
    expect(rows).toHaveLength(1);
    expect(rows[0].site.id).toBe('x-1');
    expect(rows.some((r) => r.site.id === 'zaporizhzhia')).toBe(false);
  });

  it('readings 按 site_id join，无对应站点的读数被丢弃', () => {
    const raw: NuclearSitesRaw = {
      sites: [
        { id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 },
        { id: 'b', name: 'B', country: '乙', lat: 2, lng: 2 },
      ],
      readings: [
        { site_id: 'a', reading: 0.12, unit: 'µSv/h', level: 'normal', updated: '2025-08-01T00:00:00Z' },
        { site_id: 'ghost', reading: 9.9, unit: 'µSv/h', level: 'alert' },
      ],
    };
    const rows = mergeNuclear(raw);
    expect(rows).toHaveLength(2);
    const a = rows.find((r) => r.site.id === 'a')!;
    const b = rows.find((r) => r.site.id === 'b')!;
    expect(a.reading).toBe(0.12);
    expect(a.unit).toBe('µSv/h');
    expect(a.level).toBe('normal');
    expect(a.value).toBe(20);
    expect(a.updated).toBe('2025-08-01T00:00:00Z');
    // 没有读数的站：全部降级为 null / unknown
    expect(b.reading).toBeNull();
    expect(b.unit).toBeNull();
    expect(b.value).toBeNull();
    expect(b.level).toBe('unknown');
  });

  it('readings 缺字段 → 该行降级但不影响其他行', () => {
    const raw: NuclearSitesRaw = {
      sites: [
        { id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 },
        { id: 'b', name: 'B', country: '乙', lat: 2, lng: 2 },
      ],
      readings: [
        { site_id: 'a', reading: null },
        { site_id: 'b', reading: 0.4, baseline: 0.2 },
      ],
    };
    const rows = mergeNuclear(raw);
    expect(rows.find((r) => r.site.id === 'a')!.value).toBeNull();
    // ratio=2 → 60 → elevated
    const b = rows.find((r) => r.site.id === 'b')!;
    expect(b.value).toBe(60);
    expect(b.level).toBe('elevated');
  });

  it('坐标非法 / id 缺失的站点被跳过', () => {
    const raw = {
      sites: [
        { id: 'ok', name: 'OK', country: '甲', lat: 10, lng: 10 },
        { id: '', name: '无 id', country: '甲', lat: 10, lng: 10 },
        { id: 'nan', name: 'NaN 坐标', country: '甲', lat: NaN, lng: 10 },
        { id: 'oob', name: '越界', country: '甲', lat: 200, lng: 10 },
      ],
    } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    expect(rows.map((r) => r.site.id)).toEqual(['ok']);
  });

  it('全部站点非法 → 回落种子而非返回空（不白屏）', () => {
    const raw = {
      sites: [{ id: 'bad', name: 'X', country: '甲', lat: 999, lng: 999 }],
    } as unknown as NuclearSitesRaw;
    expect(mergeNuclear(raw)).toHaveLength(6);
  });

  it('重复 site id 只保留先出现者', () => {
    const raw: NuclearSitesRaw = {
      sites: [
        { id: 'dup', name: '先', country: '甲', lat: 1, lng: 1 },
        { id: 'dup', name: '后', country: '乙', lat: 2, lng: 2 },
      ],
    };
    const rows = mergeNuclear(raw);
    expect(rows).toHaveLength(1);
    expect(rows[0].site.name).toBe('先');
  });

  it('脏 level 值被忽略，走推断兜底', () => {
    const raw = {
      sites: [{ id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 }],
      readings: [{ site_id: 'a', reading: 0.3, baseline: 0.1, level: 'CRITICAL' }],
    } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    // ratio=3 → 20 + 80 = 100 → alert
    expect(rows[0].value).toBe(100);
    expect(rows[0].level).toBe('alert');
  });

  it('显式 level:"unknown" 等同缺失，回退推断（value 与 level 自洽）', () => {
    const raw = {
      sites: [{ id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 }],
      // 显式 unknown + 读数 + baseline 齐全 → 比值推断 value=60，level 应回退为 elevated
      readings: [{ site_id: 'a', reading: 0.2, baseline: 0.1, level: 'unknown' }],
    } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    expect(rows[0].value).toBe(60);
    // 修复前：level 被 ?? 钉成 'unknown'，与 value=60 不自洽（地图用类别色、面板却显「未知」）
    expect(rows[0].level).toBe('elevated');
  });

  it('显式 level:"unknown" 且无读数 → value=null 且 level=unknown（仍自洽）', () => {
    const raw = {
      sites: [{ id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 }],
      readings: [{ site_id: 'a', baseline: 0.1, level: 'unknown' }],
    } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    expect(rows[0].value).toBeNull();
    expect(rows[0].level).toBe('unknown');
  });

  it('level 与 value 自洽：level==="unknown" ⟺ value===null', () => {
    const raw = {
      sites: [
        { id: 'a', name: 'A', country: '甲', lat: 1, lng: 1 },
        { id: 'b', name: 'B', country: '乙', lat: 2, lng: 2 },
        { id: 'c', name: 'C', country: '丙', lat: 3, lng: 3 },
      ] as unknown as NuclearSitesRaw['sites'],
      // a: 合法 level 优先；b: 显式 unknown+读数 → 推断；c: 无读数 → 缺失
      readings: [
        { site_id: 'a', reading: 0.05, baseline: 0.1, level: 'normal' },
        { site_id: 'b', reading: 0.2, baseline: 0.1, level: 'unknown' },
        { site_id: 'c', baseline: 0.1, level: 'unknown' },
      ] as unknown as NuclearSitesRaw['readings'],
    } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    for (const r of rows) {
      expect(r.level === 'unknown').toBe(r.value === null);
    }
    expect(rows.find((r) => r.site.id === 'a')!.level).toBe('normal');
    expect(rows.find((r) => r.site.id === 'b')!.level).toBe('elevated');
    expect(rows.find((r) => r.site.id === 'c')!.level).toBe('unknown');
  });

  it('name / country 缺失时降级为 id / 「未知」，不留空白行', () => {
    const raw = { sites: [{ id: 'bare', lat: 1, lng: 1 }] } as unknown as NuclearSitesRaw;
    const rows = mergeNuclear(raw);
    expect(rows[0].site.name).toBe('bare');
    expect(rows[0].site.country).toBe('未知');
  });
});

/* ------------------------------------------------------------------ */
/* formatReading                                                       */
/* ------------------------------------------------------------------ */
describe('formatReading', () => {
  it('有读数有单位 → 「0.12 µSv/h」', () => {
    expect(formatReading({ reading: 0.12, unit: 'µSv/h' })).toBe('0.12 µSv/h');
  });

  it('有读数无单位 → 只显示数值', () => {
    expect(formatReading({ reading: 0.12, unit: null })).toBe('0.12');
  });

  it('无读数 → null（面板显示「—」）', () => {
    expect(formatReading({ reading: null, unit: 'µSv/h' })).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* buildNuclearPoints：类别 / 形状 / 缺失覆盖                            */
/* ------------------------------------------------------------------ */
describe('buildNuclearPoints: 核设施图层点位', () => {
  const okRow: NuclearRow = {
    site: { id: 'a', name: 'A 站', country: '甲国', lat: 1.0, lng: 2.0, type: 'npp' },
    reading: 0.12,
    unit: 'µSv/h',
    baseline: 0.1,
    updated: '2025-08-01T00:00:00Z',
    level: 'elevated',
    value: 55,
  };

  const missingRow: NuclearRow = {
    site: { id: 'b', name: 'B 站', country: '乙国', lat: 3.0, lng: 4.0, type: 'legacy' },
    reading: null,
    unit: null,
    baseline: null,
    updated: null,
    level: 'unknown',
    value: null,
  };

  it('入参 nullish / 空数组 → 空数组（K5 不抛异常）', () => {
    expect(buildNuclearPoints(null)).toEqual([]);
    expect(buildNuclearPoints(undefined)).toEqual([]);
    expect(buildNuclearPoints([])).toEqual([]);
  });

  it('category=nuclear，shape=diamond，id 带 nuclear: 前缀（K2）', () => {
    const pts = buildNuclearPoints([okRow, missingRow]);
    expect(pts).toHaveLength(2);
    expect(pts.every((p) => p.category === 'nuclear')).toBe(true);
    expect(pts.every((p) => p.shape === 'diamond')).toBe(true);
    expect(pts.map((p) => p.id)).toEqual(['nuclear:a', 'nuclear:b']);
  });

  it('有数点着核设施类别色（明黄）', () => {
    const p = buildNuclearPoints([okRow])[0];
    expect(p.color).toBe(CATEGORY_PALETTE.nuclear);
    expect(p.status).toBe('ok');
    expect(p.value).toBe(55);
    expect(p.weight).toBeCloseTo(0.55);
  });

  it('C2-A：value=null 强制灰 + status=missing + weight=0，类别色不得覆盖', () => {
    const p = buildNuclearPoints([missingRow])[0];
    expect(p.status).toBe('missing');
    expect(p.color).toBe(CATEGORY_PALETTE.missing);
    expect(p.color).not.toBe(CATEGORY_PALETTE.nuclear);
    expect(p.weight).toBe(0);
    expect(p.severity).toBe('缺失');
    expect(p.rawMetric).toBeUndefined();
  });

  it('rawMetric 写入读数原文，group 含国家与类型', () => {
    const p = buildNuclearPoints([okRow])[0];
    expect(p.rawMetric).toBe('0.12 µSv/h');
    expect(p.group).toBe('甲国 · 核电站');
  });

  it('坐标非法的行被跳过（不画到 0,0）', () => {
    const bad: NuclearRow = {
      ...okRow,
      site: { ...okRow.site, id: 'bad', lat: NaN, lng: 10 },
    };
    expect(buildNuclearPoints([bad, okRow]).map((p) => p.id)).toEqual(['nuclear:a']);
  });

  it('端到端：feed 缺失 → 6 个种子菱形灰点，全部无光环（weight=0）', () => {
    const pts = buildNuclearPoints(mergeNuclear(null));
    expect(pts).toHaveLength(6);
    expect(pts.every((p) => p.shape === 'diamond')).toBe(true);
    expect(pts.every((p) => p.color === CATEGORY_PALETTE.missing)).toBe(true);
    expect(pts.every((p) => p.weight === 0)).toBe(true);
    expect(new Set(pts.map((p) => p.id)).size).toBe(6);
  });

  it('端到端：读数就绪 → 该站变类别色且 weight 随严重度上升', () => {
    const raw: NuclearSitesRaw = {
      sites: NUCLEAR_SEED,
      readings: [{ site_id: 'zaporizhzhia', reading: 0.3, unit: 'µSv/h', baseline: 0.1 }],
    };
    const pts = buildNuclearPoints(mergeNuclear(raw));
    const zp = pts.find((p) => p.id === 'nuclear:zaporizhzhia')!;
    expect(zp.color).toBe(CATEGORY_PALETTE.nuclear);
    expect(zp.value).toBe(100);
    expect(zp.weight).toBe(1);
    // 其余 5 站仍是缺失灰
    expect(pts.filter((p) => p.color === CATEGORY_PALETTE.missing)).toHaveLength(5);
  });
});

/* ------------------------------------------------------------------ */
/* 标签表                                                               */
/* ------------------------------------------------------------------ */
describe('NUCLEAR_LEVEL_LABEL', () => {
  it('四个分级都有中文标签', () => {
    expect(NUCLEAR_LEVEL_LABEL.normal).toBe('正常');
    expect(NUCLEAR_LEVEL_LABEL.elevated).toBe('偏高');
    expect(NUCLEAR_LEVEL_LABEL.alert).toBe('告警');
    expect(NUCLEAR_LEVEL_LABEL.unknown).toBe('未知');
  });
});
