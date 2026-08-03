import { useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from '@/components/EChart';
import { useFeed } from '@/hooks/useFeed';
import { fmtStamp } from '@/lib/format';

interface Quote {
  key: string;
  name: string;
  price?: number | null;
  value?: number | null;
  change_pct?: number | null;
  unit?: string;
  date?: string;
  as_of?: string;
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

function PriceTile({ q, large }: { q: Quote; large?: boolean }) {
  const val = q.price ?? q.value ?? null;
  const pct = q.change_pct ?? null;
  const isUp   = pct !== null && pct > 0;
  const isDown = pct !== null && pct < 0;

  const valColor  = isUp ? '#34d399' : isDown ? '#f87171' : 'rgba(255,255,255,0.75)';
  const pctColor  = isUp ? '#34d399' : isDown ? '#f87171' : 'rgba(255,255,255,0.4)';
  const pctPrefix = isUp ? '▲' : isDown ? '▼' : '';

  const fmtVal = (v: number | null | undefined) => {
    if (v === null || v === undefined) return '—';
    if (Math.abs(v) >= 10000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (Math.abs(v) >= 100)   return v.toLocaleString('en-US', { maximumFractionDigits: 1 });
    return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  };

  return (
    <div className="rounded border border-white/8 bg-black/25 px-2 py-1.5 flex flex-col gap-0.5">
      <div className="text-[10px] tracking-wider text-white/35 uppercase truncate">{q.name}</div>
      <div
        className={`font-mono font-semibold tabular-nums leading-tight ${large ? 'text-[18px]' : 'text-[14px]'}`}
        style={{ color: pct !== null ? valColor : 'rgba(255,255,255,0.8)' }}
      >
        {q.unit === 'USD' && val !== null && val !== undefined && '$'}
        {fmtVal(val)}
        {q.unit && !['USD', ''].includes(q.unit) && (
          <span className="ml-0.5 text-[10px] font-normal text-white/30">{q.unit}</span>
        )}
      </div>
      {pct !== null && (
        <div className="text-[11px] font-mono" style={{ color: pctColor }}>
          {pctPrefix}{Math.abs(pct).toFixed(2)}%
        </div>
      )}
      {q.date && !q.as_of && (
        <div className="text-[9px] text-white/20">{q.date}</div>
      )}
    </div>
  );
}

function Section({ title, items, cols = 3 }: { title: string; items: Quote[]; cols?: number }) {
  if (!items.length) return null;
  const gridClass = cols === 4 ? 'grid-cols-4' : cols === 2 ? 'grid-cols-2' : 'grid-cols-3';
  return (
    <div>
      <div className="mb-1 text-[10px] tracking-widest text-white/30 uppercase">{title}</div>
      <div className={`grid gap-1.5 ${gridClass}`}>
        {items.map((q) => <PriceTile key={q.key} q={q} />)}
      </div>
    </div>
  );
}

/**
 * MarketsPanel — 市场行情一览（仿 crucix MACRO + MARKETS）
 * 数据来自天枢 market_quotes.json（整合 commodity_yahoo + crypto + FRED）
 */
export function MarketsPanel() {
  const { data, loading, error } = useFeed<MarketQuotesRaw>('market_quotes');

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between gap-2">
        <span>📈 MACRO + MARKETS</span>
        <span className="rounded-sm bg-accent/20 px-1.5 py-0.5 text-[10px] font-mono text-accent">
          {data?.updated ? fmtStamp(data.updated) : 'LOADING'}
        </span>
      </div>

      {loading && <div className="text-xs text-white/30">加载中…</div>}
      {error   && <div className="text-xs text-amber-300">读取失败</div>}

      {!loading && !error && data && (
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto pr-0.5">

          {/* 指数 */}
          <Section title="INDEXES" items={data.indexes ?? []} cols={4} />

          {/* 加密 */}
          <Section title="CRYPTO" items={data.crypto ?? []} cols={2} />

          {/* 能源 + 金属 */}
          {(() => {
            const em = [...(data.energy ?? []), ...(data.metals ?? [])];
            if (!em.length) return null;
            return (
              <div>
                <div className="mb-1 text-[10px] tracking-widest text-white/30 uppercase">
                  ENERGY + METALS
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  {em.map((q) => <PriceTile key={q.key} q={q} />)}
                </div>
              </div>
            );
          })()}

          {/* 宏观 */}
          {(data.macro ?? []).length > 0 && (
            <div>
              <div className="mb-1 text-[10px] tracking-widest text-white/30 uppercase">MACRO</div>
              <div className="grid grid-cols-3 gap-1.5">
                {(data.macro ?? []).map((q) => <PriceTile key={q.key} q={q} />)}
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
