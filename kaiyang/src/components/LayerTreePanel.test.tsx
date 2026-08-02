import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { isValidElement, type ReactElement, type ReactNode } from 'react';
import {
  LayerTreeGroup,
  LayerTreePanel,
  LayerTreeRow,
  LayerTreeView,
  PHASE_LABEL,
  PHASE_ORDER,
  groupByPhase,
  rowStatus,
  type LayerTreePanelProps,
} from '@/components/LayerTreePanel';
import { LAYER_CATEGORIES, type LayerCategory, type LayerPhase } from '@/config/layerCategories';
import type { LayerCountMap } from '@/components/LayerLegend';
import { CATEGORY_PALETTE, withAlpha } from '@/config/theme';

/**
 * 左侧指标树（LayerTreePanel）测试。
 *
 * ⚠ 零新依赖：node 环境无 jsdom / testing-library（与 RegionTabs / SignalStreamPanel 测试同款做法）。
 * - 静态标记用 react-dom 自带的 `renderToStaticMarkup`；
 * - 交互靠**直接调用无 hook 的纯组件**（`LayerTreeView` / `LayerTreeGroup` / `LayerTreeRow`）
 *   拿到元素树，递归找 `<button>` 并手动执行其 `onClick`；
 * - `LayerTreePanel` 是唯一带 `useState` 的薄壳，只用 SSR 渲染断言其默认（全展开）形态。
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyElement = ReactElement<any>;

/** 递归收集元素树里所有 <button>（不会下钻自定义组件，正好用于分层断言）。 */
function collectButtons(node: ReactNode, out: AnyElement[] = []): AnyElement[] {
  if (Array.isArray(node)) {
    for (const c of node) collectButtons(c, out);
    return out;
  }
  if (!isValidElement(node)) return out;
  const el = node as AnyElement;
  if (el.type === 'button') out.push(el);
  collectButtons(el.props?.children as ReactNode, out);
  return out;
}

const ALL_ON = new Set<LayerCategory>(LAYER_CATEGORIES.map((d) => d.key));
const noop = () => {};

function baseProps(over: Partial<LayerTreePanelProps> = {}): LayerTreePanelProps {
  return {
    visible: ALL_ON,
    counts: {},
    onToggle: noop,
    onSetAll: noop,
    missingCount: 0,
    sitesVisible: true,
    onToggleSites: noop,
    ...over,
  };
}

/** 直接调用纯渲染体，拿到元素树（默认全部分组展开）。 */
function viewOf(
  over: Partial<LayerTreePanelProps> = {},
  openPhases: ReadonlySet<LayerPhase> = new Set(PHASE_ORDER),
  onTogglePhase: (p: LayerPhase) => void = noop,
) {
  return LayerTreeView({ ...baseProps(over), openPhases, onTogglePhase });
}

function panelHtml(over: Partial<LayerTreePanelProps> = {}): string {
  return renderToStaticMarkup(<LayerTreePanel {...baseProps(over)} />);
}

describe('LayerTreePanel: 渲染完整性', () => {
  it('渲染全部 12 个类别的中文名（枚举来自 LAYER_CATEGORIES 单一真源）', () => {
    const html = panelHtml();
    expect(LAYER_CATEGORIES).toHaveLength(12);
    for (const def of LAYER_CATEGORIES) {
      expect(html, `应渲染类别「${def.label}」`).toContain(def.label);
    }
  });

  it('渲染战略要地独立行；未提供 onToggleSites 时该行整体不出现', () => {
    expect(panelHtml()).toContain('战略要地');
    const without = renderToStaticMarkup(
      <LayerTreePanel {...baseProps()} onToggleSites={undefined} />,
    );
    expect(without).not.toContain('data-row="sites"');
  });

  it('按 phase 分出 P0 / P1 / P2 三个组头，且顺序为 P0 → P1 → P2', () => {
    const html = panelHtml();
    let cursor = -1;
    for (const phase of PHASE_ORDER) {
      const at = html.indexOf(PHASE_LABEL[phase], cursor + 1);
      expect(at, `${PHASE_LABEL[phase]} 应按 PHASE_ORDER 顺序出现`).toBeGreaterThan(cursor);
      cursor = at;
    }
    expect(html).toContain('data-phase="P0"');
    expect(html).toContain('data-phase="P1"');
    expect(html).toContain('data-phase="P2"');
  });

  it('计数只来自传入的 counts：geo=3 显示 3，未传的类别显示 0（不编造数据）', () => {
    const counts: LayerCountMap = { geo: 3 };
    const geo = LAYER_CATEGORIES.find((d) => d.key === 'geo')!;
    const row = renderToStaticMarkup(
      <LayerTreeRow def={geo} on count={counts.geo ?? 0} onToggle={noop} />,
    );
    expect(row).toContain('>3<');

    const air = LAYER_CATEGORIES.find((d) => d.key === 'air')!;
    const empty = renderToStaticMarkup(
      <LayerTreeRow def={air} on count={counts.air ?? 0} onToggle={noop} />,
    );
    expect(empty).toContain('>0<');
  });

  it('计数使用 tabular-nums 等宽数字，避免开关时列宽跳动', () => {
    expect(panelHtml({ counts: { geo: 12 } })).toContain('tabular-nums');
  });

  it('类别色一律取自 LAYER_CATEGORIES / CATEGORY_PALETTE，组件内不硬编码 hex', () => {
    const html = panelHtml();
    // ShapeSwatch 用 withAlpha(color, 0.55) 填充，命中即证明色值来自单一真源
    expect(html).toContain(withAlpha(CATEGORY_PALETTE.geo, 0.55));
    expect(html).toContain(withAlpha(CATEGORY_PALETTE.nuclear, 0.55));
  });

  it('全部 button 都是 type=button（避免落在表单里被当提交）', () => {
    for (const b of collectButtons(viewOf())) expect(b.props.type).toBe('button');
    const p0 = groupByPhase()[0];
    const headers = collectButtons(
      LayerTreeGroup({
        phase: p0.phase,
        defs: p0.defs,
        visible: ALL_ON,
        counts: {},
        open: true,
        onToggleOpen: noop,
        onToggle: noop,
      }),
    );
    for (const b of headers) expect(b.props.type).toBe('button');
  });
});

