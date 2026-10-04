/** What the player picks: Auto, a target, or Max (the refresh rate). Numbers are clamped to 30..1000. */
export type FrameRateSetting = "auto" | "max" | number;
export type FrameRateFormFactor = "mobile" | "desktop" | "unknown";

export const KNOWN_REFRESH_RATES: readonly number[];
/** The settings UI's options in display order: "auto", 30, 60, 90, 120, "max". */
export const FRAME_RATE_SETTINGS: readonly ("auto" | "max" | 30 | 60 | 90 | 120)[];
export const FRAME_RATE_STORAGE_KEY: "aetherfield_frame_rate_v1";
/** The settings UI dispatches this on window with `detail: { setting }` after persisting. */
export const FRAME_RATE_SETTING_EVENT: "aetherfield:frame-rate-setting-change";
/** The renderer dispatches this on window with a small state DTO on cap or refresh changes. */
export const FRAME_RATE_STATE_EVENT: "aetherfield:frame-rate-state";
export const MIN_FRAME_CAP_FPS: 30;

/** Snaps to the nearest known rate within `tolerance` (relative, default 0.05); otherwise rounds. Null for invalid input. */
export function snapRefreshRate(hz: number, tolerance?: number): number | null;
/** Evenly paced caps, descending: the refresh rate divided by 1, 2, 3, ... while >= minFps. */
export function allowedFrameCaps(refreshHz: number, minFps?: number): readonly number[];
/** Nearest allowed cap by frame time; exact ties go to the cap nearer in fps, then the lower. */
export function nearestAllowedCap(requestedFps: number, refreshHz: number, minFps?: number): number;
export function normalizeFrameRateSetting(value: unknown): FrameRateSetting;
/** Cap for a fixed setting on a refresh rate ("auto" and "max" give the refresh rate). */
export function resolveFixedFrameCap(setting: FrameRateSetting, refreshHz: number, minFps?: number): number;
/** Reads the versioned JSON written by serializeFrameRateSetting; anything else is "auto". */
export function parseStoredFrameRateSetting(raw: unknown): FrameRateSetting;
export function serializeFrameRateSetting(setting: FrameRateSetting): string;

export interface FrameRateOption {
	readonly value: "auto" | "max" | 30 | 60 | 90 | 120;
	/** The cap this option gives on the current screen. */
	readonly capFps: number;
	/** False when the screen cannot pace the requested number evenly (60 on 144 Hz gives 72). */
	readonly exact: boolean;
	readonly selected: boolean;
}
/** Data for the settings UI; copy and translation live in the UI. */
export function describeFrameRateOptions(state: FrameRatePolicyState): readonly FrameRateOption[];

// ---------------------------------------------------------------------------
// Refresh estimation
// ---------------------------------------------------------------------------

export interface RefreshEstimatorOptions {
	initialHz: number;
	windowSize: number;
	recentSize: number;
	minSamples: number;
	minCleanSamples: number;
	minConfirmCleanSamples: number;
	evaluateEvery: number;
	minIntervalMs: number;
	maxIntervalMs: number;
	raiseSupport: number;
	confirmEvaluations: number;
	snapTolerance: number;
	cleanWindow: number;
	cleanMaxAgeMs: number;
	staleCleanMs: number;
	loadHoldMs: number;
	maxLoadHoldMs: number;
}
export const REFRESH_ESTIMATOR_DEFAULTS: Readonly<RefreshEstimatorOptions>;

export interface RefreshEstimatorState {
	readonly phase: "detecting" | "locked";
	readonly detected: boolean;
	/** The rate rAF is delivered at (snapped); provisional until `detected`. */
	readonly refreshHz: number;
	/** Measured vsync period used by the limiter. */
	readonly periodMs: number;
	/** "clean": proven by idle-start intervals; "loaded": inferred from rendered frames. */
	readonly source: "initial" | "clean" | "loaded";
	readonly maxSeenHz: number | null;
	/** A 30 Hz rAF proven by idle frames: Low Power Mode, Energy Saver or an OS limit. */
	readonly throttled: boolean;
	/** The host should skip one render so the next interval measures vsync. */
	readonly needsProbe: boolean;
	readonly samples: number;
	readonly changes: number;
	readonly stalls: number;
	readonly lastReason: string;
}

