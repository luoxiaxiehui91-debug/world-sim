/**
 * 开阳 Wave 1 数据契约类型定义。
 * 所有类型均对应上游契约文件（grv_latest.json / news_export.json / sim_trigger.json / fred_history/manifest.json）。
 * 约定：每个 feed JSON 必须携带 schema_version（Wave 1 = "1.0"）。
 */

/** 气候 / 自然灾害事件（按需触发地图告警柱）。由上游事件 feed 提供，缺失则不渲染。 */
export interface GrvEvent {
  id: string;
  type: 'climate' | 'disaster';
  label: string;
  lat: number;
  lng: number;
  /** 事件严重度 0~100，决定柱高与配色 */
  value: number;
  /** 补充说明，如"7.8级地震 / 季风洪涝" */
  note?: string;
}

/** GRV 原始契约（grv_latest.json）。允许未知额外字段，便于未来扩展。 */
export interface GrvRaw {
  schema_version?: string;
  updated?: string;
  gdelt_updated?: string;
  source_quality?: string;
  /** 气候 / 灾害事件列表（可选）：仅当上游推送事件时才在地图上画告警柱 */
  events?: GrvEvent[];
  /** 任意维度数值键（如 taiwan_strait / middle_east_energy ...） */
  [key: string]: number | string | null | undefined | GrvEvent[];
}

/** 经适配后的单一 GRV 维度（统一内部模型，含坐标与缺失状态）。 */
export interface GrvDimension {
  id: string;
  label: string;
  /** 数值，null 表示数据源缺失该维度 */
  value: number | null;
  /** 不确定区间半宽，null 表示未知 */
  uncertainty: number | null;
  /** 是否为估算值（Wave1 数据源未提供，按 8% 估算） */
  uncertaintyEstimated: boolean;
  /** 维度类别：geographic=可投影到地图；composite=全球综合，不上地图 */
  kind: 'geographic' | 'composite';
  /** 纬度；composite 维度为 null */
  lat: number | null;
  /** 经度；composite 维度为 null */
  lng: number | null;
  group: string;
  /** 补充说明（来自维度定义，可选） */
  note?: string;
  status: 'ok' | 'missing';
  /** 是否为推导维度（GDELT聚合，无GPR基线）。true时前端显示推导值徽章+虚线边框 */
  isDerived?: boolean;
  /** 推导维度置信度 0-1（来自 grv_latest.json._derived_meta）；实测维度为 undefined */
  derivedConfidence?: number;
  /** 推导维度缺失的国家列表（来自 _derived_meta.missing） */
  derivedMissing?: string[];
}

/** 新闻 / 叙事条目（news_export.json 数组元素）。字段宽松，缺失即降级渲染。 */
export interface NewsItem {
  date?: string;
  source?: string;
  /** 原文 URL，有则标题可点击跳转 */
  url?: string;
  indicator?: string;
  series_id?: string;
  title?: string;
  category?: string;
  level?: string;
  direction?: string;
  alert_type?: string;
  current?: number;
  baseline?: number;
  ratio?: number;
  z_score?: number;
  details?: string;
  risk_note?: string;
  trigger_titles?: string[];
  [key: string]: unknown;
}

/** FRED 序列清单元信息（fred_history/manifest.json）。 */
export interface FredSeriesMeta {
  id: string;
  label: string;
  unit?: string;
  /** 相对 DATA_BASE_URL 的 CSV 路径 */
  file: string;
  color?: string;
  category?: string;
}

export interface FredManifest {
  schema_version?: string;
  updated?: string;
  series: FredSeriesMeta[];
}

/** 单条 FRED 观测点。 */
export interface FredPoint {
  date: string;
  value: number;
}

/** 加载完成后的 FRED 序列（含观测点）。 */
export interface FredSeries extends FredSeriesMeta {
  points: FredPoint[];
}

