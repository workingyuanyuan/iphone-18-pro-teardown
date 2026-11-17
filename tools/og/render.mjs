// Regenerate the Open Graph share image (public/og.jpg, 1200×630).
//   npx vite --port 5174 --strictPort   (in another terminal; the dev build exposes window.__app)
//   node tools/og/render.mjs
// Step 1 renders the exploded phone from the running app; step 2 lays it out with the title (card.html).
import { chromium } from 'playwright-core';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
const browser = await chromium.launch({ channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });

const app = await browser.newPage({ viewport: { width: 900, height: 900 }, deviceScaleFactor: 2 });
await app.goto('http://localhost:5174/', { waitUntil: 'networkidle' });
await app.waitForSelector('.cell', { state: 'attached' });
await app.waitForTimeout(800);
await app.addStyleTag({ content: '.app>*:not(.stage-host){visibility:hidden!important}' });
await app.evaluate(async () => {
  const a = window.__app;
  const V = a.stage.camera.position.constructor;
  a.stage.setInsets(0, 0, 0);
  a.viewer.hints.clear();
  a.viewer.explode = 1;
  a.viewer.refresh();
  await a.stage.flyTo({ position: new V(330, 120, 200), target: new V(0, 0, 6) }, 0.01);
});
await app.waitForTimeout(1500);
await app.locator('canvas').screenshot({ path: `${here}phone-explode.png` });

const card = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await card.goto(`file://${here}card.html`, { waitUntil: 'networkidle' });
await card.evaluate(() => document.fonts.ready);
await card.waitForTimeout(500);
await card.screenshot({ path: `${here}../../public/og.jpg`, type: 'jpeg', quality: 88 });
await browser.close();
console.log('wrote public/og.jpg');
