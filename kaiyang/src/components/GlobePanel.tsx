import { useEffect, useRef, useState } from 'react';
import Globe from 'globe.gl';
import { MAP_THEME, PALETTE, withAlpha } from '@/config/theme';
import {
  HIGHLIGHT_THRESHOLD,
  arcTooltipHtml,
  pointTooltipHtml,
  type RiskArc,
  type RiskPoint,
} from '@/lib/mapData';

export interface GlobePanelProps {
  /** 地图点位（已由上层过滤掉 composite 维度） */
  points: RiskPoint[];
  /** 地缘联动弧线 */
  arcs: RiskArc[];
  /** 当前是否为可见视图；隐藏时停止自动旋转以省电（默认 true） */
  active?: boolean;
}

/**
 * 3D 地球视图（globe.gl / three r0.185.1）。
 * 展示组件：数据由 WorldPanel 统一构建后传入，与平面地图共用同一份点位/弧线。（开阳整体为操作面板，含向各后端下发受控指令的职能，详见 DESIGN.md / DATA_CONTRACT.md）
 *
 * 视觉：本地星空背景 + 加厚青绿大气 + 经纬网格 + 渐变粗弧线 + 光环点位 + 高风险常驻标签。
 * 兼容性：所有非核心 API（graticules / rings / htmlElements）均做能力探测，缺失时静默降级，
 * 保证任何 globe.gl 版本差异都不会打断渲染循环。
 */
