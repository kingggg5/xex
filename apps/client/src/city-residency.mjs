/**
 * Pure, bounded city residency decisions. No engine objects, downloads, timers,
 * or disposal occur here. The host applies cancel/evict before starting loads,
 * then submits an acknowledged snapshot on the next update.
 * `residentBytes` is the conservative decoded geometry + texture cost, not GLB
 * transfer size. Count shared resources once upstream, or overestimate them.
 */
const MIB = 1024 * 1024;
const LODS = Object.freeze(["near", "mid", "far"]);
const MAX_CELLS = 4096;
const PROFILE_SPECS = Object.freeze({
	low: { nearDistance: 24, midDistance: 64, farDistance: 150, maxResidentBytes: 64 * MIB, maxResidentCells: 6, maxInflightCells: 1 },
	medium: { nearDistance: 34, midDistance: 90, farDistance: 180, maxResidentBytes: 96 * MIB, maxResidentCells: 8, maxInflightCells: 2 },
	high: { nearDistance: 44, midDistance: 120, farDistance: 230, maxResidentBytes: 160 * MIB, maxResidentCells: 12, maxInflightCells: 2 },
	ultra: { nearDistance: 60, midDistance: 150, farDistance: 280, maxResidentBytes: 256 * MIB, maxResidentCells: 16, maxInflightCells: 3 },
});

/** Explicit policy ceilings, not hardware certification or an FPS promise. */
export function resolveCityResidencyProfile(preset = "medium", { formFactor = "unknown" } = {}) {
	if (!Object.hasOwn(PROFILE_SPECS, preset)) throw new RangeError(`Unknown city residency preset: ${preset}`);
	const mobile = formFactor === "mobile";
	const spec = PROFILE_SPECS[preset];
	return Object.freeze({
		...spec, preset, formFactor,
		maxResidentBytes: Math.min(spec.maxResidentBytes, mobile ? 96 * MIB : Infinity),
		maxResidentCells: Math.min(spec.maxResidentCells, mobile ? 8 : Infinity),
		maxInflightCells: Math.min(spec.maxInflightCells, mobile ? 2 : Infinity),
		hysteresisDistance: 12, prefetchDistance: 28, prefetchSeconds: 3,
		maxPrefetchSpeed: 18, teleportDistance: 140,
	});
}

/**
 * @param {{cells: Array, position: {x:number,z:number}, velocity?: {x:number,z:number},
 * resident?: Array, inflight?: Array, previous?: object, profile?: object,
 * reservedBytes?: number}} input
 * Cells: {id, bounds:{minX,maxX,minZ,maxZ}, lods:{near?:{residentBytes},...}}.
 * Snapshot rows: {cellId,lod,residentBytes?}; inflight also has requestId.
 * previous is the previous plan's `next` DTO; ignore it after scene teardown.
 */
