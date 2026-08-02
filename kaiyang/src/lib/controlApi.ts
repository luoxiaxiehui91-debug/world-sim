/**
 * 控制 API 客户端
 * fetch 封装 + Bearer Token 注入 + 统一错误处理 + 超时（30s）
 * MOCK 模式：内置 mock 数据，自闭环运行
 */

import { API_BASE_URL, MOCK_ENABLED, API_TIMEOUT_MS } from '@/config/controlConfig';
import type {
  FetcherListResponse,
  RerunRequest,
  RerunResponse,
  PauseResumeResponse,
  ScheduleUpdateRequest,
  ScheduleUpdateResponse,
  OperationStatus,
  AllowedSchedulesResponse,
  ApiErrorResponse,
  Fetcher,
} from '@/types/control';

// ── Mock 数据 ──────────────────────────────────────────────

/** 模拟采集源列表 */
const MOCK_FETCHERS: Fetcher[] = [
  {
    id: 'fetch_earthquake',
    name: '地震采集（USGS 实时）',
    status: 'running',
    schedule: 'I15',
    last_run_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    last_status: 'success',
    next_run_at: new Date(Date.now() + 3 * 60 * 1000).toISOString(),
    enabled: true,
  },
  {
    id: 'fetch_fred_history',
    name: 'FRED 经济数据采集',
    status: 'running',
    schedule: 'H6',
    last_run_at: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
    last_status: 'success',
    next_run_at: new Date(Date.now() + 3 * 3600 * 1000).toISOString(),
    enabled: true,
  },
  {
    id: 'fetch_gdelt_v1',
    name: 'GDELT 全球事件采集',
    status: 'paused',
    schedule: 'I60',
    last_run_at: new Date(Date.now() - 2 * 86400 * 1000).toISOString(),
    last_status: 'success',
    next_run_at: null,
    enabled: false,
  },
  {
    id: 'fetch_news_rss',
    name: '新闻 RSS 采集',
    status: 'running',
    schedule: 'I15',
    last_run_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    last_status: 'success',
    next_run_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
    enabled: true,
  },
  {
    id: 'fetch_akshare_mid',
    name: 'AKShare 中国宏观数据',
    status: 'error',
    schedule: 'H12',
    last_run_at: new Date(Date.now() - 1 * 86400 * 1000).toISOString(),
    last_status: 'failed',
    next_run_at: new Date(Date.now() + 2 * 3600 * 1000).toISOString(),
    enabled: true,
  },
];

/** 模拟频率选项 */
const MOCK_ALLOWED_SCHEDULES: AllowedSchedulesResponse = {
  current: 'I60',
  options: [
    { label: '每15分钟', value: 'I15', description: '≤50% 安全水位' },
    { label: '每小时', value: 'I60', description: '≤50% 安全水位' },
    { label: '每6小时', value: 'H6', description: '≤50% 安全水位' },
    { label: '每12小时', value: 'H12', description: '≤50% 安全水位' },
    { label: '每天', value: 'H24', description: '≤50% 安全水位' },
  ],
};

/** 模拟操作状态存储（按 operation_id 索引） */
const mockOps: Map<string, OperationStatus> = new Map();

/** 模拟 fetcher schedule 存储 */
const mockSchedules: Map<string, string> = new Map(
  MOCK_FETCHERS.map((f) => [f.id, f.schedule]),
);

/**
 * 创建模拟操作并启动状态流转定时器。
 * 状态流转：accepted → queued(0.5s) → running(1.5s) → completed(2.5s)
 */
function createMockOperation(
  type: string,
  fetcherIds: string[],
  idempotencyKey: string,
): RerunResponse {
  const operationId = `op_mock_${crypto.randomUUID().slice(0, 8)}`;
  const now = new Date().toISOString();

  const status: OperationStatus = {
    operation_id: operationId,
    command_id: `cmd-mock-${Date.now()}`,
    idempotency_key: idempotencyKey,
    type,
    status: 'accepted',
    progress: 0,
    progress_message: '指令已通过鉴权+校验，已写入队列',
    affected_fetchers: fetcherIds,
    result: null,
    error: null,
    created_at: now,
    completed_at: null,
  };
  mockOps.set(operationId, status);

  // 0.5s → queued
  setTimeout(() => {
    const s = mockOps.get(operationId);
    if (s) {
      s.status = 'queued';
      s.progress = 10;
      s.progress_message = '已进入执行队列，等待调度器消费...';
    }
  }, 500);

  // 1.5s → running
  setTimeout(() => {
    const s = mockOps.get(operationId);
    if (s) {
      s.status = 'running';
      s.progress = 45;
      s.progress_message = '正在执行采集任务...';
    }
  }, 1500);

  // 2.5s → completed
  setTimeout(() => {
    const s = mockOps.get(operationId);
    if (s) {
      s.status = 'completed';
      s.progress = 100;
      s.progress_message = '执行完成';
      s.completed_at = new Date().toISOString();
      s.result = { success: true };
    }
  }, 2500);

  return {
    operation_id: operationId,
    status: 'accepted',
    affected_fetchers: fetcherIds,
  };
}

// ── Token ──────────────────────────────────────────────────

/** 当前活跃的 Bearer Token（由 ControlContext 注入） */
let activeToken: string | null = null;

/** 设置 API 客户端使用的 Bearer Token */
export function setApiToken(token: string | null): void {
  activeToken = token;
}

// ── 通用 fetch 封装 ────────────────────────────────────────

