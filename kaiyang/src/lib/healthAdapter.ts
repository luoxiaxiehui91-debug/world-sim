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
 *
 * 08-16 v2（用户反馈"弹框直接放标题 + 尽量中文"）：
 *  - 事件 title 字段（GDELT DOC 2.0 标题回填，NAS IP 限流恢复后自动生效）→
 *    label 直接用原标题；无 title 时用中文疾病名（"霍乱疫情"）——不用点开
 *    链接就知道发生了什么；
 *  - 疾病关键词中英映射（DISEASE_ZH）：outbreak→疫情爆发 / cholera→霍乱 等。
 */

/** 卫生关键词 → 中文（弹框标题/分组显示，尽量中文） */
export const DISEASE_ZH: Record<string, string> = {
  outbreak: '疫情爆发',
  epidemic: '流行病',
  pandemic: '大流行',
  cholera: '霍乱',
  ebola: '埃博拉',
  mpox: '猴痘',
  monkeypox: '猴痘',
  zika: '寨卡',
  'bird flu': '禽流感',
  h5n1: '禽流感',
  marburg: '马尔堡',
  lassa: '拉沙热',
  dengue: '登革热',
  polio: '脊髓灰质炎',
  measles: '麻疹',
  cyclosporiasis: '环孢子虫病',
  'whooping cough': '百日咳',
  pertussis: '百日咳',
};

function kwZh(keywords: string[] | undefined): string {
  const list = keywords ?? [];
  if (list.length === 0) return '';
  return list.map((k) => DISEASE_ZH[k] ?? k).join('/');
}

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
    const count = e.count ?? 1; // v1.1 聚合点：同城事件数（fetch_health_geo.py 落盘聚合）
    const kw = (e.keywords ?? []).join('/');
    const zh = kwZh(e.keywords);
    const media = (e.source_media ?? '').trim();
    const when = e.date ? `${e.date.slice(0, 4)}-${e.date.slice(4, 6)}-${e.date.slice(6, 8)} ${e.date.slice(8, 10)}:${e.date.slice(10, 12)} UTC` : '';
    // 08-16 v2：title（DOC API 回填）优先 → 弹框标题行直接是新闻标题；
    // 无 title 时中文疾病名（"霍乱疫情"），不用点开就知道发生了什么。
    const title = (e.title ?? '').trim();
    const label = title
      ? title
      : zh
        ? `卫生事件 · ${zh}${kw && kw !== zh ? `（${kw}）` : ''}`
        : '卫生事件';
    points.push({
      id: `health:${i}:${(e.doc ?? 'x').slice(-40)}`,
      label,
      lat: e.lat,
      lng: e.lng,
      value: null, // health 非风险语义：不显示误导数值
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `卫生 · ${zh || e.loc_name || '未知'}`,
      status: 'ok',
      color: categoryColor('health', 'ok'),
      severity: '卫生', // 中性标签
      weight: count > 1 ? Math.min(1.0, 0.5 + Math.log2(count) * 0.1) : 0.5, // v1.1 聚合点按 count 微调
      aggCount: count, // v1.1：>1 = 聚合点，FlatMapPanel 渲染计数徽标
      category: 'health',
      shape: categoryShape('health'),
      // 08-16：sourceUrl = 具体新闻原文（GKG DocumentIdentifier）——EventPopup
      // 点击点显示"查看新闻原文"链接；note 关联来源媒体（GKG 无标题列，媒体域名
      // 是"新闻关联"的最佳可用信号；标注来源可信度：媒体提及非官方确认）。
      sourceUrl: e.doc,
      note: [
        count > 1 ? `共 ${count} 起卫生事件（同地点聚合）` : '',
        kw ? `疫情类型 ${zh}${zh && zh !== kw ? `（${kw}）` : ''}` : '',
        media ? `${media} 报道` : '',
        e.loc_name ?? '',
        when,
        e.doc ? `原文 ${e.doc}` : '',
      ].filter(Boolean).join(' · '),
    });
  }
  return points;
}