/**
 * 推演触发状态（sim_trigger.json，可选）。
 * H18 统一契约（2026-08-16）：文件永远合法 JSON，两态——
 *  触发态：天枢 grv_threshold 写 {triggered: true, level: number, event/reason, triggered_at}
 *  已消费态：天璇 run.py daemon 读后写 {triggered: false, consumed: true, level, event/reason,
 *           triggered_at, consumed_at}（原 write_text("") 清空导致开阳 JSON.parse('') 崩）
 */
export interface SimTriggerRaw {
  schema_version?: string;
  triggered?: boolean;
  consumed?: boolean;
  level?: number;
  event?: string;
  reason?: string;
  triggered_at?: string;
  consumed_at?: string;
  updated?: string;
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/* 核设施 / 辐射监测（nuclear_sites.json，1.2.0 新增）                  */
/* ------------------------------------------------------------------ */

/** 辐射分级。后端优先给；缺失时前端按 baseline 倍数推断，再缺失则 'unknown'。 */
export type NuclearLevel = 'normal' | 'elevated' | 'alert' | 'unknown';

/** 核设施站点（nuclear_sites.json 的 sites[]；后端未就绪时用前端静态种子）。 */
export interface NuclearSite {
  /** 站点唯一 id（英文 kebab，如 'zaporizhzhia'） */
  id: string;
  /** 中文站名（显示用） */
  name: string;
  /** 英文/原文名（可选，tooltip 副标题） */
  name_en?: string;
  /** 国家/地区中文名 */
  country: string;
  /** 纬度，小数 4 位（≈11m） */
  lat: number;
  /** 经度，小数 4 位 */
  lng: number;
  /** 站点类型：npp=核电站 / monitor=辐射监测站 / legacy=事故遗址 */
  type?: 'npp' | 'monitor' | 'legacy';
  /** 补充说明 */
  note?: string;
}

/** 核设施辐射读数（nuclear_sites.json 的 readings[]；后端未就绪时整段缺失，前端降级「—」）。 */
export interface NuclearWatchReading {
  /** 关联 NuclearSite.id */
  site_id: string;
  /** 辐射读数；null / 字段缺失 = 无数据，面板显示「—」 */
  reading: number | null;
  /** 读数单位，如 'µSv/h' | 'nSv/h' | 'CPM'。缺失时面板不显示单位 */
  unit?: string;
  /** 本底参考值（可选，用于算倍数） */
  baseline?: number | null;
  /** 该读数的观测时间，ISO 8601 UTC */
  updated?: string;
  /** 后端给出的分级；缺失时前端按 baseline 倍数推断，再缺失则 'unknown' */
  level?: NuclearLevel;
}

/** nuclear_sites.json 顶层（sites / readings 均可选：整文件缺失或空数组均须优雅降级）。 */
export interface NuclearSitesRaw {
  schema_version?: string;
  updated?: string;
  sites?: NuclearSite[];
  readings?: NuclearWatchReading[];
}

/* ------------------------------------------------------------------ */
/* 核辐射实时读数（safecast_nuke.json，2.0.0 新增，天枢 fetch_safecast_nuke.py）*/
/* ------------------------------------------------------------------ */

/** SafeCast 单站点读数（CC0 公开 API，历史归档均值非实时流）。 */
export interface SafecastSite {
  /** 站点 key（zaporizhzhia / chernobyl / bushehr / yongbyon / fukushima / dimona） */
  key: string;
  /** 站点显示名 */
  site?: string;
  /** 平均 CPM；null = 源无数据 */
  avgCPM: number | null;
  /** 有效测量样本数 */
  n: number;
  /** avgCPM > 100 → true（历史归档均值语义，非实时告警） */
  anom: boolean;
  /** 源测量时间戳（历史归档日，如 2023-07-18；防误读为实时） */
  latest_captured_at: string | null;
}

/** safecast_nuke.json 顶层。 */
export interface SafecastNukeRaw {
  fetched_at?: string;
  source?: string;
  sites?: SafecastSite[];
  /** true = 整轮拉取降级（重试耗尽），sites 为空 */
  degraded?: boolean;
}

/* ------------------------------------------------------------------ */
/* 地理化新闻事件（news_geo.json，1.6.0 新增，详见 docs/DATA_CONTRACT.md §2.7）*/
/* ------------------------------------------------------------------ */

/** 地理化新闻事件（GDELT ActionGeo 派生）。 */
export interface NewsGeoEvent {
  id: string;
  /** 纬度，4 位小数（≈11m） */
  lat: number;
  /** 经度，4 位小数 */
  lng: number;
  /** 事件类别：天枢负责把 CAMEO 码映射到四类枚举；开阳对未知取值不猜 */
  event_type: string;
  /** 强度 0~100，与 §2.5 严重度同量纲；归一口径由天枢给定 */
  intensity: number;
  /** 国家/地区，建议用 ActionGeo_CountryCode */
  country: string;
  /** 该事件被提及次数（GDELT NumMentions），可作二级权重 */
  mention_count?: number;
  /** GKG 主题标签；缺失则整字段省略 */
  theme?: string;
  /** ActionGeo_FullName；缺失时回落显示 country */
  location_name?: string;
  /** 事件日期（GDELT SQLDATE），用于时间窗筛选 */
  event_date?: string;
  /** 事件来源新闻 URL（GDELT SOURCEURL；v1.10.5 正式化，点击弹框跳转原文） */
  source_url?: string;
}

/** news_geo.json 顶层（events 必填；空数组是合法业务态）。 */
export interface NewsGeoRaw {
  schema_version?: string;
  updated?: string;
  events: NewsGeoEvent[];
}

/* ------------------------------------------------------------------ */
/* 市场报价（market_quotes.json，1.6.0 新增 / 读取层预埋无面板）           */
/* ------------------------------------------------------------------ */

/** 单个品种报价快照。 */
export interface MarketQuote {
  /** 品种代码（如 'GC=F' 黄金 / 'CL=F' 原油 / '000001.SS' 沪深300） */
  symbol: string;
  /** 中文/英文显示名 */
  name: string;
  /** 最新价；null = 该品种本轮无报价（不删除该行，保留快照结构） */
  price: number | null;
  /** 当日涨跌幅 (%)；缺失时面板显示「—」 */
  change_pct?: number | null;
  /** 报价时间 ISO 8601 */
  updated?: string;
  /** 品种类别（'metal' | 'energy' | 'index' | ...），仅用于将来面板分组；当前无面板 */
  category?: string;
}

/** market_quotes.json 顶层（quotes[] 可选：整文件缺失或空数组均须优雅降级）。 */
export interface MarketQuotesRaw {
  schema_version?: string;
  updated?: string;
  quotes?: MarketQuote[];
}

/* ------------------------------------------------------------------ */
/* 报告索引（reports_index.json，R-1 新增）                              */
/* ------------------------------------------------------------------ */

/** 单份报告元数据（reports_index.json 的 reports[]）。 */
export interface ReportMeta {
  /** 报告唯一 id（天枢 sha1 派生） */
  id: string;
  /** 报告类型：宏观分析 / 月度简报 / 假设推演 / 演化仿真 / 预测追踪 */
  type: string;
  /** 展示标题（天枢从文件名派生） */
  title: string;
  /** 原文件名（含 .md） */
  filename: string;
  /** 相对 DATA_BASE_URL 的 markdown 路径（如 reports/xxx.md） */
  path: string;
  /** 报告日期 YYYY-MM-DD（天枢从文件名/mtime 派生） */
  updated: string;
}

/** reports_index.json 顶层。 */
export interface ReportsIndexRaw {
  schema_version?: string;
  updated?: string;
  reports?: ReportMeta[];
}

/* ------------------------------------------------------------------ */
/* 金融条件（fci_latest.json + fci_daily.csv + GSCPI.csv，R-3 新增）      */
/* ------------------------------------------------------------------ */

/** fci_latest.json 顶层（天枢 compute_fci.py 产物）。 */
export interface FciLatestRaw {
  schema_version?: string;
  /** 数据日期 YYYY-MM-DD */
  date?: string;
  as_of?: string;
  data_vintage?: string;
  /** 全样本重估 FCI（标准差，越高越紧） */
  fci_revised?: number | null;
  /** 扩展窗（无 look-ahead）FCI */
  fci_pit?: number | null;
  interpretation?: string;
  sanity_vs_nfci?: { status?: string; [k: string]: unknown };
  components?: Array<{ series_id?: string; name?: string; orient?: number; [k: string]: unknown }>;
  [key: string]: unknown;
}

/** fci_daily.csv 单行（date + fci_revised + fci_pit 等列，R-3 面板直接解析）。 */
export interface FciDailyPoint {
  date: string;
  /** 全样本重估 FCI */
  revised: number | null;
  /** 扩展窗 FCI；na（未到 burn-in）时为 null */
  pit: number | null;
}

/* ------------------------------------------------------------------ */
/* 风险信号（R-4 新增：climate/disaster/earthquake/energy/hdx/news）     */
/* ------------------------------------------------------------------ */

/** 风险信号通用壳（各文件顶层均有 _schema_version/updated/status）。 */
export interface RiskSignalBase {
  _schema_version?: string;
  schema_version?: string;
  updated?: string;
  /** 'ok' | 'unavailable' 等 */
  status?: string;
  [key: string]: unknown;
}

/** climate_signals.json（气候：ONI / FIRMS 火点 / 综合评分）。 */
export interface ClimateSignalsRaw extends RiskSignalBase {
  fetched_at?: string;
  oni?: {
    value?: number | null;
    status?: string;
    date?: string;
    interpretation?: string;
    [k: string]: unknown;
  } | null;
  firms?: {
    total_hotspots?: number;
    high_confidence?: number;
    active_fire_regions?: unknown[];
    date?: string;
    [k: string]: unknown;
  } | null;
  climate_risk_score?: number | null;
  risk_level?: string;
}

/** disaster_signals.json（自然灾害：评分 + 事件计数）。 */
export interface DisasterSignalsRaw extends RiskSignalBase {
  fetched_at?: string;
  disaster_risk_score?: number | null;
  risk_level?: string;
  event_count_24h?: number | null;
  significant_events?: unknown[];
  alerts?: unknown[];
  latest_significant?: unknown;
}

/** earthquake_risk.json（USGS 地震：评分 + 近 24h 事件）。 */
export interface EarthquakeRiskRaw extends RiskSignalBase {
  seismic_risk?: number | null;
  event_count_24h?: number | null;
  count_m45?: number | null;
  count_m55?: number | null;
  count_m65?: number | null;
  max_mag?: number | null;
  window_hours?: number | null;
  top_events?: Array<{ magnitude?: number; place?: string; time_utc?: string; [k: string]: unknown }>;
}

/** energy_risk.json（电网/能源：碳强度风险）。 */
export interface EnergyRiskRaw extends RiskSignalBase {
  grid_carbon_risk?: number | null;
  uk_grid?: {
    status?: string;
    intensity_forecast?: number | null;
    intensity_index?: string;
    fossil_share_pct?: number | null;
    [k: string]: unknown;
  } | null;
  national_grid_eso?: {
    status?: string;
    reason?: string;
    note?: string;
    [k: string]: unknown;
  } | null;
  source?: string;
}

/** hdx_risk.json / news_risk.json（多为 unavailable，保留状态展示）。 */
export interface UnavailableRiskRaw extends RiskSignalBase {
  reason?: string;
  source?: string;
}

/** news_risk.json（08-14 起 GDELT DOC 2.0 主源，含文章列表）。 */
export interface NewsRiskArticle {
  title?: string;
  url?: string;
  domain?: string;
  source?: string;
  published_at?: string;
  language?: string;
  sourcecountry?: string;
}
/** airtraffic_opensky.json（OpenSky 实时航班快照，08-14 开阳 air 图层）。 */
export interface AirTrafficPoint {
  lat: number;
  lng: number;
  alt_m?: number | null;
  vel_ms?: number | null;
  callsign?: string | null;
  origin?: string | null;
  track?: number | null;
}
export interface AirTrafficRaw extends RiskSignalBase {
  flights_in_air?: number;
  total_states?: number;
  scope?: string;
  coordinates?: AirTrafficPoint[];
}

/** airroutes.json（OpenFlights 全球航线网，08-14 开阳 air 图层静态航线网）。 */
export interface AirRouteRaw {
  from: string;
  from_lat: number;
  from_lng: number;
  to: string;
  to_lat: number;
  to_lng: number;
  /** 该机场对在 routes.dat 的出现频次（≈运营航司数，视觉权重 = 航线繁忙度） */
  flights: number;
}
export interface AirRoutesRaw extends RiskSignalBase {
  scope?: string;
  // schema_version 继承 RiskSignalBase（string）
  routes_count?: number;
  airports_indexed?: number;
  routes?: AirRouteRaw[];
}

/** sdr_summary.json（KiwiSDR 全球接收器目录，08-14 开阳 sdr 图层）。 */
export interface SdrReceiverRaw {
  id: string;
  name: string;
  /** 注意：后端字段是 lon（不是 lng） */
  lat: number;
  lon: number;
  loc: string;
  grid: string;
  status: string;
  users: string;
  updated: string;
}
export interface SdrSummaryRaw extends RiskSignalBase {
  total?: number;
  online?: number;
  offline?: number;
  receivers?: SdrReceiverRaw[];
}

/** firms_fire.json hotspots[]（NASA FIRMS 火点，1° 网格后端预聚合，08-14 thermal 图层）。 */
export interface ThermalHotspotRaw {
  /** 网格中心坐标 */
  lat: number;
  lng: number;
  /** 网格内火点数 */
  count: number;
  /** 网格内最强 FRP（辐射功率，MW） */
  frp_max: number;
  /** 网格内高置信火点数 */
  high_conf: number;
}
export interface FirmsRaw extends RiskSignalBase {
  total_hotspots?: number;
  high_confidence?: number;
  active_fire_regions?: string[];
  hotspots?: ThermalHotspotRaw[];
  upstream_window_days?: number;
}

/** spacelaunch.json（Next Spaceflight 发射记录，08-14 开阳 space 图层）。 */
export interface SpaceLaunchItemRaw {
  name?: string | null;
  /** 发射时间窗（ISO） */
  net?: string | null;
  /** upcoming: Go/TBD/...；previous: Launch Successful/Failure/... */
  status?: string | null;
  rocket?: string | null;
  provider?: string | null;
  pad_name?: string | null;
  /** 发射场坐标 */
  lat: number;
  lng: number;
  /** 'upcoming' | 'previous' */
  type?: string;
}
export interface SpaceLaunchRaw extends RiskSignalBase {
  scope?: string;
  launches_count?: number;
  launches?: SpaceLaunchItemRaw[];
}

/** health_geo.json（GDELT GKG 卫生事件地理提取，08-15 开阳 health 图层）。 */
export interface HealthEventRaw {
  doc: string;
  date: string;
  lat: number;
  lng: number;
  loc_name: string;
  keywords: string[];
}
export interface HealthGeoRaw extends RiskSignalBase {
  scope?: string;
  events_count?: number;
  events?: HealthEventRaw[];
}

export interface NewsRiskRaw extends RiskSignalBase {
  source?: string;
  gdelt?: {
    status?: string;
    count?: number;
    articles?: NewsRiskArticle[];
  };
  articles?: NewsRiskArticle[];
}
