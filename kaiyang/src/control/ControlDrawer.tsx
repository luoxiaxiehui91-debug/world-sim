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

      {/* 关闭按钮 — 悬浮显示，简洁不抢眼 */}
      <button
        type="button"
        onClick={() => {
          const sb = document.querySelector('button[title*="关闭控制台"], button[title*="控制台"]');
          if (sb instanceof HTMLElement) sb.click();
        }}
        className="absolute top-3 right-3 flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/30 hover:border-white/30 hover:bg-white/10 hover:text-white/70 transition-all"
        style={{ zIndex: 9999 }}
        title="关闭控制台"
        aria-label="关闭控制台"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </button>
    </aside>
    </>
  );
}
