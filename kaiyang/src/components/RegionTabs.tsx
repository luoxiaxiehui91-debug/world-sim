import { REGIONS, type RegionKey } from '@/config/regions';

/**
 * 地区 Tab（R-P1-02）：6 个按钮，切换地图取景范围与点位过滤。
 *
 * 纯展示组件（无 state / 无副作用），状态由 `WorldPanel` 持有并持久化到 `kaiyang.region`。
 * 视觉沿用既有 3D/2D 切换器的胶囊风格（`bg-accent/20 text-accent` 高亮），
 * **不引入新颜色**（D1 铁律：类别色轴归类别，交互控件只用 accent）。
 */
export interface RegionTabsProps {
  region: RegionKey;
  onChange: (key: RegionKey) => void;
  /** 额外容器类名（供父容器控制排布） */
  className?: string;
}

/** 单个 Tab 的悬停说明（全中文，说明这个 Tab 到底会做什么）。 */
function tabTitle(label: string, hasBbox: boolean): string {
  return hasBbox
    ? `只看${label}范围内的点位与战略要地，地图相机同步聚焦该区域`
    : '显示全球全部点位，地图相机回到默认全球视角（不过滤）';
}

export function RegionTabs({ region, onChange, className = '' }: RegionTabsProps) {
  return (
    <div
      className={`flex flex-wrap items-center gap-0.5 rounded-full border border-white/10 bg-black/30 p-0.5 ${className}`}
      role="group"
      aria-label="地区筛选"
    >
      {REGIONS.map((r) => {
        const active = r.key === region;
        return (
          <button
            key={r.key}
            type="button"
            onClick={() => onChange(r.key)}
            aria-pressed={active}
            title={tabTitle(r.label, r.bbox !== null)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] transition ${
              active ? 'bg-accent/20 text-accent' : 'text-white/45 hover:text-white/75'
            }`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}
