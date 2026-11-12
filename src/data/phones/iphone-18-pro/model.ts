import { MeshPhysicalMaterial, MeshStandardMaterial, type Material, type Object3D } from 'three';
import { M } from '../../../builders/materials';
import { loadPhoneGlb } from '../../../engine/glb';
import { parts } from './parts';

/**
 * iPhone 18 Pro geometry: built offline with Blender from the measurements in
 * tools/measure/models/iphone-18-pro (see docs/measurements.md), shipped as one GLB.
 * Body size is Apple's published drawing value.
 */
export const W = 71.85;
export const H = 150.01;
export const D = 8.75;

export const MODEL_URL = `${import.meta.env.BASE_URL}models/iphone-18-pro.glb`;

/**
 * Plain-coloured surfaces share three material classes and take their colour from vertex colours
 * (keeps draw calls low); everything else is a named material with its own shader or texture.
 */
const FACTORIES: Record<string, () => Material> = {
  'v.metal': () => new MeshStandardMaterial({ vertexColors: true, metalness: 0.9, roughness: 0.34 }),
  'v.matte': () => new MeshStandardMaterial({ vertexColors: true, metalness: 0.15, roughness: 0.68 }),
  'v.glass': () => new MeshPhysicalMaterial({ vertexColors: true, metalness: 0.3, roughness: 0.04, clearcoat: 1 }),
  backGlass: M.backGlass,
  coverGlass: M.coverGlass,
  screen: M.screen,
  coil: M.coil,
  pcb: M.pcb,
  battery: M.battery,
  dots: M.dots,
  'overlay.magsafe': () => M.overlay('#b030ff'),
  'chip.soc': () => M.chip(['A20 PRO', 'APL1xxx'], '#b9bcc0', 'rgba(50,50,55,0.8)'),
  'chip.socDie': () => M.chip(['A20 Pro', 'SoC']),
  'chip.ram': () => M.chip(['RAM'], '#1d1d22'),
  'chip.modem': () => M.chip(['C2', 'APPLE']),
  'chip.n1': () => M.chip(['N1'], '#b9bcc0', 'rgba(50,50,55,0.8)'),
  'chip.nand': () => M.chip(['SanDisk', '256GB TLC']),
};

export function materialFor(key: string): Material {
  const make = FACTORIES[key];
  if (!make) throw new Error(`unknown model material "${key}"`);
  const m = make();
  m.name = key;
  return m;
}

export const MATERIAL_KEYS = Object.keys(FACTORIES);

export function loadIphone18Pro(opts: { onProgress?: (fraction: number) => void; before?: Promise<unknown> } = {}): Promise<Map<string, Object3D>> {
  return loadPhoneGlb(
    MODEL_URL,
    parts.map((p) => p.id),
    materialFor,
    opts,
  );
}
