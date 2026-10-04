// Terrain spec §8.4 test 2: the pure CPU mirror of the splat shader (terrain-surface-math.mjs).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as M from '../src/terrain-surface-math.mjs';
import { GRAPHICS_PRESET_NAMES } from '../src/graphics-quality.mjs';

const spec = JSON.parse(readFileSync(fileURLToPath(new URL('../../../assets/models/sunmeadow-v2/terrain/terrain-spec.json', import.meta.url)), 'utf8'));
const close = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps;

test('constants equal the emitted terrain-spec.json (single source: terrain_spec.py)', () => {
	assert.equal(M.CELL_M, spec.cell.size_m);
	assert.deepEqual({ ...M.CELL_N }, spec.cell.n);
	assert.deepEqual([M.SDF.minM, M.SDF.rangeM], [spec.encodings.sdf.min_m, spec.encodings.sdf.range_m]);
	assert.deepEqual([M.RUT.minM, M.RUT.rangeM, M.RUT.sentinel, M.RUT.evalMaxM], [spec.encodings.rut.min_m, spec.encodings.rut.range_m, spec.encodings.rut.sentinel, spec.encodings.rut.eval_max_m]);
	assert.deepEqual([M.RUT.centreM, M.RUT.profileHalfM, M.RUT.depthM, M.RUT.wanderM, M.RUT.wanderFreq], [spec.rut.centre_m, spec.rut.profile_half_m, spec.rut.depth_m, spec.rut.wander_m, spec.rut.wander_freq]);
	assert.deepEqual([M.BERM.dMin, M.BERM.dMax, M.BERM.heightM], [spec.berm.d_min, spec.berm.d_max, spec.berm.height_m]);
	const hb = spec.runtime.height_blend;
	assert.deepEqual([M.BLEND.lambda, M.BLEND.delta, M.BLEND.ramp, [...M.BLEND.hScale], [...M.BLEND.hBias]], [hb.lam, hb.delta, hb.ramp, hb.h_scale, hb.h_bias]);
	const at = spec.runtime.anti_tiling;
	assert.deepEqual([M.ANTI_TILING.cos, M.ANTI_TILING.sin, [...M.ANTI_TILING.offset], M.ANTI_TILING.maskPeriodM, M.ANTI_TILING.heightGain], [at.rot_cos, at.rot_sin, at.offset, at.mask_period_m, at.height_gain]);
	for (const tier of ['0', '1', '2']) {
		assert.deepEqual([...M.FAR_FADE[tier]], spec.runtime.far_fade[tier]);
		assert.equal(M.TIER_ANISOTROPY[tier], spec.tiers[tier].anisotropy);
		for (const preset of spec.tiers[tier].presets) assert.equal(M.resolveTier(preset), Number(tier));
	}
	assert.equal(M.BRANCH_EPS, spec.runtime.branch_eps);
	assert.equal(M.FAR_DRY_SHARE, spec.mask.border_default[1], 'far material dry share = the cell border default (no edge seam)');
	assert.equal(M.TIER0_NRO_MIN, spec.runtime.tier0_nro_min);
	assert.equal(M.SAMPLER_BUDGET.cellCustom, spec.samplers.cell_custom);
	assert.equal(M.SAMPLER_BUDGET.basePbr + M.SAMPLER_BUDGET.cellCustom, 13);
});

test('corner alignment: texel centres sit on the cell borders and neighbours agree', () => {
	const n = M.CELL_N.high;
	const sw = M.cellUV(-64, -128, -64, -128);
	assert.ok(close(sw.u, 0.5 / (n + 1)) && close(sw.v, 0.5 / (n + 1)));
	const ne = M.cellUV(0, -64, -64, -128);
	assert.ok(close(ne.u, (n + 0.5) / (n + 1)) && close(ne.v, (n + 0.5) / (n + 1)));
	// shared border x = 0 between c7_r6 [-64, 0] and c8_r6 [0, 64]: column n of the west cell = column 0 of the east cell
	for (const row of [0, 17, 128, 256]) {
		const west = M.texelWorld(n, row, -64, -128), east = M.texelWorld(0, row, 0, -128);
		assert.ok(close(west.x, east.x) && close(west.z, east.z));
	}
	for (let k = 0; k < 200; k++) {
		const x = -64 + Math.random() * 64, z = -128 + Math.random() * 64;
		const { u, v } = M.cellUV(x, z, -64, -128);
		const texel = M.texelAtUV(u, v);
		const expected = M.cellTexel(x, z, -64, -128);
		// nearest texel via the sampler mapping equals the corner-aligned texel (ties at exact half-steps excluded)
		const fx = (x + 64) / 0.25 % 1, fz = (z + 128) / 0.25 % 1;
		if (Math.abs(fx - 0.5) < 1e-6 || Math.abs(fz - 0.5) < 1e-6) continue;
		assert.deepEqual(texel, expected);
	}
});

