import {
  categoryColor,
  categoryShape,
  resolvePointStatus,
  type PointStatus,
} from '@/config/layerCategories';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import {
  adaptNewsGeo,
  normalizeEvent,
  urlSlugToTitle,
  EVENT_TYPE_ZH,
  COUNTRY_ZH,
} from '@/lib/newsGeoAdapter';
import type { NewsGeoEvent, NewsGeoRaw } from '@/types/contracts';

/**
 * v1.10.8 同地点聚合：GDELT 对同一地点使用城市中心坐标（实测同城事件坐标完全一致），
 * 但 location_name 存在拼写变体（Beijing/Peking、Washington/White House/Lincoln Memorial），
 * 导致同城新闻被拆成多个点、地图上一城多点多条。
 *
 * 聚合主键 = 坐标格（0.1° ≈ 11km，城市级）：
 * - 同格事件合并为一个聚合点（Peking/Beijing 同坐标 → 自动合并；深圳/香港不同格 → 不误并）
 * - 代表事件 = mention_count 最高（保留主要报道的地点名 / 强度 / 日期）
 * - 聚合点强度 = 组内 max（最严重事件驱动尺寸）；提及数求和
 * - aggCount > 1 为聚合点（渲染计数徽标）；count = 1 保持普通点外观
 * - childrenByPointId 供弹框展示同地点全部事件（含自身）
 */
export function aggregateNewsGeo(
  raw: NewsGeoRaw | null | undefined,
): { points: RiskPoint[]; childrenByPointId: Map<string, NewsGeoEvent[]> } {
  const childrenByPointId = new Map<string, NewsGeoEvent[]>();
  if (!raw) return { points: [], childrenByPointId };

  // articles 结构（旧 NER 链，已停调度）不聚合：原样直出，兼容 K5（不白屏）
  const rawArticles = Array.isArray(
    (raw as unknown as { articles?: unknown[] }).articles,
  )
    ? (raw as unknown as { articles: unknown[] }).articles
    : [];
  if (rawArticles.length > 0) {
    return { points: adaptNewsGeo(raw), childrenByPointId };
  }

  const rawEvents = Array.isArray(raw.events) ? raw.events : [];
  if (rawEvents.length === 0) return { points: [], childrenByPointId };

  // 按坐标格分组（0.1° 网格；城市中心坐标级，容纳拼写变体）
  const groups = new Map<string, GeoGroup>();
  const seen = new Set<string>();
  for (const e of rawEvents) {
    const norm = normalizeEvent(e);
    if (!norm) continue;
    if (seen.has(norm.id)) continue; // id 全局唯一（K2），脏数据防撞车
    seen.add(norm.id);
    const key = `${Math.round(norm.lat * 10)}|${Math.round(norm.lng * 10)}`;
    const g = groups.get(key);
    if (!g) {
      groups.set(key, {
        rep: norm,
        count: 1,
        sumMention: norm.mention_count ?? 0,
        children: [norm],
      });
    } else {
      g.count += 1;
      g.sumMention += norm.mention_count ?? 0;
      g.children.push(norm);
      if ((norm.mention_count ?? 0) > (g.rep.mention_count ?? 0)) g.rep = norm;
    }
  }

  const points: RiskPoint[] = [];
  for (const g of groups.values()) {
    const point = buildPointFromEvent(g.rep);
    point.aggCount = g.count;
    if (g.count > 1) {
      point.rawMetric = `提及 ${g.sumMention} 次 · ${g.count} 条事件`;
      // 聚合点强度 = 组内最严重事件（地图一眼看出最危险地点），而非代表事件本身
      const maxIntensity = Math.max(g.rep.intensity, ...g.children.map((c) => c.intensity));
      if (maxIntensity !== g.rep.intensity) {
        point.value = maxIntensity;
        point.severity = severityLabel(maxIntensity);
        point.weight = Math.min(1, Math.max(0, maxIntensity / 100));
      }
    }
    // 单事件也注册：弹框点击显示自身（普通点不标徽标但可弹详情）
    childrenByPointId.set(point.id, g.children);
    points.push(point);
  }
  return { points, childrenByPointId };
}

interface GeoGroup {
  /** 代表事件（mention_count 最高） */
  rep: NewsGeoEvent;
  count: number;
  sumMention: number;
  children: NewsGeoEvent[];
}

/** 单事件 → RiskPoint（与 adaptNewsGeo 循环体同构；独立实现避免跨模块重构回归）。
 * 08-16 v1.11.19 同步：label = URL slug 还原英文标题 → 中文事件类型兜底；
 * group 中文（类型 · 国家）。此前只改了 adaptNewsGeo，聚合路径（WorldPanel 实际
 * 消费入口）buildPointFromEvent 仍是 location_name 当 label —— 用户实测弹框
 * 只有地点名，没有标题（v1.11.19 修漏的路径）。 */
function buildPointFromEvent(norm: NewsGeoEvent): RiskPoint {
  const value = norm.intensity;
  const status: PointStatus = resolvePointStatus(undefined, value);
  const category: 'news' | 'conflict' =
    norm.event_type === 'conflict' ? 'conflict' : 'news';
  const typeZh = EVENT_TYPE_ZH[norm.event_type] ?? norm.event_type;
  const countryZh = COUNTRY_ZH[norm.country] ?? norm.country;
  const slugTitle = urlSlugToTitle(norm.source_url);
  return {
    id: `newsgeo:${norm.id}`,
    label: slugTitle ?? `${typeZh} 类报道`,
    lat: norm.lat,
    lng: norm.lng,
    value,
    uncertainty: null,
    uncertaintyEstimated: false,
    group: `${typeZh} · ${countryZh}`,
    status,
    color: categoryColor(category, status),
    severity: severityLabel(value),
    weight: value === null ? 0 : Math.min(1, Math.max(0, value / 100)),
    category,
    shape: categoryShape(category),
    rawMetric:
      norm.mention_count !== undefined
        ? `提及 ${norm.mention_count} 次${norm.theme ? ` · ${norm.theme}` : ''}`
        : norm.theme ?? undefined,
    note: norm.event_date,
    sourceUrl: norm.source_url,
  };
}
