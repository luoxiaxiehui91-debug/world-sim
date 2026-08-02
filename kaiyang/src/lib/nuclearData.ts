import { categoryColor, categoryShape, resolvePointStatus } from '@/config/layerCategories';
import type { PointStatus } from '@/config/layerCategories';
import { NUCLEAR_SEED, NUCLEAR_TYPE_LABEL } from '@/config/nuclearSites';
import { severityLabel } from '@/config/theme';
import type { RiskPoint } from '@/lib/mapData';
import type {
  NuclearLevel,
  NuclearSite,
  NuclearSitesRaw,
  NuclearWatchReading,
} from '@/types/contracts';

/**
 * 核设施图层构建层。
 *
 * 职责边界（与 `lib/mapData.ts` 同构）：
 * - 颜色 / 形状 / 强度全部在此**预计算**进 `RiskPoint`，渲染器只做直读（K6）；
 * - 原生度量（µSv/h）归一化进 `value`(0~100)，原文放 `rawMetric` 仅供展示（K3）；
 * - 每个导出函数第一行就是入参 nullish 检查，任何降级路径不抛异常（K5 红线）。
 *
 * ⚠ 领域判断归属：辐射分级阈值本应由后端给 `level`，前端只展示。
 * 下方 `readingToValue` 的 baseline 倍数推断仅是**后端未给 level 时的兜底**，
 * 不构成开阳沉淀领域逻辑（设计稿 §10-N8）。
 */

/** 站点 + 读数合并后的一行（面板表格与图层点位的共同输入）。 */
export interface NuclearRow {
  site: NuclearSite;
  /** 读数原值；null = 无数据（面板显示「—」） */
  reading: number | null;
  /** 读数单位；缺失时不显示单位 */
  unit: string | null;
  /** 本底参考值；用于 level 缺失时推断倍数 */
  baseline: number | null;
  /** 该读数的观测时间（ISO 8601 UTC）；缺失为 null */
  updated: string | null;
  /** 分级：后端优先，其次前端按 baseline 倍数推断，再缺失为 'unknown' */
  level: NuclearLevel;
  /** 归一化严重度 0~100（K3）；null = 无法判定，点位走缺失灰 */
  value: number | null;
}

/** level → value(0~100) 映射（后端给 level 时的权威口径）。 */
const LEVEL_VALUE: Record<NuclearLevel, number | null> = {
  normal: 20,
  elevated: 55,
  alert: 85,
  unknown: null,
};

/** level → 中文标签（面板列展示）。 */
export const NUCLEAR_LEVEL_LABEL: Record<NuclearLevel, string> = {
  normal: '正常',
  elevated: '偏高',
  alert: '告警',
  unknown: '未知',
};

/** 合法 level 白名单（脏数据不炸）。 */
const LEVEL_KEYS: readonly NuclearLevel[] = ['normal', 'elevated', 'alert', 'unknown'];

function toLevel(input: unknown): NuclearLevel | null {
  return typeof input === 'string' && (LEVEL_KEYS as readonly string[]).includes(input)
    ? (input as NuclearLevel)
    : null;
}

/** 有限数守卫：NaN / Infinity / null / undefined / 字符串一律判否。 */
function finiteOrNull(input: unknown): number | null {
  return typeof input === 'number' && Number.isFinite(input) ? input : null;
}

/** 非空字符串守卫。 */
function textOrNull(input: unknown): string | null {
  return typeof input === 'string' && input.trim() !== '' ? input.trim() : null;
}

/** 坐标合法性：必须是有限数且落在地理范围内（K4）。 */
function isValidCoord(lat: unknown, lng: unknown): boolean {
  const la = finiteOrNull(lat);
  const ln = finiteOrNull(lng);
  if (la === null || ln === null) return false;
  return la >= -90 && la <= 90 && ln >= -180 && ln <= 180;
}

/** 校验并规整一条 site；不合法返回 null（跳过该站，不画到 (0,0)）。 */
function normalizeSite(raw: unknown): NuclearSite | null {
  if (!raw || typeof raw !== 'object') return null;
  const s = raw as Partial<NuclearSite>;
  const id = textOrNull(s.id);
  if (!id) return null;
  if (!isValidCoord(s.lat, s.lng)) return null;
  const type =
    s.type === 'npp' || s.type === 'monitor' || s.type === 'legacy' ? s.type : undefined;
  return {
    id,
    name: textOrNull(s.name) ?? id,
    name_en: textOrNull(s.name_en) ?? undefined,
    country: textOrNull(s.country) ?? '未知',
    lat: s.lat as number,
    lng: s.lng as number,
    type,
    note: textOrNull(s.note) ?? undefined,
  };
}

/**
 * 读数 → 归一化严重度 value(0~100)。
 *
 * 优先级（设计稿 §3.4）：
 * 1. 后端给了合法 `level` 且非 unknown → 直接映射 normal=20 / elevated=55 / alert=85；
 * 2. 否则 `reading` 与 `baseline` 齐全且 baseline>0 → `20 + (reading/baseline - 1) * 40`，夹取 [0,100]；
 * 3. 否则（仅有 reading、无 baseline，或什么都没有）→ `null`（缺失灰，不参与光环）。
 *
 * 入参可以是任意残缺对象，永不抛异常。
 */
