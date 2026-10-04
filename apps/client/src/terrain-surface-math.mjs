/**
 * Terrain splat math: the pure CPU mirror of the TerrainSurfacePlugin shader (terrain spec §3.4, §3.6, §8.1).
 *
 * Constants equal assets/models/sunmeadow-v2/terrain/terrain-spec.json (emitted by terrain_spec.py); the
 * test tests/terrain-surface-math.test.mjs asserts that. Used by tests, by the lab's exact-byte probes and,
 * later, by scatter tinting (grass roots sample the same splat). No Babylon imports.
 */

export const CELL_M = 64;
export const CELL_N = Object.freeze({ high: 256, low: 128 });
export const SDF = Object.freeze({ minM: -2, rangeM: 6 });
export const RUT = Object.freeze({ minM: -3, rangeM: 6, sentinel: 255, evalMaxM: 1.3, centreM: 0.78, profileHalfM: 0.15,
	depthM: 0.045, wanderM: 0.10, wanderFreq: 0.11 });
export const BERM = Object.freeze({ dMin: 0.05, dMax: 0.45, heightM: 0.012 });
export const BLEND = Object.freeze({ lambda: 0.6, delta: 0.12, ramp: 0.3, hScale: Object.freeze([1, 1, 1, 0.5]),
	hBias: Object.freeze([0, 0, 0, 0]) });
export const EDGE_BREAKUP = Object.freeze({ bandM: 0.7, amp: 0.9, freqs: Object.freeze([1.3, 3.1]), weights: Object.freeze([0.55, 0.25, 0.2]) });
/** R(36.87 deg) = [[0.8, -0.6], [0.6, 0.8]]; sample B at R uv + offset. */
export const ANTI_TILING = Object.freeze({ cos: 0.8, sin: 0.6, offset: Object.freeze([0.37, 0.71]), maskPeriodM: 7.3,
	maskEdges: Object.freeze([0.3, 0.7]), heightGain: 1.2 });
export const MACRO = Object.freeze({ periodsM: Object.freeze([31, 13]), weights: Object.freeze([0.65, 0.35]),
	value: Object.freeze([0.90, 1.08]), cool: Object.freeze([0.97, 1.0, 1.04]), warm: Object.freeze([1.04, 1.0, 0.94]),
	hueEdges: Object.freeze([0.35, 0.75]) });
export const FAR_FADE = Object.freeze({ 2: Object.freeze([70, 90]), 1: Object.freeze([60, 80]), 0: Object.freeze([45, 60]) });
export const TIER_PRESETS = Object.freeze({ low: 0, medium: 1, high: 2, ultra: 2 });
export const TIER_ANISOTROPY = Object.freeze({ 0: 2, 1: 4, 2: 8 });
export const LAYER_IDS = Object.freeze(["L0", "L1", "L2", "L3"]);
export const BRANCH_EPS = 0.004;
/** terrain_spec.MASK.border_default[1]: the dry share every unauthored cell border blends to; the far material uses it. */
export const FAR_DRY_SHARE = 0.35;
export const TIER0_NRO_MIN = 0.15;
/** Base PBR samplers on the ground (reflection cube, BRDF LUT, one CSM shadow) and the per-stage limit. */
export const SAMPLER_BUDGET = Object.freeze({ basePbr: 3, limit: 16, cellCustom: 10, farCustom: 2, genericRockCustom: 4, heroRockCustom: 6 });

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const smoothstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

/** Corner-aligned cell UV (spec §3.1): uv = (xz - min) / 64 * n / (n + 1) + 0.5 / (n + 1); v grows to the north. */
export function cellUV(x, z, minX, minZ, n = CELL_N.high) {
	const k = n / (n + 1) / CELL_M;
	const o = 0.5 / (n + 1);
	return { u: (x - minX) * k + o, v: (z - minZ) * k + o };
}

