import { describe, it, expect } from 'vitest';
import { adaptThermal } from '@/lib/thermalAdapter';
import { categoryColor } from '@/config/layerCategories';
import type { FirmsRaw } from '@/types/contracts';

const sampleRaw: FirmsRaw = {
  status: 'ok',
  fetched_at: '2026-08-14T00:00:00Z',
  total_hotspots: 4,
  hotspots: [
    { lat: 12.5, lng: 105.5, count: 4, frp_max: 130.2, high_conf: 2 },
    { lat: 40.5, lng: -120.5, count: 2, frp_max: 45.1, high_conf: 1 },
    { lat: -1.5, lng: 36.5, count: 1, frp_max: 8.3, high_conf: 0 },
  ],
};

describe('adaptThermal（08-14 FIRMS 1° 网格火点 → RiskPoint[]）', () => {
  it('null / 空 hotspots 降级为空数组（K5 不白屏）', () => {
    expect(adaptThermal(null)).toEqual([]);
    expect(adaptThermal({ ...sampleRaw, hotspots: [] })).toEqual([]);
    expect(adaptThermal(undefined as unknown as FirmsRaw)).toEqual([]);
  });

  it('正常转换：id 前缀 thermal:，count 归一化 value（最密网格=100）', () => {
    const pts = adaptThermal(sampleRaw);
    expect(pts).toHaveLength(3);
    expect(pts[0].id).toBe('thermal:12.5,105.5');
    expect(pts[0].lat).toBe(12.5);
    expect(pts[0].lng).toBe(105.5);
    expect(pts[0].value).toBe(100); // 4/max4
    expect(pts[1].value).toBe(50);  // 2/max4
    expect(pts[2].value).toBe(25);  // 1/max4
    expect(pts[0].category).toBe('thermal');
  });

  it('aggCount = 网格火点数（渲染计数徽标）；note 含 FRP 与高置信', () => {
    const pts = adaptThermal(sampleRaw);
    expect(pts[0].aggCount).toBe(4);
    expect(pts[0].note).toContain('130 MW');
    expect(pts[0].note).toContain('高置信 2');
    expect(pts[2].aggCount).toBe(1);
    expect(pts[2].note).not.toContain('高置信');
  });

  it('颜色/severity 走常规风险档位（火点密度 = 热异常强度）', () => {
    const pts = adaptThermal(sampleRaw);
    expect(pts[0].color).toBe(categoryColor('thermal', 'ok'));
    expect(pts[0].severity).not.toBe('SDR');
    expect(pts[0].severity).toBeTruthy();
  });

  it('坐标越界网格跳过（双保险）', () => {
    const bad: FirmsRaw = {
      ...sampleRaw,
      hotspots: [
        ...sampleRaw.hotspots!,
        { lat: 999, lng: 0, count: 3, frp_max: 1, high_conf: 0 },
        { lat: 0, lng: 190, count: 3, frp_max: 1, high_conf: 0 },
      ],
    };
    expect(adaptThermal(bad)).toHaveLength(3);
  });
});
