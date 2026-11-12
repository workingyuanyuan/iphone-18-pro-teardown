// Confirms that meshopt compression / quantisation did not move geometry: compares the world-space
// bounding box of every mesh in the shipped GLB with the same mesh in the uncompressed build.
//   node tools/compare/check-shipped.mjs [raw.glb] [shipped.glb]
import { NodeIO, getBounds } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';

await MeshoptDecoder.ready;
const [rawPath = 'public/models/iphone-18-pro.raw.glb', shipPath = 'public/models/iphone-18-pro.glb'] = process.argv.slice(2);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
const boxes = async (p) => {
  const doc = await io.read(p);
  const out = new Map();
  for (const n of doc.getRoot().listNodes()) if (n.getMesh()) out.set(n.getName(), getBounds(n));
  return out;
};
const [a, b] = [await boxes(rawPath), await boxes(shipPath)];
let worst = 0;
let worstName = '';
for (const [name, ba] of a) {
  const bb = b.get(name);
  if (!bb) throw new Error(`mesh ${name} missing from shipped GLB`);
  for (const k of ['min', 'max'])
    for (let i = 0; i < 3; i++) {
      const d = Math.abs(ba[k][i] - bb[k][i]);
      if (d > worst) [worst, worstName] = [d, name];
    }
}
console.log(`${a.size} meshes; largest bounding-box shift after compression: ${worst.toFixed(4)} mm (${worstName})`);
if (worst > 0.05) process.exit(1);
