import type { ReactElement } from 'react';
import { LAYER_CATEGORIES, MISSING_COLOR } from '@/config/layerCategories';
import type { LayerCategory, PointShape } from '@/config/layerCategories';
import { SEVERITY_LEGEND, withAlpha } from '@/config/theme';
import { STRATEGIC_SITE_COLOR } from '@/data/strategicSites';

/**
 * 分类图层图例（底部说明条）。
 *
 * 职责（1.5.0 起收窄）：
 * - 说明「色相 = 类别 / 强度 = 尺寸+脉冲」这组双轴编码（决策 D1）；
 * - 提供全开 / 全关这两个全局动作；
 * - 底部一行补充「灰虚线 = 数据缺失」的元状态说明与计数徽标。
 *
 * **逐类别开关与逐类别计数已于 1.5.0 迁移至左侧指标树 `LayerTreePanel`**，
 * 避免同一功能在底部图例与左树各存一套、状态两处显示互相打架。
 * 本文件继续导出 `LayerCountMap` / `ShapeSwatch` / `StarSwatch` 供左树复用（单一来源）。
 *
 * 边界：
 * - 本组件是**控制件**，不是地图渲染器，因此允许（也应该）import `layerCategories`
 *   以保证类别枚举与色值只有一个真源（K1）；
 * - 反之 GlobePanel / FlatMapPanel 属渲染器，只直读 `point.color/weight/shape/status`，
 *   不得反查类别定义（K6）。
 * - 本组件不持有状态：可见集合与回调全部由 WorldPanel 提供（便于持久化与测试）。
 */

/** 各类别当前点位数（缺省视为 0）。 */
export type LayerCountMap = Partial<Record<LayerCategory, number>>;

export interface LayerLegendProps {
  /** 当前可见的类别集合（用于头部 N/总数 与 全开 / 全关 的禁用判定） */
  visible: ReadonlySet<LayerCategory>;
  /** 全开 / 全关 */
  onSetAll: (visible: boolean) => void;
  /** 当前处于缺失态（灰）的点位总数；>0 时在说明行高亮 */
  missingCount?: number;
}

const SWATCH_SIZE = 12;

/**
 * 形状色块：与地图符号保持一致（circle / diamond / triangle / square）。
 * 已 export：左侧指标树 `LayerTreePanel` 直接复用，避免两处各画一套 SVG 而慢慢漂移。
 */
export function ShapeSwatch({
  shape,
  color,
  off,
}: {
  shape: PointShape;
  color: string;
  off: boolean;
}) {
  const c = SWATCH_SIZE / 2;
  const r = 4.2;
  const fill = off ? 'transparent' : withAlpha(color, 0.55);
  const stroke = off ? withAlpha(color, 0.45) : color;
  const common = {
    fill,
    stroke,
    strokeWidth: 1,
    strokeDasharray: off ? '2 1.6' : undefined,
  };

  let node: ReactElement;
  if (shape === 'arrow') {
    // 08-14 aircraft 实时航班图层：小箭头（指向右，地图上按航向 rotate 旋转）
    node = (
      <path
        d={`M ${c - r},${c - r * 0.72} L ${c + r * 0.92},${c} L ${c - r},${c + r * 0.72} L ${c - r * 0.12},${c} Z`}
        {...common}
      />
    );
  } else if (shape === 'arc') {
    // 08-14 air 全球航线网图层：小弧线（与地图弧渲染呼应；弧线图层无点位）
    node = (
      <path
        d={`M ${c - r},${c + r * 0.9} Q ${c - r * 0.4},${c - r * 1.5} ${c + r * 0.85},${c - r * 0.55}`}
        fill="none"
        stroke={stroke}
        strokeWidth={1.6}
        strokeDasharray={off ? '2 1.6' : undefined}
        opacity={off ? 0.45 : 0.95}
      />
    );
  } else if (shape === 'diamond') {
    node = <polygon points={`${c},${c - r} ${c + r},${c} ${c},${c + r} ${c - r},${c}`} {...common} />;
  } else if (shape === 'triangle') {
    node = (
      <polygon
        points={`${c},${c - r} ${c + r * 0.95},${c + r * 0.75} ${c - r * 0.95},${c + r * 0.75}`}
        {...common}
      />
    );
  } else if (shape === 'dot') {
    // 08-14 海量点简化（thermal/sdr）：小实心点，与地图 dot 渲染一致
    node = <circle cx={c} cy={c} r={r * 0.8} {...common} />;
  } else if (shape === 'square') {
    node = <rect x={c - r * 0.85} y={c - r * 0.85} width={r * 1.7} height={r * 1.7} {...common} />;
  } else {
    node = <circle cx={c} cy={c} r={r * 0.9} {...common} />;
  }

  return (
    <svg
      width={SWATCH_SIZE}
      height={SWATCH_SIZE}
      viewBox={`0 0 ${SWATCH_SIZE} ${SWATCH_SIZE}`}
      className="shrink-0"
      aria-hidden="true"
      style={off ? undefined : { filter: `drop-shadow(0 0 3px ${withAlpha(color, 0.55)})` }}
    >
      {node}
    </svg>
  );
}

