import test from "node:test";
import assert from "node:assert/strict";
import {
	RENDER_SCALE_DEFAULTS, createRenderScaleController, normalizeRenderScalingSettings, parseRenderScalingQuery,
	scaleFactorFromScale, scaleFromScaleFactor, scaledRenderSize,
} from "./render-scale-controller.mjs";

/** Deterministic PRNG so noise tests are reproducible. */
function mulberry32(seed) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/** Feeds rendered frames for `seconds` of frame time; `sample(scale, index)` returns { frameMs, gpuMs? }. */
function simulate(controller, { seconds, targetFps = 60, sample, startMs = 0 }) {
	const changes = [];
	let timeMs = startMs, index = 0;
	while (timeMs < startMs + seconds * 1000) {
		const value = sample(controller.scale, index, timeMs);
		const result = controller.update({ ...value, targetFps });
		if (result !== null) changes.push({ index, timeMs, scale: result, reason: controller.state().lastReason });
		timeMs += value.frameMs;
		index++;
	}
	return { changes, endMs: timeMs };
}

function reversals(changes, initial) {
	let previous = initial, direction = 0, count = 0;
	for (const change of changes) {
		const next = Math.sign(change.scale - previous);
		if (direction !== 0 && next !== 0 && next !== direction) count++;
		if (next !== 0) direction = next;
		previous = change.scale;
	}
	return count;
}

const T60 = 1000 / 60;

test("steady GPU headroom climbs slowly, one small step per dwell, to max", () => {
	const controller = createRenderScaleController({ minScale: 0.5, maxScale: 1, initialScale: 0.5 });
	const { changes } = simulate(controller, { seconds: 50, sample: () => ({ frameMs: T60, gpuMs: 4 }) });
	assert.equal(controller.scale, 1);
	assert.ok(changes.length === 10, `expected ten 0.05 steps, got ${changes.length}`);
	let previous = 0.5;
	for (const change of changes) {
		assert.ok(Math.abs(change.scale - previous - 0.05) < 1e-9, `step ${previous} -> ${change.scale}`);
		assert.equal(change.reason, "gpu-headroom");
		previous = change.scale;
	}
	assert.ok(changes[0].timeMs >= RENDER_SCALE_DEFAULTS.climbDelayMs, "the first climb waits for the minimum dwell");
	for (let i = 1; i < changes.length; i++) {
		assert.ok(changes[i].timeMs - changes[i - 1].timeMs >= RENDER_SCALE_DEFAULTS.climbDelayMs, "climbs are spaced by the dwell (each one reallocates the target)");
	}
	const state = controller.state();
	assert.equal(state.atMax, true);
	assert.equal(state.signal, "gpu");
	assert.ok(state.loadRatio < 0.3 && state.headroomKnown);
});

test("sustained slow frames drop quickly to min and report the deficit", () => {
	const controller = createRenderScaleController({ initialScale: 1 });
	const { changes } = simulate(controller, { seconds: 10, sample: () => ({ frameMs: 40 }) });
	assert.equal(controller.scale, RENDER_SCALE_DEFAULTS.minScale);
	assert.deepEqual(changes.map(change => change.scale), [0.8, 0.6, 0.5]);
	assert.ok(changes.at(-1).timeMs < 4500, `reached min at ${changes.at(-1).timeMs} ms`);
	assert.ok(changes.every(change => change.reason === "frames-missed"));
	const state = controller.state();
	assert.equal(state.atMin, true);
	assert.ok(state.deficitMs > 4000, "a sustained deficit at min is exposed for the frame-rate policy");
	assert.ok(state.atMinMs > 4000);
	assert.equal(state.surplusMs, 0);
	const gpu = createRenderScaleController({ initialScale: 1 });
	simulate(gpu, { seconds: 8, sample: () => ({ frameMs: 20, gpuMs: 19 }) });
	assert.equal(gpu.scale, 0.5);
	assert.equal(gpu.state().bound, "gpu");
});

test("GPU-time noise around a stable operating point does not oscillate", () => {
	const random = mulberry32(1993);
	const controller = createRenderScaleController({ initialScale: 1 });
	// Fixed cost (shadows, passes at output size) plus a share that scales with pixel count.
	const sample = scale => {
		const gpuMs = T60 * (0.2 + 0.75 * scale * scale) * (1 + (random() - 0.5) * 0.3);
		return { gpuMs, frameMs: gpuMs > T60 ? Math.ceil(gpuMs / T60) * T60 : T60 };
	};
	const { changes } = simulate(controller, { seconds: 600, sample });
	assert.ok(changes.length <= 3, `changes: ${JSON.stringify(changes.map(change => change.scale))}`);
	assert.ok(reversals(changes, 1) <= 1, "no up/down oscillation");
	assert.ok(controller.scale >= 0.8 && controller.scale <= 0.95, `settled at ${controller.scale}`);
});

