/**
 * 政权更迭事件解析（v1.11.30）
 *
 * 从演化仿真报告 md 文本中提取"## 政权更迭事件（Monte Carlo 100 runs 聚合）"节，
 * 供报告面板渲染为可视化卡片。解析失败（非演化报告/格式变化）返回 null，调用方
 * 降级为普通 markdown 渲染——解析器是增强不是依赖。
 *
 * 天璇生成格式（run.py _write_report，稳定模板）：
 *   - **美国**：换届转向 43%；换届延续 57%（月 4；43% runs 发生实质更迭） — 更迭·鹰派主导假设接任
 *   - **俄罗斯**：继承/政变 100%（月 1、2、4；21% runs 发生实质更迭） — 更迭·长期化假设接管
 */

export interface GovEventItem {
  /** 国家名（报告原文） */
  country: string;
  /** 换届转向占比（%），无则 null */
  transitionPct: number | null;
  /** 换届延续占比（%），无则 null */
  holdPct: number | null;
  /** 继承/政变事件内占比（%），无则 null */
  breakPct: number | null;
  /** run 级实质更迭率（%）（100 runs 中多少 run 发生实质更迭） */
  runsPct: number;
  /** 发生月份（报告原文，如 "4" / "1、2、4"） */
  months: string;
  /** 接任 regime 标签（如 "更迭·鹰派主导假设接任"），无则 null */
  regimeLabel: string | null;
}

export interface GovernanceParseResult {
  items: GovEventItem[];
  /** 剥离政权更迭节后的剩余 md（正文照常渲染） */
  rest: string;
}

const SECTION_HEADER = '## 政权更迭事件（Monte Carlo 100 runs 聚合）';

/** 解析单行：- **美国**：换届转向 43%；换届延续 57%（月 4；43% runs 发生实质更迭） — 标签 */
function parseLine(line: string): GovEventItem | null {
  const m = /^-\s*\*\*([^*]+)\*\*：([\s\S]*)$/.exec(line.trim());
  if (!m) return null;
  const country = m[1].trim();
  const body = m[2];

  const item: GovEventItem = {
    country,
    transitionPct: null,
    holdPct: null,
    breakPct: null,
    runsPct: 0,
    months: '',
    regimeLabel: null,
  };

  // 类型占比（可组合：换届转向 X%；换届延续 Y% / 继承/政变 Z%）
  const t = /换届转向\s*(\d+)%/.exec(body);
  const h = /换届延续\s*(\d+)%/.exec(body);
  const b = /继承\/政变\s*(\d+)%/.exec(body);
  if (t) item.transitionPct = Number(t[1]);
  if (h) item.holdPct = Number(h[1]);
  if (b) item.breakPct = Number(b[1]);
  if (item.transitionPct === null && item.holdPct === null && item.breakPct === null) return null;

  // 月 + runs 触发率：（月 1、2、4；21% runs 发生实质更迭）
  const r = /（月\s*([^；]+)；\s*([\d.]+)%\s*runs 发生实质更迭）/.exec(body);
  if (r) {
    item.months = r[1].trim();
    item.runsPct = Number(r[2]);
  }

  // 尾部 regime 标签：— 更迭·xxx接任
  const tag = /—\s*(.+)$/.exec(body);
  if (tag) item.regimeLabel = tag[1].trim();

  return item;
}

/**
 * 从 md 中提取政权更迭节。找不到节/解析不到任何行 → null（调用方照常渲染全文）。
 */
export function extractGovernanceEvents(md: string): GovernanceParseResult | null {
  if (!md || !md.includes(SECTION_HEADER)) return null;

  const lines = md.split('\n');
  const startIdx = lines.findIndex((l) => l.trim().startsWith('## 政权更迭事件'));
  if (startIdx < 0) return null;

  // 节结束 = 下一个 ## 标题（或文件尾）
  let endIdx = lines.length;
  for (let i = startIdx + 1; i < lines.length; i++) {
    if (lines[i].trim().startsWith('## ')) {
      endIdx = i;
      break;
    }
  }

  const items: GovEventItem[] = [];
  for (let i = startIdx + 1; i < endIdx; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('#')) continue;
    const item = parseLine(line);
    if (item) items.push(item);
  }
  if (items.length === 0) return null;

  const rest = [...lines.slice(0, startIdx), ...lines.slice(endIdx)].join('\n');
  return { items, rest };
}
