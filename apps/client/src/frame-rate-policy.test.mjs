import test from "node:test";
import assert from "node:assert/strict";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine.js";
import {
	KNOWN_REFRESH_RATES,
	FRAME_RATE_SETTINGS,
	allowedFrameCaps,
	nearestAllowedCap,
	snapRefreshRate,
	normalizeFrameRateSetting,
	resolveFixedFrameCap,
	parseStoredFrameRateSetting,
	serializeFrameRateSetting,
	describeFrameRateOptions,
	createRefreshRateEstimator,
	createFrameLimiter,
	createFrameRatePolicy,
	createPacedFrameRequester,
} from "./frame-rate-policy.mjs";
import { createRenderScaleController } from "./render-scale-controller.mjs";

// ---------------------------------------------------------------------------
// Synthetic rAF streams. Every timestamp carries its true vsync index, so
// pacing is judged in whole vsyncs (what the display shows), not in jittery ms.
// ---------------------------------------------------------------------------

function rng(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/** Vsync grid with bell-shaped jitter (mean of three uniforms) of at most +-jitter ms. */
function vsyncStream({ hz, seconds, jitter = 0.5, seed = 1, start = 1000, quantizeMs = 0 }) {
	const random = rng(seed);
	const period = 1000 / hz;
	const frames = [];
	const total = Math.round(hz * seconds);
	for (let i = 0; i < total; i++) {
		const noise = ((random() + random() + random()) / 3 * 2 - 1) * jitter;
		let t = start + i * period + noise;
		if (quantizeMs > 0) t = Math.round(t / quantizeMs) * quantizeMs;
		frames.push({ t, i });
	}
	return frames;
}

function vsyncGaps(rendered) {
	const gaps = new Map();
	for (let k = 1; k < rendered.length; k++) {
		const gap = rendered[k].i - rendered[k - 1].i;
		gaps.set(gap, (gaps.get(gap) ?? 0) + 1);
	}
	return gaps;
}

/** Feeds every timestamp to the policy; returns rendered frames. `onRender` runs inside a rendered frame. */
function drive(policy, frames, onRender) {
	const rendered = [];
	for (const frame of frames) {
		if (policy.frame(frame.t)) {
			rendered.push(frame);
			onRender?.(frame);
		}
	}
	return rendered;
}

/**
 * A device with back-pressure: after a rendered frame the next callback can
 * only arrive at the first vsync after the frame's cost (CPU or GPU). Idle
 * callbacks are free. `costMs(t)` returns the cost of a frame rendered at t.
 */
function driveWithCost(policy, frames, costMs, onRender) {
	const rendered = [];
	let busyUntil = -Infinity;
	for (const frame of frames) {
		if (frame.t < busyUntil) continue;
		if (policy.frame(frame.t)) {
			rendered.push(frame);
			busyUntil = frame.t + costMs(frame.t) - 0.5;
			onRender?.(frame);
		}
	}
	return rendered;
}

/** Scripted render-scale signal, shaped like render-scale-controller state(). */
function signal(policy, fields) {
	return { atMin: false, atMax: true, deficitMs: 0, surplusMs: 0, loadRatio: null, headroomKnown: false, bound: "unknown", targetFps: policy.targetFps, ...fields };
}

/** Holds a scripted signal while time passes; deficit/surplus grow like the controller's continuous timers. */
function holdSignal(policy, frames, shape) {
	let startedAt = null;
	let lastCap = policy.targetFps;
	return drive(policy, frames, frame => {
		if (startedAt === null || policy.targetFps !== lastCap) { startedAt = frame.t; lastCap = policy.targetFps; }
		const elapsed = frame.t - startedAt;
		const fields = shape(frame, elapsed, policy);
		policy.observeScale(signal(policy, fields), frame.t);
	});
}

// ---------------------------------------------------------------------------
// Ladder and settings
// ---------------------------------------------------------------------------

test("allowed caps are the clean divisors of the refresh rate, down to 30", () => {
	assert.deepEqual(allowedFrameCaps(120), [120, 60, 40, 30]);
	assert.deepEqual(allowedFrameCaps(60), [60, 30]);
	assert.deepEqual(allowedFrameCaps(90), [90, 45, 30]);
	assert.deepEqual(allowedFrameCaps(144), [144, 72, 48, 36]);
	assert.deepEqual(allowedFrameCaps(165), [165, 82.5, 55, 41.25, 33]);
	assert.deepEqual(allowedFrameCaps(240), [240, 120, 80, 60, 48, 40, 34.286, 30]);
	assert.deepEqual(allowedFrameCaps(75), [75, 37.5]);
	assert.deepEqual(allowedFrameCaps(59.94), [59.94, 29.97], "an NTSC-style 59.94 Hz panel still offers its half rate");
	assert.deepEqual(allowedFrameCaps(50), [50], "25 fps is below the floor, so 50 Hz offers only 50");
	assert.deepEqual(allowedFrameCaps(30), [30], "a 30 Hz rAF is its own ceiling");
	assert.ok(Object.isFrozen(allowedFrameCaps(120)));
	assert.deepEqual([...KNOWN_REFRESH_RATES], [30, 48, 50, 60, 72, 75, 90, 100, 120, 144, 165, 240]);
});

test("user settings clamp to the nearest allowed cap by frame time; Max is the refresh rate", () => {
	const cases = [
		// [setting, refresh, expected cap]
		[30, 60, 30], [60, 60, 60], [90, 60, 60], [120, 60, 60], ["max", 60, 60],
		[30, 90, 30], [60, 90, 45], [90, 90, 90], [120, 90, 90], ["max", 90, 90],
		[30, 120, 30], [60, 120, 60], [90, 120, 120], [120, 120, 120], ["max", 120, 120],
		[30, 144, 36], [60, 144, 72], [90, 144, 72], [120, 144, 144], ["max", 144, 144],
		[60, 165, 55], [120, 240, 120], [60, 50, 50], [60, 30, 30], [120, 30, 30],
	];
	for (const [setting, refresh, expected] of cases) {
		assert.equal(resolveFixedFrameCap(setting, refresh), expected, `${setting} on ${refresh} Hz`);
	}
	assert.equal(nearestAllowedCap(60, 144), 72, "13.9 ms is closer to 16.7 ms than 20.8 ms is");
	assert.equal(nearestAllowedCap(NaN, 144), 144);
});

test("settings normalize, persist versioned, and fall back to Auto", () => {
	assert.deepEqual([...FRAME_RATE_SETTINGS], ["auto", 30, 60, 90, 120, "max"]);
	assert.equal(normalizeFrameRateSetting("60"), 60);
	assert.equal(normalizeFrameRateSetting(59.6), 60);
	assert.equal(normalizeFrameRateSetting(5), 30, "below the floor clamps up");
	assert.equal(normalizeFrameRateSetting(5000), 1000);
	assert.equal(normalizeFrameRateSetting("max"), "max");
	for (const bad of [undefined, null, "", "fast", NaN, -1, {}, true]) assert.equal(normalizeFrameRateSetting(bad), "auto");
	for (const value of FRAME_RATE_SETTINGS) assert.equal(parseStoredFrameRateSetting(serializeFrameRateSetting(value)), value);
	for (const raw of ["{bad", JSON.stringify({ version: 0, setting: 60 }), JSON.stringify({ version: 1, setting: "warp" }), "", null]) {
		assert.equal(parseStoredFrameRateSetting(raw), "auto");
	}
});

test("measured rates snap to known rates; unknown panels keep their own rate", () => {
	assert.equal(snapRefreshRate(59.94), 60);
	assert.equal(snapRefreshRate(119.88), 120);
	assert.equal(snapRefreshRate(143.86), 144);
	assert.equal(snapRefreshRate(250), 240, "1 ms timestamp rounding at 240 Hz reads 250");
	assert.equal(snapRefreshRate(73.4), 72);
	assert.equal(snapRefreshRate(74.2), 75);
	assert.equal(snapRefreshRate(180), 180);
	assert.equal(snapRefreshRate(360.4), 360);
	assert.equal(snapRefreshRate(0), null);
	assert.equal(snapRefreshRate(NaN), null);
});

// ---------------------------------------------------------------------------
// Refresh-rate estimation
// ---------------------------------------------------------------------------

test("estimates 60/90/120/144 Hz from jittered rAF streams, idle-mixed or fully rendered", () => {
	for (const hz of [60, 90, 120, 144]) {
		for (const pattern of ["half-idle", "all-rendered"]) {
			const estimator = createRefreshRateEstimator();
			const frames = vsyncStream({ hz, seconds: 2, jitter: 0.6, seed: hz });
			let lockedAt = null;
			frames.forEach((frame, index) => {
				estimator.addFrame(frame.t, pattern === "all-rendered" ? true : index % 2 === 1);
				if (lockedAt === null && estimator.phase === "locked") lockedAt = index;
			});
			const state = estimator.state();
			assert.equal(state.refreshHz, hz, `${hz} Hz ${pattern}`);
			assert.ok(lockedAt !== null && lockedAt <= 25, `${hz} Hz ${pattern} locked after ${lockedAt} frames`);
			assert.ok(Math.abs(state.periodMs - 1000 / hz) < 0.05, `${hz} Hz period ${state.periodMs}`);
			assert.equal(state.needsProbe, false);
			assert.equal(state.throttled, false);
		}
	}
});

test("1 ms timestamp rounding and off-nominal panels still lock to the right rate", () => {
	for (const [hz, expected] of [[144, 144], [240, 240], [165, 165], [59.94, 60], [119.88, 120], [75, 75], [72, 72]]) {
		const estimator = createRefreshRateEstimator();
		const frames = vsyncStream({ hz, seconds: 2, jitter: 0.2, seed: 9, quantizeMs: 1 });
		frames.forEach((frame, index) => estimator.addFrame(frame.t, index % 2 === 1));
		assert.equal(estimator.refreshHz, expected, `${hz} Hz quantized to 1 ms`);
	}
});

test("a 30 Hz Low Power rAF becomes the ceiling: Auto, 60 and Max all resolve to 30", () => {
	for (const setting of ["auto", 60, "max"]) {
		const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, setting });
		drive(policy, vsyncStream({ hz: 30, seconds: 6, jitter: 0.5, seed: 3 }));
		const state = policy.state();
		assert.equal(state.refreshHz, 30, `${setting}: detected rAF rate`);
		assert.equal(state.throttled, true);
		assert.equal(state.lowPowerSuspected, true);
		assert.deepEqual([...state.allowedCaps], [30]);
		assert.equal(state.capFps, 30);
		assert.ok(state.limiter.probes >= 3 && state.limiter.probes <= 8, `${setting}: ${state.limiter.probes} probes to prove the 30 Hz rAF`);
	}
});

