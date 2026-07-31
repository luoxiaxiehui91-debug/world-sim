import { describe, it, expect } from 'vitest';
import {
  buildRiskPoints,
  buildEventBars,
  buildRiskArcs,
  pointTooltipHtml,
  arcTooltipHtml,
} from '@/lib/mapData';
import type { GrvDimension, GrvEvent } from '@/types/contracts';

/** 构造一个 GrvDimension 测试样本（仅填参与地图点位构建相关的字段）。 */
function mkDim(partial: Partial<GrvDimension> & Pick<GrvDimension, 'id' | 'kind'>): GrvDimension {
  return {
    label: partial.id,
    value: null,
    uncertainty: null,
    uncertaintyEstimated: false,
    lat: null,
    lng: null,
    group: '地缘',
    status: 'ok',
    note: undefined,
    ...partial,
  } as GrvDimension;
}

const sampleDims: GrvDimension[] = [
  mkDim({ id: 'taiwan_strait', kind: 'geographic', lat: 24.5, lng: 120.5, value: 70, group: '地缘', label: '台海' }),
  mkDim({ id: 'climate_risk', kind: 'geographic', lat: 74, lng: 10, value: 50, group: '非传统', label: '气候风险' }),
  mkDim({ id: 'disaster_risk', kind: 'geographic', lat: -2, lng: -80, value: 24, group: '非传统', label: '自然灾害' }),
  mkDim({ id: 'global_composite', kind: 'composite', value: 60, group: '综合', label: '全球综合' }),
  mkDim({ id: 'no_coord', kind: 'geographic', lat: null, lng: null, value: 40, group: '地缘', label: '无坐标' }),
];

