import { describe, it, expect } from 'vitest';
import { adaptNewsGeo } from '@/lib/newsGeoAdapter';
import { CATEGORY_PALETTE } from '@/config/theme';
import type { NewsGeoEvent, NewsGeoRaw } from '@/types/contracts';

/* ------------------------------------------------------------------ */
/* 入参降级（K5 红线：任何路径不抛异常）                                  */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 入参降级', () => {
  it('raw=null → 空数组', () => {
    expect(adaptNewsGeo(null)).toEqual([]);
  });

  it('raw=undefined → 空数组', () => {
    expect(adaptNewsGeo(undefined)).toEqual([]);
  });

  it('raw 为非对象（字符串 / 数字）→ 空数组', () => {
    expect(adaptNewsGeo('garbage' as unknown as NewsGeoRaw)).toEqual([]);
    expect(adaptNewsGeo(42 as unknown as NewsGeoRaw)).toEqual([]);
  });

  it('events 字段缺省 → 空数组', () => {
    expect(adaptNewsGeo({ schema_version: '1.0' } as unknown as NewsGeoRaw)).toEqual([]);
  });

  it('events 非数组 → 空数组', () => {
    expect(adaptNewsGeo({ events: 'not-array' as unknown as NewsGeoRaw['events'] })).toEqual([]);
  });

  it('events 为空数组 → 空数组（§2.7 业务态）', () => {
    expect(adaptNewsGeo({ events: [] })).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* 类别 / 形状 / id 命名空间（K2 / K6）                                  */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 类别 / 形状 / id 命名空间', () => {
  const sample: NewsGeoRaw = {
    schema_version: '1.0',
    updated: '2026-08-01T00:00:00Z',
    events: [
      {
        id: 'gdelt-1',
        lat: 35.6892,
        lng: 51.389,
        event_type: 'conflict',
        intensity: 72,
        country: 'IRN',
        location_name: 'Tehran, Iran',
      },
    ],
  };

  it('event_type=conflict → category 归入 "conflict"，shape 取 layerCategories（circle）', () => {
    const pts = adaptNewsGeo(sample);
    expect(pts).toHaveLength(1);
    expect(pts[0].category).toBe('conflict');
    expect(pts[0].shape).toBe('circle');
  });

  it('event_type 非 conflict → category 仍为 "news"', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'p', lat: 0, lng: 0, event_type: 'protest', intensity: 30, country: 'X' },
        { id: 'u', lat: 1, lng: 1, event_type: 'unknown', intensity: 30, country: 'X' },
      ],
    });
    expect(pts.every((p) => p.category === 'news')).toBe(true);
  });

  it('id 必须带 "newsgeo:" 命名空间前缀（K2，多图层合并防撞车）', () => {
    const pts = adaptNewsGeo(sample);
    expect(pts[0].id).toBe('newsgeo:gdelt-1');
    // 绝对不带空名前缀
    expect(pts[0].id.startsWith('newsgeo:')).toBe(true);
  });

  it('conflict 事件着 conflict 类别色（红 red）；非 conflict 着 news 色（青 cyan），均 status=ok', () => {
    const conflictPts = adaptNewsGeo(sample);
    expect(conflictPts[0].color).toBe(CATEGORY_PALETTE.conflict);
    expect(conflictPts[0].status).toBe('ok');
    const newsPts = adaptNewsGeo({
      events: [
        { id: 'p', lat: 0, lng: 0, event_type: 'protest', intensity: 30, country: 'X' },
      ],
    });
    expect(newsPts[0].color).toBe(CATEGORY_PALETTE.news);
    expect(newsPts[0].status).toBe('ok');
  });

  it('合法事件：value=intensity，weight=value/100 夹到 [0,1]，severity="高"（>66）', () => {
    const pts = adaptNewsGeo(sample);
    expect(pts[0].value).toBe(72);
    expect(pts[0].weight).toBeCloseTo(0.72, 5);
    expect(pts[0].severity).toBe('高');
  });
});

