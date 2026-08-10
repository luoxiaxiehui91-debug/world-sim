import { useMemo } from 'react';
import { categoryColor } from '@/config/layerCategories';
import { NUCLEAR_TYPE_LABEL } from '@/config/nuclearSites';
import { PALETTE, withAlpha } from '@/config/theme';
import { useFeed } from '@/hooks/useFeed';
import { mergeNuclear } from '@/lib/nuclearData';
import { fmtRelative } from '@/lib/format';
import type { NuclearRow } from '@/lib/nuclearData';
import type { NuclearSitesRaw, SafecastNukeRaw, SafecastSite } from '@/types/contracts';

/**
 * 核设施与辐射面板：
 * - 上段「辐射读数」：SafeCast 6 站 CPM（fetch_safecast_nuke.py，I60 每 60 分钟，
 *   CC0 公开 API，08-10 接入）。⚠ 数据为历史归档均值（latest_captured_at 多为
 *   2016-2023），anom=true 是长期背景非实时突发，只作背景状态展示。
 * - 下段「设施分布」：全球核设施站点地理信息（公开百科级坐标，nuclear_sites.json）。
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

const SITE_LABEL: Record<string, string> = {
  zaporizhzhia: '扎波罗热核电站',
  chernobyl: '切尔诺贝利禁区',
  bushehr: '布什尔核电站（伊朗）',
  yongbyon: '宁边（朝鲜）',
  fukushima: '福岛第一核电站',
  dimona: '迪莫纳（以色列）',
};

function ReadingRow({ s }: { s: SafecastSite }) {
  const label = s.site ?? SITE_LABEL[s.key] ?? s.key;
  const cpm = s.avgCPM;
  const anom = cpm !== null && s.anom;
  return (
    <tr className="border-b border-white/5 last:border-b-0">
      <td className="px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-2 shrink-0 rotate-45"
            style={{
              background: withAlpha(anom ? PALETTE.red : categoryColor('nuclear', 'ok'), 0.6),
              border: `1px solid ${anom ? PALETTE.red : categoryColor('nuclear', 'ok')}`,
              boxShadow: anom ? `0 0 8px ${withAlpha(PALETTE.red, 0.6)}` : undefined,
            }}
          />
          <span className="truncate text-[11px] text-white/80" title={label}>
            {label}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[11px]" style={{ color: cpm === null ? 'rgba(255,255,255,0.25)' : anom ? PALETTE.red : 'rgba(255,255,255,0.85)' }}>
        {cpm === null ? '—' : cpm.toFixed(2)}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-[10px] text-white/35">CPM</td>
      <td className="whitespace-nowrap px-2 py-1.5">
        {anom ? (
          <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-red-400">
            异常
          </span>
        ) : (
          <span className="text-[10px] text-white/25">正常</span>
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] text-white/30">
        n={s.n}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] text-white/25">
        {s.latest_captured_at ?? '—'}
      </td>
    </tr>
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
  const { data: sc, loading: scLoading, error: scError } = useFeed<SafecastNukeRaw | null>('safecast_nuke');
  const rows = useMemo(() => mergeNuclear(data ?? null), [data]);
  const readings = useMemo(() => sc?.sites ?? [], [sc]);

  const byType = useMemo(() => {
    const m: Record<string, number> = {};
    rows.forEach((r) => {
      const t = r.site.type ?? 'unknown';
      m[t] = (m[t] ?? 0) + 1;
    });
    return m;
  }, [rows]);

  const anomCount = useMemo(() => readings.filter((s) => s.avgCPM !== null && s.anom).length, [readings]);

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>核设施与辐射</span>
        <span className="font-mono text-[10px] font-normal text-white/30">
          {rows.length} 站点 · {readings.length} 监测站
          {sc?.fetched_at ? ` · ${fmtRelative(sc.fetched_at)}` : ''}
        </span>
      </div>

      {/* ── 辐射读数（SafeCast） ── */}
      <div className="mb-1 flex items-center gap-1.5">
        <span className="text-[10px] font-semibold tracking-widest" style={{ color: withAlpha(PALETTE.cyan, 0.9) }}>
          辐射读数 · SafeCast
        </span>
        {anomCount > 0 && (
          <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-red-400">
            {anomCount} 站异常
          </span>
        )}
        {sc?.degraded && <span className="text-[9px] text-amber-300">采集降级（重试耗尽）</span>}
      </div>
      {scError && <div className="mb-1 text-[10px] text-amber-300">辐射读数读取失败</div>}
      <div className="max-h-44 shrink-0 overflow-y-auto pr-0.5">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-[#060b16]/95 backdrop-blur">
            <tr className="border-b border-white/10">
              <HeadCell>监测站</HeadCell>
              <HeadCell align="right">CPM</HeadCell>
              <HeadCell>单位</HeadCell>
              <HeadCell>状态</HeadCell>
              <HeadCell align="right">样本</HeadCell>
              <HeadCell align="right">数据日期</HeadCell>
            </tr>
          </thead>
          <tbody>
            {scLoading ? (
              <tr><td colSpan={6} className="px-2 py-4 text-center text-[11px] text-white/30">加载读数…</td></tr>
            ) : readings.length === 0 ? (
              <tr><td colSpan={6} className="px-2 py-4 text-center text-[11px] text-white/30">暂无辐射读数</td></tr>
            ) : (
              readings.map((s) => <ReadingRow key={s.key} s={s} />)
            )}
          </tbody>
        </table>
      </div>

      {/* ── 设施分布 ── */}
      <div className="mt-2 mb-1 flex items-center gap-1.5">
        <span className="text-[10px] font-semibold tracking-widest" style={{ color: withAlpha(PALETTE.teal, 0.9) }}>
          设施分布
        </span>
        {!loading && rows.length > 0 && (
          <span className="flex flex-wrap gap-1">
            {Object.entries(byType).map(([type, count]) => (
              <span key={type} className="text-[9px] text-white/30">
                {NUCLEAR_TYPE_LABEL[type as keyof typeof NUCLEAR_TYPE_LABEL] ?? type} {count}
              </span>
            ))}
          </span>
        )}
      </div>
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
        读数：SafeCast CC0 公开网络（I60 采集）· 数据为历史归档均值（数据日期多为 2016-2023），异常为长期背景非实时告警。站点：公开百科级坐标，仅地理参考。
      </div>
    </div>
  );
}
