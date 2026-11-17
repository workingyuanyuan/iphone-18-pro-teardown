import {
  Box3,
  Color,
  Group,
  Mesh,
  MeshStandardMaterial,
  Raycaster,
  Vector2,
  Vector3,
  type Material,
  type Object3D,
} from 'three';
import type { PartDef, PhoneModel } from '../core/types';
import type { Stage } from './stage';
import { easeOut } from './tween';

interface MatState {
  m: Material;
  opacity: number;
  transparent: boolean;
  depthWrite: boolean;
  emissive?: Color;
  emissiveIntensity?: number;
}

interface PartView {
  def: PartDef;
  obj: Object3D;
  mats: MatState[];
  /** Extra-visual objects owned by this part (not by nested child parts). */
  extras: Object3D[];
  /** Removal progress 0 (installed) .. 1 (fully out and hidden). */
  out: number;
  /** Current effective opacity (used for picking). */
  opacity: number;
}

/** Parts that form the outer shell and turn translucent in X-ray mode. */
const SHELL = new Set(['frame', 'display', 'backGlass']);
const REMOVE_DIST = 90;
const INSPECT_OUT = 0.42;

const TINT = {
  selected: new Color('#fff6ea'),
  ok: new Color('#dbeaff'),
  blocked: new Color('#ff8a3d'),
};

/**
 * Owns the three.js objects of one phone and derives every visual property
 * (position, opacity, tint, extras) from explicit state each refresh.
 */
export class PhoneViewer {
  readonly root = new Group();
  private views = new Map<string, PartView>();
  private raycaster = new Raycaster();

  explode = 0;
  xray = false;
  selected: string | null = null;
  hover: { id: string; ok: boolean } | null = null;
  /** Close-up mode: everything but this part (and its family) is ghosted. */
  focus: string | null = null;
  /** A removed part shown floating near its home for inspection. */
  inspect: string | null = null;
  readonly extrasOn = new Set<string>();
  /** Parts pulsing as a hint (e.g. "you can remove these"). */
  hints = new Set<string>();
  private flashes = new Map<string, number>();
  private time = 0;

  constructor(
    model: PhoneModel,
    private stage: Stage,
    /** One object per part id, from `model.load()`. */
    objs: Map<string, Object3D>,
  ) {
    // Children first so their meshes keep their own part id.
    const ordered = [...model.parts].sort((a, b) => Number(!!b.parent) - Number(!!a.parent));
    for (const def of ordered) {
      const obj = objs.get(def.id);
      if (!obj) throw new Error(`no geometry for ${def.id}`);
      obj.userData.partId = def.id;
      this.views.set(def.id, { def, obj, mats: [], extras: [], out: 0, opacity: 1 });
    }
    for (const v of this.views.values()) {
      const parent = v.def.parent ? this.views.get(v.def.parent)!.obj : this.root;
      parent.add(v.obj);
    }
    for (const v of this.views.values()) this.collect(v);
    stage.scene.add(this.root);
    stage.onFrame((dt) => this.frame(dt));
    this.refresh();
  }

  private collect(v: PartView): void {
    const seen = new Set<Material>();
    const walk = (o: Object3D) => {
      if (o !== v.obj && o.userData.partId) return; // nested child part
      if (o.userData.extra) v.extras.push(o);
      if (o.userData.overlay) o.raycast = () => {};
      if ((o as Mesh).isMesh) {
        const mats = ([] as Material[]).concat((o as Mesh).material);
        for (const m of mats) {
          if (seen.has(m)) continue;
          seen.add(m);
          const st: MatState = { m, opacity: m.opacity, transparent: m.transparent, depthWrite: m.depthWrite };
          if (m instanceof MeshStandardMaterial) {
            st.emissive = m.emissive.clone();
            st.emissiveIntensity = m.emissiveIntensity;
          }
          v.mats.push(st);
        }
      }
      for (const c of o.children) walk(c);
    };
    walk(v.obj);
  }

  def(id: string): PartDef | undefined {
    return this.views.get(id)?.def;
  }

  setOut(id: string, k: number): void {
    const v = this.views.get(id);
    if (!v) return;
    v.out = k;
    this.refresh();
  }

  getOut(id: string): number {
    return this.views.get(id)?.out ?? 0;
  }

  flash(ids: string[]): void {
    for (const id of ids) this.flashes.set(id, 1.6);
    this.stage.invalidate();
  }

  private family(a: string, b: string): boolean {
    if (a === b) return true;
    const da = this.views.get(a)?.def,
      db = this.views.get(b)?.def;
    return da?.parent === b || db?.parent === a;
  }

  private frame(dt: number): boolean {
    this.time += dt;
    let animating = this.hints.size > 0 || this.selected !== null;
    for (const [id, t] of this.flashes) {
      const nt = t - dt;
      if (nt <= 0) this.flashes.delete(id);
      else this.flashes.set(id, nt);
      animating = true;
    }
    if (animating) this.refresh();
    return animating;
  }

