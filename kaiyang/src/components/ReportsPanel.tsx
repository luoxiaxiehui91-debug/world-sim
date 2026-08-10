import { useEffect, useMemo, useRef, useState } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { fetchText } from '@/lib/readLayer';
import { renderMarkdown } from '@/lib/markdown';
import { fmtRelative } from '@/lib/format';
import { PALETTE, withAlpha } from '@/config/theme';
import type { ReportMeta, ReportsIndexRaw } from '@/types/contracts';

/** 分组展示顺序（天枢产出的全部类型；未列出的类型追加在末尾）。 */
const TYPE_ORDER = ['宏观分析', '月度简报', '假设推演', '演化仿真', '预测追踪'];

/** 类型 → 主题色（走主题令牌，不硬编码新色）。 */
function typeColor(type: string): string {
  const MAP: Record<string, string> = {
    宏观分析: PALETTE.cyan,
    月度简报: PALETTE.teal,
    假设推演: PALETTE.amber,
    演化仿真: PALETTE.red,
    预测追踪: PALETTE.slate,
  };
  return MAP[type] ?? PALETTE.textDim;
}

/** 按类型分组（保留 TYPE_ORDER 顺序），组内最新置顶。 */
function groupReports(reports: ReportMeta[] | undefined): Array<{ type: string; items: ReportMeta[] }> {
  if (!reports) return [];
  const byType = new Map<string, ReportMeta[]>();
  for (const r of reports) {
    const list = byType.get(r.type) ?? [];
    list.push(r);
    byType.set(r.type, list);
  }
  const known = TYPE_ORDER.filter((t) => byType.has(t));
  const extra = [...byType.keys()].filter((t) => !TYPE_ORDER.includes(t));
  return [...known, ...extra].map((type) => ({
    type,
    items: (byType.get(type) ?? []).slice().sort((a, b) => (b.updated ?? '').localeCompare(a.updated ?? '')),
  }));
}

/** 面板折叠/展开图标（SVG，非 emoji）。 */
function SidebarToggleIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1={collapsed ? 15 : 9} y1="4" x2={collapsed ? 15 : 9} y2="20" />
      {collapsed && <polyline points="9,10 5,12 9,14" />}
      {!collapsed && <polyline points="15,10 19,12 15,14" />}
    </svg>
  );
}

/**
 * R-1 报告面板：按类型分组的报告列表 + markdown 内容阅读。
 * 数据源 = 天枢 reports_index.json（nginx 只读挂载 /data/）+ data/reports/*.md。
 * 左侧分类：宽度可拖拽调节（14%~55%），可折叠成窄条（色点快速切换分组）。
 */
