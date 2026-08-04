import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { fmtStamp, fmtRelative } from '@/lib/format';
import { PALETTE, withAlpha } from '@/config/theme';

interface SpaceTrackRaw {
  status?: string;
  updated?: string;
  total_active?: number;
  by_type?: { payload?: number; debris?: number; rocket_body?: number; unknown?: number };
  constellations?: { starlink?: number; oneweb?: number };
  new_objects_30d?: number;
  military_large_payload?: number;
  source?: string;
  note?: string;
}

function StatRow({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-white/5 py-1.5 last:border-b-0">
      <span className="shrink-0 text-[11px] text-white/40">{label}</span>
      <div className="text-right">
        <span
          className="font-mono text-[13px] font-semibold tabular-nums"
          style={{ color: color ?? 'rgba(255,255,255,0.85)' }}
        >
          {value ?? '—'}
        </span>
        {sub && <span className="ml-1.5 text-[10px] text-white/30">{sub}</span>}
      </div>
    </div>
  );
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div className="mt-0.5 h-1 w-full rounded-full bg-white/8">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

/**
 * 宇宙监视面板 — Space-Track.org 在轨卫星统计
 * 数据由天枢 fetch_spacetrack.py 每日采集，经 nginx 静态服务供开阳只读展示。
 */
export function SpaceWatchPanel() {
  const { data, loading, error } = useFeed<SpaceTrackRaw>('spacetrack');

  const total   = data?.total_active ?? 0;
  const payload = data?.by_type?.payload ?? 0;
  const debris  = data?.by_type?.debris ?? 0;
  const rocket  = data?.by_type?.rocket_body ?? 0;
  const starlink = data?.constellations?.starlink ?? 0;
  const oneweb   = data?.constellations?.oneweb ?? 0;
  const new30d   = data?.new_objects_30d ?? 0;

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>🛰️ 宇宙监视</span>
        <span className="font-mono text-[10px] font-normal text-white/25">
          {data?.updated ? <span title={'更新于 ' + fmtRelative(data.updated)}>{fmtStamp(data.updated)}</span> : '—'}
        </span>
      </div>

      {loading && <div className="text-xs text-white/30">加载中…</div>}
      {error && <div className="text-xs text-amber-300">读取失败</div>}

      {!loading && !error && data && (
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto">

          {/* 在轨总览 */}
          <div className="rounded-lg border border-white/8 bg-black/20 px-2.5 py-1.5">
            <div className="mb-1 text-[10px] tracking-widest text-white/30">在轨总览</div>
            <StatRow label="活跃在轨对象" value={total.toLocaleString()} color={PALETTE.teal} />
            <StatRow label="有效载荷" value={payload.toLocaleString()} sub={`${Math.round(payload/total*100)}%`} />
            <StatRow label="碎片" value={debris.toLocaleString()} sub={`${Math.round(debris/total*100)}%`} color="#f97316" />
            <StatRow label="火箭本体" value={rocket.toLocaleString()} />
            <StatRow label="近30天新增" value={new30d.toLocaleString()} color={PALETTE.amber} />
          </div>

          {/* 星座 */}
          <div className="rounded-lg border border-white/8 bg-black/20 px-2.5 py-1.5">
            <div className="mb-1 text-[10px] tracking-widest text-white/30">主要星座</div>
            <div className="space-y-2">
              <div>
                <StatRow
                  label="Starlink"
                  value={starlink.toLocaleString()}
                  sub={`${Math.round(starlink/payload*100)}% of payloads`}
                  color="#8b5cf6"
                />
                <MiniBar value={starlink} max={payload} color="#8b5cf6" />
              </div>
              <div>
                <StatRow
                  label="OneWeb"
                  value={oneweb.toLocaleString()}
                  color="#3b82f6"
                />
                <MiniBar value={oneweb} max={payload} color="#3b82f6" />
              </div>
            </div>
          </div>

          {/* 大国军事代理 */}
          <div className="rounded-lg border border-white/8 bg-black/20 px-2.5 py-1.5">
            <div className="mb-0.5 text-[10px] tracking-widest text-white/30">军事载荷代理 *</div>
            <StatRow
              label="US/RUS/CHN 大型载荷"
              value={(data?.military_large_payload ?? 0).toLocaleString()}
              color="#ef4444"
            />
            <div className="mt-1 text-[10px] leading-snug text-white/20">
              * 大型载荷（RCS Large）近似值，含商业卫星，非精确军事分类
            </div>
          </div>

          <div className="text-[10px] text-white/20">来源：{data.source}</div>
        </div>
      )}
    </div>
  );
}
