// Pure impostor maths shared by the runtime (impostors.ts) and node tests. The shader in
// impostors.ts mirrors frameCoordinates() line for line; keep them in sync.

const TAU = Math.PI * 2;

/** Grid convention of an `xexoria.impostor-atlas/2` manifest, in radians. */
export function gridParams(manifest) {
	const g = manifest.grid;
	const elMin = (g.el_min_deg * Math.PI) / 180;
	const elMax = (g.el_max_deg * Math.PI) / 180;
	return {
		azimuth: g.azimuth,
		elevation: g.elevation,
		elMin,
		elStep: g.elevation > 1 ? (elMax - elMin) / (g.elevation - 1) : 0,
		az0: g.az0_angle_rad,
		azSign: g.az_sign,
	};
}

/** Unit direction (asset-local Babylon axes, asset -> camera) of baked frame (az, el). */
export function frameDirection(params, az, el) {
	const phi = params.az0 + params.azSign * az * (TAU / params.azimuth);
	const e = params.elMin + el * params.elStep;
	return [Math.cos(e) * Math.sin(phi), Math.sin(e), Math.cos(e) * Math.cos(phi)];
}

/**
 * Bilinear frame coordinates for a local view direction (asset -> camera, unit length):
 * azimuth frames a0/a1 with weight wa (0 = a0), elevation rows e0/e1 with weight we.
 */
export function frameCoordinates(params, x, y, z) {
	const step = TAU / params.azimuth;
	const phi = Math.atan2(x, z);
	let t = ((phi - params.az0) * params.azSign) / step;
	t -= params.azimuth * Math.floor(t / params.azimuth);
	const a0 = Math.floor(t);
	const wa = t - a0;
	const a1 = (a0 + 1) % params.azimuth;
	const rows = params.elevation;
	const e = params.elStep > 0 ? (Math.asin(Math.max(-1, Math.min(1, y))) - params.elMin) / params.elStep : 0;
	const clamped = Math.max(0, Math.min(rows - 1, e));
	const e0 = Math.min(Math.floor(clamped), Math.max(rows - 2, 0));
	const e1 = Math.min(e0 + 1, rows - 1);
	const we = Math.max(0, Math.min(1, clamped - e0));
	return { a0: a0 % params.azimuth, a1, wa, e0, e1, we };
}

/** Asset-local direction from a world direction for an instance rotated by yaw (Babylon RotationY). */
export function toLocalDirection(yaw, x, y, z) {
	const c = Math.cos(yaw);
	const s = Math.sin(yaw);
	// Babylon RotationY maps local X to (c, 0, -s) and local Z to (s, 0, c); project onto those axes.
	return [x * c - z * s, y, x * s + z * c];
}

/** UV rectangle [u0, v0, u1, v1] (v = 0 top row) of a frame inside an object's block on its page. */
export function cellRect(page, object, az, el) {
	const u0 = (object.col + az) / page.cols;
	const v0 = (object.row + el) / page.rows;
	return [u0, v0, u0 + 1 / page.cols, v0 + 1 / page.rows];
}

/** Card centre in world space for an instance placed at the asset origin (x, y, z) with yaw and scale. */
export function cardCentre(object, x, y, z, yaw = 0, scale = 1) {
	const [ox, oy, oz] = object.center_from_origin;
	const c = Math.cos(yaw);
	const s = Math.sin(yaw);
	return [x + (ox * c + oz * s) * scale, y + oy * scale, z + (-ox * s + oz * c) * scale];
}

/**
 * Cross-fade amount for a mesh/impostor pair: 0 = real mesh only, 1 = impostor only. Smooth over
 * [swap - band / 2, swap + band / 2]; the dither bounds are mesh [0, 1 - t) and impostor [1 - t, 1).
 */
export function crossFade(distance, swap, band) {
	const a = swap - band / 2;
	const b = swap + band / 2;
	if (distance <= a) return 0;
	if (distance >= b) return 1;
	const u = (distance - a) / (b - a);
	return u * u * (3 - 2 * u);
}

/**
 * Albedo compensation for normal averaging: a baked texel stores the average of several leaf normals,
 * which leans towards the bake camera, so cards over-light the sun side and under-light the shade side.
 * f = clamp(a + b * dot(V, L)) with V = asset->camera and L = towards the light, both unit vectors.
 */
export function viewLightCompensation(a, b, view, light, min = 0.6, max = 1.4) {
	const d = view[0] * light[0] + view[1] * light[1] + view[2] * light[2];
	return Math.min(max, Math.max(min, a + b * d));
}

// ---------------------------------------------------------------------------------------------------------
// Tree LOD plan (C-P1-TREE): LOD0 -> LOD1 by screen coverage, LOD1 -> impostor at the shadow distance + 10 m,
// impostor end at the detail draw distance. Numbers: docs/plans/2026-10-02-device-tiers-plan.md section 3.3
// (static-mesh coverage 0.035 x coverageScale; tree impostor swap = shadow distance + 10 m with a 10 m dithered
// band; detail draw distance 150 / 180 / 230 / 280 m) and the trees decision doc section 4.3.

