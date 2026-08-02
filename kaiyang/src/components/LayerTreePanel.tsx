import { useCallback, useState } from 'react';
import { LAYER_CATEGORIES } from '@/config/layerCategories';
import type { LayerCategory, LayerCategoryDef, LayerPhase } from '@/config/layerCategories';
import { ShapeSwatch, StarSwatch, type LayerCountMap } from '@/components/LayerLegend';
import { PALETTE, withAlpha } from '@/config/theme';

/**
 * 左侧指标树（CRUCIX 对标：monitor 左栏图层树）。
 *
 * 职责：
 * - 把 12 类风险图层按**落地阶段 phase（P0/P1/P2）**分组，渲染成可折叠的树；
 * - 每行给出「形状色块 + 状态灯 + 中文名 + 计数」四件套，并作为显隐开关；
 * - 战略要地叠加层单独一行（不属于 12 类色轴，故不进 phase 分组）；
 * - 顶部提供全开 / 全关。
 *
 * 边界（与 LayerLegend 同）：
 * - 本组件是**控制件**，允许 import `layerCategories` 以保证类别枚举与色值单一真源（K1）；
 *   任何类别色一律取 `def.color`，**禁止硬编码 hex**。
 * - **不持有任何图层数据**：可见集合 / 计数 / 回调全部由 `WorldPanel` 提供。
 *   绝不在此处 `useFeed`（useFeed 不缓存，重复调用 = 重复请求），也不引入 Context。
 * - 计数只来自传入的 `counts`（已是当前地区范围内口径），组件不自行推算、不编造数据。
 *
 * 组件切分（为「零新依赖」测试服务）：
 * - `LayerTreeView` / `LayerTreeGroup` / `LayerTreeRow` / `StatusLamp` 全部是**无 hook 的纯组件**，
 *   可被直接调用拿到元素树做交互断言（项目内无 jsdom / testing-library）；
 * - `LayerTreePanel` 只是一层持有折叠状态的薄壳（唯一带 `useState` 的地方）。
 */

/** 各分组的展开状态集合（phase → 是否展开）。 */
export type OpenPhases = ReadonlySet<LayerPhase>;

/** 行状态灯三态：live=开且有数据；empty=开但当前范围无数据；off=已关闭。 */
export type LayerRowStatus = 'live' | 'empty' | 'off';

export interface LayerTreePanelProps {
  /** 当前可见的类别集合 */
  visible: ReadonlySet<LayerCategory>;
  /** 各类别点位数（当前地区范围内口径），缺省视为 0 */
  counts: LayerCountMap;
  /** 单个类别显隐切换 */
  onToggle: (category: LayerCategory) => void;
  /** 全开 / 全关 */
  onSetAll: (visible: boolean) => void;
  /** 当前处于缺失态（灰）的点位总数；>0 时在树底部提示 */
  missingCount?: number;
  /** 战略要地叠加层是否可见（独立于 12 个类别色轴） */
  sitesVisible?: boolean;
  /** 战略要地图层开关；未提供时不渲染该行 */
  onToggleSites?: () => void;
}

/** 分组渲染顺序（与 LayerPhase 语义一致，不依赖 LAYER_CATEGORIES 的排列偶然性）。 */
export const PHASE_ORDER: LayerPhase[] = ['P0', 'P1', 'P2'];

/** 分组标题：必须体现「落地阶段」，避免用户把 P2 空图层误读成数据丢了。 */
export const PHASE_LABEL: Record<LayerPhase, string> = {
  P0: 'P0 已就位',
  P1: 'P1 规划',
  P2: 'P2 待后端',
};

/** 分组悬停说明。 */
export const PHASE_HINT: Record<LayerPhase, string> = {
  P0: '数据已接入并在图上渲染',
  P1: '前端已就绪 / 部分依赖后端补字段',
  P2: '等待后端 feed，当前恒为 0 点位（不是故障）',
};

/** 状态灯配色：只用既有 PALETTE，不新增色值。 */
const STATUS_STYLE: Record<LayerRowStatus, { color: string; glow: boolean; title: string }> = {
  live: { color: PALETTE.teal, glow: true, title: '已显示 · 当前范围内有数据' },
  empty: { color: withAlpha(PALETTE.slate, 0.85), glow: false, title: '已显示 · 当前范围内无数据' },
  off: { color: withAlpha(PALETTE.slate, 0.4), glow: false, title: '已关闭' },
};

/**
 * 行状态判定（纯函数，唯一入口）。
 * 「开但没数据」与「关掉了」必须可区分：前者是诚实的空，后者是用户主动隐藏。
 */
