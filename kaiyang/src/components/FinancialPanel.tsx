import { useEffect, useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import { EChart } from '@/components/EChart';
import { useFeed } from '@/hooks/useFeed';
import { fetchText } from '@/lib/readLayer';
import { fmtNum, fmtRelative } from '@/lib/format';
import { PALETTE, withAlpha } from '@/config/theme';
import type { FciDailyPoint, FciLatestRaw, FredPoint } from '@/types/contracts';

/** fci_daily.csv 尾部近 N 个交易日（约一年） */
const FCI_WINDOW = 260;

/** 解析 fci_daily.csv（列：date,fci_revised,fci_pit,...）。na/空 → null。 */
function parseFciDaily(text: string): FciDailyPoint[] {
  const out: FciDailyPoint[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.startsWith('date,')) continue;
    const cols = line.split(',');
    const date = cols[0]?.trim();
    if (!date) continue;
    const revised = cols[1]?.trim();
    const pit = cols[2]?.trim();
    out.push({
      date,
      revised: revised && revised !== 'na' && Number.isFinite(Number(revised)) ? Number(revised) : null,
      pit: pit && pit !== 'na' && Number.isFinite(Number(pit)) ? Number(pit) : null,
    });
  }
  return out;
}

/** FCI 松紧标签（以 0 为长期均值锚；>0 偏紧）。 */
function fciRegime(v: number | null): { label: string; color: string } {
  if (v === null || !Number.isFinite(v)) return { label: '数据缺失', color: PALETTE.slate };
  if (v > 0.5) return { label: '偏紧', color: PALETTE.amber };
  if (v < -0.5) return { label: '偏松', color: PALETTE.teal };
  return { label: '中性', color: PALETTE.cyan };
}

/**
 * R-3 金融条件面板：FCI（全样本/扩展窗双轨，日频趋势）+ GSCPI（月度）。
 * 数据：fci_latest.json（最新值）+ fci_daily.csv（趋势）+ fred_history/GSCPI.csv（月度）。
 */
