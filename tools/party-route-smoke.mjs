import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeServerMessage, encodeCold, fnv1a64 } from '../apps/client/src/wire.mjs';
import { connectAuthenticatedClient, createSession, issueJoinTicket, toArrayBuffer } from './net-driver.mjs';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const bundleBytes = readFileSync(resolve(repoRoot, 'apps/client/public/content/bundle.json'));
const bundleHash = fnv1a64(bundleBytes).toString(16).padStart(16, '0');
const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? 'http://127.0.0.1:3001');
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? 'ws://127.0.0.1:3001/ws');
const origin = process.env.AETHERFIELD_ORIGIN ?? 'http://127.0.0.1:5173';

async function joinGuest() {
	const cookie = await createSession(httpBase, origin);
	const channel = await fetch(new URL('/session/channel', httpBase), {
		method: 'POST',
		headers: { Origin: origin, Cookie: cookie, 'Content-Type': 'application/json' },
		body: JSON.stringify({ channel: 0 }),
	});
	assert.equal(channel.status, 200, 'guest session must select the local test channel');
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket);
	assert.equal(client.welcome.type, 'welcome');
	assert.equal(client.welcome.content_hash.toString(16).padStart(16, '0'), bundleHash);
	return client;
}

function waitForPartyState(client, predicate, timeoutMs = 5000) {
	return new Promise((resolveState, reject) => {
		const timer = setTimeout(() => {
			client.socket.removeEventListener('message', onMessage);
			reject(new Error('Timed out waiting for the party roster update.'));
		}, timeoutMs);
		const onMessage = async (event) => {
			try {
				const message = decodeServerMessage(await toArrayBuffer(event.data));
				if (message.type !== 'cold' || message.data.t !== 'party_state') return;
				if (!predicate(message.data)) return;
				clearTimeout(timer);
				client.socket.removeEventListener('message', onMessage);
				resolveState(message.data);
			} catch (error) {
				clearTimeout(timer);
				client.socket.removeEventListener('message', onMessage);
				reject(error);
			}
		};
		client.socket.addEventListener('message', onMessage);
	});
}

const clients = [];
try {
	for (let index = 0; index < 4; index++) clients.push(await joinGuest());
	const leaderId = clients[0].welcome.player_id;
	const leaderStatePromise = waitForPartyState(clients[0], (state) => state.members.length === 1);
	clients[0].socket.send(encodeCold({ t: 'party_create' }));
	const created = await leaderStatePromise;
	assert.equal(created.leader, leaderId);
	assert.match(created.code, /^[A-Z0-9]{6}$/);
	assert.ok(created.expires_s > 0 && created.expires_s <= 600, 'party invite must expire within ten minutes');

	const membershipSnapshots = [created];
	for (let index = 1; index < clients.length; index++) {
		const expected = index + 1;
		const updates = clients.slice(0, expected).map((client) =>
			waitForPartyState(client, (state) => state.members.length === expected));
		clients[index].socket.send(encodeCold({ t: 'party_join', code: created.code }));
		const states = await Promise.all(updates);
		membershipSnapshots.push(states[0]);
		for (const state of states) {
			assert.equal(state.leader, leaderId);
			assert.equal(new Set(state.members.map((member) => member.id)).size, expected);
			assert.ok(state.members.every((member) => typeof member.name === 'string' && member.name.length > 0));
		}
	}

	const leaveUpdates = clients.map((client, index) =>
		waitForPartyState(client, (state) => state.members.length === (index === 3 ? 0 : 3)));
	clients[3].socket.send(encodeCold({ t: 'party_leave' }));
	const afterLeave = await Promise.all(leaveUpdates);
	assert.ok(afterLeave.slice(0, 3).every((state) => state.members.length === 3));
	assert.equal(afterLeave[3].code, '');

	const receipt = {
		schema: 'aetherfield.party-route-smoke/1',
		result: 'PASS',
		content_hash: bundleHash,
		players: clients.length,
		leader_id: leaderId,
		invite_code_shape: 'six uppercase alphanumeric characters',
		invite_ttl_seconds_at_create: created.expires_s,
		party_sizes_after_join: membershipSnapshots.map((state) => state.members.length),
		party_sizes_after_leave: afterLeave.map((state) => state.members.length),
		limitations: [
			'Local four-client protocol flow only; it is not a human playtest.',
			'No physical phone, touch reach, or network-impairment measurements were made.',
		],
	};
	const evidencePath = resolve(repoRoot, 'planning/evidence/party-route-smoke.json');
	writeFileSync(evidencePath, JSON.stringify(receipt, null, 2) + '\n', 'utf8');
	console.log(JSON.stringify({ ...receipt, evidence: 'planning/evidence/party-route-smoke.json' }, null, 2));
} finally {
	await Promise.allSettled(clients.map((client) => client.socket.close()));
}
