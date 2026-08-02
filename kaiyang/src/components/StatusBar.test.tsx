import { describe, it, expect } from 'vitest';
import { deriveKpis } from '@/components/StatusBar';
import { SIGNAL_DISPLAY_LIMIT, deriveSignals } from '@/components/SignalStreamPanel';
import type { NewsItem } from '@/types/contracts';

/**
 * 顶栏 KPI 派生（R-P1-03）纯函数测试。
 * 只测 `deriveKpis`：StatusBar 组件本身依赖 useFeed / Context，node 环境不渲染。
 */

function item(over: Partial<NewsItem> = {}): NewsItem {
  return { title: '某条新闻', source: '来源', date: '2026-08-01', ...over };
}

const alert = () => item({ level: 'ALERT' });
const watch = () => item({ level: 'WARNING' });
const info = () => item({ level: '' });

function repeat(make: () => NewsItem, n: number): NewsItem[] {
  return Array.from({ length: n }, make);
}

describe('deriveKpis: 基本口径', () => {
  it('空输入返回全 0', () => {
    expect(deriveKpis([])).toEqual({ signals: 0, news: 0, mainAlert: 0 });
  });

  it('news = 原始条数，signals = 未超上限时等于原始条数', () => {
    const k = deriveKpis(repeat(info, 7));
    expect(k.news).toBe(7);
    expect(k.signals).toBe(7);
    expect(k.mainAlert).toBe(0);
  });

  it('超过显示上限时 signals 截断到上限，news 仍是原始条数', () => {
    const k = deriveKpis(repeat(info, SIGNAL_DISPLAY_LIMIT + 13));
    expect(k.news).toBe(SIGNAL_DISPLAY_LIMIT + 13);
    expect(k.signals).toBe(SIGNAL_DISPLAY_LIMIT);
  });

  it('mainAlert 只数 alert 级（警报/ALERT/CRITICAL），不含 注意/观察', () => {
    const k = deriveKpis([
      alert(),
      item({ alert_type: '警报' }),
      item({ category: 'CRITICAL' }),
      watch(),
      info(),
    ]);
    expect(k.news).toBe(5);
    expect(k.signals).toBe(5);
    expect(k.mainAlert).toBe(3);
  });

  it('mainAlert 不会超过 signals（alert 数多于显示上限时一并截断）', () => {
    const k = deriveKpis(repeat(alert, SIGNAL_DISPLAY_LIMIT + 5));
    expect(k.signals).toBe(SIGNAL_DISPLAY_LIMIT);
    expect(k.mainAlert).toBe(SIGNAL_DISPLAY_LIMIT);
    expect(k.mainAlert).toBeLessThanOrEqual(k.signals);
  });
});

describe('deriveKpis: 与信号流口径一致（单一真源）', () => {
  it('signals 恒等于 SignalStreamPanel 实际渲染的条数', () => {
    for (const n of [0, 1, 39, 40, 41, 120]) {
      const items = repeat(info, n);
      expect(deriveKpis(items).signals).toBe(deriveSignals(items).length);
    }
  });

  it('mainAlert 恒等于可见范围内 alert 行数（警报排在最前，故为 min(全量, 可见)）', () => {
    const items = [...repeat(alert, 45), ...repeat(watch, 10), ...repeat(info, 30)];
    const visibleAlerts = deriveSignals(items).filter((s) => s.level === 'alert').length;
    expect(deriveKpis(items).mainAlert).toBe(visibleAlerts);
  });

  it('少量 alert 混在大量 info 里也不会被截断掉（排序保证 alert 优先可见）', () => {
    const items = [...repeat(info, 100), ...repeat(alert, 3)];
    const visibleAlerts = deriveSignals(items).filter((s) => s.level === 'alert').length;
    expect(visibleAlerts).toBe(3);
    expect(deriveKpis(items).mainAlert).toBe(3);
  });
});

describe('deriveKpis: 容错降级（K5 不抛错）', () => {
  it('null / undefined 一律降级为 0', () => {
    expect(deriveKpis(null)).toEqual({ signals: 0, news: 0, mainAlert: 0 });
    expect(deriveKpis(undefined)).toEqual({ signals: 0, news: 0, mainAlert: 0 });
  });

  it('接受 { items: [...] } 包装载荷', () => {
    expect(deriveKpis({ items: [alert(), info()] })).toEqual({
      signals: 2,
      news: 2,
      mainAlert: 1,
    });
  });

  it('包装载荷里 items 非数组时降级为 0', () => {
    expect(deriveKpis({ items: null })).toEqual({ signals: 0, news: 0, mainAlert: 0 });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(deriveKpis({ items: 'boom' } as any)).toEqual({ signals: 0, news: 0, mainAlert: 0 });
  });

  it('数组内混入 null / 非对象元素时被剔除，不计入 news', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const dirty = [alert(), null, 'x', undefined, info()] as any;
    expect(deriveKpis(dirty)).toEqual({ signals: 2, news: 2, mainAlert: 1 });
  });

  it('条目字段全缺失也不抛错，按 info 计', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const dirty = [{}, {}, {}] as any;
    expect(() => deriveKpis(dirty)).not.toThrow();
    expect(deriveKpis(dirty)).toEqual({ signals: 3, news: 3, mainAlert: 0 });
  });
});
