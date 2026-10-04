import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { encodeAction, encodeCold, encodeInput, encodePing, fnv1a64 } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	decodeSocketMessage,
	createSession,
	delay,
	issueJoinTicket,
	toArrayBuffer,
	waitForMessage,
} from "./net-driver.mjs";

// V5-11 seeded multi-client protocol bot. The fast default is a smoke test;
// the full plan gate is `node tools/swarm-smoke.mjs --bots 10 --duration-s 600`.
// For impairment, point AETHERFIELD_HTTP_URL and AETHERFIELD_WS_URL through
// tools/delay-loss-proxy.mjs; the proxy keeps its delay/jitter/loss seed.
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const bundleBytes = readFileSync(resolve(repoRoot, "apps/client/public/content/bundle.json"));
const bundle = JSON.parse(bundleBytes.toString("utf8"));
const bundleHash = fnv1a64(bundleBytes).toString(16).padStart(16, "0");
const args = process.argv.slice(2);
const arg = (name, fallback) => {
	const index = args.indexOf(`--${name}`);
	return index >= 0 ? args[index + 1] : fallback;
};
const options = {
	output: arg("output", null),
	port: Number(arg("port", process.env.AETHERFIELD_PORT ?? "3001")),
	origin: arg("origin", process.env.AETHERFIELD_ORIGIN ?? "http://127.0.0.1:5173"),
	bots: Number(arg("bots", "10")),
	durationS: Number(arg("duration-s", "6")),
	seed: Number(arg("seed", "20260929")),
	channel: Number(arg("channel", "19")),
	questBot: args.includes("--no-quest") ? null : Number(arg("quest-bot", "0")),
	reconnectBot: args.includes("--no-reconnect") ? null : Number(arg("reconnect-bot", "0")),
};
assert.ok(Number.isInteger(options.port) && options.port > 0 && options.port <= 65535, "port must be valid");
assert.ok(Number.isInteger(options.bots) && options.bots >= 1 && options.bots <= 16, "bot count must be 1–16");
assert.ok(Number.isFinite(options.durationS) && options.durationS >= 2 && options.durationS <= 600, "duration must be 2–600 seconds");
assert.ok(Number.isInteger(options.seed) && options.seed >= 0 && options.seed <= 0xffffffff, "seed must be uint32");
assert.ok(Number.isInteger(options.channel) && options.channel >= 0 && options.channel < 20, "channel must be 0–19");
for (const botIndex of [options.questBot, options.reconnectBot]) {
	assert.ok(botIndex === null || (Number.isInteger(botIndex) && botIndex >= 0 && botIndex < options.bots), "selected bot index is out of range");
}

const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? `http://127.0.0.1:${options.port}`);
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? `ws://127.0.0.1:${options.port}/ws`);
const rng = mulberry32(options.seed);
const bots = [];
const baselinePlayers = await serverPlayerCount();
const rssBefore = process.memoryUsage().rss;
let peakRss = rssBefore;
let questSteps = 0;
let reconnects = 0;
let crossVisibilityChecks = 0;
let pingCount = 0;
let acceptedActions = 0;
let protocolErrors = 0;
let socketErrors = 0;

