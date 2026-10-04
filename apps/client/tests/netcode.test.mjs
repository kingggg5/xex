import assert from "node:assert/strict";
import test from "node:test";
import {
	BLEND_FAR_MS,
	BLEND_NEAR_MS,
	CorrectionSmoother,
	InputTickScheduler,
	Predictor,
	RemoteView,
	ServerTickClock,
	classifyCorrection,
	distance,
	percentile,
} from "../src/netcode.mjs";

const openField = { radius: 0.4, height: 1.7, boxes: [], limit: 28, speed: 4.5 };

test("prediction matches fixed steps and reconcile is exact without divergence", () => {
	const predictor = new Predictor(openField);
	predictor.reset(-3, -3, 0);
	for (let seq = 1; seq <= 10; seq++) predictor.step(seq, 1, 0, Math.PI / 2);
	assert.ok(Math.abs(predictor.x - (-3 + 10 * 4.5 * 0.05)) < 1e-9);
	// Server applied seq 8 at the predicted-after-8 position: zero error.
	const anchor = predictor.ring.get(8);
	const result = predictor.reconcile({ x: anchor.x, z: anchor.z }, 8);
	assert.ok(result.error < 1e-9, `unexpected error ${result.error}`);
	assert.equal(result.band, "blend100");
	assert.equal(result.known, true);
	// Replay preserved the two newer steps on top of the server position.
	assert.ok(Math.abs(predictor.x - (-3 + 10 * 4.5 * 0.05)) < 1e-9);
});

test("sequence-zero acknowledgement anchors the Welcome position", () => {
	const predictor = new Predictor(openField);
	predictor.reset(-3, -3, 0);
	predictor.step(1, 1, 0, Math.PI / 2);
	const result = predictor.reconcile({ x: -3, z: -3 }, 0);
	assert.equal(result.known, true);
	assert.equal(result.error, 0);
	assert.ok(Math.abs(predictor.x - (-3 + 4.5 * 0.05)) < 1e-9);
});

test("genuine divergence is measured seq-anchored and replayed", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	for (let seq = 1; seq <= 6; seq++) predictor.step(seq, 1, 0, Math.PI / 2);
	const anchor = predictor.ring.get(4);
	// Server disagrees by 0.5 m at the acked sequence (e.g. loss repeat).
	const result = predictor.reconcile({ x: anchor.x + 0.5, z: anchor.z }, 4);
	assert.ok(Math.abs(result.error - 0.5) < 1e-9);
	assert.ok(Math.abs(result.ackError - 0.5) < 1e-9);
	assert.equal(result.band, "blend200");
	assert.equal(result.lagGap >= 0, true);
});

test("ack anchor avoids double-counting server repeat ticks", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	for (let seq = 1; seq <= 3; seq++) predictor.step(seq, 1, 0, Math.PI / 2);
	const ackPosition = predictor.ring.get(1);
	const serverCurrent = { x: ackPosition.x + 2 * 4.5 * 0.05, z: 0 };
	const result = predictor.reconcile(ackPosition, 1, serverCurrent);
	assert.equal(result.error, 0);
	assert.equal(result.lagGap, 0);
	assert.equal(result.ackError, 0);
});

test("correction bands match the plan thresholds", () => {
	assert.equal(classifyCorrection(0), "blend100");
	assert.equal(classifyCorrection(0.249), "blend100");
	assert.equal(classifyCorrection(0.25), "blend200");
	assert.equal(classifyCorrection(0.999), "blend200");
	assert.equal(classifyCorrection(1.0), "snap");
	assert.equal(classifyCorrection(2.5), "snap");
});

test("evicted ack falls back to a snap", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	for (let seq = 1; seq <= 70; seq++) predictor.step(seq, 1, 0, Math.PI / 2);
	const result = predictor.reconcile({ x: 99, z: 99 }, 1);
	assert.equal(result.known, false);
	assert.equal(result.band, "snap");
});

test("ring overflow snaps even when the remaining positions happen to match", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	for (let seq = 1; seq <= 70; seq++) predictor.step(seq, 0, 0, 0);
	const result = predictor.reconcile({ x: 0, z: 0 }, 0);
	assert.equal(result.error, 0);
	assert.equal(result.known, false);
	assert.equal(result.band, "snap");
});

test("distance and percentile helpers", () => {
	assert.equal(distance(0, 0, 3, 4), 5);
	assert.equal(percentile([], 0.95), 0);
	assert.equal(percentile([1, 2, 3, 4], 0.5), 3);
	assert.equal(BLEND_NEAR_MS, 100);
	assert.equal(BLEND_FAR_MS, 200);
});

test("server tick estimate slews forward on lag and backwards slowly when ahead", () => {
	const clock = new ServerTickClock();
	clock.reset(100, 0);
	assert.equal(clock.estimate(75), 101.5);
	// Server is at tick 101, projected is 101.5: slews backward slowly by at most 0.02 ticks
	const backward = clock.observe(101, 75);
	assert.equal(backward, 101.48);
	assert.equal(clock.estimate(100), 101.98);
	// Server is at tick 106, projected is 101.98 + 1.0 = 102.98: slews forward up to 0.1 ticks
	const forward = clock.observe(106, 150);
	assert.ok(forward > 102.98);
	assert.ok(forward - 102.98 <= 0.1);
});

