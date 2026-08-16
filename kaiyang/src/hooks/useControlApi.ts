/**
 * 控制面板数据获取 Hooks
 * 当前实现：useFetchers()。
 * useOperationStatus / useAllowedSchedules 暂未在任何组件中使用，
 * 后续如需单点查询 / 运行时拉取频率选项，可从 git history 找回。
 * 复用现有 useFeed 的 SWR 风格（手动 refresh + loading/error/data 三态）
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { getFetchers } from '@/lib/controlApi';
import { useControl } from '@/state/ControlContext';
import type { Fetcher } from '@/types/control';

// ── 通用异步状态 ────────────────────────────────────────────

/** 异步数据状态 */
interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

// ── useFetchers ──────────────────────────────────────────────

/** 获取全部采集源列表，支持手动刷新 */
export function useFetchers(): AsyncState<Fetcher[]> & { refresh: () => void } {
  const { token, setToken } = useControl();
  const [state, setState] = useState<AsyncState<Fetcher[]>>({
    data: null,
    loading: true,
    error: null,
  });
  const mountedRef = useRef(true);

  const fetch = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await getFetchers();
      if (mountedRef.current) {
        setState({ data: res.fetchers, loading: false, error: null });
      }
    } catch (err) {
      if ((err as { code?: number }).code === 401) {
        setToken(null);
      }
      if (mountedRef.current) {
        setState({
          data: null,
          loading: false,
          error: err instanceof Error ? err.message : '获取采集源列表失败',
        });
      }
    }
  }, [setToken]);

  // 08-16：token 变化（配置/清除）时自动重新拉取，免手动重试
  useEffect(() => {
    mountedRef.current = true;
    fetch();
    return () => {
      mountedRef.current = false;
    };
  }, [fetch, token]);

  return { ...state, refresh: fetch };
}