test("a browser-capped rAF (30 Hz display link, or WebKit's 30 ms timer) passes straight through: no cap of our own", () => {
	// 30.05 Hz puts every timestamp just under 33.33 ms: the case where an accumulator skips a whole tick.
	for (const [hz, expectedRafHz] of [[30.05, 30], [1000 / 30, 33]]) {
		const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, setting: 60 });
		drive(policy, vsyncStream({ hz, seconds: 8, jitter: 0.5, seed: 74 }));
		let state = policy.state();
		assert.equal(state.browserCap30, true, `${hz} Hz: browser cap detected`);
		assert.equal(state.lowPowerSuspected, true);
		assert.equal(state.rafHz, expectedRafHz);
		assert.equal(state.divisor, 1, "one rAF per frame: the limiter adds no cap");
		assert.equal(state.optIn, null, "Smooth 60 has nothing to earn under a browser cap");
		const before = state.limiter;
		const rendered = drive(policy, vsyncStream({ hz, seconds: 30, jitter: 0.5, seed: 75, start: 9500 }));
		state = policy.state();
		assert.equal(state.limiter.skipped - before.skipped, 0, `${hz} Hz: no callback skipped after detection`);
		assert.deepEqual([...vsyncGaps(rendered).keys()], [1], "never a 66 ms frame");
	}
});

test("Low Power turning off raises the rate back within a second", () => {
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30 });
	drive(policy, vsyncStream({ hz: 30, seconds: 6, seed: 4 }));
	assert.equal(policy.state().refreshHz, 30);
	const resumed = vsyncStream({ hz: 60, seconds: 4, seed: 5, start: 7100 });
	let raisedAt = null;
	for (const frame of resumed) {
		policy.frame(frame.t);
		if (raisedAt === null && policy.state().refreshHz === 60) raisedAt = frame.t - resumed[0].t;
	}
	assert.ok(raisedAt !== null && raisedAt < 1000, `re-locked to 60 Hz after ${raisedAt} ms`);
	const state = policy.state();
	assert.equal(state.throttled, false);
	assert.deepEqual([...state.allowedCaps], [60, 30]);
	assert.equal(state.capFps, 30, "mobile Auto stays on its 30 fps base");
});

