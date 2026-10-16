import { useEffect, useState } from 'react';
import { FEEDS, type FeedConfig } from '@/config/dataSources';
import { fetchCsv, fetchJson } from '@/lib/readLayer';
import { useStatus, type Warning } from '@/state/StatusContext';

export interface FeedState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

/**
 * 统一读取层（扩展标准 #1）。
 * 通过 feed 名称从注册表取配置，底层经 readLayer 拉取；新增 feed 不改此 hook。
 * 同时完成 schema_version 校验、时间戳采集、缺失/失败告警上报。
 */
/**
 * 源级 status 判定（各 feed JSON 顶层 status 字段）—— 10-16 CHG-20261016T234234。
 *
 * fetcher 降级时写 `status: "unavailable"` + `events: []`：HTTP 200、JSON 合法、数组为空，
 * 与「真没事件」在数据形状上无法区分。若不读顶层 status，前端只会显示一个空图层，
 * 用户看到的是「这里没有事件」而不是「数据源不可用」—— 监控系统里最坏的失效模式。
 *
 * `ok` / 字段缺失 → null（不告警，与既有行为一致）。
 */
export function sourceStatusWarning(feed: string, path: string, status: unknown): Warning | null {
  if (status === undefined || status === null) return null;
  const s = String(status);
  if (s === 'ok') return null;
  return { feed, field: 'status', message: `${path} 数据源标记不可用（status=${s}）` };
}

export function useFeed<T = unknown>(feedName: string): FeedState<T> {
  const cfg: FeedConfig | undefined = FEEDS[feedName];
  const { report, setTimestamp, setDataVersion, clearField } = useStatus();
  const [state, setState] = useState<FeedState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!cfg) {
      setState({ data: null, loading: false, error: new Error(`未知 feed: ${feedName}`) });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));

    const run = async () => {
      try {
        const data: unknown = cfg.type === 'csv' ? await fetchCsv(cfg.path) : await fetchJson(cfg.path);
        if (cancelled) return;

        // csv 类型返回 FredPoint[] 数组，无 schema_version 字段（数组不做 schema 校验）
        const isObject = typeof data === 'object' && data !== null && !Array.isArray(data);
        if (!isObject) {
          setState({ data: data as T, loading: false, error: null });
          return;
        }

        const obj = data as { schema_version?: string; _schema_version?: string; updated?: unknown; gdelt_updated?: unknown; status?: unknown };
        // schema_version 校验：兼容带下划线前缀（_schema_version）和不带（schema_version）两种写法
        const sv = obj.schema_version ?? obj._schema_version;
        if (!sv) {
          setDataVersion(cfg.name, '缺失');
          report({
            feed: cfg.name,
            field: 'schema_version',
            message: `${cfg.path} 缺少 schema_version 字段`,
          });
        } else {
          setDataVersion(cfg.name, sv);
          if (sv !== cfg.schemaVersion) {
            report({
              feed: cfg.name,
              field: 'schema_version',
              message: `schema 版本不一致（期望 ${cfg.schemaVersion}，实际 ${sv}）`,
            });
          }
        }

        // 时间戳采集
        if (obj.updated !== undefined) {
          setTimestamp(cfg.name, obj.updated == null ? null : String(obj.updated));
        }
        if (obj.gdelt_updated !== undefined) {
          setTimestamp(`${cfg.name}_gdelt`, obj.gdelt_updated == null ? null : String(obj.gdelt_updated));
        }

        // 源级 status（10-16 CHG-20261016T234234）：fetcher 降级写 unavailable + 空数组时，
        // 空图层不得被误读成「无事发生」；源恢复后清除该字段告警，避免陈旧告警永久残留。
        const statusWarn = sourceStatusWarning(cfg.name, cfg.path, obj.status);
        if (statusWarn) report(statusWarn);
        else clearField(cfg.name, 'status');

        setState({ data: data as T, loading: false, error: null });
      } catch (e) {
        if (cancelled) return;
        // H18 (2026-08-16): tolerateEmpty feed（simTrigger）——历史残留 0 字节文件
        // （旧天璇 write_text("") 契约）JSON.parse 失败 → 静默 null，不上报"读取失败"
        if (cfg.tolerateEmpty) {
          setState({ data: null, loading: false, error: null });
          return;
        }
        const err = e instanceof Error ? e : new Error(String(e));
        report({ feed: cfg.name, field: '__load__', message: `读取失败：${cfg.path}` });
        setState({ data: null, loading: false, error: err });
      }
    };

    void run();
    // feed.refreshMs > 0 时轮询重拉（本地静态文件，成本极低；仅高频 feed 启用）
    let timer: ReturnType<typeof setInterval> | undefined;
    if (cfg.refreshMs && cfg.refreshMs > 0) {
      timer = setInterval(() => {
        void run();
      }, cfg.refreshMs);
    }
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [feedName, cfg, report, setTimestamp, setDataVersion, clearField]);

  return state;
}
