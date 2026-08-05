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
  // 分类折叠状态（默认全部展开；点击组头切换）
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const filtered = useMemo(
    () => (fetchers ? filterFetchers(fetchers, searchQuery) : []),
    [fetchers, searchQuery],
  );

  // 分组定义：按 id 前缀/关键词映射到类别，解决平铺列表太乱的问题
  const GROUP_DEFS: { key: string; label: string; match: (id: string) => boolean }[] = [
    { key: 'macro', label: '宏观·FRED', match: (id) => /^(fred|fci|probit|macro|fx|world|gpr|sanctions|us_daily|china_daily)/.test(id) },
    { key: 'geo', label: '地缘', match: (id) => /^(geo|grv|gdelt)/.test(id) },
    { key: 'news', label: '新闻', match: (id) => /^(news|rss|defense|sipri)/.test(id) },
    { key: 'market', label: '市场', match: (id) => /^(crypto|commodity|market|energy|bdi|fao|china_fetch|china_meso)/.test(id) },
    { key: 'disaster', label: '灾害', match: (id) => /^(disaster|earthquake|climate|firms|hdx)/.test(id) },
    { key: 'satellite', label: '卫星', match: (id) => /^(space|spacetrack|opensky|airtraffic)/.test(id) },
    { key: 'sim', label: '推演/验证', match: (id) => /^(compute|verify|tianji|weight|narrative|slow|sim|morning|weekly|kb|health|observability|prune|export)/.test(id) },
  ];
  const grouped = useMemo(() => {
    const groups: { key: string; label: string; items: Fetcher[] }[] = GROUP_DEFS.map((g) => ({ ...g, items: [] }));
    const other: Fetcher[] = [];
    for (const f of filtered) {
      const g = GROUP_DEFS.find((d) => d.match(f.id));
      if (g) {
        groups.find((x) => x.key === g.key)?.items.push(f);
      } else {
        other.push(f);
      }
    }
    // 组内：异常状态优先，然后按 id 排序
    const sortItems = (arr: Fetcher[]) => [...arr].sort((a, b) => {
      const aBad = a.last_status !== 'success' ? 0 : 1;
      const bBad = b.last_status !== 'success' ? 0 : 1;
      return aBad - bBad || a.id.localeCompare(b.id);
    });
    const visible = groups.map((g) => ({ ...g, items: sortItems(g.items) })).filter((g) => g.items.length > 0);
    if (other.length > 0) visible.push({ key: 'other', label: '其他', items: sortItems(other) });
    return visible;
  }, [filtered]);

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

      {/* Fetcher 卡片列表（按类别分组） */}
      {grouped.map((g) => (
        <div key={g.key} className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => toggleGroup(g.key)}
            className="mt-1 flex w-full cursor-pointer items-center gap-2 text-left"
            title={collapsedGroups.has(g.key) ? '展开' + g.label : '折叠' + g.label}
          >
            <svg
              className={`h-2.5 w-2.5 shrink-0 transition-transform duration-150 ${
                collapsedGroups.has(g.key) ? '-rotate-90' : ''
              }`}
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M6 4l4 4-4 4" />
            </svg>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300/70">
              {g.label}
            </span>
            <span className="rounded bg-white/5 px-1.5 py-px text-[9px] text-white/35">
              {g.items.length}
            </span>
            {g.items.some((f) => f.last_status !== 'success') && (
              <span className="text-[9px] text-amber-300/80">⚠ 异常</span>
            )}
              <div className="h-px flex-1 bg-white/5" />
          </button>
          {!collapsedGroups.has(g.key) && (
          <div className="flex flex-col gap-2">
            {g.items.map((fetcher) => (
              <FetcherCard
                key={fetcher.id}
                fetcher={fetcher}
                selected={selectedIds.has(fetcher.id)}
                onToggleSelect={() => toggleSelect(fetcher.id)}
                onRefresh={refresh}
              />
              ))}
          </div>
          )}
        </div>
      ))}

      {/* 无搜索结果 */}
      {filtered.length === 0 && searchQuery.trim() && (
        <div className="py-8 text-center text-[12px] text-white/30">
          没有匹配「{searchQuery}」的采集源
        </div>
      )}
    </div>
  );
}