/** 构建完整 API URL */
function apiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/+$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${base}${p}`;
}

/** 构建请求头（含 Bearer Token） */
function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (activeToken) {
    headers['Authorization'] = `Bearer ${activeToken}`;
  }
  return headers;
}

/**
 * 发起 API 请求（带超时）。
 * @param path - API 路径（如 /fetchers）
 * @param options - fetch 选项
 * @param isOptional - 是否为补充端点（true 时 404 返回 null 不抛错）
 */
async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  isOptional = false,
): Promise<T | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const res = await fetch(apiUrl(path), {
      ...options,
      headers: { ...buildHeaders(), ...options.headers },
      signal: controller.signal,
    });

    if (isOptional && res.status === 404) {
      return null;
    }

    if (res.status === 401) {
      const body = await res.json().catch(() => ({}));
      const err = new Error(
        (body as ApiErrorResponse)?.error?.message ?? 'Token 无效，请重新配置',
      ) as Error & { code?: number };
      (err as unknown as Record<string, unknown>).code = 401;
      throw err;
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const apiErr = (body as ApiErrorResponse)?.error;
      const err = new Error(
        apiErr?.message ?? `请求失败 (HTTP ${res.status})`,
      ) as Error & { code?: number; details?: unknown };
      (err as unknown as Record<string, unknown>).code = res.status;
      (err as unknown as Record<string, unknown>).details = apiErr?.details;
      throw err;
    }

    // 204 No Content
    if (res.status === 204) return null as T;

    return (await res.json()) as T;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ── API 函数 ───────────────────────────────────────────────

/** GET /control/fetchers — 获取全部采集源列表 */
export async function getFetchers(): Promise<FetcherListResponse> {
  if (MOCK_ENABLED) {
    // 模拟网络延迟 200-400ms
    await new Promise((r) => setTimeout(r, 200 + Math.random() * 200));
    return { fetchers: [...MOCK_FETCHERS] };
  }
  const res = await apiFetch<FetcherListResponse>('/fetchers');
  return res!;
}

/** POST /control/fetchers/rerun — 重跑采集源 */
export async function rerunFetchers(
  body: RerunRequest,
): Promise<RerunResponse> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 150));
    return createMockOperation('fetcher_rerun', body.fetcher_ids, body.idempotency_key);
  }
  const res = await apiFetch<RerunResponse>('/fetchers/rerun', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return res!;
}

/** POST /control/fetchers/{id}/pause — 暂停采集源 */
export async function pauseFetcher(
  fetcherId: string,
  idempotencyKey: string,
): Promise<PauseResumeResponse> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    // 更新 mock 状态
    const fetcher = MOCK_FETCHERS.find((f) => f.id === fetcherId);
    if (fetcher) {
      fetcher.status = 'paused';
      fetcher.enabled = false;
    }
    return {
      fetcher_id: fetcherId,
      status: 'paused',
      updated_at: new Date().toISOString(),
    };
  }
  const res = await apiFetch<PauseResumeResponse>(`/fetchers/${fetcherId}/pause`, {
    method: 'POST',
    body: JSON.stringify({ idempotency_key: idempotencyKey }),
  });
  return res!;
}

/** POST /control/fetchers/{id}/resume — 恢复采集源 */
export async function resumeFetcher(
  fetcherId: string,
  idempotencyKey: string,
): Promise<PauseResumeResponse> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    const fetcher = MOCK_FETCHERS.find((f) => f.id === fetcherId);
    if (fetcher) {
      fetcher.status = 'running';
      fetcher.enabled = true;
    }
    return {
      fetcher_id: fetcherId,
      status: 'running',
      updated_at: new Date().toISOString(),
    };
  }
  const res = await apiFetch<PauseResumeResponse>(`/fetchers/${fetcherId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ idempotency_key: idempotencyKey }),
  });
  return res!;
}

/** PUT /control/fetchers/{id}/schedule — 调整采集频率 */
export async function updateSchedule(
  fetcherId: string,
  body: ScheduleUpdateRequest,
): Promise<ScheduleUpdateResponse> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 200));
    mockSchedules.set(fetcherId, body.schedule);
    const fetcher = MOCK_FETCHERS.find((f) => f.id === fetcherId);
    if (fetcher) {
      fetcher.schedule = body.schedule;
    }
    return {
      fetcher_id: fetcherId,
      schedule: body.schedule,
      updated_at: new Date().toISOString(),
    };
  }
  const res = await apiFetch<ScheduleUpdateResponse>(
    `/fetchers/${fetcherId}/schedule`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
  );
  return res!;
}

/** GET /control/operations/{id} — 查询操作状态 */
export async function getOperationStatus(
  operationId: string,
): Promise<OperationStatus | null> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 100));
    const op = mockOps.get(operationId);
    if (!op) return null;
    return { ...op };
  }
  return apiFetch<OperationStatus>(`/operations/${operationId}`);
}

/** GET /control/fetchers/{id}/allowed-schedules — 获取可选频率（补充端点，404 时返回 null） */
export async function getAllowedSchedules(
  fetcherId: string,
): Promise<AllowedSchedulesResponse | null> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 150));
    const current = mockSchedules.get(fetcherId) ?? 'I60';
    return { ...MOCK_ALLOWED_SCHEDULES, current };
  }
  return apiFetch<AllowedSchedulesResponse>(
    `/fetchers/${fetcherId}/allowed-schedules`,
    {},
    true, // 补充端点
  );
}
