import {
  categoryColor,
  categoryShape,
  resolvePointStatus,
} from '@/config/layerCategories';
import type { PointStatus } from '@/config/layerCategories';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import type { NewsGeoEvent, NewsGeoRaw } from '@/types/contracts';

/**
 * 地理新闻图层构建层（1.6.0 新增，读取层骨架）。
 *
 * 职责边界（与 `lib/nuclearData.ts` 同构）：
 * - 颜色 / 形状 / 强度全部在此**预计算**进 `RiskPoint`，渲染器只做直读（K6）；
 * - `intensity` 0~100 已由天枢归一（DATA_CONTRACT §2.7），开阳不自行折算；
 * - 每个导出函数第一行就是入参 nullish 检查，任何降级路径不抛异常（K5 红线）。
 *
 * 图层类别：GDELT 事件按 `event_type` 归入 `'news'`（默认）或 `'conflict'`（冲突事件，
 * 2026-08-11 路线 A：与 layerCategories.ts 已登记的 conflict 类别色对齐，可独立开关）。
 * 其余事件走 `'news'`（与 `news_export.json` 同类别）。id 命名空间 `'newsgeo:'`（K2）。
 *
 * XSS 防线二（2026-08-11）：`location_name` / `theme` / `country` / `event_type` 等
 * 外部字段一律经 `sanitizeText` 清洗（trim / 控制字符剥离 / 长度上限），渲染层
 * `pointTooltipHtml` 再统一 HTML 转义——双保险，防 GDELT 地名/URL 注入。
 */

/** 有限数守卫：NaN / Infinity / null / undefined / 字符串一律判否。 */
function finiteOrNull(input: unknown): number | null {
  return typeof input === 'number' && Number.isFinite(input) ? input : null;
}

/** 非空字符串守卫（trim 后非空）。 */
function textOrNull(input: unknown): string | null {
  return typeof input === 'string' && input.trim() !== '' ? input.trim() : null;
}

/** 外部文本消毒（XSS 防线二）：trim + 剥离控制字符 + 长度上限。
 * 用于 location_name/theme/country/event_type/event_date 等进入 tooltip 的字段；
 * HTML 转义统一由渲染层 pointTooltipHtml 完成，此处不做转义以避免双重转义。 */
function sanitizeText(input: unknown, maxLen = 120): string | null {
  const t = textOrNull(input);
  if (!t) return null;
  // 剥离 C0/C1 控制字符（保留 \t 之外的可见文本），并做长度截断
  const clean = t.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, '');
  if (clean === '') return null;
  return clean.length > maxLen ? `${clean.slice(0, maxLen)}…` : clean;
}

/** 强度归一化：夹取到 [0,100]；浮点毛刺归整到 2 位小数（与 nuclearData 对齐）。 */
function normalizeIntensity(raw: unknown): number | null {
  const v = finiteOrNull(raw);
  if (v === null) return null;
  const clamped = Math.min(100, Math.max(0, v));
  return Math.round(clamped * 100) / 100;
}

/** 坐标合法性：必须是有限数且落在地理范围内（K4）。 */
function isValidCoord(lat: unknown, lng: unknown): boolean {
  const la = finiteOrNull(lat);
  const ln = finiteOrNull(lng);
  if (la === null || ln === null) return false;
  return la >= -90 && la <= 90 && ln >= -180 && ln <= 180;
}

/** 校验并规整一条 GeoEvent；不合法返回 null（跳过该条，不画到 (0,0)）。
 * 外部文本字段经 sanitizeText 消毒（XSS 防线二）。 */
function normalizeEvent(raw: unknown): NewsGeoEvent | null {
  if (!raw || typeof raw !== 'object') return null;
  const e = raw as Partial<NewsGeoEvent>;
  const id = textOrNull(e.id);
  if (!id) return null;
  if (!isValidCoord(e.lat, e.lng)) return null;
  const intensity = normalizeIntensity(e.intensity);
  if (intensity === null) return null;
  const eventType = sanitizeText(e.event_type, 40) ?? 'unknown';
  const country = sanitizeText(e.country, 40) ?? '未知';
  const mentionCount = finiteOrNull(e.mention_count);
  const eventDate = sanitizeText(e.event_date, 40) ?? undefined;
  const theme = sanitizeText(e.theme, 60) ?? undefined;
  const locationName = sanitizeText(e.location_name, 120) ?? undefined;
  return {
    id,
    lat: e.lat as number,
    lng: e.lng as number,
    event_type: eventType,
    intensity,
    country,
    mention_count: mentionCount ?? undefined,
    event_date: eventDate,
    theme,
    location_name: locationName,
  };
}

/** articles 结构（news_geo_feed.py P3-A 新闻地理点）→ RiskPoint。
 * 新闻点无强度（intensity 是 GDELT 事件语义）→ value=null / severity='缺失'，
 * 诚实标注缺强度，不伪造 GDELT 字段。id 命名空间 `news:`（与 events 的 `newsgeo:` 区分）。 */
