import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { fixtureCollisionBoxes } from "../apps/client/src/coordinate-collision.mjs";
import { InputTickScheduler, Predictor, RemoteView, ServerTickClock, percentile } from "../apps/client/src/netcode.mjs";
import { encodeAction, encodeInput, encodePing } from "../apps/client/src/wire.mjs";
import {
	connectAuthenticatedClient,
	decodeSocketMessage,
	createSession,
	issueJoinTicket,
	toArrayBuffer,
} from "./net-driver.mjs";

// V5-04b motion-authority measurement bot.
// Supports seeded wander with turns, stops, wall sliding, and dodges on the
// sequence timeline, or patrol/observe/combat modes at 16 ms or 33 ms cadence.
// Enforces V5-04b gate criteria when --expected-rtt-ms 0|100|200 is passed:
//   node tools/netcode-bot.mjs --mode wander --port 3001 --duration-s 30 --expected-rtt-ms 0
// V5-08 combat gate: place one authenticated client in each telegraph, dodge
// from the latest snapshot, and correlate the server result event. A 150 ms
// profile expects an external 75 ms-per-direction proxy:
//   node tools/netcode-bot.mjs --mode combat --port 3002 --expected-rtt-ms 150 --trials 20 --duration-s 120
// Prints one JSON report to stdout.

function parseArgs() {
	const args = process.argv.slice(2);
	const get = (name, fallback) => {
		const index = args.indexOf(`--${name}`);
		return index >= 0 ? args[index + 1] : fallback;
	};
	return {
		mode: get("mode", "wander"),
		wsPort: args.includes("--ws-port") ? Number(get("ws-port", "NaN")) : null,
		port: Number(get("port", 3001)),
		durationS: Number(get("duration-s", 30)),
		expectedRttMs: args.includes("--expected-rtt-ms") ? Number(get("expected-rtt-ms", "NaN")) : null,
		origin: get("origin", "http://127.0.0.1:5173"),
		dodgeEveryMs: Number(get("dodge-every-ms", 1500)),
		cadenceMs: Number(get("cadence-ms", 16)),
		seed: Number(get("seed", 11)),
		trials: Number(get("trials", 20)),
	};
}

const options = parseArgs();
assert.ok(["wander", "patrol", "straight", "observe", "combat"].includes(options.mode), "mode must be wander, patrol, straight, observe, or combat");
assert.ok(Number.isFinite(options.durationS) && options.durationS >= 2 && options.durationS <= 300, "duration must be 2–300 seconds");
assert.ok(Number.isInteger(options.trials) && options.trials >= 1 && options.trials <= 100, "combat trials must be 1–100");
if (options.expectedRttMs !== null) {
	assert.ok([0, 100, 200].includes(options.expectedRttMs) || (options.mode === "combat" && options.expectedRttMs === 150), "expected RTT profile must be 0, 100, 200 ms, or 150 ms for combat");
}

function mulberry32(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}
const random = mulberry32(options.seed);

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixture = JSON.parse(readFileSync(resolve(repoRoot, "apps/protocol/coordinate-fixture-v1.json"), "utf8"));
const buildDir = resolve(repoRoot, "content/build");
const bundleName = readdirSync(buildDir, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name);
assert.equal(bundleName.length, 1, "exactly one built bundle");
const bundle = JSON.parse(readFileSync(resolve(buildDir, bundleName[0], "bundle.json"), "utf8"));

const httpBase = new URL(`http://127.0.0.1:${options.port}`);
assert.ok(options.wsPort===null||(Number.isInteger(options.wsPort)&&options.wsPort>0&&options.wsPort<=65535),"ws-port must be valid");
const websocketUrl = new URL(`ws://127.0.0.1:${options.wsPort??options.port}/ws`);
const boxes = fixtureCollisionBoxes(fixture);
const physics = {
	radius: fixture.player_capsule.radius,
	height: fixture.player_capsule.height,
	boxes,
	limit: bundle.zones[0]?.half_extent ?? 28,
	speed: bundle.player.speed,
};
const dodgeSpeedMult = bundle.abilities.dodge?.speed_mult ?? 2.2;
const dodgeDurationSteps = Math.round((bundle.abilities.dodge?.duration_ms ?? 280) / 50);
const dodgeCooldownMs = bundle.abilities.dodge?.cooldown_ms ?? 900;

