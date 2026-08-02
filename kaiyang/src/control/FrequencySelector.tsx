/**
 * 频率选择器组件
 * 先调 allowed-schedules 端点，失败降级为硬编码预设
 * 以浮动弹窗形式展示，选择后即时生效
 */

import { useState, useEffect, useCallback } from 'react';
import { useControl } from '@/state/ControlContext';
import { getAllowedSchedules, updateSchedule } from '@/lib/controlApi';
import { FALLBACK_SCHEDULES } from '@/config/controlConfig';
import type { ScheduleOption } from '@/types/control';

interface FrequencySelectorProps {
  fetcherId: string;
  currentSchedule: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function FrequencySelector({
  fetcherId,
  currentSchedule,
  onClose,
  onSuccess,
}: FrequencySelectorProps) {
  const { showToast, addLog } = useControl();

  const [options, setOptions] = useState<ScheduleOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载频率选项
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const res = await getAllowedSchedules(fetcherId);
        if (!cancelled) {
          if (res && res.options.length > 0) {
            setOptions(res.options);
          } else {
            // 降级为硬编码预设
            setOptions(FALLBACK_SCHEDULES);
          }
          setError(null);
        }
      } catch {
        if (!cancelled) {
          // 降级为硬编码预设
          setOptions(FALLBACK_SCHEDULES);
          setError(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [fetcherId]);

  // 选择频率
  const handleSelect = useCallback(
    async (value: string) => {
      if (submitting) return;
      setSubmitting(true);

      try {
        await updateSchedule(fetcherId, { schedule: value });
        showToast({
          type: 'success',
          message: '频率已更新',
          detail: `${fetcherId}: ${value}`,
        });
        addLog({
          status: 'success',
          domain: 'tianshu',
          operation: '调频',
          description: `${fetcherId}: → ${value}`,
        });
        onSuccess();
      } catch (err) {
        showToast({
          type: 'error',
          message: '调频失败',
          detail: err instanceof Error ? err.message : '未知错误',
        });
      } finally {
        setSubmitting(false);
      }
    },
    [fetcherId, submitting, showToast, addLog, onSuccess],
  );

  // 点击遮罩关闭
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center"
      onClick={handleOverlayClick}
    >
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" />

      {/* 弹窗 */}
      <div className="relative z-10 mx-4 w-64 rounded-xl border border-white/10 bg-[#0f1b2c] p-4 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-[12px] font-semibold text-white/80">调整采集频率</h4>
          <button
            type="button"
            onClick={onClose}
            className="text-white/30 hover:text-white/60 text-xs"
          >
            ✕
          </button>
        </div>

        {/* 加载态 */}
        {loading && (
          <div className="flex items-center justify-center py-6">
            <span className="animate-spin-slow h-4 w-4 rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
          </div>
        )}

        {/* 选项列表 */}
        {!loading && options.length > 0 && (
          <div className="flex flex-col gap-1">
            {options.map((opt) => {
              const isCurrent = opt.value === currentSchedule;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => handleSelect(opt.value)}
                  disabled={submitting || isCurrent}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-left text-[11px] transition-colors ${
                    isCurrent
                      ? 'border border-cyan-400/30 bg-cyan-500/10 text-cyan-300 cursor-default'
                      : 'text-white/60 hover:bg-white/5 hover:text-white/80 border border-transparent'
                  } ${
                    submitting
                      ? 'opacity-50 cursor-not-allowed'
                      : 'cursor-pointer'
                  }`}
                >
                  <span>{opt.label}</span>
                  <span className="flex items-center gap-1.5">
                    {opt.description && (
                      <span className="text-[10px] text-white/30">{opt.description}</span>
                    )}
                    {isCurrent && <span className="text-[10px] text-cyan-400">当前</span>}
                    {submitting && isCurrent === false && (
                      <span className="animate-spin-slow inline-block h-2.5 w-2.5 rounded-full border border-white/30 border-t-white/60" />
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* 降级提示 */}
        {!loading && error && (
          <p className="text-[10px] text-amber-400/70 mt-1">
            使用本地预设列表（API 不可用）
          </p>
        )}
      </div>
    </div>
  );
}
