/**
 * Pure frame-rate policy: refresh-rate estimation from requestAnimationFrame
 * timestamps, the allowed-cap ladder (clean divisors of the refresh rate), a
 * vsync-aligned frame limiter, the user setting, and the Auto controller that
 * cooperates with render-scale-controller.mjs.
 *
 * No DOM, Babylon or global access. The host injects rAF timestamps, an
 * optional clock and the requestAnimationFrame/cancelAnimationFrame pair, so
 * every decision is reproducible in `node --test`.
 *
 * Joint rule with the render-scale controller: resolution adapts first. Auto
 * lowers the cap only after the scale has sat at its minimum (or the frame is
 * CPU-bound) with a sustained deficit, and probes a higher cap only when the
 * scale is at its maximum with sustained surplus. A probe above the tier's
 * base cap is reverted as soon as the scale leaves its maximum, so Auto never
 * buys extra frames with resolution.
 */

export const KNOWN_REFRESH_RATES = Object.freeze([30, 48, 50, 60, 72, 75, 90, 100, 120, 144, 165, 240]);
/** Values the settings UI offers, in display order. */
export const FRAME_RATE_SETTINGS = Object.freeze(["auto", 30, 60, 90, 120, "max"]);
export const FRAME_RATE_STORAGE_KEY = "aetherfield_frame_rate_v1";
/** Window event the settings UI dispatches with `{ setting }` after persisting a new choice. */
export const FRAME_RATE_SETTING_EVENT = "aetherfield:frame-rate-setting-change";
/** Window event the renderer dispatches with a small state DTO when the cap or refresh rate changes. */
export const FRAME_RATE_STATE_EVENT = "aetherfield:frame-rate-state";
/** Lowest cap the ladder offers; 59.94 / 2 still counts as 30. */
export const MIN_FRAME_CAP_FPS = 30;

const STORAGE_VERSION = 1;
const MAX_SETTING_FPS = 1000;
const MAX_DIVISOR = 16;
const FLOOR_TOLERANCE = 0.02;
const DEFAULT_SNAP_TOLERANCE = 0.05;
const FPS_PRECISION = 1000;

export const REFRESH_ESTIMATOR_DEFAULTS = Object.freeze({
	/** Provisional rate until the first lock. */
	initialHz: 60,
	/** Intervals kept for the robust estimate. */
	windowSize: 120,
	/** Newest intervals that decide whether the rate changed. */
	recentSize: 24,
	/** Intervals needed before the first lock. */
	minSamples: 20,
	/** Idle-start intervals needed to change (or lower) a rate. */
	minCleanSamples: 6,
	/** Idle-start intervals that suffice to re-confirm the rate already locked. */
	minConfirmCleanSamples: 3,
	/** Intervals between re-evaluations once locked. */
	evaluateEvery: 10,
	/** Shorter intervals are coalesced callbacks, not a refresh period. */
	minIntervalMs: 2,
	/** Longer intervals are stalls, hidden time or GC, never a refresh period. */
	maxIntervalMs: 250,
	/** Share of intervals at a shorter period that proves a faster vsync. */
	raiseSupport: 0.3,
	/** Consecutive agreeing evaluations before a locked rate changes. */
	confirmEvaluations: 2,
	/** Relative distance within which a measured rate snaps to a known rate. */
	snapTolerance: DEFAULT_SNAP_TOLERANCE,
	/** Idle-start intervals kept separately, so sparse probe samples survive a fast window. */
	cleanWindow: 32,
	/** Idle-start intervals older than this no longer count. */
	cleanMaxAgeMs: 8000,
	/** When rendered frames slow down and no idle frame arrived for this long, older idle frames are stale. */
	staleCleanMs: 1000,
	/** After idle frames prove "load, not throttling", stop asking for probes this long (doubles to the max). */
	loadHoldMs: 30000,
	maxLoadHoldMs: 120000,
});

export const FRAME_LIMITER_DEFAULTS = Object.freeze({
	/** Share of the phase error folded back into the deadline grid each on-time frame. */
	phaseGain: 0.25,
	/** Rendered intervals kept for windowed stats. */
	statsWindow: 120,
	/** A deadline missed by more than this is a stall: re-anchor, do not count drops. */
	stallMs: 250,
});

export const FRAME_RATE_POLICY_DEFAULTS = Object.freeze({
	minFps: MIN_FRAME_CAP_FPS,
	/** Auto never climbs above this on phones; fixed settings may. */
	mobileAutoCeilingFps: 60,
	/** 0 means "the refresh rate". */
	desktopAutoCeilingFps: 0,
	/** Continuous deficit (scale at min or CPU-bound) before Auto steps the cap down (desktop; phones below). */
	stepDownAfterMs: 3000,
	mobileStepDownAfterMs: 5000,
	/** At most one policy-initiated cap change per this long (Mobile Safari: resolution churn has crashed it). */
	desktopMinChangeIntervalMs: 3000,
	mobileMinChangeIntervalMs: 10000,
	/** Minimum time between two Auto decisions. */
	minDwellMs: 3000,
	/** Continuous surplus at max scale before the first probe up; doubled after each failure. */
	desktopProbeUpAfterMs: 8000,
	mobileProbeUpAfterMs: 20000,
	desktopMaxProbeUpAfterMs: 120000,
	mobileMaxProbeUpAfterMs: 300000,
	/** A probe is judged over this long; above the base it must keep the scale at max. */
	probationMs: 6000,
	/** Deficit during an above-base probe that fails it. */
	probationDeficitMs: 1000,
	/** Above the base, the scale below max this long makes Auto yield one rung. */
	yieldAfterMs: 1500,
	/** A deficit step-down this soon after a probe counts as that probe failing. */
	probeFailWindowMs: 60000,
	/** Upper bound of the wait after repeated consecutive failures. */
	probeBanMaxMs: 1800000,
	/** Predicted load (loadRatio scaled to the next cap) must stay below this. */
	probeLoadMax: 0.85,
	/** Probe above the base without measured headroom. Off on phones: Safari 27.0 WebGPU hides GPU overload. */
	desktopBlindProbeAboveBase: true,
	mobileBlindProbeAboveBase: false,
	/** Sustained step-downs inside this window that flag thermal throttling: one on phones (A13 sustains 50-77 % of peak), two on desktop. */
	thermalWindowMs: 600000,
	mobileThermalStepDowns: 1,
	desktopThermalStepDowns: 2,
	/** A step-down counts as sustained when the cap had held this long. */
	thermalStableMs: 60000,
	/** No probes or opt-in promotions for this long after thermal throttling is suspected (desktop; phones below). */
	thermalHoldMs: 300000,
	mobileThermalHoldMs: 600000,
	/**
	 * Guarded opt-in for a fixed setting above the Auto base (phones by default: iPhone 11 "Smooth 60").
	 * Start at the base; promote after optInPromoteAfterMs with CPU p95 <= optInPromoteShare x the target
	 * interval (14 ms at 60); fall back after optInDemoteAfterMs with frame-interval p95 > optInDemoteShare x
	 * the target interval (18 ms at 60), or at once on thermal suspicion. Waits double per fallback.
	 */
	mobileFixedGate: true,
	desktopFixedGate: false,
	optInPromoteAfterMs: 60000,
	optInPromoteShare: 0.84,
	optInDemoteAfterMs: 5000,
	optInDemoteShare: 1.08,
	/** Holding the opt-in target this long clears the fallback back-off. */
	optInStableMs: 300000,
	/** First gap between estimator probes (one skipped render each); grows 1.2x per probe to 5 s. */
	estimatorProbeGapMs: 300,
	/** Auto waits for an unresolved refresh question at most this long, then decides on the current lock. */
	maxProbeFreezeMs: 10000,
	/** A scale signal older than this falls back to the limiter's own stats. */
	signalTimeoutMs: 2000,
	/** Fallback deficit: achieved fps below this share of the cap, or late share above fallbackLateRatio. */
	fallbackDeficitShare: 0.92,
	fallbackLateRatio: 0.15,
	/** Fallback surplus: achieved fps at or above this share with late share at or below fallbackCleanLateRatio. */
	fallbackSurplusShare: 0.97,
	fallbackCleanLateRatio: 0.02,
});

// ---------------------------------------------------------------------------
// Settings and the cap ladder
// ---------------------------------------------------------------------------

/**
 * Snaps a measured rate to the nearest known refresh rate when it lies within
 * `tolerance` (relative); otherwise rounds it, so 180 or 360 Hz panels keep
 * their own rate. Returns null for invalid input.
 * @param {number} hz @param {number} [tolerance]
 * @returns {number | null}
 */
