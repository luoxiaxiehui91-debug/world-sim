import { useEffect, useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from '@/components/EChart';
import { useFeed } from '@/hooks/useFeed';
import { useFRED } from '@/hooks/useFRED';
import { fmtNum } from '@/lib/format';
import type { FredManifest } from '@/types/contracts';

export function EconomyPanel() {
  const { data: manifest } = useFeed<FredManifest>('fred');
  const { series, loading, error } = useFRED(manifest);
  const [activeId, setActiveId] = useState<string>('');

  useEffect(() => {
    if (!activeId && series.length > 0) setActiveId(series[0].id);
  }, [series, activeId]);

  const active = series.find((s) => s.id === activeId) ?? null;

  const option = useMemo<EChartsOption>(() => {
    if (!active) return {};
    const pts = active.points;
    const color = active.color ?? '#4fd1c5';
    return {
      grid: { left: 60, right: 18, top: 18, bottom: 28 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: pts.map((p) => p.date),
        boundaryGap: false,
        axisLabel: { color: '#9fb3c8', hideOverlap: true },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#9fb3c8' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series: [
        {
          type: 'line',
          data: pts.map((p) => p.value),
          showSymbol: false,
          smooth: true,
          lineStyle: { color, width: 2 },
          areaStyle: { color: `${color}20` },
        },
      ],
    };
  }, [active]);

  const last = active && active.points.length ? active.points[active.points.length - 1] : null;

  return (
    <div className="glass-panel scanlines flex h-full min-h-[340px] flex-col">
      <div className="panel-title">📈 经济面板 · FRED 关键序列</div>
      <div className="my-2 flex flex-wrap gap-1.5">
        {series.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveId(s.id)}
            className={`chip ${s.id === activeId ? 'border-accent/60 text-accent' : 'text-white/55'}`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {error && <div className="text-xs text-amber-300">读取失败：{error.message}</div>}
      {!error && loading && <div className="text-xs text-white/40">加载中…</div>}
      {!error && !loading && active && last && (
        <div className="mb-1 text-xs text-white/50">
          最新 {last.date} · 值 {fmtNum(last.value)} {active.unit ?? ''}
          {active.category ? ` · ${active.category}` : ''}
        </div>
      )}
      {!error && !loading && series.length === 0 && (
        <div className="text-xs text-amber-300">无可用序列（manifest 缺失或路径错误）</div>
      )}
      <EChart option={option} className="min-h-[220px] flex-1" />
    </div>
  );
}