export interface RefreshRateEstimator {
	/** One call per rAF callback; `previousFrameRendered` is whether the previous callback rendered. */
	addFrame(timestampMs: number, previousFrameRendered: boolean): void;
	/** Re-detect. `forgetPrior` after a screen change: the old rate is no evidence. */
	reset(reason?: string, options?: { forgetPrior?: boolean }): void;
	readonly refreshHz: number;
	readonly periodMs: number;
	readonly phase: "detecting" | "locked";
	readonly needsProbe: boolean;
	readonly detected: boolean;
	state(): RefreshEstimatorState;
}
export function createRefreshRateEstimator(options?: Partial<RefreshEstimatorOptions>): RefreshRateEstimator;

// ---------------------------------------------------------------------------
// Frame limiter
// ---------------------------------------------------------------------------

export interface FrameLimiterOptions {
	/** Share of the phase error folded into the deadline each on-time frame (PLL gain), 0..1. */
	phaseGain: number;
	statsWindow: number;
	/** A deadline missed by more than this re-anchors without counting drops. */
	stallMs: number;
}
export const FRAME_LIMITER_DEFAULTS: Readonly<FrameLimiterOptions>;

export interface FrameLimiterTarget {
	refreshHz?: number;
	/** Measured vsync period; defaults to 1000 / refreshHz. */
	periodMs?: number;
	/** Should be one of allowedFrameCaps(refreshHz); the limiter renders every round(refreshHz / capFps) vsyncs. */
	capFps?: number;
}

export interface FrameLimiterStats {
	readonly rendered: number;
	readonly skipped: number;
	/** Rendered at least one vsync after the deadline. */
	readonly late: number;
	/** Whole intervals that never rendered. */
	readonly dropped: number;
	readonly stalls: number;
	readonly probes: number;
	readonly capFps: number;
	readonly refreshHz: number;
	readonly divisor: number;
	readonly intervalMs: number;
	/** Windowed over the last `statsWindow` rendered intervals. */
	readonly achievedFps: number | null;
	readonly meanIntervalMs: number | null;
	readonly jitterMs: number | null;
	readonly lateRatio: number;
	readonly windowFrames: number;
	readonly lastIntervalMs: number | null;
}

export interface FrameLimiter {
	/** Render when now >= deadline - vsync/2; the deadline advances by whole intervals. */
	shouldRender(nowMs: number): boolean;
	/** Returns true when the change re-anchored the grid (refresh, divisor or cap changed). */
	configure(target: FrameLimiterTarget): boolean;
	/** Skip the next frame that would render, so the following interval starts idle. */
	requestIdleFrame(): void;
	setPaused(paused: boolean): void;
	reset(): void;
	readonly intervalMs: number;
	readonly periodMs: number;
	readonly divisor: number;
	readonly capFps: number;
	readonly refreshHz: number;
	readonly paused: boolean;
	/** Interval since the previous rendered frame; null after a re-anchor, probe or stall. */
	readonly lastIntervalMs: number | null;
	readonly achievedFps: number | null;
	readonly lateRatio: number;
	readonly windowFrames: number;
	/** Quantile of the newest `lastN` rendered intervals (probe and stall intervals excluded); null below 8 samples. */
	intervalQuantile(q: number, lastN?: number): number | null;
	stats(): FrameLimiterStats;
}
export function createFrameLimiter(options?: Partial<FrameLimiterOptions> & FrameLimiterTarget): FrameLimiter;

// ---------------------------------------------------------------------------
// Policy
// ---------------------------------------------------------------------------

/**
 * Structural view of render-scale-controller.mjs `state()`; that object can be
 * passed directly. Fields mean: scale at the floor / ceiling of its range,
 * continuous deficit time the scale could not fix (at min or CPU-bound),
 * continuous clean time at max scale, and measured cost over the target interval.
 */
export interface FrameRateScaleSignal {
	readonly atMin: boolean;
	readonly atMax: boolean;
	readonly deficitMs: number;
	readonly surplusMs: number;
	readonly loadRatio?: number | null;
	readonly headroomKnown?: boolean;
	readonly bound?: "gpu" | "cpu" | "unknown";
	/** The target the signal was measured against; a mismatch with the policy's cap marks it stale. */
	readonly targetFps?: number | null;
}

