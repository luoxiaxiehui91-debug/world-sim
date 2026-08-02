/**
 * Toast 通知组件
 * 自研轻量级 Toast，通过 Context 驱动，与现有玻璃拟态风格一致
 * 支持 success/error/info 三种类型，自动消失动画
 */

import { useEffect, useState } from 'react';
import { useControl } from '@/state/ControlContext';
import type { ToastMessage } from '@/types/control';

/** Toast 颜色映射 */
const TOAST_STYLES: Record<
  ToastMessage['type'],
  { border: string; bg: string; icon: string }
> = {
  success: {
    border: 'border-emerald-400/40',
    bg: 'bg-emerald-500/10',
    icon: '✅',
  },
  error: {
    border: 'border-red-400/40',
    bg: 'bg-red-500/10',
    icon: '❌',
  },
  info: {
    border: 'border-cyan-400/40',
    bg: 'bg-cyan-500/10',
    icon: 'ℹ️',
  },
};

/** Toast 通知容器（固定在抽屉底部） */
export function ToastContainer() {
  const { toasts } = useControl();

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container pointer-events-none absolute bottom-4 left-3 right-3 z-50 flex flex-col gap-1.5">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

/** 单条 Toast（带自动消失逻辑） */
function ToastItem({ toast }: { toast: ToastMessage }) {
  const { dismissToast } = useControl();
  const [exiting, setExiting] = useState(false);
  const duration = toast.duration ?? 4000;

  useEffect(() => {
    const exitTimer = setTimeout(() => {
      setExiting(true);
    }, duration - 300);

    const removeTimer = setTimeout(() => {
      dismissToast(toast.id);
    }, duration);

    return () => {
      clearTimeout(exitTimer);
      clearTimeout(removeTimer);
    };
  }, [toast.id, duration, dismissToast]);

  const style = TOAST_STYLES[toast.type];

  return (
    <div
      className={`
        pointer-events-auto rounded-lg border px-3 py-2 text-[11px] backdrop-blur-md
        ${style.border} ${style.bg}
        ${exiting ? 'toast-exit' : 'toast-enter'}
      `}
      role="alert"
    >
      <div className="flex items-start gap-2">
        <span className="mt-px shrink-0 leading-none">{style.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-white/90">{toast.message}</p>
          {toast.detail && (
            <p className="mt-0.5 text-white/50 truncate">{toast.detail}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => dismissToast(toast.id)}
          className="ml-1 shrink-0 text-white/30 hover:text-white/60 leading-none"
          aria-label="关闭通知"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
