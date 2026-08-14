import { GRV_ARCS, getDimDef } from '@/config/grvDimensions';
import {
  categoryColor,
  categoryLabel,
  categoryShape,
  resolvePointStatus,
} from '@/config/layerCategories';
import type { LayerCategory, PointShape, PointStatus } from '@/config/layerCategories';
import { PALETTE, severityColor, severityLabel, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvDimension, GrvEvent } from '@/types/contracts';

/**
 * 3D 地球与 2D 平面地图共用的数据构建层。
 * 目的：两种视图使用完全相同的点位/弧线/配色/提示逻辑，避免重复实现导致观感不一致。
 * 关键规则：只有 kind='geographic' 且坐标齐全的维度才会出现在地图上；
 * composite（全球综合 / 全球南方）不投影，改由 GRV 面板与状态条展示。
 *
 * 视觉双轴（决策 D1）在本层**预计算**成扁平字段，渲染器只做直读：
 * - 色相 = `category` → `color`（缺失态覆盖为灰，决策 C2-A）
 * - 强度 = `weight`   → 尺寸 / 光环 / 脉冲速率
 * 渲染器不得反查类别定义（K6），这是「3D 与 2D 观感永远一致」的既有保证机制。
 */

export interface RiskPoint {
  /** 全局唯一点位 id，格式 `${category}:${原始id}`（K2 命名空间前缀，多图层合并时防撞车） */
  id: string;
  label: string;
  /** 纬度，小数 4 位约定（K4） */
  lat: number;
  /** 经度，小数 4 位约定（K4） */
  lng: number;
  /** 严重度数值，统一 0~100 量纲（K3）；null = 数据缺失 */
  value: number | null;
  uncertainty: number | null;
  uncertaintyEstimated: boolean;
  group: string;
  /** 数据状态；'missing' 是元状态，会覆盖类别色为灰（C2-A） */
  status: PointStatus;
  /** 预计算色值：categoryColor(category, status)。渲染器只读此字段 */
  color: string;
  // severity = 展示标签，勿用于着色数学；weight = 唯一数值强度
  /** 严重度**等级标签**（'低'|'中'|'高'|'缺失'）。⚠ 纯展示，禁止参与着色 / 尺寸数学 */
  severity: string;
  // severity = 展示标签，勿用于着色数学；weight = 唯一数值强度
  /** 归一化强度 0~1（缺失按 0）。★ 唯一数值强度驱动源：尺寸 / 环半径 / 高度 / 脉冲速率只认它 */
  weight: number;
  /** 图层类别（D1 色相载体）。缺省视为 'geo'，保证旧数据不炸 */
  category: LayerCategory;
  /** 方向（度，0-360 顺时针从北）。可选：仅支持方向的图层（如 air 航班航向）填充，
   *  2D 平面地图渲染为旋转小箭头；3D 球标签面向相机不渲染箭头（方向会被相机旋转干扰）。 */
  direction?: number;
  /** 符号形状；缺省取 categoryDef(category).shape */
  shape?: PointShape;
  /** 类别内的原生度量原文（如 "0.12 µSv/h" / "37 人死亡"），仅供 tooltip 展示，不参与计算 */
  rawMetric?: string;
  /** 是否为事件触发式告警柱（气候 / 灾害事件），视觉与文案区别于常驻地缘柱 */
  isEvent?: boolean;
  /** 事件补充说明（仅 isEvent 点可能存在） */
  note?: string;
  /** 事件来源新闻 URL（v1.10.5：已消毒，供弹框「查看新闻原文」跳转） */
  sourceUrl?: string;
  /** 同地点聚合计数（v1.10.8：>1 = 聚合点，渲染计数徽标；未设 = 单事件点） */
  aggCount?: number;
}

export interface RiskArc {
  id: string;
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  fromLabel: string;
  toLabel: string;
  startColor: string;
  endColor: string;
  /** 两端较高的风险值（缺失按 0） */
  intensity: number;
}

/**
 * 高严重度阈值（用于常驻标签 / 光环）。
 * v1.10.7：55 → 70（视觉降噪：默认 news_geo 613 点中 ≥55 的 281 个、≥70 的约 110 个，
 * 阈值上调 60% 减少常驻标签与脉冲动画的密度；与 SEVERITY_THRESHOLD.high=66 语义对齐）。
 */
