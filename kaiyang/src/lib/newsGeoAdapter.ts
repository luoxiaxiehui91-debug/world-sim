/**
 * newsGeoAdapter — 地区新闻图层（开阳 news/conflict 图层）。
 * 1.6.0 接入，1.10.8 聚合 + 08-16 v2 重写弹框 label。
 *
 * 数据源：fetch_news_geo → news_geo.json（GDELT 2.0 events 派生）。
 *
 * ⚠ 数据源真相（08-16 实测 news_geo.json 252 条）：
 *   - event_type 只 3 个值：political(244) / conflict(6) / protest(2) —— 简单可枚举
 *   - theme 全空（GDELT events 没填）—— 不可用
 *   - **无 title 字段**（GKG 事件无标题，标题只在 DOC API，但 NAS IP 被 429 限流）
 *   - source_url 100% 有值（具体报道 URL，URL 路径常含文章 slug）
 *
 * 08-16 v2 用户反馈："弹框第一行应该显示发生了什么（像卫生那样），尽量中文"。
 * 解决：弹框 label = URL slug 还原的伪标题（信息密度高 + 描述具体内容），
 *       fallback 到中文事件类型（`政治类报道` / `冲突事件` / `抗议活动`）。
 *       不依赖 DOC API 标题回填（NAS IP 限流）；数据源本来就有信息可用。
 */

import {
  categoryColor,
  categoryShape,
  resolvePointStatus,
} from '@/config/layerCategories';
import type { PointStatus } from '@/config/layerCategories';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import type { NewsGeoEvent, NewsGeoRaw } from '@/types/contracts';

/** 有限数守卫 */
function finiteOrNull(input: unknown): number | null {
  return typeof input === 'number' && Number.isFinite(input) ? input : null;
}

/** 非空字符串守卫 */
function textOrNull(input: unknown): string | null {
  return typeof input === 'string' && input.trim() !== '' ? input.trim() : null;
}

/** 外部文本消毒（XSS 防线二） */
function sanitizeText(input: unknown, maxLen = 120): string | null {
  const t = textOrNull(input);
  if (!t) return null;
  const clean = t.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, '');
  if (clean === '') return null;
  return clean.length > maxLen ? `${clean.slice(0, maxLen)}…` : clean;
}

/** URL 消毒（href 专用） */
export function sanitizeUrl(input: unknown): string | undefined {
  const t = textOrNull(input);
  if (!t) return undefined;
  try {
    const u = new URL(t);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : undefined;
  } catch {
    return undefined;
  }
}

function normalizeIntensity(raw: unknown): number | null {
  const v = finiteOrNull(raw);
  if (v === null) return null;
  return Math.round(Math.min(100, Math.max(0, v)) * 100) / 100;
}

function isValidCoord(lat: unknown, lng: unknown): boolean {
  const la = finiteOrNull(lat);
  const ln = finiteOrNull(lng);
  if (la === null || ln === null) return false;
  return la >= -90 && la <= 90 && ln >= -180 && ln <= 180;
}

/** event_type → 中文（08-16 实测仅 3 个值：political / conflict / protest） */
export const EVENT_TYPE_ZH: Record<string, string> = {
  political: '政治',
  conflict: '冲突',
  protest: '抗议',
};

/** 国家码 → 中文（ISO 三字母 + 部分常用别名） */
export const COUNTRY_ZH: Record<string, string> = {
  USA: '美国', CHN: '中国', FRA: '法国', TWN: '中国台湾',
  IND: '印度', GBR: '英国', DEU: '德国', RUS: '俄罗斯',
  JPN: '日本', KOR: '韩国', BRA: '巴西', AUS: '澳大利亚',
  CAN: '加拿大', MEX: '墨西哥', ZAF: '南非', EGY: '埃及',
  ISR: '以色列', IRN: '伊朗', SAU: '沙特', ARE: '阿联酋',
  TUR: '土耳其', UKR: '乌克兰', ITA: '意大利', ESP: '西班牙',
};

/**
 * URL 路径 → 可读伪标题（08-16 v2，弥补 events 无 title 字段）：
 *  - 取最后一段 slug（如 /federal-judge-threatens-doj-with-contempt-as.../）
 *  - 去尾部扩展名（.html/.htm/.aspx/.php/.htm...）
 *  - 路径全数字段（YYYY/MM/DD）剥离
 *  - - / _ → 空格；单词首字母大写
 *  - 截断到 ~70 字符 + …
 * 失败/无 slug → 返回 null（调用方 fallback EVENT_TYPE_ZH）。
 */
export function urlSlugToTitle(url: string | undefined | null, maxLen = 70): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    // 取最后路径段
    const path = u.pathname.split('/').filter(Boolean);
    if (path.length === 0) return null;
    let slug = path[path.length - 1];
    // 去扩展名
    slug = slug.replace(/\.(html?|aspx?|php|htm|xml|json|asp)$/i, '');
    // 去查询参数残留（罕见，防御）
    slug = slug.split('?')[0];
    if (!slug) return null;
    // 路径全数字段（YYYY/MM/DD 或纯 ID）剥离：保留含字母的段
    if (/^\d{4,}$/.test(slug) || /^\d{8,}$/.test(slug)) return null;
    // 分隔符转空格
    let title = slug.replace(/[-_]+/g, ' ').trim();
    if (!title) return null;
    // 首字母大写（英文单词）
    title = title
      .split(' ')
      .filter(Boolean)
      .map((w) => (w[0] ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
      .join(' ');
    if (!title) return null;
    // 截断
    if (title.length > maxLen) title = `${title.slice(0, maxLen).trimEnd()}…`;
    return title;
  } catch {
    return null;
  }
}

export function normalizeEvent(raw: unknown): NewsGeoEvent | null {
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
    source_url: sanitizeUrl(e.source_url),
  };
}

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

export function adaptNewsGeo(
  raw: NewsGeoRaw | null | undefined,
): RiskPoint[] {
  if (!raw) return [];
  // P2 修复（news-geo-contract-drift）：兼容 articles 结构（新闻文章地理点）
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
    if (seen.has(norm.id)) continue;
    seen.add(norm.id);

    const value = norm.intensity;
    const status: PointStatus = resolvePointStatus(undefined, value);
    const category: 'news' | 'conflict' = norm.event_type === 'conflict' ? 'conflict' : 'news';

    // 08-16 v2：弹框第一行 label = "发生了什么"
    // 优先 = URL slug 还原的伪标题（如 "Federal Judge Threatens Doj..."）；
    // fallback = 中文事件类型（"政治类报道" / "冲突事件" / "抗议活动"）。
    const slugTitle = urlSlugToTitle(norm.source_url);
    const typeZh = EVENT_TYPE_ZH[norm.event_type] ?? norm.event_type;
    const label = slugTitle ?? `${typeZh} 类报道`;

    // 国家码中文
    const countryZh = COUNTRY_ZH[norm.country] ?? norm.country;

    out.push({
      id: `newsgeo:${norm.id}`,
      label,
      lat: norm.lat,
      lng: norm.lng,
      value,
      uncertainty: null,
      uncertaintyEstimated: false,
      // group 内含事件类别 + 国家，便于点击 / 悬停时一眼看懂
      group: `${typeZh} · ${countryZh}`,
      status,
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
      // v1.10.5：来源 URL 透传（已 sanitizeUrl 消毒，弹框「查看新闻原文」用）
      sourceUrl: norm.source_url,
    });
  }
  return out;
}