test("isolated missed frames and hitches without GPU time never trigger drops", () => {
	const random = mulberry32(42);
	const controller = createRenderScaleController({ initialScale: 0.7 });
	const { changes } = simulate(controller, {
		seconds: 120,
		sample: (_scale, index) => ({ frameMs: index % 1500 === 700 ? 5000 : random() < 0.02 ? 2 * T60 : T60 }),
	});
	assert.ok(changes.every(change => change.scale > 0.7 - 1e-9), "no down-step from noise");
	for (let i = 1; i < changes.length; i++) {
		assert.ok(changes[i].timeMs - changes[i - 1].timeMs >= RENDER_SCALE_DEFAULTS.probeDelayMs, "probe climbs are spaced by the probe delay");
	}
	assert.ok(changes.every(change => change.reason === "probe"));
});

test("vsync-capped frames without GPU time do not climb blindly and back off after a failed probe", () => {
	const controller = createRenderScaleController({ initialScale: 0.6 });
	// Above 0.7 the device starts missing every third frame; at or below it the cap holds exactly.
	const sample = (scale, index) => ({ frameMs: scale > 0.7 + 1e-9 && index % 3 === 0 ? 2 * T60 : T60 });
	const early = simulate(controller, { seconds: 3.9, sample });
	assert.equal(early.changes.length, 0, "no climb before the probe delay while frames are capped");
	const { changes } = simulate(controller, { seconds: 120, sample, startMs: early.endMs });
	const ups = changes.filter(change => change.reason === "probe");
	const fails = changes.filter(change => change.reason === "probe-failed");
	assert.ok(ups.length >= 2 && fails.length >= 1, JSON.stringify(changes));
	assert.ok(changes.every(change => change.scale <= 0.75 + 1e-9), "never more than one step past the last good scale");
	assert.ok(fails.every(change => Math.abs(change.scale - 0.7) < 1e-9), "a failed probe reverts to the last good scale");
	const firstFail = fails[0];
	const nextProbe = ups.find(change => change.timeMs > firstFail.timeMs && change.scale > 0.7 + 1e-9);
	if (nextProbe) assert.ok(nextProbe.timeMs - firstFail.timeMs >= 2 * RENDER_SCALE_DEFAULTS.probeDelayMs, "probe delay doubles after a failure");
	assert.ok(controller.state().probeDelayMs >= 2 * RENDER_SCALE_DEFAULTS.probeDelayMs);
	assert.equal(controller.state().headroomKnown, false, "capped frames without GPU time cannot show headroom");
	const timeAbove = changes.reduce((sum, change, index) => {
		if (change.scale <= 0.7 + 1e-9) return sum;
		const end = changes[index + 1]?.timeMs ?? early.endMs + 120_000;
		return sum + end - change.timeMs;
	}, 0);
	assert.ok(timeAbove < 0.15 * 120_000, `spent ${timeAbove} ms above the failing scale`);
});

test("uncapped frame time without a GPU timer climbs only while the predicted cost fits", () => {
	const controller = createRenderScaleController({ initialScale: 0.5 });
	const cost = scale => 0.15 + 0.75 * scale * scale;
	const { changes } = simulate(controller, { seconds: 60, sample: scale => ({ frameMs: T60 * cost(scale) }) });
	assert.ok(changes.length >= 5 && changes.every(change => change.reason === "frame-headroom"));
	assert.equal(reversals(changes, 0.5), 0);
	assert.equal(controller.state().signal, "frame");
	// It stops one step before the predicted cost would leave the hysteresis band (0.75 of the interval).
	const final = controller.scale;
	assert.ok(final < 1, `climbed to ${final}`);
	assert.ok(cost(final) < 0.75 && cost(final + 0.05) >= 0.75, `stopped at ${final}`);
});

