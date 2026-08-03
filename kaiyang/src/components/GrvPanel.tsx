import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from '@/components/EChart';
import { useFeed } from '@/hooks/useFeed';
import { adaptGrv } from '@/lib/grvAdapter';
import { PALETTE, severityColor, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvDimension, GrvRaw } from '@/types/contracts';

/** 综合指数头条卡（composite 维度不上地图，改在此处以大数字呈现）。 */
function CompositeCard({ dim }: { dim: GrvDimension }) {
  const color = severityColor(dim.value);
  return (
    <div
      className="flex-1 rounded-xl border px-3 py-2"
      style={{ borderColor: withAlpha(color, 0.3), background: withAlpha(color, 0.07) }}
      title={dim.note ?? '综合指数（无地理位置）'}
    >
      <div className="text-[10px] tracking-widest text-white/40">{dim.label}</div>
      <div
        className="font-mono text-2xl font-semibold leading-tight"
        style={{ color, textShadow: `0 0 16px ${withAlpha(color, 0.4)}` }}
      >
        {fmtNum(dim.value, 1)}
      </div>
      <div className="text-[10px] text-white/30">{dim.status === 'missing' ? '数据缺失' : '综合指数'}</div>
    </div>
  );
}

/**
 * GRV 维度面板：
 * - 顶部：composite 综合指数头条数字（全球综合 / 全球南方）。
 * - 主体：geographic 维度横向条形图 + 不确定区间误差带。
 */
export function GrvPanel() {
  const { data } = useFeed<GrvRaw>('grv');
  const model = useMemo(() => adaptGrv(data), [data]);
  const dims = model.geographic;

  const option = useMemo<EChartsOption>(() => {
    const sorted = [...dims].sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
    const categories = sorted.map((d) => d.label);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const barData: any[] = sorted.map((d) => {
      const c = severityColor(d.value);
      return {
        value: d.value ?? 0,
        itemStyle: {
          borderRadius: 4,
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: withAlpha(c, 0.35) },
              { offset: 1, color: c },
            ],
          },
          shadowBlur: 10,
          shadowColor: withAlpha(c, 0.45),
        },
      };
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const errData: any[] = sorted.map((d, i) => [
      i,
      d.value ?? 0,
      d.value === null ? 0 : (d.uncertainty ?? 0),
    ]);

    return {
      grid: { left: 76, right: 28, top: 12, bottom: 24 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(6,11,22,0.92)',
        borderColor: withAlpha('#22d3ee', 0.35),
        textStyle: { color: '#d7e3ea', fontSize: 12 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          const i = params[0].dataIndex as number;
          const d = sorted[i];
          const uncTxt = d.uncertainty === null ? '未知' : `±${d.uncertainty}`;
          const est = d.uncertaintyEstimated ? '（估算）' : '';
          return `<b>${d.label}</b><br/>数值：${d.value === null ? '缺失' : fmtNum(d.value)}<br/>不确定区间：${uncTxt}${est}`;
        },
      },
      xAxis: {
        type: 'value',
        max: 105,
        axisLabel: { color: '#9fb3c8' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      yAxis: {
        type: 'category',
        data: categories,
        axisLabel: { color: '#cbd5e1' },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      },
      series: [
        { type: 'bar', data: barData, barWidth: 12, z: 1 },
        {
          type: 'custom',
          z: 2,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          renderItem: (_params: unknown, api: any): any => {
            const catIdx = api.value(0) as number;
            const val = api.value(1) as number;
            const half = api.value(2) as number;
            if (half <= 0) return { type: 'group', children: [] };
            const start = api.coord([val - half, catIdx]) as [number, number];
            const end = api.coord([val + half, catIdx]) as [number, number];
            const y = start[1];
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const style: any = { stroke: PALETTE.axis, lineWidth: 1.5, lineCap: 'round' };
            return {
              type: 'group',
              children: [
                { type: 'line', shape: { x1: start[0], y1: y, x2: end[0], y2: y }, style },
                { type: 'line', shape: { x1: start[0], y1: y - 5, x2: start[0], y2: y + 5 }, style },
                { type: 'line', shape: { x1: end[0], y1: y - 5, x2: end[0], y2: y + 5 }, style },
              ],
            };
          },
          encode: { x: [1], y: 0 },
          data: errData,
        },
      ],
    };
  }, [dims]);

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title">📊 GRV 维度风险（含不确定区间）</div>

      {model.composite.length > 0 && (
        <div className="mb-2 flex gap-2">
          {model.composite.map((d) => (
            <CompositeCard key={d.id} dim={d} />
          ))}
        </div>
      )}

      <p className="mb-2 text-[11px] text-white/40">
        误差带为 ±不确定区间。Wave1 数据源未提供该字段，按 8% 估算并标记；缺失维度以灰色显示「数据缺失」。
        综合指数无地理位置，单列于上方，不投影到地图。
      </p>
      <EChart option={option} className="flex-1" style={{ minHeight: 0 }} />
    </div>
  );
}
