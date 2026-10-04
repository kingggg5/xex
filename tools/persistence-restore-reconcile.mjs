// V5-13 restore drill (plan v5 §12.4 case 10).
//
// Play a deterministic item flow against PostgreSQL, take a pg_dump backup,
// restore it into a FRESH database, then reconcile: the append-only item
// ledger summed against the seed baseline must equal the restored bag, and
// the exp ledger must never exceed base_exp.
//
// Usage: node tools/persistence-restore-reconcile.mjs

import assert from "node:assert/strict";
import { execSync, spawn } from "node:child_process";
import { existsSync, readFileSync, readdirSync, rmSync } from "node:fs";
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
// The seed bag baseline: the starting potion carry from the content bundle.
const bundle = JSON.parse(
	readFileSync(resolve(root, "content/build", bundleDirs[0].name, "bundle.json"), "utf8"),
);
const seedPotions = bundle.abilities.potion.carry;
assert.equal(typeof seedPotions, "number", "content bundle carries the potion seed count");

const PGBIN = process.env.AETHERFIELD_PGBIN ?? "C:\\Program Files\\PostgreSQL\\16\\bin";
const psql = (...args) =>
	execSync(
		`"${PGBIN}\\psql" -h 127.0.0.1 -p 5499 -U aetherfield -v ON_ERROR_STOP=1 ${args
			.map((arg) => `"${arg}"`)
			.join(" ")}`,
		{ encoding: "utf8" },
	);
const dumpFile = resolve(root, "target", "restore-drill.dump");

const port = process.env.AETHERFIELD_DRILL_PORT ?? "3922";
const databaseUrl = process.env.AETHERFIELD_DATABASE_URL
	?? "postgres://aetherfield@127.0.0.1:5499/aetherfield";
const httpBase = `http://127.0.0.1:${port}`;
const websocketUrl = new URL(`ws://127.0.0.1:${port}/ws`);
const origin = "http://127.0.0.1:5173";


let server = null;
async function startServer() {
	server = spawn(exe, [], {
		env: { ...process.env, AETHERFIELD_PORT: port, AETHERFIELD_DATABASE_URL: databaseUrl },
		stdio: ["ignore", "ignore", "inherit"],
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

function opResult(opId) {
	return (message) =>
		message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId;
}

async function coldOp(cookie, payload) {
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket);
	assert.equal(client.welcome.type, "welcome");
	const resultPromise = waitForMessage(client.socket, opResult(payload.op_id), 10_000);
	client.socket.send(encodeCold(payload));
	const result = (await resultPromise).data;
	await client.socket.close();
	return result;
}

function psqlRows(query) {
	// -t -A -F, → one `a,b,c` line per row; empty result = "".
	const out = psql("-t", "-A", "-F,", "-c", query).trim();
	return out
		.split("\n")
		.filter((line) => line.length > 0)
		.map((line) => line.split(","));
}

try {
	process.stdout.write("restore: boot + play a deterministic item flow\n");
	await startServer();
	const session = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: origin },
		cache: "no-store",
	});
	const cookie = session.headers
		.getSetCookie()
		.map((c) => c.split(";")[0])
		.filter((c) => c.startsWith("aetherfield_"))
		.join("; ");
	// Two buys: bag 3 -> 5, ledger +1 +1 (gold 250 -> 200).
	const op1 = crypto.randomUUID();
	const r1 = await coldOp(cookie, { t: "store_buy", op_id: op1, item: "trail_potion" });
	assert.equal(r1.status, "accepted");
	const op2 = crypto.randomUUID();
	const r2 = await coldOp(cookie, { t: "store_buy", op_id: op2, item: "trail_potion" });
	assert.equal(r2.status, "accepted");
	// Give the coalescing worker its flush window, then stop the server.
	await delay(1800);
	killServer();

	process.stdout.write("restore: pg_dump + restore into a fresh database\n");
	rmSync(dumpFile, { force: true });
	execSync(
		`"${PGBIN}\\pg_dump" -h 127.0.0.1 -p 5499 -U aetherfield -Fc -f "${dumpFile}" aetherfield`,
		{ stdio: "inherit" },
	);
	psql("-c", "DROP DATABASE IF EXISTS aetherfield_restore");
	psql("-c", "CREATE DATABASE aetherfield_restore");
	execSync(
		`"${PGBIN}\\pg_restore" -h 127.0.0.1 -p 5499 -U aetherfield -d aetherfield_restore --no-owner "${dumpFile}"`,
		{ stdio: "inherit" },
	);

	process.stdout.write("restore: reconcile the ledger against the restored state\n");
	const reconcileDb = (query) => {
		const previous = process.env.PGDATABASE;
		const rows = [];
		// -d selects the restore target.
		const out = execSync(
			`"${PGBIN}\\psql" -h 127.0.0.1 -p 5499 -U aetherfield -d aetherfield_restore -t -A -F, -c "${query.replace(/"/g, '\\"')}"`,
			{ encoding: "utf8" },
		).trim();
		void previous;
		for (const line of out.split("\n").filter((line) => line.length > 0)) rows.push(line.split(","));
		return rows;
	};

	// Per-character reconcile: bag(principal,item) == seed + ledger(principal,item).
	// (The DB accumulates characters across drills, so aggregation is per principal.)
	const ledgerSums = new Map();
	for (const [principal, item, delta] of reconcileDb(
		"SELECT principal, item, COALESCE(SUM(delta),0) FROM item_ledger GROUP BY principal, item",
	)) {
		ledgerSums.set(`${principal}|${item}`, Number(delta));
	}
	const bagRows = reconcileDb(
		"SELECT principal, item, COALESCE(SUM(count),0) FROM bag_slots GROUP BY principal, item",
	);
	assert.ok(bagRows.length > 0, "the restored database must contain bag history");
	let reconciled = 0;
	for (const [principal, item, total] of bagRows) {
		const seed = item === "trail_potion" ? seedPotions : 0;
		const ledgerSum = ledgerSums.get(`${principal}|${item}`) ?? 0;
		const expected = seed + ledgerSum;
		assert.equal(
			Number(total),
			expected,
			`restored bag for ${principal}/${item} (${total}) must equal seed ${seed} + ledger ${ledgerSum}`,
		);
		if (ledgerSum !== 0) reconciled += 1;
	}
	assert.ok(reconciled > 0, "at least one character must carry ledger movements");
	process.stdout.write(`restore: reconciled ${bagRows.length} bag rows (${reconciled} with ledger movements) OK\n`);

	// Exp ledger never exceeds base_exp (field EXP rides the checkpoint path).
	const [ledgerExp, baseExp] = reconcileDb(
		"SELECT COALESCE((SELECT SUM(delta) FROM exp_ledger),0), (SELECT COALESCE(MAX(base_exp),0) FROM characters)",
	)[0].map(Number);
	assert.ok(
		ledgerExp <= baseExp,
		`exp ledger ${ledgerExp} must not exceed base_exp ${baseExp}`,
	);
	process.stdout.write(`restore: exp ledger ${ledgerExp} <= base_exp ${baseExp} OK\n`);

	process.stdout.write("restore-reconcile: PASS — backup restore reconciles with the ledger\n");
} finally {
	killServer();
	try {
		psql("-c", "DROP DATABASE IF EXISTS aetherfield_restore");
	} catch {}
	rmSync(dumpFile, { force: true });
}
