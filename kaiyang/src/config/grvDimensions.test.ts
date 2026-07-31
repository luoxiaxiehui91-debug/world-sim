import { describe, it, expect } from 'vitest';
import { getDimDef, GRV_DIMENSIONS, GRV_ARCS } from '@/config/grvDimensions';

/**
 * 验证「事件触发式告警柱」改造在维度定义层的核心契约：
 * 1. climate_risk / disaster_risk 设 renderBar:false，不再画常驻柱；
 * 2. 二者仍保留 kind:'geographic' 与 lat/lng 锚点（供 GRV_ARCS 弧线使用）；
 * 3. GRV_ARCS 仍保留指向二者的联动弧线；
 * 4. 普通 geographic 维度默认 renderBar 视为 true。
 */
describe('grvDimensions: 事件维度 renderBar 契约', () => {
  it('climate_risk 设 renderBar:false，但保留 geographic 锚点 (74,10)', () => {
    const d = getDimDef('climate_risk');
    expect(d).toBeDefined();
    expect(d!.renderBar).toBe(false);
    expect(d!.kind).toBe('geographic');
    expect(d!.lat).toBe(74);
    expect(d!.lng).toBe(10);
  });

  it('disaster_risk 设 renderBar:false，但保留 geographic 锚点 (-2,-80)', () => {
    const d = getDimDef('disaster_risk');
    expect(d).toBeDefined();
    expect(d!.renderBar).toBe(false);
    expect(d!.kind).toBe('geographic');
    expect(d!.lat).toBe(-2);
    expect(d!.lng).toBe(-80);
  });

  it('普通 geographic 维度（如 taiwan_strait）默认 renderBar 为 undefined（视为 true）', () => {
    const d = getDimDef('taiwan_strait');
    expect(d!.kind).toBe('geographic');
    expect(d!.renderBar).toBeUndefined();
  });

  it('GRV_ARCS 仍引用两个事件维度（弧线坐标不能因 renderBar:false 而丢失）', () => {
    expect(GRV_ARCS).toContainEqual(['climate_risk', 'russia_europe']);
    expect(GRV_ARCS).toContainEqual(['disaster_risk', 'india_pacific']);
  });

  it('climate_risk / disaster_risk 在维度总表中存在且仅出现一次', () => {
    const ids = GRV_DIMENSIONS.map((d) => d.id);
    expect(ids.filter((id) => id === 'climate_risk')).toHaveLength(1);
    expect(ids.filter((id) => id === 'disaster_risk')).toHaveLength(1);
  });

  it('getDimDef 对未知 id 返回 undefined', () => {
    expect(getDimDef('not_a_real_dim')).toBeUndefined();
  });
});
