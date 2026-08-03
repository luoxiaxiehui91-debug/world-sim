import { useMemo } from 'react';
import { categoryColor } from '@/config/layerCategories';
import { NUCLEAR_TYPE_LABEL } from '@/config/nuclearSites';
import { withAlpha } from '@/config/theme';
import { useFeed } from '@/hooks/useFeed';
import { mergeNuclear } from '@/lib/nuclearData';
import type { NuclearRow } from '@/lib/nuclearData';
import type { NuclearSitesRaw } from '@/types/contracts';

/**
 * 核设施分布面板：展示全球核设施站点地理信息（公开百科级坐标）。
 * 无实时辐射读数——真实核监测数据无公开可接入 API，读数列已移除。
 */

function HeadCell({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      className={`whitespace-nowrap px-2 py-1 text-[10px] font-normal tracking-wider text-white/35 ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  );
}

function SiteRow({ row }: { row: NuclearRow }) {
  const { site } = row;
  const typeLabel = site.type ? NUCLEAR_TYPE_LABEL[site.type] : '核设施';
  const lat = site.lat != null ? site.lat.toFixed(1) : '—';
  const lng = site.lng != null ? site.lng.toFixed(1) : '—';

  return (
    <tr className="border-b border-white/5 last:border-b-0">
      <td className="px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-2 shrink-0 rotate-45"
            style={{
              background: withAlpha(categoryColor('nuclear', 'ok'), 0.5),
              border: `1px solid ${categoryColor('nuclear', 'ok')}`,
            }}
          />
          <span className="truncate text-[11px] text-white/80" title={site.name_en ?? site.name}>
            {site.name}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-[10px] text-white/40">{site.country}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-[10px] text-white/30">{typeLabel}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] text-white/25">
        {lat},{lng}
      </td>
    </tr>
  );
}

export function NuclearWatchPanel() {
  const { data, loading } = useFeed<NuclearSitesRaw | null>('nuclearSites');
  const rows = useMemo(() => mergeNuclear(data ?? null), [data]);

  const byType = useMemo(() => {
    const m: Record<string, number> = {};
    rows.forEach((r) => {
      const t = r.site.type ?? 'unknown';
      m[t] = (m[t] ?? 0) + 1;
    });
    return m;
  }, [rows]);

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>🏭 核设施分布</span>
        <span className="font-mono text-[10px] font-normal text-white/30">
          {rows.length} 站点 · 公开地理信息
        </span>
      </div>

      {/* 类型统计 */}
      {!loading && rows.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {Object.entries(byType).map(([type, count]) => (
            <span key={type} className="chip text-white/40">
              {NUCLEAR_TYPE_LABEL[type as keyof typeof NUCLEAR_TYPE_LABEL] ?? type} {count}
            </span>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-[#060b16]/95 backdrop-blur">
            <tr className="border-b border-white/10">
              <HeadCell>站点</HeadCell>
              <HeadCell>国家/地区</HeadCell>
              <HeadCell>类型</HeadCell>
              <HeadCell align="right">坐标</HeadCell>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-2 py-6 text-center text-[11px] text-white/30">
                  暂无核设施站点
                </td>
              </tr>
            ) : (
              rows.map((r) => <SiteRow key={r.site.id} row={r} />)
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-1.5 shrink-0 text-[10px] leading-snug text-white/20">
        来源：公开百科级站点坐标，仅作地理参考，无实时辐射读数。
      </div>
    </div>
  );
}