const cookie = await createSession(httpBase, options.origin);
const ticket = await issueJoinTicket(httpBase, options.origin, cookie);
const client = await connectAuthenticatedClient(httpBase, websocketUrl, options.origin, cookie, ticket,physics.limit);
assert.equal(client.welcome.type, "welcome");
const playerId = client.welcome.player_id;
const predictor = new Predictor(physics);
predictor.reset(client.welcome.x, client.welcome.z, 0);
const remotes = new RemoteView();
const serverClock = new ServerTickClock();
const inputScheduler = new InputTickScheduler();

const corrections = [];
const ackErrors = [];
const lagGaps = [];
const snapshotArrivalGaps = [], snapshotTickGaps = [], snapshotRelativeDelays = [];
let firstSnapshotArrival = null, firstSnapshotTick = 0, previousSnapshotArrival = null, previousSnapshotTick = 0;
const bands = { blend100: 0, blend200: 0, snap: 0 };
let snaps = 0;
let maxSnap = 0;
let maxCorrectionEvent = null;
let latestTick = Number(client.welcome.tick);
let rttEstimateMs = 0;
let inputSyncReady = false;
const welcomeAt = performance.now();
serverClock.reset(latestTick, welcomeAt);
inputScheduler.reset(serverClock.estimate(welcomeAt));

const remoteRenders = new Map();
const remotePathMeters = new Map();
const remoteStepSamples = [];
const remoteGapSamples = [];
let remoteMaxJump = 0;
let maxRemoteStepEvent = null;
let remoteSamples = 0;
let remoteMaxSampleGapMs = 0;
const rtts = [];
let pingNonce = 0;
const pingSent = new Map();
let socketErrors = 0;
let protocolErrors = 0;
const pingIntervalMs = 2000;

let dodgeStartSeq = 0;
let dodgeBoostEndSeq = 0;
let lastDodgePressAt = 0;
let nextDodgeAt = options.dodgeEveryMs > 0 ? performance.now() + 1000 : Infinity;
let dodgesAttempted = 0;
let dodgesAccepted = 0;
let dodgesRejected = 0;
const pendingActions = new Map();
const pendingTrialIds = new Map();
const combatTrials = [];
const combatEventLog = [];
const activeCombatTrials = new Map();
const seenCombatEvents = new Set();
const previousMonsterStates = new Map();
let combatTarget = null;
let combatHold = false;
let combatDown = false;

const expectedCorrectionP95 = new Map([[0, 0.15], [100, 0.25], [200, 0.40]]);
const remoteConnected = new Map();

client.socket.addEventListener("error", (err) => { socketErrors++; console.error("[bot] socket error:", err); });
client.socket.addEventListener("close", () => { console.log("[bot] socket closed"); });

