/**
 * Pure render-scale policy. Keep this module independent of Babylon and the
 * DOM: the renderer feeds one sample per rendered frame and applies the scale
 * only when `update()` returns a new value.
 *
 * `scale` is the linear fraction of the output resolution the 3D scene is
 * rendered at (1 = native, 0.5 = half width and half height). For FSR 1 the
 * Babylon `scaleFactor` is `1 / scale`.
 *
 * Adapted from ClearWater6.1 by SamG-Coder (MIT, see THIRD_PARTY_NOTICES.md),
 * `app.js` mobile adaptive scale: a frame-time EMA (`avg * 0.94 + ms * 0.06`)
 * evaluated in windows, dropping 0.1 when slow and climbing 0.05 when fast.
 * Changes here: thresholds are relative to the caller's target frame interval;
 * GPU time is preferred when the host has it; a missed-frame ratio replaces the
 * EMA as the down signal when frames are capped; climbing is predicted-cost
 * hysteresis, or a slow probe when headroom is unobservable; every change or
 * reset is followed by a warm-up.
 *
 * Anti-churn: every scale change reallocates the reduced scene target, and
 * repeated WebGPU resolution changes are a known Safari risk (WebKit bug
 * 312563: prior render targets accumulate). Drops stay prompt; climbs wait a
 * minimum dwell; a drop soon after a climb undoes only that climb and doubles
 * the dwell; a climb that holds through the churn window halves it again.
 */

export const RENDER_SCALE_DEFAULTS = Object.freeze({
	minScale: 0.5,
	maxScale: 1,
	stepDown: 0.1,
	stepUp: 0.05,
	quantum: 0.05,
	emaAlpha: 0.06,
	/** One decision per `windowSeconds` of rendered time, with at least `minWindowFrames` frames. */
	windowSeconds: 1,
	minWindowFrames: 8,
	/** Frames ignored after a reset or a scale change (pipeline rebuild, cache warm-up). */
	warmupFrames: 12,
	/** An interval above `missFactor` target intervals is a missed frame. */
	missFactor: 1.5,
	missRatioDown: 0.1,
	/** At or above this missed share the drop is doubled. */
	missRatioSevere: 0.5,
	missRatioClean: 0.02,
	/** GPU (or uncapped frame) cost EMA above this share of the target interval steps down. */
	costDownAt: 0.9,
	/** Climb only when the cost predicted after the step stays below this share. */
	costUpAt: 0.75,
	/** With GPU time, missed frames count as GPU-bound only above this load; below it they are CPU-bound. */
	cpuBoundBelow: 0.6,
	/** Without GPU time, a frame-interval EMA above this many target intervals steps down. */
	frameDownAt: 1.2,
	/** A frame-interval EMA at or above this share of the target means frames are capped (vsync or limiter). */
	cappedAt: 0.85,
	/** Minimum rendered time after any change or reset before a climb with measured headroom. */
	climbDelayMs: 3000,
	/** Capped without GPU time: clean time before probing one step up. */
	probeDelayMs: 4000,
	/** A drop within `churnWindowMs` of a climb doubles both delays, up to this cap; a climb that holds that long halves them. */
	maxClimbDelayMs: 32000,
	churnWindowMs: 15000,
	/** A drop within this many windows of a climb undoes only that climb (one up-step). */
	probationWindows: 2,
	/** Isolated intervals above this are hitches (tab switch, GC, shader compile) and are ignored. */
	hitchMs: 250,
	sustainedHitches: 4,
	/** Share of frames in a window that must carry a GPU time for the GPU signal to be used. */
	gpuCoverage: 0.2,
});

const SCALE_PRECISION = 10_000;
const MAX_BACKOFF = 64;

/**
 * @param {Partial<RenderScaleControllerOptions>} [options]
 * @returns {RenderScaleController}
 */
