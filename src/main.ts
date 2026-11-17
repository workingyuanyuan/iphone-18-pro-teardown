import './styles.css';
import { iphone18Pro } from './data/phones/iphone-18-pro';
import { App } from './ui/app';

const host = document.getElementById('root')!;

/** Canvas textures (wallpaper, chip labels) draw text once, so wait briefly for the CJK web font. */
async function fontsReady(): Promise<void> {
  if (!document.fonts?.load) return;
  const load = Promise.all([
    // Google Fonts serves CJK in unicode-range subsets: request every glyph the canvases draw.
    document.fonts.load('500 30px "Noto Sans TC"', '11月6日 星期五'),
    document.fonts.load('600 22px "Noto Sans TC"', '鋰離子電池'),
    document.fonts.load('16px "Noto Sans TC"', '警告：請勿拆解、擠壓或加熱'),
    document.fonts.load('600 150px "Noto Sans TC"', '9:41'),
  ]).then(() => undefined);
  await Promise.race([load, new Promise<void>((r) => setTimeout(r, 1500))]);
}

const esc = (t: string) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function showLoading(name: string): (fraction: number) => void {
  host.innerHTML = `<div class="boot" role="status" aria-live="polite">
    <p class="boot-title">正在載入 ${esc(name)} 的 3D 模型…</p>
    <div class="boot-bar"><i></i></div>
  </div>`;
  const bar = host.querySelector<HTMLElement>('.boot-bar i')!;
  return (f) => (bar.style.width = `${Math.round(f * 100)}%`);
}

function showError(title: string, body: string, retry?: () => void): void {
  host.innerHTML = `<div class="fatal" role="alert"><h1>${esc(title)}</h1><p>${esc(body)}</p>${
    retry ? '<button class="primary boot-retry" type="button">重新載入模型</button>' : ''
  }</div>`;
  if (retry) host.querySelector<HTMLButtonElement>('.boot-retry')!.addEventListener('click', retry);
}

let attempt = 0;

/** Load the model, then start the app. Controls only exist once the geometry is in place. */
async function boot(): Promise<void> {
  const phone = iphone18Pro;
  const mine = ++attempt; // a retry supersedes any load still in flight
  const progress = showLoading(phone.name);
  let objs;
  try {
    objs = await phone.load({ onProgress: progress, before: fontsReady() });
  } catch (err) {
    if (mine !== attempt) return;
    console.error(err);
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
    showError('3D 模型載入失敗', offline ? '目前似乎沒有網路連線。連上網路後再試一次。' : '模型檔下載或解析時出了問題。請再試一次；如果一直失敗，重新整理頁面。', () => void boot());
    return;
  }
  if (mine !== attempt) return;
  host.innerHTML = '';
  try {
    const app = new App(host, phone, objs);
    if (import.meta.env.DEV) (window as unknown as { __app: App }).__app = app;
    // Render statistics for tools/shots.mjs (draw calls, triangles).
    (window as unknown as { __renderInfo: () => unknown }).__renderInfo = () => (app as unknown as { stage: { renderer: { info: unknown } } }).stage.renderer.info;
  } catch (err) {
    console.error(err);
    showError('無法啟動 3D 檢視', '你的瀏覽器可能不支援 WebGL，或圖形功能被關閉了。請換用最新版 Chrome、Edge、Safari 或 Firefox 再試一次。');
  }
}

void boot();
