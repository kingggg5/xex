import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, mkdtempSync, rmSync, copyFileSync, statSync, realpathSync, readdirSync, openSync, readSync, closeSync, renameSync, lstatSync } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseCityTraversal } from '../src/grounded-city.mjs';

const defaultClientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const defaultRoot = path.resolve(defaultClientRoot, '../..');
const CITY_PREFIX = 'assets/models/reference-city/r5/';

function readJsonBounded(filename, limit) {
  if (!statSync(filename).isFile() || statSync(filename).size > limit) throw new Error(`City selection JSON exceeds its byte budget: ${filename}`);
  return JSON.parse(readFileSync(filename, 'utf8'));
}
function inside(parent, child) {
  const relative = path.relative(parent, child);
  return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}
function digestFile(filename) {
  const digest = createHash('sha256');
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  const fd = openSync(filename, 'r');
  try { for (;;) { const count = readSync(fd, buffer, 0, buffer.length, null); if (!count) break; digest.update(buffer.subarray(0, count)); } }
  finally { closeSync(fd); }
  return digest.digest('hex');
}
function exactKeys(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !keys.includes(key))) throw new Error(`Invalid ${label} fields.`);
}
function canonical(value, roundNumbers = false) {
  if (typeof value === 'number') return roundNumbers ? Math.fround(value) : value;
  if (Array.isArray(value)) return value.map(item => canonical(item, roundNumbers));
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key], roundNumbers)]));
  return value;
}
function traversalOperation(value) {
  const pick = (object, names) => Object.fromEntries(names.map(name => [name, object?.[name]]));
  if (!value || !Array.isArray(value.surfaces) || !Array.isArray(value.blockers)) throw new Error('Selected city traversal lacks operational geometry.');
  return {
    ...pick(value, ['schema', 'units', 'city_bounds']),
    contract: pick(value.contract, ['max_step_m', 'max_slope_degrees', 'feet_offset_m', 'query_epsilon_m', 'max_movement_substep_m']),
    surfaces: value.surfaces.map(surface => pick(surface, ['id', 'kind', 'vertices', 'triangles'])),
    blockers: value.blockers.map(blocker => pick(blocker, ['id', 'kind', 'polygon_xz', 'y_min', 'y_max'])),
  };
}
function fingerprint(value, roundNumbers = false) { return createHash('sha256').update(JSON.stringify(canonical(value, roundNumbers))).digest('hex'); }
function fnv1a64(bytes) {
  let value = 14695981039346656037n;
  for (const byte of bytes) value = BigInt.asUintN(64, (value ^ BigInt(byte)) * 1099511628211n);
  return value.toString(16).padStart(16, '0');
}
function inspectSelectedRuntime(filename) {
  const fd = openSync(filename, 'r');
  let document;
  const bytes = statSync(filename).size;
  try {
    const header = Buffer.alloc(20);
    if (readSync(fd, header, 0, 20, 0) !== 20 || header.toString('ascii', 0, 4) !== 'glTF' || header.readUInt32LE(4) !== 2 || header.readUInt32LE(8) !== bytes || header.readUInt32LE(16) !== 0x4e4f534a) throw new Error('Selected runtime has an invalid GLB header.');
    const length = header.readUInt32LE(12);
    if (length > 16 * 1024 * 1024 || length > bytes - 20) throw new Error('Selected runtime JSON chunk exceeds its bounds.');
    const json = Buffer.alloc(length);
    if (readSync(fd, json, 0, length, 20) !== length) throw new Error('Selected runtime JSON chunk is truncated.');
    document = JSON.parse(json.toString('utf8').replace(/[\0 ]+$/u, ''));
  } finally { closeSync(fd); }
  const extensions = document.extensionsUsed ?? [];
  if (document.asset?.version !== '2.0' || !Array.isArray(extensions) || !extensions.includes('EXT_meshopt_compression') || !extensions.includes('KHR_texture_basisu')) throw new Error('Selected R5 runtime must retain glTF 2.0, Meshopt and KTX2/Basis compression.');
  const semantics = new Set(); let triangles = 0;
  for (const mesh of document.meshes ?? []) for (const primitive of mesh.primitives ?? []) {
    if ((primitive.mode ?? 4) !== 4) throw new Error('Selected city runtime contains a non-triangle primitive.');
    if (!Number.isSafeInteger(primitive.attributes?.POSITION)) throw new Error('Selected city runtime is missing its position accessor.');
    semantics.add(Object.keys(primitive.attributes ?? {}).sort().join(','));
    const accessor = document.accessors?.[primitive.indices ?? primitive.attributes?.POSITION];
    if (!accessor || !Number.isSafeInteger(accessor.count) || accessor.count <= 0 || accessor.count % 3 !== 0) throw new Error('Selected city runtime contains an invalid triangle accessor.');
    triangles += accessor.count / 3;
  }
  if (semantics.size !== 1 || !triangles || triangles > 900000) throw new Error('Selected city runtime violates its shared attributes or 900000-triangle budget.');
  return { bytes, triangles, attribute_semantics: [...semantics][0].split(','), mesh_count: document.meshes.length, material_count: document.materials?.length ?? 0, texture_count: document.textures?.length ?? 0 };
}

