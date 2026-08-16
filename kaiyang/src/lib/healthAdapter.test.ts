import { describe, it, expect } from 'vitest';
import { adaptHealth } from '@/lib/healthAdapter';
import { categoryColor } from '@/config/layerCategories';
import type { HealthGeoRaw } from '@/types/contracts';

const sampleRaw: HealthGeoRaw = {
  status: 'ok',
  fetched_at: '2026-08-15T01:30:00Z',
  events_count: 3,
  events: [
    { doc: 'https://abc.example/cyclosporiasis', date: '20260815013000', lat: 38.8951, lng: -77.0364, loc_name: 'Washington DC', keywords: ['cyclosporiasis', 'outbreak'] },
    { doc: 'https://news.example/measles', date: '20260815010000', lat: 39.3498, lng: -75.5148, loc_name: 'Delaware', keywords: ['measles'] },
    { doc: 'https://news.example/africa', date: '20260815001500', lat: -1.29, lng: 36.82, loc_name: 'Nairobi', keywords: ['cholera'] },
  ],
};

describe('adaptHealth（08-15 GDELT 卫生事件 → RiskPoint[]）', () => {
  it('null / 空 events 降级为空数组（K5 不白屏）', () => {
    expect(adaptHealth(null)).toEqual([]);
    expect(adaptHealth({ ...sampleRaw, events: [] })).toEqual([]);
    expect(adaptHealth(undefined as unknown as HealthGeoRaw)).toEqual([]);
  });

  it('正常转换：id 前缀 health:，坐标映射，关键词进 label', () => {
    const pts = adaptHealth(sampleRaw);
    expect(pts).toHaveLength(3);
    expect(pts[0].id.startsWith('health:')).toBe(true);
    expect(pts[0].lat).toBe(38.8951);
    expect(pts[0].lng).toBe(-77.0364);
    expect(pts[0].label).toContain('cyclosporiasis');
    expect(pts[0].category).toBe('health');
    expect(pts[2].label).toContain('cholera');
  });

  it('value 恒 null + severity 中性「卫生」（非风险语义，air/thermal 教训复用）', () => {
    for (const p of adaptHealth(sampleRaw)) {
      expect(p.value).toBeNull();
      expect(p.severity).toBe('卫生');
      expect(p.weight).toBe(0.5);
    }
  });

  it('note 含关键词/地点/时间（hover 看详情）', () => {
    const pts = adaptHealth(sampleRaw);
    expect(pts[0].note).toContain('cyclosporiasis');
    expect(pts[0].note).toContain('Washington DC');
    expect(pts[0].note).toContain('2026-08-15');
    expect(pts[1].note).toContain('Delaware');
  });

  it('08-16 v2：中文疾病名映射（弹框标题不用点开就知道发生了什么）', () => {
    const pts = adaptHealth(sampleRaw);
    // label 中文优先：环孢子虫病 / 麻疹 / 霍乱
    expect(pts[0].label).toContain('环孢子虫病');
    expect(pts[1].label).toContain('麻疹');
    expect(pts[2].label).toContain('霍乱');
    // 英文关键词保留（可读性兜底）
    expect(pts[0].label).toContain('cyclosporiasis');
    // group 中文
    expect(pts[2].group).toContain('霍乱');
  });

  it('08-16 v2：title（DOC API 回填）优先于中文疾病名 + sourceUrl 原文链接', () => {
    const withTitle: HealthGeoRaw = {
      ...sampleRaw,
      events: [
        { ...sampleRaw.events![0], title: 'FDA inspecting Mexico produce after cyclosporiasis outbreak' },
      ],
    };
    const pts = adaptHealth(withTitle);
    expect(pts[0].label).toBe('FDA inspecting Mexico produce after cyclosporiasis outbreak');
    expect(pts[0].sourceUrl).toBe('https://abc.example/cyclosporiasis');
  });

  it('坐标越界跳过（双保险）', () => {
    const bad: HealthGeoRaw = {
      ...sampleRaw,
      events: [...sampleRaw.events!, { doc: 'x', date: '20260815000000', lat: 999, lng: 0, loc_name: 'bad', keywords: [] }],
    };
    expect(adaptHealth(bad)).toHaveLength(3);
  });

  it('颜色走 health 类别色', () => {
    expect(adaptHealth(sampleRaw)[0].color).toBe(categoryColor('health', 'ok'));
  });
});
