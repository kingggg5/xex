/** Ground-only city traversal. The renderer and prediction share authored support,
 * but this module contains no meshes, network data, or mutable game state.
 * Every geometry operation rounds to f32 in the same order as the Rust port.
 */
const f = Math.fround;
const add = (a, b) => f(f(a) + f(b));
const sub = (a, b) => f(f(a) - f(b));
const mul = (a, b) => f(f(a) * f(b));
const div = (a, b) => f(f(a) / f(b));
const CELL_M = 16;
const WORLD_BOUND_M = 4096;
const MAX_VERTICES = 100000;
const MAX_TRIANGLES = 50000;
const MAX_SURFACES = 4096;
const MAX_BLOCKERS = 2048;
const MAX_INDEX_REFERENCES = 300000;
const MAX_INDEX_CELLS = 8192;
const MAX_BOXES = 4096;
const MAX_SUBSTEPS = 16;
// tan(50 degrees)^2, rounded once; avoid implementation-dependent trig at runtime.
const MAX_SLOPE_TAN_SQUARED = f(1.420276625461206);
const SUPPORT_KINDS = new Set(["ground", "path", "plaza", "plaza_base", "terrace", "stairs", "bridge", "castle_forecourt", "ramp"]);
const BLOCKER_KINDS = new Set(["solid_structure", "tree_trunk", "wall", "street_object", "water_hazard"]);
const fields = new WeakMap();

function invalid(message) { throw new TypeError(`Invalid city traversal: ${message}`); }
function boundedNumber(value, label) {
	if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > WORLD_BOUND_M) invalid(label);
	return f(value);
}
function array(value, limit, label) {
	if (!Array.isArray(value) || value.length > limit) invalid(label);
	return value;
}
function vec(value, count, label) {
	if (!Array.isArray(value) || value.length !== count) invalid(label);
	return value.map((v) => boundedNumber(v, label));
}
function named(value, label) {
	if (typeof value !== "string" || value.length < 1 || value.length > 240) invalid(label);
	return value;
}
function key(x, z) { return `${x},${z}`; }
function convexPolygon(polygon) {
	let orientation = 0;
	for (let i=0;i<polygon.length;i++) {
		const a=polygon[i],b=polygon[(i+1)%polygon.length],dx=sub(b[0],a[0]),dz=sub(b[1],a[1]);
		if (dx===0 && dz===0) return false;
		for (const point of polygon) {
			const cross=sub(mul(dx,sub(point[1],a[1])),mul(dz,sub(point[0],a[0])));
			if (Math.abs(cross)<=f(.00001)) continue;
			const sign=Math.sign(cross);if (!orientation) orientation=sign;else if(sign!==orientation)return false;
		}
	}
	return orientation!==0;
}
function insert(index, item, bounds, budget) {
	const minX = Math.floor(bounds.minX / CELL_M), maxX = Math.floor(bounds.maxX / CELL_M);
	const minZ = Math.floor(bounds.minZ / CELL_M), maxZ = Math.floor(bounds.maxZ / CELL_M);
	const count = (maxX - minX + 1) * (maxZ - minZ + 1);
	budget.references += count;
	if (budget.references > MAX_INDEX_REFERENCES) invalid("spatial index reference budget");
	for (let x = minX; x <= maxX; x++) for (let z = minZ; z <= maxZ; z++) {
		const cellKey = key(x, z);
		let cell = index.get(cellKey);
		if (!cell) {
			if (index.size >= MAX_INDEX_CELLS) invalid("spatial index cell budget");
			cell = []; index.set(cellKey, cell);
		}
		cell.push(item);
	}
}

/** Validate and privately copy the authored payload. Roofs and decorative meshes
 * cannot become floors by adding a high triangle to a recognized input schema.
 */