  /** Recompute every part's transform and material state from the current state. */
  refresh(): void {
    const pulse = 0.5 + 0.5 * Math.sin(this.time * 4);
    const fades = new Map<string, number>();
    // Pass 1: transforms and removal fade of top-level parts (children inherit both).
    for (const v of this.views.values()) {
      const { def, obj } = v;
      if (def.parent) continue;
      let fade = 1;
      if (def.removable) {
        const inspecting = this.inspect === def.id && v.out >= 1;
        const out = inspecting ? INSPECT_OUT : v.out;
        const e = this.explode;
        const d = REMOVE_DIST * easeOut(out);
        obj.position.set(
          def.explode[0] * e + def.removeDir[0] * d,
          def.explode[1] * e + def.removeDir[1] * d,
          def.explode[2] * e + def.removeDir[2] * d,
        );
        fade = inspecting ? 1 : v.out < 0.55 ? 1 : Math.max(0, 1 - (v.out - 0.55) / 0.45);
        fades.set(def.id, fade);
        continue;
      }
      fades.set(def.id, fade);
    }
    // Pass 2: opacity, tint and extras.
    for (const v of this.views.values()) {
      const { def } = v;
      const fade = fades.get(def.parent ?? def.id) ?? 1;
      v.opacity = fade * this.ghostOf(def.id);
      if (!def.parent) v.obj.visible = v.opacity > 0.01;

      let tint: Color | null = null;
      let k = 0;
      if (this.selected === def.id) {
        tint = TINT.selected;
        k = 0.06 + 0.05 * pulse;
      } else if (this.hover?.id === def.id) {
        tint = this.hover.ok ? TINT.ok : TINT.blocked;
        k = 0.16;
      } else if (this.flashes.has(def.id)) {
        tint = TINT.blocked;
        k = 0.1 + 0.3 * pulse;
      } else if (this.hints.has(def.id)) {
        tint = TINT.ok;
        k = 0.04 + 0.14 * pulse;
      }

      for (const s of v.mats) {
        const o = s.opacity * v.opacity;
        const translucent = o < 0.999;
        s.m.opacity = o;
        const transparent = translucent || s.transparent;
        if (s.m.transparent !== transparent) {
          s.m.transparent = transparent;
          s.m.needsUpdate = true;
        }
        s.m.depthWrite = translucent ? false : s.depthWrite;
        if (s.m instanceof MeshStandardMaterial && s.emissive) {
          s.m.emissive.copy(s.emissive);
          if (tint) s.m.emissive.lerp(tint, k);
          // Ghosted glowing surfaces (the lit screen) must dim with their opacity.
          s.m.emissiveIntensity = (s.emissiveIntensity ?? 1) * Math.min(1, v.opacity);
        }
      }
      const extraOn = this.extrasOn.has(def.id);
      for (const x of v.extras) x.visible = x.userData.extra === 'show' ? extraOn : !extraOn;
    }
    this.stage.invalidate();
  }

  private ghostOf(id: string): number {
    const v = this.views.get(id)!;
    const top = v.def.parent ?? id;
    if (this.inspect) return this.family(this.inspect, id) ? 1 : 0.08;
    if (this.focus) {
      if (this.family(this.focus, id) || this.focus === top) return 1;
      // Hide whatever sits on top of the focused part so the close-up is unobstructed.
      return this.coversOf(this.focus).has(top) ? 0 : 0.07;
    }
    if (this.xray && SHELL.has(top) && this.selected !== id) return 0.13;
    return 1;
  }

  /** All parts that (transitively) cover `id`. */
  private coversOf(id: string): Set<string> {
    const out = new Set<string>();
    const start = this.views.get(id)?.def;
    const stack = [...(start?.parent ? this.views.get(start.parent)!.def.blockedBy : []), ...(start?.blockedBy ?? [])];
    while (stack.length) {
      const b = stack.pop()!;
      if (out.has(b)) continue;
      out.add(b);
      stack.push(...(this.views.get(b)?.def.blockedBy ?? []));
    }
    return out;
  }

  /** Part id under a normalised device coordinate, ignoring hidden and ghosted parts. */
  pick(ndc: Vector2): string | null {
    this.raycaster.setFromCamera(ndc, this.stage.camera);
    const hits = this.raycaster.intersectObject(this.root, true);
    for (const h of hits) {
      let o: Object3D | null = h.object;
      let visible = true;
      let id: string | null = null;
      while (o) {
        if (!o.visible) visible = false;
        if (!id && o.userData.partId) id = o.userData.partId;
        o = o.parent;
      }
      if (!visible || !id) continue;
      if ((this.views.get(id)?.opacity ?? 0) < 0.3) continue;
      return id;
    }
    return null;
  }

  /** World-space bounds of a part, excluding decorative overlays. */
  bounds(id: string): Box3 {
    const v = this.views.get(id);
    const b = new Box3();
    if (!v) return b;
    v.obj.updateWorldMatrix(true, true);
    v.obj.traverse((o) => {
      if (o.userData.overlay) return;
      let p: Object3D | null = o;
      while (p && p !== v.obj) {
        if (p.userData.overlay) return;
        p = p.parent;
      }
      if ((o as Mesh).isMesh) b.expandByObject(o, false);
    });
    return b;
  }

  center(id: string): Vector3 {
    return this.bounds(id).getCenter(new Vector3());
  }
}
