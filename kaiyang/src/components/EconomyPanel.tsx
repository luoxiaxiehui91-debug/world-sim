import { useEffect, useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from '@/components/EChart';
import { useFeed } from '@/hooks/useFeed';
import { useFRED } from '@/hooks/useFRED';
import { fmtNum } from '@/lib/format';
import type { FredManifest, FredSeriesMeta } from '@/types/contracts';

/** 时间范围选项 */
const TIME_RANGES = [
  { label: '1Y',  months: 12  },
  { label: '2Y',  months: 24  },
  { label: '5Y',  months: 60  },
  { label: '10Y', months: 120 },
  { label: '全部', months: 0   },
];

export function EconomyPanel() {
  const { data: manifest } = useFeed<FredManifest>('fred');
  const { series, loading, error } = useFRED(manifest);
  const [activeId, setActiveId] = useState<string>('');
  const [timeRange, setTimeRange] = useState<number>(24);        // 默认显示 2 年
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set()); // 已隐藏的序列
  const [showToggle, setShowToggle] = useState(false);           // 是否展开序列管理器

  useEffect(() => {
    if (!activeId && series.length > 0) setActiveId(series[0].id);
  }, [series, activeId]);

  // 当前活跃序列的可见数据（按时间范围裁剪）
  const active = series.find((s) => s.id === activeId) ?? null;
  const visibleSeries = series.filter((s) => !hiddenIds.has(s.id));

  const pts = useMemo(() => {
    if (!active) return [];
    const all = active.points;
    if (timeRange === 0) return all;
    // 从末尾取最近 N 个月
    const cutDate = new Date();
    cutDate.setMonth(cutDate.getMonth() - timeRange);
    // 本地日期拼接（不用 toISOString：UTC 日期会在 UTC+8 早上 8 点前偏移一天）
    const cutStr = cutDate.getFullYear() + '-' + String(cutDate.getMonth() + 1).padStart(2, '0') + '-' + String(cutDate.getDate()).padStart(2, '0');
    return all.filter((p) => p.date >= cutStr);
  }, [active, timeRange]);

  const option = useMemo<EChartsOption>(() => {
    if (!active || pts.length === 0) return {};
    const color = active.color ?? '#4fd1c5';
    return {
      grid: { left: 60, right: 18, top: 12, bottom: 60 },
      tooltip: { trigger: 'axis' },
      dataZoom: [
        {
          type: 'slider',
          bottom: 8,
          height: 20,
          borderColor: 'rgba(255,255,255,0.1)',
          backgroundColor: 'rgba(255,255,255,0.03)',
          fillerColor: `${color}18`,
          handleStyle: { color, borderColor: color },
          textStyle: { color: '#9fb3c8', fontSize: 10 },
          start: 0,
          end: 100,
        },
        { type: 'inside', zoomOnMouseWheel: true, moveOnMouseMove: true },
      ],
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
          smooth: false,
          lineStyle: { color, width: 1.5 },
          areaStyle: { color: `${color}15` },
        },
      ],
    };
  }, [active, pts]);

  const last = pts.length ? pts[pts.length - 1] : null;

  const toggleHide = (id: string) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      // 如果隐藏了当前活跃序列，切换到第一个可见序列
      return next;
    });
  };

  // 若当前 active 被隐藏，自动切换到第一个可见序列
  useEffect(() => {
    if (activeId && hiddenIds.has(activeId)) {
      const first = series.find((s) => !hiddenIds.has(s.id));
      if (first) setActiveId(first.id);
    }
  }, [hiddenIds, activeId, series]);

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between">
        <span>📈 经济面板 · FRED 关键序列</span>
        <button
          onClick={() => setShowToggle((v) => !v)}
          className="text-[11px] text-white/30 hover:text-white/60 transition-colors"
          title="管理显示序列"
        >
          {showToggle ? '收起 ▲' : '序列管理 ▼'}
        </button>
      </div>

      {/* 序列管理器：点击显示/隐藏 */}
      {showToggle && (
        <div className="mb-2 rounded-lg border border-white/8 bg-black/20 px-2 py-1.5">
          <div className="mb-1 text-[10px] text-white/30 tracking-wider">勾选显示 · 点击取消</div>
          <div className="flex flex-wrap gap-1">
            {series.map((s) => {
              const hidden = hiddenIds.has(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => toggleHide(s.id)}
                  className={`chip text-[10px] transition-all ${
                    hidden
                      ? 'border-white/10 text-white/20 line-through'
                      : 'border-accent/40 text-accent/80'
                  }`}
                  title={hidden ? '点击显示' : '点击隐藏'}
                >
                  {hidden ? '○' : '●'} {s.label}
                </button>
              );
            })}
          </div>
          <div className="mt-1 text-[10px] text-white/25">
            显示 {series.length - hiddenIds.size} / {series.length} 个序列
          </div>
        </div>
      )}

      {/* 序列选择 chip（只显示未隐藏的） */}
      <div className="my-1 flex flex-wrap gap-1">
        {visibleSeries.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveId(s.id)}
            className={`chip text-[11px] ${s.id === activeId ? 'border-accent/60 text-accent' : 'text-white/50'}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 时间范围选择 */}
      <div className="mb-1 flex items-center gap-1">
        <span className="text-[10px] text-white/25 mr-0.5">时间范围</span>
        {TIME_RANGES.map((r) => (
          <button
            key={r.label}
            onClick={() => setTimeRange(r.months)}
            className={`rounded px-1.5 py-0.5 text-[10px] transition-colors ${
              timeRange === r.months
                ? 'bg-accent/20 text-accent'
                : 'text-white/30 hover:text-white/60'
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {error && <div className="text-xs text-amber-300">读取失败：{error.message}</div>}
      {!error && loading && <div className="text-xs text-white/40">加载中…</div>}
      {!error && !loading && active && last && (
        <div className="mb-0.5 text-[11px] text-white/45">
          最新 {last.date} · {fmtNum(last.value)} {active.unit ?? ''}
          {active.category ? ` · ${active.category}` : ''}
          <span className="ml-2 text-white/25">{pts.length} 个数据点</span>
        </div>
      )}
      {!error && !loading && series.length === 0 && (
        <div className="text-xs text-amber-300">无可用序列</div>
      )}
      <EChart option={option} className="flex-1" style={{ minHeight: 0 }} />
    </div>
  );
}
