import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  EMPTY_SELECTION,
  SelectionProvider,
  selectionReducer,
  useSelection,
  type SelectionSnapshot,
} from '@/state/SelectionContext';

/**
 * SelectionContext 契约测试。
 *
 * ⚠ 测试策略说明（零新依赖铁律）：本项目 vitest 跑在 **node 环境**，未安装 jsdom /
 * @testing-library/react，因此无法做「点击 → 断言重渲染」式的交互测试。
 * 应对：把状态迁移收敛成纯函数 `selectionReducer` 直接测（select / clearFocus 全覆盖），
 * 再用 react-dom 自带的 `renderToStaticMarkup`（既有依赖，零新增）验证
 * Provider 装配、默认值下发与「脱离 Provider 使用会抛错」这三件事。
 */

/* ------------------------------------------------------------------ */
/* 纯 reducer：select / clearFocus                                     */
/* ------------------------------------------------------------------ */
describe('SelectionContext: selectionReducer', () => {
  it('初始快照两槽位均为 null', () => {
    expect(EMPTY_SELECTION).toEqual({ selectedSignalKey: null, focusPointId: null });
  });

  it('select：写入信号 key（无 focus 时 focusPointId 为 null）', () => {
    const next = selectionReducer(EMPTY_SELECTION, {
      type: 'select',
      key: 'cpi-3',
      focusPointId: null,
    });
    expect(next).toEqual({ selectedSignalKey: 'cpi-3', focusPointId: null });
  });

  it('select：可同时写入信号 key 与地图聚焦点 id', () => {
    const next = selectionReducer(EMPTY_SELECTION, {
      type: 'select',
      key: 'sig-1',
      focusPointId: 'geo:taiwan_strait',
    });
    expect(next.selectedSignalKey).toBe('sig-1');
    expect(next.focusPointId).toBe('geo:taiwan_strait');
  });

  it('select：key 传 null 表示取消选中（同时清 focus）', () => {
    const selected: SelectionSnapshot = {
      selectedSignalKey: 'sig-1',
      focusPointId: 'geo:taiwan_strait',
    };
    const next = selectionReducer(selected, { type: 'select', key: null, focusPointId: null });
    expect(next).toEqual(EMPTY_SELECTION);
  });

  it('select：只给 focusPointId（地图点反向选中场景），信号 key 为 null', () => {
    const next = selectionReducer(EMPTY_SELECTION, {
      type: 'select',
      key: null,
      focusPointId: 'nuclear:zaporizhzhia',
    });
    expect(next).toEqual({ selectedSignalKey: null, focusPointId: 'nuclear:zaporizhzhia' });
  });

  it('clearFocus：只清地图聚焦，保留信号行选中', () => {
    const selected: SelectionSnapshot = { selectedSignalKey: 'sig-9', focusPointId: 'geo:x' };
    const next = selectionReducer(selected, { type: 'clearFocus' });
    expect(next).toEqual({ selectedSignalKey: 'sig-9', focusPointId: null });
  });

  it('clearFocus：本已无聚焦时返回原对象引用（不触发无谓重渲染）', () => {
    const state: SelectionSnapshot = { selectedSignalKey: 'sig-9', focusPointId: null };
    expect(selectionReducer(state, { type: 'clearFocus' })).toBe(state);
  });

  it('select：值未变化时返回原对象引用', () => {
    const state: SelectionSnapshot = { selectedSignalKey: 'sig-9', focusPointId: 'geo:x' };
    const next = selectionReducer(state, {
      type: 'select',
      key: 'sig-9',
      focusPointId: 'geo:x',
    });
    expect(next).toBe(state);
  });

  it('reducer 不修改入参（纯函数）', () => {
    const state: SelectionSnapshot = { selectedSignalKey: 'a', focusPointId: 'b' };
    selectionReducer(state, { type: 'select', key: 'c', focusPointId: 'd' });
    selectionReducer(state, { type: 'clearFocus' });
    expect(state).toEqual({ selectedSignalKey: 'a', focusPointId: 'b' });
  });

  it('未知 action 原样返回（前向兼容，不抛异常）', () => {
    const state: SelectionSnapshot = { selectedSignalKey: 'a', focusPointId: 'b' };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(selectionReducer(state, { type: 'unknown' } as any)).toBe(state);
  });
});

/* ------------------------------------------------------------------ */
/* Provider 装配                                                       */
/* ------------------------------------------------------------------ */
function Probe() {
  const { selectedSignalKey, focusPointId, selectSignal, clearFocus } = useSelection();
  return (
    <i
      data-selected={String(selectedSignalKey)}
      data-focus={String(focusPointId)}
      data-api={`${typeof selectSignal}/${typeof clearFocus}`}
    />
  );
}

describe('SelectionContext: SelectionProvider', () => {
  it('渲染子树，并向消费者下发初始 null 选中态与两个回调', () => {
    const html = renderToStaticMarkup(
      <SelectionProvider>
        <Probe />
      </SelectionProvider>,
    );
    expect(html).toContain('data-selected="null"');
    expect(html).toContain('data-focus="null"');
    expect(html).toContain('data-api="function/function"');
  });

  it('脱离 Provider 使用 useSelection 会抛出中文提示', () => {
    expect(() => renderToStaticMarkup(<Probe />)).toThrow('useSelection 必须在 <SelectionProvider> 内使用');
  });
});
