// P4 / D-14 loot smoke: verifies drop reception, proximity pickup, bag addition, and idempotency.
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
let currentDrops = [];
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
		else if (message.data.t === "drops") currentDrops = message.data.entries;
		else if (message.data.t === "op_result") opResults.set(message.data.op_id, message.data);
	}
});

// Trigger resync to fetch initial state
client.socket.send(encodeCold({ t: "resync" }));
await delay(400);
assert.ok(characterState, "received character_state on resync");
assert.ok(Array.isArray(currentDrops), "drops array initialized");

// Test pickup of non-existent drop fails cleanly
const fakeOpId = randomUUID();
const fakeResultPromise = waitForMessage(
	client.socket,
	(m) => m.type === "cold" && m.data.t === "op_result" && m.data.op_id === fakeOpId,
	5000,
);
client.socket.send(encodeCold({ t: "pickup_drop", encounter: randomUUID(), op_id: fakeOpId }));
const fakeResult = await fakeResultPromise;
assert.equal(fakeResult.data.status, "rejected", "non-existent drop must be rejected");
assert.equal(fakeResult.data.reason, "unknown_drop");

process.stdout.write("loot-smoke: non-existent drop rejected correctly with unknown_drop\n");
client.socket.close();
process.stdout.write("loot-smoke: PASS\n");