export function snapRefreshRate(hz, tolerance = DEFAULT_SNAP_TOLERANCE) {
	if (!isPositiveFinite(hz)) return null;
	const limit = Math.log1p(isPositiveFinite(tolerance) ? Math.min(tolerance, 0.5) : DEFAULT_SNAP_TOLERANCE);
	let best = KNOWN_REFRESH_RATES[0];
	let bestError = Infinity;
	for (const rate of KNOWN_REFRESH_RATES) {
		const error = Math.abs(Math.log(hz / rate));
		if (error < bestError) { best = rate; bestError = error; }
	}
	return bestError <= limit ? best : Math.max(1, Math.round(hz));
}

/**
 * Caps that pace evenly: the refresh rate divided by 1, 2, 3, ... down to
 * `minFps`. A refresh rate below the floor offers only itself.
 * 120 -> [120, 60, 40, 30]; 144 -> [144, 72, 48, 36]; 90 -> [90, 45, 30].
 * @param {number} refreshHz @param {number} [minFps]
 * @returns {readonly number[]} descending
 */
export function allowedFrameCaps(refreshHz, minFps = MIN_FRAME_CAP_FPS) {
	const refresh = isPositiveFinite(refreshHz) ? refreshHz : 60;
	const floor = (isPositiveFinite(minFps) ? minFps : MIN_FRAME_CAP_FPS) * (1 - FLOOR_TOLERANCE);
	const caps = [roundFps(refresh)];
	for (let divisor = 2; divisor <= MAX_DIVISOR && refresh / divisor >= floor; divisor++) caps.push(roundFps(refresh / divisor));
	return Object.freeze(caps);
}

/**
 * Nearest allowed cap by frame-time distance (the budget the GPU actually
 * sees); an exact frame-time tie goes to the cap nearer in fps, then the lower.
 * 60 on 144 Hz -> 72; 30 on 144 Hz -> 36; 60 on 90 Hz -> 45; 90 on 60 Hz -> 60.
 * @param {number} requestedFps @param {number} refreshHz @param {number} [minFps]
 * @returns {number}
 */
export function nearestAllowedCap(requestedFps, refreshHz, minFps = MIN_FRAME_CAP_FPS) {
	return nearestInLadder(requestedFps, allowedFrameCaps(refreshHz, minFps));
}

/**
 * Accepts "auto", "max", a number or a numeric string. Numbers are rounded and
 * clamped to [MIN_FRAME_CAP_FPS, 1000]; anything else is "auto".
 * @param {unknown} value
 * @returns {FrameRateSetting}
 */
export function normalizeFrameRateSetting(value) {
	if (value === "auto" || value === "max") return value;
	const numeric = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
	if (typeof numeric !== "number" || !Number.isFinite(numeric) || numeric <= 0) return "auto";
	return Math.min(MAX_SETTING_FPS, Math.max(MIN_FRAME_CAP_FPS, Math.round(numeric)));
}

/**
 * Cap for a fixed setting on a given refresh rate. "auto" resolves like "max"
 * here; Auto's starting cap comes from the policy.
 * @param {FrameRateSetting} setting @param {number} refreshHz @param {number} [minFps]
 */
export function resolveFixedFrameCap(setting, refreshHz, minFps = MIN_FRAME_CAP_FPS) {
	const normalized = normalizeFrameRateSetting(setting);
	const caps = allowedFrameCaps(refreshHz, minFps);
	return typeof normalized === "number" ? nearestInLadder(normalized, caps) : caps[0];
}

/** @param {unknown} raw @returns {FrameRateSetting} Malformed or old data behaves as Auto. */
export function parseStoredFrameRateSetting(raw) {
	if (typeof raw !== "string" || raw === "") return "auto";
	try {
		const parsed = JSON.parse(raw);
		if (typeof parsed !== "object" || parsed === null || parsed.version !== STORAGE_VERSION) return "auto";
		return normalizeFrameRateSetting(parsed.setting);
	} catch {
		return "auto";
	}
}

/** @param {FrameRateSetting} setting @returns {string} */
export function serializeFrameRateSetting(setting) {
	return JSON.stringify({ version: STORAGE_VERSION, setting: normalizeFrameRateSetting(setting) });
}

/**
 * What each offered setting would do on the current screen, for the settings
 * UI ("60 -> 72 on this 144 Hz screen"). Data only; copy lives in the UI.
 * @param {FrameRatePolicyState} state
 * @returns {readonly FrameRateOption[]}
 */
export function describeFrameRateOptions(state) {
	const refreshHz = isPositiveFinite(state?.refreshHz) ? state.refreshHz : 60;
	const minFps = isPositiveFinite(state?.minFps) ? state.minFps : MIN_FRAME_CAP_FPS;
	return Object.freeze(FRAME_RATE_SETTINGS.map(value => {
		const capFps = value === "auto"
			? (state?.setting === "auto" && isPositiveFinite(state.capFps) ? state.capFps : (isPositiveFinite(state?.autoBaseCapFps) ? state.autoBaseCapFps : allowedFrameCaps(refreshHz, minFps)[0]))
			: resolveFixedFrameCap(value, refreshHz, minFps);
		return Object.freeze({
			value,
			capFps,
			exact: typeof value !== "number" || Math.abs(capFps - value) < 0.5,
			selected: state?.setting === value,
		});
	}));
}

// ---------------------------------------------------------------------------
// Refresh-rate estimation
// ---------------------------------------------------------------------------

/**
 * Estimates the rate at which rAF is delivered. An interval that starts at an
 * idle callback (no render) is "clean": it measures vsync, not our frame cost.
 * Any samples may raise the estimate (load cannot make callbacks faster); only
 * clean samples may lower it, because a GPU-bound 60 Hz stream looks exactly
 * like a 30 Hz rAF. When a slower stream has no clean samples the estimator
 * sets `needsProbe` and the host skips one render to obtain one.
 *
 * @param {Partial<RefreshEstimatorOptions>} [options]
 * @returns {RefreshRateEstimator}
 */
