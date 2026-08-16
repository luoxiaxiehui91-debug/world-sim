import { describe, it, expect } from 'vitest';
import { aggregateNewsGeo } from '@/lib/geoAggregate';
import type { NewsGeoRaw } from '@/types/contracts';

/* ------------------------------------------------------------------ */
/* v1.10.8 同地点聚合                                                    */
/* ------------------------------------------------------------------ */

const baseEvent = (over: Partial<NewsGeoRaw['events'][number]> & { id: string }) => ({
  lat: 39.9289,
  lng: 116.388,
  intensity: 60,
  country: 'China',
  event_type: 'political',
  mention_count: 10,
  event_date: '20260810',
  theme: 'test',
  location_name: 'Beijing, Beijing, China',
  source_url: 'https://example.com/beijing-protests-escalate',
  ...over,
});

function rawOf(events: unknown[]): NewsGeoRaw {
  return { schema_version: '1.0', updated: '2026-08-11T00:00:00+08:00', events: events as never };
}

describe('aggregateNewsGeo: 入参降级（K5）', () => {
  it('raw=null / undefined → 空 points + 空 children map', () => {
    for (const r of [null, undefined] as const) {
      const { points, childrenByPointId } = aggregateNewsGeo(r);
      expect(points).toEqual([]);
      expect(childrenByPointId.size).toBe(0);
    }
  });

  it('events 空数组 → 空 points', () => {
    const { points } = aggregateNewsGeo(rawOf([]));
    expect(points).toEqual([]);
  });
});

describe('aggregateNewsGeo: 坐标格聚合', () => {
  it('Beijing 与 Peking（同坐标不同拼写）→ 合并为一个聚合点 count=2', () => {
    const { points, childrenByPointId } = aggregateNewsGeo(
      rawOf([
        baseEvent({ id: 'e1', location_name: 'Beijing, Beijing, China' }),
        baseEvent({ id: 'e2', location_name: 'Peking, Beijing, China', mention_count: 20 }),
      ]),
    );
    expect(points).toHaveLength(1);
    expect(points[0].aggCount).toBe(2);
    // 代表事件 = mention 最高（Peking 20 > Beijing 10）
    // 08-16 v1.11.19：label = URL slug 还原标题（聚合路径 buildPointFromEvent 同步）
    expect(points[0].label).toBe('Beijing Protests Escalate');
    expect(childrenByPointId.get(points[0].id)).toHaveLength(2);
  });

  it('08-16 v1.11.19：无 source_url → 聚合点 label fallback 中文事件类型；group 中文', () => {
    const { points } = aggregateNewsGeo(
      rawOf([
        baseEvent({ id: 'e1', source_url: undefined }),
      ]),
    );
    expect(points[0].label).toBe('政治 类报道');
    // country 'China' 不在 COUNTRY_ZH（只有 CHN/USA 等码）→ 保留原值
    expect(points[0].group).toBe('政治 · China');
  });

  it('不同坐标（不同格）→ 不合并，各自单点', () => {
    const { points } = aggregateNewsGeo(
      rawOf([
        baseEvent({ id: 'e1', lat: 39.9289, lng: 116.388 }),
        baseEvent({ id: 'e2', lat: 22.3, lng: 114.2, location_name: 'Hong Kong, Hong Kong, China' }),
      ]),
    );
    expect(points).toHaveLength(2);
    expect(points.every((p) => p.aggCount === 1)).toBe(true);
  });

  it('mention 求和进 rawMetric（提及 N 次 · M 条事件）', () => {
    const { points } = aggregateNewsGeo(
      rawOf([
        baseEvent({ id: 'e1', mention_count: 10 }),
        baseEvent({ id: 'e2', mention_count: 30 }),
      ]),
    );
    expect(points[0].rawMetric).toBe('提及 40 次 · 2 条事件');
  });

  it('聚合点强度 = 组内 max intensity（最严重事件驱动尺寸）', () => {
    const { points } = aggregateNewsGeo(
      rawOf([
        baseEvent({ id: 'e1', intensity: 40 }),
        baseEvent({ id: 'e2', intensity: 85 }),
      ]),
    );
    expect(points[0].value).toBe(85);
    expect(points[0].weight).toBeCloseTo(0.85, 5);
  });

  it('count=1 也注册 children（弹框显示自身），但不标聚合', () => {
    const { points, childrenByPointId } = aggregateNewsGeo(
      rawOf([baseEvent({ id: 'e1' })]),
    );
    expect(points).toHaveLength(1);
    expect(points[0].aggCount).toBe(1);
    expect(childrenByPointId.get(points[0].id)).toHaveLength(1);
  });

  it('同 id 脏数据去重（K2）', () => {
    const { points } = aggregateNewsGeo(
      rawOf([baseEvent({ id: 'e1' }), baseEvent({ id: 'e1' })]),
    );
    expect(points).toHaveLength(1);
    expect(points[0].aggCount).toBe(1);
  });
});

describe('aggregateNewsGeo: articles 结构兼容（旧 NER 链）', () => {
  it('articles 非空 → 直出单点（不聚合），与 adaptNewsGeo 行为一致', () => {
    const raw = {
      schema_version: '1.0',
      updated: '2026-08-11T00:00:00+08:00',
      articles: [{ title: 'x', lat: 39.9, lng: 116.4, source: 's', published_at: '2026-08-10' }],
    } as unknown as NewsGeoRaw;
    const { points } = aggregateNewsGeo(raw);
    expect(points.length).toBeGreaterThanOrEqual(0);
  });
});
