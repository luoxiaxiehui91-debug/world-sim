import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { RegionTabs } from '@/components/RegionTabs';
import { REGIONS, type RegionKey } from '@/config/regions';

/**
 * RegionTabs 渲染 + 交互测试。
 *
 * ⚠ 零新依赖：node 环境无 jsdom / testing-library。
 * - 静态标记用 react-dom 自带的 `renderToStaticMarkup`（既有依赖）；
 * - 点击回调靠**直接调用组件函数**拿到元素树、递归找到 button 并手动执行其 `onClick` ——
 *   本组件无任何 hook（纯函数组件），这样调用是安全的。
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyElement = ReactElement<any>;

/** 递归收集元素树里所有 <button>。 */
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

function buttonsOf(region: RegionKey, onChange: (k: RegionKey) => void): AnyElement[] {
  return collectButtons(RegionTabs({ region, onChange }));
}

const noop = () => {};

describe('RegionTabs: 渲染', () => {
  it('渲染 6 个 Tab，标签为中文的 全球/美洲/欧洲/中东/亚太/非洲', () => {
    const buttons = buttonsOf('world', noop);
    expect(buttons).toHaveLength(6);
    expect(buttons.map((b) => b.props.children)).toEqual([
      '全球',
      '美洲',
      '欧洲',
      '中东',
      '亚太',
      '非洲',
    ]);
  });

  it('Tab 顺序与 REGIONS 一致（单一真源，不另抄一份）', () => {
    const html = renderToStaticMarkup(<RegionTabs region="world" onChange={noop} />);
    let cursor = -1;
    for (const r of REGIONS) {
      const at = html.indexOf(r.label, cursor + 1);
      expect(at, `${r.label} 应按 REGIONS 顺序出现`).toBeGreaterThan(cursor);
      cursor = at;
    }
  });

  it('无障碍：容器 role=group + 中文 aria-label，每个 Tab 都有 aria-pressed 与中文 title', () => {
    const html = renderToStaticMarkup(<RegionTabs region="europe" onChange={noop} />);
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="地区筛选"');
    const buttons = buttonsOf('europe', noop);
    for (const b of buttons) {
      expect(typeof b.props['aria-pressed']).toBe('boolean');
      expect(String(b.props.title).length).toBeGreaterThan(0);
    }
    expect(html.match(/aria-pressed="true"/g) ?? []).toHaveLength(1);
  });

  it('active 态只有当前地区一个，且用既有 accent 高亮（不引入新色）', () => {
    const buttons = buttonsOf('mid_east', noop);
    const actives = buttons.filter((b) => b.props['aria-pressed'] === true);
    expect(actives).toHaveLength(1);
    expect(actives[0].props.children).toBe('中东');
    expect(String(actives[0].props.className)).toContain('bg-accent/20');
    expect(String(actives[0].props.className)).toContain('text-accent');
    for (const b of buttons.filter((x) => x.props['aria-pressed'] !== true)) {
      expect(String(b.props.className)).not.toContain('bg-accent/20');
    }
  });

  it('全部 button 都是 type=button（避免落在表单里被当提交）', () => {
    for (const b of buttonsOf('world', noop)) expect(b.props.type).toBe('button');
  });

  it('未知 region（脏 localStorage 强转）不高亮任何 Tab，也不抛错', () => {
    const bogus = 'atlantis' as RegionKey;
    expect(() => renderToStaticMarkup(<RegionTabs region={bogus} onChange={noop} />)).not.toThrow();
    const buttons = buttonsOf(bogus, noop);
    expect(buttons.filter((b) => b.props['aria-pressed'] === true)).toHaveLength(0);
  });
});

describe('RegionTabs: onChange 触发', () => {
  it('点击每个 Tab 都回调对应的 RegionKey', () => {
    const seen: RegionKey[] = [];
    const buttons = buttonsOf('world', (k) => seen.push(k));
    for (const b of buttons) b.props.onClick();
    expect(seen).toEqual(['world', 'americas', 'europe', 'mid_east', 'asia_pacific', 'africa']);
  });

  it('点击当前已选中的 Tab 也照常回调（父层自行去重，组件不吞事件）', () => {
    const seen: RegionKey[] = [];
    const buttons = buttonsOf('africa', (k) => seen.push(k));
    const africa = buttons.find((b) => b.props['aria-pressed'] === true)!;
    africa.props.onClick();
    expect(seen).toEqual(['africa']);
  });
});
