import { decodeServerMessage, encodeInput } from "../apps/client/src/wire.mjs";
import { connectAuthenticatedClient, createSession, delay, issueJoinTicket, toArrayBuffer } from "./net-driver.mjs";

// R3/V5-05a: steady 20 Hz inputs with an uplink stall every 2 s, then a flush
// of the held frames (what TCP delivers after a short radio/Wi-Fi hiccup).
// Token buckets must absorb the flush; only sustained excess may close, and
// then only with an Error(rate_limited) first.
// Usage: node tools/stall-test.mjs <port> <stall-ms>
// (Server port defaults to 3001; use AETHERFIELD_PORT=<p> on the server and
// pass <p> here for parallel verification runs.)

const port = Number(process.argv[2] ?? 3001);
const stallMs = Number(process.argv[3] ?? 300);
const origin = "http://127.0.0.1:5173";
const httpBase = new URL(`http://127.0.0.1:${port}`);
const cookie = await createSession(httpBase, origin);
const ticket = await issueJoinTicket(httpBase, origin, cookie);
const client = await connectAuthenticatedClient(httpBase, new URL(`ws://127.0.0.1:${port}/ws`), origin, cookie, ticket);
const started = performance.now();
let closedAt = null, errorPacket = null, sentInputs = 0, stalls = 0;
client.socket.addEventListener("close", () => { closedAt ??= (performance.now() - started) / 1000; });
client.socket.addEventListener("message", async (event) => {
	try { const m = decodeServerMessage(await toArrayBuffer(event.data)); if (m.type === "error") errorPacket = m.code; } catch {}
});
let held = [];
let stallUntil = 0;
let nextStallAt = started + 1000 + Math.random() * 1000;
let generated = 0;
const timer = setInterval(() => {
	if (closedAt !== null) return;
	const now = performance.now();
	// Exactly 20 Hz by the clock (a 50 ms setInterval runs at ~16 Hz here).
	const due = Math.floor((now - started) / 50) - generated;
	if (now >= nextStallAt && stallUntil === 0) { stalls++; stallUntil = now + stallMs; nextStallAt = now + 2000; }
	for (let i = 0; i < due; i++) {
		generated++;
		const packet = encodeInput(client.welcome.epoch, ++client.sequence, 1, 0, Math.PI / 2);
		sentInputs++;
		if (stallUntil > now) held.push(packet); else client.socket.send(packet);
	}
	if (stallUntil !== 0 && now >= stallUntil) { for (const p of held) client.socket.send(p); held = []; stallUntil = 0; }
}, 4);
await delay(32000);
clearInterval(timer);
console.log(JSON.stringify({ stall_ms: stallMs, stalls_before_close_or_end: stalls, inputs_sent: sentInputs, socket_closed_at_s: closedAt, error_packet_before_close: errorPacket }));
process.exit(0);
