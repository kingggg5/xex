/**
 * Grass field placement (grass-v1): pure, deterministic maths for grass-field.ts. No Babylon imports, so every rule,
 * distribution and LOD formula is unit-tested in Node (tests/grass-placement.test.mjs).
 *
 * Procedural by construction (owner direction 2026-10-02 21:35, "try to make procedural"):
 * - Distribution: seeded integer-hash value noise in world space, a clustered tussock process (parents on a world
 *   grid of slots, Poisson children), density masks from the terrain control maps and analytic exclusion SDFs
 *   (paths, water, footprints, arena markings, clearings, city ownership). A patch only owns the parents whose slot
 *   lies inside it, so generation order never matters and patches have no seams.
 * - Clump geometry: seeded procedural meshes (fan tuft of outward-leaning bundle quads, flower plant with stems and
 *   up-facing heads, clover rosette), normalised to height 1 so one instance matrix scales them.
 * - Variation: per instance height, width, yaw, bend (lean), atlas variant, mirror, hue, value and dryness, all from
 *   the seed. Wind and the night tint are evaluated in the shader (grass-field-shaders.mjs).
 *
 * Determinism: integer hashing (lowbias32) and arithmetic only inside the placement loops (no Math.random, no
 * transcendental functions), so a seed reproduces byte-identical instance buffers.
 *
 * Coordinates: Babylon world XZ (+x east, +z north), metres; facing/yaw in radians, atan2(dx, dz) convention.
 */

export const GRASS_GEN_VERSION = 1;
/** Tuft patch edge (m): 4 x 4 patches per 64 m art cell. */
export const PATCH_M = 16;
/** Flower / clover block edge (m): sparse layers use coarser blocks to save draws. */
export const PLANT_BLOCK_M = 32;
/** Tussock slot grid (m) and the expected clumps per tussock (1 + Poisson(2.5), capped at 7). */
export const SLOT_M = 0.7;
export const SINGLES_M = 0.9;
export const TUSSOCK_LAMBDA = 2.5;
export const TUSSOCK_MAX = 7;
/** Mean clump count of a tussock: 1 + E[min(Poisson(2.5), 6)]. */
export const TUSSOCK_MEAN = 3.4651;
/** Share of the density carried by tussocks; singles add SINGLES_SHARE (spec §5.4: singles ~10 %). Calibrated in the
 * tests so a uniform meadow generates its zone density within +-6 %. */
export const TUSSOCK_FILL = 1.04;
export const SINGLES_SHARE = 0.05;
/** Hard caps (spec §7 "hard limits"). */
export const PATCH_CAP = 1500;
export const REGION_CAP = 48000;
/** Height classes (m): base and range. Index order S, M, T, R (sedge/reed). */
export const HEIGHT_CLASSES = Object.freeze([
	Object.freeze({ id: "S", base: 0.33, min: 0.26, max: 0.42, aspect: 1.25 }),
	Object.freeze({ id: "M", base: 0.52, min: 0.42, max: 0.64, aspect: 1.1 }),
	Object.freeze({ id: "T", base: 0.8, min: 0.66, max: 0.98, aspect: 0.95 }),
	Object.freeze({ id: "R", base: 1.0, min: 0.82, max: 1.22, aspect: 0.62 }),
]);
/** Atlas bundle column pairs per class (grass_atlas_v1 cells B0..B7): S/M lush fans, T tall/combed, dry/wispy, sedge. */
export const BUNDLE_PAIRS = Object.freeze({ lush: 0, tall: 2, dry: 4, sedge: 6 });
/** Flower head columns in atlas row 2 (F0..F7). */
export const FLOWER_FAMILIES = Object.freeze(["yellow", "white", "orange", "red", "blue", "yarrow", "pink", "violet"]);
export const FLOWER_COLUMN = Object.freeze(Object.fromEntries(FLOWER_FAMILIES.map((name, index) => [name, index])));
/** Layer kinds (instance meshes). */
export const LAYER_KINDS = Object.freeze(["tuft", "flower", "clover"]);

// =====================================================================================================================
// Hashing, PRNG and noise
// =====================================================================================================================

/** lowbias32 integer hash (Chris Wellons): good avalanche, pure 32-bit arithmetic. */
export function hashU32(value) {
	let x = value >>> 0;
	x ^= x >>> 16;
	x = Math.imul(x, 0x7feb352d);
	x ^= x >>> 15;
	x = Math.imul(x, 0x846ca68b);
	x ^= x >>> 16;
	return x >>> 0;
}

/** Hash of up to four integers and a seed (order-sensitive). */
export function hashInts(seed, a, b = 0, c = 0, d = 0) {
	let h = hashU32((seed >>> 0) ^ 0x9e3779b9);
	h = hashU32(h ^ (a | 0));
	h = hashU32(h ^ (b | 0) ^ 0x85ebca6b);
	h = hashU32(h ^ (c | 0) ^ 0xc2b2ae35);
	return hashU32(h ^ (d | 0) ^ 0x27d4eb2f);
}

/** Uniform [0, 1) with 24 bits from a hash. */
export const unitFromHash = (h) => (h >>> 8) / 16777216;

/** Deterministic 32-bit PRNG (mulberry32): arithmetic only. */
export function createRng(seed) {
	let a = seed >>> 0;
	const next = () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
	return {
		next,
		/** Approximately normal (Irwin-Hall of 4 uniforms, variance-corrected): mean 0, sd 1, bounded at +-3.46. */
		normal() { return (next() + next() + next() + next() - 2) * 1.7320508075688772; },
		/** Poisson sample by inverse transform with a fixed table (lambda = TUSSOCK_LAMBDA). */
		poisson() {
			const u = next();
			for (let k = 0; k < POISSON_CDF.length; k++) if (u < POISSON_CDF[k]) return k;
			return POISSON_CDF.length;
		},
		int(n) { return Math.floor(next() * n) % n; },
	};
}

/** CDF of Poisson(2.5) for k = 0..9 (exp(-2.5) written out, so no engine-dependent exp). */
const POISSON_CDF = (() => {
	const e = 0.0820849986238988;
	const out = [];
	let p = e;
	let sum = e;
	for (let k = 0; k < 10; k++) {
		out.push(sum);
		p = p * TUSSOCK_LAMBDA / (k + 1);
		sum += p;
	}
	return out;
})();

const fade = (t) => t * t * (3 - 2 * t);
export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const smoothstep = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const lerp = (a, b, t) => a + (b - a) * t;

/** One-call 2D lattice hash for the noise fields. */
export const hashLattice = (seed, ix, iz) => hashU32(Math.imul(ix | 0, 0x8da6b343) ^ Math.imul(iz | 0, 0xd8163841) ^ Math.imul(seed | 0, 0x9e3779b1));

/** Integer-lattice value noise in [0, 1): world-space, seam-free, order independent. */
export function valueNoise(x, z, seed) {
	const ix = Math.floor(x);
	const iz = Math.floor(z);
	const fx = fade(x - ix);
	const fz = fade(z - iz);
	const a = unitFromHash(hashLattice(seed, ix, iz));
	const b = unitFromHash(hashLattice(seed, ix + 1, iz));
	const c = unitFromHash(hashLattice(seed, ix, iz + 1));
	const d = unitFromHash(hashLattice(seed, ix + 1, iz + 1));
	return lerp(lerp(a, b, fx), lerp(c, d, fx), fz);
}

/** Two- or three-octave value fbm, normalised to [0, 1). */
export function fbm(x, z, seed, octaves = 2) {
	let sum = 0;
	let amp = 1;
	let norm = 0;
	let f = 1;
	for (let o = 0; o < octaves; o++) {
		sum += amp * valueNoise(x * f + o * 17.31, z * f - o * 9.17, seed + o * 1013);
		norm += amp;
		amp *= 0.5;
		f *= 2.03;
	}
	return sum / norm;
}

// =====================================================================================================================
// Signed distance helpers (XZ plane)
// =====================================================================================================================

/** Distance from (px, pz) to segment a-b, and the segment parameter t in [0, 1]. */
export function segmentDistance(px, pz, ax, az, bx, bz) {
	const dx = bx - ax;
	const dz = bz - az;
	const len2 = dx * dx + dz * dz;
	const t = len2 > 0 ? clamp01(((px - ax) * dx + (pz - az) * dz) / len2) : 0;
	const qx = ax + dx * t - px;
	const qz = az + dz * t - pz;
	return { d: Math.sqrt(qx * qx + qz * qz), t };
}

/** Distance to an open polyline [[x, z], ...] and the arc length at the closest point. */
export function polylineDistance(px, pz, points) {
	let best = Infinity;
	let along = 0;
	let walked = 0;
	for (let i = 0; i + 1 < points.length; i++) {
		const [ax, az] = points[i];
		const [bx, bz] = points[i + 1];
		const seg = Math.hypot(bx - ax, bz - az);
		const hit = segmentDistance(px, pz, ax, az, bx, bz);
		if (hit.d < best) { best = hit.d; along = walked + hit.t * seg; }
		walked += seg;
	}
	return { d: best, along };
}

/** Flat segment list [ax, az, bx, bz, ...] of a polyline. */
export function polylineSegments(points) {
	const out = [];
	for (let i = 0; i + 1 < points.length; i++) out.push(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]);
	return out;
}

/** Distance to a flat segment list (see polylineSegments). */
export function segmentsDistance(px, pz, segs) {
	let best = Infinity;
	for (let i = 0; i < segs.length; i += 4) {
		const ax = segs[i], az = segs[i + 1], dx = segs[i + 2] - ax, dz = segs[i + 3] - az;
		const len2 = dx * dx + dz * dz;
		const t = len2 > 0 ? clamp01(((px - ax) * dx + (pz - az) * dz) / len2) : 0;
		const qx = ax + dx * t - px;
		const qz = az + dz * t - pz;
		const d2 = qx * qx + qz * qz;
		if (d2 < best) best = d2;
	}
	return Math.sqrt(best);
}

/** Keep only the segments whose AABB, grown by `margin`, overlaps `box`. */
function clipSegments(segs, box, margin) {
	const out = [];
	for (let i = 0; i < segs.length; i += 4) {
		const minX = Math.min(segs[i], segs[i + 2]) - margin, maxX = Math.max(segs[i], segs[i + 2]) + margin;
		const minZ = Math.min(segs[i + 1], segs[i + 3]) - margin, maxZ = Math.max(segs[i + 1], segs[i + 3]) + margin;
		if (minX <= box[1] && maxX >= box[0] && minZ <= box[3] && maxZ >= box[2]) out.push(segs[i], segs[i + 1], segs[i + 2], segs[i + 3]);
	}
	return out;
}

/** Even-odd point in polygon. */
export function pointInPolygon(px, pz, polygon) {
	let inside = false;
	for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
		const [xi, zi] = polygon[i];
		const [xj, zj] = polygon[j];
		if ((zi > pz) !== (zj > pz) && px < ((xj - xi) * (pz - zi)) / (zj - zi) + xi) inside = !inside;
	}
	return inside;
}

/** Signed distance to a closed polygon: negative inside. */
export function polygonSignedDistance(px, pz, polygon) {
	let best = Infinity;
	for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
		const hit = segmentDistance(px, pz, polygon[j][0], polygon[j][1], polygon[i][0], polygon[i][1]);
		if (hit.d < best) best = hit.d;
	}
	return pointInPolygon(px, pz, polygon) ? -best : best;
}

/** Signed distance to an oriented box (centre, half extents along local X/Z, yaw with atan2(dx, dz) facing). */
export function boxSignedDistance(px, pz, cx, cz, hx, hz, yaw = 0) {
	const c = Math.cos(yaw);
	const s = Math.sin(yaw);
	const dx = px - cx;
	const dz = pz - cz;
	// local X = (cos a, -sin a), local Z = (sin a, cos a) (colliders.json convention)
	const lx = dx * c - dz * s;
	const lz = dx * s + dz * c;
	const qx = Math.abs(lx) - hx;
	const qz = Math.abs(lz) - hz;
	const outside = Math.hypot(Math.max(qx, 0), Math.max(qz, 0));
	return outside + Math.min(Math.max(qx, qz), 0);
}

const AABB_INF = Object.freeze([Infinity, -Infinity, Infinity, -Infinity]);
const pointsBounds = (points, pad) => {
	let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
	for (const [x, z] of points) {
		if (x < minX) minX = x;
		if (x > maxX) maxX = x;
		if (z < minZ) minZ = z;
		if (z > maxZ) maxZ = z;
	}
	return [minX - pad, maxX + pad, minZ - pad, maxZ + pad];
};
const overlaps = (a, b) => a[0] <= b[1] && a[1] >= b[0] && a[2] <= b[3] && a[3] >= b[2];

// =====================================================================================================================
// Rules: compiled primitives and point sampling
// =====================================================================================================================

