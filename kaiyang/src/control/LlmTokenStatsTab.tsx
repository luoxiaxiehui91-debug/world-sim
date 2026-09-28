/**
 * LLM token 用量面板（只读）
 * 数据源：GET /api/v1/control/llm-token-stats?days=N（后端 control_server.py）
 * 与「LLM 配置」面板不同：这里看的是**实际消耗**，不是使用点配置。
 */

import { useState } from 'react';
import { useLlmTokenStats } from '@/hooks/useControlApi';
import type { TokenBucket } from '@/types/control';

const DAY_OPTIONS = [7, 14, 30];

function fmt(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('en-US');
}

function Row({ label, bucket }: { label: string; bucket: TokenBucket }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-white/5 bg-white/[0.02] px-2 py-1">
      <span className="truncate text-[10px] text-white/70">{label}</span>
      <span className="shrink-0 text-[10px] tabular-nums text-white/50">
        {fmt(bucket.calls)} 次 · {fmt(bucket.total_tokens)} tok
        {bucket.failures > 0 ? (
          <span className="ml-1 text-red-400">失败 {fmt(bucket.failures)}</span>
        ) : null}
      </span>
    </div>
  );
}

export function LlmTokenStatsTab() {
  const [days, setDays] = useState(7);
  const { data, loading, error, refresh } = useLlmTokenStats(days);

  const byDay = data
    ? Object.entries(data.by_day).sort((a, b) => (a[0] < b[0] ? 1 : -1))
    : [];
  const byUsage = data
    ? Object.entries(data.by_usage).sort((a, b) => b[1].total_tokens - a[1].total_tokens)
    : [];

  return (
    <div className="space-y-2 py-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-cyan-300/90">LLM token 用量</span>
        <div className="flex items-center gap-1">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={
                'rounded border px-1.5 py-0.5 text-[9px] transition-colors ' +
                (d === days
                  ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-300/90'
                  : 'border-white/5 bg-white/[0.02] text-white/45 hover:text-white/70')
              }
            >
              {d}天
            </button>
          ))}
          <button
            type="button"
            onClick={refresh}
            className="rounded border border-white/5 bg-white/[0.02] px-1.5 py-0.5 text-[9px] text-white/45 hover:text-white/70"
          >
            刷新
          </button>
        </div>
      </div>

      {loading && <div className="text-[10px] text-white/40">加载中…</div>}
      {error && <div className="text-[10px] text-red-400">{error}</div>}
      {!loading && !error && !data && (
        <div className="text-[10px] text-white/40">暂无数据（端点未返回）</div>
      )}

      {data && (
        <>
          <div className="rounded-md border border-cyan-400/20 bg-cyan-400/[0.04] px-2 py-1.5">
            <div className="flex items-baseline justify-between">
              <span className="text-[10px] text-white/50">近 {data.days} 天合计</span>
              <span className="text-[11px] tabular-nums text-cyan-300/90">
                {fmt(data.total.total_tokens)} tokens
              </span>
            </div>
            <div className="mt-0.5 text-[9px] tabular-nums text-white/45">
              {fmt(data.total.calls)} 次调用 · 提示 {fmt(data.total.prompt_tokens)} ·
              补全 {fmt(data.total.completion_tokens)}
              {data.total.failures > 0 ? (
                <span className="ml-1 text-red-400">· 失败 {fmt(data.total.failures)}</span>
              ) : null}
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] text-white/50">按用途</div>
            {byUsage.length === 0 ? (
              <div className="text-[9px] text-white/35">无</div>
            ) : (
              byUsage.map(([k, v]) => <Row key={k} label={k} bucket={v} />)
            )}
          </div>

          <div className="space-y-1">
            <div className="text-[10px] text-white/50">按日（近 {byDay.length} 天）</div>
            {byDay.length === 0 ? (
              <div className="text-[9px] text-white/35">无</div>
            ) : (
              byDay.map(([k, v]) => <Row key={k} label={k} bucket={v} />)
            )}
          </div>

          <div className="space-y-1">
            <div className="text-[10px] text-white/50">明细（按用量降序，最多 8 行）</div>
            {data.rows.slice(0, 8).map((r, i) => (
              <div
                key={`${r.d}-${r.usage_id}-${r.model}-${i}`}
                className="rounded-md border border-white/5 bg-white/[0.02] px-2 py-1"
              >
                <div className="flex items-center justify-between">
                  <span className="truncate text-[10px] text-white/70">
                    {r.d} · {r.usage_id || '(none)'}
                  </span>
                  <span className="shrink-0 text-[10px] tabular-nums text-white/50">
                    {fmt(r.total_tokens)} tok
                  </span>
                </div>
                <div className="truncate text-[9px] text-white/35">
                  {r.model || '—'}
                  {r.avg_ms ? ` · 均 ${fmt(Math.round(r.avg_ms))}ms` : ''}
                  {` · ${fmt(r.calls)} 次`}
                </div>
              </div>
            ))}
          </div>

          <div className="text-[9px] text-white/30">
            日界按北京时间 · 数据源 public.llm_token_usage_daily
          </div>
        </>
      )}
    </div>
  );
}