export function parseCityTraversal(input, worldExtent = WORLD_BOUND_M) {
	if (!Number.isFinite(worldExtent) || worldExtent <= 0 || worldExtent > WORLD_BOUND_M) invalid('zone extent');
	const checkExtent = (values) => { if (values.some(v => Math.abs(v) > worldExtent)) invalid('coordinate outside zone extent'); };
	if (!input || typeof input !== "object" || !["xexoria.city-traversal/1","xexoria.city-traversal/2"].includes(input.schema) || input.units !== "metres") invalid("schema/units");
	const policy = input.contract;
	const hasWorldSupport=!!policy&&Object.prototype.hasOwnProperty.call(policy,'world_support');
	if(hasWorldSupport&&typeof policy.world_support!=='boolean')invalid('world_support must be boolean');
	const worldSupport=hasWorldSupport&&policy.world_support===true;
	if((input.schema==='xexoria.city-traversal/2')!==worldSupport)invalid('world_support requires schema2; schema2 requires true');
	if (!policy || !Number.isFinite(policy.max_step_m) || policy.max_step_m <= 0 || policy.max_step_m > 0.36 ||
		policy.max_slope_degrees !== 50 || !Number.isFinite(policy.query_epsilon_m) || policy.query_epsilon_m <= 0 || policy.query_epsilon_m > 0.00005 ||
		!Number.isFinite(policy.max_movement_substep_m) || policy.max_movement_substep_m < 0.025 || policy.max_movement_substep_m > 0.1 ||
		!Number.isFinite(policy.feet_offset_m) || policy.feet_offset_m < 0 || policy.feet_offset_m > 0.03) invalid("movement contract");
	const bounds = input.city_bounds;
	if (!bounds || typeof bounds !== "object") invalid("explicit city_bounds required");
	const domain = {
		minX: boundedNumber(bounds.min_x, "city min_x"), maxX: boundedNumber(bounds.max_x, "city max_x"),
		minZ: boundedNumber(bounds.min_z, "city min_z"), maxZ: boundedNumber(bounds.max_z, "city max_z"),
	};
	if (domain.minX >= domain.maxX || domain.minZ >= domain.maxZ) invalid("city bounds order");
	checkExtent(Object.values(domain));
	const triangleIndex = new Map(), blockerIndex = new Map();
	const budget = { references: 0 };
	const ids = new Set();
	let vertexCount = 0, triangleCount = 0, skippedTriangles = 0;
	for (const surface of array(input.surfaces, MAX_SURFACES, "surfaces")) {
		if (!surface || !SUPPORT_KINDS.has(surface.kind)) invalid("surface kind (roof/non-support excluded)");
		const id = named(surface.id, "surface id");
		if (ids.has(id)) invalid("duplicate surface id");
		ids.add(id);
		const vertices = array(surface.vertices, MAX_VERTICES, "vertices").map((v) => vec(v, 3, "vertex"));
		for (const vertex of vertices) checkExtent(vertex);
		vertexCount += vertices.length;
		if (vertexCount > MAX_VERTICES) invalid("total vertex budget");
		for (const indices of array(surface.triangles, MAX_TRIANGLES, "triangles")) {
			triangleCount++;
			if (triangleCount > MAX_TRIANGLES) invalid("total triangle budget");
			if (!Array.isArray(indices) || indices.length !== 3 || indices.some((i) => !Number.isInteger(i) || i < 0 || i >= vertices.length)) invalid("triangle indices");
			const [a, b, c] = indices.map((i) => vertices[i]);
			const abX = sub(b[0], a[0]), abY = sub(b[1], a[1]), abZ = sub(b[2], a[2]);
			const acX = sub(c[0], a[0]), acY = sub(c[1], a[1]), acZ = sub(c[2], a[2]);
			const area = sub(mul(abX, acZ), mul(abZ, acX));
			const nx = sub(mul(abY, acZ), mul(abZ, acY));
			const nz = sub(mul(abX, acY), mul(abY, acX));
			const horizontalNormalSquared = add(mul(nx, nx), mul(nz, nz));
			if (Math.abs(area) < 0.00000001 || horizontalNormalSquared > mul(mul(area, area), MAX_SLOPE_TAN_SQUARED)) {
				skippedTriangles++; continue;
			}
			const triBounds = { minX: Math.min(a[0], b[0], c[0]), maxX: Math.max(a[0], b[0], c[0]), minZ: Math.min(a[2], b[2], c[2]), maxZ: Math.max(a[2], b[2], c[2]) };
			insert(triangleIndex, { a, abX, abY, abZ, acX, acY, acZ, area, bounds: triBounds }, triBounds, budget);
		}
	}
	ids.clear();
	let polygonVertices = 0;
	for (const blocker of array(input.blockers ?? [], MAX_BLOCKERS, "blockers")) {
		if (!blocker || !BLOCKER_KINDS.has(blocker.kind)) invalid("blocker kind");
		const id = named(blocker.id, "blocker id");
		if (ids.has(id)) invalid("duplicate blocker id");
		ids.add(id);
		const polygon = array(blocker.polygon_xz, 64, "blocker polygon").map((v) => vec(v, 2, "polygon vertex"));
		for (const vertex of polygon) checkExtent(vertex);
		polygonVertices += polygon.length;
		if (polygon.length < 3 || polygonVertices > MAX_VERTICES) invalid("polygon vertex budget");
		if (!convexPolygon(polygon)) invalid('blocker polygon must be nondegenerate convex boundary');
		const minY = boundedNumber(blocker.y_min, "blocker y_min"), maxY = boundedNumber(blocker.y_max, "blocker y_max");
		checkExtent([minY, maxY]);
		if (minY >= maxY) invalid("blocker height order");
		const polyBounds = { minX: Math.min(...polygon.map((p) => p[0])), maxX: Math.max(...polygon.map((p) => p[0])), minZ: Math.min(...polygon.map((p) => p[1])), maxZ: Math.max(...polygon.map((p) => p[1])) };
		insert(blockerIndex, { polygon, minY, maxY, bounds: polyBounds }, polyBounds, budget);
	}
	if (triangleIndex.size + blockerIndex.size > MAX_INDEX_CELLS) invalid('combined spatial cell budget');
	const field = Object.freeze({
		schema: input.schema, worldSupport, bounds: Object.freeze(domain), maxStepM: f(policy.max_step_m),
		maxSlopeDegrees: 50, epsilonM: f(policy.query_epsilon_m), substepM: f(policy.max_movement_substep_m),
		feetOffsetM: f(policy.feet_offset_m), stats: Object.freeze({ vertexCount, triangleCount, skippedTriangles, blockerCount: ids.size, indexReferences: budget.references, indexCells: triangleIndex.size + blockerIndex.size }),
	});
	fields.set(field, { triangleIndex, blockerIndex });
	return field;
}

