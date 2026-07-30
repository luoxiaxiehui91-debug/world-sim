import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { PALETTE, withAlpha } from '@/config/theme';
import { fmtNum, truncate } from '@/lib/format';
import type { NewsItem } from '@/types/contracts';

/** 信号严重度（由 level / alert_type 文案推断，字段缺失即降级为普通信号）。 */
type SignalLevel = 'alert' | 'watch' | 'info';

interface Signal {
  key: string;
  title: string;
  source: string;
  date: string;
  level: SignalLevel;
  metric: string;
}

const LEVEL_COLOR: Record<SignalLevel, string> = {
  alert: PALETTE.red,
  watch: PALETTE.amber,
  info: PALETTE.cyan,
};

const LEVEL_TEXT: Record<SignalLevel, string> = {
  alert: '警报',
  watch: '注意',
  info: '观察',
};

function levelOf(item: NewsItem): SignalLevel {
  const raw = `${item.level ?? ''}${item.category ?? ''}${item.alert_type ?? ''}`;
  if (raw.includes('警报') || raw.includes('ALERT') || raw.includes('CRITICAL')) return 'alert';
  if (raw.includes('注意') || raw.includes('WARNING')) return 'watch';
  return 'info';
}

/** 把新闻条目压缩成一行「信号」。 */
function toSignal(item: NewsItem, index: number): Signal {
  const parts: string[] = [];
  if (typeof item.current === 'number') parts.push(`当前 ${fmtNum(item.current, 2)}`);
  if (typeof item.z_score === 'number') parts.push(`Z ${fmtNum(item.z_score, 2)}`);
  if (typeof item.ratio === 'number') parts.push(`倍数 ${fmtNum(item.ratio, 1)}`);
  if (item.direction) parts.push(String(item.direction));
  return {
    key: `${item.series_id ?? item.indicator ?? 'sig'}-${index}`,
    title: truncate(String(item.title ?? item.indicator ?? '（无标题）'), 42),
    source: String(item.source ?? '未知来源'),
    date: String(item.date ?? '—'),
    level: levelOf(item),
    metric: parts.join(' · '),
  };
}

/**
 * 右侧「最新信号流」：把 news_export 压成高密度单行信号列表，
 * 按严重度着色 + 脉冲点，仿指挥中心滚动流。字段缺失自动降级，不报错。
 */
export function SignalStreamPanel() {
  const { data, loading, error } = useFeed<NewsItem[]>('news');
  // 兼容数组或 { items: [...] } 包装（含 schema_version）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = data as any;
  const items = useMemo<NewsItem[]>(() => (Array.isArray(raw) ? raw : (raw?.items ?? [])), [raw]);

  const signals = useMemo<Signal[]>(() => {
    const mapped = items.map(toSignal);
    const weight: Record<SignalLevel, number> = { alert: 0, watch: 1, info: 2 };
    return [...mapped].sort((a, b) => weight[a.level] - weight[b.level]).slice(0, 40);
  }, [items]);

  const alertCount = signals.filter((s) => s.level === 'alert').length;

  return (
    <div className="glass-panel scanlines flex h-full min-h-[240px] flex-col">
      <div className="panel-title">
        📡 最新信号流
        <span className="ml-auto text-[10px] font-normal text-white/35">
          共 {signals.length} 条 · 警报 {alertCount}
        </span>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto pr-0.5">
        {loading && <div className="text-[11px] text-white/40">加载中…</div>}
        {error && <div className="text-[11px] text-amber-300">读取失败：{error.message}</div>}
        {!loading && !error && signals.length === 0 && (
          <div className="text-[11px] text-white/40">暂无信号</div>
        )}
        {signals.map((s) => {
          const color = LEVEL_COLOR[s.level];
          return (
            <div
              key={s.key}
              className="signal-row flex items-start gap-2 rounded-lg border border-white/5 bg-black/20 px-2 py-1.5"
              style={{ borderLeft: `2px solid ${withAlpha(color, 0.7)}` }}
              title={`${s.title} · ${s.source} · ${s.date}`}
            >
              <i
                className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                  s.level === 'alert' ? 'animate-pulseSoft' : ''
                }`}
                style={{ background: color, boxShadow: `0 0 8px ${withAlpha(color, 0.75)}` }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] text-white/80">{s.title}</div>
                <div className="truncate text-[10px] text-white/35">
                  {s.date} · {s.source}
                  {s.metric ? ` · ${s.metric}` : ''}
                </div>
              </div>
              <span className="shrink-0 text-[10px]" style={{ color }}>
                {LEVEL_TEXT[s.level]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