export function readingToValue(
  row: Pick<NuclearRow, 'reading' | 'baseline' | 'level'> | null | undefined,
): number | null {
  if (!row) return null;

  const level = toLevel(row.level);
  if (level && level !== 'unknown') return LEVEL_VALUE[level];

  const reading = finiteOrNull(row.reading);
  const baseline = finiteOrNull(row.baseline);
  if (reading === null || baseline === null || baseline <= 0) return null;

  const ratio = reading / baseline;
  const value = 20 + (ratio - 1) * 40;
  if (!Number.isFinite(value)) return null;
  const clamped = Math.min(100, Math.max(0, value));
  // 浮点毛刺归整：0.36/0.12 这类除法会算出 99.99999999999999，
  // 直接外传会让 weight 差一个 ULP、并让 severity 阈值判定在边界上抖动。
  // 严重度只需 2 位小数精度，统一在此收口（K3：value 是 0~100 的对外量纲契约）。
  return Math.round(clamped * 100) / 100;
}

/** value(0~100) → level（前端兜底推断，口径与 LEVEL_VALUE 对齐）。 */
function valueToLevel(value: number | null): NuclearLevel {
  if (value === null) return 'unknown';
  if (value >= 85) return 'alert';
  if (value >= 55) return 'elevated';
  return 'normal';
}

/**
 * 合并 feed 与静态种子，产出面板与图层共用的行数据。
 *
 * 降级矩阵（K5）：
 * | 输入 | 行为 |
 * |---|---|
 * | `raw` 为 null / undefined（文件缺失或 HTTP 错误） | 用 `NUCLEAR_SEED`，读数全 null |
 * | `raw.sites` 缺字段 / 为空数组 | 同上（空是合法业务态，不告警） |
 * | `raw.sites` 非空 | **完全覆盖**种子（后端为准） |
 * | `raw.readings` 缺失 / 为空 | 各行 reading=null，面板显示「—」 |
 * | 单条 reading 的 site_id 无对应站点 | 丢弃该条（不凭空造站） |
 *
 * 输出顺序：与生效的站点列表顺序一致（稳定，便于表格与图层对照）。
 */
export function mergeNuclear(raw: NuclearSitesRaw | null | undefined): NuclearRow[] {
  const rawSites = Array.isArray(raw?.sites) ? raw.sites : [];
  const normalized: NuclearSite[] = [];
  const seen = new Set<string>();
  for (const s of rawSites) {
    const site = normalizeSite(s);
    if (!site) continue;
    if (seen.has(site.id)) continue; // 同 id 取先出现者，避免表格重复行
    seen.add(site.id);
    normalized.push(site);
  }

  // feed 站点为空 ⇒ 回落静态种子（一级降级）
  const sites = normalized.length > 0 ? normalized : NUCLEAR_SEED;

  // readings 按 site_id join；同 id 取最后一条（后到覆盖先到）
  const readingById = new Map<string, NuclearWatchReading>();
  const rawReadings = Array.isArray(raw?.readings) ? raw.readings : [];
  for (const r of rawReadings) {
    if (!r || typeof r !== 'object') continue;
    const sid = textOrNull((r as NuclearWatchReading).site_id);
    if (!sid) continue;
    readingById.set(sid, r as NuclearWatchReading);
  }

  return sites.map((site) => {
    const r = readingById.get(site.id);
    const reading = finiteOrNull(r?.reading);
    const baseline = finiteOrNull(r?.baseline);
    const backendLevel = toLevel(r?.level);
    const value = readingToValue({ reading, baseline, level: backendLevel ?? 'unknown' });
    return {
      site,
      reading,
      unit: textOrNull(r?.unit),
      baseline,
      updated: textOrNull(r?.updated),
      // 后端 level 优先；显式 'unknown' 等同缺失，按推断出的 value 反推，再缺失为 unknown
      level: backendLevel && backendLevel !== 'unknown' ? backendLevel : valueToLevel(value),
      value,
    };
  });
}

/** 读数原文（tooltip / 面板复用）：有数则「0.12 µSv/h」，无数则 null。 */
export function formatReading(row: Pick<NuclearRow, 'reading' | 'unit'>): string | null {
  if (row.reading === null) return null;
  return row.unit ? `${row.reading} ${row.unit}` : String(row.reading);
}

/**
 * 行数据 → 地图点位（`category:'nuclear'` / `shape:'diamond'`）。
 *
 * - `value === null` ⇒ `status='missing'` ⇒ 灰 + weight 0（C2-A / K3）；
 * - id 带 `nuclear:` 命名空间前缀（K2）；
 * - `rawMetric` 放读数原文，不参与任何计算。
 */
export function buildNuclearPoints(rows: NuclearRow[] | null | undefined): RiskPoint[] {
  if (!rows || rows.length === 0) return [];
  const out: RiskPoint[] = [];
  for (const row of rows) {
    if (!row?.site) continue;
    const { site } = row;
    if (!isValidCoord(site.lat, site.lng)) continue;
    const value = finiteOrNull(row.value);
    const status: PointStatus = resolvePointStatus(undefined, value);
    const typeLabel = site.type ? NUCLEAR_TYPE_LABEL[site.type] : '核设施';
    out.push({
      id: `nuclear:${site.id}`,
      label: site.name,
      lat: site.lat,
      lng: site.lng,
      value,
      uncertainty: null,
      uncertaintyEstimated: false,
      group: `${site.country} · ${typeLabel}`,
      status,
      color: categoryColor('nuclear', status),
      severity: severityLabel(value),
      weight: value === null ? 0 : Math.min(1, Math.max(0, value / 100)),
      category: 'nuclear',
      shape: categoryShape('nuclear'),
      rawMetric: formatReading(row) ?? undefined,
      note: site.note,
    });
  }
  return out;
}