client.socket.addEventListener("message", async (event) => {
	let message;
	try {
		message = await decodeSocketMessage(client.socket,event.data);
	} catch (e) {
		console.error("[bot] decode error:", e);
		protocolErrors++;
		return;
	}
	if (message.type === "error") {
		console.error("[bot] server error packet:", message);
		return;
	}
	const now = performance.now();
	if (message.type === "pong") {
		const sentAt = pingSent.get(message.nonce);
		if (sentAt !== undefined) {
			pingSent.delete(message.nonce);
			const rtt = Math.max(0, now - sentAt);
			if (rtt < 10000) {
				rtts.push(rtt);
				if (rtts.length > 16) rtts.shift();
				const sorted = [...rtts].sort((a, b) => a - b);
				rttEstimateMs = sorted[Math.floor(sorted.length * 0.5)];
				if (!inputSyncReady) {
					inputScheduler.reset(serverClock.estimate(now), rttEstimateMs);
					inputSyncReady = true;
				}
			}
		}
		return;
	}
	if (message.type === "action_result") {
		const action = pendingActions.get(message.seq);
		pendingActions.delete(message.seq);
		const trialId = pendingTrialIds.get(message.seq);
		pendingTrialIds.delete(message.seq);
		if (trialId !== undefined) {
			const trial = combatTrials.find((item) => item.id === trialId);
			if (trial) trial.dodge_accepted = message.accepted;
		}
		if (message.accepted) {
			dodgesAccepted++;
		} else {
			dodgesRejected++;
			if (action === "dodge") {
				dodgeStartSeq = 0;
				dodgeBoostEndSeq = 0;
				predictor.cancelDodgeBoost(message.seq);
			}
		}
		return;
	}
	if (message.type !== "snapshot") return;
	if (message.tick <= BigInt(latestTick)) return;
	latestTick = Number(message.tick);
	if(firstSnapshotArrival===null){firstSnapshotArrival=now;firstSnapshotTick=latestTick;}
	if(previousSnapshotArrival!==null){snapshotArrivalGaps.push(now-previousSnapshotArrival);snapshotTickGaps.push(latestTick-previousSnapshotTick);snapshotRelativeDelays.push((now-firstSnapshotArrival)-(latestTick-firstSnapshotTick)*50);}
	previousSnapshotArrival=now;previousSnapshotTick=latestTick;
	for(const samples of [snapshotArrivalGaps,snapshotTickGaps,snapshotRelativeDelays])if(samples.length>12000)samples.shift();
	serverClock.observe(latestTick, now);
	remotes.observeSnapshot(latestTick, now);
	if (options.mode !== "observe") {
		const self = message.players.find((player) => player.id === playerId);
		if (self) {
			const before = { x: predictor.x, z: predictor.z };
			const ackPosition = predictor.ring.get(message.ack_seq);
			const result = predictor.reconcile(
				{ x: message.ack_x, z: message.ack_z },
				message.ack_seq,
				{ x: self.x, z: self.z },
			);
			corrections.push(result.error);
			if (result.ackError !== null) ackErrors.push(result.ackError);
			lagGaps.push(result.lagGap);
			bands[result.band]++;
			if (maxCorrectionEvent === null || result.error > maxCorrectionEvent.error_m) {
				maxCorrectionEvent = {
					tick: latestTick,
					ack_seq: message.ack_seq,
					before,
					predicted_ack_position: ackPosition ?? null,
					server_ack_position: { x: message.ack_x, z: message.ack_z },
					server_position: { x: self.x, z: self.z },
					after: { x: predictor.x, z: predictor.z },
					error_m: result.error,
					ack_error_m: result.ackError,
					lag_gap_m: result.lagGap,
				};
			}
			if (result.band === "snap") {
				snaps++;
				maxSnap = Math.max(maxSnap, result.error);
			}
		}
	}
	if (options.mode === "combat") {
		const self = message.players.find((player) => player.id === playerId);
		if (self) {
			combatDown = self.down;
			const active = message.monsters.filter((monster) => monster.active && monster.kind === 1);
			const nearest = active
				.map((monster) => ({ monster, distance: Math.hypot(monster.x - self.x, monster.z - self.z) }))
				.sort((a, b) => a.distance - b.distance)[0];
			combatTarget = nearest ? { x: nearest.monster.x, z: nearest.monster.z } : null;
			combatHold = combatDown || message.monsters.some((monster) => monster.active && monster.state === 2 && monster.ability === 5);

			for (const monster of message.monsters) {
				const previousState = previousMonsterStates.get(monster.id);
				let trial = activeCombatTrials.get(monster.id);
				if (monster.active && monster.state === 2 && monster.ability === 5 && previousState !== 2
					&& combatTrials.length < options.trials) {
					const insideRadius = Math.hypot(self.x - monster.target_x, self.z - monster.target_z)
						<= (bundle.enemies.puddlekin?.splash_radius ?? 2.5);
					trial = insideRadius ? {
						id: combatTrials.length + 1,
						monster_id: monster.id,
						warning_tick: message.tick,
						expected_impact_tick: message.tick + BigInt(monster.state_ticks) + 1n,
						hp_at_warning: self.hp,
						inside_radius_at_warning: true,
						dodge_sent: false,
						dodge_accepted: null,
						evade_event: false,
						damage: 0,
						impact_distance_m: null,
						passed: null,
					} : null;
					if (trial) {
						combatTrials.push(trial);
						activeCombatTrials.set(monster.id, trial);
					}
				}
				if (monster.active && monster.state === 2 && monster.ability === 5 && trial) {
					trial.expected_impact_tick = message.tick + BigInt(monster.state_ticks) + 1n;
					if (trial.inside_radius_at_warning && !trial.dodge_sent && monster.state_ticks <= 7 && inputSyncReady) {
						const actionSeq = ++client.sequence;
						dodgeStartSeq = actionSeq;
						dodgeBoostEndSeq = actionSeq + dodgeDurationSteps;
						pendingActions.set(actionSeq, "dodge");
						pendingTrialIds.set(actionSeq, trial.id);
						client.socket.send(encodeAction(client.welcome.epoch, actionSeq, "dodge", predictor.facing, 0, latestTick >>> 0));
						lastDodgePressAt = now;
						dodgesAttempted++;
						trial.dodge_sent = true;
					}
				} else if (trial && monster.ability === 5 && monster.state >= 3) {
					trial.impact_distance_m = Number(Math.hypot(self.x - monster.target_x, self.z - monster.target_z).toFixed(3));
					trial.hp_at_impact = self.hp;
					trial.down_at_impact = self.down;
				}
				previousMonsterStates.set(monster.id, monster.state);
			}

			for (const event of message.events) {
				if (event.action === "splash_hop" && combatEventLog.length < 64) {
					combatEventLog.push({ id: event.id.toString(), source_id: event.source_id, target_kind: event.target_kind, target_id: event.target_id, flags: event.flags, damage: event.amount });
				}
				if (seenCombatEvents.has(event.id)) continue;
				seenCombatEvents.add(event.id);
				if (seenCombatEvents.size > 256) seenCombatEvents.delete(seenCombatEvents.values().next().value);
				if (event.action !== "splash_hop" || event.target_id !== playerId) continue;
				const trial = activeCombatTrials.get(event.source_id);
				if (!trial) continue;
				if ((event.flags & (1 << 3)) !== 0) trial.evade_event = true;
				if (event.damage > 0) trial.damage = Math.max(trial.damage, event.damage);
			}
			for (const [monsterId, trial] of activeCombatTrials) {
				if (message.tick <= trial.expected_impact_tick + 12n) continue;
				trial.passed = trial.inside_radius_at_warning && trial.dodge_accepted === true && trial.evade_event && trial.damage === 0;
				activeCombatTrials.delete(monsterId);
			}
		}
	}
	const present = new Set();
	for (const player of message.players) {
		if (player.id === playerId) continue;
		present.add(player.id);
		remoteConnected.set(player.id, player.connected);
		remotes.push(player.id, Number(message.tick), player.x, player.z);
	}
	remotes.prune(present);
	for (const id of [...remoteConnected.keys()]) {
		if (!present.has(id)) remoteConnected.delete(id);
	}
});

