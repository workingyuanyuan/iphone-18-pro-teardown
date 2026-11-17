import { Vector2, Vector3, type Object3D } from 'three';
import { Assembly, type Step } from '../core/assembly';
import type { ExtraKind, PartDef, PhoneModel, Side } from '../core/types';
import { Stage, type Pose } from '../engine/stage';
import { PhoneViewer } from '../engine/viewer';
import { categoryIcon, categoryName, icon } from './icons';

const EXTRA_LABEL: Record<ExtraKind, [string, string]> = {
  magsafe: ['顯示 MagSafe 線圈範圍', '收起線圈範圍'],
  dotProjector: ['投射紅外光點', '關閉光點'],
  peelSticker: ['撕開黑色貼紙', '貼回貼紙'],
  wmcm: ['掀開頂蓋看封裝', '蓋回頂蓋'],
};

const VIEWS: { id: string; label: string; pos: [number, number, number] }[] = [
  { id: 'three', label: '45°', pos: [230, 110, 330] },
  { id: 'front', label: '正面', pos: [0, 0, 420] },
  { id: 'back', label: '背面', pos: [0, 0, -420] },
  { id: 'side', label: '側面', pos: [-420, 20, 40] },
];

const h = <K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, html?: string): HTMLElementTagNameMap[K] => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (html !== undefined) el.innerHTML = html;
  return el;
};

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

const toSeconds = (t: string) => t.split(':').reduce((a, b) => a * 60 + Number(b), 0);

/** Wires the assembly state, the 3D viewer and the DOM together. */
export class App {
  private assembly: Assembly;
  private stage: Stage;
  private viewer: PhoneViewer;
  private queue: Promise<void> = Promise.resolve();
  private busy = 0;
  private guiding = false;
  private history: Step[][] = [];
  private removalOrder: string[] = [];
  private selected: string | null = null;
  /** What the info panel last showed, so it scrolls back to the top only when the subject changes. */
  private infoShown: string | null | undefined;
  private returnPose: Pose | null = null;
  private guideCaption = '';
  private touchedAnything = false;
  private mobileTab: 'parts' | 'info' | null = null;
  private reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  private el!: {
    root: HTMLElement;
    stageHost: HTMLElement;
    list: HTMLElement;
    info: HTMLElement;
    progress: HTMLElement;
    caption: HTMLElement;
    tooltip: HTMLElement;
    toast: HTMLElement;
    undo: HTMLButtonElement;
    reset: HTMLButtonElement;
    next: HTMLButtonElement;
    xray: HTMLButtonElement;
    explode: HTMLInputElement;
    tabs: HTMLElement;
    toolbar: HTMLElement;
    mat: HTMLElement;
  };

  constructor(
    private host: HTMLElement,
    private model: PhoneModel,
    /** Loaded geometry, one object per part id (see PhoneModel.load). */
    objs: Map<string, Object3D>,
  ) {
    this.assembly = new Assembly(model.parts);
    this.buildDom();
    this.stage = new Stage(this.el.stageHost);
    this.stage.tweens.speed = this.reduceMotion ? 0.25 : 1;
    this.stage.onContextLost = () => this.toast('3D 繪圖暫時中斷，請重新整理頁面。', 8000);
    this.viewer = new PhoneViewer(model, this.stage, objs);
    this.viewer.hints = new Set(model.parts.filter((p) => this.assembly.canRemove(p.id)).map((p) => p.id));
    this.bindPointer();
    this.bindKeys();
    new ResizeObserver(() => this.updateInsets()).observe(this.el.root);
    this.renderAll();
  }

  // ---------------------------------------------------------------- DOM

