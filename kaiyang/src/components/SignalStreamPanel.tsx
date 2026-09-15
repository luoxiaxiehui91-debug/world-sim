import { useCallback, useMemo, useState } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { useSelection } from '@/state/SelectionContext';
import { categoryColor, categoryLabel } from '@/config/layerCategories';
import { PALETTE, withAlpha } from '@/config/theme';
import { fmtNum, truncate } from '@/lib/format';
import type { NewsItem } from '@/types/contracts';

/** 信号严重度（由 level / alert_type 文案推断，字段缺失即降级为普通信号）。 */
export type SignalLevel = 'alert' | 'watch' | 'info';

export interface Signal {
  key: string;
  title: string;
  source: string;
  date: string;
  level: SignalLevel;
  metric: string;
  /**
   * 对应的地图点位 id（`RiskPoint.id`）。
   * ⚠ 当前 news feed **没有坐标也没有点位 id**，故这里恒为 null —— 见 `pointIdOf` 注释。
   */
  focusId: string | null;
  /** 点击行内展开的详情字段（完整标题 / 原文链接 / 摘要等）。无则展开区为空。 */
  fullTitle: string;
  url: string | null;
  detail: string | null;
  riskNote: string | null;
  triggerTitles: string[] | null;
}

/** 信号流最多渲染多少条（顶栏 KPI 的「信号」口径与此一致）。 */
export const SIGNAL_DISPLAY_LIMIT = 40;

/**
 * 严重度色（双轴之「强度」轴）：只用于右侧脉冲点与等级文字。
 * ⚠ 不要拿它当左侧色条——左侧色条是「类别」轴，见 STREAM_CATEGORY_COLOR。
 */
const LEVEL_COLOR: Record<SignalLevel, string> = {
  alert: PALETTE.red,
  watch: PALETTE.amber,
  info: PALETTE.cyan,
};

/**
 * 本流的图层类别色（双轴之「色相」轴）。
 * 信号流全部来自 news feed，故恒为 'news' 类别色，与地图上未来的地理新闻点位同色，
 * 让用户在「地图 ↔ 信号流」之间能靠同一个色相把同一层数据串起来。
 */
const STREAM_CATEGORY_COLOR = categoryColor('news');
const STREAM_CATEGORY_LABEL = categoryLabel('news');

const LEVEL_TEXT: Record<SignalLevel, string> = {
  alert: '警报',
  watch: '注意',
  info: '观察',
};

/** 排序权重：警报 → 注意 → 观察（顶栏 KPI 依赖「警报恒排在最前」这一性质）。 */
const LEVEL_WEIGHT: Record<SignalLevel, number> = { alert: 0, watch: 1, info: 2 };

/** news feed 的两种合法载荷：裸数组，或 `{ items: [...] }` 包装（含 schema_version）。 */
export type NewsFeedPayload = NewsItem[] | { articles?: NewsItem[] | null; items?: NewsItem[] | null } | null | undefined;

/**
 * 归一化 news 载荷；任何非法形状一律降级为空数组（K5：不抛错、不白屏）。
 * 数组内的 null / 非对象元素也会被剔除，下游可安全直接读字段。
 */
export function newsItemsOf(raw: NewsFeedPayload): NewsItem[] {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.articles)
      ? raw.articles
      : Array.isArray(raw?.items)
        ? raw.items
        : [];
  return list
    .filter((it): it is NewsItem => !!it && typeof it === 'object')
    // 按日期倒序（最新前置）：news_export 原序为插入顺序，旧新闻会占据首屏（如 7-31 新闻显示在 8-05 前面）
    .sort((a, b) => String(b.date ?? '').localeCompare(String(a.date ?? '')));
}

export function signalLevelOf(item: NewsItem): SignalLevel {
  const raw = `${item.level ?? ''}${item.category ?? ''}${item.alert_type ?? ''}`;
  if (raw.includes('警报') || raw.includes('ALERT') || raw.includes('CRITICAL')) return 'alert';
  if (raw.includes('注意') || raw.includes('WARNING')) return 'watch';
  return 'info';
}

