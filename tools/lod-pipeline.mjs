// LOD pipeline (Claude lane, 2026-10-01): drive gltf-transform + meshoptimizer instead of hand-decimating.
// Usage: node tools/lod-pipeline.mjs <input.glb> <outDir> [--ratios 1,0.4,0.15] [--errors 0,0.002,0.01] [--report out.json]
// Writes <name>_lod<N>.glb per ratio and a triangle report. Never overwrites the input.
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const requireClient = createRequire(path.join(root, 'apps/client/package.json'));
const load = async name => import(pathToFileURL(requireClient.resolve(name)).href);
const { NodeIO } = await load('@gltf-transform/core');
const { ALL_EXTENSIONS } = await load('@gltf-transform/extensions');
const { dedup, weld, simplify, prune, join, flatten, compactPrimitive } = await load('@gltf-transform/functions');
const { MeshoptSimplifier, MeshoptEncoder, MeshoptDecoder } = await load('meshoptimizer');

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 ? args[index + 1] : fallback;
};
const [input, outDir] = args;
if (!input || !outDir) throw new Error('usage: lod-pipeline.mjs <input.glb> <outDir> [--ratios ...] [--errors ...]');
const ratios = option('ratios', '1,0.4,0.15').split(',').map(Number);
const errors = option('errors', '0,0.002,0.01').split(',').map(Number);
if (ratios.length !== errors.length) throw new Error('--ratios and --errors need the same count');
// --hlod: flatten + join pieces that share a material before welding, and free borders, for far/HLOD levels only.
const hlod = args.includes('--hlod');
// --permissive: meshoptimizer v1 permissive mode (collapses across seams/non-manifold kit joins). Far LOD/HLOD only; verify visually.
const permissive = args.includes('--permissive');
const compress = !args.includes('--plain');
// --strip-textures: geometry-only review copies (e.g. Blender import, which cannot read KTX2/basisu).
const stripTextures = args.includes('--strip-textures');

await MeshoptSimplifier.ready;
await MeshoptEncoder.ready;
await MeshoptDecoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
});

function triangles(document) {
  let total = 0;
  for (const mesh of document.getRoot().listMeshes()) {
    for (const prim of mesh.listPrimitives()) {
      if (prim.getMode() !== 4) continue; // TRIANGLES only
      const indices = prim.getIndices();
      total += (indices ? indices.getCount() : prim.getAttribute('POSITION').getCount()) / 3;
    }
  }
  return Math.round(total);
}

function permissiveSimplify(document, ratio, error) {
  for (const mesh of document.getRoot().listMeshes()) for (const prim of mesh.listPrimitives()) {
    if (prim.getMode() !== 4) continue;
    const pos = prim.getAttribute('POSITION'); const n = pos.getCount();
    const P = new Float32Array(n * 3), el = [0, 0, 0];
    for (let i = 0; i < n; i++) { pos.getElement(i, el); P.set(el, i * 3); }
    const uv = prim.getAttribute('TEXCOORD_0'), nor = prim.getAttribute('NORMAL');
    const stride = (uv ? 2 : 0) + (nor ? 3 : 0);
    const A = new Float32Array(Math.max(1, n * stride)), u = [0, 0], v = [0, 0, 0];
    for (let i = 0; i < n; i++) {
      let o = i * stride;
      if (uv) { uv.getElement(i, u); A[o++] = u[0]; A[o++] = u[1]; }
      if (nor) { nor.getElement(i, v); A[o++] = v[0]; A[o++] = v[1]; A[o++] = v[2]; }
    }
    const weights = [...(uv ? [0.5, 0.5] : []), ...(nor ? [0.25, 0.25, 0.25] : [])];
    const acc = prim.getIndices();
    const I = acc ? Uint32Array.from(acc.getArray()) : Uint32Array.from({ length: n }, (_, i) => i);
    const target = Math.max(3, Math.floor(I.length * ratio / 3) * 3);
    const [out] = stride
      ? MeshoptSimplifier.simplifyWithAttributes(I, P, 3, A, stride, weights, null, target, error, ['Permissive'])
      : MeshoptSimplifier.simplify(I, P, 3, target, error, ['Permissive']);
    const indices = document.createAccessor().setType('SCALAR').setArray(out).setBuffer(document.getRoot().listBuffers()[0]);
    prim.setIndices(indices);
    compactPrimitive(prim);
  }
}

await mkdir(outDir, { recursive: true });
const base = path.basename(input, path.extname(input));
const source = await io.read(input);
const sourceTriangles = triangles(source);
const report = { tool: 'tools/lod-pipeline.mjs', input, mode: permissive ? 'permissive (meshoptimizer v1)' : hlod ? 'hlod (flatten+join, free borders)' : 'per-mesh (locked borders)', source_triangles: sourceTriangles, lods: [] };
for (const [level, ratio] of ratios.entries()) {
  const started = Date.now();
  const document = await io.read(input);
  if (ratio < 1) {
    // Weld first so the simplifier sees a connected surface; keep borders so modular kit seams stay closed.
    if (permissive) {
      await document.transform(dedup());
      permissiveSimplify(document, ratio, errors[level]);
      await document.transform(prune());
    } else {
      const steps = hlod ? [dedup(), flatten(), join({ keepNamed: false }), weld()] : [dedup(), weld()];
      await document.transform(
        ...steps,
        simplify({ simplifier: MeshoptSimplifier, ratio, error: errors[level], lockBorder: !hlod }),
        prune(),
      );
    }
  }
  const out = path.join(outDir, `${base}_lod${level}.glb`);
  if (!compress) for (const ext of document.getRoot().listExtensionsUsed()) if (ext.extensionName === 'EXT_meshopt_compression') ext.dispose();
  if (stripTextures) {
    for (const tex of document.getRoot().listTextures()) tex.dispose();
    for (const ext of document.getRoot().listExtensionsUsed()) if (ext.extensionName === 'KHR_texture_basisu') ext.dispose();
  }
  await io.write(out, document);
  const tris = triangles(document);
  report.lods.push({ level, ratio, error: errors[level], triangles: tris, kept: +(tris / sourceTriangles).toFixed(3),
    seconds: +((Date.now() - started) / 1000).toFixed(1), path: out });
  console.log(`LOD${level} ratio=${ratio} error=${errors[level]} -> ${tris.toLocaleString()} tris (${(100 * tris / sourceTriangles).toFixed(1)}%)`);
}
const reportPath = option('report', path.join(outDir, `${base}_lod-report.json`));
await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log('REPORT', reportPath);