test('orientation fixture: PNG row 0 = north, loaded with invertY = true', () => {
	const n = M.CELL_N.high, eps = 1e-3;
	const { u, v } = M.cellUV(0 - eps, -64 - eps, -64, -128);   // NE corner of c7_r6
	assert.deepEqual(M.texelAtUV(u, v), { col: n, row: 0 });
	assert.deepEqual(M.texelWorld(n, 0, -64, -128), { x: 0, z: -64 });
	const sw = M.cellUV(-64 + eps, -128 + eps, -64, -128);
	assert.deepEqual(M.texelAtUV(sw.u, sw.v), { col: 0, row: n });
});

test('SDF and rut encodings round-trip within 1.2 cm; 255 means no rut', () => {
	for (let d = -2; d <= 4; d += 0.0137) assert.ok(Math.abs(M.decodeSdf(M.encodeSdf(d)) - d) <= 0.0118, `sdf ${d}`);
	for (let l = -3; l <= 3; l += 0.0113) assert.ok(Math.abs(M.decodeRut(M.encodeRut(l)) - l) <= 0.0119, `rut ${l}`);
	assert.equal(M.encodeRut(null), 255);
	assert.equal(M.decodeRut(255), null);
	assert.equal(M.encodeSdf(-9), 0);
	assert.equal(M.encodeSdf(99), 255);
});

test('weights: splat bytes give an exact derived mud weight, quantisation sums to 255', () => {
	const w = M.splatWeights(100, 60, 40);
	assert.ok(close(w.reduce((a, b) => a + b, 0), 1));
	assert.equal(Math.round(w[3] * 255), 55);
	assert.throws(() => M.splatWeights(200, 60, 10));
	for (let k = 0; k < 500; k++) {
		const raw = [Math.random(), Math.random() * 0.5, Math.random() ** 3, Math.random() * 0.2];
		const q = M.quantiseWeights(raw);
		assert.equal(q.reduce((a, b) => a + b, 0), 255);
		const total = raw.reduce((a, b) => a + b, 0);
		q.forEach((byte, i) => assert.ok(Math.abs(byte - raw[i] / total * 255) < 1 + 1e-9));
	}
});

test('height blend: normalised, monotone in its own height, and a zero-weight layer never appears', () => {
	for (let k = 0; k < 300; k++) {
		const w = M.quantiseWeights([Math.random(), Math.random(), Math.random(), Math.random() * 0.3]).map(b => b / 255);
		const h = [Math.random(), Math.random(), Math.random(), Math.random()];
		const b = M.heightBlend(w, h);
		assert.ok(close(b.reduce((s, x) => s + x, 0), 1, 1e-9));
		w.forEach((wi, i) => { if (wi === 0) assert.equal(b[i], 0); });
		const i = k % 4;
		const higher = [...h]; higher[i] = Math.min(1, h[i] + 0.2);
		assert.ok(M.heightBlend(w, higher)[i] >= b[i] - 1e-12, 'raising a layer height never lowers its share');
	}
	const zero = M.heightBlend([1, 0, 0, 0], [0, 1, 1, 1]);
	assert.deepEqual(zero, [1, 0, 0, 0]);
});

