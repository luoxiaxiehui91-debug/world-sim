import { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
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

/**
 * 2D 平面世界地图视图（Leaflet 原生渲染，Wave 2 1.7.0 迁移自 d3-geo + SVG）。
 *
 * 与 3D 地球共用同一份点位/弧线数据与配色（lib/mapData.ts），信息密度更高、一眼看全。
 *
 * ⚠ 渲染器只读约定（K6）：本组件**只直读** `p.color / p.weight / p.shape / p.status`，
 * 不 import `config/layerCategories`。类别 → 色/形/强度的换算全部在构建层完成，
 * 保证与 3D 地球观感严格一致。
 */

/** 脉冲周期区间（秒）：weight 越高越快，对应「强度 = 脉冲速率」这一半双轴。 */
const PULSE_SLOW_S = 3.2;
const PULSE_FAST_S = 1.1;

/** 要地星形符号基准外接半径（像素），再乘 siteScale(importance)。 */
const SITE_STAR_RADIUS = 4.4;

/** 大圆弧采样点数 */
const ARC_SAMPLES = 56;

export interface FlatMapPanelProps {
  points: RiskPoint[];
  arcs: RiskArc[];
  /** 战略要地叠加层（独立于类别色轴；上层关掉开关时传空数组） */
  sites?: StrategicSite[];
  /** 当前是否为可见视图；隐藏时清除 hover 状态（默认 true） */
  active?: boolean;
  /** 地区取景（R-P1-02）：`world` 用整球 fitBounds，其余按 bbox 矩形 flyToBounds（默认 world） */
  region?: RegionKey;
  /** 聚焦点位 id（R-P1-03）：命中点加一圈聚焦光环；null = 不聚焦 */
  focusPointId?: string | null;
  /** 点击点位回调（供上层反向选中；未传则点位不可点击） */
  onPointClick?: (point: RiskPoint) => void;
}

/**
 * 球面线性插值：在两点之间沿大圆路径采样，生成折线坐标序列。
 * 效果与 d3-geo 的 `geoInterpolate` 等价。
 */
function greatCircleArc(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
  samples: number = ARC_SAMPLES,
): [number, number][] {
  const toRad = Math.PI / 180;
  const φ1 = lat1 * toRad;
  const λ1 = lng1 * toRad;
  const φ2 = lat2 * toRad;
  const λ2 = lng2 * toRad;

  // 球面角距
  const Δφ = φ2 - φ1;
  const Δλ = λ2 - λ1;
  const a = Math.sin(Δφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
  const δ = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  if (δ < 1e-12) {
    // 两点几乎重合，直接返回直线
    return [
      [lat1, lng1],
      [lat2, lng2],
    ];
  }

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
    result.push([φ / toRad, λ / toRad]);
  }
  return result;
}

/**
 * 将像素半径转换为地理度数偏移（在指定纬度处）。
 * Web Mercator 投影下 longitude 度/像素 = 360 / (256 * 2^z)，
 * latitude 近似相同（对小符号可忽略 Mercator 纬向拉伸）。
 */
function pixelToDeg(pixelRadius: number, zoom: number): number {
  if (isNaN(zoom) || zoom <= 0) return pixelRadius * (360 / 256);
  return pixelRadius * (360 / (256 * Math.pow(2, zoom)));
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
  const mapRef = useRef<L.Map | null>(null);
  const pointLayerRef = useRef<L.LayerGroup | null>(null);
  const arcLayerRef = useRef<L.LayerGroup | null>(null);
  const siteLayerRef = useRef<L.LayerGroup | null>(null);
  const focusRingRef = useRef<L.LayerGroup | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(3);
  const [mapReady, setMapReady] = useState(false);
  const zoomLevelRef = useRef<number>(3);

  /* ── 地图初始化 ──────────────────────────────────────────── */

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let mapForCleanup: L.Map | null = null;
    let ro: ResizeObserver | null = null;

    try {
    const map = L.map(el, {
      center: [22, 70],
      zoom: 3,
      minZoom: 2,
      maxZoom: 8,
      zoomControl: true,
      attributionControl: false,
    });

    if (!map) throw new Error('L.map 返回 null');
    mapForCleanup = map;

    // 离线 GeoJSON 底图（world-atlas Natural Earth 110m，无需外网）
    // 替代 CARTO tile layer，解决内网环境图块缺失问题
    const landGeo = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.land,
    );
    const countriesGeo = topojson.feature(
      worldAtlas as unknown as Parameters<typeof topojson.feature>[0],
      (worldAtlas as any).objects.countries,
    );

    // 修复 antimeridian wrapping：world-atlas 中俄罗斯/美国阿拉斯加等多边形跨越 ±180°，
    // Leaflet 会画出横穿地图的错误连线。将经度 clip 到 [-180, 180] 消除视觉错误。
    function clipGeoJSON(geo: GeoJSON.FeatureCollection): GeoJSON.FeatureCollection {
      const clampLng = (lng: number) => Math.max(-180, Math.min(180, lng));
      function clipCoord(c: number[]): number[] { return [clampLng(c[0]), c[1]]; }
      function clipRing(ring: number[][]): number[][] { return ring.map(clipCoord); }
      function clipGeom(geom: GeoJSON.Geometry): GeoJSON.Geometry {
        if (geom.type === 'Polygon') return { ...geom, coordinates: geom.coordinates.map(clipRing) };
        if (geom.type === 'MultiPolygon') return { ...geom, coordinates: geom.coordinates.map(p => p.map(clipRing)) };
        return geom;
      }
      return { ...geo, features: geo.features.map(f => ({ ...f, geometry: clipGeom(f.geometry) })) };
    }
    const landClipped = clipGeoJSON(landGeo as unknown as GeoJSON.FeatureCollection);
    const countriesClipped = clipGeoJSON(countriesGeo as unknown as GeoJSON.FeatureCollection);

    L.geoJSON(landClipped as GeoJSON.GeoJsonObject, {
      style: { fillColor: '#1a2332', fillOpacity: 1, color: 'transparent', weight: 0 },
      interactive: false,
    }).addTo(map);

    L.geoJSON(countriesClipped as GeoJSON.GeoJsonObject, {
      style: { fillColor: 'transparent', fillOpacity: 0, color: '#2a3f5a', weight: 0.5, opacity: 0.7 },
      interactive: false,
    }).addTo(map);

    map.doubleClickZoom.disable();
    map.on('dblclick', () => map.fitBounds([[-90, -180], [90, 180]]));
    map.on('zoomend', () => {
      const z = map.getZoom();
      zoomLevelRef.current = z;
      setZoomLevel(z);
    });

    // 创建图层组：自上而下 arc → point → site → focusRing
    const arcLayer = L.layerGroup().addTo(map);
    const pointLayer = L.layerGroup().addTo(map);
    const siteLayer = L.layerGroup().addTo(map);
    const focusRing = L.layerGroup().addTo(map);

    mapRef.current = map;
    arcLayerRef.current = arcLayer;
    pointLayerRef.current = pointLayer;
    siteLayerRef.current = siteLayer;
    focusRingRef.current = focusRing;
    const initZoom = map.getZoom();
    zoomLevelRef.current = initZoom;
    setZoomLevel(initZoom);
    setMapReady(true);

    // ResizeObserver → invalidateSize
    ro = new ResizeObserver(() => {
      map.invalidateSize();
    });
    ro.observe(el);

    // react-grid-layout 延迟渲染 → 容器可能 0 高度时初始化地图
    // 用双重 rAF 确保在布局稳定后再 invalidateSize
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        map?.invalidateSize();
      });
    });

    } catch (err) {
      console.error('FlatMapPanel 地图初始化失败', err);
      setMapReady(false);
    }

    return () => {
      ro?.disconnect();
      mapForCleanup?.remove();
      mapRef.current = null;
      arcLayerRef.current = null;
      pointLayerRef.current = null;
      siteLayerRef.current = null;
      focusRingRef.current = null;
      setMapReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── region prop → flyTo ────────────────────────────────── */

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // ⛔ react-grid-layout 0 高度时 flyToBounds 会算出 NaN 像素 → 崩
    const size = map.getSize();
    if (size.x <= 0 || size.y <= 0) {
      // 推迟到下次 invalidateSize 完成后再飞
      setTimeout(() => {
        if (mapRef.current && mapRef.current.getSize().x > 0) {
          if (region === 'world') {
            mapRef.current.flyToBounds([[-90, -180], [90, 180]], { duration: 0.8 });
          } else {
            const bbox = regionBbox(region);
            if (bbox) {
              const [minLng, minLat, maxLng, maxLat] = bbox;
              mapRef.current.flyToBounds([[minLat, minLng], [maxLat, maxLng]], { duration: 0.8, padding: [6, 6] });
            }
          }
        }
      }, 300);
      return;
    }

    if (region === 'world') {
      map.flyToBounds([[-90, -180], [90, 180]], { duration: 0.8 });
      return;
    }

    const bbox = regionBbox(region);
    if (bbox) {
      const [minLng, minLat, maxLng, maxLat] = bbox;
      map.flyToBounds(
        [
          [minLat, minLng],
          [maxLat, maxLng],
        ],
        { duration: 0.8, padding: [6, 6] },
      );
    }
  }, [region, mapReady]);

  /* ── active 显隐控制 ─────────────────────────────────────── */

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.style.display = active ? '' : 'none';
    // ⛔ 切到 2D 视图时 Leaflet 容器尺寸缓存可能仍为 0 → 强制刷新
    if (active) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const m = mapRef.current;
          if (!m) return;
          m.invalidateSize();
        });
      });
    }
  }, [active]);

  /* ── 切走时清除地图 hover（Leaflet 自带 tooltip 会自动消失）──── */

  /* ── RiskPoint → CircleMarker / Polygon ──────────────────── */

  const buildPointLayer = useCallback(() => {
    const layer = pointLayerRef.current;
    const map = mapRef.current;
    if (!layer || !map || !mapReady) return;

    layer.clearLayers();
    const zoom = zoomLevelRef.current;

    for (const p of points) {
      // ⛔ NaN 坐标降级跳过（防止 Invalid LatLng 崩溃）
      if (isNaN(p.lat) || isNaN(p.lng)) continue;
      const missing = p.status === 'missing';
      const core = (2.6 + p.weight * 3.4) * (p.isEvent ? 1.25 : 1) * 1.5;
      const halo = core * 3.2;
      const highlight =
        !missing && ((p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent === true);

      const pulseSec = (PULSE_SLOW_S - p.weight * (PULSE_SLOW_S - PULSE_FAST_S)).toFixed(2);

      const fillColor = missing ? withAlpha(p.color, 0.18) : p.color;
      const strokeColor = missing ? p.color : withAlpha('#ffffff', 0.5);
      const strokeWeight = missing ? 1 : 0.6;

      const className = missing
        ? 'leaflet-point-missing'
        : highlight
          ? 'leaflet-point-pulse'
          : '';

      if (p.shape === 'diamond') {
        const diamondR = core * 1.4;
        const offsetDeg = pixelToDeg(diamondR, zoom);
        const polygon = L.polygon(
          [
            [p.lat + offsetDeg, p.lng],
            [p.lat, p.lng + offsetDeg],
            [p.lat - offsetDeg, p.lng],
            [p.lat, p.lng - offsetDeg],
          ],
          {
            fillColor,
            color: strokeColor,
            weight: strokeWeight,
            fillOpacity: 0.85,
            className,
            lineJoin: 'round',
          },
        );

        if (highlight) {
          const el = polygon.getElement();
          if (el) (el as HTMLElement).style.setProperty('--ky-pulse-duration', `${pulseSec}s`);
        }

        polygon.bindTooltip(pointTooltipHtml(p), {
          direction: 'top',
          offset: [0, -diamondR * 2],
          className: 'leaflet-tooltip-dark',
        });
        polygon.on('click', () => onPointClick?.(p));
        polygon.addTo(layer);
      } else {
        // 光环（非缺失态）
        if (!missing) {
          L.circleMarker([p.lat, p.lng], {
            radius: halo,
            fillColor: p.color,
            color: 'transparent',
            weight: 0,
            fillOpacity: 0.14,
            interactive: false,
          }).addTo(layer);

          L.circleMarker([p.lat, p.lng], {
            radius: core * 1.8,
            fillColor: p.color,
            color: 'transparent',
            weight: 0,
            fillOpacity: 0.22,
            interactive: false,
          }).addTo(layer);
        } else {
          // 缺失点：透明命中区保证可悬停
          L.circleMarker([p.lat, p.lng], {
            radius: Math.max(halo, 9),
            fillColor: 'transparent',
            color: 'transparent',
            weight: 0,
            fillOpacity: 0,
            interactive: true,
          }).addTo(layer);
        }

        const marker = L.circleMarker([p.lat, p.lng], {
          radius: core,
          fillColor,
          color: strokeColor,
          weight: strokeWeight,
          fillOpacity: 0.85,
          className,
        });

        if (highlight) {
          const el = marker.getElement();
          if (el) (el as HTMLElement).style.setProperty('--ky-pulse-duration', `${pulseSec}s`);
        }

        marker.bindTooltip(pointTooltipHtml(p), {
          direction: 'top',
          offset: [0, -core],
          className: 'leaflet-tooltip-dark',
        });
        marker.on('click', () => onPointClick?.(p));
        marker.addTo(layer);
      }
    }
  }, [points, mapReady, onPointClick]);

  useEffect(() => {
    buildPointLayer();
  }, [buildPointLayer]);

  /* ── RiskArc → Polyline ─────────────────────────────────── */

  useEffect(() => {
    const layer = arcLayerRef.current;
    const map = mapRef.current;
    if (!layer || !map || !mapReady) return;

    layer.clearLayers();

    for (const a of arcs) {
      if (isNaN(a.startLat) || isNaN(a.startLng) || isNaN(a.endLat) || isNaN(a.endLng)) continue;
      // 大圆弧采样，效果与 d3-geo 的 geoInterpolate 等价
      const coords = greatCircleArc(a.startLat, a.startLng, a.endLat, a.endLng);
      const polyline = L.polyline(coords, {
        color: a.startColor,
        weight: 0.9 + (a.intensity / 100) * 1.5,
        dashArray: '6 10',
        className: 'leaflet-arc',
        opacity: 0.75,
        lineCap: 'round',
      });

      polyline.bindTooltip(arcTooltipHtml(a), {
        direction: 'center',
        className: 'leaflet-tooltip-dark',
      });
      polyline.addTo(layer);
    }
  }, [arcs, mapReady]);

  /* ── StrategicSite → DivIcon ────────────────────────────── */

  useEffect(() => {
    const layer = siteLayerRef.current;
    const map = mapRef.current;
    if (!layer || !map || !mapReady) return;

    layer.clearLayers();

    for (const s of sites) {
      if (isNaN(s.lat) || isNaN(s.lng)) continue;
      const r = SITE_STAR_RADIUS * siteScale(s.importance);
      const iconSize = Math.round(r * 2);

      const icon = L.divIcon({
        html: '★',
        className: 'leaflet-site-icon',
        iconSize: [iconSize, iconSize],
        iconAnchor: [iconSize / 2, iconSize / 2],
      });

      const marker = L.marker([s.lat, s.lng], { icon });
      marker.bindTooltip(siteTooltipText(s), {
        direction: 'top',
        offset: [0, -iconSize / 2],
        className: 'leaflet-tooltip-dark',
      });
      marker.addTo(layer);
    }
  }, [sites, mapReady]);

  /* ── focusPointId → 聚焦光环 ────────────────────────────── */

  useEffect(() => {
    const layer = focusRingRef.current;
    if (!layer || !mapReady) return;

    layer.clearLayers();

    if (focusPointId === null) return;

    const target = points.find((p) => p.id === focusPointId);
    if (!target) return;
    if (isNaN(target.lat) || isNaN(target.lng)) return;

    const core = (2.6 + target.weight * 3.4) * (target.isEvent ? 1.25 : 1) * 1.5;
    const halo = core * 3.2;
    const focusR = Math.max(halo * 1.35, 12);

    L.circleMarker([target.lat, target.lng], {
      radius: focusR,
      fillColor: 'transparent',
      color: withAlpha(target.color, 0.9),
      weight: 1.2,
      dashArray: '3 3',
      fillOpacity: 0,
      interactive: false,
      className: 'animate-pulseSoft',
    }).addTo(layer);
  }, [focusPointId, points, mapReady]);

  /* ── 渲染 ──────────────────────────────────────────────── */

  return (
    <div
      ref={containerRef}
      className="flat-map-container"
      style={{ background: MAP_THEME.flatOceanFill }}
    >
      {/* 缩放级别指示器（P1-1） */}
      <div className="leaflet-zoom-indicator">z={zoomLevel}</div>
    </div>
  );
}