  private buildDom(): void {
    const root = h('div', 'app');
    root.innerHTML = `
      <header class="topbar">
        <h1 class="title">${esc(this.model.name)} 拆解</h1>
        <div class="topbar-actions">
          <a class="src-link" href="${this.model.source.url}" target="_blank" rel="noopener">資料來源：微機分 WekiHome 拆解影片</a>
          <button class="help-btn">怎麼拆</button>
        </div>
      </header>
      <div class="stage-host"></div>
      <aside class="mat" data-pane="parts" aria-label="零件墊">
        <div class="mat-head">
          <h2>零件墊</h2>
          <span class="progress" aria-live="polite"></span>
          <button class="mat-reset reset">全部組回</button>
        </div>
        <div class="mat-grid" role="list"></div>
        <div class="mat-foot"></div>
      </aside>
      <aside class="info-panel" data-pane="info" aria-label="零件介紹"></aside>
      <div class="guide-caption" role="status"></div>
      <nav class="toolbar" aria-label="工具列">
        <div class="tool-group views" role="group" aria-label="視角">
          ${VIEWS.map((v) => `<button class="seg" data-view="${v.id}">${v.label}</button>`).join('')}
        </div>
        <button class="tool view-cycle" title="切換視角">${icon.eye}<span>視角</span></button>
        <label class="tool-group slider" title="爆炸圖：把零件沿厚度方向拉開">
          ${icon.explode}<span>爆炸圖</span>
          <input type="range" min="0" max="1" step="0.01" value="0" aria-label="爆炸圖程度" />
        </label>
        <button class="tool xray" aria-pressed="false" title="X 光：外殼變透明">${icon.xray}<span>X 光</span></button>
        <button class="tool undo" title="復原上一步">${icon.undo}<span>復原</span></button>
        <button class="tool primary next" title="照影片順序拆下一個零件"><span>下一步</span></button>
      </nav>
      <nav class="tabs" aria-label="面板">
        <button data-tab="parts">零件墊 <b class="mat-count"></b></button><button data-tab="info">介紹</button>
      </nav>
      <div class="tooltip" role="tooltip"></div>
      <div class="toast" role="status"></div>`;
    this.host.appendChild(root);
    const q = <T extends Element>(s: string) => root.querySelector(s) as T;
    this.el = {
      root,
      stageHost: q('.stage-host'),
      list: q('.mat-grid'),
      info: q('.info-panel'),
      mat: q('.mat'),
      toolbar: q('.toolbar'),
      progress: q('.progress'),
      caption: q('.guide-caption'),
      tooltip: q('.tooltip'),
      toast: q('.toast'),
      undo: q('.undo'),
      reset: q('.reset'),
      next: q('.next'),
      xray: q('.xray'),
      explode: q('.slider input'),
      tabs: q('.tabs'),
    };

    root.querySelectorAll<HTMLButtonElement>('[data-view]').forEach((b) =>
      b.addEventListener('click', () => this.flyView(b.dataset.view!)),
    );
    this.el.explode.addEventListener('pointerdown', () => {
      // Layers separate along the phone's thickness; a side-on angle shows that best.
      if (this.viewer.explode === 0 && !this.viewer.focus && !this.viewer.inspect)
        this.stage.flyTo({ position: new Vector3(340, 110, 170), target: new Vector3(0, 0, 8) });
    });
    this.el.explode.addEventListener('input', () => {
      this.viewer.explode = Number(this.el.explode.value);
      this.viewer.refresh();
    });
    this.el.xray.addEventListener('click', () => {
      this.viewer.xray = !this.viewer.xray;
      this.el.xray.setAttribute('aria-pressed', String(this.viewer.xray));
      this.viewer.refresh();
    });
    this.el.undo.addEventListener('click', () => this.undo());
    let viewIdx = 0;
    q<HTMLButtonElement>('.view-cycle').addEventListener('click', () => {
      viewIdx = (viewIdx + 1) % VIEWS.length;
      this.flyView(VIEWS[viewIdx].id);
      this.toast(`視角：${VIEWS[viewIdx].label}`, 1200);
    });
    this.el.reset.addEventListener('click', () => this.installAll());
    this.el.next.addEventListener('click', () => this.guidedNext());
    this.el.tabs.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((b) =>
      b.addEventListener('click', () => this.setTab(b.dataset.tab as 'parts' | 'info')),
    );
    // The overview sheet (shown when nothing is selected) carries the instructions.
    q<HTMLButtonElement>('.help-btn').addEventListener('click', () => {
      this.select(null);
      if (this.isMobile() && this.mobileTab !== 'info') this.setTab('info');
    });
  }

