import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import { fmtStamp } from '@/lib/format';
import { PALETTE, withAlpha } from '@/config/theme';
import type { SimTriggerRaw } from '@/types/contracts';

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-white/5 py-1 last:border-b-0">
      <span className="shrink-0 text-[10px] tracking-wider text-white/35">{label}</span>
      <span className="truncate text-right font-mono text-[11px]" style={{ color: tone ?? 'rgba(255,255,255,0.75)' }}>
        {value}
      </span>
    </div>
  );
}

/**
 * 侧栏状态小卡：把顶部状态条的时间戳 / schema 版本 / 缺失告警 / 推演触发做成可嵌入卡片。
 * 与 StatusBar 共用 StatusContext，不重复采集，纯读取展示。
 *
 * 告警过滤：以下属于"已知结构性缺失"，暂无数据源，不在此面板显示：
 *   - market_quotes（无行情接入）
 *   - nuclear（辐射读数无真实数据源）
 *   - news_geo（新闻地理化有延迟，空数组属正常）
 */
const KNOWN_STRUCTURAL_MISSING = new Set(['market_quotes', 'nuclear', 'news_geo']);

export function StatusMiniPanel() {
  const { warnings, timestamps, dataVersions } = useStatus();
  const { data: sim } = useFeed<SimTriggerRaw | null>('simTrigger');
  const triggered = sim?.triggered === true;
  const schemaText =
    Object.entries(dataVersions)
      .map(([k, v]) => `${k}:${v ?? '缺失'}`)
      .join(' ') || '—';

  const actionableWarnings = warnings.filter(
    (w) => !KNOWN_STRUCTURAL_MISSING.has(w.feed)
  );

  return (
    <div className="glass-panel scanlines flex h-full min-h-[200px] flex-col">
      <div className="panel-title">🛰️ 数据状态</div>

      <div className="rounded-xl border border-white/5 bg-black/20 px-2.5 py-1.5">
        <Row label="GRV 时间" value={fmtStamp(timestamps['grv'])} />
        <Row label="GDELT 时间" value={fmtStamp(timestamps['grv_gdelt'])} />
        <Row label="新闻时间" value={fmtStamp(timestamps['news'])} />
        <Row label="SCHEMA" value={schemaText} />
        <Row
          label="推演触发"
          value={triggered ? `已触发 ${sim?.level ?? ''}`.trim() : '未触发'}
          tone={triggered ? PALETTE.red : PALETTE.teal}
        />
      </div>

      <div className="mt-2 flex-1 overflow-y-auto pr-0.5">
        <div className="mb-1 text-[10px] tracking-widest text-white/35">
          缺失 / 异常告警（{actionableWarnings.length}）
        </div>
        {actionableWarnings.length === 0 ? (
          <div
            className="rounded-lg px-2 py-1 text-[11px]"
            style={{ background: withAlpha(PALETTE.teal, 0.08), color: PALETTE.teal }}
          >
            数据完整，无告警
          </div>
        ) : (
          <ul className="space-y-1">
            {actionableWarnings.map((w) => (
              <li
                key={`${w.feed}:${w.field}`}
                className="rounded-lg px-2 py-1 text-[11px] leading-snug"
                style={{ background: withAlpha(PALETTE.amber, 0.08), color: withAlpha(PALETTE.amber, 0.95) }}
                title={`${w.feed} · ${w.field}`}
              >
                {w.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
