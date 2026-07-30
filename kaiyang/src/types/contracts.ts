/**
 * 开阳 Wave 1 数据契约类型定义。
 * 所有类型均对应上游契约文件（grv_latest.json / news_export.json / sim_trigger.json / fred_history/manifest.json）。
 * 约定：每个 feed JSON 必须携带 schema_version（Wave 1 = "1.0"）。
 */

/** GRV 原始契约（grv_latest.json）。允许未知额外字段，便于未来扩展。 */
export interface GrvRaw {
  schema_version?: string;
  updated?: string;
  gdelt_updated?: string;
  source_quality?: string;
  /** 任意维度数值键（如 taiwan_strait / middle_east_energy ...） */
  [key: string]: number | string | null | undefined;
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
}

/** 新闻 / 叙事条目（news_export.json 数组元素）。字段宽松，缺失即降级渲染。 */
export interface NewsItem {
  date?: string;
  source?: string;
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
