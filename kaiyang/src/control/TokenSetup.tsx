/**
 * API Token 配置组件（08-16 新增）
 * 折叠式：默认显示状态行（已配置/未配置），展开后输入 + 保存 + 清除。
 * Token 经 ControlContext.setToken 写入 → setApiToken（注入请求头）+ setStoredToken（localStorage）。
 * 背景：P1-D fail-closed 后无 token 一律 401，而此前前端无任何 token 配置入口，
 * 控制台天枢 tab 直接显示「Token 无效」且无法恢复。
 */
import { useState } from 'react';
import { useControl } from '@/state/ControlContext';

export function TokenSetup({ onSaved }: { onSaved?: () => void }) {
  const { token, setToken } = useControl();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(token ?? '');

  const handleSave = () => {
    setToken(value.trim() || null);
    setEditing(false);
    onSaved?.();
  };

  const handleClear = () => {
    setValue('');
    setToken(null);
    setEditing(false);
    onSaved?.();
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2 border-b border-white/5 px-3 py-1.5 text-[11px]">
        <span className={token ? 'text-emerald-300/80' : 'text-amber-300/80'}>
          {token ? 'API Token 已配置' : 'API Token 未配置'}
        </span>
        <button
          type="button"
          onClick={() => {
            setValue(token ?? '');
            setEditing(true);
          }}
          className="rounded border border-cyan-400/30 px-2 py-px text-[10px] text-cyan-300/90 transition-colors hover:bg-cyan-500/10"
        >
          配置
        </button>
        {token && (
          <button
            type="button"
            onClick={handleClear}
            className="rounded border border-white/10 px-2 py-px text-[10px] text-white/40 transition-colors hover:text-white/70"
          >
            清除
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 border-b border-white/5 px-3 py-2">
      <div className="flex items-center gap-1.5">
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="粘贴 CONTROL_TOKEN"
          autoFocus
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80 placeholder:text-white/25 outline-none transition-colors focus:border-cyan-400/40"
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSave();
          }}
        />
        <button
          type="button"
          onClick={handleSave}
          className="rounded-md border border-cyan-400/40 bg-cyan-500/10 px-2 py-1 text-[11px] text-cyan-300 transition-colors hover:bg-cyan-500/20"
        >
          保存
        </button>
      </div>
      <p className="text-[10px] leading-relaxed text-white/30">
        Token 来自天枢运行区 compose 的 CONTROL_TOKEN（运行区 compose）。仅存于本机浏览器 localStorage。
      </p>
    </div>
  );
}
