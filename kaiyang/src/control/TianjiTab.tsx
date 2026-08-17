/**
 * 天玑 Tab 主组件（v1.11.31 只读版）
 *
 * 校验层（天玑）状态展示：校验触发 watchdog 状态 + PG 预测存档统计/最近列表
 * + 推理溯源计数 + 玉衡权重更新日志。
 * 只读：不触发验证、不审批权重（控制面二期）。
 *
 * 数据源：
 *  - tianji_trigger.json（天枢 write_tianji_trigger.py / 天玑 verify_watchdog.py 契约）
 *  - tianji_summary.json（天枢 tianji_summary_export.py I30 每 30 分钟导出）
 */

import { useFeed } from '@/hooks/useFeed';
import { PALETTE, withAlpha } from '@/config/theme';
import type { TianjiSummaryRaw, TianjiTriggerRaw } from '@/types/contracts';

/** 预测状态徽标配色。 */
const STATUS_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  awaiting_human: { label: '待人工', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
  pending: { label: '待验证', color: '#5eead4', bg: 'rgba(45,212,191,0.12)' },
  verified: { label: '已验证', color: '#86efac', bg: 'rgba(134,239,172,0.12)' },
  data_unavailable: { label: '数据缺失', color: 'rgba(255,255,255,0.5)', bg: 'rgba(255,255,255,0.08)' },
};

function statusBadge(status?: string) {
  const s = STATUS_STYLE[status ?? ''] ?? { label: status ?? '—', color: 'rgba(255,255,255,0.55)', bg: 'rgba(255,255,255,0.08)' };
  return (
    <span
      className="shrink-0 rounded px-1.5 py-0.5 text-[8px] font-medium"
      style={{ color: s.color, background: s.bg }}
    >
      {s.label}
    </span>
  );
}

/** 短 ID（前 10 字符）。 */
function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}

