import { useEffect, useState } from 'react';
import { fetchCsv } from '@/lib/readLayer';
import type { FredManifest, FredSeries } from '@/types/contracts';
import { useStatus } from '@/state/StatusContext';

/**
 * 加载 FRED 清单中各序列的 CSV（同经 readLayer，不改读取层）。
 * manifest 为 null 时不加载；单个序列失败则降级为空序列并上报告警。
 */
export function useFRED(manifest: FredManifest | null): {
  series: FredSeries[];
  loading: boolean;
  error: Error | null;
} {
  const { report } = useStatus();
  const [series, setSeries] = useState<FredSeries[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!manifest) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    const metas = manifest.series ?? [];
    Promise.all(
      metas.map(async (m): Promise<FredSeries> => {
        try {
          const points = await fetchCsv(m.file);
          return { ...m, points };
        } catch {
          report({ feed: 'fred', field: m.id, message: `FRED 序列缺失：${m.file}` });
          return { ...m, points: [] };
        }
      }),
    )
      .then((res) => {
        if (!cancelled) {
          setSeries(res);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [manifest, report]);

  return { series, loading, error };
}