describe('LayerTreePanel: 状态灯三态', () => {
  it('rowStatus 纯函数：开+有数=live，开+无数=empty，关=off', () => {
    expect(rowStatus(true, 3)).toBe('live');
    expect(rowStatus(true, 0)).toBe('empty');
    expect(rowStatus(false, 3)).toBe('off');
    expect(rowStatus(false, 0)).toBe('off');
  });

  it('visible 含 geo 且 counts.geo>0 → 该行状态灯 data-status="live"', () => {
    const geo = LAYER_CATEGORIES.find((d) => d.key === 'geo')!;
    const html = renderToStaticMarkup(<LayerTreeRow def={geo} on count={3} onToggle={noop} />);
    expect(html).toContain('data-status="live"');
    expect(html).toContain('data-off="false"');
  });

  it('图层开着但当前范围无数据 → data-status="empty"，不伪装成 live', () => {
    const geo = LAYER_CATEGORIES.find((d) => d.key === 'geo')!;
    const html = renderToStaticMarkup(<LayerTreeRow def={geo} on count={0} onToggle={noop} />);
    expect(html).toContain('data-status="empty"');
    expect(html).not.toContain('data-status="live"');
  });

  it('visible 不含某类别 → 该行 data-off="true" 且状态灯为 off', () => {
    const geo = LAYER_CATEGORIES.find((d) => d.key === 'geo')!;
    const html = renderToStaticMarkup(
      <LayerTreeRow def={geo} on={false} count={5} onToggle={noop} />,
    );
    expect(html).toContain('data-off="true"');
    expect(html).toContain('data-status="off"');
  });
});

describe('LayerTreePanel: 交互回调', () => {
  it('点击类别行回调 onToggle 且参数为该行的类别键', () => {
    const seen: LayerCategory[] = [];
    for (const def of LAYER_CATEGORIES) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const el = LayerTreeRow({ def, on: true, count: 0, onToggle: (k) => seen.push(k) }) as any;
      expect(el.type).toBe('button');
      expect(el.props['aria-pressed']).toBe(true);
      el.props.onClick();
    }
    expect(seen).toEqual(LAYER_CATEGORIES.map((d) => d.key));
  });

  it('点击战略要地行调用 onToggleSites（且不误触 onToggle）', () => {
    let sites = 0;
    const toggled: LayerCategory[] = [];
    const buttons = collectButtons(
      viewOf({ onToggleSites: () => (sites += 1), onToggle: (k) => toggled.push(k) }),
    );
    const siteBtn = buttons.find((b) => b.props['data-row'] === 'sites')!;
    expect(siteBtn).toBeDefined();
    siteBtn.props.onClick();
    expect(sites).toBe(1);
    expect(toggled).toEqual([]);
  });

  it('点击「全开」回调 onSetAll(true)，点击「全关」回调 onSetAll(false)', () => {
    const seen: boolean[] = [];
    // 半开状态：两个按钮都可用
    const half = new Set<LayerCategory>(['geo']);
    const buttons = collectButtons(viewOf({ visible: half, onSetAll: (v) => seen.push(v) }));
    const all = buttons.find((b) => b.props.children === '全开')!;
    const none = buttons.find((b) => b.props.children === '全关')!;
    expect(all.props.disabled).toBe(false);
    expect(none.props.disabled).toBe(false);
    all.props.onClick();
    none.props.onClick();
    expect(seen).toEqual([true, false]);
  });

  it('全开态禁用「全开」、全关态禁用「全关」（与底部图例行为一致）', () => {
    const onAll = collectButtons(viewOf({ visible: ALL_ON }));
    expect(onAll.find((b) => b.props.children === '全开')!.props.disabled).toBe(true);
    expect(onAll.find((b) => b.props.children === '全关')!.props.disabled).toBe(false);

    const offAll = collectButtons(viewOf({ visible: new Set<LayerCategory>() }));
    expect(offAll.find((b) => b.props.children === '全开')!.props.disabled).toBe(false);
    expect(offAll.find((b) => b.props.children === '全关')!.props.disabled).toBe(true);
  });
});

