import {
  AdditiveBlending,
  Color,
  DoubleSide,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  type Texture,
} from 'three';
import * as T from './textures';

/**
 * Material factory. Every call returns a NEW material so each part owns its materials
 * (highlight / ghost effects mutate them per part). Textures are shared and cached.
 */
const cache = new Map<string, Texture>();
function cached(key: string, make: () => Texture): Texture {
  let t = cache.get(key);
  if (!t) cache.set(key, (t = make()));
  return t;
}

const std = (o: ConstructorParameters<typeof MeshStandardMaterial>[0]) => new MeshStandardMaterial(o);

export const M = {
  /** Anodised burgundy aluminium (video unit colour). */
  frame: () => std({ color: '#5e1f2c', metalness: 0.85, roughness: 0.38 }),
  frameInner: () => std({ color: '#4a1822', metalness: 0.7, roughness: 0.55 }),
  /** Bright CNC chamfer / bosses. */
  aluminum: () => std({ color: '#c8c4c4', metalness: 1, roughness: 0.3 }),
  steel: () => std({ color: '#c9cbcf', metalness: 1, roughness: 0.28, map: cached('brushed', () => T.brushed()) }),
  steelDark: () => std({ color: '#8c8f94', metalness: 1, roughness: 0.4 }),
  /** Frosted ceramic-shield back glass, tinted like the frame. */
  backGlass: () =>
    new MeshPhysicalMaterial({ color: '#4a1621', metalness: 0.15, roughness: 0.62, clearcoat: 0.35, clearcoatRoughness: 0.6 }),
  coverGlass: () =>
    new MeshPhysicalMaterial({ color: '#050506', metalness: 0, roughness: 0.04, clearcoat: 1, clearcoatRoughness: 0.03, reflectivity: 0.6 }),
  screen: () =>
    std({
      color: '#000000',
      emissive: new Color('#ffffff'),
      emissiveMap: cached('wallpaper', () => T.wallpaper()),
      emissiveIntensity: 0.85,
      roughness: 0.25,
      metalness: 0,
    }),
  oledBlack: () => std({ color: '#0d0d10', roughness: 0.6, metalness: 0.2 }),
  copper: () => std({ color: '#c47a43', metalness: 1, roughness: 0.32 }),
  coil: () => std({ color: '#ffffff', metalness: 0.85, roughness: 0.35, map: cached('coilRadial', () => T.coilRadial()) }),
  magnet: () => std({ color: '#7d7f84', metalness: 0.9, roughness: 0.45 }),
  graphite: () => std({ color: '#1b1b1e', metalness: 0.15, roughness: 0.85 }),
  graphiteGray: () => std({ color: '#55575c', metalness: 0.4, roughness: 0.7 }),
  pcb: () => std({ color: '#ffffff', map: cached('pcb', () => T.pcb()), metalness: 0.2, roughness: 0.6 }),
  pcbEdge: () => std({ color: '#b78a3c', metalness: 0.8, roughness: 0.4 }),
  chip: (lines: string[], bg?: string, fg?: string) =>
    std({ color: '#ffffff', map: T.chipLabel(lines, bg, fg), metalness: 0.2, roughness: 0.55 }),
  /** Package that only needs a dark epoxy top. */
  epoxy: () => std({ color: '#141416', metalness: 0.2, roughness: 0.6 }),
  smd: () => std({ color: '#b39360', metalness: 0.4, roughness: 0.5 }),
  smdDark: () => std({ color: '#2b2b2e', metalness: 0.3, roughness: 0.6 }),
  battery: () => std({ color: '#ffffff', map: cached('battery', () => T.batteryLabel()), metalness: 0.85, roughness: 0.35 }),
  flex: () => std({ color: '#b46a1c', metalness: 0.3, roughness: 0.5 }),
  flexBlack: () => std({ color: '#1e1e20', metalness: 0.2, roughness: 0.6 }),
  lensGlass: () =>
    new MeshPhysicalMaterial({ color: '#07080b', metalness: 0.2, roughness: 0.02, clearcoat: 1, clearcoatRoughness: 0, iridescence: 0.6, iridescenceIOR: 1.5 }),
  lensRing: () => std({ color: '#9a9ca2', metalness: 1, roughness: 0.22 }),
  sapphire: () => new MeshPhysicalMaterial({ color: '#141418', metalness: 0.4, roughness: 0.05, clearcoat: 1 }),
  plasticBlack: () => std({ color: '#151517', metalness: 0.05, roughness: 0.7 }),
  rubber: () => std({ color: '#262628', metalness: 0, roughness: 0.9 }),
  foam: () => std({ color: '#2a2a2c', metalness: 0, roughness: 1 }),
  membrane: () => std({ color: '#e8e8e4', metalness: 0, roughness: 0.9 }),
  grille: () => std({ color: '#ffffff', map: cached('grille', () => T.grille()), metalness: 0.6, roughness: 0.5 }),
  usbRed: () => std({ color: '#4d1822', metalness: 0.1, roughness: 0.6 }),
  gold: () => std({ color: '#d4af37', metalness: 1, roughness: 0.25 }),
  flash: () => new MeshPhysicalMaterial({ color: '#e9e4d6', metalness: 0, roughness: 0.3, clearcoat: 1, emissive: '#3a3528' }),
  dots: () =>
    new MeshBasicMaterial({
      map: cached('dots', () => T.dotPattern()),
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
      side: DoubleSide,
    }),
  /** Purple overlay showing the MagSafe coil footprint (easter egg, as in the video graphic). */
  overlay: (color: string) =>
    new MeshBasicMaterial({ color, transparent: true, opacity: 0.45, depthWrite: false, side: DoubleSide }),
};

export const shadowTexture = () => cached('shadow', () => T.shadowBlob());
