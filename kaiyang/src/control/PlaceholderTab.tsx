/**
 * 建设中占位 Tab 组件
 * 天璇 / 天玑 / 玉衡共用，显示建设中文案
 * 已评：保留镜像，等待后端 P1+
 */

interface PlaceholderTabProps {
  /** Tab 标题 */
  title: string;
  /** 描述文案 */
  description: string;
}

export function PlaceholderTab({ title, description }: PlaceholderTabProps) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
      {/* 建设图标（SVG，v1.11.29 替换原 emoji 🚧——P0-1 禁止 emoji 作功能图标） */}
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-white/5">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'rgba(255,255,255,0.45)' }} aria-hidden="true">
          <path d="M9 3h6v4l-4.5 5v5l-3 4V3z" />
          <path d="M9 12h6" />
        </svg>
      </div>

      {/* 标题 */}
      <h2 className="text-sm font-semibold text-white/50">{title}</h2>

      {/* 描述 */}
      <p className="max-w-[240px] text-[12px] leading-relaxed text-white/30">
        {description}
      </p>

      {/* 装饰性进度点 */}
      <div className="mt-3 flex gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-white/10" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/15" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/10" />
      </div>
    </div>
  );
}
