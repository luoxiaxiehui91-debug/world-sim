import type { FredManifest, GrvRaw, NewsItem, SimTriggerRaw } from '@/types/contracts';

/**
 * 数据根地址（DATA_BASE_URL）。
 * 优先级：构建期环境变量 VITE_DATA_BASE_URL > 运行时全局 window.__KAIYANG_DATA_BASE_URL__ > 默认 './data/'。
 * NAS 部署时由容器注入只读挂载路径（如 '/mnt/tianshu-data/'）。
 */
export const DATA_BASE_URL: string = (() => {
  const fromEnv = import.meta.env.VITE_DATA_BASE_URL as string | undefined;
  const fromGlobal = (
    window as unknown as { __KAIYANG_DATA_BASE_URL__?: string }
  ).__KAIYANG_DATA_BASE_URL__;
  const raw = fromEnv ?? fromGlobal ?? './data/';
  return raw.endsWith('/') ? raw : `${raw}/`;
})();

/** feed 注册项：新增数据源只需在此登记，读取层无需改动（扩展标准 #1）。 */
export interface FeedConfig {
  name: string;
  /** 相对 DATA_BASE_URL 的路径 */
  path: string;
  type: 'json' | 'csv';
  /** 期望的 schema 版本（breaking change 须 bump） */
  schemaVersion: string;
  description: string;
}

export const FEEDS: Record<string, FeedConfig> = {
  grv: {
    name: 'grv',
    path: 'grv_latest.json',
    type: 'json',
    schemaVersion: '1.0',
    description: 'GRV 11 维风险状态（含不确定区间）',
  },
  news: {
    name: 'news',
    path: 'news_export.json',
    type: 'json',
    schemaVersion: '1.0',
    description: '新闻 / 叙事导出',
  },
  simTrigger: {
    name: 'simTrigger',
    path: 'sim_trigger.json',
    type: 'json',
    schemaVersion: '1.0',
    description: '推演触发状态（可选）',
  },
  fred: {
    name: 'fred',
    path: 'fred_history/manifest.json',
    type: 'json',
    schemaVersion: '1.0',
    description: 'FRED 关键序列清单',
  },
};

// 仅用于类型推导的占位（避免未使用导入告警）。
export type _Grv = GrvRaw;
export type _News = NewsItem;
export type _Sim = SimTriggerRaw;
export type _Fred = FredManifest;
