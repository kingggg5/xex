import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { decodeServerMessage, encodeAction, encodeCold, encodeInput, fnv1a64 } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	createSession,
	delay,
	issueJoinTicket,
	toArrayBuffer,
	waitForMessage,
} from "./net-driver.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const buildRoot = resolve(root, "content/build");
const bundleDirs = readdirSync(buildRoot, { withFileTypes: true }).filter((entry) => entry.isDirectory());
assert.equal(bundleDirs.length, 1, "content/build must contain one validated bundle");
const bundleBytes = readFileSync(resolve(buildRoot, bundleDirs[0].name, "bundle.json"));
const bundle = JSON.parse(new TextDecoder().decode(bundleBytes));
assert.equal(fnv1a64(bundleBytes).toString(16).padStart(16, "0"), bundleDirs[0].name);
assert.equal(bundle.zones.length, 1, "smoke bundle must identify one active zone");
const routeZone = bundle.zones[0];
assert.ok(routeZone && Number.isFinite(routeZone.half_extent) && routeZone.half_extent >= 4 && routeZone.half_extent <= 4096,
	"validated bundle must provide the active zone half_extent");
const zoneLimit = routeZone.half_extent;
const wait = (socket, accept, timeoutMs = 3000) => waitForMessage(socket, accept, timeoutMs, zoneLimit);

const httpBase = new URL(process.env.AETHERFIELD_HTTP_URL ?? "http://127.0.0.1:3001");
const websocketUrl = new URL(process.env.AETHERFIELD_WS_URL ?? "ws://127.0.0.1:3001/ws");
const origin = process.env.AETHERFIELD_ORIGIN ?? "http://127.0.0.1:5173";
const clients = [];