export function createRenderScaleController(options = {}) {
	const config = normalizeControllerOptions(options);
	// The start stays exact (e.g. 1 / 1.5) so a preset renders at its documented size; steps then land on the quantum grid.
	let scale = clampToRange(typeof options.initialScale === "number" && Number.isFinite(options.initialScale) ? options.initialScale : config.maxScale, config);
	let targetFps = null;
	let targetMs = null;
	let emaFrameMs = null;
	let emaGpuMs = null;
	let warmup = config.warmupFrames;
	let consecutiveHitches = 0;
	let windowFrames = 0;
	let windowMissed = 0;
	let windowGpu = 0;
	let windowElapsedMs = 0;
	let cleanMs = 0;
	let backoff = 1;
	let clockMs = 0;
	let sinceChangeMs = 0;
	let lastClimbAtMs = null;
	let lastClimbSignal = "none";
	let probation = 0;
	let atMinMs = 0;
	let atMaxMs = 0;
	let deficitMs = 0;
	let surplusMs = 0;
	let changes = 0;
	let lastMissRatio = null;
	let lastSignal = "none";
	let lastReason = "start";
	let bound = "unknown";
	const climbDelay = () => Math.min(config.maxClimbDelayMs, config.climbDelayMs * backoff);
	const probeDelay = () => Math.min(config.maxClimbDelayMs, config.probeDelayMs * backoff);

	function clearWindow() {
		windowFrames = 0;
		windowMissed = 0;
		windowGpu = 0;
		windowElapsedMs = 0;
	}

	function restart(reason) {
		clearWindow();
		emaFrameMs = null;
		emaGpuMs = null;
		warmup = config.warmupFrames;
		consecutiveHitches = 0;
		cleanMs = 0;
		sinceChangeMs = 0;
		probation = 0;
		lastClimbAtMs = null;
		deficitMs = 0;
		surplusMs = 0;
		lastReason = reason;
	}

	function setScale(next, reason) {
		if (next === scale) return null;
		scale = next;
		changes++;
		restart(reason);
		return scale;
	}

	function decide() {
		const frames = windowFrames;
		const elapsed = windowElapsedMs;
		clockMs += elapsed;
		sinceChangeMs += elapsed;
		const missRatio = windowMissed / frames;
		const gpuKnown = emaGpuMs !== null && windowGpu >= Math.max(3, Math.ceil(frames * config.gpuCoverage));
		const capped = emaFrameMs !== null && emaFrameMs >= config.cappedAt * targetMs;
		const signal = gpuKnown ? "gpu" : capped ? "probe" : "frame";
		const load = (gpuKnown ? emaGpuMs : emaFrameMs) / targetMs;
		const upNext = clampToRange(snap(scale + config.stepUp, config.quantum), config);
		const predictedLoad = load * (upNext / scale) ** 2;
		const missing = missRatio > config.missRatioDown;
		const clean = missRatio <= config.missRatioClean;
		// Half a target interval of tolerance, as for the window length.
		const dwellDone = sinceChangeMs + targetMs / 2 >= climbDelay();
		let want = 0;
		let reason = "hold";
		bound = "unknown";
		if (signal === "gpu") {
			if (load > config.costDownAt || (missing && load > config.cpuBoundBelow)) {
				want = -1; reason = "gpu-slow"; bound = "gpu";
			} else if (missing) {
				reason = "cpu-bound"; bound = "cpu";
			} else if (clean && predictedLoad < config.costUpAt) {
				if (dwellDone) { want = 1; reason = "gpu-headroom"; } else reason = "dwell";
			}
		} else if (missing || emaFrameMs > config.frameDownAt * targetMs) {
			want = -1; reason = "frames-missed";
		} else if (signal === "frame") {
			if (clean && predictedLoad < config.costUpAt) {
				if (dwellDone) { want = 1; reason = "frame-headroom"; } else reason = "dwell";
			}
		} else if (clean) {
			cleanMs += elapsed;
			if (cleanMs + targetMs / 2 >= probeDelay()) { want = 1; reason = "probe"; }
		} else {
			cleanMs = 0;
		}
		// Anti-churn: judge the most recent climb.
		let revert = false;
		if (lastClimbAtMs !== null) {
			if (want < 0) {
				if (probation > 0) {
					revert = true;
					reason = lastClimbSignal === "probe" ? "probe-failed" : "climb-failed";
				}
				if (clockMs - lastClimbAtMs < config.churnWindowMs) backoff = Math.min(MAX_BACKOFF, backoff * 2);
				lastClimbAtMs = null;
			} else if (clockMs - lastClimbAtMs >= config.churnWindowMs) {
				backoff = Math.max(1, backoff / 2);
				lastClimbAtMs = null;
			}
		}
		if (probation > 0) probation--;
		const drop = revert ? config.stepUp : missRatio >= config.missRatioSevere ? config.stepDown * 2 : config.stepDown;
		const next = want < 0 ? clampToRange(snap(scale - drop, config.quantum), config)
			: want > 0 ? upNext : scale;
		const atMin = scale <= config.minScale;
		const atMax = scale >= config.maxScale;
		atMinMs = atMin ? atMinMs + elapsed : 0;
		atMaxMs = atMax ? atMaxMs + elapsed : 0;
		// Resolution cannot hold the target: either it is already at the floor, or GPU time shows a CPU bottleneck.
		deficitMs = (want < 0 && next === scale) || reason === "cpu-bound" ? deficitMs + elapsed : 0;
		surplusMs = atMax && want >= 0 && clean ? surplusMs + elapsed : 0;
		lastMissRatio = missRatio;
		lastSignal = signal;
		lastReason = reason;
		clearWindow();
		if (next === scale) return null;
		const keepDeficit = deficitMs, keepAtMin = atMinMs, keepAtMax = atMaxMs;
		const changed = setScale(next, reason);
		atMinMs = scale <= config.minScale ? keepAtMin : 0;
		atMaxMs = scale >= config.maxScale ? keepAtMax : 0;
		deficitMs = keepDeficit;
		if (want > 0) {
			probation = config.probationWindows;
			lastClimbAtMs = clockMs;
			lastClimbSignal = signal;
		}
		return changed;
	}

	return {
		get scale() { return scale; },
		update(sample) {
			const frameMs = typeof sample === "object" && sample !== null ? sample.frameMs : undefined;
			if (typeof frameMs !== "number" || !Number.isFinite(frameMs) || frameMs <= 0) return null;
			const fps = positiveFinite(sample.targetFps, targetFps ?? 60);
			if (fps !== targetFps) {
				const first = targetFps === null;
				targetFps = fps;
				targetMs = 1000 / fps;
				backoff = 1;
				restart(first ? "start" : "target-changed");
			}
			if (frameMs > config.hitchMs) {
				consecutiveHitches++;
				if (consecutiveHitches < config.sustainedHitches) return null;
			} else {
				consecutiveHitches = 0;
			}
			if (warmup > 0) {
				warmup--;
				return null;
			}
			const boundedMs = Math.min(frameMs, 1000);
			emaFrameMs = emaFrameMs === null ? boundedMs : emaFrameMs * (1 - config.emaAlpha) + boundedMs * config.emaAlpha;
			const gpuMs = sample.gpuMs;
			if (typeof gpuMs === "number" && Number.isFinite(gpuMs) && gpuMs > 0) {
				const boundedGpu = Math.min(gpuMs, 1000);
				emaGpuMs = emaGpuMs === null ? boundedGpu : emaGpuMs * (1 - config.emaAlpha) + boundedGpu * config.emaAlpha;
				windowGpu++;
			}
			windowFrames++;
			windowElapsedMs += boundedMs;
			if (frameMs > config.missFactor * targetMs) windowMissed++;
			// Half a target interval of tolerance keeps a 60-frame window at 60 fps despite float rounding.
			if (windowFrames < config.minWindowFrames || windowElapsedMs + targetMs / 2 < config.windowSeconds * 1000) return null;
			return decide();
		},
		reset(reason = "reset") {
			restart(typeof reason === "string" && reason ? reason.slice(0, 32) : "reset");
		},
		setRange(minScale, maxScale) {
			const range = normalizeRange(minScale, maxScale);
			config.minScale = range.minScale;
			config.maxScale = range.maxScale;
			backoff = 1;
			return setScale(clampToRange(snap(scale, config.quantum), config), "range-changed");
		},
		state() {
			const load = targetMs === null ? null
				: lastSignal === "gpu" && emaGpuMs !== null ? emaGpuMs / targetMs
				: emaFrameMs !== null ? emaFrameMs / targetMs : null;
			return Object.freeze({
				scale,
				minScale: config.minScale,
				maxScale: config.maxScale,
				atMin: scale <= config.minScale,
				atMax: scale >= config.maxScale,
				targetFps,
				targetMs,
				signal: lastSignal,
				bound,
				emaFrameMs,
				emaGpuMs,
				loadRatio: load,
				headroomKnown: lastSignal === "gpu" || lastSignal === "frame",
				missRatio: lastMissRatio,
				atMinMs,
				atMaxMs,
				deficitMs,
				surplusMs,
				sinceChangeMs,
				backoff,
				climbDelayMs: climbDelay(),
				probeDelayMs: probeDelay(),
				warmupRemaining: warmup,
				changes,
				lastReason,
			});
		},
	};
}

