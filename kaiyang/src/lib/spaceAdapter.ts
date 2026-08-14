import { categoryColor, categoryShape } from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { SpaceLaunchRaw } from '@/types/contracts';

/**
 * spacelaunch.json → RiskPoint[]（开阳 space 太空活动图层，08-14 接入）。
 *
 * 数据源：fetch_spacelaunch.py（Next Spaceflight Launch Library 2，日档 0705）。
 * launches：upcoming 未来计划 + previous 最近完成发射，含发射场 pad 坐标。
 *
 * ⚠ 语义边界（08-14，air/thermal 教训复用）：space 是「发射活动」可视化，
 *   **不是风险评分**——发射次数/国家不代表风险等级。
 *  - value 恒为 null（不显示误导数值）；
 *  - weight 统一 0.5（不区分大小）；
 *  - severity 固定中性标签 '太空'；
 *  - note 展示发射时间（net）/ 状态 / 火箭 / 服务商（hover 看详情）。
 */
export function adaptSpace(raw: SpaceLaunchRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.launches) || raw.launches.length === 0) {
    return [];
  }
  const points: RiskPoint[] = [];
  for (let i = 0; i < raw.launches.length; i++) {
    const l = raw.launches[i];
    // 坐标越界兜底（后端已校验，双保险）
    if (
      !Number.isFinite(l.lat) || !Number.isFinite(l.lng) ||
      l.lat < -90 || l.lat > 90 || l.lng < -180 || l.lng > 180
    ) {
      continue;
    }
    const upcoming = l.type === 'upcoming';
    const noteParts = [
      upcoming ? (l.net ? `计划 ${l.net}` : '计划 时间待定') : (l.net ? `已完成 ${l.net}` : '已完成'),
      l.status ? `状态 ${l.status}` : '',
      l.rocket ?? '',
    ].filter(Boolean);
    points.push({
      id: `space:${i}:${(l.name ?? 'x').slice(0, 30)}`,
      label: l.name ?? `发射 ${l.lat.toFixed(1)},${l.lng.toFixed(1)}`,
      lat: l.lat,
      lng: l.lng,
      value: null, // space 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `太空 · ${l.provider ?? '未知服务商'}`,
      status: 'ok',
      color: categoryColor('space', 'ok'),
      severity: '太空', // 中性标签
      weight: 0.5, // 统一大小（发射活动无大小语义）
      category: 'space',
      shape: categoryShape('space'),
      note: noteParts.join(' · '),
    });
  }
  return points;
}