test("a GPU-bound 60 Hz stream is not mistaken for a 30 Hz rAF, and does not keep probing", () => {
	// Fixed 60 cap, every rendered frame costs 20 ms (misses a vsync); idle callbacks are free.
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, setting: 60 });
	const frames = vsyncStream({ hz: 60, seconds: 120, jitter: 0.4, seed: 6 });
	driveWithCost(policy, frames, () => 20);
	const state = policy.state();
	assert.equal(state.refreshHz, 60, "idle-frame probes still see 16.7 ms vsync");
	assert.equal(state.throttled, false);
	assert.equal(state.capFps, 60, "a fixed setting is not changed by load");
	assert.ok(state.limiter.probes <= 16, `${state.limiter.probes} probes in 2 minutes`);
});

test("moving the window from 144 Hz to 60 Hz is re-detected, with or without a screen-change event", () => {
	for (const notify of [true, false]) {
		const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
		drive(policy, vsyncStream({ hz: 144, seconds: 3, seed: 7 }));
		assert.equal(policy.state().refreshHz, 144);
		assert.equal(policy.state().capFps, 72, "High tier 60 fps maps to 72 on 144 Hz");
		const moved = vsyncStream({ hz: 60, seconds: 8, seed: 8, start: 4100 });
		if (notify) policy.notifyScreenChange(moved[0].t);
		let detectedAt = null;
		for (const frame of moved) {
			policy.frame(frame.t);
			if (detectedAt === null && policy.state().refreshHz === 60) detectedAt = frame.t - moved[0].t;
		}
		assert.ok(detectedAt !== null && detectedAt < (notify ? 1000 : 5000), `notify=${notify}: re-detected after ${detectedAt} ms`);
		assert.equal(policy.state().capFps, 60);
	}
});

// ---------------------------------------------------------------------------
// Vsync-aligned limiter
// ---------------------------------------------------------------------------

test("limiter at 120 Hz paces 60 fps at exactly 2 vsyncs and 40 fps at exactly 3, under jitter", () => {
	for (const [cap, divisor] of [[60, 2], [40, 3], [30, 4]]) {
		for (const jitter of [0.5, 1.5]) {
			const limiter = createFrameLimiter({ refreshHz: 120, capFps: cap });
			const frames = vsyncStream({ hz: 120, seconds: 60, jitter, seed: cap + jitter * 10 });
			const rendered = frames.filter(frame => limiter.shouldRender(frame.t));
			const gaps = vsyncGaps(rendered);
			assert.deepEqual([...gaps.keys()], [divisor], `cap ${cap} jitter ${jitter}: gaps ${JSON.stringify([...gaps])}`);
			const stats = limiter.stats();
			assert.equal(stats.late, 0);
			assert.equal(stats.dropped, 0);
			assert.ok(Math.abs(stats.achievedFps - cap) < 0.2, `achieved ${stats.achievedFps}`);
			assert.ok(Math.abs(limiter.intervalMs - 1000 / cap) < 1e-9);
		}
	}
});

test("the deadline grid follows a slightly-off vsync for 5 minutes without slipping", () => {
	// The limiter believes exactly 120 Hz; the panel runs at 119.88 Hz (and 120.12 Hz).
	for (const actual of [119.88, 120.12]) {
		const limiter = createFrameLimiter({ refreshHz: 120, capFps: 60 });
		const rendered = vsyncStream({ hz: actual, seconds: 300, jitter: 0.5, seed: 12 }).filter(frame => limiter.shouldRender(frame.t));
		assert.deepEqual([...vsyncGaps(rendered).keys()], [2], `${actual} Hz`);
	}
});

test("a late frame costs one long interval, then pacing resumes on the new phase", () => {
	const limiter = createFrameLimiter({ refreshHz: 60, capFps: 30 });
	const frames = vsyncStream({ hz: 60, seconds: 4, jitter: 0.3, seed: 13 });
	const hitchIndex = 101; // a rendered vsync (odd index after the first render at 0? find dynamically below)
	const rendered = [];
	let skippedOnce = false;
	for (const frame of frames) {
		// Drop the first callback that would render after 100 vsyncs: main-thread jank delays it by one vsync.
		if (!skippedOnce && frame.i >= hitchIndex - 1 && (frame.i % 2 === 0)) { skippedOnce = true; continue; }
		if (limiter.shouldRender(frame.t)) rendered.push(frame);
	}
	const gaps = [...vsyncGaps(rendered).entries()];
	assert.deepEqual(gaps.sort(), [[2, rendered.length - 2], [3, 1]], `one 3-vsync gap, never a 1-vsync catch-up: ${JSON.stringify(gaps)}`);
	const stats = limiter.stats();
	assert.equal(stats.late, 1);
	assert.equal(stats.dropped, 0);
});

test("a long hitch counts dropped intervals; a stall re-anchors without counting", () => {
	const limiter = createFrameLimiter({ refreshHz: 60, capFps: 60 });
	for (let i = 0; i <= 10; i++) limiter.shouldRender(1000 + i * 1000 / 60);
	assert.equal(limiter.shouldRender(1000 + 14 * 1000 / 60), true, "a frame 3 vsyncs late renders at once");
	let stats = limiter.stats();
	assert.equal(stats.late, 1);
	assert.equal(stats.dropped, 3, "intervals 11, 12 and 13 never rendered");
	assert.equal(limiter.shouldRender(1000 + 15 * 1000 / 60), true, "pacing resumes on the next vsync");
	limiter.shouldRender(5000);
	stats = limiter.stats();
	assert.equal(stats.stalls, 1);
	assert.equal(stats.dropped, 3);
	assert.equal(limiter.lastIntervalMs, null, "a stall interval is not a frame-time sample");
});

test("limiter fails open on bad timestamps and pauses without counting", () => {
	const limiter = createFrameLimiter({ refreshHz: 60, capFps: 30 });
	assert.equal(limiter.shouldRender(NaN), true);
	limiter.setPaused(true);
	assert.equal(limiter.shouldRender(1000), false);
	limiter.setPaused(false);
	assert.equal(limiter.shouldRender(9000), true, "the first frame after a pause renders immediately");
	assert.equal(limiter.stats().stalls, 0);
});

// ---------------------------------------------------------------------------
// Auto and the joint rule with the render-scale controller (scripted signals)
// ---------------------------------------------------------------------------

