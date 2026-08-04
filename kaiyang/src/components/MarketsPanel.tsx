import { useFeed } from '@/hooks/useFeed';
import { fmtStamp, fmtRelative } from '@/lib/format';

interface Quote {
  key: string;
  name: string;
  price?: number | null;
  value?: number | null;
  change_pct?: number | null;
  unit?: string;
  date?: string;
  as_of?: string;
  /** 5-day closing prices for sparkline (optional).
   *  Add this field to market_quotes.json items to enable mini chart. */
  spark5?: number[];
}

interface MarketQuotesRaw {
  _schema_version?: string;
  updated?: string;
  indexes?: Quote[];
  crypto?: Quote[];
  energy?: Quote[];
  metals?: Quote[];
  macro?: Quote[];
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmtVal(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return (v / 1_000_000).toLocaleString('en-US', { maximumFractionDigits: 2 }) + 'M';
  if (abs >= 10_000)    return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
  if (abs >= 100)       return v.toLocaleString('en-US', { maximumFractionDigits: 1 });
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

/** BTC / ETH / SOL / BNB get brand colors; everything else returns null. */
function cryptoBrandColor(key: string): string | null {
  const MAP: Record<string, string> = {
    BTC: '#f7931a',
    ETH: '#627eea',
    SOL: '#9945ff',
    BNB: '#f0b90b',
  };
  return MAP[key.toUpperCase()] ?? null;
}

/** wti / brent are crude oil — get special treatment on decline. */
function isCrudeOil(key: string): boolean {
  return ['wti', 'brent', 'crude_wti', 'crude_brent'].includes(key.toLowerCase());
}

// ─── Sparkline ────────────────────────────────────────────────────────────────

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null;
  const W = 52, H = 22, PAD = 2;
  const lo = Math.min(...data);
  const hi = Math.max(...data);
  const range = hi - lo || 1;

  const pts = data
    .map((v, i) => {
      const x = PAD + (i / (data.length - 1)) * (W - PAD * 2);
      const y = H - PAD - ((v - lo) / range) * (H - PAD * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const lastV = data[data.length - 1];
  const dotX  = (W - PAD).toFixed(1);
  const dotY  = (H - PAD - ((lastV - lo) / range) * (H - PAD * 2)).toFixed(1);

  return (
    <svg width={W} height={H} style={{ display: 'block', flexShrink: 0 }}>
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.75}
      />
      <circle cx={dotX} cy={dotY} r="2" fill={color} opacity={0.95} />
    </svg>
  );
}

// ─── LIVE badge ───────────────────────────────────────────────────────────────

function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
      </span>
      <span className="font-mono text-[10px] font-bold tracking-widest text-emerald-400">LIVE</span>
    </span>
  );
}

// ─── PriceTile ────────────────────────────────────────────────────────────────

interface TileProps {
  q: Quote;
  valueSize?: number;
  isCrypto?: boolean;
}

function PriceTile({ q, valueSize = 16, isCrypto }: TileProps) {
  const val = q.price ?? q.value ?? null;
  const pct = q.change_pct ?? null;
  const isUp   = pct !== null && pct > 0;
  const isDown = pct !== null && pct < 0;
  const crude  = isCrudeOil(q.key);

  const brandColor  = isCrypto ? cryptoBrandColor(q.key) : null;
  const changeColor = isUp ? '#34d399' : isDown ? '#f87171' : 'rgba(255,255,255,0.45)';
  const valueColor  = brandColor ?? (pct !== null ? changeColor : 'rgba(255,255,255,0.88)');
  const sparkColor  = brandColor ?? changeColor;
  const pctArrow    = isUp ? '▲' : isDown ? '▼' : '';
  const showDollar  = isCrypto || q.unit === 'USD';

  // Left accent bar via inset box-shadow (does not affect layout)
  const leftBarColor = isUp
    ? 'rgba(52,211,153,0.80)'
    : isDown
    ? 'rgba(248,113,113,0.80)'
    : 'rgba(255,255,255,0.07)';

  const brandGlow = brandColor
    ? `inset 0 1px 0 ${brandColor}28`
    : 'inset 0 1px 0 rgba(255,255,255,0.04)';

  // Crude oil falling: signal red background tint
  const bgColor = crude && isDown
    ? 'rgba(185,28,28,0.18)'
    : 'rgba(6,10,22,0.82)';

  return (
    <div
      style={{
        background:   bgColor,
        border:       '1px solid rgba(255,255,255,0.13)',
        borderRadius: '6px',
        padding:      '8px 10px 7px',
        display:      'flex',
        flexDirection: 'column',
        gap:           '4px',
        boxShadow:    `inset 2px 0 0 ${leftBarColor}, ${brandGlow}`,
        transition:   'background 0.3s ease',
      }}
    >
      {/* name label — 10px, uppercase, tracking-widest, dim */}
      <div
        style={{
          fontSize:      '10px',
          letterSpacing: '0.14em',
          color:         'rgba(255,255,255,0.30)',
          textTransform: 'uppercase',
          fontFamily:    'ui-monospace, "Cascadia Code", "SF Mono", monospace',
          fontWeight:    600,
          overflow:      'hidden',
          whiteSpace:    'nowrap',
          textOverflow:  'ellipsis',
        }}
      >
        {q.name}
      </div>

      {/* main value */}
      <div
        style={{
          fontFamily:    'ui-monospace, "Cascadia Code", "SF Mono", monospace',
          fontWeight:    700,
          fontSize:      `${valueSize}px`,
          lineHeight:    1.15,
          color:         valueColor,
          letterSpacing: '-0.01em',
        }}
      >
        {showDollar && val !== null && val !== undefined && (
          <span
            style={{
              fontSize:  Math.round(valueSize * 0.70) + 'px',
              opacity:   0.55,
              marginRight: '1px',
            }}
          >
            $
          </span>
        )}
        {fmtVal(val)}
        {q.unit && !['USD', ''].includes(q.unit) && (
          <span
            style={{
              fontSize:   '10px',
              opacity:    0.32,
              marginLeft: '3px',
              fontWeight: 400,
            }}
          >
            {q.unit}
          </span>
        )}
      </div>

      {/* change % row — 13px, bold, prominent */}
      {pct !== null && (
        <div
          style={{
            fontFamily:    'ui-monospace, "Cascadia Code", monospace',
            fontSize:      '13px',
            fontWeight:    700,
            color:         changeColor,
            lineHeight:    1,
            letterSpacing: '0.01em',
          }}
        >
          {pctArrow && <span style={{ marginRight: '2px' }}>{pctArrow}</span>}
          {Math.abs(pct).toFixed(2)}%
        </div>
      )}

      {/* sparkline row (only when spark5 present) */}
      {q.spark5 && q.spark5.length >= 2 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1px' }}>
          <Sparkline data={q.spark5} color={sparkColor} />
        </div>
      )}
    </div>
  );
}

