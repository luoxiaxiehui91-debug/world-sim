import { useCallback, useEffect, useRef, useState } from 'react';
import * as d3geo from 'd3-geo';
import * as d3zoom from 'd3-zoom';
import * as d3sel from 'd3-selection';
import * as topojson from 'topojson-client';
import worldAtlas from 'world-atlas/countries-110m.json';
import { MAP_THEME, withAlpha } from '@/config/theme';
import { regionBbox, type RegionKey } from '@/config/regions';
import {
  HIGHLIGHT_THRESHOLD,
  type RiskArc,
  type RiskPoint,
  pointTooltipHtml,
  arcTooltipHtml,
} from '@/lib/mapData';
import {
  siteScale,
  siteTooltipText,
  type StrategicSite,
} from '@/data/strategicSites';
import './FlatMapPanel.css';

/** 脉冲周期区间（秒）：weight 越高越快。 */
const PULSE_SLOW_S = 3.2;
const PULSE_FAST_S = 1.1;

/** 战略要地星形基准字体大小（px），再乘 siteScale(importance)。
 *  v1.10.3：14→16.8（×1.2）地缘要地图标加大。 */
const SITE_STAR_FONT = 16.8;

/** zoom 反向补偿指数（v1.10.4，crucix 半补偿：点随 zoom 按 1/√k 微缩放）。
 *  指数 1 = 完全恒定（旧行为：缩小后图标不缩小）；指数 0.5 = 半补偿
 *  （缩小后图标变小但比地图慢、保持可读；放大后变大但比地图慢、不膨胀）。
 *  观感不合适时调此常量即可。 */
const INV_SCALE_EXP = 0.5;

/** 大圆弧采样点数 */
const ARC_SAMPLES = 56;

export interface FlatMapPanelProps {
  points: RiskPoint[];
  arcs: RiskArc[];
  sites?: StrategicSite[];
  active?: boolean;
  region?: RegionKey;
  focusPointId?: string | null;
  onPointClick?: (point: RiskPoint) => void;
}

/** tooltip 定位信息 */
interface TooltipState {
  html: string;
  x: number;
  y: number;
}

/** 球面线性插值：沿大圆路径采样 [lng, lat] 坐标序列（d3-geo 约定：x=lng, y=lat）。 */
function greatCircleArc(
  lat1: number, lng1: number,
  lat2: number, lng2: number,
  samples: number = ARC_SAMPLES,
): [number, number][] {
  const toRad = Math.PI / 180;
  const φ1 = lat1 * toRad, λ1 = lng1 * toRad;
  const φ2 = lat2 * toRad, λ2 = lng2 * toRad;

  const Δφ = φ2 - φ1, Δλ = λ2 - λ1;
  const a = Math.sin(Δφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
  const δ = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  if (δ < 1e-12) return [[lng1, lat1], [lng2, lat2]];

  const sinδ = Math.sin(δ);
  const result: [number, number][] = [];
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const A = Math.sin((1 - t) * δ) / sinδ;
    const B = Math.sin(t * δ) / sinδ;
    const x = A * Math.cos(φ1) * Math.cos(λ1) + B * Math.cos(φ2) * Math.cos(λ2);
    const y = A * Math.cos(φ1) * Math.sin(λ1) + B * Math.cos(φ2) * Math.sin(λ2);
    const z = A * Math.sin(φ1) + B * Math.sin(φ2);
    const φ = Math.atan2(z, Math.sqrt(x * x + y * y));
    const λ = Math.atan2(y, x);
    result.push([λ / toRad, φ / toRad]);
  }
  return result;
}

/**
 * 把 [lng, lat] 数组用投影函数转换，在以下情况打断成多段：
 * 1. 投影返回 null（超出投影域）
 * 2. 相邻两点像素跨度超过 maxJump（应对 geoNaturalEarth1 边界点不返回 null 但坐标飞跃的情况）
 */
