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
      {/* 建设图标 */}
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-white/10 bg-white/5">
        <span className="text-2xl">🚧</span>
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
