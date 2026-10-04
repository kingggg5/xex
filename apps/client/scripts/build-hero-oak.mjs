import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const client = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(client, '../..');
const kit = path.join(root, 'assets/models/hero-oak/v1');
const cli = path.join(client, 'node_modules/@gltf-transform/cli/bin/cli.js');
const ktxDir = process.env.KTX_SOFTWARE_BIN || path.join(root, '.harness/.cache/toolchains/ktx-4.4.2/portable/bin');
const ktx = path.join(ktxDir, process.platform === 'win32' ? 'ktx.exe' : 'ktx');
const hash = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const run = (executable, args) => {
  const result = spawnSync(executable, args, { cwd: root, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Oak build step failed: ${path.basename(executable)} (${result.status})`);
};
if (!existsSync(ktx)) throw new Error('Set KTX_SOFTWARE_BIN to KTX-Software 4.4.2 bin.');
const version = spawnSync(ktx, ['--version'], { encoding: 'utf8' });
if (version.status !== 0 || !version.stdout.includes('4.4.2')) throw new Error('Oak texture recipe requires KTX 4.4.2.');
const source = path.join(kit, 'source.glb');
if (hash(source) !== 'e94771196fb9839f4551faf9d344883971b037fa27516a197b6a2edfea79b2da') {
  throw new Error('Oak source differs from the reviewed Tripo export. Inspect the new source before packaging.');
}
if (!process.argv.includes('--pack-only')) {
  run(process.env.BLENDER_BIN || 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe',
    ['--background', '--factory-startup', '--python-exit-code', '1', '--python',
      path.join(root, 'assets/blender/world/prepare_hero_oak.py'), '--', '--source', source, '--output', kit]);
}
const geometry = JSON.parse(readFileSync(path.join(kit, 'geometry-receipt.json'), 'utf8'));
run(process.env.PYTHON_BIN || 'python', ['-B', path.join(root, 'tools/verify_hero_oak.py')]);
const footprintPath = path.join(root, 'planning/evidence/hero-oak-footprint-build-20260930.json');
const footprint = JSON.parse(readFileSync(footprintPath, 'utf8'));
if (footprint.status !== 'PASS' || footprint.lods.length !== 3) throw new Error('Oak footprint validation failed.');
const texture = path.join(client, 'src/assets/world/hero_oak_albedo.ktx2');
run(ktx, ['create', '--format', 'R8G8B8A8_SRGB', '--assign-tf', 'srgb', '--encode', 'basis-lz',
  '--qlevel', '200', '--clevel', '2', '--threads', '2', '--generate-mipmap',
  path.join(kit, 'hero_oak_albedo_2048.png'), texture]);
run(ktx, ['validate', '--gltf-basisu', texture]);
const lods = [];
for (const lod of geometry.lods) {
  const raw = path.join(kit, lod.path);
  if (footprint.lods[lod.lod].sha256 !== hash(raw)) throw new Error('Stale oak footprint proof.');
  const runtime = path.join(client, `src/assets/world/hero_oak_lod${lod.lod}.meshopt.glb`);
  run(process.execPath, [cli, 'meshopt', raw, runtime, '--level', 'medium']);
  run(process.execPath, [cli, 'validate', runtime]);
  const bytes = readFileSync(runtime);
  if (bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(8) !== bytes.length) throw new Error('Invalid oak GLB.');
  const doc = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString('utf8'));
  const primitives = (doc.meshes ?? []).flatMap(mesh => mesh.primitives);
  const triangles = primitives.reduce((n, primitive) => n + doc.accessors[primitive.indices].count / 3, 0);
  if (triangles !== lod.triangles || triangles > 12000 || bytes.length > 512 * 1024
      || doc.images?.length || doc.materials?.length || !doc.extensionsRequired?.includes('EXT_meshopt_compression')) {
    throw new Error(`Oak LOD ${lod.lod} failed the geometry-only runtime policy.`);
  }
  lods.push({ lod: lod.lod, triangles, source_sha256: hash(raw),
    path: path.relative(root, runtime).replaceAll('\\', '/'), bytes: bytes.length, sha256: hash(runtime) });
}
const ktxBytes = readFileSync(texture);
if (ktxBytes.readUInt32LE(20) !== 2048 || ktxBytes.readUInt32LE(24) !== 2048
    || ktxBytes.readUInt32LE(40) !== 12 || ktxBytes.length > 2 * 1024 * 1024) {
  throw new Error('Oak texture does not satisfy the 2048px/12-mip/2MiB policy.');
}
const manifest = {
  schema: 'aetherfield.hero-oak-package/1',
  source: { path: 'assets/models/hero-oak/v1/source.glb', sha256: hash(source),
    provider: 'Tripo Studio', model: 'Smart Mesh P2.0', job_id: '6a99dbb8-6e74-464c-846c-384db112d414',
    requested_quads: 6000, observed_editor_faces: 7815, observed_editor_vertices: 6049,
    privacy: 'Private', credits_before: 25190, credits_after: 25160,
    geometry_credits: 0, geometry_trial_used: true, texture_credits: 30,
    reference: 'assets/models/hero-oak/v1/reference.png', reference_sha256: hash(path.join(kit, 'reference.png')),
    image_prompt_call_id: 'call_Odo4oFCWNa37f9HPyfQCClJA',
    prompt_record: 'assets/models/world-v2/image-generation-provenance.json' },
  license: { id: 'LicenseRef-Tripo-Paid-Generated', account_basis: 'User reports Pro; private generation and paid controls observed at creation.',
    guide: 'https://www.tripo3d.ai/help/privacy-policy/how-to-use-tripo-models-commercially', checked_on: '2026-09-30',
    input: 'Original host-generated reference; not a named-game model or downloaded game texture.' },
  editable_master: 'assets/models/hero-oak/v1/hero_oak.blend',
  normalization: geometry, lods,
  texture: { path: path.relative(root, texture).replaceAll('\\', '/'), width: 2048, height: 2048,
    levels: 12, codec: 'BasisLZ/ETC1S', color_space: 'sRGB', bytes: ktxBytes.length, sha256: hash(texture) },
  placement_ids: ['sunmeadow_pine_west_mid', 'sunmeadow_oak_east'],
  coverage_thresholds: { medium: 0.035, distant: 0.006 },
  footprint_evidence: 'planning/evidence/hero-oak-footprint-build-20260930.json',
  footprint_evidence_sha256: hash(footprintPath),
  footprint_status: footprint.status,
  art_quality_gate: { status: 'REJECTED_FOR_DEFAULT_GAME',
    evidence: 'planning/evidence/nature-art-review-20260930.json',
    reason: 'Folded foliage masses, leaf plates, truncated roots and bark distortion remain below the reference.',
    use: 'Development-only heroOakPreview=1 comparison; default cells retain authored trees.' },
  limitations: ['GPU import and two-backend motion verification are pending browser reconnection.',
    'No measured Android/iOS frame-time or memory result.', 'Three mesh LODs share one resident texture; mip filtering is not texture residency streaming.',
    'Source has baked texture detail and no authored normal/ORM maps or skeletal rig.',
    'Wind is procedural vertex deformation, not a physical tree simulation.']
};
writeFileSync(path.join(kit, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ status: 'PASS', lods, texture_bytes: ktxBytes.length }));