/**
 * Zone spec defaults (open meadow). Densities are clumps/m^2 at generation (Ultra) density, before the cluster mask
 * (spec §5.2). Mix = S, M, T, R fractions.
 */
export const MEADOW = Object.freeze({
	density: 3.0,
	mix: Object.freeze([0.55, 0.35, 0.10, 0]),
	dryness: 0.15,
	shade: 0,
	maxHeight: 1.25,
	heightScale: 1,
	cluster: 1,
	flowerDrift: 1 / 150,
	flowerSingle: 0.02,
	flowers: Object.freeze({ yellow: 0.26, white: 0.26, orange: 0.16, red: 0.12, pink: 0.1, violet: 0.04, yarrow: 0.06, blue: 0 }),
	clover: 1 / 110,
	plantHeight: 1,
});

const PATH_DEFAULTS = Object.freeze({ edgeStrip: 0.25, fade: 1.2, verge: [0.6, 2.4], vergeBoost: 1.3, jitter: 0.35, trampled: false });

/**
 * Compile a rules DTO into fast primitives. The DTO is plain data (hashable); `masks` may carry decoded terrain
 * control maps (typed arrays). Unknown keys are ignored.
 * @param {import("./grass-placement.d.mts").GrassRulesData} data
 */
export function compileRules(data) {
	if (!data || data.schema !== "xexoria.grass-rules/1") throw new Error("Grass rules must use schema xexoria.grass-rules/1");
	const seed = (data.seed ?? 20261002) >>> 0;
	const base = { ...MEADOW, ...(data.base ?? {}), flowers: { ...MEADOW.flowers, ...(data.base?.flowers ?? {}) } };
	const prims = [];
	for (const path of data.paths ?? []) {
		const p = { ...PATH_DEFAULTS, ...path };
		const reach = p.width / 2 + p.verge[1] + p.jitter + 0.5;
		prims.push({ type: "path", id: p.id, points: p.points, segs: polylineSegments(p.points), reach, half: p.width / 2, p,
			bounds: pointsBounds(p.points, reach) });
	}
	for (const water of data.water ?? []) {
		const bank = water.bank ?? [0.2, 1.6];
		const blue = water.blue ?? [0.6, 2.5];
		const reach = Math.max(bank[1], blue[1]) + 0.5;
		if (water.points) prims.push({ type: "water", id: water.id, points: water.points, segs: polylineSegments(water.points), reach: water.width / 2 + reach, half: water.width / 2, bank, blue, noReeds: water.noReeds === true,
			bounds: pointsBounds(water.points, water.width / 2 + reach) });
		else prims.push({ type: "pool", id: water.id, x: water.center[0], z: water.center[1], r: water.radius, bank, blue, noReeds: water.noReeds === true,
			bounds: [water.center[0] - water.radius - reach, water.center[0] + water.radius + reach, water.center[1] - water.radius - reach, water.center[1] + water.radius + reach] });
	}
	for (const o of data.obstacles ?? []) {
		const ring = o.ring ?? 0;
		const pad = o.pad ?? 0.08;
		const reach = Math.max(ring, pad) + 0.5;
		if (o.shape === "circle") prims.push({ type: "obstacle", shape: "circle", id: o.id, kind: o.kind, x: o.x, z: o.z, r: o.r, pad, ring, boost: o.boost ?? 1.5, ringMix: o.ringMix ?? null, flowers: o.flowers ?? 0,
			bounds: [o.x - o.r - reach, o.x + o.r + reach, o.z - o.r - reach, o.z + o.r + reach] });
		else if (o.shape === "box") {
			const ext = Math.hypot(o.hx, o.hz) + reach;
			prims.push({ type: "obstacle", shape: "box", id: o.id, kind: o.kind, x: o.x, z: o.z, hx: o.hx, hz: o.hz, yaw: o.yaw ?? 0, pad, ring, boost: o.boost ?? 1.5, ringMix: o.ringMix ?? null, flowers: o.flowers ?? 0,
				bounds: [o.x - ext, o.x + ext, o.z - ext, o.z + ext] });
		} else if (o.shape === "polygon") prims.push({ type: "obstacle", shape: "polygon", id: o.id, kind: o.kind, polygon: o.polygon, pad, ring, boost: o.boost ?? 1.5, ringMix: o.ringMix ?? null, flowers: o.flowers ?? 0,
			bounds: pointsBounds(o.polygon, reach) });
	}
	for (const c of data.clearings ?? []) {
		const rx = c.rx ?? c.r;
		const rz = c.rz ?? c.r;
		prims.push({ type: "clearing", id: c.id, x: c.x, z: c.z, rx, rz, coreDensity: c.coreDensity ?? 0.6, coreMaxHeight: c.coreMaxHeight ?? 0.32,
			borderBoost: c.borderBoost ?? 1.33, flowers: c.flowers !== false, bounds: [c.x - rx * 1.1 - 1, c.x + rx * 1.1 + 1, c.z - rz * 1.1 - 1, c.z + rz * 1.1 + 1] });
	}
	for (const d of data.discs ?? []) prims.push({ type: "disc", id: d.id, x: d.x, z: d.z, r: d.r, factor: d.factor ?? 0.3, shortOnly: d.shortOnly !== false, ring: d.ring ?? 0,
		bounds: [d.x - d.r - (d.ring ?? 0) - 0.5, d.x + d.r + (d.ring ?? 0) + 0.5, d.z - d.r - (d.ring ?? 0) - 0.5, d.z + d.r + (d.ring ?? 0) + 0.5] });
	for (const a of data.arenas ?? []) prims.push({ type: "arena", id: a.id, x: a.x, z: a.z, r: a.r, flowerHeight: a.flowerHeight ?? 0.35, flowers: a.flowers ?? { white: 0.6, yellow: 0.4 },
		edge: a.edge ?? 0.6, bounds: [a.x - a.r - 1, a.x + a.r + 1, a.z - a.r - 1, a.z + a.r + 1] });
	for (const w of data.walls ?? []) prims.push({ type: "wall", id: w.id, points: w.points, segs: polylineSegments(w.points), reach: (w.toe ?? 1.5) + (w.reach ?? 40), side: w.side ?? 1, toe: w.toe ?? 1.5, boost: w.boost ?? 1.4,
		bounds: pointsBounds(w.points, (w.toe ?? 1.5) + (w.reach ?? 40)) });
	const zones = (data.zones ?? []).map((zone, index) => ({ ...zone, index, priority: zone.priority ?? index,
		bounds: zone.polygon ? pointsBounds(zone.polygon, (zone.outsideBand?.[1] ?? 0) + (zone.edge ?? 1) + 1) : zone.ring ? [zone.ring.x - zone.ring.r1 - 1, zone.ring.x + zone.ring.r1 + 1, zone.ring.z - zone.ring.r1 - 1, zone.ring.z + zone.ring.r1 + 1]
			: zone.circle ? [zone.circle.x - zone.circle.r - 1, zone.circle.x + zone.circle.r + 1, zone.circle.z - zone.circle.r - 1, zone.circle.z + zone.circle.r + 1] : AABB_INF,
		spec: { ...zone.spec, flowers: zone.spec?.flowers ? { ...zone.spec.flowers } : undefined } })).sort((a, b) => b.priority - a.priority);
	const noGo = (data.noGo ?? []).map(r => ({ ...r, fade: r.fade ?? 2 }));
	const masks = (data.masks ?? []).map(m => ({ ...m, size: m.n + 1, step: 64 / m.n }));
	return {
		id: data.id ?? "rules", seed, domain: data.domain, base, prims, zones, noGo, masks,
		maskUse: { paths: true, dirt: true, dryLush: true, ao: true, ...(data.maskUse ?? {}) },
		ground: data.ground ?? { kind: "flat", tint: [0.9, 0.92, 0.86] },
		flowerSites: data.flowerSites ?? [],
		dryMacro: data.dryMacro ?? 0.14,
		hueMacro: data.hueMacro ?? 6,
		data,
	};
}

/** Primitives whose influence can reach the AABB [minX, maxX, minZ, maxZ]. */
export function primitivesFor(rules, box) {
	return {
		prims: rules.prims.filter(p => overlaps(p.bounds, box)).map(p => (p.segs && p.type !== "wall" ? { ...p, segs: clipSegments(p.segs, box, p.reach) } : p))
			.filter(p => !p.segs || p.segs.length > 0),
		zones: rules.zones.filter(z => overlaps(z.bounds, box)),
		noGo: rules.noGo.filter(r => overlaps([r.minX - r.fade, r.maxX + r.fade, r.minZ - r.fade, r.maxZ + r.fade], box)),
		masks: rules.masks.filter(m => overlaps([m.minX, m.minX + 64, m.minZ, m.minZ + 64], box)),
	};
}

/** Bilinear sample of a terrain control map (RGB bytes, row 0 = north) at world (x, z); returns [r, g, b] / 255. */
export function sampleMask(mask, channels, x, z) {
	const fc = (x - mask.minX) / mask.step;
	const fr = (mask.minZ + 64 - z) / mask.step;
	if (fc < 0 || fr < 0 || fc > mask.n || fr > mask.n) return null;
	const c0 = Math.min(mask.n - 1, Math.floor(fc));
	const r0 = Math.min(mask.n - 1, Math.floor(fr));
	const tx = fc - c0;
	const tz = fr - r0;
	const size = mask.size;
	const ch = mask.channels ?? 3;
	const out = [0, 0, 0];
	for (let k = 0; k < 3; k++) {
		const v00 = channels[(r0 * size + c0) * ch + k];
		const v10 = channels[(r0 * size + c0 + 1) * ch + k];
		const v01 = channels[((r0 + 1) * size + c0) * ch + k];
		const v11 = channels[((r0 + 1) * size + c0 + 1) * ch + k];
		out[k] = lerp(lerp(v00, v10, tx), lerp(v01, v11, tx), tz) / 255;
	}
	return out;
}

/** In-place mix toward a target class mix. */
const mixToward = (mix, target, t) => { for (let i = 0; i < 4; i++) mix[i] += (target[i] - mix[i]) * t; return mix; };
const setMix = (mix, target) => { for (let i = 0; i < 4; i++) mix[i] = target[i]; return mix; };
const MIX_SHORT = Object.freeze([1, 0, 0, 0]);
const MIX_TALL = Object.freeze([0.15, 0.4, 0.45, 0]);
const MIX_REEDS = Object.freeze([0.18, 0.12, 0, 0.7]);
const MIX_VERGE = Object.freeze([0.4, 0.45, 0.15, 0]);
const MIX_CLEARING_EDGE = Object.freeze([0.7, 0.3, 0, 0]);
const MIX_CLEARING_BORDER = Object.freeze([0.3, 0.45, 0.25, 0]);

/** A reusable ground sample (sampleGround writes into it, so generation loops allocate nothing per point). */
export function createGroundSample() {
	return {
		zone: "meadow", density: 0, mix: [0, 0, 0, 0], dryness: 0, shade: 0, maxHeight: 0, heightScale: 1, cluster: 1,
		flowerDrift: 0, flowerSingle: 0, flowers: MEADOW.flowers, clover: 0, plantHeight: 1,
		keepGrass: 1, keepPlants: 1, boost: 1, bank: 0, blue: 0, vergeWear: 0, arena: false,
		maxPlantHeight: Infinity, noReeds: false, pathEdge: Infinity,
	};
}

/**
 * Ground sample at (x, z): the zone spec after every exclusion, ring and mask (spec §5.2-5.3). `keepGrass` and
 * `keepPlants` are the density multipliers for tufts and for flowers/clover (arenas keep flowers but no grass).
 * @param {ReturnType<typeof compileRules>} rules
 * @param {ReturnType<typeof primitivesFor>} [local] primitives pre-filtered for the patch (optional)
 * @param {ReturnType<typeof createGroundSample>} [out] reused result object
 */
