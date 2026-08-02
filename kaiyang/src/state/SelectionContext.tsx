import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';

/**
 * 跨面板「选中 / 聚焦」共享态（R-P1-03）。
 *
 * 两个正交的槽位，**刻意分开**：
 * - `selectedSignalKey`：右侧信号流里被点中的那一行（纯 UI 选中态）。
 * - `focusPointId`：地图上要聚焦高亮的 `RiskPoint.id`（相机 + 光环）。
 *
 * 为什么分开：当前 news 信号**没有坐标**（`news_export.json` 无 lat/lng，也无对应地图点 id），
 * 点信号只能做行内选中，跳不了地图。把两个槽位分开，就能诚实表达
 * 「选中了信号，但没有可聚焦的地图点」这一真实状态，而不是伪造一个跳转目标。
 * 等天枢 GDELT `news_geo` feed 就绪、信号带上 `focusId` 后，
 * 只要在 `selectSignal(key, focusId)` 第二参传值即可自动联动，本层无需改动。
 *
 * 状态迁移收敛在纯函数 `selectionReducer` 里，便于零依赖单测（本项目 vitest 跑 node 环境，无 DOM）。
 */

/** 可序列化的选中快照（纯数据，无回调）。 */
export interface SelectionSnapshot {
  /** 信号流中选中行的 key（`Signal.key`）；null = 未选中 */
  selectedSignalKey: string | null;
  /** 地图聚焦点位 id（`RiskPoint.id`）；null = 不聚焦 */
  focusPointId: string | null;
}

/** 空选中态（初始值，也是 `selectSignal(null)` 的落点）。 */
export const EMPTY_SELECTION: SelectionSnapshot = {
  selectedSignalKey: null,
  focusPointId: null,
};

export type SelectionAction =
  | { type: 'select'; key: string | null; focusPointId: string | null }
  | { type: 'clearFocus' };

/**
 * 选中态迁移（纯函数，无副作用）。
 * - `select`：同时写入信号 key 与聚焦点 id（任一可为 null）。
 * - `clearFocus`：**只**清地图聚焦，保留信号行选中（用户可能只是想取消镜头跟随）。
 * - 值未变化时返回原对象引用，避免无谓重渲染。
 */
export function selectionReducer(
  state: SelectionSnapshot,
  action: SelectionAction,
): SelectionSnapshot {
  switch (action.type) {
    case 'select': {
      const key = action.key ?? null;
      const focusPointId = action.focusPointId ?? null;
      if (state.selectedSignalKey === key && state.focusPointId === focusPointId) return state;
      return { selectedSignalKey: key, focusPointId };
    }
    case 'clearFocus': {
      if (state.focusPointId === null) return state;
      return { selectedSignalKey: state.selectedSignalKey, focusPointId: null };
    }
    default:
      return state;
  }
}

export interface SelectionState extends SelectionSnapshot {
  /**
   * 选中一条信号。
   * @param key 信号行 key；传 null 表示取消选中
   * @param focusPointId 对应的地图点位 id；**当前 news 信号一律不传**（无坐标，见文件头注释）
   */
  selectSignal: (key: string | null, focusPointId?: string | null) => void;
  /** 只清地图聚焦，保留信号行选中 */
  clearFocus: () => void;
}

const Ctx = createContext<SelectionState | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [snapshot, dispatch] = useReducer(selectionReducer, EMPTY_SELECTION);

  const selectSignal = useCallback((key: string | null, focusPointId?: string | null) => {
    dispatch({ type: 'select', key: key ?? null, focusPointId: focusPointId ?? null });
  }, []);

  const clearFocus = useCallback(() => {
    dispatch({ type: 'clearFocus' });
  }, []);

  const api = useMemo<SelectionState>(
    () => ({
      selectedSignalKey: snapshot.selectedSignalKey,
      focusPointId: snapshot.focusPointId,
      selectSignal,
      clearFocus,
    }),
    [snapshot, selectSignal, clearFocus],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export function useSelection(): SelectionState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSelection 必须在 <SelectionProvider> 内使用');
  return v;
}
