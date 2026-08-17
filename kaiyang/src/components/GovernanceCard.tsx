/**
 * 政权更迭事件可视化卡片（v1.11.30）
 *
 * 渲染演化仿真报告的"政权更迭事件"节（跨 100 runs 聚合）为结构化卡片：
 * 每主权一行——类型占比条（换届转向 teal / 换届延续 灰 / 继承政变 红）
 * + run 级实质更迭率 badge + 发生月份 + 接任 regime 标签。
 *
 * 数据来自 lib/governance.ts 的 extractGovernanceEvents（纯文本解析，
 * 无后端改动；历史报告同样生效）。
 */

import { PALETTE, withAlpha } from '@/config/theme';
import type { GovEventItem } from '@/lib/governance';

interface Props {
  items: GovEventItem[];
}

/** 单行占比条（三段：转向 / 延续 / 继承），宽度按占比分配。 */
function ProportionBar({ item }: { item: GovEventItem }) {
  const segs: { key: string; pct: number; color: string; label: string }[] = [];
  if (item.transitionPct != null) segs.push({ key: 't', pct: item.transitionPct, color: PALETTE.teal, label: `换届转向 ${item.transitionPct}%` });
  if (item.holdPct != null) segs.push({ key: 'h', pct: item.holdPct, color: 'rgba(255,255,255,0.28)', label: `换届延续 ${item.holdPct}%` });
  if (item.breakPct != null) segs.push({ key: 'b', pct: item.breakPct, color: '#f87171', label: `继承/政变 ${item.breakPct}%` });
  const total = segs.reduce((s, x) => s + x.pct, 0) || 1;

  return (
    <div className="mt-1 flex h-1.5 w-full overflow-hidden rounded-full bg-white/5" role="img" aria-label={segs.map((s) => s.label).join('、')}>
      {segs.map((s) => (
        <div
          key={s.key}
          title={s.label}
          style={{ width: `${(s.pct / total) * 100}%`, background: s.color }}
        />
      ))}
    </div>
  );
}

/** 单主权行。 */
function GovRow({ item }: { item: GovEventItem }) {
  const high = item.runsPct >= 50;
  return (
    <div className="px-2.5 py-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium" style={{ color: withAlpha(PALETTE.text, 0.9) }}>
          {item.country}
        </span>
        <span
          className="shrink-0 rounded px-1.5 py-0.5 text-[8px] font-medium"
          style={{
            color: high ? '#fbbf24' : withAlpha(PALETTE.teal, 0.9),
            background: high ? 'rgba(251,191,36,0.12)' : 'rgba(45,212,191,0.10)',
          }}
          title="100 次模拟中发生实质更迭（换届转向/继承政变）的比例"
        >
          {item.runsPct}% runs 实质更迭
        </span>
      </div>
      <ProportionBar item={item} />
      <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[9px] text-white/35">
        {item.months && <span>月 {item.months}</span>}
        {item.regimeLabel && (
          <span className="text-white/45">→ {item.regimeLabel}</span>
        )}
      </div>
    </div>
  );
}

export function GovernanceCard({ items }: Props) {
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-white/10 bg-white/[0.03]">
      {/* 头部 */}
      <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.02] px-2.5 py-1.5">
        <span className="text-[11px] font-semibold" style={{ color: withAlpha(PALETTE.text, 0.9) }}>
          政权更迭事件
        </span>
        <span className="rounded bg-white/5 px-1.5 py-0.5 text-[8px] text-white/40">
          Monte Carlo 100 runs 聚合
        </span>
      </div>
      {/* 列表 */}
      <div className="divide-y divide-white/5">
        {items.map((it) => (
          <GovRow key={it.country} item={it} />
        ))}
      </div>
      {/* 图例 */}
      <div className="flex items-center gap-3 border-t border-white/5 px-2.5 py-1 text-[8px] text-white/30">
        <span className="flex items-center gap-1">
          <i className="h-1.5 w-1.5 rounded-full" style={{ background: PALETTE.teal }} />
          换届转向
        </span>
        <span className="flex items-center gap-1">
          <i className="h-1.5 w-1.5 rounded-full bg-white/28" />
          换届延续
        </span>
        <span className="flex items-center gap-1">
          <i className="h-1.5 w-1.5 rounded-full" style={{ background: '#f87171' }} />
          继承/政变
        </span>
        <span className="ml-auto">占比 = 事件内分布；badge = run 级触发率</span>
      </div>
    </div>
  );
}