export const RENDER_SCALING_DEFAULTS = Object.freeze({
	mode: "off",
	scaleFactor: 1.5,
	sharpnessStops: 0.2,
	samples: 4,
	adaptive: false,
	/** Adaptive range in FSR scale factors: best quality end and lowest-resolution end. */
	minScaleFactor: 1,
	maxScaleFactor: 2,
});

const FSR_PRESETS = Object.freeze({ ultra: 1.3, quality: 1.5, balanced: 1.7, performance: 2 });
const MAX_SCALE_FACTOR = 3;
const MAX_SHARPNESS_STOPS = 2;

/**
 * Normalizes caller settings into bounded primitives. Unknown modes fall back
 * to "off"; numbers are clamped to the ranges FSR 1 accepts.
 * @param {Partial<RenderScalingSettings>} [settings]
 * @returns {Readonly<RenderScalingSettings>}
 */
export function normalizeRenderScalingSettings(settings = {}) {
	const input = typeof settings === "object" && settings !== null ? settings : {};
	const minScaleFactor = clampNumber(input.minScaleFactor, 1, MAX_SCALE_FACTOR, RENDER_SCALING_DEFAULTS.minScaleFactor);
	const maxScaleFactor = Math.max(minScaleFactor, clampNumber(input.maxScaleFactor, 1, MAX_SCALE_FACTOR, RENDER_SCALING_DEFAULTS.maxScaleFactor));
	const scaleFactor = clampNumber(input.scaleFactor, 1, MAX_SCALE_FACTOR, RENDER_SCALING_DEFAULTS.scaleFactor);
	const samples = Math.round(clampNumber(input.samples, 1, 8, RENDER_SCALING_DEFAULTS.samples));
	return Object.freeze({
		mode: input.mode === "fsr" ? "fsr" : "off",
		scaleFactor: round(scaleFactor),
		sharpnessStops: round(clampNumber(input.sharpnessStops, 0, MAX_SHARPNESS_STOPS, RENDER_SCALING_DEFAULTS.sharpnessStops)),
		samples: samples >= 8 ? 8 : samples >= 4 ? 4 : samples >= 2 ? 2 : 1,
		adaptive: input.adaptive === true,
		minScaleFactor: round(minScaleFactor),
		maxScaleFactor: round(maxScaleFactor),
	});
}

