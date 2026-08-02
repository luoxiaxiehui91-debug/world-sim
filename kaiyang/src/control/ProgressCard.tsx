/**
 * 内嵌进度卡片组件
 * 操作进行中状态展示，含进度条 + 状态文本
 * 颜色：--ky-cyan（进行中）/ --ky-teal（完成）/ --ky-red（失败）
 */

import type { PendingOperation, OperationState } from '@/types/control';

/** 状态 → 颜色映射 */
const STATUS_COLORS: Record<OperationState, string> = {
  accepted: '#fbbf24', // amber
  queued: '#fbbf24',
  running: '#22d3ee', // cyan
  completed: '#5eead4', // teal
  failed: '#f87171', // red
};

/** 状态 → 中文标签 */
const STATUS_LABELS: Record<OperationState, string> = {
  accepted: '已受理',
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

/** 默认进度（状态无精确 progress 时的估算） */
const DEFAULT_PROGRESS: Record<OperationState, number> = {
  accepted: 5,
  queued: 15,
  running: 50,
  completed: 100,
  failed: 100,
};

interface ProgressCardProps {
  op: PendingOperation;
}

export function ProgressCard({ op }: ProgressCardProps) {
  const color = STATUS_COLORS[op.status];
  const label = STATUS_LABELS[op.status];
  const progress = DEFAULT_PROGRESS[op.status];

  const isRunning = op.status === 'running';
  const isTerminal =
    op.status === 'completed' || op.status === 'failed';

  return (
    <div className="rounded-lg border border-white/5 bg-black/20 px-2.5 py-2">
      {/* 状态文本 + 百分比 */}
      <div className="mb-1.5 flex items-center justify-between text-[10px]">
        <span className="flex items-center gap-1.5" style={{ color }}>
          {isRunning && (
            <span className="inline-block h-2 w-2 animate-spin-slow rounded-full border-2 border-current border-t-transparent" />
          )}
          {isTerminal && (
            <span className="text-xs">
              {op.status === 'completed' ? '✅' : '❌'}
            </span>
          )}
          {label}
        </span>
        <span className="font-mono text-white/50">{progress}%</span>
      </div>

      {/* 进度条 */}
      <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isRunning ? 'progress-bar-animated' : ''
          }`}
          style={{
            width: `${progress}%`,
            backgroundColor: color,
            boxShadow: `0 0 6px ${color}66`,
          }}
        />
      </div>
    </div>
  );
}