export function createRefreshRateEstimator(options = {}) {
	const config = normalizeEstimatorOptions(options);
	const intervals = new Float64Array(config.windowSize);
	const allScratch = new Float64Array(config.windowSize);
	const recentScratch = new Float64Array(config.windowSize);
	const cleanIntervals = new Float64Array(config.cleanWindow);
	const cleanTimes = new Float64Array(config.cleanWindow);
	const cleanScratch = new Float64Array(config.cleanWindow);
	let head = 0;
	let count = 0;
	let cleanHead = 0;
	let cleanCount = 0;
	let lastTimestamp = null;
	let loadHoldUntil = -Infinity;
	let loadHoldMs = config.loadHoldMs;
	let phase = "detecting";
	let lockedHz = snapRefreshRate(config.initialHz, config.snapTolerance) ?? 60;
	let periodMs = 1000 / lockedHz;
	let detected = false;
	let source = "initial";
	let maxSeenHz = null;
	let pendingHz = null;
	let pendingCount = 0;
	let sinceEvaluation = 0;
	let needsProbe = false;
	let changes = 0;
	let stalls = 0;
	let samplesSinceReset = 0;
	/** False after a screen change: the old rate is no evidence about the new screen. */
	let hasPrior = true;
	let lastReason = "start";

	function push(interval, clean, at) {
		intervals[head] = interval;
		head = (head + 1) % config.windowSize;
		if (count < config.windowSize) count++;
		if (!clean) return;
		cleanIntervals[cleanHead] = interval;
		cleanTimes[cleanHead] = at;
		cleanHead = (cleanHead + 1) % config.cleanWindow;
		if (cleanCount < config.cleanWindow) cleanCount++;
	}

	function freshCleanCount(now) {
		let fresh = 0;
		for (let i = 0; i < cleanCount; i++) if (now - cleanTimes[i] <= config.cleanMaxAgeMs) fresh++;
		return fresh;
	}

	function confirm(hz) {
		if (pendingHz === hz) pendingCount++;
		else { pendingHz = hz; pendingCount = 1; }
		return pendingCount >= config.confirmEvaluations;
	}

	function lock(hz, measuredPeriod, from, reason) {
		const nominal = 1000 / hz;
		const refined = Math.abs(measuredPeriod - nominal) <= nominal * 0.02 ? measuredPeriod : nominal;
		if (!detected || hz !== lockedHz) changes++;
		lockedHz = hz;
		periodMs = refined;
		source = from;
		detected = true;
		phase = "locked";
		pendingHz = null;
		pendingCount = 0;
		maxSeenHz = Math.max(maxSeenHz ?? 0, hz);
		hasPrior = true;
		lastReason = reason;
	}

	function refine(measuredPeriod) {
		const nominal = 1000 / lockedHz;
		if (Math.abs(measuredPeriod - nominal) > nominal * 0.02) return;
		periodMs = periodMs * 0.8 + measuredPeriod * 0.2;
	}

	function holdForLoad(now) {
		// Idle frames see the locked vsync while rendered frames are slower: it is load, not a throttled rAF.
		loadHoldUntil = now + loadHoldMs;
		loadHoldMs = Math.min(config.maxLoadHoldMs, loadHoldMs * 2);
		lastReason = "load-confirmed";
	}

	function evaluate(now) {
		sinceEvaluation = 0;
		for (let i = 0; i < count; i++) allScratch[i] = intervals[i];
		const all = allScratch.subarray(0, count).sort();
		const loaded = lowestCluster(all, config.raiseSupport);
		// Changes of rate are judged on the newest intervals; the full window only refines a rate already agreed.
		const recentCount = Math.min(count, config.recentSize);
		for (let k = 0; k < recentCount; k++) recentScratch[k] = intervals[(head - 1 - k + config.windowSize) % config.windowSize];
		const recent = lowestCluster(recentScratch.subarray(0, recentCount).sort(), config.raiseSupport) ?? loaded;
		let fresh = 0;
		let newestClean = -Infinity;
		for (let i = 0; i < cleanCount; i++) {
			if (now - cleanTimes[i] > config.cleanMaxAgeMs) continue;
			cleanScratch[fresh++] = cleanIntervals[i];
			if (cleanTimes[i] > newestClean) newestClean = cleanTimes[i];
		}
		// Idle frames that stopped arriving while rendered frames slowed down predate the change: they vouch for
		// nothing, and must not outvote the probes that follow. Discard them.
		if (phase === "locked" && recent !== null && recent.periodMs > periodMs * 1.4 && now - newestClean > config.staleCleanMs) {
			fresh = 0;
			cleanCount = 0;
			cleanHead = 0;
		}
		let clean = null;
		if (fresh >= Math.min(config.minConfirmCleanSamples, config.minCleanSamples)) {
			const candidate = robustPeriod(cleanScratch.subarray(0, fresh).sort());
			if (candidate && candidate.support >= 0.6) clean = { ...candidate, strong: fresh >= config.minCleanSamples, hz: snapRefreshRate(1000 / candidate.periodMs, config.snapTolerance) ?? lockedHz };
		}
		if (phase === "detecting") {
			if (clean && (clean.strong || clean.hz === lockedHz)) {
				const slower = loaded !== null && loaded.periodMs > clean.periodMs * 1.4;
				lock(clean.hz, clean.periodMs, "clean", "detected-clean");
				needsProbe = false;
				if (slower) holdForLoad(now);
				return;
			}
			if (count < config.minSamples || !loaded) return;
			const hz = snapRefreshRate(1000 / loaded.periodMs, config.snapTolerance) ?? lockedHz;
			if (loaded.periodMs <= periodMs * 1.25) {
				// Same or faster than the prior: rendered frames cannot outrun vsync.
				lock(hz, loaded.periodMs, "loaded", "detected");
				needsProbe = false;
			} else if (!hasPrior) {
				// The screen changed, so the old rate proves nothing: take the stream, then confirm with idle frames.
				lock(hz, loaded.periodMs, "loaded", "detected-unconfirmed");
				needsProbe = true;
			} else {
				// Slower: load or a throttled rAF. Keep the prior until idle frames decide.
				needsProbe = true;
			}
			return;
		}
		const slowerLoaded = recent !== null && recent.periodMs > periodMs * 1.4;
		if (clean) {
			if (clean.hz !== lockedHz) {
				if (clean.strong) {
					// Unanimous idle-frame evidence changes the rate at once; otherwise two evaluations must agree.
					if (clean.support >= 0.9 || confirm(clean.hz)) lock(clean.hz, clean.periodMs, "clean", clean.hz > lockedHz ? "faster-clean" : "slower-clean");
					needsProbe = false;
				} else {
					needsProbe = true;
				}
				return;
			}
			pendingHz = null;
			pendingCount = 0;
			source = "clean";
			refine(clean.periodMs);
			if (slowerLoaded && needsProbe) holdForLoad(now);
			needsProbe = false;
			return;
		}
		if (!loaded || !recent) return;
		if (recent.periodMs < periodMs * 0.75 && recent.support >= config.raiseSupport) {
			const hz = snapRefreshRate(1000 / recent.periodMs, config.snapTolerance) ?? lockedHz;
			if (hz > lockedHz && confirm(hz)) lock(hz, recent.periodMs, "loaded", "faster-loaded");
			needsProbe = false;
			return;
		}
		if (slowerLoaded) {
			pendingHz = null;
			pendingCount = 0;
			needsProbe = now >= loadHoldUntil;
			return;
		}
		pendingHz = null;
		pendingCount = 0;
		needsProbe = false;
		loadHoldMs = config.loadHoldMs;
		if (source !== "clean") refine(loaded.periodMs);
	}

	return {
		addFrame(timestampMs, previousFrameRendered) {
			if (typeof timestampMs !== "number" || !Number.isFinite(timestampMs)) return;
			if (lastTimestamp === null || timestampMs < lastTimestamp) { lastTimestamp = timestampMs; return; }
			const interval = timestampMs - lastTimestamp;
			lastTimestamp = timestampMs;
			if (interval < config.minIntervalMs) return;
			if (interval > config.maxIntervalMs) { stalls++; return; }
			const clean = previousFrameRendered === false;
			push(interval, clean, timestampMs);
			samplesSinceReset++;
			sinceEvaluation++;
			const due = phase === "detecting"
				? (clean && freshCleanCount(timestampMs) >= config.minCleanSamples) || (samplesSinceReset >= config.minSamples && sinceEvaluation >= Math.min(config.evaluateEvery, config.minSamples))
				: sinceEvaluation >= config.evaluateEvery || (clean && needsProbe);
			if (due) evaluate(timestampMs);
		},
		reset(reason = "reset", { forgetPrior = false } = {}) {
			head = 0;
			count = 0;
			cleanHead = 0;
			cleanCount = 0;
			lastTimestamp = null;
			phase = "detecting";
			pendingHz = null;
			pendingCount = 0;
			sinceEvaluation = 0;
			samplesSinceReset = 0;
			needsProbe = false;
			loadHoldUntil = -Infinity;
			loadHoldMs = config.loadHoldMs;
			if (forgetPrior) { hasPrior = false; maxSeenHz = null; }
			lastReason = typeof reason === "string" && reason ? reason.slice(0, 32) : "reset";
		},
		get refreshHz() { return lockedHz; },
		get periodMs() { return periodMs; },
		get phase() { return phase; },
		get needsProbe() { return needsProbe; },
		get detected() { return detected; },
		state() {
			return Object.freeze({
				phase,
				detected,
				refreshHz: lockedHz,
				periodMs,
				source,
				maxSeenHz,
				/** A browser-capped rAF below 40 Hz (30 Hz, or WebKit's 30 ms timer) proven by idle frames, not inferred from slow rendered frames. */
				throttled: detected && lockedHz < 40 && source === "clean",
				needsProbe,
				samples: count,
				changes,
				stalls,
				lastReason,
			});
		},
	};
}

// ---------------------------------------------------------------------------
// Vsync-aligned frame limiter
// ---------------------------------------------------------------------------

/**
 * Decides per rAF callback whether to render. The cap's interval is a whole
 * number of vsync periods; a callback renders when `now >= deadline - period/2`,
 * so the threshold sits half a vsync before the deadline and timestamp jitter
 * below half a vsync cannot move a frame to a neighbouring vsync. On-time
 * frames advance the deadline by exactly one interval plus a small phase
 * correction (a phase-locked loop) so the grid follows the real vsync without
 * drifting. A frame one or more vsyncs late re-anchors to its own vsync, so a
 * hitch costs one long interval instead of a long-then-short pair.
 *
 * @param {Partial<FrameLimiterOptions> & { refreshHz?: number, periodMs?: number, capFps?: number }} [options]
 * @returns {FrameLimiter}
 */