function sendProbe() {
	if (client.socket.readyState !== 1) return;
	pingNonce = (pingNonce + 1) >>> 0 || 1;
	const sentAt = performance.now();
	for (const [nonce, pendingAt] of pingSent) {
		if (sentAt - pendingAt >= 10000) pingSent.delete(nonce);
	}
	while (pingSent.size >= 8) pingSent.delete(pingSent.keys().next().value);
	pingSent.set(pingNonce, sentAt);
	client.socket.send(encodePing(pingNonce, Math.floor(sentAt) % 4294967296));
}
const pingTimer = setInterval(sendProbe, pingIntervalMs);
sendProbe();

let moveX = 1;
let moveZ = 0;
let nextTurnAt = performance.now();
let patrolDir = predictor.x >= 0 ? -1 : 1;

const stopAt = Date.now() + options.durationS * 1000;
let stopTimer = 0;
const movementTimer = setInterval(() => {
	const combatTrialsComplete = options.mode === "combat"
		&& combatTrials.length >= options.trials
		&& rtts.length >= 5
		&& combatTrials.slice(0, options.trials).every((trial) => trial.passed !== null);
	if (Date.now() >= stopAt || combatTrialsComplete) {
		clearInterval(movementTimer);
		clearInterval(pingTimer);
		clearInterval(remoteTimer);
		clearTimeout(stopTimer);
		client.socket.close().finally(report);
		return;
	}
	const now = performance.now();
	if (options.mode === "wander" && now >= nextTurnAt) {
		const pick = random();
		if (pick < 0.08) {
			moveX = 0;
			moveZ = 0;
		} else {
			const angle = Math.floor(random() * 8) * (Math.PI / 4);
			moveX = Math.sin(angle);
			moveZ = Math.cos(angle);
		}
		// Steer toward center near boundary
		if (Math.abs(predictor.x) > 20 || Math.abs(predictor.z) > 20) {
			const len = Math.hypot(predictor.x, predictor.z) || 1;
			moveX = -predictor.x / len;
			moveZ = -predictor.z / len;
		}
		nextTurnAt = now + 250 + random() * 750;
	}

	// Trigger dodge at intervals / cooldown edge
	if (inputSyncReady && options.mode !== "observe" && options.mode !== "combat" && options.dodgeEveryMs > 0 && now >= nextDodgeAt && now - lastDodgePressAt >= dodgeCooldownMs) {
		lastDodgePressAt = now;
		const actionSeq = ++client.sequence;
		dodgeStartSeq = actionSeq;
		dodgeBoostEndSeq = actionSeq + dodgeDurationSteps;
		pendingActions.set(actionSeq, "dodge");
		const dodgeFacing = moveX !== 0 || moveZ !== 0 ? Math.atan2(moveX, moveZ) : predictor.facing;
		client.socket.send(encodeAction(client.welcome.epoch, actionSeq, "dodge", dodgeFacing, 0, latestTick >>> 0));
		dodgesAttempted++;
		// Alternate between regular interval and cooldown-edge dodge
		const atCooldownEdge = (dodgesAttempted % 3 === 0);
		nextDodgeAt = now + (atCooldownEdge ? dodgeCooldownMs : options.dodgeEveryMs);
	}

	if (inputSyncReady && options.mode !== "observe") {
		const dueTicks = inputScheduler.takeDue(serverClock.estimate(now), rttEstimateMs, 2);
		for (let step = 0; step < dueTicks.length; step++) {
			let x = moveX;
			let z = moveZ;
			if (options.mode === "combat") {
				if (combatHold || combatDown || !combatTarget) {
					x = 0;
					z = 0;
				} else {
					const dx = combatTarget.x - predictor.x;
					const dz = combatTarget.z - predictor.z;
					const distance = Math.hypot(dx, dz);
					if (distance > 5.0) {
						x = dx / distance;
						z = dz / distance;
					} else {
						x = 0;
						z = 0;
					}
				}
			} else if (options.mode === "patrol") {
				if (predictor.x > 20) patrolDir = -1;
				if (predictor.x < -20) patrolDir = 1;
				x = patrolDir;
				z = 0;
			} else if (options.mode === "straight") {
				x = 1;
				z = 0;
			}
			const facing = x !== 0 || z !== 0 ? Math.atan2(x, z) : predictor.facing;
			const inputSeq = ++client.sequence;
			const isDodging = dodgeStartSeq > 0 && inputSeq > dodgeStartSeq && inputSeq <= dodgeBoostEndSeq;
			const mult = isDodging ? dodgeSpeedMult : 1;
			predictor.step(inputSeq, x, z, facing, mult);
			client.socket.send(encodeInput(client.welcome.epoch, inputSeq, x, z, facing));
		}
	}
}, options.cadenceMs);

