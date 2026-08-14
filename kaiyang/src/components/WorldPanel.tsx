import { useCallback, useEffect, useMemo, useState } from 'react';
import { EventPopup } from '@/components/EventPopup';
import { FlatMapPanel } from '@/components/FlatMapPanel';
import { GlobePanel } from '@/components/GlobePanel';
import { LayerLegend, type LayerCountMap } from '@/components/LayerLegend';
import { LayerTreePanel } from '@/components/LayerTreePanel';
import { RegionTabs } from '@/components/RegionTabs';
import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import { useSelection } from '@/state/SelectionContext';
import { adaptGrv } from '@/lib/grvAdapter';
import { aggregateNewsGeo } from '@/lib/geoAggregate';
import { adaptAirTraffic } from '@/lib/airTrafficAdapter';
import { buildEventBars, buildRiskArcs, buildRiskPoints, type RiskPoint } from '@/lib/mapData';
import { buildNuclearPoints, mergeNuclear } from '@/lib/nuclearData';
import {
  ALL_CATEGORIES,
  DEFAULT_VISIBLE_CATEGORIES,
  LAYER_VISIBILITY_STORAGE_KEY,
  MAX_POINTS_PER_LAYER,
  UNCAPPED_LAYERS,
  parseLayerVisibility,
  serializeLayerVisibility,
  type LayerCategory,
} from '@/config/layerCategories';
import {
  DEFAULT_REGION,
  REGION_STORAGE_KEY,
  inRegion,
  regionDef,
  toRegionKey,
  type RegionKey,
} from '@/config/regions';
import {
  STRATEGIC_SITES,
  STRATEGIC_SITES_DEFAULT_VISIBLE,
  STRATEGIC_SITES_STORAGE_KEY,
  validStrategicSites,
} from '@/data/strategicSites';
import { severityColor, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvRaw, MarketQuotesRaw, NewsGeoRaw, NuclearSitesRaw ,
  AirTrafficRaw} from '@/types/contracts';

/** 视图模式：3D 地球 / 2D 平面地图。 */
export type WorldViewMode = 'globe' | 'flat';

const STORAGE_KEY = 'kaiyang.worldViewMode';

/** 从 localStorage 读取上次选择的视图模式（失败时回退 3D）。 */
function readInitialMode(): WorldViewMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'flat' ? 'flat' : 'globe';
  } catch {
    return 'globe';
  }
}

/**
 * 读取上次的图层显隐（K8）。
 * 键位 `kaiyang.layerVisibility` 已在 `config/layerCategories.ts` 登记；
 * 解析逻辑（含新类别前向兼容、未知键丢弃）同样收敛在那里，本处只负责 IO 与异常兜底。
 */
function readInitialVisibility(): LayerCategory[] {
  try {
    return parseLayerVisibility(window.localStorage.getItem(LAYER_VISIBILITY_STORAGE_KEY));
  } catch {
    return [...DEFAULT_VISIBLE_CATEGORIES];
  }
}

/**
 * 读取战略要地叠加层的显隐偏好（独立键位 `kaiyang.strategicSitesVisible`）。
 * 与分类图层互不干扰；解析失败或首访时回落默认「开」。
 */
function readInitialSitesVisible(): boolean {
  try {
    const raw = window.localStorage.getItem(STRATEGIC_SITES_STORAGE_KEY);
    if (raw === null) return STRATEGIC_SITES_DEFAULT_VISIBLE;
    return raw === 'true';
  } catch {
    return STRATEGIC_SITES_DEFAULT_VISIBLE;
  }
}

/**
 * 读取上次选择的地区（R-P1-02，键位 `kaiyang.region`）。
 * 解析逻辑（未知键回落 world）收敛在 `config/regions.ts`，本处只负责 IO 与异常兜底。
 */
function readInitialRegion(): RegionKey {
  try {
    return toRegionKey(window.localStorage.getItem(REGION_STORAGE_KEY));
  } catch {
    return DEFAULT_REGION;
  }
}

