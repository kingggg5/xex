/** Measured startup checkpoints. These units are phases, never a byte-weighted percentage. */
export const BOOTSTRAP_PHASE_IDS = Object.freeze([
	"content", "renderer", "codecs", "assets", "shaders", "room", "snapshot", "first_frame",
]);

const phaseIds = new Set(BOOTSTRAP_PHASE_IDS);
const states = new Set(["pending", "active", "complete", "error"]);
const maximumRecent = 6;

/** Accept only a bounded primitive DTO; discard unrelated engine/server objects. */
export function parseBootstrapPhaseEvent(value) {
	if (!value || typeof value !== "object" || Array.isArray(value)) return null;
	if (!phaseIds.has(value.id) || !states.has(value.state)) return null;
	const event = { id: value.id, state: value.state };
	if (value.resource !== undefined) {
		if (typeof value.resource !== "string" || value.resource.length < 1 || value.resource.length > 160 || /[\r\n\u0000]/.test(value.resource)) return null;
		event.resource = value.resource;
	}
	if (value.errorCode !== undefined) {
		if (typeof value.errorCode !== "string" || !/^[a-z][a-z0-9_.-]{0,63}$/.test(value.errorCode) || value.state !== "error") return null;
		event.errorCode = value.errorCode;
	}
	if (value.loaded !== undefined || value.total !== undefined) {
		if (!Number.isSafeInteger(value.loaded) || value.loaded < 0 || !Number.isSafeInteger(value.total) || value.total <= 0 || value.loaded > value.total || !event.resource) return null;
		event.loaded = value.loaded;
		event.total = value.total;
	}
	return event;
}

/**
 * Forward Babylon's measured transfer counters for ONE named asset only.
 * Transfer completion does not complete the asset phase: its loader promise must settle.
 */
export function bootstrapAssetProgress(resource, progress) {
	const value = { id: "assets", state: "active", resource };
	if (progress?.lengthComputable === true
		&& Number.isSafeInteger(progress.loaded) && progress.loaded >= 0
		&& Number.isSafeInteger(progress.total) && progress.total > 0
		&& progress.loaded <= progress.total) {
		value.loaded = progress.loaded;
		value.total = progress.total;
	}
	return parseBootstrapPhaseEvent(value);
}

/**
 * One bounded startup attempt. Create a new model for a new full attempt/reconnect screen.
 * The caller owns real readiness gates, event timing, UI translations and notifications.
 */
export function createBootstrapProgress(ids = BOOTSTRAP_PHASE_IDS) {
	if (!Array.isArray(ids) || ids.length < 1 || ids.length > BOOTSTRAP_PHASE_IDS.length
		|| new Set(ids).size !== ids.length || ids.some(id => !phaseIds.has(id))) {
		throw new TypeError("Declare a nonempty unique list of known bootstrap phases.");
	}
	const order = [...ids];
	const phases = new Map(order.map(id => [id, { id, state: "pending" }]));
	const recentIds = [];

	function update(input) {
		const event = parseBootstrapPhaseEvent(input);
		if (!event || !phases.has(event.id)) return false;
		const previous = phases.get(event.id);
		// Completed phases remain complete despite duplicate, delayed or failed callbacks.
		if (previous.state === "complete" || (event.state === "pending" && previous.state !== "pending")) return false;
		if (JSON.stringify(previous) === JSON.stringify(event)) return false;
		phases.set(event.id, event);
		const oldIndex = recentIds.indexOf(event.id);
		// Byte-only updates refresh a row, rather than crowding earlier checkpoints out.
		if (previous.state !== event.state || previous.resource !== event.resource || oldIndex < 0) {
			if (oldIndex >= 0) recentIds.splice(oldIndex, 1);
			recentIds.push(event.id);
			if (recentIds.length > maximumRecent) recentIds.shift();
		}
		return true;
	}

	function snapshot() {
		const copy = id => Object.freeze({ ...phases.get(id) });
		const rows = order.map(copy);
		const completed = rows.filter(phase => phase.state === "complete").length;
		return Object.freeze({
			phases: Object.freeze(rows),
			recent: Object.freeze(recentIds.map(copy)),
			completed,
			total: rows.length,
			unit: "phases",
			ready: completed === rows.length,
			failed: rows.some(phase => phase.state === "error"),
		});
	}

	return Object.freeze({ update, snapshot });
}