test("alternating heavy and light scenes: drops stay prompt while climb churn backs off", () => {
	const controller = createRenderScaleController({ initialScale: 1 });
	let frames = 0, missed = 0;
	// GPU cost alternates every 4 s between a heavy and a light scene; 0.1 of the interval is fixed cost.
	const sample = (scale, _index, timeMs) => {
		const heavy = Math.floor(timeMs / 4000) % 2 === 0;
		const gpuMs = T60 * ((heavy ? 1.4 : 0.5) * scale * scale + 0.1);
		frames++;
		if (gpuMs > T60) missed++;
		return { gpuMs, frameMs: gpuMs > T60 ? Math.ceil(gpuMs / T60) * T60 : T60 };
	};
	const { changes } = simulate(controller, { seconds: 600, sample });
	const early = changes.filter(change => change.timeMs < 120_000).length / 2;
	const late = changes.filter(change => change.timeMs >= 300_000).length / 5;
	assert.ok(late < early, `changes per minute decay: ${early} in the first 2 min, ${late} in the last 5 min`);
	assert.ok(changes.length <= 60, `total reallocations in 10 min: ${changes.length}`);
	assert.ok(controller.state().climbDelayMs >= 12_000, `climb delay backed off to ${controller.state().climbDelayMs} ms`);
	assert.ok(missed / frames < 0.05, `missed-frame share ${(missed / frames).toFixed(3)}`);
	// A cost cliff above 0.8 (cache or bandwidth) makes a predicted-safe climb fail: it is undone, not overshot, and backs off.
	const cliff = createRenderScaleController({ initialScale: 0.8 });
	const cliffRun = simulate(cliff, { seconds: 60, sample: scale => {
		const gpuMs = T60 * (scale > 0.8 + 1e-9 ? 1.5 * scale * scale : 0.5 * scale * scale + 0.1);
		return { gpuMs, frameMs: gpuMs > T60 ? Math.ceil(gpuMs / T60) * T60 : T60 };
	} });
	const failed = cliffRun.changes.filter(change => change.reason === "climb-failed");
	assert.ok(failed.length >= 2, JSON.stringify(cliffRun.changes));
	assert.ok(failed.every(change => Math.abs(change.scale - 0.8) < 1e-9), "each failed climb returns to the last good scale");
	assert.ok(cliffRun.changes.length <= 8, `cliff reallocations in 60 s: ${cliffRun.changes.length}`);
	for (let i = 2; i < failed.length; i++) {
		assert.ok(failed[i].timeMs - failed[i - 1].timeMs > failed[i - 1].timeMs - failed[i - 2].timeMs, "the wait grows after each failure");
	}
});

test("CPU-bound misses with an idle GPU hold the scale and expose a deficit", () => {
	const controller = createRenderScaleController({ initialScale: 0.8 });
	const { changes } = simulate(controller, { seconds: 10, sample: () => ({ frameMs: 2.2 * T60, gpuMs: 0.25 * T60 }) });
	assert.equal(changes.length, 0, "lowering resolution cannot fix a CPU bottleneck");
	const state = controller.state();
	assert.equal(state.bound, "cpu");
	assert.equal(state.lastReason, "cpu-bound");
	assert.ok(state.deficitMs > 7000);
});

test("surplus at max is exposed only for clean windows, and a target change re-evaluates the scale", () => {
	const controller = createRenderScaleController({ initialScale: 1 });
	simulate(controller, { seconds: 6, sample: () => ({ frameMs: T60, gpuMs: 5 }) });
	assert.equal(controller.scale, 1);
	assert.ok(controller.state().surplusMs >= 4000);
	assert.ok(controller.state().loadRatio < 0.35);
	// The frame-rate policy raises the cap to 120: the same 5 ms GPU load becomes 0.6 of the interval; 9 ms becomes 1.08.
	const result = simulate(controller, { seconds: 6, targetFps: 120, sample: () => ({ frameMs: 1000 / 120, gpuMs: 9 }) });
	assert.ok(result.changes.length >= 1 && controller.scale < 1, "resolution adapts first to hold the higher target");
	assert.equal(controller.state().targetFps, 120);
	assert.equal(controller.state().surplusMs, 0);
});

test("reset after a hidden tab or resize discards partial evidence and warms up again", () => {
	const controller = createRenderScaleController({ initialScale: 1 });
	simulate(controller, { seconds: 0.7, sample: () => ({ frameMs: 50 }) });
	controller.reset("hidden");
	let state = controller.state();
	assert.equal(state.warmupRemaining, RENDER_SCALE_DEFAULTS.warmupFrames);
	assert.equal(state.emaFrameMs, null);
	assert.equal(state.lastReason, "hidden");
	const { changes } = simulate(controller, { seconds: 3, sample: () => ({ frameMs: T60 }) });
	assert.equal(changes.length, 0, "slow frames from before the reset do not cause a drop");
	controller.reset("resize");
	state = controller.state();
	assert.equal(state.scale, 1, "reset keeps the scale");
	assert.equal(state.deficitMs, 0);
	assert.equal(controller.update({ frameMs: NaN, targetFps: 60 }), null);
	assert.equal(controller.update({ frameMs: -5, targetFps: 60 }), null);
	assert.equal(controller.update(null), null);
});

