import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { transform } from 'esbuild';
import { compileMapBase, createMapBaseLoader, mapBaseCrop, projectMapPoint, rasterizeMapBase, MAP_BASE_LIMITS } from '../src/ui/hud-map-base.mjs';

const fixture = () => ({ zones: [{ half_extent: 100, terrain_cells: [{ bounds_xz: [-20, 20, -50, -30] }], city_traversal: { surfaces: [{ kind: 'ground', vertices: [[0, 0, 0], [10, 0, 0], [0, 0, 10]], triangles: [[0, 1, 2]] }], blockers: [{ kind: 'water_hazard', polygon_xz: [[-3, 10], [3, 10], [3, 20], [-3, 20]] }, { kind: 'tree_trunk', polygon_xz: [[0, 0], [2, 0], [0, 2]] }] }, world_routes: [{ width: 3.8, points: [[0, -40], [0, -50]] }] }] });
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
const response = b => ({ ok: true, json: async () => b });
const flush = () => new Promise(resolve => setImmediate(resolve));

test('north is +Z/up, east is +X/right, and player stays centered at every zoom', () => {
  for (const extent of [72, 36, 18]) {
    assert.deepEqual(projectMapPoint(8, 12, 8, 12, extent), { x: 128, y: 128 });
    assert.deepEqual(projectMapPoint(8 + extent, 12 + extent, 8, 12, extent), { x: 240, y: 16 });
  }
  assert.equal(projectMapPoint(NaN, 0, 0, 0, 72), null);
  assert.equal(projectMapPoint(0, 0, 0, 0, 0), null);
  assert.equal(projectMapPoint(0, 0, 0, 0, 72, 256, NaN), null);
});

test('atlas crop and live marker use exactly the same centered north projection', () => {
  for (const extent of [72, 36, 18]) {
    const crop = mapBaseCrop(308, 12, 60, extent);
    for (const [x, z] of [[12, 60], [18, 80], [-8, 24]]) {
      const atlasX = 512 + x * 1024 / 616, atlasY = 512 - z * 1024 / 616;
      const actual = projectMapPoint(x, z, 12, 60, extent);
      near(crop.dx + (atlasX - crop.sx) / crop.sw * crop.dw, actual.x);
      near(crop.dy + (atlasY - crop.sy) / crop.sh * crop.dh, actual.y);
    }
  }
});

test('world-edge crop clips destination rather than stretching known geography', () => {
  const full = mapBaseCrop(100, 0, 0, 20);
  const edge = mapBaseCrop(100, 100, 100, 20);
  assert.ok(edge.sw < full.sw && edge.sh < full.sh);
  near(edge.dw / edge.sw, full.dw / full.sw);
  near(edge.dh / edge.sh, full.dh / full.sh);
  assert.ok(edge.dy > 0); // unknown space north of the authored extent remains blank
  assert.equal(mapBaseCrop(100, 1000, 1000, 20), null);
});

test('compact base retains only authored coverage/water/route width and refuses wrong zones', () => {
  const data = fixture(), model = compileMapBase(data, 100);
  assert.equal(model.polygons.length, 2);
  assert.deepEqual(Array.from(model.polygons[1].points), [-3, 10, 3, 10, 3, 20, -3, 20]);
  assert.equal(model.routes[0].width, 3.8);
  assert.equal(model.triangleCount, 1);
  assert.equal(model.byteLength, 24 + 12 + 32 + 32 + 16);
  assert.equal('monster_spawns' in model, false);
  data.zones[0].city_traversal.surfaces[0].vertices[0][0] = 90;
  assert.equal(model.meshes[0].vertices[0], 0); // not a reference to the decoded bundle
  assert.equal(compileMapBase(data, 99), null);
  data.zones.push(structuredClone(data.zones[0]));
  assert.equal(compileMapBase(data, 100), null); // no zone identity means no guessing
});