/** Inspect the selected immutable R5 package and its already-admitted field.
 * This neither generates geometry nor admits/rebuilds any gameplay content. */
export function selectActiveCityRevision(projectRoot = defaultRoot) {
  const root = realpathSync(projectRoot);
  const sourceDir = realpathSync(path.join(root, CITY_PREFIX));
  if (!inside(root, sourceDir)) throw new Error('R5 source directory escapes its project root.');
  const manifestPath = path.join(sourceDir, 'active-revision.json');
  if (!existsSync(manifestPath)) throw new Error('R5 active-revision.json is required; refusing fallback to an older canonical master.');
  if (!inside(sourceDir, realpathSync(manifestPath))) throw new Error('Active city revision pointer escapes its R5 directory.');
  const selected = readJsonBounded(manifestPath, 32768);
  exactKeys(selected, ['schema', 'revision', 'selected_utc', 'files', 'texture_policy', 'source_policy', 'retired_static_ids', 'replacement_gate_ids', 'native_status'], 'active city revision');
  if (selected.schema !== 'xexoria.city-active-revision/1' || typeof selected.revision !== 'string' || !/^r5-[a-z0-9][a-z0-9-]{0,95}$/u.test(selected.revision)) throw new Error('Unsupported active city revision schema or revision.');
  const keys = Object.keys(selected.files ?? {});
  const blendKeys = keys.filter(key => key.endsWith('.blend'));
  if (keys.length !== 4 || blendKeys.length !== 1 || !['city-source.glb', 'city-runtime.meshopt.glb', 'city-traversal-v1.json'].every(key => keys.includes(key))) throw new Error('Active city revision must pin one master, source GLB, runtime GLB and traversal.');
  const files = {};
  for (const key of keys) {
    const record = selected.files[key]; exactKeys(record, ['path', 'sha256'], `selected ${key}`);
    if (typeof record.path !== 'string' || !record.path.startsWith(CITY_PREFIX) || record.path.includes('\\') || record.path.split('/').some(part => !part || part === '.' || part === '..') || path.posix.basename(record.path) !== key || typeof record.sha256 !== 'string' || !/^[a-f0-9]{64}$/u.test(record.sha256)) throw new Error(`Invalid selected path or hash: ${key}`);
    const absolute = realpathSync(path.resolve(root, record.path));
    if (!inside(sourceDir, absolute) || !statSync(absolute).isFile() || statSync(absolute).size > 1024 * 1024 * 1024) throw new Error(`Selected city file escapes its source directory or byte budget: ${key}`);
    if (digestFile(absolute) !== record.sha256) throw new Error(`Selected city SHA256 mismatch: ${key}`);
    files[key] = { ...record, absolute };
  }
  const rawTraversal = readJsonBounded(files['city-traversal-v1.json'].absolute, 32 * 1024 * 1024);
  if (rawTraversal.source?.master_sha256 !== files[blendKeys[0]].sha256 || rawTraversal.source?.master_path !== files[blendKeys[0]].path) throw new Error('Selected traversal does not identify its pinned editable master.');
  const operation = traversalOperation(rawTraversal);
  const zones = readJsonBounded(path.join(root, 'content/source/zones.json'), 32 * 1024 * 1024);
  const matches = (zones.zones ?? []).filter(zone => zone.city_traversal && fingerprint(zone.city_traversal) === fingerprint(operation));
  if (matches.length !== 1) throw new Error('Selected city traversal is not already admitted in exactly one authored zone.');
  const zone = matches[0]; parseCityTraversal(operation, zone.half_extent);
  if (!Array.isArray(selected.retired_static_ids) || !Array.isArray(selected.replacement_gate_ids) || !selected.replacement_gate_ids.length) throw new Error('Selected city revision lacks gate replacement records.');
  if ((zone.static_colliders ?? []).some(collider => selected.retired_static_ids.includes(collider.id)) || selected.replacement_gate_ids.some(id => !operation.blockers.some(blocker => blocker.id === id))) throw new Error('Selected field still contains retired gate boxes or lacks replacement blockers.');
  const buildDir = path.join(root, 'content/build');
  const builds = readdirSync(buildDir, { withFileTypes: true }).filter(entry => entry.isDirectory());
  if (builds.length !== 1 || !/^[a-f0-9]{16}$/u.test(builds[0].name)) throw new Error('City selection needs exactly one current hashed content bundle.');
  const bundlePath = path.join(buildDir, builds[0].name, 'bundle.json');
  if (statSync(bundlePath).size > 32 * 1024 * 1024) throw new Error('Built content exceeds its byte budget.');
  const bundleBytes = readFileSync(bundlePath);
  if (fnv1a64(bundleBytes) !== builds[0].name) throw new Error('Built content bytes do not match their FNV hash directory.');
  const bundle = JSON.parse(bundleBytes.toString('utf8'));
  const builtZone = (bundle.zones ?? []).find(entry => entry.id === zone.id);
  // Rust serializes f32 coordinates; compare the same rounded values rather
  // than rejecting harmless decimal spelling changes from serde.
  if (!builtZone?.city_traversal || fingerprint(builtZone.city_traversal, true) !== fingerprint(operation, true)) throw new Error('Rebuild content: selected city art and hashed traversal disagree.');
  return { schema: 'xexoria.city-build-selection/1', revision: selected.revision, content_hash: builds[0].name, files, master_key: blendKeys[0], runtime: inspectSelectedRuntime(files['city-runtime.meshopt.glb'].absolute), policy: 'Reuse the verified compressed selected runtime; no Blender regeneration, source/candidate overwrite, manifest rewrite or new field admission.' };
}

