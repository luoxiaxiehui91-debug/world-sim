import { useMemo } from 'react';
import { PALETTE, withAlpha } from '@/config/theme';
import { sanitizeUrl } from '@/lib/newsGeoAdapter';
import type { RiskPoint } from '@/lib/mapData';
import type { NewsGeoEvent } from '@/types/contracts';

/** 事件类型徽标色（四枚举 + 兜底；复用主题令牌，不硬编码新色）。 */
function typeColor(eventType: string): string {
  const MAP: Record<string, string> = {
    conflict: PALETTE.red,
    protest: PALETTE.amber,
    disaster: PALETTE.teal,
    political: PALETTE.cyan,
    unknown: PALETTE.textDim,
  };
  return MAP[eventType] ?? PALETTE.textDim;
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

interface EventPopupProps {
  /** 选中的事件点（RiskPoint 已含 sourceUrl 消毒值） */
  point: RiskPoint;
  /** 同地点事件列表（WorldPanel 已按 location_name 过滤，原始 NewsGeoEvent） */
  related: NewsGeoEvent[];
  onClose: () => void;
}

/**
 * v1.10.5 事件弹框：点击地图事件点后展示详情 + 同地点事件列表。
 * 安全：所有文本经 React 默认转义渲染；链接 href 经 sanitizeUrl 消毒（仅 http/https）。
 */
export function EventPopup({ point, related, onClose }: EventPopupProps) {
  const items = useMemo(() => {
    return related
      .filter((e) => e.id !== point.id.replace(/^newsgeo:/, ''))
      .slice(0, 10);
  }, [related, point]);

  return (
    <div className="absolute right-3 top-3 z-20 w-72 max-w-[calc(100%-1.5rem)]">
      <div className="glass-panel scanlines flex max-h-[70%] flex-col overflow-hidden rounded-lg">
        {/* 标题行 */}
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
          <div className="min-w-0">
            <div className="truncate text-[12px] font-semibold text-white/90">{point.label}</div>
            <div className="truncate text-[10px] text-white/35">{point.group}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="关闭"
            aria-label="关闭弹框"
            className="shrink-0 rounded border border-white/10 p-1 text-white/40 transition-colors hover:border-white/30 hover:text-white/80"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {/* 选中点详情 */}
          <div className="mb-1.5 space-y-0.5 text-[10px] leading-snug text-white/50">
            {point.note && <div>时间：{point.note}</div>}
            {point.rawMetric && <div>强度：{point.rawMetric}</div>}
            <div>等级：{point.severity}</div>
          </div>
          {point.sourceUrl ? (
            <a
              href={point.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mb-2 block rounded border border-white/10 px-2 py-1 text-center text-[11px] transition-colors hover:border-white/30"
              style={{ color: withAlpha(PALETTE.cyan, 0.9) }}
            >
              查看新闻原文
            </a>
          ) : (
            <div className="mb-2 text-[10px] text-white/25">无原文链接</div>
          )}

          {/* 同地点事件列表 */}
          <div className="mb-1 text-[10px] font-semibold tracking-widest text-white/45">
            同地点事件 · {related.length}
          </div>
          {items.length === 0 ? (
            <div className="text-[10px] text-white/25">无其他事件</div>
          ) : (
            <ul className="space-y-1">
              {items.map((e) => {
                const href = sanitizeUrl(e.source_url);
                const c = typeColor(e.event_type);
                return (
                  <li key={e.id} className="rounded border border-white/6 bg-black/20 px-2 py-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: c, boxShadow: `0 0 4px ${withAlpha(c, 0.6)}` }}
                      />
                      <span className="truncate text-[10px]" style={{ color: withAlpha(c, 0.9) }}>
                        {e.event_type}
                      </span>
                      <span className="ml-auto shrink-0 text-[9px] text-white/30">{e.event_date}</span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2">
                      <span className="truncate text-[9px] text-white/35">
                        {e.mention_count !== undefined ? `提及 ${e.mention_count} 次` : ''}
                        {e.intensity !== undefined ? ` · 强度 ${e.intensity}` : ''}
                      </span>
                      {href && (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-[9px] underline-offset-2 hover:underline"
                          style={{ color: withAlpha(PALETTE.cyan, 0.8) }}
                        >
                          原文
                        </a>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
