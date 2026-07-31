import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import { adaptGrv } from '@/lib/grvAdapter';
import { severityColor, withAlpha } from '@/config/theme';
import { fmtNum, fmtStamp } from '@/lib/format';
import type { GrvRaw, SimTriggerRaw } from '@/types/contracts';

function Stamp({ label, t }: { label: string; t: string | null | undefined }) {
  return (
    <span className="chip" title={`${label} 数据时间：${t ?? '未知'}`}>
      <span className="text-white/40">{label}</span>
      <span className="text-white/70">{fmtStamp(t)}</span>
    </span>
  );
}

/** 顶部状态条：综合指数 + 数据时间戳 + schema 版本 + 推演触发 + 缺失字段告警（扩展标准 #3）。 */
export function StatusBar() {
  const { warnings, timestamps, dataVersions } = useStatus();
  const { data: sim } = useFeed<SimTriggerRaw | null>('simTrigger');
  const { data: grv } = useFeed<GrvRaw>('grv');
  const model = useMemo(() => adaptGrv(grv), [grv]);
  const headline = model.headline;
  const headlineColor = severityColor(headline?.value ?? null);

  const simData = sim ?? null;
  const triggered = simData?.triggered === true;
  const warningText = warnings.map((w) => `· ${w.message}`).join('\n');
  const schemaText = Object.entries(dataVersions)
    .map(([k, v]) => `${k}:${v ?? '缺失'}`)
    .join('  ');

  return (
    <header className="glass scanlines mx-4 mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 text-xs">
      <div className="mr-2 flex items-center gap-2">
        <span className="title-glow font-bold tracking-[0.3em] text-accent">开阳</span>
        <span className="hidden text-white/40 sm:inline">WAVE 1 · 世界推演操作面板</span>
      </div>

      {headline && (
        <span
          className="chip"
          title={headline.note ?? '全球综合指数（无地理位置，不投影到地图）'}
          style={{
            borderColor: withAlpha(headlineColor, 0.5),
            background: withAlpha(headlineColor, 0.1),
          }}
        >
          <span className="text-white/45">{headline.label}</span>
          <b style={{ color: headlineColor }}>{fmtNum(headline.value)}</b>
        </span>
      )}

      <Stamp label="GRV" t={timestamps['grv']} />
      <Stamp label="GDELT" t={timestamps['grv_gdelt']} />
      <Stamp label="新闻" t={timestamps['news']} />
      <span className="chip" title="各 feed 实际 schema 版本">
        <span className="text-white/40">schema</span>
        <span className="text-white/70">{schemaText || '—'}</span>
      </span>
      {triggered ? (
        <span className="chip border-rose-400/50 text-rose-300" title={simData?.reason}>
          ⚠ 推演触发
        </span>
      ) : (
        <span className="chip border-emerald-400/40 text-emerald-300">推演未触发</span>
      )}
      {warnings.length > 0 ? (
        <span className="chip border-amber-400/50 text-amber-300" title={warningText}>
          ⚠ 缺失告警 {warnings.length}
        </span>
      ) : (
        <span className="chip border-emerald-400/40 text-emerald-300">数据完整</span>
      )}
    </header>
  );
}