/**
 * Reads `?fsr=off|1.3|1.5|1.7|2|ultra|quality|balanced|performance`,
 * `&sharp=<stops>`, `&auto=0|1` and `&fsrMsaa=1|2|4|8`. Returns null when the
 * query has no `fsr` parameter, so the default stays off.
 * @param {string} search
 * @returns {Readonly<RenderScalingSettings> | null}
 */
export function parseRenderScalingQuery(search) {
	const params = new URLSearchParams(typeof search === "string" ? search : "");
	if (!params.has("fsr")) return null;
	const raw = (params.get("fsr") ?? "").trim().toLowerCase();
	const preset = Object.hasOwn(FSR_PRESETS, raw) ? FSR_PRESETS[raw] : null;
	const numeric = raw === "" ? NaN : Number(raw);
	const scaleFactor = preset ?? (Number.isFinite(numeric) && numeric >= 1 && numeric <= MAX_SCALE_FACTOR ? numeric : null);
	const sharp = params.get("sharp");
	const msaa = params.get("fsrMsaa");
	return normalizeRenderScalingSettings({
		mode: scaleFactor === null ? "off" : "fsr",
		scaleFactor: scaleFactor ?? undefined,
		sharpnessStops: sharp === null || sharp.trim() === "" ? undefined : Number(sharp),
		samples: msaa === null || msaa.trim() === "" ? undefined : Number(msaa),
		adaptive: params.get("auto") === "1",
	});
}

/** @param {number} scaleFactor @returns {number} */
export function scaleFromScaleFactor(scaleFactor) {
	return round(1 / clampNumber(scaleFactor, 1, MAX_SCALE_FACTOR, 1));
}

