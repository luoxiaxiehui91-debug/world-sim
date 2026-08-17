/**
 * 天璇 Tab 主组件（v1.11.29 只读版）
 *
 * "只看不动"：展示推演触发状态 + 最近演化仿真报告列表，点击可读报告全文。
 * 触发 / 调参等写操作属控制面二期（天璇控制台待办），本期不实现。
 *
 * 数据源：
 *  - reports_index.json（天枢 generate_reports_index.py 产物）→ 过滤 type=演化仿真
 *  - sim_trigger.json（H18 统一契约）→ 当前触发/已消费状态
 *  - data/reports/*.md → 报告全文（fetchText + renderMarkdown，与报告面板同机制）
 */

import { useState, useMemo, useEffect } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { fetchText } from '@/lib/readLayer';
import { renderMarkdown } from '@/lib/markdown';
import { extractGovernanceEvents } from '@/lib/governance';
import { GovernanceCard } from '@/components/GovernanceCard';
import { PALETTE, withAlpha } from '@/config/theme';
import type { ReportsIndexRaw, ReportMeta, SimTriggerRaw } from '@/types/contracts';

/** 从报告文件名解析 级别/校准分：2026-08-17_13-39_演化_L2_校准51.4.md */
function parseSimMeta(filename: string): { level: number; score: string } | null {
  const m = /_L(\d)_校准([\d.]+)\.md$/.exec(filename);
  return m ? { level: Number(m[1]), score: m[2] } : null;
}

