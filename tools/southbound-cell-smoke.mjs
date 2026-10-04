import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeServerMessage, encodeInput, fnv1a64 } from '../apps/client/src/wire.mjs';
import { connectAuthenticatedClient, createSession, delay, issueJoinTicket, toArrayBuffer } from './net-driver.mjs';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bundleBytes = readFileSync(resolve(repoRoot, 'apps/client/public/content/bundle.json'));
const bundle = JSON.parse(bundleBytes.toString('utf8'));
const coordinateFixture = JSON.parse(readFileSync(resolve(repoRoot, 'apps/protocol/coordinate-fixture-v1.json'), 'utf8'));
const playerRadius = coordinateFixture.player_capsule.radius;
const playerHeight = coordinateFixture.player_capsule.height;
const bundleHash = fnv1a64(bundleBytes).toString(16).padStart(16, '0');
const zone = bundle.zones[0];
const cells = new Map(zone.terrain_cells.map((cell) => [cell.id, cell]));
const marker = zone.pois.south_trail_marker;
const cart = zone.world_props.find((prop) => prop.id === 'sunmeadow_broken_cart');
const southRoute = zone.world_routes.find((route) => route.id === 'southbound_trail');

assert.equal(zone.half_extent, 308, 'the original server boundary stays unchanged');
assert.equal(cells.size, 2, 'the two southbound 64 m cells are in the shared client/server bundle');
assert.equal(cells.get('sunmeadow_c7_r6').neighbors.east, 'sunmeadow_c8_r6');
assert.equal(cells.get('sunmeadow_c8_r6').neighbors.west, 'sunmeadow_c7_r6');
assert.equal(cells.get('sunmeadow_c7_r6').surface_y, cells.get('sunmeadow_c8_r6').surface_y);
assert.ok(cart, 'c8 contains the authored broken-cart landmark');
assert.ok(southRoute?.points.some(([x, z]) => Math.hypot(x - marker.x, z - marker.z) <= 20), 'the exploration route passes the trail-marker clearing');
assert.ok(zone.static_colliders.some((collider) => collider.id === 'sunmeadow_windstone'), 'the marker has an authoritative collider');

const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? 'http://127.0.0.1:3001');
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? 'ws://127.0.0.1:3001/ws');
const allowedOrigin = process.env.AETHERFIELD_ORIGIN ?? 'http://127.0.0.1:5173';
const cookie = await createSession(httpBase, allowedOrigin);
const channelResponse = await fetch(new URL('/session/channel', httpBase), {
	method: 'POST',
	headers: { Origin: allowedOrigin, Cookie: cookie, 'Content-Type': 'application/json' },
	body: JSON.stringify({ channel: 0 }),
});
assert.equal(channelResponse.status, 200, 'local guest must select the development channel');
const ticket = await issueJoinTicket(httpBase, allowedOrigin, cookie);
const client = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, cookie, ticket);
try {
assert.equal(client.welcome.content_hash.toString(16).padStart(16, '0'), bundleHash, 'server and client must use the same cell/collider bundle');

const nextSnapshot = (timeoutMs = 5000) => new Promise((resolveSnapshot, rejectSnapshot) => {
	const timer = setTimeout(() => {
		client.socket.removeEventListener('message', onMessage);
		rejectSnapshot(new Error('Timed out waiting for the southbound-cell snapshot.'));
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
assert.ok(spawn, 'joined player appears in the authoritative snapshot');
const start = { x: spawn.x, z: spawn.z };
const startedAt = Date.now();
let sequence = 0;
let collisionSamples = 0;
async function walkUntil(predicate, x, z, maxTicks, description) {
	for (let tick = 0; tick < maxTicks && !predicate(position()); tick++) {
		client.socket.send(encodeInput(client.welcome.epoch, ++sequence, x, z, 0));
		latest = await nextSnapshot();
		assert.ok(capsuleIsClear(position(), zone.static_colliders, playerRadius, playerHeight),
			`route penetrated an authored collider at ${JSON.stringify(position())}`);
		collisionSamples++;
	}
	assert.ok(predicate(position()), `player failed to reach ${description}: ${JSON.stringify(position())}`);
}

await walkUntil((player) => player.z <= -86.0, 0, -1, 450, 'the new southbound route');
await walkUntil((player) => player.x <= marker.x + 1.2, -1, 0, 120, 'the trail-marker lane');
await walkUntil((player) => Math.hypot(player.x - marker.x, player.z - marker.z) <= 2.2, 0, -1, 120, 'the south trail marker');
const markerPosition = position();
await walkUntil((player) => player.x >= cart.x - 2.5, 1, 0, 300, 'the east c8 terrain cell');
await walkUntil((player) => Math.hypot(player.x - cart.x, player.z - cart.z) <= 3.0, 0, -1, 90, 'the c8 broken-cart landmark');
client.socket.send(encodeInput(client.welcome.epoch, ++sequence, 0, 0, 0));
await delay(120);
const finalPosition = position();
assert.ok(finalPosition.z < -94, 'the player crossed the old field edge at Z=-42 into the new cells');
assert.ok(finalPosition.x > 0, 'the player crossed the reciprocal seam into c8');
assert.ok(capsuleIsClear(finalPosition, zone.static_colliders, playerRadius, playerHeight), 'the final server position clears every authored prop collider');

const receipt = {
	schema: 'aetherfield.southbound-cell-smoke/1',
	result: 'PASS',
	created_at: new Date().toISOString(),
	content_hash: bundleHash,
	zone_half_extent_m: zone.half_extent,
	cells: [...cells.values()].map((cell) => ({ id: cell.id, bounds_xz: cell.bounds_xz, surface_y: cell.surface_y })),
	start,
	landmarks: {
		trail_marker: { x: marker.x, z: marker.z, reached_within_m: Number(Math.hypot(markerPosition.x - marker.x, markerPosition.z - marker.z).toFixed(2)) },
		broken_cart: { x: cart.x, z: cart.z, reached_within_m: Number(Math.hypot(finalPosition.x - cart.x, finalPosition.z - cart.z).toFixed(2)) },
	},
	final: { x: finalPosition.x, z: finalPosition.z },
	travel_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(2)),
	colliders: zone.static_colliders.length,
	collision_samples_checked: collisionSamples,
	limitations: [
		'Local authenticated single-player route smoke; not an Android/iOS visual or frame-time test.',
		'Terrain cells are flat y=0 and do not qualify a full heightfield or navigation mesh.',
		'This does not measure 500-player AOI, network, or server capacity.',
	],
};
const receiptName = basename(process.env.AETHERFIELD_SMOKE_RECEIPT ?? 'southbound-cell-smoke.json');
assert.ok(receiptName.endsWith('.json'), 'receipt must be a JSON filename');
writeFileSync(resolve(repoRoot, 'planning/evidence', receiptName), JSON.stringify(receipt, null, 2) + '\n');
console.log(JSON.stringify(receipt, null, 2));
} finally {
	if (client.socket.readyState !== 3) await client.socket.close();
	await delay(120);
}

function capsuleIsClear(player, colliders, radius, capsuleHeight) {
	return colliders.every((collider) => {
		const [centerX, centerY, centerZ] = collider.center;
		const [width, height, depth] = collider.size;
		if (centerY + height / 2 <= 0 || centerY - height / 2 >= capsuleHeight) return true;
		const closestX = Math.max(centerX - width / 2, Math.min(centerX + width / 2, player.x));
		const closestZ = Math.max(centerZ - depth / 2, Math.min(centerZ + depth / 2, player.z));
		return (player.x - closestX) ** 2 + (player.z - closestZ) ** 2 > radius ** 2;
	});
}