export function createFrameLimiter(options = {}) {
	const config = {
		phaseGain: clampNumber(options.phaseGain, 0, 1, FRAME_LIMITER_DEFAULTS.phaseGain),
		statsWindow: Math.round(clampNumber(options.statsWindow, 8, 1200, FRAME_LIMITER_DEFAULTS.statsWindow)),
		stallMs: clampNumber(options.stallMs, 50, 10000, FRAME_LIMITER_DEFAULTS.stallMs),
	};
	const windowIntervals = new Float64Array(config.statsWindow);
	const windowLate = new Uint8Array(config.statsWindow);
	const quantileScratch = new Float64Array(config.statsWindow);
	let windowHead = 0;
	let windowCount = 0;
	let windowSum = 0;
	let windowLateCount = 0;
	let refreshHz = 60;
	let periodMs = 1000 / 60;
	let capFps = 60;
	let divisor = 1;
	let intervalMs = periodMs;
	let deadline = null;
	let lastRenderAt = null;
	let lastIntervalMs = null;
	let paused = false;
	let probeRequested = false;
	let probing = false;
	const totals = { rendered: 0, skipped: 0, late: 0, dropped: 0, stalls: 0, probes: 0 };

	function clearWindow() {
		windowHead = 0;
		windowCount = 0;
		windowSum = 0;
		windowLateCount = 0;
	}

	function record(interval, late) {
		if (windowCount === config.statsWindow) {
			windowSum -= windowIntervals[windowHead];
			windowLateCount -= windowLate[windowHead];
		} else {
			windowCount++;
		}
		windowIntervals[windowHead] = interval;
		windowLate[windowHead] = late ? 1 : 0;
		windowSum += interval;
		windowLateCount += late ? 1 : 0;
		windowHead = (windowHead + 1) % config.statsWindow;
	}

	function configure(next) {
		const nextRefresh = isPositiveFinite(next?.refreshHz) ? next.refreshHz : refreshHz;
		const nextPeriod = isPositiveFinite(next?.periodMs) ? next.periodMs : 1000 / nextRefresh;
		const nextCap = isPositiveFinite(next?.capFps) ? Math.min(next.capFps, nextRefresh) : Math.min(capFps, nextRefresh);
		const nextDivisor = Math.max(1, Math.round(nextRefresh / nextCap));
		const structural = nextRefresh !== refreshHz || nextDivisor !== divisor || nextCap !== capFps;
		const previousInterval = intervalMs;
		refreshHz = nextRefresh;
		periodMs = nextPeriod;
		capFps = nextCap;
		divisor = nextDivisor;
		intervalMs = divisor * periodMs;
		if (structural) {
			// Keep the phase of the last rendered frame; the next deadline is one new interval after it.
			deadline = lastRenderAt === null ? null : lastRenderAt + intervalMs;
			clearWindow();
		} else if (deadline !== null) {
			// A refined period only nudges the pending deadline; pacing state and stats survive.
			deadline += intervalMs - previousInterval;
		}
		return structural;
	}

	configure(options);

	return {
		shouldRender(nowMs) {
			if (typeof nowMs !== "number" || !Number.isFinite(nowMs)) return true;
			if (paused) return false;
			const half = periodMs / 2;
			if (deadline === null || lastRenderAt === null || nowMs < lastRenderAt) {
				deadline = nowMs + intervalMs;
				lastIntervalMs = null;
				lastRenderAt = nowMs;
				probing = false;
				totals.rendered++;
				return true;
			}
			if (nowMs < deadline - half) { totals.skipped++; return false; }
			if (probeRequested) {
				// Skip one frame that would have rendered: the next interval then starts at an idle callback.
				probeRequested = false;
				probing = true;
				totals.probes++;
				totals.skipped++;
				return false;
			}
			const error = nowMs - deadline;
			const interval = nowMs - lastRenderAt;
			if (probing) {
				probing = false;
				deadline = nowMs + intervalMs;
				lastIntervalMs = null;
			} else if (error >= config.stallMs) {
				totals.stalls++;
				deadline = nowMs + intervalMs;
				lastIntervalMs = null;
			} else if (error >= half) {
				// At least one vsync late: count it, count whole intervals that never rendered, re-anchor here.
				totals.late++;
				totals.dropped += Math.floor((error + half) / intervalMs);
				deadline = nowMs + intervalMs;
				lastIntervalMs = interval;
				record(interval, true);
			} else {
				const correction = Math.max(-periodMs / 4, Math.min(periodMs / 4, error * config.phaseGain));
				deadline += intervalMs + correction;
				lastIntervalMs = interval;
				record(interval, false);
			}
			lastRenderAt = nowMs;
			totals.rendered++;
			return true;
		},
		configure,
		requestIdleFrame() { probeRequested = true; },
		setPaused(value) {
			const next = value === true;
			if (next === paused) return;
			paused = next;
			if (!paused) {
				deadline = null;
				lastRenderAt = null;
				lastIntervalMs = null;
				probeRequested = false;
				probing = false;
				clearWindow();
			}
		},
		reset() {
			deadline = null;
			lastRenderAt = null;
			lastIntervalMs = null;
			probeRequested = false;
			probing = false;
			clearWindow();
		},
		get intervalMs() { return intervalMs; },
		get periodMs() { return periodMs; },
		get divisor() { return divisor; },
		get capFps() { return capFps; },
		get refreshHz() { return refreshHz; },
		get paused() { return paused; },
		get lastIntervalMs() { return lastIntervalMs; },
		get achievedFps() { return windowCount > 0 && windowSum > 0 ? 1000 * windowCount / windowSum : null; },
		get lateRatio() { return windowCount > 0 ? windowLateCount / windowCount : 0; },
		get windowFrames() { return windowCount; },
		/** Quantile of the newest lastN rendered intervals (probe and stall intervals excluded); null below 8. */
		intervalQuantile(q, lastN = windowCount) {
			const n = Math.min(windowCount, Math.max(1, Math.round(lastN)));
			if (n < 8) return null;
			for (let k = 0; k < n; k++) quantileScratch[k] = windowIntervals[(windowHead - 1 - k + config.statsWindow) % config.statsWindow];
			const sorted = quantileScratch.subarray(0, n).sort();
			return sorted[Math.min(n - 1, Math.floor(n * q))];
		},
		stats() {
			let mean = null;
			let jitter = null;
			if (windowCount > 0) {
				mean = windowSum / windowCount;
				let squares = 0;
				for (let i = 0; i < windowCount; i++) squares += (windowIntervals[i] - mean) ** 2;
				jitter = Math.sqrt(squares / windowCount);
			}
			return Object.freeze({
				...totals,
				capFps,
				refreshHz,
				divisor,
				intervalMs,
				achievedFps: mean === null ? null : 1000 / mean,
				meanIntervalMs: mean,
				jitterMs: jitter,
				lateRatio: windowCount > 0 ? windowLateCount / windowCount : 0,
				windowFrames: windowCount,
				lastIntervalMs,
			});
		},
	};
}

// ---------------------------------------------------------------------------
// Policy: setting + estimator + limiter + Auto
// ---------------------------------------------------------------------------

/**
 * @param {Partial<FrameRatePolicyOptions>} [options]
 * @returns {FrameRatePolicy}
 */
