import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { moveCapsule } from "../src/coordinate-collision.mjs";
import { moveGroundedCapsule, parseCityTraversal, sampleCityHeight } from "../src/grounded-city.mjs";

const rect = (id, minX, maxX, minZ, maxZ, y = 0, kind = "ground") => ({
	id, kind, vertices: [[minX, y, minZ], [maxX, y, minZ], [maxX, y, maxZ], [minX, y, maxZ]], triangles: [[0, 1, 2], [0, 2, 3]],
});
function payload(surfaces = [rect("floor", -10, 10, -10, 10)], blockers = []) {
	return { schema: "xexoria.city-traversal/1", units: "metres", city_bounds: { min_x: -10, max_x: 10, min_z: -10, max_z: 10 },
		contract: { max_step_m: 0.36, max_slope_degrees: 50, feet_offset_m: 0.015, query_epsilon_m: 0.00005, max_movement_substep_m: 0.1 }, surfaces, blockers };
}
const near = (value, expected, label) => assert.ok(Math.abs(value - expected) < 0.0001, `${label}: ${value} vs ${expected}`);
function move(field, position, delta, boxes = []) { return moveGroundedCapsule(position, delta, 0.35, 1.8, boxes, 308, field); }

test("highest semantic floor is sampled, privately copied, and immutable", () => {
	const source = payload([rect("floor", -10, 10, -10, 10), rect("plinth", -2, 2, -2, 2, 0.15, "stairs")]);
	const field = parseCityTraversal(source);
	assert.equal(sampleCityHeight(field, 0, 0), Math.fround(0.15));
	assert.equal(sampleCityHeight(field, 5, 5), 0);
	assert.ok(Object.isFrozen(field) && Object.isFrozen(field.bounds) && Object.isFrozen(field.stats));
	source.surfaces[1].vertices[0][1] = 99;
	assert.equal(sampleCityHeight(field, 0, 0), Math.fround(0.15));
	assert.throws(() => { field.maxStepM = 9; }, TypeError);
});

test("outside city retains meadow floor but missing authored city support rejects movement", () => {
	const field = parseCityTraversal(payload([rect("west", -10, -1, -10, 10)]));
	assert.equal(sampleCityHeight(field, -11, 0), 0);
	assert.equal(sampleCityHeight(field, 0, 0), null);
	const stopped = move(field, { x: -1.25, z: 0 }, { x: 0.8, z: 0 });
	assert.ok(stopped.x <= -1, `crossed unsupported hole at ${stopped.x}`);
	assert.deepEqual(move(field, { x: 0, z: 0 }, { x: 0.5, z: 0 }), { x: 0, y: 0, z: 0 });
	assert.equal(sampleCityHeight(field, NaN, 0), null);
});

test("grounded steps walk up and down actual .15m stair treads", () => {
	const surfaces = [rect("floor", -10, 10, -10, 10)];
	for (let i = 0; i < 6; i++) surfaces.push(rect(`step-${i}`, i * 0.5, (i + 1) * 0.5, -1, 1, (i + 1) * 0.15, "stairs"));
	const field = parseCityTraversal(payload(surfaces));
	let p = { x: -0.25, z: 0 };
	for (let i = 0; i < 6; i++) p = move(field, p, { x: 0.5, z: 0 });
	near(p.x, 2.75, "climbed position"); near(p.y, 0.9, "climbed support");
	for (let i = 0; i < 6; i++) p = move(field, p, { x: -0.5, z: 0 });
	near(p.x, -0.25, "descended position"); assert.equal(p.y, 0);
});

test("cliff ledges and source bridge .9m approach gaps cannot teleport feet", () => {
	const field = parseCityTraversal(payload([rect("floor", -10, 10, -10, 10), rect("bridge", 0, 4, -1, 1, 0.9, "bridge")]));
	const up = move(field, { x: -0.2, y: 0, z: 0 }, { x: 0.8, z: 0 });
	assert.ok(up.x < 0); assert.equal(up.y, 0);
	const down = move(field, { x: 0.2, y: Math.fround(0.9), z: 0 }, { x: -0.8, z: 0 });
	assert.ok(down.x >= 0); near(down.y, 0.9, "no falling teleport");
	assert.deepEqual(move(field, { x: 0.2, y: 0, z: 0 }, { x: 0.1, z: 0 }), { x: 0.2, y: 0, z: 0 }, "incorrect start height does not snap to bridge");
});

test("slope limit excludes too-steep triangles while ramps remain continuous", () => {
	const ramp = { id: "ramp", kind: "ramp", vertices: [[-1, 0, -1], [1, 0, -1], [1, 1, 1], [-1, 1, 1]], triangles: [[0, 1, 2], [0, 2, 3]] };
	const field = parseCityTraversal(payload([ramp]));
	near(sampleCityHeight(field, 0, 0), 0.5, "ramp interpolation");
	const walked = move(field, { x: 0, z: -0.5 }, { x: 0, z: 1 });
	near(walked.z, 0.5, "ramp progress"); near(walked.y, 0.75, "ramp support");
	const steep = structuredClone(ramp); steep.vertices[2][1] = 4; steep.vertices[3][1] = 4;
	const rejected = parseCityTraversal(payload([steep]));
	assert.equal(rejected.stats.skippedTriangles, 2); assert.equal(sampleCityHeight(rejected, 0, 0), null);
});

