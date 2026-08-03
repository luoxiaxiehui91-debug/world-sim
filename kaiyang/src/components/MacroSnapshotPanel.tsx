import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { useFRED } from '@/hooks/useFRED';
import { fmtNum } from '@/lib/format';
import { severityColor, withAlpha } from '@/config/theme';
import type { FredManifest } from '@/types/contracts';

/** 快照指标定义 */
const SNAPSHOT_IDS = [
  { id: 'VIXCLS',   label: 'VIX 恐慌指数',  unit: '',    hi: 30, lo: 15, higherBad: true  },
  { id: 'DTWEXBGS', label: '美元指数',        unit: '',    hi: 115, lo: 95, higherBad: false },
  { id: 'DFF',      label: '联邦基金利率',    unit: '%',   hi: 5.5, lo: 0, higherBad: false },
  { id: 'BAA10Y',   label: 'HY 信用利差',     unit: '%',   hi: 4, lo: 1,   higherBad: true  },
  { id: 'T10Y2Y',   label: '10Y-2Y 利差',    unit: '%',   hi: 0, lo: -2,  higherBad: false },
  { id: 'M2SL',     label: 'M2 货币供应',     unit: 'B$',  hi: null, lo: null, higherBad: false },
];

function SnapshotCard({
  label, value, unit, pct, higherBad,
}: {
  label: string; value: number | null; unit: string; pct: number | null; higherBad: boolean;
}) {
  const displayVal = value !== null ? `${fmtNum(value)}${unit ? ' ' + unit : ''}` : '—';
  // 风险色：higherBad 时高值=红，低值=绿；反之相反
  let color = 'rgba(255,255,255,0.7)';
  if (pct !== null) {
    const stress = higherBad ? pct : (1 - pct);
    if (stress > 0.7) color = '#ef4444';
    else if (stress > 0.4) color = '#f59e0b';
    else color = '#34d399';
  }

  return (
    <div
      className="rounded-lg border border-white/8 bg-black/20 px-2.5 py-2 flex flex-col gap-0.5"
    >
      <div className="text-[10px] text-white/35 truncate">{label}</div>
      <div
        className="font-mono text-[15px] font-semibold tabular-nums leading-tight"
        style={{ color }}
      >
        {displayVal}
      </div>
      {pct !== null && (
        <div className="mt-0.5 h-0.5 w-full rounded-full bg-white/8">
          <div
            className="h-full rounded-full"
            style={{ width: `${Math.round(pct * 100)}%`, background: color }}
          />
        </div>
      )}
    </div>
  );
}

/**
 * 宏观快照面板 — FRED 关键序列最新值一览
 * 数据来自天枢 fred_history/*.csv，经 nginx 静态服务供开阳只读。
 */
export function MacroSnapshotPanel() {
  const { data: manifest } = useFeed<FredManifest>('fred');
  const { series, loading } = useFRED(manifest);

  const snapshots = useMemo(() => {
    return SNAPSHOT_IDS.map((def) => {
      const s = series.find((s) => s.id === def.id);
      const pts = s?.points ?? [];
      const last = pts.length ? pts[pts.length - 1] : null;
      const val = last ? last.value : null;

      // 归一化到 [0,1]（hi/lo 区间内）
      let pct: number | null = null;
      if (val !== null && def.hi !== null && def.lo !== null) {
        pct = Math.max(0, Math.min(1, (val - def.lo) / (def.hi - def.lo)));
      }

      // M2 用万亿美元展示
      let displayVal = val;
      let displayUnit = def.unit;
      if (def.id === 'M2SL' && val !== null) {
        displayVal = Math.round(val / 1000 * 10) / 10;
        displayUnit = 'T$';
      }

      return { ...def, value: displayVal, unit: displayUnit, pct, date: last?.date };
    });
  }, [series]);

  const lastUpdate = snapshots.find((s) => s.date)?.date;

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>📊 宏观快照</span>
        <span className="text-[10px] text-white/25">{lastUpdate ?? '—'}</span>
      </div>

      {loading && <div className="text-xs text-white/30">加载中…</div>}

      {!loading && (
        <div className="grid grid-cols-2 gap-1.5 overflow-y-auto">
          {snapshots.map((s) => (
            <SnapshotCard
              key={s.id}
              label={s.label}
              value={s.value}
              unit={s.unit}
              pct={s.pct}
              higherBad={s.higherBad}
            />
          ))}
        </div>
      )}

      <div className="mt-auto pt-1 text-[10px] text-white/20">
        来源：FRED，天枢每日05:30更新
      </div>
    </div>
  );
}
