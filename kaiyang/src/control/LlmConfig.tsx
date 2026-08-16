/**
 * LLM 配置面板（08-16 新增）
 * 折叠式：默认状态行（使用点数 + 覆盖数），展开后表格——每个使用点：
 * 名称 / 容器 / 用途 / 当前模型 / 修改输入框 / 保存。
 * 数据源：GET /control/llm-usage；修改：PUT /control/llm-usage/{id}（写
 * data/llm_config.json，原子写，下次调用生效——天枢热挂载即时、天璇读共享文件）。
 */
import { useCallback, useEffect, useState } from 'react';
import { getLlmUsage, updateLlmUsage } from '@/lib/controlApi';
import type { LlmUsage } from '@/types/control';

const CONTAINER_ZH: Record<string, string> = {
  tianshu: '天枢',
  tianxuan: '天璇',
  tianji: '天玑',
};

export function LlmConfig() {
  const [open, setOpen] = useState(false);
  const [usages, setUsages] = useState<LlmUsage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const list = await getLlmUsage();
      setUsages(list);
      setDrafts(Object.fromEntries(list.map((u) => [u.id, u.model])));
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载 LLM 配置失败');
    }
  }, []);

  useEffect(() => {
    if (open && usages === null) refresh();
  }, [open, usages, refresh]);

  const handleSave = async (u: LlmUsage) => {
    const next = (drafts[u.id] ?? '').trim();
    if (!next) return;
    setSavingId(u.id);
    setSavedMsg(null);
    const ok = await updateLlmUsage(u.id, next);
    setSavingId(null);
    if (ok) {
      setSavedMsg(`${u.name} → ${next}（下次调用生效）`);
      await refresh();
    } else {
      setError(`修改 ${u.name} 失败`);
    }
  };

  const overriddenCount = usages?.filter((u) => u.overridden).length ?? 0;

  return (
    <div className="border-b border-white/5">
      <div className="flex items-center gap-2 px-3 py-1.5 text-[11px]">
        <span className={usages && overriddenCount > 0 ? 'text-cyan-300/90' : 'text-white/50'}>
          {usages ? `LLM 使用点 ${usages.length} 个${overriddenCount ? ` · ${overriddenCount} 个已覆盖` : ''}` : 'LLM 配置'}
        </span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="rounded border border-cyan-400/30 px-2 py-px text-[10px] text-cyan-300/90 transition-colors hover:bg-cyan-500/10"
        >
          {open ? '收起' : '配置'}
        </button>
      </div>

      {open && (
        <div className="max-h-56 space-y-1.5 overflow-y-auto px-3 pb-2">
          {!usages && !error && <div className="text-[10px] text-white/30">加载中…</div>}
          {error && <div className="text-[10px] text-red-400">{error}</div>}
          {savedMsg && <div className="text-[10px] text-emerald-300/90">{savedMsg}</div>}
          {usages?.map((u) => (
            <div key={u.id} className="rounded-md border border-white/5 bg-white/[0.02] px-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-medium text-white/80">
                  {u.name}
                  {u.overridden && <span className="ml-1 text-cyan-300/80">· 已覆盖</span>}
                </span>
                <span className="shrink-0 text-[9px] text-white/30">
                  {CONTAINER_ZH[u.container] ?? u.container} · {u.endpoint}
                </span>
              </div>
              <div className="mt-0.5 text-[9px] leading-snug text-white/35">{u.purpose}</div>
              <div className="mt-1 flex items-center gap-1.5">
                <input
                  value={drafts[u.id] ?? ''}
                  onChange={(e) => setDrafts((d) => ({ ...d, [u.id]: e.target.value }))}
                  className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
                  placeholder={u.model}
                  spellCheck={false}
                />
                <button
                  type="button"
                  disabled={savingId === u.id}
                  onClick={() => handleSave(u)}
                  className="shrink-0 rounded border border-cyan-400/30 px-2 py-px text-[10px] text-cyan-300/90 transition-colors hover:bg-cyan-500/10 disabled:opacity-40"
                >
                  {savingId === u.id ? '保存中…' : '保存'}
                </button>
              </div>
            </div>
          ))}
          <div className="pt-0.5 text-[9px] leading-snug text-white/25">
            修改写入天枢 data/llm_config.json（原子写），天枢热挂载即时生效，天璇/天玑下次调用读取。
          </div>
        </div>
      )}
    </div>
  );
}
