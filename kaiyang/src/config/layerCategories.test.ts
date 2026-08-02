import { describe, it, expect } from 'vitest';
import {
  ALL_CATEGORIES,
  DEFAULT_VISIBLE_CATEGORIES,
  FALLBACK_CATEGORY,
  LAYER_CATEGORIES,
  LAYER_VISIBILITY_STORAGE_KEY,
  MAX_POINTS_PER_LAYER,
  MISSING_COLOR,
  categoryColor,
  categoryDef,
  categoryLabel,
  categoryShape,
  parseLayerVisibility,
  resolvePointStatus,
  serializeLayerVisibility,
  toLayerCategory,
  type LayerCategory,
} from '@/config/layerCategories';
import { CATEGORY_PALETTE, PALETTE, SEVERITY_LEGEND, severityColor, severityLabel } from '@/config/theme';

/**
 * 分类图层地基（T-U01）的契约测试。
 * 覆盖：枚举完整性、色值唯一性、缺失覆盖（C2-A）、defaultVisible 合法性、
 * 严重度轴未被破坏（C1-A）、localStorage 前向兼容（K8）。
 */

/* ------------------------------------------------------------------ */
/* 枚举完整性                                                          */
/* ------------------------------------------------------------------ */
describe('layerCategories: 枚举完整性', () => {
  it('ALL_CATEGORIES.length === LAYER_CATEGORIES.length', () => {
    expect(ALL_CATEGORIES).toHaveLength(LAYER_CATEGORIES.length);
  });

  it('共 12 个类别，键两两唯一（osint 已因合规否决永久删除）', () => {
    expect(LAYER_CATEGORIES).toHaveLength(12);
    expect(new Set(ALL_CATEGORIES).size).toBe(12);
    expect(ALL_CATEGORIES).not.toContain('osint' as LayerCategory);
    expect(CATEGORY_PALETTE).not.toHaveProperty('osint');
  });

  it('每个类别键都能在 CATEGORY_PALETTE 中找到同名色（色值单一事实来源）', () => {
    for (const def of LAYER_CATEGORIES) {
      const paletteColor = (CATEGORY_PALETTE as Record<string, string>)[def.key];
      expect(paletteColor).toBeDefined();
      expect(def.color).toBe(paletteColor);
    }
  });

  it('12 个类别色两两不同（色相=类别，同色即不可区分）', () => {
    const colors = LAYER_CATEGORIES.map((d) => d.color.toLowerCase());
    expect(new Set(colors).size).toBe(colors.length);
  });

  it('类别色均为合法 6 位 hex', () => {
    for (const def of LAYER_CATEGORIES) {
      expect(def.color).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it('C3-A 调整后的三个色值与设计稿一致（不得改回红/紫/绿）', () => {
    expect(categoryColor('thermal')).toBe('#fb923c');
    expect(categoryColor('space')).toBe('#818cf8');
    expect(categoryColor('health')).toBe('#a3e635');
  });

  it('每个类别的 phase / shape / defaultVisible 均合法', () => {
    for (const def of LAYER_CATEGORIES) {
      expect(['P0', 'P1', 'P2']).toContain(def.phase);
      expect(['circle', 'diamond', 'triangle', 'square']).toContain(def.shape);
      expect(typeof def.defaultVisible).toBe('boolean');
      expect(def.label.length).toBeGreaterThan(0);
      expect(def.desc.length).toBeGreaterThan(0);
    }
  });

  it('P0 阶段恰好是 geo / event / nuclear 三类', () => {
    const p0 = LAYER_CATEGORIES.filter((d) => d.phase === 'P0').map((d) => d.key);
    expect(p0).toEqual(['geo', 'event', 'nuclear']);
  });

  it('nuclear 与 chokepoint 默认形状为菱形（与相邻色靠形状区分）', () => {
    expect(categoryShape('nuclear')).toBe('diamond');
    expect(categoryShape('chokepoint')).toBe('diamond');
    expect(categoryShape('geo')).toBe('circle');
  });

  it('DEFAULT_VISIBLE_CATEGORIES 是 ALL_CATEGORIES 的子集', () => {
    for (const k of DEFAULT_VISIBLE_CATEGORIES) {
      expect(ALL_CATEGORIES).toContain(k);
    }
  });

  it('护栏常量已预埋且为正整数（§10-N5）', () => {
    expect(Number.isInteger(MAX_POINTS_PER_LAYER)).toBe(true);
    expect(MAX_POINTS_PER_LAYER).toBeGreaterThan(0);
  });
});

/* ------------------------------------------------------------------ */
/* categoryColor：缺失覆盖类别色（C2-A）                                */
/* ------------------------------------------------------------------ */
describe('categoryColor: 缺失态覆盖类别色（C2-A）', () => {
  it('status=missing 时返回 PALETTE.slate，不被任何类别色覆盖', () => {
    expect(categoryColor('nuclear', 'missing')).toBe(PALETTE.slate);
    expect(categoryColor('geo', 'missing')).toBe(PALETTE.slate);
    expect(categoryColor('conflict', 'missing')).toBe(PALETTE.slate);
    expect(MISSING_COLOR).toBe(PALETTE.slate);
    expect(PALETTE.slate).toBe('#64748b');
  });

  it('status=missing 对未知类别同样生效', () => {
    expect(categoryColor(undefined, 'missing')).toBe(PALETTE.slate);
    expect(categoryColor('not-a-category' as LayerCategory, 'missing')).toBe(PALETTE.slate);
  });

  it('status 缺省为 ok，返回类别色', () => {
    expect(categoryColor('geo')).toBe('#5eead4');
    expect(categoryColor('event')).toBe('#fbbf24');
    expect(categoryColor('nuclear')).toBe('#facc15');
  });

  it('未知类别（ok 态）降级为兜底类别色，不抛异常', () => {
    expect(categoryColor(undefined)).toBe(categoryColor(FALLBACK_CATEGORY));
    expect(categoryColor('nope' as LayerCategory)).toBe(categoryColor(FALLBACK_CATEGORY));
  });
});

/* ------------------------------------------------------------------ */
/* 查询辅助函数                                                        */
/* ------------------------------------------------------------------ */
describe('categoryDef / categoryLabel / toLayerCategory', () => {
  it('categoryDef 对已知类别返回定义，对未知返回 undefined', () => {
    expect(categoryDef('nuclear')?.label).toBe('核设施');
    expect(categoryDef(undefined)).toBeUndefined();
    expect(categoryDef('nope' as LayerCategory)).toBeUndefined();
  });

  it('categoryLabel 未知类别时原样回显键，完全缺省时返回「未分类」', () => {
    expect(categoryLabel('geo')).toBe('地缘风险');
    expect(categoryLabel('nope' as LayerCategory)).toBe('nope');
    expect(categoryLabel(undefined)).toBe('未分类');
  });

  it('toLayerCategory 只接受合法键', () => {
    expect(toLayerCategory('geo')).toBe('geo');
    expect(toLayerCategory('nope')).toBeUndefined();
    expect(toLayerCategory(42)).toBeUndefined();
    expect(toLayerCategory(null)).toBeUndefined();
  });
});

/* ------------------------------------------------------------------ */
/* resolvePointStatus：元状态判定                                      */
/* ------------------------------------------------------------------ */
describe('resolvePointStatus: 元状态判定', () => {
  it('上游标记 missing → missing（即使有数值）', () => {
    expect(resolvePointStatus('missing', 70)).toBe('missing');
  });

  it('数值缺失 / 非有限数 → missing', () => {
    expect(resolvePointStatus('ok', null)).toBe('missing');
    expect(resolvePointStatus('ok', undefined)).toBe('missing');
    expect(resolvePointStatus('ok', NaN)).toBe('missing');
    expect(resolvePointStatus('ok', Infinity)).toBe('missing');
    expect(resolvePointStatus(undefined, null)).toBe('missing');
  });

  it('有限数值 + 非 missing → ok（含 0 与负数）', () => {
    expect(resolvePointStatus('ok', 0)).toBe('ok');
    expect(resolvePointStatus('ok', -5)).toBe('ok');
    expect(resolvePointStatus(undefined, 42)).toBe('ok');
  });
});

/* ------------------------------------------------------------------ */
/* 严重度轴未被破坏（C1-A：两轴正交）                                   */
/* ------------------------------------------------------------------ */
describe('严重度轴完好（C1-A）', () => {
  it('severityColor / severityLabel / SEVERITY_LEGEND 仍在且行为未变', () => {
    expect(severityColor(null)).toBe(PALETTE.slate);
    expect(severityColor(10)).toBe(PALETTE.teal);
    expect(severityColor(50)).toBe(PALETTE.amber);
    expect(severityColor(80)).toBe(PALETTE.red);
    expect(severityLabel(80)).toBe('高');
    expect(SEVERITY_LEGEND.map((l) => l.label)).toEqual(['低', '中', '高', '缺失']);
  });

  it('CATEGORY_PALETTE 与 PALETTE 各自独立存在，未互相覆盖', () => {
    expect(PALETTE.teal).toBe('#5eead4');
    expect(CATEGORY_PALETTE.geo).toBe(PALETTE.teal);
    expect(CATEGORY_PALETTE.missing).toBe(PALETTE.slate);
  });
});

/* ------------------------------------------------------------------ */
/* localStorage 可见性持久化（K8）                                      */
/* ------------------------------------------------------------------ */
describe('图层可见性持久化（K8）', () => {
  it('键位与登记一致', () => {
    expect(LAYER_VISIBILITY_STORAGE_KEY).toBe('kaiyang.layerVisibility');
  });

  it('空 / 非法输入 → 默认可见集合，不抛异常', () => {
    expect(parseLayerVisibility(null)).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('{ 坏 JSON')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('123')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
    expect(parseLayerVisibility('{"visible":"nope"}')).toEqual(DEFAULT_VISIBLE_CATEGORIES);
  });

  it('往返一致：序列化后再解析得到同一集合', () => {
    const round = parseLayerVisibility(serializeLayerVisibility(['geo', 'nuclear']));
    expect(round).toEqual(['geo', 'nuclear']);
  });

  it('全部关闭也能正确往返（空数组不被当成非法输入）', () => {
    expect(parseLayerVisibility(serializeLayerVisibility([]))).toEqual([]);
  });

  it('未知类别键被丢弃', () => {
    const raw = JSON.stringify({ visible: ['geo', 'ghost-layer'], known: ALL_CATEGORIES });
    expect(parseLayerVisibility(raw)).toEqual(['geo']);
  });

  it('前向兼容：快照 known 里没有的新类别按 defaultVisible 补入', () => {
    // 模拟"老版本只知道 geo/event"的快照：用户当时关掉了 event
    const legacy = JSON.stringify({ visible: ['geo'], known: ['geo', 'event'] });
    const result = parseLayerVisibility(legacy);
    expect(result).toContain('geo');
    expect(result).not.toContain('event'); // 用户主动关掉的，尊重
    expect(result).toContain('nuclear'); // 新类别，按 defaultVisible 补入
  });

  it('纯数组形态（防御性兼容）原样尊重，不做补入', () => {
    expect(parseLayerVisibility(JSON.stringify(['geo']))).toEqual(['geo']);
  });

  it('解析结果顺序恒与 ALL_CATEGORIES 一致（图例顺序稳定）', () => {
    const raw = JSON.stringify({ visible: ['nuclear', 'geo', 'event'], known: ALL_CATEGORIES });
    expect(parseLayerVisibility(raw)).toEqual(['geo', 'event', 'nuclear']);
  });
});
