import { categoryColor, categoryShape } from '@/config/layerCategories';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import type { FirmsRaw } from '@/types/contracts';

/**
 * firms_fire.json → RiskPoint[]（开阳 thermal 热异常图层，08-14 接入）。
 *
 * 数据源：fetch_firms.py（NASA FIRMS VIIRS NRT，日档 0908，直连）。
 * hotspots = **1° 网格后端预聚合**（海量火点聚合为网格点：格心 + 火点计数 +
 * 最强 FRP + 高置信数；DECISION_MATRIX D2「热点图层建议后端预聚合」）。
 *
 * ⚠ 语义边界（08-14）：thermal 是「火点活跃度」可视化——火点密度是热异常
 * 强度的直接度量（区别于 air 的「高度≠风险」）。
 *  - value = 网格火点计数归一化（0-100，相对全局最密网格），severity 按常规档位；
 *  - aggCount = 网格火点数 → 渲染中心计数徽标（复用聚合点机制）；
 *  - weight = value/100（火点越密点越大）；
 *  - note 展示火点数 / 最强 FRP / 高置信数。
 */
export function adaptThermal(raw: FirmsRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.hotspots) || raw.hotspots.length === 0) {
    return [];
  }
  const hotspots = raw.hotspots;
  // 归一化基准：最密网格的 count 作为 100%（数据已按 count 降序）
  const maxCount = Math.max(1, hotspots[0]?.count ?? 1);
  const points: RiskPoint[] = [];
  for (const h of hotspots) {
    // 坐标越界兜底（后端已校验，双保险）
    if (
      !Number.isFinite(h.lat) || !Number.isFinite(h.lng) ||
      h.lat < -90 || h.lat > 90 || h.lng < -180 || h.lng > 180
    ) {
      continue;
    }
    const value = Math.min(100, Math.round((h.count / maxCount) * 100));
    points.push({
      id: `thermal:${h.lat.toFixed(1)},${h.lng.toFixed(1)}`,
      label: `热异常 ${h.count} 火点`,
      lat: h.lat,
      lng: h.lng,
      value,
      uncertainty: null,
      uncertaintyEstimated: false,
      group: '热异常',
      status: 'ok',
      color: categoryColor('thermal', 'ok'),
      severity: severityLabel(value),
      weight: value / 100,
      category: 'thermal',
      shape: categoryShape('thermal'),
      aggCount: h.count, // 网格火点数 → 中心计数徽标
      note:
        `${h.count} 个火点 · 最强 FRP ${h.frp_max !== undefined && Number.isFinite(h.frp_max) ? `${Math.round(h.frp_max)} MW` : '—'}` +
        (h.high_conf ? ` · 高置信 ${h.high_conf}` : ''),
    });
  }
  return points;
}
