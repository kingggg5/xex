import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodeServerMessage, encodeCold, encodeInput, encodePing, fnv1a64 } from '../apps/client/src/wire.mjs';
import { connectAuthenticatedClient, createSession, delay, issueJoinTicket, toArrayBuffer, waitForMessage } from './net-driver.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidencePath = path.join(root, 'planning/evidence/minotaur-npc-network-20261001.json');
const logPath = path.join(root, 'planning/evidence/minotaur-npc-network-20261001.log');
const httpBase = new URL('http://127.0.0.1:3001');
const websocketUrl = new URL('ws://127.0.0.1:3001/ws');
const origin = 'http://127.0.0.1:5173';
const expectedHash = fnv1a64(await fs.readFile(path.join(root,'apps/client/public/content/bundle.json'))).toString(16).padStart(16,'0');
const startedAt = Date.now(), deadline = startedAt + 120_000;
const logs = [];
const report = {
	schemaVersion: 1, createdAt: new Date().toISOString(), status: 'FAIL',
	scope: 'Fresh locally created guest session; authenticated movement, proximity gating, NPC dialogue and forged-choice rejection. No browser cookies, persistent accounts, teleport packets, combat, quest acceptance or claims.',
	server: httpBase.href, origin, expectedContentHash: expectedHash, checks: {}, route: [], issues: [],
};
let client, latestSnapshot, protocolError, snapshotCount = 0, inputCount = 0, deadlineTimer;
const log = message => { logs.push(message); console.log(message); };
const budget = () => {
	assert.ok(Date.now() < deadline, '120-second smoke budget expired');
	if (protocolError) throw protocolError;
	if (client) assert.equal(client.socket.readyState, 1, 'own authenticated socket must remain open');
};
let zone;
const wait = (accept, timeoutMs = 5000) => {
	budget();
	return waitForMessage(client.socket, accept, Math.min(timeoutMs, Math.max(1, deadline - Date.now())), zone.half_extent);
};
const position = () => latestSnapshot?.players.find(player => player.id === client.welcome.player_id);
const ownPosition = () => {
	const player = position();
	assert.ok(player, 'own player must be visible in an authoritative snapshot');
	return { x: player.x, z: player.z };
};
const sendInput = (x, z) => {
	budget();
	client.socket.send(encodeInput(client.welcome.epoch, ++client.sequence, x, z, Math.atan2(x, z)));
	inputCount++;
};
const driveTo = async (x, z, radius = 0.5) => {
	const routeStart = Date.now();
	const stepDeadline = Math.min(deadline - 8000, routeStart + 55_000);
	while (Date.now() < stepDeadline) {
		budget();
		const current = ownPosition(), dx = x - current.x, dz = z - current.z;
		if (Math.hypot(dx, dz) <= radius) break;
		const distance = Math.hypot(dx, dz) || 1;
		sendInput(dx / distance, dz / distance);
		await delay(60);
	}
	sendInput(0, 0);
	await delay(200);
	const current = ownPosition();
	assert.ok(Math.hypot(current.x - x, current.z - z) <= radius + 0.25, `Normal movement did not reach (${x}, ${z}); actual (${current.x}, ${current.z}).`);
	const entry = { target: { x, z }, actual: current, travelSeconds: (Date.now() - routeStart) / 1000, authoritativeTick: String(latestSnapshot.tick), acknowledgementSequence: latestSnapshot.ack_seq };
	report.route.push(entry);
	log(`Reached (${x}, ${z}) via authenticated movement at (${current.x.toFixed(2)}, ${current.z.toFixed(2)}).`);
};