test("input scheduler targets server ticks with an uplink lead and bounded catch-up", () => {
	const scheduler = new InputTickScheduler();
	scheduler.reset(100);
	assert.deepEqual(scheduler.takeDue(100), [101]);
	assert.deepEqual(scheduler.takeDue(103), [102, 103, 104]);
	scheduler.reset(100, 50);
	assert.deepEqual(scheduler.takeDue(100, 50), [102]);
	scheduler.reset(0);
	assert.deepEqual(scheduler.takeDue(20, 0, 4), [18, 19, 20, 21]);
	assert.equal(scheduler.skippedTicks, 17);
});

test("remote view interpolates between samples and holds at the edges", () => {
	const remotes = new RemoteView();
	remotes.push(7, 100, 0, 0);
	remotes.push(7, 101, 1, 0);
	remotes.push(7, 102, 2, 0);
	// delay 100 ms = 2 ticks: latest 102 renders tick 100 (held at oldest).
	const held = remotes.sample(7, 102);
	assert.deepEqual([held.x, held.z, held.held], [0, 0, true]);
	// Latest 104 renders tick 102 exactly.
	remotes.push(7, 103, 3, 0);
	remotes.push(7, 104, 4, 0);
	const exact = remotes.sample(7, 104);
	assert.ok(Math.abs(exact.x - 2) < 1e-9 && Math.abs(exact.z) < 1e-9);
	// Midpoint interpolation between stored samples.
	const mid = remotes.sample(7, 103);
	assert.ok(Math.abs(mid.x - 1) < 1e-9, `mid interpolation off: ${mid.x}`);
	const renderedFrame = remotes.sample(7, 102.5);
	assert.ok(Math.abs(renderedFrame.x - 0.5) < 1e-9, `fractional tick interpolation off: ${renderedFrame.x}`);
	remotes.prune(new Set());
	assert.equal(remotes.sample(7, 104), null);
});

test("new remote entities stay hidden until their delayed timeline is buffered", () => {
	const remotes = new RemoteView();
	remotes.push(12, 10, 0, 0);
	remotes.push(12, 11, 1, 0);
	assert.equal(remotes.sample(12, 11), null);
	remotes.push(12, 12, 2, 0);
	const firstVisible = remotes.sample(12, 12.5);
	assert.ok(firstVisible);
	assert.equal(firstVisible.x, 0.5);
});

test("remote extrapolation is bounded beyond the delayed render timeline", () => {
	const remotes = new RemoteView();
	remotes.push(9, 10, 0, 0);
	remotes.push(9, 11, 1, 0);
	// The render target is tick 11.5: extrapolate 25 ms beyond the newest sample.
	const extrapolated = remotes.sample(9, 13.5);
	assert.deepEqual(extrapolated, { x: 1.5, z: 0, held: false });
	// 105 ms beyond the target buffer is held at the extrapolation limit (x: 1 + 1 * 2 = 3).
	const held = remotes.sample(9, 15.1);
	assert.deepEqual(held, { x: 3, z: 0, held: true });
});

test("remote delay adapts to p95 snapshot arrival jitter, not stable latency or skipped ticks", () => {
	const calm = new RemoteView();
	for (let tick = 0; tick < 60; tick++) calm.observeSnapshot(tick, 500 + tick * 50);
	assert.equal(calm.delayMs, 100);
	assert.equal(calm.jitterP95Ms, 0);
	// A skipped snapshot arriving over its two-tick server interval is not jitter.
	calm.observeSnapshot(61, 500 + 61 * 50);
	assert.equal(calm.delayMs, 100);
	const jittery = new RemoteView();
	for (let tick = 0; tick < 51; tick++) {
		jittery.observeSnapshot(tick, 1000 + tick * 50 + (tick % 2 === 0 ? 0 : 30));
	}
	assert.equal(jittery.delayMs, 130);
	assert.equal(jittery.jitterP95Ms, 30);
	const offset = new RemoteView();
	for (let tick = 0; tick < 51; tick++) offset.observeSnapshot(tick, 9000 + tick * 50);
	assert.equal(offset.delayMs, 100);
});

test("correction smoothing preserves continuity without blending zero-error updates", () => {
	const smoother = new CorrectionSmoother();
	smoother.correct({ x: 1, z: 0 }, { x: 0.9, z: 0 }, 0.1, "blend100", 1000);
	assert.deepEqual(smoother.sample(0.9, 0, 1000), { x: 1, z: 0 });
	assert.ok(Math.abs(smoother.sample(0.9, 0, 1050).x - 0.95) < 1e-9);
	const startedAt = smoother.startedAt;
	smoother.correct({ x: 0.9, z: 0 }, { x: 0.9, z: 0 }, 0, "blend100", 1050);
	assert.equal(smoother.startedAt, startedAt);
	assert.ok(Math.abs(smoother.sample(0.9, 0, 1100).x - 0.9) < 1e-9);
	smoother.correct({ x: 0.9, z: 0 }, { x: 4, z: 4 }, 1, "snap", 1100);
	assert.deepEqual(smoother.sample(4, 4, 1100), { x: 4, z: 4 });
});

