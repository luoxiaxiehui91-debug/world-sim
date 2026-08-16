import { useMemo } from 'react';
import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import { useControl } from '@/state/ControlContext';
import { adaptGrv } from '@/lib/grvAdapter';
import {
  SIGNAL_DISPLAY_LIMIT,
  newsItemsOf,
  signalLevelOf,
  type NewsFeedPayload,
} from '@/components/SignalStreamPanel';
import { severityColor, withAlpha } from '@/config/theme';
import { fmtNum, fmtStamp, parseTs, fmtRelative } from '@/lib/format';
import type { GrvRaw, NewsItem, SimTriggerRaw } from '@/types/contracts';

function Stamp({ label, t }: { label: string; t: string | null | undefined }) {
  const parsed = parseTs(t);
  const isStale = parsed ? Date.now() - parsed.getTime() > 24 * 3600 * 1000 : false;
  const rel = fmtRelative(t);
  return (
    <span
      className={`chip ${isStale ? 'border-amber-400/60 text-amber-300' : ''}`}
      title={`${label} 数据时间：${t ?? '未知'}${rel !== '—' ? '（' + rel + '）' : ''}${isStale ? ' ⚠ 超过24h未更新' : ''}`}
    >
      <span className={isStale ? 'text-amber-400/70' : 'text-white/40'}>{label}</span>
      <span className={isStale ? 'text-amber-300' : 'text-white/70'}>{fmtStamp(t)}{isStale ? ' ⚠' : ''}</span>
    </span>
  );
}

/** 顶栏 KPI 计数（R-P1-03）。 */
export interface Kpis {
  /** 信号流实际渲染条数 = min(原始条数, 显示上限 40) */
  signals: number;
  /** news feed 有效条数（未截断；已剔除 null / 非对象脏元素） */
  news: number;
  /** 主告警数 = 信号流可见范围内 alert 级条数 */
  mainAlert: number;
}

/**
 * 由 news 载荷派生顶栏三个 KPI（**纯函数**，便于零依赖单测）。
 *
 * 口径与 `SignalStreamPanel` 严格对齐（复用同一套 `newsItemsOf` / `signalLevelOf` / 上限常量，
 * 不另抄一份判定逻辑）：信号流按「警报 → 注意 → 观察」排序后截断，
 * 因此可见范围内的 alert 数恒等于 `min(全量 alert 数, 可见条数)`。
 *
 * 任何非法载荷（null / undefined / 非数组 / 缺字段）一律降级为 0，不抛错（K5）。
 */
export function deriveKpis(items: NewsFeedPayload): Kpis {
  const list = newsItemsOf(items);
  const news = list.length;
  const signals = Math.min(news, SIGNAL_DISPLAY_LIMIT);
  let alerts = 0;
  for (const it of list) {
    if (signalLevelOf(it) === 'alert') alerts += 1;
  }
  return { signals, news, mainAlert: Math.min(alerts, signals) };
}