export function GlobePanel({ points, arcs, active = true }: GlobePanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // globe.gl 无官方 TS 类型，统一按 any 处理（保持与既有实现一致）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 初始化 3D 地球。带显式尺寸、ResizeObserver 兜底与错误可见化。
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let world: any;
    try {
      // 规范初始化：new Globe(el)。显式设置宽高，避免容器初始 0 尺寸导致 canvas 0 像素。
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      world = new Globe(el) as any;
      globeRef.current = world;

      const applySize = () => {
        // 优先用容器自身尺寸；若首帧为 0（布局未稳），回退到父级，避免 0×0。
        const w = el.clientWidth || el.parentElement?.clientWidth || 0;
        const h = el.clientHeight || el.parentElement?.clientHeight || 0;
        if (w > 0 && h > 0 && globeRef.current) {
          globeRef.current.width(w).height(h);
        }
      };

      world
        .backgroundColor('rgba(0,0,0,0)')
        .showGlobe(true)
        .showAtmosphere(true)
        .atmosphereColor(MAP_THEME.atmosphereColor)
        .atmosphereAltitude(MAP_THEME.atmosphereAltitude)
        .globeImageUrl(MAP_THEME.earthTextureUrl)
        .bumpImageUrl(MAP_THEME.earthBumpUrl)
        .pointOfView({ lat: 22, lng: 70, altitude: 2.4 }, 0);

      // 星空深空背景（本地贴图，离线可用）。加载失败时下方 CSS 深空渐变兜底。
      if (typeof world.backgroundImageUrl === 'function') {
        world.backgroundImageUrl(MAP_THEME.starFieldUrl);
      }
      // 经纬网格（科技感）
      if (typeof world.showGraticules === 'function') {
        world.showGraticules(true);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const controls = world.controls() as any;
      if (controls) {
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.35;
        controls.enableZoom = true;
      }

      applySize();
      const ro = new ResizeObserver(applySize);
      ro.observe(el);
      resizeObserverRef.current = ro;
      // rAF 兜底：下一帧布局确定后再校正一次，杜绝初始 0 尺寸。
      const raf = requestAnimationFrame(applySize);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (el as any).__globeRaf = raf;
    } catch (err) {
      // 初始化抛错不再静默：把错误渲染到面板内，便于定位。
      setError(err instanceof Error ? err.message : String(err));
      globeRef.current = null;
      return;
    }

    return () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const raf = (el as any).__globeRaf;
      if (typeof raf === 'number') cancelAnimationFrame(raf);
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const w = globeRef.current as any;
      try {
        if (w && typeof w._destructor === 'function') w._destructor();
      } catch {
        /* 忽略销毁异常 */
      }
      if (el) el.innerHTML = '';
      globeRef.current = null;
    };
  }, []);

  // 视图切到平面地图时停止自动旋转（保持 WebGL 上下文存活，避免反复创建/销毁）
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const world = globeRef.current as any;
    if (!world || typeof world.controls !== 'function') return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const controls = world.controls() as any;
      if (controls) controls.autoRotate = active;
    } catch {
      /* 控件不可用时忽略 */
    }
  }, [active]);

  // 数据驱动：风险点位 + 光环 + 常驻标签 + 地缘联动弧线
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const world = globeRef.current as any;
    if (!world) return;

    try {
      world
        .pointsData(points)
        .pointLat('lat')
        .pointLng('lng')
        .pointColor('color')
        .pointAltitude((p: RiskPoint) => (p.value === null ? 0.01 : 0.03 + p.weight * 0.17))
        .pointRadius((p: RiskPoint) => (p.value === null ? 0.3 : 0.4 + p.weight * 0.25))
        .pointLabel((p: RiskPoint) => pointTooltipHtml(p))
        .arcsData(arcs)
        .arcStartLat('startLat')
        .arcStartLng('startLng')
        .arcEndLat('endLat')
        .arcEndLng('endLng')
        .arcColor((a: RiskArc) => [
          withAlpha(a.startColor, 0.95),
          withAlpha(a.endColor, 0.95),
        ])
        .arcAltitudeAutoScale(MAP_THEME.arcAltitudeAutoScale)
        .arcStroke((a: RiskArc) => MAP_THEME.arcStroke * (0.75 + (a.intensity / 100) * 0.6))
        .arcDashLength(0.42)
        .arcDashGap(0.16)
        .arcDashAnimateTime((a: RiskArc) => 2600 - Math.min(1200, a.intensity * 12))
        .arcLabel((a: RiskArc) => arcTooltipHtml(a));

      // 高风险点位脉冲光环（能力探测，缺失则跳过）；事件告警柱始终带光环
      if (typeof world.ringsData === 'function') {
        const rings = points.filter((p) => (p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent);
        world
          .ringsData(rings)
          .ringLat('lat')
          .ringLng('lng')
          .ringColor((p: RiskPoint) => (t: number) => withAlpha(p.color, Math.max(0, 1 - t) * 0.55))
          .ringMaxRadius((p: RiskPoint) => 3 + p.weight * 3)
          .ringPropagationSpeed(1.6)
          .ringRepeatPeriod(1100);
      }

      // 高风险常驻发光标签（CSS2D 层，能力探测）；事件告警柱始终带标签
      if (typeof world.htmlElementsData === 'function') {
        const labeled = points.filter((p) => (p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent);
        world
          .htmlElementsData(labeled)
          .htmlLat('lat')
          .htmlLng('lng')
          .htmlAltitude((p: RiskPoint) => 0.06 + p.weight * 0.17)
          .htmlElement((p: RiskPoint) => {
            const div = document.createElement('div');
            div.className = 'globe-tag';
            div.style.color = p.color;
            div.style.borderColor = withAlpha(p.color, 0.5);
            div.style.boxShadow = `0 0 12px ${withAlpha(p.color, 0.35)}`;
            div.textContent = `${p.isEvent ? '⚠ ' : ''}${p.label} ${p.value === null ? '—' : p.value.toFixed(0)}`;
            return div;
          });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [points, arcs]);

  return (
    <div ref={containerRef} className="globe-stage relative h-full w-full overflow-hidden rounded-xl">
      {error && (
        <div className="absolute inset-0 z-10 flex items-center justify-center p-4">
          <div
            className="rounded-lg border px-4 py-3 text-center text-sm"
            style={{
              borderColor: withAlpha(PALETTE.red, 0.5),
              background: withAlpha(PALETTE.red, 0.12),
              color: PALETTE.red,
            }}
          >
            地球渲染失败：{error}
          </div>
        </div>
      )}
    </div>
  );
}