function inCity(field, x, z) {
	const b = field.bounds;
	return x >= b.minX && x <= b.maxX && z >= b.minZ && z <= b.maxZ;
}
/** Surface top in metres. A missing floor inside the city is a gap, not zero. */
export function sampleCityHeight(field, x, z) {
	if (!Number.isFinite(x) || !Number.isFinite(z)) return null;
	x = f(x); z = f(z);
	if (!field) return 0;
	const data = fields.get(field);
	if (!data) throw new TypeError("Expected a parsed city traversal field");
	const outside=!inCity(field,x,z);
	if(outside&&!field.worldSupport)return 0;
	const triangles = data.triangleIndex.get(key(Math.floor(x / CELL_M), Math.floor(z / CELL_M))) ?? [];
	let highest = null;
	for (const tri of triangles) {
		const b = tri.bounds, epsilon = field.epsilonM;
		if (x < sub(b.minX, epsilon) || x > add(b.maxX, epsilon) || z < sub(b.minZ, epsilon) || z > add(b.maxZ, epsilon)) continue;
		const ax = sub(x, tri.a[0]), az = sub(z, tri.a[2]);
		const u = div(sub(mul(ax, tri.acZ), mul(az, tri.acX)), tri.area);
		const v = div(sub(mul(tri.abX, az), mul(tri.abZ, ax)), tri.area);
		if (u < -epsilon || v < -epsilon || add(u, v) > add(1, epsilon)) continue;
		const y = add(tri.a[1], add(mul(u, tri.abY), mul(v, tri.acY)));
		if (highest === null || y > highest) highest = y;
	}
	return highest===null&&outside?0:highest;
}

