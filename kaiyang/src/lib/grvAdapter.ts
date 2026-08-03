import { GRV_DIMENSIONS } from '@/config/grvDimensions';
import type { GrvDimension, GrvRaw } from '@/types/contracts';

/**
 * 将 GRV 原始契约适配为统一内部模型（11 维 + 坐标 + 缺失状态 + 地理/综合分类）。
 * - 上游无 lat/lng：使用 grvDimensions.ts 内置默认坐标（composite 维度无坐标）。
 * - 上游无不确定区间字段：按 8% 比例估算并标记 estimated（契约要求该字段，Wave1 数据未提供）。
 * - 上游缺少某维度：status='missing'，供状态条告警与降级渲染。
 */

/** Wave1 估算比例（数据源未提供不确定区间时的回退）。 */
const UNCERTAINTY_RATIO = 0.08;

function estimateUncertainty(value: number): number {
  return Math.max(3, Math.round(Math.abs(value) * UNCERTAINTY_RATIO * 10) / 10);
}

export interface GrvModel {
  /** 全部维度（含 composite） */
  dimensions: GrvDimension[];
  /** 可投影到地图的地理维度 */
  geographic: GrvDimension[];
  /** 全球综合维度（不上地图，走头条数字 + 状态条） */
  composite: GrvDimension[];
  /** 头条综合指数（优先 global_composite；缺失则取第一个有值的 composite） */
  headline: GrvDimension | null;
  updated: string | null;
  gdeltUpdated: string | null;
  sourceQuality: string | null;
  /** 上游存在但内部未映射的键（用于状态告警） */
  missingKeys: string[];
}

export function adaptGrv(raw: GrvRaw | null): GrvModel {
  const missingKeys: string[] = [];
  // 推导维度元数据（来自 grv_latest.json._derived_meta）
  const derivedMeta = (raw as Record<string, unknown> | null)?._derived_meta as
    Record<string, { confidence?: number; missing?: string[]; note?: string }> | undefined;

  const dimensions: GrvDimension[] = GRV_DIMENSIONS.map((def) => {
    const rawVal = def.sourceKey ? raw?.[def.sourceKey] : undefined;
    const numVal = typeof rawVal === 'number' && Number.isFinite(rawVal) ? rawVal : null;
    if (def.sourceKey && (rawVal === undefined || rawVal === null)) {
      missingKeys.push(def.sourceKey);
    }
    const isComposite = def.kind === 'composite';
    // 推导维度不确定区间 = 实测维度的 1.5-2 倍（confidence < 0.65 用 2 倍）
    let uncertainty: number | null = null;
    if (numVal !== null && !isComposite) {
      const base = estimateUncertainty(numVal);
      if (def.isDerived) {
        const conf = derivedMeta?.[def.id]?.confidence ?? 0;
        uncertainty = Math.round(base * (conf >= 0.65 ? 1.5 : 2.0) * 10) / 10;
      } else {
        uncertainty = base;
      }
    }

    const meta = def.isDerived ? derivedMeta?.[def.id] : undefined;
    return {
      id: def.id,
      label: def.label,
      value: numVal,
      uncertainty,
      uncertaintyEstimated: numVal !== null && !isComposite,
      kind: def.kind,
      lat: def.lat ?? null,
      lng: def.lng ?? null,
      group: def.group,
      note: def.note,
      status: numVal === null ? 'missing' : 'ok',
      isDerived: def.isDerived ?? false,
      derivedConfidence: meta?.confidence,
      derivedMissing: meta?.missing,
    };
  });

  const geographic = dimensions.filter(
    (d) => d.kind === 'geographic' && d.lat !== null && d.lng !== null,
  );
  const composite = dimensions.filter((d) => d.kind === 'composite');
  const headline =
    composite.find((d) => d.id === 'global_composite' && d.value !== null) ??
    composite.find((d) => d.value !== null) ??
    composite[0] ??
    null;

  return {
    dimensions,
    geographic,
    composite,
    headline,
    updated: raw?.updated ?? null,
    gdeltUpdated: raw?.gdelt_updated ?? null,
    sourceQuality: raw?.source_quality ?? null,
    missingKeys,
  };
}

/** 取风险最高的前 N 个维度（缺失值排最后）。 */
export function topRisks(dims: GrvDimension[], n = 6): GrvDimension[] {
  return [...dims]
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))
    .slice(0, Math.max(0, n));
}
