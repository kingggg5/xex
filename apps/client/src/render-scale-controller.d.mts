export type RenderScalingMode = "off" | "fsr";

export interface RenderScalingSettings {
	/** "fsr" renders the 3D scene smaller and upscales it with AMD FSR 1 (EASU + RCAS). */
	readonly mode: RenderScalingMode;
	/** Render this much smaller than the output (AMD presets 1.3 / 1.5 / 1.7 / 2). Range 1..3. */
	readonly scaleFactor: number;
	/** RCAS sharpness reduction in stops; 0 is the sharpest. Range 0..2, default 0.2. */
	readonly sharpnessStops: number;
	/** MSAA samples on the reduced-size scene target: 1, 2, 4 or 8 (WebGPU supports 1 and 4). */
	readonly samples: number;
	/** Let the controller move scaleFactor within [minScaleFactor, maxScaleFactor]. */
	readonly adaptive: boolean;
	readonly minScaleFactor: number;
	readonly maxScaleFactor: number;
}

export interface RenderScaleControllerOptions {
	/** Linear resolution fraction range; FSR scaleFactor is 1 / scale. */
	minScale: number;
	maxScale: number;
	initialScale: number;
	stepDown: number;
	stepUp: number;
	quantum: number;
	emaAlpha: number;
	windowSeconds: number;
	minWindowFrames: number;
	warmupFrames: number;
	missFactor: number;
	missRatioDown: number;
	missRatioSevere: number;
	missRatioClean: number;
	costDownAt: number;
	costUpAt: number;
	cpuBoundBelow: number;
	frameDownAt: number;
	cappedAt: number;
	/** Minimum rendered time after any change or reset before a climb with measured headroom. */
	climbDelayMs: number;
	/** Capped frames without GPU time: clean time before a blind one-step probe. */
	probeDelayMs: number;
	/** Cap for both delays after back-off. */
	maxClimbDelayMs: number;
	/** A drop within this time after a climb doubles the delays; a climb that holds this long halves them. */
	churnWindowMs: number;
	/** A drop within this many windows after a climb undoes only that climb. */
	probationWindows: number;
	hitchMs: number;
	sustainedHitches: number;
	gpuCoverage: number;
}

export interface RenderScaleSample {
	/** Interval since the previous rendered frame, in milliseconds. */
	frameMs: number;
	/** GPU time of a recent frame when the host has a timer (WebGL2 timer query); omit or null otherwise. */
	gpuMs?: number | null;
	/** Frame-rate target the scale must hold; may change at runtime (frame-rate policy). */
	targetFps: number;
}

export type RenderScaleSignal = "none" | "gpu" | "frame" | "probe";

export interface RenderScaleControllerState {
	readonly scale: number;
	readonly minScale: number;
	readonly maxScale: number;
	readonly atMin: boolean;
	readonly atMax: boolean;
	readonly targetFps: number | null;
	readonly targetMs: number | null;
	/** Which signal decided the last window: GPU time, uncapped frame time, or capped frames (blind probe). */
	readonly signal: RenderScaleSignal;
	/** "cpu" only when GPU time proves frames miss while the GPU is idle. */
	readonly bound: "gpu" | "cpu" | "unknown";
	readonly emaFrameMs: number | null;
	readonly emaGpuMs: number | null;
	/** Cost EMA divided by the target interval: above 1 is a deficit, below 1 is headroom. */
	readonly loadRatio: number | null;
	/** False when frames are capped and no GPU time exists: loadRatio cannot show headroom. */
	readonly headroomKnown: boolean;
	readonly missRatio: number | null;
	/** Continuous rendered time at the floor / ceiling of the range. */
	readonly atMinMs: number;
	readonly atMaxMs: number;
	/** Continuous time the target was missed and resolution could not fix it (at min, or CPU-bound). */
	readonly deficitMs: number;
	/** Continuous time at max scale with clean windows. */
	readonly surplusMs: number;
	/** Rendered time since the last scale change or reset (each change reallocates the scene target). */
	readonly sinceChangeMs: number;
	/** Climb back-off multiplier: 1 normally, doubled by churn (a drop soon after a climb), at most 64. */
	readonly backoff: number;
	/** Effective delays after back-off. */
	readonly climbDelayMs: number;
	readonly probeDelayMs: number;
	readonly warmupRemaining: number;
	readonly changes: number;
	readonly lastReason: string;
}

export interface RenderScaleController {
	readonly scale: number;
	/** Feed one rendered frame; returns the new scale only when it changes, otherwise null. */
	update(sample: RenderScaleSample): number | null;
	/** Clear EMAs, windows and probes after a tab hide/show, resize, settings change or context restore. */
	reset(reason?: string): void;
	/** Change the range; returns the clamped scale if it changed, otherwise null. */
	setRange(minScale: number, maxScale: number): number | null;
	state(): RenderScaleControllerState;
}

export const RENDER_SCALE_DEFAULTS: Readonly<Omit<RenderScaleControllerOptions, "initialScale">>;
export const RENDER_SCALING_DEFAULTS: Readonly<RenderScalingSettings>;
export function createRenderScaleController(options?: Partial<RenderScaleControllerOptions>): RenderScaleController;
export function normalizeRenderScalingSettings(settings?: Partial<RenderScalingSettings>): Readonly<RenderScalingSettings>;
/** Null when the query has no `fsr` parameter (default off). */
export function parseRenderScalingQuery(search: string): Readonly<RenderScalingSettings> | null;
export function scaleFromScaleFactor(scaleFactor: number): number;
export function scaleFactorFromScale(scale: number): number;
export function scaledRenderSize(outputWidth: number, outputHeight: number, scaleFactor: number): { width: number; height: number };
