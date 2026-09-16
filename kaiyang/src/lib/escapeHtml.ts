/** HTML 实体转义（XSS 防线：所有进入 tooltip / 图表 formatter HTML 的外部文本统一在此转义）。
 *
 * 渲染层**唯一**转义点 —— 避免与适配层重复转义造成双重转义。
 *
 * 09-16 从 `lib/mapData.ts` 提取为共享模块：平面地图 tooltip、3D 地球 htmlElements、
 * echarts `tooltip.formatter` 均在渲染层构建 HTML 字符串，原先各自裸插值，现统一复用本函数。
 * 详见红线 #81（「补丁只打在一条路径上，同族没跟着改」）。
 */
export function escapeHtml(value: unknown): string {
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
