/** Disposable local guest probe. Credentials remain in memory and are never
 * logged or saved. This does not use browser cookies or change game settings.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PROTOCOL_VERSION, decodeServerMessage, encodeJoin, encodeInput, encodePing, fnv1a64 } from '../apps/client/src/wire.mjs';
import { openAuthenticatedSocket, toArrayBuffer, waitForMessage } from './net-driver.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origin = 'http://127.0.0.1:5173';
const direct = 'http://127.0.0.1:3917';
const frozenPath = path.join(root, '.harness/.cache/city-native-review/baseline-v1/content/bundle.json');
const expectedBytes = await readFile(frozenPath);
const bundle = JSON.parse(expectedBytes.toString('utf8'));
const expectedHash = fnv1a64(expectedBytes).toString(16).padStart(16, '0');
const zoneLimit = bundle.zones[0].half_extent;
const frozenResponse = await fetch(new URL('/content/bundle.json', origin), { cache: 'no-store', signal: AbortSignal.timeout(3000) });
const servedHash = frozenResponse.ok ? fnv1a64(new Uint8Array(await frozenResponse.arrayBuffer())).toString(16).padStart(16, '0') : null;
const report = { schema: 'xexoria.native-city-network-diagnosis/1', origin, frozen_content_hash: expectedHash, frozen_served_status: frozenResponse.status, frozen_served_content_hash: servedHash, expected_protocol: PROTOCOL_VERSION, probes: [], secrets_logged_or_saved: false, browser_storage_accessed: false, product_or_auth_settings_changed: false };

async function fetchOwn(url, options = {}) {
  return fetch(url, { ...options, cache: 'no-store', signal: AbortSignal.timeout(3000) });
}
async function probe(base, label) {
  const result = { label, http: base, ws: base.replace(/^http/u, 'ws') + '/ws', status: 'FAIL', stages: {}, packet_types: {}, decoder_errors: [] };
  let cookie = '', ticket = null, socket = null;
  try {
    const health = await fetchOwn(new URL('/healthz', base)); result.stages.health_status = health.status;
    const providers = await fetchOwn(new URL('/auth/providers', base)); result.stages.providers_status = providers.status;
    if (providers.ok) { const body = await providers.json(); result.stages.providers = { google: body.google === true, discord: body.discord === true }; }
    const session = await fetchOwn(new URL('/session', base), { method: 'POST', headers: { Origin: origin } });
    result.stages.session_status = session.status; assert.equal(session.status, 204, 'fresh own session failed');
    const header = session.headers.get('set-cookie'); assert.ok(header?.startsWith('aetherfield_session='), 'fresh own cookie missing');
    cookie = header.split(';')[0]; result.stages.own_cookie_received = true;
    const whoami = await fetchOwn(new URL('/session/whoami', base), { headers: { Cookie: cookie } }); result.stages.own_whoami_status = whoami.status;
    const ticketResponse = await fetchOwn(new URL('/session/ticket', base), { method: 'POST', headers: { Origin: origin, Cookie: cookie } });
    result.stages.ticket_status = ticketResponse.status; assert.equal(ticketResponse.status, 200, 'own ticket issuance failed');
    const ticketBody = await ticketResponse.json(); assert.match(ticketBody.ticket, /^[a-f0-9]{64}$/u, 'ticket shape invalid');
    ticket = Uint8Array.from(Buffer.from(ticketBody.ticket, 'hex')); result.stages.own_ticket_received = true;
    socket = await openAuthenticatedSocket(new URL(result.ws), origin, cookie); result.stages.websocket_upgrade_status = 101;
    socket.addEventListener('message', async event => {
      try {
        const bytes = await toArrayBuffer(event.data);
        const message = decodeServerMessage(bytes, zoneLimit);
        result.packet_types[message.type] = (result.packet_types[message.type] ?? 0) + 1;
        if (message.type === 'welcome') result.stages.incoming_protocol = new DataView(bytes).getUint8(2);
      } catch (error) { result.decoder_errors.push(error?.message ?? 'decoder failed'); }
    });
    const welcomePromise = waitForMessage(socket, message => message.type === 'welcome' || message.type === 'error', 3000, zoneLimit);
    socket.send(encodeJoin(ticket)); ticket.fill(0); ticket = null;
    const welcome = await welcomePromise;
    if (welcome.type === 'error') throw new Error(`Server join error: ${welcome.code}`);
    assert.equal(welcome.type, 'welcome');
    result.stages.welcome = { protocol: PROTOCOL_VERSION, epoch: welcome.epoch, zone_id: welcome.zone_id, tick_hz: welcome.tick_hz, content_hash: welcome.content_hash.toString(16).padStart(16, '0'), spawn_xz: [welcome.x, welcome.z] };
    assert.ok(welcome.epoch > 0); assert.equal(result.stages.welcome.content_hash, expectedHash, 'welcome/frozen content mismatch');
    assert.equal(welcome.zone_id, bundle.zones[0].id); assert.equal(welcome.tick_hz, bundle.tick_hz);
    const snapshotPromise = waitForMessage(socket, message => message.type === 'snapshot' && message.players.some(player => player.id === welcome.player_id) && message.ack_seq >= 1, 3000, zoneLimit);
    socket.send(encodeInput(welcome.epoch, 1, 0, 0, 0));
    const snapshot = await snapshotPromise; result.stages.neutral_input_ack = snapshot.ack_seq; result.stages.own_snapshot_received = true;
    const nonce = 1727, sentAt = Date.now();
    const pongPromise = waitForMessage(socket, message => message.type === 'pong' && message.nonce === nonce, 3000, zoneLimit);
    socket.send(encodePing(nonce, sentAt >>> 0)); await pongPromise; result.stages.ping_round_trip_ms = Date.now() - sentAt;
    assert.equal(result.decoder_errors.length, 0); result.status = 'PASS';
  } catch (error) {
    // Deliberately print only the bounded error message, never request objects,
    // headers, cookie/ticket values, raw packets or cold identity payloads.
    result.error = String(error?.message ?? 'probe failed').slice(0, 240);
  } finally {
    ticket?.fill(0); ticket = null; cookie = '';
    if (socket) { await socket.close(1000); result.stages.own_websocket_closed = socket.readyState === 3; }
  }
  return result;
}

const deadline = setTimeout(() => { console.log(JSON.stringify({ status: 'FAIL', reason: '25-second local probe deadline', secrets_logged_or_saved: false })); process.exit(1); }, 25000);
try {
  report.probes.push(await probe(direct, 'direct-backend'));
  report.probes.push(await probe(origin, 'frozen-preview-proxy'));
  report.status = servedHash === expectedHash && report.probes.every(probe => probe.status === 'PASS') ? 'PASS' : 'FAIL';
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.status === 'PASS' ? 0 : 1;
} finally { clearTimeout(deadline); }
