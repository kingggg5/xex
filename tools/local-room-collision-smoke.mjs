import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { decodeServerMessage, encodeAction, encodeCold, encodeInput, encodePing, fnv1a64 } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	createSession,
	delay,
	issueJoinTicket,
	openAuthenticatedSocket,
	rejectedHandshakeStatus,
	toArrayBuffer,
	waitForMessage,
	waitForSocketClose,
} from "./net-driver.mjs";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const buildRoot = resolve(repoRoot, "content/build");
const bundleHashDir = readdirSync(buildRoot, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name);
assert.equal(bundleHashDir.length, 1, "content/build must contain exactly one bundle");
const bundleBytes = readFileSync(resolve(buildRoot, bundleHashDir[0], "bundle.json"));
const bundleHash = fnv1a64(bundleBytes);
assert.equal(bundleHash.toString(16).padStart(16, "0"), bundleHashDir[0], "bundle hash must match its build directory");
const bundle = JSON.parse(new TextDecoder().decode(bundleBytes));
assert.equal(bundle.zones.length, 1, "smoke bundle must identify one active zone");
const defaultZone = bundle.zones[0];
assert.ok(defaultZone && Number.isFinite(defaultZone.half_extent) && defaultZone.half_extent >= 4 && defaultZone.half_extent <= 4096,
	"validated bundle must provide the active zone half_extent");
const zoneLimit = defaultZone.half_extent;
const wait = (socket, accept, timeoutMs = 3000) => waitForMessage(socket, accept, timeoutMs, zoneLimit);

const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? "http://127.0.0.1:3001");
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? "ws://127.0.0.1:3001/ws");
const allowedOrigin = process.env.AETHERFIELD_ORIGIN ?? "http://127.0.0.1:5173";