/** 本地今天 YYYY-MM-DD（与 ReportsPanel 同口径）。 */
function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function TianxuanTab() {
  const { data: indexData, loading: indexLoading } = useFeed<ReportsIndexRaw>('reports_index');
  const { data: sim } = useFeed<SimTriggerRaw | null>('simTrigger');

  // 演化仿真报告（天璇产物），按 updated 倒序
  const simReports = useMemo(() => {
    const arr = (indexData?.reports ?? []).filter((r) => r.type === '演化仿真');
    return [...arr].sort(
      (a, b) => b.updated.localeCompare(a.updated) || b.filename.localeCompare(a.filename),
    );
  }, [indexData]);

  const [selected, setSelected] = useState<ReportMeta | null>(null);
  const [md, setMd] = useState<string>('');
  const [mdLoading, setMdLoading] = useState(false);
  const [mdError, setMdError] = useState<string | null>(null);
  // v1.11.30 政权更迭事件：解析一次缓存，卡片 + 剥离节后的正文（与报告面板同机制）
  const gov = useMemo(() => extractGovernanceEvents(md), [md]);

  // 选中变化 → 拉取 markdown 全文（与 ReportsPanel 同机制）
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setMdLoading(true);
    setMdError(null);
    fetchText(selected.path)
      .then((text) => {
        if (!cancelled) {
          setMd(text);
          setMdLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setMdError(e instanceof Error ? e.message : String(e));
          setMdLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  // 默认选中最新一份
  useEffect(() => {
    if (!selected && simReports.length > 0) setSelected(simReports[0]);
  }, [simReports, selected]);

  const today = todayStr();
  const simActive = Boolean(sim?.triggered);

  return (
    <div className="flex flex-col gap-3">
      {/* ── 触发状态卡片 ─────────────────────────────── */}
      <div
        className="rounded border p-2.5"
        style={{
          borderColor: simActive ? 'rgba(239,68,68,0.35)' : 'rgba(255,255,255,0.10)',
          background: simActive ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.03)',
        }}
        aria-label="推演触发状态"
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
            推演触发状态
          </span>
          <span
            className="rounded px-1.5 py-0.5 text-[9px] font-medium"
            style={{
              color: simActive ? '#f87171' : 'rgba(255,255,255,0.45)',
              background: simActive ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.06)',
            }}
          >
            {simActive ? '待触发' : '未触发'}
          </span>
        </div>
        {simActive ? (
          <div className="mt-1.5 space-y-0.5 text-[10px]" style={{ color: withAlpha(PALETTE.text, 0.7) }}>
            <div>级别：L{sim?.level ?? 2}｜事件：{sim?.event || sim?.reason || '—'}</div>
            <div className="text-white/35">触发：{sim?.triggered_at || '—'}</div>
          </div>
        ) : (
          <div className="mt-1.5 text-[10px] text-white/35">
            当前无待处理推演。GRV ≥ 68 时天枢自动写入触发文件，天璇 daemon 读取后执行仿真。
          </div>
        )}
      </div>

      {/* ── 最近推演记录 ─────────────────────────────── */}
      <div className="rounded border border-white/10 bg-white/[0.02]">
        <div className="flex items-center justify-between border-b border-white/10 px-2.5 py-1.5">
          <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
            最近推演记录
          </span>
          <span className="text-[9px] text-white/30">
            {indexLoading ? '加载中…' : `${simReports.length} 份`}
          </span>
        </div>
        {simReports.length === 0 ? (
          <div className="px-2.5 py-4 text-center text-[10px] text-white/30">暂无演化仿真报告</div>
        ) : (
          <ul className="max-h-[220px] divide-y divide-white/5 overflow-y-auto">
            {simReports.map((r) => {
              const meta = parseSimMeta(r.filename);
              const isToday = r.updated === today;
              const active = selected?.id === r.id;
              return (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(r)}
                    className="w-full px-2.5 py-1.5 text-left transition-colors hover:bg-white/[0.04]"
                    style={{
                      background: active ? 'rgba(255,255,255,0.06)' : undefined,
                      borderLeft: active ? `2px solid ${PALETTE.teal}` : '2px solid transparent',
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className="truncate text-[10px] leading-snug"
                        style={{ color: active ? withAlpha(PALETTE.text, 0.95) : withAlpha(PALETTE.text, 0.7) }}
                      >
                        {r.title}
                      </span>
                      {meta && (
                        <span className="shrink-0 rounded bg-white/5 px-1 py-0.5 text-[8px] text-white/45">
                          L{meta.level} · {meta.score}
                        </span>
                      )}
                    </div>
                    <div
                      className="mt-0.5 text-[9px]"
                      style={{ color: isToday ? withAlpha(PALETTE.teal, 0.85) : 'rgba(255,255,255,0.30)' }}
                    >
                      {isToday ? '今天' : r.updated}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* ── 报告全文（只读） ──────────────────────────── */}
      {selected && (
        <div className="rounded border border-white/10 bg-white/[0.02]">
          <div className="flex items-center justify-between border-b border-white/10 px-2.5 py-1.5">
            <span className="truncate text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
              {selected.title}
            </span>
            <span className="shrink-0 text-[9px] text-white/30">{selected.updated}</span>
          </div>
          <div className="max-h-[320px] overflow-y-auto px-3 py-2">
            {mdLoading ? (
              <div className="py-6 text-center text-[10px] text-white/30">加载中…</div>
            ) : mdError ? (
              <div className="py-6 text-center text-[10px]" style={{ color: '#f87171' }}>
                读取失败：{mdError}
              </div>
            ) : (
              <>
                {/* v1.11.30 政权更迭事件卡片（解析成功才渲染；失败降级纯文本） */}
                {gov && <GovernanceCard items={gov.items} />}
                <div
                  className="sim-report-md text-[11px] leading-relaxed"
                  style={{ color: withAlpha(PALETTE.text, 0.85) }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(gov ? gov.rest : md) }}
                />
              </>
            )}
          </div>
        </div>
      )}

      {/* ── 底部说明 ──────────────────────────────────── */}
      <p className="text-[9px] leading-relaxed text-white/25">
        只读视图：手动触发 / 政权情景调参属控制面二期，建设中。报告全文与报告中心同源。
      </p>
    </div>
  );
}
