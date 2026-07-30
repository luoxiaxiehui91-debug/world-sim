import { GRV_ARCS, getDimDef } from '@/config/grvDimensions';
import { PALETTE, severityColor, severityLabel, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvDimension } from '@/types/contracts';

/**
 * 3D 地球与 2D 平面地图共用的数据构建层。
 * 目的：两种视图使用完全相同的点位/弧线/配色/提示逻辑，避免重复实现导致观感不一致。
 * 关键规则：只有 kind='geographic' 且坐标齐全的维度才会出现在地图上；
 * composite（全球综合 / 全球南方）不投影，改由 GRV 面板与状态条展示。
 */

export interface RiskPoint {
  id: string;
  label: string;
  lat: number;
  lng: number;
  value: number | null;
  uncertainty: number | null;
  uncertaintyEstimated: boolean;
  group: string;
  status: 'ok' | 'missing';
  color: string;
  severity: string;
  /** 归一化强度 0~1（缺失按 0） */
  weight: number;
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

/** 高严重度阈值（用于常驻标签 / 光环）。 */
export const HIGHLIGHT_THRESHOLD = 55;

/** 由维度列表构建地图点位（自动过滤 composite 与缺坐标项）。 */
export function buildRiskPoints(dims: GrvDimension[]): RiskPoint[] {
  const out: RiskPoint[] = [];
  for (const d of dims) {
    if (d.kind !== 'geographic') continue;
    if (d.lat === null || d.lng === null) continue;
    const v = d.value;
    out.push({
      id: d.id,
      label: d.label,
      lat: d.lat,
      lng: d.lng,
      value: v,
      uncertainty: d.uncertainty,
      uncertaintyEstimated: d.uncertaintyEstimated,
      group: d.group,
      status: d.status,
      color: severityColor(v),
      severity: severityLabel(v),
      weight: v === null ? 0 : Math.min(1, Math.max(0, v / 100)),
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

/** 统一的点位提示气泡 HTML（globe.gl pointLabel 与平面地图 tooltip 共用）。 */
export function pointTooltipHtml(p: RiskPoint): string {
  const val = p.value === null ? '数据缺失' : fmtNum(p.value);
  const unc =
    p.value === null || p.uncertainty === null
      ? '未知'
      : `±${fmtNum(p.uncertainty)}${p.uncertaintyEstimated ? '（估算）' : ''}`;
  return (
    `<div style="font:12px/1.5 ui-sans-serif,system-ui,'PingFang SC',sans-serif;` +
    `background:rgba(6,11,22,0.92);border:1px solid ${withAlpha(p.color, 0.55)};` +
    `box-shadow:0 0 18px ${withAlpha(p.color, 0.28)};color:${PALETTE.text};` +
    `padding:6px 10px;border-radius:8px;white-space:nowrap;">` +
    `<b style="color:${p.color}">${p.label}</b>` +
    `<span style="opacity:.5;margin-left:6px">${p.group}</span><br/>` +
    `风险值 <b>${val}</b> · 等级 ${p.severity}<br/>` +
    `<span style="opacity:.6">不确定区间 ${unc}</span>` +
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