export function ReportsPanel() {
  const { data, loading, error } = useFeed<ReportsIndexRaw>('reports_index');
  const groups = useMemo(() => groupReports(data?.reports), [data]);
  const total = useMemo(() => data?.reports?.length ?? 0, [data]);

  const [selected, setSelected] = useState<ReportMeta | null>(null);
  const [md, setMd] = useState<string>('');
  const [mdLoading, setMdLoading] = useState(false);
  const [mdError, setMdError] = useState<string | null>(null);

  // 侧栏：默认 40% 宽；可拖拽（14%~55%）；可折叠成 36px 窄条
  const [sidebarPct, setSidebarPct] = useState(40);
  const [collapsed, setCollapsed] = useState(false);
  const dragRef = useRef<{ startX: number; startPct: number } | null>(null);

  function onDragStart(e: React.MouseEvent) {
    e.preventDefault();
    const container = e.currentTarget.parentElement;
    if (!container) return;
    dragRef.current = { startX: e.clientX, startPct: sidebarPct };
    const containerW = container.clientWidth || 600;
    const onMove = (ev: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const pct = Math.min(55, Math.max(14, d.startPct + ((ev.clientX - d.startX) / containerW) * 100));
      setSidebarPct(pct);
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  // 首次加载到数据时默认选中第一份（组序 + 组内排序的第一条）
  useEffect(() => {
    if (!selected && groups.length > 0 && groups[0].items.length > 0) {
      setSelected(groups[0].items[0]);
    }
  }, [groups, selected]);

  // 选中变化 → 拉取 markdown 内容
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

  return (
    <div className="glass-panel scanlines flex h-full min-h-[240px] flex-col">
      <div className="panel-title flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          报告中心
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? '展开分类列表' : '折叠分类列表'}
            className="rounded border border-white/10 p-0.5 text-white/40 transition-colors hover:border-white/30 hover:text-white/80"
          >
            <SidebarToggleIcon collapsed={collapsed} />
          </button>
        </span>
        <span className="text-[10px] font-normal text-white/30">
          {loading ? '加载中…' : `${total} 份 · 更新 ${fmtRelative(data?.updated)}`}
        </span>
      </div>

      {error && <div className="text-[11px] text-amber-300">报告索引读取失败</div>}
      {!error && loading && <div className="text-[11px] text-white/40">加载中…</div>}
      {!error && !loading && groups.length === 0 && (
        <div className="text-[11px] text-white/40">暂无报告</div>
      )}

      {!error && !loading && groups.length > 0 && (
        <div className="flex min-h-0 flex-1 gap-1.5">
          {/* ── 左侧：分组列表（可折叠 / 可拖拽调宽） ── */}
          {collapsed ? (
            <div className="flex w-9 shrink-0 flex-col items-center gap-1.5 overflow-y-auto py-1">
              {groups.map((g) => {
                const c = typeColor(g.type);
                const activeGroup = g.items.some((r) => selected?.id === r.id);
                return (
                  <button
                    key={g.type}
                    type="button"
                    title={`${g.type}（${g.items.length} 份）`}
                    onClick={() => setSelected(g.items[0])}
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition-colors"
                    style={{
                      borderColor: activeGroup ? withAlpha(c, 0.6) : 'rgba(255,255,255,0.10)',
                      background: activeGroup ? withAlpha(c, 0.15) : 'rgba(255,255,255,0.03)',
                    }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: c, boxShadow: `0 0 5px ${withAlpha(c, 0.6)}` }} />
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="shrink-0 overflow-y-auto pr-0.5" style={{ width: `${sidebarPct}%` }}>
              {groups.map((g) => {
                const c = typeColor(g.type);
                return (
                  <div key={g.type} className="mb-1.5">
                    <div
                      className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold tracking-widest"
                      style={{ color: withAlpha(c, 0.9) }}
                    >
                      <span
                        className="inline-block h-1.5 w-1.5 rounded-full"
                        style={{ background: c, boxShadow: `0 0 6px ${withAlpha(c, 0.6)}` }}
                      />
                      {g.type}
                      <span className="text-white/25">{g.items.length}</span>
                    </div>
                    <div className="space-y-0.5">
                      {g.items.map((r) => {
                        const active = selected?.id === r.id;
                        return (
                          <button
                            key={r.id}
                            type="button"
                            onClick={() => setSelected(r)}
                            className="block w-full rounded-md border px-2 py-1 text-left transition-colors"
                            style={{
                              borderColor: active ? withAlpha(c, 0.5) : 'rgba(255,255,255,0.06)',
                              background: active ? withAlpha(c, 0.10) : 'rgba(255,255,255,0.02)',
                            }}
                          >
                            <div className="truncate text-[11px] leading-snug" style={{ color: active ? withAlpha(PALETTE.text, 0.95) : withAlpha(PALETTE.text, 0.72) }}>
                              {r.title}
                            </div>
                            <div className="text-[9px] text-white/30">{r.updated}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ── 拖拽分隔条（仅展开态） ── */}
          {!collapsed && (
            <div
              onMouseDown={onDragStart}
              className="w-1 shrink-0 cursor-col-resize self-stretch rounded-full bg-white/5 transition-colors hover:bg-white/20"
              title="拖拽调整分类栏宽度"
            />
          )}

          {/* ── 右侧：markdown 内容 ── */}
          <div className="min-w-0 flex-1 overflow-y-auto rounded-lg border border-white/8 bg-black/25 px-3 py-2">
            {!selected && <div className="text-[11px] text-white/35">从左侧选择一份报告</div>}
            {mdLoading && <div className="text-[11px] text-white/35">加载报告…</div>}
            {mdError && <div className="text-[11px] text-amber-300">内容读取失败：{mdError}</div>}
            {!mdLoading && !mdError && selected && (
              <article
                className="md-body"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(md) }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
