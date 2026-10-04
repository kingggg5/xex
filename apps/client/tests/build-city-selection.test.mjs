import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync, renameSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildCityAsset, selectActiveCityRevision } from '../scripts/build-city-asset.mjs';

const cacheRoot = fileURLToPath(new URL('../../../.harness/.cache/city-build-selection-tests/', import.meta.url));
mkdirSync(cacheRoot, { recursive: true });
const hash = file => createHash('sha256').update(readFileSync(file)).digest('hex');
function fnv(bytes) { let value = 14695981039346656037n; for (const byte of bytes) value = BigInt.asUintN(64, (value ^ BigInt(byte)) * 1099511628211n); return value.toString(16).padStart(16, '0'); }
function json(file, value) { writeFileSync(file, JSON.stringify(value)); }
function glb() {
  // Selection fixture only: this metadata tests format/budget checks; it is not
  // a drawable mesh or a visual-quality qualification.
  const document = { asset: { version: '2.0' }, extensionsUsed: ['EXT_meshopt_compression', 'KHR_texture_basisu'], meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2 }] }], accessors: [{ count: 3 }, { count: 3 }, { count: 3 }], materials: [{}] };
  const text = Buffer.from(JSON.stringify(document));
  const chunk = Buffer.alloc(Math.ceil(text.length / 4) * 4, 32); text.copy(chunk);
  const buffer = Buffer.alloc(20 + chunk.length); buffer.write('glTF', 0); buffer.writeUInt32LE(2, 4); buffer.writeUInt32LE(buffer.length, 8); buffer.writeUInt32LE(chunk.length, 12); buffer.writeUInt32LE(0x4e4f534a, 16); chunk.copy(buffer, 20); return buffer;
}
function fixture(t) {
  const root = mkdtempSync(path.join(cacheRoot, 'case-'));
  t.after(() => {
    const resolved = path.resolve(root);
    assert.equal(path.dirname(resolved), path.resolve(cacheRoot));
    assert.ok(path.basename(resolved).startsWith('case-'));
    rmSync(resolved, { recursive: true, force: true });
  });
  const sourceDir = path.join(root, 'assets/models/reference-city/r5');
  const selectedDir = path.join(sourceDir, 'selected'); mkdirSync(selectedDir, { recursive: true });
  const files = {};
  for (const [name, bytes] of [['selected.blend', Buffer.from('immutable Blender fixture')], ['city-source.glb', glb()], ['city-runtime.meshopt.glb', glb()]]) {
    const filename = path.join(selectedDir, name); writeFileSync(filename, bytes);
    files[name] = { path: path.relative(root, filename).replaceAll('\\', '/'), sha256: hash(filename) };
  }
  const operation = { schema: 'xexoria.city-traversal/1', units: 'metres', city_bounds: { min_x: -10, max_x: 10, min_z: -10, max_z: 10 }, contract: { max_step_m: 0.36, max_slope_degrees: 50, feet_offset_m: 0.015, query_epsilon_m: 0.00005, max_movement_substep_m: 0.1 }, surfaces: [{ id: 'floor', kind: 'ground', vertices: [[-10, 0, -10], [10, 0, -10], [10, 0, 10], [-10, 0, 10]], triangles: [[0, 1, 2], [0, 2, 3]] }], blockers: [{ id: 'gate wall', kind: 'wall', polygon_xz: [[4, 4], [5, 4], [5, 5], [4, 5]], y_min: 0, y_max: 2 }] };
  const traversalFile = path.join(selectedDir, 'city-traversal-v1.json');
  json(traversalFile, { ...operation, source: { master_path: files['selected.blend'].path, master_sha256: files['selected.blend'].sha256 } });
  files['city-traversal-v1.json'] = { path: path.relative(root, traversalFile).replaceAll('\\', '/'), sha256: hash(traversalFile) };
  const selected = { schema: 'xexoria.city-active-revision/1', revision: 'r5-selected-test', files, retired_static_ids: ['old_gate_wall'], replacement_gate_ids: ['gate wall'] };
  const pointer = path.join(sourceDir, 'active-revision.json'); json(pointer, selected);
  const zonesFile = path.join(root, 'content/source/zones.json'); mkdirSync(path.dirname(zonesFile), { recursive: true });
  const zone = { id: 1, half_extent: 308, static_colliders: [], city_traversal: operation }; json(zonesFile, { zones: [zone] });
  const buildRoot = path.join(root, 'content/build'); mkdirSync(buildRoot, { recursive: true });
  const bytes = Buffer.from(JSON.stringify({ schema: 1, zones: [zone] })); const contentHash = fnv(bytes);
  const build = path.join(buildRoot, contentHash); mkdirSync(build); writeFileSync(path.join(build, 'bundle.json'), bytes);
  const destination = path.join(root, 'apps/client/src/assets/models/env_reference_city.glb'); mkdirSync(path.dirname(destination), { recursive: true }); writeFileSync(destination, 'older live runtime');
  for (const name of ['reference_city.blend', 'city-source.glb', 'city-runtime.glb', 'manifest.json']) writeFileSync(path.join(sourceDir, name), `immutable canonical ${name}`);
  const protectedFiles = [...Object.values(files).map(record => path.join(root, record.path)), ...['reference_city.blend', 'city-source.glb', 'city-runtime.glb', 'manifest.json'].map(name => path.join(sourceDir, name))];
  return { root, selected, pointer, files, operation, zone, zonesFile, traversalFile, destination, build, buildRoot, contentHash, protectedFiles };
}
function quietBuild(args, root) { const previous = console.log; try { console.log = () => {}; return buildCityAsset(args, root); } finally { console.log = previous; } }