test("AABB blockers use current elevation and retain X then Z wall sliding", () => {
	const field = parseCityTraversal(payload([rect("upper terrace", -10, 10, -10, 10, 3, "terrace")]));
	const lower = { minX: 0, maxX: 0.2, minY: 0, maxY: 2, minZ: -3, maxZ: 3 };
	const crossed = move(field, { x: -0.5, z: 0 }, { x: 1, z: 0 }, [lower]);
	near(crossed.x, 0.5, "lower object is vertically clear"); near(crossed.y, 3, "upper support");
	const upper = { ...lower, minY: 3.1, maxY: 5 };
	const slide = move(field, { x: -0.5, z: 0 }, { x: 1, z: 0.5 }, [upper]);
	assert.ok(slide.x <= -0.35); near(slide.z, 0.5, "wall slide");
});

test("polygon blockers expand by radius and vertically clear below the terrace", () => {
	const wall = { id: "rotated wall", kind: "wall", polygon_xz: [[0, -1], [1, 0], [0, 1], [-1, 0]], y_min: 0, y_max: 2 };
	const field = parseCityTraversal(payload(undefined, [wall]));
	const stopped = move(field, { x: -1.5, z: 0 }, { x: 1, z: 0 });
	assert.ok(stopped.x <= -1.35, `capsule penetrated polygon at ${stopped.x}`);
	const corner = moveGroundedCapsule({ x: 0.9, z: 0.9 }, { x: 0.2, z: 0 }, 0.1, 1.8, [], 308, field);
	near(corner.x, 1.1, "outside convex polygon corner must not collide with its AABB");
	const high = parseCityTraversal(payload([rect("terrace", -10, 10, -10, 10, 3, "terrace")], [wall]));
	near(move(high, { x: -0.5, z: 0 }, { x: 1, z: 0 }).x, 0.5, "lower polygon vertical clearance");
});

test("oversized movement is rejected instead of tunnelling and invalid inputs preserve position", () => {
	const field = parseCityTraversal(payload());
	const p = { x: -2, y: 0, z: 0 };
	assert.deepEqual(move(field, p, { x: 9, z: 0 }), p);
	assert.deepEqual(move(field, p, { x: NaN, z: 0 }), p);
	assert.deepEqual(moveGroundedCapsule(p, { x: 0.2, z: 0 }, -1, 1.8, [], 308, field), p);
	assert.deepEqual(move(field, p, { x: 0.2, z: 0 }, [{ minX: NaN }]), p);
	const thin = { minX: 0, maxX: 0.005, minY: 0, maxY: 2, minZ: -3, maxZ: 3 };
	assert.ok(move(field, { x: -1, z: 0 }, { x: 1.5, z: 0 }, [thin]).x <= -0.35);
});

test("parser rejects roofs, forged contract, malformed triangles and unbounded index work", () => {
	for (const change of [
		(p) => { p.surfaces[0].kind = "roof"; },
		(p) => { p.surfaces[0].vertices[0][0] = NaN; },
		(p) => { p.surfaces[0].triangles[0][0] = 9; },
		(p) => { p.contract.max_step_m = 9; },
		(p) => { p.contract.max_slope_degrees = 80; },
		(p) => { delete p.city_bounds; },
		(p) => { p.surfaces.push(p.surfaces[0]); },
		(p) => { p.surfaces[0].vertices[0][0] = -5000; },
	]) { const p = payload(); change(p); assert.throws(() => parseCityTraversal(p), /Invalid city traversal/); }
	const giant = payload([rect("huge floor", -4096, 4096, -4096, 4096)]);
	assert.throws(() => parseCityTraversal(giant), /spatial index/);
	const many = payload(); many.surfaces[0].triangles = Array.from({ length: 50001 }, () => [0, 1, 2]);
	assert.throws(() => parseCityTraversal(many), /triangles/);
	assert.throws(() => sampleCityHeight({}, 0, 0), /parsed city/);
});

test("flat-ground fixture preserves baseline XZ collision within f32 tolerance", () => {
	const cases = [
		{ p: { x: -1, z: 0.5 }, d: { x: 1.4, z: 0 } },
		{ p: { x: 6, z: -1 }, d: { x: 0, z: 1.4 } },
		{ p: { x: 0.123, z: -0.456 }, d: { x: 0.35, z: -0.175 } },
	];
	for (const { p, d } of cases) {
		const old = moveCapsule(p, d, 0.35, 1.8, [], 28);
		const now = moveGroundedCapsule(p, d, 0.35, 1.8, [], 28);
		near(now.x, old.x, "baseline x"); near(now.z, old.z, "baseline z"); assert.equal(now.y, 0);
	}
	// Explicit exact f32 fixture for the server port, rather than double math.
	assert.deepEqual(moveGroundedCapsule({ x: 0.125, z: -0.5 }, { x: 0.25, z: 0 }, 0.35, 1.8, [], 28), { x: 0.3750000298023224, y: 0, z: -0.5 });
});

test("real city payload parses and agrees with authored landmark support", () => {
	const source = JSON.parse(readFileSync(new URL("../../../planning/city-traversal-v1.json", import.meta.url), "utf8"));
	const field = parseCityTraversal(source);
	assert.ok(field.stats.triangleCount <= 50000 && field.stats.vertexCount <= 100000);
	for (const landmark of source.landmarks) near(sampleCityHeight(field, landmark.x, landmark.z), landmark.support_y, landmark.id);
	assert.equal(sampleCityHeight(field, 150, 100), 0, "outside city retains zone floor");
});
