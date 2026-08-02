/**
 * 操作日志 localStorage 读写封装
 * 50 条上限，超限自动裁剪最早条目
 */

import { LOG_STORAGE_KEY, LOG_MAX_ENTRIES } from '@/config/controlConfig';
import type { OperationLogEntry } from '@/types/control';

/**
 * 读取全部操作日志（按时间倒序）。
 * localStorage 不可用时返回空数组。
 */
export function readLogs(): OperationLogEntry[] {
  try {
    const raw = localStorage.getItem(LOG_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as OperationLogEntry[];
  } catch {
    return [];
  }
}

/**
 * 追加一条日志条目。
 * 自动裁剪超过 LOG_MAX_ENTRIES 的最早条目。
 */
export function appendLog(entry: OperationLogEntry): void {
  try {
    const logs = readLogs();
    logs.unshift(entry); // 最新在前
    if (logs.length > LOG_MAX_ENTRIES) {
      logs.length = LOG_MAX_ENTRIES;
    }
    localStorage.setItem(LOG_STORAGE_KEY, JSON.stringify(logs));
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
}

/**
 * 写入完整的日志数组（用于 Context 批量同步）。
 * 自动裁剪超过 LOG_MAX_ENTRIES 的最早条目。
 */
export function writeLogs(logs: OperationLogEntry[]): void {
  try {
    const trimmed = logs.slice(0, LOG_MAX_ENTRIES);
    localStorage.setItem(LOG_STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    /* 静默忽略 */
  }
}
