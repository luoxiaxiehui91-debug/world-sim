import { describe, it, expect } from 'vitest';
import { adaptAirRoutes } from '@/lib/airRoutesAdapter';
import { CATEGORY_PALETTE } from '@/config/theme';
import type { AirRoutesRaw } from '@/types/contracts';

const sampleRaw: AirRoutesRaw = {
  status: 'ok',
  as_of: '2026-08-14T08:00:00Z',
  scope: 'global',
  schema_version: '1',
  routes_count: 3,
  airports_indexed: 7698,
  routes: [
    { from: 'PEK', from_lat: 40.08, from_lng: 116.58, to: 'JFK', to_lat: 40.64, to_lng: -73.78, flights: 20 },
    { from: 'NRT', from_lat: 35.76, from_lng: 140.39, to: 'TPE', to_lat: 25.08, to_lng: 121.23, flights: 10 },
    { from: 'LOS', from_lat: 6.58, from_lng: 3.32, to: 'CDG', to_lat: 49.01, to_lng: 2.55, flights: 5 },
  ],
};

describe('adaptAirRoutes（08-14 air 全球航线网 → RiskArc[]）', () => {
  it('null / 空 routes 降级为空数组（K5 不白屏）', () => {
    expect(adaptAirRoutes(null)).toEqual([]);
    expect(adaptAirRoutes({ ...sampleRaw, routes: [] })).toEqual([]);
    expect(adaptAirRoutes(undefined as unknown as AirRoutesRaw)).toEqual([]);
  });

  it('正常转换：id 前缀 airroute:，颜色固定 air 翡翠绿（非风险色轴）', () => {
    const arcs = adaptAirRoutes(sampleRaw);
    expect(arcs).toHaveLength(3);
    expect(arcs[0].id).toBe('airroute:PEK__JFK');
    expect(arcs[0].startLat).toBe(40.08);
    expect(arcs[0].endLng).toBe(-73.78);
    expect(arcs[0].fromLabel).toBe('PEK');
    expect(arcs[0].toLabel).toBe('JFK');
    expect(arcs[0].startColor).toBe(CATEGORY_PALETTE.air);
    expect(arcs[0].endColor).toBe(CATEGORY_PALETTE.air);
  });

  it('intensity = 繁忙度线性归一化（20-100），top1 为 100、非风险语义', () => {
    const arcs = adaptAirRoutes(sampleRaw);
    // flights 20/10/5，max=20 → 100 / 60 / 40
    expect(arcs[0].intensity).toBe(100);
    expect(arcs[1].intensity).toBe(60);
    expect(arcs[2].intensity).toBe(40);
  });

  it('坐标越界的航线跳过（双保险，不画到异常位置）', () => {
    const bad: AirRoutesRaw = {
      ...sampleRaw,
      routes: [
        ...sampleRaw.routes!,
        { from: 'BAD', from_lat: 999, from_lng: 0, to: 'X', to_lat: 0, to_lng: 0, flights: 3 },
        { from: 'BAD2', from_lat: 0, from_lng: 0, to: 'X2', to_lat: -91, to_lng: 0, flights: 2 },
      ],
    };
    expect(adaptAirRoutes(bad)).toHaveLength(3);
  });

  it('flights 非正数 / 缺失不炸（Math.max 兜底）', () => {
    const weird: AirRoutesRaw = {
      ...sampleRaw,
      routes: [{ from: 'A', from_lat: 0, from_lng: 0, to: 'B', to_lat: 1, to_lng: 1, flights: 0 }],
    };
    const arcs = adaptAirRoutes(weird);
    expect(arcs).toHaveLength(1);
    expect(Number.isFinite(arcs[0].intensity)).toBe(true);
  });
});
