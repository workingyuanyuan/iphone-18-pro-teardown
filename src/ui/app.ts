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
  private returnPose: Pose | null = null;
  private guideCaption = '';
  private touchedAnything = false;
  private mobileTab: 'parts' | 'info' | 'tray' | null = null;
  private reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  private el!: {
    root: HTMLElement;
    stageHost: HTMLElement;
    list: HTMLElement;
    info: HTMLElement;
    tray: HTMLElement;
    trayItems: HTMLElement;
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
    onboarding: HTMLElement;
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
        <div class="brand"><span class="brand-mark">${icon.sparkle}</span><span>拆機實驗室</span></div>
        <div class="model-pill" title="目前機型">${esc(this.model.name)}</div>
        <div class="progress" aria-live="polite"></div>
        <div class="topbar-actions">
          <a class="src-link" href="${this.model.source.url}" target="_blank" rel="noopener">資料來源：微機分 WekiHome 拆解影片</a>
          <button class="icon-btn help-btn" aria-label="操作說明">${icon.help}</button>
        </div>
      </header>
      <div class="stage-host"></div>
      <aside class="panel parts-panel" data-pane="parts" aria-label="零件清單">
        <div class="panel-head"><h2>零件清單</h2><span class="legend"><i class="dot ok"></i>可拆 <i class="dot lock"></i>被擋住 <i class="dot gone"></i>已拆</span></div>
        <div class="part-list" role="list"></div>
      </aside>
      <aside class="panel info-panel" data-pane="info" aria-label="零件介紹"></aside>
      <section class="tray" data-pane="tray" aria-label="零件盤">
        <div class="tray-head"><h2>零件盤</h2><span class="tray-hint">拆下的零件會放在這裡，點一下就能拿起來看</span><button class="act tray-reset">${icon.reset}全部組回</button></div>
        <div class="tray-items"></div>
      </section>
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
        <div class="tool-group">
          <button class="tool undo" title="復原上一步">${icon.undo}<span>復原</span></button>
          <button class="tool reset" title="全部組回">${icon.reset}<span>全部組回</span></button>
        </div>
        <button class="tool primary next" title="照影片順序拆下一個零件">${icon.next}<span>下一步</span></button>
      </nav>
      <nav class="tabs" aria-label="面板">
        <button data-tab="parts">零件</button><button data-tab="info">介紹</button><button data-tab="tray">零件盤 <b class="tray-count"></b></button>
      </nav>
      <div class="tooltip" role="tooltip"></div>
      <div class="toast" role="status"></div>
      <div class="onboarding" role="dialog" aria-modal="false" aria-labelledby="ob-title">
        <div class="ob-card">
          <h2 id="ob-title">把 ${esc(this.model.name)} 拆開來看看</h2>
          <ol>
            <li><b>拖曳</b>旋轉、<b>滾輪 / 雙指</b>縮放，看看手機的每一面。</li>
            <li><b>點一下零件</b>看它是什麼；發出<span class="c-ok">青綠色光</span>的就是現在拆得下來的。</li>
            <li>按卡片上的 <b>「拆下」</b>，一層一層往裡面探索；被擋住的零件會告訴你要先拆哪個。</li>
            <li>不想自己找？按右下角 <b>「下一步」</b>，照拆解影片的順序帶你走一遍。</li>
          </ol>
          <button class="primary ob-go">開始探索</button>
        </div>
      </div>`;
    this.host.appendChild(root);
    const q = <T extends Element>(s: string) => root.querySelector(s) as T;
    this.el = {
      root,
      stageHost: q('.stage-host'),
      list: q('.part-list'),
      info: q('.info-panel'),
      tray: q('.tray'),
      trayItems: q('.tray-items'),
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
      onboarding: q('.onboarding'),
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
    q<HTMLButtonElement>('.tray-reset').addEventListener('click', () => this.installAll());
    this.el.reset.addEventListener('click', () => this.installAll());
    this.el.next.addEventListener('click', () => this.guidedNext());
    this.el.tabs.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((b) =>
      b.addEventListener('click', () => this.setTab(b.dataset.tab as 'parts' | 'info' | 'tray')),
    );
    q<HTMLButtonElement>('.ob-go').addEventListener('click', () => this.closeOnboarding());
    q<HTMLButtonElement>('.help-btn').addEventListener('click', () => this.el.onboarding.classList.add('show'));
    let seen = false;
    try {
      seen = localStorage.getItem('teardown.onboarded') === '1';
    } catch {
      /* storage unavailable */
    }
    if (!seen) this.el.onboarding.classList.add('show');
  }

  private closeOnboarding(): void {
    this.el.onboarding.classList.remove('show');
    try {
      localStorage.setItem('teardown.onboarded', '1');
    } catch {
      /* storage unavailable */
    }
  }

  private isMobile(): boolean {
    return this.el.root.clientWidth < 960;
  }

  private setTab(tab: 'parts' | 'info' | 'tray' | null): void {
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
    if (this.isMobile()) {
      const sheet = this.mobileTab ? (this.el.root.querySelector(`[data-pane="${this.mobileTab}"]`) as HTMLElement) : null;
      const tb = (this.el.root.querySelector('.toolbar') as HTMLElement).getBoundingClientRect();
      const bottom = sheet ? r.bottom - sheet.getBoundingClientRect().top : r.bottom - tb.top;
      this.stage?.setInsets(0, 0, Math.max(0, bottom - 40));
    } else {
      const left = (this.el.root.querySelector('.parts-panel') as HTMLElement).getBoundingClientRect().right - r.left;
      const info = this.el.info.getBoundingClientRect();
      const right = this.el.info.classList.contains('open') ? r.right - info.left : 0;
      const tray = this.el.tray.getBoundingClientRect();
      const bottom = r.bottom - Math.min(tray.top, (this.el.root.querySelector('.toolbar') as HTMLElement).getBoundingClientRect().top);
      this.stage?.setInsets(left, right, bottom * 0.6);
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
    if (!this.assembly.isInstalled(id)) return { kind: 'gone', text: '已拆下，放在零件盤' };
    const blockers = this.assembly.blockersOf(id);
    if (blockers.length) return { kind: 'lock', text: `被${this.names(blockers)}擋住` };
    return { kind: 'ok', text: '現在可以拆下' };
  }

  // ---------------------------------------------------------------- rendering

  private renderAll(): void {
    this.renderList();
    this.renderInfo();
    this.renderTray();
    this.renderToolbar();
    this.renderTabs();
  }

  private renderList(): void {
    const order = [...this.model.guideOrder];
    const top = ['frame', ...order];
    const html = top
      .map((id) => {
        const rows = [id, ...this.model.parts.filter((p) => p.parent === id).map((p) => p.id)];
        return rows
          .map((rid) => {
            const d = this.def(rid);
            const st = this.status(rid);
            const child = d.parent ? ' child' : '';
            const sel = this.selected === rid ? ' selected' : '';
            const mark = st.kind === 'ok' ? icon.out : st.kind === 'lock' ? icon.lock : st.kind === 'gone' ? icon.check : '';
            return `<button class="part-row ${st.kind}${child}${sel}" data-id="${rid}" role="listitem" aria-label="${esc(d.name)}：${esc(st.text)}">
              <span class="cat">${categoryIcon[d.category]}</span>
              <span class="pname">${esc(d.name)}<small>${esc(st.text)}</small></span>
              <span class="mark">${mark}</span></button>`;
          })
          .join('');
      })
      .join('');
    this.el.list.innerHTML = html;
    this.el.list.querySelectorAll<HTMLButtonElement>('.part-row').forEach((b) =>
      b.addEventListener('click', () => this.select(b.dataset.id!, { fromList: true })),
    );
    const removable = this.model.parts.filter((p) => p.removable).length;
    this.el.progress.innerHTML = `已拆 <b>${this.removalOrder.length}</b> / ${removable} 個零件`;
  }

  private renderInfo(): void {
    const id = this.selected;
    const panel = this.el.info;
    if (!id) {
      panel.classList.remove('open');
      panel.innerHTML = `<div class="info-empty">
        <h2>${esc(this.model.name)}</h2>
        <p>點選手機上的任何零件，這裡會告訴你它是什麼、做什麼用，以及拆解影片裡發現的小知識。</p>
        <p class="muted">${esc(this.model.sizeNote)}</p></div>`;
      this.updateInsets();
      return;
    }
    const d = this.def(id);
    const st = this.status(id);
    const focusOn = this.viewer.focus === id || this.viewer.inspect === id;
    const btns: string[] = [];
    if (d.removable) {
      if (st.kind === 'ok') btns.push(`<button class="primary act" data-act="remove">${icon.out}拆下</button>`);
      if (st.kind === 'lock') btns.push(`<button class="primary act" data-act="through">${icon.out}幫我拆到這裡</button>`);
      if (st.kind === 'gone') btns.push(`<button class="primary act" data-act="install">${icon.undo}裝回去</button>`);
    }
    if (this.assembly.isInstalled(id) || d.removable)
      btns.push(`<button class="act" data-act="focus">${focusOn ? icon.close + '離開特寫' : icon.zoom + '特寫'}</button>`);
    if (d.extra) {
      const on = this.viewer.extrasOn.has(id);
      btns.push(`<button class="act extra" data-act="extra" aria-pressed="${on}">${icon.sparkle}${EXTRA_LABEL[d.extra][on ? 1 : 0]}</button>`);
    }
    const t = (s?: { t: string }) =>
      s ? `<a class="ts" href="${this.model.source.url}?t=${toSeconds(s.t)}" target="_blank" rel="noopener" title="在影片中查看">${icon.play}${s.t}</a>` : '';
    panel.classList.add('open');
    panel.innerHTML = `
      <div class="card">
        <button class="icon-btn close" aria-label="關閉">${icon.close}</button>
        <div class="badge">${categoryIcon[d.category]}${categoryName[d.category]}</div>
        <h2>${esc(d.name)}</h2>
        ${d.subtitle ? `<div class="subtitle">${esc(d.subtitle)}</div>` : ''}
        <div class="status ${st.kind}">${st.kind === 'lock' ? icon.lock : ''}${esc(st.text)}</div>
        <div class="actions">${btns.join('')}</div>
        <p class="summary">${esc(d.summary)}</p>
        ${d.specs?.length ? `<dl class="specs">${d.specs.map((s) => `<div><dt>${esc(s.label)}</dt><dd>${esc(s.value)} ${t(s.source)}</dd></div>`).join('')}</dl>` : ''}
        ${d.facts?.length ? `<h3>拆解發現</h3><ul class="facts">${d.facts.map((f) => `<li>${esc(f.text)} ${t(f.source)}</li>`).join('')}</ul>` : ''}
        <p class="geo-note">${d.geometry === 'observed' ? '' : '這個零件在拆解影像裡被其他零件擋住，外形與位置是推估的。'}</p>
      </div>`;
    panel.querySelector('.close')!.addEventListener('click', () => this.select(null));
    panel.querySelectorAll<HTMLButtonElement>('.act').forEach((b) => b.addEventListener('click', () => this.action(b.dataset.act!, id)));
    this.updateInsets();
  }

  private renderTray(): void {
    const items = this.removalOrder;
    this.el.trayItems.innerHTML = items.length
      ? items
          .map((id) => {
            const d = this.def(id);
            return `<button class="tray-item${this.selected === id ? ' selected' : ''}" data-id="${id}">${categoryIcon[d.category]}<span>${esc(d.name)}</span></button>`;
          })
          .join('')
      : '<div class="tray-empty">還沒有拆下任何零件</div>';
    this.el.trayItems.querySelectorAll<HTMLButtonElement>('.tray-item').forEach((b) =>
      b.addEventListener('click', () => this.select(b.dataset.id!, { inspect: true })),
    );
    this.el.root.querySelector('.tray-count')!.textContent = items.length ? String(items.length) : '';
    this.el.tray.classList.toggle('has-items', items.length > 0);
  }

  private renderToolbar(): void {
    this.el.undo.disabled = this.history.length === 0;
    this.el.reset.disabled = this.removalOrder.length === 0;
    const done = !this.model.guideOrder.some((id) => this.assembly.isInstalled(id));
    this.el.next.querySelector('span')!.textContent = done ? '重新開始' : '下一步';
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
        if (pre.length) this.toast(`先拆下${this.names(pre.map((s) => s.id))}…`);
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
    this.guideCaption = `<b>導覽 ${idx}/${this.model.guideOrder.length}</b>${esc(d.guideLine ?? `取出${d.name}。`)}`;
    this.renderToolbar();
    this.guiding = true;
    try {
      await this.ensureVisible(target);
      await this.run(() => this.assembly.nextGuided(this.model.guideOrder));
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
        if (this.el.onboarding.classList.contains('show')) this.closeOnboarding();
        else if (this.viewer.focus || this.viewer.inspect) {
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