export function planCityResidency({ cells, position, velocity = { x: 0, z: 0 }, resident = [], inflight = [], previous = {}, profile = resolveCityResidencyProfile(), reservedBytes = 0 }) {
	validateProfile(profile);
	const point = validatePoint(position);
	const motion = validatePoint(velocity);
	positiveBytes(reservedBytes, "reservedBytes", true);
	if (!Array.isArray(cells) || cells.length > MAX_CELLS) throw new RangeError(`City catalog must contain at most ${MAX_CELLS} cells.`);
	const catalog = new Map();
	for (const cell of cells) {
		if (!cell || typeof cell.id !== "string" || !cell.id || catalog.has(cell.id)) throw new TypeError("City cells need unique nonempty IDs.");
		const b = cell.bounds;
		if (!b || ![b.minX, b.maxX, b.minZ, b.maxZ].every(Number.isFinite) || b.minX > b.maxX || b.minZ > b.maxZ) throw new TypeError(`Invalid bounds for ${cell.id}.`);
		if (!cell.lods || !LODS.some(lod => cell.lods[lod])) throw new TypeError(`Missing LODs for ${cell.id}.`);
		for (const lod of LODS) if (cell.lods[lod]) positiveBytes(cell.lods[lod].residentBytes, `${cell.id}/${lod}.residentBytes`);
		catalog.set(cell.id, cell);
	}
	const residents = validateSnapshot(resident, catalog, false);
	const pending = validateSnapshot(inflight, catalog, true);
	if (!Array.isArray(previous.selection ?? []) || (previous.selection?.length ?? 0) > MAX_CELLS) throw new RangeError("Previous city selection exceeds the cell limit.");
	const prior = new Map((previous.selection ?? []).map(row => [row.cellId, row.lod]));
	const teleported = previous.position != null && Math.hypot(point.x - validatePoint(previous.position).x, point.z - previous.position.z) > profile.teleportDistance;
	const speed = Math.hypot(motion.x, motion.z);
	const factor = speed > profile.maxPrefetchSpeed ? profile.maxPrefetchSpeed / speed : 1;
	const projected = { x: point.x + motion.x * factor * profile.prefetchSeconds, z: point.z + motion.z * factor * profile.prefetchSeconds };
	const wanted = [];
	for (const cell of cells) {
		const distance = distanceToBounds(point, cell.bounds);
		const oldLod = teleported ? undefined : prior.get(cell.id) ?? residents.get(cell.id)?.lod ?? pending.get(cell.id)?.lod;
		let lod = distanceLod(distance, oldLod, profile);
		let prefetch = false;
		// A bounded swept approach avoids missing a cell between movement samples.
		// Prefetch requests detail only when moving toward that cell's near zone.
		if (!teleported && speed > 0 && distanceToBounds(projected, cell.bounds) < distance && segmentBoundsDistance(point, projected, cell.bounds) <= profile.nearDistance + profile.prefetchDistance && distance > profile.nearDistance + profile.hysteresisDistance) {
			if (lod !== "near") { lod = "near"; prefetch = true; }
		}
		if (lod) wanted.push({ cell, lod, distance, prefetch, rank: prefetch ? 3 : LODS.indexOf(lod) });
	}
	wanted.sort((a, b) => a.rank - b.rank || a.distance - b.distance || a.cell.id.localeCompare(b.cell.id));
	const selection = [], load = [], rejected = [], retireAfterReady = [], replaceUnderPressure = [];
	let accountedBytes = reservedBytes, inflightCount = 0;
	for (const item of wanted) {
		const { cell } = item;
		const existing = residents.get(cell.id);
		const loading = pending.get(cell.id);
		let admitted = false;
		let reason = "missing-lod";
		if (selection.length >= profile.maxResidentCells) { rejected.push({ cellId: cell.id, wantedLod: item.lod, reason: "cell-budget" }); continue; }
		for (const lod of LODS.slice(LODS.indexOf(item.lod))) {
			const asset = cell.lods[lod];
			if (!asset) continue;
			const ready = existing?.lod === lod;
			const requested = !ready && loading?.lod === lod;
			const needsRequest = !ready && !requested;
			let oldBytes = existing && !ready ? snapshotBytes(existing, cell) : 0;
			const targetBytes = ready ? snapshotBytes(existing, cell) : requested ? snapshotBytes(loading, cell) : asset.residentBytes;
			// A snapshot can already exceed a lowered quality ceiling. Release its
			// old variant before allocating a replacement rather than deadlocking.
			const releaseOldFirst = oldBytes > profile.maxResidentBytes - reservedBytes;
			if (releaseOldFirst) oldBytes = 0;
			if (accountedBytes + oldBytes + targetBytes > profile.maxResidentBytes) { reason = "byte-budget"; continue; }
			if (!ready && inflightCount >= profile.maxInflightCells) { reason = "inflight-budget"; continue; }
			accountedBytes += oldBytes + targetBytes;
			if (!ready) inflightCount++;
			selection.push({ cellId: cell.id, lod, distance: item.distance, prefetch: item.prefetch, state: ready ? "resident" : requested ? "loading" : "requested" });
			if (needsRequest) load.push({ cellId: cell.id, lod, residentBytes: targetBytes, reason: item.prefetch ? "approach" : "distance" });
			if (existing && !ready) {
				if (releaseOldFirst) replaceUnderPressure.push({ cellId: cell.id, lod: existing.lod, reason: "replacement-budget" });
				else retireAfterReady.push({ cellId: cell.id, lod: existing.lod, replacementLod: lod });
			}
			admitted = true;
			break;
		}
		// Preserve usable detail while higher-quality work waits for a free slot.
		if (!admitted && existing && accountedBytes + snapshotBytes(existing, cell) <= profile.maxResidentBytes) {
			accountedBytes += snapshotBytes(existing, cell);
			selection.push({ cellId: cell.id, lod: existing.lod, distance: item.distance, prefetch: item.prefetch, state: "resident" });
		}
		if (!admitted) rejected.push({ cellId: cell.id, wantedLod: item.lod, reason });
	}
	const chosen = new Map(selection.map(row => [row.cellId, row]));
	const evict = [...replaceUnderPressure, ...resident.filter(row => !chosen.has(row.cellId)).map(row => ({ cellId: row.cellId, lod: row.lod, reason: teleported ? "teleport" : "outside-or-budget" }))];
	const cancel = inflight.filter(row => { const target = chosen.get(row.cellId); return !target || target.lod !== row.lod || target.state === "resident"; }).map(row => ({ cellId: row.cellId, lod: row.lod, requestId: row.requestId, reason: teleported ? "teleport" : "superseded-or-outside" }));
	return {
		selection, load, evict, cancel, retireAfterReady, rejected, teleported,
		// The whole-city distant proxy is separately owned; keep it until visible
		// prepared districts cover its geometry and after any failed/cancelled load.
		keepDistantFallback: true,
		budget: { accountedBytes, reservedBytes, residentCells: selection.length, inflightCells: inflightCount, maxResidentBytes: profile.maxResidentBytes, maxResidentCells: profile.maxResidentCells, maxInflightCells: profile.maxInflightCells, withinBudget: accountedBytes <= profile.maxResidentBytes },
		next: { position: { ...point }, selection: selection.map(({ cellId, lod }) => ({ cellId, lod })) },
	};
}

