/**
 * @typedef {import("./coordinate-fixture").CollisionBox} CollisionBox
 * @typedef {import("./coordinate-fixture").CoordinateFixture} CoordinateFixture
 * @typedef {import("./coordinate-fixture").StaticCollider} StaticCollider
 * @typedef {{x: number, z: number}} PositionXZ
 * @typedef {{x: number, z: number}} DeltaXZ
 */

/** @param {[number, number, number]} center @param {[number, number, number]} dimensions @returns {CollisionBox} */
function boxFromCenter(center, dimensions) {
	return {
		minX: center[0] - dimensions[0] / 2,
		maxX: center[0] + dimensions[0] / 2,
		minY: center[1] - dimensions[1] / 2,
		maxY: center[1] + dimensions[1] / 2,
		minZ: center[2] - dimensions[2] / 2,
		maxZ: center[2] + dimensions[2] / 2,
	};
}

/** @param {CoordinateFixture} fixture @returns {CollisionBox[]} */
export function fixtureCollisionBoxes(fixture) {
	const boxes = [boxFromCenter(fixture.unit_cube.center, fixture.unit_cube.dimensions)];
	const doorway = fixture.doorway;
	for (const side of [-1, 1]) {
		const center = [
			doorway.floor_center[0] + side * (doorway.clear_width / 2 + doorway.wall_thickness / 2),
			doorway.floor_center[1] + doorway.clear_height / 2,
			doorway.floor_center[2],
		];
		boxes.push(boxFromCenter(center, [doorway.wall_thickness, doorway.clear_height, doorway.wall_thickness]));
	}
	return boxes;
}

/** @param {StaticCollider[]} colliders @returns {CollisionBox[]} */
export function staticColliderBoxes(colliders) {
	return colliders.map(({ center, size }) => boxFromCenter(center, size));
}

/** @param {PositionXZ} position @param {number} radius @param {number} height @param {CollisionBox} box */
export function capsuleOverlapsBox(position, radius, height, box) {
	if (box.maxY <= 0 || box.minY >= height) return false;
	const closestX = Math.max(box.minX, Math.min(position.x, box.maxX));
	const closestZ = Math.max(box.minZ, Math.min(position.z, box.maxZ));
	const dx = position.x - closestX;
	const dz = position.z - closestZ;
	return dx * dx + dz * dz <= radius * radius;
}

/** @param {PositionXZ} position @param {DeltaXZ} delta @param {number} radius @param {number} height @param {CollisionBox[]} boxes @param {number} worldLimit @returns {PositionXZ} */
export function moveCapsule(position, delta, radius, height, boxes, worldLimit) {
	if (![position.x, position.z, delta.x, delta.z, radius, height, worldLimit].every(Number.isFinite) ||
		radius <= 0 || height <= 0 || worldLimit <= radius) return { ...position };

	const coordinateLimit = worldLimit - radius;
	const maxStep = Math.max(radius / 2, 0.05);
	const distance = Math.max(Math.abs(delta.x), Math.abs(delta.z));
	const steps = Math.min(16, Math.max(1, Math.ceil(distance / maxStep)));
	const stepX = delta.x / steps;
	const stepZ = delta.z / steps;
	let x = Math.max(-coordinateLimit, Math.min(coordinateLimit, position.x));
	let z = Math.max(-coordinateLimit, Math.min(coordinateLimit, position.z));

	for (let step = 0; step < steps; step++) {
		const nextX = Math.max(-coordinateLimit, Math.min(coordinateLimit, x + stepX));
		if (!boxes.some((box) => capsuleOverlapsBox({ x: nextX, z }, radius, height, box))) x = nextX;
		const nextZ = Math.max(-coordinateLimit, Math.min(coordinateLimit, z + stepZ));
		if (!boxes.some((box) => capsuleOverlapsBox({ x, z: nextZ }, radius, height, box))) z = nextZ;
	}
	return { x, z };
}
