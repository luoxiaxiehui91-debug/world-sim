/**
 * 轻量 Markdown → HTML 渲染器（R-1 报告模块用）。
 *
 * 定位：报告来自天枢 LLM 产物，正文可信，但仍是外部文本 —— 一律先 HTML 转义再排版，
 * 杜绝 XSS（任何 <script> 等标签原样显示为文本）。
 *
 * 支持子集（对齐天枢报告实际用到的语法）：
 *   - 标题 # ~ ######
 *   - 分隔线 ---
 *   - 引用块 >
 *   - 表格（| 行，含 :---: 对齐行）
 *   - 有序 / 无序列表（- * 1. 2.）
 *   - 围栏代码块 ```（保留原文，不转义内部）
 *   - 行内：**加粗** *斜体* `行内代码` [链接](url)
 *   - 段落
 *
 * 不实现：图片 / 脚注 / HTML 原生标签 / 任务列表。缺失即按纯文本呈现，绝不报错。
 */

/** HTML 转义（防 XSS，所有文本入口必须先过此函数）。 */
function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 行内样式：加粗 / 斜体 / 行内代码 / 链接。入参已转义。 */
function inline(text: string): string {
  // 行内代码：反引号包起来的内容原样展示（先处理，避免代码内的 ** 被二次解析）
  let out = text.replace(/`([^`]+)`/g, (_m, code: string) => `<code>${code}</code>`);
  // 链接 [text](url) —— 仅允许 http(s) 协议，防 javascript: 注入
  out = out.replace(
    /\[([^\]]+)\]\(((?:https?:)?\/\/[^)\s]+)\)/g,
    (_m, label: string, url: string) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`,
  );
  // 加粗 **x**（必须在斜体之前处理）
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // 斜体 *x*（不能跨空格；已转义文本中 * 原样存在）
  out = out.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>');
  return out;
}

/** 单行 → <li>。 */
function listItem(line: string): string {
  const trimmed = line.replace(/^[-*+]\s+/, '').replace(/^\d+[.)]\s+/, '');
  return `<li>${inline(trimmed)}</li>`;
}

/** 解析表格行（| a | b |）→ <tr>。对齐行（|:---:|）返回 null。 */
function tableRow(line: string, isHead: boolean): string | null {
  const cells = line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());
  if (cells.every((c) => /^:?-{2,}:?$/.test(c))) return null; // 对齐分隔行
  const tag = isHead ? 'th' : 'td';
  const html = cells.map((c) => `<${tag}>${inline(c)}</${tag}>`).join('');
  return `<tr>${html}</tr>`;
}

/**
 * 渲染 markdown 文本 → HTML 片段。
 * 空输入返回空串；任何输入都不抛异常。
 */
export function renderMarkdown(md: string): string {
  if (!md) return '';
  const rawLines = String(md).split(/\r?\n/);

  const out: string[] = [];
  let i = 0;

  while (i < rawLines.length) {
    const line = rawLines[i];

    // ── 围栏代码块 ──
    if (/^\s*```/.test(line)) {
      const buf: string[] = [];
      i++;
      while (i < rawLines.length && !/^\s*```/.test(rawLines[i])) {
        buf.push(rawLines[i]);
        i++;
      }
      i++; // 跳过结束围栏
      out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }

    // ── 空行：跳过 ──
    if (line.trim() === '') {
      i++;
      continue;
    }

    // ── 标题 ──
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      out.push(`<h${level}>${inline(esc(h[2]))}</h${level}>`);
      i++;
      continue;
    }

    // ── 分隔线 ──
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push('<hr/>');
      i++;
      continue;
    }

    // ── 表格：当前行以 | 开头且下一行为对齐行 ──
    if (/^\s*\|/.test(line) && i + 1 < rawLines.length) {
      const alignLine = rawLines[i + 1].trim();
      if (/^\|?[\s:|-]+\|?$/.test(alignLine) && alignLine.includes('-')) {
        const head = tableRow(line, true);
        if (head) {
          out.push('<table><thead>', head, '</thead><tbody>');
          i += 2; // 跳过表头 + 对齐行
          while (i < rawLines.length && /^\s*\|/.test(rawLines[i]) && rawLines[i].trim() !== '') {
            const row = tableRow(rawLines[i], false);
            if (row) out.push(row);
            i++;
          }
          out.push('</tbody></table>');
          continue;
        }
      }
    }

    // ── 引用块（连续 > 行）──
    if (/^\s*>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < rawLines.length && /^\s*>\s?/.test(rawLines[i])) {
        buf.push(rawLines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      out.push(`<blockquote>${inline(esc(buf.join('<br/>')))}</blockquote>`);
      continue;
    }

    // ── 无序列表（连续 - / * 行）──
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf: string[] = [];
      while (i < rawLines.length && /^\s*[-*+]\s+/.test(rawLines[i])) {
        buf.push(listItem(esc(rawLines[i])));
        i++;
      }
      out.push(`<ul>${buf.join('')}</ul>`);
      continue;
    }

    // ── 有序列表（连续 1. 2. 行）──
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const buf: string[] = [];
      while (i < rawLines.length && /^\s*\d+[.)]\s+/.test(rawLines[i])) {
        buf.push(listItem(esc(rawLines[i])));
        i++;
      }
      out.push(`<ol>${buf.join('')}</ol>`);
      continue;
    }

    // ── 普通段落（连续非空行合并）──
    const para: string[] = [];
    while (
      i < rawLines.length &&
      rawLines[i].trim() !== '' &&
      !/^\s*(```|>|[-*+]\s|\d+[.)]\s|#|#{1,6}\s|\||-{3,})\s*$/.test(rawLines[i])
    ) {
      para.push(esc(rawLines[i]));
      i++;
    }
    if (para.length === 0) i++; // 游标必进：孤立 | / # 等不进任何分支的行强制消费，防主循环死循环（2026-08-24 P0）
    out.push(`<p>${inline(para.join(' '))}</p>`);
  }

  return out.join('\n');
}
