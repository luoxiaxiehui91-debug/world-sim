/**
 * 操作状态轮询 Hook
 * 3s 间隔轮询 / 30 次超时 / 自动 unlock fetcher / 自动写日志
 *
 * 使用方式：
 *   useOperationPolling(pendingOps, onComplete)
 *   - pendingOps: ControlContext 中的进行中操作 map
 *   - 自动执行轮询逻辑，完成后调用回调
 */

import { useEffect, useRef } from 'react';
import { useControl } from '@/state/ControlContext';
import { getOperationStatus } from '@/lib/controlApi';
import { POLL_INTERVAL_MS, POLL_MAX_ATTEMPTS } from '@/config/controlConfig';
import type { PendingOperation, OperationState } from '@/types/control';

/** 终态集合 */
const TERMINAL_STATES: Set<OperationState> = new Set(['completed', 'failed']);

/**
 * 操作状态轮询 Hook。
 *
 * 对 pendingOps 中每个操作独立轮询，终态后自动：
 * - removePendingOp
 * - unlockFetcher（对每个 affected fetcher）
 * - showToast + addLog
 */
export function useOperationPolling() {
  const {
    pendingOps,
    removePendingOp,
    unlockFetcher,
    showToast,
    addLog,
  } = useControl();

  // 记录每个操作的轮询次数（key = operationId）
  const pollCounts = useRef<Map<string, number>>(new Map());
  // 标记已处理的操作（防止重复回调）
  const processed = useRef<Set<string>>(new Set());

  useEffect(() => {
    const opIds = Object.keys(pendingOps);
    if (opIds.length === 0) return;

    const intervalId = setInterval(async () => {
      for (const opId of opIds) {
        // 已处理的跳过
        if (processed.current.has(opId)) continue;

        const count = pollCounts.current.get(opId) ?? 0;

        // 超时处理
        if (count >= POLL_MAX_ATTEMPTS) {
          processed.current.add(opId);
          pollCounts.current.delete(opId);

          const op = pendingOps[opId];
          if (op) {
            // 超时 toast + 日志
            showToast({
              type: 'error',
              message: `操作超时：${op.type}`,
              detail: `操作 ${op.operationId} 在 ${POLL_MAX_ATTEMPTS * POLL_INTERVAL_MS / 1000}s 内未完成`,
            });
            addLog({
              status: 'failed',
              domain: 'tianshu',
              operation: op.type === 'fetcher_rerun' ? '重跑' : op.type,
              description: `操作超时：${op.fetcherIds.join(', ')}`,
              detail: `轮询 ${POLL_MAX_ATTEMPTS} 次无终态`,
            });
            // 解锁
            for (const fid of op.fetcherIds) {
              unlockFetcher(fid);
            }
            removePendingOp(opId);
          }
          continue;
        }

        // 轮询
        try {
          const status = await getOperationStatus(opId);
          pollCounts.current.set(opId, count + 1);

          if (!status) continue;

          // 检查是否到达终态
          if (TERMINAL_STATES.has(status.status)) {
            processed.current.add(opId);
            pollCounts.current.delete(opId);

            const op = pendingOps[opId];
            if (!op) continue;

            if (status.status === 'completed') {
              showToast({
                type: 'success',
                message: '操作完成',
                detail: `${op.type}: ${op.fetcherIds.join(', ')}`,
              });
              addLog({
                status: 'success',
                domain: 'tianshu',
                operation: op.type === 'fetcher_rerun' ? '重跑' : op.type,
                description: `操作完成：${op.fetcherIds.join(', ')}`,
              });
            } else {
              const errMsg = status.error?.message ?? '未知错误';
              showToast({
                type: 'error',
                message: '操作失败',
                detail: errMsg,
              });
              addLog({
                status: 'failed',
                domain: 'tianshu',
                operation: op.type === 'fetcher_rerun' ? '重跑' : op.type,
                description: `操作失败：${op.fetcherIds.join(', ')}`,
                detail: errMsg,
              });
            }

            // 解锁所有受影响的 fetcher
            for (const fid of op.fetcherIds) {
              unlockFetcher(fid);
            }
            removePendingOp(opId);
          }
        } catch {
          // 单次轮询失败不处理，继续下一次
          pollCounts.current.set(opId, count + 1);
        }
      }

      // 所有操作都已处理后清除定时器
      const remaining = Object.keys(pendingOps).filter(
        (id) => !processed.current.has(id),
      );
      if (remaining.length === 0) {
        clearInterval(intervalId);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }, [pendingOps, removePendingOp, unlockFetcher, showToast, addLog]);
}