export function TianjiTab() {
  const { data: summary, loading: sumLoading } = useFeed<TianjiSummaryRaw | null>('tianjiSummary');
  const { data: trig } = useFeed<TianjiTriggerRaw | null>('tianjiTrigger');

  const pred = summary?.predictions;
  const weight = summary?.weight_update_log;
  const exit = trig?.last_result?.exit;

  return (
    <div className="flex flex-col gap-3">
      {/* ── 校验触发状态卡片 ─────────────────────────────── */}
      <div
        className="rounded border p-2.5"
        style={{
          borderColor: exit === 0 ? 'rgba(45,212,191,0.30)' : 'rgba(255,255,255,0.10)',
          background: exit === 0 ? 'rgba(45,212,191,0.05)' : 'rgba(255,255,255,0.03)',
        }}
        aria-label="天玑校验触发状态"
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
            校验触发状态
          </span>
          <span
            className="rounded px-1.5 py-0.5 text-[9px] font-medium"
            style={{
              color: trig?.processed ? 'rgba(255,255,255,0.45)' : '#fbbf24',
              background: trig?.processed ? 'rgba(255,255,255,0.06)' : 'rgba(251,191,36,0.12)',
            }}
          >
            {trig?.processed ? '已处理' : '待处理'}
          </span>
        </div>
        <div className="mt-1.5 space-y-0.5 text-[10px]" style={{ color: withAlpha(PALETTE.text, 0.7) }}>
          {trig ? (
            <>
              <div>
                批次：{trig.batch_id || '—'}
                {exit !== undefined && (
                  <span style={{ color: exit === 0 ? '#86efac' : '#f87171' }}>
                    ｜ 最近结果 exit={exit}（{exit === 0 ? '成功' : '失败'}）
                  </span>
                )}
              </div>
              <div className="text-white/35">
                触发：{trig.triggered_at || '—'}
                {trig.processed_at ? ` ｜ 处理：${trig.processed_at}` : ''}
              </div>
            </>
          ) : (
            <div className="text-white/35">今日校验批次尚未触发（scheduler 09:42 每日写 trigger）</div>
          )}
        </div>
      </div>

      {/* ── 预测存档统计 ─────────────────────────────────── */}
      <div className="rounded border border-white/10 bg-white/[0.02]">
        <div className="flex items-center justify-between border-b border-white/10 px-2.5 py-1.5">
          <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
            预测存档（PG tianji.predictions）
          </span>
          <span className="text-[9px] text-white/30">
            {sumLoading ? '加载中…' : summary?.updated?.slice(0, 16) || '—'}
          </span>
        </div>
        {!summary || summary.ok === false ? (
          <div className="px-2.5 py-4 text-center text-[10px] text-white/30">
            {summary?.ok === false ? `PG 导出降级：${summary.error ?? '不可读'}` : '暂无数据'}
          </div>
        ) : (
          <div className="px-2.5 py-2">
            {/* 统计行：总量 + 类型 + 状态 */}
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-semibold" style={{ color: withAlpha(PALETTE.text, 0.95) }}>
                {pred?.total ?? 0}
              </span>
              <span className="text-[9px] text-white/30">条</span>
              <span className="ml-auto flex gap-1">
                {Object.entries(pred?.by_type ?? {}).map(([t, n]) => (
                  <span key={t} className="rounded bg-white/5 px-1.5 py-0.5 text-[8px] text-white/50">
                    {t} {n}
                  </span>
                ))}
              </span>
            </div>
            {/* 状态分布条 */}
            {Object.entries(pred?.by_status ?? {}).length > 0 && (
              <div className="mt-1.5 flex h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                {Object.entries(pred!.by_status!).map(([st, n]) => {
                  const style = STATUS_STYLE[st];
                  const total = pred?.total || 1;
                  return (
                    <div
                      key={st}
                      title={`${st}: ${n}`}
                      style={{ width: `${(n / total) * 100}%`, background: style?.color ?? 'rgba(255,255,255,0.3)' }}
                    />
                  );
                })}
              </div>
            )}
            <div className="mt-1 flex flex-wrap gap-x-2 text-[8px] text-white/30">
              {Object.entries(pred?.by_status ?? {}).map(([st, n]) => {
                const style = STATUS_STYLE[st];
                return (
                  <span key={st} className="flex items-center gap-1">
                    <i className="h-1 w-1 rounded-full" style={{ background: style?.color ?? '#888' }} />
                    {style?.label ?? st} {n}
                  </span>
                );
              })}
              <span className="ml-auto">
                推理追溯 {summary?.reasoning_trace?.total ?? 0} 条 ｜ 权重更新 {weight?.total ?? 0} 条
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── 最近预测列表 ─────────────────────────────────── */}
      <div className="rounded border border-white/10 bg-white/[0.02]">
        <div className="border-b border-white/10 px-2.5 py-1.5 text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
          最近预测
        </div>
        {!pred?.recent?.length ? (
          <div className="px-2.5 py-3 text-center text-[10px] text-white/30">暂无预测记录</div>
        ) : (
          <ul className="max-h-[200px] divide-y divide-white/5 overflow-y-auto">
            {pred.recent.map((r) => (
              <li key={r.id} className="px-2.5 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[10px]" style={{ color: withAlpha(PALETTE.text, 0.8) }}>
                    {r.scenario_id || shortId(r.id)}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    {r.type === 'quantitative' && r.final_prob != null && (
                      <span className="text-[8px] text-white/40">{Math.round(r.final_prob * 100)}%</span>
                    )}
                    {statusBadge(r.status)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[8px] text-white/30">
                  {r.type && <span>{r.type}</span>}
                  {r.target_direction && <span>方向 {r.target_direction}</span>}
                  {r.confidence_tier && <span>{r.confidence_tier}</span>}
                  {r.due_at && <span className="ml-auto">验证至 {r.due_at.slice(0, 10)}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── 权重更新日志（玉衡联动） ─────────────────────── */}
      {weight?.recent?.length ? (
        <div className="rounded border border-white/10 bg-white/[0.02]">
          <div className="border-b border-white/10 px-2.5 py-1.5 text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
            最近权重更新
          </div>
          <ul className="divide-y divide-white/5">
            {weight.recent.map((w) => (
              <li key={w.id} className="px-2.5 py-1.5">
                <div className="flex items-center justify-between text-[10px]" style={{ color: withAlpha(PALETTE.text, 0.8) }}>
                  <span className="truncate">{w.signal_name || `#${w.id}`}</span>
                  <span className="shrink-0 text-[8px] text-white/35">
                    {w.weight_before} → {w.weight_after}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-[8px] text-white/30">{w.reason || w.target_type}</div>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-[9px] leading-relaxed text-white/25">
          权重更新日志为空——verify_auto（每月 1 日）执行验证并反哺权重后出现。
        </p>
      )}

      <p className="text-[9px] leading-relaxed text-white/25">
        只读视图：触发验证 / 权重审批属控制面二期，建设中。数据源 = 天枢 tianji_summary_export.py
        （每 30 分钟导出 PG）＋ tianji_trigger.json（watchdog 契约）。
      </p>
    </div>
  );
}