const clients = [];
try {
	const missingOriginApi = await fetch(new URL("/session", httpBase), {
		method: "POST",
		cache: "no-store",
	});
	assert.equal(missingOriginApi.status, 403, "session creation must reject a missing Origin");
	const missingCookieTicket = await fetch(new URL("/session/ticket", httpBase), {
		method: "POST",
		headers: { Origin: allowedOrigin },
		cache: "no-store",
	});
	assert.equal(missingCookieTicket.status, 401, "ticket issuance must require the session cookie");
	const sessionWithBody = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: allowedOrigin, "Content-Type": "text/plain" },
		body: "unexpected",
	});
	assert.equal(sessionWithBody.status, 400, "session creation must reject request bodies");
	const oversizedBody = await fetch(new URL("/session", httpBase), {
		method: "POST",
		headers: { Origin: allowedOrigin, "Content-Type": "text/plain" },
		body: "x".repeat(129),
	});
	assert.equal(oversizedBody.status, 413, "session endpoints must apply a bounded request-body limit");

	const firstCookie = await createSession(httpBase, allowedOrigin);
	const secondCookie = await createSession(httpBase, allowedOrigin);
	const setChannel = async (cookie, channel) => {
		const res = await fetch(new URL("/session/channel", httpBase), {
			method: "POST",
			headers: { Origin: allowedOrigin, Cookie: cookie, "Content-Type": "application/json" },
			body: JSON.stringify({ channel }),
		});
		assert.equal(res.status, 200);
	};
	await setChannel(firstCookie, 0);
	await setChannel(secondCookie, 0);
	const idleSocket = await openAuthenticatedSocket(websocketUrl, allowedOrigin, firstCookie);
	const joinWaitStartedAt = Date.now();
	await waitForSocketClose(idleSocket, 7000);
	const joinWaitMs = Date.now() - joinWaitStartedAt;
	assert.ok(joinWaitMs >= 4000 && joinWaitMs < 7000, "unjoined WebSocket must close at its idle deadline");
	assert.equal(await rejectedHandshakeStatus(websocketUrl, firstCookie, null), 403, "WebSocket must reject a missing Origin");
	assert.equal(await rejectedHandshakeStatus(websocketUrl, firstCookie, "https://attacker.example"), 403, "WebSocket must reject a foreign Origin");
	assert.equal(await rejectedHandshakeStatus(websocketUrl, null, allowedOrigin), 401, "WebSocket must reject a missing session cookie");

	const firstTicket = await issueJoinTicket(httpBase, allowedOrigin, firstCookie);
	const secondTicket = await issueJoinTicket(httpBase, allowedOrigin, secondCookie);
	const wrongSession = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, secondCookie, firstTicket, zoneLimit);
	clients.push(wrongSession);
	assert.equal(wrongSession.welcome.type, "error", "a ticket must be bound to its issuing cookie session");
	assert.equal(wrongSession.welcome.code, "invalid_join");
	await wrongSession.socket.close();

	const first = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, firstCookie, firstTicket, zoneLimit);
	clients.push(first);
	assert.equal(first.welcome.type, "welcome");
	const second = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, secondCookie, secondTicket, zoneLimit);
	clients.push(second);
	assert.equal(second.welcome.type, "welcome");
	assert.notEqual(first.welcome.player_id, second.welcome.player_id, "separate joins must produce distinct players");
	for (const client of [first, second]) {
		assert.equal(client.welcome.zone_id, bundle.zones[0].id, "welcome must name the bundle zone");
		assert.equal(client.welcome.tick_hz, bundle.tick_hz, "welcome must name the bundle tick rate");
		assert.equal(client.welcome.content_hash, bundleHash, "welcome content hash must match the built bundle");
	}

	const firstCharacterPromise = wait(first.socket, (message) => message.type === "cold" && message.tag === "character_state");
	const firstQuestPromise = wait(first.socket, (message) => message.type === "cold" && message.tag === "quest_state");
	const secondCharacterPromise = wait(second.socket, (message) => message.type === "cold" && message.tag === "character_state");
	const secondQuestPromise = wait(second.socket, (message) => message.type === "cold" && message.tag === "quest_state");
	first.socket.send(encodeCold({ t: "resync" }));
	second.socket.send(encodeCold({ t: "resync" }));
	const [firstCharacter, firstQuest, secondCharacter, secondQuest] = await Promise.all([firstCharacterPromise, firstQuestPromise, secondCharacterPromise, secondQuestPromise]);
	assert.equal(firstCharacter.data.rev, 1, "new session must receive its initial character revision");
	assert.equal(firstCharacter.data.level, 1);
	assert.equal(firstCharacter.data.exp, 0);
	assert.equal(firstCharacter.data.bag.find((item) => item.item === "trail_potion")?.count, 3);
	assert.equal(firstQuest.data.quest, "three_windmarks");
	assert.equal(firstQuest.data.state, "not_started");
	assert.equal(secondCharacter.data.bag.find((item) => item.item === "trail_potion")?.count, 3);
	assert.equal(secondQuest.data.state, "not_started");
	const potionOp = "123e4567-e89b-42d3-a456-426614174000";
	const potionResultPromise = wait(first.socket, (message) => message.type === "cold" && message.tag === "op_result");
	first.socket.send(encodeCold({ t: "use_item", item: "trail_potion", op_id: potionOp }));
	const potionResult = await potionResultPromise;
	assert.equal(potionResult.data.status, "rejected", "a full-health character cannot consume a potion");
	assert.equal(potionResult.data.reason, "hp_full");
	assert.equal(potionResult.data.ends_at_ms, 0);

	const pingNonce = 0x70a1;
	second.socket.send(encodePing(pingNonce, 4242));
	const pong = await wait(second.socket, (message) => message.type === "pong" && message.nonce === pingNonce);
	assert.equal(pong.client_ms, 4242, "pong must echo the client timestamp");
	assert.ok(pong.server_tick > 0n, "pong must carry the server tick");

	const replay = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, firstCookie, firstTicket, zoneLimit);
	clients.push(replay);
	assert.equal(replay.welcome.type, "error", "a consumed join ticket must not be replayable");
	assert.equal(replay.welcome.code, "invalid_join");
	await replay.socket.close();

	let latestSnapshot;
	const snapshots = [];
	first.socket.addEventListener("message", async (event) => {
		try {
		const message = decodeServerMessage(await toArrayBuffer(event.data), zoneLimit);
			if (message.type === "snapshot") {
				latestSnapshot = message;
				snapshots.push(message);
			}
		} catch {
			// The opening handshake is already decoded separately; this listener tracks server snapshots.
		}
	});

	const playerPosition = (playerId) => latestSnapshot?.players.find((player) => player.id === playerId);
	const sendInput = (client, x, z) => {
		client.socket.send(encodeInput(client.welcome.epoch, ++client.sequence, x, z, 0));
	};
	const driveUntil = async (client, predicate, x, z) => {
		// Stay below the 20 Hz apply rate so this scripted route does not build
		// an input queue before it changes direction.
		const deadline = Date.now() + 8000;
		while (Date.now() < deadline) {
			const current = playerPosition(client.welcome.player_id);
			if (current && predicate(current)) break;
			sendInput(client, x, z);
			await delay(60);
		}
		sendInput(client, 0, 0);
		await delay(120);
		return playerPosition(client.welcome.player_id);
	};
	const start = { x: first.welcome.x, z: first.welcome.z };
	await delay(100);
	let current = playerPosition(first.welcome.player_id);
	assert.ok(current, "first player must appear in an intermediate snapshot");
	const clearanceToCube = (player) => Math.hypot(
		player.x - Math.max(0, Math.min(player.x, 1)),
		player.z - Math.max(0, Math.min(player.z, 1)),
	);
	const outsideX = current.x < -0.35 || current.x > 1.35;
	const outsideZ = current.z < -0.35 || current.z > 1.35;
	if (outsideX && outsideZ) {
		const zDirection = current.z < 0 ? 1 : -1;
		const targetZ = current.z < 0 ? 0.25 : 0.75;
		current = await driveUntil(first, (player) => zDirection > 0 ? player.z >= targetZ : player.z <= targetZ, 0, zDirection);
	}
	current = playerPosition(first.welcome.player_id);
	assert.ok(current, "first player must appear before cube approach");
	if (clearanceToCube(current) > 0.55) {
		const xDirection = current.x < 0 ? 1 : current.x > 1 ? -1 : 0;
		const zDirection = xDirection === 0 ? (current.z < 0 ? 1 : -1) : 0;
		current = await driveUntil(first, (player) => clearanceToCube(player) <= 0.55, xDirection, zDirection);
	}

	assert.ok(latestSnapshot, "server must publish a world snapshot");
	const firstPlayer = latestSnapshot.players.find((player) => player.id === first.welcome.player_id);
	const secondPlayer = latestSnapshot.players.find((player) => player.id === second.welcome.player_id);
	assert.ok(firstPlayer && secondPlayer, "both joined players must appear in the authoritative snapshot");
	assert.ok(clearanceToCube(firstPlayer) < 0.7, `smoke route did not reach the cube collision boundary: start=${JSON.stringify(start)} final=(${firstPlayer.x},${firstPlayer.z}) distance=${clearanceToCube(firstPlayer)}`);

	const pressureStart = snapshots.length;
	const pressureStartedAt = Date.now();
	while (Date.now() - pressureStartedAt < 3000) {
		sendInput(first, 1, 0);
		await delay(45);
	}
	const pressureDurationMs = Date.now() - pressureStartedAt;
	sendInput(first, 0, 0);
	await delay(150);
	const wallSamples = snapshots
		.slice(pressureStart)
		.map((snapshot) => snapshot.players.find((player) => player.id === first.welcome.player_id))
		.filter(Boolean);
	assert.ok(wallSamples.length >= 30, `continuous wall pressure produced too few snapshots: ${wallSamples.length}`);
	const wallClearances = wallSamples.map(clearanceToCube);
	const minimumClearance = Math.min(...wallClearances);
	const maximumClearance = Math.max(...wallClearances);
	assert.ok(minimumClearance >= 0.35 - 0.02, `server allowed capsule into unit cube: minimum clearance=${minimumClearance}`);
	assert.ok(minimumClearance < 0.45, `continuous input did not reach contact: minimum clearance=${minimumClearance}`);
	assert.ok(maximumClearance < 0.7, `player left the wall during pressure: maximum clearance=${maximumClearance}`);
	assert.ok(wallSamples.every((player) => player.x < 0 && player.z >= 0 && player.z <= 1), "wall-pressure samples left the cube's left face");

	// Queue up to 3 inputs and apply one per tick. Center the capsule, then let
	// the horizontal queue drain before moving through the doorway.
	await driveUntil(second, (player) => player.x >= 5.8, 1, 0);
	const doorwayPosition = await driveUntil(second, (player) => player.z >= 1.0, 0, 1);
	assert.ok(doorwayPosition, "second player must appear after doorway traversal");
	assert.ok(Math.abs(doorwayPosition.x - 6.0) <= 0.4, `player did not fit through doorway: x=${doorwayPosition.x}`);
	const m101 = latestSnapshot?.monsters.find((m) => m.id === 101) ?? { x: 3.5, z: 4.0 };
	const doorwayCur = playerPosition(second.welcome.player_id) ?? doorwayPosition;
	const mdx = m101.x - doorwayCur.x;
	const mdz = m101.z - doorwayCur.z;
	const mlen = Math.hypot(mdx, mdz) || 1;
	await driveUntil(second, (player) => Math.hypot(player.x - m101.x, player.z - m101.z) <= 2.5, mdx / mlen, mdz / mlen);
	const slashPos = playerPosition(second.welcome.player_id) ?? doorwayCur;
	const cur101 = latestSnapshot?.monsters.find((m) => m.id === 101) ?? m101;
	const slashAim = Math.atan2(cur101.x - slashPos.x, cur101.z - slashPos.z);
	const actionRoomTick = latestSnapshot.tick;
	const actionSeq = ++second.sequence;
	second.socket.send(encodeAction(second.welcome.epoch, actionSeq, "arc_slash", slashAim, 101, Number(latestSnapshot.tick)));
	const actionResult = await wait(
		second.socket,
		(message) => message.type === "action_result" && message.seq === actionSeq,
	);
	assert.equal(actionResult.accepted, true, "arc slash must be accepted with a typed result");
	assert.equal(actionResult.reason, "none");
	assert.equal(typeof actionResult.ends_at_ms, "bigint");
	assert.equal(actionResult.ends_at_ms % 50n, 0n, "accepted expiry must use the room tick clock");
	assert.ok(actionResult.ends_at_ms >= actionRoomTick * 50n + 5000n);
	const attackSnapshot = await wait(
		second.socket,
		(message) => message.type === "snapshot" && message.events.some(
			(event) => event.source_id === second.welcome.player_id && event.target_id === 101,
		),
	);
	assert.ok(actionResult.ends_at_ms <= attackSnapshot.tick * 50n + 5000n, "arc slash expiry must fit the server evaluation tick plus its full 5000 ms duration");
	const attackEvent = attackSnapshot.events.find(
		(event) => event.source_id === second.welcome.player_id && event.target_id === 101,
	);
	assert.ok(attackEvent && attackEvent.id > 0n, "server must resolve the binary action into an event");

	const secondWelcome = second.welcome;
	const closePromise = waitForSocketClose(second.socket);
	second.socket.close();
	await closePromise;
	await delay(80);
	const rejoinTicket = await issueJoinTicket(httpBase, allowedOrigin, second.sessionCookie);
	const resumed = await connectAuthenticatedClient(httpBase, websocketUrl, allowedOrigin, second.sessionCookie, rejoinTicket, zoneLimit);
	clients.push(resumed);
	assert.equal(resumed.welcome.type, "welcome");
	assert.equal(resumed.welcome.player_id, secondWelcome.player_id, "rejoin must restore the same player");
	assert.notEqual(resumed.welcome.epoch, secondWelcome.epoch, "rejoin must advance the connection epoch");
	const resumedCharacterPromise = wait(resumed.socket, (message) => message.type === "cold" && message.tag === "character_state");
	const resumedQuestPromise = wait(resumed.socket, (message) => message.type === "cold" && message.tag === "quest_state");
	resumed.socket.send(encodeCold({ t: "resync" }));
	const [resumedCharacter, resumedQuest] = await Promise.all([resumedCharacterPromise, resumedQuestPromise]);
	assert.ok(resumedCharacter.data.rev >= secondCharacter.data.rev, "reconnect must resync the latest character revision");
	assert.equal(resumedCharacter.data.bag.find((item) => item.item === "trail_potion")?.count, 3);
	assert.equal(resumedQuest.data.state, "not_started");
	const resumedSnapshot = await wait(
		resumed.socket,
		(message) => message.type === "snapshot" && message.players.some(
			(player) => player.id === resumed.welcome.player_id && player.connected,
		),
	);
	assert.ok(resumedSnapshot.players.some((player) => player.id === resumed.welcome.player_id && player.connected));
	const finalFirstPlayer = playerPosition(first.welcome.player_id);
	assert.ok(finalFirstPlayer, "first player remains in the authoritative snapshot");

	process.stdout.write(JSON.stringify({
		result: "PASS",
		origin_checks: { missing: 403, foreign: 403, missing_cookie: 401, missing_ticket_cookie: 401 },
		limits: { rejected_body: sessionWithBody.status, oversized_body: oversizedBody.status, unjoined_socket_ms: joinWaitMs },
		players: [first.welcome.player_id, second.welcome.player_id],
		start_position: start,
		first_player_position: { x: finalFirstPlayer.x, z: finalFirstPlayer.z },
		wall_pressure: {
			duration_ms: pressureDurationMs,
			snapshots: wallSamples.length,
			minimum_clearance_m: Number(minimumClearance.toFixed(3)),
			maximum_clearance_m: Number(maximumClearance.toFixed(3)),
		},
		doorway_exit_position: { x: doorwayPosition.x, z: doorwayPosition.z },
		ping: { nonce: pong.nonce, server_tick: pong.server_tick.toString() },
		action_result: { seq: actionResult.seq, accepted: actionResult.accepted, ends_at_ms: actionResult.ends_at_ms.toString() },
		binary_attack: { event_id: attackEvent.id.toString(), action: attackEvent.action, monster_id: attackEvent.target_id },
		reconnect: { player_id: resumed.welcome.player_id, old_epoch: secondWelcome.epoch, new_epoch: resumed.welcome.epoch },
		server_state_resync: { character_revision: resumedCharacter.data.rev, quest_revision: resumedQuest.data.rev, initial_potions: 3, full_health_potion_rejected: potionResult.data.reason },
		tick: latestSnapshot.tick.toString(),
	}) + "\n");
} finally {
	await Promise.allSettled(clients.map((client) => client.socket.close()));
}
