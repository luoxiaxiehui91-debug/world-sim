import { useEffect, useMemo, useRef, useState } from 'react';
import Globe from 'globe.gl';
import * as THREE from 'three';
import { MAP_THEME, PALETTE, withAlpha } from '@/config/theme';
import { WORLD_CAMERA, regionCamera, type RegionKey } from '@/config/regions';
import {
  HIGHLIGHT_THRESHOLD,
  arcTooltipHtml,
  pointTooltipHtml,
  type RiskArc,
  type RiskPoint,
} from '@/lib/mapData';
import {
  STRATEGIC_SITE_COLOR,
  siteScale,
  siteTooltipText,
  type StrategicSite,
} from '@/data/strategicSites';

export interface GlobePanelProps {
  /** 地图点位（已由上层过滤掉 composite 维度） */
  points: RiskPoint[];
  /** 地缘联动弧线 */
  arcs: RiskArc[];
  /** 战略要地叠加层（独立于类别色轴；上层关掉开关时传空数组） */
  sites?: StrategicSite[];
  /** 当前是否为可见视图；隐藏时停止自动旋转以省电（默认 true） */
  active?: boolean;
  /** 地区取景（R-P1-02）：非 world 时相机飞到该地区 bbox 中心（默认 world = 默认视角） */
  region?: RegionKey;
  /** 聚焦点位 id（R-P1-03）：命中点加粗光环 + 加速脉冲 + 常驻标签，相机飞过去 */
  focusPointId?: string | null;
  /** 点击点位回调（供上层反向选中） */
  onPointClick?: (point: RiskPoint) => void;
}

/**
 * 3D 地球视图（globe.gl / three r0.185.1）。
 * 展示组件：数据由 WorldPanel 统一构建后传入，与平面地图共用同一份点位/弧线。（开阳整体为操作面板，含向各后端下发受控指令的职能，详见 DESIGN.md / DATA_CONTRACT.md）
 *
 * 视觉：本地星空背景 + 加厚青绿大气 + 经纬网格 + 渐变粗弧线 + 光环点位 + 高风险常驻标签。
 * 兼容性：所有非核心 API（graticules / rings / htmlElements）均做能力探测，缺失时静默降级，
 * 保证任何 globe.gl 版本差异都不会打断渲染循环。
 *
 * ⚠ 渲染器只读约定（K6）：本组件**只直读** `p.color / p.weight / p.shape / p.status`，
 * 不得 import `config/layerCategories` 去反查类别定义。类别 → 色/形/强度的换算
 * 一律在 `lib/mapData.ts` / `lib/nuclearData.ts` 预计算完成，这是「3D 与 2D 观感
 * 永远一致」的既有保证机制；一旦渲染器自己算色，两个视图必然漂移。
 */

/** 光环重复周期区间（毫秒）：weight 越高脉冲越快，即「强度 = 脉冲速率」这一半双轴。 */
const RING_PERIOD_SLOW = 1800;
const RING_PERIOD_FAST = 700;

/* ── 地区取景与聚焦（P1）──────────────────────────────────────────── */

/** 相机飞行动画时长（毫秒）。 */
const CAMERA_FLY_MS = 900;
/** 聚焦点的光环周期（毫秒）：明显快于任何常规点，一眼能认出「就是这个」。 */
const FOCUS_RING_PERIOD = 520;

/* ── 战略要地叠加层（P1）────────────────────────────────────────────
 * 独立于 RiskPoint：固定琥珀金 + 星形精灵 + 常驻中文标签，不走类别色轴（D1）。
 * 层位分配：符号占 customLayer（RiskPoint 未使用），标签并入既有 htmlElements 层。 */

/** 相机高度超过此值时隐藏要地标签（只留符号），避免拉远后标签糊成一片。 */
const SITE_LABEL_MAX_ALTITUDE = 2.9;
/** 要地符号在地表之上的抬升（略高于常规点，避免被高风险柱遮住）。 */
const SITE_ALTITUDE = 0.012;

/** 星形精灵贴图（模块级单例：颜色固定，8 个点位共用一张，避免重复建纹理）。 */
let starTexture: THREE.CanvasTexture | null = null;

