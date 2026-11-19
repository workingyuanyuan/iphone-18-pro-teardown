import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { meta } from '../src/data/phones/iphone-18-pro/meta';
import { guideOrder, parts } from '../src/data/phones/iphone-18-pro/parts';
import { renderStaticText } from '../src/seo/staticText';

/** The crawlable text version written into index.html (vite.config.ts). */
describe('static text version', () => {
  const html = renderStaticText({ ...meta, parts, guideOrder });
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  it('names and describes every part', () => {
    for (const p of parts) {
      expect(html, p.id).toContain(esc(p.name));
      expect(html, p.id).toContain(esc(p.summary));
    }
  });

  it('lists the removable parts in video order', () => {
    const at = guideOrder.map((id) => html.indexOf(`<h3>${esc(parts.find((p) => p.id === id)!.name)}`));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });

  it('escapes markup in the data', () => {
    const out = renderStaticText({ ...meta, guideOrder: ['x'], parts: [{ ...parts[1], id: 'x', name: '<b>&</b>' }] });
    expect(out).toContain('&lt;b&gt;&amp;&lt;/b&gt;');
  });

  it('has a marker to replace in index.html', () => {
    expect(readFileSync('index.html', 'utf8')).toContain('<!-- static-text -->');
  });
});
