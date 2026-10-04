import test from "node:test";
import assert from "node:assert/strict";
import {
	LAYOUT_STORAGE_KEY, beginControlDrag, cancelLayoutSession, clampControl, createLayoutSession,
	emptyLayout, endControlDrag, layoutProfile, loadLayout, parseLayout, resetLayoutSession,
	saveLayoutProfile, updateControlDrag,
} from "../src/hud-control-layout.mjs";

const memory = initial => {
	const entries = new Map(initial === undefined ? [] : [[LAYOUT_STORAGE_KEY, initial]]);
	return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value) };
};
test("desktop and mobile orientations keep independent positions", () => {
	assert.equal(layoutProfile(1440, 900), "desktop");
	assert.equal(layoutProfile(844, 390), "mobile-landscape");
	assert.equal(layoutProfile(390, 844), "mobile-portrait");
	assert.equal(layoutProfile(1024, 768, true), "mobile-landscape");
	const storage = memory();
	let data = emptyLayout();
	for (const [profile, x] of [["desktop", .1], ["mobile-landscape", .8], ["mobile-portrait", .9]]) {
		const result = saveLayoutProfile(storage, data, profile, { attack: { x, y: .7 } });
		assert.equal(result.ok, true); data = result.layout;
	}
	const loaded = loadLayout(storage);
	assert.equal(loaded.status, "loaded");
	assert.deepEqual(Object.values(loaded.layout.profiles).map(value => value.attack.x), [.1, .8, .9]);
});
test("invalid, oversized and unknown saved data never enters layout state", () => {
	const encode = positions => JSON.stringify({ version: 1, profiles: { desktop: positions } });
	for (const value of ["{", " ".repeat(16385), "null", "[]", JSON.stringify({ version: 2, profiles: {} }),
		encode({ attack: { x: -1, y: .5 } }), encode({ attack: { x: .1, y: 1.01 } }),
		encode({ attack: { x: ".5", y: .5 } }), encode({ attack: { x: .5, y: .5, arbitrary: 1 } }),
		encode({ unknown_control: { x: .5, y: .5 } }), '{"version":1,"profiles":{"__proto__":{"attack":{"x":0.5,"y":0.5}}}}',
		'{"version":1,"profiles":{"desktop":{"__proto__":{"x":0.5,"y":0.5}}}}']) {
		assert.equal(parseLayout(value), null);
		assert.deepEqual(loadLayout(memory(value)), { status: "invalid", layout: emptyLayout() });
	}
	assert.equal({}.attack, undefined);
});
test("unavailable storage reports failure and retains the prior saved layout", () => {
	const denied = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("QuotaExceededError"); } };
	assert.equal(loadLayout(denied).status, "unavailable");
	const layout = { version: 1, profiles: { desktop: { attack: { x: .7, y: .8 } } } };
	const result = saveLayoutProfile(denied, layout, "desktop", { attack: { x: .4, y: .3 } });
	assert.equal(result.ok, false); assert.equal(result.layout, layout);
	assert.deepEqual(layout.profiles.desktop.attack, { x: .7, y: .8 });
});
test("the writer refuses unknown controls or malformed points without crashing", () => {
	for (const value of [null, [], { attack: null }, { attack: { x: Infinity, y: .5 } }, { unknown: { x: .5, y: .5 } }]) {
		const result = saveLayoutProfile(memory(), emptyLayout(), "desktop", value);
		assert.equal(result.ok, false);
	}
});
test("Cancel and Reset never mutate saved data; saved Reset affects only the current profile", () => {
	const positions = { joystick: { x: .2, y: .8 }, attack: { x: .8, y: .8 } };
	const session = createLayoutSession(positions);
	session.draft.attack.x = .6;
	assert.deepEqual(cancelLayoutSession(session), positions);
	resetLayoutSession(session); assert.deepEqual(session.draft, {});
	assert.deepEqual(cancelLayoutSession(session), positions);
	const layout = { version: 1, profiles: { desktop: positions, "mobile-portrait": positions } };
	const result = saveLayoutProfile(memory(), layout, "desktop", session.draft);
	assert.equal(result.ok, true); assert.equal(result.layout.profiles.desktop, undefined);
	assert.deepEqual(result.layout.profiles["mobile-portrait"], positions);
	assert.deepEqual(layout.profiles.desktop, positions);
});
test("safe-area clamping keeps the full 44px target reachable after orientation and viewport changes", () => {
	const sizes = [{ width: 390, height: 844 }, { width: 844, height: 390 }, { width: 320, height: 240 }];
	const safe = { left: 35, right: 20, top: 24, bottom: 21 };
	for (const viewport of sizes) for (const point of [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: .5, y: .5 }]) {
		const size = { width: 40, height: 36 };
		const result = clampControl(point, size, viewport, safe);
		assert.ok(result.x * viewport.width - 22 >= safe.left + 4 - .00001);
		assert.ok(result.x * viewport.width + 22 <= viewport.width - safe.right - 4 + .00001);
		assert.ok(result.y * viewport.height - 22 >= safe.top + 4 - .00001);
		assert.ok(result.y * viewport.height + 22 <= viewport.height - safe.bottom - 4 + .00001);
	}
});
test("pointer cancellation rolls back just that drag and releases pointer ownership", () => {
	const original = { attack: { x: .8, y: .8 } };
	const session = createLayoutSession(original);
	assert.equal(beginControlDrag(session, "attack", 3, original.attack), true);
	assert.equal(beginControlDrag(session, "joystick", 4, { x: .2, y: .8 }), false);
	assert.equal(updateControlDrag(session, 4, { x: .4, y: .4 }), false);
	assert.equal(updateControlDrag(session, 3, { x: .4, y: .4 }), true);
	assert.equal(endControlDrag(session, 4, true), false);
	assert.equal(endControlDrag(session, 3, true), true);
	assert.equal(session.pointer, null); assert.deepEqual(session.draft, original);
	assert.equal(updateControlDrag(session, 3, { x: .3, y: .3 }), false);
	assert.equal(beginControlDrag(session, "joystick", 4, { x: .2, y: .8 }), true);
	updateControlDrag(session, 4, { x: .3, y: .5 }); endControlDrag(session, 4, true);
	assert.equal(session.draft.joystick, undefined);
});
test("a completed drag becomes draft data, with no shared reference to input or saved state", () => {
	const session = createLayoutSession({});
	const point = { x: .7, y: .8 };
	assert.equal(beginControlDrag(session, "attack", 5, point), true);
	assert.equal(updateControlDrag(session, 5, point), true);
	endControlDrag(session, 5); point.x = .1;
	assert.deepEqual(session.draft.attack, { x: .7, y: .8 });
	assert.equal(beginControlDrag(session, "untrusted", 6, point), false);
});
