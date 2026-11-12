import { type BufferAttribute, type Material, type Mesh, type Object3D } from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js';

/**
 * Loads a phone model built by tools/blender (see tools/README.md).
 *
 * Contract of the GLB:
 *  - coordinates are phone-local millimetres, +z = screen (exported without the glTF Y-up flip);
 *  - every top-level node is one part and carries `extras.partId`; it has an identity transform;
 *  - meshes below it carry `extras.extra` ('show' | 'hide') and `extras.overlay` like the old
 *    procedural builder's userData, so the viewer needs no special cases;
 *  - material *names* are keys; real materials are created here per part (parts fade and tint
 *    independently, so materials must never be shared between parts).
 */
export type MaterialFactory = (key: string) => Material;

export class ModelLoadError extends Error {}

export async function loadPhoneGlb(
  url: string,
  partIds: string[],
  materialFor: MaterialFactory,
  opts: { onProgress?: (fraction: number) => void; before?: Promise<unknown> } = {},
): Promise<Map<string, Object3D>> {
  const { onProgress, before } = opts;
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  let gltf;
  try {
    gltf = await loader.loadAsync(url, (e) => {
      if (onProgress && e.lengthComputable && e.total > 0) onProgress(Math.min(e.loaded / e.total, 1));
    });
  } catch (err) {
    throw new ModelLoadError(`無法載入 3D 模型（${url}）`, { cause: err });
  }
  // Canvas textures draw text once, so wait for whatever the caller needs first (web fonts).
  await before?.catch(() => undefined);
  const parts = new Map<string, Object3D>();
  const flipped = new Set<BufferAttribute>(); // meshopt/dedup can share one UV accessor between meshes
  for (const node of [...gltf.scene.children]) {
    const id = node.userData.partId as string | undefined;
    if (!id) continue;
    node.removeFromParent();
    const mats = new Map<string, Material>();
    node.traverse((o) => {
      const mesh = o as Mesh;
      if (!mesh.isMesh) return;
      const src = mesh.material as Material;
      let mat = mats.get(src.name);
      if (!mat) mats.set(src.name, (mat = materialFor(src.name)));
      src.dispose();
      mesh.material = mat;
      // glTF stores V top-down; our canvas textures are drawn bottom-up like the old builder's.
      const uv = mesh.geometry.getAttribute('uv') as BufferAttribute | undefined;
      if (uv && !flipped.has(uv)) {
        flipped.add(uv);
        for (let i = 0; i < uv.count; i++) uv.setY(i, 1 - uv.getY(i));
        uv.needsUpdate = true;
      }
    });
    parts.set(id, node);
  }
  const missing = partIds.filter((id) => !parts.has(id));
  if (missing.length) throw new ModelLoadError(`3D 模型缺少零件：${missing.join('、')}`);
  return parts;
}