function projectArc(
  coords: [number, number][],
  proj: d3geo.GeoProjection,
  maxJump = 200,
): Array<[number, number][]> {
  const segments: Array<[number, number][]> = [];
  let cur: [number, number][] = [];
  for (const [lng, lat] of coords) {
    const pt = proj([lng, lat]);
    if (!pt) {
      if (cur.length >= 2) segments.push(cur);
      cur = [];
    } else {
      const p = pt as [number, number];
      if (cur.length > 0) {
        const prev = cur[cur.length - 1];
        const dx = Math.abs(p[0] - prev[0]);
        const dy = Math.abs(p[1] - prev[1]);
        if (dx > maxJump || dy > maxJump) {
          if (cur.length >= 2) segments.push(cur);
          cur = [];
        }
      }
      cur.push(p);
    }
  }
  if (cur.length >= 2) segments.push(cur);
  return segments;
}

export function FlatMapPanel({
  points,
  arcs,
  sites = [],
  active = true,
  region = 'world',
  focusPointId = null,
  onPointClick,
}: FlatMapPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const gRef = useRef<SVGGElement | null>(null);           // 变换容器（zoom target）
  const projRef = useRef<d3geo.GeoProjection | null>(null);
  const zoomRef = useRef<d3zoom.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  /** 把 MouseEvent 的 clientX/Y 转换为容器内相对坐标（规避 CSS transform 导致 fixed 定位偏移）*/
  const toContainerPos = useCallback((e: MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: e.clientX, y: e.clientY };
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);
  const transformRef = useRef<d3zoom.ZoomTransform>(d3zoom.zoomIdentity);
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);

  /**
   * tooltip 跟随 mousemove 的 rAF 节流（08-14 19:5x 用户反馈卡顿）：
   * 8000+ 点每个都挂 mousemove → setTooltip 的监听，鼠标扫过时每帧触发多次
   * React state 更新 → 整个 SVG 重渲染卡顿。合并到每帧最多一次 setTooltip。
   */
  const tooltipRafRef = useRef<number | null>(null);
  const pendingTooltipRef = useRef<{ x: number; y: number } | null>(null);
  const scheduleTooltipMove = useCallback((x: number, y: number) => {
    pendingTooltipRef.current = { x, y };
    if (tooltipRafRef.current !== null) return; // 本帧已有调度，合并
    tooltipRafRef.current = requestAnimationFrame(() => {
      tooltipRafRef.current = null;
      const pos = pendingTooltipRef.current;
      pendingTooltipRef.current = null;
      if (pos) {
        setTooltip(prev => (prev ? { ...prev, x: pos.x, y: pos.y } : null));
      }
    });
  }, []);
  useEffect(() => () => {
    if (tooltipRafRef.current !== null) cancelAnimationFrame(tooltipRafRef.current);
  }, []);

  /** 统一对现有点位 / 聚焦环 / 星标施加 zoom 反向补偿（v1.10.4 半补偿：1/√k）。
   *
   * 2026-08-11 v1.10.2 根治「缩放态下切分类 → 全部放大」：
   * 反向缩放此前只在 zoom 事件里施加；点组/聚焦环重建（切分类/点击）后新建元素
   * 不含反向缩放，而 .fm-root 的 zoom transform 仍在 → 按 k 倍渲染。现在 zoom 事件、
   * buildPoints 重建后、聚焦环重建后三个调用点共用本函数。
   *
   * v1.10.4：指数 1（完全恒定）→ INV_SCALE_EXP=0.5（crucix 半补偿，点随 zoom 微缩放）——
   * 缩小后图标变小（比地图慢、保持可读），放大后变大（比地图慢、不膨胀）。
   */
  const applyPointInvScale = useCallback(() => {
    const t = transformRef.current;
    if (!gRef.current) return;
    const invScale = t && t.k > 0 ? 1 / Math.pow(t.k, INV_SCALE_EXP) : 1;
    const root = d3sel.select(gRef.current);
    // 星标：字号反向缩放
    root.selectAll<SVGTextElement, unknown>('.fm-site-star').each(function() {
      const el = d3sel.select(this);
      const base = parseFloat(el.attr('data-fs') || '14');
      el.attr('font-size', base * invScale);
    });
    // 点位 group + 聚焦环：translate(cx,cy) scale(invScale)
    root.selectAll<SVGGElement, unknown>('.fm-point-group, .fm-focus-ring').each(function() {
      const el = d3sel.select(this);
      const cx = el.attr('data-cx');
      const cy = el.attr('data-cy');
      el.attr('transform', `translate(${cx},${cy}) scale(${invScale})`);
    });
  }, []);

  /* ── 容器尺寸监听 ────────────────────────────────────────── */

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setDims({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setDims({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  /* ── active 显隐控制 ─────────────────────────────────────── */

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.style.visibility = active ? '' : 'hidden';
  }, [active]);

  /* ── 投影 + 底图初始化（dims 就绪后执行一次）────────────── */

  useEffect(() => {
    if (!dims || dims.w <= 0 || dims.h <= 0) return;
    const { w, h } = dims;

    const proj = d3geo.geoNaturalEarth1().fitSize([w, h], { type: 'Sphere' });
    projRef.current = proj;

    const svgEl = svgRef.current;
    if (!svgEl) return;

    const svg = d3sel.select(svgEl);
    svg.attr('width', w).attr('height', h);

    // zoom 行为
    const zoom = d3zoom.zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, 12])
      .on('zoom', (event: d3zoom.D3ZoomEvent<SVGSVGElement, unknown>) => {
        const t = event.transform;
        transformRef.current = t;
        d3sel.select(gRef.current).attr('transform', t.toString());
        // 星标 + 点位 group + 聚焦环反向缩放，保持视觉尺寸固定（v1.10.2 抽公共函数）
        applyPointInvScale();
        setZoomLevel(Math.round(t.k * 10) / 10);
      });
    zoomRef.current = zoom;
    svg.call(zoom);
    svg.on('dblclick.zoom', () => {
      svg.call(zoom.transform, d3zoom.zoomIdentity);
    });

    // 底图：陆地填充
    const land = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.land,
    );
    const countries = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.countries,
    );
    const path = d3geo.geoPath(proj);

    const g = d3sel.select(gRef.current);

    // 海洋背景（Sphere）
    g.selectAll('.fm-ocean').data([null]).join('path')
      .attr('class', 'fm-ocean')
      .attr('d', path({ type: 'Sphere' } as d3geo.GeoPermissibleObjects) ?? '')
      .attr('fill', (MAP_THEME as any).flatOceanFill ?? '#060b16')
      .attr('stroke', 'none');

    // 陆地填充
    g.selectAll('.fm-land').data([null]).join('path')
      .attr('class', 'fm-land')
      .attr('d', path(land as d3geo.GeoPermissibleObjects) ?? '')
      .attr('fill', '#1a2332')
      .attr('stroke', 'none');

    // 国家边界线
    g.selectAll('.fm-borders').data([null]).join('path')
      .attr('class', 'fm-borders')
      .attr('d', path(countries as d3geo.GeoPermissibleObjects) ?? '')
      .attr('fill', 'none')
      .attr('stroke', '#3a5070')
      .attr('stroke-width', '0.4')
      .attr('stroke-opacity', '0.6');

    // 经纬网（轻淡格线）
    const graticule = d3geo.geoGraticule()();
    g.selectAll('.fm-graticule').data([null]).join('path')
      .attr('class', 'fm-graticule')
      .attr('d', path(graticule) ?? '')
      .attr('fill', 'none')
      .attr('stroke', '#1e2d42')
      .attr('stroke-width', '0.3')
      .attr('stroke-opacity', '0.5');

    // 确保数据层在底图之上
    const ensureLayer = (cls: string) => {
      if (!g.select('.' + cls).node()) g.append('g').attr('class', cls);
    };
    ensureLayer('fm-arcs-layer');
    ensureLayer('fm-points-layer');
    ensureLayer('fm-sites-layer');
    ensureLayer('fm-focus-layer');

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dims]);

  /* ── region → 重新 fitSize 并重置 zoom ────────────────────── */

  useEffect(() => {
    if (!dims || dims.w <= 0 || dims.h <= 0) return;
    const proj = projRef.current;
    const svg = svgRef.current;
    const zoom = zoomRef.current;
    if (!proj || !svg || !zoom) return;

    const { w, h } = dims;

    if (region === 'world') {
      proj.fitSize([w, h], { type: 'Sphere' });
    } else {
      const bbox = regionBbox(region);
      if (bbox) {
        const [minLng, minLat, maxLng, maxLat] = bbox;
        const geoRect: d3geo.GeoPermissibleObjects = {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[
              [minLng, minLat], [maxLng, minLat],
              [maxLng, maxLat], [minLng, maxLat],
              [minLng, minLat],
            ]],
          },
          properties: {},
        };
        proj.fitExtent([[20, 20], [w - 20, h - 20]], geoRect);
      }
    }

    // 重绘底图 path
    const g = d3sel.select(gRef.current);
    const path = d3geo.geoPath(proj);

    const land = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.land,
    );
    const countries = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.countries,
    );

    g.select('.fm-ocean').attr('d', path({ type: 'Sphere' } as d3geo.GeoPermissibleObjects) ?? '');
    g.select('.fm-land').attr('d', path(land as d3geo.GeoPermissibleObjects) ?? '');
    g.select('.fm-borders').attr('d', path(countries as d3geo.GeoPermissibleObjects) ?? '');
    g.select('.fm-graticule').attr('d', path(d3geo.geoGraticule()()) ?? '');

    // 重置 zoom（让数据层跟着更新）
    d3sel.select(svg).call(zoom.transform, d3zoom.zoomIdentity);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region, dims]);

  /* ── 弧线层 ─────────────────────────────────────────────── */

  useEffect(() => {
    const g = d3sel.select(gRef.current);
    const proj = projRef.current;
    if (!proj) return;

    const layer = g.select<SVGGElement>('.fm-arcs-layer');
    if (!layer.node()) return;

    // 每条弧线渲染为 <g> 内若干 <path> 段（投影断点处打断）
    const groups = layer.selectAll<SVGGElement, RiskArc>('.fm-arc-group')
      .data(arcs, (d) => d.id ?? `${d.startLat},${d.startLng},${d.endLat},${d.endLng}`);

    groups.exit().remove();

    const enter = groups.enter().append('g').attr('class', 'fm-arc-group');

    const merged = enter.merge(groups);

    merged.each(function(a) {
      const grp = d3sel.select(this);
      grp.selectAll('path').remove();

      if (isNaN(a.startLat) || isNaN(a.startLng) || isNaN(a.endLat) || isNaN(a.endLng)) return;

      const coords = greatCircleArc(a.startLat, a.startLng, a.endLat, a.endLng);
      const segments = projectArc(coords, proj);
      const strokeW = 0.9 + (a.intensity / 100) * 1.5;

      for (const seg of segments) {
        if (seg.length < 2) continue;
        const d = 'M' + seg.map(pt => pt.join(',')).join('L');
        grp.append('path')
          .attr('d', d)
          .attr('fill', 'none')
          .attr('stroke', a.startColor)
          .attr('stroke-width', strokeW)
          .attr('stroke-opacity', 0.75)
          .attr('stroke-linecap', 'round')
          .attr('class', 'fm-arc')
          .on('mouseenter', function(event: MouseEvent) {
            const pos = toContainerPos(event);
            setTooltip({ html: arcTooltipHtml(a), x: pos.x, y: pos.y });
          })
          .on('mousemove', function(event: MouseEvent) {
            const pos = toContainerPos(event);
            scheduleTooltipMove(pos.x, pos.y);
          })
          .on('mouseleave', () => setTooltip(null));
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arcs, dims]);

  /* ── 点位层 ─────────────────────────────────────────────── */

  const buildPoints = useCallback(() => {
    const g = d3sel.select(gRef.current);
    const proj = projRef.current;
    if (!proj) return;

    const layer = g.select<SVGGElement>('.fm-points-layer');
    if (!layer.node()) return;

    layer.selectAll('*').remove();

    for (const p of points) {
      if (isNaN(p.lat) || isNaN(p.lng)) continue;
      const px = proj([p.lng, p.lat]);
      if (!px) continue;
      const [cx, cy] = px;

      const missing = p.status === 'missing';
      // 2026-08-11 视觉重构（crucix 化）：中心大小 clamp[2.4,7.2]（v1.10.6 ×0.8 收窄），
      // 删除 ×1.25×1.5 双重放大；事件/高风险由外环脉冲区分，不再靠加大 core。
      // v1.10.7：再收窄 ×0.63 → clamp[1.6,4.6]（主理人"图标偏大"反馈第二轮；降噪目标 2D 普通点 ≤5px）
      // v1.10.8 聚合点：同地点合并后按 log2(count) 放大（clamp 5~9）以容纳计数徽标
      const isAgg = (p.aggCount ?? 0) > 1;
      const core = isAgg
        ? Math.min(9, Math.max(5, 4 + Math.log2(p.aggCount ?? 1) * 1.3))
        : Math.min(4.6, Math.max(1.6, 1.6 + p.weight * 3.0));
      const highlight =
        !missing && ((p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent === true || isAgg);
      const pulseSec = (PULSE_SLOW_S - p.weight * (PULSE_SLOW_S - PULSE_FAST_S)).toFixed(2);
      const fillColor = missing ? withAlpha(p.color, 0.18) : p.color;
      const strokeColor = missing ? p.color : withAlpha('#ffffff', 0.35);
      const strokeW = missing ? 1 : 0.5;

      const grp = layer.append('g')
        .attr('class', 'fm-point-group')
        .attr('data-cx', cx)
        .attr('data-cy', cy)
        .attr('transform', `translate(${cx},${cy})`)
        .attr('cursor', onPointClick ? 'pointer' : 'default');

      if (p.shape === 'diamond') {
        const r = core * 1.4;
        // 子元素画在原点
        const pts = `0,${-r} ${r},0 0,${r} ${-r},0`;
        const poly = grp.append('polygon')
          .attr('points', pts)
          .attr('fill', fillColor)
          .attr('stroke', strokeColor)
          .attr('stroke-width', strokeW)
          .attr('fill-opacity', 0.85);

        if (missing) {
          poly.attr('stroke-dasharray', '2.5 2').attr('stroke-opacity', 0.85).attr('fill-opacity', 0.18);
        } else if (highlight) {
          poly.attr('class', 'fm-point-pulse').style('--ky-pulse-duration', `${pulseSec}s`);
        }
      } else if (p.shape === 'arrow') {
        // 08-14 空域活动图层（air）：只画航向箭头、不画圆点圈（用户拍板：有箭头就不需要圈）。
        // SVG transform rotate 顺时针 = 航向 0-360 从北，近似可用；
        // direction 缺失时箭头朝北（后端 track 100% 有值，兜底防点消失）。
        grp.append('path')
          .attr('d', 'M 6 0 L -2.5 -3 L -0.8 0 L -2.5 3 Z')
          .attr('fill', withAlpha(p.color, 0.9))
          .attr(
            'transform',
            typeof p.direction === 'number' && Number.isFinite(p.direction)
              ? `rotate(${p.direction})`
              : '', // 空 transform = 箭头朝北（d3 attr 不接受 undefined）
          )
          .attr('pointer-events', 'none');
      } else if (p.shape === 'dot') {
        // 08-14 海量点简化渲染（thermal/sdr）：只画核心圆，无外环/光晕。
        // 点数大（数千）时每点省 2 个 SVG 元素，配合 tooltip rAF 节流防卡顿（用户反馈）。
        // v1.11.5：core 用普通点公式（1.6~4.6px）而非聚合放大（5~9px）——用户反馈「圆太大」。
        // v1.11.6：去掉中心计数徽标（用户反馈「数字去掉」）——密集区数字糊成一片，
        // 火点数信息移到 hover tooltip（note 已含 count / FRP / 高置信）。
        const dotCore = Math.min(4.6, Math.max(1.6, 1.6 + p.weight * 3.0));
        const dot = grp.append('circle')
          .attr('cx', 0).attr('cy', 0).attr('r', dotCore)
          .attr('fill', fillColor).attr('stroke', strokeColor).attr('stroke-width', strokeW)
          .attr('fill-opacity', 0.85);
        if (missing) {
          dot.attr('stroke-dasharray', '2.5 2').attr('stroke-opacity', 0.85).attr('fill-opacity', 0.18);
        }
      } else {
        // 弧光（2026-08-11 视觉重构 crucix 化）：薄描边环贴附外侧 + 内层淡光晕 + 中心实体。
        // v1.10.3 弧光收窄：外环 r 2.2→1.8 更贴附、线宽 1.2→1.0、透明度 0.6→0.5。
        if (!missing) {
          // 外环：薄描边环贴附（crucix ACLED 冲突点式），脉冲仅此层
          const ring = grp.append('circle')
            .attr('cx', 0).attr('cy', 0).attr('r', core * 1.5)
            .attr('fill', 'none')
            .attr('stroke', withAlpha(p.color, 0.5))
            .attr('stroke-width', 1.0)
            .attr('pointer-events', 'none');
          if (highlight) {
            ring.attr('class', 'fm-ring-pulse').style('--ky-pulse-duration', `${pulseSec}s`);
          }
          // 内层过渡：很淡的贴附光晕（非实心大圈）
          grp.append('circle')
            .attr('cx', 0).attr('cy', 0).attr('r', core * 1.2)
            .attr('fill', withAlpha(p.color, 0.10))
            .attr('stroke', 'none')
            .attr('pointer-events', 'none');
        }

        const circle = grp.append('circle')
          .attr('cx', 0).attr('cy', 0).attr('r', core)
          .attr('fill', fillColor).attr('stroke', strokeColor).attr('stroke-width', strokeW)
          .attr('fill-opacity', 0.75);

        if (missing) {
          circle.attr('stroke-dasharray', '2.5 2').attr('stroke-opacity', 0.85).attr('fill-opacity', 0.18);
        }
        // 中心稳定：核心不加脉冲（脉冲只动外环）
        // v1.10.8 聚合点：中心叠加白色计数徽标（同地点事件数；pointer-events none 不挡点击）
        if (isAgg) {
          grp.append('text')
            .attr('x', 0).attr('y', 0)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'central')
            .attr('fill', '#ffffff')
            .attr('font-size', Math.max(6.5, core * 0.85))
            .attr('font-weight', 600)
            .attr('pointer-events', 'none')
            .style('user-select', 'none')
            .text(String(p.aggCount));
        }
      }

      grp
        .on('mouseenter', function(event: MouseEvent) {
          const pos = toContainerPos(event);
          setTooltip({ html: pointTooltipHtml(p), x: pos.x, y: pos.y });
        })
        .on('mousemove', function(event: MouseEvent) {
          const pos = toContainerPos(event);
          scheduleTooltipMove(pos.x, pos.y);
        })
        .on('mouseleave', () => {
          pendingTooltipRef.current = null;
          setTooltip(null);
        })
        .on('click', () => onPointClick?.(p));
    }
    // v1.10.2：重建后的新点组补上 zoom 反向缩放（根治缩放态切分类 → 全部放大）
    applyPointInvScale();
  }, [points, dims, onPointClick, applyPointInvScale, scheduleTooltipMove]);

  useEffect(() => {
    buildPoints();
  }, [buildPoints]);

  /* ── 战略要地层 ──────────────────────────────────────────── */

  useEffect(() => {
    const g = d3sel.select(gRef.current);
    const proj = projRef.current;
    if (!proj) return;

    const layer = g.select<SVGGElement>('.fm-sites-layer');
    if (!layer.node()) return;

    layer.selectAll('*').remove();

    for (const s of sites) {
      if (isNaN(s.lat) || isNaN(s.lng)) continue;
      const px = proj([s.lng, s.lat]);
      if (!px) continue;
      const [cx, cy] = px;
      const fontSize = SITE_STAR_FONT * siteScale(s.importance);

      layer.append('text')
        .attr('x', cx).attr('y', cy)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'central')
        .attr('font-size', fontSize)
        .attr('data-fs', fontSize)
        .attr('fill', '#fbbf24')
        .attr('class', 'fm-site-star')
        .attr('cursor', 'pointer')
        .text('★')
        .on('mouseenter', function(event: MouseEvent) {
          const pos = toContainerPos(event);
          setTooltip({ html: `<span>${siteTooltipText(s)}</span>`, x: pos.x, y: pos.y });
        })
        .on('mousemove', function(event: MouseEvent) {
          const pos = toContainerPos(event);
          setTooltip(prev => prev ? { ...prev, x: pos.x, y: pos.y } : null);
        })
        .on('mouseleave', () => setTooltip(null));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sites, dims]);

  /* ── 聚焦光环层 ──────────────────────────────────────────── */

  useEffect(() => {
    const g = d3sel.select(gRef.current);
    const proj = projRef.current;
    if (!proj) return;

    const layer = g.select<SVGGElement>('.fm-focus-layer');
    if (!layer.node()) return;

    layer.selectAll('*').remove();

    if (focusPointId === null) return;
    const target = points.find((p) => p.id === focusPointId);
    if (!target || isNaN(target.lat) || isNaN(target.lng)) return;

    const px = proj([target.lng, target.lat]);
    if (!px) return;
    const [cx, cy] = px;

    // 2026-08-11 视觉重构：聚焦环收敛到 core×2.4（旧 halo×1.35≈46px 过大）；v1.10.6 core ×0.8
    // v1.10.7：core 同步普通点新公式（1.6+3w），聚焦环乘数 ×2.0 下限 8（与普通点环/星标同量级）
    // v1.10.8：聚合点聚焦环对齐聚合尺寸（同地图点渲染公式）
    const isAgg = (target.aggCount ?? 0) > 1;
    const core = isAgg
      ? Math.min(9, Math.max(5, 4 + Math.log2(target.aggCount ?? 1) * 1.3))
      : Math.min(4.6, Math.max(1.6, 1.6 + target.weight * 3.0));
    const focusR = Math.max(core * 2.0, 8);

    layer.append('g')
      .attr('class', 'fm-focus-ring')
      .attr('data-cx', cx)
      .attr('data-cy', cy)
      .attr('transform', `translate(${cx},${cy})`)
      .append('circle')
        .attr('cx', 0).attr('cy', 0).attr('r', focusR)
        .attr('fill', 'none')
        .attr('stroke', withAlpha(target.color, 0.9))
        .attr('stroke-width', 1.2)
        .attr('stroke-dasharray', '3 3')
        .attr('pointer-events', 'none')
        .attr('class', 'animate-pulseSoft');
    // v1.10.2：聚焦环重建后补上 zoom 反向缩放（根治缩放态点击 → 超大聚焦环）
    applyPointInvScale();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusPointId, points, dims, applyPointInvScale]);

  /* ── active=false 时清 tooltip ───────────────────────────── */

  useEffect(() => {
    if (!active) setTooltip(null);
  }, [active]);

  /* ── 渲染 ──────────────────────────────────────────────── */

  return (
    <div
      ref={containerRef}
      className="flat-map-container"
      style={{ background: MAP_THEME.flatOceanFill }}
    >
      <svg ref={svgRef} className="fm-svg" style={{ width: '100%', height: '100%', display: 'block' }}>
        <g ref={gRef} className="fm-root" />
      </svg>

      {/* 缩放级别指示器 */}
      <div className="leaflet-zoom-indicator">z={zoomLevel}</div>

      {/* tooltip */}
      {tooltip && (
        <div
          className="fm-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
          dangerouslySetInnerHTML={{ __html: tooltip.html }}
        />
      )}
    </div>
  );
}
