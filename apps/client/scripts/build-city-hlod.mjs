import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync, copyFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(clientRoot, '../..');
const cityDir = path.join(root, 'assets/models/reference-city/r5');
const master = path.join(cityDir, 'reference_city.blend');
const source = path.join(cityDir, 'city-source.glb');
const fullRuntime = path.join(cityDir, 'city-runtime.glb');
const exporter = path.join(root, 'assets/blender/city_r5/build_meadow_hlod_proxy_r5.py');
const output = path.join(clientRoot, 'src/assets/models/env_reference_city_hlod.glb');
const manifestPath = path.join(cityDir, 'meadow-hlod-manifest.json');
const cli = path.join(clientRoot, 'node_modules/@gltf-transform/cli/bin/cli.js');
const blender = process.env.BLENDER_BIN || 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const triangleLimit = 25_000;
const materialLimit = 8;
const byteLimit = 4 * 1024 * 1024;

function run(executable, args, env = process.env) {
  const result = spawnSync(executable, args, { cwd: root, env, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Meadow HLOD build step failed with exit ${result.status}`);
}

const sha256 = (value) => createHash('sha256').update(readFileSync(value)).digest('hex');

function readGlb(pathname) {
  const bytes = readFileSync(pathname);
  if (bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length) {
    throw new Error(`Invalid GLB header: ${pathname}`);
  }
  const jsonLength = bytes.readUInt32LE(12);
  const document = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
  let triangles = 0;
  for (const mesh of document.meshes ?? []) {
    for (const primitive of mesh.primitives ?? []) {
      if ((primitive.mode ?? 4) !== 4) continue;
      const accessorIndex = primitive.indices ?? primitive.attributes?.POSITION;
      const accessor = document.accessors?.[accessorIndex];
      if (!accessor) throw new Error(`Unmeasurable triangle accessor in ${pathname}`);
      triangles += Math.floor(accessor.count / 3);
    }
  }
  return { bytes, document, triangles };
}

for (const pathToCheck of [master, source, fullRuntime, exporter, cli, blender]) {
  if (!existsSync(pathToCheck)) throw new Error(`Required city HLOD input is missing: ${pathToCheck}`);
}

const sourceHashes = { master: sha256(master), source: sha256(source), fullRuntime: sha256(fullRuntime) };
const temporaryRoot = mkdtempSync(path.join(tmpdir(), 'aetherfield-meadow-hlod-'));
const candidate = path.join(temporaryRoot, 'city-meadow-hlod-source.glb');
const blenderStats = path.join(temporaryRoot, 'city-meadow-hlod-source.stats.json');
const optimized = path.join(temporaryRoot, 'city-meadow-hlod-meshopt.glb');
try {
  run(blender, ['--background', master, '--python-exit-code', '1', '--python', exporter,
    '--', '--candidate', candidate, '--stats', blenderStats]);
  run(process.execPath, [cli, 'meshopt', candidate, optimized, '--level', 'medium']);
  run(process.execPath, [cli, 'validate', optimized]);

  const runtime = readGlb(optimized);
  const materialCount = runtime.document.materials?.length ?? 0;
  const imageCount = runtime.document.images?.length ?? 0;
  const extensions = runtime.document.extensionsUsed ?? [];
  if (runtime.triangles > triangleLimit) throw new Error(`HLOD exceeds triangle cap: ${runtime.triangles} > ${triangleLimit}`);
  if (materialCount > materialLimit) throw new Error(`HLOD exceeds material cap: ${materialCount} > ${materialLimit}`);
  if (imageCount !== 0) throw new Error(`Texture-free HLOD contains ${imageCount} images.`);
  if (!extensions.includes('EXT_meshopt_compression')) throw new Error('HLOD is missing EXT_meshopt_compression.');
  if (runtime.bytes.length > byteLimit) throw new Error(`HLOD exceeds transfer cap: ${runtime.bytes.length} > ${byteLimit} bytes.`);

  const geometry = JSON.parse(readFileSync(blenderStats, 'utf8'));
  if (runtime.triangles !== geometry.candidate.triangles) {
    throw new Error(`Blender measured ${geometry.candidate.triangles} triangles; packed GLB contains ${runtime.triangles}.`);
  }
  for (const [key, original] of Object.entries({ master, source, fullRuntime })) {
    if (sha256(original) !== sourceHashes[key]) throw new Error(`Protected R5 ${key} changed during HLOD packaging.`);
  }

  copyFileSync(optimized, output);
  const manifest = {
    schema: 'aetherfield.meadow-city-hlod-package/1',
    source: {
      terrainMeshes: geometry.source.terrain_meshes.length,
      sourceTerrainTriangles: geometry.source.terrain_meshes.reduce((sum, mesh) => sum + mesh.source_triangles, 0),
      proxyMeshes: geometry.source.proxy_mesh_count,
      proxyTriangles: geometry.source.proxy_triangle_count,
      masterSha256: sourceHashes.master,
      citySourceSha256: sourceHashes.source,
      fullRuntimeSha256: sourceHashes.fullRuntime,
    },
    runtime: {
      path: path.relative(root, output).replaceAll('\\', '/'),
      bytes: runtime.bytes.length,
      sha256: sha256(output),
      triangles: runtime.triangles,
      meshes: runtime.document.meshes?.length ?? 0,
      materials: materialCount,
      embeddedImages: imageCount,
      compression: 'Meshopt medium; no embedded textures; eight-color vertex palette',
    },
    limits: { triangles: triangleLimit, materials: materialLimit, bytes: byteLimit },
    preservedR5Master: true,
  };
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  console.log(JSON.stringify({ result: 'PASS', ...manifest.runtime, manifest: path.relative(root, manifestPath) }, null, 2));
} finally {
  const resolvedTemporaryRoot = path.resolve(temporaryRoot);
  const resolvedTemporaryParent = path.resolve(tmpdir());
  if (path.dirname(resolvedTemporaryRoot) !== resolvedTemporaryParent || !path.basename(resolvedTemporaryRoot).startsWith('aetherfield-meadow-hlod-')) {
    throw new Error('Refusing to remove an unexpected temporary HLOD build directory.');
  }
  rmSync(resolvedTemporaryRoot, { recursive: true, force: true });
}