  private isMobile(): boolean {
    return this.el.root.clientWidth < 960;
  }

  private setTab(tab: 'parts' | 'info' | null): void {
    this.mobileTab = this.mobileTab === tab ? null : tab;
    this.renderTabs();
  }

  private renderTabs(): void {
    this.el.root.dataset.tab = this.mobileTab ?? '';
    this.el.tabs.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((b) =>
      b.classList.toggle('active', b.dataset.tab === this.mobileTab),
    );
    this.updateInsets();
  }

  private updateInsets(): void {
    const r = this.el.root.getBoundingClientRect();
    const tb = this.el.toolbar.getBoundingClientRect();
    if (this.isMobile()) {
      const sheet = this.mobileTab ? (this.el.root.querySelector(`[data-pane="${this.mobileTab}"]`) as HTMLElement) : null;
      const bottom = sheet ? r.bottom - sheet.getBoundingClientRect().top : r.bottom - tb.top;
      this.stage?.setInsets(0, 0, Math.max(0, bottom - 40));
    } else {
      // Both side panels are always on screen; the guided caption sits just above the toolbar.
      const left = this.el.mat.getBoundingClientRect().right - r.left;
      const right = r.right - this.el.info.getBoundingClientRect().left;
      this.stage?.setInsets(left, right, r.bottom - tb.top + 36);
    }
  }

  // ---------------------------------------------------------------- state helpers

  private def(id: string): PartDef {
    return this.assembly.parts.get(id)!;
  }

  private names(ids: string[]): string {
    return ids.map((id) => `「${this.def(id).name}」`).join('、');
  }

  private status(id: string): { kind: 'ok' | 'lock' | 'gone' | 'fixed'; text: string } {
    const d = this.def(id);
    if (!d.removable) {
      if (d.parent) return { kind: 'fixed', text: this.assembly.isInstalled(id) ? `焊在${this.def(d.parent).name}上` : `跟著${this.def(d.parent).name}一起拆下了` };
      return { kind: 'fixed', text: '手機骨架，所有零件都裝在它上面' };
    }
    if (!this.assembly.isInstalled(id)) return { kind: 'gone', text: '已拆下，放在零件墊' };
    const blockers = this.assembly.blockersOf(id);
    if (blockers.length) return { kind: 'lock', text: `被${this.names(blockers)}擋住` };
    return { kind: 'ok', text: '現在可以拆下' };
  }

  // ---------------------------------------------------------------- rendering

  private renderAll(): void {
    this.renderMat();
    this.renderInfo();
    this.renderToolbar();
    this.renderTabs();
  }

  /** Teardown position (1-based, video order) of a removable part. */
  private stepOf(id: string): number {
    return this.model.guideOrder.indexOf(id) + 1;
  }