test('default R5 build retains the selected package and leaves all sources/manifests immutable', t => {
  const f = fixture(t); const before = f.protectedFiles.map(hash);
  const selection = quietBuild([], f.root);
  assert.equal(selection.revision, 'r5-selected-test'); assert.equal(selection.content_hash, f.contentHash);
  assert.equal(hash(f.destination), f.files['city-runtime.meshopt.glb'].sha256);
  assert.deepEqual(f.protectedFiles.map(hash), before);
  assert.equal(selection.runtime.triangles, 1);
});

test('check-selection is read-only even when the live runtime differs', t => {
  const f = fixture(t); const before = [...f.protectedFiles, f.destination].map(hash);
  quietBuild(['--revision', 'r5', '--check-selection'], f.root);
  assert.deepEqual([...f.protectedFiles, f.destination].map(hash), before);
});

test('missing active pointer never falls back to canonical Blender source', t => {
  const f = fixture(t); rmSync(f.pointer); const before = hash(f.destination);
  assert.throws(() => quietBuild([], f.root), /required; refusing fallback/);
  assert.equal(hash(f.destination), before);
});

test('tampered selected bytes fail before changing the live asset', t => {
  const f = fixture(t); const before = hash(f.destination);
  writeFileSync(path.join(f.root, f.files['city-runtime.meshopt.glb'].path), 'tampered runtime');
  assert.throws(() => quietBuild([], f.root), /SHA256 mismatch/); assert.equal(hash(f.destination), before);
});

test('unknown selection schema and escaping source paths are rejected', t => {
  const f = fixture(t); f.selected.schema = 'unapproved/2'; json(f.pointer, f.selected);
  assert.throws(() => selectActiveCityRevision(f.root), /schema or revision/);
  f.selected.schema = 'xexoria.city-active-revision/1'; f.selected.files['city-source.glb'].path = 'assets/models/reference-city/r5/../city-source.glb'; json(f.pointer, f.selected);
  assert.throws(() => selectActiveCityRevision(f.root), /Invalid selected path/);
});

test('traversal must identify the pinned master and be admitted in authored content', t => {
  const f = fixture(t); const raw = JSON.parse(readFileSync(f.traversalFile, 'utf8')); raw.source.master_sha256 = '0'.repeat(64); json(f.traversalFile, raw);
  f.files['city-traversal-v1.json'].sha256 = hash(f.traversalFile); json(f.pointer, f.selected);
  assert.throws(() => selectActiveCityRevision(f.root), /pinned editable master/);
  raw.source.master_sha256 = f.files['selected.blend'].sha256; json(f.traversalFile, raw); f.files['city-traversal-v1.json'].sha256 = hash(f.traversalFile); json(f.pointer, f.selected);
  f.zone.city_traversal = { ...f.operation, blockers: [] }; json(f.zonesFile, { zones: [f.zone] });
  assert.throws(() => selectActiveCityRevision(f.root), /not already admitted/);
});

test('hashed bundle integrity and matching built traversal remain mandatory', t => {
  const f = fixture(t); const bundleFile = path.join(f.build, 'bundle.json'); writeFileSync(bundleFile, '{}');
  assert.throws(() => selectActiveCityRevision(f.root), /FNV hash directory/);
  const staleZone = { ...f.zone, city_traversal: { ...f.operation, blockers: [] } };
  const bytes = Buffer.from(JSON.stringify({ schema: 1, zones: [staleZone] })); const newBuild = path.join(f.buildRoot, fnv(bytes));
  assert.equal(path.dirname(path.resolve(f.build)), path.resolve(f.buildRoot)); assert.equal(path.dirname(path.resolve(newBuild)), path.resolve(f.buildRoot));
  renameSync(f.build, newBuild); writeFileSync(path.join(newBuild, 'bundle.json'), bytes);
  assert.throws(() => selectActiveCityRevision(f.root), /hashed traversal disagree/);
});

test('retired gate boxes cannot remain and replacement blockers cannot disappear', t => {
  const f = fixture(t); f.zone.static_colliders = [{ id: 'old_gate_wall' }]; json(f.zonesFile, { zones: [f.zone] });
  assert.throws(() => selectActiveCityRevision(f.root), /retired gate boxes/);
  f.zone.static_colliders = []; json(f.zonesFile, { zones: [f.zone] }); f.selected.replacement_gate_ids.push('missing gate mesh'); json(f.pointer, f.selected);
  assert.throws(() => selectActiveCityRevision(f.root), /replacement blockers/);
});

test('regeneration and malformed build options cannot bypass the selection', t => {
  const f = fixture(t); const before = [...f.protectedFiles, f.destination].map(hash);
  assert.throws(() => quietBuild(['--regenerate-source'], f.root), /immutable selected R5 source/);
  assert.throws(() => quietBuild(['--revision'], f.root), /Provide --revision/);
  assert.throws(() => quietBuild(['--force'], f.root), /Unknown city build option/);
  assert.deepEqual([...f.protectedFiles, f.destination].map(hash), before);
});
