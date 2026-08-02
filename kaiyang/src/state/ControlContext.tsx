/**
 * 控制面板全局状态 Context
 * 管理：抽屉开关 / Tab 切换 / Token / 操作锁 / Toast / 日志
 * 使用 useReducer 管理复杂状态，与现有 StatusContext 模式一致
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';
import type {
  ControlState,
  ControlAction,
  ControlTab,
  ControlContextValue,
  PendingOperation,
  ToastMessage,
  OperationLogEntry,
} from '@/types/control';
import {
  getEnvToken,
  getStoredToken,
  setStoredToken,
} from '@/config/controlConfig';
import { setApiToken } from '@/lib/controlApi';
import { readLogs, appendLog, writeLogs } from '@/lib/operationLog';

// ── 初始状态 ───────────────────────────────────────────────

/** 从优先级链读取初始 Token */
function resolveInitialToken(): string | null {
  const env = getEnvToken();
  if (env) return env;
  return getStoredToken();
}

const initialState: ControlState = {
  drawerOpen: false,
  activeTab: 'tianshu',
  token: resolveInitialToken(),
  pendingOps: {},
  toasts: [],
  logs: [],
  lockedFetchers: [],
};

// ── Reducer ────────────────────────────────────────────────

function controlReducer(state: ControlState, action: ControlAction): ControlState {
  switch (action.type) {
    case 'TOGGLE_DRAWER':
      return { ...state, drawerOpen: !state.drawerOpen };

    case 'CLOSE_DRAWER':
      return { ...state, drawerOpen: false };

    case 'SET_ACTIVE_TAB':
      return { ...state, activeTab: action.tab };

    case 'SET_TOKEN':
      return { ...state, token: action.token };

    case 'ADD_PENDING_OP':
      return {
        ...state,
        pendingOps: { ...state.pendingOps, [action.op.operationId]: action.op },
      };

    case 'REMOVE_PENDING_OP': {
      const { [action.id]: _removed, ...rest } = state.pendingOps;
      return { ...state, pendingOps: rest };
    }

    case 'ADD_TOAST':
      return { ...state, toasts: [...state.toasts, action.toast] };

    case 'REMOVE_TOAST':
      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== action.id),
      };

    case 'ADD_LOG': {
      const newLogs = [action.entry, ...state.logs].slice(0, 50);
      return { ...state, logs: newLogs };
    }

    case 'SET_LOGS':
      return { ...state, logs: action.logs };

    case 'LOCK_FETCHER':
      if (state.lockedFetchers.includes(action.id)) return state;
      return {
        ...state,
        lockedFetchers: [...state.lockedFetchers, action.id],
      };

    case 'UNLOCK_FETCHER':
      return {
        ...state,
        lockedFetchers: state.lockedFetchers.filter((id) => id !== action.id),
      };

    default:
      return state;
  }
}

// ── Context ────────────────────────────────────────────────

const Ctx = createContext<ControlContextValue | null>(null);

/** 控制面板状态 Provider */
export function ControlProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(controlReducer, initialState);

  // 启动时加载 localStorage 中的操作日志
  useEffect(() => {
    try {
      const stored = readLogs();
      if (stored.length > 0) {
        dispatch({ type: 'SET_LOGS', logs: stored });
      }
    } catch {
      /* 静默忽略 */
    }
  }, []);

  // Token 变更时同步到 API 客户端 + localStorage
  useEffect(() => {
    setApiToken(state.token);
    setStoredToken(state.token);
  }, [state.token]);

  // 日志变更时持久化
  useEffect(() => {
    writeLogs(state.logs);
  }, [state.logs]);

  // ── 操作方法 ────────────────────────────────────────────

  const toggleDrawer = useCallback(() => {
    dispatch({ type: 'TOGGLE_DRAWER' });
  }, []);

  const closeDrawer = useCallback(() => {
    dispatch({ type: 'CLOSE_DRAWER' });
  }, []);

  const setActiveTab = useCallback((tab: ControlTab) => {
    dispatch({ type: 'SET_ACTIVE_TAB', tab });
  }, []);

  const setToken = useCallback((t: string | null) => {
    dispatch({ type: 'SET_TOKEN', token: t });
  }, []);

  const addPendingOp = useCallback((op: PendingOperation) => {
    dispatch({ type: 'ADD_PENDING_OP', op });
  }, []);

  const removePendingOp = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_PENDING_OP', id });
  }, []);

  const showToast = useCallback((toast: Omit<ToastMessage, 'id'>) => {
    const id = crypto.randomUUID();
    dispatch({ type: 'ADD_TOAST', toast: { ...toast, id } });
  }, []);

  const dismissToast = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_TOAST', id });
  }, []);

  const addLog = useCallback(
    (entry: Omit<OperationLogEntry, 'id' | 'timestamp'>) => {
      const full: OperationLogEntry = {
        ...entry,
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
      };
      dispatch({ type: 'ADD_LOG', entry: full });
      // 同时写入 localStorage（双重写入，确保 Context 和 localStorage 同步）
      appendLog(full);
    },
    [],
  );

  const lockFetcher = useCallback((id: string) => {
    dispatch({ type: 'LOCK_FETCHER', id });
  }, []);

  const unlockFetcher = useCallback((id: string) => {
    dispatch({ type: 'UNLOCK_FETCHER', id });
  }, []);

  const isLocked = useCallback(
    (id: string) => state.lockedFetchers.includes(id),
    [state.lockedFetchers],
  );

  // ── Context Value ─────────────────────────────────────────

  const value = useMemo<ControlContextValue>(
    () => ({
      drawerOpen: state.drawerOpen,
      activeTab: state.activeTab,
      token: state.token,
      pendingOps: state.pendingOps,
      toasts: state.toasts,
      logs: state.logs,
      lockedFetchers: state.lockedFetchers,
      toggleDrawer,
      closeDrawer,
      setActiveTab,
      setToken,
      addPendingOp,
      removePendingOp,
      showToast,
      dismissToast,
      addLog,
      lockFetcher,
      unlockFetcher,
      isLocked,
    }),
    [
      state.drawerOpen,
      state.activeTab,
      state.token,
      state.pendingOps,
      state.toasts,
      state.logs,
      state.lockedFetchers,
      toggleDrawer,
      closeDrawer,
      setActiveTab,
      setToken,
      addPendingOp,
      removePendingOp,
      showToast,
      dismissToast,
      addLog,
      lockFetcher,
      unlockFetcher,
      isLocked,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** 使用控制面板 Context */
export function useControl(): ControlContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useControl 必须在 <ControlProvider> 内使用');
  return v;
}