export const HIGHLIGHT_THRESHOLD = 70;

/**
 * 由维度列表构建地图点位（自动过滤 composite 与缺坐标项）。
 * 类别恒为 'geo'；id 带 `geo:` 命名空间前缀（K2）。
 * 入参为 nullish 时返回空数组（K5 降级红线：任何路径不抛异常）。
 */
export function buildRiskPoints(dims: GrvDimension[] | null | undefined): RiskPoint[] {
  if (!dims || dims.length === 0) return [];
  const out: RiskPoint[] = [];
  for (const d of dims) {
    if (!d) continue;
    if (d.kind !== 'geographic') continue;
    // renderBar=false 的维度（气候/自然灾害）不画常驻柱，改由事件触发式告警柱表达
    if (getDimDef(d.id)?.renderBar === false) continue;
    if (d.lat === null || d.lng === null) continue;
    // 坐标必须是有限数（K4）：配置/上游异常时跳过该点，而非画到 (0,0)
    if (!Number.isFinite(d.lat) || !Number.isFinite(d.lng)) continue;
    const v = d.value;
    // 元状态判定（C2-A）：上游 missing 或数值非有限，一律按缺失处理
    const status = resolvePointStatus(d.status, v);
    out.push({
      id: `geo:${d.id}`,
      label: d.label,
      lat: d.lat,
      lng: d.lng,
      value: v,
      uncertainty: d.uncertainty,
      uncertaintyEstimated: d.uncertaintyEstimated,
      group: d.group,
      status,
      color: categoryColor('geo', status),
      severity: severityLabel(v),
      weight: v === null ? 0 : Math.min(1, Math.max(0, v / 100)),
      category: 'geo',
      shape: categoryShape('geo'),
    });
  }
  return out;
}

/**
 * 由事件列表构建事件触发式告警柱（气候 / 自然灾害）。
 * 入参为空 / undefined 时返回空数组（优雅降级：无事件则地图上什么都不画）。
 */
export function buildEventBars(events?: GrvEvent[]): RiskPoint[] {
  if (!events || events.length === 0) return [];
  const out: RiskPoint[] = [];
  for (const e of events) {
    // 坐标必须是有限数：Number.isFinite 不做类型强制，undefined / null / NaN / Infinity / 字符串均返回 false
    if (!Number.isFinite(e?.lat) || !Number.isFinite(e?.lng)) continue;
    // value 同样必须是有限数：否则 weight=NaN 且 severity 被错判为「低」，
    // 会渲染出高度异常/不可见却显示「低」等级的误导性告警柱，与坐标无效跳过保持同一语义
    if (!Number.isFinite(e?.value)) continue;
    out.push({
      id: `event:${e.id}`,
      label: e.label,
      lat: e.lat,
      lng: e.lng,
      value: e.value,
      uncertainty: null,
      uncertaintyEstimated: false,
      group: e.type === 'disaster' ? '自然灾害' : '气候',
      status: 'ok',
      // 已在上方通过 Number.isFinite 双校验，此处 status 恒为 'ok'
      color: categoryColor('event', 'ok'),
      severity: severityLabel(e.value),
      weight: Math.min(1, Math.max(0, e.value / 100)),
      category: 'event',
      shape: categoryShape('event'),
      isEvent: true,
      note: e.note,
    });
  }
  return out;
}

/** 由维度列表构建地缘联动弧线（两端必须都是有坐标的地理维度）。 */
export function buildRiskArcs(dims: GrvDimension[]): RiskArc[] {
  const byId = new Map<string, GrvDimension>();
  for (const d of dims) byId.set(d.id, d);

  const arcs: RiskArc[] = [];
  for (const [a, b] of GRV_ARCS) {
    const da = byId.get(a);
    const db = byId.get(b);
    if (!da || !db) continue;
    if (da.kind !== 'geographic' || db.kind !== 'geographic') continue;
    if (da.lat === null || da.lng === null || db.lat === null || db.lng === null) continue;
    // 定义层坐标兜底校验（若配置被改动导致坐标缺失，则跳过而非画到 0,0）
    if (!getDimDef(a) || !getDimDef(b)) continue;

    const va = da.value ?? 0;
    const vb = db.value ?? 0;
    arcs.push({
      id: `${a}__${b}`,
      startLat: da.lat,
      startLng: da.lng,
      endLat: db.lat,
      endLng: db.lng,
      fromLabel: da.label,
      toLabel: db.label,
      startColor: severityColor(da.value),
      endColor: severityColor(db.value),
      intensity: Math.max(va, vb),
    });
  }
  return arcs;
}