const remoteTimer = setInterval(() => {
	const now = performance.now();
	const estimatedServerTick = serverClock.estimate(now);
	for (const [id, connected] of remoteConnected) {
		const rendered = remotes.sample(id, estimatedServerTick);
		if (!rendered) continue;
		const previous = remoteRenders.get(id);
		if (previous) {
			const step = Math.hypot(rendered.x - previous.x, rendered.z - previous.z);
			const sampleGapMs = now - previous.at;
			const step16ms = sampleGapMs > 0 ? step * (16.6667 / sampleGapMs) : step;
			remoteStepSamples.push(step16ms);
			remoteGapSamples.push(sampleGapMs);
			if (remoteStepSamples.length > 4096) remoteStepSamples.shift();
			if (remoteGapSamples.length > 4096) remoteGapSamples.shift();
			if (step16ms > remoteMaxJump) {
				remoteMaxJump = step16ms;
				maxRemoteStepEvent = {
					player_id: id,
					latest_tick: latestTick,
					estimated_server_tick: estimatedServerTick,
					delay_ms: remotes.delayMs,
					previous: { x: previous.x, z: previous.z, at: previous.at, held: previous.held },
					rendered: { x: rendered.x, z: rendered.z, held: rendered.held },
					samples: remotes.tracks.get(id)?.slice(-2) ?? [],
				};
			}
			remotePathMeters.set(id, (remotePathMeters.get(id) ?? 0) + step);
			remoteMaxSampleGapMs = Math.max(remoteMaxSampleGapMs, sampleGapMs);
			remoteSamples++;
		}
		remoteRenders.set(id, { x: rendered.x, z: rendered.z, at: now, held: rendered.held });
	}
}, 16);