/* ------------------------------------------------------------------ */
/* buildRiskPoints：常驻柱必须排除 renderBar:false 的事件维度            */
/* ------------------------------------------------------------------ */
describe('buildRiskPoints: 事件维度不再画常驻柱', () => {
  it('结果不含 climate_risk / disaster_risk，但含普通 geographic 维度', () => {
    const ids = buildRiskPoints(sampleDims).map((p) => p.id);
    expect(ids).toContain('taiwan_strait');
    expect(ids).not.toContain('climate_risk');
    expect(ids).not.toContain('disaster_risk');
  });

  it('结果排除 composite 与缺坐标维度', () => {
    const ids = buildRiskPoints(sampleDims).map((p) => p.id);
    expect(ids).not.toContain('global_composite');
    expect(ids).not.toContain('no_coord');
  });

  it('常驻柱派生字段正确（value/group/status/color/severity/weight）', () => {
    const tw = buildRiskPoints(sampleDims).find((p) => p.id === 'taiwan_strait')!;
    expect(tw.value).toBe(70);
    expect(tw.group).toBe('地缘');
    expect(tw.status).toBe('ok');
    expect(tw.color).toBeTruthy();
    expect(tw.severity).toBe('高');
    expect(tw.weight).toBeCloseTo(0.7);
  });

  it('常驻柱不被标记为事件柱', () => {
    const pts = buildRiskPoints(sampleDims);
    expect(pts.every((p) => p.isEvent !== true)).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* buildEventBars：事件触发式告警柱（优雅降级 + 触发渲染）              */
/* ------------------------------------------------------------------ */
describe('buildEventBars: 事件触发式告警柱', () => {
  it('入参 undefined → 返回空数组（平时不画任何事件柱）', () => {
    expect(buildEventBars(undefined)).toEqual([]);
  });

  it('入参空数组 → 返回空数组', () => {
    expect(buildEventBars([])).toEqual([]);
  });

  it('单个气候事件 → 生成事件柱（isEvent=true, group=气候）', () => {
    const bars = buildEventBars([
      { id: 'evt-1', type: 'climate', label: '北极高温', lat: 70, lng: 5, value: 80 },
    ]);
    expect(bars).toHaveLength(1);
    const b = bars[0];
    expect(b.isEvent).toBe(true);
    expect(b.id).toBe('evt-1');
    expect(b.lat).toBe(70);
    expect(b.lng).toBe(5);
    expect(b.value).toBe(80);
    expect(b.group).toBe('气候');
    expect(b.status).toBe('ok');
    expect(b.severity).toBe('高');
    expect(b.weight).toBeCloseTo(0.8);
    expect(b.note).toBeUndefined();
  });

  it('disaster 类型 → group 映射为「自然灾害」', () => {
    const bars = buildEventBars([
      { id: 'evt-2', type: 'disaster', label: '地震', lat: 35, lng: 139, value: 60 },
    ]);
    expect(bars[0].group).toBe('自然灾害');
  });

  it('note 字段透传', () => {
    const bars = buildEventBars([
      { id: 'evt-3', type: 'disaster', label: '洪水', lat: 20, lng: 100, value: 30, note: '季风洪涝' },
    ]);
    expect(bars[0].note).toBe('季风洪涝');
  });

  it('value 越界时 weight 夹取到 [0,1]', () => {
    const bars = buildEventBars([
      { id: 'hi', type: 'climate', label: 'h', lat: 1, lng: 2, value: 250 },
      { id: 'lo', type: 'climate', label: 'l', lat: 3, lng: 4, value: -50 },
    ]);
    const hi = bars.find((b) => b.id === 'hi')!;
    const lo = bars.find((b) => b.id === 'lo')!;
    expect(hi.weight).toBe(1);
    expect(lo.weight).toBe(0);
    expect(hi.severity).toBe('高');
    expect(lo.severity).toBe('低');
  });

  it('坐标缺失/非数字的事件被跳过', () => {
    const bars = buildEventBars([
      { id: 'ok', type: 'climate', label: '正常', lat: 10, lng: 10, value: 40 },
      { id: 'bad-nan', type: 'climate', label: '坏', lat: NaN, lng: 10, value: 40 },
      { id: 'bad-undef', type: 'climate', label: '坏2', lat: 10, lng: undefined as unknown as number, value: 40 },
    ]);
    expect(bars.map((b) => b.id)).toEqual(['ok']);
  });

  it('value 非有限（NaN / ±Infinity / undefined / null）的事件被跳过', () => {
    const bars = buildEventBars([
      { id: 'ok', type: 'climate', label: '正常', lat: 10, lng: 10, value: 40 },
      { id: 'nan', type: 'climate', label: '坏', lat: 11, lng: 11, value: NaN },
      { id: 'pos-inf', type: 'climate', label: '坏2', lat: 12, lng: 12, value: Infinity },
      { id: 'neg-inf', type: 'disaster', label: '坏3', lat: 13, lng: 13, value: -Infinity },
      { id: 'undef', type: 'disaster', label: '坏4', lat: 14, lng: 14, value: undefined as unknown as number },
      { id: 'null', type: 'disaster', label: '坏5', lat: 15, lng: 15, value: null as unknown as number },
    ]);
    expect(bars.map((b) => b.id)).toEqual(['ok']);
  });

  it('value 为有限数（含 <0 / >100）时正常渲染事件柱', () => {
    const bars = buildEventBars([
      { id: 'neg', type: 'climate', label: '负', lat: 1, lng: 1, value: -20 },
      { id: 'over', type: 'climate', label: '超', lat: 2, lng: 2, value: 200 },
      { id: 'mid', type: 'disaster', label: '中', lat: 3, lng: 3, value: 55 },
    ]);
    expect(bars.map((b) => b.id)).toEqual(['neg', 'over', 'mid']);
    const over = bars.find((b) => b.id === 'over')!;
    expect(over.weight).toBe(1);
    expect(over.severity).toBe('高');
  });

  it('多个事件 → 全部生成', () => {
    const bars = buildEventBars([
      { id: 'a', type: 'climate', label: 'A', lat: 1, lng: 1, value: 10 },
      { id: 'b', type: 'disaster', label: 'B', lat: 2, lng: 2, value: 90 },
    ]);
    expect(bars).toHaveLength(2);
  });
});

/* ------------------------------------------------------------------ */
/* buildRiskArcs：事件维度仍保留坐标 → 联动弧线不丢失                   */
/* ------------------------------------------------------------------ */
describe('buildRiskArcs: 事件维度坐标仍用于弧线', () => {
  const dims: GrvDimension[] = [
    mkDim({ id: 'climate_risk', kind: 'geographic', lat: 74, lng: 10, value: 50, group: '非传统', label: '气候风险' }),
    mkDim({ id: 'disaster_risk', kind: 'geographic', lat: -2, lng: -80, value: 24, group: '非传统', label: '自然灾害' }),
    mkDim({ id: 'russia_europe', kind: 'geographic', lat: 49, lng: 32, value: 65, group: '地缘', label: '俄乌/东欧' }),
    mkDim({ id: 'india_pacific', kind: 'geographic', lat: 1.3, lng: 103.8, value: 55, group: '地缘', label: '印太' }),
  ];

  it('climate_risk → russia_europe 弧线存在且用锚点坐标', () => {
    const arc = buildRiskArcs(dims).find((a) => a.id === 'climate_risk__russia_europe');
    expect(arc).toBeDefined();
    expect(arc!.startLat).toBe(74);
    expect(arc!.startLng).toBe(10);
    expect(arc!.endLat).toBe(49);
    expect(arc!.endLng).toBe(32);
  });

  it('disaster_risk → india_pacific 弧线存在且用锚点坐标', () => {
    const arc = buildRiskArcs(dims).find((a) => a.id === 'disaster_risk__india_pacific');
    expect(arc).toBeDefined();
    expect(arc!.startLat).toBe(-2);
    expect(arc!.startLng).toBe(-80);
  });
});

/* ------------------------------------------------------------------ */
/* 集成：事件维度从「常驻柱」转变为「事件触发式告警柱」                  */
/* ------------------------------------------------------------------ */
describe('集成: 常驻柱消失、事件柱在事件坐标出现', () => {
  const events: GrvEvent[] = [
    { id: 'evt-c', type: 'climate', label: '北极升温', lat: 74, lng: 10, value: 70 },
    { id: 'evt-d', type: 'disaster', label: '环太地震', lat: -2, lng: -80, value: 60 },
  ];

  it('合并后：既无 climate_risk 也无 disaster_risk 的常驻柱 id，事件柱按事件 id 出现', () => {
    const perms = buildRiskPoints(sampleDims);
    const evts = buildEventBars(events);
    const allIds = [...perms.map((p) => p.id), ...evts.map((p) => p.id)];
    expect(allIds).not.toContain('climate_risk');
    expect(allIds).not.toContain('disaster_risk');
    expect(evts.map((p) => p.id)).toEqual(['evt-c', 'evt-d']);
    expect(evts.every((p) => p.isEvent === true)).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* 提示气泡：事件点 vs 常驻点文案区分                                    */
/* ------------------------------------------------------------------ */
describe('pointTooltipHtml: 事件/常驻文案区分', () => {
  const eventPt = {
    id: 'evt-1',
    label: '北极高温',
    lat: 70,
    lng: 5,
    value: 80,
    uncertainty: null,
    uncertaintyEstimated: false,
    group: '气候',
    status: 'ok',
    color: '#f87171',
    severity: '高',
    weight: 0.8,
    isEvent: true,
    note: '北极圈异常升温',
  } as const;

  const normalPt = {
    id: 'taiwan_strait',
    label: '台海',
    lat: 24.5,
    lng: 120.5,
    value: 70,
    uncertainty: 5.6,
    uncertaintyEstimated: true,
    group: '地缘',
    status: 'ok',
    color: '#f87171',
    severity: '高',
    weight: 0.7,
  } as const;

  it('事件点渲染 ⚠ + 事件类型 + 详情', () => {
    const html = pointTooltipHtml(eventPt);
    expect(html).toContain('⚠');
    expect(html).toContain('北极高温');
    expect(html).toContain('事件类型：气候');
    expect(html).toContain('详情：北极圈异常升温');
  });

  it('灾害事件渲染「事件类型：自然灾害」', () => {
    const html = pointTooltipHtml({ ...eventPt, group: '自然灾害', note: undefined });
    expect(html).toContain('事件类型：自然灾害');
  });

  it('常驻点渲染风险值 + 不确定区间，且无 ⚠', () => {
    const html = pointTooltipHtml(normalPt);
    expect(html).not.toContain('⚠');
    expect(html).toContain('台海');
    expect(html).toContain('地缘');
    expect(html).toContain('风险值');
    expect(html).toContain('不确定区间');
  });

  it('value 为 null 的常驻点显示「数据缺失」', () => {
    const html = pointTooltipHtml({ ...normalPt, value: null });
    expect(html).toContain('数据缺失');
  });
});

/* ------------------------------------------------------------------ */
/* 弧线提示文案                                                          */
/* ------------------------------------------------------------------ */
describe('arcTooltipHtml', () => {
  it('渲染两端标签与联动强度', () => {
    const html = arcTooltipHtml({
      id: 'x',
      startLat: 0,
      startLng: 0,
      endLat: 1,
      endLng: 1,
      fromLabel: '气候风险',
      toLabel: '俄乌/东欧',
      startColor: '#000',
      endColor: '#fff',
      intensity: 65,
    });
    expect(html).toContain('气候风险');
    expect(html).toContain('俄乌/东欧');
    expect(html).toContain('65');
  });
});
