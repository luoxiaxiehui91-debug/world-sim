import { categoryColor, categoryShape, type PointStatus } from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { SdrSummaryRaw } from '@/types/contracts';

/**
 * sdr_summary.json → RiskPoint[]（开阳 sdr 软件无线电图层，08-14 接入）。
 *
 * 数据源：fetch_kiwisdr.py（KiwiSDR 目录，日更，rx.skywavelinux.com/kiwisdr_com.js）。
 * receivers：851 个全球接收器（含 lat/lon/name/loc/status/users）。
 *
 * ⚠ 语义边界（08-14，air 教训复用）：sdr 是「接收器覆盖」可视化，**不是风险评分**。
 *  - value 恒为 null（不显示误导数值）；
 *  - status==='active' → ok（sdr 色）；非 active → missing（灰，仍显示位置）；
 *  - weight 统一 0.5（接收器无大小语义）；
 *  - severity 固定中性标签 'SDR'；
 *  - hover/弹框展示名称、位置、用户数、最近上线。
 */
export function adaptSdr(raw: SdrSummaryRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.receivers) || raw.receivers.length === 0) {
    return [];
  }
  const points: RiskPoint[] = [];
  for (const r of raw.receivers) {
    // 坐标越界兜底（后端已校验，双保险）
    if (
      typeof r.lat !== 'number' || typeof r.lon !== 'number' ||
      r.lat < -90 || r.lat > 90 || r.lon < -180 || r.lon > 180
    ) {
      continue;
    }
    const status: PointStatus = r.status === 'active' ? 'ok' : 'missing';
    points.push({
      id: `sdr:${r.id}`,
      label: r.name ?? `SDR ${r.id}`,
      lat: r.lat,
      lng: r.lon,
      value: null, // sdr 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `SDR · ${r.loc ?? '未知'}`,
      status,
      color: categoryColor('sdr', status),
      severity: 'SDR', // 中性标签，替代 低/中/高
      weight: 0.5, // 统一大小（接收器无大小语义）
      category: 'sdr',
      shape: categoryShape('sdr'),
      rawMetric: r.grid ? `网格 ${r.grid}` : undefined,
      note: `${r.loc ?? '未知位置'} · ${r.users !== undefined && r.users !== '' ? `${r.users} 用户` : '—'}${r.updated ? ` · 更新 ${r.updated}` : ''}`,
    });
  }
  return points;
}