test("Auto starts from the tier target, bounded by refresh and the phone ceiling", () => {
	const start = (formFactor, tierTargetFps, hz) => {
		const policy = createFrameRatePolicy({ formFactor, tierTargetFps });
		drive(policy, vsyncStream({ hz, seconds: 2, seed: hz }));
		return policy.state();
	};
	assert.equal(start("mobile", 30, 60).capFps, 30, "iPhone 11 class: 30 on 60 Hz");
	assert.equal(start("mobile", 30, 120).capFps, 30, "120 Hz Android: 30");
	assert.deepEqual([...start("mobile", 30, 120).autoLadder], [60, 40, 30], "phones never Auto-climb past 60");
	assert.equal(start("mobile", 30, 144).capFps, 36);
	assert.equal(start("desktop", 60, 60).capFps, 60);
	assert.equal(start("desktop", 60, 144).capFps, 72);
	assert.equal(start("desktop", 60, 240).capFps, 60);
	assert.equal(start("desktop", 30, 144).capFps, 36, "desktop Low/Medium keep their 30 fps tier target");
	assert.deepEqual([...start("desktop", 60, 144).autoLadder], [144, 72, 48, 36]);
});

test("Auto steps the cap down only after the scale sits at min with a sustained deficit", () => {
	const frames = vsyncStream({ hz: 120, seconds: 40, seed: 21 });
	// GPU-bound deficit while the scale is still above min: resolution is still adapting; the cap must hold.
	let policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMin: false, atMax: false, deficitMs: 0, bound: "gpu", surplusMs: 0, missRatio: 0.5, elapsed }));
	assert.equal(policy.state().capFps, 60);
	assert.equal(policy.state().lastChange, null);

	// Same deficit but the scale is at min: after 3 s of deficit the cap drops one rung (60 -> 40 on 120 Hz).
	policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	let firstDropAt = null;
	holdSignal(policy, frames, (frame, elapsed) => {
		if (firstDropAt === null && policy.targetFps !== 60) firstDropAt = frame.t;
		return { atMin: true, atMax: false, deficitMs: elapsed, bound: "gpu" };
	});
	const state = policy.state();
	assert.equal(state.stepDowns >= 1, true);
	assert.ok(firstDropAt !== null && firstDropAt - frames[0].t >= 3000, "never before the dwell and 3 s of deficit");
	assert.ok([40, 30].includes(state.capFps), `stepped to ${state.capFps}`);
	assert.equal(state.lastChange.reason, "deficit");
});

test("a CPU-bound deficit (resolution cannot help) also steps down, scale not at min", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	holdSignal(policy, vsyncStream({ hz: 120, seconds: 20, seed: 22 }), (frame, elapsed, p) => p.targetFps === 60 ? { atMin: false, atMax: true, deficitMs: elapsed, bound: "cpu" } : { atMax: true });
	assert.equal(policy.state().capFps, 40, "one rung: 40 fps fits the CPU cost");
	assert.equal(policy.state().lastChange.reason, "deficit");
});

test("Auto probes up only at max scale with sustained surplus; an above-base probe reverts when the scale leaves max", () => {
	const frames = vsyncStream({ hz: 144, seconds: 60, seed: 23 });
	// Surplus but not at max: no probe.
	let policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: false, atMin: false, surplusMs: elapsed }));
	assert.equal(policy.state().capFps, 72);
	assert.equal(policy.state().lastChange.reason, "refresh-changed", "only the 60 -> 72 remap after detecting 144 Hz");

	// At max with surplus: probe 72 -> 144 after 8 s; the scale then leaves max -> revert, delay doubles.
	policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	let probedAt = null;
	holdSignal(policy, frames, (frame, elapsed) => {
		if (policy.targetFps === 144) {
			if (probedAt === null) probedAt = frame.t;
			return { atMax: frame.t - probedAt < 1500, surplusMs: 0 };
		}
		return { atMax: true, surplusMs: elapsed };
	});
	const state = policy.state();
	assert.ok(probedAt !== null, "a probe happened");
	assert.equal(state.capFps, 72, "reverted to the base");
	assert.ok(state.failedProbes >= 1);
	assert.ok(state.probeDelayMs >= 16000, `delay doubled to ${state.probeDelayMs}`);
	assert.ok(state.lastChange.reason === "probe-failed" || state.lastChange.reason === "probe");
});

test("a probe that keeps the scale at max is credited after the fail window and halves the back-off", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	holdSignal(policy, vsyncStream({ hz: 144, seconds: 30, seed: 24 }), (frame, elapsed) => ({ atMax: true, surplusMs: elapsed }));
	assert.equal(policy.state().capFps, 144);
	assert.equal(policy.state().successfulProbes, 0, "not credited inside the 60 s fail window");
	holdSignal(policy, vsyncStream({ hz: 144, seconds: 50, seed: 26, start: 31000 }), (frame, elapsed) => ({ atMax: true, surplusMs: elapsed }));
	const state = policy.state();
	assert.equal(state.capFps, 144);
	assert.equal(state.successfulProbes, 1);
	assert.equal(state.failedProbes, 0);
	assert.equal(state.probeDelayMs, 8000);
});

test("phones never probe above their base blind, but do with measured headroom", () => {
	const frames = vsyncStream({ hz: 120, seconds: 90, seed: 25 });
	let policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: true, surplusMs: elapsed, headroomKnown: false }));
	assert.equal(policy.state().capFps, 30, "Safari WebGPU hides overload: no blind probes on phones");

	policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: true, surplusMs: elapsed, headroomKnown: true, loadRatio: 0.3 }));
	assert.equal(policy.state().capFps, 60, "30 -> 40 -> 60 with GPU headroom; never past the phone ceiling");

	policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: true, surplusMs: elapsed, headroomKnown: true, loadRatio: 0.7 }));
	assert.equal(policy.state().capFps, 30, "predicted 0.93 at 40 fps exceeds 0.85: no probe");
});

test("without a scale controller, cheap CPU frames never authorize a phone probe above base; desktop may probe", () => {
	for (const [formFactor, expected] of [["mobile", 30], ["desktop", 120]]) {
		const policy = createFrameRatePolicy({ formFactor, tierTargetFps: formFactor === "mobile" ? 30 : 60 });
		drive(policy, vsyncStream({ hz: 120, seconds: 90, seed: 45 }), () => policy.recordWork(2));
		const state = policy.state();
		assert.equal(state.scaleSignal, "limiter");
		assert.equal(state.capFps, expected, `${formFactor}: CPU-only headroom (2 ms of work) ${formFactor === "mobile" ? "cannot" : "may"} lift the cap`);
	}
	// A heavy CPU frame vetoes even a desktop blind probe: 9 ms of work at 60 fps predicts 1.08 at 120.
	const heavy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	drive(heavy, vsyncStream({ hz: 120, seconds: 60, seed: 46 }), () => heavy.recordWork(9));
	assert.equal(heavy.state().capFps, 60);
});