/**
 * 战略要地色块：四角星 + 固定琥珀金，与地图符号保持一致。
 * 与类别色轴（D1）完全独立，单独成块、不复用类别开关样式里的圆/菱形。
 * 已 export：左侧指标树 `LayerTreePanel` 直接复用（单一来源）。
 */
export function StarSwatch({ off }: { off: boolean }) {
  const c = SWATCH_SIZE / 2;
  const outer = 5;
  const inner = outer * 0.36;
  const pts: string[] = [];
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI / 4) * i - Math.PI / 2;
    const r = i % 2 === 0 ? outer : inner;
    pts.push(`${(c + Math.cos(angle) * r).toFixed(2)},${(c + Math.sin(angle) * r).toFixed(2)}`);
  }
  return (
    <svg
      width={SWATCH_SIZE}
      height={SWATCH_SIZE}
      viewBox={`0 0 ${SWATCH_SIZE} ${SWATCH_SIZE}`}
      className="shrink-0"
      aria-hidden="true"
      style={off ? undefined : { filter: `drop-shadow(0 0 3px ${withAlpha(STRATEGIC_SITE_COLOR, 0.6)})` }}
    >
      <polygon
        points={pts.join(' ')}
        fill={off ? 'transparent' : withAlpha(STRATEGIC_SITE_COLOR, 0.7)}
        stroke={off ? withAlpha(STRATEGIC_SITE_COLOR, 0.45) : STRATEGIC_SITE_COLOR}
        strokeWidth={0.8}
        strokeDasharray={off ? '2 1.6' : undefined}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LayerLegend({ visible, onSetAll, missingCount = 0 }: LayerLegendProps) {
  const visibleCount = LAYER_CATEGORIES.filter((d) => visible.has(d.key)).length;
  const total = LAYER_CATEGORIES.length;
  const allOn = visibleCount === total;
  const allOff = visibleCount === 0;

  return (
    <div className="mt-2 rounded-lg border border-white/5 bg-black/20 px-2 py-1.5">
      {/* 标题行 + 全开 / 全关 */}
      <div className="mb-1 flex items-center gap-2 text-[10px] text-white/40">
        <span className="tracking-wide">图层（色相 = 类别）</span>
        <span className="text-white/25">
          {visibleCount}/{total}
        </span>
        <div className="ml-auto flex items-center gap-1">
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

      {/* 说明行：另一半双轴（严重度）+ 缺失态元状态。
          逐类别开关已迁至左侧指标树 LayerTreePanel，此处不再重复一套。 */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-white/35">
        <span className="text-white/30">强度 = 尺寸/脉冲</span>
        {SEVERITY_LEGEND.map((l) => (
          <span key={l.level} className="flex items-center gap-1">
            <i
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: l.color, boxShadow: `0 0 6px ${withAlpha(l.color, 0.6)}` }}
            />
            {l.label}
          </span>
        ))}
        <span
          className="ml-auto flex items-center gap-1"
          title="数据缺失是元状态，强制灰 + 虚线，且不参与光环 / 常驻标签（决策 C2-A）"
        >
          <i
            className="layer-swatch-missing inline-block h-2 w-2 rounded-full border"
            style={{ borderColor: MISSING_COLOR }}
          />
          <span className={missingCount > 0 ? 'text-white/50' : 'text-white/25'}>
            数据缺失{missingCount > 0 ? ` ${missingCount}` : ''}
          </span>
        </span>
      </div>
    </div>
  );
}
