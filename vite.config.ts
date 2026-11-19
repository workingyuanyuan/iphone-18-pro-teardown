import { defineConfig, type Plugin } from 'vite';
import { meta } from './src/data/phones/iphone-18-pro/meta.ts';
import { guideOrder, parts } from './src/data/phones/iphone-18-pro/parts.ts';
import { renderStaticText } from './src/seo/staticText.ts';

/** Replaces `<!-- static-text -->` in index.html with the crawlable text version of the teardown. */
function staticText(): Plugin {
  const marker = '<!-- static-text -->';
  return {
    name: 'static-text',
    transformIndexHtml(html) {
      if (!html.includes(marker)) throw new Error(`index.html is missing ${marker}`);
      return html.replace(marker, () => renderStaticText({ ...meta, parts, guideOrder }));
    },
  };
}

export default defineConfig({
  base: './',
  build: { target: 'es2022', chunkSizeWarningLimit: 1200 },
  plugins: [staticText()],
});
