import { useEffect, useMemo, useState } from 'react';
import { GlobePanel } from '@/components/GlobePanel';
import { FlatMapPanel } from '@/components/FlatMapPanel';
import { useFeed } from '@/hooks/useFeed';
import { useStatus } from '@/state/StatusContext';
import { adaptGrv } from '@/lib/grvAdapter';
import { buildEventBars, buildRiskArcs, buildRiskPoints } from '@/lib/mapData';
import { SEVERITY_LEGEND, severityColor, withAlpha } from '@/config/theme';
import { fmtNum } from '@/lib/format';
import type { GrvRaw } from '@/types/contracts';

/** 视图模式：3D 地球 / 2D 平面地图。 */
export type WorldViewMode = 'globe' | 'flat';

const STORAGE_KEY = 'kaiyang.worldViewMode';

/** 从 localStorage 读取上次选择的视图模式（失败时回退 3D）。 */
function readInitialMode(): WorldViewMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'flat' ? 'flat' : 'globe';
  } catch {
    return 'globe';
  }
}

/**
 * 世界视图主面板：3D 地球 / 2D 平面地图切换容器。
 * - 两种视图共享同一份 GRV 数据与配色（lib/mapData.ts 构建），观感与语义一致。
 * - composite（全球综合 / 全球南方）不投影到地图，改在此处头部与 GRV 面板以数字呈现。
 * - 两个子视图始终挂载、以显隐切换，避免反复创建 / 销毁 WebGL 上下文。
 */
export function WorldPanel() {
  const [mode, setMode] = useState<WorldViewMode>(readInitialMode);
  const { data, loading, error } = useFeed<GrvRaw>('grv');
  const { report } = useStatus();
  const model = useMemo(() => adaptGrv(data), [data]);
  const points = useMemo(() => buildRiskPoints(model.geographic), [model]);
  const arcs = useMemo(() => buildRiskArcs(model.geographic), [model]);
  // 事件触发式告警柱（气候 / 灾害事件）：无事件时为空数组，地图上什么都不画
  const eventPoints = useMemo(() => buildEventBars(data?.events), [data]);
  const allPoints = useMemo(() => [...points, ...eventPoints], [points, eventPoints]);

  // 记住上次的视图选择
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, [mode]);

  // 缺失维度上报告警（供状态条记录）
  useEffect(() => {
    if (!data) return;
    model.dimensions
      .filter((d) => d.status === 'missing')
      .forEach((d) => report({ feed: 'grv', field: d.id, message: `GRV 维度缺失：${d.label}` }));
  }, [model, data, report]);

  const headline = model.headline;
  const headlineColor = severityColor(headline?.value ?? null);

  return (
    <div className="glass-panel scanlines flex h-full min-h-[520px] flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="panel-title mb-0">
          {mode === 'globe' ? '🌐 全球风险地球' : '🗺️ 全球风险平面图'}
        </div>
        <span className="chip text-white/45" title="仅地理维度上图；综合维度不投影；含事件触发式告警柱">
          地理维度 {allPoints.length}
        </span>

        {eventPoints.length > 0 && (
          <span
            className="chip"
            title="气候 / 灾害事件触发的地图告警柱（来自 grv_latest.json events[]）"
            style={{ borderColor: withAlpha('#f59e0b', 0.5), color: '#fbbf24' }}
          >
            ⚠ 事件 {eventPoints.length}
          </span>
        )}

        {headline && (
          <span
            className="chip"
            title={headline.note ?? '全球综合指数（无地理位置，不投影到地图）'}
            style={{ borderColor: withAlpha(headlineColor, 0.5), color: headlineColor }}
          >
            {headline.label} {fmtNum(headline.value)}
          </span>
        )}

        <div className="ml-auto flex items-center gap-1 rounded-full border border-white/10 bg-black/30 p-0.5">
          <button
            type="button"
            onClick={() => setMode('globe')}
            className={`rounded-full px-2.5 py-0.5 text-[11px] transition ${
              mode === 'globe' ? 'bg-accent/20 text-accent' : 'text-white/45 hover:text-white/75'
            }`}
            aria-pressed={mode === 'globe'}
          >
            🌐 3D
          </button>
          <button
            type="button"
            onClick={() => setMode('flat')}
            className={`rounded-full px-2.5 py-0.5 text-[11px] transition ${
              mode === 'flat' ? 'bg-accent/20 text-accent' : 'text-white/45 hover:text-white/75'
            }`}
            aria-pressed={mode === 'flat'}
          >
            🗺️ 平面
          </button>
        </div>
      </div>

      <div className="relative min-h-[400px] flex-1">
        <div
          className={`absolute inset-0 ${mode === 'globe' ? '' : 'pointer-events-none invisible'}`}
          aria-hidden={mode !== 'globe'}
        >
          <GlobePanel points={allPoints} arcs={arcs} active={mode === 'globe'} />
        </div>
        <div
          className={`absolute inset-0 ${mode === 'flat' ? '' : 'pointer-events-none invisible'}`}
          aria-hidden={mode !== 'flat'}
        >
          <FlatMapPanel points={allPoints} arcs={arcs} active={mode === 'flat'} />
        </div>

        {loading && (
          <div className="pointer-events-none absolute left-2 top-2 z-10 text-[11px] text-white/40">
            数据加载中…
          </div>
        )}
        {error && (
          <div className="absolute left-2 top-2 z-10 rounded-md border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
            GRV 读取失败：{error.message}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-white/50">
        {SEVERITY_LEGEND.map((l) => (
          <span key={l.level} className="flex items-center gap-1">
            <i
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: l.color, boxShadow: `0 0 8px ${withAlpha(l.color, 0.6)}` }}
            />
            {l.label}
          </span>
        ))}
        <span className="ml-auto text-white/30">
          {mode === 'globe' ? '拖拽旋转 · 滚轮缩放' : '悬停查看维度详情'}
        </span>
      </div>
    </div>
  );
}