/** Detail draw distance (impostor end) per preset, metres (device-tiers plan 3.3, desktop column of each preset). */
export const TREE_DETAIL_DISTANCE = Object.freeze({ low: 150, medium: 180, high: 230, ultra: 280, epic: 360 });
/** Base LOD1 screen coverage of a static mesh at the 1080p reference (the oak, assets research L22). */
export const TREE_LOD1_COVERAGE = 0.035;
/** Width of the LOD0 -> LOD1 dithered band, metres (both LODs draw complementary screen-door halves inside it). */
export const TREE_LOD1_BAND = 4;
/** Width of the LOD1 -> impostor dithered band, metres (trees decision 4.3). */
export const TREE_SWAP_BAND = 10;

/** clamp(2.07 Mpx / 3D render pixels, 0.36, 4): a triangle covers about the same pixels on every class. */
export function coverageScale(renderPixels) {
	if (!Number.isFinite(renderPixels) || renderPixels <= 0) return 1;
	return Math.min(4, Math.max(0.36, 2_073_600 / renderPixels));
}

/**
 * Distance at which a bounding sphere of `radius` reaches `coverage` of the screen, with Babylon's
 * useLODScreenCoverage metric: pi (r / d)^2 / (aspect * (2 tan(fov / 2))^2), vertical FOV fixed.
 */
export function coverageDistance(radius, coverage, fov, aspect) {
	const t = 2 * Math.tan(fov / 2);
	return radius * Math.sqrt(Math.PI / (Math.max(1e-6, coverage) * Math.max(1e-6, aspect) * t * t));
}

/**
 * Per-tier tree plan. `profile`: { shadowDistance, renderPixelCount, preset, vegetationDensity }.
 * Returns the swap and band (m), the impostor end (m), the LOD1 coverage threshold and the density (0..1).
 */
export function treeLodPlan(profile, overrides = {}) {
	const swap = Number.isFinite(overrides.swap) ? overrides.swap : (profile.shadowDistance ?? 130) + 10;
	// The end band must not overlap the swap band.
	const end = Math.max(swap + 2 * TREE_SWAP_BAND, TREE_DETAIL_DISTANCE[profile.preset] ?? TREE_DETAIL_DISTANCE.high);
	return {
		lod1Coverage: TREE_LOD1_COVERAGE * coverageScale(profile.renderPixelCount),
		lod1Band: TREE_LOD1_BAND,
		swap,
		band: TREE_SWAP_BAND,
		end,
		density: Math.min(1, Math.max(0, profile.vegetationDensity ?? 1)),
		force: overrides.force ?? null,
	};
}

/** LOD1 switch distance for one tree (bounding radius r at its scale), kept clear of the impostor band. */
export function treeLod1Distance(plan, radius, fov, aspect) {
	const d = coverageDistance(radius, plan.lod1Coverage, fov, aspect);
	return Math.max(plan.lod1Band, Math.min(d, plan.swap - plan.band / 2 - plan.lod1Band));
}

/**
 * Representation of one tree at `distance`: lod0, lod1 and card are [lower, upper) ranges of the 8x8 Bayer
 * threshold (the DitheredTileFadeMaterialPlugin / impostor setFade convention), or null when not drawn.
 * Inside a band two neighbours split the range, so every pixel is drawn by exactly one representation (no pop,
 * no alpha blending): LOD0 -> LOD1 over `lod1Band` around `lod1Distance`, mesh -> card over `band` around `swap`,
 * card -> nothing over `band` just before `end`. Quantised to 1/64 (the dither has 64 levels).
 * `hasCard` false (bushes): the mesh dissolves over the swap band instead of becoming a card.
 */
export function treeLodState(distance, plan, lod1Distance, hasCard = true) {
	const q = (v) => Math.round(v * 64) / 64;
	const full = [0, 1];
	if (plan.force === "none") return { lod0: null, lod1: null, card: null };
	if (plan.force === "lod0") return { lod0: full, lod1: null, card: null };
	if (plan.force === "lod1") return { lod0: null, lod1: full, card: null };
	if (plan.force === "impostor") return hasCard ? { lod0: null, lod1: null, card: full } : { lod0: null, lod1: full, card: null };
	const u = q(crossFade(distance, lod1Distance, plan.lod1Band));            // 0 = LOD0, 1 = LOD1
	const t = q(crossFade(distance, plan.swap, plan.band));                   // 0 = mesh, 1 = card
	const e = q(crossFade(distance, plan.end - plan.band / 2, plan.band));    // 1 = beyond the end
	const meshEnd = 1 - t;
	const range = (a, b) => (b > a ? [a, b] : null);
	return {
		lod0: u < 1 ? range(0, Math.min(1 - u, meshEnd)) : null,
		lod1: u > 0 ? range(Math.min(1 - u, meshEnd), meshEnd) : null,
		card: hasCard && t > 0 ? range(meshEnd, 1 - e) : null,
	};
}

/** Stable vegetation-density thinning: kept while the golden-ratio order of the index is below the density. */
export function densityKeeps(index, density) {
	return (index * 0.61803398875) % 1 < density;
}
