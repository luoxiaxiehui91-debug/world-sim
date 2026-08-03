/**
 * 控制抽屉容器组件
 * 380px 玻璃拟态 + slide-in-right / slide-out-right CSS 动画
 * z-index 覆盖在现有网格上方，不破坏原有布局
 */

import { useEffect, useRef, useState } from 'react';
import { useControl } from '@/state/ControlContext';
import { DRAWER_WIDTH, MOCK_ENABLED } from '@/config/controlConfig';
import { TabBar } from '@/control/TabBar';
import { TianshuTab } from '@/control/TianshuTab';
import { PlaceholderTab } from '@/control/PlaceholderTab';
import { ToastContainer } from '@/control/Toast';

type AnimationPhase = 'entering' | 'entered' | 'exiting' | 'exited';

export function ControlDrawer() {
  const { drawerOpen, activeTab } = useControl();
  const [phase, setPhase] = useState<AnimationPhase>('exited');
  const prevOpen = useRef(false);

  useEffect(() => {
    if (drawerOpen && !prevOpen.current) {
      setPhase('entering');
      const id = requestAnimationFrame(() => {
        requestAnimationFrame(() => { setPhase('entered'); });
      });
      prevOpen.current = true;
      return () => cancelAnimationFrame(id);
    } else if (!drawerOpen && prevOpen.current) {
      setPhase('exiting');
      const id = setTimeout(() => { setPhase('exited'); }, 350);
      prevOpen.current = false;
      return () => clearTimeout(id);
    }
  }, [drawerOpen]);

  if (phase === 'exited') return null;
  const isVisible = phase === 'entering' || phase === 'entered';

  return (
    <>
      {isVisible && (
        <div
          className="fixed inset-0"
          style={{ zIndex: 40, background: 'rgba(0, 0, 0, 0.4)', backdropFilter: 'blur(2px)' }}
          onClick={() => {
            /* backdrop click → close by clicking the StatusBar's toggle button */
            const sb = document.querySelector('button[title*="关闭控制台"], button[title*="控制台"]');
            if (sb instanceof HTMLElement) sb.click();
          }}
          aria-hidden="true"
        />
      )}
      <aside
        className={`control-drawer glass scanlines ${isVisible ? 'drawer-open' : 'drawer-closing'}`}
        style={{ width: DRAWER_WIDTH, overflow: 'visible', zIndex: 50 }}
        aria-label="控制面板"
      >

      {MOCK_ENABLED && (
        <div
          className="flex items-center gap-2 px-3 py-2 text-[11px] font-medium"
          style={{
            background: 'rgba(251,191,36,0.10)',
            borderBottom: '1px solid rgba(251,191,36,0.25)',
            color: 'var(--ky-amber)',
          }}
          aria-label="MOCK模式提示"
        >
          <span style={{ fontSize: 13 }}>⚠</span>
          控制功能未连接（天枢侧 API 未实现）
        </div>
      )}
      <TabBar />
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {activeTab === 'tianshu' && <TianshuTab />}
        {activeTab === 'tianxuan' && <PlaceholderTab title="天璇" description="推演控制 · 建设中" />}
        {activeTab === 'tianji' && <PlaceholderTab title="天玑" description="校验触发 · 建设中" />}
        {activeTab === 'yuheng' && <PlaceholderTab title="玉衡" description="权重矩阵审批 · 建设中" />}
        {activeTab === 'operation_log' && <PlaceholderTab title="操作日志" description="日志功能 · 建设中" />}
      </div>
      <ToastContainer />

      {/* 关闭箭头 — 抽屉左侧垂直居中，点击收起 */}
      <button
        type="button"
        onClick={() => {
          const sb = document.querySelector('button[title*="关闭控制台"], button[title*="控制台"]');
          if (sb instanceof HTMLElement) sb.click();
        }}
        className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 flex h-10 w-5 items-center justify-center rounded-l-md border border-r-0 border-white/10 bg-black/40 text-white/30 hover:border-white/25 hover:bg-black/60 hover:text-white/70 transition-all"
        style={{ zIndex: 9999 }}
        title="关闭控制台"
        aria-label="关闭控制台"
      >
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" aria-hidden="true">
          <path d="M2 2l4 5-4 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
    </aside>
    </>
  );
}
