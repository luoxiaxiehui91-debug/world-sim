import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

/** 缺失 / 异常告警项（扩展标准 #3：字段容错 + 状态条记录）。 */
export interface Warning {
  feed: string;
  field: string;
  message: string;
}

interface StatusApi {
  warnings: Warning[];
  /** 上报告警（按 feed:field 去重） */
  report: (w: Warning) => void;
  /** 清除某 feed 的全部告警 */
  clear: (feed: string) => void;
  /** 各 feed 数据时间戳 */
  timestamps: Record<string, string | null>;
  setTimestamp: (key: string, t: string | null) => void;
  /** 推演触发状态（可选） */
  simTrigger: Record<string, unknown> | null;
  setSimTrigger: (v: Record<string, unknown> | null) => void;
  /** 各 feed 实际 schema 版本 */
  dataVersions: Record<string, string | null>;
  setDataVersion: (feed: string, v: string | null) => void;
}

const Ctx = createContext<StatusApi | null>(null);

export function StatusProvider({ children }: { children: ReactNode }) {
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [timestamps, setTimestamps] = useState<Record<string, string | null>>({});
  const [simTrigger, setSimTrigger] = useState<Record<string, unknown> | null>(null);
  const [dataVersions, setDataVersions] = useState<Record<string, string | null>>({});
  // 跨渲染去重集合（不触发重渲染）
  const seen = useRef<Set<string>>(new Set());

  const report = useCallback((w: Warning) => {
    const key = `${w.feed}:${w.field}`;
    if (seen.current.has(key)) return;
    seen.current.add(key);
    setWarnings((prev) => [...prev, w]);
  }, []);

  const clear = useCallback((feed: string) => {
    setWarnings((prev) => prev.filter((x) => x.feed !== feed));
    for (const k of Array.from(seen.current)) {
      if (k.startsWith(`${feed}:`)) seen.current.delete(k);
    }
  }, []);

  const setTimestamp = useCallback((key: string, t: string | null) => {
    setTimestamps((prev) => (prev[key] === t ? prev : { ...prev, [key]: t }));
  }, []);

  const setDataVersion = useCallback((feed: string, v: string | null) => {
    setDataVersions((prev) => (prev[feed] === v ? prev : { ...prev, [feed]: v }));
  }, []);

  const api = useMemo<StatusApi>(
    () => ({
      warnings,
      report,
      clear,
      timestamps,
      setTimestamp,
      simTrigger,
      setSimTrigger,
      dataVersions,
      setDataVersion,
    }),
    [warnings, report, clear, timestamps, setTimestamp, simTrigger, dataVersions, setDataVersion],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useStatus(): StatusApi {
  const v = useContext(Ctx);
  if (!v) throw new Error('useStatus 必须在 <StatusProvider> 内使用');
  return v;
}
