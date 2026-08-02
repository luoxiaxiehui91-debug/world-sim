/**
 * 天枢 Tab 主组件
 * 采集源管理：搜索 + fetcher 卡片列表 + 批量重跑
 * 包含 Token 未配置警告横幅
 */

import { useState, useMemo, useCallback } from 'react';
import { useControl } from '@/state/ControlContext';
import { useFetchers } from '@/hooks/useControlApi';
import { useOperationPolling } from '@/hooks/useOperationPolling';
import { rerunFetchers } from '@/lib/controlApi';
import { FetcherCard } from '@/control/FetcherCard';
import type { Fetcher } from '@/types/control';

/** 搜索过滤 fetcher */
function filterFetchers(fetchers: Fetcher[], query: string): Fetcher[] {
  if (!query.trim()) return fetchers;
  const q = query.trim().toLowerCase();
  return fetchers.filter(
    (f) =>
      f.id.toLowerCase().includes(q) || f.name.toLowerCase().includes(q),
  );
}

export function TianshuTab() {
  const {
    token,
    showToast,
    addPendingOp,
    lockFetcher,
    unlockFetcher,
    isLocked,
    setToken,
  } = useControl();

  // 数据获取
  const { data: fetchers, loading, error, refresh } = useFetchers();

  // 启动操作轮询
  useOperationPolling();

  // 搜索状态
  const [searchQuery, setSearchQuery] = useState('');

  // 批量选择状态
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 过滤后的列表
  const filtered = useMemo(
    () => (fetchers ? filterFetchers(fetchers, searchQuery) : []),
    [fetchers, searchQuery],
  );

  // 全选/取消全选
  const allSelected =
    filtered.length > 0 && filtered.every((f) => selectedIds.has(f.id));

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((f) => f.id)));
    }
  };

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // 批量重跑
  const handleBatchRerun = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;

    const idempotencyKey = crypto.randomUUID();
    const lockedIds: string[] = [];

    // 先锁定所有选中的 fetcher
    for (const id of ids) {
      if (!isLocked(id)) {
        lockFetcher(id);
        lockedIds.push(id);
      }
    }

    try {
      const res = await rerunFetchers({
        fetcher_ids: ids,
        idempotency_key: idempotencyKey,
      });

      // 添加进行中操作
      addPendingOp({
        operationId: res.operation_id,
        type: 'fetcher_rerun',
        fetcherIds: ids,
        idempotencyKey,
        startedAt: new Date().toISOString(),
        status: 'accepted',
      });

      showToast({
        type: 'info',
        message: `批量重跑已提交`,
        detail: `${ids.length} 个采集源，操作ID: ${res.operation_id}`,
      });
    } catch (err) {
      if ((err as { code?: number }).code === 401) {
        setToken(null);
      }
      showToast({
        type: 'error',
        message: '批量重跑失败',
        detail: err instanceof Error ? err.message : '未知错误',
      });
      // 解锁
      for (const id of lockedIds) {
        unlockFetcher(id);
      }
    }
  }, [selectedIds, isLocked, lockFetcher, unlockFetcher, addPendingOp, showToast, setToken]);

  // ── 加载态 ──────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center text-[12px] text-white/40">
        <span className="animate-spin-slow mr-2 inline-block h-4 w-4 rounded-full border-2 border-cyan-400/30 border-t-cyan-400" />
        加载采集源列表...
      </div>
    );
  }

  // ── 错误态 ──────────────────────────────────────────────

  if (error) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-3 text-center">
        <p className="text-[12px] text-red-400">加载失败：{error}</p>
        <button
          type="button"
          onClick={refresh}
          className="chip cursor-pointer border-cyan-400/30 text-cyan-300 hover:bg-cyan-500/10"
        >
          重试
        </button>
      </div>
    );
  }

  // ── 空态 ────────────────────────────────────────────────

  if (!fetchers || fetchers.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-[12px] text-white/30">
        暂无采集源
      </div>
    );
  }

  // ── 正常渲染 ────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-3 pt-3">
      {/* Token 未配置警告横幅 */}
      {!token && (
        <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
          ⚠ 未配置 API Token，部分操作可能受限。请配置 Token 后使用。
        </div>
      )}

      {/* 搜索栏 + 批量操作 */}
      <div className="flex items-center gap-2">
        {/* 搜索框 */}
        <div className="relative flex-1">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px] text-white/30">
            🔍
          </span>
          <input
            type="text"
            placeholder="搜索采集源..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-white/5 py-1.5 pl-7 pr-2.5 text-[11px] text-white/80 placeholder:text-white/25 outline-none transition-colors focus:border-cyan-400/40"
          />
        </div>

        {/* 批量重跑按钮 */}
        {selectedIds.size > 0 && (
          <button
            type="button"
            onClick={handleBatchRerun}
            className="chip cursor-pointer border-cyan-400/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20"
            title={`批量重跑 ${selectedIds.size} 个采集源`}
          >
            重跑({selectedIds.size})
          </button>
        )}
      </div>

      {/* 全选行 */}
      {filtered.length > 0 && (
        <label className="flex cursor-pointer items-center gap-2 text-[11px] text-white/40 hover:text-white/60">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleSelectAll}
            className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-cyan-400"
          />
          全选 ({filtered.length})
        </label>
      )}

      {/* Fetcher 卡片列表 */}
      <div className="flex flex-col gap-2">
        {filtered.map((fetcher) => (
          <FetcherCard
            key={fetcher.id}
            fetcher={fetcher}
            selected={selectedIds.has(fetcher.id)}
            onToggleSelect={() => toggleSelect(fetcher.id)}
            onRefresh={refresh}
          />
        ))}
      </div>

      {/* 无搜索结果 */}
      {filtered.length === 0 && searchQuery.trim() && (
        <div className="py-8 text-center text-[12px] text-white/30">
          没有匹配「{searchQuery}」的采集源
        </div>
      )}
    </div>
  );
}