export function FinancialPanel() {
  const { data: fci, loading: fciLoading, error: fciError } = useFeed<FciLatestRaw>('fci_latest');
  const { data: gscpi, loading: gscpiLoading, error: gscpiError } = useFeed<FredPoint[]>('gscpi');
  const [daily, setDaily] = useState<FciDailyPoint[]>([]);
  const [dailyError, setDailyError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchText('fci_daily.csv')
      .then((t) => {
        if (!cancelled) setDaily(parseFciDaily(t));
      })
      .catch((e) => {
        if (!cancelled) setDailyError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const trend = useMemo(() => daily.slice(-FCI_WINDOW), [daily]);

  const fciVal = fci?.fci_revised ?? null;
  const fciReg = fciRegime(fciVal);
  const gscpiLast: FredPoint | null = gscpi && gscpi.length > 0 ? gscpi[gscpi.length - 1] : null;
  const gscpiTrend = useMemo(() => (gscpi ?? []).slice(-36), [gscpi]);

  const option = useMemo<EChartsOption>(() => {
    if (trend.length === 0 && gscpiTrend.length === 0) return {};
    const dates = trend.map((p) => p.date);
    return {
      grid: { left: 42, right: 42, top: 14, bottom: 22 },
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['FCI', 'GSCPI'],
        textStyle: { color: PALETTE.textDim, fontSize: 10 },
        top: 0,
        right: 8,
      },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLabel: { color: PALETTE.textDim, hideOverlap: true, fontSize: 9 },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      },
      yAxis: [
        {
          type: 'value',
          name: 'FCI σ',
          scale: true,
          splitNumber: 3,
          nameTextStyle: { color: PALETTE.textDim, fontSize: 9 },
          axisLabel: { color: PALETTE.textDim, fontSize: 9 },
          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
        },
        {
          type: 'value',
          name: 'GSCPI',
          scale: true,
          splitNumber: 3,
          nameTextStyle: { color: PALETTE.textDim, fontSize: 9 },
          axisLabel: { color: PALETTE.textDim, fontSize: 9 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: 'FCI',
          type: 'line',
          yAxisIndex: 0,
          data: trend.map((p) => (p.revised === null ? null : p.revised)),
          showSymbol: false,
          connectNulls: true,
          lineStyle: { color: PALETTE.cyan, width: 1.5 },
          areaStyle: { color: withAlpha(PALETTE.cyan, 0.08) },
        },
        {
          name: 'GSCPI',
          type: 'line',
          yAxisIndex: 1,
          data: gscpiTrend.map((p) => p.value),
          showSymbol: true,
          symbolSize: 3,
          lineStyle: { color: PALETTE.amber, width: 1.2 },
        },
      ],
    };
  }, [trend, gscpiTrend]);

  const loading = fciLoading || gscpiLoading;
  const error = fciError || gscpiError;

  return (
    <div className="glass-panel scanlines flex h-full flex-col">
      <div className="panel-title flex items-center justify-between">
        <span>💰 金融条件 · FCI / GSCPI</span>
        <span className="text-[10px] font-normal text-white/30">
          更新 {fmtRelative(fci?.as_of ?? fci?.date)}
        </span>
      </div>

      {error && <div className="text-[11px] text-amber-300">读取失败</div>}
      {loading && !error && <div className="text-[11px] text-white/40">加载中…</div>}

      {/* ── FCI 头条 ── */}
      <div className="mb-1.5 flex items-center gap-3 rounded-xl border px-3 py-2"
        style={{ borderColor: withAlpha(fciReg.color, 0.35), background: withAlpha(fciReg.color, 0.07) }}
      >
        <div>
          <div className="text-[9px] tracking-widest text-white/40">金融条件指数 FCI</div>
          <div className="font-mono text-2xl font-semibold leading-tight" style={{ color: fciReg.color, textShadow: `0 0 16px ${withAlpha(fciReg.color, 0.4)}` }}>
            {fmtNum(fciVal, 3)}
          </div>
          <div className="text-[9px] text-white/35">
            {fci?.date ?? '—'} · 数据谱系 {fci?.data_vintage ?? '—'}
          </div>
        </div>
        <div className="ml-auto text-right">
          <div className="rounded-md px-2 py-0.5 text-[11px] font-semibold" style={{ color: fciReg.color, background: withAlpha(fciReg.color, 0.12) }}>
            {fciReg.label}
          </div>
          <div className="mt-1 text-[9px] text-white/30">越高 = 金融条件越紧（标准差）</div>
        </div>
      </div>

      {/* ── GSCPI 头条 ── */}
      <div className="mb-1.5 flex items-center justify-between rounded-xl border border-white/8 bg-black/20 px-3 py-1.5">
        <div className="text-[10px] text-white/50">全球供应链压力 GSCPI（月度）</div>
        <div className="font-mono text-base font-semibold" style={{ color: PALETTE.amber }}>
          {gscpiLast ? fmtNum(gscpiLast.value, 3) : '—'}
          <span className="ml-2 text-[10px] font-normal text-white/30">{gscpiLast?.date ?? ''}</span>
        </div>
      </div>

      {/* ── 双轴趋势图 ── */}
      <div className="min-h-0 flex-1">
        {dailyError && trend.length === 0 && (
          <div className="text-[10px] text-amber-300">FCI 历史缺失：{dailyError}</div>
        )}
        {!dailyError && trend.length === 0 && !loading && (
          <div className="text-[10px] text-white/35">暂无趋势数据</div>
        )}
        <EChart option={option} className="h-full w-full" />
      </div>

      {/* ── FCI 成分（折叠信息） ── */}
      {fci?.components && fci.components.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-[10px] text-white/35 hover:text-white/60">
            FCI 成分分解（{fci.components.length}）
          </summary>
          <div className="mt-1 flex flex-wrap gap-1">
            {fci.components.map((c) => (
              <span key={c.series_id ?? c.name} className="chip text-[9px] text-white/45">
                {c.name}
              </span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
