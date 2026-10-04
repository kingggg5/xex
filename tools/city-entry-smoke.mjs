import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeServerMessage, encodeInput, fnv1a64 } from '../apps/client/src/wire.mjs';
import { connectAuthenticatedClient, createSession, delay, issueJoinTicket, toArrayBuffer } from './net-driver.mjs';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bundleBytes = readFileSync(resolve(repoRoot, 'apps/client/public/content/bundle.json'));
const bundle = JSON.parse(bundleBytes.toString('utf8'));
const bundleHash = fnv1a64(bundleBytes).toString(16).padStart(16, '0');
const zone = bundle.zones[0];
const gate = zone.pois.city_gate;
assert.ok(zone.half_extent >= gate.z + 152, 'zone must include the full authored city up to its north edge');
assert.ok(Array.isArray(zone.static_colliders) && zone.static_colliders.length >= 2, 'zone must publish gate-wing colliders');

const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? 'http://127.0.0.1:3001');
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? 'ws://127.0.0.1:3001/ws');
const allowedOrigin = process.env.AETHERFIELD_ORIGIN ?? 'http://127.0.0.1:5173';
const cookie = await createSession(httpBase, allowedOrigin);
const channelResponse = await fetch(new URL('/session/channel', httpBase), {
  method: 'POST',
  headers: { Origin: allowedOrigin, Cookie: cookie, 'Content-Type': 'application/json' },
  body: JSON.stringify({ channel: 0 }),
});
assert.equal(channelResponse.status, 200, 'guest session must select the development channel');
const ticket = await issueJoinTicket(httpBase, allowedOrigin, cookie);
const client = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, cookie, ticket);
assert.equal(client.welcome.type, 'welcome');
assert.equal(client.welcome.content_hash.toString(16).padStart(16, '0'), bundleHash);

const nextSnapshot = (timeoutMs = 5000) => new Promise((resolveSnapshot, rejectSnapshot) => {
  const timer = setTimeout(() => {
    client.socket.removeEventListener('message', onMessage);
    rejectSnapshot(new Error('Timed out waiting for the city-entry snapshot.'));
  }, timeoutMs);
  const onMessage = async (event) => {
    try {
      const message = decodeServerMessage(await toArrayBuffer(event.data), zone.half_extent);
      if (message.type !== 'snapshot') return;
      clearTimeout(timer);
      client.socket.removeEventListener('message', onMessage);
      resolveSnapshot(message);
    } catch (error) {
      clearTimeout(timer);
      client.socket.removeEventListener('message', onMessage);
      rejectSnapshot(error);
    }
  };
  client.socket.addEventListener('message', onMessage);
});

let latest = await nextSnapshot();
const position = () => latest.players.find((player) => player.id === client.welcome.player_id);
const spawn = position();
assert.ok(spawn, 'joined player must appear in the authoritative snapshot');
const start = { x: spawn.x, z: spawn.z };
const targetZ = gate.z + 152; // R5 fountain/plaza center in the authored layout.
const startedAt = Date.now();
const deadline = startedAt + 65_000;
let latestAfter = spawn;
while (latestAfter.z < targetZ - 2.0 && Date.now() < deadline) {
  client.socket.send(encodeInput(client.welcome.epoch, ++client.sequence, 0, 1, 0));
  latest = await nextSnapshot(5000);
  latestAfter = position();
}
client.socket.send(encodeInput(client.welcome.epoch, ++client.sequence, 0, 0, 0));
await delay(120);
assert.ok(latestAfter.z >= targetZ - 2.0,
  `player did not reach the city plaza: spawn=${start.z.toFixed(2)} final=${latestAfter.z.toFixed(2)} target=${targetZ}`);
assert.ok(Math.abs(latestAfter.x - start.x) < 0.4, 'straight gate route must preserve the lateral lane');
assert.ok(Math.abs(start.x) < 7.0, 'spawn lane must fit inside the clear gate opening');
assert.ok(latestAfter.z < zone.half_extent - 2.0, 'plaza route must remain inside the server zone');
client.socket.close();
await delay(120);

console.log(JSON.stringify({
  result: 'PASS',
  content_hash: bundleHash,
  zone_half_extent: zone.half_extent,
  gate: { x: gate.x, z: gate.z, clear_opening_m: 15 },
  spawn: { x: start.x, z: start.z },
  plaza: { x: latestAfter.x, z: latestAfter.z },
  travel_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(2)),
}, null, 2));
