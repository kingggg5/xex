// E07 live smoke: buy + equip the blade, assert derived ATK on the wire,
// then verify the equipment + job state survive a server restart.
import assert from "node:assert/strict";
import { spawn, execSync } from "node:child_process";
import { existsSync } from "node:fs";
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
assert.ok(existsSync(exe), "build the server first");
const port = "3923";
const httpBase = `http://127.0.0.1:${port}`;
const ws = new URL(`ws://127.0.0.1:${port}/ws`);
const origin = "http://127.0.0.1:5173";
let server = null;

async function startServer() {
	server = spawn(exe, [], {
		env: { ...process.env, AETHERFIELD_PORT: port, AETHERFIELD_DATABASE_URL: process.env.AETHERFIELD_DATABASE_URL ?? "postgres://aetherfield@127.0.0.1:5499/aetherfield" },
		stdio: ["ignore", "ignore", "ignore"],
	});
	const deadline = Date.now() + 30_000;
	while (Date.now() < deadline) {
		try {
			if ((await fetch(new URL("/healthz", httpBase))).ok) return;
		} catch {}
		await delay(250);
	}
	throw new Error("server unhealthy");
}
function killServer() {
	if (server && server.exitCode === null) execSync(`taskkill /PID ${server.pid} /T /F`, { stdio: "ignore" });
	server = null;
}
async function session(existing) {
	const res = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: origin, ...(existing ? { Cookie: existing } : {}) },
	});
	return res.headers.getSetCookie().map((c) => c.split(";")[0]).filter((c) => c.startsWith("aetherfield_")).join("; ");
}
async function cold(cookie, payload) {
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, ws, origin, cookie, ticket);
	const resultPromise = waitForMessage(
		client.socket,
		(m) => m.type === "cold" && m.tag === "op_result" && m.data.op_id === payload.op_id,
		10_000,
	);
	client.socket.send(encodeCold(payload));
	const result = (await resultPromise).data;
	// the server pushes a fresh character_state right after accepted ops
	const state = await waitForMessage(
		client.socket,
		(m) => m.type === "cold" && m.tag === "character_state",
		10_000,
	).catch(() => null);
	await client.socket.close();
	return { result, state: state?.data ?? null };
}

try {
	await startServer();
	const cookie = await session();
	// buy blade (gold 250-80=170)
	let out = await cold(cookie, { t: "store_buy", op_id: crypto.randomUUID(), item: "frontier_blade" });
	assert.equal(out.result.status, "accepted", `buy: ${out.result.reason}`);
	// equip it
	out = await cold(cookie, { t: "equip_item", op_id: crypto.randomUUID(), item: "frontier_blade" });
	assert.equal(out.result.status, "accepted", `equip: ${out.result.reason}`);
	assert.equal(out.state?.atk, 53, "ATK = 25 base + STR10*2 + blade 8");
	assert.equal(out.state?.def, 3, "DEF = VIT/2 = 3");
	assert.equal(out.state?.base_exp_next, 100, "base curve at level 1");
	assert.equal(out.state?.job_exp_next, 80, "job curve at job level 1");
	assert.ok(out.state?.equipment?.some((e) => e.slot === "weapon" && e.item === "frontier_blade"), "equipment on the wire");
	// restart and verify the equipped blade survives
	await delay(1800);
	killServer();
	await startServer();
	const cookie2 = await session(cookie);
	const ticket = await issueJoinTicket(httpBase, origin, cookie2);
	const client = await connectAuthenticatedClient(httpBase, ws, origin, cookie2, ticket);
	const statePromise = waitForMessage(client.socket, (m) => m.type === "cold" && m.tag === "character_state", 10_000);
	client.socket.send(encodeCold({ t: "resync" }));
	const state = (await statePromise).data;
	await client.socket.close();
	assert.equal(state.gold, 170, "wallet after purchase survives");
	assert.ok(state.equipment?.some((e) => e.slot === "weapon" && e.item === "frontier_blade"), "equipped blade survives");
	assert.equal(state.atk, 53, "derived ATK recomputed from durable equipment");
	process.stdout.write("equip-smoke: PASS — buy+equip+persist+derived stats end to end\n");
} finally {
	killServer();
}
