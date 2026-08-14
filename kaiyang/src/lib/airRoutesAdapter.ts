import { CATEGORY_PALETTE } from '@/config/theme';
import type { RiskArc } from '@/lib/mapData';
import type { AirRoutesRaw } from '@/types/contracts';

/**
 * airroutes.json → RiskArc[]（开阳 air 全球航线网图层，08-14 接入）。
 *
 * 数据源：fetch_airroutes.py（OpenFlights airports.dat + routes.dat，CC BY-SA 4.0，~2014）。
 * routes 为 top 500 主要航线（按 routes.dat 机场对频次降序，flights = 运营航司数）。
 *
 * ⚠ 语义边界（08-14）：航线网是「全球空中走廊结构」可视化，**不是风险评分**。
 *  - startColor/endColor 固定 air 类别色（翡翠绿），不套风险色轴；
 *  - intensity = 航线繁忙度归一化（flights 线性映射 20-100），仅驱动弧的粗细/动画
 *    （热门干线粗、冷门支线细），不表达任何风险；
 *  - air 图层没有点位，是纯 RiskArc 弧层（复用既有 2D greatCircleArc / 3D arcsData）。
 *
 * ⚠ 覆盖优势（08-14 用户问「非洲/中国上空基本空」）：航线网是计划结构数据，
 *  全球主要航线完整（含非洲/中国上空国际干线），无 OpenSky ADS-B 接收器覆盖盲区。
 */
export function adaptAirRoutes(raw: AirRoutesRaw | null): RiskArc[] {
  if (!raw || !Array.isArray(raw.routes) || raw.routes.length === 0) {
    return [];
  }
  const routes = raw.routes;
  // 繁忙度归一化基准：top1 flights 作为 100% 参照（数据已按 flights 降序）
  const maxFlights = Math.max(1, routes[0]?.flights ?? 1);
  const color = CATEGORY_PALETTE.air;
  const arcs: RiskArc[] = [];
  for (const r of routes) {
    // 坐标越界兜底（后端已校验，双保险）
    if (
      !Number.isFinite(r.from_lat) || !Number.isFinite(r.from_lng) ||
      !Number.isFinite(r.to_lat) || !Number.isFinite(r.to_lng) ||
      r.from_lat < -90 || r.from_lat > 90 ||
      r.from_lng < -180 || r.from_lng > 180 ||
      r.to_lat < -90 || r.to_lat > 90 ||
      r.to_lng < -180 || r.to_lng > 180
    ) {
      continue;
    }
    // 繁忙度 → 强度（20-100 线性）：热门干线粗、冷门支线细；非风险语义
    const intensity = Math.round(20 + 80 * (r.flights / maxFlights));
    arcs.push({
      id: `airroute:${r.from}__${r.to}`,
      startLat: r.from_lat,
      startLng: r.from_lng,
      endLat: r.to_lat,
      endLng: r.to_lng,
      fromLabel: r.from,
      toLabel: r.to,
      startColor: color,
      endColor: color,
      intensity,
    });
  }
  return arcs;
}
