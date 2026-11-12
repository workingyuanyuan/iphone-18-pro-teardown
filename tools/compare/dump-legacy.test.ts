/**
 * One-off baseline export: dumps the procedural three.js model's triangles per part id so the
 * compare tool can score the "before" state. Run with:
 *   LEGACY_BUILD=../../src/data/phones/iphone-18-pro/build.ts npx vitest run --root . tools/compare/dump-legacy.test.ts
 * (kept for reference after build.ts was replaced by the GLB loader; needs the old build.ts from git history)
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { test } from 'vitest';
import { Vector3, type Mesh, type Object3D } from 'three';

const ctx = new Proxy({}, { get: () => () => ({ addColorStop() {}, width: 0, data: [] }), set: () => true });
(globalThis as Record<string, unknown>).document = {
  createElement: () => ({ width: 0, height: 0, getContext: () => ctx, style: {} }),
};

test.skipIf(!process.env.LEGACY_BUILD)('dump legacy geometry', async () => {
  const mod = await import(/* @vite-ignore */ process.env.LEGACY_BUILD ?? '../../src/data/phones/iphone-18-pro/build.ts');
  const parts: Map<string, Object3D> = mod.buildIphone18Pro();
  const out: Record<string, { name: string; extra?: string; overlay?: boolean; tris: number[] }[]> = {};
  const v = new Vector3();
  for (const [id, root] of parts) {
    root.updateMatrixWorld(true);
    out[id] = [];
    root.traverse((o) => {
      const m = o as Mesh;
      if (!m.isMesh) return;
      let extra: string | undefined, overlay = false;
      for (let p: Object3D | null = o; p; p = p.parent) {
        extra ??= p.userData.extra;
        overlay ||= !!p.userData.overlay;
      }
      const g = m.geometry.index ? m.geometry.toNonIndexed() : m.geometry;
      const pos = g.getAttribute('position');
      const tris: number[] = [];
      for (let i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld);
        tris.push(+v.x.toFixed(3), +v.y.toFixed(3), +v.z.toFixed(3));
      }
      const mat = Array.isArray(m.material) ? m.material[0] : m.material;
      out[id].push({ name: mat.name || mat.type, extra, overlay, tris });
    });
  }
  mkdirSync('refs/out', { recursive: true });
  writeFileSync('refs/out/legacy-parts.json', JSON.stringify(out));
});
