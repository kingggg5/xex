// Classic Ragnarok Stat Allocation smoke: verifies stat reception, rejection on 0 points, and wire schema.
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { decodeServerMessage, encodeCold } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	createSession,
	delay,
	issueJoinTicket,
	toArrayBuffer,
	waitForMessage,
} from "./net-driver.mjs";

const port = Number(process.argv[2] ?? 3001);
const origin = "http://127.0.0.1:5173";
const httpBase = new URL(`http://127.0.0.1:${port}`);

const cookie = await createSession(httpBase, origin);
const ticket = await issueJoinTicket(httpBase, origin, cookie);
const client = await connectAuthenticatedClient(httpBase, new URL(`ws://127.0.0.1:${port}/ws`), origin, cookie, ticket);

assert.ok(client.welcome, "welcome received on connect");

let characterState = null;
const opResults = new Map();

client.socket.addEventListener("message", async (event) => {
	let message;
	try {
		message = decodeServerMessage(await toArrayBuffer(event.data));
	} catch {
		return;
	}
	if (message.type === "cold") {
		if (message.data.t === "character_state") characterState = message.data;
		else if (message.data.t === "op_result") opResults.set(message.data.op_id, message.data);
	}
});

// Trigger resync to fetch initial state
client.socket.send(encodeCold({ t: "resync" }));
await delay(400);

assert.ok(characterState, "received character_state on resync");
assert.ok(characterState.stats, "stats block present in character_state");
assert.equal(typeof characterState.stats.str, "number", "STR stat present");
assert.equal(typeof characterState.stats.agi, "number", "AGI stat present");
assert.equal(typeof characterState.stats.vit, "number", "VIT stat present");
assert.equal(typeof characterState.stats.int, "number", "INT stat present");
assert.equal(typeof characterState.stats.dex, "number", "DEX stat present");
assert.equal(typeof characterState.stats.luk, "number", "LUK stat present");
assert.equal(typeof characterState.stat_points, "number", "stat_points present");

process.stdout.write(`stat-smoke: initial stats STR=${characterState.stats.str} AGI=${characterState.stats.agi} VIT=${characterState.stats.vit} INT=${characterState.stats.int} DEX=${characterState.stats.dex} LUK=${characterState.stats.luk} points=${characterState.stat_points}\n`);

// Test allocation without sufficient points is rejected
const opId = randomUUID();
const resultPromise = waitForMessage(
	client.socket,
	(m) => m.type === "cold" && m.data.t === "op_result" && m.data.op_id === opId,
	5000,
);

client.socket.send(encodeCold({
	t: "stat_allocate",
	stat: "str",
	points: 1,
	op_id: opId,
}));

const result = await resultPromise;
assert.equal(result.data.status, "rejected", "allocating with 0 points must be rejected");
assert.equal(result.data.reason, "insufficient_stat_points");

process.stdout.write("stat-smoke: zero-points allocation rejected cleanly with insufficient_stat_points\n");
client.socket.close();
process.stdout.write("stat-smoke: PASS\n");
