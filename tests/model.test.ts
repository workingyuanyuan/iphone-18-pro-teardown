import { readFileSync, statSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parts } from '../src/data/phones/iphone-18-pro/parts';

/**
 * Contract between the Blender build (tools/blender) and the viewer, checked on the shipped GLB:
 * part ids, easter-egg toggles, material keys, and the performance budget.
 */
const GLB = 'public/models/iphone-18-pro.glb';
const BUDGET = { bytes: 1_500_000, triangles: 100_000, drawCalls: 60 };

interface Node {
  name?: string;
  mesh?: number;
  children?: number[];
  extras?: Record<string, unknown>;
  translation?: number[];
  rotation?: number[];
  scale?: number[];
  matrix?: number[];
}

function readGlb(path: string) {
  const buf = readFileSync(path);
  expect(buf.readUInt32LE(0)).toBe(0x46546c67); // "glTF"
  const jsonLen = buf.readUInt32LE(12);
  return JSON.parse(buf.subarray(20, 20 + jsonLen).toString('utf8')) as {
    nodes: Node[];
    scenes: { nodes: number[] }[];
    meshes: { primitives: { material: number; indices: number; attributes: Record<string, number> }[] }[];
    materials: { name: string }[];
    accessors: { count: number }[];
    extensionsUsed?: string[];
  };
}

describe('iphone-18-pro.glb', () => {
  const gltf = readGlb(GLB);
  const roots = gltf.scenes[0].nodes.map((i) => gltf.nodes[i]);
  const byId = new Map(roots.map((n) => [n.extras?.partId as string, n]));
  const meshesOf = (n: Node): Node[] => (n.children ?? []).map((i) => gltf.nodes[i]).filter((c) => c.mesh !== undefined);

  it('has exactly one identity root node per part id', () => {
    const ids = roots.map((n) => n.extras?.partId as string);
    expect(ids.length).toBe(new Set(ids).size); // no duplicate roots that the loader would silently overwrite
    expect(ids.sort()).toEqual(parts.map((p) => p.id).sort());
    for (const n of roots) {
      // the viewer overwrites part-root positions, so roots must not carry a transform of their own
      expect(n.matrix ?? n.translation ?? n.rotation ?? n.scale, n.name).toBeUndefined();
      expect(meshesOf(n).length, n.name).toBeGreaterThan(0);
    }
  });

  it('gives every part with an easter egg geometry that toggles', () => {
    const want: Record<string, string[]> = { magsafe: ['show', 'hide'], dotProjector: ['show'], peelSticker: ['hide'], wmcm: ['show', 'hide'] };
    for (const p of parts.filter((q) => q.extra)) {
      const tags = meshesOf(byId.get(p.id)!).map((m) => m.extras?.extra);
      for (const t of want[p.extra!]) expect(tags, p.id).toContain(t);
    }
  });

  it('marks purely decorative overlays so they are not pickable', () => {
    const overlays = roots.flatMap(meshesOf).filter((m) => m.extras?.overlay);
    expect(overlays.map((m) => m.name).sort()).toEqual(['backGlass/overlay.magsafe/show/overlay', 'faceId/dots/show/overlay']);
  });

  it('only uses material keys the web side knows', async () => {
    (globalThis as Record<string, unknown>).document ??= { createElement: () => ({ getContext: () => new Proxy({}, { get: () => () => ({ addColorStop() {} }), set: () => true }), style: {} }) };
    const { MATERIAL_KEYS } = await import('../src/data/phones/iphone-18-pro/model');
    for (const m of gltf.materials) expect(MATERIAL_KEYS, m.name).toContain(m.name);
  });

  it('keeps every material key distinct through optimisation', () => {
    const matOf = (id: string) => meshesOf(byId.get(id)!).flatMap((m) => gltf.meshes[m.mesh!].primitives.map((p) => gltf.materials[p.material].name));
    expect(new Set(gltf.materials.map((m) => m.name)).size).toBe(gltf.materials.length);
    expect(matOf('backGlass')).toEqual(expect.arrayContaining(['backGlass', 'coil', 'overlay.magsafe']));
    expect(matOf('display')).toEqual(expect.arrayContaining(['coverGlass', 'screen']));
    expect(matOf('battery')).toContain('battery');
    expect(matOf('apBoard')).toContain('pcb');
    expect(matOf('soc')).toEqual(expect.arrayContaining(['chip.soc', 'chip.socDie', 'chip.ram']));
    for (const id of ['modem', 'n1', 'nand']) expect(matOf(id)).toEqual([`chip.${id}`]);
  });

  it('is meshopt-compressed and within the performance budget', () => {
    expect(gltf.extensionsUsed).toContain('EXT_meshopt_compression');
    expect(statSync(GLB).size).toBeLessThanOrEqual(BUDGET.bytes);
    const prims = gltf.meshes.flatMap((m) => m.primitives);
    const triangles = prims.reduce((s, p) => s + gltf.accessors[p.indices].count / 3, 0);
    expect(triangles).toBeLessThanOrEqual(BUDGET.triangles);
    // one primitive = one draw call; meshes that only appear with an easter egg on are not drawn by default
    const visible = roots.flatMap(meshesOf).filter((m) => m.extras?.extra !== 'show');
    const draws = visible.reduce((s, m) => s + gltf.meshes[m.mesh!].primitives.length, 0);
    expect(draws).toBeLessThanOrEqual(BUDGET.drawCalls);
  });
});
