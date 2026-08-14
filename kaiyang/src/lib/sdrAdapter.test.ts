import { describe, it, expect } from 'vitest';
import { adaptSdr } from '@/lib/sdrAdapter';
import { categoryColor } from '@/config/layerCategories';
import type { SdrSummaryRaw } from '@/types/contracts';

const sampleRaw: SdrSummaryRaw = {
  status: 'ok',
  fetched_at: '2026-08-14T00:00:00Z',
  total: 3,
  online: 3,
  offline: 0,
  receivers: [
    { id: 'a1', name: 'RX Beijing', lat: 39.9, lon: 116.4, loc: 'Beijing CN', grid: 'OM89', status: 'active', users: '5', updated: 'Thursday, 13-Aug-2026 20:00:00 GMT' },
    { id: 'a2', name: 'RX Nairobi', lat: -1.29, lon: 36.82, loc: 'Nairobi KE', grid: 'KI88', status: 'active', users: '2', updated: 'Thursday, 13-Aug-2026 19:00:00 GMT' },
    { id: 'a3', name: 'RX Offline', lat: 0, lon: 0, loc: 'Nowhere', grid: 'AA00', status: 'offline', users: '0', updated: 'Monday, 01-Aug-2026 00:00:00 GMT' },
  ],
};

describe('adaptSdr（08-14 KiwiSDR 接收器 → RiskPoint[]）', () => {
  it('null / 空 receivers 降级为空数组（K5 不白屏）', () => {
    expect(adaptSdr(null)).toEqual([]);
    expect(adaptSdr({ ...sampleRaw, receivers: [] })).toEqual([]);
    expect(adaptSdr(undefined as unknown as SdrSummaryRaw)).toEqual([]);
  });

  it('正常转换：id 前缀 sdr:，lon→lng 映射，坐标合法', () => {
    const pts = adaptSdr(sampleRaw);
    expect(pts).toHaveLength(3);
    expect(pts[0].id).toBe('sdr:a1');
    expect(pts[0].lat).toBe(39.9);
    expect(pts[0].lng).toBe(116.4);
    expect(pts[0].label).toBe('RX Beijing');
    expect(pts[0].category).toBe('sdr');
  });

  it('active → ok（sdr 色）；offline → missing（灰覆盖类别色，C2-A）', () => {
    const pts = adaptSdr(sampleRaw);
    expect(pts[0].status).toBe('ok');
    expect(pts[0].color).toBe(categoryColor('sdr', 'ok'));
    expect(pts[2].status).toBe('missing');
    expect(pts[2].color).toBe(categoryColor('sdr', 'missing'));
  });

  it('value 恒 null + severity 中性（非风险语义，air 教训）', () => {
    for (const p of adaptSdr(sampleRaw)) {
      expect(p.value).toBeNull();
      expect(p.severity).toBe('SDR');
    }
  });

  it('坐标越界接收器跳过（双保险）', () => {
    const bad: SdrSummaryRaw = {
      ...sampleRaw,
      receivers: [
        ...sampleRaw.receivers!,
        { id: 'b1', name: 'Bad', lat: 999, lon: 0, loc: 'X', grid: 'AA', status: 'active', users: '0', updated: '' },
        { id: 'b2', name: 'Bad2', lat: 0, lon: 200, loc: 'X', grid: 'AA', status: 'active', users: '0', updated: '' },
      ],
    };
    expect(adaptSdr(bad)).toHaveLength(3);
  });
});
