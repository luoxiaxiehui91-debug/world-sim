/**
 * 单个 Fetcher 卡片组件
 * 状态指示灯（●/◐/○）+ 元信息 + 操作按钮组（重跑/暂停恢复/调频）
 * 防双击 lock + spinner
 */

import { useState, useCallback } from 'react';
import { useControl } from '@/state/ControlContext';
import { rerunFetchers, pauseFetcher, resumeFetcher } from '@/lib/controlApi';
import { ProgressCard } from '@/control/ProgressCard';
import { FrequencySelector } from '@/control/FrequencySelector';
import { ConfirmDialog } from '@/control/ConfirmDialog';
import type { Fetcher, PendingOperation } from '@/types/control';

/** 状态指示灯配置 */
const STATUS_STYLES: Record<
  Fetcher['status'],
  { color: string; glow: string; label: string; icon: string }
> = {
  running: {
    color: '#5eead4',
    glow: '0 0 6px rgba(94, 234, 212, 0.6)',
    label: '运行中',
    icon: '●',
  },
  paused: {
    color: '#fbbf24',
    glow: '0 0 6px rgba(251, 191, 36, 0.5)',
    label: '暂停中',
    icon: '◐',
  },
  error: {
    color: '#f87171',
    glow: '0 0 6px rgba(248, 113, 113, 0.5)',
    label: '异常',
    icon: '○',
  },
};

/** 格式化相对时间（适用于过去和未来时间） */
function relativeTime(iso: string | null): string {
  if (!iso) return '从未运行';
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffSec = Math.floor((now - then) / 1000);

  // 未来时间（如 next_run_at）
  if (diffSec < 0) {
    const absSec = Math.abs(diffSec);
    if (absSec < 60) return `${absSec}秒后`;
    const absMin = Math.floor(absSec / 60);
    if (absMin < 60) return `${absMin}分钟后`;
    const absHr = Math.floor(absMin / 60);
    if (absHr < 24) return `${absHr}小时后`;
    const absDay = Math.floor(absHr / 24);
    return `${absDay}天后`;
  }

  // 过去时间
  if (diffSec < 60) return `${diffSec}秒前`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}小时前`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}天前`;
}

/** 格式化调度表达式为中文 */
function formatSchedule(schedule: string): string {
  const map: Record<string, string> = {
    I15: '每15分钟',
    I60: '每小时',
    H6: '每6小时',
    H12: '每12小时',
    H24: '每天',
  };
  return map[schedule] ?? schedule;
}

interface FetcherCardProps {
  fetcher: Fetcher;
  selected: boolean;
  onToggleSelect: () => void;
  onRefresh: () => void;
}