function normalizeArticlePoint(raw: unknown): RiskPoint | null {
  if (!raw || typeof raw !== 'object') return null;
  const a = raw as {
    title?: unknown;
    url?: unknown;
    lat?: unknown;
    lng?: unknown;
    source?: unknown;
    published_at?: unknown;
  };
  const title = sanitizeText(a.title, 160);
  if (!title) return null;
  if (!isValidCoord(a.lat, a.lng)) return null;
  const url = sanitizeText(a.url, 200);
  const id = url ?? title.slice(0, 64);
  const src = sanitizeText(a.source, 60);
  const published = sanitizeText(a.published_at, 60);
  return {
    id: `news:${id}`,
    label: title,
    lat: a.lat as number,
    lng: a.lng as number,
    value: null,
    uncertainty: null,
    uncertaintyEstimated: false,
    group: src ? `news · ${src}` : 'news',
    status: 'ok',
    color: categoryColor('news', 'ok'),
    severity: severityLabel(null),
    weight: 0,
    category: 'news',
    shape: categoryShape('news'),
    rawMetric: published ? `发布于 ${published}` : undefined,
  };
}

/**
 * feed → RiskPoint[]（`category:'news'` / `shape:'circle'` / id 前缀 `newsgeo:`）。
 *
 * 降级矩阵（K5）：
 * | 输入 | 行为 |
 * |---|---|
 * | `raw` 为 null / undefined（文件缺失） | 返回空数组，**不抛异常** |
 * | `raw.events` 缺字段 / 非数组 | 返回空数组 |
 * | `raw.events` 为空数组 | 返回空数组（图层不渲染，符合 §2.7 业务态） |
 * | 单条事件 intensity 缺失或非有限数 | 跳过该条（不画到地图） |
 * | 单条事件坐标非有限或越界 | 跳过该条 |
 * | 重复 id | 取先出现者（同 nuclearData 口径，避免点位 id 撞车） |
 *
 * 因 `intensity` 已由天枢归一（DATA_CONTRACT §2.7），本适配器不再二次折算；
 * 所有点 `status='ok'`（缺强度直接跳过，不进 missing 通道）。
 */
export function adaptNewsGeo(
  raw: NewsGeoRaw | null | undefined,
): RiskPoint[] {
  if (!raw) return [];
  // P2 修复（news-geo-contract-drift）：兼容 news_geo_feed.py 的 articles 结构
  // （新闻文章地理点 title/url/lat/lng/source/published_at——GDELT events 无标题字段）。
  // 两结构并存：GDELT 写 events、NER 新闻地理化写 articles，adapter 都归一成 RiskPoint。
  const rawArticles = Array.isArray(
    (raw as unknown as { articles?: unknown[] }).articles,
  )
    ? (raw as unknown as { articles: unknown[] }).articles
    : [];
  if (rawArticles.length > 0) {
    const out: RiskPoint[] = [];
    const seen = new Set<string>();
    for (const a of rawArticles) {
      const norm = normalizeArticlePoint(a);
      if (!norm) continue;
      if (seen.has(norm.id)) continue;
      seen.add(norm.id);
      out.push(norm);
    }
    return out;
  }
  const rawEvents = Array.isArray(raw.events) ? raw.events : [];
  if (rawEvents.length === 0) return [];

  const out: RiskPoint[] = [];
  const seen = new Set<string>();
  for (const e of rawEvents) {
    const norm = normalizeEvent(e);
    if (!norm) continue;
    // id 全局唯一约束：K2 命名空间前缀 'newsgeo:' 之后仍可能在脏数据撞车
    if (seen.has(norm.id)) continue;
    seen.add(norm.id);

    // intensity 已是 0~100 归一值（D1：归一为视觉强度 weight）
    const value = norm.intensity;
    const status: PointStatus = resolvePointStatus(undefined, value);
    // 2026-08-11 路线 A：event_type==='conflict' 归入已登记的 conflict 类别（独立开关 + 红系配色），
    // 其余事件走 'news' 类别。categoryLabel/图例计数随 category 自动对齐。
    const category: 'news' | 'conflict' = norm.event_type === 'conflict' ? 'conflict' : 'news';
    const displayLabel = norm.location_name ?? norm.country;
    out.push({
      id: `newsgeo:${norm.id}`,
      label: displayLabel,
      lat: norm.lat,
      lng: norm.lng,
      value,
      uncertainty: null,
      uncertaintyEstimated: false,
      // group 内含事件类别 + 国家，便于点击 / 悬停时一眼看懂
      group: `${norm.event_type} · ${norm.country}`,
      status,
      // intensity=null 不会走到这里（normalizeIntensity 已拦截），强制 'ok'
      color: categoryColor(category, status),
      severity: severityLabel(value),
      weight: value === null ? 0 : Math.min(1, Math.max(0, value / 100)),
      category,
      shape: categoryShape(category),
      // 原始度量原样传入 tooltip（不参与计算）
      rawMetric:
        norm.mention_count !== undefined
          ? `提及 ${norm.mention_count} 次${norm.theme ? ` · ${norm.theme}` : ''}`
          : norm.theme ?? undefined,
      note: norm.event_date,
    });
  }
  return out;
}
