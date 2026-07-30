import { DATA_BASE_URL } from '@/config/dataSources';
import type { FredPoint } from '@/types/contracts';

/**
 * 统一底层读取层。
 * 所有数据均经此层从 DATA_BASE_URL 拉取；新增 feed / 序列不改此处（扩展标准 #1）。
 */

/**
 * 同路径并发去重：多个面板同时读取同一 feed（如 grv 被地图/摘要/GRV/状态条共用）时，
 * 只发一次网络请求，避免 StrictMode 双挂载与多面板重复拉取。请求结束即释放，不做持久缓存。
 */
const inFlight = new Map<string, Promise<string>>();

export async function fetchText(relativePath: string): Promise<string> {
  const url = DATA_BASE_URL + relativePath;
  const existing = inFlight.get(url);
  if (existing) return existing;

  const task = (async (): Promise<string> => {
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`数据读取失败 ${url} (HTTP ${res.status})`);
    }
    return res.text();
  })();

  inFlight.set(url, task);
  try {
    return await task;
  } finally {
    inFlight.delete(url);
  }
}

export async function fetchJson<T>(relativePath: string): Promise<T> {
  const text = await fetchText(relativePath);
  return JSON.parse(text) as T;
}

export async function fetchCsv(relativePath: string): Promise<FredPoint[]> {
  const text = await fetchText(relativePath);
  return parseFredCsv(text);
}

/** 解析 FRED CSV（首行为表头 date,value；末列为数值列）。 */
export function parseFredCsv(text: string): FredPoint[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length < 2) return [];
  const header = lines[0].split(',').map((s) => s.trim());
  const dateIdx = 0;
  const valueIdx = header.length - 1; // FRED 末列为数值
  const out: FredPoint[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    const date = cols[dateIdx]?.trim();
    const raw = cols[valueIdx]?.trim();
    if (!date || raw === undefined || raw === '') continue;
    const value = Number(raw);
    if (Number.isFinite(value)) {
      out.push({ date, value });
    }
  }
  return out;
}