export function FetcherCard({
  fetcher,
  selected,
  onToggleSelect,
  onRefresh,
}: FetcherCardProps) {
  const {
    isLocked,
    lockFetcher,
    unlockFetcher,
    pendingOps,
    showToast,
    addLog,
    addPendingOp,
    setToken,
  } = useControl();

  const locked = isLocked(fetcher.id);
  const statusStyle = STATUS_STYLES[fetcher.status];

  // 确认弹窗状态
  const [confirmAction, setConfirmAction] = useState<
    'pause' | 'resume' | null
  >(null);

  // 频率选择器开关
  const [freqOpen, setFreqOpen] = useState(false);

  // 查找此 fetcher 的进行中操作
  const activeOp: PendingOperation | null = (() => {
    for (const op of Object.values(pendingOps)) {
      if (op.fetcherIds.includes(fetcher.id)) return op;
    }
    return null;
  })();

  // ── 操作处理 ──────────────────────────────────────────

  const handleRerun = useCallback(async () => {
    if (locked) return;
    const idempotencyKey = crypto.randomUUID();
    lockFetcher(fetcher.id);

    try {
      const res = await rerunFetchers({
        fetcher_ids: [fetcher.id],
        idempotency_key: idempotencyKey,
      });

      addPendingOp({
        operationId: res.operation_id,
        type: 'fetcher_rerun',
        fetcherIds: [fetcher.id],
        idempotencyKey,
        startedAt: new Date().toISOString(),
        status: 'accepted',
      });

      showToast({
        type: 'info',
        message: '重跑已提交',
        detail: `${fetcher.name} · ${res.operation_id}`,
      });
    } catch (err) {
      if ((err as { code?: number }).code === 401) {
        setToken(null);
      }
      unlockFetcher(fetcher.id);
      showToast({
        type: 'error',
        message: '重跑失败',
        detail: err instanceof Error ? err.message : '未知错误',
      });
    }
  }, [fetcher, locked, lockFetcher, unlockFetcher, addPendingOp, showToast, setToken]);

  const handlePause = useCallback(async () => {
    if (locked) return;
    const idempotencyKey = crypto.randomUUID();
    lockFetcher(fetcher.id);

    try {
      await pauseFetcher(fetcher.id, idempotencyKey);
      showToast({
        type: 'success',
        message: '已暂停',
        detail: `${fetcher.name} 已暂停采集`,
      });
      addLog({
        status: 'success',
        domain: 'tianshu',
        operation: '暂停',
        description: `暂停采集源：${fetcher.name}`,
      });
      unlockFetcher(fetcher.id);
      onRefresh();
    } catch (err) {
      if ((err as { code?: number }).code === 401) {
        setToken(null);
      }
      unlockFetcher(fetcher.id);
      showToast({
        type: 'error',
        message: '暂停失败',
        detail: err instanceof Error ? err.message : '未知错误',
      });
    }
  }, [fetcher, locked, lockFetcher, unlockFetcher, showToast, addLog, onRefresh, setToken]);

  const handleResume = useCallback(async () => {
    if (locked) return;
    const idempotencyKey = crypto.randomUUID();
    lockFetcher(fetcher.id);

    try {
      await resumeFetcher(fetcher.id, idempotencyKey);
      showToast({
        type: 'success',
        message: '已恢复',
        detail: `${fetcher.name} 已恢复采集`,
      });
      addLog({
        status: 'success',
        domain: 'tianshu',
        operation: '恢复',
        description: `恢复采集源：${fetcher.name}`,
      });
      unlockFetcher(fetcher.id);
      onRefresh();
    } catch (err) {
      if ((err as { code?: number }).code === 401) {
        setToken(null);
      }
      unlockFetcher(fetcher.id);
      showToast({
        type: 'error',
        message: '恢复失败',
        detail: err instanceof Error ? err.message : '未知错误',
      });
    }
  }, [fetcher, locked, lockFetcher, unlockFetcher, showToast, addLog, onRefresh, setToken]);

  // ── 渲染 ──────────────────────────────────────────────

  return (
    <>
      <div
        className={`panel-card flex flex-col gap-2 ${
          selected ? 'border-cyan-400/30 bg-cyan-500/5' : ''
        }`}
      >
        {/* 第一行：选择框 + 状态灯 + 名称 */}
        <div className="flex items-center gap-2">
          {/* 选择框 */}
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-cyan-400 shrink-0"
          />

          {/* 状态指示灯 */}
          <span
            className={`inline-block text-xs leading-none ${
              fetcher.status === 'running' ? 'animate-pulseSoft' : ''
            }`}
            style={{
              color: statusStyle.color,
              textShadow: statusStyle.glow,
            }}
            title={statusStyle.label}
          >
            {statusStyle.icon}
          </span>

          {/* 名称 */}
          <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-white/80">
            {fetcher.name}
          </span>

          {/* ID */}
          <span className="shrink-0 text-[10px] text-white/30 font-mono">
            {fetcher.id}
          </span>
        </div>

        {/* 第二行：元信息 */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-white/40">
          <span title={fetcher.schedule}>
            频率：{formatSchedule(fetcher.schedule)}
          </span>
          <span title={fetcher.last_run_at ?? undefined}>
            上次：{relativeTime(fetcher.last_run_at)}
          </span>
          {fetcher.last_status && (
            <span
              className={
                fetcher.last_status === 'success'
                  ? 'text-emerald-400/70'
                  : 'text-red-400/70'
              }
            >
              {fetcher.last_status === 'success' ? '✅' : '❌'}
            </span>
          )}
          {fetcher.next_run_at && (
            <span title={fetcher.next_run_at}>
              下次：{relativeTime(fetcher.next_run_at)}
            </span>
          )}
        </div>

        {/* 进度卡片（操作进行中） */}
        {activeOp && <ProgressCard op={activeOp} />}

        {/* 第三行：操作按钮组 */}
        <div className="flex items-center gap-1.5">
          {/* 重跑 */}
          <button
            type="button"
            onClick={handleRerun}
            disabled={locked}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] transition-colors ${
              locked
                ? 'border-white/5 bg-white/5 text-white/20 cursor-not-allowed'
                : 'border-cyan-400/30 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20'
            }`}
          >
            {locked ? (
              <span className="animate-spin-slow inline-block h-2.5 w-2.5 rounded-full border border-white/30 border-t-white/60" />
            ) : null}
            重跑
          </button>

          {/* 暂停 / 恢复 */}
          {fetcher.status === 'paused' ? (
            <button
              type="button"
              onClick={() => setConfirmAction('resume')}
              disabled={locked}
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] transition-colors ${
                locked
                  ? 'border-white/5 bg-white/5 text-white/20 cursor-not-allowed'
                  : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
              }`}
            >
              恢复
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmAction('pause')}
              disabled={locked}
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] transition-colors ${
                locked
                  ? 'border-white/5 bg-white/5 text-white/20 cursor-not-allowed'
                  : 'border-amber-400/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
              }`}
            >
              暂停
            </button>
          )}

          {/* 调频 */}
          <button
            type="button"
            onClick={() => setFreqOpen(true)}
            disabled={locked}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] transition-colors ${
              locked
                ? 'border-white/5 bg-white/5 text-white/20 cursor-not-allowed'
                : 'border-white/10 bg-white/5 text-white/50 hover:border-white/20 hover:text-white/70'
            }`}
          >
            频率 ⏷
          </button>
        </div>
      </div>

      {/* 暂停确认弹窗 */}
      <ConfirmDialog
        open={confirmAction === 'pause'}
        title="暂停采集源"
        message={
          <span>
            确定暂停 <b className="text-white/80">{fetcher.name}</b>
            ？暂停后该采集源将停止更新。
          </span>
        }
        confirmLabel="确认暂停"
        onConfirm={() => {
          setConfirmAction(null);
          handlePause();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      {/* 恢复确认弹窗 */}
      <ConfirmDialog
        open={confirmAction === 'resume'}
        title="恢复采集源"
        message={
          <span>
            确定恢复 <b className="text-white/80">{fetcher.name}</b>
            ？恢复后将按原频率继续采集。
          </span>
        }
        confirmLabel="确认恢复"
        confirmVariant="primary"
        onConfirm={() => {
          setConfirmAction(null);
          handleResume();
        }}
        onCancel={() => setConfirmAction(null)}
      />

      {/* 频率选择器 */}
      {freqOpen && (
        <FrequencySelector
          fetcherId={fetcher.id}
          currentSchedule={fetcher.schedule}
          onClose={() => setFreqOpen(false)}
          onSuccess={() => {
            setFreqOpen(false);
            onRefresh();
          }}
        />
      )}
    </>
  );
}
