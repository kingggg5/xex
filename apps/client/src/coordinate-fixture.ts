export interface CoordinateFixture {
	schema_version: 1;
	units: "m";
	handedness: "left";
	axes: { right: "+x"; up: "+y"; forward: "+z" };
	tolerance_m: number;
	unit_cube: { center: [number, number, number]; dimensions: [number, number, number] };
	player_capsule: { feet: [number, number, number]; radius: number; height: number; axis: "+y" };
	doorway: {
		floor_center: [number, number, number];
		clear_width: number;
		clear_height: number;
		wall_thickness: number;
	};
	ramp: { lower_origin: [number, number, number]; width: number; run: number; rise: number };
}

export interface CollisionBox {
	minX: number;
	maxX: number;
	minY: number;
	maxY: number;
	minZ: number;
	maxZ: number;
}

/** A server-authored, axis-aligned static obstacle in world meters. */
export interface StaticCollider {
	id: string;
	center: [number, number, number];
	size: [number, number, number];
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isVector3(value: unknown): value is [number, number, number] {
	return Array.isArray(value) && value.length === 3 && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

function isPositive(value: unknown): value is number {
	return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function parseCoordinateFixture(value: unknown): CoordinateFixture {
	if (!isRecord(value) || value.schema_version !== 1 || value.units !== "m" || value.handedness !== "left") {
		throw new Error("Unsupported coordinate fixture version or convention.");
	}
	if (!isRecord(value.axes) || value.axes.right !== "+x" || value.axes.up !== "+y" || value.axes.forward !== "+z") {
		throw new Error("Coordinate fixture axes do not match the game world.");
	}
	const tolerance = value.tolerance_m;
	if (!isPositive(tolerance) || tolerance > 0.01) throw new Error("Invalid coordinate tolerance.");
	if (!isRecord(value.unit_cube) || !isVector3(value.unit_cube.center) || !isVector3(value.unit_cube.dimensions)) {
		throw new Error("Invalid unit-cube fixture.");
	}
	if (!value.unit_cube.dimensions.every((dimension) => Math.abs(dimension - 1) <= tolerance)) {
		throw new Error("Coordinate fixture cube must measure one meter on every axis.");
	}
	if (!isRecord(value.player_capsule) || !isVector3(value.player_capsule.feet) || value.player_capsule.axis !== "+y" ||
		!isPositive(value.player_capsule.radius) || !isPositive(value.player_capsule.height) ||
		value.player_capsule.height + tolerance < value.player_capsule.radius * 2) {
		throw new Error("Invalid player capsule fixture.");
	}
	if (!isRecord(value.doorway) || !isVector3(value.doorway.floor_center) ||
		!isPositive(value.doorway.clear_width) || !isPositive(value.doorway.clear_height) ||
		!isPositive(value.doorway.wall_thickness) || value.doorway.clear_width + tolerance < value.player_capsule.radius * 2 ||
		value.doorway.clear_height + tolerance < value.player_capsule.height) {
		throw new Error("Invalid doorway fixture or capsule clearance.");
	}
	if (!isRecord(value.ramp) || !isVector3(value.ramp.lower_origin) || !isPositive(value.ramp.width) ||
		!isPositive(value.ramp.run) || !isPositive(value.ramp.rise)) {
		throw new Error("Invalid ramp fixture.");
	}
	return value as unknown as CoordinateFixture;
}

export function parseStaticColliders(value: unknown): StaticCollider[] {
	if (!Array.isArray(value) || value.length > 512) {
		throw new Error("Invalid zone static-collider list.");
	}
	const ids = new Set<string>();
	return value.map((entry) => {
		if (!isRecord(entry) || typeof entry.id !== "string" || !/^[a-zA-Z0-9_-]{1,64}$/.test(entry.id) ||
			ids.has(entry.id) || !isVector3(entry.center) || !isVector3(entry.size) ||
			!entry.size.every((dimension) => dimension > 0)) {
			throw new Error("Invalid zone static collider.");
		}
		ids.add(entry.id);
		return {
			id: entry.id,
			center: [...entry.center] as [number, number, number],
			size: [...entry.size] as [number, number, number],
		};
	});
}
