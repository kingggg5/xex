import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cardCentre, cellRect, crossFade, frameCoordinates, frameDirection, gridParams, toLocalDirection } from "../src/impostor-math.mjs";

const manifest = JSON.parse(readFileSync(new URL("../../../assets/models/impostors/sunmeadow-trees-v2/sunmeadow_trees.impostors.json", import.meta.url), "utf8"));
const params = gridParams(manifest);
const close = (a, b, eps = 1e-5) => Math.abs(a - b) <= eps;

test("manifest v2 declares the grid convention the runtime relies on", () => {
	assert.equal(manifest.schema, "xexoria.impostor-atlas/2");
	assert.equal(params.azimuth, 8);
	assert.equal(params.elevation, 4);
	assert.ok(params.azSign === 1 || params.azSign === -1);
	assert.equal(manifest.frames.length, params.azimuth * params.elevation);
});

test("frameDirection reproduces every baked frame direction", () => {
	for (const frame of manifest.frames) {
		const [x, y, z] = frameDirection(params, frame.az, frame.el);
		assert.ok(close(x, frame.dir[0]) && close(y, frame.dir[1]) && close(z, frame.dir[2]), `frame ${frame.az},${frame.el}`);
	}
});

test("frameCoordinates lands exactly on each baked frame", () => {
	for (const frame of manifest.frames) {
		const c = frameCoordinates(params, ...frame.dir);
		const az = c.wa < 0.5 ? c.a0 : c.a1;
		const el = c.we < 0.5 ? c.e0 : c.e1;
		assert.equal(az, frame.az, `az of ${frame.az},${frame.el}`);
		assert.equal(el, frame.el, `el of ${frame.az},${frame.el}`);
		assert.ok(Math.min(c.wa, 1 - c.wa) < 1e-4, "azimuth weight is 0 or 1 on a baked frame");
		assert.ok(Math.min(c.we, 1 - c.we) < 1e-4, "elevation weight is 0 or 1 on a baked frame");
	}
});