export interface FrameRatePowerHints {
	/** For example Battery Status level <= 0.2 (Chromium only). */
	lowBattery?: boolean;
	charging?: boolean | null;
}

export interface FrameRatePolicyTuning {
	minFps: number;
	mobileAutoCeilingFps: number;
	/** 0 means the refresh rate. */
	desktopAutoCeilingFps: number;
	stepDownAfterMs: number;
	mobileStepDownAfterMs: number;
	/** At most one policy-initiated cap change per interval (Mobile Safari churn guard). */
	desktopMinChangeIntervalMs: number;
	mobileMinChangeIntervalMs: number;
	mobileThermalStepDowns: number;
	desktopThermalStepDowns: number;
	/** Guarded opt-in for a fixed setting above the Auto base (iPhone 11 "Smooth 60"). */
	mobileFixedGate: boolean;
	desktopFixedGate: boolean;
	optInPromoteAfterMs: number;
	/** CPU p95 must be <= this share of the target interval (0.84: 14 ms at 60). */
	optInPromoteShare: number;
	optInDemoteAfterMs: number;
	/** Frame-interval p95 above this share of the target interval falls back (1.08: 18 ms at 60). */
	optInDemoteShare: number;
	optInStableMs: number;
	minDwellMs: number;
	desktopProbeUpAfterMs: number;
	mobileProbeUpAfterMs: number;
	desktopMaxProbeUpAfterMs: number;
	mobileMaxProbeUpAfterMs: number;
	probationMs: number;
	probationDeficitMs: number;
	yieldAfterMs: number;
	probeFailWindowMs: number;
	probeBanMaxMs: number;
	probeLoadMax: number;
	desktopBlindProbeAboveBase: boolean;
	mobileBlindProbeAboveBase: boolean;
	thermalWindowMs: number;
	thermalStableMs: number;
	thermalHoldMs: number;
	mobileThermalHoldMs: number;
	estimatorProbeGapMs: number;
	maxProbeFreezeMs: number;
	signalTimeoutMs: number;
	fallbackDeficitShare: number;
	fallbackLateRatio: number;
	fallbackSurplusShare: number;
	fallbackCleanLateRatio: number;
}
export const FRAME_RATE_POLICY_DEFAULTS: Readonly<FrameRatePolicyTuning>;

export interface FrameRatePolicyChange {
	readonly reason: string;
	readonly capFps: number;
	readonly refreshHz: number;
	readonly paused: boolean;
	readonly previousCapFps: number | null;
	readonly previousRefreshHz: number | null;
}

export interface FrameRatePolicyOptions extends FrameRatePolicyTuning {
	setting: FrameRateSetting;
	/** graphics-quality resolved targetFps (after mobile ceilings): the Auto base. */
	tierTargetFps: number;
	/** graphics-quality autoCeilingFps: highest cap Auto may probe to on this tier; 0 = the refresh rate. */
	autoCeilingFps: number;
	formFactor: FrameRateFormFactor;
	/** Provisional rate until detection (default 60). */
	initialRefreshHz: number;
	estimator: Partial<RefreshEstimatorOptions>;
	limiter: Partial<FrameLimiterOptions>;
	/** Called synchronously on refresh, cap, setting and visibility changes; errors are swallowed. */
	onChange: (change: FrameRatePolicyChange) => void;
}