/* ------------------------------------------------------------------ */
/* 字段容错与规整                                                       */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 字段容错与规整', () => {
  it('intensity 缺省 → 该条被跳过，不进 missing 通道（intensity 由天枢归一，不二次折算）', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'no-intensity', lat: 0, lng: 0, event_type: 'protest', intensity: NaN, country: 'X' },
      ],
    });
    expect(pts).toEqual([]);
  });

  it('intensity 越界 [-30 / 220] → 夹到 [0,100]', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: -30, country: 'X' },
        { id: 'b', lat: 0, lng: 0, event_type: 'x', intensity: 220, country: 'X' },
      ],
    });
    expect(pts.map((p) => p.value)).toEqual([0, 100]);
  });

  it('intensity 浮点毛刺 (66.66666…) → 归整到 2 位小数', () => {
    const pts = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 66.66666666, country: 'X' }],
    });
    expect(pts[0].value).toBe(66.67);
  });

  it('坐标非有限数（NaN / Infinity）→ 整条跳过', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'nan-l', lat: NaN, lng: 10, event_type: 'x', intensity: 50, country: 'X' },
        { id: 'inf-g', lat: 10, lng: Infinity, event_type: 'x', intensity: 50, country: 'X' },
      ],
    });
    expect(pts).toEqual([]);
  });

  it('坐标越界（|lat|>90 / |lng|>180）→ 整条跳过，不画到 (0,0)', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'oob-lat', lat: 95, lng: 10, event_type: 'x', intensity: 50, country: 'X' },
        { id: 'oob-lng', lat: 10, lng: 200, event_type: 'x', intensity: 50, country: 'X' },
        { id: 'ok', lat: 12.34, lng: 56.78, event_type: 'x', intensity: 50, country: 'X' },
      ],
    });
    expect(pts.map((p) => p.id)).toEqual(['newsgeo:ok']);
  });

  it('id 缺失 → 跳过该条', () => {
    const pts = adaptNewsGeo({
      events: [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: '' as any, lat: 0, lng: 0, event_type: 'x', intensity: 50, country: 'X' },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: undefined as any, lat: 0, lng: 0, event_type: 'x', intensity: 50, country: 'X' },
        { id: 'good', lat: 0, lng: 0, event_type: 'x', intensity: 50, country: 'X' },
      ],
    });
    expect(pts.map((p) => p.id)).toEqual(['newsgeo:good']);
  });

  it('重复 id → 只保留先出现者（避免图层点位 id 撞车）', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'dup', lat: 10, lng: 10, event_type: 'first', intensity: 50, country: 'A' },
        { id: 'dup', lat: 20, lng: 20, event_type: 'second', intensity: 60, country: 'B' },
      ],
    });
    expect(pts).toHaveLength(1);
    expect(pts[0].id).toBe('newsgeo:dup');
    // 取先出现者 → 第一条的 lat/lng/group
    expect(pts[0].lat).toBe(10);
    expect(pts[0].lng).toBe(10);
    expect(pts[0].group).toBe('first · A');
  });
});