  /**
   * The parts mat: one numbered cell per removable part, in teardown order. A cell fills in when its
   * part comes off, so the mat is the parts list, the removed-parts tray and the progress display.
   */
  private renderMat(): void {
    const cell = (id: string) => {
      const d = this.def(id);
      const st = this.status(id);
      const sel = this.selected === id ? ' selected' : '';
      const mark = st.kind === 'ok' ? icon.out : st.kind === 'lock' ? icon.lock : st.kind === 'gone' ? icon.check : '';
      const n = this.stepOf(id);
      return `<button class="cell ${st.kind}${sel}" data-id="${id}" role="listitem" aria-label="${n}. ${esc(d.name)}：${esc(st.text)}" title="${esc(st.text)}">
        <span class="num">${n}</span><span class="mark">${mark}</span>
        <span class="cname">${esc(d.name)}</span></button>`;
    };
    const base = this.model.parts.find((p) => !p.removable && !p.parent);
    const baseCell = base
      ? `<button class="cell base${this.selected === base.id ? ' selected' : ''}" data-id="${base.id}" aria-label="${esc(base.name)}：${esc(this.status(base.id).text)}">
          <span class="num">骨架</span><span class="cname">${esc(base.name)}</span></button>`
      : '';
    this.el.list.innerHTML = this.model.guideOrder.map(cell).join('');
    this.el.mat.querySelector('.mat-foot')!.innerHTML = baseCell;
    this.el.mat.querySelectorAll<HTMLButtonElement>('.cell').forEach((b) =>
      b.addEventListener('click', () => this.select(b.dataset.id!, { fromList: true })),
    );
    const total = this.model.guideOrder.length;
    const off = this.removalOrder.length;
    this.el.progress.innerHTML = `已拆 <b>${off}</b> / ${total}`;
    this.el.root.querySelector('.mat-count')!.textContent = off ? String(off) : '';
  }

  private renderOverview(): string {
    const [w, hh, d] = this.model.size;
    const jump = (id: string, line: string) =>
      `<button class="jump" data-goto="${id}"><b>${esc(this.def(id).name)}</b><span>${line}</span></button>`;
    return `<div class="card overview">
        <h2>動手拆開它</h2>
        <p class="summary">這是一支可以拆的 3D ${esc(this.model.name)}。${this.model.guideOrder.length} 個零件照拆解影片的順序編號，拆下來的會擺到零件墊上。</p>
        <ol class="howto">
          <li>拖曳旋轉，滾輪或雙指縮放。</li>
          <li>點一下零件看介紹。發亮的零件現在就拆得下來。</li>
          <li>按「拆下」往裡面走；被擋住的零件會告訴你要先拆哪個。</li>
          <li>想照影片的順序看，就一直按「下一步」。</li>
        </ol>
        <h3>這一代最值得看的三個地方</h3>
        <div class="jumps">
          ${jump('vc', '面積是上一代的三倍多，幾乎蓋住整支手機')}
          ${jump('faceId', '紅外鏡頭藏到螢幕底下，靈動島因此變小')}
          ${jump('soc', '記憶體從疊在處理器上面改成擺在旁邊')}
        </div>
        <dl class="specs">
          <div><dt>機身尺寸</dt><dd>${w} × ${hh} × ${d} mm</dd></div>
          <div><dt>拆解影片</dt><dd><a href="${this.model.source.url}" target="_blank" rel="noopener">微機分 WekiHome</a>，${esc(this.model.source.date)}</dd></div>
        </dl>
        <p class="geo-note">${esc(this.model.sizeNote)}厚度方向的位置是推估的。</p>
      </div>`;
  }

  private bindGoto(panel: HTMLElement): void {
    panel.querySelectorAll<HTMLButtonElement>('[data-goto]').forEach((b) =>
      b.addEventListener('click', () => this.select(b.dataset.goto!, { fromList: true })),
    );
  }