/** HTML 实体转义（XSS 防线：所有进入 tooltip HTML 的外部文本统一在此转义）。
 * 渲染层唯一转义点——避免与适配层再转义造成双重转义。 */
function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (ch) =>
      ch === '&'
        ? '&amp;'
        : ch === '<'
          ? '&lt;'
          : ch === '>'
            ? '&gt;'
            : ch === '"'
              ? '&quot;'
              : '&#39;',
  );
}

/** 统一的点位提示气泡 HTML（globe.gl pointLabel 与平面地图 tooltip 共用；事件点走告警文案）。 */
export function pointTooltipHtml(p: RiskPoint): string {
  const val = p.value === null ? '数据缺失' : fmtNum(p.value);
  const label = escapeHtml(p.label);
  const group = escapeHtml(p.group);
  const rawMetric = escapeHtml(p.rawMetric);
  const note = escapeHtml(p.note);
  const shell =
    `<div style="font:12px/1.5 ui-sans-serif,system-ui,'PingFang SC',sans-serif;` +
    `background:rgba(6,11,22,0.92);border:1px solid ${withAlpha(p.color, 0.55)};` +
    `box-shadow:0 0 18px ${withAlpha(p.color, 0.28)};color:${PALETTE.text};` +
    `padding:6px 10px;border-radius:8px;white-space:nowrap;">`;

  // 类别行：告诉用户「这个色相代表哪一层」，是 D1 双轴的可读性兜底
  const catLine = `<span style="opacity:.6">图层类别 ${escapeHtml(categoryLabel(p.category))}</span>`;
  // 原生度量行：仅在构建函数显式提供时出现（如核读数 "0.12 µSv/h"），不参与任何计算
  const rawLine = rawMetric ? `<br/><span style="opacity:.6">原始读数 ${rawMetric}</span>` : '';

  if (p.isEvent) {
    const noteLine = note ? `<br/><span style="opacity:.6">详情：${note}</span>` : '';
    return (
      shell +
      `<b style="color:${p.color}">⚠ ${label}</b>` +
      `<span style="opacity:.5;margin-left:6px">事件类型：${group}</span><br/>` +
      `事件严重度 <b>${val}</b> · 等级 ${escapeHtml(p.severity)}<br/>` +
      catLine +
      rawLine +
      noteLine +
      `</div>`
    );
  }

  const unc =
    p.value === null || p.uncertainty === null
      ? '未知'
      : `±${fmtNum(p.uncertainty)}${p.uncertaintyEstimated ? '（估算）' : ''}`;
  return (
    shell +
    `<b style="color:${p.color}">${label}</b>` +
    `<span style="opacity:.5;margin-left:6px">${group}</span><br/>` +
    `风险值 <b>${val}</b> · 等级 ${escapeHtml(p.severity)}<br/>` +
    catLine +
    rawLine +
    `<br/><span style="opacity:.6">不确定区间 ${escapeHtml(unc)}</span>` +
    `</div>`
  );
}

/** 弧线提示文案。 */
export function arcTooltipHtml(a: RiskArc): string {
  return (
    `<div style="font:12px/1.5 ui-sans-serif,system-ui,sans-serif;` +
    `background:rgba(6,11,22,0.9);border:1px solid ${withAlpha(PALETTE.cyan, 0.4)};` +
    `color:${PALETTE.text};padding:4px 8px;border-radius:6px;white-space:nowrap;">` +
    `${a.fromLabel} ↔ ${a.toLabel} · 联动强度 ${fmtNum(a.intensity, 0)}</div>`
  );
}