export function createFrameRatePolicy(options = {}) {
	const input = typeof options === "object" && options !== null ? options : {};
	let formFactor = normalizeFormFactor(input.formFactor);
	const tuning = normalizePolicyOptions(input);
	const estimator = createRefreshRateEstimator({ ...input.estimator, initialHz: input.initialRefreshHz ?? input.estimator?.initialHz });
	const limiter = createFrameLimiter({ ...input.limiter, refreshHz: estimator.refreshHz, periodMs: estimator.periodMs });
	const onChange = typeof input.onChange === "function" ? input.onChange : null;
	const workSamples = new Float64Array(60);
	const workScratch = new Float64Array(60);
	let workHead = 0;
	let workCount = 0;

	let setting = normalizeFrameRateSetting(input.setting ?? "auto");
	let tierTargetFps = isPositiveFinite(input.tierTargetFps) ? input.tierTargetFps : (formFactor === "mobile" ? 30 : 60);
	/** graphics-quality autoCeilingFps for the tier; 0 means no tier limit. */
	let tierCeilingFps = isPositiveFinite(input.autoCeilingFps) ? input.autoCeilingFps : 0;
	let refreshHz = estimator.refreshHz;
	let caps = allowedFrameCaps(refreshHz, tuning.minFps);
	let capFps = caps[0];
	let paused = false;
	let lastTimestamp = null;
	let lastRendered = false;
	let lastChangeAt = null;
	let lastChange = null;
	let probation = null;
	let lastProbeAt = -Infinity;
	let lastPolicyChangeAt = -Infinity;
	/** Guarded opt-in state for a fixed setting above the Auto base; null otherwise. */
	let guard = null;
	let guardFrames = 0;
	let probeCredited = true;
	let consecutiveFailures = 0;
	let belowMaxSince = null;
	let probeDelayMs = probeBase();
	let failedProbes = 0;
	let successfulProbes = 0;
	let stepDowns = 0;
	const sustainedDrops = [];
	let thermalUntil = -Infinity;
	let powerHints = Object.freeze({ lowBattery: false, charging: null });
	// Reused objects: observeScale and the fallback run every rendered frame, so they must not allocate.
	const scaleSignal = { atMin: false, atMax: false, deficitMs: 0, surplusMs: 0, loadRatio: null, headroomKnown: false, bound: "unknown", targetFps: null };
	const fallbackSignal = { atMin: true, atMax: true, deficitMs: 0, surplusMs: 0, loadRatio: null, headroomKnown: false, bound: "unknown", targetFps: 0 };
	let hasScaleSignal = false;
	let scaleSignalAt = -Infinity;
	let needsProbeSince = null;
	let fallbackDeficitMs = 0;
	let fallbackSurplusMs = 0;
	let estimatorProbeAt = -Infinity;
	let estimatorProbeGapMs = tuning.estimatorProbeGapMs;
	let lastFrameIntervalMs = null;

	function probeBase() { return formFactor === "mobile" ? tuning.mobileProbeUpAfterMs : tuning.desktopProbeUpAfterMs; }
	function probeMax() { return formFactor === "mobile" ? tuning.mobileMaxProbeUpAfterMs : tuning.desktopMaxProbeUpAfterMs; }
	function blindAboveBase() { return formFactor === "mobile" ? tuning.mobileBlindProbeAboveBase : tuning.desktopBlindProbeAboveBase; }
	function autoCeiling() {
		const configured = formFactor === "mobile" ? tuning.mobileAutoCeilingFps : tuning.desktopAutoCeilingFps;
		return Math.min(configured > 0 ? configured : Infinity, tierCeilingFps > 0 ? tierCeilingFps : Infinity);
	}
	function powerLimited() { return powerHints.lowBattery === true && powerHints.charging !== true; }
	function stepDownAfter() { return formFactor === "mobile" ? tuning.mobileStepDownAfterMs : tuning.stepDownAfterMs; }
	function thermalStepDowns() { return formFactor === "mobile" ? tuning.mobileThermalStepDowns : tuning.desktopThermalStepDowns; }
	function minChangeInterval() { return formFactor === "mobile" ? tuning.mobileMinChangeIntervalMs : tuning.desktopMinChangeIntervalMs; }
	function gateEnabled() { return formFactor === "mobile" ? tuning.mobileFixedGate : tuning.desktopFixedGate; }

	/** Auto's rungs: allowed caps at or below the Auto ceiling (never empty). */
	function autoLadder() {
		const ceiling = autoCeiling();
		const ladder = caps.filter(cap => cap <= ceiling * 1.001);
		return ladder.length > 0 ? ladder : [caps[caps.length - 1]];
	}

	function baseCap() { return nearestInLadder(tierTargetFps, autoLadder()); }

	function emit(reason, previous) {
		if (!onChange) return;
		try {
			onChange(Object.freeze({ reason, capFps, refreshHz, paused, previousCapFps: previous?.capFps ?? null, previousRefreshHz: previous?.refreshHz ?? null }));
		} catch {
			// A failing listener must not stop frame pacing.
		}
	}

	function clearSignals() {
		belowMaxSince = null;
		fallbackDeficitMs = 0;
		fallbackSurplusMs = 0;
		workHead = 0;
		workCount = 0;
		hasScaleSignal = false;
		scaleSignalAt = -Infinity;
	}

	/** Policy-initiated changes are rate-limited (one per minChangeInterval); returns false when deferred. */
	function applyCap(nextCap, reason, now, { policy = true } = {}) {
		if (nextCap === capFps) return false;
		if (policy && now - lastPolicyChangeAt < minChangeInterval()) return false;
		if (policy) lastPolicyChangeAt = now;
		const previous = { capFps, refreshHz };
		lastChange = Object.freeze({ from: capFps, to: nextCap, reason, at: now });
		capFps = nextCap;
		lastChangeAt = now;
		limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps });
		clearSignals();
		emit(reason, previous);
		return true;
	}

	/**
	 * A fixed setting above the Auto base on a gated device starts at the base and earns the target
	 * (iPhone 11: Auto 30, Smooth 60 opt-in). Returns the guard, or null for a plain fixed cap.
	 */
	function setupGuard() {
		guard = null;
		if (setting === "auto" || !gateEnabled()) return null;
		const target = resolveFixedFrameCap(setting, refreshHz, tuning.minFps);
		const floor = Math.min(target, baseCap());
		if (target <= floor + 0.01) return null;
		guard = { target, floor, underMs: 0, overMs: 0, cpuOk: false, slow: false, demotions: 0, waitMs: tuning.optInPromoteAfterMs, promotedAt: null };
		return guard;
	}

	/** Cap for the current setting after a (re)start: the Auto base, the guarded floor, or the fixed cap. */
	function startCap() {
		const gate = setupGuard();
		if (setting === "auto") return baseCap();
		return gate ? gate.floor : resolveFixedFrameCap(setting, refreshHz, tuning.minFps);
	}

	function resolveCapForRefresh(previousCap) {
		if (setting !== "auto") return startCap();
		const base = baseCap();
		if (previousCap === null) return base;
		// Keep a stepped-down cap across a refresh change; never jump above the base without a probe.
		return Math.min(base, nearestInLadder(previousCap, autoLadder()));
	}

	function syncRefresh(now) {
		const nextHz = estimator.refreshHz;
		const periodChanged = Math.abs(estimator.periodMs - limiter.periodMs) > 1e-6;
		if (nextHz === refreshHz) {
			if (periodChanged) limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps });
			return;
		}
		const previous = { capFps, refreshHz };
		refreshHz = nextHz;
		caps = allowedFrameCaps(refreshHz, tuning.minFps);
		if (probation) { probation = null; probeCredited = true; }
		const nextCap = resolveCapForRefresh(capFps);
		if (nextCap !== capFps) lastChange = Object.freeze({ from: capFps, to: nextCap, reason: "refresh-changed", at: now });
		capFps = nextCap;
		lastChangeAt = now;
		limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps });
		clearSignals();
		emit("refresh-changed", previous);
	}

	/** Quantile of recent CPU work per rendered frame (the paced requester's clock); null below 30 samples. */
	function workQuantile(q) {
		if (workCount < 30) return null;
		for (let i = 0; i < workCount; i++) workScratch[i] = workSamples[i];
		const sorted = workScratch.subarray(0, workCount).sort();
		return sorted[Math.min(workCount - 1, Math.floor(workCount * q))];
	}

	function windowedLoadRatio() {
		const p90 = workQuantile(0.9);
		return p90 === null ? null : p90 / limiter.intervalMs;
	}

	function updateFallback(interval) {
		if (interval === null) return;
		const achieved = limiter.achievedFps;
		if (achieved === null || limiter.windowFrames < 8) return;
		const late = limiter.lateRatio;
		fallbackDeficitMs = achieved < capFps * tuning.fallbackDeficitShare || late > tuning.fallbackLateRatio ? fallbackDeficitMs + interval : 0;
		fallbackSurplusMs = achieved >= capFps * tuning.fallbackSurplusShare && late <= tuning.fallbackCleanLateRatio ? fallbackSurplusMs + interval : 0;
	}

	/** The scale controller's state when fresh; otherwise the limiter's own view at a fixed scale. */
	function currentSignal(now) {
		if (hasScaleSignal && now - scaleSignalAt <= tuning.signalTimeoutMs) return scaleSignal;
		fallbackSignal.deficitMs = fallbackDeficitMs;
		fallbackSignal.surplusMs = fallbackSurplusMs;
		// No GPU-inclusive cost here; CPU work (windowedLoadRatio) is applied separately as a veto only.
		fallbackSignal.loadRatio = null;
		fallbackSignal.headroomKnown = false;
		fallbackSignal.targetFps = capFps;
		return fallbackSignal;
	}

	/** Doubles the back-off; the probe can no longer be credited as a success. */
	function chargeFailedProbe() {
		failedProbes++;
		consecutiveFailures++;
		probeCredited = true;
		probeDelayMs = Math.min(probeMax(), probeDelayMs * 2);
	}

	function failProbe(now, revertTo) {
		if (!applyCap(revertTo, "probe-failed", now)) return; // rate-limited: retried next frame
		chargeFailedProbe();
		probation = null;
	}

	/** From the third failure in a row the wait keeps doubling past the cap (to 30 min): a hard limit is not retried every few minutes. */
	function effectiveProbeDelay() {
		const extra = consecutiveFailures >= 3 ? 2 ** (consecutiveFailures - 2) : 1;
		return Math.min(tuning.probeBanMaxMs, probeDelayMs * extra);
	}

	function probeStillAccountable(now) {
		return !probeCredited && now - lastProbeAt <= tuning.probeFailWindowMs;
	}

	function noteSustainedDrop(now, heldMs) {
		if (heldMs < tuning.thermalStableMs) return;
		sustainedDrops.push(now);
		while (sustainedDrops.length > 0 && now - sustainedDrops[0] > tuning.thermalWindowMs) sustainedDrops.shift();
		if (sustainedDrops.length >= thermalStepDowns()) {
			thermalUntil = now + (formFactor === "mobile" ? tuning.mobileThermalHoldMs : tuning.thermalHoldMs);
			probeDelayMs = probeMax();
		}
	}

	function evaluateAuto(now) {
		if (setting !== "auto" || paused) return;
		if (estimator.phase === "detecting") return;
		if (estimator.needsProbe && needsProbeSince !== null && now - needsProbeSince < tuning.maxProbeFreezeMs) return;
		const signal = currentSignal(now);
		if (isPositiveFinite(signal.targetFps) && Math.abs(signal.targetFps - capFps) > 0.01) return;
		const ladder = autoLadder();
		let index = ladder.indexOf(capFps);
		if (index < 0) {
			applyCap(nearestInLadder(capFps, ladder), "ladder-changed", now, { policy: false });
			return;
		}
		const deficit = finiteOrZero(signal.deficitMs);
		const surplus = finiteOrZero(signal.surplusMs);
		const cannotFixWithScale = signal.atMin === true || signal.bound === "cpu";
		const sinceChange = lastChangeAt === null ? Infinity : now - lastChangeAt;
		const base = baseCap();
		const aboveBase = capFps > base + 0.01;
		belowMaxSince = aboveBase && signal.atMax !== true ? (belowMaxSince ?? now) : null;

		// A probe earns its success only after surviving the whole fail window; probation alone is too short.
		if (!probeCredited && now - lastProbeAt > tuning.probeFailWindowMs) {
			probeCredited = true;
			successfulProbes++;
			consecutiveFailures = 0;
			probeDelayMs = Math.max(probeBase(), probeDelayMs / 2);
		}

		if (probation) {
			if (deficit >= stepDownAfter() && cannotFixWithScale) { failProbe(now, probation.fromCap); return; }
			if (probation.aboveBase && (signal.atMax !== true || deficit >= tuning.probationDeficitMs)) { failProbe(now, probation.fromCap); return; }
			if (now - probation.startedAt >= tuning.probationMs) probation = null;
			return;
		}
		if (sinceChange < tuning.minDwellMs) return;

		// Above the tier base, frames are a bonus that must not cost resolution: yield a rung first.
		if (aboveBase && belowMaxSince !== null && now - belowMaxSince >= tuning.yieldAfterMs && index < ladder.length - 1) {
			const accountable = probeStillAccountable(now);
			if (applyCap(ladder[index + 1], "yield-to-resolution", now) && accountable) chargeFailedProbe();
			return;
		}

		if (deficit >= stepDownAfter() && cannotFixWithScale && index < ladder.length - 1) {
			const achieved = limiter.achievedFps ?? capFps;
			let target = ladder[index + 1];
			for (let i = index + 1; i < ladder.length; i++) {
				target = ladder[i];
				if (ladder[i] <= achieved * 1.05) break;
			}
			if (probeStillAccountable(now)) {
				if (applyCap(target, "probe-failed", now)) chargeFailedProbe();
			} else if (applyCap(target, "deficit", now)) {
				stepDowns++;
				noteSustainedDrop(now, sinceChange);
				probeDelayMs = Math.max(probeDelayMs, Math.min(probeMax(), probeBase() * 2));
			}
			return;
		}

		if (powerLimited() && capFps > base) { applyCap(base, "low-battery", now); return; }
		// Surplus earned during a thermal hold does not count: the wait starts when the hold ends.
		const usableSurplus = Math.min(surplus, now - thermalUntil);
		if (index === 0 || signal.atMax !== true || usableSurplus < effectiveProbeDelay() || now < thermalUntil) return;
		const next = ladder[index - 1];
		const nextAboveBase = next > base + 0.01;
		if (nextAboveBase && powerLimited()) return;
		// Any measured cost that predicts overload at the next rung vetoes the probe: the controller's loadRatio only
		// when it can see headroom (capped frames without a GPU timer read ~1 and mean "unknown"), and CPU work always
		// (a lower bound: CPU work alone cannot vouch for GPU headroom, so it never authorizes a probe).
		const measured = signal.headroomKnown === true && isPositiveFinite(signal.loadRatio) ? signal.loadRatio : 0;
		const cpu = windowedLoadRatio() ?? 0;
		if (Math.max(measured, cpu) * next / capFps >= tuning.probeLoadMax) return;
		// Above the base, a probe needs GPU-inclusive headroom unless blind probing is allowed (desktop: back-pressure shows failures).
		if (signal.headroomKnown !== true && nextAboveBase && !blindAboveBase()) return;
		const from = capFps;
		if (!applyCap(next, "probe", now)) return;
		probation = { fromCap: from, startedAt: now, aboveBase: nextAboveBase };
		lastProbeAt = now;
		probeCredited = false;
	}

	/** Guarded opt-in: a fixed setting above the Auto base on a gated device. Works from frame timings alone. */
	function evaluateGuard(now, interval) {
		if (!guard || paused || interval === null || estimator.phase === "detecting") return;
		const thermal = now < thermalUntil;
		guardFrames++;
		if (capFps !== guard.target) {
			// At the floor: earn the target with a sustained window of cheap CPU frames (Safari WebGL2 has no GPU timer).
			if (guardFrames % 10 === 0) {
				const cpu = workQuantile(0.95);
				guard.cpuOk = !thermal && !powerLimited() && cpu !== null && cpu <= tuning.optInPromoteShare * 1000 / guard.target;
			}
			guard.underMs = guard.cpuOk ? guard.underMs + interval : 0;
			if (guard.underMs >= guard.waitMs && applyCap(guard.target, "opt-in-promote", now)) {
				guard.promotedAt = now;
				guard.underMs = 0;
				guard.overMs = 0;
				guard.slow = false;
			}
			return;
		}
		// At the target: fall back after sustained slow frames, or as soon as thermal throttling is suspected.
		if (guardFrames % 10 === 0) {
			const p95 = limiter.intervalQuantile(0.95, 60);
			guard.slow = p95 !== null && p95 > tuning.optInDemoteShare * 1000 / guard.target;
		}
		guard.overMs = guard.slow ? guard.overMs + interval : 0;
		if (thermal || guard.overMs >= tuning.optInDemoteAfterMs) {
			const held = guard.promotedAt === null ? 0 : now - guard.promotedAt;
			if (!applyCap(guard.floor, thermal ? "opt-in-thermal" : "opt-in-fallback", now)) return;
			guard.demotions++;
			guard.waitMs = Math.min(tuning.probeBanMaxMs, tuning.optInPromoteAfterMs * 2 ** guard.demotions);
			guard.underMs = 0;
			guard.overMs = 0;
			guard.cpuOk = false;
			stepDowns++;
			if (!thermal) noteSustainedDrop(now, held);
			return;
		}
		if (guard.demotions > 0 && guard.promotedAt !== null && now - guard.promotedAt >= tuning.optInStableMs) {
			guard.demotions = 0;
			guard.waitMs = tuning.optInPromoteAfterMs;
		}
	}

	function restartAuto(now, reason) {
		probation = null;
		probeCredited = true;
		consecutiveFailures = 0;
		lastProbeAt = -Infinity;
		probeDelayMs = probeBase();
		const previous = { capFps, refreshHz };
		const next = startCap();
		if (next !== capFps) lastChange = Object.freeze({ from: capFps, to: next, reason, at: now });
		capFps = next;
		lastChangeAt = now;
		limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps });
		clearSignals();
		emit(reason, previous);
	}

	capFps = startCap();
	limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps });

	return {
		frame(timestampMs) {
			if (typeof timestampMs !== "number" || !Number.isFinite(timestampMs)) return true;
			if (paused) return false;
			lastTimestamp = timestampMs;
			estimator.addFrame(timestampMs, lastRendered);
			syncRefresh(timestampMs);
			if (estimator.needsProbe) {
				if (needsProbeSince === null) needsProbeSince = timestampMs;
				if (timestampMs - estimatorProbeAt >= estimatorProbeGapMs) {
					limiter.requestIdleFrame();
					estimatorProbeAt = timestampMs;
					estimatorProbeGapMs = Math.min(5000, estimatorProbeGapMs * 1.2);
				}
			} else {
				needsProbeSince = null;
				estimatorProbeGapMs = tuning.estimatorProbeGapMs;
			}
			const render = limiter.shouldRender(timestampMs);
			lastRendered = render;
			if (render) {
				// While the refresh rate is in question (detecting, or idle-frame probes pending) the interval may
				// reflect a throttled rAF rather than frame cost: withhold it so the scale controller does not react.
				lastFrameIntervalMs = estimator.phase === "detecting" || estimator.needsProbe ? null : limiter.lastIntervalMs;
				updateFallback(lastFrameIntervalMs);
				if (lastChangeAt === null) lastChangeAt = timestampMs;
				evaluateAuto(timestampMs);
				evaluateGuard(timestampMs, lastFrameIntervalMs);
			}
			return render;
		},
		recordWork(workMs) {
			if (!isPositiveFinite(workMs)) return;
			workSamples[workHead] = Math.min(workMs, 1000);
			workHead = (workHead + 1) % workSamples.length;
			if (workCount < workSamples.length) workCount++;
		},
		observeScale(signal, nowMs) {
			if (signal === null || signal === undefined) { hasScaleSignal = false; scaleSignalAt = -Infinity; return; }
			if (typeof signal !== "object") return;
			scaleSignal.atMin = signal.atMin === true;
			scaleSignal.atMax = signal.atMax === true;
			scaleSignal.deficitMs = finiteOrZero(signal.deficitMs);
			scaleSignal.surplusMs = finiteOrZero(signal.surplusMs);
			scaleSignal.loadRatio = isPositiveFinite(signal.loadRatio) ? signal.loadRatio : null;
			scaleSignal.headroomKnown = signal.headroomKnown === true;
			scaleSignal.bound = signal.bound === "gpu" || signal.bound === "cpu" ? signal.bound : "unknown";
			scaleSignal.targetFps = isPositiveFinite(signal.targetFps) ? signal.targetFps : null;
			hasScaleSignal = true;
			scaleSignalAt = isPositiveFinite(nowMs) ? nowMs : (lastTimestamp ?? 0);
		},
		setSetting(value, nowMs) {
			const next = normalizeFrameRateSetting(value);
			if (next === setting) return setting;
			setting = next;
			restartAuto(isPositiveFinite(nowMs) ? nowMs : (lastTimestamp ?? 0), "setting-changed");
			return setting;
		},
		setTier(tier, nowMs) {
			const value = typeof tier === "object" && tier !== null ? tier : {};
			const target = isPositiveFinite(value.targetFps) ? value.targetFps : tierTargetFps;
			const factor = value.formFactor === undefined ? formFactor : normalizeFormFactor(value.formFactor);
			const ceiling = value.autoCeilingFps === undefined ? tierCeilingFps : (isPositiveFinite(value.autoCeilingFps) ? value.autoCeilingFps : 0);
			if (target === tierTargetFps && factor === formFactor && ceiling === tierCeilingFps) return false;
			tierTargetFps = target;
			formFactor = factor;
			tierCeilingFps = ceiling;
			if (setting === "auto" || gateEnabled() || guard !== null) restartAuto(isPositiveFinite(nowMs) ? nowMs : (lastTimestamp ?? 0), "tier-changed");
			return true;
		},
		setPowerHints(hints) {
			const value = typeof hints === "object" && hints !== null ? hints : {};
			powerHints = Object.freeze({ lowBattery: value.lowBattery === true, charging: typeof value.charging === "boolean" ? value.charging : null });
		},
		notifyVisibility(hidden, nowMs) {
			const now = isPositiveFinite(nowMs) ? nowMs : (lastTimestamp ?? 0);
			if (hidden === true) {
				if (paused) return;
				paused = true;
				limiter.setPaused(true);
				if (probation) {
					// A probe interrupted by hiding proves nothing: return to the cap it started from.
					const from = probation.fromCap;
					probation = null;
					probeCredited = true;
					if (from !== capFps) { lastChange = Object.freeze({ from: capFps, to: from, reason: "hidden", at: now }); capFps = from; limiter.configure({ refreshHz, periodMs: estimator.periodMs, capFps }); }
				}
				emit("hidden", { capFps, refreshHz });
				return;
			}
			if (!paused) return;
			paused = false;
			estimator.reset("visible");
			limiter.setPaused(false);
			lastRendered = false;
			lastFrameIntervalMs = null;
			lastChangeAt = now;
			clearSignals();
			emit("visible", { capFps, refreshHz });
		},
		notifyResize() {
			estimator.reset("resize");
			lastFrameIntervalMs = null;
		},
		notifyScreenChange(nowMs) {
			estimator.reset("screen-change", { forgetPrior: true });
			limiter.reset();
			lastRendered = false;
			lastFrameIntervalMs = null;
			lastChangeAt = isPositiveFinite(nowMs) ? nowMs : (lastTimestamp ?? lastChangeAt);
		},
		get targetFps() { return capFps; },
		get capFps() { return capFps; },
		get intervalMs() { return limiter.intervalMs; },
		get lastFrameIntervalMs() { return lastFrameIntervalMs; },
		get paused() { return paused; },
		state() {
			const estimate = estimator.state();
			const ladder = autoLadder();
			return Object.freeze({
				setting,
				mode: setting === "auto" ? "auto" : "fixed",
				formFactor,
				tierTargetFps,
				tierCeilingFps: tierCeilingFps > 0 ? tierCeilingFps : null,
				minFps: tuning.minFps,
				refreshHz,
				refreshDetected: estimate.detected,
				refreshPhase: estimate.phase,
				periodMs: estimate.periodMs,
				maxRefreshHz: estimate.maxSeenHz,
				throttled: estimate.throttled,
				/** A 30 Hz rAF: iOS Low Power Mode, Chrome Energy Saver or another OS limit. It is the ceiling. */
				lowPowerSuspected: estimate.throttled,
				/** Perf-overlay names (iPhone 11 target doc §7.3): the raw rAF rate and the browser-cap flag. */
				rafHz: refreshHz,
				browserCap30: estimate.throttled,
				optIn: guard ? Object.freeze({ targetFps: guard.target, floorFps: guard.floor, promoted: capFps === guard.target, waitMs: guard.waitMs, demotions: guard.demotions }) : null,
				needsProbe: estimate.needsProbe,
				allowedCaps: caps,
				autoLadder: Object.freeze([...ladder]),
				autoBaseCapFps: baseCap(),
				autoCeilingFps: Number.isFinite(autoCeiling()) ? autoCeiling() : null,
				capFps,
				targetFps: capFps,
				intervalMs: limiter.intervalMs,
				divisor: limiter.divisor,
				paused,
				probation: probation ? Object.freeze({ ...probation }) : null,
				probeDelayMs,
				effectiveProbeDelayMs: effectiveProbeDelay(),
				consecutiveFailedProbes: consecutiveFailures,
				failedProbes,
				successfulProbes,
				stepDowns,
				thermalSuspected: lastTimestamp !== null && lastTimestamp < thermalUntil,
				powerLimited: powerLimited(),
				scaleSignal: hasScaleSignal && lastTimestamp !== null && lastTimestamp - scaleSignalAt <= tuning.signalTimeoutMs ? "scale-controller" : "limiter",
				lastChange,
				lastFrameIntervalMs,
				limiter: limiter.stats(),
				estimator: estimate,
			});
		},
	};
}

