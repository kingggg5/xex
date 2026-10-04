// Terrain spec §8.4 test 4: apps/client/src/assets/world/terrain/terrain-layerset.json (schema xexoria.terrain-layerset/1).
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const terrainDir = fileURLToPath(new URL('../src/assets/world/terrain/', import.meta.url));
const manifest = JSON.parse(readFileSync(path.join(terrainDir, 'terrain-layerset.json'), 'utf8'));
const spec = JSON.parse(readFileSync(fileURLToPath(new URL('../../../assets/models/sunmeadow-v2/terrain/terrain-spec.json', import.meta.url)), 'utf8'));
const sha = file => createHash('sha256').update(readFileSync(file)).digest('hex');
const KTX2_ID = Buffer.from([0xab, 0x4b, 0x54, 0x58, 0x20, 0x32, 0x30, 0xbb, 0x0d, 0x0a, 0x1a, 0x0a]);

test('schema, encoding and layer order', () => {
	assert.equal(manifest.schema, 'xexoria.terrain-layerset/1');
	assert.equal(manifest.albedoEncoding, 'srgb-bytes-in-unorm');
	assert.deepEqual(manifest.layers.map(l => l.id), ['L0', 'L1', 'L2', 'L3']);
	assert.deepEqual(manifest.layers.map(l => l.channel), ['R', 'G', 'B', 'A']);
	assert.deepEqual(manifest.relief.map(l => l.id), ['R0', 'R1']);
	assert.ok(String(manifest.tools?.ktx).includes('4.4.2'), 'pinned KTX-Software 4.4.2');
});

test('channel packing, tiles, height ranges and resolutions follow the spec', () => {
	const specLayers = [...spec.layers, ...spec.relief_layers];
	for (const layer of [...manifest.layers, ...manifest.relief]) {
		const s = specLayers.find(x => x.id === layer.id);
		assert.deepEqual(layer.packing, { ah: ['albedo.r', 'albedo.g', 'albedo.b', 'height'], nro: ['normal.x', 'normal.y', 'roughness', 'ao'] });
		assert.equal(layer.albedoEncoding, 'srgb-bytes-in-unorm');
		assert.equal(layer.tile_m, s.tile_m);
		assert.equal(layer.height_range_m, s.height_range_m);
		const wanted = [...new Set(Object.values(s.res))].map(String).sort();
		assert.deepEqual(Object.keys(layer.files.ah).sort(), wanted, `${layer.id} AH resolutions`);
		assert.deepEqual(Object.keys(layer.files.nro).sort(), wanted, `${layer.id} NRO resolutions`);
	}
});

test('far-path means are finite and plausible', () => {
	for (const layer of [...manifest.layers, ...manifest.relief]) {
		assert.equal(layer.mean_linear_rgb.length, 3);
		for (const v of layer.mean_linear_rgb) assert.ok(Number.isFinite(v) && v > 0.005 && v < 0.6, `${layer.id} mean ${v}`);
		assert.ok(Number.isFinite(layer.mean_roughness) && layer.mean_roughness > 0.2 && layer.mean_roughness <= 1);
	}
	const [lush, , dirt] = manifest.layers;
	assert.ok(lush.mean_linear_rgb[1] > lush.mean_linear_rgb[0] && lush.mean_linear_rgb[1] > lush.mean_linear_rgb[2], 'lush is green');
	assert.ok(dirt.mean_linear_rgb[0] > dirt.mean_linear_rgb[2], 'dirt is warm');
});

test('every layer file exists, is a KTX2 container and matches its SHA-256', () => {
	for (const layer of [...manifest.layers, ...manifest.relief]) {
		for (const map of ['ah', 'nro']) {
			for (const file of Object.values(layer.files[map])) {
				const full = path.join(terrainDir, file);
				assert.ok(existsSync(full), file);
				assert.ok(readFileSync(full).subarray(0, 12).equals(KTX2_ID), `${file} is KTX2`);
				assert.equal(sha(full), layer.sha256[file], `${file} hash`);
			}
		}
	}
});

test('stats flags: every layer passes §3.3 at source; decoded flags are recorded per resolution', () => {
	for (const layer of [...manifest.layers, ...manifest.relief]) {
		assert.equal(layer.stats.source_pass, true, `${layer.id} source gates`);
		assert.deepEqual(Object.keys(layer.stats.decoded_pass).sort(), Object.keys(layer.files.ah).sort());
		for (const [res, tilt] of Object.entries(layer.stats.mip0_tilt_deg)) assert.ok(Number.isFinite(tilt) && tilt > 1, `${layer.id} ${res} mip0 tilt`);
	}
});

test('cells: corner-aligned 64 m bounds, 257 and 129 splat/data PNGs, hashes match, masks passed', () => {
	assert.ok(manifest.cells.live && manifest.cells.lab && manifest.cells.v2, 'live, lab and v2 sets');
	assert.deepEqual(Object.keys(manifest.cells.live).sort(), ['sunmeadow_c7_r6', 'sunmeadow_c8_r6']);
	for (const [set, cells] of Object.entries(manifest.cells)) {
		for (const [id, cell] of Object.entries(cells)) {
			const [x0, x1, z0, z1] = cell.bounds;
			assert.equal(x1 - x0, 64, `${set}/${id}`);
			assert.equal(z1 - z0, 64, `${set}/${id}`);
			assert.equal(cell.masks_pass, true, `${set}/${id} passed the §3.5 validations`);
			for (const map of ['splat', 'data']) {
				for (const res of ['257', '129']) {
					const file = cell[map][res];
					const full = path.join(terrainDir, file);
					assert.ok(existsSync(full), file);
					const bytes = readFileSync(full);
					assert.equal(bytes.readUInt32BE(16), Number(res), `${file} width`);
					assert.equal(bytes[25], 2, `${file} is RGB (colour type 2)`);
					assert.equal(sha(full), cell.sha256[file]);
				}
			}
		}
	}
	// live cells reuse the zones.json ids and bounds (spec §0 contract)
	assert.deepEqual(manifest.cells.live.sunmeadow_c7_r6.bounds, [-64, 0, -128, -64]);
	assert.deepEqual(manifest.cells.live.sunmeadow_c8_r6.bounds, [0, 64, -128, -64]);
});

test('lab calibration textures exist as KTX2 and PNG', () => {
	for (const entry of Object.values(manifest.calibration)) {
		for (const kind of ['ktx2', 'png']) {
			const full = path.join(terrainDir, entry[kind]);
			assert.ok(existsSync(full), entry[kind]);
			assert.equal(sha(full), entry.sha256[kind]);
		}
	}
});
