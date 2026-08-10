import { useFeed } from '@/hooks/useFeed';
import { severityColor, severityLabel, withAlpha, PALETTE } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { ReactNode } from 'react';
import type {
  ClimateSignalsRaw,
  DisasterSignalsRaw,
  EarthquakeRiskRaw,
  EnergyRiskRaw,
  UnavailableRiskRaw,
} from '@/types/contracts';

/* ── 通用小部件 ────────────────────────────────────────────────────────── */

/** 状态徽章：ok → 正常（青绿）；unavailable → 不可用（灰）；其他原样。 */
function StatusBadge({ status, updated }: { status?: string; updated?: string }) {
  if (!status) return <span className="text-[9px] text-white/30">—</span>;
  const ok = status === 'ok';
  const color = ok ? PALETTE.teal : PALETTE.slate;
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-wider"
      style={{ color, background: withAlpha(color, 0.12), border: `1px solid ${withAlpha(color, 0.35)}` }}
      title={updated}
    >
      {ok ? '正常' : status === 'unavailable' ? '不可用' : status}
    </span>
  );
}

/** 评分行：大数字 + 严重度进度条（与风险摘要 RiskRow 同款视觉）。 */
function ScoreBar({ label, value, unit }: { label: string; value: number | null | undefined; unit?: string }) {
  const color = severityColor(value);
  const pct = value === null || value === undefined ? 0 : Math.min(100, Math.max(0, value));
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] text-white/50">{label}</span>
        <span className="font-mono text-[13px] font-semibold" style={{ color }}>
          {fmtNum(value)}
          {unit && <span className="ml-0.5 text-[9px] text-white/30">{unit}</span>}
        </span>
      </div>
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${withAlpha(color, 0.45)}, ${color})`,
            boxShadow: `0 0 6px ${withAlpha(color, 0.5)}`,
          }}
        />
      </div>
    </div>
  );
}

/** 事件告警行（复用 Wave1 events[] 告警柱的色阶语义：value → severityColor）。 */
function EventRow({ label, detail, value }: { label: string; detail?: string; value: number | null }) {
  const color = severityColor(value);
  return (
    <div className="flex items-center gap-1.5 border-l-2 py-0.5 pl-1.5" style={{ borderColor: withAlpha(color, 0.6) }}>
      <span className="shrink-0 text-[10px] font-medium" style={{ color }}>
        {label}
      </span>
      {detail && <span className="min-w-0 truncate text-[9px] text-white/40" title={detail}>{detail}</span>}
    </div>
  );
}

/** 信号卡片壳：标题 + 状态徽章 + 内容区。 */
function SignalCard({ title, status, updated, children }: {
  title: string;
  status?: string;
  updated?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-white/8 bg-black/20 px-2.5 py-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-white/80">{title}</span>
        <StatusBadge status={status} updated={updated} />
      </div>
      {children}
    </div>
  );
}

/** 地震震级 → 0-100 严重度（M4→0，M8→100），供告警行着色。 */
function magToValue(mag: number | null | undefined): number | null {
  if (mag === null || mag === undefined || !Number.isFinite(mag)) return null;
  return Math.min(100, Math.max(0, ((mag - 4) / 4) * 100));
}

/* ── 面板主体 ───────────────────────────────────────────────────────────── */

/**
 * R-4 风险信号面板：6 类信号卡片（气候/灾害/地震/能源/HDX/新闻）。
 * 每个信号带评分条 + 事件告警行（复用 Wave1 events[] 的色阶语义）；缺失/不可用降级展示。
 */
export function RiskSignalsPanel() {
  const climate = useFeed<ClimateSignalsRaw>('climate_signals');
  const disaster = useFeed<DisasterSignalsRaw>('disaster_signals');
  const earthquake = useFeed<EarthquakeRiskRaw>('earthquake_risk');
  const energy = useFeed<EnergyRiskRaw>('energy_risk');
  const hdx = useFeed<UnavailableRiskRaw>('hdx_risk');
  const news = useFeed<UnavailableRiskRaw>('news_risk');

  return (
    <div className="glass-panel scanlines flex h-full min-h-[240px] flex-col">
      <div className="panel-title">🚨 风险信号</div>
      <div className="grid flex-1 grid-cols-2 gap-2 overflow-y-auto pr-0.5 lg:grid-cols-3">
        {/* ── 气候 ── */}
        <SignalCard title="气候风险" status={climate.data?.status} updated={climate.data?.updated}>
          <ScoreBar label="综合评分" value={climate.data?.climate_risk_score} />
          {climate.data?.oni && (
            <EventRow
              label={climate.data.oni.status ?? 'ONI'}
              detail={climate.data.oni.interpretation}
              value={climate.data.oni.value !== null && climate.data.oni.value !== undefined
                ? Math.min(100, Math.max(0, climate.data.oni.value * 20))
                : null}
            />
          )}
          {climate.data?.firms && (
            <div className="text-[9px] text-white/40">
              FIRMS 火点 {climate.data.firms.total_hotspots ?? 0}（高置信 {climate.data.firms.high_confidence ?? 0}）· {climate.data.firms.date ?? ''}
            </div>
          )}
          {climate.error && <div className="text-[10px] text-amber-300">读取失败</div>}
        </SignalCard>

        {/* ── 自然灾害 ── */}
        <SignalCard title="自然灾害" status={disaster.data?.status} updated={disaster.data?.updated}>
          <ScoreBar label="24h 风险评分" value={disaster.data?.disaster_risk_score} />
          <div className="text-[9px] text-white/40">24h 事件 {disaster.data?.event_count_24h ?? '—'} 起</div>
          {Array.isArray(disaster.data?.alerts) && disaster.data!.alerts!.length > 0 && (
            <div className="text-[9px] text-amber-300/80">告警：{disaster.data!.alerts!.length} 条</div>
          )}
          {disaster.error && <div className="text-[10px] text-amber-300">读取失败</div>}
        </SignalCard>

        {/* ── 地震 ── */}
        <SignalCard title="地震风险" status={earthquake.data?.status} updated={earthquake.data?.updated}>
          <ScoreBar label="地震风险" value={earthquake.data?.seismic_risk} unit="/100" />
          <div className="text-[9px] text-white/40">
            24h {earthquake.data?.event_count_24h ?? '—'} 起 · M≥4.5×{earthquake.data?.count_m45 ?? '—'} ·
            M≥5.5×{earthquake.data?.count_m55 ?? '—'} · M≥6.5×{earthquake.data?.count_m65 ?? '—'}
          </div>
          {(earthquake.data?.top_events ?? []).slice(0, 3).map((e, i) => (
            <EventRow
              key={`${e.time_utc ?? i}-${i}`}
              label={`M${fmtNum(e.magnitude, 1)}`}
              detail={e.place}
              value={magToValue(e.magnitude)}
            />
          ))}
          {earthquake.error && <div className="text-[10px] text-amber-300">读取失败</div>}
        </SignalCard>

        {/* ── 能源 ── */}
        <SignalCard title="能源 / 电网" status={energy.data?.status} updated={energy.data?.updated}>
          <ScoreBar label="电网碳风险" value={energy.data?.grid_carbon_risk} unit="/100" />
          {energy.data?.uk_grid && (
            <div className="text-[9px] text-white/40">
              碳强度预测 {energy.data.uk_grid.intensity_forecast ?? '—'} gCO₂/kWh ·{' '}
              {energy.data.uk_grid.intensity_index ?? '—'}
            </div>
          )}
          {energy.data?.national_grid_eso?.status === 'skipped' && (
            <div className="text-[9px] text-white/30">NESO 跳过：{energy.data.national_grid_eso.reason ?? ''}</div>
          )}
          {energy.error && <div className="text-[10px] text-amber-300">读取失败</div>}
        </SignalCard>

        {/* ── HDX 人道危机 ── */}
        <SignalCard title="人道危机 (HDX)" status={hdx.data?.status} updated={hdx.data?.updated}>
          {hdx.data?.status === 'unavailable' && (
            <div className="text-[9px] text-white/35">数据源不可用：{hdx.data?.reason ?? '—'}</div>
          )}
          {hdx.data?.source && <div className="text-[9px] text-white/25">来源 {hdx.data.source}</div>}
          {hdx.error && <div className="text-[10px] text-amber-300">读取失败</div>}
          {!hdx.error && !hdx.data && <div className="text-[9px] text-white/30">数据缺失</div>}
        </SignalCard>

        {/* ── 新闻风险 ── */}
        <SignalCard title="新闻风险" status={news.data?.status} updated={news.data?.updated}>
          {news.data?.status === 'unavailable' && (
            <div className="text-[9px] text-white/35">聚合源不可用（缺 API key）</div>
          )}
          {news.data?.source && <div className="text-[9px] text-white/25">来源 {news.data.source}</div>}
          {news.error && <div className="text-[10px] text-amber-300">读取失败</div>}
          {!news.error && !news.data && <div className="text-[9px] text-white/30">数据缺失</div>}
        </SignalCard>
      </div>
    </div>
  );
}