try {
	for (let index = 0; index < options.bots; index++) bots.push(await createBot(index));
	process.stdout.write(`swarm-smoke: joined ${bots.length} seeded bots on channel ${options.channel}\n`);
	await delay(600);
	assertCrossVisibility();
	await resyncAll();
	if (options.questBot !== null) {
		await acceptQuestStep(bots[options.questBot]);
		questSteps = 1;
	}

	const durationMs = options.durationS * 1000;
	const startTime = Date.now();
	let tick = 0;
	let nextProgressAt = 60_000;
	let reconnectDone = options.reconnectBot === null;
	let lastRssSampleAt = startTime;
	while (Date.now() - startTime < durationMs) {
		const elapsed = Date.now() - startTime;
		if (!reconnectDone && elapsed >= durationMs / 2) {
			await reconnectBot(bots[options.reconnectBot]);
			reconnects += 1;
			reconnectDone = true;
			await delay(300);
			assertCrossVisibility();
		}
		tick += 1;
		for (let index = 0; index < bots.length; index++) {
			const bot = bots[index];
			if (!bot.connected) continue;
			const position = currentPlayer(bot);
			const seedPhase = bot.phase;
			const angle = tick * 0.1 + seedPhase;
			const moveX = Math.cos(angle) * 0.62;
			const moveZ = Math.sin(angle) * 0.62;
			sendInput(bot, moveX, moveZ);
			if (tick % 20 === index % 20) {
				bot.pingNonce = (bot.pingNonce + 1) >>> 0;
				const now = Math.floor(performance.now()) >>> 0;
				bot.client.socket.send(encodePing(bot.pingNonce, now));
			}
			if (tick % 40 === index % 40) {
				const target = nearestMonster(bot, position);
				if (target) {
					const aim = Math.atan2(target.x - position.x, target.z - position.z);
					const sequence = ++bot.sequence;
					bot.client.socket.send(encodeAction(bot.client.welcome.epoch, sequence, "attack", aim, target.id,
						Number(bot.latestSnapshot?.tick ?? 0n)));
				}
			}
		}
		await delay(50);
		if (Date.now() - lastRssSampleAt >= 1_000) {
			peakRss = Math.max(peakRss, process.memoryUsage().rss);
			lastRssSampleAt = Date.now();
		}
		if (tick % 100 === 0) {
			assertCrossVisibility();
			if (options.durationS >= 60 && Date.now() - startTime >= nextProgressAt) {
				process.stdout.write(`swarm-smoke: ${Math.floor((Date.now() - startTime) / 1000)} s, ${totalSnapshots()} snapshots\n`);
				nextProgressAt += 60_000;
			}
		}
	}

	const preClose = {
		min_snapshots: Math.min(...bots.map((bot) => bot.snapshots)),
		max_snapshots: Math.max(...bots.map((bot) => bot.snapshots)),
		pings: bots.reduce((sum, bot) => sum + bot.pings, 0),
		actions_accepted: bots.reduce((sum, bot) => sum + bot.acceptedActions, 0),
		protocol_errors: protocolErrors + bots.reduce((sum, bot) => sum + bot.protocolErrors, 0),
		socket_errors: socketErrors + bots.reduce((sum, bot) => sum + bot.socketErrors, 0),
	};
	assert.ok(preClose.min_snapshots > 0, "every bot must receive snapshots");
	assert.ok(preClose.pings > 0, "bots must receive ping responses");
	assert.equal(preClose.protocol_errors, 0, "no bot may see protocol errors");
	assert.equal(preClose.socket_errors, 0, "no bot may see socket errors before teardown");
	assert.equal(reconnects, options.reconnectBot === null ? 0 : 1, "selected reconnect must complete");

	await Promise.allSettled(bots.map((bot) => bot.client.socket.close()));
	for (const bot of bots) bot.connected = false;
	const cleanupPassed = await waitForPlayerCount(baselinePlayers, 10_000);
	assert.ok(cleanupPassed, "all bot sessions must leave the server room after socket close");
	const rssAfter = process.memoryUsage().rss;
	const evidencePath = options.output ? resolve(options.output) : resolve(repoRoot, `planning/evidence/v5-11-swarm-${options.bots}-${options.durationS}s-seed-${options.seed}.json`);
	const report = {
		schema: "aetherfield.v5-11-swarm/1",
		result: "PASS",
		seed: options.seed,
		bots: options.bots,
		duration_s: options.durationS,
		channel: options.channel,
		bundle_hash: bundleHash,
		party_quest_steps: questSteps,
		reconnects,
		cross_visibility_checks: crossVisibilityChecks,
		...preClose,
		server_players_before: baselinePlayers,
		server_players_after: await serverPlayerCount(),
		cleanup_passed: cleanupPassed,
		bot_runner_memory: { rss_before_bytes: rssBefore, peak_rss_bytes: peakRss, rss_after_bytes: rssAfter },
		limitations: [
			"A local protocol bot run is not a human playtest or Android/iPhone performance measurement.",
			"Peak RSS measures the Node bot runner, not the Rust server process or GPU memory.",
		],
	};
	writeFileSync(evidencePath, JSON.stringify(report, null, 2) + "\n", "utf8");
	console.log(JSON.stringify({ ...report, evidence: relative(repoRoot, evidencePath).replaceAll("\\", "/") }, null, 2));
} finally {
	await Promise.allSettled(bots.filter((bot) => bot.connected).map((bot) => bot.client.socket.close()));
}

function mulberry32(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

async function createBot(index) {
	const cookie = await createSession(httpBase, options.origin);
	const channelResponse = await fetch(new URL("/session/channel", httpBase), {
		method: "POST",
		headers: { Origin: options.origin, Cookie: cookie, "Content-Type": "application/json" },
		body: JSON.stringify({ channel: options.channel }),
	});
	assert.equal(channelResponse.status, 200, "guest session must select the isolated test channel");
	const ticket = await issueJoinTicket(httpBase, options.origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, options.origin, cookie, ticket,bundle.zones[0]?.half_extent??28);
	assert.equal(client.welcome.type, "welcome");
	assert.equal(client.welcome.content_hash.toString(16).padStart(16, "0"), bundleHash);
	const bot = {
		index, cookie, client, id: client.welcome.player_id, sequence: 0,
		phase: rng() * Math.PI * 2, pingNonce: (options.seed + index * 1000) >>> 0,
		latestSnapshot: null, snapshots: 0, pings: 0, acceptedActions: 0,
		protocolErrors: 0, socketErrors: 0, connected: true, identity: null,
	};
	attach(bot, client);
	return bot;
}

async function resyncAll() {
	const states = bots.map((bot) => waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "character_state", 5000));
	for (const bot of bots) bot.client.socket.send(encodeCold({ t: "resync" }));
	const results = await Promise.all(states);
	for (let index = 0; index < bots.length; index++) bots[index].identity = results[index].data.name;
}