test('bad triangle references are not drawn and over-budget geometry fails closed', () => {
  const data = fixture(); data.zones[0].terrain_cells = []; data.zones[0].city_traversal.blockers = [];
  data.zones[0].city_traversal.surfaces[0].triangles = [[0, 1, 99]];
  assert.equal(compileMapBase(data, 100), null);
  data.zones[0].city_traversal.surfaces[0].triangles = [[0, 1, 2]];
  data.zones[0].city_traversal.surfaces[0].vertices = Array.from({ length: MAP_BASE_LIMITS.vertices + 1 }, () => [0, 0, 0]);
  assert.equal(compileMapBase(data, 100), null);
});

test('actual zone remains within compact budget and preserves the three canal gaps', () => {
  const bundle = JSON.parse(readFileSync(new URL('../public/content/bundle.json', import.meta.url)));
  const model = compileMapBase(bundle, 308);
  assert.ok(model && model.byteLength < MAP_BASE_LIMITS.bytes);
  const waters = model.polygons.filter(p => p.kind === 'water_hazard');
  assert.equal(waters.length, 3);
  const ranges = waters.map(p => { const z = Array.from(p.points).filter((_, i) => i % 2); return [Math.min(...z), Math.max(...z)]; }).sort((a, b) => a[0] - b[0]);
  assert.ok(ranges[0][1] < ranges[1][0] && ranges[1][1] < ranges[2][0]);
  assert.equal(model.routes[0].width, bundle.zones[0].world_routes[0].width);
});

test('one atlas bake stays at 1024; crop/movement does not traverse source triangles', () => {
  let triangles = 0;
  const ctx = { fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() { triangles++; }, fill() {}, stroke() {} };
  const canvas = { getContext: () => ctx, width: 0, height: 0 };
  assert.equal(rasterizeMapBase(compileMapBase(fixture(), 100), canvas), true);
  assert.equal(canvas.width, 1024); assert.equal(canvas.height, 1024);
  const baked = triangles;
  for (let i = 0; i < 100; i++) mapBaseCrop(100, i / 10, 0, 20);
  assert.equal(triangles, baked);
});

test('concurrent subscribers share one request; cached compact model survives remount', async () => {
  let calls = 0, signal;
  const loader = createMapBaseLoader(async (_, options) => { calls++; signal = options.signal; return response(fixture()); });
  const a = loader.acquire(100), b = loader.acquire(100);
  a.release();
  const [first, second] = await Promise.all([a.promise, b.promise]);
  assert.equal(calls, 1); assert.equal(first, second); assert.equal(signal.aborted, false);
  b.release(); b.release();
  const remount = loader.acquire(100); assert.equal(await remount.promise, first); remount.release(); assert.equal(calls, 1);
});

test('last unmount aborts pending fetch; ignored late response cannot become cached terrain', async () => {
  let resolve, calls = 0, firstSignal;
  const loader = createMapBaseLoader((_, options) => { calls++; if (calls === 1) { firstSignal = options.signal; return new Promise(r => resolve = r); } return Promise.resolve(response(fixture())); });
  const old = loader.acquire(100); await flush(); old.release();
  assert.equal(firstSignal.aborted, true);
  const current = loader.acquire(100); const model = await current.promise;
  resolve(response(fixture())); assert.equal(await old.promise, null);
  assert.ok(model); assert.equal(calls, 2); current.release();
  const remount = loader.acquire(100); assert.equal(await remount.promise, model); remount.release();
});

test('failed source stays blank and a later mount can retry without caching failure', async () => {
  let calls = 0;
  const loader = createMapBaseLoader(async () => ++calls === 1 ? { ok: false } : response(fixture()));
  const first = loader.acquire(100); assert.equal(await first.promise, null); first.release();
  const second = loader.acquire(100); assert.ok(await second.promise); assert.equal(calls, 2); second.release();
});

