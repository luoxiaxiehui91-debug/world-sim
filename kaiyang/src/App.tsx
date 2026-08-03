import { useCallback, useMemo, useState } from 'react';
import type { ComponentType } from 'react';
import { Responsive, WidthProvider } from 'react-grid-layout';
import type { Layout, Layouts } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';

import { StatusProvider } from '@/state/StatusContext';
import { ControlProvider } from '@/state/ControlContext';
import { SelectionProvider } from '@/state/SelectionContext';
import { StatusBar } from '@/components/StatusBar';
import { ControlDrawer } from '@/control/ControlDrawer';
import { PANELS } from '@/panels/registry';

// ---- react-grid-layout 初始化 ----

const ResponsiveGridLayout = WidthProvider(Responsive);
const STORAGE_KEY = 'kaiyang.v3.panelLayout';

/** 从 panelRegistry 推导初始布局（3 行 × 12 栅格，Bloomberg/Grafana 情报面板范式）。 */
function buildDefaultLayout(): Layout[] {
  // 行 0：主视图区（h=7），行 7：分析区（h=6），行 13：次要区（h=5）
  const positions: Record<string, { x: number; y: number }> = {
    'risk-summary':   { x: 0,  y: 0  },
    'world':          { x: 2,  y: 0  },
    'signal-stream':  { x: 9,  y: 0  },
    'grv':            { x: 0,  y: 7  },
    'economy':        { x: 4,  y: 7  },
    'status-mini':    { x: 0,  y: 13 },
    'news':           { x: 3,  y: 13 },
    'nuclear-watch':  { x: 9,  y: 13 },
  };

  const panels = PANELS.filter((p) => p.visible).sort((a, b) => a.order - b.order);
  return panels.map((p) => {
    const pos = positions[p.id] ?? { x: 0, y: 0 };
    return {
      i: p.id,
      x: pos.x,
      y: pos.y,
      w: p.defaultLayout.w,
      h: p.defaultLayout.h,
      minW: p.defaultLayout.minW,
      minH: p.defaultLayout.minH,
    };
  });
}

/** 默认布局（惰性计算，仅首次挂载时调用一次）。 */
const defaultLayouts: Layout[] = buildDefaultLayout();

/** 合并缓存布局与默认布局：registry 中有但缓存中没有的新面板追加到末尾（Q6）。 */
function mergeWithDefaults(saved: Layout[], defaults: Layout[]): Layout[] {
  const savedIds = new Set(saved.map((l) => l.i));
  const newItems = defaults.filter((d) => !savedIds.has(d.i));
  if (newItems.length === 0) return saved;
  // 计算缓存中最低的 y+h 值，新面板从该行下方开始
  const maxY = Math.max(...saved.map((l) => l.y + l.h), 0);
  return [
    ...saved,
    ...newItems.map((d, i) => ({
      ...d,
      y: maxY,
      x: (i * d.w) % 12,
    })),
  ];
}

/** 从 localStorage 加载布局（失败时回退默认布局）。 */
function loadLayout(): Layout[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed: Layout[] = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return mergeWithDefaults(parsed, defaultLayouts);
      }
    }
  } catch {
    /* localStorage 不可用或数据损坏 → 回退默认布局 */
  }
  return defaultLayouts;
}

// ---- 根组件 ----

/**
 * 开阳 Wave 2 根组件。
 * 1.7.0：面板布局从 CSS Grid 迁移至 react-grid-layout 可拖拽网格，
 * 支持拖拽重排 + 右下角 resize + localStorage 持久化（K8 / Q5 / Q6）。
 * 控制抽屉作为独立覆盖层渲染，不受网格布局影响。
 * 视觉：固定深空星野背景层 + 顶部状态条 + 可拖拽面板区（小屏单列降级）。
 */