test('anti-tiling rotation: R and R^T are inverses; the decoded normal of B is brought back by R^T', () => {
	for (let k = 0; k < 100; k++) {
		const x = Math.random() * 2 - 1, y = Math.random() * 2 - 1;
		const back = M.unrotateNormalXY(...Object.values(M.rotateNormalXY(x, y)));
		assert.ok(close(back.x, x, 1e-12) && close(back.y, y, 1e-12));
	}
	// height field sampled through B's coordinates: h(uv) = f(R uv + o). Its uv-frame gradient is R^T (grad f)(R uv + o).
	const f = (u, v) => Math.sin(3.1 * u) + 0.4 * Math.cos(2.3 * v + 0.7 * u);
	const gf = (u, v) => [3.1 * Math.cos(3.1 * u) - 0.28 * Math.sin(2.3 * v + 0.7 * u), -0.92 * Math.sin(2.3 * v + 0.7 * u)];
	for (let k = 0; k < 50; k++) {
		const u = Math.random() * 4, v = Math.random() * 4, e = 1e-5;
		const b = M.rotateUV(u, v);
		const h = (uu, vv) => { const q = M.rotateUV(uu, vv); return f(q.u, q.v); };
		const numeric = [(h(u + e, v) - h(u - e, v)) / (2 * e), (h(u, v + e) - h(u, v - e)) / (2 * e)];
		const [gx, gy] = gf(b.u, b.v);
		const analytic = M.unrotateNormalXY(gx, gy);
		assert.ok(close(numeric[0], analytic.x, 1e-6) && close(numeric[1], analytic.y, 1e-6));
	}
	assert.equal(M.antiTilingBlend(0, 0.5, 0.5), 0);
	assert.equal(M.antiTilingBlend(1, 0.5, 0.5), 1);
	assert.ok(M.antiTilingBlend(0.5, 0.2, 0.8) > M.antiTilingBlend(0.5, 0.8, 0.2), 'the taller sample wins');
});

test('tier resolution from every graphics preset; far fade and rut/berm profiles', () => {
	for (const preset of GRAPHICS_PRESET_NAMES) assert.ok([0, 1, 2].includes(M.resolveTier(preset)), preset);
	assert.equal(M.resolveTier({ preset: 'ultra' }), 2);
	assert.throws(() => M.resolveTier('potato'));
	assert.equal(M.farFade(10, 2), 0);
	assert.equal(M.farFade(95, 2), 1);
	assert.ok(M.farFade(80, 2) > 0 && M.farFade(80, 2) < 1);
	assert.ok(close(M.rutProfile(0), -M.RUT.depthM));
	assert.equal(M.rutProfile(0.15), 0);
	const e = 1e-6;
	for (const s of [-0.12, -0.05, 0.03, 0.1]) assert.ok(close((M.rutProfile(s + e) - M.rutProfile(s - e)) / (2 * e), M.rutSlope(s), 1e-6));
	assert.ok(close(M.bermProfile(0.25), M.BERM.heightM));
	assert.equal(M.bermProfile(0.5), 0);
});

test('hash value noise is deterministic, in [0, 1) and continuous', () => {
	for (let k = 0; k < 200; k++) {
		const x = Math.random() * 200 - 100, y = Math.random() * 200 - 100;
		const v = M.valueNoise(x, y);
		assert.ok(v >= 0 && v < 1);
		assert.equal(v, M.valueNoise(x, y));
		assert.ok(Math.abs(M.valueNoise(x + 1e-4, y) - v) < 1e-2);
	}
});

test('terrain slots are declared once and never substrings of each other', () => {
	const slots = Object.keys(M.TERRAIN_SLOTS);
	assert.deepEqual(slots, ['grass_ground', 'terrain_bluff_rock', 'terrain_cliff_rock', 'terrain_outcrop_rock', 'terrain_ground_decal']);
	for (const a of slots) for (const b of slots) if (a !== b) assert.ok(!a.includes(b), `${b} is a substring of ${a}`);
	assert.equal(M.terrainSlotOf('Cell sunmeadow_c7_r6 / grass_ground'), 'grass_ground');
	assert.equal(M.terrainSlotOf('Cell sunmeadow_c7_r7 / terrain_cliff_rock'), 'terrain_cliff_rock');
	assert.equal(M.terrainSlotOf('Cell sunmeadow_c7_r6 / stone_foundation'), null);
});

test('memory estimate basis (spec §7.1): High layers 8.67 MiB, per-cell maps 0.67 MiB', () => {
	const layers = M.memoryEstimateMiB({ layerSizes: [1024, 1024, 1024, 1024, 1024, 1024, 512, 512], cellTexels: 257, cells: 0 });
	assert.ok(Math.abs(layers - 8.667) < 0.01, String(layers));
	const cells = M.memoryEstimateMiB({ layerSizes: [], cellTexels: 257, cells: 6 });
	assert.ok(Math.abs(cells - 4.03) < 0.01, String(cells));
});

// ---- GPU cost study (P1 report §10): baked noise fields, exact hash, PNG decode and cell-map bake ----