// ─── Section ──────────────────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  items: Quote[];
  cols?: number;
  isCrypto?: boolean;
  valueSize?: number;
}

function Section({ title, items, cols = 3, isCrypto, valueSize }: SectionProps) {
  if (!items.length) return null;
  return (
    <div>
      {/* header: uppercase label + horizontal divider extending to right */}
      <div
        style={{
          display:       'flex',
          alignItems:    'center',
          gap:           '8px',
          marginBottom:  '8px',
        }}
      >
        <span
          style={{
            fontSize:      '10px',
            letterSpacing: '0.16em',
            color:         'rgba(255,255,255,0.25)',
            textTransform: 'uppercase',
            fontFamily:    'ui-monospace, monospace',
            fontWeight:    700,
            whiteSpace:    'nowrap',
          }}
        >
          {title}
        </span>
        <div
          style={{
            flex:       1,
            height:     '1px',
            background: 'rgba(255,255,255,0.07)',
          }}
        />
      </div>

      {/* tile grid */}
      <div
        style={{
          display:               'grid',
          gridTemplateColumns:   `repeat(${cols}, 1fr)`,
          gap:                   '7px',
        }}
      >
        {items.map((q) => (
          <PriceTile key={q.key} q={q} isCrypto={isCrypto} valueSize={valueSize} />
        ))}
      </div>
    </div>
  );
}

// ─── MarketsPanel ─────────────────────────────────────────────────────────────

/**
 * MarketsPanel — 市场行情一览（仿 crucix MACRO + MARKETS 终端视觉风格）
 *
 * 数据来自天枢 market_quotes.json（整合 commodity_yahoo + crypto + FRED）。
 * 可选：在各 Quote 对象中加 spark5: [c1,c2,c3,c4,c5] 字段以启用 sparkline。
 *
 * 视觉规范：
 *   - 标签 10px uppercase tracking-widest
 *   - 数值：指数/加密 20px，商品 16px，宏观 14px
 *   - 涨跌% 13px bold，单独一行
 *   - 卡片左侧 2px inset bar：涨绿跌红
 *   - 原油（WTI/Brent）下跌时红色底纹（重要信号）
 *   - BTC=#f7931a  ETH=#627eea
 */
export function MarketsPanel() {
  const { data, loading, error } = useFeed<MarketQuotesRaw>('market_quotes');
  const energyMetals = [...(data?.energy ?? []), ...(data?.metals ?? [])];

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      {/* ── header ── */}
      <div className="panel-title flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] font-bold tracking-widest">
            MACRO + MARKETS
          </span>
          {!loading && !error && data && <LiveBadge />}
        </div>
        <span
          style={{
            background:   'rgba(34,211,238,0.09)',
            border:       '1px solid rgba(34,211,238,0.20)',
            borderRadius: '3px',
            padding:      '2px 7px',
            fontSize:     '10px',
            fontFamily:   'monospace',
            color:        '#22d3ee',
            letterSpacing: '0.06em',
          }}
        >
          {data?.updated ? <span title={'更新于 ' + fmtRelative(data.updated)}>{fmtStamp(data.updated)}</span> : '—'}
        </span>
      </div>

      {/* ── loading / error ── */}
      {loading && (
        <div className="px-1 py-2 font-mono text-[11px] text-white/30">载入中…</div>
      )}
      {error && (
        <div className="px-1 py-2 font-mono text-[11px] text-amber-400">读取失败</div>
      )}

      {/* ── data ── */}
      {!loading && !error && data && (
        <div className="flex flex-1 flex-col gap-3.5 overflow-y-auto pr-0.5">
          <Section
            title="INDEXES"
            items={data.indexes ?? []}
            cols={4}
            valueSize={20}
          />
          <Section
            title="CRYPTO"
            items={data.crypto ?? []}
            cols={2}
            isCrypto
            valueSize={20}
          />
          {energyMetals.length > 0 && (
            <Section
              title="ENERGY + METALS"
              items={energyMetals}
              cols={3}
              valueSize={16}
            />
          )}
          {(data.macro ?? []).length > 0 && (
            <Section
              title="MACRO"
              items={data.macro ?? []}
              cols={3}
              valueSize={14}
            />
          )}
        </div>
      )}
    </div>
  );
}
