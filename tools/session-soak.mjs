import { decodeServerMessage, encodeInput, encodePing } from "../apps/client/src/wire.mjs";
import { connectAuthenticatedClient, createSession, delay, issueJoinTicket, toArrayBuffer } from "./net-driver.mjs";

// V5-05a gate: a long-lived session must survive past the 1 h idle TTL
// (socket tasks refresh it every 5 min) and reconnect to the SAME character.
// Usage: node tools/session-soak.mjs <port> <duration-min>
// Prints one JSON report. Duration default is 90 per the acceptance.

const port = Number(process.argv[2] ?? 3001);
const durationMin = Number(process.argv[3] ?? 90);
const outPath = process.argv[4] ?? null;
const origin = "http://127.0.0.1:5173";
const httpBase = new URL(`http://127.0.0.1:${port}`);
const wsUrl = new URL(`ws://127.0.0.1:${port}/ws`);

const cookie = await createSession(httpBase, origin);
const ticket = await issueJoinTicket(httpBase, origin, cookie);
const client = await connectAuthenticatedClient(httpBase, wsUrl, origin, cookie, ticket);
const playerId = client.welcome.player_id;
const firstEpoch = client.welcome.epoch;
const startedAt = Date.now();
const deadline = startedAt + durationMin * 60 * 1000;
let snapshots = 0;
let lastSnapshotAt = Date.now();
let closedEarly = null;
let shuttingDown = false;
client.socket.addEventListener("close", () => { if (!shuttingDown) closedEarly ??= (Date.now() - startedAt) / 1000; });
client.socket.addEventListener("message", async (event) => {
	try {
		const m = decodeServerMessage(await toArrayBuffer(event.data));
		if (m.type === "snapshot") { snapshots++; lastSnapshotAt = Date.now(); }
	} catch {}
});

let direction = 1;
let seq = 0;
let nonce = 0;
const timer = setInterval(() => {
	if (Date.now() >= deadline || closedEarly !== null) return;
	// Gentle patrol so the world simulates while the session ages.
	if (client.welcome.x !== undefined) {
		seq++;
		client.socket.send(encodeInput(client.welcome.epoch, seq, direction, 0, direction > 0 ? Math.PI / 2 : -Math.PI / 2));
		if (seq % 400 === 0) direction = -direction;
	}
}, 50);
const pingTimer = setInterval(() => {
	if (Date.now() >= deadline || closedEarly !== null) return;
	client.socket.send(encodePing(++nonce, Date.now() % 4294967296));
}, 2000);

while (Date.now() < deadline && closedEarly === null) await delay(1000);
clearInterval(timer);
clearInterval(pingTimer);
shuttingDown = true;
const uptimeS = (Date.now() - startedAt) / 1000;
await client.socket.close().catch(() => {});
await delay(2000);

// Rejoin on the SAME cookie: must restore the same character.
const rejoinStarted = Date.now();
let rejoined = null;
try {
	const ticket2 = await issueJoinTicket(httpBase, origin, cookie);
	const again = await connectAuthenticatedClient(httpBase, wsUrl, origin, cookie, ticket2);
	rejoined = {
		latency_s: +((Date.now() - rejoinStarted) / 1000).toFixed(2),
		same_player: again.welcome.player_id === playerId,
		epoch_bumped: again.welcome.epoch > firstEpoch,
	};
	await again.socket.close().catch(() => {});
} catch (error) {
	rejoined = { error: String(error?.message ?? error) };
}
const report = {
	result: "DONE",
	duration_min: durationMin,
	uptime_s: Math.round(uptimeS),
	snapshots,
	closed_early_at_s: closedEarly,
	player_id: playerId,
	rejoined,
};
console.log(JSON.stringify(report));
if (outPath) {
	const { writeFileSync } = await import("node:fs");
	writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n");
}
await delay(500);
process.exit(0);
