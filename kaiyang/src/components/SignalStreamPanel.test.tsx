import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  SIGNAL_DISPLAY_LIMIT,
  SignalRow,
  deriveSignals,
  newsItemsOf,
  signalLevelOf,
  toSignal,
  type Signal,
} from '@/components/SignalStreamPanel';
import type { NewsItem } from '@/types/contracts';

/**
 * 信号流（R-P1-03）测试：序号渲染 / 选中高亮 / 点击回调 / 派生与降级。
 *
 * ⚠ 零新依赖：node 环境无 jsdom。
 * - `SignalRow` 是**纯函数组件**（无 hook），可用 `renderToStaticMarkup` 直接渲染断言；
 * - 点击回调靠直接调用组件函数拿到元素树后手动执行 `onClick`。
 * - `SignalStreamPanel` 本体依赖 useFeed / useSelection，不在此渲染。
 */

function sig(over: Partial<Signal> = {}): Signal {
  return {
    key: 'k-0',
    title: '某条信号',
    source: '路透',
    date: '2026-08-01',
    level: 'info',
    metric: '',
    focusId: null,
    fullTitle: '某条信号',
    url: null,
    detail: null,
    riskNote: null,
    triggerTitles: null,
    ...over,
  };
}

const noop = () => {};

function rowOf(props: Parameters<typeof SignalRow>[0]) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return SignalRow(props) as any;
}

describe('SignalRow: 序号渲染', () => {
  it('0 基下标渲染成 #1 起的序号前缀', () => {
    for (const [index, label] of [
      [0, '#1'],
      [1, '#2'],
      [9, '#10'],
      [39, '#40'],
    ] as const) {
      const html = renderToStaticMarkup(
        <SignalRow signal={sig()} index={index} selected={false} onSelect={noop} />,
      );
      expect(html).toContain(label);
    }
  });

  it('序号用 tabular-nums 等宽数字，避免滚动时列宽跳动', () => {
    const html = renderToStaticMarkup(
      <SignalRow signal={sig()} index={0} selected={false} onSelect={noop} />,
    );
    expect(html).toContain('tabular-nums');
  });

  it('序号与标题 / 来源 / 日期同行渲染，标题不丢', () => {
    const html = renderToStaticMarkup(
      <SignalRow
        signal={sig({ title: '霍尔木兹海峡通行受阻', source: '彭博', date: '2026-07-30' })}
        index={2}
        selected={false}
        onSelect={noop}
      />,
    );
    expect(html).toContain('#3');
    expect(html).toContain('霍尔木兹海峡通行受阻');
    expect(html).toContain('彭博');
    expect(html).toContain('2026-07-30');
  });

  it('列表整体渲染时序号连续且从 #1 开始', () => {
    const list = [sig({ key: 'a' }), sig({ key: 'b' }), sig({ key: 'c' })];
    const html = renderToStaticMarkup(
      <>
        {list.map((s, i) => (
          <SignalRow key={s.key} signal={s} index={i} selected={false} onSelect={noop} />
        ))}
      </>,
    );
    let cursor = -1;
    for (const label of ['#1', '#2', '#3']) {
      const at = html.indexOf(label, cursor + 1);
      expect(at, `${label} 应按顺序出现`).toBeGreaterThan(cursor);
      cursor = at;
    }
  });
});