async function main() {
	const bundleBytes = await fs.readFile(path.join(root, 'apps/client/public/content/bundle.json'));
	const bundle = JSON.parse(bundleBytes.toString('utf8'));
	const contentHash = fnv1a64(bundleBytes).toString(16).padStart(16, '0');
	assert.equal(contentHash, expectedHash, 'checked-in client bundle must be the NPC content revision');
	zone = bundle.zones.find(candidate => candidate.id === bundle.npcs.bovine_shaman.zone);
	assert.ok(zone, 'NPC must belong to a known zone');
	const npc = bundle.npcs.bovine_shaman;
	assert.deepEqual({ x: npc.x, z: npc.z, radius: npc.radius }, { x: 20, z: 156, radius: 3 });
	const viteContentResponse = await fetch(new URL('/content/bundle.json', origin), { cache: 'no-store', signal: AbortSignal.timeout(5000) });
	assert.equal(viteContentResponse.status, 200, 'Vite must serve the current content bundle');
	const viteHash = fnv1a64(new Uint8Array(await viteContentResponse.arrayBuffer())).toString(16).padStart(16, '0');
	assert.equal(viteHash, expectedHash, 'Vite content must match the tested source');

	// createSession issues a brand-new opaque guest cookie; never load user/browser storage.
	const cookie = await createSession(httpBase, origin);
	const channelResponse = await fetch(new URL('/session/channel', httpBase), {
		method: 'POST', headers: { Origin: origin, Cookie: cookie, 'Content-Type': 'application/json' },
		body: JSON.stringify({ channel: 0 }), cache: 'no-store', signal: AbortSignal.timeout(5000),
	});
	assert.equal(channelResponse.status, 200, 'own guest must select the development channel');
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket, zone.half_extent);
	assert.equal(client.welcome.type, 'welcome');
	assert.equal(client.welcome.content_hash.toString(16).padStart(16, '0'), expectedHash, 'server must serve the same NPC content revision');
	assert.equal(client.welcome.zone_id, npc.zone);
	report.checks.contentHashMatchesClientViteAndServer = true;
	report.checks.ownFreshGuestSession = true;
	client.socket.addEventListener('message', async event => {
		try {
			const message = decodeServerMessage(await toArrayBuffer(event.data), zone.half_extent);
			if (message.type === 'snapshot') { latestSnapshot = message; snapshotCount++; }
			if (message.type === 'error') protocolError = new Error(`Server protocol error: ${message.code}`);
		} catch (error) { protocolError = error; }
	});
	await wait(message => message.type === 'snapshot' && message.players.some(player => player.id === client.welcome.player_id));
	report.spawn = ownPosition();
	assert.ok(Math.hypot(report.spawn.x - npc.x, report.spawn.z - npc.z) > npc.radius, 'fresh spawn must be out of NPC interaction range');
	log('Joined own fresh guest; client, Vite and server content hashes match.');

	const initialQuestPromise = wait(message => message.type === 'cold' && message.tag === 'quest_state');
	client.socket.send(encodeCold({ t: 'resync' }));
	const initialQuest = (await initialQuestPromise).data;
	assert.equal(initialQuest.state, 'not_started');
	report.initialQuest = initialQuest;
	const rangePromise = wait(message => message.type === 'cold' && message.tag === 'notice');
	client.socket.send(encodeCold({ t: 'interact', npc: 'bovine_shaman' }));
	const rangeNotice = (await rangePromise).data;
	assert.equal(rangeNotice.key, 'interaction_out_of_range', 'server must reject NPC talk from the fresh spawn');
	report.checks.initialOutOfRangeRejected = true;
	report.outOfRangeNotice = rangeNotice.key;
	log('NPC interaction from spawn correctly rejected as out of range.');

	const pingNonce = 73129, clientMs = Date.now() >>> 0, pingStarted = Date.now();
	const pongPromise = wait(message => message.type === 'pong' && message.nonce === pingNonce);
	client.socket.send(encodePing(pingNonce, clientMs));
	const pong = await pongPromise;
	assert.equal(pong.client_ms, clientMs);
	report.ping = { roundTripMs: Date.now() - pingStarted, serverTick: String(pong.server_tick) };
	report.checks.authenticatedPingPong = true;

	await driveTo(10.1, -2);
	await driveTo(10.1, 140);
	await driveTo(20, 156, 1.1);
	const finalPosition = ownPosition();
	const interactionDistance = Math.hypot(finalPosition.x - npc.x, finalPosition.z - npc.z);
	assert.ok(interactionDistance <= npc.radius, 'movement must end inside the server-defined NPC radius');
	report.interactionPosition = finalPosition;
	report.interactionDistanceMeters = interactionDistance;
	report.checks.normalAuthoritativeMovementReachedNpc = true;

	const greetingPromise = wait(message => message.type === 'cold' && message.tag === 'dialogue');
	client.socket.send(encodeCold({ t: 'interact', npc: 'bovine_shaman' }));
	const greeting = (await greetingPromise).data;
	assert.equal(greeting.npc, 'bovine_shaman');
	assert.equal(greeting.text_key, 'bovine_shaman_greet');
	assert.deepEqual(greeting.choices, [], 'city elder is a conversation NPC with no quest accept choices');
	assert.match(greeting.token, /^[0-9a-f]{32}$/, 'server must issue a valid dialogue token');
	report.dialogue = { npc: greeting.npc, textKey: greeting.text_key, choices: greeting.choices, validTokenIssued: true };
	report.checks.npcDialogueAndEmptyChoices = true;
	log('Within range: elder greeting returned with no quest choices.');

	const forgedPromise = wait(message => message.type === 'cold' && message.tag === 'notice');
	client.socket.send(encodeCold({ t: 'choose', npc: 'bovine_shaman', token: greeting.token, choice: 'accept' }));
	const forgedNotice = (await forgedPromise).data;
	assert.equal(forgedNotice.key, 'choice_invalid_choice', 'a valid elder token must not accept Sella’s quest');
	report.forgedChoiceNotice = forgedNotice.key;
	report.checks.validNpcTokenCannotAcceptQuest = true;
	const finalQuestPromise = wait(message => message.type === 'cold' && message.tag === 'quest_state');
	client.socket.send(encodeCold({ t: 'resync' }));
	const finalQuest = (await finalQuestPromise).data;
	assert.equal(finalQuest.state, 'not_started');
	assert.deepEqual(finalQuest, initialQuest, 'NPC conversation and forged acceptance must leave the entire quest state unchanged');
	report.finalQuest = finalQuest;
	report.checks.questStateUnchanged = true;
	report.authoritativeSnapshotsReceived = snapshotCount;
	report.movementInputsSent = inputCount;
	report.finalAcknowledgementSequence = latestSnapshot.ack_seq;
	report.checks.freshOwnPlayerVisibilitySnapshots = snapshotCount > 1 && Boolean(position());
	assert.equal(report.checks.freshOwnPlayerVisibilitySnapshots, true);
	log('Forged accept rejected; quest remains unchanged and not started.');
	report.status = 'PASS';
}

try {
	await Promise.race([main(), new Promise((_, reject) => { deadlineTimer = setTimeout(() => reject(new Error('120-second overall smoke timeout')), 120_000); })]);
} catch (error) {
	report.issues.push(error?.message ?? String(error));
	log(`FAIL: ${error?.message ?? String(error)}`);
} finally {
	clearTimeout(deadlineTimer);
	if (client) {
		await client.socket.close(1500);
		report.ownWebSocketClosed = client.socket.readyState === 3;
	}
	report.elapsedSeconds = (Date.now() - startedAt) / 1000;
	await fs.mkdir(path.dirname(evidencePath), { recursive: true });
	await fs.writeFile(evidencePath, JSON.stringify(report, null, 2) + '\n');
	await fs.writeFile(logPath, logs.join('\n') + '\n');
}
console.log(JSON.stringify({ status: report.status, contentHash: expectedHash, elapsedSeconds: report.elapsedSeconds, checks: report.checks, issues: report.issues, evidence: evidencePath }));
// Bounds this smoke process even if an earlier HTTP request did not settle.
process.exit(report.status === 'PASS' ? 0 : 1);