test("halfway between two azimuth frames blends them 50/50", () => {
	const a = frameDirection(params, 2, 1);
	const b = frameDirection(params, 3, 1);
	const mid = [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
	const len = Math.hypot(...mid);
	const c = frameCoordinates(params, mid[0] / len, mid[1] / len, mid[2] / len);
	assert.deepEqual([c.a0, c.a1], [2, 3]);
	assert.ok(close(c.wa, 0.5, 1e-3));
});

test("azimuth wraps from the last frame back to frame 0", () => {
	const last = frameDirection(params, params.azimuth - 1, 0);
	const first = frameDirection(params, 0, 0);
	const mid = [last[0] + first[0], 0, last[2] + first[2]];
	const len = Math.hypot(...mid);
	const c = frameCoordinates(params, mid[0] / len, 0, mid[2] / len);
	assert.deepEqual([c.a0, c.a1], [params.azimuth - 1, 0]);
});

test("elevation clamps below the horizon and above the top row", () => {
	assert.deepEqual([frameCoordinates(params, 0, -0.5, 0.86).e0, frameCoordinates(params, 0, -0.5, 0.86).we], [0, 0]);
	const top = frameCoordinates(params, 0, 0.99, 0.14);
	assert.equal(top.e1, params.elevation - 1);
	assert.equal(top.we, 1);
});

test("instance yaw is undone: rotating instance and camera together keeps the frame", () => {
	const yaw = 1.3;
	const local = frameDirection(params, 5, 2);
	// World direction = RotationY(yaw) applied to the local direction.
	const c = Math.cos(yaw), s = Math.sin(yaw);
	const world = [local[0] * c + local[2] * s, local[1], -local[0] * s + local[2] * c];
	const back = toLocalDirection(yaw, ...world);
	assert.ok(close(back[0], local[0]) && close(back[1], local[1]) && close(back[2], local[2]));
	const coords = frameCoordinates(params, ...back);
	assert.equal(coords.wa < 0.5 ? coords.a0 : coords.a1, 5);
});

test("cell rectangles stay inside the page with v = 0 at the top row", () => {
	for (const object of manifest.objects) {
		const page = manifest.pages[object.page];
		const [u0, v0, u1, v1] = cellRect(page, object, params.azimuth - 1, params.elevation - 1);
		assert.ok(u0 >= 0 && v0 >= 0 && u1 <= 1 + 1e-9 && v1 <= 1 + 1e-9, object.id);
		assert.ok(close(cellRect(page, object, 0, 0)[1], object.row / page.rows));
	}
});

test("card centre follows yaw and scale from the asset origin", () => {
	const object = { col: 0, row: 0, center_from_origin: [1, 3, 0] };
	assert.deepEqual(cardCentre(object, 10, 0, 5, 0, 1), [11, 3, 5]);
	const [x, y, z] = cardCentre(object, 0, 0, 0, Math.PI / 2, 2);
	assert.ok(close(x, 0) && close(y, 6) && close(z, -2));
});

test("cross-fade is 0 inside, 1 outside and smooth across the band", () => {
	assert.equal(crossFade(40, 60, 8), 0);
	assert.equal(crossFade(80, 60, 8), 1);
	assert.ok(close(crossFade(60, 60, 8), 0.5));
	let previous = -1;
	for (let d = 55; d <= 65; d += 0.5) { const t = crossFade(d, 60, 8); assert.ok(t >= previous); previous = t; }
});

test("view-light compensation reproduces the measured real/card ratios (tree A, 30 m, game sun)", async () => {
	const { viewLightCompensation } = await import("../src/impostor-math.mjs");
	// Real vs uncompensated card mean brightness from tests/impostor-review.html, 2026-10-02 (WebGL2).
	const measured = { 0: [109, 116.5], 45: [93, 90.6], 90: [77, 62.4], 135: [70, 58.8], 180: [86, 75.3], 225: [96, 96.5], 270: [109, 127.1], 315: [116, 131.8] };
	const sun = [0.55, 0.82, -0.35];
	const len = Math.hypot(...sun);
	const L = sun.map(v => v / len);
	const shading = manifest.shading;
	for (const [az, [real, card]] of Object.entries(measured)) {
		const a = (Number(az) * Math.PI) / 180;
		const camera = [-Math.sin(a) * 30, 6.6 - 3.5, -Math.cos(a) * 30]; // eye 6.6 m, card centre 3.5 m
		const vl = Math.hypot(...camera);
		const V = camera.map(v => v / vl);
		const f = viewLightCompensation(shading.albedo_scale, shading.view_light_slope, V, L);
		const error = Math.abs(card * f - real) / real;
		assert.ok(error < 0.08, `azimuth ${az}: compensated ${Math.round(card * f)} vs real ${real} (${(error * 100).toFixed(1)} %)`);
	}
	assert.equal(viewLightCompensation(1, -10, [1, 0, 0], [1, 0, 0]), 0.6, "clamped below");
	assert.equal(viewLightCompensation(1, 10, [1, 0, 0], [1, 0, 0]), 1.4, "clamped above");
});

// ---- Tree LOD plan (C-P1-TREE): device-tiers plan 3.3 numbers and the dithered hand-over between representations.
import { coverageDistance, coverageScale, densityKeeps, treeLod1Distance, treeLodPlan, treeLodState, TREE_DETAIL_DISTANCE } from "../src/impostor-math.mjs";

const TIERS = { low: { shadowDistance: 55, renderPixelCount: 1_310_720, preset: "low", vegetationDensity: 0.45 },
	medium: { shadowDistance: 85, renderPixelCount: 2_073_600, preset: "medium", vegetationDensity: 0.7 },
	high: { shadowDistance: 130, renderPixelCount: 2_073_600, preset: "high", vegetationDensity: 1 },
	ultra: { shadowDistance: 190, renderPixelCount: 3_686_400, preset: "ultra", vegetationDensity: 1.25 } };

test("tree plan: swap = shadow distance + 10 m, 10 m band, end at the detail draw distance, density clamped", () => {
	for (const [name, profile] of Object.entries(TIERS)) {
		const plan = treeLodPlan(profile);
		assert.equal(plan.swap, profile.shadowDistance + 10, name);
		assert.equal(plan.band, 10, name);
		assert.equal(plan.end, TREE_DETAIL_DISTANCE[name], name);
		assert.ok(plan.end >= plan.swap + 2 * plan.band, `${name}: end band clear of the swap band`);
		assert.equal(plan.density, Math.min(1, profile.vegetationDensity), name);
	}
	assert.equal(treeLodPlan(TIERS.high, { swap: 60 }).swap, 60);
});

test("coverage scale follows the plan: x1 at 1080p, x4 cap on small phones, x0.36 floor", () => {
	assert.equal(coverageScale(2_073_600), 1);
	assert.equal(coverageScale(300_000), 4);
	assert.equal(coverageScale(20_000_000), 0.36);
	assert.ok(close(coverageScale(921_600), 2.25), "desktop-low 1280x720 = x2.25");
	assert.equal(coverageScale(null), 1);
});

test("coverage distance inverts Babylon's useLODScreenCoverage metric", () => {
	const fov = 1.02, aspect = 16 / 9, radius = 5;
	const d = coverageDistance(radius, 0.035, fov, aspect);
	const minZ = 0.1;
	const screenArea = (minZ * 2 * Math.tan(fov / 2)) ** 2 * aspect;
	const meshArea = Math.PI * ((radius * minZ) / d) ** 2;
	assert.ok(close(meshArea / screenArea, 0.035, 1e-9));
	assert.ok(d > 25 && d < 40, `LOD1 of a 5 m-radius tree at 1080p is ${d}`);
});

test("tree state: one representation per pixel through both dithered bands", () => {
	const plan = treeLodPlan(TIERS.high);
	const d1 = treeLod1Distance(plan, 5, 1.02, 16 / 9);
	const covered = (s) => [s.lod0, s.lod1, s.card].filter(Boolean).reduce((sum, [a, b]) => sum + (b - a), 0);
	for (let d = 0; d < plan.end + 20; d += 0.25) {
		const s = treeLodState(d, plan, d1);
		const ranges = [s.lod0, s.lod1, s.card].filter(Boolean).sort((a, b) => a[0] - b[0]);
		for (let i = 1; i < ranges.length; i++) assert.ok(ranges[i][0] >= ranges[i - 1][1] - 1e-9, `overlap at ${d} m`);
		if (d < plan.end - plan.band) assert.ok(close(covered(s), 1, 1e-9), `hole at ${d} m: ${JSON.stringify(s)}`);
	}
	assert.deepEqual(treeLodState(1, plan, d1), { lod0: [0, 1], lod1: null, card: null });
	assert.deepEqual(treeLodState(d1 + 3, plan, d1), { lod0: null, lod1: [0, 1], card: null });
	assert.deepEqual(treeLodState(plan.swap, plan, d1), { lod0: null, lod1: [0, 0.5], card: [0.5, 1] });
	assert.deepEqual(treeLodState(plan.swap + 6, plan, d1), { lod0: null, lod1: null, card: [0, 1] });
	assert.deepEqual(treeLodState(plan.end + 1, plan, d1), { lod0: null, lod1: null, card: null });
});

test("tree state: no card for bushes (they dissolve over the swap band), forced review modes", () => {
	const plan = treeLodPlan(TIERS.medium);
	const d1 = treeLod1Distance(plan, 1, 1.02, 16 / 9);
	assert.deepEqual(treeLodState(plan.swap, plan, d1, false), { lod0: null, lod1: [0, 0.5], card: null });
	assert.deepEqual(treeLodState(plan.swap + 6, plan, d1, false), { lod0: null, lod1: null, card: null });
	assert.deepEqual(treeLodState(500, treeLodPlan(TIERS.medium, { force: "impostor" }), d1), { lod0: null, lod1: null, card: [0, 1] });
	assert.deepEqual(treeLodState(500, treeLodPlan(TIERS.medium, { force: "lod1" }), d1), { lod0: null, lod1: [0, 1], card: null });
});

test("LOD1 distance never reaches into the impostor band, even with a short swap override", () => {
	const plan = treeLodPlan(TIERS.high, { swap: 30 });
	const d1 = treeLod1Distance(plan, 7, 1.02, 16 / 9);
	assert.ok(d1 + plan.lod1Band / 2 <= plan.swap - plan.band / 2 + 1e-9, `d1 ${d1}`);
});

test("density thinning is stable and close to the requested share", () => {
	const kept = (density) => Array.from({ length: 200 }, (_, i) => densityKeeps(i, density)).filter(Boolean).length / 200;
	assert.ok(Math.abs(kept(0.45) - 0.45) < 0.03);
	assert.ok(Math.abs(kept(0.7) - 0.7) < 0.03);
	assert.equal(kept(1), 1);
	for (let i = 0; i < 50; i++) if (densityKeeps(i, 0.45)) assert.ok(densityKeeps(i, 0.7), "a tree kept at Low stays at Medium");
});
