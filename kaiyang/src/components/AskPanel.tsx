import { useCallback, useState } from 'react';
import { askQuestion } from '@/lib/controlApi';

/**
 * 智能问答面板 — 基于当前系统数据快照提问。
 *
 * 2026-10-17 S4：后端端点自 8899 的 `/ask` 迁入控制面 `/api/v1/control/ask`，
 * 因此**必须先在右侧「控制」抽屉填入 Token**，否则返回 401（此处给出明确提示）。
 * 服务端保留限流（60s / 10 次）与单条 500 字上限，前端只做对应提示。
 */
export function AskPanel() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await askQuestion(q));
    } catch (e) {
      const err = e as Error & { code?: number };
      if (err?.code === 401) {
        setError('未授权：请先在右侧「控制」抽屉填入 Token');
      } else if (err?.code === 429) {
        setError('提问过于频繁，请稍后再试（每 60 秒最多 10 次）');
      } else {
        setError(err?.message || '请求失败');
      }
    } finally {
      setLoading(false);
    }
  }, [question, loading]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Ctrl/Cmd + Enter 提交（纯 Enter 保留换行）
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        void submit();
      }
    },
    [submit],
  );

  return (
    <div className="flex h-full flex-col gap-2 p-1">
      <div className="flex items-start gap-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={500}
          rows={2}
          placeholder="基于当前数据快照提问…（Ctrl + Enter 发送）"
          className="min-h-0 flex-1 resize-none rounded-md border border-white/10 bg-black/25 px-2.5 py-2 text-[12px] text-slate-100 placeholder:text-white/25 focus:border-white/25 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!question.trim() || loading}
          className="shrink-0 rounded-md border border-white/12 bg-white/8 px-3 py-1.5 text-[12px] text-slate-100 transition-colors hover:bg-white/14 disabled:cursor-not-allowed disabled:opacity-35"
        >
          {loading ? '思考中…' : '提问'}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/25 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-white/8 bg-black/20 px-2.5 py-2">
        {loading && (
          <div className="text-[11px] text-white/40">正在基于数据快照生成回答…</div>
        )}
        {!loading && !answer && !error && (
          <div className="text-[11px] text-white/30">
            回答基于当前 GRV、情境事件、弱信号、气候与灾害快照生成，会区分已知事实与推断。
          </div>
        )}
        {!loading && answer && (
          <div className="whitespace-pre-wrap text-[12px] leading-relaxed text-slate-200">
            {answer}
          </div>
        )}
      </div>
    </div>
  );
}
