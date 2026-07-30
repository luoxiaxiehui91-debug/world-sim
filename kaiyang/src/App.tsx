import type { ComponentType } from 'react';
import { StatusProvider } from '@/state/StatusContext';
import { StatusBar } from '@/components/StatusBar';
import { PANELS } from '@/panels/registry';

/**
 * 开阳 Wave 1 根组件。
 * 布局由 panelRegistry 驱动：新增面板只需在注册表加一项，本处无需改动。
 * 视觉：固定深空星野背景层 + 顶部状态条 + 12 栅格面板区（小屏单列降级）。
 */
export default function App() {
  const panels = PANELS.filter((p) => p.visible).sort((a, b) => a.order - b.order);

  return (
    <StatusProvider>
      <div className="relative flex min-h-full flex-col">
        <div className="starfield" aria-hidden="true" />
        <StatusBar />
        <main className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-12">
          {panels.map((p) => {
            const Panel = p.component as ComponentType;
            return (
              <section key={p.id} className={p.className}>
                <Panel />
              </section>
            );
          })}
        </main>
        <footer className="px-4 pb-4 text-center text-[11px] text-white/30">
          世界推演系统 · 开阳 Wave 1 · 纯展示层（只读契约文件，不调用任何数据源）
        </footer>
      </div>
    </StatusProvider>
  );
}