function summarize(samples) {
	if (samples.length === 0) return { n: 0, p50: 0, p95: 0, p99: 0, max: 0, nonzero_pct: 0 };
	const sorted = [...samples].sort((a, b) => a - b);
	const nonzero = samples.filter((v) => v > 1e-4).length;
	return {
		n: samples.length,
		p50: Number(percentile(sorted, 0.5).toFixed(4)),
		p95: Number(percentile(sorted, 0.95).toFixed(4)),
		p99: Number(percentile(sorted, 0.99).toFixed(4)),
		max: Number(sorted[sorted.length - 1].toFixed(4)),
		nonzero_pct: Number((100 * nonzero / samples.length).toFixed(2)),
	};
}

let reported = false;
function report() {
	if (reported) return;
	reported = true;
	clearInterval(movementTimer);
	clearInterval(pingTimer);
	clearInterval(remoteTimer);
	const correctionSummary = summarize(corrections);
	const maxReportedSnap = Number(maxSnap.toFixed(4));
	const remotePathM = Math.max(0, ...remotePathMeters.values());
	const over1cmCount = corrections.filter((c) => c > 0.01).length;
	const over1cmPct = corrections.length > 0 ? Number((100 * over1cmCount / corrections.length).toFixed(2)) : 0;
	const dodgeAcceptanceRate = dodgesAttempted > 0 ? Number((100 * dodgesAccepted / dodgesAttempted).toFixed(2)) : 100;

	let gate = null;
	const combatTrialSuccesses = combatTrials.filter((trial) => trial.passed === true).length;
	const combatTrialSuccessRate = combatTrials.length > 0
		? Number((100 * combatTrialSuccesses / combatTrials.length).toFixed(2)) : 0;
	if (options.mode === "combat") {
		const rttProfilePassed = options.expectedRttMs === 150 && rtts.length >= 5
			&& Math.abs(summarize(rtts).p50 - 150) <= 50;
		const trialsPassed = combatTrials.length >= options.trials
			&& combatTrialSuccessRate >= 95
			&& combatTrials.every((trial) => trial.passed !== null);
		gate = {
			name: "v5-08-combat-150ms-rtt",
			expected_rtt_ms: 150,
			measured_rtt: summarize(rtts),
			trials_required: options.trials,
			trials_observed: combatTrials.length,
			evades: combatTrialSuccesses,
			success_rate_pct: combatTrialSuccessRate,
			rtt_profile_passed: rttProfilePassed,
			passed: rttProfilePassed && trialsPassed && socketErrors === 0 && protocolErrors === 0,
		};
	} else if (options.expectedRttMs !== null && options.mode !== "observe") {
		const threshold = expectedCorrectionP95.get(options.expectedRttMs);
		const p95Passed = correctionSummary.n >= 100 && correctionSummary.p95 <= threshold;
		const p99Passed = correctionSummary.p99 <= threshold * 2;
		const snapPassed = maxReportedSnap <= 1.0;
		const dodgePassed = dodgesAttempted === 0 || dodgeAcceptanceRate >= 99;
		const noErrors = socketErrors === 0 && protocolErrors === 0;
		gate = {
			name: "v5-04b-motion-authority",
			expected_rtt_ms: options.expectedRttMs,
			max_p95_m: threshold,
			measured_p95_m: correctionSummary.p95,
			measured_p99_m: correctionSummary.p99,
			minimum_samples: 100,
			measured_samples: correctionSummary.n,
			over_1cm_pct: over1cmPct,
			dodge_acceptance_pct: dodgeAcceptanceRate,
			dodges_attempted: dodgesAttempted,
			dodges_accepted: dodgesAccepted,
			dodges_rejected: dodgesRejected,
			passed: p95Passed && p99Passed && snapPassed && dodgePassed && noErrors,
		};
	} else if (options.mode === "observe" && options.expectedRttMs === 100) {
		const gapSummary = summarize(remoteGapSamples);
		gate = {
			name: "remote-interpolation",
			expected_rtt_ms: 100,
			minimum_samples: 300,
			max_sample_gap_ms: 50,
			p95_step_m: 0.15,
			max_step_m: 0.20,
			minimum_active_path_m: 1,
			passed: remoteSamples >= 300 && remoteMaxSampleGapMs <= 50
				&& gapSummary.p95 <= 35
				&& summarize(remoteStepSamples).p95 <= 0.15 && remoteMaxJump <= 0.20
				&& remotePathM >= 1
				&& remotes.delayMs >= 75 && remotes.delayMs <= 200,
		};
	}
	const result = gate === null ? "MEASURED" : gate.passed ? "PASS" : "FAIL";
	console.log(JSON.stringify({
		result,
		mode: options.mode,
		port: options.port,
		duration_s: options.durationS,
		player_id: playerId,
		corrections: correctionSummary,
		corrections_over_1cm_pct: over1cmPct,
		ack_error: summarize(ackErrors),
		lag_gap: summarize(lagGaps),
		snapshot_delivery: {arrival_gap_ms:summarize(snapshotArrivalGaps),tick_gap:summarize(snapshotTickGaps),relative_delay_ms:summarize(snapshotRelativeDelays),delay_reference:"receiver elapsed minus server tick elapsed, relative to first delivery; not absolute one-way delay"},
		bands,
		dodges: {
			attempted: dodgesAttempted,
			accepted: dodgesAccepted,
			rejected: dodgesRejected,
			acceptance_pct: dodgeAcceptanceRate,
		},
		snap_corrections: snaps,
		max_snap_correction_m: maxReportedSnap,
		max_correction_event: maxCorrectionEvent,
		remote: {
			samples: remoteSamples,
			active_path_m: Number(remotePathM.toFixed(4)),
			step_m: summarize(remoteStepSamples),
			sample_gap_ms: summarize(remoteGapSamples),
			max_step_event: maxRemoteStepEvent,
			max_step_m: Number(remoteMaxJump.toFixed(4)),
			max_sample_gap_ms: Number(remoteMaxSampleGapMs.toFixed(2)),
			interp_delay_ms: Number(remotes.delayMs.toFixed(2)),
			jitter_p95_ms: Number(remotes.jitterP95Ms.toFixed(2)),
		},
		rtt_ms: summarize(rtts),
		protocol_errors: protocolErrors,
		socket_errors: socketErrors,
		input_sync_ready: inputSyncReady,
		input_ticks_skipped: inputScheduler.skippedTicks,
		gate,
		combat_trials: options.mode === "combat" ? combatTrials : undefined,
		combat_event_log: options.mode === "combat" ? combatEventLog : undefined,
	}, (_key, value) => typeof value === "bigint" ? value.toString() : value));
	if (result === "FAIL") process.exitCode = 1;
}

stopTimer = setTimeout(() => {
	clearInterval(movementTimer);
	clearInterval(pingTimer);
	clearInterval(remoteTimer);
	client.socket.close().finally(report);
}, options.durationS * 1000 + 4000);
await new Promise((resolve) => client.socket.addEventListener("close", resolve, { once: true }));