test("no oscillation: noisy signals below the thresholds never move the cap", () => {
	const random = rng(31);
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	let deficit = 0;
	let surplus = 0;
	let atMax = true;
	drive(policy, vsyncStream({ hz: 120, seconds: 600, seed: 32 }), frame => {
		// Every ~0.5-2.5 s the controller's view flips; deficits and surpluses never last long enough.
		if (random() < 1 / 90) atMax = !atMax;
		deficit = random() < 0.02 ? 0 : deficit + 1000 / 60;
		surplus = atMax && random() > 0.01 ? surplus + 1000 / 60 : 0;
		policy.observeScale(signal(policy, { atMin: !atMax && random() < 0.5, atMax, deficitMs: Math.min(deficit, 2900), surplusMs: Math.min(surplus, 7900) }), frame.t);
	});
	assert.equal(policy.state().lastChange, null, "10 minutes of noise: zero cap changes");
});

test("no oscillation at a capacity boundary: failed probes back off exponentially", () => {
	// Desktop 60 Hz, base 60. The device holds 30 at max scale but 60 only at min scale with a deficit.
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	const changes = [];
	let sinceCap = null;
	let cap = null;
	holdSignal(policy, vsyncStream({ hz: 60, seconds: 1800, jitter: 0.3, seed: 33 }), (frame, elapsed) => {
		if (cap !== policy.targetFps) { if (cap !== null) changes.push({ t: frame.t, to: policy.targetFps }); cap = policy.targetFps; sinceCap = frame.t; }
		const held = frame.t - sinceCap;
		if (cap === 60) return held < 4000 ? { atMax: false, atMin: false } : { atMin: true, atMax: false, deficitMs: held - 4000 };
		return { atMax: true, surplusMs: elapsed };
	});
	const state = policy.state();
	assert.equal(state.capFps === 30 || state.capFps === 60, true);
	assert.ok(changes.length <= 14, `${changes.length} changes in 30 minutes`);
	const probes = changes.filter(change => change.to === 60).map(change => change.t);
	for (let k = 2; k < probes.length; k++) assert.ok(probes[k] - probes[k - 1] >= probes[k - 1] - probes[k - 2] - 1, "probe gaps never shrink");
	assert.ok(state.probeDelayMs >= 64000, `back-off reached ${state.probeDelayMs}`);
});

test("two sustained step-downs within 10 minutes flag thermal throttling and hold probes", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, desktopMaxProbeUpAfterMs: 120000 });
	// 120 Hz desktop: probe to 120 succeeds, then after 70 s the device heats and 120 needs min scale; later 60 too.
	let heated = 0;
	holdSignal(policy, vsyncStream({ hz: 120, seconds: 400, seed: 34 }), (frame, elapsed, p) => {
		const t = frame.t - 1000;
		if (t > 90000 && p.targetFps === 120 && heated === 0) heated = 1;
		if (t > 170000 && p.targetFps === 60 && heated === 1) heated = 2;
		if ((heated === 1 && p.targetFps === 120) || (heated === 2 && p.targetFps === 60)) return { atMin: true, atMax: false, deficitMs: elapsed };
		return { atMax: true, surplusMs: heated ? 0 : elapsed };
	});
	const state = policy.state();
	assert.equal(state.stepDowns, 2);
	assert.equal(state.thermalSuspected, true);
	assert.equal(state.capFps, 40);
	assert.equal(state.probeDelayMs, 120000);
});

test("above the base, Auto yields a rung as soon as holding it would cost resolution", () => {
	// Probe 72 -> 144 succeeds; 90 s later the scene gets heavier and the scale controller starts lowering resolution.
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	let heavierAt = null;
	holdSignal(policy, vsyncStream({ hz: 144, seconds: 120, seed: 37 }), (frame, elapsed, p) => {
		if (p.targetFps === 144 && frame.t > 91000) {
			heavierAt ??= frame.t;
			return { atMax: false, atMin: false };
		}
		return { atMax: true, surplusMs: p.targetFps === 144 ? elapsed : (heavierAt === null ? elapsed : 0) };
	});
	const state = policy.state();
	assert.equal(state.capFps, 72, "back to the base instead of 144 fps at a lower resolution");
	assert.equal(state.lastChange.reason, "yield-to-resolution");
	assert.ok(state.lastChange.at - heavierAt >= 1500 && state.lastChange.at - heavierAt < 2500, `yielded ${state.lastChange.at - heavierAt} ms after the scale left max`);
	assert.equal(state.successfulProbes, 1, "the probe had survived its fail window, so the yield is not a failure");
	assert.equal(state.failedProbes, 0);
});

test("a probe dropped by hiding is never credited later", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	const frames = vsyncStream({ hz: 144, seconds: 12, seed: 38 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: true, surplusMs: elapsed }));
	assert.equal(policy.state().capFps, 144);
	policy.notifyVisibility(true, 13100);
	policy.notifyVisibility(false, 14000);
	holdSignal(policy, vsyncStream({ hz: 144, seconds: 80, seed: 39, start: 14000 }), () => ({ atMax: true, surplusMs: 0 }));
	const state = policy.state();
	assert.equal(state.successfulProbes, 0);
	assert.equal(state.failedProbes, 0);
	assert.equal(state.capFps, 72);
});

test("onChange reports refresh, cap and visibility changes, and a throwing listener cannot stop pacing", () => {
	const changes = [];
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, onChange: change => { changes.push(change); throw new Error("listener bug"); } });
	const rendered = drive(policy, vsyncStream({ hz: 144, seconds: 2, seed: 40 }));
	policy.setSetting(30, 3100);
	policy.notifyVisibility(true, 3200);
	policy.notifyVisibility(false, 3300);
	assert.deepEqual(changes.map(change => [change.reason, change.previousCapFps, change.capFps, change.refreshHz]), [
		["refresh-changed", 60, 72, 144],
		["setting-changed", 72, 36, 144],
		["hidden", 36, 36, 144],
		["visible", 36, 36, 144],
	]);
	assert.ok(Object.isFrozen(changes[0]));
	assert.ok(rendered.length > 100, "frames kept rendering despite the listener throwing");
});