export function buildCityAsset(args = process.argv.slice(2), projectRoot = defaultRoot) {
const root = path.resolve(projectRoot);
const clientRoot = path.join(root, 'apps/client');
let revisionFlags = 0;
for (let index = 0; index < args.length; index++) {
  if (args[index] === '--revision') { revisionFlags++; index++; if (revisionFlags > 1 || index >= args.length) throw new Error('Provide --revision once with an rN value.'); }
  else if (!['--pack-only', '--regenerate-source', '--check-selection'].includes(args[index])) throw new Error(`Unknown city build option: ${args[index]}`);
}
const revisionIndex = args.indexOf('--revision');
const revision = revisionIndex >= 0 ? args[revisionIndex + 1] : 'r5';
if (!/^r[1-9]\d*$/.test(revision)) throw new Error('City revision must use rN form, such as r1 or r2.');
if (revision === 'r5') {
  if (args.includes('--regenerate-source')) throw new Error('Cannot regenerate the immutable selected R5 source. Build and review a separate versioned candidate before changing active-revision.json.');
  const selection = selectActiveCityRevision(root);
  const selectedRuntime = selection.files['city-runtime.meshopt.glb'];
  const destination = path.join(clientRoot, 'src/assets/models/env_reference_city.glb');
  const summary = { ...selection, files: Object.fromEntries(Object.entries(selection.files).map(([key, { absolute, ...record }]) => [key, record])) };
  if (args.includes('--check-selection')) { console.log(JSON.stringify({ ...summary, action: 'checked-read-only' })); return summary; }
  if (!inside(realpathSync(clientRoot), realpathSync(path.dirname(destination))) || (existsSync(destination) && lstatSync(destination).isSymbolicLink())) throw new Error('Refusing an unexpected live city runtime destination.');
  if (!existsSync(destination) || digestFile(destination) !== selectedRuntime.sha256) {
    const pending = path.join(path.dirname(destination), `.env_reference_city.${randomUUID()}.pending.glb`);
    try { copyFileSync(selectedRuntime.absolute, pending); if (digestFile(pending) !== selectedRuntime.sha256) throw new Error('Selected runtime changed during staging.'); renameSync(pending, destination); }
    finally { rmSync(pending, { force: true }); }
  }
  console.log(JSON.stringify({ ...summary, action: 'selected-runtime-retained', destination: path.relative(root, destination).replaceAll('\\', '/') }));
  return summary;
}
if (args.includes('--check-selection')) throw new Error('--check-selection applies to the selected R5 package only.');
const sourceDir = path.join(root, 'assets/models/reference-city', revision);
const source = path.join(sourceDir, 'city-source.glb');
const runtime = path.join(clientRoot, 'src/assets/models/env_reference_city.glb');
const candidate = path.join(sourceDir, 'city-runtime.glb');
const cli = path.join(clientRoot, 'node_modules/@gltf-transform/cli/bin/cli.js');
const blender = process.env.BLENDER_BIN || 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const blenderScript = revision === 'r5'
  ? path.join('assets', 'blender', 'city_r5', 'build_city_r5.py')
  : path.join('assets', 'blender', 'build_reference_city_' + revision + '.py');
function run(executable, args, env = process.env) {
  const result = spawnSync(executable, args, {cwd: root, env, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Asset step failed with exit ${result.status}`);
}
const preservedMaster = path.join(sourceDir, 'reference_city.blend');
const regenerateSource = args.includes('--regenerate-source');
// Saved art is authoritative. Default builds must retain reviewed placement,
// UV, window, traversal and hollow-basin repairs instead of regenerating them.
if (!args.includes('--pack-only') && (revision !== 'r5' || !existsSync(preservedMaster) || regenerateSource)) {
  if (!existsSync(blender)) throw new Error('Set BLENDER_BIN to the installed Blender executable.');
  run(blender, ['--background', '--factory-startup', '--python-exit-code', '1', '--python', blenderScript]);
}
if (!existsSync(source)) throw new Error('Build the Blender source before packaging.');
const hasBasisTextures = ['r4', 'r5'].includes(revision);
const textureBuildRoot = hasBasisTextures ? mkdtempSync(path.join(tmpdir(), `aetherfield-city-${revision}-`)) : null;
let textureInput = source;
let geometryOptimization = null;
try {
  if (revision === 'r5') {
    const runtimeSource = path.join(textureBuildRoot, 'city-runtime-source.glb');
    const stats = path.join(textureBuildRoot, 'city-runtime-geometry.json');
    const master = path.join(sourceDir, 'reference_city.blend');
    const runtimeBuilder = path.join(root, 'assets/blender/city_r5/export_runtime_r5.py');
    if (!existsSync(blender)) throw new Error('Set BLENDER_BIN to the installed Blender executable for the R5 runtime geometry pass.');
    run(blender, ['--background', master, '--python-exit-code', '1', '--python', runtimeBuilder,
      '--', '--candidate', runtimeSource, '--stats', stats]);
    geometryOptimization = JSON.parse(readFileSync(stats, 'utf8'));
    textureInput = runtimeSource;
  }
  if (hasBasisTextures) {
    const ktxBin = process.env.KTX_SOFTWARE_BIN;
    if (!ktxBin) throw new Error(`Set KTX_SOFTWARE_BIN to the KTX-Software 4.4.2 bin directory for the ${revision} PBR texture build.`);
    const ktxExecutable = path.join(ktxBin, process.platform === 'win32' ? 'ktx.exe' : 'ktx');
    if (!existsSync(ktxExecutable)) throw new Error(`KTX CLI not found: ${ktxExecutable}`);
    const version = spawnSync(ktxExecutable, ['--version'], {encoding: 'utf8'});
    if (version.status !== 0 || !`${version.stdout}\n${version.stderr}`.includes('4.4.2')) {
      throw new Error(`The ${revision} texture recipe is pinned to KTX-Software 4.4.2.`);
    }
    const ktxEnv = {
      ...process.env,
      PATH: [ktxBin, process.env.PATH ?? ''].filter(Boolean).join(path.delimiter),
    };
    const uastc = path.join(textureBuildRoot, 'city-uastc.glb');
    const etc1s = path.join(textureBuildRoot, 'city-basis.glb');
    run(process.execPath, [cli, 'uastc', textureInput, uastc,
      '--slots', '{normalTexture,occlusionTexture,metallicRoughnessTexture}',
      '--level', '2', '--jobs', '2', '--rdo', '--rdo-lambda', '2', '--zstd', '9'], ktxEnv);
    run(process.execPath, [cli, 'etc1s', uastc, etc1s, '--slots', 'baseColor', '--quality', '180', '--jobs', '2'], ktxEnv);
    textureInput = etc1s;
  }
  run(process.execPath, [cli, 'meshopt', textureInput, candidate, '--level', 'medium']);
  run(process.execPath, [cli, 'validate', candidate]);
} finally {
  if (textureBuildRoot) {
    const resolvedTempRoot = path.resolve(textureBuildRoot);
    const resolvedTempParent = path.resolve(tmpdir());
    if (path.dirname(resolvedTempRoot) !== resolvedTempParent || !path.basename(resolvedTempRoot).startsWith(`aetherfield-city-${revision}-`)) {
      throw new Error('Refusing to remove an unexpected temporary city-build directory.');
    }
    rmSync(resolvedTempRoot, {recursive: true, force: true});
  }
}
const hash = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const runtimeBytes = readFileSync(candidate);
if (runtimeBytes.toString('ascii', 0, 4) !== 'glTF') throw new Error('Runtime city is not a GLB file.');
const jsonLength = runtimeBytes.readUInt32LE(12);
const runtimeDoc = JSON.parse(runtimeBytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
const semanticSets = new Set((runtimeDoc.meshes || []).flatMap(mesh => mesh.primitives.map(primitive => Object.keys(primitive.attributes).sort().join(','))));
if (semanticSets.size !== 1) throw new Error(`Runtime city meshes do not share vertex attributes: ${[...semanticSets].join(' | ')}`);
const runtimeTriangles = (runtimeDoc.meshes || []).reduce((meshTotal, mesh) => meshTotal + mesh.primitives.reduce((primitiveTotal, primitive) => {
  const accessorIndex = primitive.indices ?? primitive.attributes.POSITION;
  const accessor = runtimeDoc.accessors?.[accessorIndex];
  if (!accessor) throw new Error(`Runtime city primitive ${mesh.name ?? '(unnamed)'} has no measurable triangle accessor.`);
  return primitiveTotal + Math.floor(accessor.count / 3);
}, 0), 0);
if (!(runtimeDoc.extensionsUsed || []).includes('EXT_meshopt_compression')) throw new Error('Runtime city is missing EXT_meshopt_compression.');
if (hasBasisTextures && !(runtimeDoc.extensionsUsed || []).includes('KHR_texture_basisu')) throw new Error(`${revision.toUpperCase()} runtime city is missing KTX2/Basis Universal texture compression.`);
if (revision === 'r5') {
  if (!geometryOptimization?.candidate?.glb_accessor_triangles) throw new Error('R5 geometry optimization receipt is missing its measured triangle count.');
  if (runtimeTriangles !== geometryOptimization.candidate.glb_accessor_triangles) {
    throw new Error(`R5 runtime triangles ${runtimeTriangles} do not match Blender candidate ${geometryOptimization.candidate.glb_accessor_triangles}.`);
  }
  if (runtimeTriangles > geometryOptimization.candidate.limit_triangles) {
    throw new Error(`R5 runtime exceeds its triangle limit: ${runtimeTriangles} > ${geometryOptimization.candidate.limit_triangles}.`);
  }
  // The measured source candidate lives only in a task-local temp directory;
  // keep the portable manifest free of machine-specific paths.
  geometryOptimization.candidate.path = '<temporary>/city-runtime-source.glb';
  geometryOptimization.stats_path = undefined;
}
const manifestPath = path.join(sourceDir, 'manifest.json');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
manifest.revision = revision;
const refName = ['r4', 'r5'].includes(revision) ? 'city-layout-target-20260928.png' : 'ChatGPT Image Sep 27, 2026, 08_38_17 PM-1.png';
const ref = path.join(root, 'docs/ui', refName);
const master = path.join(sourceDir, 'reference_city.blend');
manifest.license = revision === 'r4'
  ? 'Project-authored geometry plus Poly Haven CC0 textures; source receipts in provenance.json. Reference pixels are not embedded.'
  : revision === 'r5'
    ? 'Project-authored city geometry and materials plus one Quaternius Fantasy Props MegaKit Stall_Cart_Empty mesh and its PBR textures, CC0 1.0; source receipt in assets/third-party/quaternius-fantasy-props-megakit/.'
    : 'Project-authored geometry and materials; no third-party meshes, textures, or embedded reference pixels.';
if (revision === 'r5') {
  manifest.third_party_assets = [{
    name: 'Quaternius Fantasy Props MegaKit — Stall_Cart_Empty',
    license: 'CC0 1.0 Universal',
    source_page: 'https://quaternius.com/packs/fantasypropsmegakit.html',
    download_page: 'https://quaternius.itch.io/fantasy-props-megakit',
    model: 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF/Stall_Cart_Empty.gltf',
    license_file: 'assets/third-party/quaternius-fantasy-props-megakit/License_Standard.txt',
  }];
}
manifest.reference_image_sha256 = hash(ref);
manifest.editable_master = {
  path: path.relative(root, master).replaceAll('\\', '/'),
  bytes: readFileSync(master).length,
  sha256: hash(master),
};
manifest.attribute_semantics = [...semanticSets][0].split(',');
manifest.runtime = {
  path: path.relative(root, runtime).replaceAll('\\', '/'),
  bytes: runtimeBytes.length,
  sha256: hash(candidate),
  compression: hasBasisTextures ? 'Meshopt medium + KTX2 ETC1S base color / UASTC normal, occlusion and metallic-roughness; KTX 4.4.2, glTF Transform 4.5.0' : 'EXT_meshopt_compression; glTF Transform 4.5.0, level medium',
  mesh_count: runtimeDoc.meshes.length,
  material_count: runtimeDoc.materials.length,
  texture_count: (runtimeDoc.textures || []).length,
};
if (geometryOptimization) {
  manifest.geometry_optimization = geometryOptimization;
  manifest.runtime.source_triangles = manifest.triangles;
  manifest.runtime.triangles = runtimeTriangles;
}
copyFileSync(candidate, runtime);
writeFileSync(manifestPath, JSON.stringify(manifest, null, 2)+'\n');
console.log(JSON.stringify(manifest.runtime));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) buildCityAsset();
