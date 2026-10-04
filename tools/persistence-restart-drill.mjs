// V5-12 restart drill (plan v5 §7 + §12.3 acceptance).
//
// Boot the server against real PostgreSQL, play a deterministic delta
// (buy a potion: gold 250 -> 225), hard-kill the process, boot it again,
// and rejoin with the SAME cookies. The durable character must come back:
// same name, same wallet, same bag — not a fresh seed.
//
// Usage: node tools/persistence-restart-drill.mjs
// Env: AETHERFIELD_DRILL_PORT (default 3912), AETHERFIELD_DATABASE_URL
//      (default the local dev instance on 127.0.0.1:5499).

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { execSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { decodeServerMessage, encodeCold } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	delay,
	issueJoinTicket,
	toArrayBuffer,
	waitForMessage,
} from "./net-driver.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const exe = resolve(root, "apps/server/target/debug/aetherfield-server.exe");
assert.ok(existsSync(exe), "server binary missing; run cargo build first");
const bundleDirs = readdirSync(resolve(root, "content/build"), { withFileTypes: true })
	.filter((entry) => entry.isDirectory());
assert.equal(bundleDirs.length, 1, "content/build must contain one validated bundle");

const port = process.env.AETHERFIELD_DRILL_PORT ?? "3912";
const databaseUrl = process.env.AETHERFIELD_DATABASE_URL
	?? "postgres://aetherfield@127.0.0.1:5499/aetherfield";
const httpBase = `http://127.0.0.1:${port}`;
const websocketUrl = new URL(`ws://127.0.0.1:${port}/ws`);
const origin = "http://127.0.0.1:5173";

let server = null;
async function startServer() {
	server = spawn(exe, [], {
		env: { ...process.env, AETHERFIELD_PORT: port, AETHERFIELD_DATABASE_URL: databaseUrl },
		stdio: ["ignore", "inherit", "inherit"],
	});
	const deadline = Date.now() + 30_000;
	while (Date.now() < deadline) {
		try {
			const health = await fetch(new URL("/healthz", httpBase), { cache: "no-store" });
			if (health.ok) return;
		} catch {
			// not up yet
		}
		await delay(250);
	}
	throw new Error("server did not become healthy in 30s");
}

function killServer() {
	if (!server || server.exitCode !== null) return;
	// Hard kill (plan §12.4 drills crash, not graceful shutdowns). /T so the
	// log thread dies with the process, /F so nothing graceful can save it.
	execSync(`taskkill /PID ${server.pid} /T /F`, { stdio: "ignore" });
	server = null;
}

// Capture every Set-Cookie; the principal cookie rides next to the session.
// `existing` re-sends the browser's current cookies (the restart leg relies
// on the principal cookie being the durable identity carrier).
async function createSessionWithCookies(existing) {
	const response = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: origin, ...(existing ? { Cookie: existing } : {}) },
		cache: "no-store",
	});
	assert.equal(response.status, 204);
	const jar = response.headers.getSetCookie()
		.map((cookie) => cookie.split(";")[0])
		.filter((cookie) => cookie.startsWith("aetherfield_"));
	assert.ok(jar.some((c) => c.startsWith("aetherfield_session=")), "session cookie missing");
	assert.ok(jar.some((c) => c.startsWith("aetherfield_principal=")), "principal cookie missing (V5-12)");
	return jar.join("; ");
}

async function whoami(cookie) {
	const response = await fetch(new URL("/session/whoami", httpBase), {
		headers: { Origin: origin, Cookie: cookie },
		cache: "no-store",
	});
	assert.equal(response.status, 200);
	return response.json();
}

async function joinAndReadState(cookie) {
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket);
	assert.equal(client.welcome.type, "welcome");
	const statePromise = waitForMessage(
		client.socket,
		(message) => message.type === "cold" && message.tag === "character_state",
		10_000,
	);
	client.socket.send(encodeCold({ t: "resync" }));
	const state = (await statePromise).data;
	await client.socket.close();
	return state;
}

const opResult = (opId) => (message) =>
	message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId;

try {
	process.stdout.write("drill: boot 1\n");
	await startServer();

	process.stdout.write("drill: first session\n");
	const cookie = await createSessionWithCookies();
	const whoFirst = await whoami(cookie);
	assert.match(whoFirst.name, /^Traveler-/);

	process.stdout.write("drill: join + buy potion (gold 250 -> 225)\n");
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket);
	assert.equal(client.welcome.type, "welcome");
	client.socket.addEventListener("message", async (event) => {
		try {
			const message = decodeServerMessage(await toArrayBuffer(event.data));
			if (message.type === "cold") process.stdout.write(`  [cold ${message.tag}]\n`);
		} catch {}
	});

	process.stdout.write("drill: waiting initialState\n");
	// The world does not auto-push state on every join path: ask for it.
	const statePromise = waitForMessage(
		client.socket,
		(message) => message.type === "cold" && message.tag === "character_state",
		10_000,
	);
	client.socket.send(encodeCold({ t: "resync" }));
	const initialState = (await statePromise).data;
	assert.equal(initialState.gold, 250, "fresh character starts with the economy wallet");

	process.stdout.write("drill: sending store_buy\n");
	const opId = crypto.randomUUID();
	const resultPromise = waitForMessage(client.socket, opResult(opId), 10_000);
	client.socket.send(encodeCold({ t: "store_buy", op_id: opId, item: "trail_potion" }));
	const result = (await resultPromise).data;
	assert.equal(result.status, "accepted", `store_buy must accept (${result.reason})`);

	const afterState = (await waitForMessage(
		client.socket,
		(message) => message.type === "cold" && message.tag === "character_state",
		10_000,
	)).data;
	assert.equal(afterState.gold, 225, "potion costs 25 gold");
	await client.socket.close();

	// Give the coalescing worker its 1s flush window, then hard-kill.
	process.stdout.write("drill: flush window + hard kill\n");
	await delay(1600);
	killServer();

	process.stdout.write("drill: boot 2 (restart)\n");
	await startServer();

	// The session is ephemeral by design (1h, in-memory); the PRINCIPAL is
	// what survives. Re-session with the same cookies: the server mints a
	// fresh session bound to the same durable principal.
	process.stdout.write("drill: re-session with the SAME cookies\n");
	const cookie2 = await createSessionWithCookies(cookie);
	const whoSecond = await whoami(cookie2);
	assert.equal(whoSecond.name, whoFirst.name, "durable identity keeps the same name");
	const restored = await joinAndReadState(cookie2);
	assert.equal(restored.gold, 225, "wallet restored from PostgreSQL, not reseeded to 250");
	assert.equal(
		restored.bag.find((item) => item.item === "trail_potion")?.count,
		initialState.bag.find((item) => item.item === "trail_potion")?.count + 1,
		"the bought potion is in the restored bag",
	);
	assert.equal(restored.level, initialState.level, "level restored");
	assert.equal(restored.quest_state, initialState.quest_state, "quest state restored");
	assert.equal(restored.handle, initialState.handle, "handle restored");

	process.stdout.write("drill: PASS — durable character survived a hard kill\n");
} finally {
	killServer();
}