/**
 * 单图层点位数量护栏（设计稿 §10-N5）。
 * 超出 `MAX_POINTS_PER_LAYER` 的部分直接截断并在控制台告警，
 * 避免某个 feed 突然膨胀（如热异常火点）把帧率打死。
 * 08-14：`UNCAPPED_LAYERS`（air 空域活动）豁免——用户拍板全量显示，截断后缺一部分没意义。
 */
function capPointsPerLayer(points: RiskPoint[]): RiskPoint[] {
  const seen = new Map<LayerCategory, number>();
  let truncated = false;
  const out: RiskPoint[] = [];
  for (const p of points) {
    const n = (seen.get(p.category) ?? 0) + 1;
    seen.set(p.category, n);
    if (!UNCAPPED_LAYERS.has(p.category) && n > MAX_POINTS_PER_LAYER) {
      truncated = true;
      continue;
    }
    out.push(p);
  }
  if (truncated) {
    // eslint-disable-next-line no-console
    console.warn(
      `[WorldPanel] 某图层点位超过 ${MAX_POINTS_PER_LAYER} 上限，已截断以保护渲染性能`,
    );
  }
  return out;
}

/**
 * 世界视图主面板：3D 地球 / 2D 平面地图切换容器。
 * - 两种视图共享同一份点位数据与配色（lib/mapData.ts + lib/nuclearData.ts 构建），观感与语义一致。
 * - composite（全球综合 / 全球南方）不投影到地图，改在此处头部与 GRV 面板以数字呈现。
 * - 两个子视图始终挂载、以显隐切换，避免反复创建 / 销毁 WebGL 上下文。
 *
 * 分类图层（1.2.0）：
 * - **层叠合并顺序固定为**（K7）：海量点 → 常规点 → 事件点 → 地理新闻（1.6.0 新增） → 固定设施。
 *   后合并者绘制在上层，保证核设施等「少而重要」的固定标记不被海量点淹没。
 * - 显隐过滤只在本层做一次，子视图拿到的就是「该画什么」的最终列表（渲染器无过滤职责）。
 */