/* ------------------------------------------------------------------ */
/* 展示字段：label / group / rawMetric / note                            */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 展示字段', () => {
  it('label: location_name 存在 → 取 location_name；缺失 → 回落 country', () => {
    const withLoc = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'protest', intensity: 30, country: 'IRN', location_name: 'Tehran, Iran' },
      ],
    });
    const withoutLoc = adaptNewsGeo({
      events: [
        { id: 'b', lat: 0, lng: 0, event_type: 'protest', intensity: 30, country: 'IRN' },
      ],
    });
    expect(withLoc[0].label).toBe('Tehran, Iran');
    expect(withoutLoc[0].label).toBe('IRN');
  });

  it('group: 含 event_type + country，便于一眼看懂', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'conflict', intensity: 30, country: 'IRN' },
      ],
    });
    expect(pts[0].group).toBe('conflict · IRN');
  });

  it('event_type 未知/缺失 → 降级为 "unknown"，group 显示 unknown', () => {
    const pts = adaptNewsGeo({
      events: [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: 'a', lat: 0, lng: 0, event_type: '' as any, intensity: 30, country: 'X' },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: 'b', lat: 0, lng: 0, event_type: null as any, intensity: 30, country: 'X' },
      ],
    });
    expect(pts).toHaveLength(2);
    expect(pts.every((p) => p.group === 'unknown · X')).toBe(true);
  });

  it('country 缺失 → 降级为 "未知"，不留空白', () => {
    const pts = adaptNewsGeo({
      events: [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: '' as any },
      ],
    });
    expect(pts[0].group).toContain('未知');
  });

  it('rawMetric：mention_count 与 theme 同时存在 → "提及 N 次 · THEME"', () => {
    const pts = adaptNewsGeo({
      events: [
        {
          id: 'a',
          lat: 0,
          lng: 0,
          event_type: 'x',
          intensity: 30,
          country: 'X',
          mention_count: 42,
          theme: 'TAX_FNCACT',
        },
      ],
    });
    expect(pts[0].rawMetric).toBe('提及 42 次 · TAX_FNCACT');
  });

  it('rawMetric：仅有 theme（无 mention_count）→ 只显示 theme', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', theme: 'TAX_FNCACT' },
      ],
    });
    expect(pts[0].rawMetric).toBe('TAX_FNCACT');
  });

  it('rawMetric：都缺 → undefined（不进 tooltip）', () => {
    const pts = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X' }],
    });
    expect(pts[0].rawMetric).toBeUndefined();
  });

  it('note：透传 event_date，缺失则 undefined', () => {
    const withDate = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', event_date: '20260728' },
      ],
    });
    const withoutDate = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X' }],
    });
    expect(withDate[0].note).toBe('20260728');
    expect(withoutDate[0].note).toBeUndefined();
  });
});

/* ------------------------------------------------------------------ */
/* 与图层体系的契约                                                    */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 与图层体系的契约', () => {
  it('所有点位 category="news"，与现有图层类别一致 → LayerTreePanel 计数天然合并', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: '1', lat: 10, lng: 10, event_type: 'x', intensity: 50, country: 'X' },
        { id: '2', lat: 20, lng: 20, event_type: 'y', intensity: 30, country: 'Y' },
      ],
    });
    expect(pts.every((p) => p.category === 'news')).toBe(true);
  });

  it('intensity=0：weight=0，severity="低"（阈值 < 40）', () => {
    const pts = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 0, country: 'X' }],
    });
    expect(pts[0].weight).toBe(0);
    expect(pts[0].severity).toBe('低');
  });

  it('intensity=100：weight=1，severity="高"（≥66）', () => {
    const pts = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 100, country: 'X' }],
    });
    expect(pts[0].weight).toBe(1);
    expect(pts[0].severity).toBe('高');
  });
});

/* ------------------------------------------------------------------ */
/* XSS 输入消毒（2026-08-11 路线 A 防线二）                              */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: XSS 输入消毒', () => {
  it('location_name 超长 → 截断到 120 字符并补省略号，label 不含原始尾段', () => {
    const longName = 'A'.repeat(200);
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', location_name: longName },
      ],
    });
    expect(pts[0].label).toHaveLength(121); // 120 + '…'
    expect(pts[0].label).toContain('…');
  });

  it('location_name 含控制字符 → 剥离控制字符（保留可见文本）', () => {
    const dirty = 'Tehran\u0000\u0001Iran';
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', location_name: dirty },
      ],
    });
    expect(pts[0].label).toBe('TehranIran');
  });

  it('theme 为空字符串 / 纯空白 → 降级 undefined，不进 rawMetric', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', theme: '   ' },
      ],
    });
    expect(pts[0].rawMetric).toBeUndefined();
  });

  it('HTML 转义由渲染层 pointTooltipHtml 统一完成（此处不清洗 <>& 等字符，避免双重转义）', () => {
    const pts = adaptNewsGeo({
      events: [
        {
          id: 'a',
          lat: 0,
          lng: 0,
          event_type: 'x',
          intensity: 30,
          country: 'X',
          location_name: '<img src=x onerror=alert(1)>',
        },
      ],
    });
    // 适配层保留原文（渲染层 escapeHtml 负责转义）
    expect(pts[0].label).toBe('<img src=x onerror=alert(1)>');
  });
});
