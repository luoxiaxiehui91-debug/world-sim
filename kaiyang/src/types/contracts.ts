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

/** 推演触发状态（sim_trigger.json，可选）。 */
export interface SimTriggerRaw {
  schema_version?: string;
  triggered?: boolean;
  level?: string;
  reason?: string;
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