export function WorldPanel() {
  const [mode, setMode] = useState<WorldViewMode>(readInitialMode);
  const [visibleCategories, setVisibleCategories] =
    useState<LayerCategory[]>(readInitialVisibility);
  const [sitesVisible, setSitesVisible] = useState<boolean>(readInitialSitesVisible);
  const [region, setRegion] = useState<RegionKey>(readInitialRegion);

  const { data, loading, error } = useFeed<GrvRaw>('grv');
  const { data: nuclearRaw } = useFeed<NuclearSitesRaw>('nuclearSites');
  // 1.6.0 新增：地理新闻读取层骨架。feed 缺失 / 空 events 适配为 []（K5 不白屏）
  const { data: newsGeoRaw } = useFeed<NewsGeoRaw>('news_geo');
  // 08-14 air 图层：OpenSky 实时航班（feed 缺失 → []，K5 不白屏）
  const { data: airRaw } = useFeed<AirTrafficRaw>('airtraffic');
  // 1.6.0 预埋：市场行情读取层仅触发 fetch，本批无面板（不为它分配 RingPoint）
  const { data: marketRaw } = useFeed<MarketQuotesRaw>('market_quotes');
  const { report } = useStatus();
  // 跨面板聚焦（R-P1-03）：地图消费 focusPointId，点击点位可反向写回
  const { focusPointId, selectSignal, clearFocus } = useSelection();

  const model = useMemo(() => adaptGrv(data), [data]);
  const points = useMemo(() => buildRiskPoints(model.geographic), [model]);
  const arcs = useMemo(() => buildRiskArcs(model.geographic), [model]);
  // 事件触发式告警柱（气候 / 灾害事件）：无事件时为空数组，地图上什么都不画
  const eventPoints = useMemo(() => buildEventBars(data?.events), [data]);
  // v1.10.8 同地点聚合：GDELT 同城事件（含拼写变体 Beijing/Peking）合并为一个聚合点，
  // 返回聚合 RiskPoint[]（aggCount>1 带计数徽标）+ childrenByPointId（弹框展示同地点全部事件）
  const { points: newsGeoPoints, childrenByPointId } = useMemo(
    () => aggregateNewsGeo(newsGeoRaw ?? null),
    [newsGeoRaw],
  );
  const airPoints = useMemo(() => adaptAirTraffic(airRaw ?? null), [airRaw]);
  // 核设施：feed 缺失时 mergeNuclear 回落静态种子，读数为空 ⇒ 灰色虚线菱形（不白屏、不编数）
  const nuclearRows = useMemo(() => mergeNuclear(nuclearRaw ?? null), [nuclearRaw]);
  const nuclearPoints = useMemo(() => buildNuclearPoints(nuclearRows), [nuclearRows]);

  // K7 层叠顺序：海量点(P2 暂无) → 常规点 → 事件点 → 地理新闻 → 固定设施
  // 地理新闻位于「事件点」之后、「核设施」之前：与 event 同属增量信息但更稳定，
  // 落在固定设施之下避免海量时淹没核读数菱形。
  void marketRaw; // 显式标记已消费（仅 fetch 不渲染，预埋备查）
  const allPoints = useMemo(
    () => capPointsPerLayer([...points, ...eventPoints, ...newsGeoPoints, ...airPoints, ...nuclearPoints]),
    [points, eventPoints, newsGeoPoints, airPoints, nuclearPoints],
  );

  const visibleSet = useMemo<ReadonlySet<LayerCategory>>(
    () => new Set(visibleCategories),
    [visibleCategories],
  );

  // 地区范围内的点位（world 时 inRegion 恒真，等价于升级前行为）
  const regionPoints = useMemo(
    () => allPoints.filter((p) => inRegion(p, region)),
    [allPoints, region],
  );

  // 过滤 = 地区范围 ∩ 图层显隐
  const visiblePoints = useMemo(
    () => regionPoints.filter((p) => visibleSet.has(p.category)),
    [regionPoints, visibleSet],
  );

  // 弧线是地缘维度之间的联动，随 geo 图层一起显隐
  const visibleArcs = useMemo(() => (visibleSet.has('geo') ? arcs : []), [visibleSet, arcs]);

  // 战略要地：常驻叠加层，独立于 12 类风险色轴；开关关掉时传空数组给子视图。
  // validStrategicSites 已做容错（坐标越界 / 缺字段 / 重复 id 一律跳过），空数据绝白屏。
  // 要地同样按地区过滤：切到「中东」时不该还在画面外挂着巴拿马运河
  const sites = useMemo<ReturnType<typeof validStrategicSites>>(
    () =>
      sitesVisible ? validStrategicSites(STRATEGIC_SITES).filter((s) => inRegion(s, region)) : [],
    [sitesVisible, region],
  );

  // 图例计数按**当前地区**统计：切到中东时，图例里的数字就是中东范围内的点位数
  const counts = useMemo<LayerCountMap>(() => {
    const map: LayerCountMap = {};
    for (const p of regionPoints) map[p.category] = (map[p.category] ?? 0) + 1;
    return map;
  }, [regionPoints]);

  const missingCount = useMemo(
    () => visiblePoints.filter((p) => p.status === 'missing').length,
    [visiblePoints],
  );

  const toggleCategory = useCallback((category: LayerCategory) => {
    setVisibleCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      // 始终按 ALL_CATEGORIES 的稳定顺序落库，避免持久化内容随点击顺序抖动
      return ALL_CATEGORIES.filter((k) => next.has(k));
    });
  }, []);

  const setAllCategories = useCallback((on: boolean) => {
    setVisibleCategories(on ? [...ALL_CATEGORIES] : []);
  }, []);

  // 记住上次的视图选择
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, [mode]);

  // 记住上次的图层显隐（K8）
  useEffect(() => {
    try {
      window.localStorage.setItem(
        LAYER_VISIBILITY_STORAGE_KEY,
        serializeLayerVisibility(visibleCategories),
      );
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, [visibleCategories]);

  // 记住战略要地的显隐偏好（独立键位）
  useEffect(() => {
    try {
      window.localStorage.setItem(STRATEGIC_SITES_STORAGE_KEY, String(sitesVisible));
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, [sitesVisible]);

  // 记住上次选择的地区（R-P1-02，键位 kaiyang.region）
  useEffect(() => {
    try {
      window.localStorage.setItem(REGION_STORAGE_KEY, region);
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, [region]);

  // 聚焦点若被地区切换 / 图层关闭挤出可见集，清掉聚焦态：
  // 否则相机会停在一个「什么都没画」的位置，用户看不到任何高亮，像是卡住了。
  useEffect(() => {
    if (!focusPointId) return;
    if (!visiblePoints.some((p) => p.id === focusPointId)) clearFocus();
  }, [focusPointId, visiblePoints, clearFocus]);

  // 缺失维度上报告警（供状态条记录）
  useEffect(() => {
    if (!data) return;
    model.dimensions
      .filter((d) => d.status === 'missing')
      .forEach((d) => report({ feed: 'grv', field: d.id, message: `GRV 维度缺失：${d.label}` }));
  }, [model, data, report]);

  const headline = model.headline;
  const headlineColor = severityColor(headline?.value ?? null);
  const eventVisible = visibleSet.has('event');
  // 事件计数随地区收敛（与图例计数同口径）
  const regionEventCount = regionPoints.filter((p) => p.category === 'event').length;
  const regionLabel = regionDef(region)?.label ?? '全球';
  // v1.10.5 弹框：点击地图点位 → 聚焦 + 弹框（同地点事件列表）
  const [popupPoint, setPopupPoint] = useState<RiskPoint | null>(null);
  // v1.10.8 弹框事件源：直接取聚合组的 children（比 location_name 过滤更准——聚合 key 已含拼写变体合并）
  const popupChildren = useMemo(() => {
    if (!popupPoint) return [];
    return childrenByPointId.get(popupPoint.id) ?? [];
  }, [popupPoint, childrenByPointId]);
  // 点击地图点位 → 反向写回聚焦态（信号侧无 key 可给，故第一参传 null）；
  // 仅新闻/冲突类别弹框（GRV/核设施点只聚焦，v1.10.8 明确边界）
  const handlePointClick = useCallback(
    (p: RiskPoint) => {
      const willFocus = focusPointId !== p.id;
      selectSignal(null, willFocus ? p.id : null);
      const isNewsPoint = p.category === 'news' || p.category === 'conflict';
      setPopupPoint(willFocus && isNewsPoint ? p : null);
    },
    [selectSignal, focusPointId],
  );

  return (
    <div className="glass-panel scanlines flex h-full min-h-[560px] flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="panel-title mb-0">
          {mode === 'globe' ? '全球风险地球' : '全球风险平面图'}
        </div>
        <span
          className="chip text-white/45"
          title={`已按图层开关过滤后的可见点位 / ${regionLabel}范围内点位（全球共 ${allPoints.length}）；综合维度不投影`}
        >
          点位 {visiblePoints.length}/{regionPoints.length}
        </span>

        {regionEventCount > 0 && eventVisible && (
          <span
            className="chip"
            title="气候 / 灾害事件触发的地图告警柱（来自 grv_latest.json events[]）"
            style={{ borderColor: withAlpha('#f59e0b', 0.5), color: '#fbbf24' }}
          >
            ⚠ 事件 {regionEventCount}
          </span>
        )}

        {headline && (
          <span
            className="chip"
            title={headline.note ?? '全球综合指数（无地理位置，不投影到地图）'}
            style={{ borderColor: withAlpha(headlineColor, 0.5), color: headlineColor }}
          >
            {headline.label} {fmtNum(headline.value)}
          </span>
        )}

        <div className="ml-auto flex items-center gap-1 rounded-full border border-white/10 bg-black/30 p-0.5">
          <button
            type="button"
            onClick={() => setMode('globe')}
            className={`rounded-full px-2.5 py-0.5 text-[11px] transition ${mode === 'globe' ? 'bg-accent/20 text-accent' : 'text-white/40 hover:text-white/70'}`}
            aria-pressed={mode === 'globe'}
          >
            🌐 3D 地球
          </button>
          <button
            type="button"
            onClick={() => setMode('flat')}
            className={`rounded-full px-2.5 py-0.5 text-[11px] transition ${mode === 'flat' ? 'bg-accent/20 text-accent' : 'text-white/40 hover:text-white/70'}`}
            aria-pressed={mode === 'flat'}
          >
            🗺️ 平面
          </button>
        </div>
      </div>

      {/* 地区 Tab（R-P1-02）：独立一行，避免与视图切换器在窄屏挤成一团 */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <RegionTabs region={region} onChange={setRegion} />
        {region !== 'world' && (
          <span className="chip text-white/45" title="点击「全球」可取消地区过滤">
            已聚焦 {regionLabel}
          </span>
        )}
      </div>

      {/* 主体：左侧指标树 + 地图。左树复用本组件已有的图层状态，
          不新建 Context、不重复 useFeed（useFeed 无缓存，重复调用 = 重复请求）。 */}
      <div className="flex min-h-[400px] flex-1 gap-3">
        <LayerTreePanel
          visible={visibleSet}
          counts={counts}
          onToggle={toggleCategory}
          onSetAll={setAllCategories}
          missingCount={missingCount}
          sitesVisible={sitesVisible}
          onToggleSites={() => setSitesVisible((v) => !v)}
        />

        <div className="relative min-w-0 flex-1">
          <div
            className={`absolute inset-0 ${mode === 'globe' ? '' : 'pointer-events-none invisible'}`}
            aria-hidden={mode !== 'globe'}
          >
            <GlobePanel
              points={visiblePoints}
              arcs={visibleArcs}
              sites={sites}
              active={mode === 'globe'}
              region={region}
              focusPointId={focusPointId}
              onPointClick={handlePointClick}
            />
          </div>

          <div
            className={`absolute inset-0 ${mode === 'flat' ? '' : 'pointer-events-none invisible'}`}
            aria-hidden={mode !== 'flat'}
          >
            <FlatMapPanel
              points={visiblePoints}
              arcs={visibleArcs}
              sites={sites}
              active={mode === 'flat'}
              region={region}
              focusPointId={focusPointId}
              onPointClick={handlePointClick}
            />
          </div>

          {loading && (
            <div className="pointer-events-none absolute left-2 top-2 z-10 text-[11px] text-white/40">
              数据加载中…
            </div>
          )}
          {error && (
            <div className="absolute left-2 top-2 z-10 rounded-md border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
              GRV 读取失败：{error.message}
            </div>
          )}

          {/* v1.10.5 事件弹框：点击地理新闻点显示详情 + 同地点事件列表（v1.10.8 源 = 聚合组 children） */}
          {popupPoint && (
            <EventPopup
              point={popupPoint}
              related={popupChildren}
              onClose={() => setPopupPoint(null)}
            />
          )}
        </div>
      </div>

      <LayerLegend visible={visibleSet} onSetAll={setAllCategories} missingCount={missingCount} />

      <div className="mt-1 text-right text-[10px] text-white/25">
        {mode === 'globe' ? '拖拽旋转 · 滚轮缩放 · 点击点位聚焦' : '悬停查看维度详情 · 点击点位聚焦'}
      </div>
    </div>
  );
}
