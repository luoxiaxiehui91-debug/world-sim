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
import type { EChartsOption } from 'echarts';
import { useFeed } from '@/hooks/useFeed';
import { fetchText } from '@/lib/readLayer';
import { renderMarkdown } from '@/lib/markdown';
import { extractGovernanceEvents } from '@/lib/governance';
import { GovernanceCard } from '@/components/GovernanceCard';
import { EChart } from '@/components/EChart';
import { PALETTE, withAlpha } from '@/config/theme';
import type { ReportsIndexRaw, ReportMeta, SimTriggerRaw, TianxuanGrvRaw } from '@/types/contracts';

/**
 * 路径线配色（M9）：从类别色板取 3 个高对比、非红/非琥珀色——
 * 红/琥珀是 severity 语义色，用于路径会被误读成「危险路径」。
 * 青 cyan / 靛紫 space / 翡翠 air，三者色相分离。
 */
const PATH_COLORS = ['#22d3ee', '#818cf8', '#34d399'] as const;

/** ISO 时刻 → 简短本地显示（YYYY-MM-DD HH:mm）；缺失返回占位。 */
function fmtStamp(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * 天璇 GRV 24 月多路径推演轨迹图（F1）。
 *
 * 认识论（蓝图 v6「两内核不混用」）：本图 =【天璇·数学基线】数学蒙特卡洛推演，
 * 非天枢此刻观测、非官方预报、未经天玑校验此具体轨迹。三层来源图例非交互并列，
 * 标签对称（不单给某层贬/褒），当前层高亮、另两层灰显。
 *
 * · M1  固定高度容器（TianxuanTab 外层 flex 无 bounded-height 链，h-full 会塌成 0）
 * · M2  每路径均值线 + ±std 不确定带（只画均值线会被读成精确预报）
 * · M9  路径配色非红/琥珀
 * · M10 线宽/透明度按 probability（主导路径更粗更实）
 * · M11 baseline_grv 作 month-0「现在」锚点，各路径自此分散
 */
function TianxuanTrajChart() {
  const { data } = useFeed<TianxuanGrvRaw | null>('tianxuanGrv');
  const paths = useMemo(() => data?.paths ?? [], [data]);
  const months = useMemo(() => data?.months ?? [], [data]);
  const hasData = paths.length > 0 && months.length > 0;
  const baseline = typeof data?.baseline_grv === 'number' ? data.baseline_grv : null;

  const option = useMemo<EChartsOption>(() => {
    const cats = ['现在', ...months];
    const series: NonNullable<EChartsOption['series']> = [];
    const legendData: string[] = [];

    paths.forEach((p, i) => {
      const color = PATH_COLORS[i % PATH_COLORS.length];
      const prob = typeof p.probability === 'number' ? p.probability : 0;
      const width = 1.5 + prob * 2.5; // 主导路径更粗
      const opacity = 0.5 + prob * 0.5; // 尾部路径更淡
      const name = `${p.label} · ${(prob * 100).toFixed(0)}%`;
      legendData.push(name);

      const mean = p.monthly_grv ?? [];
      const std = p.monthly_grv_std ?? [];
      // 均值线含 month-0 锚点（自共享观测出发）
      const meanWithAnchor = [baseline, ...mean];
      // 不确定带：lower(隐形) 打底 + 2*std 堆叠出 areaStyle（锚点处 std=0，带收窄成点）
      const lower = [baseline, ...mean.map((v, k) => (v == null ? null : v - (std[k] ?? 0)))];
      const band = [0, ...mean.map((v, k) => (v == null ? null : 2 * (std[k] ?? 0)))];

      series.push({
        name: `__lo_${i}`,
        type: 'line',
        data: lower,
        stack: `band${i}`,
        lineStyle: { opacity: 0 },
        symbol: 'none',
        silent: true,
        z: 1,
      });
      series.push({
        name: `__band_${i}`,
        type: 'line',
        data: band,
        stack: `band${i}`,
        lineStyle: { opacity: 0 },
        areaStyle: { color, opacity: 0.1 },
        symbol: 'none',
        silent: true,
        z: 1,
      });
      series.push({
        name,
        type: 'line',
        data: meanWithAnchor,
        smooth: true,
        symbol: 'none',
        lineStyle: { color, width, opacity },
        itemStyle: { color },
        z: 3,
        ...(i === 0
          ? {
              markLine: {
                silent: true,
                symbol: 'none',
                lineStyle: { color: 'rgba(255,255,255,0.18)', type: 'dashed' },
                label: { show: false },
                data: [{ xAxis: '现在' }],
              },
            }
          : {}),
      });
    });

    // month-0 观测锚点（单点，标当前观测值）
    if (baseline != null) {
      series.push({
        name: '当前观测',
        type: 'scatter',
        data: [[0, baseline]],
        symbolSize: 7,
        itemStyle: { color: PALETTE.text, borderColor: PALETTE.space, borderWidth: 1 },
        silent: true,
        z: 4,
      });
    }

    return {
      grid: { left: 6, right: 10, top: 24, bottom: 4, containLabel: true },
      legend: {
        data: legendData,
        top: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: withAlpha(PALETTE.text, 0.7), fontSize: 9 },
      },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: 'rgba(10,14,26,0.92)',
        borderColor: 'rgba(255,255,255,0.12)',
        textStyle: { color: PALETTE.text, fontSize: 10 },
        // 过滤掉隐形带辅助序列
        formatter: (params: unknown) => {
          const arr = (Array.isArray(params) ? params : [params]) as Array<{
            seriesName?: string;
            axisValueLabel?: string;
            marker?: string;
            value?: unknown;
          }>;
          const shown = arr.filter((p) => !String(p.seriesName ?? '').startsWith('__'));
          if (!shown.length) return '';
          const head = shown[0].axisValueLabel ?? '';
          const lines = shown.map((p) => {
            const raw = Array.isArray(p.value) ? p.value[1] : p.value;
            const v = raw == null || raw === '' ? '—' : Number(raw).toFixed(1);
            return `${p.marker ?? ''}${p.seriesName}: ${v}`;
          });
          return [head, ...lines].join('<br/>');
        },
      },
      xAxis: {
        type: 'category',
        data: cats,
        boundaryGap: false,
        axisLabel: { hideOverlap: true, fontSize: 9, interval: 'auto', color: withAlpha(PALETTE.text, 0.5) },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        name: 'GRV',
        nameTextStyle: { color: withAlpha(PALETTE.text, 0.5), fontSize: 9 },
        axisLabel: { fontSize: 9, color: withAlpha(PALETTE.text, 0.5) },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series,
    };
  }, [paths, months, baseline]);

  return (
    <div className="rounded border border-white/10 bg-white/[0.02]">
      <div className="flex items-center justify-between border-b border-white/10 px-2.5 py-1.5">
        <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
          天璇推演 · GRV 24 月轨迹
        </span>
        <span className="shrink-0 text-[9px] text-white/40">
          {hasData ? `生成于 ${fmtStamp(data?.generated_at)}` : ''}
        </span>
      </div>

      {/* 三层来源图例（非交互，标签对称：当前层高亮、另两层灰显） */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2.5 pt-1.5 text-[9px]">
        <span className="inline-flex items-center gap-1" style={{ color: withAlpha(PALETTE.text, 0.85) }}>
          <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: PATH_COLORS[0] }} />
          {data?.kernel_label ?? '天璇·数学基线'}（本图）
        </span>
        <span className="inline-flex items-center gap-1 text-white/30">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-white/25" />
          天枢观测（此刻横截面 → 见主屏 GRV 维度面板）
        </span>
        <span className="inline-flex items-center gap-1 text-white/30">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-white/25" />
          LLM 沙盘（第二内核 · 未接入）
        </span>
      </div>

      {hasData ? (
        <>
          {/* M1：显式固定高度容器（外层无 bounded-height 链，h-full 会塌成 0px） */}
          <div className="px-1.5 pt-1">
            <EChart option={option} className="h-[220px] w-full" />
          </div>
          <div className="space-y-0.5 px-2.5 pb-2 pt-0.5">
            {baseline != null && (
              <p className="text-[9px] text-white/40">
                month-0「现在」= 当前观测 {baseline.toFixed(1)}；各路径自此出发，因扰动逐月分散。阴影带为簇内 ±1σ 不确定区间。
              </p>
            )}
            <p className="text-[9px] text-white/30">
              轨迹每 30 分钟由天枢从最新仿真报告导出；报告列表与本图可能短时不同步。
            </p>
            {data?.disclaimer && (
              <p className="text-[10px]" style={{ color: withAlpha(PALETTE.text, 0.5) }}>
                {data.disclaimer}
              </p>
            )}
          </div>
        </>
      ) : (
        <div className="px-2.5 py-6 text-center text-[10px] text-white/30">
          暂无推演轨迹，等待首次触发。GRV ≥ 68 时天枢自动写入触发文件，天璇 daemon 执行仿真后此处成图。
        </div>
      )}
    </div>
  );
}

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

      {/* ── 天璇推演轨迹图（F1：天璇·数学基线，与观测层首尾相接） ─── */}
      <TianxuanTrajChart />

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
