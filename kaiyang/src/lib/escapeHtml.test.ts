import { describe, expect, it } from 'vitest';
import { escapeHtml } from '@/lib/escapeHtml';

describe('escapeHtml', () => {
  it('五个危险字符全部转义', () => {
    expect(escapeHtml('&<>"\'')).toBe('&amp;&lt;&gt;&quot;&#39;');
  });

  it('阻断 img onerror 注入（tooltip / formatter 通用防线）', () => {
    const out = escapeHtml('<img src=x onerror=alert(1)>');
    expect(out).not.toContain('<img');
    expect(out).toContain('&lt;img');
  });

  it('null / undefined 兜底为空串', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });

  it('非字符串输入先转字符串', () => {
    expect(escapeHtml(0)).toBe('0');
    expect(escapeHtml(false)).toBe('false');
  });

  it('普通文本不产生多余实体（无双重转义）', () => {
    expect(escapeHtml('风险值 12.5 · 等级 高')).toBe('风险值 12.5 · 等级 高');
  });

  it('已转义文本再转义会产生双重转义 —— 故调用点须确保只转义一次', () => {
    expect(escapeHtml(escapeHtml('<b>'))).toBe('&amp;lt;b&amp;gt;');
  });
});
