import test from "node:test";
import assert from "node:assert/strict";
import { projectMinimapCoordinate } from "../src/minimap-projection.mjs";

test("world coordinates use the same measured scale for the player and POI markers", () => {
	const extent = 308;
	const radius = 90;
	const cases = [
		[-308, 12],
		[-152, 51.506493506493506],
		[-24, 83.92207792207792],
		[0, 90],
		[24, 96.07792207792208],
		[176, 134.57142857142856],
		[304, 166.98701298701297],
		[308, 168],
	];
	for (const [coordinate, expected] of cases) {
		assert.ok(Math.abs(projectMinimapCoordinate(coordinate, extent, radius) - expected) < 1e-9);
	}
});

test("minimap projection keeps the center fixed and clamps at the circular edge", () => {
	assert.equal(projectMinimapCoordinate(0, 308, 90), 90);
	assert.equal(projectMinimapCoordinate(-308, 308, 90), 12);
	assert.equal(projectMinimapCoordinate(308, 308, 90), 168);
	assert.equal(projectMinimapCoordinate(-900, 308, 90), 12);
	assert.equal(projectMinimapCoordinate(900, 308, 90), 168);
});
