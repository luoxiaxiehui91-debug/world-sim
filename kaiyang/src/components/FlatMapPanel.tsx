import { useEffect, useMemo, useRef, useState } from 'react';
import {
  geoEquirectangular,
  geoGraticule10,
  geoInterpolate,
  geoPath,
  type GeoPermissibleObjects,
  type GeoProjection,
  type GeoSphere,
} from 'd3-geo';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry } from 'geojson';
import type { GeometryCollection, Topology } from 'topojson-specification';
import { MAP_THEME, PALETTE, withAlpha } from '@/config/theme';
import { HIGHLIGHT_THRESHOLD, type RiskArc, type RiskPoint } from '@/lib/mapData';
import { fmtNum } from '@/lib/format';

/**
 * 2D 平面世界地图视图（d3-geo + topojson-client + world-atlas，均为 MIT/ISC）。
 * 与 3D 地球共用同一份点位/弧线数据与配色（lib/mapData.ts），信息密度更高、一眼看全。
 *
 * 离线：国界数据取自 world-atlas 的 countries-110m.json，已随包拷贝到 public/assets/，
 * 运行时按相对路径读取，不依赖任何外网 CDN。
 */

/** world-atlas countries-110m（构建产物内的静态资源，相对路径，离线可用）。 */
const WORLD_TOPO_URL = `${import.meta.env.BASE_URL}assets/countries-110m.json`;

export interface FlatMapPanelProps {
  points: RiskPoint[];
  arcs: RiskArc[];
  /** 当前是否为可见视图；隐藏时清除 hover 状态（默认 true） */
  active?: boolean;
}

interface Size {
  width: number;
  height: number;
}

interface HoverState {
  point: RiskPoint;
  x: number;
  y: number;
}

const SPHERE: GeoSphere = { type: 'Sphere' };
const PADDING = 6;
/** 大圆弧采样点数 */
const ARC_SAMPLES = 56;

/** 把大圆弧投影成若干条折线（跨 180° 经线处断开，避免横穿整幅地图）。 */
function buildArcPolylines(projection: GeoProjection, arc: RiskArc, width: number): string[] {
  const interpolate = geoInterpolate([arc.startLng, arc.startLat], [arc.endLng, arc.endLat]);
  const segments: string[] = [];
  let current: string[] = [];
  let prevX: number | null = null;

  for (let i = 0; i <= ARC_SAMPLES; i++) {
    const [lng, lat] = interpolate(i / ARC_SAMPLES);
    const projected = projection([lng, lat]);
    if (!projected) {
      if (current.length > 1) segments.push(current.join(' '));
      current = [];
      prevX = null;
      continue;
    }
    const [x, y] = projected;
    if (prevX !== null && Math.abs(x - prevX) > width / 2) {
      if (current.length > 1) segments.push(current.join(' '));
      current = [];
    }
    current.push(`${current.length === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`);
    prevX = x;
  }
  if (current.length > 1) segments.push(current.join(' '));
  return segments;
}

