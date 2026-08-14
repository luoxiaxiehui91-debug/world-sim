import { categoryColor, categoryShape } from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { FirmsRaw } from '@/types/contracts';

/**
 * firms_fire.json → RiskPoint[]（开阳 thermal 热异常图层，08-14 接入）。
 *
 * 数据源：fetch_firms.py（NASA FIRMS VIIRS NRT，日档 0908，直连）。
 * hotspots = **1° 网格后端预聚合**（海量火点聚合为网格点：格心 + 火点计数 +
 * 最强 FRP + 高置信数；DECISION_MATRIX D2「热点图层建议后端预聚合」）。
 *
 * ⚠ 语义边界（08-14 22:2x 用户追问「风险值怎么定的？非洲/西伯利亚相当高」，
 *   air 教训复用）：thermal 是「火点活跃度」可视化，**不是人类风险评分**。
 *   火点密度 ≠ 风险——西伯利亚无人区森林大火（单格 1800+ 火点）和非洲季节性
 *   烧荒（单格 1400+）火点极多，但对人口风险未必高；反之人口区山火点少但
 *   风险高。因此：
 *   - value 恒为 null（不显示误导的「风险值」数字）；
 *   - weight = count 归一化（0-1）仅驱动点大小/3D 高度（密度视觉）；
 *   - severity 固定中性标签 '火点活跃'（不显示 低/中/高）；
 *   - note 展示火点数 / 最强 FRP / 高置信数（hover 看真实密度）。
 *
 * ⚠ 等级筛选（08-14 19:5x 用户反馈「太占资源直接卡住了」）：
 *  - 4031 个网格点 × 4 SVG 元素/点（环+光晕+圆+徽标）≈ 1.6 万元素直接卡死；
 *  - 等级 = count 分档：极高 ≥500（59 格）/ 高 ≥100（340 格）/ 中 ≥50（527 格）；
 *  - **MIN_THERMAL_COUNT = 50**：count < 50 的零星火点格（占 87%：4031→527）不渲染，
 *    信息量低（零星单点燃烧），渲染量降至 ~2100 元素保持流畅。
 */
export const MIN_THERMAL_COUNT = 50;

export function adaptThermal(raw: FirmsRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.hotspots) || raw.hotspots.length === 0) {
    return [];
  }
  const hotspots = raw.hotspots;
  // 归一化基准：最密网格的 count 作为 weight=1（数据已按 count 降序）
  const maxCount = Math.max(1, hotspots[0]?.count ?? 1);
  const points: RiskPoint[] = [];
  for (const h of hotspots) {
    // 等级筛选：零星火点格（count < MIN_THERMAL_COUNT）不渲染
    if (!Number.isFinite(h.count) || h.count < MIN_THERMAL_COUNT) {
      continue;
    }
    // 坐标越界兜底（后端已校验，双保险）
    if (
      !Number.isFinite(h.lat) || !Number.isFinite(h.lng) ||
      h.lat < -90 || h.lat > 90 || h.lng < -180 || h.lng > 180
    ) {
      continue;
    }
    // weight = 火点密度归一化（0-1），仅驱动点大小/3D 高度；非风险语义
    const weight = Math.min(1, Math.max(0, h.count / maxCount));
    points.push({
      id: `thermal:${h.lat.toFixed(1)},${h.lng.toFixed(1)}`,
      label: `热异常 ${h.count} 火点`,
      lat: h.lat,
      lng: h.lng,
      value: null, // thermal 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: '热异常',
      status: 'ok',
      color: categoryColor('thermal', 'ok'),
      severity: '火点活跃', // 中性标签，替代 低/中/高
      weight,
      category: 'thermal',
      shape: categoryShape('thermal'),
      note:
        `${h.count} 个火点 · 最强 FRP ${h.frp_max !== undefined && Number.isFinite(h.frp_max) ? `${Math.round(h.frp_max)} MW` : '—'}` +
        (h.high_conf ? ` · 高置信 ${h.high_conf}` : ''),
    });
  }
  return points;
}
