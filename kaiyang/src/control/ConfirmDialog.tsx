/**
 * 高危操作确认弹窗
 * Modal + 显式确认按钮，不可回车误触
 * 用于暂停采集源、批量操作等不可逆操作
 */

import { useEffect, useRef, type ReactNode } from 'react';

export interface ConfirmDialogProps {
  /** 是否显示弹窗 */
  open: boolean;
  /** 弹窗标题 */
  title: string;
  /** 弹窗内容（支持 ReactNode） */
  message: ReactNode;
  /** 确认按钮文字 */
  confirmLabel?: string;
  /** 取消按钮文字 */
  cancelLabel?: string;
  /** 确认按钮样式（默认 danger 红色） */
  confirmVariant?: 'danger' | 'primary';
  /** 确认回调 */
  onConfirm: () => void;
  /** 取消/关闭回调 */
  onCancel: () => void;
}

/**
 * 高危确认弹窗组件。
 * 特性：
 * - 点击遮罩层不关闭（必须显式点击按钮）
 * - Enter 键不触发确认
 * - 确认按钮有明确的颜色区分
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确认',
  cancelLabel = '取消',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  // 弹窗打开时聚焦确认按钮
  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => {
        confirmRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // 阻止 Enter 键全局触发
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
      }
      if (e.key === 'Escape') {
        onCancel();
      }
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [open, onCancel]);

  if (!open) return null;

  const confirmBtnClass =
    confirmVariant === 'danger'
      ? 'bg-red-500/20 border-red-400/40 text-red-300 hover:bg-red-500/30'
      : 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300 hover:bg-cyan-500/30';

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* 遮罩层（不响应点击，防止误触关闭） */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* 弹窗本体 */}
      <div
        className="relative z-10 mx-4 w-full max-w-sm rounded-xl border border-white/10 bg-[#0f1b2c] p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <h3
          id="confirm-dialog-title"
          className="mb-2 text-sm font-semibold text-white/90"
        >
          {title}
        </h3>

        <div className="mb-5 text-[12px] text-white/60">{message}</div>

        <div className="flex justify-end gap-2.5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-white/10 bg-white/5 px-3.5 py-1.5 text-[12px] text-white/60 transition-colors hover:bg-white/10 hover:text-white/80"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`rounded-lg border px-3.5 py-1.5 text-[12px] font-medium transition-colors ${confirmBtnClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
