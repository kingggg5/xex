/** Device-local layout data only. No game state, input state or engine objects are persisted. */
export const LAYOUT_STORAGE_KEY = "xexoria_control_layout_v1";
export const LAYOUT_PROFILES = Object.freeze(["desktop", "mobile-portrait", "mobile-landscape"]);
export const CONTROL_IDS = Object.freeze([
	"joystick", "attack", "arc_slash", "guard", "dodge", "potion", "bag", "menu", "fullscreen", "context",
	...['character', 'bag', 'skills', 'friends', 'group', 'map', 'store', 'tower', 'settings'].map(id => `nav-${id}`),
]);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
const validPoint = point => record(point) && Object.keys(point).length === 2 && own(point, "x") && own(point, "y")
	&& Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1;
export function layoutProfile(width, height, touch = false) {
	return width <= 900 || touch ? height > width ? "mobile-portrait" : "mobile-landscape" : "desktop";
}
export function clonePositions(positions) {
	return Object.fromEntries(Object.entries(positions).map(([id, point]) => [id, { x: point.x, y: point.y }]));
}
export function emptyLayout() { return { version: 1, profiles: {} }; }
export function parseLayout(raw) {
	if (typeof raw !== "string" || raw.length > 16384) return null;
	try {
		const data = JSON.parse(raw);
		if (!record(data) || data.version !== 1 || !record(data.profiles) || Object.keys(data).length !== 2) return null;
		const output = emptyLayout();
		for (const [profile, positions] of Object.entries(data.profiles)) {
			if (!LAYOUT_PROFILES.includes(profile) || !record(positions) || Object.keys(positions).length > CONTROL_IDS.length) return null;
			for (const [id, point] of Object.entries(positions)) if (!CONTROL_IDS.includes(id) || !validPoint(point)) return null;
			output.profiles[profile] = clonePositions(positions);
		}
		return output;
	} catch { return null; }
}
export function loadLayout(storage) {
	try {
		const raw = storage.getItem(LAYOUT_STORAGE_KEY);
		if (raw === null) return { layout: emptyLayout(), status: "missing" };
		const layout = parseLayout(raw);
		return layout ? { layout, status: "loaded" } : { layout: emptyLayout(), status: "invalid" };
	} catch { return { layout: emptyLayout(), status: "unavailable" }; }
}
/** A failed write leaves the editing session open; callers must not show a saved success. */
export function saveLayoutProfile(storage, layout, profile, positions) {
	if (!LAYOUT_PROFILES.includes(profile) || !record(positions) || Object.keys(positions).length > CONTROL_IDS.length
		|| Object.entries(positions).some(([id, point]) => !CONTROL_IDS.includes(id) || !validPoint(point))) return { ok: false, layout };
	const next = { version: 1, profiles: { ...layout.profiles } };
	if (Object.keys(positions).length) next.profiles[profile] = clonePositions(positions);
	else delete next.profiles[profile];
	const encoded = JSON.stringify(next);
	if (!parseLayout(encoded)) return { ok: false, layout };
	try { storage.setItem(LAYOUT_STORAGE_KEY, encoded); return { ok: true, layout: next }; }
	catch { return { ok: false, layout }; }
}
/** Normalized centers are clamped against real CSS-pixel sizes and visible viewport/safe areas. */
export function clampControl(point, size, viewport, inset = {}) {
	const width = Math.max(1, viewport.width), height = Math.max(1, viewport.height);
	const w = Math.max(44, size.width), h = Math.max(44, size.height);
	const axis = (coordinate, extent, length, start, end) => {
		const low = Math.min(extent / 2, Math.max(0, start) + length / 2 + 4);
		const high = Math.max(low, extent - Math.max(0, end) - length / 2 - 4);
		return Math.max(low, Math.min(high, coordinate * extent));
	};
	const x = axis(Number.isFinite(point.x) ? point.x : .5, width, w, inset.left ?? 0, inset.right ?? 0);
	const y = axis(Number.isFinite(point.y) ? point.y : .5, height, h, inset.top ?? 0, inset.bottom ?? 0);
	return { x: x / width, y: y / height };
}
export function createLayoutSession(positions) {
	return { original: clonePositions(positions), draft: clonePositions(positions), pointer: null };
}
export function resetLayoutSession(session) { session.draft = {}; session.pointer = null; }
export function cancelLayoutSession(session) { session.pointer = null; return clonePositions(session.original); }
export function beginControlDrag(session, id, pointerId, point) {
	if (session.pointer !== null || !CONTROL_IDS.includes(id) || !validPoint(point)) return false;
	session.pointer = { id, pointerId, original: session.draft[id] ? { ...session.draft[id] } : null, start: { ...point } };
	return true;
}
export function updateControlDrag(session, pointerId, point) {
	if (!session.pointer || session.pointer.pointerId !== pointerId || !validPoint(point)) return false;
	session.draft[session.pointer.id] = { ...point }; return true;
}
export function endControlDrag(session, pointerId, cancelled = false) {
	const pointer = session.pointer;
	if (!pointer || pointer.pointerId !== pointerId) return false;
	if (cancelled) {
		if (pointer.original) session.draft[pointer.id] = { ...pointer.original };
		else delete session.draft[pointer.id];
	}
	session.pointer = null; return true;
}