test("prediction is deterministic for identical inputs", () => {
	const run = () => {
		const predictor = new Predictor(openField);
		predictor.reset(-3, -3, 0);
		for (let seq = 1; seq <= 40; seq++) predictor.step(seq, seq % 2 ? 1 : 0, seq % 2 ? 0 : 1, 0);
		return [predictor.x, predictor.z];
	};
	assert.deepEqual(run(), run());
});

test("predictor sub-step render position interpolates smoothly between steps", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	predictor.step(1, 1, 0, Math.PI / 2);
	const stepDist = 4.5 * 0.05; // 0.225m
	assert.ok(Math.abs(predictor.x - stepDist) < 1e-9);
	assert.deepEqual(predictor.renderPosition(0.0), { x: 0, z: 0 });
	const half = predictor.renderPosition(0.5);
	assert.ok(Math.abs(half.x - stepDist * 0.5) < 1e-9);
	const full = predictor.renderPosition(1.0);
	assert.ok(Math.abs(full.x - stepDist) < 1e-9);
});

test("predictor cancelDodgeBoost undos boost on rejected action inputs", () => {
	const predictor = new Predictor(openField);
	predictor.reset(0, 0, 0);
	// Step 1 normal
	predictor.step(1, 1, 0, 0, 1.0);
	// Action at seq 2, next inputs predicted with 2.2x boost
	predictor.step(3, 1, 0, 0, 2.2);
	predictor.step(4, 1, 0, 0, 2.2);
	const boostedX = predictor.x;
	// Server rejects dodge at seq 2
	predictor.cancelDodgeBoost(2);
	assert.ok(predictor.x < boostedX);
	assert.equal(predictor.inputs.get(3).mult, 1.0);
	assert.equal(predictor.inputs.get(4).mult, 1.0);
});

test("input scheduler rate-limits lead changes and pulls nextTick back on decrease", () => {
	const scheduler = new InputTickScheduler();
	scheduler.reset(100, 100); // 100ms = 2 ticks lead -> nextTick = 103
	// High RTT spike to 1500 ms: lead should increase by at most 1 tick per call
	scheduler.takeDue(100, 1500);
	assert.equal(scheduler.leadTicks, 3); // was 2, moved to 3 (not 30)
	// Normal RTT of 50 ms follows: lead decreases smoothly and movement resumes without stalling
	const due = scheduler.takeDue(102, 50);
	assert.ok(due.length > 0, "late pong must not freeze movement input");
});

test("60-minute simulated-time clock drift keeps held frames under 1% with bidirectional slew", () => {
	function rng(seed) {
		let s = seed >>> 0;
		return () => {
			s = (s + 0x6d2b79f5) >>> 0;
			let t = s;
			t = Math.imul(t ^ (t >>> 15), t | 1);
			t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
			return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
		};
	}
	function runSimulation(ppm, skipEveryMin, minutes = 60) {
		const random = rng(3);
		const clock = new ServerTickClock();
		const remotes = new RemoteView();
		const period = 50 * (1 + ppm * 1e-6);
		const arrivals = [];
		let tick = 0, t = 0, skipped = 0;
		const end = minutes * 60000;
		while (t < end) {
			t += period;
			if (skipEveryMin > 0 && Math.floor(t / (skipEveryMin * 60000)) > skipped) { skipped++; t += period; }
			tick++;
			arrivals.push({ tick, at: t + 40 + random() * 30 });
		}
		arrivals.sort((a, b) => a.at - b.at);
		clock.reset(0, 0);
		let i = 0, lastTick = 0;
		let totalRendered = 0, heldFrames = 0;
		for (let now = 0; now < end; now += 16) {
			while (i < arrivals.length && arrivals[i].at <= now) {
				const a = arrivals[i++];
				if (a.tick <= lastTick) continue;
				lastTick = a.tick;
				clock.observe(a.tick, a.at);
				remotes.observeSnapshot(a.tick, a.at);
				remotes.push(7, a.tick, a.tick * 0.225, 0);
			}
			const r = remotes.sample(7, clock.estimate(now));
			if (r) {
				totalRendered++;
				if (r.held) heldFrames++;
			}
		}
		return (heldFrames / totalRendered) * 100;
	}

	for (const [ppm, skip] of [[0, 0], [50, 0], [100, 0], [-100, 0], [0, 5]]) {
		const heldPct = runSimulation(ppm, skip, 60);
		assert.ok(heldPct <= 1.0, `ppm=${ppm} skip=${skip} heldPct=${heldPct}% exceeds 1%`);
	}
});

