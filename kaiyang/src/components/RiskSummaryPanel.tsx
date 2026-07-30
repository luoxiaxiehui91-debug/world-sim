import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { adaptGrv, topRisks } from '@/lib/grvAdapter';
import { severityColor, severityLabel, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvDimension, GrvRaw } from '@/types/contracts';

/** 单条风险卡（标签 + 数值 + 严重度色条）。 */
function RiskRow({ dim }: { dim: GrvDimension }) {
  const color = severityColor(dim.value);
  const pct = dim.value === null ? 0 : Math.min(100, Math.max(0, dim.value));
  return (
    <div className="panel-card group">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[12px] text-white/80" title={dim.note ?? dim.label}>
          {dim.label}
        </span>
        <span className="shrink-0 font-mono text-[12px]" style={{ color }}>
          {fmtNum(dim.value)}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${withAlpha(color, 0.45)}, ${color})`,
            boxShadow: `0 0 8px ${withAlpha(color, 0.55)}`,
          }}
        />
      </div>
      <div className="mt-0.5 flex items-center justify-between text-[10px] text-white/35">
        <span>{dim.group}</span>
        <span style={{ color: withAlpha(color, 0.85) }}>{severityLabel(dim.value)}</span>
      </div>
    </div>
  );
}

/**
 * 左侧风险摘要小卡组：全球综合头条 + Top N 高风险地理维度。
 * 数据源与地图 / GRV 面板完全一致（adaptGrv），composite 单列不混入排行。
 */
export function RiskSummaryPanel() {
  const { data, loading, error } = useFeed<GrvRaw>('grv');
  const model = useMemo(() => adaptGrv(data), [data]);
  const tops = useMemo(() => topRisks(model.geographic, 6), [model]);
  const headline = model.headline;
  const headlineColor = severityColor(headline?.value ?? null);
  const missingCount = model.dimensions.filter((d) => d.status === 'missing').length;

  return (
    <div className="glass-panel scanlines flex h-full min-h-[240px] flex-col">
      <div className="panel-title">🎯 风险摘要</div>

      {headline && (
        <div
          className="mb-2 rounded-xl border px-3 py-2"
          style={{
            borderColor: withAlpha(headlineColor, 0.35),
            background: withAlpha(headlineColor, 0.08),
          }}
        >
          <div className="text-[10px] tracking-widest text-white/40">{headline.label}</div>
          <div
            className="font-mono text-3xl font-semibold leading-tight"
            style={{ color: headlineColor, textShadow: `0 0 18px ${withAlpha(headlineColor, 0.45)}` }}
          >
            {fmtNum(headline.value, 1)}
          </div>
          <div className="text-[10px] text-white/35">综合指数 · 不投影到地图</div>
        </div>
      )}

      <div className="mb-1 text-[10px] tracking-widest text-white/35">高风险地区 TOP {tops.length}</div>
      <div className="flex-1 space-y-1.5 overflow-y-auto pr-0.5">
        {loading && <div className="text-[11px] text-white/40">加载中…</div>}
        {error && <div className="text-[11px] text-amber-300">读取失败</div>}
        {!loading && tops.map((d) => <RiskRow key={d.id} dim={d} />)}
      </div>

      <div className="mt-2 text-[10px] text-white/30">
        缺失维度 {missingCount} / {model.dimensions.length}
      </div>
    </div>
  );
}