describe('SignalRow: 选中态与点击', () => {
  it('可点击且是 div role=button（2026-08-05 d1a1b39 改：button 内不能嵌 a 链接），带 aria-pressed 无障碍标记', () => {
    const el = rowOf({ signal: sig(), index: 0, selected: false, onSelect: noop });
    expect(el.type).toBe('div');
    expect(el.props.role).toBe('button');
    expect(el.props.tabIndex).toBe(0);
    expect(el.props['aria-pressed']).toBe(false);
  });

  it('选中行加 accent 高亮边框（复用既有 accent，不引入新色）', () => {
    const on = rowOf({ signal: sig(), index: 0, selected: true, onSelect: noop });
    const off = rowOf({ signal: sig(), index: 0, selected: false, onSelect: noop });
    expect(on.props['aria-pressed']).toBe(true);
    expect(String(on.props.className)).toContain('border-accent/60');
    expect(String(off.props.className)).not.toContain('border-accent/60');
    expect(String(off.props.className)).toContain('border-white/5');
  });

  it('选中态不改左侧类别色条（D1 色相轴不被选中态污染）', () => {
    const on = rowOf({ signal: sig(), index: 0, selected: true, onSelect: noop });
    const off = rowOf({ signal: sig(), index: 0, selected: false, onSelect: noop });
    expect(on.props.style.borderLeft).toBe(off.props.style.borderLeft);
  });

  it('点击回调带回整条信号', () => {
    const seen: Signal[] = [];
    const s = sig({ key: 'sig-7' });
    rowOf({ signal: s, index: 6, selected: false, onSelect: (x) => seen.push(x) }).props.onClick();
    expect(seen).toHaveLength(1);
    expect(seen[0].key).toBe('sig-7');
  });

  it('无坐标信号的 tooltip 诚实说明「暂不联动地图」，不伪造跳转', () => {
    const el = rowOf({ signal: sig({ focusId: null }), index: 0, selected: false, onSelect: noop });
    expect(String(el.props.title)).toContain('暂不联动地图');
  });

  it('一旦信号带上 focusId（待 news_geo 就绪），tooltip 改为「点击聚焦地图点位」', () => {
    const el = rowOf({
      signal: sig({ focusId: 'pt-hormuz' }),
      index: 0,
      selected: false,
      onSelect: noop,
    });
    expect(String(el.props.title)).toContain('点击聚焦地图点位');
  });
});

describe('deriveSignals / toSignal', () => {
  const alert: NewsItem = { title: 'A', level: 'ALERT' };
  const watch: NewsItem = { title: 'W', level: 'WARNING' };
  const info: NewsItem = { title: 'I' };

  it('按 警报 → 注意 → 观察 排序', () => {
    const out = deriveSignals([info, watch, alert]);
    expect(out.map((s) => s.level)).toEqual(['alert', 'watch', 'info']);
  });

  it('截断到显示上限', () => {
    const out = deriveSignals(Array.from({ length: SIGNAL_DISPLAY_LIMIT + 9 }, () => info));
    expect(out).toHaveLength(SIGNAL_DISPLAY_LIMIT);
  });

  it('key 唯一（同 series_id 靠下标区分）', () => {
    const same = Array.from({ length: 5 }, () => ({ ...info, series_id: 'X' }));
    const keys = deriveSignals(same).map((s) => s.key);
    expect(new Set(keys).size).toBe(5);
  });

  it('当前 news 条目无坐标 → focusId 恒为 null（诚实边界）', () => {
    expect(deriveSignals([alert, watch, info]).every((s) => s.focusId === null)).toBe(true);
  });

  it('条目带 point_id 时 focusId 透传（为 news_geo 预留，零改动生效）', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const geo = { title: 'G', point_id: 'pt-suez' } as any;
    expect(toSignal(geo, 0).focusId).toBe('pt-suez');
  });

  it('字段全缺失也不抛错，降级为「（无标题）/ 未知来源 / —」', () => {
    const s = toSignal({}, 0);
    expect(s.title).toBe('（无标题）');
    expect(s.source).toBe('未知来源');
    expect(s.date).toBe('—');
    expect(s.level).toBe('info');
  });
});

describe('newsItemsOf / signalLevelOf: 容错', () => {
  it('裸数组、{items} 包装、null / undefined 全部安全归一', () => {
    expect(newsItemsOf([{ title: 'a' }])).toHaveLength(1);
    expect(newsItemsOf({ items: [{ title: 'a' }, { title: 'b' }] })).toHaveLength(2);
    expect(newsItemsOf(null)).toEqual([]);
    expect(newsItemsOf(undefined)).toEqual([]);
    expect(newsItemsOf({ items: null })).toEqual([]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(newsItemsOf('boom' as any)).toEqual([]);
  });

  it('剔除数组内 null / 非对象元素', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(newsItemsOf([{ title: 'a' }, null, 0, 'x'] as any)).toHaveLength(1);
  });

  it('等级判定覆盖中英文关键词，未命中降级 info', () => {
    expect(signalLevelOf({ level: '警报' })).toBe('alert');
    expect(signalLevelOf({ alert_type: 'CRITICAL' })).toBe('alert');
    expect(signalLevelOf({ category: 'ALERT' })).toBe('alert');
    expect(signalLevelOf({ level: '注意' })).toBe('watch');
    expect(signalLevelOf({ level: 'WARNING' })).toBe('watch');
    expect(signalLevelOf({})).toBe('info');
    expect(signalLevelOf({ level: '随便什么' })).toBe('info');
  });
});