/** Texel (column, row) that holds world (x, z); PNG row 0 = north (z = maxZ), loaded with invertY = true. */
export function cellTexel(x, z, minX, minZ, n = CELL_N.high) {
	const step = CELL_M / n;
	return { col: Math.round((x - minX) / step), row: Math.round((minZ + CELL_M - z) / step) };
}

/** World position of a texel centre (inverse of cellTexel). */
export function texelWorld(col, row, minX, minZ, n = CELL_N.high) {
	const step = CELL_M / n;
	return { x: minX + col * step, z: minZ + CELL_M - row * step };
}

/**
 * The texel an invertY = true sampler fetches at uv (nearest): image row 0 sits at v = 1.
 * cellUV followed by this mapping returns cellTexel - the CPU orientation fixture of test 2.
 */
export function texelAtUV(u, v, n = CELL_N.high) {
	const size = n + 1;
	return { col: clamp(Math.floor(u * size), 0, n), row: clamp(Math.floor((1 - v) * size), 0, n) };
}

export const encodeSdf = (d) => clamp(Math.round((d - SDF.minM) / SDF.rangeM * 255), 0, 255);
export const decodeSdf = (byte) => byte / 255 * SDF.rangeM + SDF.minM;
export const encodeRut = (l) => (l === null || l === undefined || Number.isNaN(l)) ? RUT.sentinel
	: clamp(Math.round((l - RUT.minM) / RUT.rangeM * 254), 0, 254);
export const decodeRut = (byte) => byte >= RUT.sentinel ? null : byte / 254 * RUT.rangeM + RUT.minM;

/** Splat bytes -> [lush, dry, dirt, mud]; mud = 255 - r - g - b, exact. */
export function splatWeights(r, g, b) {
	const mud = 255 - r - g - b;
	if (mud < 0) throw new RangeError("Splat bytes exceed 255");
	return [r / 255, g / 255, b / 255, mud / 255];
}

