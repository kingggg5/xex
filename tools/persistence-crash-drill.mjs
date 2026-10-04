// V5-13 crash drill (plan v5 §12.4 failure matrix, cases 1-2 + retry-once).
//
// Scenario A — crash BEFORE commit: the op result reached the client but the
//   transaction never committed. Nothing is granted: after a restart the
//   retry of the same op_id succeeds exactly once (gold 250 -> 225).
// Scenario B — crash AFTER commit, before the reply: the committed result
//   replays after a restart (durable op-cache hydration) and the wallet is
//   deducted exactly once (no double grant on the retry).
//
// Usage: node tools/persistence-crash-drill.mjs

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
assert.equal(bundleDirs.length, 1);

const port = process.env.AETHERFIELD_DRILL_PORT ?? "3921";
const databaseUrl = process.env.AETHERFIELD_DATABASE_URL
	?? "postgres://aetherfield@127.0.0.1:5499/aetherfield";
const httpBase = `http://127.0.0.1:${port}`;
const websocketUrl = new URL(`ws://127.0.0.1:${port}/ws`);
const origin = "http://127.0.0.1:5173";

let server = null;
let serverExited = null;

async function startServer(failpoint) {
	const env = { ...process.env, AETHERFIELD_PORT: port, AETHERFIELD_DATABASE_URL: databaseUrl };
	if (failpoint) env.AETHERFIELD_FAILPOINT = failpoint;
	serverExited = null;
	server = spawn(exe, [], { env, stdio: ["ignore", "ignore", "inherit"] });
	server.on("exit", (code) => {
		serverExited = code;
	});
	const deadline = Date.now() + 30_000;
	while (Date.now() < deadline) {
		try {
			const health = await fetch(new URL("/healthz", httpBase), { cache: "no-store" });
			if (health.ok) return;
		} catch {}
		await delay(250);
	}
	throw new Error("server did not become healthy");
}

function killServer() {
	if (!server || server.exitCode !== null) return;
	execSync(`taskkill /PID ${server.pid} /T /F`, { stdio: "ignore" });
	server = null;
}

async function waitServerExit(timeoutMs = 15_000) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (serverExited !== null) return serverExited;
		await delay(100);
	}
	throw new Error("the failpoint crash never happened");
}

async function retryingFetch(url, options, attempts = 4) {
	let lastError = null;
	for (let attempt = 0; attempt < attempts; attempt++) {
		try {
			return await fetch(url, options);
		} catch (error) {
			lastError = error;
			await delay(600);
		}
	}
	throw lastError;
}

async function createSessionWithCookies(existing) {
	const response = await retryingFetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: origin, ...(existing ? { Cookie: existing } : {}) },
		cache: "no-store",
	});
	assert.equal(response.status, 204);
	return response.headers
		.getSetCookie()
		.map((cookie) => cookie.split(";")[0])
		.filter((cookie) => cookie.startsWith("aetherfield_"))
		.join("; ");
}

async function joinAndReadGold(cookie) {
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
	return state.gold;
}

function opResult(opId) {
	return (message) =>
		message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId;
}

async function buyPotion(cookie, opId) {
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket);
	assert.equal(client.welcome.type, "welcome");
	const resultPromise = waitForMessage(client.socket, opResult(opId), 10_000);
	client.socket.send(encodeCold({ t: "store_buy", op_id: opId, item: "trail_potion" }));
	const result = (await resultPromise).data;
	await client.socket.close();
	return result;
}

try {
	// ---- Scenario A: crash before commit ----
	process.stdout.write("drill A: boot with FAILPOINT=before_commit\n");
	await startServer("before_commit");
	const cookieA = await createSessionWithCookies();
	const goldBefore = await joinAndReadGold(cookieA);
	assert.equal(goldBefore, 250, "fresh character wallet");

	const opIdA = crypto.randomUUID();
	process.stdout.write("drill A: store_buy then crash before commit\n");
	const resultA = await buyPotion(cookieA, opIdA);
	assert.equal(resultA.status, "accepted", "the client saw the op accepted pre-crash");
	const exitCode = await waitServerExit();
	assert.ok(exitCode !== 0 && exitCode !== null, `worker crashed at the failpoint (code ${exitCode})`);

	process.stdout.write("drill A: restart clean — nothing granted\n");
	await startServer(null);
	const cookieA2 = await createSessionWithCookies(cookieA);
	const goldAfterCrash = await joinAndReadGold(cookieA2);
	assert.equal(goldAfterCrash, 250, "crash before commit grants nothing");

	process.stdout.write("drill A: retry the SAME op_id — granted once\n");
	const retryA = await buyPotion(cookieA2, opIdA);
	assert.equal(retryA.status, "accepted", "the retry succeeds once");
	const goldA = await joinAndReadGold(cookieA2);
	assert.equal(goldA, 225, "exactly one deduction after the crash+retry");
	killServer();

	// ---- Scenario B: crash after commit, before the reply ----
	process.stdout.write("drill B: boot with FAILPOINT=after_commit_before_notify\n");
	await startServer("after_commit_before_notify");
	const cookieB = await createSessionWithCookies(cookieA2);
	const opIdB = crypto.randomUUID();
	const resultB = await buyPotion(cookieB, opIdB);
	assert.equal(resultB.status, "accepted");
	const exitB = await waitServerExit();
	assert.ok(exitB !== 0 && exitB !== null, "worker crashed after commit");

	process.stdout.write("drill B: restart clean — committed result replays\n");
	await startServer(null);
	const cookieB2 = await createSessionWithCookies(cookieB);
	const goldCommitted = await joinAndReadGold(cookieB2);
	assert.equal(goldCommitted, 200, "the committed op survived the crash (225 -> 200 once)");

	const retryB = await buyPotion(cookieB2, opIdB);
	assert.equal(retryB.status, "accepted", "the retry replays the committed result");
	const goldFinal = await joinAndReadGold(cookieB2);
	assert.equal(goldFinal, 200, "no double grant: the replay must not deduct again");

	process.stdout.write("drill B: PASS\n");
	process.stdout.write("crash-drill: PASS — §12.4 cases 1-2 hold end to end\n");
} finally {
	killServer();
}
