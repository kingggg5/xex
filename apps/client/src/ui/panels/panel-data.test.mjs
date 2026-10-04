import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const result = await build({ entryPoints: [fileURLToPath(new URL("../panel-data.ts", import.meta.url))], bundle: true, platform: "node", format: "esm", write: false, logLevel: "silent" });
const panel = await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);

test("character refinement reflects existing gold, safe-limit and maximum rules without mutating server state", () => {
	const state = { name: "Traveler", handle: "traveler", level: 2, job_level: 1, atk: 30, def: 4, hp: 100, max_hp: 120, exp: 4, base_exp_next: 20, job_exp: 1, job_exp_next: 10, stat_points: 3, stats: { str: 1, agi: 2, vit: 3, int: 4, dex: 5, luk: 6 }, gold: 150, equipment: [{ slot: "weapon", item: "sword" }, { slot: "armor", item: "vest" }], refine: { weapon: 4, armor: 10 } };
	const snapshot = panel.characterPanelData(state, (id) => id);
	assert.equal(snapshot.equipment[0].refineCost, 150);
	assert.equal(snapshot.equipment[0].successPercent, 70);
	assert.equal(snapshot.equipment[0].canRefine, true);
	assert.equal(snapshot.equipment[1].canRefine, false);
	assert.equal(panel.characterPanelData({ ...state, gold: 149 }, (id) => id).equipment[0].canRefine, false);
	assert.equal(panel.characterPanelData(state, (id) => id, false).equipment[0].canRefine, false);
	assert.equal(panel.characterPanelData({ ...state, refine: { weapon: 0 } }, (id) => id).equipment[0].successPercent, 100);
	snapshot.stats.str = 99;
	snapshot.equipment[0].refine = 9;
	assert.equal(state.stats.str, 1);
	assert.equal(state.refine.weapon, 4);
});

test("server row snapshots remain bounded and retain tower-only presence", () => {
	const friends = Array.from({ length: 100 }, (_, i) => ({ handle: `player_${i}`, name: `Player ${i}`, online: true, channel: null, tower: null, inTower: true }));
	const snapshot = panel.presencePanelData(friends);
	assert.equal(snapshot.length, 80);
	assert.equal(snapshot[0].inTower, true);
	assert.equal(panel.presenceLabel(snapshot[0], "en"), "Tower");
	assert.equal(panel.groupPanelData({ code: "ABC123", members: friends }).members.length, 16);
	assert.equal(panel.groupPanelData({ code: "ABC123", members: friends }).members[0].inTower, true);
	const rooms = Array.from({ length: 100 }, (_, channel) => ({ channel, players: 2, capacity: 50 }));
	const roomSnapshot = panel.roomPanelData({ current: 7, rooms: [...rooms, { channel: -1, players: 0, capacity: 50 }] });
	assert.equal(roomSnapshot.rooms.length, 64);
	assert.equal(roomSnapshot.current, 7);
	assert.equal(panel.roomPanelData({ current: -1, rooms: null }).status, "unavailable");
	assert.equal(panel.roomPanelData({ current: -1, rooms: null }).current, null);
});

test("map sanitizes finite coordinates and caps source collections", () => {
	const points = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`poi_${i}`, { x: i, z: i }]));
	const routes = Array.from({ length: 100 }, (_, i) => ({ id: `${i}`, width: 1, points: Array.from({ length: 100 }, () => [1, 2]) }));
	const snapshot = panel.mapPanelData(points, NaN, routes, { x: Infinity, z: NaN }, [], { inTower: false, floor: 0, bestFloor: 0 }, "en");
	assert.equal(snapshot.points.length, 80);
	assert.equal(snapshot.routes.length, 64);
	assert.equal(snapshot.routes[0].points.length, 80);
	assert.deepEqual(snapshot.player, { x: 0, z: 0 });
	assert.equal(panel.projectPanelCoordinate(Infinity, 28), 170);
	assert.equal(panel.projectPanelCoordinate(100, 28), 340);
	assert.equal(JSON.parse(JSON.stringify(snapshot)).routes.length, 64);
});

test("settings persist through existing hooks and dispose preference and resize subscriptions", () => {
	const originalWindow = globalThis.window;
	const originalStorage = globalThis.localStorage;
	const data = new Map();
	const storage = { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
	const listeners = new Map();
	globalThis.localStorage = storage;
	globalThis.window = { localStorage: storage, matchMedia: () => ({ matches: false }), innerWidth: 1200, innerHeight: 800, devicePixelRatio: 1, addEventListener: (type, callback) => listeners.set(type, callback), removeEventListener: (type) => listeners.delete(type), setTimeout, clearTimeout };
	try {
		panel.changeSettingsPreferences({ uiScale: 1.15, shake: false, flash: true, volume: 0.4 });
		const snapshots = [];
		const stop = panel.observeSettingsPreferences("en", (snapshot) => snapshots.push(snapshot));
		assert.equal(snapshots.at(-1).prefs.uiScale, 1.15);
		assert.equal(listeners.has("resize"), true);
		panel.changeGraphicsPreference("low");
		panel.changeEnvironmentPreference({ weather: "rain", cycle: false });
		assert.equal(snapshots.at(-1).graphics, "low");
		assert.equal(snapshots.at(-1).weather, "rain");
		assert.equal(snapshots.at(-1).cycle, false);
		assert.ok(data.has("aetherfield_settings"));
		assert.ok(data.has("aetherfield_graphics_quality_v1"));
		assert.ok(data.has("aetherfield_environment_v1"));
		stop();
		assert.equal(listeners.has("resize"), false);
		const count = snapshots.length;
		panel.changeGraphicsPreference("high");
		panel.changeEnvironmentPreference({ weather: "clear" });
		assert.equal(snapshots.length, count);
		panel.resetPanelSettings();
		assert.equal(panel.settingsPanelData("en").prefs.uiScale, 1);
		assert.equal(panel.settingsPanelData("en").graphics, null);
		assert.equal(panel.settingsPanelData("en").weather, "auto");
	} finally {
		if (originalWindow === undefined) delete globalThis.window; else globalThis.window = originalWindow;
		if (originalStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = originalStorage;
	}
});
