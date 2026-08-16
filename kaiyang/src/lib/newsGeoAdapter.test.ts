import { describe, it, expect } from 'vitest';
import { adaptNewsGeo, urlSlugToTitle, EVENT_TYPE_ZH, COUNTRY_ZH } from '@/lib/newsGeoAdapter';
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
  it('intensity 缺省 → 该条被跳过，不进 missing 通道', () => {
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

  it('坐标越界 → 整条跳过', () => {
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

  it('重复 id → 只保留先出现者', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'dup', lat: 10, lng: 10, event_type: 'first', intensity: 50, country: 'A' },
        { id: 'dup', lat: 20, lng: 20, event_type: 'second', intensity: 60, country: 'B' },
      ],
    });
    expect(pts).toHaveLength(1);
    expect(pts[0].id).toBe('newsgeo:dup');
    expect(pts[0].lat).toBe(10);
    expect(pts[0].lng).toBe(10);
    // 'first' 不在 EVENT_TYPE_ZH → 原值保留；'A' 不在 COUNTRY_ZH → 原值
    expect(pts[0].group).toBe('first · A');
  });
});

/* ------------------------------------------------------------------ */
/* 展示字段（08-16 v2：label = slug → 中文类型兜底；group 中文）           */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 展示字段', () => {
  it('08-16 v2 label：source_url 有有效 slug → 取 slug 还原的英文标题（首字母大写）', () => {
    const pts = adaptNewsGeo({
      events: [
        {
          id: 'a',
          lat: 0,
          lng: 0,
          event_type: 'political',
          intensity: 30,
          country: 'USA',
          source_url: 'https://www.themarysue.com/federal-judge-threatens-doj-with-contempt-as.html',
        },
      ],
    });
    // slug "federal-judge-threatens-doj-with-contempt-as" 47 字符 < 70 → 不截断，无 …
    expect(pts[0].label).toBe('Federal Judge Threatens Doj With Contempt As');
  });

  it('08-16 v2 label：无 source_url → fallback 到中文事件类型「政治 类报道」', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'political', intensity: 30, country: 'X' },
      ],
    });
    expect(pts[0].label).toBe('政治 类报道');
  });

  it('08-16 v2 label：event_type=conflict → 「冲突 类报道」；protest → 「抗议 类报道」', () => {
    const c = adaptNewsGeo({
      events: [
        { id: 'c', lat: 0, lng: 0, event_type: 'conflict', intensity: 30, country: 'X' },
      ],
    });
    const p = adaptNewsGeo({
      events: [
        { id: 'p', lat: 0, lng: 0, event_type: 'protest', intensity: 30, country: 'X' },
      ],
    });
    expect(c[0].label).toBe('冲突 类报道');
    expect(p[0].label).toBe('抗议 类报道');
  });

  it('08-16 v2 label：未知 event_type → fallback 「unknown 类报道」（中文映射表兜底）', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'mysterious_type', intensity: 30, country: 'X' },
      ],
    });
    expect(pts[0].label).toBe('mysterious_type 类报道');
  });

  it('08-16 v2 group：含中文事件类型 + 中文国家「冲突 · 伊朗」', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'conflict', intensity: 30, country: 'IRN' },
      ],
    });
    expect(pts[0].group).toBe('冲突 · 伊朗');
  });

  it('08-16 v2 group：未映射国家保留 ISO 码「政治 · X」', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'political', intensity: 30, country: 'X' },
      ],
    });
    expect(pts[0].group).toBe('政治 · X');
  });

  it('event_type 未知/缺失 → group 显示 "unknown · X"（country 不映射保留原值）', () => {
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

  it('country 缺失 → 降级为 "未知"', () => {
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
          id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X',
          mention_count: 42, theme: 'TAX_FNCACT',
        },
      ],
    });
    expect(pts[0].rawMetric).toBe('提及 42 次 · TAX_FNCACT');
  });

  it('rawMetric：仅有 theme → 只显示 theme', () => {
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

  it('sourceUrl：透传 source_url（弹框「查看新闻原文」用）', () => {
    const pts = adaptNewsGeo({
      events: [
        {
          id: 'a', lat: 0, lng: 0, event_type: 'political', intensity: 30, country: 'USA',
          source_url: 'https://example.com/abc',
        },
      ],
    });
    expect(pts[0].sourceUrl).toBe('https://example.com/abc');
  });
});

