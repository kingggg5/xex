/** Device-local control presets. The legacy key is read-only; v2 commits in one write. */
import { CONTROL_IDS, LAYOUT_PROFILES, clampControl, clonePositions, loadLayout, parseLayout } from './hud-control-layout.mjs';

export const CONTROL_SET_STORAGE_KEY = 'xexoria_control_sets_v2';
export const MAX_CONTROL_SETS = 12;
export const MAX_CONTROL_SET_NAME = 40;
export const CONTROL_ART_IDS = Object.freeze(['native', 'a02-frostglass', 'a04-wildwood-jade', 'a05-astral-orbit', 'a08-dawn-petal', 'a10-dragonbone', 'b04-floating-thumbstick', 'b09-crystal-silver', 'b13-celestial-rune']);
export const CONTROL_GROUPS = Object.freeze({
	movement: Object.freeze(['joystick', 'context']),
	combat: Object.freeze(['attack', 'arc_slash', 'guard', 'dodge', 'potion']),
	menu: Object.freeze(CONTROL_IDS.filter(id => !['joystick', 'context', 'attack', 'arc_slash', 'guard', 'dodge', 'potion'].includes(id))),
});
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const keys = (value, expected) => record(value) && Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
const copyProfiles = profiles => Object.fromEntries(Object.entries(profiles).map(([profile, positions]) => [profile, clonePositions(positions)]));
const validProfiles = profiles => parseLayout(JSON.stringify({ version: 1, profiles })) !== null;
export function controlSetName(value) {
	return typeof value === 'string' ? [...value.replace(/[\u0000-\u001f\u007f-\u009f]/g, '').trim()].slice(0, MAX_CONTROL_SET_NAME).join('') : '';
}
const sameName = (a, b) => a.toLocaleLowerCase('en') === b.toLocaleLowerCase('en');
export function emptyControlSets(profiles = {}) {
	return { version: 2, activeId: 'default', sets: [{ id: 'default', name: 'Default', art: 'native', profiles: copyProfiles(profiles) }] };
}
export function cloneControlSets(collection) {
	return { version: 2, activeId: collection.activeId, sets: collection.sets.map(set => ({ ...set, profiles: copyProfiles(set.profiles) })) };
}
export function activeControlSet(collection) { return collection.sets.find(set => set.id === collection.activeId) ?? collection.sets[0]; }
export function parseControlSets(raw) {
	if (typeof raw !== 'string' || raw.length > 98304) return null;
	try {
		const data = JSON.parse(raw);
		if (!keys(data, ['version', 'activeId', 'sets']) || data.version !== 2 || typeof data.activeId !== 'string'
			|| !Array.isArray(data.sets) || data.sets.length < 1 || data.sets.length > MAX_CONTROL_SETS) return null;
		const ids = new Set(), names = new Set();
		for (const set of data.sets) {
			if (!keys(set, ['id', 'name', 'art', 'profiles']) || typeof set.id !== 'string' || !/^(default|set-[1-9]\d{0,2})$/.test(set.id)
				|| typeof set.name !== 'string' || !set.name || controlSetName(set.name) !== set.name || !CONTROL_ART_IDS.includes(set.art)
				|| !validProfiles(set.profiles) || ids.has(set.id) || names.has(set.name.toLocaleLowerCase('en'))) return null;
			if (set.id === 'default' && (set.name !== 'Default' || set.art !== 'native')) return null;
			ids.add(set.id); names.add(set.name.toLocaleLowerCase('en'));
		}
		if (data.sets[0].id !== 'default' || !ids.has(data.activeId)) return null;
		return cloneControlSets(data);
	} catch { return null; }
}
export function loadControlSets(storage) {
	try {
		const raw = storage.getItem(CONTROL_SET_STORAGE_KEY);
		if (raw !== null) {
			const parsed = parseControlSets(raw);
			if (parsed) return { collection: parsed, status: 'loaded' };
			const legacy = loadLayout(storage);
			return { collection: emptyControlSets(legacy.layout.profiles), status: legacy.status === 'loaded' ? 'invalid-recovered' : 'invalid' };
		}
		const legacy = loadLayout(storage);
		return { collection: emptyControlSets(legacy.layout.profiles), status: legacy.status === 'loaded' ? 'migrated' : legacy.status };
	} catch { return { collection: emptyControlSets(), status: 'unavailable' }; }
}
/** Save publishes a validated snapshot only after the single local-storage write succeeds. */
export function saveControlSets(storage, saved, draft) {
	let validated;
	try { validated = parseControlSets(JSON.stringify(draft)); } catch { return { ok: false, collection: saved, reason: 'invalid' }; }
	if (!validated) return { ok: false, collection: saved, reason: 'invalid' };
	try { storage.setItem(CONTROL_SET_STORAGE_KEY, JSON.stringify(validated)); return { ok: true, collection: validated }; }
	catch { return { ok: false, collection: saved, reason: 'unavailable' }; }
}
export function createControlSet(collection, name) {
	name = controlSetName(name);
	if (!name) return { ok: false, collection, reason: 'empty-name' };
	if (collection.sets.some(set => sameName(set.name, name))) return { ok: false, collection, reason: 'duplicate-name' };
	if (collection.sets.length >= MAX_CONTROL_SETS) return { ok: false, collection, reason: 'limit' };
	const next = cloneControlSets(collection);
	let index = 1; while (next.sets.some(set => set.id === `set-${index}`)) index++;
	const copy = activeControlSet(next);
	next.activeId = `set-${index}`;
	next.sets.push({ id: next.activeId, name, art: copy.art, profiles: copyProfiles(copy.profiles) });
	return { ok: true, collection: next };
}
export function renameControlSet(collection, name) {
	name = controlSetName(name);
	if (collection.activeId === 'default') return { ok: false, collection, reason: 'protected' };
	if (!name) return { ok: false, collection, reason: 'empty-name' };
	if (collection.sets.some(set => set.id !== collection.activeId && sameName(set.name, name))) return { ok: false, collection, reason: 'duplicate-name' };
	const next = cloneControlSets(collection); activeControlSet(next).name = name;
	return { ok: true, collection: next };
}
export function deleteControlSet(collection) {
	if (collection.activeId === 'default') return { ok: false, collection, reason: 'protected' };
	const next = cloneControlSets(collection);
	next.sets = next.sets.filter(set => set.id !== next.activeId); next.activeId = 'default';
	return { ok: true, collection: next };
}
export function selectControlSet(collection, id) {
	if (!collection.sets.some(set => set.id === id)) return collection;
	const next = cloneControlSets(collection); next.activeId = id; return next;
}
export function updateControlSetProfile(collection, profile, positions) {
	if (!LAYOUT_PROFILES.includes(profile) || !validProfiles({ [profile]: positions })) return collection;
	const next = cloneControlSets(collection), set = activeControlSet(next);
	if (Object.keys(positions).length) set.profiles[profile] = clonePositions(positions); else delete set.profiles[profile];
	return next;
}
export function updateControlSetArt(collection, art) {
	if (collection.activeId === 'default' || !CONTROL_ART_IDS.includes(art)) return collection;
	const next = cloneControlSets(collection); activeControlSet(next).art = art; return next;
}
/** One shared delta stops the entire chosen group at the first safe-area boundary. */
export function translateControlGroup(positions, sizes, delta, viewport, inset = {}) {
	let minX = -Infinity, maxX = Infinity, minY = -Infinity, maxY = Infinity;
	for (const [id, point] of Object.entries(positions)) {
		if (!CONTROL_IDS.includes(id) || !sizes[id]) continue;
		const low = clampControl({ x: 0, y: 0 }, sizes[id], viewport, inset), high = clampControl({ x: 1, y: 1 }, sizes[id], viewport, inset);
		minX = Math.max(minX, low.x - point.x); maxX = Math.min(maxX, high.x - point.x);
		minY = Math.max(minY, low.y - point.y); maxY = Math.min(maxY, high.y - point.y);
	}
	const x = minX > maxX ? 0 : Math.max(minX, Math.min(maxX, Number.isFinite(delta.x) ? delta.x : 0));
	const y = minY > maxY ? 0 : Math.max(minY, Math.min(maxY, Number.isFinite(delta.y) ? delta.y : 0));
	return Object.fromEntries(Object.entries(positions).filter(([id]) => CONTROL_IDS.includes(id) && sizes[id]).map(([id, point]) => [id, { x: point.x + x, y: point.y + y }]));
}