/** 顶部状态条：综合指数 + 数据时间戳 + schema 版本 + 推演触发 + 缺失字段告警（扩展标准 #3）。 */
export function StatusBar() {
  const { warnings, timestamps, dataVersions } = useStatus();
  const { toggleDrawer, drawerOpen } = useControl();
  const { data: sim } = useFeed<SimTriggerRaw | null>('simTrigger');
  const { data: grv } = useFeed<GrvRaw>('grv');
  // news 与信号流复用同一 feed（useFeed 已按 feed:field 去重告警，重复订阅不会重复计告警）
  const { data: news } = useFeed<NewsItem[]>('news');
  const model = useMemo(() => adaptGrv(grv), [grv]);
  const kpis = useMemo(() => deriveKpis(news), [news]);
  const headline = model.headline;
  const headlineColor = severityColor(headline?.value ?? null);

  const simData = sim ?? null;
  const triggered = simData?.triggered === true;
  const consumed = simData?.consumed === true;
  const warningText = warnings.map((w) => `· ${w.message}`).join('\n');
  // P2 修复（sim-trigger-flag-missing）：与 StatusMiniPanel:27 一致——结构性缺失
  // （market_quotes 无面板/nuclear 静态种子/news_geo 延迟/simTrigger 空文件合法静止）
  // 不进告警计数，消除常驻伪告警
  const KNOWN_STRUCTURAL_MISSING = new Set(['market_quotes', 'nuclear', 'news_geo', 'simTrigger']);
  const actionableWarnings = warnings.filter((w) => !KNOWN_STRUCTURAL_MISSING.has(w.feed));
  const schemaText = Object.entries(dataVersions)
    .map(([k, v]) => `${k}:${v ?? '缺失'}`)
    .join('  ');

  return (
    <header className="glass scanlines mx-4 mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 text-xs relative z-[60]">
      <div className="mr-2 flex items-center gap-2">
        <span className="title-glow font-bold tracking-[0.3em] text-accent">开阳</span>
        <span className="hidden text-white/40 sm:inline">WAVE 2 · 世界推演操作面板</span>
      </div>

      {headline && (
        <span
          className="chip"
          title={headline.note ?? '全球综合指数（无地理位置，不投影到地图）'}
          style={{
            borderColor: withAlpha(headlineColor, 0.5),
            background: withAlpha(headlineColor, 0.1),
          }}
        >
          <span className="text-white/45">{headline.label}</span>
          <b style={{ color: headlineColor }}>{fmtNum(headline.value)}</b>
        </span>
      )}

      {/* R-P1-03 顶栏 KPI 计数：信号 / 新闻 / 主告警（口径见 deriveKpis） */}
      <span className="chip" title={`信号流实际渲染条数（上限 ${SIGNAL_DISPLAY_LIMIT} 条）`}>
        <span className="text-white/40">信号</span>
        <b className="tabular-nums text-white/80">{kpis.signals}</b>
      </span>
      <span className="chip" title="news feed 有效条数（未截断）">
        <span className="text-white/40">新闻</span>
        <b className="tabular-nums text-white/80">{kpis.news}</b>
      </span>
      <span
        className={`chip ${
          kpis.mainAlert > 0
            ? 'border-rose-400/50 bg-rose-500/10 text-rose-300'
            : 'border-amber-400/25 text-amber-200/50'
        }`}
        title="信号流可见范围内「警报」级条数"
      >
        <span className="opacity-60">主告警</span>
        <b className="tabular-nums">{kpis.mainAlert}</b>
      </span>

      <Stamp label="GRV" t={timestamps['grv']} />
      <Stamp label="GDELT" t={timestamps['grv_gdelt']} />
      <Stamp label="新闻" t={timestamps['news']} />
      <Stamp label="GEO" t={timestamps['news_geo']} />
      <span className="chip" title="各 feed 实际 schema 版本">
        <span className="text-white/40">schema</span>
        <span className="text-white/70">{schemaText || '—'}</span>
      </span>
      {triggered ? (
        <span className="chip border-rose-400/50 text-rose-300" title={simData?.reason}>
          ⚠ 推演触发
        </span>
      ) : consumed ? (
        <span
          className="chip border-cyan-400/40 text-cyan-300/80"
          title={`上次触发已消费（${simData?.event ?? ''}，${simData?.consumed_at ?? ''}）`}
        >
          上次触发已消费
        </span>
      ) : (
        <span className="chip border-emerald-400/40 text-emerald-300">推演未触发</span>
      )}
      {actionableWarnings.length > 0 ? (
        <span className="chip border-amber-400/50 text-amber-300" title={warningText}>
          ⚠ 缺失告警 {actionableWarnings.length}
        </span>
      ) : (
        <span className="chip border-emerald-400/40 text-emerald-300">数据完整</span>
      )}

      {/* 控制台 toggle 按钮（最右侧） */}
      <div className="ml-auto">
        <button
          type="button"
          onClick={toggleDrawer}
          className={`chip cursor-pointer transition-colors ${
            drawerOpen
              ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-300'
              : 'border-white/10 bg-white/5 text-white/50 hover:border-cyan-400/30 hover:text-cyan-300'
          }`}
          title={drawerOpen ? '关闭控制台' : '打开控制台'}
        >
          <span className="text-xs">🔧</span>
          <span>控制台</span>
        </button>
      </div>
    </header>
  );
}