  private renderInfo(): void {
    const id = this.selected;
    const panel = this.el.info;
    panel.classList.toggle('open', !!id);
    const changed = this.infoShown !== id;
    this.infoShown = id;
    if (!id) {
      panel.innerHTML = this.renderOverview();
      this.bindGoto(panel);
      if (changed) panel.scrollTop = 0;
      this.updateInsets();
      return;
    }
    const d = this.def(id);
    const st = this.status(id);
    const focusOn = this.viewer.focus === id || this.viewer.inspect === id;
    const btns: string[] = [];
    if (d.removable) {
      if (st.kind === 'ok') btns.push(`<button class="primary act" data-act="remove">拆下</button>`);
      if (st.kind === 'lock') btns.push(`<button class="primary act" data-act="through">幫我拆到這裡</button>`);
      if (st.kind === 'gone') btns.push(`<button class="primary act" data-act="install">裝回去</button>`);
    }
    if (this.assembly.isInstalled(id) || d.removable)
      btns.push(`<button class="act" data-act="focus">${focusOn ? icon.close + '離開特寫' : icon.zoom + '特寫'}</button>`);
    if (d.extra) {
      const on = this.viewer.extrasOn.has(id);
      btns.push(`<button class="act extra" data-act="extra" aria-pressed="${on}">${EXTRA_LABEL[d.extra][on ? 1 : 0]}</button>`);
    }
    const t = (s?: { t: string }) =>
      s ? `<a class="ts" href="${this.model.source.url}?t=${toSeconds(s.t)}" target="_blank" rel="noopener" title="在影片中查看">${icon.play}${s.t}</a>` : '';
    const kids = this.model.parts.filter((p) => p.parent === id);
    const step = d.removable ? `<span class="step">第 ${this.stepOf(id)} 個拆</span>` : '';
    panel.innerHTML = `
      <div class="card">
        <button class="icon-btn close" aria-label="關閉">${icon.close}</button>
        <div class="meta"><span class="kind">${categoryIcon[d.category]}${categoryName[d.category]}</span>${step}</div>
        <h2>${esc(d.name)}</h2>
        ${d.subtitle ? `<div class="subtitle">${esc(d.subtitle)}</div>` : ''}
        <div class="status ${st.kind}">${st.kind === 'lock' ? icon.lock : ''}${esc(st.text)}</div>
        <div class="actions">${btns.join('')}</div>
        <p class="summary">${esc(d.summary)}</p>
        ${
          kids.length
            ? `<h3>焊在上面的晶片</h3><div class="jumps">${kids
                .map((k) => `<button class="jump" data-goto="${k.id}"><b>${esc(k.name)}</b>${k.subtitle ? `<span>${esc(k.subtitle)}</span>` : ''}</button>`)
                .join('')}</div>`
            : ''
        }
        ${d.parent ? `<div class="jumps"><button class="jump" data-goto="${d.parent}"><span>它焊在</span><b>${esc(this.def(d.parent).name)}</b></button></div>` : ''}
        ${d.specs?.length ? `<dl class="specs">${d.specs.map((s) => `<div><dt>${esc(s.label)}</dt><dd>${esc(s.value)} ${t(s.source)}</dd></div>`).join('')}</dl>` : ''}
        ${d.facts?.length ? `<h3>拆解發現</h3><ul class="facts">${d.facts.map((f) => `<li>${esc(f.text)} ${t(f.source)}</li>`).join('')}</ul>` : ''}
        ${d.geometry === 'observed' ? '' : '<p class="geo-note">這個零件在拆解影像裡被其他零件擋住，外形與位置是推估的。</p>'}
      </div>`;
    if (changed) panel.scrollTop = 0;
    panel.querySelector('.close')!.addEventListener('click', () => this.select(null));
    panel.querySelectorAll<HTMLButtonElement>('.act').forEach((b) => b.addEventListener('click', () => this.action(b.dataset.act!, id)));
    this.bindGoto(panel);
    this.updateInsets();
  }

  private renderToolbar(): void {
    this.el.undo.disabled = this.history.length === 0;
    this.el.reset.disabled = this.removalOrder.length === 0;
    const done = !this.model.guideOrder.some((id) => this.assembly.isInstalled(id));
    this.el.next.querySelector('span')!.textContent = done ? '全部組回，重新開始' : '下一步';
    this.el.caption.innerHTML = this.guideCaption;
    this.el.caption.classList.toggle('show', !!this.guideCaption);
  }

  private toast(msg: string, ms = 3200): void {
    this.el.toast.innerHTML = msg;
    this.el.toast.classList.add('show');
    clearTimeout((this.toast as unknown as { t?: number }).t);
    (this.toast as unknown as { t?: number }).t = window.setTimeout(() => this.el.toast.classList.remove('show'), ms);
  }

  // ---------------------------------------------------------------- selection & camera