function attach(bot, client) {
	client.socket.addEventListener("error", () => { bot.socketErrors += 1; });
	client.socket.addEventListener("message", async (event) => {
		try {
			const message = await decodeSocketMessage(client.socket,event.data);
			if (message.type === "snapshot") {
				bot.snapshots += 1;
				bot.latestSnapshot = message;
			} else if (message.type === "pong") {
				bot.pings += 1;
			} else if (message.type === "action_result" && message.accepted) {
				bot.acceptedActions += 1;
			}
		} catch {
			bot.protocolErrors += 1;
		}
	});
}

async function resyncCharacter(bot) {
	const statePromise = waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "character_state", 5000);
	bot.client.socket.send(encodeCold({ t: "resync" }));
	const state = await statePromise;
	return state.data;
}

async function acceptQuestStep(bot) {
	const questPromise = waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "quest_state", 5000);
	bot.client.socket.send(encodeCold({ t: "resync" }));
	let quest = await questPromise;
	if (quest.data.state !== "not_started") return "existing_quest";
	const guide = bundle.npcs.sella;
	await driveTo(bot, guide.x, guide.z, 1.2);
	const dialoguePromise = waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "dialogue", 5000);
	bot.client.socket.send(encodeCold({ t: "interact", npc: "sella" }));
	const dialogue = await dialoguePromise;
	const closedPromise = waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "dialogue_closed", 5000);
	const activeQuestPromise = waitForMessage(bot.client.socket,
		(message) => message.type === "cold" && message.tag === "quest_state" && message.data.state === "active", 5000);
	bot.client.socket.send(encodeCold({ t: "choose", npc: "sella", token: dialogue.data.token, choice: "accept" }));
	assert.equal((await closedPromise).data.reason, "accepted");
	quest = await activeQuestPromise;
	return quest.data.state;
}

async function driveTo(bot, targetX, targetZ, radius) {
	const deadline = Date.now() + 20_000;
	while (Date.now() < deadline) {
		const current = currentPlayer(bot);
		if (current && Math.hypot(current.x - targetX, current.z - targetZ) <= radius) break;
		if (current) {
			const dx = targetX - current.x;
			const dz = targetZ - current.z;
			const length = Math.hypot(dx, dz) || 1;
			sendInput(bot, dx / length, dz / length);
		}
		await delay(50);
	}
	sendInput(bot, 0, 0);
	await delay(120);
	const final = currentPlayer(bot);
	assert.ok(final && Math.hypot(final.x - targetX, final.z - targetZ) <= radius + 0.35,
		`seeded quest bot ${bot.id} failed to reach the guide`);
}

async function reconnectBot(bot) {
	const beforeName = bot.identity ?? (await resyncCharacter(bot)).name;
	await bot.client.socket.close();
	bot.connected = false;
	await delay(150);
	const ticket = await issueJoinTicket(httpBase, options.origin, bot.cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, options.origin, bot.cookie, ticket,bundle.zones[0]?.half_extent??28);
	assert.equal(client.welcome.type, "welcome");
	assert.equal(client.welcome.content_hash.toString(16).padStart(16, "0"), bundleHash);
	bot.client = client;
	bot.id = client.welcome.player_id;
	bot.sequence = 0;
	bot.latestSnapshot = null;
	bot.connected = true;
	attach(bot, client);
	const after = await resyncCharacter(bot);
	assert.equal(after.name, beforeName, "reconnect must resume the same named character");
	bot.identity = after.name;
}

function currentPlayer(bot) {
	return bot.latestSnapshot?.players.find((player) => player.id === bot.id) ?? null;
}

function nearestMonster(bot, position) {
	if (!position) return null;
	return (bot.latestSnapshot?.monsters ?? [])
		.filter((monster) => monster.active)
		.map((monster) => ({ monster, distance: Math.hypot(monster.x - position.x, monster.z - position.z) }))
		.sort((left, right) => left.distance - right.distance)[0]?.monster ?? null;
}

function sendInput(bot, x, z) {
	bot.client.socket.send(encodeInput(bot.client.welcome.epoch, ++bot.sequence, x, z, 0));
}

function assertCrossVisibility() {
	crossVisibilityChecks += 1;
	for (const bot of bots) {
		if (!bot.connected || !bot.latestSnapshot) continue;
		for (const other of bots) {
			if (!other.connected) continue;
			assert.ok(bot.latestSnapshot.players.some((player) => player.id === other.id),
				`bot ${bot.id} must observe bot ${other.id}`);
		}
	}
}

function totalSnapshots() {
	return bots.reduce((sum, bot) => sum + bot.snapshots, 0);
}

async function serverPlayerCount() {
	const response = await fetch(new URL("/healthz", httpBase), { cache: "no-store" });
	assert.equal(response.status, 200, "local server health endpoint must respond");
	const health = await response.json();
	assert.equal(health.status, "ok");
	return health.players;
}

async function waitForPlayerCount(expected, timeoutMs) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (await serverPlayerCount() === expected) return true;
		await delay(100);
	}
	return (await serverPlayerCount()) === expected;
}
