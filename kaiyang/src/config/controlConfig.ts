/**
 * 开阳控制面板 · 配置文件
 * API Base URL、默认配置、频率硬编码预设、MOCK 开关
 */

import type { ScheduleOption } from '@/types/control';

// ── API Base URL ───────────────────────────────────────────

/** 控制 API 默认 Base URL — 指向天枢 control_server.py（:8900） */
const DEFAULT_API_BASE_URL =
  `${window.location.protocol}//${window.location.hostname}:8900/api/v1/control/`;

/**
 * 控制 API Base URL。
 * 优先级：localStorage('kaiyang_control_api_base_url') > VITE_CONTROL_API_BASE_URL env > 默认值
 */
export const API_BASE_URL: string = (() => {
  try {
    const stored = localStorage.getItem('kaiyang_control_api_base_url');
    if (stored) return stored;
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
  const fromEnv = (import.meta.env.VITE_CONTROL_API_BASE_URL as string | undefined);
  if (fromEnv) return fromEnv.endsWith('/') ? fromEnv : `${fromEnv}/`;
  return DEFAULT_API_BASE_URL;
})();

// ── Token ──────────────────────────────────────────────────

/** 从环境变量读取 Token */
export function getEnvToken(): string | null {
  const t = import.meta.env.VITE_CONTROL_API_TOKEN as string | undefined;
  return t && t.length > 0 ? t : null;
}

/** 从 localStorage 读取 Token */
export function getStoredToken(): string | null {
  try {
    return localStorage.getItem('kaiyang_control_token');
  } catch {
    return null;
  }
}

/** 保存 Token 到 localStorage */
export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem('kaiyang_control_token', token);
    } else {
      localStorage.removeItem('kaiyang_control_token');
    }
  } catch {
    /* localStorage 不可用时静默忽略 */
  }
}

// ── Mock ───────────────────────────────────────────────────

/** MOCK 开关：true = 使用内置 mock 数据，false = 真实 HTTP 请求
 *  A3a 天枢控制 API 上线后默认改为 false。
 *  VITE_CONTROL_MOCK=true 可在开发时恢复 mock 模式。
 */
export const MOCK_ENABLED: boolean = (() => {
  const env = import.meta.env.VITE_CONTROL_MOCK as string | undefined;
  if (env === 'true' || env === '1') return true;
  return false; // 默认关闭 mock，连接真实 API
})();

// ── 频率硬编码预设（频率选择器降级用）──────────────────────

/** 硬编码频率预设列表。
 * 当 allowed-schedules 端点不可用时，FrequencySelector 降级使用此列表。
 * 值与后端调度表达式格式对齐（I15=每15分钟, I60=每小时, H6=每6小时...）
 */
export const FALLBACK_SCHEDULES: ScheduleOption[] = [
  { label: '每15分钟', value: 'I15', description: '高频采集' },
  { label: '每小时', value: 'I60', description: '标准频率' },
  { label: '每6小时', value: 'H6', description: '中等频率' },
  { label: '每12小时', value: 'H12', description: '低频采集' },
  { label: '每天', value: 'H24', description: '日频采集' },
];

// ── 操作状态轮询配置 ───────────────────────────────────────

/** 轮询间隔（毫秒） */
export const POLL_INTERVAL_MS = 3000;

/** 最大轮询次数（超过则 timeout） */
export const POLL_MAX_ATTEMPTS = 30;

/** API 请求超时（毫秒） */
export const API_TIMEOUT_MS = 30000;

// ── 操作日志配置 ───────────────────────────────────────────

/** localStorage 存储键 */
export const LOG_STORAGE_KEY = 'kaiyang_operation_logs';

/** 日志最大条数 */
export const LOG_MAX_ENTRIES = 50;

// ── 抽屉配置 ───────────────────────────────────────────────

/** 抽屉宽度（px） */
export const DRAWER_WIDTH = 380;