export function rowStatus(on: boolean, count: number): LayerRowStatus {
  if (!on) return 'off';
  return count > 0 ? 'live' : 'empty';
}

/** 按 phase 分组（顺序：PHASE_ORDER；组内顺序沿用 LAYER_CATEGORIES）。空组不产出。 */
export function groupByPhase(
  defs: readonly LayerCategoryDef[] = LAYER_CATEGORIES,
): Array<{ phase: LayerPhase; defs: LayerCategoryDef[] }> {
  const out: Array<{ phase: LayerPhase; defs: LayerCategoryDef[] }> = [];
  for (const phase of PHASE_ORDER) {
    const members = defs.filter((d) => d.phase === phase);
    if (members.length > 0) out.push({ phase, defs: members });
  }
  return out;
}

/** 状态灯：小圆点，三态由 `rowStatus` 决定，绝不因为「没数据」就伪装成有数据。 */
export function StatusLamp({ status }: { status: LayerRowStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <i
      data-status={status}
      title={s.title}
      aria-hidden="true"
      className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
      style={{
        background: s.color,
        boxShadow: s.glow ? `0 0 5px ${withAlpha(PALETTE.teal, 0.8)}` : undefined,
      }}
    />
  );
}

export interface LayerTreeRowProps {
  def: LayerCategoryDef;
  on: boolean;
  count: number;
  onToggle: (category: LayerCategory) => void;
}

/** 类别叶子行：整行即开关。纯组件，无 hook。 */
export function LayerTreeRow({ def, on, count, onToggle }: LayerTreeRowProps) {
  const status = rowStatus(on, count);
  const empty = count === 0;
  return (
    <button
      type="button"
      onClick={() => onToggle(def.key)}
      data-off={on ? 'false' : 'true'}
      data-category={def.key}
      aria-pressed={on}
      title={`${def.label}（${def.phase}）· ${def.desc}${empty ? ' · 当前无数据' : ` · ${count} 点`}`}
      className="layer-legend-item flex w-full items-center gap-1 rounded py-0.5 pl-2 pr-1 text-left"
    >
      <ShapeSwatch shape={def.shape} color={def.color} off={!on} />
      <StatusLamp status={status} />
      <span
        className={`layer-legend-label truncate text-[11px] ${
          empty ? 'text-white/30' : 'text-white/70'
        }`}
      >
        {def.label}
      </span>
      <span
        className={`ml-auto shrink-0 text-[10px] tabular-nums ${
          empty ? 'text-white/20' : 'text-white/45'
        }`}
      >
        {count}
      </span>
    </button>
  );
}

export interface LayerTreeGroupProps {
  phase: LayerPhase;
  defs: readonly LayerCategoryDef[];
  visible: ReadonlySet<LayerCategory>;
  counts: LayerCountMap;
  open: boolean;
  onToggleOpen: (phase: LayerPhase) => void;
  onToggle: (category: LayerCategory) => void;
}

