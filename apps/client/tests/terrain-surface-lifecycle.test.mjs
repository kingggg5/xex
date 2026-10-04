// Terrain spec §8.4 test 3: TerrainSurface lifecycle on NullEngine (create, dispose x2, fallback, weather, tiers).
import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import * as M from '../src/terrain-surface-math.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
const bundled = await build({ stdin: { contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial';
export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
export * from './src/terrain-surface';`, resolveDir: root, loader: 'ts' }, bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent', loader: { '.png': 'empty', '.ktx2': 'empty' } });
const api = await import('data:text/javascript;base64,' + Buffer.from(bundled.outputFiles[0].text).toString('base64'));

const layer = (id, name, tile, res) => ({ id, name, channel: 'R', tile_m: tile,
	files: { ah: Object.fromEntries(res.map(r => [String(r), `layers/${name}_ah_${r}.ktx2`])), nro: Object.fromEntries(res.map(r => [String(r), `layers/${name}_nro_${r}.ktx2`])) },
	packing: { ah: [], nro: [] }, albedoEncoding: 'srgb-bytes-in-unorm', height_range_m: 0.1, mean_linear_rgb: [0.1, 0.2, 0.05], mean_roughness: 0.85 });
const cell = (minX, minZ) => ({ bounds: [minX, minX + 64, minZ, minZ + 64],
	splat: { 257: `cells/t/${minX}_${minZ}_splat_257.png`, 129: `cells/t/${minX}_${minZ}_splat_129.png` },
	data: { 257: `cells/t/${minX}_${minZ}_terrain_257.png`, 129: `cells/t/${minX}_${minZ}_terrain_129.png` } });
const manifest = {
	schema: 'xexoria.terrain-layerset/1', albedoEncoding: 'srgb-bytes-in-unorm',
	layers: [layer('L0', 'lush', 6, [1024, 512]), layer('L1', 'dry', 5, [1024, 512]), layer('L2', 'dirt', 4, [1024, 512]), layer('L3', 'mud', 3, [512])],
	relief: [layer('R0', 'rock', 4, [1024, 512]), layer('R1', 'moss', 3, [512, 256])],
	cells: { t: { c7: cell(-64, -128), c8: cell(0, -128) } },
};

function fixture({ fail = () => false } = {}) {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	const created = [];
	const createTexture = (url, opts) => {
		const t = api.RawTexture.CreateRGBATexture(new Uint8Array([255, 255, 255, 255]), 1, 1, scene, false, false);
		created.push({ url, t, opts });
		// NullEngine raw textures never report isReady(): signal load/error asynchronously like a real texture
		queueMicrotask(() => (fail(url) ? opts.onError('fixture failure') : opts.onLoad()));
		return t;
	};
	return { engine, scene, created, createTexture };
}
const counts = scene => ({ textures: scene.textures.length, materials: scene.materials.length, before: scene.onBeforeRenderObservable.observers.length,
	disposeObs: scene.onDisposeObservable.observers.length });

test('create, use and dispose (twice) return to the baseline counts', async () => {
	const f = fixture();
	try {
		const legacy = new api.PBRMaterial('env-shared-world-grass', f.scene);
		const baseline = counts(f.scene);
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => `mem://${u}`, legacy, set: 't', createTexture: f.createTexture });
		const a = surface.materialForCell('c7'), b = surface.materialForCell('c8');
		assert.notEqual(a, b, 'grass_ground is one material per cell');
		assert.equal(surface.materialForCell('c7'), a, 'cached');
		assert.equal(await surface.whenCellReady('c7'), true);
		assert.equal(await surface.resolveCellMaterial('c8'), b);
		surface.rockMaterial('terrain_cliff_rock', 'c7');
		surface.rockMaterial('terrain_outcrop_rock');
		assert.ok(f.scene.materials.length > baseline.materials);
		const est = surface.memoryEstimate();
		assert.equal(est.residentCells, 2);
		assert.ok(est.mib > 0 && est.basis.length > 10);
		surface.retainCell('c7');
		surface.releaseCell('c7');
		assert.equal(surface.memoryEstimate().residentCells, 1, 'released cell textures and material');
		surface.dispose();
		surface.dispose();
		assert.deepEqual(counts(f.scene), baseline);
		assert.ok(f.created.every(c => c.t.isDisposed?.() ?? c.t.getInternalTexture() === null), 'every created texture disposed');
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('KTX2 layer textures are UNORM (never sRGB-tagged) and cell maps load with invertY = true', () => {
	const f = fixture();
	try {
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, set: 't', createTexture: f.createTexture });
		surface.materialForCell('c7');
		for (const c of f.created) {
			assert.equal(c.opts.srgb, false, `${c.url} must not be sRGB-tagged (the shader decodes)`);
			assert.equal(c.opts.invertY, true);
		}
		assert.ok(f.created.some(c => c.url.endsWith('lush_ah_1024.ktx2')), 'High tier loads the 1024 layers');
		assert.ok(f.created.some(c => c.url.endsWith('splat_257.png')));
		surface.dispose();
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('a failed texture falls back to the legacy material', async () => {
	const f = fixture({ fail: url => url === 'cells/t/0_-128_splat_257.png' });   // only cell c8's splat map fails
	try {
		const legacy = new api.PBRMaterial('env-shared-world-grass', f.scene);
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, legacy, set: 't', createTexture: f.createTexture });
		const warn = console.warn; console.warn = () => {};
		try {
			assert.equal(await surface.resolveCellMaterial('c8'), legacy);
			assert.equal(await surface.whenCellReady('c8'), false);
			assert.equal(await surface.whenCellReady('c7'), true);
		} finally { console.warn = warn; }
		surface.dispose();
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('weather written on the legacy material reaches every terrain material (world-weather.ts contract)', () => {
	const f = fixture();
	try {
		const legacy = new api.PBRMaterial('env-shared-world-grass', f.scene);
		legacy.roughness = 0.94 - 1 * 0.22;
		legacy.albedoColor.set(0.91 - 0.1, 0.94 - 0.08, 0.86 - 0.08);
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, legacy, set: 't', createTexture: f.createTexture });
		const material = surface.materialForCell('c7');
		const plugin = material.pluginManager.getPlugin('TerrainSurface');
		assert.ok(plugin && plugin.registerForExtraEvents);
		const writes = {};
		plugin.hardBindForSubMesh({ updateFloat4: (name, x, y, z, w) => { writes[name] = [x, y, z, w]; } });
		assert.ok(Math.abs(writes.terrainWeather[0] - 1) < 1e-9, 'rainWet = (0.94 - roughness) / 0.22');
		assert.ok(Math.abs(writes.terrainWeather[1] - 0.81 / 0.914) < 1e-6, 'tint ratio');
		assert.ok(Math.abs(writes.terrainLook[0] - 0.72 / 0.94) < 1e-9, 'weather roughness factor');
		assert.deepEqual(writes.terrainCell.slice(0, 2), [-64, -128]);
		assert.ok(Math.abs(writes.terrainCell[2] - 256 / 257 / 64) < 1e-12 && Math.abs(writes.terrainCell[3] - 0.5 / 257) < 1e-12);
		assert.deepEqual(writes.terrainTile, [1 / 6, 1 / 5, 1 / 4, 1 / 3]);
		assert.deepEqual(writes.terrainBlend, [0.6, 0.12, 70, 90]);
		legacy.roughness = 0.94;
		plugin.hardBindForSubMesh({ updateFloat4: (name, x) => { writes[name] = [x]; } });
		assert.equal(writes.terrainWeather[0], 0, 'dry');
		surface.dispose();
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('setQuality: tier define on every plugin, 1024 -> 512 swap only after the new set is ready', async () => {
	const f = fixture();
	try {
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, set: 't', createTexture: f.createTexture });
		const material = surface.materialForCell('c7');
		const plugin = material.pluginManager.getPlugin('TerrainSurface');
		const old = f.created.filter(c => c.url.includes('_1024.ktx2')).map(c => c.t);
		surface.setQuality({ preset: 'low' });
		assert.equal(surface.tier, 0);
		assert.equal(plugin.state.tier, 0);
		const defines = {};
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_TIER, 0);
		assert.equal(defines.TERRAIN_SPLAT, true);
		assert.equal(await surface.whenLayersReady(), true);
		assert.ok(f.created.some(c => c.url.endsWith('lush_ah_512.ktx2')));
		assert.ok(old.every(t => t.getInternalTexture() === null), 'old 1024 set disposed after the swap');
		surface.setQuality({ preset: 'medium' });
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_TIER, 1);
		surface.debug('normal');
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_DEBUG, 3);
		surface.solo(2);
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_SOLO, 3);
		surface.solo(null);
		surface.debug('off');
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_DEBUG, false);
		assert.equal(defines.TERRAIN_SOLO, false);
		surface.dispose();
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('manifest guards: schema and albedo encoding are enforced', () => {
	const f = fixture();
	try {
		assert.throws(() => api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest: { ...manifest, schema: 'x' }, resolveUrl: u => u, createTexture: f.createTexture }));
		assert.throws(() => api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest: { ...manifest, albedoEncoding: 'srgb' }, resolveUrl: u => u, createTexture: f.createTexture }));
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, set: 't', createTexture: f.createTexture });
		assert.throws(() => surface.materialForCell('nope'));
		assert.deepEqual(surface.cellIds(), ['c7', 'c8']);
		surface.dispose();
	} finally { f.scene.dispose(); f.engine.dispose(); }
});