test("a tier's Auto ceiling bounds probes; setTier restarts Auto from the new base", () => {
	const frames = vsyncStream({ hz: 144, seconds: 60, seed: 44 });
	// Desktop Low/Medium: base 30, Auto may climb to 60 at most -> on 144 Hz the rungs are 48 and 36.
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 30, autoCeilingFps: 60 });
	holdSignal(policy, frames.slice(0, 144 * 40), (frame, elapsed) => ({ atMax: true, surplusMs: elapsed }));
	let state = policy.state();
	assert.deepEqual([...state.autoLadder], [48, 36]);
	assert.equal(state.autoBaseCapFps, 36);
	assert.equal(state.capFps, 48, "probed 36 -> 48 and stopped at the tier ceiling");
	assert.equal(state.tierCeilingFps, 60);
	// The player picks High: base 60 (72 on 144 Hz), no tier ceiling.
	assert.equal(policy.setTier({ targetFps: 60, autoCeilingFps: 0 }, frames[144 * 40].t), true);
	state = policy.state();
	assert.equal(state.capFps, 72);
	assert.deepEqual([...state.autoLadder], [144, 72, 48, 36]);
	assert.equal(state.lastChange.reason, "tier-changed");
	assert.equal(policy.setTier({ targetFps: 60, autoCeilingFps: 0 }), false, "no change, no restart");
});

test("event names are stable strings for the settings UI and the renderer", async () => {
	const { FRAME_RATE_SETTING_EVENT, FRAME_RATE_STATE_EVENT, FRAME_RATE_STORAGE_KEY } = await import("./frame-rate-policy.mjs");
	assert.equal(FRAME_RATE_SETTING_EVENT, "aetherfield:frame-rate-setting-change");
	assert.equal(FRAME_RATE_STATE_EVENT, "aetherfield:frame-rate-state");
	assert.equal(FRAME_RATE_STORAGE_KEY, "aetherfield_frame_rate_v1");
});

/** Drives a phone that reports CPU work each rendered frame, logging cap changes. */
function phoneRun(policy, frames, { costMs, cpuMs }) {
	const changes = [];
	let cap = policy.targetFps;
	driveWithCost(policy, frames, t => costMs(t - 1000), frame => {
		policy.recordWork(cpuMs(frame.t - 1000));
		if (policy.targetFps !== cap) {
			changes.push({ s: Math.round((frame.t - 1000) / 100) / 10, to: policy.targetFps, reason: policy.state().lastChange.reason });
			cap = policy.targetFps;
		}
	});
	return changes;
}

test("iPhone 11 Smooth 60 opt-in: starts at 30, earns 60 after 60 s of cheap frames, falls back after 5 s over 18 ms, then waits twice as long", () => {
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, setting: 60 });
	assert.equal(policy.targetFps, 30, "the opt-in starts at the safe base");
	// GPU cost 9 ms, except a heavy scene (20 ms per frame: misses every 60 Hz vsync) from 100 s to 200 s. CPU stays 9 ms.
	const changes = phoneRun(policy, vsyncStream({ hz: 60, seconds: 300, jitter: 0.4, seed: 81 }), {
		costMs: t => (t > 100000 && t < 200000 ? 20 : 9),
		cpuMs: () => 9,
	});
	assert.deepEqual(changes.map(change => [change.to, change.reason]), [[60, "opt-in-promote"], [30, "opt-in-fallback"], [60, "opt-in-promote"]]);
	assert.ok(changes[0].s >= 60 && changes[0].s < 64, `promoted at ${changes[0].s} s`);
	assert.ok(changes[1].s >= 105 && changes[1].s < 108, `fell back at ${changes[1].s} s (5 s over 18 ms)`);
	assert.ok(changes[2].s - changes[1].s >= 120, `second promotion waited ${changes[2].s - changes[1].s} s (doubled)`);
	const state = policy.state();
	assert.equal(state.optIn.promoted, true);
	assert.equal(state.optIn.demotions, 1);
	assert.equal(state.thermalSuspected, false, "a 44 s hold is not a thermal pattern");
});

test("a CPU-heavy phone never earns Smooth 60", () => {
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, setting: 60 });
	const changes = phoneRun(policy, vsyncStream({ hz: 60, seconds: 180, seed: 82 }), { costMs: () => 15, cpuMs: () => 15 });
	assert.deepEqual(changes, [], "CPU p95 15 ms is above the 14 ms gate");
	assert.equal(policy.state().optIn.promoted, false);
});

test("slow A13-style thermal decline steps Smooth 60 down once and holds, without oscillating", () => {
	// GPU cost climbs from 10 ms to 22 ms over 10 minutes, then keeps climbing slowly: the device keeps heating.
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, setting: 60 });
	const changes = phoneRun(policy, vsyncStream({ hz: 60, seconds: 900, jitter: 0.4, seed: 83 }), {
		costMs: t => 10 + 12 * t / 600000,
		cpuMs: () => 8,
	});
	assert.deepEqual(changes.map(change => [change.to, change.reason]), [[60, "opt-in-promote"], [30, "opt-in-fallback"]], JSON.stringify(changes));
	assert.ok(changes[1].s > 330 && changes[1].s < 360, `fell back once misses began (${changes[1].s} s)`);
	assert.equal(policy.state().thermalSuspected, true, "held 60 for minutes, then could not: thermal");
});

test("Auto on a 120 Hz phone: a slow thermal decline steps down once, then holds for 10 minutes", () => {
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30 });
	const changes = [];
	let cap = policy.targetFps;
	holdSignal(policy, vsyncStream({ hz: 120, seconds: 1150, seed: 84 }), (frame, elapsed, p) => {
		if (p.targetFps !== cap) { changes.push({ s: Math.round((frame.t - 1000) / 1000), to: p.targetFps, reason: p.state().lastChange.reason }); cap = p.targetFps; }
		const t = frame.t - 1000;
		const hot = t > 300000; // after 5 minutes, 60 needs min scale and still misses
		if (hot && p.targetFps === 60) return { atMin: true, atMax: false, deficitMs: elapsed };
		return { atMax: true, surplusMs: elapsed, headroomKnown: true, loadRatio: hot ? 0.45 : 0.3 };
	});
	const downs = changes.filter(change => change.to < 60 && change.reason !== "probe");
	assert.equal(downs.length, 1, JSON.stringify(changes));
	assert.equal(downs[0].reason, "deficit");
	const after = changes.filter(change => change.s > downs[0].s);
	assert.ok(after.every(change => change.s - downs[0].s >= 600 + 300), `no probe inside the 10-minute hold plus a fresh 5-minute wait: ${JSON.stringify(after)}`);
	assert.equal(policy.state().thermalSuspected, false, "the hold has expired by the end of the run");
});

