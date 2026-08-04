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
/**
 * parseTs — 时间戳确定性解析。
 * 数据源契约：天枢容器 TZ=Asia/Shanghai，所有时间戳为北京时间。
 * 无时区后缀的 ISO 串（如 grv.updated='2026-08-05T06:10:03'）显式补 +08:00，
 * 消除 ES5(UTC)/ES2015+(本地) 语义漂移与跨浏览器时区差异。
 */
export function parseTs(t: string | null | undefined): Date | null {
  if (!t) return null;
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)/.exec(t);
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(t);
  if (m && !hasTz) {
    const d = new Date(m[1] + 'T' + m[2] + '+08:00');
    return isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(t);
  return isNaN(d.getTime()) ? null : d;
}

/** fmtRelative — 相对时间（新鲜度直观显示）：刚刚 / X 分钟前 / X 小时前 / X 天前 / MM-DD */
export function fmtRelative(t: string | null | undefined): string {
  const d = parseTs(t);
  if (!d) return '—';
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return diffMin + ' 分钟前';
  const hr = Math.floor(diffMin / 60);
  if (hr < 24) return hr + ' 小时前';
  const day = Math.floor(hr / 24);
  if (day < 7) return day + ' 天前';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t ?? '');
  return m ? m[2] + '-' + m[3] : day + ' 天前';
}

export function fmtStamp(t: string | null | undefined): string {
  if (!t) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(t);
  if (m) return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
  return t;
}
