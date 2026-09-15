import { useEffect, useMemo, useState } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import type { NewsItem } from '@/types/contracts';
import { newsItemsOf } from './SignalStreamPanel';

function NewsCard({ item }: { item: NewsItem }) {
  const [open, setOpen] = useState(false);
  const levelColor =
    item.level && item.level.includes('警报')
      ? 'border-rose-400/50 text-rose-300'
      : item.level && item.level.includes('注意')
        ? 'border-amber-400/50 text-amber-300'
        : 'border-white/15 text-white/60';
  const title = item.title ?? item.indicator ?? '（无标题）';
  const hasDetail =
    !!item.details ||
    !!item.risk_note ||
    (item.trigger_titles?.length ?? 0) > 0 ||
    item.current !== undefined;

  return (
    <div className="panel-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {/* 标题：有 url 时可点击跳转，否则纯文本 */}
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block truncate text-sm text-white/85 hover:text-accent transition-colors"
              title={title}
            >
              {title} ↗
            </a>
          ) : (
            <div className="truncate text-sm text-white/85" title={title}>{title}</div>
          )}
          <div className="mt-0.5 text-[11px] text-white/40">
            {item.date ?? '—'} · {item.source ?? '未知来源'}
            {item.indicator ? ` · ${item.indicator}` : ''}
          </div>
        </div>
        <span className={`chip shrink-0 ${levelColor}`}>{item.level ?? '—'}</span>
      </div>
      {hasDetail && (
        <button
          className="mt-1 text-[11px] text-accent/80 hover:text-accent"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '收起 ▲' : '展开详情 ▼'}
        </button>
      )}
      {open && (
        <div className="mt-2 space-y-1 text-[11px] leading-relaxed text-white/55">
          {item.details && <div>{item.details}</div>}
          {item.risk_note && <div className="text-amber-200/80">⚠ {item.risk_note}</div>}
          {item.trigger_titles?.map((t, i) => (
            <div key={i} className="border-l-2 border-accent/30 pl-2">
              {t}
            </div>
          ))}
          {item.current !== undefined && (
            <div>
              当前值 {item.current}
              {item.baseline !== undefined ? ` · 基线 ${item.baseline}` : ''}
              {item.ratio !== undefined ? ` · 倍数 ${item.ratio}` : ''}
              {item.z_score !== undefined ? ` · Z ${item.z_score}` : ''}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function NewsPanel() {
  const { data, loading, error } = useFeed<NewsItem[]>('newsAll');
  const { setTimestamp } = useStatus();
  // 兼容数组或 { items: [...] } 包装（含 schema_version）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  // newsItemsOf：兼容裸数组 / {articles} / {items}，按 date 倒序（最新前置）
  const items = useMemo<NewsItem[]>(() => newsItemsOf(data as never), [data]);

  // P0 修复（news-fake-timestamp）：时间戳优先取顶层 updated/exported_at（含完整时间，
  // 由 news_exporter 写入）；纯日期 items[0].date 仅作兜底（parseTs 已兼容纯日期防 UTC 午夜）
  const newsTs = useMemo<string | null>(() => {
    const raw = data as { updated?: string; exported_at?: string } | null;
    return raw?.updated ?? raw?.exported_at ?? items[0]?.date ?? null;
  }, [data, items]);

  useEffect(() => {
    if (newsTs) setTimestamp('news', newsTs);
  }, [newsTs, setTimestamp]);

  return (
    <div className="glass-panel scanlines flex h-full min-h-[340px] flex-col">
      <div className="panel-title">📰 新闻 / 叙事面板</div>
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {loading && <div className="text-xs text-white/40">加载中…</div>}
        {error && <div className="text-xs text-amber-300">读取失败：{error.message}</div>}
        {!loading && !error && items.length === 0 && (
          <div className="text-xs text-white/40">暂无新闻条目</div>
        )}
        {items.map((it, i) => (
          <NewsCard key={i} item={it} />
        ))}
      </div>
    </div>
  );
}