test("phones rate-limit cap changes: at most one policy change per 10 s, even under a flapping signal", () => {
	const policy = createFrameRatePolicy({ formFactor: "mobile", tierTargetFps: 30, mobileProbeUpAfterMs: 0, minDwellMs: 0 });
	const times = [];
	let cap = policy.targetFps;
	let flip = false;
	drive(policy, vsyncStream({ hz: 120, seconds: 120, seed: 85 }), frame => {
		if (policy.targetFps !== cap) { times.push(frame.t); cap = policy.targetFps; }
		flip = !flip;
		// Every frame alternates "deficit at min" and "surplus at max with headroom": the worst case for churn.
		policy.observeScale(flip ? signal(policy, { atMin: true, atMax: false, deficitMs: 60000 }) : signal(policy, { atMax: true, surplusMs: 60000, headroomKnown: true, loadRatio: 0.2 }), frame.t);
	});
	assert.ok(times.length >= 2, `the signal did move the cap (${times.length} changes)`);
	for (let k = 1; k < times.length; k++) assert.ok(times[k] - times[k - 1] >= 10000 - 1, `changes ${times[k] - times[k - 1]} ms apart`);
});

test("low battery keeps Auto at its base", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	policy.setPowerHints({ lowBattery: true, charging: false });
	holdSignal(policy, vsyncStream({ hz: 144, seconds: 40, seed: 35 }), (frame, elapsed) => ({ atMax: true, surplusMs: elapsed, headroomKnown: true, loadRatio: 0.2 }));
	assert.equal(policy.state().capFps, 72);
	assert.equal(policy.state().powerLimited, true);
});

test("desktop fixed settings ignore Auto signals; changing the setting restarts from the right cap", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, setting: 120 });
	const frames = vsyncStream({ hz: 144, seconds: 20, seed: 36 });
	holdSignal(policy, frames.slice(0, 1440), (frame, elapsed) => ({ atMin: true, atMax: false, deficitMs: elapsed }));
	assert.equal(policy.state().capFps, 144, "120 on 144 Hz is 144, and load never lowers a fixed cap");
	policy.setSetting("30", frames[1440].t);
	assert.equal(policy.state().capFps, 36);
	policy.setSetting("auto", frames[1441].t);
	assert.equal(policy.state().capFps, 72);
	const options = describeFrameRateOptions(policy.state());
	assert.deepEqual(options.map(option => [option.value, option.capFps, option.exact]), [["auto", 72, true], [30, 36, false], [60, 72, false], [90, 72, false], [120, 144, false], ["max", 144, true]]);
	assert.equal(options.find(option => option.selected).value, "auto");
});

// ---------------------------------------------------------------------------
// Visibility
// ---------------------------------------------------------------------------

test("hidden pauses rendering; visible re-detects (here 60 -> 120 Hz) and freezes Auto until locked", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	holdSignal(policy, vsyncStream({ hz: 60, seconds: 4, seed: 41 }), () => ({ atMax: true }));
	assert.equal(policy.state().refreshHz, 60);
	policy.notifyVisibility(true, 5000);
	assert.equal(policy.paused, true);
	assert.equal(policy.frame(5010), false, "no rendering while hidden");
	assert.equal(policy.frame(5020), false);
	policy.notifyVisibility(false, 60000);
	assert.equal(policy.state().refreshPhase, "detecting");
	const back = vsyncStream({ hz: 120, seconds: 3, seed: 42, start: 60000 });
	let firstRender = null;
	let lockedAt = null;
	for (const frame of back) {
		const rendered = policy.frame(frame.t);
		if (rendered && firstRender === null) firstRender = frame.t;
		if (lockedAt === null && policy.state().refreshPhase === "locked") lockedAt = frame.t;
		policy.observeScale(signal(policy, { atMin: true, deficitMs: 60000 }), frame.t);
	}
	assert.equal(firstRender, back[0].t, "the first frame back renders at once");
	assert.ok(lockedAt !== null && lockedAt - 60000 < 500);
	assert.equal(policy.state().refreshHz, 120);
	assert.equal(policy.state().capFps, 60, "Auto held its cap: the dwell restarted at the return");
});

test("a probe interrupted by hiding reverts without counting as a failure", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	const frames = vsyncStream({ hz: 144, seconds: 12, seed: 43 });
	holdSignal(policy, frames, (frame, elapsed) => ({ atMax: true, surplusMs: elapsed }));
	assert.equal(policy.state().capFps, 144);
	assert.ok(policy.state().probation !== null, "still on probation");
	policy.notifyVisibility(true, frames.at(-1).t + 10);
	const state = policy.state();
	assert.equal(state.capFps, 72);
	assert.equal(state.failedProbes, 0);
	assert.equal(state.probation, null);
});

// ---------------------------------------------------------------------------
// Babylon 9.27.1 integration through engine.customAnimationFrameRequester
// ---------------------------------------------------------------------------

function babylonHarness(policy) {
	const engine = new NullEngine({ renderWidth: 8, renderHeight: 8 });
	let nextId = 0;
	const queue = new Map();
	let cancelled = 0;
	const requester = createPacedFrameRequester({
		policy,
		requestFrame: callback => { const id = ++nextId; queue.set(id, callback); return id; },
		cancelFrame: id => { if (queue.delete(id)) cancelled++; },
		now: () => 0,
	});
	// Babylon destructures these methods, so they must not depend on `this`.
	const { requestAnimationFrame, cancelAnimationFrame } = requester;
	engine.customAnimationFrameRequester = { requestAnimationFrame, cancelAnimationFrame };
	const begins = [];
	let current = null;
	engine.onBeginFrameObservable.add(() => begins.push(current));
	const renderLoop = () => {};
	engine.runRenderLoop(renderLoop);
	return {
		engine,
		begins,
		tick(frame) {
			current = frame;
			assert.equal(queue.size, 1, "exactly one native request is outstanding");
			const [id, callback] = queue.entries().next().value;
			queue.delete(id);
			callback(frame.t);
		},
		close() {
			engine.stopRenderLoop(renderLoop);
			assert.equal(queue.size, 0, "stopRenderLoop cancels the outstanding native request");
			engine.dispose();
			return cancelled;
		},
	};
}