/** Largest-remainder quantisation of 4 weights to bytes summing to 255 (the mask exporter's rule). */
export function quantiseWeights(w) {
	const total = w.reduce((s, v) => s + Math.max(0, v), 0) || 1;
	const scaled = w.map(v => Math.max(0, v) / total * 255);
	const base = scaled.map(Math.floor);
	let short = 255 - base.reduce((s, v) => s + v, 0);
	const order = scaled.map((v, i) => [v - base[i], i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
	for (const [, i] of order) { if (short <= 0) break; base[i] += 1; short -= 1; }
	return base;
}

/**
 * Height blend (spec §3.6 step 1): v_i = w_i + lambda * h_i' * smoothstep(0, ramp, w_i), h_i' = h_i * scale + bias;
 * m = max(v) - delta; b_i = max(v_i - m, 0) / sum. A zero-weight layer never appears.
 */
export function heightBlend(weights, heights, opts = {}) {
	const lambda = opts.lambda ?? BLEND.lambda, delta = opts.delta ?? BLEND.delta, ramp = opts.ramp ?? BLEND.ramp;
	const hScale = opts.hScale ?? BLEND.hScale, hBias = opts.hBias ?? BLEND.hBias;
	const v = weights.map((w, i) => w + lambda * (heights[i] * hScale[i] + hBias[i]) * smoothstep(0, ramp, w));
	const m = Math.max(...v) - delta;
	const b = v.map(x => Math.max(x - m, 0));
	const s = b.reduce((a, x) => a + x, 0) || 1;
	return b.map(x => x / s);
}

/** Anti-tiling sample B coordinate: R(36.87 deg) uv + offset. */
export function rotateUV(u, v) {
	const { cos: c, sin: s, offset } = ANTI_TILING;
	return { u: c * u - s * v + offset[0], v: s * u + c * v + offset[1] };
}

/** Bring B's decoded normal XY back into the uv frame: R^T n (gradients rotate with the coordinates). */
export function unrotateNormalXY(x, y) {
	const { cos: c, sin: s } = ANTI_TILING;
	return { x: c * x + s * y, y: -s * x + c * y };
}

/** Rotate a uv-frame vector into B's frame (R n); unrotateNormalXY is its inverse. */
export function rotateNormalXY(x, y) {
	const { cos: c, sin: s } = ANTI_TILING;
	return { x: c * x - s * y, y: s * x + c * y };
}

/** Anti-tiling blend factor from the 7.3 m mask noise value and the two sampled heights. */
export function antiTilingBlend(maskNoise, hA, hB) {
	const [e0, e1] = ANTI_TILING.maskEdges;
	return clamp((smoothstep(e0, e1, maskNoise) - 0.5) * 2 + (hB - hA) * ANTI_TILING.heightGain + 0.5, 0, 1);
}

/** Tier from a graphics preset name (or a resolved preset object with .preset). */
export function resolveTier(preset) {
	const name = typeof preset === "string" ? preset : preset?.preset;
	const tier = TIER_PRESETS[name];
	if (tier === undefined) throw new RangeError(`Unknown graphics preset ${String(name)}`);
	return tier;
}

/** Far fade 0 (near) .. 1 (far path only). */
export function farFade(distanceM, tier) {
	const [a, b] = FAR_FADE[tier];
	return smoothstep(a, b, distanceM);
}

/** Wheel-rut height profile (normal only): -D (1 - (s / 0.15)^2)^2 for |s| < 0.15 m. */
export function rutProfile(s) {
	const q = s / RUT.profileHalfM;
	return Math.abs(q) >= 1 ? 0 : -RUT.depthM * (1 - q * q) ** 2;
}

/** d(rutProfile)/ds, used for the analytic rut normal. */
export function rutSlope(s) {
	const h = RUT.profileHalfM, q = s / h;
	return Math.abs(q) >= 1 ? 0 : RUT.depthM * 4 * q * (1 - q * q) / h;
}

/** Berm lip outside the path edge: 0.012 m sin bump over d in [0.05, 0.45] m. */
export function bermProfile(d) {
	if (d <= BERM.dMin || d >= BERM.dMax) return 0;
	return BERM.heightM * Math.sin(Math.PI * (d - BERM.dMin) / (BERM.dMax - BERM.dMin));
}

/** Hash value noise identical to the shader's terrainVN (Dave Hoskins hash12, no sin). */
export function hash12(x, y) {
	let p3x = fract(x * 0.1031), p3y = fract(y * 0.1031), p3z = fract(x * 0.1031);
	const d = p3x * (p3y + 33.33) + p3y * (p3z + 33.33) + p3z * (p3x + 33.33);
	p3x += d; p3y += d; p3z += d;
	return fract((p3x + p3y) * p3z);
}
function fract(v) { return v - Math.floor(v); }
export function valueNoise(x, y) {
	const ix = Math.floor(x), iy = Math.floor(y);
	const fx = x - ix, fy = y - iy;
	const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
	const a = hash12(ix, iy), b = hash12(ix + 1, iy), c = hash12(ix, iy + 1), d = hash12(ix + 1, iy + 1);
	return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}

/**
 * The shader's terrainVN evaluation order (terrain-surface.ts; path-edge and rut-wander noise, GPU only): the four
 * corner hashes share their per-axis terms,
 * p3 = (a, b, a) with a = fract(x * 0.1031), b = fract(y * 0.1031), so dot(p3, p3.yzx + 33.33) = 2ab + a^2 + 66.66a +
 * 33.33b and hash = fract((a + b + 2d) (a + d)). Rounded to fp32 at every step like the GPU; it equals valueNoise up to
 * fp32 rounding (test 2 bounds the difference).
 */
export function valueNoiseShared(x, y) {
	const f32 = Math.fround;
	const px = f32(x), py = f32(y);
	const ix = Math.floor(px), iy = Math.floor(py);
	const fx = f32(px - ix), fy = f32(py - iy);
	const wx = f32(f32(fx * fx) * f32(3 - f32(2 * fx))), wy = f32(f32(fy * fy) * f32(3 - f32(2 * fy)));
	const fr = v => f32(v - Math.floor(v));
	const a0 = fr(f32(ix * 0.1031)), a1 = fr(f32(f32(ix + 1) * 0.1031));
	const b0 = fr(f32(iy * 0.1031)), b1 = fr(f32(f32(iy + 1) * 0.1031));
	const ka = a => f32(a * f32(a + 66.66)), kb = b => f32(b * 33.33);
	const h = (a, b) => {
		const d = f32(f32(f32(2 * a) * b) + f32(ka(a) + kb(b)));
		return fr(f32(f32(f32(a + b) + f32(2 * d)) * f32(a + d)));
	};
	const h00 = h(a0, b0), h10 = h(a1, b0), h01 = h(a0, b1), h11 = h(a1, b1);
	const mx0 = h00 + (h10 - h00) * wx, mx1 = h01 + (h11 - h01) * wx;
	return mx0 + (mx1 - mx0) * wy;
}

/**
 * Exact lattice hash for the fields that are baked on the CPU and also evaluated on the GPU (macro, anti-tiling mask):
 * Gustavson's permutation polynomial (34x^2 + x) mod 289 applied twice. Every intermediate is an integer below 2^24,
 * so fp32 on any GPU and fp64 here give the same value. The fract-based hash12 cannot do that: wherever its pre-fract
 * value lands near an integer, a rounding difference flips the result (0.1-0.5 % of lattice points even at small
 * coordinates; GPU study, P1 report §10). Period 289 lattice cells (3.7 km for the 13 m octave).
 */
const mod289 = v => ((v % 289) + 289) % 289;
const permute289 = v => mod289((34 * v + 1) * v);
export function hashExact(ix, iy) {
	return permute289(mod289(permute289(mod289(ix)) + mod289(iy))) / 289;
}
/** Value noise on hashExact (the shader's terrainVNx). */
export function valueNoiseExact(x, y) {
	const ix = Math.floor(x), iy = Math.floor(y);
	const fx = x - ix, fy = y - iy;
	const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
	const a = hashExact(ix, iy), b = hashExact(ix + 1, iy), c = hashExact(ix, iy + 1), d = hashExact(ix + 1, iy + 1);
	return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}

/** Macro value/hue field M2 (spec §3.6 step 4): 0.65 vn(xz / 31) + 0.35 vn(xz / 13), exact hash. */
export function macroField(x, z) {
	const [p0, p1] = MACRO.periodsM, [w0, w1] = MACRO.weights;
	return w0 * valueNoiseExact(x / p0, z / p0) + w1 * valueNoiseExact(x / p1, z / p1);
}

/** Anti-tiling blend mask (spec §3.6 step 3): vn(xz / 7.3), exact hash. */
export function antiTilingMaskField(x, z) {
	return valueNoiseExact(x / ANTI_TILING.maskPeriodM, z / ANTI_TILING.maskPeriodM);
}

/** valueNoiseExact(x / period, z / period) on the grid xs × zs (row-major over zs); lattice hashes computed once. */
function valueNoiseExactGrid(xs, zs, period) {
	const axis = coords => {
		const i = new Float64Array(coords.length), w = new Float64Array(coords.length);
		for (let k = 0; k < coords.length; k++) {
			const p = coords[k] / period, f = Math.floor(p), t = p - f;
			i[k] = f; w[k] = t * t * (3 - 2 * t);
		}
		return { i, w, min: Math.min(...i), max: Math.max(...i) };
	};
	const X = axis(xs), Z = axis(zs);
	const tw = X.max - X.min + 2, th = Z.max - Z.min + 2;
	const table = new Float64Array(tw * th);
	for (let r = 0; r < th; r++) for (let c = 0; c < tw; c++) table[r * tw + c] = hashExact(X.min + c, Z.min + r);
	const out = new Float64Array(xs.length * zs.length);
	for (let r = 0; r < zs.length; r++) {
		const zr = (Z.i[r] - Z.min) * tw, uy = Z.w[r];
		for (let c = 0; c < xs.length; c++) {
			const k = zr + X.i[c] - X.min, ux = X.w[c];
			const a = table[k], b = table[k + 1], cc = table[k + tw], d = table[k + tw + 1];
			out[r * xs.length + c] = a + (b - a) * ux + (cc - a) * uy + (a - b - cc + d) * ux * uy;
		}
	}
	return out;
}

/**
 * A baked field on the cell's texel grid in PNG row order (row 0 = north): "macro" (macroField) or "mask"
 * (antiTilingMaskField). Same values as the point functions; the lattice hashes are computed once per octave.
 */
export function cellFieldGrid(kind, minX, minZ, n) {
	const step = CELL_M / n;
	const xs = Float64Array.from({ length: n + 1 }, (_, col) => minX + col * step);
	const zs = Float64Array.from({ length: n + 1 }, (_, row) => minZ + CELL_M - row * step);
	if (kind === "mask") return valueNoiseExactGrid(xs, zs, ANTI_TILING.maskPeriodM);
	if (kind !== "macro") throw new RangeError(`unknown cell field ${kind}`);
	const [p0, p1] = MACRO.periodsM, [w0, w1] = MACRO.weights;
	const a = valueNoiseExactGrid(xs, zs, p0), b = valueNoiseExactGrid(xs, zs, p1);
	for (let k = 0; k < a.length; k++) a[k] = w0 * a[k] + w1 * b[k];
	return a;
}

/**
 * Minimal PNG decoder for the per-cell maps: 8-bit grey, RGB or RGBA, non-interlaced, any row filter. It returns the
 * stored bytes exactly (no colour management, no premultiplication). `inflate` turns the zlib IDAT stream into bytes
 * (browser: DecompressionStream("deflate"); node: zlib.inflateSync) and may return a promise.
 */
export async function decodePng(bytes, inflate) {
	const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
	const signature = [137, 80, 78, 71, 13, 10, 26, 10];
	if (u8.length < 33 || signature.some((v, i) => u8[i] !== v)) throw new Error("not a PNG");
	const view = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
	let pos = 8, width = 0, height = 0, depth = 0, type = -1, interlace = 0;
	const idat = [];
	while (pos + 8 <= u8.length) {
		const len = view.getUint32(pos);
		const tag = String.fromCharCode(u8[pos + 4], u8[pos + 5], u8[pos + 6], u8[pos + 7]);
		if (pos + 12 + len > u8.length) throw new Error(`PNG chunk ${tag} truncated`);
		if (tag === "IHDR") { width = view.getUint32(pos + 8); height = view.getUint32(pos + 12); depth = u8[pos + 16]; type = u8[pos + 17]; interlace = u8[pos + 20]; }
		else if (tag === "IDAT") idat.push(u8.subarray(pos + 8, pos + 8 + len));
		else if (tag === "IEND") break;
		pos += 12 + len;
	}
	const channels = { 0: 1, 2: 3, 6: 4 }[type];
	if (depth !== 8 || !channels || interlace !== 0 || !width || !height) throw new Error(`unsupported PNG (bit depth ${depth}, colour type ${type}, interlace ${interlace})`);
	const joined = new Uint8Array(idat.reduce((sum, a) => sum + a.length, 0));
	idat.reduce((o, a) => { joined.set(a, o); return o + a.length; }, 0);
	const raw = await inflate(joined);
	const stride = width * channels;
	if (raw.length < height * (stride + 1)) throw new Error("PNG image data truncated");
	const data = new Uint8Array(height * stride);
	for (let y = 0; y < height; y++) {
		const filter = raw[y * (stride + 1)], src = y * (stride + 1) + 1, dst = y * stride;
		if (filter > 4) throw new Error(`PNG row filter ${filter}`);
		for (let x = 0; x < stride; x++) {
			const a = x >= channels ? data[dst + x - channels] : 0;
			const b = y > 0 ? data[dst - stride + x] : 0;
			const c = x >= channels && y > 0 ? data[dst - stride + x - channels] : 0;
			let pred = 0;
			if (filter === 1) pred = a;
			else if (filter === 2) pred = b;
			else if (filter === 3) pred = (a + b) >> 1;
			else if (filter === 4) {
				const e = a + b - c, pa = Math.abs(e - a), pb = Math.abs(e - b), pc = Math.abs(e - c);
				pred = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
			}
			data[dst + x] = (raw[src + x] + pred) & 255;
		}
	}
	return { width, height, channels, data };
}

/**
 * RGBA8 upload bytes for a per-cell map with a world-space field baked into alpha (the cell PNGs carry no alpha, spec
 * §3.4, so reading alpha in the shader costs nothing). RGB bytes stay exact. Rows are reordered south-first because the
 * upload does not flip: texture v grows to the north, as with the PNG loaded with invertY = true. PNG texel (col, row)
 * sits at texelWorld(col, row) on the corner-aligned grid, so neighbouring cells bake identical border values.
 * `field` is "macro" / "mask" (cellFieldGrid) or a point function (x, z) => value in [0, 1].
 */
export function bakeCellMapRGBA(png, field, minX, minZ, n = png.width - 1) {
	const { width, height, channels, data } = png;
	if (width !== n + 1 || height !== n + 1) throw new Error(`cell map is ${width}x${height}, expected ${n + 1}x${n + 1}`);
	const step = CELL_M / n;
	const grid = typeof field === "string" ? cellFieldGrid(field, minX, minZ, n) : null;
	const out = new Uint8Array(width * height * 4);
	for (let row = 0; row < height; row++) {
		const z = minZ + CELL_M - row * step;
		const dst = (height - 1 - row) * width * 4;
		for (let col = 0; col < width; col++) {
			const s = (row * width + col) * channels, o = dst + col * 4;
			out[o] = data[s];
			out[o + 1] = data[s + (channels > 1 ? 1 : 0)];
			out[o + 2] = data[s + (channels > 2 ? 2 : 0)];
			const v = grid ? grid[row * width + col] : field(minX + col * step, z);
			out[o + 3] = Math.round(clamp(v, 0, 1) * 255);
		}
	}
	return out;
}

/** Runtime texture memory (MiB) from formats and levels (spec §7.1 basis: ~1 B/texel compressed, 4 B RGBA8, mips x 4/3). */
export function memoryEstimateMiB({ layerSizes, cellTexels, cells, compressed = true, cellMaps = 2 }) {
	const mip = 4 / 3;
	const layers = layerSizes.reduce((s, size) => s + size * size * (compressed ? 1 : 4) * mip, 0);
	const cellBytes = cells * cellMaps * cellTexels * cellTexels * 4 * mip;
	return (layers + cellBytes) / (1024 * 1024);
}

/**
 * §5.7 terrain material slots, declared once and stable from v2. `grass_ground` is the per-cell splat material
 * (ground, hills and banks); the rock slots use the rock plugin; the decal slot is P2. environment.ts maps cell
 * meshes ("Cell <id> / <slot>") by substring, so no slot may be a substring of another (tests/terrain-cell-binding).
 */
export const TERRAIN_SLOTS = Object.freeze({
	grass_ground: "cell",
	terrain_bluff_rock: "rock",
	terrain_cliff_rock: "rock",
	terrain_outcrop_rock: "rock",
	terrain_ground_decal: "decal",
});

/** The terrain slot named in a cell mesh name, or null for non-terrain slots. */
export function terrainSlotOf(meshName) {
	const name = String(meshName).toLowerCase();
	return Object.keys(TERRAIN_SLOTS).find(slot => name.includes(slot)) ?? null;
}
