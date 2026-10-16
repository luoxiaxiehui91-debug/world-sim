import { describe, it, expect } from 'vitest';
import { sourceStatusWarning } from '@/hooks/useFeed';

/**
 * useFeed 源级 status 判定测试（10-16 CHG-20261016T234234）。
 *
 * 背景：各 fetcher 的 JSON 顶层带 status 字段，降级时写 `status: "unavailable"` +
 * `events: []`。HTTP 200 + JSON 合法 + 空数组，与「真没事件」在数据形状上无法区分；
 * 前端若不读顶层 status，空图层会被误读成「无事发生」（监控系统最坏失效模式）。
 *
 * ⚠ 只测纯函数 sourceStatusWarning：useFeed 本体是 React hook（node 环境无 renderHook），
 * 其接线（report / clearField）由构建期 tsc + 人工链路验证覆盖。
 */

const PATH = '/data/health_geo.json';

describe('useFeed: sourceStatusWarning', () => {
  it('status=ok → null（不告警，与既有行为一致）', () => {
    expect(sourceStatusWarning('health_geo', PATH, 'ok')).toBeNull();
  });

  it('status 字段缺失 → null（旧数据无该字段，不新增伪告警）', () => {
    expect(sourceStatusWarning('health_geo', PATH, undefined)).toBeNull();
    expect(sourceStatusWarning('health_geo', PATH, null)).toBeNull();
  });

  it('status=unavailable → 告警，feed/field/message 三要素齐全', () => {
    const w = sourceStatusWarning('health_geo', PATH, 'unavailable');
    expect(w).not.toBeNull();
    expect(w!.feed).toBe('health_geo');
    expect(w!.field).toBe('status');
    expect(w!.message).toContain(PATH);
    expect(w!.message).toContain('unavailable');
  });

  it('非字符串 status（数字 / 对象）也判定为异常值', () => {
    expect(sourceStatusWarning('f', PATH, 503)?.message).toContain('503');
    expect(sourceStatusWarning('f', PATH, { a: 1 })?.message).toContain('[object Object]');
  });

  it('空字符串 status → 告警（fetcher 不会写空串，保守按异常处理）', () => {
    expect(sourceStatusWarning('f', PATH, '')).not.toBeNull();
  });

  it('field 固定为 status（与 StatusContext 的 feed:field 去重键对齐）', () => {
    const w = sourceStatusWarning('firms', '/data/firms.json', 'degraded');
    expect(w!.field).toBe('status');
  });
});