test("paced requester gates Babylon's beginFrame, so only rendered frames advance the engine", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, setting: 60 });
	const harness = babylonHarness(policy);
	const frames = vsyncStream({ hz: 120, seconds: 20, jitter: 0.5, seed: 51 });
	for (const frame of frames) harness.tick(frame);
	assert.equal(policy.state().refreshHz, 120);
	assert.equal(policy.state().capFps, 60);
	const settled = harness.begins.filter(frame => frame.i > 240);
	assert.deepEqual([...vsyncGaps(settled).keys()], [2], "every engine frame after detection is 2 vsyncs apart");
	assert.equal(harness.engine.frameId, harness.begins.length, "skipped vsyncs never reach beginFrame/endFrame");
	assert.ok(Math.abs(harness.begins.length - 20 * 60) < 30);
	assert.equal(harness.close(), 1);
});

test("requester cancel and dispose release the native request", () => {
	const policy = createFrameRatePolicy({ setting: "max" });
	const outstanding = new Map();
	let id = 0;
	const requester = createPacedFrameRequester({ policy, requestFrame: callback => { outstanding.set(++id, callback); return id; }, cancelFrame: handle => outstanding.delete(handle) });
	const calls = [];
	const first = requester.requestAnimationFrame(t => calls.push(t));
	assert.equal(outstanding.size, 1);
	requester.cancelAnimationFrame(first + 1);
	assert.equal(outstanding.size, 1, "a stale id does not cancel the current request");
	requester.cancelAnimationFrame(first);
	assert.equal(outstanding.size, 0);
	requester.requestAnimationFrame(t => calls.push(t));
	const [handle, callback] = outstanding.entries().next().value;
	outstanding.delete(handle);
	callback(1000);
	assert.deepEqual(calls, [1000]);
	requester.requestAnimationFrame(t => calls.push(t));
	requester.dispose();
	assert.equal(outstanding.size, 0);
	assert.throws(() => createPacedFrameRequester({ policy, requestFrame: null, cancelFrame: () => {} }), TypeError);
});

// ---------------------------------------------------------------------------
// End to end with the real render-scale controller
// ---------------------------------------------------------------------------

test("Energy Saver / Low Power halving rAF mid-session does not cost resolution", () => {
	// Desktop laptop, Auto 60 on 60 Hz, light scene (5 ms GPU). At 20 s the browser throttles rAF to 30 Hz.
	for (const setting of ["auto", 60]) {
		const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60, setting });
		const scale = createRenderScaleController();
		let lowestScale = 1;
		let lockedAt = null;
		const frames = [...vsyncStream({ hz: 60, seconds: 20, seed: 71 }), ...vsyncStream({ hz: 30, seconds: 30, seed: 72, start: 21000 })];
		drive(policy, frames, frame => {
			const frameMs = policy.lastFrameIntervalMs;
			if (frameMs !== null) scale.update({ frameMs, gpuMs: 5, targetFps: policy.targetFps });
			policy.observeScale(scale.state(), frame.t);
			lowestScale = Math.min(lowestScale, scale.scale);
			if (lockedAt === null && frame.t > 21000 && policy.state().throttled) lockedAt = frame.t - 21000;
		});
		assert.ok(lockedAt !== null && lockedAt < 6000, `${setting}: 30 Hz ceiling confirmed after ${lockedAt} ms`);
		assert.equal(policy.state().capFps, 30);
		assert.equal(lowestScale, 1, `${setting}: the scale never dropped (lowest ${lowestScale})`);
	}
});

test("end to end without a GPU timer (WebGPU today): capped frames still let a light desktop probe up", () => {
	// The controller cannot see headroom when frames are capped and gpuMs is null; its loadRatio (~1) must not veto.
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	const scale = createRenderScaleController();
	const cost = () => 3; // a light scene: 3 ms per frame at any cap
	driveWithCost(policy, vsyncStream({ hz: 144, seconds: 60, jitter: 0.3, seed: 73 }), cost, frame => {
		const frameMs = policy.lastFrameIntervalMs;
		if (frameMs !== null) scale.update({ frameMs, gpuMs: null, targetFps: policy.targetFps });
		policy.observeScale(scale.state(), frame.t);
	});
	const state = policy.state();
	assert.equal(scale.state().headroomKnown, false);
	assert.equal(state.capFps, 144, `a blind desktop probe 72 -> 144 succeeded (cap ${state.capFps})`);
	assert.equal(state.failedProbes, 0);
});

test("joint rule end to end: the real scale controller adapts resolution first, then Auto lowers the cap", () => {
	const policy = createFrameRatePolicy({ formFactor: "desktop", tierTargetFps: 60 });
	const scale = createRenderScaleController();
	const log = [];
	// GPU cost model: 12 ms fixed + 24 ms x scale^2. 60 fps needs <= 16.7 ms: even min scale (0.5) costs 18 ms.
	const gpuMs = () => 12 + 24 * scale.scale ** 2;
	driveWithCost(policy, vsyncStream({ hz: 60, seconds: 120, jitter: 0.3, seed: 61 }), gpuMs, frame => {
		const frameMs = policy.lastFrameIntervalMs;
		if (frameMs !== null) scale.update({ frameMs, gpuMs: gpuMs(), targetFps: policy.targetFps });
		const state = scale.state();
		policy.observeScale(state, frame.t);
		log.push({ t: frame.t, cap: policy.targetFps, scale: state.scale, atMin: state.atMin, deficitMs: state.deficitMs });
	});
	const firstDrop = log.findIndex(entry => entry.cap !== 60);
	assert.ok(firstDrop > 0, "the cap dropped");
	const before = log[firstDrop - 1];
	assert.equal(before.atMin, true, "the scale was at its minimum when the cap dropped");
	assert.ok(before.deficitMs >= 3000, `with ${before.deficitMs} ms of deficit`);
	assert.ok(log.slice(0, firstDrop).some(entry => entry.scale < 1), "resolution moved first");
	assert.equal(policy.state().capFps, 30);
	const after = log.slice(firstDrop).filter(entry => entry.cap === 30).at(-1);
	assert.ok(after.scale > 0.5, `at 30 fps the scale climbed back to ${after.scale}`);
	assert.ok(log.slice(firstDrop).every(entry => entry.cap === 30 || entry.cap === 60), "only ladder rungs");
});