function overlapsBox(x, y, z, radius, height, box) {
	if (f(box.maxY) <= y || f(box.minY) >= add(y, height)) return false;
	const dx = sub(x, Math.max(f(box.minX), Math.min(x, f(box.maxX))));
	const dz = sub(z, Math.max(f(box.minZ), Math.min(z, f(box.maxZ))));
	return add(mul(dx, dx), mul(dz, dz)) <= mul(radius, radius);
}
function overlapsPolygon(x, z, radius, polygon) {
	let inside = false;
	for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
		const a = polygon[j], b = polygon[i];
		const abX = sub(b[0], a[0]), abZ = sub(b[1], a[1]);
		const lengthSquared = add(mul(abX, abX), mul(abZ, abZ));
		const apX = sub(x, a[0]), apZ = sub(z, a[1]);
		const t = lengthSquared > 0 ? Math.max(0, Math.min(1, div(add(mul(apX, abX), mul(apZ, abZ)), lengthSquared))) : 0;
		const dx = sub(x, add(a[0], mul(t, abX))), dz = sub(z, add(a[1], mul(t, abZ)));
		if (add(mul(dx, dx), mul(dz, dz)) <= mul(radius, radius)) return true;
		if ((a[1] > z) !== (b[1] > z) && x < add(a[0], div(mul(sub(z, a[1]), abX), abZ))) inside = !inside;
	}
	return inside;
}
function blocked(data, x, y, z, radius, height, boxes) {
	for (const box of boxes) if (overlapsBox(x, y, z, radius, height, box)) return true;
	if (!data) return false;
	const minX = Math.floor(sub(x, radius) / CELL_M), maxX = Math.floor(add(x, radius) / CELL_M);
	const minZ = Math.floor(sub(z, radius) / CELL_M), maxZ = Math.floor(add(z, radius) / CELL_M);
	for (let cx = minX; cx <= maxX; cx++) for (let cz = minZ; cz <= maxZ; cz++) {
		for (const blocker of data.blockerIndex.get(key(cx, cz)) ?? []) {
			if (blocker.maxY <= y || blocker.minY >= add(y, height)) continue;
			const b = blocker.bounds;
			if (x < sub(b.minX, radius) || x > add(b.maxX, radius) || z < sub(b.minZ, radius) || z > add(b.maxZ, radius)) continue;
			if (overlapsPolygon(x, z, radius, blocker.polygon)) return true;
		}
	}
	return false;
}
function validBoxes(boxes) {
	return Array.isArray(boxes) && boxes.length <= MAX_BOXES && boxes.every((b) => b &&
		[b.minX, b.maxX, b.minY, b.maxY, b.minZ, b.maxZ].every((v) => Number.isFinite(v) && Math.abs(v) <= WORLD_BOUND_M) &&
		b.minX <= b.maxX && b.minY <= b.maxY && b.minZ <= b.maxZ);
}

/** X then Z wall sliding mirrors coordinate-collision. Oversized motion is
 * rejected instead of capping subdivision and tunnelling through a thin wall.
 * Returned y is support height; add feetOffsetM only in character rendering.
 */
export function moveGroundedCapsule(position, delta, radius, height, boxes, worldLimit, field = null) {
	const sampled = sampleCityHeight(field, position.x, position.z);
	const startY = position.y === undefined ? (sampled ?? 0) : position.y;
	const unchanged = { x: position.x, y: startY, z: position.z };
	if (![position.x, position.z, startY, delta.x, delta.z, radius, height, worldLimit].every(Number.isFinite) ||
		radius <= 0 || radius > 2 || height <= 0 || height > 10 || worldLimit <= radius || worldLimit > WORLD_BOUND_M ||
		!validBoxes(boxes) || sampled === null) return unchanged;
	const data = field ? fields.get(field) : null;
	const maxStep = field?.maxStepM ?? f(0.36), epsilon = field?.epsilonM ?? f(0.00005);
	if (Math.abs(sub(sampled, startY)) > add(maxStep, epsilon)) return unchanged;
	const dx = f(delta.x), dz = f(delta.z), stepM = field?.substepM ?? f(0.1);
	const distance = f(Math.sqrt(add(mul(dx, dx), mul(dz, dz))));
	const steps = Math.max(1, Math.ceil(div(distance, stepM)));
	if (steps > MAX_SUBSTEPS) return unchanged;
	const coordinateLimit = sub(worldLimit, radius);
	const clamp = (v) => f(Math.max(-coordinateLimit, Math.min(coordinateLimit, v)));
	let x = clamp(position.x), z = clamp(position.z), y = f(startY);
	const sx = div(dx, steps), sz = div(dz, steps);
	const tryAt = (tx, tz) => {
		const support = sampleCityHeight(field, tx, tz);
		if (support === null || Math.abs(sub(support, y)) > add(maxStep, epsilon) || blocked(data, tx, support, tz, f(radius), f(height), boxes)) return false;
		y = support; return true;
	};
	for (let i = 0; i < steps; i++) {
		const nx = clamp(add(x, sx));
		if (tryAt(nx, z)) x = nx;
		const nz = clamp(add(z, sz));
		if (tryAt(x, nz)) z = nz;
	}
	return { x, y, z };
}