test('baked cell maps (GPU cost study): PNG bytes decoded, fields in alpha, TERRAIN_NOISE_MAPS on; a corrupt PNG falls back to legacy', async () => {
	const { deflateSync } = await import('node:zlib');
	// 257 x 257 RGB PNG, filter 0, splat = (lush 255, 0, 0) / data = (sdf 160, rut 255, ao 200)
	const png = rgb => {
		const size = 257, row = 1 + size * 3, raw = Buffer.alloc(size * row);
		for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) raw.set(rgb, y * row + 1 + x * 3);
		const chunk = (tag, body) => { const b = Buffer.alloc(12 + body.length); b.writeUInt32BE(body.length, 0); b.write(tag, 4, 'latin1'); body.copy(b, 8); return b; };
		const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 2;
		return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
	};
	const bytes = { splat: png([255, 0, 0]), data: png([160, 255, 200]) };
	const loads = [];
	const loadBytes = async url => {
		loads.push(url);
		if (url === 'cells/t/0_-128_terrain_257.png') return new Uint8Array([1, 2, 3]);   // c8's data map is corrupt
		return url.includes('_splat_') ? bytes.splat : bytes.data;
	};
	const uploads = [];
	const update = api.RawTexture.prototype.update;
	api.RawTexture.prototype.update = function (data) { uploads.push({ name: this.name, data }); return update.call(this, data); };
	const f = fixture();
	try {
		const legacy = new api.PBRMaterial('env-shared-world-grass', f.scene);
		const baseline = counts(f.scene);
		const surface = api.createTerrainSurface(f.scene, { profile: { preset: 'high' }, manifest, resolveUrl: u => u, legacy, set: 't', createTexture: f.createTexture, loadBytes });
		const material = surface.materialForCell('c7');
		assert.equal(await surface.whenCellReady('c7'), true);
		assert.equal(await surface.resolveCellMaterial('c7'), material);
		const plugin = material.pluginManager.getPlugin('TerrainSurface');
		const defines = {};
		plugin.prepareDefines(defines);
		assert.equal(defines.TERRAIN_NOISE_MAPS, true);
		assert.ok(f.created.every(c => !c.url.endsWith('.png')), 'cell PNGs are not loaded as image textures');
		const splat = uploads.find(u => u.name.endsWith('-64_-128_splat_257.png')), data = uploads.find(u => u.name.endsWith('-64_-128_terrain_257.png'));
		assert.ok(splat && data && splat.data.length === 257 * 257 * 4);
		assert.deepEqual(Array.from(splat.data.subarray(0, 3)), [255, 0, 0], 'RGB bytes exact');
		assert.deepEqual(Array.from(data.data.subarray(4 * 1000, 4 * 1000 + 3)), [160, 255, 200]);
		// alpha = baked fields: texel (0, 0) of the upload is the south-west corner (-64, -128)
		assert.equal(splat.data[3], Math.round(M.macroField(-64, -128) * 255));
		assert.equal(data.data[3], Math.round(M.antiTilingMaskField(-64, -128) * 255));
		const warn = console.warn; console.warn = () => {};
		try {
			assert.equal(await surface.resolveCellMaterial('c8'), legacy, 'corrupt cell map -> legacy ground');
		} finally { console.warn = warn; }
		assert.ok(loads.includes('cells/t/0_-128_terrain_257.png'));
		surface.dispose();
		assert.deepEqual(counts(f.scene), baseline, 'raw cell textures disposed with the surface');
	} finally { api.RawTexture.prototype.update = update; f.scene.dispose(); f.engine.dispose(); }
});
