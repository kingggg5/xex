import test from 'node:test';
import assert from 'node:assert/strict';
import { LAYOUT_STORAGE_KEY, CONTROL_IDS } from '../src/hud-control-layout.mjs';
import {
	CONTROL_GROUPS, CONTROL_SET_STORAGE_KEY, MAX_CONTROL_SETS, activeControlSet, cloneControlSets,
	createControlSet, deleteControlSet, emptyControlSets, loadControlSets, parseControlSets,
	renameControlSet, saveControlSets, selectControlSet, translateControlGroup, updateControlSetArt, updateControlSetProfile,
} from '../src/control-set.mjs';

function memory(initial = {}) {
	const values = new Map(Object.entries(initial)), writes = [];
	return { values, writes, getItem: key => values.get(key) ?? null, setItem(key, value) { writes.push(key); values.set(key, value); } };
}
test('legacy positions migrate across all orientations without a read-time write or deleting legacy data', () => {
	const profiles = { desktop: { attack: { x: .8, y: .8 } }, 'mobile-portrait': { joystick: { x: .2, y: .7 } }, 'mobile-landscape': { potion: { x: .5, y: .8 } } };
	const legacy = JSON.stringify({ version: 1, profiles }), storage = memory({ [LAYOUT_STORAGE_KEY]: legacy });
	const loaded = loadControlSets(storage);
	assert.equal(loaded.status, 'migrated'); assert.equal(activeControlSet(loaded.collection).art, 'native');
	assert.deepEqual(activeControlSet(loaded.collection).profiles, profiles); assert.deepEqual(storage.writes, []);
	let draft = createControlSet(loaded.collection, 'Touch controls').collection;
	draft = updateControlSetProfile(draft, 'mobile-landscape', { attack: { x: .75, y: .85 } });
	draft = updateControlSetArt(draft, 'b13-celestial-rune');
	const saved = saveControlSets(storage, loaded.collection, draft);
	assert.equal(saved.ok, true); assert.deepEqual(storage.writes, [CONTROL_SET_STORAGE_KEY]);
	assert.equal(storage.values.get(LAYOUT_STORAGE_KEY), legacy);
	assert.deepEqual(activeControlSet(saved.collection).profiles.desktop, profiles.desktop);
	assert.deepEqual(activeControlSet(saved.collection).profiles['mobile-portrait'], profiles['mobile-portrait']);
	assert.equal(loadControlSets(storage).status, 'loaded');
});
test('uncommitted edits, selection, rename, deletion, and profile reset are independent of saved sets', () => {
	const original = emptyControlSets({ desktop: { attack: { x: .8, y: .8 } }, 'mobile-landscape': { joystick: { x: .2, y: .8 } } });
	let draft = createControlSet(cloneControlSets(original), 'One-handed').collection;
	draft = updateControlSetArt(draft, 'a04-wildwood-jade');
	draft = updateControlSetProfile(draft, 'desktop', {});
	assert.equal(activeControlSet(draft).profiles.desktop, undefined);
	assert.deepEqual(activeControlSet(draft).profiles['mobile-landscape'], { joystick: { x: .2, y: .8 } });
	draft = renameControlSet(draft, 'Left hand').collection;
	const selected = selectControlSet(draft, 'default');
	assert.equal(activeControlSet(selected).art, 'native');
	assert.equal(activeControlSet(draft).name, 'Left hand');
	draft = deleteControlSet(draft).collection;
	assert.deepEqual(draft, original); assert.deepEqual(original.sets[0].profiles.desktop, { attack: { x: .8, y: .8 } });
});
test('protected original style, unique names, and the twelve-set bound are enforced', () => {
	let data = emptyControlSets();
	assert.equal(deleteControlSet(data).ok, false); assert.equal(renameControlSet(data, 'new').ok, false);
	assert.equal(updateControlSetArt(data, 'a02-frostglass'), data);
	assert.equal(createControlSet(data, '  ').reason, 'empty-name');
	data = createControlSet(data, ' Custom ').collection;
	assert.equal(activeControlSet(data).name, 'Custom');
	assert.equal(createControlSet(data, 'custom').reason, 'duplicate-name');
	for (let i = 2; i < MAX_CONTROL_SETS; i++) data = createControlSet(data, `Set ${i}`).collection;
	assert.equal(data.sets.length, MAX_CONTROL_SETS); assert.equal(createControlSet(data, 'Too many').reason, 'limit');
	assert.equal(parseControlSets(JSON.stringify(data)).sets.length, MAX_CONTROL_SETS);
});
test('a denied canonical write retains the exact saved state and leaves the draft retryable', () => {
	const saved = emptyControlSets(), draft = createControlSet(saved, 'Retry me').collection;
	let attempts = 0;
	const blocked = { setItem(key) { attempts++; assert.equal(key, CONTROL_SET_STORAGE_KEY); throw new Error('QuotaExceededError'); } };
	const result = saveControlSets(blocked, saved, draft);
	assert.equal(result.ok, false); assert.equal(result.collection, saved); assert.equal(attempts, 1);
	assert.equal(activeControlSet(draft).name, 'Retry me'); assert.equal(saved.sets.length, 1);
	const storage = memory(); assert.equal(saveControlSets(storage, saved, draft).ok, true);
	assert.deepEqual(storage.writes, [CONTROL_SET_STORAGE_KEY]);
});
test('malformed or hostile new data is rejected and valid earlier layout is recovered', () => {
	const valid = emptyControlSets(), encode = change => { const next = cloneControlSets(valid); change(next); return JSON.stringify(next); };
	const invalid = [null, '{', ' '.repeat(98305), encode(next => next.activeId = 'unknown'),
		encode(next => next.sets[0].art = 'unknown'), encode(next => next.sets[0].art = 'a02-frostglass'),
		encode(next => next.sets[0].profiles.desktop = { attack: { x: -1, y: .5 } }),
		encode(next => next.sets[0].profiles.desktop = { unknown: { x: .5, y: .5 } }),
		encode(next => next.sets[0].profiles.desktop = { attack: { x: '.5', y: .5 } }),
		encode(next => next.sets[0].extra = 'unknown'),
		'{"version":2,"activeId":"default","sets":[{"id":"default","name":"Default","art":"native","profiles":{"__proto__":{"attack":{"x":0.5,"y":0.5}}}}]}'];
	for (const value of invalid) assert.equal(parseControlSets(value), null);
	const legacy = JSON.stringify({ version: 1, profiles: { desktop: { guard: { x: .3, y: .4 } } } });
	const storage = memory({ [CONTROL_SET_STORAGE_KEY]: '{', [LAYOUT_STORAGE_KEY]: legacy });
	const restored = loadControlSets(storage);
	assert.equal(restored.status, 'invalid-recovered'); assert.deepEqual(activeControlSet(restored.collection).profiles.desktop.guard, { x: .3, y: .4 });
	assert.equal(storage.values.get(CONTROL_SET_STORAGE_KEY), '{'); assert.deepEqual(storage.writes, []);
	assert.equal({}.attack, undefined);
	assert.equal(loadControlSets({ getItem() { throw new Error('SecurityError'); } }).status, 'unavailable');
});
test('movement, combat, and menu groups partition the actual adjustable controls', () => {
	const ids = Object.values(CONTROL_GROUPS).flat();
	assert.equal(new Set(ids).size, ids.length); assert.deepEqual([...ids].sort(), [...CONTROL_IDS].sort());
});
test('a whole group moves by one shared safe-area-clamped delta and retains its spacing', () => {
	const positions = { attack: { x: .75, y: .7 }, guard: { x: .85, y: .6 } }, sizes = { attack: { width: 64, height: 64 }, guard: { width: 44, height: 44 } };
	const view = { width: 844, height: 390 }, safe = { left: 30, right: 30, top: 20, bottom: 20 };
	const moved = translateControlGroup(positions, sizes, { x: 2, y: 2 }, view, safe);
	assert.ok(moved.guard.x * view.width + 22 <= view.width - safe.right - 4 + 1e-6);
	assert.ok(moved.attack.y * view.height + 32 <= view.height - safe.bottom - 4 + 1e-6);
	assert.ok(Math.abs((moved.guard.x - moved.attack.x) - .1) < 1e-10);
	assert.ok(Math.abs((moved.attack.y - moved.guard.y) - .1) < 1e-10);
	assert.deepEqual(positions, { attack: { x: .75, y: .7 }, guard: { x: .85, y: .6 } });
	const left = translateControlGroup(positions, sizes, { x: -2, y: -2 }, view, safe);
	assert.ok(left.attack.x * view.width - 32 >= safe.left + 4 - 1e-6);
	assert.ok(left.guard.y * view.height - 22 >= safe.top + 4 - 1e-6);
});