export function sampleGround(rules, x, z, local, out) {
	const L = local ?? rules;
	const zonesList = L.zones ?? rules.zones;
	let spec = rules.base;
	let zoneId = "meadow";
	for (const zone of zonesList) {
		if (x < zone.bounds[0] || x > zone.bounds[1] || z < zone.bounds[2] || z > zone.bounds[3]) continue;
		let inside = false;
		if (zone.polygon) {
			// Wobbly polygon edge (+-edge m) so zone borders never read as straight lines.
			const edge = zone.edge ?? 1;
			const wobble = (valueNoise(x / 4.3, z / 4.3, rules.seed + 77) - 0.5) * 2 * edge;
			const distance = polygonSignedDistance(x, z, zone.polygon);
			inside = zone.outsideBand ? distance >= zone.outsideBand[0] && distance <= zone.outsideBand[1] : distance + wobble < 0;
		} else if (zone.circle) inside = Math.hypot(x - zone.circle.x, z - zone.circle.z) < zone.circle.r;
		else if (zone.ring) { const d = Math.hypot(x - zone.ring.x, z - zone.ring.z); inside = d >= zone.ring.r0 && d <= zone.ring.r1; }
		if (inside) { spec = zone.merged ?? (zone.merged = mergeSpec(rules.base, zone.spec)); zoneId = zone.id; break; }
	}
	const s = out ?? createGroundSample();
	s.zone = zoneId;
	s.density = spec.density; setMix(s.mix, spec.mix); s.dryness = spec.dryness; s.shade = spec.shade;
	s.maxHeight = spec.maxHeight; s.heightScale = spec.heightScale; s.cluster = spec.cluster;
	s.tipHex = spec.tipHex ?? null;
	s.flowerDrift = spec.flowerDrift; s.flowerSingle = spec.flowerSingle; s.flowers = spec.flowers; s.clover = spec.clover; s.plantHeight = spec.plantHeight ?? 1;
	s.keepGrass = 1; s.keepPlants = 1; s.boost = 1; s.bank = 0; s.blue = 0; s.vergeWear = 0; s.arena = false;
	s.maxPlantHeight = Infinity; s.noReeds = false; s.pathEdge = Infinity;
	// --- ownership (city) ---
	for (const r of L.noGo ?? rules.noGo) {
		const inside = Math.min(x - r.minX, r.maxX - x, z - r.minZ, r.maxZ - z);
		if (inside > -r.fade) {
			const k = 1 - smoothstep(-r.fade, 0, inside);
			s.keepGrass *= k; s.keepPlants *= k;
			if (k <= 0) return s;
		}
	}
	// --- analytic primitives ---
	const prims = L.prims ?? rules.prims;
	for (const p of prims) {
		if (x < p.bounds[0] || x > p.bounds[1] || z < p.bounds[2] || z > p.bounds[3]) continue;
		switch (p.type) {
			case "water": case "pool": {
				const d = p.type === "water" ? segmentsDistance(x, z, p.segs) - p.half : Math.hypot(x - p.x, z - p.z) - p.r;
				if (d < 0.15) { s.keepGrass = 0; s.keepPlants = 0; return s; }
				if (d < p.bank[1]) {
					const bank = 1 - smoothstep(p.bank[0], p.bank[1], d);
					if (bank > s.bank) s.bank = bank;
					if (p.noReeds) s.noReeds = true;
					s.dryness *= 1 - bank;
				}
				if (d >= p.blue[0] && d <= p.blue[1]) s.blue = Math.max(s.blue, 1);
				break;
			}
			case "obstacle": {
				let d;
				if (p.shape === "circle") d = Math.hypot(x - p.x, z - p.z) - p.r;
				else if (p.shape === "box") d = boxSignedDistance(x, z, p.x, p.z, p.hx, p.hz, p.yaw);
				else d = polygonSignedDistance(x, z, p.polygon);
				if (d < p.pad) { s.keepGrass = 0; s.keepPlants = 0; return s; }
				if (p.ring > 0 && d < p.ring) {
					const t = 1 - smoothstep(p.ring * 0.4, p.ring, d);
					s.boost *= lerp(1, p.boost, t);
					mixToward(s.mix, p.ringMix ?? MIX_TALL, t * 0.8);
					s.dryness *= 1 - 0.6 * t;
					if (p.flowers > 0) s.flowerSingle += p.flowers * t;
				}
				break;
			}
			case "path": {
				const centre = segmentsDistance(x, z, p.segs);
				if (centre - p.half > p.p.verge[1] + p.p.jitter + 0.4) break;
				// Ragged edge: jitter the half width with a 7 m and a 2 m noise (+-jitter m).
				const n = 0.65 * (valueNoise(x / 7, z / 7, rules.seed + 11) - 0.5) + 0.35 * (valueNoise(x / 2, z / 2, rules.seed + 23) - 0.5);
				const d = centre - p.half - n * 2 * p.p.jitter;
				if (d < s.pathEdge) s.pathEdge = d;
				if (d < -p.p.edgeStrip) {
					if (!p.p.trampled) { s.keepGrass = 0; s.keepPlants = 0; return s; }
					s.keepGrass *= 0.17; s.keepPlants = 0; setMix(s.mix, MIX_SHORT); s.dryness = Math.max(s.dryness, 0.5); s.maxHeight = Math.min(s.maxHeight, 0.34);
				} else if (d < 0) {
					s.keepGrass *= p.p.trampled ? 0.25 : 0.2; s.keepPlants = 0; setMix(s.mix, MIX_SHORT); s.dryness = Math.max(s.dryness, 0.5); s.maxHeight = Math.min(s.maxHeight, 0.36);
				} else if (d < p.p.fade) {
					const t = smoothstep(0, p.p.fade, d);
					s.keepGrass *= lerp(0.18, 1, t);
					s.keepPlants *= t * t;
					mixToward(s.mix, MIX_SHORT, (1 - t) * 0.6);
					s.dryness = Math.max(s.dryness, lerp(0.4, s.dryness, t));
				}
				if (d >= p.p.verge[0] - 0.4 && d < p.p.verge[1] + 0.4) {
					const t = smoothstep(p.p.verge[0] - 0.4, p.p.verge[0], d) * (1 - smoothstep(p.p.verge[1], p.p.verge[1] + 0.4, d));
					s.boost *= lerp(1, p.p.vergeBoost, t);
					mixToward(s.mix, MIX_VERGE, t * 0.7);
					s.vergeWear = Math.max(s.vergeWear, t);
					s.flowerSingle += 0.02 * t;
				}
				break;
			}
			case "clearing": {
				const q = Math.hypot((x - p.x) / p.rx, (z - p.z) / p.rz);
				if (q < 0.6) {
					s.keepGrass *= p.coreDensity / Math.max(0.01, s.density); setMix(s.mix, MIX_SHORT); s.maxHeight = Math.min(s.maxHeight, p.coreMaxHeight);
					s.keepPlants = 0; s.dryness = Math.max(s.dryness, 0.3); s.cluster = Math.min(s.cluster, 0.5);
				} else if (q < 0.85) {
					const t = smoothstep(0.6, 0.85, q);
					s.keepGrass *= lerp(p.coreDensity / Math.max(0.01, s.density), 1, t); mixToward(s.mix, MIX_CLEARING_EDGE, 1 - t * 0.5);
					s.maxHeight = Math.min(s.maxHeight, lerp(p.coreMaxHeight, 0.7, t)); s.keepPlants *= t * t;
				} else if (q < 1.05) {
					const t = 1 - Math.abs(q - 0.95) / 0.1;
					s.boost *= lerp(1, p.borderBoost, clamp01(t)); mixToward(s.mix, MIX_CLEARING_BORDER, clamp01(t));
					if (p.flowers) s.flowerSingle += 0.05 * clamp01(t);
				}
				break;
			}
			case "disc": {
				const d = Math.hypot(x - p.x, z - p.z);
				if (d < p.r) {
					s.keepGrass *= p.factor; if (p.shortOnly) { setMix(s.mix, MIX_SHORT); s.maxHeight = Math.min(s.maxHeight, 0.36); }
					s.keepPlants *= p.factor;
				} else if (p.ring > 0 && d < p.r + p.ring) {
					s.boost *= 1.4; mixToward(s.mix, MIX_TALL, 0.6);
				}
				break;
			}
			case "arena": {
				const d = Math.hypot(x - p.x, z - p.z);
				if (d < p.r) {
					// Arena marking: no grass tufts (ground telegraphs stay readable); low flowers only.
					const t = smoothstep(p.r - p.edge, p.r, d);
					s.keepGrass *= t;
					s.arena = t < 0.5;
					s.maxPlantHeight = Math.min(s.maxPlantHeight, p.flowerHeight);
					s.flowers = p.flowers;
					s.clover = 0;
					s.flowerDrift = Math.max(s.flowerDrift, 1 / 40);
				}
				break;
			}
			case "wall": {
				const dist = segmentsDistance(x, z, p.segs);
				const side = wallSide(x, z, p.points) * p.side;
				if (side < 0) { s.keepGrass = 0; s.keepPlants = 0; return s; }
				if (dist < p.toe) {
					const t = 1 - smoothstep(0.2, p.toe, dist);
					s.boost *= lerp(1, p.boost, t); mixToward(s.mix, MIX_TALL, t * 0.8);
				}
				break;
			}
			default: break;
		}
	}
	// --- terrain control maps (density masks) ---
	for (const m of L.masks ?? rules.masks) {
		if (x < m.minX || x > m.minX + 64 || z < m.minZ || z > m.minZ + 64) continue;
		const splat = sampleMask(m, m.splat, x, z);
		const data = m.data ? sampleMask(m, m.data, x, z) : null;
		if (!splat) continue;
		const [lush, dry, dirt] = splat;
		const mud = Math.max(0, 1 - lush - dry - dirt);
		const sdf = data ? data[0] * 6 - 2 : 4;
		const use = rules.maskUse;
		if (use.paths && data) {
			if (sdf < -0.25) { s.keepGrass = 0; s.keepPlants = 0; return s; }
			if (sdf < 1.2) { const t = smoothstep(-0.25, 1.2, sdf); s.keepGrass *= lerp(0.15, 1, t); s.keepPlants *= t * t; mixToward(s.mix, MIX_SHORT, (1 - t) * 0.6); }
		}
		const dirtAway = use.paths ? 1 : smoothstep(1.2, 2.2, sdf);
		if (use.dirt) s.keepGrass *= 1 - smoothstep(0.3, 0.7, dirt * dirtAway);
		if (use.dryLush) {
			s.dryness = clamp01(s.dryness + dry * 0.55 - lush * 0.08);
			s.keepGrass *= (0.82 + 0.3 * lush) * (1 - 0.6 * mud);
			if (mud > 0.25) mixToward(s.mix, MIX_REEDS, smoothstep(0.25, 0.7, mud) * 0.6);
		}
		if (use.ao && data) s.shade = Math.max(s.shade, clamp01((1 - data[2]) * 1.6));
		break;
	}
	// --- banks (reeds + sedge, blue flowers) ---
	if (s.bank > 0) {
		s.keepGrass *= lerp(1, 2.2 / Math.max(0.5, s.density), s.bank * 0.5);
		if (!s.noReeds) mixToward(s.mix, MIX_REEDS, s.bank * 0.85);
		if(rules.data.blueprint){s.tipHex='#4f783d';s.shade=Math.max(s.shade,.25);s.maxHeight=Math.min(s.maxHeight,.9);}
	}
	if (s.blue > 0 && !s.noReeds) {
		s.flowers = { ...s.flowers, blue: (s.flowers.blue ?? 0) + 1.2 };
		s.flowerSingle += 0.05;
	}
	return s;
}

/** Side of a polyline: +1 left of the walking direction, -1 right (2D cross product of the nearest segment). */
export function wallSide(x, z, points) {
	let best = Infinity;
	let sign = 1;
	for (let i = 0; i + 1 < points.length; i++) {
		const [ax, az] = points[i];
		const [bx, bz] = points[i + 1];
		const hit = segmentDistance(x, z, ax, az, bx, bz);
		if (hit.d < best) {
			best = hit.d;
			const cross = (bx - ax) * (z - az) - (bz - az) * (x - ax);
			sign = cross >= 0 ? 1 : -1;
		}
	}
	return sign;
}

function mergeSpec(base, over) {
	if (!over) return base;
	const out = { ...base };
	for (const [key, value] of Object.entries(over)) if (value !== undefined) out[key] = value;
	if (over.flowers) out.flowers = { ...over.flowers };
	return out;
}

/** Final tuft density (clumps/m^2) at a sample, before the cluster mask. */
export const grassDensity = (s) => Math.max(0, s.density * s.keepGrass * s.boost);

// =====================================================================================================================
// Clustering, size and colour fields
// =====================================================================================================================

let maskMeanCache = null;
/** Mean of the raw cluster mask over a large area (computed once, deterministic). */
export function clusterMaskMean() {
	if (maskMeanCache !== null) return maskMeanCache;
	let sum = 0;
	let n = 0;
	for (let i = 0; i < 160; i++) for (let j = 0; j < 160; j++) { sum += rawClusterMask(1, i * 1.37 - 110, j * 1.41 - 112); n++; }
	maskMeanCache = sum / n;
	return maskMeanCache;
}

