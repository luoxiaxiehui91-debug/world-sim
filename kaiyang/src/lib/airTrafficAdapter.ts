import {
  categoryColor,
  categoryShape,
  type PointStatus,
} from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { AirTrafficRaw } from '@/types/contracts';

/**
 * airtraffic_opensky.json → RiskPoint[]（开阳 air 空域活动图层，08-14 接入）。
 *
 * 数据源：fetch_airtraffic_opensky.py（OpenSky /api/states/all，I30 实时快照）。
 * coordinates 已由后端均匀采样 ≤500 个在飞航班（含 lat/lng/alt/vel/callsign/origin）。
 *
 * ⚠ 语义边界（08-14 修正，用户指出「风险值是什么」）：
 *  - air 图层是「空域活动可视化」，**不是风险评分**。飞行高度 ≠ 风险等级。
 *  - value 恒为 null（不参与风险值/等级体系，点位不显示误导数字）；
 *  - weight 用高度归一化仅驱动点尺寸（高飞的点略大，纯视觉）；
 *  - severity 固定中性标签 '空域'（弹框不显示 低/中/高）；
 *  - hover/弹框展示航班号、高度、速度、起飞机场国。
 */
export function adaptAirTraffic(raw: AirTrafficRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.coordinates) || raw.coordinates.length === 0) {
    return [];
  }
  const status: PointStatus = 'ok';
  const points: RiskPoint[] = [];

  for (let i = 0; i < raw.coordinates.length; i++) {
    const c = raw.coordinates[i];
    // 坐标越界兜底（后端已校验，双保险）
    if (
      typeof c.lat !== 'number' || typeof c.lng !== 'number' ||
      c.lat < -90 || c.lat > 90 || c.lng < -180 || c.lng > 180
    ) {
      continue;
    }
    const alt = typeof c.alt_m === 'number' ? c.alt_m : 0;
    // 高度归一化仅驱动点尺寸（纯视觉），不参与风险值体系
    const heightWeight = Math.min(1, Math.max(0, alt / 15000));
    const label = c.callsign ?? `航班${i + 1}`;
    points.push({
      id: `air:${i}:${label}-${c.lat.toFixed(4)}-${c.lng.toFixed(4)}`,
      label,
      lat: c.lat,
      lng: c.lng,
      value: null, // air 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `空域 · ${c.origin ?? '未知'}`,
      status,
      color: categoryColor('air', status),
      severity: '空域', // 中性标签，替代 低/中/高
      weight: heightWeight,
      category: 'air',
      shape: categoryShape('air'),
      rawMetric: c.origin ? `起飞机场国 ${c.origin}` : undefined,
      note:
        `高度 ${c.alt_m !== null && c.alt_m !== undefined ? `${Math.round(c.alt_m)}m` : '—'} · ` +
        `速度 ${c.vel_ms !== null && c.vel_ms !== undefined ? `${Math.round(c.vel_ms)}m/s` : '—'}`,
      sourceUrl: undefined,
    });
  }
  return points;
}
