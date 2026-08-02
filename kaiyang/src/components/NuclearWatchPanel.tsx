import { useMemo } from 'react';
import { categoryColor } from '@/config/layerCategories';
import { NUCLEAR_TYPE_LABEL } from '@/config/nuclearSites';
import { PALETTE, withAlpha } from '@/config/theme';
import { useFeed } from '@/hooks/useFeed';
import { fmtStamp } from '@/lib/format';
import { NUCLEAR_LEVEL_LABEL, formatReading, mergeNuclear } from '@/lib/nuclearData';
import type { NuclearRow } from '@/lib/nuclearData';
import type { NuclearLevel, NuclearSitesRaw } from '@/types/contracts';

/**
 * Nuclear Watch 面板：核设施辐射读数监视表。
 *
 * 降级策略（K5，四级全覆盖，任何路径不白屏）：
 * 1. feed 文件缺失 / HTTP 错误 → 顶部「数据缺失」提示条 + 表格照常用静态种子渲染站点；
 * 2. `sites` 为空数组 → 同上但不提示（空是合法业务态，由 mergeNuclear 回落种子）；
 * 3. 单站读数缺失 → 读数列显示「—」，等级列显示「未知」；
 * 4. 整体读数皆缺 → 底部脚注说明「读数待后端接入」。
 *
 * 本面板**不做任何领域判断**：分级优先用后端 `level`，前端只负责展示。
 */

/** 等级 → 展示色。unknown 走缺失灰，与地图缺失态同源（C2-A）。 */
function levelTone(level: NuclearLevel): string {
  switch (level) {
    case 'alert':
      return PALETTE.red;
    case 'elevated':
      return PALETTE.amber;
    case 'normal':
      return PALETTE.teal;
    default:
      return PALETTE.slate;
  }
}

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
  const reading = formatReading(row);
  const tone = levelTone(row.level);
  const typeLabel = site.type ? NUCLEAR_TYPE_LABEL[site.type] : '核设施';

  return (
    <tr className="border-b border-white/5 last:border-b-0">
      <td className="px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          {/* 菱形色块：与地图上的核设施符号形状一致，便于表↔图对照 */}
          <span
            aria-hidden
            className="inline-block h-2 w-2 shrink-0 rotate-45"
            style={{
              background: row.value === null ? 'transparent' : categoryColor('nuclear', 'ok'),
              border: `1px ${row.value === null ? 'dashed' : 'solid'} ${categoryColor(
                'nuclear',
                row.value === null ? 'missing' : 'ok',
              )}`,
            }}
          />
          <span className="truncate text-[11px] text-white/80" title={site.name_en ?? site.name}>
            {site.name}
          </span>
        </div>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-[10px] text-white/40">{site.country}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-[10px] text-white/30">{typeLabel}</td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[11px]" style={{ color: tone }}>
        {reading ?? '—'}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right">
        <span
          className="rounded px-1.5 py-0.5 text-[10px]"
          style={{ background: withAlpha(tone, 0.12), color: tone }}
        >
          {NUCLEAR_LEVEL_LABEL[row.level]}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] text-white/30">
        {row.updated ? fmtStamp(row.updated) : '—'}
      </td>
    </tr>
  );
}

export function NuclearWatchPanel() {
  const { data, loading, error } = useFeed<NuclearSitesRaw | null>('nuclearSites');

  // mergeNuclear 自带 nullish 兜底：error / loading 时同样返回种子站点，表格不空
  const rows = useMemo(() => mergeNuclear(data ?? null), [data]);

  const withReading = rows.filter((r) => r.reading !== null).length;
  const alertCount = rows.filter((r) => r.level === 'alert').length;
  // feed 明确失败才提示「数据缺失」；空数组属合法业务态，不提示（K5）
  const feedMissing = !loading && (error !== null || data === null);

  return (
    <div className="glass-panel scanlines flex h-full min-h-[200px] flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>☢️ 核设施监视</span>
        <span className="font-mono text-[10px] font-normal text-white/30">
          {rows.length} 站 · 有读数 {withReading}
          {alertCount > 0 ? ` · 告警 ${alertCount}` : ''}
        </span>
      </div>

      {feedMissing && (
        <div
          className="mb-2 rounded-lg px-2 py-1 text-[11px] leading-snug"
          style={{ background: withAlpha(PALETTE.amber, 0.1), color: withAlpha(PALETTE.amber, 0.95) }}
        >
          数据缺失：nuclear_sites.json 未就绪，以下为前端静态站点种子，读数暂不可用。
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-[#060b16]/95 backdrop-blur">
            <tr className="border-b border-white/10">
              <HeadCell>站点</HeadCell>
              <HeadCell>国家/地区</HeadCell>
              <HeadCell>类型</HeadCell>
              <HeadCell align="right">读数</HeadCell>
              <HeadCell align="right">等级</HeadCell>
              <HeadCell align="right">观测时间</HeadCell>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-2 py-6 text-center text-[11px] text-white/30">
                  暂无核设施站点
                </td>
              </tr>
            ) : (
              rows.map((r) => <SiteRow key={r.site.id} row={r} />)
            )}
          </tbody>
        </table>
      </div>

      {withReading === 0 && rows.length > 0 && (
        <div className="mt-1.5 shrink-0 text-[10px] leading-snug text-white/25">
          读数列全为「—」：辐射读数需后端 readings[] 提供，开阳不自连外部数据源。
          站点坐标为公开百科级近似值，仅作占位。
        </div>
      )}
    </div>
  );
}