/** fp32 port of the shader's terrainVNx (terrain-surface.ts), operation by operation. */
function shaderVNx(x, y) {
	const f32 = Math.fround;
	const mod289 = v => f32(v - f32(289 * Math.floor(f32(f32(v + 0.5) * f32(1 / 289)))));
	const px = f32(x), py = f32(y), ix = Math.floor(px), iy = Math.floor(py);
	const fx = f32(px - ix), fy = f32(py - iy);
	const wx = f32(f32(fx * fx) * f32(3 - f32(2 * fx))), wy = f32(f32(fy * fy) * f32(3 - f32(2 * fy)));
	const m = [ix, ix + 1, iy, iy + 1].map(v => mod289(f32(v)));
	const p = [m[0], m[1]].map(v => mod289(f32(f32(f32(34 * v) + 1) * v)));
	const s = [p[0] + m[2], p[1] + m[2], p[0] + m[3], p[1] + m[3]].map(v => (f32(v) >= 289 ? f32(v - 289) : f32(v)));
	const h = s.map(v => f32(mod289(f32(f32(f32(34 * v) + 1) * v)) * f32(1 / 289)));
	const a = h[0] + (h[1] - h[0]) * wx, b = h[2] + (h[3] - h[2]) * wx;
	return a + (b - a) * wy;
}

test('baked fields use an exact hash: the GPU evaluation (fp32) equals the CPU bake', () => {
	let worst = 0;
	for (let k = 0; k < 20000; k++) {
		const x = (Math.random() * 2 - 1) * 200, y = (Math.random() * 2 - 1) * 200;
		worst = Math.max(worst, Math.abs(shaderVNx(x, y) - M.valueNoiseExact(x, y)));
	}
	assert.ok(worst < 5e-5, `|GPU fp32 - CPU| ${worst} (fp32 interpolation only; no hash flips)`);
	for (let i = -300; i < 300; i += 7) for (let j = -300; j < 300; j += 11) {
		const h = M.hashExact(i, j);
		assert.ok(h >= 0 && h < 1 && Number.isInteger(Math.round(h * 289 * 1e6) / 1e6), 'hash is k/289');
		assert.equal(h, M.hashExact(i + 289, j - 289), 'period 289');
	}
	// same statistics as the hash12 value noise it replaces for the baked fields
	let s1 = 0, s2 = 0, q1 = 0, q2 = 0;
	const n = 20000;
	for (let k = 0; k < n; k++) {
		const x = Math.random() * 400, y = Math.random() * 400;
		const a = M.valueNoise(x, y), b = M.valueNoiseExact(x, y);
		s1 += a; q1 += a * a; s2 += b; q2 += b * b;
	}
	assert.ok(Math.abs(s1 / n - s2 / n) < 0.02 && Math.abs(Math.sqrt(q1 / n - (s1 / n) ** 2) - Math.sqrt(q2 / n - (s2 / n) ** 2)) < 0.02);
	assert.ok(Math.abs(M.valueNoiseExact(3 + 1e-6, 5.5) - M.valueNoiseExact(3 - 1e-6, 5.5)) < 1e-4, 'continuous across lattice lines');
});

test('the shader terrainVN order (shared per-axis terms) is the P1 hash; fract flips are why baked fields do not use it', () => {
	let close = 0, n = 0;
	for (let k = 0; k < 20000; k++) {
		const x = (Math.random() * 2 - 1) * 50, y = (Math.random() * 2 - 1) * 50;
		if (Math.abs(M.valueNoiseShared(x, y) - M.valueNoise(x, y)) < 0.02) close++;
		n++;
	}
	assert.ok(close / n > 0.98, `share within 0.02: ${close / n}`);
});

test('cell field grids equal the point functions; fields stay in [0, 1]', () => {
	for (const [minX, minZ, n] of [[-32, -32, 256], [448, -512, 128]]) {
		for (const kind of ['macro', 'mask']) {
			const grid = M.cellFieldGrid(kind, minX, minZ, n);
			assert.equal(grid.length, (n + 1) ** 2);
			for (let row = 0; row <= n; row += 13) for (let col = 0; col <= n; col += 17) {
				const { x, z } = M.texelWorld(col, row, minX, minZ, n);
				const ref = kind === 'macro' ? M.macroField(x, z) : M.antiTilingMaskField(x, z);
				assert.ok(Math.abs(grid[row * (n + 1) + col] - ref) < 1e-12, `${kind} (${col}, ${row})`);
				assert.ok(ref >= 0 && ref < 1);
			}
		}
	}
	assert.throws(() => M.cellFieldGrid('other', 0, 0, 8));
});