/** 生成四角星贴图；canvas 不可用时返回 null，调用方跳过符号层（降级不抛异常）。 */
function getStarTexture(): THREE.CanvasTexture | null {
  if (starTexture) return starTexture;
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const c = size / 2;
  const outer = c * 0.92;
  const inner = outer * 0.34;
  ctx.beginPath();
  // 8 个顶点交替内外半径 = 四角星（与 RiskPoint 的圆点 / 菱形明显区分）
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI / 4) * i - Math.PI / 2;
    const r = i % 2 === 0 ? outer : inner;
    const x = c + Math.cos(angle) * r;
    const y = c + Math.sin(angle) * r;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = STRATEGIC_SITE_COLOR;
  ctx.shadowColor = STRATEGIC_SITE_COLOR;
  ctx.shadowBlur = 10;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = 'rgba(255,255,255,0.75)';
  ctx.stroke();
  starTexture = new THREE.CanvasTexture(canvas);
  return starTexture;
}

/** 要地悬停气泡（与 pointTooltipHtml 同款外壳，但走固定琥珀金而非类别色）。 */
function siteTooltipHtml(site: StrategicSite): string {
  return (
    `<div style="font:12px/1.5 ui-sans-serif,system-ui,'PingFang SC',sans-serif;` +
    `background:rgba(6,11,22,0.92);border:1px solid ${withAlpha(STRATEGIC_SITE_COLOR, 0.55)};` +
    `box-shadow:0 0 18px ${withAlpha(STRATEGIC_SITE_COLOR, 0.28)};color:${PALETTE.text};` +
    `padding:6px 10px;border-radius:8px;white-space:nowrap;">` +
    `<b style="color:${STRATEGIC_SITE_COLOR}">✦ ${site.name}</b>` +
    `<br/><span style="opacity:.6">${siteTooltipText(site)}</span>` +
    `</div>`
  );
}

/** htmlElements 层的数据联合体：既有的高风险点标签 + 新增的要地标签共用一层。 */
type GlobeHtmlDatum =
  | { kind: 'point'; lat: number; lng: number; alt: number; point: RiskPoint }
  | { kind: 'site'; lat: number; lng: number; alt: number; site: StrategicSite };