  private select(id: string | null, opts: { fromList?: boolean; inspect?: boolean } = {}): void {
    const prev = this.selected;
    this.selected = id;
    this.viewer.selected = id;
    // Extras belong to the selection; switch them off when leaving a part.
    if (prev && prev !== id) this.viewer.extrasOn.delete(prev);
    const removed = id ? !this.assembly.isInstalled(id) : false;
    if (!id || (this.viewer.focus && this.viewer.focus !== id) || (this.viewer.inspect && this.viewer.inspect !== id)) this.exitFocus(!id);
    if (id && removed && (opts.inspect || opts.fromList)) {
      const d = this.def(id);
      this.enterFocus(d.parent && !this.assembly.isInstalled(d.parent) ? d.parent : id, true);
    } else if (id && opts.fromList) this.ensureVisible(id);
    if (id && this.status(id).kind === 'lock') this.viewer.flash(this.assembly.blockersOf(id));
    if (id && this.isMobile() && (opts.fromList || opts.inspect || this.mobileTab)) this.mobileTab = 'info';
    this.viewer.refresh();
    this.renderAll();
  }

  private sideOf(id: string): Side {
    const d = this.def(id);
    return d.parent ? this.def(d.parent).viewFrom : d.viewFrom;
  }

  /** If the camera looks at the wrong face of the phone, swing around to the part's side. */
  private async ensureVisible(id: string): Promise<void> {
    const side = this.sideOf(id);
    const cam = this.stage.camera.position.clone().sub(this.stage.controls.target);
    if (side === 'front' && cam.z < 40) await this.flyView('three');
    else if (side === 'back' && cam.z > -40) await this.flyView('backThree');
    else if (side === 'side' && cam.x > -60) await this.flyView('side');
  }

  private flyView(view: string): Promise<void> {
    if (this.viewer.focus || this.viewer.inspect) this.exitFocus(false);
    const preset = VIEWS.find((v) => v.id === view)?.pos ?? (view === 'backThree' ? [-230, 110, -330] : [230, 110, 330]);
    return this.stage.flyTo({ position: new Vector3(...preset), target: new Vector3(0, 0, 0) });
  }

  private enterFocus(id: string, inspect: boolean): void {
    if (!this.viewer.focus && !this.viewer.inspect) this.returnPose = this.stage.pose();
    if (inspect) {
      this.viewer.inspect = id;
      this.viewer.focus = null;
    } else {
      this.viewer.focus = id;
      this.viewer.inspect = null;
    }
    this.viewer.refresh();
    const b = this.viewer.bounds(id);
    const c = b.getCenter(new Vector3());
    const size = b.getSize(new Vector3());
    const span = Math.max(size.x, size.y, size.z * 0.6, 18);
    const dist = (span * 1.9) / Math.tan((this.stage.camera.fov * Math.PI) / 360) / 2 / this.stage.camera.zoom;
    const side = this.sideOf(id);
    const dir = side === 'back' ? new Vector3(-0.28, 0.2, -1) : side === 'side' ? new Vector3(-1, 0.25, 0.35) : new Vector3(0.28, 0.2, 1);
    this.stage.flyTo({ position: c.clone().add(dir.normalize().multiplyScalar(Math.max(dist, 70))), target: c });
  }

  private exitFocus(flyBack: boolean): void {
    if (!this.viewer.focus && !this.viewer.inspect) return;
    this.viewer.focus = null;
    this.viewer.inspect = null;
    this.viewer.refresh();
    if (flyBack && this.returnPose) this.stage.flyTo(this.returnPose);
    this.returnPose = null;
  }

  // ---------------------------------------------------------------- actions