function rawClusterMask(seed, x, z) {
	// 1.5 m domain warp, 7.5 m patches, 2 octaves (spec §5.4).
	const wx = x + 1.5 * (valueNoise(x / 5.1, z / 5.1, seed + 101) * 2 - 1);
	const wz = z + 1.5 * (valueNoise(x / 5.1 + 17.3, z / 5.1 - 4.1, seed + 202) * 2 - 1);
	const n = fbm(wx / 7.5, wz / 7.5, seed + 303, 2);
	// Sharper than spec §5.4 (0.15 + 0.85 M over 0.38..0.62): the owner samples show bare ground between clump
	// groups, and the carpet gate (>= 25 % of 2 m bins with <= 1 clump) needs gaps near 0.06x the mean.
	return 0.03 + 0.97 * smoothstep(0.42, 0.6, n);
}

/** Cluster multiplier at (x, z): patches ~1.9x, gaps ~0.06x, mean 1 (strength 0 = uniform). */
export function clusterMask(seed, x, z, strength = 1) {
	const m = rawClusterMask(seed, x, z) / clusterMaskMean();
	return lerp(1, m, clamp01(strength));
}

/** 6 m size field: +-18 %. */
export const sizeField = (seed, x, z) => 1 + 0.18 * (valueNoise(x / 6, z / 6, seed + 404) * 2 - 1);

/** sRGB hex -> linear rgb. */
export function linearFromHex(hex) {
	const h = hex.replace("#", "");
	return [0, 2, 4].map(i => srgbToLinear(parseInt(h.slice(i, i + 2), 16) / 255));
}
export const srgbToLinear = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
export const linearToSrgb = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);

/** Rotate an rgb colour's hue by `degrees` (YIQ rotation; luminance preserved). */
export function rotateHue(rgb, degrees) {
	const [r, g, b] = rgb;
	const y = 0.299 * r + 0.587 * g + 0.114 * b;
	const i = 0.596 * r - 0.274 * g - 0.322 * b;
	const q = 0.211 * r - 0.523 * g + 0.312 * b;
	const a = (degrees * Math.PI) / 180;
	const c = Math.cos(a);
	const s = Math.sin(a);
	const i2 = i * c - q * s;
	const q2 = i * s + q * c;
	return [y + 0.956 * i2 + 0.621 * q2, y - 0.272 * i2 - 0.647 * q2, y - 1.106 * i2 + 1.703 * q2];
}

/** Reference tip colour (linear) the hue rotation is measured against (#9cbc58). */
const TIP_REFERENCE = linearFromHex("#9cbc58");
const DRY_TINT = Object.freeze([1.2, 1.05, 0.7]);
const SHADE_TINT = Object.freeze([0.88, 0.95, 1.06]);

/**
 * Linear tip-tint multiplier for the atlas colour (spec §5.6): dryness, shade, value and hue jitter, macro hue.
 * Channels are clamped to [0.55, 1.5]; the shader clamps the final albedo.
 */
export function tipTint(dryness, shade, value, hueDegrees) {
	const d = clamp01(dryness);
	const sh = clamp01(shade);
	let m = [lerp(1, DRY_TINT[0], d), lerp(1, DRY_TINT[1], d), lerp(1, DRY_TINT[2], d)];
	m = m.map((v, i) => v * lerp(1, SHADE_TINT[i], sh) * value);
	if (hueDegrees) {
		const rotated = rotateHue(TIP_REFERENCE, hueDegrees);
		m = m.map((v, i) => v * clamp(rotated[i] / TIP_REFERENCE[i], 0.7, 1.4));
	}
	return m.map(v => clamp(v, 0.55, 1.5));
}

// =====================================================================================================================
// Ground colour model (root band). The legacy ground (environment.ts createGroundAndPath + the c7/c8 cell GLBs)
// carries a vertex tint from groundVariation(x, z), plus verge and landmark wear in the live cells
// (assets/blender/world/build_sunmeadow_cells.py world_uv_and_color). The shader multiplies this tint by the ground
// texture sampled at the fragment, the terrain albedoColor (weather) and the meadow macro, i.e. the ground's own chain.
// =====================================================================================================================

/** environment.ts groundVariation (Math.sin is fine here: this runs once per instance, outside the hash loops). */
export function groundVariation(x, z) {
	const value = 0.55 + 0.14 * Math.sin(x * 0.17 + 1.7) * Math.cos(z * 0.15) + 0.08 * Math.sin(x * 0.36 - z * 0.26 + 3.1) + 0.03 * Math.cos(x * 0.68 + z * 0.52);
	return clamp01(value);
}

/** Vertex tint (linear rgb) of the legacy ground meshes at (x, z). */
export function legacyGroundTint(ground, x, z) {
	const v = groundVariation(x, z);
	let r = lerp(0.82, 0.98, v);
	let g = lerp(0.84, 0.99, v);
	let b = lerp(0.79, 0.94, v);
	const cell = ground.cells?.find(c => x >= c.bounds[0] && x <= c.bounds[1] && z >= c.bounds[2] && z <= c.bounds[3]);
	if (cell && ground.route) {
		const shoulder = Math.abs(x - routeXAtZ(ground.route, z));
		let edge = Math.max(0, 1 - Math.abs(shoulder - 4.3) / 3.3);
		edge *= Math.min(1, Math.max(0, (-z - 64) / 9));
		let wear = edge * 0.28;
		for (const landmark of ground.landmarks ?? []) {
			const radius = landmark.kind === "trail_marker" ? 4.5 : 3.5;
			const d = Math.hypot(x - landmark.x, z - landmark.z);
			wear = Math.max(wear, Math.max(0, 1 - d / radius) ** 2 * 0.35);
		}
		r = Math.min(1, r + 0.1 * wear);
		g *= 1 - 0.3 * wear;
		b *= 1 - 0.2 * wear;
	}
	return [r, g, b];
}

/** build_sunmeadow_cells.route_x_at_z: linear interpolation of the authored route by z. */
export function routeXAtZ(points, z) {
	for (let i = 0; i + 1 < points.length; i++) {
		const [x0, z0] = points[i];
		const [x1, z1] = points[i + 1];
		if (Math.min(z0, z1) <= z && z <= Math.max(z0, z1)) return x0 + (x1 - x0) * ((z - z0) / (z1 - z0 || 1));
	}
	let best = points[0];
	for (const p of points) if (Math.abs(p[1] - z) < Math.abs(best[1] - z)) best = p;
	return best[0];
}

/** Ground colour at the root: a tint (texture mode) or a full linear colour (mean mode). */
export function groundAt(rules, x, z) {
	const g = rules.ground;
	if (g.kind === "legacy") return legacyGroundTint(g, x, z);
	if (g.kind === "mean") return g.color.slice();
	return (g.tint ?? [0.9, 0.92, 0.86]).slice();
}

// =====================================================================================================================
// Generation
// =====================================================================================================================

const SALT = Object.freeze({ slot: 0x51a7, child: 0xc41d, single: 0x5191, r: 0x7e57, drift: 0xd71f, flower: 0xf10e, clover: 0xc10e, site: 0x517e, colour: 0xc0105 });

/**
 * One instance record. Positions in metres; tint/ground linear; `col` is the atlas column offset (tufts: even bundle
 * pair 0/2/4/6; flowers: head column 0..7; clover: leaf variant 0/1); `opt` turns on optional mesh parts.
 * @typedef {{ kind: "tuft"|"flower"|"clover", x: number, y: number, z: number, yaw: number, height: number, width: number,
 *   col: number, mirror: 0|1, opt: 0|1, r: number, tint: number[], ground: number[], ao: number, wind: number }} GrassInstance
 */

function pickClass(mix, u) {
	let acc = 0;
	const total = mix[0] + mix[1] + mix[2] + mix[3] || 1;
	for (let i = 0; i < 4; i++) {
		acc += mix[i] / total;
		if (u < acc) return i;
	}
	return 0;
}

function bundlePair(cls, dryness, rng) {
	if (cls === 3) return BUNDLE_PAIRS.sedge;
	if (dryness > 0.42 && rng.next() < smoothstep(0.42, 0.75, dryness)) return BUNDLE_PAIRS.dry;
	if (cls === 2) return rng.next() < 0.65 ? BUNDLE_PAIRS.tall : BUNDLE_PAIRS.dry;
	if (cls === 1) return rng.next() < 0.55 ? BUNDLE_PAIRS.lush : BUNDLE_PAIRS.tall;
	return BUNDLE_PAIRS.lush;
}

function macroHue(rules, x, z) {
	return (fbm(x / 26, z / 26, rules.seed + 909, 2) - 0.5) * 2 * rules.hueMacro;
}
function macroDry(rules, x, z) {
	return (fbm(x / 21, z / 21, rules.seed + 808, 2) - 0.5) * 2 * rules.dryMacro;
}

/**
 * Generate the tuft instances of patch (i, j): tussocks from the world slot grid (parents owned by this patch) plus
 * gap singles, sorted by the thinning key r. Deterministic for (rules, i, j).
 * @param {ReturnType<typeof compileRules>} rules
 */
export function generateTuftPatch(rules, i, j, opts = {}) {
	const x0 = i * PATCH_M;
	const z0 = j * PATCH_M;
	const box = [x0 - 3, x0 + PATCH_M + 3, z0 - 3, z0 + PATCH_M + 3];
	const local = primitivesFor(rules, box);
	const out = [];
	const seed = rules.seed;
	const slotArea = SLOT_M * SLOT_M;
	const s = createGroundSample();
	const sChild = createGroundSample();
	const placed = new Float64Array((TUSSOCK_MAX + 3) * 2);
	const gx0 = Math.floor(x0 / SLOT_M) - 1;
	const gz0 = Math.floor(z0 / SLOT_M) - 1;
	const gx1 = Math.ceil((x0 + PATCH_M) / SLOT_M) + 1;
	const gz1 = Math.ceil((z0 + PATCH_M) / SLOT_M) + 1;
	for (let gx = gx0; gx <= gx1; gx++) {
		for (let gz = gz0; gz <= gz1; gz++) {
			const rng = createRng(hashInts(seed, gx, gz, SALT.slot, GRASS_GEN_VERSION));
			const px = (gx + 0.12 + 0.76 * rng.next()) * SLOT_M;
			const pz = (gz + 0.12 + 0.76 * rng.next()) * SLOT_M;
			if (px < x0 || px >= x0 + PATCH_M || pz < z0 || pz >= z0 + PATCH_M) continue;
			sampleGround(rules, px, pz, local, s);
			if (s.keepGrass <= 0) continue;
			const dens = grassDensity(s) * clusterMask(seed, px, pz, s.cluster);
			const p = (TUSSOCK_FILL * dens * slotArea) / TUSSOCK_MEAN;
			const u = rng.next();
			if (u >= p) continue;
			// Saturated slots (p > 1) grow bigger tussocks instead of more parents.
			let count = 1 + Math.min(TUSSOCK_MAX - 1, rng.poisson());
			if (p > 1) count = Math.min(TUSSOCK_MAX + 2, Math.round(count * Math.min(p, 1.8)));
			const cls = pickClass(s.mix, rng.next());
			const rT = unitFromHash(hashInts(seed, gx, gz, SALT.r));
			const yaw0 = rng.next() * Math.PI * 2;
			const tussockValue = 1 + (rng.next() - 0.5) * 0.1;
			const tussockDry = (rng.next() - 0.5) * 0.16;
			const fields = { dry: macroDry(rules, px, pz), hue: macroHue(rules, px, pz), size: sizeField(seed, px, pz) };
			const pair = bundlePair(cls, s.dryness + fields.dry + tussockDry, rng);
			const sigma = cls === 2 ? 0.36 : cls === 3 ? 0.3 : 0.28;
			let placedCount = 0;
			for (let k = 0; k < count; k++) {
				// Up to three tries per child to honour the 0.12 m minimum spacing (spec §5.4).
				let cx = px, cz = pz, ok = false;
				for (let attempt = 0; attempt < 3 && !ok; attempt++) {
					cx = k === 0 ? px + rng.normal() * 0.04 : px + rng.normal() * sigma;
					cz = k === 0 ? pz + rng.normal() * 0.04 : pz + rng.normal() * sigma;
					ok = true;
					for (let q = 0; q < placedCount; q++) {
						const dx = placed[q * 2] - cx, dz = placed[q * 2 + 1] - cz;
						if (dx * dx + dz * dz < 0.0144) { ok = false; break; }
					}
				}
				if (!ok) continue;
				const sc = sampleGround(rules, cx, cz, local, sChild);
				if (sc.keepGrass <= 0) continue;
				if (k > 0 && rng.next() > clamp01(sc.keepGrass * sc.boost / Math.max(0.05, s.keepGrass * s.boost)) + 0.05) continue;
				placed[placedCount * 2] = cx; placed[placedCount * 2 + 1] = cz; placedCount++;
				const childCls = k === 0 ? cls : rng.next() < 0.8 ? cls : pickClass(sc.mix, rng.next());
				out.push(makeTuft(rules, sc, childCls, k === 0 ? pair : (childCls === cls ? pair : bundlePair(childCls, sc.dryness, rng)), cx, cz,
					yaw0 + (k === 0 ? 0 : rng.normal() * 0.7), Math.min(0.9999, rT + 0.004 * k), k === 0 ? 1.1 : 0.85 + 0.12 * rng.next(), tussockValue, tussockDry, rng, dens, fields));
			}
		}
	}
	// Singles: ~10 % of the zone density, without the cluster mask, to sprinkle the gaps.
	const sx0 = Math.floor(x0 / SINGLES_M);
	const sz0 = Math.floor(z0 / SINGLES_M);
	const sx1 = Math.ceil((x0 + PATCH_M) / SINGLES_M);
	const sz1 = Math.ceil((z0 + PATCH_M) / SINGLES_M);
	for (let gx = sx0; gx <= sx1; gx++) {
		for (let gz = sz0; gz <= sz1; gz++) {
			const rng = createRng(hashInts(seed, gx, gz, SALT.single, GRASS_GEN_VERSION));
			const px = (gx + 0.1 + 0.8 * rng.next()) * SINGLES_M;
			const pz = (gz + 0.1 + 0.8 * rng.next()) * SINGLES_M;
			if (px < x0 || px >= x0 + PATCH_M || pz < z0 || pz >= z0 + PATCH_M) continue;
			sampleGround(rules, px, pz, local, s);
			if (s.keepGrass <= 0) continue;
			const p = grassDensity(s) * SINGLES_SHARE * SINGLES_M * SINGLES_M;
			if (rng.next() >= p) continue;
			const cls = pickClass(s.mix, rng.next());
			const pair = bundlePair(cls, s.dryness, rng);
			out.push(makeTuft(rules, s, cls, pair, px, pz, rng.next() * Math.PI * 2, unitFromHash(hashInts(seed, gx, gz, SALT.single, SALT.r)), 0.95, 1, 0, rng, grassDensity(s),
				{ dry: macroDry(rules, px, pz), hue: macroHue(rules, px, pz), size: sizeField(seed, px, pz) }));
		}
	}
	out.sort((a, b) => a.r - b.r || a.x - b.x || a.z - b.z);
	if (out.length > (opts.cap ?? PATCH_CAP)) out.length = opts.cap ?? PATCH_CAP;
	return out;
}

