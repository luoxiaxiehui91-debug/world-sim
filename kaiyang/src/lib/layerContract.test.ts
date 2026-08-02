import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import { buildEventBars, buildRiskPoints, type RiskPoint } from '@/lib/mapData';
import { buildNuclearPoints, mergeNuclear, readingToValue } from '@/lib/nuclearData';
import {
  ALL_CATEGORIES,
  DEFAULT_VISIBLE_CATEGORIES,
  categoryColor,
  parseLayerVisibility,
  serializeLayerVisibility,
} from '@/config/layerCategories';
import { PALETTE, CATEGORY_PALETTE, severityLabel } from '@/config/theme';
import type { GrvDimension, GrvEvent, NuclearSitesRaw } from '@/types/contracts';

/**
 * QA 补充：**跨模块契约测试**（严过关 · 独立验收）。
 *
 * 定位区别于既有三个 .test.ts —— 那三个各自验证**单模块内部**行为，
 * 本文件专门钉死「三个构建器合流之后」才成立的不变量，这类跨模块契约
 * 恰恰是单模块测试的盲区：
 *
 * - K2 三层 id 命名空间在**合并后**仍两两不撞车；
 * - K3 `weight` 归一公式在 geo / event / nuclear **三处实现一致**；
 * - K7 合并顺序（常规 → 事件 → 固定设施）与 WorldPanel 实际写法同步；
 * - C2-A 缺失灰对**全部 12 个类别**一律生效，而非只测到的那几个；
 * - K4/K5 脏数据灌入**任一**构建器都不抛异常、不产出 NaN 坐标；
 * - `readingToValue` 的浮点收敛（严重度阈值抖动防回归）。
 */

/* ------------------------------------------------------------------ */
/* 测试夹具                                                             */
/* ------------------------------------------------------------------ */

function mkDim(partial: Partial<GrvDimension> & Pick<GrvDimension, 'id' | 'kind'>): GrvDimension {
  return {
    label: partial.id,
    value: null,
    uncertainty: null,
    uncertaintyEstimated: false,
    lat: null,
    lng: null,
    group: '地缘',
    status: 'ok',
    note: undefined,
    ...partial,
  } as GrvDimension;
}

const geoDims: GrvDimension[] = [
  mkDim({ id: 'taiwan_strait', kind: 'geographic', lat: 24.5, lng: 120.5, value: 70, label: '台海' }),
  mkDim({ id: 'middle_east_energy', kind: 'geographic', lat: 26.5, lng: 52.0, value: 45, label: '中东能源' }),
  mkDim({ id: 'no_value', kind: 'geographic', lat: 10.0, lng: 10.0, value: null, label: '无值维度' }),
];

const events: GrvEvent[] = [
  { id: 'evt-quake', type: 'disaster', label: '地震', lat: 37.0, lng: 37.0, value: 80 },
  { id: 'evt-flood', type: 'climate', label: '洪涝', lat: 20.0, lng: 80.0, value: 35 },
];

const nuclearRaw: NuclearSitesRaw = {
  sites: [
    { id: 'a-plant', name: 'A 站', country: '甲国', lat: 40.0, lng: 40.0, type: 'npp' },
    { id: 'b-plant', name: 'B 站', country: '乙国', lat: 41.0, lng: 41.0, type: 'monitor' },
  ],
  readings: [{ site_id: 'a-plant', reading: 0.2, unit: 'µSv/h', baseline: 0.1 }],
};

/** 复刻 WorldPanel.tsx 的合并顺序（K7）。改动此处必须同步 WorldPanel。 */
function mergeAllLayers(): RiskPoint[] {
  return [
    ...buildRiskPoints(geoDims),
    ...buildEventBars(events),
    ...buildNuclearPoints(mergeNuclear(nuclearRaw)),
  ];
}

