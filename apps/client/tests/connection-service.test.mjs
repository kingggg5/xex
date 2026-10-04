import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { createChannelSelectionCore } from "../src/connection-service.mjs";

// Exercise the established TypeScript parser and production adapter without a DOM or new tooling.
async function sourceModule(relative) {
	const result = await build({ entryPoints: [fileURLToPath(new URL(relative, import.meta.url))], bundle: true, write: false, format: "esm", platform: "node", logLevel: "silent" });
	return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`);
}
const { parseRooms } = await sourceModule("../src/rooms-ui.ts");
const { createChannelSelectionService } = await sourceModule("../src/channel-selection-service.ts");
const roomBody = () => ({ rooms: Array.from({ length: 20 }, (_, channel) => ({ channel, players: channel === 17 ? 50 : channel, capacity: 50 })) });
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const session = () => json({ identity: { provider: "guest", display_name: "Traveler" } });
const healthy = () => json({ status: "ok", world_alive: true });

function fixture(fetchImpl, extras = {}) {
	const saved = [];
	const service = createChannelSelectionCore({ worldName: "Verdant Frontier", fetchImpl, parseRooms, saveStoredChannel: channel => saved.push(channel), ...extras });
	return { service, saved };
}

test("loads all 20 real occupancy rows with one server measurement and no extra probes", async () => {
	const calls = [];
	const body = roomBody();
	body.rooms[0].name = "East Grove";
	body.rooms[1].name = "";
	const ticks = [100, 127];
	const { service } = fixture(async (path, init) => { calls.push([path, init]); return json(body); }, { now: () => ticks.shift() });
	const result = await service.load();
	assert.equal(result.rooms.length, 20);
	assert.equal(result.rooms[0].name, "East Grove");
	assert.equal(result.rooms[1].name, "Verdant Frontier");
	assert.deepEqual(result.rooms[17], { channel: 17, players: 50, capacity: 50, name: "Verdant Frontier" });
	assert.equal(result.latencyMs, 27);
	assert.equal(result.autoAvailable, true);
	assert.equal(result.rooms.some(room => "latencyMs" in room || "ping" in room), false);
	assert.deepEqual(calls.map(([path]) => path), ["/rooms"]);
	assert.equal(calls[0][1].cache, "no-store");
	assert.equal(calls[0][1].credentials, "same-origin");
});

test("full occupancy stays exact and disables Auto when every listed channel is full", async () => {
	const body = roomBody();
	for (const room of body.rooms) room.players = room.capacity + 2;
	const { service } = fixture(async () => json(body));
	const result = await service.load();
	assert.equal(result.autoAvailable, false);
	assert.equal(result.rooms.every(room => room.players === 52), true);
});

test("optional server names survive a parser that returns only the declared room fields", async () => {
	const body = roomBody();
	body.rooms[0].name = "  East Grove  ";
	body.rooms[1].name = null;
	body.rooms[2].name = "Bad\u0000name";
	body.rooms[3].name = "x".repeat(81);
	body.rooms[4].name = 42;
	const { service } = fixture(async () => json(body), {
		parseRooms: value => parseRooms(value)?.map(({ channel, players, capacity }) => ({ channel, players, capacity })) ?? null,
	});
	const result = await service.load();
	assert.equal(result.rooms[0].name, "East Grove");
	for (const index of [1, 2, 3, 4, 5]) assert.equal(result.rooms[index].name, "Verdant Frontier");
	assert.deepEqual(result.rooms.map(({ channel, players, capacity }) => ({ channel, players, capacity })),
		body.rooms.map(({ channel, players, capacity }) => ({ channel, players, capacity })));
});

test("unavailable room lists enable Auto only after valid session and health checks", async () => {
	const calls = [];
	const { service } = fixture(async path => {
		calls.push(path);
		if (path === "/rooms") return new Response("Unavailable", { status: 503 });
		return path === "/session/whoami" ? session() : healthy();
	});
	assert.deepEqual(await service.load(), { rooms: [], latencyMs: null, autoAvailable: true, warnings: ["channel_unavailable"] });
	assert.deepEqual(calls, ["/rooms", "/session/whoami", "/healthz"]);
});

test("unconfirmed session, malformed identity, degraded world, or failed health disable Auto", async t => {
	for (const [label, identity, health] of [
		["expired", () => new Response(null, { status: 401 }), healthy],
		["identity", () => json({ identity: { provider: "guest" } }), healthy],
		["degraded", session, () => json({ status: "degraded", world_alive: false })],
		["health", session, () => new Response(null, { status: 503 })],
	]) await t.test(label, async () => {
		const { service } = fixture(async path => path === "/rooms" ? json({ rooms: "broken" }) : path === "/session/whoami" ? identity() : health());
		assert.equal((await service.load()).autoAvailable, false);
	});
});

test("rejects malformed, duplicate, excessive, and oversized room payloads without inventing counts", async t => {
	const badBodies = [
		{ rooms: [{ channel: 0, players: -1, capacity: 50 }] },
		{ rooms: [roomBody().rooms[0], roomBody().rooms[0]] },
		{ rooms: Array.from({ length: 65 }, (_, channel) => ({ channel, players: 1, capacity: 50 })) },
		{ rooms: [], junk: "x".repeat(33_000) },
	];
	for (let index = 0; index < badBodies.length; index++) await t.test(String(index), async () => {
		const { service } = fixture(async path => path === "/rooms" ? json(badBodies[index]) : path === "/session/whoami" ? session() : healthy());
		const result = await service.load();
		assert.deepEqual(result.rooms, []);
		assert.equal(result.latencyMs, null);
		assert.equal(result.autoAvailable, true);
		assert.deepEqual(result.warnings, ["invalid_response"]);
	});
});

test("empty valid room lists are unavailable for Auto without extra health traffic", async () => {
	const calls = [];
	const { service } = fixture(async path => { calls.push(path); return json({ rooms: [] }); });
	assert.equal((await service.load()).autoAvailable, false);
	assert.deepEqual(calls, ["/rooms"]);
});

test("explicit cancellation reaches fetch and never launches fallback requests", async () => {
	const calls = [];
	let requestSignal;
	const { service } = fixture((path, init) => { calls.push(path); requestSignal = init.signal; return new Promise(() => {}); });
	const controller = new AbortController();
	const pending = assert.rejects(service.load(controller.signal), { name: "AbortError" });
	controller.abort("private cancellation reason");
	await pending;
	assert.equal(requestSignal.aborted, true);
	assert.deepEqual(calls, ["/rooms"]);
});

test("a pre-aborted load sends no HTTP request", async () => {
	let calls = 0;
	const { service } = fixture(async () => { calls++; return json(roomBody()); });
	const controller = new AbortController();
	controller.abort();
	await assert.rejects(service.load(controller.signal), { name: "AbortError" });
	assert.equal(calls, 0);
});

test("a new load cancels stale work even when the fetch adapter ignores cancellation", async () => {
	let finishOld;
	let calls = 0;
	const { service } = fixture(async () => ++calls === 1 ? new Promise(resolve => { finishOld = resolve; }) : json(roomBody()));
	const old = assert.rejects(service.load(), { name: "AbortError" });
	const latest = await service.load();
	finishOld(json({ rooms: [] }));
	await old;
	assert.equal(latest.rooms.length, 20);
	assert.equal(calls, 2);
});

test("request deadlines abort hung rooms and independently bound both fallback checks", async () => {
	const signals = [];
	const { service } = fixture((_path, init) => { signals.push(init.signal); return new Promise(() => {}); }, { timeoutMs: 10 });
	const result = await service.load();
	assert.equal(result.autoAvailable, false);
	assert.deepEqual(result.warnings, ["timeout"]);
	assert.equal(signals.length, 3);
	assert.equal(signals.every(signal => signal.aborted), true);
});

test("saves only matching channel echoes and supports legacy 204 including Auto", async t => {
	for (const [channel, response] of [[7, () => json({ channel: 7 })], [null, () => json({ channel: null })], [4, () => new Response(null, { status: 204 })]]) {
		await t.test(String(channel), async () => {
			let sent;
			const { service, saved } = fixture(async (path, init) => { sent = [path, init]; return response(); });
			await service.apply(channel);
			assert.deepEqual(saved, [channel]);
			assert.equal(sent[0], "/session/channel");
			assert.equal(sent[1].method, "POST");
			assert.equal(sent[1].body, JSON.stringify({ channel }));
			assert.equal(sent[1].credentials, "same-origin");
		});
	}
});

test("HTTP failures, malformed JSON and mismatched echoes never persist selection", async t => {
	for (const [label, response, code] of [
		["rejected", () => new Response("unknown_channel", { status: 400 }), "channel_rejected"],
		["expired", () => new Response("secret-cookie", { status: 401 }), "session_required"],
		["server", () => new Response("private server detail", { status: 500 }), "channel_unavailable"],
		["malformed", () => new Response("broken JSON"), "invalid_response"],
		["echo", () => json({ channel: 9 }), "invalid_response"],
		["missing", () => json({}), "invalid_response"],
	]) await t.test(label, async () => {
		const { service, saved } = fixture(async () => response());
		await assert.rejects(service.apply(7), error => error.code === code && !/secret|private/.test(error.message));
		assert.deepEqual(saved, []);
	});
});

test("invalid channel input and network failure return safe errors without saving", async () => {
	let calls = 0;
	const { service, saved } = fixture(async () => { calls++; throw new Error("private network details"); });
	for (const bad of [-1, 65536, 1.5, undefined, "2"]) await assert.rejects(service.apply(bad), { code: "invalid_channel" });
	assert.equal(calls, 0);
	await assert.rejects(service.apply(2), { code: "network_error" });
	assert.deepEqual(saved, []);
});

test("superseded or aborted channel writes cannot persist late success", async () => {
	let finishOld;
	let calls = 0;
	const { service, saved } = fixture(async () => ++calls === 1 ? new Promise(resolve => { finishOld = resolve; }) : json({ channel: 9 }));
	const old = assert.rejects(service.apply(7), { name: "AbortError" });
	await service.apply(9);
	finishOld(json({ channel: 7 }));
	await old;
	assert.deepEqual(saved, [9]);
	const controller = new AbortController();
	controller.abort();
	await assert.rejects(service.apply(9, controller.signal), { name: "AbortError" });
	assert.deepEqual(saved, [9]);
});

test("production adapter persists to existing channel storage only after a confirmed response", async () => {
	const oldFetch = globalThis.fetch;
	const oldWindow = globalThis.window;
	const storage = new Map();
	try {
		globalThis.window = { localStorage: { setItem: (key, value) => storage.set(key, value) } };
		globalThis.fetch = async () => json({ channel: 7 });
		const service = createChannelSelectionService({ worldName: "Verdant Frontier" });
		await service.apply(7);
		assert.equal(storage.get("aetherfield_channel"), "7");
		globalThis.fetch = async () => json({ channel: 9 });
		await assert.rejects(service.apply(3), { code: "invalid_response" });
		assert.equal(storage.get("aetherfield_channel"), "7");
	} finally {
		globalThis.fetch = oldFetch;
		if (oldWindow === undefined) delete globalThis.window;
		else globalThis.window = oldWindow;
	}
});