function makeTuft(rules, s, cls, pair, x, z, yaw, r, dome, tussockValue, tussockDry, rng, localDensity, fields) {
	const c = HEIGHT_CLASSES[cls];
	const jitter = 1 + (rng.next() - 0.5) * 0.24;
	let height = c.base * fields.size * jitter * dome * s.heightScale;
	height = clamp(height, Math.min(0.35, s.maxHeight), Math.min(0.9, s.maxHeight));
	const width = height * c.aspect * (1 + (rng.next() - 0.5) * 0.2);
	const dryness = clamp01(s.dryness + fields.dry + tussockDry + s.vergeWear * 0.25);
	const value = tussockValue * (1 + rng.normal() * 0.05);
	const hue = fields.hue + rng.normal() * 2.5 + (cls === 3 ? -8 : 0);
	const tint = s.tipHex ? linearFromHex(s.tipHex).map((v,k)=>clamp(v/TIP_REFERENCE[k]*clamp(value,.9,1.1),.55,1.5)) : tipTint(dryness, s.shade, clamp(value, 0.82, 1.18), hue);
	// Painted contact shade sits inside the clump, leaving the quiet ground gaps readable (look target v2 §5.5).
	const ao = lerp(0.62, 0.18, smoothstep(0.5, 5, localDensity));
	return {
		kind: "tuft", heightClass:c.id, x, y: 0, z, yaw: ((yaw % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2), height, width,
		col: pair, mirror: rng.next() < 0.5 ? 1 : 0, opt: 0, r, tint, ground: groundAt(rules, x, z), ao,
		wind: cls === 3 ? 0.7 : cls === 2 ? 1.1 : 1,
	};
}

function pickFamily(weights, u) {
	let total = 0;
	for (const name of FLOWER_FAMILIES) total += Math.max(0, weights[name] ?? 0);
	if (total <= 0) return "white";
	let acc = 0;
	for (const name of FLOWER_FAMILIES) {
		acc += Math.max(0, weights[name] ?? 0) / total;
		if (u < acc) return name;
	}
	return FLOWER_FAMILIES[0];
}

/**
 * Generate the flower and clover instances of plant block (i, j) (PLANT_BLOCK_M): seeded drifts (one family per
 * drift, 15 % accents), explicit flower sites (layout / dressing bake), sparse singles and clover patches.
 * Returns { flowers, clover }, each sorted by r.
 */
export function generatePlantBlock(rules, i, j, opts = {}) {
	const x0 = i * PLANT_BLOCK_M;
	const z0 = j * PLANT_BLOCK_M;
	const box = [x0 - 4, x0 + PLANT_BLOCK_M + 4, z0 - 4, z0 + PLANT_BLOCK_M + 4];
	const local = primitivesFor(rules, box);
	const seed = rules.seed;
	const flowers = [];
	const clover = [];
	const inBlock = (x, z) => x >= x0 && x < x0 + PLANT_BLOCK_M && z >= z0 && z < z0 + PLANT_BLOCK_M;
	const addFlower = (s, x, z, family, r, rng, scale = 1) => {
		if (s.keepPlants <= 0 || rng.next() > s.keepPlants) return;
		const base = (0.27 + rng.next() * 0.15) * s.plantHeight * scale;
		const height = Math.min(base, s.maxPlantHeight);
		const value = 1 + rng.normal() * 0.06;
		const tint = [value, value, value].map((v, k) => v * (k === 2 ? 1 + rng.normal() * 0.03 : 1));
		flowers.push({ kind: "flower", x, y: 0, z, yaw: rng.next() * Math.PI * 2, height, width: height * (0.95 + rng.next() * 0.2),
			col: FLOWER_COLUMN[family], mirror: rng.next() < 0.5 ? 1 : 0, opt: 0, r, tint: tint.map(v => clamp(v, 0.8, 1.2)),
			ground: groundAt(rules, x, z), ao: 0.78, wind: 1.15 });
	};
	// Flower drifts on a 6 m jittered grid.
	const D = 6;
	for (let gx = Math.floor(x0 / D) - 1; gx <= Math.ceil((x0 + PLANT_BLOCK_M) / D); gx++) {
		for (let gz = Math.floor(z0 / D) - 1; gz <= Math.ceil((z0 + PLANT_BLOCK_M) / D); gz++) {
			const rng = createRng(hashInts(seed, gx, gz, SALT.drift, GRASS_GEN_VERSION));
			const cx = (gx + 0.15 + 0.7 * rng.next()) * D;
			const cz = (gz + 0.15 + 0.7 * rng.next()) * D;
			if (!inBlock(cx, cz)) continue;
			const s = sampleGround(rules, cx, cz, local);
			if (s.keepPlants <= 0) continue;
			const p = s.flowerDrift * D * D * s.keepPlants;
			if (rng.next() >= p) continue;
			const family = pickFamily(s.flowers, rng.next());
			const accent = pickFamily(s.flowers, rng.next());
			const count = 5 + rng.int(10);
			const radius = 0.8 + rng.next() * 1.4;
			const rD = unitFromHash(hashInts(seed, gx, gz, SALT.drift, SALT.r)) * 0.85;
			for (let k = 0; k < count; k++) {
				const fx = cx + rng.normal() * radius * 0.5;
				const fz = cz + rng.normal() * radius * 0.5;
				const sf = sampleGround(rules, fx, fz, local);
				addFlower(sf, fx, fz, rng.next() < 0.15 ? accent : family, Math.min(0.9999, rD + 0.003 * k), rng);
			}
		}
	}
	// Explicit flower sites (layout flower patches, dressing bake): { x, z, radius, count, family }.
	for (const [index, site] of (rules.flowerSites ?? []).entries()) {
		if (!inBlock(site.x, site.z)) continue;
		const rng = createRng(hashInts(seed, index, 0, SALT.site, GRASS_GEN_VERSION));
		const rS = unitFromHash(hashInts(seed, index, 1, SALT.site)) * 0.7;
		const count = site.count ?? 8;
		for (let k = 0; k < count; k++) {
			const fx = site.x + rng.normal() * (site.radius ?? 1) * 0.55;
			const fz = site.z + rng.normal() * (site.radius ?? 1) * 0.55;
			const sf = sampleGround(rules, fx, fz, local);
			if(site.zoneId && sf.zone!==site.zoneId)continue;
			const family=site.families?pickFamily(site.families,rng.next()):FLOWER_COLUMN[site.family]!==undefined?site.family:"white";
			addFlower(sf, fx, fz, family, Math.min(0.9999, rS + 0.003 * k), rng, site.scale ?? 1);
		}
	}
	// Singles on a 2.2 m grid.
	const S = 2.2;
	for (let gx = Math.floor(x0 / S); gx <= Math.ceil((x0 + PLANT_BLOCK_M) / S); gx++) {
		for (let gz = Math.floor(z0 / S); gz <= Math.ceil((z0 + PLANT_BLOCK_M) / S); gz++) {
			const rng = createRng(hashInts(seed, gx, gz, SALT.flower, GRASS_GEN_VERSION));
			const fx = (gx + 0.1 + 0.8 * rng.next()) * S;
			const fz = (gz + 0.1 + 0.8 * rng.next()) * S;
			if (!inBlock(fx, fz)) continue;
			const s = sampleGround(rules, fx, fz, local);
			if (s.keepPlants <= 0) continue;
			if (rng.next() >= s.flowerSingle * S * S) continue;
			addFlower(s, fx, fz, pickFamily(s.flowers, rng.next()), unitFromHash(hashInts(seed, gx, gz, SALT.flower, SALT.r)), rng, 0.92);
		}
	}
	// Clover patches on a 5 m grid.
	const C = 5;
	for (let gx = Math.floor(x0 / C) - 1; gx <= Math.ceil((x0 + PLANT_BLOCK_M) / C); gx++) {
		for (let gz = Math.floor(z0 / C) - 1; gz <= Math.ceil((z0 + PLANT_BLOCK_M) / C); gz++) {
			const rng = createRng(hashInts(seed, gx, gz, SALT.clover, GRASS_GEN_VERSION));
			const cx = (gx + 0.15 + 0.7 * rng.next()) * C;
			const cz = (gz + 0.15 + 0.7 * rng.next()) * C;
			if (!inBlock(cx, cz)) continue;
			const s = sampleGround(rules, cx, cz, local);
			if (s.keepPlants <= 0 || s.arena) continue;
			if (rng.next() >= s.clover * C * C * s.keepPlants) continue;
			const count = 6 + rng.int(12);
			const radius = 0.5 + rng.next() * 0.9;
			const rC = unitFromHash(hashInts(seed, gx, gz, SALT.clover, SALT.r)) * 0.9;
			const variant = rng.next() < 0.6 ? 0 : 1;
			const flowering = rng.next() < 0.45 ? 1 : 0;
			for (let k = 0; k < count; k++) {
				const fx = cx + rng.normal() * radius * 0.5;
				const fz = cz + rng.normal() * radius * 0.5;
				const sf = sampleGround(rules, fx, fz, local);
				if (sf.keepPlants <= 0 || rng.next() > sf.keepPlants) continue;
				const height = (0.08 + rng.next() * 0.05) * (1 + sf.shade * 0.2);
				const value = 1 + rng.normal() * 0.06;
				clover.push({ kind: "clover", x: fx, y: 0, z: fz, yaw: rng.next() * Math.PI * 2, height, width: height * (0.9 + rng.next() * 0.3),
					col: variant, mirror: rng.next() < 0.5 ? 1 : 0, opt: flowering && rng.next() < 0.6 ? 1 : 0, r: Math.min(0.9999, rC + 0.003 * k),
					tint: tipTint(sf.dryness * 0.5, sf.shade, clamp(value, 0.85, 1.15), macroHue(rules, fx, fz) * 0.6), ground: groundAt(rules, fx, fz), ao: 0.8, wind: 0.6 });
			}
		}
	}
	const sortR = (a, b) => a.r - b.r || a.x - b.x || a.z - b.z;
	flowers.sort(sortR);
	clover.sort(sortR);
	const cap = opts.cap ?? PATCH_CAP;
	if (flowers.length > cap) flowers.length = cap;
	if (clover.length > cap) clover.length = cap;
	return { flowers, clover };
}

// =====================================================================================================================
// Instance packing (GPU buffers)
// =====================================================================================================================

/** Floats per instance in the custom "grassInst" vertex buffer. */
export const INSTANCE_FLOATS = 4;

const byte = (v) => Math.round(clamp01(v) * 255);
/** Pack three [0, 1] values into an exactly representable float (24-bit integer). */
export const pack3 = (a, b, c) => byte(a) + byte(b) * 256 + byte(c) * 65536;
export function unpack3(v) {
	const a = v % 256;
	const b = Math.floor(v / 256) % 256;
	const c = Math.floor(v / 65536);
	return [a / 255, b / 255, c / 255];
}

/**
 * Thin-instance buffers for a sorted instance list: Babylon matrices (16 floats: yaw, scale (w, h, w), translation)
 * and the packed grassInst vec4:
 * x = (col * 2 + mirror) + r * 0.998 (r = thinning key)
 * y = pack3(tint / 2) (tip tint, linear multiplier 0..2)
 * z = pack3(sqrt(ground)) (legacy: vertex tint; mean mode: full linear ground colour; sqrt keeps dark precision)
 * w = pack3(ao, wind / 2, opt)
 * Also returns r (Float32Array, ascending) and the AABB of the instances (with wind / lean margins).
 */
export function packInstances(list) {
	const n = list.length;
	const matrices = new Float32Array(n * 16);
	const data = new Float32Array(n * INSTANCE_FLOATS);
	const r = new Float32Array(n);
	let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity, maxH = 0;
	for (let k = 0; k < n; k++) {
		const it = list[k];
		const c = Math.cos(it.yaw);
		const s = Math.sin(it.yaw);
		const o = k * 16;
		matrices[o] = it.width * c; matrices[o + 1] = 0; matrices[o + 2] = -it.width * s; matrices[o + 3] = 0;
		matrices[o + 4] = 0; matrices[o + 5] = it.height; matrices[o + 6] = 0; matrices[o + 7] = 0;
		matrices[o + 8] = it.width * s; matrices[o + 9] = 0; matrices[o + 10] = it.width * c; matrices[o + 11] = 0;
		matrices[o + 12] = it.x; matrices[o + 13] = it.y; matrices[o + 14] = it.z; matrices[o + 15] = 1;
		const d = k * INSTANCE_FLOATS;
		data[d] = (it.col * 2 + it.mirror) + Math.min(0.9999, Math.max(0, it.r)) * 0.998;
		data[d + 1] = pack3(it.tint[0] / 2, it.tint[1] / 2, it.tint[2] / 2);
		data[d + 2] = pack3(Math.sqrt(clamp01(it.ground[0])), Math.sqrt(clamp01(it.ground[1])), Math.sqrt(clamp01(it.ground[2])));
		data[d + 3] = pack3(it.ao, it.wind / 2, it.opt);
		r[k] = it.r;
		const reach = it.width * 0.75 + 0.1;
		if (it.x - reach < minX) minX = it.x - reach;
		if (it.x + reach > maxX) maxX = it.x + reach;
		if (it.z - reach < minZ) minZ = it.z - reach;
		if (it.z + reach > maxZ) maxZ = it.z + reach;
		if (it.height > maxH) maxH = it.height;
	}
	return { count: n, matrices, data, r, bounds: n ? { min: [minX, -0.1, minZ], max: [maxX, maxH * 1.35 + 0.1, maxZ] } : null };
}

/** Count of sorted thinning keys strictly below `value` (binary search). */
export function lowerBound(sorted, value) {
	let lo = 0;
	let hi = sorted.length;
	while (lo < hi) {
		const mid = (lo + hi) >>> 1;
		if (sorted[mid] < value) lo = mid + 1;
		else hi = mid;
	}
	return lo;
}

// =====================================================================================================================
// Tiers and distance LOD (spec §6.2, device tiers plan §3.3)
// =====================================================================================================================

/**
 * Grass tier table. Low is off (the painted ground carries the meadow on weak devices; brief: "On Low, grass is off
 * or a sparse far tint"). Mobile multiplies density by 0.72 and distances by 0.85, with a 0.35 far band.
 */
export const GRASS_TIERS = Object.freeze({
	low: Object.freeze({ enabled: false, fTier: 0, distance: 0.5, far: 0.4, benders: 1, atlas: "half", ground: "mean", plants: false, plantDistance: 0.7 }),
	medium: Object.freeze({ enabled: true, fTier: 0.56, distance: 0.75, far: 0.4, benders: 1, atlas: "half", ground: "mean", plants: true, plantDistance: 0.7 }),
	high: Object.freeze({ enabled: true, fTier: 0.8, distance: 1, far: 0.4, benders: 1, atlas: "full", ground: "texture", plants: true, plantDistance: 0.75 }),
	ultra: Object.freeze({ enabled: true, fTier: 1, distance: 1.25, far: 0.4, benders: 1, atlas: "full", ground: "texture", plants: true, plantDistance: 0.8 }),
	epic: Object.freeze({ enabled: true, fTier: 1, distance: 1.5, far: 0.6, benders: 1, atlas: "full", ground: "texture", plants: true, plantDistance: 0.85 }),
});

/** Resolve the grass tier from a graphics profile ({ preset, formFactor?, vegetationDensity?, vegetationDistanceFactor? }). */
export function resolveGrassTier(profile) {
	const preset = typeof profile?.preset === "string" && profile.preset in GRASS_TIERS ? profile.preset : "high";
	const t = GRASS_TIERS[preset];
	const mobile = profile?.formFactor === "mobile";
	const density = mobile ? 0.72 : 1;
	const distance = mobile ? 0.85 : 1;
	return {
		preset, mobile, enabled: t.enabled,
		fTier: Math.min(1, t.fTier * density), distance: t.distance * distance, far: mobile ? 0.35 : t.far,
		benders: t.benders, atlas: mobile && t.atlas === "full" ? "half" : t.atlas, ground: mobile ? "mean" : t.ground,
		plants: t.plants, plantDistance: t.plantDistance,
	};
}

/** Distance bands (eye distance, m) for a tier and the camera boom radius (spec §6.2). */
export function grassBands(tier, cameraRadius = 13) {
	const f = tier.distance;
	const near = Math.min(f * Math.max(26, cameraRadius + 13), 90 - 34 * f);
	const mid = near + 16 * f;
	const end = Math.min(mid + 18 * f, 90);
	return { near, mid, end, far: tier.far, fTier: tier.fTier, window: 0.06 };
}

/** Density profile f(d): 1 inside near, linear to `far` at mid, linear to 0 at end. */
export function densityProfile(d, bands) {
	if (d <= bands.near) return 1;
	if (d <= bands.mid) return lerp(1, bands.far, (d - bands.near) / Math.max(1e-6, bands.mid - bands.near));
	if (d <= bands.end) return lerp(bands.far, 0, (d - bands.mid) / Math.max(1e-6, bands.end - bands.mid));
	return 0;
}

/** Per-instance presence p in [0, 1] (shader formula, spec §6.2). */
export function presence(r, d, bands) {
	if (r >= bands.fTier || d >= bands.end) return 0;
	const terminal = 1-smoothstep(bands.end-Math.min(6,(bands.end-bands.mid)/3),bands.end,d);
	return clamp01(1 + (bands.fTier * densityProfile(d, bands) - r) / bands.window)*terminal;
}

/** Prefix of a sorted patch to submit when its nearest point is `dNearest` away: no instance with presence > 0 is cut. */
export function prefixFraction(dNearest, bands) {
	if(dNearest>=bands.end)return 0;
	return Math.min(bands.fTier, bands.fTier * densityProfile(dNearest, bands) + bands.window);
}

/** Scale bands for a sparse layer (flowers / clover fade earlier). */
export function scaleBands(bands, factor) {
	return { ...bands, near: bands.near * factor, mid: bands.mid * factor, end: bands.end * factor };
}

/** Nearest 3D distance from an eye to an AABB { min, max }. */
export function aabbDistance(eye, bounds) {
	const dx = Math.max(bounds.min[0] - eye[0], 0, eye[0] - bounds.max[0]);
	const dy = Math.max(bounds.min[1] - eye[1], 0, eye[1] - bounds.max[1]);
	const dz = Math.max(bounds.min[2] - eye[2], 0, eye[2] - bounds.max[2]);
	return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

// =====================================================================================================================
// Procedural clump geometry (normalised: root at the origin, height 1). UV encoding (atlas grass_atlas_v1, 256 px
// units, 8 x 4): uv = atlas position in units (u in [0, 8], v in [0, 4], image row 0 = v 0). A vertex with u < 0 uses
// the instance column: u_units = -u + col. A vertex with v >= 4 belongs to an optional part (drawn only when the
// instance's opt flag is 1; real v = v - 4). Each builder also returns the quad count for the tests.
// =====================================================================================================================

/** Atlas layout constants (must match grass_atlas_v1.json). */
export const ATLAS = Object.freeze({ units: [8, 4], unitPx: 256, gutterPx: 8, bundleRootPx: 504, bundleTopPx: 8, rowFlowers: 2, rowLeaves: 3 });

function pushQuad(geo, corners, uvs, normals) {
	const base = geo.positions.length / 3;
	for (let k = 0; k < 4; k++) {
		geo.positions.push(...corners[k]);
		geo.uvs.push(...uvs[k]);
		geo.normals.push(...normals[k]);
	}
	geo.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
	geo.quads++;
}

/** Soft dome normal: mostly up, a little outward (spec §4.2), so a clump lights like the ground under it. */
export function domeNormal(x, y, z, up = 0.72) {
	const ox = x;
	const oy = y + 0.6;
	const oz = z;
	const ol = Math.hypot(ox, oy, oz) || 1;
	const nx = lerp(ox / ol, 0, up);
	const ny = lerp(oy / ol, 1, up);
	const nz = lerp(oz / ol, 0, up);
	const l = Math.hypot(nx, ny, nz) || 1;
	return [nx / l, ny / l, nz / l];
}

/**
 * Fan tuft: `count` outward-leaning bundle quads (2 segments each, curving outward) radiating from the root. Reads as
 * a radial fan from the elevated camera and as a full fan from the 13 m camera (owner samples 205854 / 210121).
 * Quads alternate between the instance's bundle pair (column col and col + 1).
 */
export function buildTuftGeometry(seed = 7, count = 6) {
	const rng = createRng(hashInts(seed, 3, 5, 0x7f7f));
	const geo = { positions: [], normals: [], uvs: [], indices: [], quads: 0 };
	const tilts = [12, 30, 20, 36, 16, 26, 22, 32];
	const U = ATLAS.unitPx;
	// Bundle cell content (cell-local px): x 8..248 (centre 128), y 8 (tip) .. 504 (root).
	const halfWidths = [0.075, 0.17, 0.24];
	const rows = [0, 0.45, 1];
	const vPx = [504, 504 - 0.45 * 496, 8];
	for (let k = 0; k < count; k++) {
		const yaw = (k / count) * Math.PI * 2 + (rng.next() - 0.5) * 0.4;
		const tilt = ((tilts[(k + Math.floor(rng.next() * 3)) % tilts.length] + (rng.next() - 0.5) * 6) * Math.PI) / 180;
		const r0 = 0.025 + 0.025 * rng.next();
		const t1 = tilt * 0.55;
		const t2 = tilt * 1.35;
		// radial (outward) and tangential directions
		const ox = Math.sin(yaw);
		const oz = Math.cos(yaw);
		const tx = Math.cos(yaw);
		const tz = -Math.sin(yaw);
		const pts = [];
		let reach = r0;
		let height = -0.03;
		for (let rowIndex = 0; rowIndex < 3; rowIndex++) {
			if (rowIndex === 1) { reach += 0.45 * Math.sin(t1); height += 0.45 * Math.cos(t1); }
			if (rowIndex === 2) { reach += 0.55 * Math.sin(t2); height += 0.55 * Math.cos(t2); }
			pts.push([reach, height]);
		}
		const column = k % 2;
		const mirror = k % 3 === 2;
		const quadsRows = [[0, 1], [1, 2]];
		for (const [a, b] of quadsRows) {
			const corner = (rowIndex, side) => {
				const [rad, h] = pts[rowIndex];
				const w = halfWidths[rowIndex] * side;
				return [ox * rad + tx * w, h, oz * rad + tz * w];
			};
			const uvOf = (rowIndex, side) => {
				const localX = 128 + side * (mirror ? -1 : 1) * 120 * (halfWidths[rowIndex] / halfWidths[2]);
				return [-(column + localX / U), vPx[rowIndex] / U];
			};
			const cs = [corner(a, -1), corner(a, 1), corner(b, 1), corner(b, -1)];
			const us = [uvOf(a, -1), uvOf(a, 1), uvOf(b, 1), uvOf(b, -1)];
			const ns = cs.map(p => domeNormal(p[0], Math.max(0, p[1]), p[2]));
			pushQuad(geo, cs, us, ns);
		}
	}
	return {...finishGeometry(geo),fanCount:count,segmentsPerFan:2};
}

/**
 * Flower plant: two crossed stem cards (atlas G3, G4), two short leafy base quads (G5) and up-facing head quads at
 * the painted stem tips (atlas F row, instance column). `tips` = { G3: [[px, py] ...], G4: [...] } absolute atlas px
 * (manifest tips_px); defaults are used until the atlas manifest is known.
 */
export function buildFlowerGeometry(tips = DEFAULT_STEM_TIPS, seed = 11) {
	const rng = createRng(hashInts(seed, 9, 2, 0xf10e));
	const geo = { positions: [], normals: [], uvs: [], indices: [], quads: 0 };
	const U = ATLAS.unitPx;
	const rowG = ATLAS.rowLeaves;
	const cards = [{ cell: 3, yaw: 0.35, tipsPx: tips.G3 ?? DEFAULT_STEM_TIPS.G3 }, { cell: 4, yaw: 0.35 + Math.PI / 2, tipsPx: tips.G4 ?? DEFAULT_STEM_TIPS.G4 }];
	// Stem cards: content 240 x 240 px (cell-local 8..248) -> quad x in [-0.5, 0.5], y in [0, 1] (root at 248 px).
	const heads = [];
	for (const card of cards) {
		const tx = Math.cos(card.yaw);
		const tz = -Math.sin(card.yaw);
		const lean = 0.08;
		const ox = Math.sin(card.yaw) * lean;
		const oz = Math.cos(card.yaw) * lean;
		const corner = (lx, ly) => [tx * lx + ox * ly, ly, tz * lx + oz * ly];
		const cs = [corner(-0.5, -0.02), corner(0.5, -0.02), corner(0.5, 1), corner(-0.5, 1)];
		const u0 = card.cell + 8 / U;
		const u1 = card.cell + 248 / U;
		const v0 = rowG + 248 / U;
		const v1 = rowG + 8 / U;
		const us = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]];
		pushQuad(geo, cs, us, cs.map(p => domeNormal(p[0], Math.max(0, p[1]), p[2], 0.8)));
		for (const [px, py] of card.tipsPx) {
			const localX = (px - (card.cell * U + 128)) / 240;
			const localY = (rowG * U + 248 - py) / 240;
			heads.push(corner(localX, localY));
		}
	}
	// Leafy base: two short outward-leaning quads (G5).
	for (let k = 0; k < 2; k++) {
		const yaw = k * Math.PI + 0.9 + (rng.next() - 0.5) * 0.4;
		const ox = Math.sin(yaw);
		const oz = Math.cos(yaw);
		const tx = Math.cos(yaw);
		const tz = -Math.sin(yaw);
		const tilt = 0.45;
		const h = 0.42;
		const corner = (lx, ly) => [tx * lx + ox * (0.02 + ly * Math.sin(tilt)), ly * Math.cos(tilt) - 0.02, tz * lx + oz * (0.02 + ly * Math.sin(tilt))];
		const cs = [corner(-0.24, 0), corner(0.24, 0), corner(0.24, h), corner(-0.24, h)];
		const u0 = 5 + 8 / U;
		const u1 = 5 + 248 / U;
		const v0 = rowG + 248 / U;
		const v1 = rowG + 8 / U;
		const us = k === 0 ? [[u0, v0], [u1, v0], [u1, v1], [u0, v1]] : [[u1, v0], [u0, v0], [u0, v1], [u1, v1]];
		pushQuad(geo, cs, us, cs.map(p => domeNormal(p[0], Math.max(0, p[1]), p[2], 0.8)));
	}
	// Heads: near-horizontal quads at the tips, tilted up to ~28 deg toward a seeded direction, size ~0.2 of the height.
	const rowF = ATLAS.rowFlowers;
	for (const [hx, hy, hz] of heads) {
		const size = 0.19 + rng.next() * 0.06;
		const dir = rng.next() * Math.PI * 2;
		const tilt = (12 + rng.next() * 18) * Math.PI / 180;
		// head plane basis: a = horizontal axis, b = tilted axis
		const ax = Math.cos(dir), az = -Math.sin(dir);
		const bx = Math.sin(dir) * Math.cos(tilt), by = Math.sin(tilt), bz = Math.cos(dir) * Math.cos(tilt);
		const corner = (sa, sb) => [hx + ax * sa * size / 2 + bx * sb * size / 2, hy + by * sb * size / 2 + 0.01, hz + az * sa * size / 2 + bz * sb * size / 2];
		const cs = [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
		// Head cell content: a circle of radius <= 112 px around the cell centre -> map the quad to centre +-116 px.
		const lo = (128 - 116) / U;
		const hi = (128 + 116) / U;
		const us = [[-lo, rowF + hi], [-hi, rowF + hi], [-hi, rowF + lo], [-lo, rowF + lo]];
		pushQuad(geo, cs, us, cs.map(() => [0, 1, 0]));
	}
	return finishGeometry(geo);
}

/** Default stem tips (absolute atlas px) until the forge manifest is known: 4 tips on G3, 3 on G4. */
export const DEFAULT_STEM_TIPS = Object.freeze({
	G3: Object.freeze([[3 * 256 + 92, 3 * 256 + 64], [3 * 256 + 128, 3 * 256 + 30], [3 * 256 + 160, 3 * 256 + 52], [3 * 256 + 112, 3 * 256 + 96]]),
	G4: Object.freeze([[4 * 256 + 100, 3 * 256 + 48], [4 * 256 + 150, 3 * 256 + 40], [4 * 256 + 128, 3 * 256 + 80]]),
});

/**
 * Clover rosette: 6 leaf quads (top-down trifoliate leaves G0/G1, instance column) radiating around the root at
 * low heights with a slight upward tilt, plus 2 optional white clover heads (G6, drawn when opt = 1).
 */
export function buildCloverGeometry(seed = 5) {
	const rng = createRng(hashInts(seed, 4, 4, 0xc10e));
	const geo = { positions: [], normals: [], uvs: [], indices: [], quads: 0 };
	const U = ATLAS.unitPx;
	const rowG = ATLAS.rowLeaves;
	const lo = (128 - 108) / U;
	const hi = (128 + 108) / U;
	const leaves = 6;
	for (let k = 0; k < leaves; k++) {
		const dir = (k / leaves) * Math.PI * 2 + (rng.next() - 0.5) * 0.5;
		const dist = 0.55 + rng.next() * 0.9;
		const h = 0.3 + rng.next() * 0.7;
		const size = 1.05 + rng.next() * 0.4;
		const tilt = (8 + rng.next() * 22) * Math.PI / 180;
		const cx = Math.sin(dir) * dist;
		const cz = Math.cos(dir) * dist;
		const ax = Math.cos(dir + 0.6 * (rng.next() - 0.5)), az = -Math.sin(dir);
		const bx = Math.sin(dir) * Math.cos(tilt), by = Math.sin(tilt), bz = Math.cos(dir) * Math.cos(tilt);
		const corner = (sa, sb) => [cx + ax * sa * size / 2 + bx * sb * size / 2, h + by * sb * size / 2, cz + az * sa * size / 2 + bz * sb * size / 2];
		const cs = [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
		const us = [[-lo, rowG + hi], [-hi, rowG + hi], [-hi, rowG + lo], [-lo, rowG + lo]];
		pushQuad(geo, cs, us, cs.map(() => [0, 1, 0]));
	}
	// Optional white heads (G6) on short stalks: v + 4 marks optional vertices.
	for (let k = 0; k < 2; k++) {
		const dir = rng.next() * Math.PI * 2;
		const dist = 0.3 + rng.next() * 0.6;
		const h = 1.6 + rng.next() * 0.6;
		const size = 0.75;
		const cx = Math.sin(dir) * dist;
		const cz = Math.cos(dir) * dist;
		const corner = (sa, sb) => [cx + sa * size / 2, h + sb * 0.08, cz + sb * size / 2];
		const cs = [corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1)];
		const hlo = 6 + (128 - 70) / U;
		const hhi = 6 + (128 + 70) / U;
		const vlo = rowG + 4 + (128 - 70) / U;
		const vhi = rowG + 4 + (128 + 70) / U;
		const us = [[hlo, vhi], [hhi, vhi], [hhi, vlo], [hlo, vlo]];
		pushQuad(geo, cs, us, cs.map(() => [0, 1, 0]));
	}
	return finishGeometry(geo);
}

/** Normalise to height 1 (max y), convert to typed arrays and report counts. */
function finishGeometry(geo) {
	let maxY = 0;
	for (let i = 1; i < geo.positions.length; i += 3) maxY = Math.max(maxY, geo.positions[i]);
	const scale = maxY > 0 ? 1 / maxY : 1;
	const positions = new Float32Array(geo.positions.map(v => v * scale));
	return {
		positions,
		normals: new Float32Array(geo.normals),
		uvs: new Float32Array(geo.uvs),
		indices: new Uint16Array(geo.indices),
		quads: geo.quads,
		vertexCount: positions.length / 3,
		triangleCount: geo.indices.length / 3,
		radius: (() => { let r = 0; for (let i = 0; i < positions.length; i += 3) r = Math.max(r, Math.hypot(positions[i], positions[i + 2])); return r; })(),
	};
}

// =====================================================================================================================
// Region generation helpers (tests, receipts, lab previews)
// =====================================================================================================================

/** Patch index range covering a domain [minX, maxX, minZ, maxZ]. */
export function patchRange(domain, size = PATCH_M) {
	return { i0: Math.floor(domain[0] / size), i1: Math.ceil(domain[1] / size) - 1, j0: Math.floor(domain[2] / size), j1: Math.ceil(domain[3] / size) - 1 };
}

/** v3 layout adapter. All exclusions follow the checked-in design rather than a second hand-authored map. */
export function grassRulesFromLayout(layout, dressing = {}, monsters = {}, derived = null, blueprint = null) {
	if (layout?.version !== "v3-features") throw new TypeError("Grass requires the current v3-features layout");
	const obstacles = [];
	const polygon = (id, points, pad = 0.15) => obstacles.push({ id, kind: "footprint", shape: "polygon", polygon: points, pad });
	const box = (id, b, pad = 0.15) => obstacles.push({ id, kind: "footprint", shape: "box", x: (b[0]+b[1])/2, z: (b[2]+b[3])/2, hx: (b[1]-b[0])/2, hz: (b[3]-b[2])/2, pad });
	const circle = (id, x, z, r, pad = 0.15) => obstacles.push({ id, kind: "footprint", shape: "circle", x, z, r, pad });
	for (const feature of layout.features ?? []) {
		for (const c of feature.colliders ?? []) {
			if (c.polygon_xz) polygon(c.id, c.polygon_xz, .3);
			else if (c.bounds_xz) box(c.id, c.bounds_xz, .3);
			else if (c.center_xz && c.radius_m) circle(c.id, ...c.center_xz, c.radius_m, .3);
		}
		for (const deck of [...(feature.decks ?? []), ...(feature.walkways ?? [])]) {
			if (deck.polygon_xz) polygon(deck.id, deck.polygon_xz, .3);
			else if (deck.bounds_xz) box(deck.id, deck.bounds_xz, .3);
		}
		for (const b of feature.buildings ?? []) if (b.center_xz && b.diameter_m) circle(b.id, ...b.center_xz, b.diameter_m/2, .4);
	}
	for (const bridge of layout.bridges ?? []) obstacles.push({ id: bridge.id, kind: "bridge", shape: "box", x: bridge.center_xz[0], z: bridge.center_xz[1], hx: bridge.deck_width_m/2, hz: bridge.length_m/2, yaw: Math.atan2(...bridge.along_xz), pad: .4 });
	for (const l of layout.landmarks ?? []) {
		if (l.radius_m && (l.position_xz || l.center_xz) && l.kind !== "stone_circle_altar") circle(l.id, ...(l.position_xz ?? l.center_xz), l.radius_m);
		if (l.kind === "camp") box(l.id, l.bounds_xz, .15);
	}
	for (const entry of dressing.entries ?? []) {
		if (["flower", "grass", "clover", "lily_pad", "lotus"].includes(entry.class)) continue;
		if (entry.footprint_r > .22) circle(entry.id, entry.x, entry.z, entry.footprint_r, .08);
	}
	const zones = (layout.vegetation_zones ?? []).filter(z => z.polygon_xz).map(z => ({ id: z.id, polygon: z.polygon_xz, spec: z.kind === "flower_meadow"
		? { density: 2.2, flowerDrift: .014, flowers: { white: .4, yellow: .35, orange: .1, red: .1, blue: .025, violet: .025 } }
		: { density: z.kind === "pine_stand" ? 1.2 : 1.8, shade: .4, dryness: .22 } }));
	const water = [];
	// Exact derived stream samples become narrow capsules, preserving changing width and bends.
	if (derived) {
		const samples = derived.stream.samples_1m;
		for (let i=0;i<samples.length-1;i++) { const a=samples[i],b=samples[i+1]; water.push({id:`stream-${i}`,points:[[a.x,a.z],[b.x,b.z]],width:Math.max(a.w,b.w)+2.4,noReeds:true}); }
		water.push({id:"falls-pool",center:derived.pool.center_xz,radius:derived.pool.radius+1.2,noReeds:true});
		for (const lake of derived.lakes) {
			if(!blueprint&&(lake.blueprint_id||String(lake.id).startsWith('blueprint_')))continue;
			if (lake.outline_xz) polygon(lake.id,lake.outline_xz,1.2);
			else water.push({id:lake.id,center:lake.center_xz,radius:lake.radius_m+1.2,noReeds:true});
		}
	} else for (const w of layout.water ?? []) {
		if (w.outline_xz) polygon(w.id,w.outline_xz,1.2);
		else if (w.center_xz) water.push({id:w.id,center:w.center_xz,radius:w.radius_m+1.2,noReeds:true});
		else if (w.points) water.push({id:w.id,points:w.points,width:w.width_m+2.4,noReeds:true});
	}
	const clearings = (layout.clearings ?? []).map(c=>({id:c.id,x:c.center_xz[0],z:c.center_xz[1],rx:c.radius_m??(c.bounds_xz[1]-c.bounds_xz[0])/2,rz:c.radius_m??(c.bounds_xz[3]-c.bounds_xz[2])/2,coreDensity:0,coreMaxHeight:.25,flowers:false}));
	const discs = (monsters.spawn_rows ?? []).flatMap(s => { const p=s.home_xz??s.position_xz??s.center_xz??s.at_xz; return p?[{id:`spawn-${s.row??s.id}`,x:p[0],z:p[1],r:2.5,factor:0}]:[]; });
	for (const c of layout.clearings ?? []) circle(`quiet-${c.id}`, ...c.center_xz,6,.1);
	const arena = (layout.landmarks ?? []).find(l=>l.kind === "stone_circle_altar");
	if (arena) circle("quiet-arena", ...arena.center_xz, arena.boss_arena_radius_m,.1);
	const data={ schema:"xexoria.grass-rules/1", id:`sunmeadow-${layout.version}`, seed:20261003, domain:[-56,46,-104,8],
		base:{density:2.25,maxHeight:.9,heightScale:1.15}, paths:(layout.paths??[]).map(p=>({id:p.id,points:p.points,width:p.width_m+.5,jitter:.18})),
		obstacles, water, clearings, discs, zones, noGo:[{minX:-124,maxX:124,minZ:8,maxZ:304,fade:2}], ground:{kind:"flat",tint:[.75,.85,.72]} };
	return blueprint?grassRulesWithBlueprint(data,layout,dressing,derived,blueprint):data;
}

/** Same generator/compiler, explicit blueprint masks and four source-derived flower drifts. */
export function grassRulesWithBlueprint(data,layout,dressing,derived,blueprint){
	if(blueprint.schema!=='xexoria.map-blueprint/1')throw new TypeError('Unsupported grass blueprint');
	const out={...data,id:`${data.id}-${blueprint.version}`,base:{...data.base,mix:[.5,.35,.15,0],cluster:1},obstacles:[...data.obstacles],zones:[...data.zones],water:[...data.water],flowerSites:[]};
	const items=blueprint.items??[],knoll=items.find(i=>i.id==='T1'),arena=blueprint.boss?.at??[0,-68],arenaRadius=blueprint.boss?.arena_keep_clear_m??12;
	// Blueprint garden uses exact prefab obstacles instead of the legacy whole-croft blanket.
	const croft=(layout.features??[]).find(f=>f.id==='sunmeadow_croft');out.obstacles=out.obstacles.filter(o=>o.id!=='sunmeadow_croft');
	for(const c of croft?.colliders??[])if(c.center_xz&&c.size_m)out.obstacles.push({id:c.id,kind:'footprint',shape:'box',x:c.center_xz[0],z:c.center_xz[1],hx:c.size_m[0]/2,hz:c.size_m[1]/2,yaw:c.yaw_rad??0,pad:.3});
	for(const item of items){
		if(item.id==='T1'&&item.poly)out.obstacles.push({id:'blueprint-T1-no-height-support',kind:'footprint',shape:'polygon',polygon:item.poly,pad:.6});
		else if(item.solid&&item.cat!=='palm'){
			if(item.poly)out.obstacles.push({id:`blueprint-${item.id}`,kind:'footprint',shape:'polygon',polygon:item.poly,pad:.35});
			else if(item.line)for(let k=1;k<item.line.length;k++)out.paths=[...out.paths,{id:`blueprint-${item.id}-${k}`,points:[item.line[k-1],item.line[k]],width:.6,fade:.3,vergeBoost:1,jitter:0}];
			else if(item.xz&&item.r)out.obstacles.push({id:`blueprint-${item.id}`,kind:'footprint',shape:'circle',x:item.xz[0],z:item.xz[1],r:item.r,pad:.35});
		}
	}
	out.obstacles.push({id:'blueprint-arena-quiet12',kind:'footprint',shape:'circle',x:arena[0],z:arena[1],r:arenaRadius,pad:.1});
	const addZone=(zone)=>out.zones.push({edge:0,priority:100,...zone});
	const hunt=(layout.vegetation_zones??[]).find(z=>z.id==='hunt_flowers');
	const glade=(layout.dressing_zones?.wildflower_meadows??[]).find(z=>z.id==='wf_glade_edge')?.ring;
	const garden=(layout.features??[]).find(f=>f.id==='sunmeadow_croft')?.hero_dressing?.find(d=>d.id==='croft_veg_patch');
	const flowerSpec=(flowers,extra={})=>({density:2.2,maxHeight:.9,flowerDrift:.035,flowerSingle:.06,flowers,...extra});
	if(hunt?.polygon_xz)addZone({id:'G2-hunt-drift',polygon:hunt.polygon_xz,spec:flowerSpec({white:.55,yellow:.45})});
	if(glade)addZone({id:'G2-glade-drift',ring:{x:glade.center_xz[0],z:glade.center_xz[1],r0:Math.max(glade.r_m[0],arenaRadius+.8),r1:Math.max(glade.r_m[1],arenaRadius+2.8)},spec:flowerSpec({white:.6,yellow:.4},{maxHeight:.35,plantHeight:.8})});
	if(knoll?.poly)addZone({id:'G2-knoll-supported-bank-drift',polygon:knoll.poly,outsideBand:[.8,3.5],spec:flowerSpec({red:.55,orange:.45},{maxHeight:.45,dryness:.8,mix:[.8,.2,0,0],tipHex:'#b59a4e'})});
	if(garden?.polygon_xz)addZone({id:'G2-croft-garden-drift',priority:120,polygon:garden.polygon_xz,outsideBand:[.35,2.8],spec:flowerSpec({violet:1},{maxHeight:.35,plantHeight:.9})});
	if(croft?.bounds_xz){const b=croft.bounds_xz;addZone({id:'G5-croft-short',priority:108,polygon:[[b[0],b[2]],[b[1],b[2]],[b[1],b[3]],[b[0],b[3]]],spec:{density:.6,maxHeight:.25,mix:[1,0,0,0],dryness:.4,flowerSingle:0,flowerDrift:0}});}
	const east=(layout.vegetation_zones??[]).find(z=>z.id==='east_oak_grove')?.polygon_xz;
	if(east){const b=pointsBounds(east,0);addZone({id:'G3-east-supported-toe',priority:80,polygon:[[b[1]-7,b[2]],[b[1],b[2]],[b[1],b[3]],[b[1]-7,b[3]]],spec:{density:1.8,dryness:.8,maxHeight:.45,mix:[.85,.15,0,0],tipHex:'#b59a4e'}});}
	for(const lake of derived?.lakes??[]){
		if(!lake.outline_xz)continue;
		const margin=lake.blueprint_id?.startsWith('P')? .6:1.2;
		// Replace old outline keepout with the actual host margin for blueprint bodies.
		if(lake.blueprint_id){out.obstacles=out.obstacles.filter(o=>o.id!==lake.id);out.obstacles.push({id:lake.id,kind:'footprint',shape:'polygon',polygon:lake.outline_xz,pad:margin});}
		addZone({id:`G4-${lake.id}-flat-bank`,priority:90,polygon:lake.outline_xz,outsideBand:[margin+.05,margin+2.3],spec:{density:2.6,dryness:.02,shade:.25,maxHeight:.9,mix:[.15,.25,.25,.35],tipHex:'#4f783d',flowerSingle:.01,flowerDrift:.012}});
	}
	for(let i=1;i<(derived?.stream?.samples_1m?.length??0);i+=4){const a=derived.stream.samples_1m[i-1],b=derived.stream.samples_1m[Math.min(i+3,derived.stream.samples_1m.length-1)];const half=Math.max(a.w,b.w)/2+1.2;out.water.push({id:`G4-stream-bank-${i}`,points:[[a.x,a.z],[b.x,b.z]],width:half*2,bank:[.05,2.3],noReeds:false});}
	const camps=items.filter(i=>i.id==='ST3');for(const c of camps)if(c.xz)addZone({id:'G5-hunter-short',priority:110,circle:{x:c.xz[0],z:c.xz[1],r:c.r+3},spec:{density:.6,maxHeight:.25,mix:[1,0,0,0],dryness:.55,flowerSingle:0,flowerDrift:0}});
	// Place each explicit drift at a safe point of its own compiled zone; scatter resamples children.
	const compiled=compileRules(out);
	for(const zone of out.zones.filter(z=>z.id.startsWith('G2-'))){const z=compiled.zones.find(v=>v.id===zone.id);let best=null,bestScore=Infinity;
		const cx=(z.bounds[0]+z.bounds[1])/2,cz=(z.bounds[2]+z.bounds[3])/2;const step=zone.id.includes('garden')?.5:1;
		for(let x=Math.max(data.domain[0],z.bounds[0]);x<Math.min(data.domain[1],z.bounds[1]);x+=step)for(let y=Math.max(data.domain[2],z.bounds[2]);y<Math.min(data.domain[3],z.bounds[3]);y+=step){const s=sampleGround(compiled,x,y);if(s.zone!==zone.id||s.keepPlants<.1)continue;const score=(x-cx)**2+(y-cz)**2;if(score<bestScore){best=[x,y];bestScore=score;}}
		if(best)out.flowerSites.push({id:zone.id,x:best[0],z:best[1],radius:zone.id.includes('garden')?1:1.8,count:64,families:zone.spec.flowers,zoneId:zone.id});
	}
	out.blueprint={version:blueprint.version,grassIds:(blueprint.grass??[]).map(g=>g.id),heightSupport:'flat-only;T1 excluded',sourceHashes:{layout:stableHash(layout),dressing:stableHash(dressing),blueprint:stableHash(blueprint),water:stableHash(derived)},footprintIds:out.obstacles.filter(o=>o.id.startsWith('blueprint-')).map(o=>o.id)};
	return out;
}

/** Conservative grass triangle allowance after actual non-grass cell cost and already admitted patches. */
export function grassCellAllowance(baseTriangles,usedGrassTriangles,trianglesPerInstance,cellLimit){return Math.max(0,Math.floor((cellLimit-Math.max(0,baseTriangles)-Math.max(0,usedGrassTriangles))/Math.max(1,trianglesPerInstance)));}

/** Bounded governor: continuous shader bands; a 2 second hysteresis prevents oscillating density. */
export function governGrass(state, submitted, cap, deltaSeconds) {
	let factor=state.factor??1, quiet=state.quiet??0;
	if(submitted>cap){factor=Math.max(.35,factor*.9);quiet=0;}
	else if(submitted<cap*.8){quiet+=Math.min(.5,Math.max(0,deltaSeconds));if(quiet>=2){factor=Math.min(1,factor/.9);quiet=0;}}
	else quiet=0;
	return {factor,quiet};
}

/** Stable short hash of a JSON-able value (FNV-1a 32 over the canonical JSON), for receipts and seeds. */
export function stableHash(value) {
	const json = JSON.stringify(canonical(value));
	let h = 0x811c9dc5;
	for (let i = 0; i < json.length; i++) {
		h ^= json.charCodeAt(i);
		h = Math.imul(h, 0x01000193);
	}
	return (h >>> 0).toString(16).padStart(8, "0");
}
function canonical(value) {
	if (Array.isArray(value)) return value.map(canonical);
	if (ArrayBuffer.isView(value)) return { typed: value.length, hash: typedHash(value) };
	if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
	return value;
}
function typedHash(view) {
	const bytes = new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
	let h = 0x811c9dc5;
	for (let i = 0; i < bytes.length; i++) { h ^= bytes[i]; h = Math.imul(h, 0x01000193); }
	return (h >>> 0).toString(16);
}
