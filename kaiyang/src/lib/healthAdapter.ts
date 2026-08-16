import { categoryColor, categoryShape } from '@/config/layerCategories';
import type { RiskPoint } from '@/lib/mapData';
import type { HealthGeoRaw } from '@/types/contracts';

/**
 * health_geo.json → RiskPoint[]（开阳 health 卫生监视图层，08-15 接入）。
 *
 * 数据源：fetch_health_geo.py（GDELT 2.0 GKG 卫生关键词过滤 + V1Locations 坐标，
 * I60 增量，保留 72h 窗口）。
 *
 * ⚠ 语义边界（08-15，air/thermal/space 教训复用）：health 是「卫生事件活动」
 *   可视化，**不是风险评分**——新闻提及 ≠ 实际疫情等级（pandemic loan fraud 类
 *   噪声实测存在，已用关键词排除但仍可能有少量误报）。
 *  - value 恒为 null（不显示误导数值）；
 *  - weight 统一 0.5（不区分大小）；
 *  - severity 固定中性标签 '卫生'；
 *  - note 展示关键词（疫情类型）/ 报道地点 / 时间（hover 看详情）。
 */
export function adaptHealth(raw: HealthGeoRaw | null): RiskPoint[] {
  if (!raw || !Array.isArray(raw.events) || raw.events.length === 0) {
    return [];
  }
  const points: RiskPoint[] = [];
  for (let i = 0; i < raw.events.length; i++) {
    const e = raw.events[i];
    // 坐标越界兜底（后端已校验，双保险）
    if (
      !Number.isFinite(e.lat) || !Number.isFinite(e.lng) ||
      e.lat < -90 || e.lat > 90 || e.lng < -180 || e.lng > 180
    ) {
      continue;
    }
    const kw = (e.keywords ?? []).join('/');
    const media = (e.source_media ?? '').trim();
    const when = e.date ? `${e.date.slice(0, 4)}-${e.date.slice(4, 6)}-${e.date.slice(6, 8)} ${e.date.slice(8, 10)}:${e.date.slice(10, 12)} UTC` : '';
    points.push({
      id: `health:${i}:${(e.doc ?? 'x').slice(-40)}`,
      label: kw ? `卫生事件 · ${kw}` : '卫生事件',
      lat: e.lat,
      lng: e.lng,
      value: null, // health 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `卫生 · ${e.loc_name ?? '未知'}`,
      status: 'ok',
      color: categoryColor('health', 'ok'),
      severity: '卫生', // 中性标签
      weight: 0.5, // 统一大小（事件无大小语义）
      category: 'health',
      shape: categoryShape('health'),
      // 08-16：note 关联新闻——来源媒体 + 报道链接（doc URL）。GKG 无标题列，
      // 媒体域名是"新闻关联"的最佳可用信号；标注来源可信度（媒体提及非官方确认）。
      note: [
        kw ? `类型 ${kw}` : '',
        media ? `${media} 报道` : '',
        e.loc_name ?? '',
        when,
        e.doc ? `原文 ${e.doc}` : '',
      ].filter(Boolean).join(' · '),
    });
  }
  return points;
}
