// Screenshot the running site in fixed states, for before/after comparison and perf numbers.
//   node tools/shots.mjs <out-dir> [--url http://localhost:4173] [--throttle 4]
// Needs a preview server (`npm run build && npm run preview`) and Google Chrome.
import { chromium } from 'playwright-core';
import { mkdirSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const outDir = args[0] ?? 'docs/screenshots';
const opt = (k, d) => (args.includes(k) ? args[args.indexOf(k) + 1] : d);
const url = opt('--url', 'http://localhost:4173');
const throttle = Number(opt('--throttle', '1'));
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const t0 = Date.now();
await page.goto(url, { waitUntil: 'networkidle' });
await page.waitForSelector('canvas', { timeout: 30000 });
await page.waitForSelector('[data-view]', { timeout: 30000 });
const loadMs = Date.now() - t0;
const settle = (ms = 1600) => page.waitForTimeout(ms);
const click = async (sel) => {
  await page.locator(sel).first().click({ force: true });
  await settle();
};
// dismiss onboarding if present
for (const sel of ['.onboard button', '.onboarding button', '.intro button']) {
  if (await page.locator(sel).count()) await page.locator(sel).first().click({ force: true }).catch(() => {});
}
await settle();
const shot = (name) => page.screenshot({ path: `${outDir}/${name}.png` });
await click('[data-view="three"]');
await shot('01-three');
await click('[data-view="back"]');
await shot('02-back');
await click('[data-view="front"]');
await shot('03-front');
await click('[data-view="side"]');
await shot('04-side');
await click('[data-view="three"]');
await click('.xray');
await shot('05-xray');
await click('.xray');
await page.locator('.slider input').evaluate((el) => {
  el.value = '1';
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
await settle(2200);
await shot('06-explode');

// guided teardown: N = next step. Shots after the display is off, after the vapor chamber, etc.
await page.locator('.slider input').evaluate((el) => {
  el.value = '0';
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
await settle();
const next = async (n) => {
  for (let i = 0; i < n; i++) {
    await page.keyboard.press('n');
    await settle(4200);
  }
  await page.keyboard.press('Escape');
  await settle(600);
};
await next(2); // SIM tray, back glass
await click('[data-view="back"]');
await shot('07-back-glass-off');
await next(1); // display
await click('[data-view="front"]');
await shot('08-display-off');
await next(2); // connector covers, vapor chamber
await click('[data-view="front"]');
await shot('09-vc-off');
await next(4); // battery, Face ID, rear camera, top speaker
await click('[data-view="front"]');
await shot('10-board');
await page.locator('.slider input').evaluate((el) => {
  el.value = '1';
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
await click('[data-view="three"]');

// load failure and retry
const p2 = await browser.newPage({ viewport: { width: 900, height: 600 } });
let fail = true;
await p2.route('**/*.glb', (r) => (fail ? r.abort() : r.continue()));
await p2.goto(url);
await p2.waitForSelector('.boot-retry', { timeout: 20000 });
await p2.screenshot({ path: `${outDir}/11-load-error.png` });
fail = false;
await p2.locator('.boot-retry').click();
const retryOk = await p2.waitForSelector('canvas', { timeout: 20000 }).then(() => true, () => false);
await p2.close();

// perf: frame times while orbiting in exploded view, optionally CPU-throttled
const cdp = await page.context().newCDPSession(page);
if (throttle > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: throttle });
// Start a frame timer in the page, drag with the real (CDP) mouse so OrbitControls gets a proper
// pointer, then stop. A before/after canvas comparison proves the camera actually moved.
const box = await page.locator('canvas').first().boundingBox();
const cx = box.x + box.width / 2,
  cy = box.y + box.height / 2;
const before = await page.locator('canvas').first().screenshot();
await page.evaluate(() => {
  const w = window;
  w.__frames = [];
  w.__stopFrames = false;
  let last = performance.now();
  const tick = (t) => {
    w.__frames.push(t - last);
    last = t;
    if (!w.__stopFrames) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
await page.mouse.move(cx, cy);
await page.mouse.down();
for (let i = 0; i < 180; i++) await page.mouse.move(cx + Math.sin(i / 20) * 200, cy + Math.cos(i / 25) * 60, { steps: 1 });
await page.mouse.up();
const perf = await page.evaluate(() => {
  const w = window;
  w.__stopFrames = true;
  const s = w.__frames.slice(5).sort((a, b) => a - b);
  const info = w.__renderInfo?.();
  return {
    frames: s.length,
    medianMs: s[Math.floor(s.length / 2)],
    p95Ms: s[Math.floor(s.length * 0.95)],
    drawCalls: info?.render?.calls ?? null,
    triangles: info?.render?.triangles ?? null,
    geometries: info?.memory?.geometries ?? null,
    textures: info?.memory?.textures ?? null,
  };
});
await settle(400);
perf.cameraMoved = !before.equals(await page.locator('canvas').first().screenshot());
const res = await page.evaluate(() =>
  performance.getEntriesByType('resource').filter((e) => /\.(glb|wasm)(\?|$)/.test(e.name)).map((e) => ({ name: e.name.split('/').pop(), transfer: e.transferSize, decoded: e.decodedBodySize })),
);
const report = { url, loadMs, throttle, perf, resources: res, errors, retryAfterFailedLoad: retryOk, note: 'software WebGL (SwiftShader): frame times are a lower bound on speed, not a phone measurement' };
writeFileSync(`${outDir}/report.json`, JSON.stringify(report, null, 1));
console.log(JSON.stringify(report, null, 1));
await browser.close();
