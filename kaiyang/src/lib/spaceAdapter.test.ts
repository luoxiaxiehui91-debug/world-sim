import { describe, it, expect } from 'vitest';
import { adaptSpace } from '@/lib/spaceAdapter';
import { categoryColor } from '@/config/layerCategories';
import type { SpaceLaunchRaw } from '@/types/contracts';

const sampleRaw: SpaceLaunchRaw = {
  status: 'ok',
  fetched_at: '2026-08-14T14:00:00Z',
  launches_count: 3,
  launches: [
    { name: 'Falcon 9 | USSF-366', net: '2026-08-15T21:52:00Z', status: 'Go', rocket: 'Falcon 9', provider: 'SpaceX', pad_name: 'SLC-4E', lat: 34.632, lng: -120.611, type: 'upcoming' },
    { name: 'Long March 5 | X', net: '2026-08-10T00:00:00Z', status: 'Launch Successful', rocket: 'Long March 5', provider: 'CASC', pad_name: 'Wenchang', lat: 19.62, lng: 110.95, type: 'previous' },
    { name: 'Soyuz | Y', net: '2026-08-12T00:00:00Z', status: 'Launch Successful', rocket: 'Soyuz 2.1a', provider: 'Roscosmos', pad_name: 'Baikonur', lat: 45.92, lng: 63.34, type: 'previous' },
  ],
};

describe('adaptSpace（08-14 Next Spaceflight 发射 → RiskPoint[]）', () => {
  it('null / 空 launches 降级为空数组（K5 不白屏）', () => {
    expect(adaptSpace(null)).toEqual([]);
    expect(adaptSpace({ ...sampleRaw, launches: [] })).toEqual([]);
    expect(adaptSpace(undefined as unknown as SpaceLaunchRaw)).toEqual([]);
  });

  it('正常转换：id 前缀 space:，pad 坐标映射，坐标越界跳过', () => {
    const pts = adaptSpace(sampleRaw);
    expect(pts).toHaveLength(3);
    expect(pts[0].id.startsWith('space:')).toBe(true);
    expect(pts[0].lat).toBe(34.632);
    expect(pts[0].lng).toBe(-120.611);
    expect(pts[0].label).toBe('Falcon 9 | USSF-366');
    expect(pts[0].category).toBe('space');
    const bad: SpaceLaunchRaw = {
      ...sampleRaw,
      launches: [...sampleRaw.launches!, { name: 'Bad', lat: 999, lng: 0, type: 'upcoming' }],
    };
    expect(adaptSpace(bad)).toHaveLength(3);
  });

  it('value 恒 null + severity 中性「太空」（非风险语义，air/thermal 教训复用）', () => {
    for (const p of adaptSpace(sampleRaw)) {
      expect(p.value).toBeNull();
      expect(p.severity).toBe('太空');
      expect(p.weight).toBe(0.5);
    }
  });

  it('note 含时间/状态/火箭，upcoming 与 previous 文案区分', () => {
    const pts = adaptSpace(sampleRaw);
    expect(pts[0].note).toContain('计划');
    expect(pts[0].note).toContain('2026-08-15');
    expect(pts[0].note).toContain('Go');
    expect(pts[0].note).toContain('Falcon 9');
    expect(pts[1].note).toContain('已完成');
    expect(pts[1].note).toContain('Launch Successful');
  });

  it('颜色走 space 类别色', () => {
    const pts = adaptSpace(sampleRaw);
    expect(pts[0].color).toBe(categoryColor('space', 'ok'));
  });
});