try {
	const cookie = await createSession(httpBase, origin);
	const ticket = await issueJoinTicket(httpBase, origin, cookie);
	const client = await connectAuthenticatedClient(httpBase, websocketUrl, origin, cookie, ticket, zoneLimit);
	clients.push(client);
	assert.equal(client.welcome.type, "welcome");
	process.stdout.write("route-smoke: joined\n");
	let latestSnapshot = null;
	client.socket.addEventListener("message", async (event) => {
		try {
			const message = decodeServerMessage(await toArrayBuffer(event.data), zoneLimit);
			if (message.type === "snapshot") latestSnapshot = message;
			if (message.type === "cold") process.stdout.write(`route-smoke: cold ${message.tag} ${JSON.stringify(message.data)}\n`);
		} catch {
			// State assertions below use waitForMessage; this listener only tracks position.
		}
	});

	const questMessage = (windmarkCount, huntCount, state) => (message) =>
		message.type === "cold"
		&& message.tag === "quest_state"
		&& message.data.objectives.windmark >= windmarkCount
		&& message.data.objectives.hunt >= huntCount
		&& (!state || message.data.state === state);
	const sendInput = (x, z) => client.socket.send(encodeInput(client.welcome.epoch, ++client.sequence, x, z, 0));
	const position = () => latestSnapshot?.players.find((player) => player.id === client.welcome.player_id);
	const driveTo = async (x, z, radius = 1.25) => {
		const deadline = Date.now() + 30_000;
		while (Date.now() < deadline) {
			const current = position();
			if (current && Math.hypot(current.x - x, current.z - z) <= radius) break;
			if (current) {
				const dx = x - current.x;
				const dz = z - current.z;
				const length = Math.hypot(dx, dz) || 1;
				sendInput(dx / length, dz / length);
			}
			await delay(60);
		}
		sendInput(0, 0);
		await delay(180);
		const current = position();
		assert.ok(current && Math.hypot(current.x - x, current.z - z) <= radius + 0.25,
			`route bot failed to reach (${x},${z}); actual=${JSON.stringify(current)}`);
	};

	const initialCharacterPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "character_state");
	const initialQuestPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "quest_state");
	client.socket.send(encodeCold({ t: "resync" }));
	const [initialCharacter, initialQuest] = await Promise.all([initialCharacterPromise, initialQuestPromise]);
	process.stdout.write("route-smoke: initial resync\n");
	assert.equal(initialQuest.data.state, "not_started");
	assert.equal(initialCharacter.data.bag.find((item) => item.item === "trail_potion")?.count, 3);

	const farNotice = wait(client.socket, (message) => message.type === "cold" && message.tag === "notice" && message.data.key === "interaction_out_of_range");
	client.socket.send(encodeCold({ t: "interact", npc: "sella" }));
	await farNotice;
	process.stdout.write("route-smoke: range gate\n");

	const sella = bundle.npcs.sella;
	await driveTo(sella.x, sella.z, 1.2);
	process.stdout.write("route-smoke: reached Sella\n");
	const greetingPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "dialogue");
	client.socket.send(encodeCold({ t: "interact", npc: "sella" }));
	const greeting = await greetingPromise;
	process.stdout.write("route-smoke: dialogue opened\n");
	assert.equal(greeting.data.text_key, "sella_greet");
	const acceptedPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "dialogue_closed");
	client.socket.send(encodeCold({ t: "choose", npc: "sella", token: greeting.data.token, choice: "accept" }));
	assert.equal((await acceptedPromise).data.reason, "accepted");
	await wait(client.socket, questMessage(0, 0, "active"));
	process.stdout.write("route-smoke: accepted quest\n");
	const wrongOrderPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "notice" && message.data.key === "windmark_wrong_order");
	client.socket.send(encodeCold({ t: "activate", marker: "windmark_2" }));
	await wrongOrderPromise;

	const zone = bundle.zones.find((entry) => entry.id === client.welcome.zone_id);
	assert.ok(zone, "welcome zone must exist in the validated content bundle");
	await driveTo(zone.pois.windmark_1.x, zone.pois.windmark_1.z);
	process.stdout.write(`route-smoke: windmark 1 position=${JSON.stringify(position())}\n`);
	const channelStarted = wait(client.socket, (message) => message.type === "cold" && message.tag === "notice");
	client.socket.send(encodeCold({ t: "activate", marker: "windmark_1" }));
	const channelNotice = await channelStarted;
	assert.equal(channelNotice.data.key, "windmark_channel_started");
	const cancelledPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "notice" && message.data.key === "windmark_channel_interrupted");
	for (let index = 0; index < 4; index++) {
		sendInput(1, 0);
		await delay(60);
	}
	sendInput(0, 0);
	await cancelledPromise;

	for (const marker of ["windmark_1", "windmark_2", "windmark_3"]) {
		const point = zone.pois[marker];
		await driveTo(point.x, point.z);
		const nextCount = Number(marker.at(-1));
		const questUpdate = wait(client.socket, questMessage(nextCount, 0, "active"));
		client.socket.send(encodeCold({ t: "activate", marker }));
		await wait(client.socket, (message) => message.type === "cold" && message.tag === "notice" && message.data.key === "windmark_channel_started");
		await questUpdate;
	}

	const driveToTarget = async (getTarget, radius = 1.2) => {
		const deadline = Date.now() + 30_000;
		while (Date.now() < deadline) {
			const current = position();
			const target = getTarget();
			if (!target) {
				await delay(60);
				continue;
			}
			const dist = Math.hypot(current.x - target.x, current.z - target.z);
			if (current && dist <= radius) {
				process.stdout.write(`route-smoke: arrived near target dist=${dist.toFixed(2)} target=(${target.x.toFixed(2)}, ${target.z.toFixed(2)}) pos=(${current.x.toFixed(2)}, ${current.z.toFixed(2)})\n`);
				break;
			}
			if (current) {
				const dx = target.x - current.x;
				const dz = target.z - current.z;
				const length = Math.hypot(dx, dz) || 1;
				sendInput(dx / length, dz / length);
			}
			await delay(60);
		}
		sendInput(0, 0);
		await delay(120);
	};

	for (let hunt = 0; hunt < 3; hunt++) {
		// Locate an alive puddlekin
		let target = null;
		for (let wait = 0; wait < 60; wait++) {
			target = latestSnapshot?.monsters.find((m) => m.kind === 1 && m.hp > 0);
			if (target) break;
			await delay(100);
		}
		assert.ok(target, "must locate an alive puddlekin");
		const targetId = target.id;
		process.stdout.write(`route-smoke: hunt ${hunt + 1} selected target id=${targetId} kind=${target.kind} hp=${target.hp} at (${target.x}, ${target.z})\n`);
		await driveToTarget(() => latestSnapshot?.monsters.find((m) => m.id === targetId), 1.2);

		const questUpdate = wait(client.socket, questMessage(3, hunt + 1, hunt === 2 ? "ready_to_claim" : "active"), 15000);
		let acceptedStrikes = 0;
		for (let attempt = 0; attempt < 12; attempt++) {
			let curTarget = latestSnapshot?.monsters.find((m) => m.id === targetId);
			if (curTarget && curTarget.hp === 0) {
				process.stdout.write(`route-smoke: target ${targetId} defeated\n`);
				break;
			}
			let curPos = position();
			if (curPos && curTarget && Math.hypot(curTarget.x - curPos.x, curTarget.z - curPos.z) > 1.8) {
				await driveToTarget(() => latestSnapshot?.monsters.find((m) => m.id === targetId), 1.2);
				curPos = position();
				curTarget = latestSnapshot?.monsters.find((m) => m.id === targetId);
			}
			const tx = curTarget ? curTarget.x : target.x;
			const tz = curTarget ? curTarget.z : target.z;
			const aimPos = curPos ?? position();
			const aim = aimPos ? Math.atan2(tx - aimPos.x, tz - aimPos.z) : 0;
			const sequence = ++client.sequence;
			const actionResult = wait(client.socket, (message) => message.type === "action_result" && message.seq === sequence);
			client.socket.send(encodeAction(client.welcome.epoch, sequence, "attack", aim, targetId, Number(latestSnapshot?.tick ?? 0n)));
			const result = await actionResult;
			if (result.accepted) {
				acceptedStrikes++;
				await delay(450);
			} else {
				const remainingMs = Number(result.ends_at_ms - (latestSnapshot?.tick ?? client.welcome.tick) * 50n);
				await delay(Math.max(0, remainingMs) || 200);
			}
		}
		assert.ok(acceptedStrikes > 0, "at least one strike must be accepted to defeat monster");
		await questUpdate;
		process.stdout.write(`route-smoke: hunt kill ${hunt + 1} confirmed\n`);
	}

	await driveTo(sella.x, sella.z, 1.2);
	const turnInPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "dialogue");
	client.socket.send(encodeCold({ t: "interact", npc: "sella" }));
	const turnIn = await turnInPromise;
	assert.ok(turnIn.data.choices.some((choice) => choice.id === "claim"));
	const opId = "123e4567-e89b-42d3-a456-426614174099";
	const resultPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId);
	client.socket.send(encodeCold({ t: "claim", quest: "three_windmarks", op_id: opId }));
	const result = await resultPromise;
	assert.equal(result.data.status, "accepted");
	process.stdout.write("route-smoke: claim result\n");
	const finalCharacterPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "character_state" && message.data.level === 2);
	const finalQuestPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "quest_state" && message.data.state === "completed");
	const [finalCharacter, finalQuest] = await Promise.all([finalCharacterPromise, finalQuestPromise]);
	assert.ok(finalCharacter.data.exp >= 17, `expected exp >= 17, got ${finalCharacter.data.exp}`);
	assert.ok((finalCharacter.data.pouch.dew_bead ?? 0) >= 1, "expected at least 1 dew_bead in pouch");
	assert.ok((finalCharacter.data.stat_points ?? 0) >= 3, "expected at least 3 stat_points on level up");
	assert.equal(finalCharacter.data.bag.find((item) => item.item === "gale_seed")?.count, 1);
	assert.equal(finalQuest.data.objectives.windmark, 3);
	assert.equal(finalQuest.data.objectives.hunt, 3);
	for (const step of ["accepted", "windmark_1", "windmark_2", "windmark_3", "hunt_1", "hunt_2", "hunt_3", "returned", "claimed"]) {
		assert.ok(Number.isSafeInteger(finalQuest.data.step_ticks[step]), `route step ${step} must carry a server tick`);
	}
	const routeTicks = ["accepted", "windmark_1", "windmark_2", "windmark_3", "hunt_1", "hunt_2", "hunt_3", "returned", "claimed"]
		.map((step) => finalQuest.data.step_ticks[step]);
	assert.ok(routeTicks.every((tick, index) => index === 0 || tick >= routeTicks[index - 1]), "route timestamps must be monotonic");

	const duplicatePromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId, 6000);
	client.socket.send(encodeCold({ t: "claim", quest: "three_windmarks", op_id: opId }));
	assert.equal((await duplicatePromise).data.status, "accepted");
	process.stdout.write("route-smoke: duplicate result\n");
	const conflictPromise = wait(client.socket, (message) => message.type === "cold" && message.tag === "op_result" && message.data.op_id === opId, 6000);
	client.socket.send(encodeCold({ t: "claim", quest: "other_quest", op_id: opId }));
	assert.equal((await conflictPromise).data.reason, "op_id_conflict");
	process.stdout.write("route-smoke: payload conflict\n");

	process.stdout.write(JSON.stringify({
		result: "PASS",
		player_id: client.welcome.player_id,
		quest: "three_windmarks",
		windmarks: finalQuest.data.objectives.windmark,
		hunt: finalQuest.data.objectives.hunt,
		step_ticks: finalQuest.data.step_ticks,
		claim: result.data.status,
		character: { level: finalCharacter.data.level, exp: finalCharacter.data.exp, dew_beads: finalCharacter.data.pouch.dew_bead, gale_seeds: finalCharacter.data.bag.find((item) => item.item === "gale_seed")?.count },
		operation_retry: "accepted_once",
		changed_payload: "op_id_conflict",
		channel_cancelled_on_movement: true,
	}) + "\n");
} finally {
	await Promise.allSettled(clients.map((client) => client.socket.close()));
}