/**
 * Adapter for Babylon's `engine.customAnimationFrameRequester`. Babylon calls
 * `requestAnimationFrame`/`cancelAnimationFrame` destructured (no `this`), so
 * both are closures. Every native callback goes through `policy.frame()`; a
 * skipped vsync re-requests natively and never reaches the engine, so
 * beginFrame, getDeltaTime() and scene animation run only for rendered frames.
 *
 * @param {PacedFrameRequesterOptions} options
 * @returns {PacedFrameRequester}
 */
export function createPacedFrameRequester(options) {
	const policy = options?.policy;
	const requestFrame = options?.requestFrame;
	const cancelFrame = options?.cancelFrame;
	if (!policy || typeof policy.frame !== "function") throw new TypeError("A frame-rate policy is required.");
	if (typeof requestFrame !== "function" || typeof cancelFrame !== "function") throw new TypeError("requestFrame and cancelFrame must be functions.");
	const clock = typeof options.now === "function" ? options.now : null;
	let pending = null;
	let pendingId = 0;
	let nextId = 0;
	let nativeHandle = null;
	let disposed = false;

	const onNativeFrame = timestamp => {
		nativeHandle = null;
		if (disposed || pending === null) return;
		let render = true;
		try { render = policy.frame(timestamp) !== false; } catch { render = true; }
		if (!render) {
			nativeHandle = requestFrame(onNativeFrame);
			return;
		}
		const callback = pending;
		pending = null;
		const started = clock ? clock() : 0;
		try {
			callback(timestamp);
		} finally {
			if (clock && typeof policy.recordWork === "function") policy.recordWork(clock() - started);
		}
	};

	return {
		requestAnimationFrame(callback) {
			if (typeof callback !== "function") throw new TypeError("requestAnimationFrame needs a callback.");
			pending = callback;
			pendingId = ++nextId;
			if (nativeHandle === null && !disposed) nativeHandle = requestFrame(onNativeFrame);
			return pendingId;
		},
		cancelAnimationFrame(id) {
			if (id !== undefined && id !== pendingId) return;
			pending = null;
			if (nativeHandle !== null) {
				cancelFrame(nativeHandle);
				nativeHandle = null;
			}
		},
		dispose() {
			disposed = true;
			pending = null;
			if (nativeHandle !== null) {
				cancelFrame(nativeHandle);
				nativeHandle = null;
			}
		},
		get pending() { return pending !== null; },
	};
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Median-centred mean of the intervals within +-25% of the median. @param {Float64Array} sorted */
function robustPeriod(sorted) {
	const n = sorted.length;
	if (n === 0) return null;
	const median = n % 2 === 1 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
	if (!(median > 0)) return null;
	let sum = 0;
	let inliers = 0;
	for (let i = 0; i < n; i++) {
		const value = sorted[i];
		if (value >= median * 0.75 && value <= median * 1.25) { sum += value; inliers++; }
	}
	if (inliers < 3) return null;
	return { periodMs: sum / inliers, support: inliers / n };
}

/**
 * The fastest well-supported cluster: when at least `minSupport` of the
 * intervals sit below 0.75 of the median, the vsync is that faster cluster
 * and the rest are frames that missed it.
 * @param {Float64Array} sorted @param {number} minSupport
 */
function lowestCluster(sorted, minSupport) {
	const n = sorted.length;
	if (n < 3) return null;
	const median = n % 2 === 1 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
	let fast = 0;
	while (fast < n && sorted[fast] <= median * 0.75) fast++;
	if (fast >= 3 && fast >= minSupport * n) {
		const cluster = robustPeriod(sorted.subarray(0, fast));
		return cluster ? { periodMs: cluster.periodMs, support: (cluster.support * fast) / n } : null;
	}
	return robustPeriod(sorted);
}

/**
 * Nearest rung by frame time; an exact frame-time tie (60 on 90 Hz: 11.1 vs
 * 22.2 ms around 16.7 ms) goes to the rung nearer in fps, then to the lower.
 * @param {number} requestedFps @param {readonly number[]} ladder descending
 */
function nearestInLadder(requestedFps, ladder) {
	if (!isPositiveFinite(requestedFps)) return ladder[0];
	const target = 1000 / requestedFps;
	let best = ladder[0];
	let bestError = Infinity;
	for (const cap of ladder) {
		const error = Math.abs(1000 / cap - target);
		if (error < bestError - 1e-6) { best = cap; bestError = error; continue; }
		if (Math.abs(error - bestError) <= 1e-6) {
			const fpsError = Math.abs(cap - requestedFps);
			const bestFpsError = Math.abs(best - requestedFps);
			if (fpsError < bestFpsError - 1e-6 || (Math.abs(fpsError - bestFpsError) <= 1e-6 && cap < best)) best = cap;
		}
	}
	return best;
}

function normalizeEstimatorOptions(options) {
	const input = typeof options === "object" && options !== null ? options : {};
	const pick = (key, min, max) => clampNumber(input[key], min, max, REFRESH_ESTIMATOR_DEFAULTS[key]);
	const windowSize = Math.round(pick("windowSize", 16, 1024));
	return {
		initialHz: pick("initialHz", 1, 1000),
		windowSize,
		recentSize: Math.min(windowSize, Math.round(pick("recentSize", 8, 1024))),
		minSamples: Math.min(windowSize, Math.round(pick("minSamples", 4, 1024))),
		minCleanSamples: Math.min(windowSize, Math.round(pick("minCleanSamples", 3, 1024))),
		minConfirmCleanSamples: Math.min(windowSize, Math.round(pick("minConfirmCleanSamples", 2, 1024))),
		evaluateEvery: Math.round(pick("evaluateEvery", 1, 1024)),
		minIntervalMs: pick("minIntervalMs", 0, 50),
		maxIntervalMs: pick("maxIntervalMs", 50, 10000),
		raiseSupport: pick("raiseSupport", 0.05, 1),
		confirmEvaluations: Math.round(pick("confirmEvaluations", 1, 20)),
		snapTolerance: pick("snapTolerance", 0, 0.5),
		cleanWindow: Math.round(pick("cleanWindow", 4, 1024)),
		cleanMaxAgeMs: pick("cleanMaxAgeMs", 100, 600_000),
		staleCleanMs: pick("staleCleanMs", 50, 600_000),
		loadHoldMs: pick("loadHoldMs", 0, 3_600_000),
		maxLoadHoldMs: Math.max(pick("loadHoldMs", 0, 3_600_000), pick("maxLoadHoldMs", 0, 3_600_000)),
	};
}

function normalizePolicyOptions(options) {
	const pick = (key, min, max) => clampNumber(options[key], min, max, FRAME_RATE_POLICY_DEFAULTS[key]);
	const flag = key => typeof options[key] === "boolean" ? options[key] : FRAME_RATE_POLICY_DEFAULTS[key];
	const desktopProbe = pick("desktopProbeUpAfterMs", 0, 3_600_000);
	const mobileProbe = pick("mobileProbeUpAfterMs", 0, 3_600_000);
	return {
		minFps: pick("minFps", 1, 240),
		mobileAutoCeilingFps: pick("mobileAutoCeilingFps", 0, 1000),
		desktopAutoCeilingFps: pick("desktopAutoCeilingFps", 0, 1000),
		stepDownAfterMs: pick("stepDownAfterMs", 0, 600_000),
		mobileStepDownAfterMs: pick("mobileStepDownAfterMs", 0, 600_000),
		desktopMinChangeIntervalMs: pick("desktopMinChangeIntervalMs", 0, 600_000),
		mobileMinChangeIntervalMs: pick("mobileMinChangeIntervalMs", 0, 600_000),
		mobileThermalStepDowns: Math.round(pick("mobileThermalStepDowns", 1, 20)),
		desktopThermalStepDowns: Math.round(pick("desktopThermalStepDowns", 1, 20)),
		mobileFixedGate: flag("mobileFixedGate"),
		desktopFixedGate: flag("desktopFixedGate"),
		optInPromoteAfterMs: pick("optInPromoteAfterMs", 0, 3_600_000),
		optInPromoteShare: pick("optInPromoteShare", 0.05, 4),
		optInDemoteAfterMs: pick("optInDemoteAfterMs", 0, 600_000),
		optInDemoteShare: pick("optInDemoteShare", 0.5, 4),
		optInStableMs: pick("optInStableMs", 0, 86_400_000),
		minDwellMs: pick("minDwellMs", 0, 600_000),
		desktopProbeUpAfterMs: desktopProbe,
		mobileProbeUpAfterMs: mobileProbe,
		desktopMaxProbeUpAfterMs: Math.max(desktopProbe, pick("desktopMaxProbeUpAfterMs", 0, 3_600_000)),
		mobileMaxProbeUpAfterMs: Math.max(mobileProbe, pick("mobileMaxProbeUpAfterMs", 0, 3_600_000)),
		probationMs: pick("probationMs", 0, 600_000),
		probationDeficitMs: pick("probationDeficitMs", 0, 600_000),
		yieldAfterMs: pick("yieldAfterMs", 0, 600_000),
		probeFailWindowMs: pick("probeFailWindowMs", 0, 3_600_000),
		probeLoadMax: pick("probeLoadMax", 0.05, 4),
		probeBanMaxMs: pick("probeBanMaxMs", 0, 86_400_000),
		desktopBlindProbeAboveBase: flag("desktopBlindProbeAboveBase"),
		mobileBlindProbeAboveBase: flag("mobileBlindProbeAboveBase"),
		thermalWindowMs: pick("thermalWindowMs", 0, 86_400_000),
		thermalStableMs: pick("thermalStableMs", 0, 86_400_000),
		thermalHoldMs: pick("thermalHoldMs", 0, 86_400_000),
		mobileThermalHoldMs: pick("mobileThermalHoldMs", 0, 86_400_000),
		estimatorProbeGapMs: pick("estimatorProbeGapMs", 16, 60_000),
		maxProbeFreezeMs: pick("maxProbeFreezeMs", 0, 600_000),
		signalTimeoutMs: pick("signalTimeoutMs", 100, 600_000),
		fallbackDeficitShare: pick("fallbackDeficitShare", 0.1, 1),
		fallbackLateRatio: pick("fallbackLateRatio", 0, 1),
		fallbackSurplusShare: pick("fallbackSurplusShare", 0.1, 1),
		fallbackCleanLateRatio: pick("fallbackCleanLateRatio", 0, 1),
	};
}

/** @param {unknown} value @returns {"mobile" | "desktop" | "unknown"} */
function normalizeFormFactor(value) {
	return value === "mobile" || value === "desktop" ? value : "unknown";
}

function roundFps(value) {
	return Math.round(value * FPS_PRECISION) / FPS_PRECISION;
}

function isPositiveFinite(value) {
	return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function finiteOrZero(value) {
	return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0;
}

function clampNumber(value, min, max, fallback) {
	if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
	return Math.min(max, Math.max(min, value));
}

/** @typedef {import("./frame-rate-policy.d.mts").FrameRateSetting} FrameRateSetting */
/** @typedef {import("./frame-rate-policy.d.mts").FrameRateOption} FrameRateOption */
/** @typedef {import("./frame-rate-policy.d.mts").RefreshEstimatorOptions} RefreshEstimatorOptions */
/** @typedef {import("./frame-rate-policy.d.mts").RefreshRateEstimator} RefreshRateEstimator */
/** @typedef {import("./frame-rate-policy.d.mts").FrameLimiterOptions} FrameLimiterOptions */
/** @typedef {import("./frame-rate-policy.d.mts").FrameLimiter} FrameLimiter */
/** @typedef {import("./frame-rate-policy.d.mts").FrameRatePolicyOptions} FrameRatePolicyOptions */
/** @typedef {import("./frame-rate-policy.d.mts").FrameRatePolicy} FrameRatePolicy */
/** @typedef {import("./frame-rate-policy.d.mts").FrameRatePolicyState} FrameRatePolicyState */
/** @typedef {import("./frame-rate-policy.d.mts").PacedFrameRequesterOptions} PacedFrameRequesterOptions */
/** @typedef {import("./frame-rate-policy.d.mts").PacedFrameRequester} PacedFrameRequester */
