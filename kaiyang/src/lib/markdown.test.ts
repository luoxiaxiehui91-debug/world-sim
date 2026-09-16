import { describe, expect, it } from 'vitest';
import { renderMarkdown } from '@/lib/markdown';

describe('renderMarkdown', () => {
  it('空输入返回空串', () => {
    expect(renderMarkdown('')).toBe('');
  });

  it('标题 / 分隔线 / 引用块', () => {
    const html = renderMarkdown('# 标题\n\n---\n\n> 引用内容');
    expect(html).toContain('<h1>标题</h1>');
    expect(html).toContain('<hr/>');
    expect(html).toContain('<blockquote>引用内容</blockquote>');
  });

  it('加粗 / 斜体 / 行内代码 / 链接', () => {
    const html = renderMarkdown('**粗** 与 *斜* 与 `code` 与 [链接](https://example.com)');
    expect(html).toContain('<strong>粗</strong>');
    expect(html).toContain('<em>斜</em>');
    expect(html).toContain('<code>code</code>');
    expect(html).toContain('<a href="https://example.com"');
  });

  it('表格（含对齐行）', () => {
    const md = ['| 维度 | 值 |', '|:---|---:|', '| A | 1 |', '| B | 2 |'].join('\n');
    const html = renderMarkdown(md);
    expect(html).toContain('<table>');
    expect(html).toContain('<th>维度</th>');
    expect(html).toContain('<td>A</td>');
  });

  it('围栏代码块内不做行内解析', () => {
    const md = '```\n**not bold**\n```';
    const html = renderMarkdown(md);
    expect(html).toContain('<pre><code>**not bold**</code></pre>');
    expect(html).not.toContain('<strong>');
  });

  it('XSS 安全：脚本/事件属性被转义为纯文本', () => {
    const html = renderMarkdown('<script>alert(1)</script>');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('XSS 安全：表格单元格内的 HTML 同样被转义（N1 回归）', () => {
    const md = ['| 维度 | 值 |', '|:---|---:|', '| <img src=x onerror=alert(1)> | 1 |'].join('\n');
    const html = renderMarkdown(md);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('javascript: 协议链接不被渲染为可点击链接', () => {
    const html = renderMarkdown('[x](javascript:alert(1))');
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain('<a ');
  });

  it('无序 / 有序列表', () => {
    const html = renderMarkdown('- a\n- b\n\n1. one\n2. two');
    expect(html).toContain('<ul>');
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>a</li>');
    expect(html).toContain('<li>one</li>');
  });
});
