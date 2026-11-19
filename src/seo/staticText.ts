import type { PartDef } from '../core/types.ts';

/**
 * Text version of the teardown, written into the served index.html at build time (vite.config.ts).
 * The 3D view draws into a WebGL canvas, which search engines cannot read; this gives crawlers,
 * screen readers and visitors without JavaScript the same part names, summaries and findings.
 * It sits in normal flow behind the fixed app layer (see `.text-version` in styles.css).
 */
export interface StaticTextModel {
  name: string;
  size: [number, number, number];
  sizeNote: string;
  source: { title: string; url: string; date: string };
  parts: PartDef[];
  guideOrder: string[];
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function partBody(p: PartDef, heading: 'h3' | 'h4'): string {
  const sub = p.subtitle ? ` <span lang="en">${esc(p.subtitle)}</span>` : '';
  const facts = p.facts?.length ? `<ul>${p.facts.map((f) => `<li>${esc(f.text)}</li>`).join('')}</ul>` : '';
  return `<${heading}>${esc(p.name)}${sub}</${heading}><p>${esc(p.summary)}</p>${facts}`;
}

export function renderStaticText(m: StaticTextModel): string {
  const byId = new Map(m.parts.map((p) => [p.id, p]));
  const childrenOf = (id: string) => m.parts.filter((p) => p.parent === id);
  const base = m.parts.filter((p) => !p.parent && !m.guideOrder.includes(p.id));
  const [w, h, d] = m.size;

  const steps = m.guideOrder
    .map((id) => {
      const p = byId.get(id);
      if (!p) throw new Error(`guideOrder lists unknown part "${id}"`);
      const kids = childrenOf(id);
      const chips = kids.length ? `<section><p>焊在上面的晶片：</p>${kids.map((k) => partBody(k, 'h4')).join('')}</section>` : '';
      return `<li>${partBody(p, 'h3')}${chips}</li>`;
    })
    .join('\n      ');

  return `<article class="text-version" aria-labelledby="text-version-title">
    <h1 id="text-version-title">${esc(m.name)} 拆解</h1>
    <p>用 3D 互動的方式一層層拆開 ${esc(m.name)}，看懂手機裡的每個零件。${m.guideOrder.length} 個零件照拆解影片的順序編號：點一下零件看介紹，按「拆下」往裡面走，被擋住的零件會告訴你要先拆哪個；也可以拉開爆炸圖、切換 X 光，或一直按「下一步」照影片的順序看。</p>
    <h2>機身</h2>
    ${base.map((p) => partBody(p, 'h3')).join('\n    ')}
    <h2>拆解順序與零件</h2>
    <ol>
      ${steps}
    </ol>
    <h2>資料來源</h2>
    <p>拆解內容來自微機分 WekiHome 的影片《${esc(m.source.title)}》（${esc(m.source.date)}，${esc(m.source.url)}）。機身尺寸 ${w} × ${h} × ${d} mm。${esc(m.sizeNote)}厚度方向的位置是推估的。</p>
  </article>`;
}