/**
 * 取信号对应的地图点位 id。
 *
 * ⚠ **诚实边界**：`news_export.json` 当前既无 lat/lng，也无点位 id，所以这里**恒返回 null**，
 * 点击信号只会做行内选中，**不会**在地图上乱跳到某个不相干的点（不伪造跳转）。
 * 这里预留了 `point_id` 的读取：等天枢 GDELT `news_geo` feed 就绪、条目带上该字段后，
 * 无需改动本组件与 `SelectionContext`，地图聚焦（相机 + 光环）即自动生效。
 */
function pointIdOf(item: NewsItem): string | null {
  const id = (item as NewsItem & { point_id?: unknown }).point_id;
  return typeof id === 'string' && id.length > 0 ? id : null;
}

/** 把新闻条目压缩成一行「信号」。 */
export function toSignal(item: NewsItem, index: number): Signal {
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
    level: signalLevelOf(item),
    metric: parts.join(' · '),
    focusId: pointIdOf(item),
    fullTitle: String(item.title ?? item.indicator ?? '（无标题）'),
    url: typeof item.url === 'string' && item.url ? item.url : null,
    detail: typeof item.details === 'string' && item.details ? item.details : null,
    riskNote: typeof item.risk_note === 'string' && item.risk_note ? item.risk_note : null,
    triggerTitles: Array.isArray(item.trigger_titles) && item.trigger_titles.length > 0 ? item.trigger_titles : null,
  };
}

/** 派生要渲染的信号列表：按严重度排序后截断到 `SIGNAL_DISPLAY_LIMIT`。 */
export function deriveSignals(items: NewsItem[]): Signal[] {
  const mapped = items.map(toSignal);
  return [...mapped]
    .sort((a, b) => LEVEL_WEIGHT[a.level] - LEVEL_WEIGHT[b.level])
    .slice(0, SIGNAL_DISPLAY_LIMIT);
}

export interface SignalRowProps {
  signal: Signal;
  /** 0 基下标，渲染成 `#1` 起的序号前缀 */
  index: number;
  selected: boolean;
  onSelect: (signal: Signal) => void;
  /** 是否展开行内详情（受控，由父组件维护展开 key，本组件保持纯函数） */
  expanded?: boolean;
}

/**
 * 单条信号行（**纯函数组件，无 hook**）。
 * 抽出来是为了能在 node 环境下直接渲染断言（本项目零新依赖，无 jsdom）。
 */
export function SignalRow({ signal: s, index, selected, onSelect, expanded }: SignalRowProps) {
  // 强度轴：脉冲点 / 等级文字
  const levelTone = LEVEL_COLOR[s.level];
  const hint = s.focusId
    ? '点击聚焦地图点位'
    : expanded
      ? '点击收起详情'
      : '点击展开详情（该信号无地理坐标，暂不联动地图）';
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={() => onSelect(s)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(s);
        }
      }}
      className={`signal-row flex w-full cursor-pointer items-start gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors ${
        selected
          ? 'border-accent/60 bg-accent/10'
          : 'border-white/5 bg-black/20 hover:border-white/15'
      }`}
      // 色相轴：左侧竖条恒为类别色，不随严重度 / 选中态变化
      style={{ borderLeft: `2px solid ${withAlpha(STREAM_CATEGORY_COLOR, 0.7)}` }}
      title={`#${index + 1} · ${STREAM_CATEGORY_LABEL} · ${LEVEL_TEXT[s.level]} · ${s.title} · ${s.source} · ${s.date}\n${hint}`}
    >
      <span className="mt-0.5 w-6 shrink-0 text-right text-[10px] tabular-nums text-white/30">
        #{index + 1}
      </span>
      <i
        className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
          s.level === 'alert' ? 'animate-pulseSoft' : ''
        }`}
        style={{ background: levelTone, boxShadow: `0 0 8px ${withAlpha(levelTone, 0.75)}` }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] text-white/80">{s.title}</div>
        <div className="truncate text-[10px] text-white/35">
          {s.date} · {s.source}
          {s.metric ? ` · ${s.metric}` : ''}
        </div>
        {expanded && (
          <div className="mt-1.5 space-y-1 border-t border-white/5 pt-1.5 text-[11px] leading-relaxed text-white/55">
            <div className="text-white/75">{s.fullTitle}</div>
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block truncate text-accent/90 transition-colors hover:text-accent"
                onClick={(e) => e.stopPropagation()}
              >
                原文链接 ↗
              </a>
            )}
            {s.detail && <div>{s.detail}</div>}
            {s.riskNote && <div className="text-amber-200/80">⚠ {s.riskNote}</div>}
            {s.triggerTitles?.map((t, i) => (
              <div key={i} className="border-l-2 border-accent/30 pl-2">
                {t}
              </div>
            ))}
          </div>
        )}
      </div>
      <span className="shrink-0 text-[10px]" style={{ color: levelTone }}>
        {LEVEL_TEXT[s.level]}
      </span>
    </div>
  );
}

/**
 * 右侧「最新信号流」：把 news_export 压成高密度单行信号列表，仿指挥中心滚动流。
 * 字段缺失自动降级，不报错。
 *
 * 视觉双轴（决策 D1）在此**显式分离**：
 * - **左侧竖色条 = 图层类别**（恒为 news 类别色），回答「这条属于哪一层」；
 * - **右侧脉冲圆点 + 等级文字 = 严重度**（警报/注意/观察），回答「有多严重」。
 * 升级前两者共用同一套严重度色，导致类别信息完全丢失、且与地图色相语义冲突。
 *
 * R-P1-03：每行加 `#序号` 前缀，行可点击写入全局选中态（`SelectionContext`）。
 * 联动地图的真实边界见 `pointIdOf` 注释 —— 现阶段只有行内选中，不伪造地图跳转。
 */
