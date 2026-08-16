/**
 * LLM 配置面板（08-16 新增；v2 平台化：换平台 / 选输模型 / 配 API key）
 * 折叠式：状态行 → 展开表格。每个使用点：
 *   平台下拉（内置 MiMo / SiliconFlow / MiniMax / OpenAI / Anthropic，可自定义 URL）
 *   → 模型（datalist 预置平台模型 + 可手输）→ API key（不回显明文，显示已配置标记）
 *   → 保存（PUT /control/llm-usage/{id}：写 data/llm_config.json 原子写）。
 * 天枢热挂载即时生效；天璇读共享配置文件（llm_config.json），下次调用生效。
 */
import { useCallback, useEffect, useState } from 'react';
import { getLlmUsage, updateLlmUsage } from '@/lib/controlApi';
import type { LlmPlatform, LlmUsage } from '@/types/control';

const CONTAINER_ZH: Record<string, string> = {
  tianshu: '天枢',
  tianxuan: '天璇',
  tianji: '天玑',
};

/** 每使用点的编辑草稿：平台 / 模型 / key（仅用户输入） */
interface Draft {
  platform: string;
  model: string;
  apiKey: string;
}

export function LlmConfig() {
  const [open, setOpen] = useState(false);
  const [usages, setUsages] = useState<LlmUsage[] | null>(null);
  const [platforms, setPlatforms] = useState<LlmPlatform[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const res = await getLlmUsage();
      setUsages(res.usages);
      setPlatforms(res.platforms);
      setDrafts(
        Object.fromEntries(
          res.usages.map((u) => [
            u.id,
            { platform: u.platform, model: u.model, apiKey: '' },
          ]),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载 LLM 配置失败');
    }
  }, []);

  useEffect(() => {
    if (open && usages === null) refresh();
  }, [open, usages, refresh]);

  const setDraft = (id: string, patch: Partial<Draft>) =>
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] ?? { platform: '', model: '', apiKey: '' }), ...patch } }));

  const handlePlatformChange = (u: LlmUsage, pid: string) => {
    const plat = platforms.find((p) => p.id === pid);
    setDraft(u.id, {
      platform: pid,
      model: plat?.default_model ?? '',
      apiKey: '',
    });
  };

  const handleSave = async (u: LlmUsage) => {
    const d = drafts[u.id];
    if (!d?.platform || !d.model.trim()) return;
    setSavingId(u.id);
    setSavedMsg(null);
    const ok = await updateLlmUsage(u.id, {
      platform: d.platform,
      model: d.model.trim(),
      apiKey: d.apiKey.trim() || undefined,
    });
    setSavingId(null);
    if (ok) {
      setSavedMsg(`${u.name} → ${d.platform}/${d.model.trim()}（下次调用生效）`);
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
        <div className="max-h-64 space-y-1.5 overflow-y-auto px-3 pb-2">
          {!usages && !error && <div className="text-[10px] text-white/30">加载中…</div>}
          {error && <div className="text-[10px] text-red-400">{error}</div>}
          {savedMsg && <div className="text-[10px] text-emerald-300/90">{savedMsg}</div>}
          {usages?.map((u) => {
            const d = drafts[u.id];
            const plat = platforms.find((p) => p.id === d?.platform);
            return (
              <div key={u.id} className="rounded-md border border-white/5 bg-white/[0.02] px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-medium text-white/80">
                    {u.name}
                    {u.overridden && <span className="ml-1 text-cyan-300/80">· 已覆盖</span>}
                  </span>
                  <span className="shrink-0 text-[9px] text-white/30">
                    {CONTAINER_ZH[u.container] ?? u.container} · {u.platform_name}
                  </span>
                </div>
                <div className="mt-0.5 text-[9px] leading-snug text-white/35">{u.purpose}</div>
                <div className="mt-1 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <select
                      value={d?.platform ?? u.platform}
                      onChange={(e) => handlePlatformChange(u, e.target.value)}
                      className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
                    >
                      {platforms.map((p) => (
                        <option key={p.id} value={p.id} className="bg-[#0b1220]">
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <span className="shrink-0 text-[9px] text-white/30">
                      {plat?.base_url ?? ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <input
                      list={`llm-models-${u.id}`}
                      value={d?.model ?? u.model}
                      onChange={(e) => setDraft(u.id, { model: e.target.value })}
                      className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
                      placeholder={u.model}
                      spellCheck={false}
                    />
                    <datalist id={`llm-models-${u.id}`}>
                      {(plat?.models ?? []).map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                    <input
                      value={d?.apiKey ?? ''}
                      onChange={(e) => setDraft(u.id, { apiKey: e.target.value })}
                      type="password"
                      placeholder={u.api_key_masked ? `已配置 ${u.api_key_masked}（留空不换）` : 'API Key（可选）'}
                      className="w-32 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
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
              </div>
            );
          })}
          <div className="pt-0.5 text-[9px] leading-snug text-white/25">
            平台 + 模型 + API key 写入天枢 data/llm_config.json（原子写）。天枢即时生效；天璇/天玑下次调用读取；key 仅存 NAS 本地，不回显明文。
          </div>
        </div>
      )}
    </div>
  );
}