export function FlatMapPanel({ points, arcs, active = true }: FlatMapPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const [land, setLand] = useState<FeatureCollection<Geometry> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  // 容器尺寸跟踪
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const apply = () => {
      const width = el.clientWidth || el.parentElement?.clientWidth || 0;
      const height = el.clientHeight || el.parentElement?.clientHeight || 0;
      setSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    const raf = requestAnimationFrame(apply);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  // 国界拓扑加载（失败时降级为「只有经纬网格 + 点位」的地图，不阻断渲染）
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const res = await fetch(WORLD_TOPO_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const topo = (await res.json()) as Topology;
        if (cancelled) return;
        const countries = topo.objects?.countries as GeometryCollection | undefined;
        if (!countries) throw new Error('countries 图层缺失');
        const fc = feature(topo, countries) as unknown as FeatureCollection<Geometry>;
        setLand(fc);
        setLoadError(null);
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  // 切走时清掉悬停卡片，避免隐藏视图残留提示
  useEffect(() => {
    if (!active) setHover(null);
  }, [active]);

  const { width, height } = size;

  const projection = useMemo<GeoProjection | null>(() => {
    if (width <= 0 || height <= 0) return null;
    return geoEquirectangular().fitExtent(
      [
        [PADDING, PADDING],
        [width - PADDING, height - PADDING],
      ],
      SPHERE,
    );
  }, [width, height]);

  const pathGen = useMemo(() => (projection ? geoPath(projection) : null), [projection]);

  const spherePath = useMemo(
    () => (pathGen ? pathGen(SPHERE as unknown as GeoPermissibleObjects) ?? '' : ''),
    [pathGen],
  );

  const graticulePath = useMemo(
    () => (pathGen ? pathGen(geoGraticule10() as unknown as GeoPermissibleObjects) ?? '' : ''),
    [pathGen],
  );

  const landPaths = useMemo<string[]>(() => {
    if (!pathGen || !land) return [];
    const out: string[] = [];
    for (const f of land.features) {
      const d = pathGen(f as unknown as GeoPermissibleObjects);
      if (d) out.push(d);
    }
    return out;
  }, [pathGen, land]);

  const arcPaths = useMemo(() => {
    if (!projection || width <= 0) return [];
    return arcs.flatMap((a) =>
      buildArcPolylines(projection, a, width).map((d, i) => ({
        key: `${a.id}-${i}`,
        d,
        arc: a,
      })),
    );
  }, [projection, arcs, width]);

  const projectedPoints = useMemo(() => {
    if (!projection) return [];
    return points.flatMap((p) => {
      const xy = projection([p.lng, p.lat]);
      if (!xy) return [];
      return [{ point: p, x: xy[0], y: xy[1] }];
    });
  }, [projection, points]);

  const ready = width > 0 && height > 0 && projection !== null;

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden rounded-xl"
      style={{ background: MAP_THEME.flatOceanFill }}
    >
      {ready && (
        <svg width={width} height={height} role="img" aria-label="全球风险平面地图">
          <defs>
            {arcs.map((a) => (
              <linearGradient key={`grad-${a.id}`} id={`arc-grad-${a.id}`} x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={a.startColor} stopOpacity={0.9} />
                <stop offset="100%" stopColor={a.endColor} stopOpacity={0.9} />
              </linearGradient>
            ))}
            <radialGradient id="flat-ocean-glow" cx="50%" cy="50%" r="60%">
              <stop offset="0%" stopColor={withAlpha(PALETTE.cyan, 0.1)} />
              <stop offset="100%" stopColor="rgba(0,0,0,0)" />
            </radialGradient>
          </defs>

          {/* 海洋 + 球体边界辉光 */}
          <path d={spherePath} fill="url(#flat-ocean-glow)" stroke={withAlpha(PALETTE.cyan, 0.25)} strokeWidth={1} />
          {/* 经纬网格 */}
          <path d={graticulePath} fill="none" stroke={MAP_THEME.flatGraticule} strokeWidth={0.5} />
          {/* 陆地 */}
          <g>
            {landPaths.map((d, i) => (
              <path
                key={`land-${i}`}
                d={d}
                fill={MAP_THEME.flatLandFill}
                stroke={MAP_THEME.flatLandStroke}
                strokeWidth={0.5}
              />
            ))}
          </g>
          {/* 地缘联动弧线（与 3D 同源同色，虚线流动） */}
          <g>
            {arcPaths.map(({ key, d, arc }) => (
              <path
                key={key}
                d={d}
                className="flat-arc"
                fill="none"
                stroke={`url(#arc-grad-${arc.id})`}
                strokeWidth={0.9 + (arc.intensity / 100) * 1.5}
                strokeLinecap="round"
                opacity={0.75}
              >
                <title>{`${arc.fromLabel} ↔ ${arc.toLabel} · 联动强度 ${fmtNum(arc.intensity, 0)}`}</title>
              </path>
            ))}
          </g>
          {/* 风险点位（光晕 + 核心点 + 高风险常驻标签） */}
          <g>
            {projectedPoints.map(({ point: p, x, y }) => {
              // 事件告警柱略放大以示告警感
              const core = (2.6 + p.weight * 3.4) * (p.isEvent ? 1.25 : 1);
              const halo = core * 3.2;
              const highlight = (p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent === true;
              return (
                <g
                  key={p.id}
                  onMouseEnter={() => setHover({ point: p, x, y })}
                  onMouseLeave={() => setHover(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <circle cx={x} cy={y} r={halo} fill={withAlpha(p.color, 0.14)} />
                  <circle cx={x} cy={y} r={core * 1.8} fill={withAlpha(p.color, 0.22)} />
                  <circle
                    cx={x}
                    cy={y}
                    r={core}
                    fill={p.color}
                    stroke={withAlpha('#ffffff', 0.5)}
                    strokeWidth={0.6}
                    className={highlight ? 'flat-point-pulse' : undefined}
                  />
                  {highlight && (
                    <text
                      x={x + halo + 3}
                      y={y + 3}
                      fill={p.color}
                      fontSize={10}
                      style={{ pointerEvents: 'none', textShadow: `0 0 6px ${withAlpha(p.color, 0.6)}` }}
                    >
                      {p.isEvent ? '⚠ ' : ''}
                      {p.label} {p.value === null ? '—' : p.value.toFixed(0)}
                    </text>
                  )}
                  <title>
                    {p.isEvent
                      ? `⚠ 事件 ${p.label} · 严重度 ${fmtNum(p.value)}${p.note ? ` · ${p.note}` : ''}`
                      : `${p.label} · ${p.value === null ? '数据缺失' : fmtNum(p.value)}`}
                  </title>
                </g>
              );
            })}
          </g>
        </svg>
      )}

      {/* hover 提示卡 */}
      {hover && (
        <div
          className="pointer-events-none absolute z-20 rounded-lg px-2.5 py-1.5 text-[11px] leading-relaxed"
          style={{
            left: Math.min(Math.max(hover.x + 12, 8), Math.max(8, width - 190)),
            top: Math.min(Math.max(hover.y - 46, 8), Math.max(8, height - 74)),
            background: 'rgba(6,11,22,0.92)',
            border: `1px solid ${withAlpha(hover.point.color, 0.55)}`,
            boxShadow: `0 0 18px ${withAlpha(hover.point.color, 0.28)}`,
            color: PALETTE.text,
            minWidth: 150,
          }}
        >
          <div className="font-semibold" style={{ color: hover.point.color }}>
            {hover.point.isEvent ? '⚠ ' : ''}
            {hover.point.label}
            <span className="ml-1.5 text-[10px] font-normal text-white/40">
              {hover.point.isEvent ? `事件类型：${hover.point.group}` : hover.point.group}
            </span>
          </div>
          <div>
            {hover.point.isEvent ? '事件严重度' : '风险值'}{' '}
            <b>{hover.point.value === null ? '数据缺失' : fmtNum(hover.point.value)}</b> · 等级{' '}
            {hover.point.severity}
          </div>
          {hover.point.isEvent ? (
            hover.point.note && <div className="text-white/50">详情：{hover.point.note}</div>
          ) : (
            <div className="text-white/50">
              不确定区间{' '}
              {hover.point.value === null || hover.point.uncertainty === null
                ? '未知'
                : `±${fmtNum(hover.point.uncertainty)}${hover.point.uncertaintyEstimated ? '（估算）' : ''}`}
            </div>
          )}
        </div>
      )}

      {loadError && (
        <div className="absolute bottom-2 left-2 z-10 rounded-md border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
          国界数据加载失败（{loadError}），已降级为网格视图
        </div>
      )}
    </div>
  );
}
