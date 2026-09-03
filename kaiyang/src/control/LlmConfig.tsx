/**
 * LLM 配置面板（08-16 新增；09-03 ADR-0015：恢复密钥框——write-only 经 POST /llm-secret
 * 写 NAS config/.env（0600，双 gitignore），即时热生效免 recreate；面板仅显示掩码状态）
 * 折叠式：状态行 → 展开表格。每个使用点：
 *   平台下拉（内置平台：MiMo Plan / MiMo API / SiliconFlow 等）
 *   → 模型（实时 /models 下拉 + 静态清单兜底）
 *   → 保存（PUT /control/llm-usage/{id}：写 data/llm_config.json 原子写+模板自动再生）。
 * 天枢热挂载即时生效；天璇读共享配置文件（llm_config.json），下次调用生效。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  getLlmUsage,
  getLlmSecrets,
  getPlatformModels,
  setLlmSecret,
  updateLlmUsage,
} from '@/lib/controlApi';
import type { LlmPlatform, LlmSecretStatus, LlmUsage } from '@/types/control';

const CONTAINER_ZH: Record<string, string> = {
  tianshu: '天枢',
  tianxuan: '天璇',
  tianji: '天玑',
};

/** 每使用点的编辑草稿：平台 / 模型 / key（仅用户输入） */
interface Draft {
  platform: string;
  model: string;
}

export function LlmConfig() {
  const [open, setOpen] = useState(false);
  const [usages, setUsages] = useState<LlmUsage[] | null>(null);
  const [platforms, setPlatforms] = useState<LlmPlatform[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [liveModels, setLiveModels] = useState<Record<string, string[]>>({});
  const [secrets, setSecrets] = useState<LlmSecretStatus[] | null>(null);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [keyMsg, setKeyMsg] = useState<string | null>(null);
  const [savingKeyPid, setSavingKeyPid] = useState<string | null>(null);

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
            { platform: u.platform, model: u.model },
          ]),
        ),
      );
      // 密钥状态（掩码；失败静默，不阻塞面板）
      void getLlmSecrets()
        .then(setSecrets)
        .catch(() => undefined);
      // 并行拉取涉及平台的实时模型全集（失败静默，datalist 回落静态清单）
      const pids = [...new Set(res.usages.map((u) => u.platform))];
      void Promise.all(
        pids.map(async (pid) => {
          const models = await getPlatformModels(pid);
          if (models && models.length > 0) {
            setLiveModels((prev) => ({ ...prev, [pid]: models }));
          }
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载 LLM 配置失败');
    }
  }, []);

  useEffect(() => {
    if (open && usages === null) refresh();
  }, [open, usages, refresh]);

  const setDraft = (id: string, patch: Partial<Draft>) =>
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] ?? { platform: '', model: '' }), ...patch } }));

  const handlePlatformChange = (u: LlmUsage, pid: string) => {
    const plat = platforms.find((p) => p.id === pid);
    setDraft(u.id, {
      platform: pid,
      model: plat?.default_model ?? '',
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
    });
    setSavingId(null);
    if (ok) {
      setSavedMsg(`${u.name} → ${d.platform}/${d.model.trim()}（下次调用生效）`);
      await refresh();
    } else {
      setError(`修改 ${u.name} 失败`);
    }
  };

  const handleSaveKey = async (u: LlmUsage) => {
    const key = (keyDrafts[u.platform] ?? '').trim();
    if (!key) return;
    setSavingKeyPid(u.platform);
    setKeyMsg(null);
    const res = await setLlmSecret(u.platform, key);
    setSavingKeyPid(null);
    if (res.ok) {
      setKeyMsg(`${u.platform_name} 密钥${res.message ?? '已保存'}`);
      setKeyDrafts((kd) => ({ ...kd, [u.platform]: '' }));
      await refresh();
    } else {
      setKeyMsg(`${u.platform_name} 密钥保存失败：${res.error ?? '未知错误'}`);
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
          {keyMsg && <div className="text-[10px] text-emerald-300/90">{keyMsg}</div>}
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
                    {(() => {
                      const opts = [
                        ...new Set([
                          ...(liveModels[plat?.id ?? ''] ?? plat?.models ?? [])
                            .filter((mm) => !/(tts|asr|voice)/i.test(mm)),
                          d?.model ?? u.model,
                        ]),
                      ];
                      const cur = d?.model ?? u.model;
                      return (
                        <select
                          value={cur}
                          onChange={(e) => setDraft(u.id, { model: e.target.value })}
                          className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
                        >
                          {!opts.includes(cur) && cur && (
                            <option key={cur} value={cur}>{cur}</option>
                          )}
                          {opts.map((mm) => (
                            <option key={mm} value={mm}>{mm}</option>
                          ))}
                        </select>
                      );
                    })()}
                    {/* 模型保存（平台/模型写 data/llm_config.json + 兜底模板自动再生）；密钥见下方 write-only 框（ADR-0015） */}
                    <button
                      type="button"
                      disabled={savingId === u.id}
                      onClick={() => handleSave(u)}
                      className="shrink-0 rounded border border-cyan-400/30 px-2 py-px text-[10px] text-cyan-300/90 transition-colors hover:bg-cyan-500/10 disabled:opacity-40"
                    >
                      {savingId === u.id ? '保存中…' : '保存'}
                    </button>
                  </div>
                  {(() => {
                    const sec = secrets?.find((s) => s.platform === (d?.platform ?? u.platform));
                    return (
                      <div className="flex items-center gap-1.5">
                        <input
                          type="password"
                          value={keyDrafts[d?.platform ?? u.platform] ?? ''}
                          onChange={(e) =>
                            setKeyDrafts((kd) => ({
                              ...kd,
                              [d?.platform ?? u.platform]: e.target.value,
                            }))
                          }
                          placeholder={
                            sec?.masked
                              ? `已配置 ${sec.masked}（${sec.source}）`
                              : '未配置密钥'
                          }
                          className="min-w-0 flex-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[10px] text-white/80 outline-none focus:border-cyan-400/40"
                        />
                        <button
                          type="button"
                          disabled={savingKeyPid === (d?.platform ?? u.platform) || !(keyDrafts[d?.platform ?? u.platform] ?? '').trim()}
                          onClick={() => handleSaveKey(u)}
                          className="shrink-0 rounded border border-cyan-400/30 px-2 py-px text-[10px] text-cyan-300/90 transition-colors hover:bg-cyan-500/10 disabled:opacity-40"
                        >
                          {savingKeyPid === (d?.platform ?? u.platform) ? '保存中…' : '存密钥'}
                        </button>
                      </div>
                    );
                  })()}
                  <div className="text-[9px] leading-snug text-amber-200/60">
                    密钥 write-only 保存至 NAS config/.env（0600，不回显不入库），即时生效免重启
                  </div>
                </div>
              </div>
            );
          })}
          <div className="pt-0.5 text-[9px] leading-snug text-white/25">
            平台 + 模型写入天枢 data/llm_config.json（原子写，兜底模板自动再生），天枢即时生效、天璇/天玑下次调用读取。密钥 write-only 写 NAS config/.env（ADR-0015，0600 双 gitignore），即时热生效；config 永不存 key。
          </div>
        </div>
      )}
    </div>
  );
}