// Execute the actual component effect bodies with a small 2D/loader fixture.
// No copied implementation, browser/GPU, synthetic terrain, or Svelte scheduler claim.
async function componentEffects() {
  const source = readFileSync(new URL('../src/ui/HudMinimap.svelte', import.meta.url), 'utf8');
  const bodies = [...source.matchAll(/\t\$effect\(\(\) => \{[\s\S]*?\n\t\}\);/g)];
  assert.equal(bodies.length, 2);
  return Promise.all(bodies.map(async ([body]) => (await transform(body, { loader: 'ts' })).code));
}

test('actual component Tower gate starts no loader, clears previous base, and keeps main-world preview loading', async () => {
  const [body] = await componentEffects();
  let acquisitions = 0, releases = 0;
  const loader = { acquire() { acquisitions++; return { promise: Promise.resolve({}), release() { releases++; } }; } };
  const atlas = { width: 1024, height: 1024 };
  const document = { createElement: () => atlas };
  const execute = new Function('$effect', 'useMainMap', 'safeExtent', 'sharedMapBaseLoader', 'document', 'rasterizeMapBase', 'baseRaster', `${body};return ()=>baseRaster;`);
  let cleanup;
  const disabled = execute(fn => cleanup = fn(), false, 308, loader, document, () => true, atlas);
  assert.equal(disabled(), null); assert.equal(acquisitions, 0); assert.equal(cleanup, undefined);
  const enabled = execute(fn => cleanup = fn(), true, 308, loader, document, () => true, null);
  await flush(); assert.equal(enabled(), atlas); assert.equal(acquisitions, 1);
  cleanup(); assert.equal(enabled(), null); assert.equal(releases, 1); assert.equal(atlas.width, 0); assert.equal(atlas.height, 0);
});

test('actual paint gate rejects a stale main-world atlas in Tower while live markers still draw', async () => {
  const [, body] = await componentEffects();
  let images = 0, rings = 0;
  const ctx = new Proxy({ createRadialGradient: () => ({ addColorStop() {} }), drawImage() { images++; }, arc() { rings++; } }, { get(target, key) { return key in target ? target[key] : () => {}; } });
  const canvas = { getContext: () => ctx };
  const model = { points: [{ id: 'npc', x: 0, z: 0 }], routes: [], showPreviewParty: false };
  const execute = new Function('$effect', 'model', 'canvas', 'viewExtent', 'playerX', 'playerZ', 'projectMapPoint', 'mapBaseCrop', 'useMainMap', 'baseRaster', 'safeExtent', 'preview', 'dot', body);
  execute(fn => fn(), model, canvas, 72, 0, 0, projectMapPoint, mapBaseCrop, false, { width: 1024 }, 308, false, () => {});
  assert.equal(images, 0); assert.equal(rings, 1);
  execute(fn => fn(), model, canvas, 72, 0, 0, projectMapPoint, mapBaseCrop, true, { width: 1024 }, 308, false, () => {});
  assert.equal(images, 1);
});

test('entering Tower releases an actual pending request and fences late raster creation', async () => {
  const [body] = await componentEffects();
  let resolve, signal, created = 0, cleanup;
  const loader = createMapBaseLoader((_, options) => { signal = options.signal; return new Promise(r => resolve = r); });
  const execute = new Function('$effect', 'useMainMap', 'safeExtent', 'sharedMapBaseLoader', 'document', 'rasterizeMapBase', 'baseRaster', `${body};return ()=>baseRaster;`);
  const document = { createElement() { created++; return { width: 1024, height: 1024 }; } };
  const main = execute(fn => cleanup = fn(), true, 100, loader, document, () => true, null);
  await flush(); cleanup();
  const tower = execute(fn => fn(), false, 100, loader, document, () => true, null);
  assert.equal(signal.aborted, true);
  resolve(response(fixture())); await flush();
  assert.equal(created, 0); assert.equal(main(), null); assert.equal(tower(), null);
});