export function SignalStreamPanel() {
  const { data, loading, error } = useFeed<NewsItem[]>('news');
  const { selectedSignalKey, selectSignal } = useSelection();
  const items = useMemo<NewsItem[]>(() => newsItemsOf(data), [data]);
  const signals = useMemo<Signal[]>(() => deriveSignals(items), [items]);

  const alertCount = signals.filter((s) => s.level === 'alert').length;

  // 行内详情展开 key（受控；与选中态独立——点击行=选中+展开，再次点击=取消+收起）
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const handleSelect = useCallback(
    (s: Signal) => {
      // 再次点击已选中行 = 取消选中（同时清掉可能存在的地图聚焦）+ 收起详情
      if (s.key === selectedSignalKey) {
        selectSignal(null, null);
        setExpandedKey(null);
        return;
      }
      selectSignal(s.key, s.focusId);
      setExpandedKey((prev) => (prev === s.key ? null : s.key));
    },
    [selectedSignalKey, selectSignal],
  );

  return (
    <div className="glass-panel scanlines flex h-full min-h-[240px] flex-col">
      <div className="panel-title">
        📡 最新信号流
        <span className="ml-auto text-[10px] font-normal text-white/35">
          共 {signals.length} 条 · 警报 {alertCount}
        </span>
      </div>

      <div
        className="mb-1 flex items-center gap-1.5 text-[10px] text-white/30"
        title="左侧色条表示图层类别（与地图同色相），右侧圆点与文字表示严重度；行首 # 为当前排序下的序号"
      >
        <i
          className="inline-block h-2.5 w-0.5 shrink-0 rounded-sm"
          style={{ background: STREAM_CATEGORY_COLOR }}
        />
        <span>{STREAM_CATEGORY_LABEL}</span>
        <span className="text-white/15">·</span>
        <span>色条=类别 / 圆点=严重度</span>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto pr-0.5">
        {loading && <div className="text-[11px] text-white/40">加载中…</div>}
        {error && <div className="text-[11px] text-amber-300">读取失败：{error.message}</div>}
        {!loading && !error && signals.length === 0 && (
          <div className="text-[11px] text-white/40">暂无信号</div>
        )}
        {signals.map((s, i) => (
          <SignalRow
            key={s.key}
            signal={s}
            index={i}
            selected={s.key === selectedSignalKey}
            onSelect={handleSelect}
            expanded={s.key === expandedKey}
          />
        ))}
      </div>
    </div>
  );
}
