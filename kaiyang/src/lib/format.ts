import { severityColor, severityLabel } from '@/config/theme';

/**
 * 风险着色与格式化工具（全中文 UI）。
 * 配色单一事实来源是 config/theme.ts；此处仅做语义别名，避免历史调用点大改。
 */

/** 根据风险数值返回颜色（缺失=灰，低=青，中=琥珀，高=红）。 */
export function riskColor(value: number | null): string {
  return severityColor(value);
}

/** 风险等级中文标签。 */
export function riskLabel(value: number | null): string {
  return severityLabel(value);
}

/** 数值格式化；非有限值返回占位符。 */
export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

/** 截断过长文本。 */
export function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** 时间戳精简显示（保留到分钟；解析失败原样返回）。 */
export function fmtStamp(t: string | null | undefined): string {
  if (!t) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(t);
  if (m) return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
  return t;
}
