import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { capsuleOverlapsBox, fixtureCollisionBoxes, moveCapsule, staticColliderBoxes } from "../src/coordinate-collision.mjs";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine.js";
import { Mesh } from "@babylonjs/core/Meshes/mesh.js";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder.js";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData.js";
import { Scene } from "@babylonjs/core/scene.js";
import { Vector3 } from "@babylonjs/core/Maths/math.vector.js";

const fixture = JSON.parse(readFileSync(new URL("../../protocol/coordinate-fixture-v1.json", import.meta.url), "utf8"));

function assertNear(actual, expected, tolerance, label) {
	assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: expected ${expected}, received ${actual}`);
}

function worldBounds(mesh) {
	mesh.computeWorldMatrix(true);
	const bounds = mesh.getBoundingInfo().boundingBox;
	return { min: bounds.minimumWorld, max: bounds.maximumWorld };
}

test("Babylon geometry matches the shared meter, axis, doorway, and ramp fixture", () => {
	assert.equal(fixture.schema_version, 1);
	assert.equal(fixture.units, "m");
	assert.equal(fixture.handedness, "left");
	assert.deepEqual(fixture.axes, { right: "+x", up: "+y", forward: "+z" });

	const engine = new NullEngine({ renderWidth: 64, renderHeight: 64 });
	const scene = new Scene(engine);
	const fixtureBoxes = fixtureCollisionBoxes(fixture);
	try {
		assert.equal(scene.useRightHandedSystem, false);

		const cubeSpec = fixture.unit_cube;
		const cube = MeshBuilder.CreateBox("fixture-unit-cube", {
			width: cubeSpec.dimensions[0],
			height: cubeSpec.dimensions[1],
			depth: cubeSpec.dimensions[2],
		}, scene);
		cube.position = Vector3.FromArray(cubeSpec.center);
		const cubeBounds = worldBounds(cube);
		for (const axis of ["x", "y", "z"]) {
			assertNear(cubeBounds.min[axis], 0, fixture.tolerance_m, `cube minimum ${axis}`);
			assertNear(cubeBounds.max[axis], 1, fixture.tolerance_m, `cube maximum ${axis}`);
		}
		assertNear(cubeBounds.min.x, fixtureBoxes[0].minX, fixture.tolerance_m, "cube collision minimum x");
		assertNear(cubeBounds.max.z, fixtureBoxes[0].maxZ, fixture.tolerance_m, "cube collision maximum z");

		const capsuleSpec = fixture.player_capsule;
		const capsule = MeshBuilder.CreateCapsule("fixture-player-capsule", {
			radius: capsuleSpec.radius,
			height: capsuleSpec.height,
			tessellation: 24,
		}, scene);
		capsule.position = new Vector3(
			capsuleSpec.feet[0],
			capsuleSpec.feet[1] + capsuleSpec.height / 2,
			capsuleSpec.feet[2],
		);
		const capsuleBounds = worldBounds(capsule);
		assertNear(capsuleBounds.min.y, capsuleSpec.feet[1], fixture.tolerance_m, "capsule foot");
		assertNear(capsuleBounds.max.y - capsuleBounds.min.y, capsuleSpec.height, fixture.tolerance_m, "capsule total height");
		assertNear(capsuleBounds.max.x - capsuleBounds.min.x, capsuleSpec.radius * 2, fixture.tolerance_m, "capsule width");

		const doorway = fixture.doorway;
		const [doorX, doorY, doorZ] = doorway.floor_center;
		const post = doorway.wall_thickness;
		const left = MeshBuilder.CreateBox("fixture-door-left", {
			width: post, height: doorway.clear_height, depth: post,
		}, scene);
		left.position.set(doorX - doorway.clear_width / 2 - post / 2, doorY + doorway.clear_height / 2, doorZ);
		const right = MeshBuilder.CreateBox("fixture-door-right", {
			width: post, height: doorway.clear_height, depth: post,
		}, scene);
		right.position.set(doorX + doorway.clear_width / 2 + post / 2, doorY + doorway.clear_height / 2, doorZ);
		const lintel = MeshBuilder.CreateBox("fixture-door-lintel", {
			width: doorway.clear_width + post * 2, height: post, depth: post,
		}, scene);
		lintel.position.set(doorX, doorY + doorway.clear_height + post / 2, doorZ);
		assertNear(worldBounds(left).max.x, doorX - doorway.clear_width / 2, fixture.tolerance_m, "door left clear edge");
		assertNear(worldBounds(right).min.x, doorX + doorway.clear_width / 2, fixture.tolerance_m, "door right clear edge");
		assertNear(worldBounds(lintel).min.y, doorY + doorway.clear_height, fixture.tolerance_m, "door clear height");
		assertNear(worldBounds(left).min.x, fixtureBoxes[1].minX, fixture.tolerance_m, "left jamb collision x");
		assertNear(worldBounds(right).max.z, fixtureBoxes[2].maxZ, fixture.tolerance_m, "right jamb collision z");
		assert.ok(capsuleSpec.radius * 2 < doorway.clear_width);
		assert.ok(capsuleSpec.height < doorway.clear_height);

		const rampSpec = fixture.ramp;
		const [rampX, rampY, rampZ] = rampSpec.lower_origin;
		const positions = [
			rampX - rampSpec.width / 2, rampY, rampZ,
			rampX + rampSpec.width / 2, rampY, rampZ,
			rampX - rampSpec.width / 2, rampY + rampSpec.rise, rampZ + rampSpec.run,
			rampX + rampSpec.width / 2, rampY + rampSpec.rise, rampZ + rampSpec.run,
		];
		const indices = [0, 1, 2, 1, 3, 2];
		const normals = [];
		VertexData.ComputeNormals(positions, indices, normals);
		const rampMesh = new Mesh("fixture-ramp-surface", scene);
		const vertexData = new VertexData();
		vertexData.positions = positions;
		vertexData.indices = indices;
		vertexData.normals = normals;
		vertexData.applyToMesh(rampMesh);
		const rampBounds = worldBounds(rampMesh);
		assertNear(rampBounds.max.x - rampBounds.min.x, rampSpec.width, fixture.tolerance_m, "ramp width");
		assertNear(rampBounds.max.y - rampBounds.min.y, rampSpec.rise, fixture.tolerance_m, "ramp rise");
		assertNear(rampBounds.max.z - rampBounds.min.z, rampSpec.run, fixture.tolerance_m, "ramp run");
	} finally {
		scene.dispose();
		engine.dispose();
	}
});

test("client capsule prediction blocks fixture solids and passes the doorway", () => {
	const boxes = fixtureCollisionBoxes(fixture);
	const { radius, height } = fixture.player_capsule;

	const stopped = moveCapsule({ x: -1, z: 0.5 }, { x: 2, z: 0 }, radius, height, boxes, 28);
	assert.ok(stopped.x > -0.55 && stopped.x <= -0.35 + fixture.tolerance_m, `cube collision ended at ${stopped.x}`);
	assert.equal(stopped.z, 0.5);

	const passed = moveCapsule({ x: 6, z: -1 }, { x: 0, z: 2 }, radius, height, boxes, 28);
	assert.ok(passed.z > 0.9, `capsule did not pass through doorway: ${passed.z}`);

	const blocked = moveCapsule({ x: 5.4, z: -1 }, { x: 0, z: 2 }, radius, height, boxes, 28);
	assert.ok(blocked.z < 0, `doorpost did not stop capsule: ${blocked.z}`);
	assert.equal(capsuleOverlapsBox({ x: 6, z: 0 }, radius, height, {
		minX: 5.25, maxX: 6.75, minY: 2.2, maxY: 2.5, minZ: -0.15, maxZ: 0.15,
	}), false, "capsule should clear the lintel vertically");
});

test("server city-wall boxes leave the gate open and block entry through either wing", () => {
	const boxes = staticColliderBoxes([
		{ id: "town_gate_west_wing", center: [-32.25, 6.5, 24], size: [49.5, 14, 3.4] },
		{ id: "town_gate_east_wing", center: [32.25, 6.5, 24], size: [49.5, 14, 3.4] },
	]);
	const { radius, height } = fixture.player_capsule;
	const throughGate = moveCapsule({ x: 0, z: -2 }, { x: 0, z: 50 }, radius, height, boxes, 308);
	assert.ok(throughGate.z > 24, `open gate blocked entry at z=${throughGate.z}`);
	assert.ok(throughGate.z <= 48, `movement escaped its requested distance at z=${throughGate.z}`);

	const intoWing = moveCapsule({ x: 12, z: -2 }, { x: 0, z: 50 }, radius, height, boxes, 308);
	assert.ok(intoWing.z < 24, `gate wing did not block entry at z=${intoWing.z}`);
	assert.equal(boxes.length, 2);
	assert.equal(boxes[0].minX, -57);
	assert.equal(boxes[1].minX, 7.5);
});
