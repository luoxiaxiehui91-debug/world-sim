import {
  categoryColor,
  categoryShape,
  type PointStatus,
} from '@/config/layerCategories';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import type { AirTrafficRaw } from '@/types/contracts';

/**
 * airtraffic_opensky.json → RiskPoint[]（开阳 air 空域活动图层，08-14 接入）。
 *
 * 数据源：fetch_airtraffic_opensky.py（OpenSky /api/states/all，I30 实时快照）。
 * coordinates 已由后端均匀采样 ≤500 个在飞航班（含 lat/lng/alt/vel/callsign/origin）。
 *
 * 点位语义：
 *  - value = 高度归一化（0~15000m → 0~100），weight 驱动尺寸
 *  - hover 显示 高度/速度/起飞机场国（rawMetric/note）
 *  - 空数据 / feed 缺失 → []（K5 不白屏）
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
    const value = Math.round(Math.min(100, Math.max(0, (alt / 15000) * 100)));
    const label = c.callsign ?? `航班${i + 1}`;
    points.push({
      id: `air:${i}:${label}-${c.lat.toFixed(4)}-${c.lng.toFixed(4)}`,
      label,
      lat: c.lat,
      lng: c.lng,
      value,
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `空域 · ${c.origin ?? '未知'}`,
      status,
      color: categoryColor('air', status),
      severity: severityLabel(value),
      weight: value / 100,
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
