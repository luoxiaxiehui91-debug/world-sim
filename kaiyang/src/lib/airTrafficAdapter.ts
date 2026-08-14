import {
  categoryColor,
  type PointStatus,
} from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { AirTrafficRaw } from '@/types/contracts';

/**
 * airtraffic_opensky.json → RiskPoint[]（开阳 aircraft 实时航班子图层，08-14 接入）。
 *
 * 数据源：fetch_airtraffic_opensky.py（OpenSky /api/states/all，I30 实时快照）。
 * coordinates 为**全量**在飞航班（08-14 起不再采样；OpenSky 按请求计费不按条数，
 * 当前约 6182 点，UNCAPPED_LAYERS 豁免截断，全量渲染）。
 *
 * ⚠ 语义边界（08-14 修正，用户指出「风险值是什么」）：
 *  - aircraft 图层是「空域活动可视化」，**不是风险评分**。飞行高度 ≠ 风险等级。
 *  - value 恒为 null（不参与风险值/等级体系，点位不显示误导数字）；
 *  - weight 固定 0.5（用户拍板：统一大小，区分大小没意义）；
 *  - severity 固定中性标签 '空域'（弹框不显示 低/中/高）；
 *  - shape = 'arrow'（08-14 用户拍板：2D 只画航向箭头、不画圆点圈）；
 *  - hover/弹框展示航班号、高度、速度、起飞机场国。
 *
 * ⚠ 覆盖盲区（08-14 用户问「非洲/中国上空基本空」）：
 *  - OpenSky 是众包 ADS-B 接收器网络，非洲/中国/俄罗斯内陆接收器稀疏，
 *    那些区域航班收不到信号 → 不代表真实空情。
 *  - air 图层已改为静态全球航线网（airroutes.json，无盲区）；本适配器
 *    仅供 aircraft 子图层（默认关），打开时 desc 已标注盲区。
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
    const label = c.callsign ?? `航班${i + 1}`;
    // 航向（0-360 顺时针从北）→ direction（2D 平面地图渲染旋转箭头）
    const track =
      typeof c.track === 'number' && Number.isFinite(c.track)
        ? ((c.track % 360) + 360) % 360
        : undefined;
    points.push({
      id: `aircraft:${i}:${label}-${c.lat.toFixed(4)}-${c.lng.toFixed(4)}`,
      label,
      lat: c.lat,
      lng: c.lng,
      value: null, // aircraft 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `空域 · ${c.origin ?? '未知'}`,
      status,
      color: categoryColor('aircraft', status),
      severity: '空域', // 中性标签，替代 低/中/高
      weight: 0.5, // 统一大小（用户拍板：不区分大小）
      category: 'aircraft',
      shape: 'arrow', // 08-14：2D 只画航向箭头不画圆点圈（用户拍板）
      direction: track, // 2D 地图画航向箭头
      rawMetric: c.origin ? `起飞机场国 ${c.origin}` : undefined,
      note:
        `高度 ${c.alt_m !== null && c.alt_m !== undefined ? `${Math.round(c.alt_m)}m` : '—'} · ` +
        `速度 ${c.vel_ms !== null && c.vel_ms !== undefined ? `${Math.round(c.vel_ms)}m/s` : '—'}` +
        (track !== undefined ? ` · 航向 ${Math.round(track)}°` : ''),
      sourceUrl: undefined,
    });
  }
  return points;
}