  private action(act: string, id: string): void {
    this.dismissHints();
    switch (act) {
      case 'remove':
        this.run(() => this.assembly.planRemove(id));
        break;
      case 'through': {
        const pre = this.assembly.planRemove(id).slice(0, -1);
        if (pre.length) this.toast(`先拆下${this.names(pre.map((s) => s.id))}`);
        this.run(() => this.assembly.planRemove(id));
        break;
      }
      case 'install':
        this.exitFocus(true);
        this.run(() => this.assembly.planInstall(id));
        break;
      case 'focus':
        if (this.viewer.focus === id || this.viewer.inspect === id) this.exitFocus(true);
        else this.enterFocus(id, !this.assembly.isInstalled(id));
        this.renderInfo();
        break;
      case 'extra':
        if (this.viewer.extrasOn.has(id)) this.viewer.extrasOn.delete(id);
        else {
          this.viewer.extrasOn.add(id);
          if (this.def(id).extra === 'dotProjector') this.flyDots();
        }
        this.viewer.refresh();
        this.renderInfo();
        break;
    }
  }

  private flyDots(): void {
    this.exitFocus(false);
    this.stage.flyTo({ position: new Vector3(150, 120, 330), target: new Vector3(0, 40, 30) });
  }

  private dismissHints(): void {
    if (this.touchedAnything) return;
    this.touchedAnything = true;
    this.viewer.hints.clear();
    this.viewer.refresh();
  }

  /**
   * Queue a plan. The plan is computed when the queue reaches it (so rapid clicks never act on
   * stale state). Each step updates the logical state first, then animates.
   */
  private run(plan: Step[] | (() => Step[]), opts: { record?: boolean; fast?: boolean } = {}): Promise<void> {
    const record = opts.record ?? true;
    this.busy++;
    this.el.root.classList.add('busy');
    this.queue = this.queue.then(async () => {
      const steps = typeof plan === 'function' ? plan() : plan;
      const done: Step[] = [];
      for (const step of steps) {
        try {
          this.assembly.apply(step);
        } catch (err) {
          console.warn(err);
          break;
        }
        done.push(step);
        if (step.op === 'remove') {
          this.removalOrder.push(step.id);
          if (this.viewer.inspect === step.id) this.viewer.inspect = null;
          const f = this.viewer.focus;
          if (f && (f === step.id || this.def(f).parent === step.id)) this.exitFocus(true);
        } else {
          this.removalOrder = this.removalOrder.filter((x) => x !== step.id);
          if (this.viewer.inspect === step.id) this.exitFocus(false);
        }
        this.renderAll();
        const dur = opts.fast ? 0.28 : steps.length > 2 ? 0.5 : 0.8;
        const from = step.op === 'remove' ? 0 : 1;
        const to = 1 - from;
        await this.stage.tweens.run(dur, (k) => this.viewer.setOut(step.id, from + (to - from) * k), { key: `part:${step.id}` });
      }
      if (record && done.length) this.history.push(done);
      const removed = new Set(this.assembly.removedIds());
      this.removalOrder = [...this.removalOrder.filter((x) => removed.has(x)), ...[...removed].filter((x) => !this.removalOrder.includes(x))];
      this.busy--;
      if (!this.busy) this.el.root.classList.remove('busy');
      this.renderAll();
    });
    return this.queue;
  }

  /** History is read and cleared inside the queue so it always matches completed actions. */
  private undo(): void {
    if (!this.history.length && !this.busy) return;
    this.guideCaption = '';
    this.exitFocus(false);
    this.run(
      () => {
        const last = this.history.pop();
        if (!last) return [];
        return [...last].reverse().map((s): Step => ({ op: s.op === 'remove' ? 'install' : 'remove', id: s.id }));
      },
      { record: false },
    );
  }

  private installAll(): void {
    this.guideCaption = '';
    this.exitFocus(false);
    this.viewer.extrasOn.clear();
    this.run(
      () => {
        this.history = [];
        return this.assembly.planInstallAll();
      },
      { record: false, fast: true },
    );
  }