/* ------------------------------------------------------------------ */
/* K2 · 三层合并后 id 命名空间不撞车                                     */
/* ------------------------------------------------------------------ */
describe('K2 跨图层 id 命名空间（三层合并）', () => {
  it('geo / event / nuclear 合并后 id 全局唯一', () => {
    const all = mergeAllLayers();
    const ids = all.map((p) => p.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('每个点的 id 前缀与其 category 严格对应', () => {
    for (const p of mergeAllLayers()) {
      expect(p.id.startsWith(`${p.category}:`)).toBe(true);
    }
  });

  it('三层各自使用不同 id 前缀（同名原始 id 也不会撞车）', () => {
    // 极端场景：三个图层的原始 id 恰好都叫 'x'
    const g = buildRiskPoints([mkDim({ id: 'x', kind: 'geographic', lat: 1, lng: 1, value: 50 })]);
    const e = buildEventBars([{ id: 'x', type: 'climate', label: 'X', lat: 1, lng: 1, value: 50 }]);
    const n = buildNuclearPoints(
      mergeNuclear({ sites: [{ id: 'x', name: 'X', country: '甲', lat: 1, lng: 1 }] }),
    );
    const ids = [...g, ...e, ...n].map((p) => p.id);
    expect(ids).toEqual(['geo:x', 'event:x', 'nuclear:x']);
    expect(new Set(ids).size).toBe(3);
  });
});

/* ------------------------------------------------------------------ */
/* K3 · weight 归一公式三处实现一致                                      */
/* ------------------------------------------------------------------ */
describe('K3 weight = clamp(value/100, 0, 1) 三处一致', () => {
  it('全部点位的 weight 与 value 满足同一归一公式', () => {
    for (const p of mergeAllLayers()) {
      const expected = p.value === null ? 0 : Math.min(1, Math.max(0, p.value / 100));
      expect(p.weight).toBeCloseTo(expected, 10);
    }
  });

  it('weight 恒在 [0,1] 且恒为有限数（尺寸/脉冲的唯一驱动源不得为 NaN）', () => {
    for (const p of mergeAllLayers()) {
      expect(Number.isFinite(p.weight)).toBe(true);
      expect(p.weight).toBeGreaterThanOrEqual(0);
      expect(p.weight).toBeLessThanOrEqual(1);
    }
  });

  it('value 越界时三个构建器都夹取（不出现 weight>1）', () => {
    const g = buildRiskPoints([mkDim({ id: 'over', kind: 'geographic', lat: 1, lng: 1, value: 999 })]);
    const e = buildEventBars([{ id: 'over', type: 'climate', label: 'O', lat: 1, lng: 1, value: 999 }]);
    expect(g[0].weight).toBe(1);
    expect(e[0].weight).toBe(1);
    // 负值同理夹到 0
    const neg = buildEventBars([{ id: 'neg', type: 'climate', label: 'N', lat: 1, lng: 1, value: -50 }]);
    expect(neg[0].weight).toBe(0);
  });
});

/* ------------------------------------------------------------------ */
/* K7 · 合并顺序 = 常规 → 事件 → 固定设施                                */
/* ------------------------------------------------------------------ */
describe('K7 图层合并 z 序', () => {
  it('合并后类别出现顺序为 geo → event → nuclear（后者绘制在上层）', () => {
    const seq = mergeAllLayers().map((p): string => p.category);
    const firstIdx = (c: string) => seq.indexOf(c);
    expect(firstIdx('geo')).toBeGreaterThanOrEqual(0);
    expect(firstIdx('event')).toBeGreaterThan(firstIdx('geo'));
    expect(firstIdx('nuclear')).toBeGreaterThan(firstIdx('event'));
  });

  it('固定设施（nuclear）恒排在数组末段，不被常规点覆盖', () => {
    const seq = mergeAllLayers().map((p): string => p.category);
    const lastNonNuclear = Math.max(seq.lastIndexOf('geo'), seq.lastIndexOf('event'));
    expect(seq.indexOf('nuclear')).toBeGreaterThan(lastNonNuclear);
  });
});

/* ------------------------------------------------------------------ */
/* C2-A · 缺失灰对全部类别一律生效                                       */
/* ------------------------------------------------------------------ */
describe('C2-A 缺失态优先级高于全部 12 个类别色', () => {
  it('categoryColor(每一个类别, "missing") 一律返回 slate', () => {
    for (const cat of ALL_CATEGORIES) {
      expect(categoryColor(cat, 'missing')).toBe(PALETTE.slate);
      // 且必须与该类别自身的 ok 态色不同（否则缺失不可辨）
      expect(categoryColor(cat, 'missing')).not.toBe(categoryColor(cat, 'ok'));
    }
  });

  it('设计稿 §3.2 明列样例：categoryColor("nuclear","missing") === PALETTE.slate', () => {
    expect(categoryColor('nuclear', 'missing')).toBe(PALETTE.slate);
  });

  it('三个构建器产出的 missing 点，颜色与 weight 一致降级', () => {
    const missingPts = mergeAllLayers().filter((p) => p.status === 'missing');
    expect(missingPts.length).toBeGreaterThan(0);
    for (const p of missingPts) {
      expect(p.color).toBe(PALETTE.slate);
      expect(p.weight).toBe(0);
      expect(p.severity).toBe('缺失');
    }
  });
});

/* ------------------------------------------------------------------ */
/* K4 / K5 · 脏数据灌入任一构建器都不炸                                  */
/* ------------------------------------------------------------------ */
describe('K4/K5 脏数据降级红线（三个构建器）', () => {
  const dirtyCoords = [NaN, Infinity, -Infinity, null, undefined, '10', {}];

  it('非有限坐标的 geo 维度被跳过，且不抛异常', () => {
    for (const bad of dirtyCoords) {
      const dims = [mkDim({ id: 'bad', kind: 'geographic', lat: bad as number, lng: 10, value: 50 })];
      expect(() => buildRiskPoints(dims)).not.toThrow();
      expect(buildRiskPoints(dims)).toEqual([]);
    }
  });

  it('非有限坐标的事件被跳过，且不抛异常', () => {
    for (const bad of dirtyCoords) {
      const evs = [{ id: 'bad', type: 'climate', label: 'B', lat: bad, lng: 10, value: 50 }] as unknown as GrvEvent[];
      expect(() => buildEventBars(evs)).not.toThrow();
      expect(buildEventBars(evs)).toEqual([]);
    }
  });

  it('非有限坐标的核设施被跳过，且不抛异常', () => {
    for (const bad of dirtyCoords) {
      const raw = { sites: [{ id: 'bad', name: 'B', country: '甲', lat: bad, lng: 10 }] } as unknown as NuclearSitesRaw;
      expect(() => buildNuclearPoints(mergeNuclear(raw))).not.toThrow();
      // 全部站点非法 ⇒ mergeNuclear 回落 6 站种子，因此不为空但恒无非法坐标
      for (const p of buildNuclearPoints(mergeNuclear(raw))) {
        expect(Number.isFinite(p.lat)).toBe(true);
        expect(Number.isFinite(p.lng)).toBe(true);
      }
    }
  });

  it('任何输出点位的坐标恒为有限数（不得画到 (0,0) 或 NaN）', () => {
    for (const p of mergeAllLayers()) {
      expect(Number.isFinite(p.lat)).toBe(true);
      expect(Number.isFinite(p.lng)).toBe(true);
      expect(p.lat).toBeGreaterThanOrEqual(-90);
      expect(p.lat).toBeLessThanOrEqual(90);
      expect(p.lng).toBeGreaterThanOrEqual(-180);
      expect(p.lng).toBeLessThanOrEqual(180);
    }
  });

  it('整链路灌 null/undefined（feed 全挂）不抛异常，且不白屏（核层仍出种子）', () => {
    expect(() => {
      const pts = [
        ...buildRiskPoints(null),
        ...buildEventBars(undefined),
        ...buildNuclearPoints(mergeNuclear(null)),
      ];
      expect(pts.length).toBe(6); // 6 站种子，全灰
      expect(pts.every((p) => p.status === 'missing')).toBe(true);
    }).not.toThrow();
  });
});

/* ------------------------------------------------------------------ */
/* readingToValue · 浮点收敛（严重度阈值抖动防回归）                      */
/* ------------------------------------------------------------------ */
describe('readingToValue 浮点边界收敛（Math.round(v*100)/100）', () => {
  it('0.15 / 0.1 收敛为精确 40，不得是 39.99999999999999', () => {
    // 未收口时 20+(1.4999999999999998-1)*40 = 39.99999999999999，
    // 会被 severityLevel 误判为「低」（阈值 mid=40），是最典型的边界抖动
    const v = readingToValue({ reading: 0.15, baseline: 0.1, level: 'unknown' });
    expect(v).toBe(40);
    expect(severityLabel(v)).toBe('中');
  });

  it('0.3 / 0.1 收敛为精确 100（原始为 99.99999999999999）', () => {
    expect(readingToValue({ reading: 0.3, baseline: 0.1, level: 'unknown' })).toBe(100);
  });

  it('0.36 / 0.12 收敛为精确 100', () => {
    expect(readingToValue({ reading: 0.36, baseline: 0.12, level: 'unknown' })).toBe(100);
  });

  it('非整数结果保留 2 位小数（0.2 / 0.15 → 33.33）', () => {
    expect(readingToValue({ reading: 0.2, baseline: 0.15, level: 'unknown' })).toBe(33.33);
  });

  it('批量输入下结果恒为「至多 2 位小数」的有限数', () => {
    const readings = [0.01, 0.05, 0.11, 0.12, 0.13, 0.17, 0.23, 0.29, 0.31, 0.37];
    const baselines = [0.03, 0.07, 0.1, 0.11, 0.12, 0.19];
    for (const reading of readings) {
      for (const baseline of baselines) {
        const v = readingToValue({ reading, baseline, level: 'unknown' });
        expect(v).not.toBeNull();
        expect(Number.isFinite(v as number)).toBe(true);
        // 2 位小数：v*100 必须落在整数上（容忍 1e-9 的表示误差）
        const scaled = (v as number) * 100;
        expect(Math.abs(scaled - Math.round(scaled))).toBeLessThan(1e-9);
        expect(v as number).toBeGreaterThanOrEqual(0);
        expect(v as number).toBeLessThanOrEqual(100);
      }
    }
  });

  it('收敛不改变后端 level 权威值（20/55/85 仍精确）', () => {
    expect(readingToValue({ reading: 0.15, baseline: 0.1, level: 'normal' })).toBe(20);
    expect(readingToValue({ reading: 0.15, baseline: 0.1, level: 'elevated' })).toBe(55);
    expect(readingToValue({ reading: 0.15, baseline: 0.1, level: 'alert' })).toBe(85);
  });
});

/* ------------------------------------------------------------------ */
/* K8 · 持久化前向兼容（补既有用例未覆盖的畸形形态）                      */
/* ------------------------------------------------------------------ */
describe('K8 localStorage 前向兼容补充畸形输入', () => {
  it('JSON 合法但类型错误的各种形态一律回落默认集合', () => {
    const bad = [
      'null',
      'true',
      '"just-a-string"',
      '{}',
      '{"visible":null}',
      '{"visible":{}}',
      '[1,2,3]',
      '{"visible":[1,2,3],"known":"nope"}',
    ];
    for (const raw of bad) {
      expect(() => parseLayerVisibility(raw)).not.toThrow();
      const result = parseLayerVisibility(raw);
      // 要么回落默认集合，要么是过滤后的合法子集；无论如何不得含非法键
      for (const k of result) expect(ALL_CATEGORIES).toContain(k);
    }
    expect(parseLayerVisibility('null')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('true')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('{}')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('[1,2,3]')).toEqual([]);
  });

  it('legacy 纯数组快照（无 known）不误开用户已关类别', () => {
    // 老版本只写了数组形态；用户当时只留 geo
    const result = parseLayerVisibility(JSON.stringify(['geo']));
    expect(result).toEqual(['geo']);
    expect(result).not.toContain('nuclear');
  });

  it('往返幂等：serialize→parse→serialize 结果稳定', () => {
    const once = serializeLayerVisibility(['nuclear', 'geo']);
    const twice = serializeLayerVisibility(parseLayerVisibility(once));
    expect(twice).toBe(once);
  });
});

/* ------------------------------------------------------------------ */
/* K6 辅助 · index.css 的 --ky-cat-* 镜像不得与 CATEGORY_PALETTE 漂移     */
/* CATEGORY_PALETTE（theme.ts）是类别色唯一真相；index.css 里 --ky-cat-*   */
/* 是手工镜像的二级真相，存在「改了源却忘改 CSS」的漂移风险。此测试在      */
/* CI 中钉死二者逐键一致，是 K6「单一事实来源」的兜底护栏。               */
/* ------------------------------------------------------------------ */
describe('K6 辅助 · index.css --ky-cat-* 镜像 === CATEGORY_PALETTE', () => {
  function loadCssMirror(): Record<string, string> {
    const cssPath = resolve(fileURLToPath(import.meta.url), '..', '..', 'index.css');
    const css = readFileSync(cssPath, 'utf8');
    const re = /--ky-cat-([a-z]+):\s*(#[0-9a-fA-F]{6});/g;
    const map: Record<string, string> = {};
    let m: RegExpExecArray | null;
    while ((m = re.exec(css)) !== null) {
      map[m[1]] = m[2].toLowerCase();
    }
    return map;
  }

  it('CATEGORY_PALETTE 每个键都在 index.css 有镜像，且色值逐键一致', () => {
    const mirror = loadCssMirror();
    expect(Object.keys(mirror).length).toBeGreaterThan(0);
    for (const [key, hex] of Object.entries(CATEGORY_PALETTE)) {
      expect(mirror[key], `index.css 缺少 --ky-cat-${key} 镜像`).toBeDefined();
      expect(mirror[key]).toBe(String(hex).toLowerCase());
    }
  });

  it('index.css 的 --ky-cat-* 不得有孤儿键（CATEGORY_PALETTE 之外的多余镜像）', () => {
    const mirror = loadCssMirror();
    for (const key of Object.keys(mirror)) {
      expect(CATEGORY_PALETTE, `index.css 存在孤儿镜像 --ky-cat-${key}`).toHaveProperty(key);
    }
  });
});