describe('LayerTreePanel: 分组折叠', () => {
  const p0 = groupByPhase().find((g) => g.phase === 'P0')!;

  function group(open: boolean, onToggleOpen: (p: LayerPhase) => void = noop) {
    return {
      phase: p0.phase,
      defs: p0.defs,
      visible: ALL_ON,
      counts: {} as LayerCountMap,
      open,
      onToggleOpen,
      onToggle: noop,
    };
  }

  it('默认展开：P0 组内的「地缘风险」等类别行可见', () => {
    const html = renderToStaticMarkup(<LayerTreeGroup {...group(true)} />);
    for (const def of p0.defs) expect(html).toContain(def.label);
    expect(html).toContain('aria-expanded="true"');
  });

  it('折叠后组内类别行不再渲染，但组头仍在', () => {
    const html = renderToStaticMarkup(<LayerTreeGroup {...group(false)} />);
    for (const def of p0.defs) {
      expect(html, `折叠后不应出现「${def.label}」`).not.toContain(def.label);
    }
    expect(html).toContain(PHASE_LABEL.P0);
    expect(html).toContain('aria-expanded="false"');
  });

  it('点击组头回调 onToggleOpen 且参数为该组的 phase', () => {
    const seen: LayerPhase[] = [];
    const header = collectButtons(LayerTreeGroup(group(true, (p) => seen.push(p))))[0];
    header.props.onClick();
    expect(seen).toEqual(['P0']);
  });

  it('组头显示「本组已开数 / 本组总数」', () => {
    const only = new Set<LayerCategory>([p0.defs[0].key]);
    const html = renderToStaticMarkup(<LayerTreeGroup {...group(true)} visible={only} />);
    expect(html).toContain(`1/${p0.defs.length}`);
  });
});

describe('groupByPhase: 分组纯函数', () => {
  it('覆盖全部 12 个类别，无遗漏无重复', () => {
    const flat = groupByPhase().flatMap((g) => g.defs.map((d) => d.key));
    expect(flat).toHaveLength(LAYER_CATEGORIES.length);
    expect(new Set(flat).size).toBe(LAYER_CATEGORIES.length);
  });

  it('每组内元素的 phase 与组名一致，且组顺序为 PHASE_ORDER 的子序列', () => {
    const groups = groupByPhase();
    for (const g of groups) {
      for (const d of g.defs) expect(d.phase).toBe(g.phase);
    }
    const expected = PHASE_ORDER.filter((p) => groups.some((g) => g.phase === p));
    expect(groups.map((g) => g.phase)).toEqual(expected);
  });

  it('空分组不产出（传入只含 P0 的子集时只得到一个组）', () => {
    const onlyP0 = LAYER_CATEGORIES.filter((d) => d.phase === 'P0');
    const groups = groupByPhase(onlyP0);
    expect(groups).toHaveLength(1);
    expect(groups[0].phase).toBe('P0');
  });
});

describe('LayerTreePanel: 布局与无障碍', () => {
  it('容器是 aside[aria-label=指标树]，定宽不撑破布局且可纵向滚动', () => {
    const html = panelHtml();
    expect(html).toContain('aria-label="指标树"');
    expect(html).toContain('w-40');
    expect(html).toContain('shrink-0');
    expect(html).toContain('overflow-y-auto');
  });

  it('中文标签统一 truncate 防溢出，行复用既有 .layer-legend-item 样式', () => {
    const html = panelHtml();
    expect(html).toContain('layer-legend-label truncate');
    expect(html).toContain('layer-legend-item');
  });

  it('missingCount>0 时展示「数据缺失 N」，为 0 时不展示该提示', () => {
    expect(panelHtml({ missingCount: 7 })).toContain('数据缺失');
    expect(panelHtml({ missingCount: 7 })).toContain('>7<');
    expect(panelHtml({ missingCount: 0 })).not.toContain('数据缺失');
  });

  it('头部展示「已开类别数 / 总数」，随 visible 变化', () => {
    expect(panelHtml({ visible: ALL_ON })).toContain(`12/${LAYER_CATEGORIES.length}`);
    expect(panelHtml({ visible: new Set<LayerCategory>(['geo', 'event']) })).toContain(
      `2/${LAYER_CATEGORIES.length}`,
    );
  });
});