function validatePoint(value) {
	if (!value || !Number.isFinite(value.x) || !Number.isFinite(value.z)) throw new TypeError("City position and velocity need finite x/z coordinates.");
	return value;
}
function positiveBytes(value, label, zeroAllowed = false) {
	if (!Number.isSafeInteger(value) || value < (zeroAllowed ? 0 : 1)) throw new RangeError(`${label} must be a ${zeroAllowed ? "nonnegative" : "positive"} safe integer.`);
}
function validateProfile(p) {
	for (const key of ["nearDistance", "midDistance", "farDistance", "hysteresisDistance", "prefetchDistance", "prefetchSeconds", "maxPrefetchSpeed", "teleportDistance"]) if (!Number.isFinite(p[key]) || p[key] < 0) throw new RangeError(`Invalid city profile ${key}.`);
	if (!(p.nearDistance < p.midDistance && p.midDistance < p.farDistance)) throw new RangeError("City LOD distances must increase.");
	for (const key of ["maxResidentBytes", "maxResidentCells", "maxInflightCells"]) positiveBytes(p[key], key);
	if (p.maxResidentCells > MAX_CELLS || p.maxInflightCells > p.maxResidentCells) throw new RangeError("City profile cell limits are invalid.");
}
function validateSnapshot(rows, catalog, isInflight) {
	if (!Array.isArray(rows) || rows.length > MAX_CELLS) throw new RangeError("City snapshots exceed the cell limit.");
	const map = new Map();
	for (const row of rows) {
		const cell = catalog.get(row?.cellId);
		if (!cell || !LODS.includes(row.lod) || !cell.lods[row.lod] || map.has(row.cellId)) throw new TypeError("City snapshot contains an unknown, duplicate, or unavailable cell/LOD.");
		if (row.residentBytes != null) positiveBytes(row.residentBytes, "snapshot residentBytes");
		if (isInflight && (typeof row.requestId !== "string" || !row.requestId)) throw new TypeError("Inflight city loads need a nonempty requestId.");
		map.set(row.cellId, row);
	}
	return map;
}
function snapshotBytes(row, cell) { return row.residentBytes ?? cell.lods[row.lod].residentBytes; }
function distanceLod(distance, previous, p) {
	if (distance <= p.nearDistance || previous === "near" && distance <= p.nearDistance + p.hysteresisDistance) return "near";
	if (distance <= p.midDistance || ["near", "mid"].includes(previous) && distance <= p.midDistance + p.hysteresisDistance) return "mid";
	if (distance <= p.farDistance || previous && distance <= p.farDistance + p.hysteresisDistance) return "far";
	return null;
}
function distanceToBounds(p, b) { return Math.hypot(Math.max(b.minX - p.x, 0, p.x - b.maxX), Math.max(b.minZ - p.z, 0, p.z - b.maxZ)); }
function segmentBoundsDistance(a, b, box) {
	// Squared distance between segment and all rectangle edges, plus endpoints.
	const corners = [{ x: box.minX, z: box.minZ }, { x: box.maxX, z: box.minZ }, { x: box.maxX, z: box.maxZ }, { x: box.minX, z: box.maxZ }];
	let distance = Math.min(distanceToBounds(a, box), distanceToBounds(b, box));
	for (let i = 0; i < 4; i++) {
		const c = corners[i], d = corners[(i + 1) % 4];
		const cross = (u, v, w) => (v.x - u.x) * (w.z - u.z) - (v.z - u.z) * (w.x - u.x);
		if (cross(a, b, c) * cross(a, b, d) <= 0 && cross(c, d, a) * cross(c, d, b) <= 0 && Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x)) <= Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) && Math.max(Math.min(a.z, b.z), Math.min(c.z, d.z)) <= Math.min(Math.max(a.z, b.z), Math.max(c.z, d.z))) return 0;
		distance = Math.min(distance, pointSegmentDistance(a, c, d), pointSegmentDistance(b, c, d), pointSegmentDistance(c, a, b), pointSegmentDistance(d, a, b));
	}
	return distance;
}
function pointSegmentDistance(p, a, b) {
	const dx = b.x - a.x, dz = b.z - a.z, length2 = dx * dx + dz * dz;
	const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.z - a.z) * dz) / length2));
	return Math.hypot(p.x - a.x - dx * t, p.z - a.z - dz * t);
}