/** PNG encoder for the tests: 8-bit, the given row filters, zlib from node. */
async function encodePng(width, height, channels, data, filters) {
	const { deflateSync } = await import('node:zlib');
	const stride = width * channels, raw = Buffer.alloc(height * (stride + 1));
	for (let y = 0; y < height; y++) {
		const f = filters[y % filters.length];
		raw[y * (stride + 1)] = f;
		for (let x = 0; x < stride; x++) {
			const v = data[y * stride + x];
			const a = x >= channels ? data[y * stride + x - channels] : 0, b = y > 0 ? data[(y - 1) * stride + x] : 0;
			const c = x >= channels && y > 0 ? data[(y - 1) * stride + x - channels] : 0;
			const e = a + b - c, pa = Math.abs(e - a), pb = Math.abs(e - b), pc = Math.abs(e - c);
			const pred = [0, a, b, (a + b) >> 1, pa <= pb && pa <= pc ? a : pb <= pc ? b : c][f];
			raw[y * (stride + 1) + 1 + x] = (v - pred) & 255;
		}
	}
	const chunk = (tag, body) => { const b = Buffer.alloc(12 + body.length); b.writeUInt32BE(body.length, 0); b.write(tag, 4, 'latin1'); body.copy(b, 8); return b; };
	const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = { 1: 0, 3: 2, 4: 6 }[channels];
	return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const inflate = async data => new Uint8Array((await import('node:zlib')).inflateSync(data));

test('PNG decoder returns the stored bytes exactly for every row filter and channel layout', async () => {
	for (const channels of [1, 3, 4]) {
		const w = 13, h = 9, data = Uint8Array.from({ length: w * h * channels }, (_, i) => (i * 37 + (i >> 3) * 11) & 255);
		const png = await encodePng(w, h, channels, data, [0, 1, 2, 3, 4]);
		const out = await M.decodePng(png, inflate);
		assert.deepEqual([out.width, out.height, out.channels], [w, h, channels]);
		assert.deepEqual(Array.from(out.data), Array.from(data));
	}
	await assert.rejects(M.decodePng(new Uint8Array(40), inflate), /not a PNG/);
	const bad = await encodePng(4, 4, 3, new Uint8Array(48), [0]);
	bad[24] = 16;   // IHDR bit depth 16
	await assert.rejects(M.decodePng(bad, inflate), /unsupported PNG/);
});

test('cell-map bake: exact RGB, south row first, alpha = field, neighbours bake identical borders', async () => {
	const n = 8, size = n + 1;
	const rgb = Uint8Array.from({ length: size * size * 3 }, (_, i) => (i * 29) & 255);
	const png = await M.decodePng(await encodePng(size, size, 3, rgb, [0, 4]), inflate);
	const out = M.bakeCellMapRGBA(png, 'macro', -64, -128, n);
	assert.equal(out.length, size * size * 4);
	for (let row = 0; row < size; row++) for (let col = 0; col < size; col++) {
		const src = (row * size + col) * 3, dst = ((size - 1 - row) * size + col) * 4;   // PNG row 0 (north) uploads last
		assert.deepEqual([out[dst], out[dst + 1], out[dst + 2]], [rgb[src], rgb[src + 1], rgb[src + 2]]);
		const { x, z } = M.texelWorld(col, row, -64, -128, n);
		assert.equal(out[dst + 3], Math.round(M.macroField(x, z) * 255));
	}
	const alpha = (bytes, row, col) => bytes[((size - 1 - row) * size + col) * 4 + 3];
	const west = M.bakeCellMapRGBA(png, 'mask', -64, -128, n), east = M.bakeCellMapRGBA(png, 'mask', 0, -128, n), north = M.bakeCellMapRGBA(png, 'mask', -64, -64, n);
	for (let k = 0; k < size; k++) {
		assert.equal(alpha(west, k, n), alpha(east, k, 0), 'shared east/west border column');
		assert.equal(alpha(west, 0, k), alpha(north, n, k), 'shared north/south border row');
	}
	assert.throws(() => M.bakeCellMapRGBA(png, 'macro', 0, 0, 16), /expected 17x17/);
});