export interface FrameRatePolicyState {
	readonly setting: FrameRateSetting;
	readonly mode: "auto" | "fixed";
	readonly formFactor: FrameRateFormFactor;
	readonly tierTargetFps: number;
	readonly tierCeilingFps: number | null;
	readonly minFps: number;
	/** rAF delivery rate in use (provisional 60 until refreshDetected). */
	readonly refreshHz: number;
	readonly refreshDetected: boolean;
	readonly refreshPhase: "detecting" | "locked";
	readonly periodMs: number;
	readonly maxRefreshHz: number | null;
	readonly throttled: boolean;
	/** A 30 Hz rAF proven by idle frames: treat as Low Power Mode / Energy Saver; it is the ceiling. */
	readonly lowPowerSuspected: boolean;
	/** Same as refreshHz, under the perf overlay's name. */
	readonly rafHz: number;
	/** Same as throttled, under the perf overlay's name: a browser cap below 40 Hz (Low Power Mode, idle page, media session, untapped cross-origin iframe, Energy Saver). */
	readonly browserCap30: boolean;
	/** Guarded opt-in state for a fixed setting above the Auto base; null when not gated. */
	readonly optIn: Readonly<{ targetFps: number; floorFps: number; promoted: boolean; waitMs: number; demotions: number }> | null;
	readonly needsProbe: boolean;
	readonly allowedCaps: readonly number[];
	readonly autoLadder: readonly number[];
	readonly autoBaseCapFps: number;
	readonly autoCeilingFps: number | null;
	readonly capFps: number;
	/** Same as capFps: what the render-scale controller must hold. */
	readonly targetFps: number;
	readonly intervalMs: number;
	readonly divisor: number;
	readonly paused: boolean;
	readonly probation: Readonly<{ fromCap: number; startedAt: number; aboveBase: boolean }> | null;
	readonly probeDelayMs: number;
	readonly effectiveProbeDelayMs: number;
	readonly consecutiveFailedProbes: number;
	readonly failedProbes: number;
	readonly successfulProbes: number;
	readonly stepDowns: number;
	readonly thermalSuspected: boolean;
	readonly powerLimited: boolean;
	/** Which signal Auto used: the render-scale controller, or the limiter's own stats at a fixed scale. */
	readonly scaleSignal: "scale-controller" | "limiter";
	readonly lastChange: Readonly<{ from: number; to: number; reason: string; at: number }> | null;
	readonly lastFrameIntervalMs: number | null;
	readonly limiter: FrameLimiterStats;
	readonly estimator: RefreshEstimatorState;
}

export interface FrameRatePolicy {
	/** Every native rAF callback: feeds the estimator, runs Auto, returns whether to render this vsync. */
	frame(timestampMs: number): boolean;
	/** CPU time of a rendered frame (the paced requester measures it when given a clock). */
	recordWork(workMs: number): void;
	/** Latest render-scale-controller state once per rendered frame; null switches to the limiter fallback. */
	observeScale(signal: FrameRateScaleSignal | null, nowMs?: number): void;
	setSetting(setting: FrameRateSetting | string, nowMs?: number): FrameRateSetting;
	/** Graphics tier changed: new Auto base and ceiling; Auto restarts from the base. Returns false when nothing changed. */
	setTier(tier: { targetFps?: number; formFactor?: FrameRateFormFactor; autoCeilingFps?: number }, nowMs?: number): boolean;
	setPowerHints(hints: FrameRatePowerHints): void;
	/** Page hidden: pause. Visible again: resume and re-detect the refresh rate. */
	notifyVisibility(hidden: boolean, nowMs?: number): void;
	notifyResize(nowMs?: number): void;
	/** Window moved to another display, or devicePixelRatio changed: re-detect without trusting the old rate. */
	notifyScreenChange(nowMs?: number): void;
	readonly targetFps: number;
	readonly capFps: number;
	readonly intervalMs: number;
	/** rAF-timestamp interval of the last rendered frame for render-scale `update({ frameMs })`; null to skip a sample. */
	readonly lastFrameIntervalMs: number | null;
	readonly paused: boolean;
	state(): FrameRatePolicyState;
}
export function createFrameRatePolicy(options?: Partial<FrameRatePolicyOptions>): FrameRatePolicy;

// ---------------------------------------------------------------------------
// Babylon adapter
// ---------------------------------------------------------------------------

export interface PacedFrameRequesterOptions {
	policy: Pick<FrameRatePolicy, "frame"> & Partial<Pick<FrameRatePolicy, "recordWork">>;
	/** Usually window.requestAnimationFrame.bind(window). */
	requestFrame: (callback: (timestampMs: number) => void) => number;
	cancelFrame: (handle: number) => void;
	/** Optional clock (performance.now) to measure CPU work per rendered frame. */
	now?: () => number;
}

/** Shape Babylon's `engine.customAnimationFrameRequester` accepts; both methods work destructured. */
export interface PacedFrameRequester {
	requestAnimationFrame(callback: (timestampMs: number) => void): number;
	cancelAnimationFrame(id?: number): void;
	dispose(): void;
	readonly pending: boolean;
}
export function createPacedFrameRequester(options: PacedFrameRequesterOptions): PacedFrameRequester;
