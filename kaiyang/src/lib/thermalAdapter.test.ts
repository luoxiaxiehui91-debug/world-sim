import { describe, it, expect } from 'vitest';
import { adaptThermal, MIN_THERMAL_COUNT } from '@/lib/thermalAdapter';
import { categoryColor } from '@/config/layerCategories';
import type { FirmsRaw } from '@/types/contracts';

const sampleRaw: FirmsRaw = {
  status: 'ok',
  fetched_at: '2026-08-14T00:00:00Z',
  total_hotspots: 10,
  hotspots: [
    { lat: 12.5, lng: 105.5, count: 200, frp_max: 130.2, high_conf: 2 },
    { lat: 40.5, lng: -120.5, count: 80, frp_max: 45.1, high_conf: 1 },
    { lat: -1.5, lng: 36.5, count: 50, frp_max: 8.3, high_conf: 0 },
  ],
};

describe('adaptThermal（08-14 FIRMS 1° 网格火点 → RiskPoint[]）', () => {
  it('null / 空 hotspots 降级为空数组（K5 不白屏）', () => {
    expect(adaptThermal(null)).toEqual([]);
    expect(adaptThermal({ ...sampleRaw, hotspots: [] })).toEqual([]);
    expect(adaptThermal(undefined as unknown as FirmsRaw)).toEqual([]);
  });

  it('等级筛选：count < MIN_THERMAL_COUNT 的零星火点格不渲染（08-14 用户反馈卡顿）', () => {
    const mixed: FirmsRaw = {
      ...sampleRaw,
      hotspots: [
        ...sampleRaw.hotspots!,
        { lat: 10, lng: 10, count: MIN_THERMAL_COUNT - 1, frp_max: 1, high_conf: 0 },
        { lat: 11, lng: 11, count: 1, frp_max: 0.5, high_conf: 0 },
      ],
    };
    expect(adaptThermal(mixed)).toHaveLength(3); // 200/80/50 保留，49/1 滤掉
  });

  it('正常转换：id 前缀 thermal:，weight = count 归一化（最密网格=1）', () => {
    const pts = adaptThermal(sampleRaw);
    expect(pts).toHaveLength(3);
    expect(pts[0].id).toBe('thermal:12.5,105.5');
    expect(pts[0].lat).toBe(12.5);
    expect(pts[0].lng).toBe(105.5);
    expect(pts[0].weight).toBe(1);   // 200/max200
    expect(pts[1].weight).toBeCloseTo(0.4); // 80/max200
    expect(pts[2].weight).toBeCloseTo(0.25); // 50/max200
    expect(pts[0].category).toBe('thermal');
  });

  it('value 恒 null + severity 中性「火点活跃」（非风险语义，air 教训复用）', () => {
    for (const p of adaptThermal(sampleRaw)) {
      expect(p.value).toBeNull();
      expect(p.severity).toBe('火点活跃');
      expect(p.aggCount).toBeUndefined();
    }
  });

  it('note 含真实火点数 / FRP / 高置信（hover 看详情，替代风险值数字）', () => {
    const pts = adaptThermal(sampleRaw);
    expect(pts[0].note).toContain('200 个火点');
    expect(pts[0].note).toContain('130 MW');
    expect(pts[0].note).toContain('高置信 2');
    expect(pts[2].note).toContain('50 个火点');
    expect(pts[2].note).not.toContain('高置信');
  });

  it('坐标越界网格跳过（双保险）', () => {
    const bad: FirmsRaw = {
      ...sampleRaw,
      hotspots: [
        ...sampleRaw.hotspots!,
        { lat: 999, lng: 0, count: 200, frp_max: 1, high_conf: 0 },
        { lat: 0, lng: 190, count: 200, frp_max: 1, high_conf: 0 },
      ],
    };
    expect(adaptThermal(bad)).toHaveLength(3);
  });
});