/** @param {number} scale @returns {number} */
export function scaleFactorFromScale(scale) {
	return round(1 / clampNumber(scale, 1 / MAX_SCALE_FACTOR, 1, 1));
}

/**
 * Size of the reduced scene target, matching Babylon PostProcess sizing
 * (`(renderWidth * (1 / scaleFactor)) | 0`).
 * @param {number} outputWidth @param {number} outputHeight @param {number} scaleFactor
 */
export function scaledRenderSize(outputWidth, outputHeight, scaleFactor) {
	const ratio = 1 / clampNumber(scaleFactor, 1, MAX_SCALE_FACTOR, 1);
	return { width: Math.max(1, (outputWidth * ratio) | 0), height: Math.max(1, (outputHeight * ratio) | 0) };
}

/** @param {Partial<RenderScaleControllerOptions>} options */
function normalizeControllerOptions(options) {
	const input = typeof options === "object" && options !== null ? options : {};
	const pick = (key, min, max) => clampNumber(input[key], min, max, RENDER_SCALE_DEFAULTS[key]);
	const range = normalizeRange(input.minScale, input.maxScale);
	return {
		...range,
		stepDown: pick("stepDown", 0.01, 0.5),
		stepUp: pick("stepUp", 0.01, 0.5),
		quantum: pick("quantum", 0.005, 0.25),
		emaAlpha: pick("emaAlpha", 0.001, 1),
		windowSeconds: pick("windowSeconds", 0.1, 10),
		minWindowFrames: Math.round(pick("minWindowFrames", 1, 600)),
		warmupFrames: Math.round(pick("warmupFrames", 0, 600)),
		missFactor: pick("missFactor", 1.05, 4),
		missRatioDown: pick("missRatioDown", 0, 1),
		missRatioSevere: pick("missRatioSevere", 0, 1),
		missRatioClean: pick("missRatioClean", 0, 1),
		costDownAt: pick("costDownAt", 0.1, 4),
		costUpAt: pick("costUpAt", 0.05, 4),
		cpuBoundBelow: pick("cpuBoundBelow", 0, 4),
		frameDownAt: pick("frameDownAt", 1, 4),
		cappedAt: pick("cappedAt", 0.1, 1),
		climbDelayMs: pick("climbDelayMs", 0, 600_000),
		probeDelayMs: pick("probeDelayMs", 0, 600_000),
		maxClimbDelayMs: Math.max(pick("climbDelayMs", 0, 600_000), pick("probeDelayMs", 0, 600_000), pick("maxClimbDelayMs", 0, 3_600_000)),
		churnWindowMs: pick("churnWindowMs", 0, 600_000),
		probationWindows: Math.round(pick("probationWindows", 0, 60)),
		hitchMs: pick("hitchMs", 20, 10_000),
		sustainedHitches: Math.round(pick("sustainedHitches", 1, 120)),
		gpuCoverage: pick("gpuCoverage", 0, 1),
	};
}

function normalizeRange(minScale, maxScale) {
	const max = clampNumber(maxScale, 1 / MAX_SCALE_FACTOR, 1, RENDER_SCALE_DEFAULTS.maxScale);
	const min = Math.min(max, clampNumber(minScale, 1 / MAX_SCALE_FACTOR, 1, RENDER_SCALE_DEFAULTS.minScale));
	return { minScale: round(min), maxScale: round(max) };
}

function clampToRange(value, config) {
	return round(Math.min(config.maxScale, Math.max(config.minScale, value)));
}

function snap(value, quantum) {
	const number = typeof value === "number" && Number.isFinite(value) ? value : 1;
	return Math.round(number / quantum) * quantum;
}

function round(value) {
	return Math.round(value * SCALE_PRECISION) / SCALE_PRECISION;
}

function clampNumber(value, min, max, fallback) {
	if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
	return Math.min(max, Math.max(min, value));
}

function positiveFinite(value, fallback) {
	return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

/** @typedef {import("./render-scale-controller.d.mts").RenderScaleControllerOptions} RenderScaleControllerOptions */
/** @typedef {import("./render-scale-controller.d.mts").RenderScaleController} RenderScaleController */
/** @typedef {import("./render-scale-controller.d.mts").RenderScalingSettings} RenderScalingSettings */