export function GlobePanel({
  points,
  arcs,
  sites = [],
  active = true,
  region = 'world',
  focusPointId = null,
  onPointClick,
}: GlobePanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // globe.gl 无官方 TS 类型，统一按 any 处理（保持与既有实现一致）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 相机拉远时隐藏要地标签；用 ref 去抖，避免 onZoom 每帧触发 setState
  const [siteLabelsOn, setSiteLabelsOn] = useState(true);
  const siteLabelsOnRef = useRef(true);

  // v1.10.7 Top-80 标签截断：常驻标签按 intensity 降序只保留前 80 个点标签
  // （聚焦点恒在首位，即使它 intensity 低也要可见；悬停 tooltip 由 pointLabel 提供，不受截断影响）。
  // 降噪根因：默认视图 281 个 ≥HIGHLIGHT 的标签互相遮挡，截断到 Top-80 后标签云消散。
  const labeledPoints = useMemo<GlobeHtmlDatum[]>(() => {
    return points
      .filter(
        (p) =>
          p.status !== 'missing' &&
          (focusPointId !== null && p.id === focusPointId ||
            (p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent),
      )
      .map((p) => ({
        kind: 'point' as const,
        lat: p.lat,
        lng: p.lng,
        alt: 0.06 + p.weight * 0.17,
        point: p,
      }))
      .sort((a, b) => {
        const aFocus = a.point.id === focusPointId ? 1 : 0;
        const bFocus = b.point.id === focusPointId ? 1 : 0;
        if (aFocus !== bFocus) return bFocus - aFocus; // 聚焦点最前
        return (b.point.value ?? 0) - (a.point.value ?? 0); // 其余 intensity 降序
      })
      .slice(0, 80);
  }, [points, focusPointId]);

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
        // 初始视角与 regions.WORLD_CAMERA 同源，避免「初始化」与「切回全球」两处漂移
        .pointOfView(WORLD_CAMERA, 0);

      // 星空深空背景（本地贴图，离线可用）。加载失败时下方 CSS 深空渐变兜底。
      if (typeof world.backgroundImageUrl === 'function') {
        world.backgroundImageUrl(MAP_THEME.starFieldUrl);
      }
      // 经纬网格（科技感）
      if (typeof world.showGraticules === 'function') {
        world.showGraticules(true);
      }

      // 视距联动：拉远到一定高度后隐藏战略要地标签（符号仍常驻）
      if (typeof world.onZoom === 'function') {
        world.onZoom((pov: { altitude?: number } | undefined) => {
          const on = (pov?.altitude ?? 0) <= SITE_LABEL_MAX_ALTITUDE;
          if (siteLabelsOnRef.current !== on) {
            siteLabelsOnRef.current = on;
            setSiteLabelsOn(on);
          }
        });
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

  /**
   * 地区取景（R-P1-02）：相机飞到该地区 bbox 中心，`world` 回默认全球视角。
   * 2D 是矩形裁切、3D 是球面视角，两者观感本就不可能一致（设计稿 N6-③）；
   * 这里只保证「中心一致 + 跨度越大看得越远」，换算公式收敛在 `regionCamera`。
   */
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const world = globeRef.current as any;
    if (!world || typeof world.pointOfView !== 'function') return;
    try {
      world.pointOfView(regionCamera(region), CAMERA_FLY_MS);
    } catch {
      /* 相机 API 异常不影响渲染 */
    }
  }, [region]);

  /**
   * 单点聚焦（R-P1-03）：2026-08-11 v1.10.2 起不再飞相机（对齐 crucix：点击只标记不飞）。
   * 选中态由 rings 聚焦标记表达（isFocus 切换 ring 基径 2.2+2.2w → 3.5+2.2w）；
   * 相机只在初始加载 / region 切换时定位（上方 region effect）。
   */
  // 数据驱动：风险点位 + 光环 + 常驻标签 + 地缘联动弧线
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const world = globeRef.current as any;
    if (!world) return;

    /** 是否为当前聚焦点（只比 id，不猜坐标）。 */
    const isFocus = (p: RiskPoint) => focusPointId !== null && p.id === focusPointId;

    try {
      world
        .pointsData(points)
        .pointLat('lat')
        .pointLng('lng')
        .pointColor('color')
        // 缺失点压扁、缩小：与 C2-A 的「灰 + 无光环 + 无标签」一起，
        // 把「无数据」和「低风险」在视觉上彻底区分开
        .pointAltitude((p: RiskPoint) => (p.status === 'missing' ? 0.01 : 0.03 + p.weight * 0.17))
        // v1.10.6 ×0.8 收窄：0.4+0.25w → 0.32+0.2w（主理人"图标偏大"反馈）
        // v1.10.7 再收窄 ×0.68：0.32+0.2w → 0.22+0.14w（与 2D 新公式同量级；缺失 0.18）
        .pointRadius((p: RiskPoint) => (p.status === 'missing' ? 0.18 : 0.22 + p.weight * 0.14))
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

      // 点击点位 → 上层反向选中（能力探测；未传回调时注销点击，避免残留旧闭包）
      if (typeof world.onPointClick === 'function') {
        world.onPointClick(onPointClick ? (p: RiskPoint) => onPointClick(p) : () => {});
      }

      // 高风险点位脉冲光环（能力探测，缺失则跳过）；事件告警柱始终带光环。
      // 决策 C2-A：status='missing' 的点一律不参与光环——「无数据」不许看起来像「在活动」。
      // 聚焦点（R-P1-03）额外破例进入光环层：即使它是低风险点，也要能被一眼找到。
      if (typeof world.ringsData === 'function') {
        const rings = points.filter(
          (p) =>
            p.status !== 'missing' &&
            (isFocus(p) || (p.value ?? 0) >= HIGHLIGHT_THRESHOLD || p.isEvent),
        );
        world
          .ringsData(rings)
          .ringLat('lat')
          .ringLng('lng')
          .ringColor((p: RiskPoint) => (t: number) =>
            withAlpha(p.color, Math.max(0, 1 - t) * (isFocus(p) ? 0.85 : 0.55)),
          )
          // v1.10.6 ring ×0.8 收窄（与 pointRadius 联动，主理人"图标偏大"反馈）
          // v1.10.7 再收窄：1.76+1.76w → 1.2+1.1w（普通）/ 2.8 → 1.9（聚焦），与 2D 新环同量级
          .ringMaxRadius((p: RiskPoint) => (isFocus(p) ? 1.9 : 1.2) + p.weight * 1.1)
          // 强度 = 脉冲速率：weight 越高，扩散越快、周期越短
          .ringPropagationSpeed((p: RiskPoint) => (isFocus(p) ? 1.5 : 0.8) + p.weight * 0.8)
          .ringRepeatPeriod((p: RiskPoint) =>
            isFocus(p)
              ? FOCUS_RING_PERIOD
              : Math.round(RING_PERIOD_SLOW - p.weight * (RING_PERIOD_SLOW - RING_PERIOD_FAST)),
          );
      }

      // 战略要地符号层（customLayer，RiskPoint 未占用）：固定琥珀金星形精灵。
      // 精灵始终朝向相机，无需处理球面法线朝向；能力缺失时静默跳过（只丢符号不丢标签）。
      if (
        typeof world.customLayerData === 'function' &&
        typeof world.customThreeObject === 'function' &&
        typeof world.getCoords === 'function'
      ) {
        const tex = getStarTexture();
        world
          .customLayerData(tex ? sites : [])
          .customThreeObject((s: StrategicSite) => {
            const material = new THREE.SpriteMaterial({
              map: tex ?? undefined,
              transparent: true,
              depthWrite: false,
            });
            const sprite = new THREE.Sprite(material);
            // v1.10.3：3.2→3.84（×1.2）地缘要地图标加大（与 2D 星标联动）
            const size = 3.84 * siteScale(s.importance);
            sprite.scale.set(size, size, 1);
            return sprite;
          })
          .customThreeObjectUpdate((obj: THREE.Object3D, s: StrategicSite) => {
            const coords = world.getCoords(s.lat, s.lng, SITE_ALTITUDE);
            if (coords) obj.position.set(coords.x, coords.y, coords.z);
          })
          .customLayerLabel((s: StrategicSite) => siteTooltipHtml(s));
      }

      // 常驻标签层（CSS2D，能力探测）：高风险 / 事件点标签 + 战略要地标签共用一层。
      // 决策 C2-A：缺失点不出常驻标签，避免屏幕上出现一排「—」噪声。
      // v1.10.7：点标签 = labeledPoints（Top-80 降序截断，聚焦点恒在列）；悬停 tooltip 走 pointLabel 不受影响。
      if (typeof world.htmlElementsData === 'function') {
        const labeled: GlobeHtmlDatum[] = labeledPoints;
        // 拉远时只隐藏要地标签，风险点标签不受影响（两者取舍标准不同）
        const siteLabels: GlobeHtmlDatum[] = siteLabelsOn
          ? sites.map((s) => ({
              kind: 'site' as const,
              lat: s.lat,
              lng: s.lng,
              alt: SITE_ALTITUDE + 0.02,
              site: s,
            }))
          : [];

        world
          .htmlElementsData([...labeled, ...siteLabels])
          .htmlLat((d: GlobeHtmlDatum) => d.lat)
          .htmlLng((d: GlobeHtmlDatum) => d.lng)
          .htmlAltitude((d: GlobeHtmlDatum) => d.alt)
          .htmlElement((d: GlobeHtmlDatum) => {
            const div = document.createElement('div');
            div.className = 'globe-tag';
            if (d.kind === 'site') {
              // 战略要地：固定琥珀金 + 星形字形，与任何类别色标签一眼可分
              div.classList.add('globe-tag-site');
              div.style.color = STRATEGIC_SITE_COLOR;
              div.style.borderColor = withAlpha(STRATEGIC_SITE_COLOR, 0.55);
              div.style.boxShadow = `0 0 12px ${withAlpha(STRATEGIC_SITE_COLOR, 0.35)}`;
              div.textContent = `✦ ${d.site.name}`;
              div.title = siteTooltipText(d.site);
              return div;
            }
            const p = d.point;
            // 边框 / 辉光取类别色（p.color 已由构建层预计算为类别色），
            // 让标签一眼可归层，与平面地图的点位色相一致
            div.style.color = p.color;
            div.style.borderColor = withAlpha(p.color, isFocus(p) ? 0.95 : 0.5);
            div.style.boxShadow = `0 0 ${isFocus(p) ? 20 : 12}px ${withAlpha(p.color, isFocus(p) ? 0.6 : 0.35)}`;
            // 形状字形：与 2D 的菱形符号呼应（只读 p.shape，不反查类别定义）
            const glyph = p.isEvent ? '⚠ ' : p.shape === 'diamond' ? '◆ ' : '';
            div.textContent = `${glyph}${p.label} ${p.value === null ? '—' : p.value.toFixed(0)}`;
            return div;
          });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [points, arcs, sites, siteLabelsOn, focusPointId, onPointClick, labeledPoints]);

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