export default function App() {
  const visiblePanels = useMemo(
    () => PANELS.filter((p) => p.visible).sort((a, b) => a.order - b.order),
    [],
  );

  const [layout, setLayout] = useState<Layout[]>(() => loadLayout());
  const [dynamicRowHeight, setDynamicRowHeight] = useState<number>(72);

  /** 自动布局：根据视口高度调整 rowHeight，再 compact 面板填满可视区。 */
  const onAutoLayout = useCallback(() => {
    const vh = window.innerHeight;
    // 扣除状态栏 (~56px) + footer (~44px) + 容器 padding/margin (~72px)
    const availH = Math.max(400, vh - 172);
    // 14 行覆盖三个区域：主视图(6) + 分析(4) + 次要(4)
    const totalRows = 14;
    const rowH = Math.max(60, Math.floor(availH / totalRows));
    setDynamicRowHeight(rowH);

    // 清除缓存、恢复默认布局并用 compact 消灭空隙
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    setLayout(defaultLayouts);

    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(defaultLayouts)); } catch { /* ignore */ }
  }, []);

  /** 面板拖拽/缩放后持久化到 localStorage。 */
  const onLayoutChange = useCallback((currentLayout: Layout[], allLayouts: Layouts) => {
    // 优先取 allLayouts.lg（Responsive 模式下跨断点布局），回退 currentLayout
    const lgLayout: Layout[] = allLayouts?.lg ?? currentLayout;
    setLayout(lgLayout);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(lgLayout));
    } catch {
      /* 隐私模式下写入失败可忽略 */
    }
  }, []);

  /** 重置布局：清除缓存，恢复默认。 */
  const onResetLayout = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* 忽略 */
    }
    setLayout(defaultLayouts);
  }, []);

  return (
    <StatusProvider>
      <ControlProvider>
        {/* 选中/聚焦共享态：信号流点选 ↔ 地图聚焦（R-P1-03），与上面两个 Provider 并列 */}
        <SelectionProvider>
          <div className="relative flex min-h-full flex-col">
            <div className="starfield" aria-hidden="true" />
            <StatusBar />

            {/* 面板区：react-grid-layout 可拖拽网格（1.7.0） */}
            <main className="flex-1">
              <ResponsiveGridLayout
                className="layout min-h-screen"
                layouts={{ lg: layout }}
                breakpoints={{ lg: 1024, md: 768, sm: 0 }}
                cols={{ lg: 12, md: 1, sm: 1 }}
                rowHeight={dynamicRowHeight}
                draggableHandle=".panel-drag-handle"
                onLayoutChange={onLayoutChange}
                compactType="vertical"
                margin={[12, 12]}
                containerPadding={[16, 16]}
              >
                {visiblePanels.map((panel) => {
                  const Panel = panel.component as ComponentType;
                  return (
                    <div
                      key={panel.id}
                      className="glass-panel rounded-lg overflow-hidden flex flex-col"
                    >
                      {/* 拖拽 handle：仅标题栏区域可拖拽，与面板内容隔离 */}
                      <div className="panel-drag-handle flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/10 cursor-grab active:cursor-grabbing select-none">
                        <h3 className="text-sm font-medium text-slate-200 truncate">
                          {panel.title}
                        </h3>
                      </div>
                      <div className="flex-1 overflow-auto p-2">
                        <Panel />
                      </div>
                    </div>
                  );
                })}
              </ResponsiveGridLayout>
            </main>

            <footer className="relative z-[60] flex items-center justify-between px-4 pb-4 text-[11px] text-white/30">
              <span>世界推演系统 · 开阳 Wave 2 v1.7.2 · 操作面板</span>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={onAutoLayout}
                  className="rounded-md border border-emerald-400/50 bg-emerald-500/15 px-3 py-1 text-[13px] font-medium text-emerald-200 hover:border-emerald-400 hover:bg-emerald-500/30 hover:text-emerald-100 transition-colors"
                  title="根据屏幕高度自动调整面板布局"
                  style={{ zIndex: 9999, position: 'relative' }}
                >
                  ⚡ 自动布局
                </button>
                <button
                  type="button"
                  onClick={onResetLayout}
                  className="rounded-md border border-cyan-400/50 bg-cyan-500/15 px-3 py-1 text-[13px] font-medium text-cyan-200 hover:border-cyan-400 hover:bg-cyan-500/30 hover:text-cyan-100 transition-colors"
                  title="重置面板布局到默认排列"
                  style={{ zIndex: 9999, position: 'relative' }}
                >
                  ↺ 重置布局
                </button>
              </div>
            </footer>

            {/* 控制抽屉覆盖层 */}
            <ControlDrawer />
          </div>
        </SelectionProvider>
      </ControlProvider>
    </StatusProvider>
  );
}
