import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  StatusProvider,
  filterOutWarning,
  useStatus,
  type Warning,
} from '@/state/StatusContext';

/**
 * StatusContext 契约测试（filterOutWarning + Provider 装配）。
 *
 * ⚠ 测试策略说明（零新依赖铁律，同 SelectionContext.test.tsx）：vitest 跑 node 环境，
 * 无 jsdom / @testing-library/react，无法做「上报 → 断言重渲染」式交互测试。
 * 应对：把告警过滤收敛成纯函数 filterOutWarning 直接测（全分支覆盖），
 * 再用 react-dom 自带 renderToStaticMarkup 验证 Provider 装配与脱离 Provider 抛错。
 *
 * 10-16 CHG-20261016T234234：新增 clearField（feed 恢复后消陈旧告警）与共用纯函数。
 */

const W = (feed: string, field: string): Warning => ({ feed, field, message: `${feed}/${field}` });

const LIST: Warning[] = [
  W('health_geo', 'status'),
  W('health_geo', 'schema_version'),
  W('grv', 'status'),
];

/* ------------------------------------------------------------------ */
/* 纯函数：filterOutWarning                                            */
/* ------------------------------------------------------------------ */
describe('StatusContext: filterOutWarning', () => {
  it('省略 field → 移除该 feed 全部告警', () => {
    expect(filterOutWarning(LIST, 'health_geo')).toEqual([W('grv', 'status')]);
  });

  it('传入 field → 只移除该 feed:field 一条', () => {
    expect(filterOutWarning(LIST, 'health_geo', 'status')).toEqual([
      W('health_geo', 'schema_version'),
      W('grv', 'status'),
    ]);
  });

  it('同 feed 不同 field 互不影响（精确匹配）', () => {
    expect(filterOutWarning(LIST, 'health_geo', 'schema_version')).toEqual([
      W('health_geo', 'status'),
      W('grv', 'status'),
    ]);
  });

  it('feed 不命中 → 内容不变且返回新数组（不改入参）', () => {
    const out = filterOutWarning(LIST, 'nope', 'status');
    expect(out).toEqual(LIST);
    expect(out).not.toBe(LIST);
  });

  it('空列表 → 空列表', () => {
    expect(filterOutWarning([], 'health_geo', 'status')).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* Provider 装配（renderToStaticMarkup，零新依赖）                     */
/* ------------------------------------------------------------------ */
describe('StatusContext: Provider 装配', () => {
  it('Provider 正常渲染 children', () => {
    const html = renderToStaticMarkup(
      createElement(StatusProvider, null, createElement('span', null, 'ok')),
    );
    expect(html).toContain('ok');
  });

  it('脱离 Provider 使用 useStatus 抛错（含可定位信息）', () => {
    const Bad = () => {
      useStatus();
      return null;
    };
    expect(() => renderToStaticMarkup(createElement(Bad))).toThrow(/StatusProvider/);
  });
});