/* ------------------------------------------------------------------ */
/* urlSlugToTitle 单元测试（08-16 v2 工具）                              */
/* ------------------------------------------------------------------ */
describe('urlSlugToTitle', () => {
  it('标准 slug → Title Case + 去扩展名', () => {
    expect(urlSlugToTitle('https://example.com/2026/08/15/federal-judge-threatens-doj.html'))
      .toBe('Federal Judge Threatens Doj');
  });

  it('长 slug → 截断到 70 字符 + …', () => {
    const longSlug = 'a'.repeat(100);
    const url = `https://example.com/${longSlug}.html`;
    const t = urlSlugToTitle(url);
    expect(t).not.toBeNull();
    expect(t!.endsWith('…')).toBe(true);
    expect(t!.length).toBeLessThanOrEqual(71); // 70 + …
  });

  it('扩展名去 .htm / .aspx / .php', () => {
    expect(urlSlugToTitle('https://example.com/foo.htm')).toBe('Foo');
    expect(urlSlugToTitle('https://example.com/foo.aspx')).toBe('Foo');
    expect(urlSlugToTitle('https://example.com/foo.php')).toBe('Foo');
  });

  it('纯数字 slug（如日期 / ID）→ null', () => {
    expect(urlSlugToTitle('https://example.com/20260815')).toBeNull();
    expect(urlSlugToTitle('https://example.com/12345678')).toBeNull();
  });

  it('无 slug（仅根路径）→ null', () => {
    expect(urlSlugToTitle('https://example.com/')).toBeNull();
    expect(urlSlugToTitle('https://example.com')).toBeNull();
  });

  it('null / 空 / 非 URL → null', () => {
    expect(urlSlugToTitle(null)).toBeNull();
    expect(urlSlugToTitle(undefined)).toBeNull();
    expect(urlSlugToTitle('')).toBeNull();
    expect(urlSlugToTitle('not a url')).toBeNull();
  });

  it('_ 和 - 都视为单词分隔符', () => {
    expect(urlSlugToTitle('https://example.com/foo_bar-baz.html')).toBe('Foo Bar Baz');
  });
});

/* ------------------------------------------------------------------ */
/* EVENT_TYPE_ZH / COUNTRY_ZH 映射表测试                                 */
/* ------------------------------------------------------------------ */
describe('新闻映射表常量', () => {
  it('EVENT_TYPE_ZH 覆盖实测 3 个 event_type 值', () => {
    expect(EVENT_TYPE_ZH.political).toBe('政治');
    expect(EVENT_TYPE_ZH.conflict).toBe('冲突');
    expect(EVENT_TYPE_ZH.protest).toBe('抗议');
  });

  it('COUNTRY_ZH 含常用国家码', () => {
    expect(COUNTRY_ZH.USA).toBe('美国');
    expect(COUNTRY_ZH.CHN).toBe('中国');
    expect(COUNTRY_ZH.RUS).toBe('俄罗斯');
  });
});

/* ------------------------------------------------------------------ */
/* 与图层体系的契约                                                    */
/* ------------------------------------------------------------------ */
describe('adaptNewsGeo: 与图层体系的契约', () => {
  it('所有点位 category="news"（conflict 例外），与现有图层类别一致', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: '1', lat: 10, lng: 10, event_type: 'x', intensity: 50, country: 'X' },
        { id: '2', lat: 20, lng: 20, event_type: 'y', intensity: 30, country: 'Y' },
      ],
    });
    expect(pts.every((p) => p.category === 'news')).toBe(true);
  });

  it('intensity=0：weight=0，severity="低"', () => {
    const pts = adaptNewsGeo({
      events: [{ id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 0, country: 'X' }],
    });
    expect(pts[0].weight).toBe(0);
    expect(pts[0].severity).toBe('低');
  });

  it('intensity=100：weight=1，severity="高"', () => {
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
  it('theme 为空字符串 / 纯空白 → 降级 undefined，不进 rawMetric', () => {
    const pts = adaptNewsGeo({
      events: [
        { id: 'a', lat: 0, lng: 0, event_type: 'x', intensity: 30, country: 'X', theme: '   ' },
      ],
    });
    expect(pts[0].rawMetric).toBeUndefined();
  });

  it('HTML 转义由渲染层 pointTooltipHtml 统一完成；不可信 URL（javascript:/data: 含特殊字符）被 sanitizeUrl 丢弃', () => {
    const pts = adaptNewsGeo({
      events: [
        {
          id: 'a', lat: 0, lng: 0, event_type: 'political', intensity: 30, country: 'USA',
          source_url: 'javascript:alert(1)',
        },
      ],
    });
    // 不可信 URL 被 sanitizeUrl 拒 → source_url=undefined → slug=null → label fallback 中文类型
    expect(pts[0].label).not.toContain('<');
    expect(pts[0].label).not.toContain('javascript');
    expect(pts[0].label).toBe('政治 类报道');
  });
});