test("range changes clamp the scale and outputs stay on the quantum grid", () => {
	const controller = createRenderScaleController({ minScale: 1 / 2, maxScale: 1 / 1.3, initialScale: 1 });
	assert.equal(controller.scale, 0.7692);
	assert.equal(controller.setRange(0.5, 0.6), 0.6);
	assert.equal(controller.setRange(0.5, 0.6), null);
	const { changes } = simulate(controller, { seconds: 5, sample: () => ({ frameMs: 50 }) });
	assert.deepEqual(changes.map(change => change.scale), [0.5]);
	assert.equal(controller.state().atMin, true);
});

test("query settings default off, accept AMD presets and clamp every number", () => {
	assert.equal(parseRenderScalingQuery(""), null);
	assert.equal(parseRenderScalingQuery("?renderer=webgl2"), null);
	assert.equal(parseRenderScalingQuery("?fsr=off").mode, "off");
	assert.equal(parseRenderScalingQuery("?fsr=garbage").mode, "off");
	assert.equal(parseRenderScalingQuery("?fsr=").mode, "off");
	assert.deepEqual(parseRenderScalingQuery("?fsr=1.5"), { mode: "fsr", scaleFactor: 1.5, sharpnessStops: 0.2, samples: 4, adaptive: false, minScaleFactor: 1, maxScaleFactor: 2 });
	assert.equal(parseRenderScalingQuery("?fsr=quality").scaleFactor, 1.5);
	assert.equal(parseRenderScalingQuery("?fsr=ultra").scaleFactor, 1.3);
	assert.equal(parseRenderScalingQuery("?fsr=balanced").scaleFactor, 1.7);
	assert.equal(parseRenderScalingQuery("?fsr=performance").scaleFactor, 2);
	assert.equal(parseRenderScalingQuery("?fsr=9").mode, "off");
	const tuned = parseRenderScalingQuery("?fsr=1.7&sharp=0.5&auto=1&fsrMsaa=1");
	assert.equal(tuned.sharpnessStops, 0.5);
	assert.equal(tuned.adaptive, true);
	assert.equal(tuned.samples, 1);
	assert.equal(parseRenderScalingQuery("?fsr=1.3&sharp=7").sharpnessStops, 2);
	assert.equal(parseRenderScalingQuery("?fsr=1.3&sharp=").sharpnessStops, 0.2);
	assert.equal(parseRenderScalingQuery("?fsr=1.3&fsrMsaa=3").samples, 2);
	assert.equal(parseRenderScalingQuery("?fsr=1.3&auto=yes").adaptive, false);
	assert.ok(Object.isFrozen(parseRenderScalingQuery("?fsr=1.3")));
	assert.deepEqual(normalizeRenderScalingSettings({ mode: "dlss", scaleFactor: 0.2, minScaleFactor: 2.5, maxScaleFactor: 1.2 }),
		{ mode: "off", scaleFactor: 1, sharpnessStops: 0.2, samples: 4, adaptive: false, minScaleFactor: 2.5, maxScaleFactor: 2.5 });
});

test("scale and scale-factor helpers match Babylon post-process sizing", () => {
	assert.deepEqual(scaledRenderSize(1920, 1080, 1.5), { width: 1280, height: 720 });
	assert.deepEqual(scaledRenderSize(1920, 1080, 1.3), { width: 1476, height: 830 });
	assert.deepEqual(scaledRenderSize(1920, 1080, 1.7), { width: 1129, height: 635 });
	assert.deepEqual(scaledRenderSize(1920, 1080, 2), { width: 960, height: 540 });
	assert.deepEqual(scaledRenderSize(1, 1, 3), { width: 1, height: 1 });
	assert.equal(scaleFromScaleFactor(2), 0.5);
	assert.equal(scaleFactorFromScale(0.5), 2);
	assert.equal(scaleFactorFromScale(0.75), 1.3333);
	assert.equal(scaleFactorFromScale(5), 1);
});