/** 一个 phase 分组：可折叠组头 + 若干叶子行。纯组件，无 hook。 */
export function LayerTreeGroup({
  phase,
  defs,
  visible,
  counts,
  open,
  onToggleOpen,
  onToggle,
}: LayerTreeGroupProps) {
  const onCount = defs.filter((d) => visible.has(d.key)).length;
  return (
    <div className="mb-0.5" data-group={phase}>
      <button
        type="button"
        onClick={() => onToggleOpen(phase)}
        aria-expanded={open}
        data-phase={phase}
        title={`${PHASE_LABEL[phase]} · ${PHASE_HINT[phase]}`}
        className="layer-legend-item flex w-full items-center gap-1 rounded px-1 py-0.5 text-left"
      >
        <span className="w-2 shrink-0 text-[9px] leading-none text-white/35" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className="truncate text-[10px] tracking-wide text-white/45">
          {PHASE_LABEL[phase]}
        </span>
        <span className="ml-auto shrink-0 text-[9px] tabular-nums text-white/25">
          {onCount}/{defs.length}
        </span>
      </button>

      {open && (
        <div className="mt-px flex flex-col gap-px border-l border-white/5 pl-0.5">
          {defs.map((def) => (
            <LayerTreeRow
              key={def.key}
              def={def}
              on={visible.has(def.key)}
              count={counts[def.key] ?? 0}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export interface LayerTreeViewProps extends LayerTreePanelProps {
  /** 当前展开的分组集合 */
  openPhases: OpenPhases;
  /** 分组折叠 / 展开 */
  onTogglePhase: (phase: LayerPhase) => void;
}

/**
 * 指标树的**纯渲染体**（无 hook）：全部标记与交互都在这里，便于零依赖测试直接调用。
 * 折叠状态由外部（`LayerTreePanel`）持有并下传。
 */
export function LayerTreeView({
  visible,
  counts,
  onToggle,
  onSetAll,
  missingCount = 0,
  sitesVisible = false,
  onToggleSites,
  openPhases,
  onTogglePhase,
}: LayerTreeViewProps) {
  const total = LAYER_CATEGORIES.length;
  const visibleCount = LAYER_CATEGORIES.filter((d) => visible.has(d.key)).length;
  const allOn = visibleCount === total;
  const allOff = visibleCount === 0;
  const groups = groupByPhase();

  return (
    <aside
      aria-label="指标树"
      className="ky-layer-tree flex w-40 shrink-0 flex-col overflow-y-auto rounded-lg border border-white/5 bg-black/20 px-1 py-1.5"
    >
      {/* 树头：标题 + 计数 + 全开 / 全关 */}
      <div className="mb-1 px-1">
        <div className="flex items-center gap-1 text-[10px] text-white/40">
          <span className="tracking-wide">指标树</span>
          <span className="ml-auto tabular-nums text-white/25">
            {visibleCount}/{total}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-1">
          <button
            type="button"
            onClick={() => onSetAll(true)}
            disabled={allOn}
            className="rounded px-1.5 py-0.5 text-[10px] text-white/45 transition hover:bg-white/10 hover:text-white/80 disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent"
          >
            全开
          </button>
          <span className="text-white/15">|</span>
          <button
            type="button"
            onClick={() => onSetAll(false)}
            disabled={allOff}
            className="rounded px-1.5 py-0.5 text-[10px] text-white/45 transition hover:bg-white/10 hover:text-white/80 disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent"
          >
            全关
          </button>
        </div>
      </div>

      {/* 战略要地：独立叠加层，不属于 12 类色轴，故不进 phase 分组 */}
      {onToggleSites && (
        <button
          type="button"
          onClick={onToggleSites}
          data-off={sitesVisible ? 'false' : 'true'}
          data-row="sites"
          aria-pressed={sitesVisible}
          title="战略要地（国际公认的航运咽喉点 / 运河 / 海角）· 固定琥珀金星形标记，不参与风险类别编码"
          className="layer-legend-item mb-1 flex w-full items-center gap-1 rounded px-1 py-0.5 text-left"
        >
          <StarSwatch off={!sitesVisible} />
          <StatusLamp status={sitesVisible ? 'live' : 'off'} />
          <span
            className={`layer-legend-label truncate text-[11px] ${
              sitesVisible ? 'text-white/70' : 'text-white/30'
            }`}
          >
            战略要地
          </span>
          <span className="ml-auto shrink-0 text-[10px] text-amber-300/80" aria-hidden="true">
            ★
          </span>
        </button>
      )}

      {/* 按落地阶段分组的类别树 */}
      <div className="flex flex-col">
        {groups.map((g) => (
          <LayerTreeGroup
            key={g.phase}
            phase={g.phase}
            defs={g.defs}
            visible={visible}
            counts={counts}
            open={openPhases.has(g.phase)}
            onToggleOpen={onTogglePhase}
            onToggle={onToggle}
          />
        ))}
      </div>

      {/* 缺失态提示：与底部图例同口径，此处只做轻量提醒 */}
      {missingCount > 0 && (
        <div
          className="mt-auto border-t border-white/5 px-1 pt-1 text-[10px] text-white/35"
          title="数据缺失是元状态，强制灰 + 虚线，且不参与光环 / 常驻标签（决策 C2-A）"
        >
          数据缺失 <span className="tabular-nums text-white/50">{missingCount}</span>
        </div>
      )}
    </aside>
  );
}

/**
 * 左侧指标树（对外入口）。
 * 唯一的状态是「哪些分组是展开的」——纯 UI 局部状态，默认全展开，不持久化、不上提。
 */
export function LayerTreePanel(props: LayerTreePanelProps) {
  const [openPhases, setOpenPhases] = useState<ReadonlySet<LayerPhase>>(
    () => new Set<LayerPhase>(PHASE_ORDER),
  );

  const handleTogglePhase = useCallback((phase: LayerPhase) => {
    setOpenPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phase)) next.delete(phase);
      else next.add(phase);
      return next;
    });
  }, []);

  return <LayerTreeView {...props} openPhases={openPhases} onTogglePhase={handleTogglePhase} />;
}
