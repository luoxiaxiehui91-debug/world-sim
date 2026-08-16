/**
 * 开阳控制面板 · TypeScript 类型定义
 * 对应系统设计 Part A §3.1 类型图 + 后端接口需求回复 §2-3
 */

// ── Fetcher（采集源）──────────────────────────────────────

/** 采集源状态（与后端 jobs.state.yaml 对齐） */
export type FetcherStatus = 'running' | 'paused' | 'error';

/** 采集源上次运行结果 */
export type FetcherLastStatus = 'success' | 'failed' | null;

/** 单个采集源实体（对应 GET /control/fetchers 返回的数组元素） */
export interface Fetcher {
  /** 唯一标识，即模块名（如 fetch_earthquake） */
  id: string;
  /** 人类可读名称 */
  name: string;
  /** 运行状态 */
  status: FetcherStatus;
  /** 调度表达式（如 I15 / H6 / cron 0 9 * * *） */
  schedule: string;
  /** 上次运行时间（ISO 8601），null 表示从未运行 */
  last_run_at: string | null;
  /** 上次运行结果 */
  last_status: FetcherLastStatus;
  /** 下次计划运行时间（ISO 8601），null 表示未知 */
  next_run_at: string | null;
  /** 采集源是否启用（暂停/恢复状态） */
  enabled: boolean;
}

/** GET /control/fetchers 响应 */
export interface FetcherListResponse {
  fetchers: Fetcher[];
}

// ── 调度频率 ──────────────────────────────────────────────

/** 单个频率选项（对应 allowed-schedules 端点返回） */
export interface ScheduleOption {
  /** 中文标签，如「每15分钟」 */
  label: string;
  /** 调度表达式值，如「I15」 */
  value: string;
  /** 补充说明，如「≤50% 安全水位」 */
  description: string;
}

/** GET /control/fetchers/{id}/allowed-schedules 响应 */
export interface AllowedSchedulesResponse {
  /** 当前频率 */
  current: string;
  /** 可选频率列表 */
  options: ScheduleOption[];
}

// ── 操作状态机 ────────────────────────────────────────────

/** 操作状态（accepted → queued → running → completed/failed） */
export type OperationState =
  | 'accepted'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed';

/** API 错误详情 */
export interface ApiErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

/** API 错误响应 */
export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

/** LLM 使用点（GET /control/llm-usage；08-16 开阳控制台统一改模型） */
export interface LlmUsage {
  id: string;
  name: string;
  purpose: string;
  /** 代码/环境默认模型；None 时展示 "（env 默认）" */
  default_model: string | null;
  endpoint: string;
  container: 'tianshu' | 'tianxuan' | 'tianji' | string;
  adjustable: boolean;
  /** 当前生效模型（配置覆盖 > 默认） */
  model: string;
  /** 是否被 llm_config.json 覆盖 */
  overridden: boolean;
}

export interface LlmUsageResponse {
  usages: LlmUsage[];
}

/** 操作状态（GET /control/operations/{id} 响应） */
export interface OperationStatus {
  operation_id: string;
  command_id: string;
  idempotency_key: string;
  type: string;
  status: OperationState;
  /** 进度 0-100 */
  progress: number;
  /** 人类可读进度描述 */
  progress_message: string;
  /** 受影响的 fetcher ID 列表 */
  affected_fetchers: string[];
  /** completed 时的结果数据 */
  result: unknown;
  /** failed 时的错误信息 */
  error: ApiErrorDetail | null;
  created_at: string;
  completed_at: string | null;
}

// ── 请求/响应体 ───────────────────────────────────────────

/** POST /control/fetchers/rerun 请求体 */
export interface RerunRequest {
  fetcher_ids: string[];
  idempotency_key: string;
}

/** POST /control/fetchers/rerun 响应体 */
export interface RerunResponse {
  operation_id: string;
  status: string;
  affected_fetchers: string[];
}

/** POST pause/resume 响应体 */
export interface PauseResumeResponse {
  fetcher_id: string;
  status: string;
  updated_at: string;
}

/** PUT schedule 请求体 */
export interface ScheduleUpdateRequest {
  schedule: string;
}

/** PUT schedule 响应体 */
export interface ScheduleUpdateResponse {
  fetcher_id: string;
  schedule: string;
  updated_at: string;
}

// ── 前端状态实体 ──────────────────────────────────────────

/** 控制面板 Tab 标识 */
export type ControlTab =
  | 'tianshu'
  | 'tianxuan'
  | 'tianji'
  | 'yuheng'
  | 'operation_log';

/** Tab 配置项 */
export interface TabConfig {
  key: ControlTab;
  label: string;
  icon: string;
}

/** Toast 消息 */
export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
  detail?: string;
  /** 显示时长（毫秒），默认 4000 */
  duration?: number;
}

/** 进行中的操作（前端追踪用） */
export interface PendingOperation {
  operationId: string;
  type: string;
  fetcherIds: string[];
  idempotencyKey: string;
  startedAt: string;
  status: OperationState;
}

/** 操作日志条目（localStorage 持久化） */
export interface OperationLogEntry {
  id: string;
  timestamp: string;
  status: 'success' | 'failed' | 'pending';
  domain: 'tianshu';
  operation: string;
  description: string;
  detail?: string;
}

// ── ControlContext ─────────────────────────────────────────

/** ControlContext 对外暴露的值 */
export interface ControlContextValue {
  drawerOpen: boolean;
  activeTab: ControlTab;
  token: string | null;
  pendingOps: Record<string, PendingOperation>;
  toasts: ToastMessage[];
  logs: OperationLogEntry[];
  lockedFetchers: string[];
  toggleDrawer: () => void;
  closeDrawer: () => void;
  setActiveTab: (tab: ControlTab) => void;
  setToken: (t: string | null) => void;
  addPendingOp: (op: PendingOperation) => void;
  removePendingOp: (id: string) => void;
  showToast: (toast: Omit<ToastMessage, 'id'>) => void;
  dismissToast: (id: string) => void;
  addLog: (entry: Omit<OperationLogEntry, 'id' | 'timestamp'>) => void;
  lockFetcher: (id: string) => void;
  unlockFetcher: (id: string) => void;
  isLocked: (id: string) => boolean;
}

// ── Reducer ────────────────────────────────────────────────

/** useReducer 的 state 形状 */
export interface ControlState {
  drawerOpen: boolean;
  activeTab: ControlTab;
  token: string | null;
  pendingOps: Record<string, PendingOperation>;
  toasts: ToastMessage[];
  logs: OperationLogEntry[];
  lockedFetchers: string[];
}

/** useReducer 的 action 联合类型 */
export type ControlAction =
  | { type: 'TOGGLE_DRAWER' }
  | { type: 'CLOSE_DRAWER' }
  | { type: 'SET_ACTIVE_TAB'; tab: ControlTab }
  | { type: 'SET_TOKEN'; token: string | null }
  | { type: 'ADD_PENDING_OP'; op: PendingOperation }
  | { type: 'REMOVE_PENDING_OP'; id: string }
  | { type: 'ADD_TOAST'; toast: ToastMessage }
  | { type: 'REMOVE_TOAST'; id: string }
  | { type: 'ADD_LOG'; entry: OperationLogEntry }
  | { type: 'SET_LOGS'; logs: OperationLogEntry[] }
  | { type: 'LOCK_FETCHER'; id: string }
  | { type: 'UNLOCK_FETCHER'; id: string };