  private async guidedNext(): Promise<void> {
    this.dismissHints();
    if (this.busy || this.guiding) return;
    const plan = this.assembly.nextGuided(this.model.guideOrder);
    if (!plan.length) {
      this.installAll();
      this.toast('全部零件已經組回，可以重新開始拆解。');
      return;
    }
    const target = plan[plan.length - 1].id;
    const d = this.def(target);
    const idx = this.model.guideOrder.indexOf(target) + 1;
    this.select(target);
    this.guideCaption = `<b>第 ${idx} / ${this.model.guideOrder.length} 步</b>${esc(d.guideLine ?? `取出${d.name}。`)}`;
    this.renderToolbar();
    this.guiding = true;
    try {
      await this.ensureVisible(target);
      await this.run(() => this.assembly.nextGuided(this.model.guideOrder));
      if (!this.model.guideOrder.some((x) => this.assembly.isInstalled(x)) && this.guideCaption) {
        this.guideCaption = `<b>拆完了</b>${this.model.guideOrder.length} 個零件都在零件墊上，點任何一格可以拿起來再看一次。`;
        this.renderToolbar();
      }
    } finally {
      this.guiding = false;
    }
  }

  // ---------------------------------------------------------------- input

  private bindPointer(): void {
    const canvas = this.stage.renderer.domElement;
    const ndc = new Vector2();
    let down: { x: number; y: number; t: number } | null = null;
    let lastTap = { id: '', t: 0 };
    const toNdc = (e: PointerEvent | MouseEvent) => {
      const r = canvas.getBoundingClientRect();
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      return ndc;
    };
    canvas.addEventListener('pointerdown', (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
      this.hideTooltip();
    });
    canvas.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 600;
      down = null;
      if (moved > 6 || !quick) return;
      const id = this.viewer.pick(toNdc(e));
      const now = performance.now();
      if (id && lastTap.id === id && now - lastTap.t < 350) {
        // Double tap / click: close-up.
        if (this.viewer.focus !== id && this.viewer.inspect !== id) this.enterFocus(id, !this.assembly.isInstalled(id));
        this.renderInfo();
        lastTap = { id: '', t: 0 };
        return;
      }
      lastTap = { id: id ?? '', t: now };
      if (id) this.select(id);
      else if (this.viewer.focus || this.viewer.inspect) {
        this.exitFocus(true);
        this.renderInfo();
      } else this.select(null);
    });
    let pending = false;
    canvas.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || e.buttons) return;
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => {
        pending = false;
        const id = this.viewer.pick(toNdc(e));
        this.setHover(id, e.clientX, e.clientY);
      });
    });
    canvas.addEventListener('pointerleave', () => this.setHover(null, 0, 0));
  }

  private setHover(id: string | null, x: number, y: number): void {
    const canvas = this.stage.renderer.domElement;
    if (!id) {
      if (this.viewer.hover) {
        this.viewer.hover = null;
        this.viewer.refresh();
      }
      canvas.style.cursor = '';
      this.hideTooltip();
      return;
    }
    const d = this.def(id);
    const st = this.status(id);
    const hover = d.removable ? { id, ok: st.kind === 'ok' } : null;
    if (hover?.id !== this.viewer.hover?.id || hover?.ok !== this.viewer.hover?.ok) {
      this.viewer.hover = hover;
      this.viewer.refresh();
    }
    canvas.style.cursor = 'pointer';
    const tip = this.el.tooltip;
    tip.innerHTML = `<b>${esc(d.name)}</b><span class="${st.kind}">${st.kind === 'lock' ? icon.lock : ''}${esc(st.text)}</span>`;
    tip.style.transform = `translate(${x + 16}px, ${y + 14}px)`;
    tip.classList.add('show');
  }

  private hideTooltip(): void {
    this.el.tooltip.classList.remove('show');
  }

  private bindKeys(): void {
    window.addEventListener('keydown', (e) => {
      if ((e.target as HTMLElement).tagName === 'INPUT') return;
      if (e.key === 'Escape') {
        if (this.viewer.focus || this.viewer.inspect) {
          this.exitFocus(true);
          this.renderInfo();
        } else this.select(null);
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && this.selected && this.assembly.canRemove(this.selected)) {
        this.action('remove', this.selected);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        this.undo();
      } else if (e.key === 'n' || e.key === 'N') this.guidedNext();
    });
  }
}
