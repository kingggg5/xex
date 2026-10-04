import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import { EngineInstrumentation } from "@babylonjs/core/Instrumentation/engineInstrumentation";
import "@babylonjs/core/Engines/Extensions/engine.query";
import "@babylonjs/core/Engines/AbstractEngine/abstractEngine.timeQuery";
import type { Scene } from "@babylonjs/core/scene";
import type { RenderScalingHandle, RenderScalingSettings, RenderScalingStats } from "../render-scaling";

/** Nearest-rank summary; missing values (NaN) are omitted, never zero-filled. */
export interface ProbeSummary { n: number; mean: number | null; p50: number | null; p90: number | null; p95: number | null; p99: number | null; max: number | null }
export interface ProbeSample {
	durationMs: number; frames: number; renderedFps: number;
	frameMs: ProbeSummary; cpuSceneMs: ProbeSummary; gpuMs: ProbeSummary; drawCalls: ProbeSummary; activeMeshes: ProbeSummary;
	jsHeapUsedMB: { start: number | null; end: number | null; max: number | null };
	frameCap: number | null; hardwareScalingLevel: number; visible: boolean; focused: boolean;
	statsStart: RenderScalingStats; statsEnd: RenderScalingStats;
	/** Every frame interval in the window, 0.01 ms resolution, for re-analysis. */
	intervals: number[];
}
export interface RenderScalingProbe {
	readonly version: 1;
	stats(): RenderScalingStats;
	apply(change: Partial<RenderScalingSettings>): RenderScalingStats;
	/** Bench only: null removes Babylon's frame limiter, a number sets engine.maxFPS. */
	setFrameCap(fps: number | null): number | null;
	/** Bench only: plain bilinear A/B through Babylon hardware scaling (the browser upscales the canvas). */
	setHardwareScaling(level: number): number;
	sample(durationMs: number): Promise<ProbeSample>;
	environment(): Record<string, string | number | boolean | null>;
	dispose(): void;
}

type MemoryPerformance = Performance & { memory?: { usedJSHeapSize: number } };
type InfoEngine = { getGlInfo?: () => { vendor: string; renderer: string; version: string }; version: number; isWebGPU: boolean };
declare global { interface Window { __xexoriaRenderScaling?: RenderScalingProbe } }

const CAPACITY = 30_000;
const FIELDS = ["frameMs", "cpuSceneMs", "gpuMs", "drawCalls", "activeMeshes"] as const;

function summarize(values: Float64Array, length: number): ProbeSummary {
	const finite = Array.from(values.subarray(0, length)).filter(Number.isFinite).sort((a, b) => a - b);
	if (!finite.length) return { n: 0, mean: null, p50: null, p90: null, p95: null, p99: null, max: null };
	const rank = (fraction: number) => finite[Math.max(0, Math.ceil(fraction * finite.length) - 1)];
	const round = (value: number) => Math.round(value * 1000) / 1000;
	return { n: finite.length, mean: round(finite.reduce((sum, value) => sum + value, 0) / finite.length), p50: round(rank(0.5)), p90: round(rank(0.9)),
		p95: round(rank(0.95)), p99: round(rank(0.99)), max: round(finite[finite.length - 1]) };
}

function heapMB(): number | null {
	const memory = (performance as MemoryPerformance).memory;
	return memory && Number.isFinite(memory.usedJSHeapSize) ? Math.round(memory.usedJSHeapSize / 10485.76) / 100 : null;
}

/** DEV/bench instrument for the render-scaling receipts. Loaded only with `?fsr=...&rsProbe=1`. */
export function installRenderScalingProbe(scene: Scene, handle: RenderScalingHandle): RenderScalingProbe {
	window.__xexoriaRenderScaling?.dispose();
	const engine = scene.getEngine();
	const instrumentation = new SceneInstrumentation(scene);
	instrumentation.captureFrameTime = true;
	const engineInstrumentation = new EngineInstrumentation(engine);
	const gpuTimer = !engine.isWebGPU && !!engine.getCaps().timerQuery;
	if (gpuTimer) engineInstrumentation.captureGPUFrameTime = true;
	const columns = Object.fromEntries(FIELDS.map(field => [field, new Float64Array(CAPACITY)])) as Record<(typeof FIELDS)[number], Float64Array>;
	let length = 0, recording = false, lastAt = 0, gpuSeen = -1, heapMax: number | null = null, disposed = false;
	const observer = scene.onAfterRenderObservable.add(() => {
		const now = performance.now();
		const frameMs = lastAt > 0 ? now - lastAt : NaN;
		lastAt = now;
		if (!recording || length >= CAPACITY) return;
		let gpuMs = NaN;
		if (gpuTimer) {
			const counter = engineInstrumentation.gpuFrameTimeCounter;
			if (counter.count !== gpuSeen && counter.current > 0) { gpuSeen = counter.count; gpuMs = counter.current / 1_000_000; }
		}
		columns.frameMs[length] = frameMs;
		columns.cpuSceneMs[length] = instrumentation.frameTimeCounter.current;
		columns.gpuMs[length] = gpuMs;
		columns.drawCalls[length] = instrumentation.drawCallsCounter.current;
		columns.activeMeshes[length] = scene.getActiveMeshes().length;
		length++;
		if (length % 30 === 0) { const heap = heapMB(); if (heap !== null) heapMax = Math.max(heapMax ?? 0, heap); }
	});
	const probe: RenderScalingProbe = {
		version: 1,
		stats: () => handle.stats(),
		apply: change => handle.update(change),
		setFrameCap(fps) {
			engine.maxFPS = typeof fps === "number" && Number.isFinite(fps) && fps > 0 ? fps : undefined;
			return engine.maxFPS ?? null;
		},
		setHardwareScaling(level) {
			if (Number.isFinite(level) && level > 0) { engine.setHardwareScalingLevel(level); engine.resize(); }
			return engine.getHardwareScalingLevel();
		},
		async sample(durationMs) {
			if (disposed) throw new Error("Probe disposed");
			const wait = Math.max(500, Math.min(120_000, Number.isFinite(durationMs) ? durationMs : 10_000));
			length = 0; lastAt = 0; gpuSeen = engineInstrumentation.gpuFrameTimeCounter.count; heapMax = null;
			const statsStart = handle.stats(), heapStart = heapMB(), started = performance.now();
			recording = true;
			await new Promise(resolve => window.setTimeout(resolve, wait));
			recording = false;
			const elapsed = performance.now() - started;
			const result: ProbeSample = {
				durationMs: Math.round(elapsed), frames: length, renderedFps: Math.round(length * 100_000 / elapsed) / 100,
				frameMs: summarize(columns.frameMs, length), cpuSceneMs: summarize(columns.cpuSceneMs, length), gpuMs: summarize(columns.gpuMs, length),
				drawCalls: summarize(columns.drawCalls, length), activeMeshes: summarize(columns.activeMeshes, length),
				jsHeapUsedMB: { start: heapStart, end: heapMB(), max: heapMax },
				frameCap: engine.maxFPS ?? null, hardwareScalingLevel: engine.getHardwareScalingLevel(),
				visible: document.visibilityState === "visible", focused: document.hasFocus(),
				statsStart, statsEnd: handle.stats(),
				intervals: Array.from(columns.frameMs.subarray(0, length)).filter(Number.isFinite).map(value => Math.round(value * 100) / 100),
			};
			return result;
		},
		environment() {
			const info = (engine as unknown as InfoEngine).getGlInfo?.();
			const canvas = engine.getRenderingCanvas();
			return {
				backend: engine.isWebGPU ? "WebGPU" : `WebGL${(engine as unknown as InfoEngine).version}`,
				gpuVendor: info?.vendor ?? null, gpuRenderer: info?.renderer ?? null, gpuVersion: info?.version ?? null,
				gpuTimer: gpuTimer ? "webgl2-timer-query" : "unavailable",
				maxMSAASamples: engine.getCaps().maxMSAASamples ?? null,
				devicePixelRatio: window.devicePixelRatio, cssWidth: canvas?.clientWidth ?? null, cssHeight: canvas?.clientHeight ?? null,
				drawingBufferWidth: engine.getRenderWidth(true), drawingBufferHeight: engine.getRenderHeight(true),
				hardwareScalingLevel: engine.getHardwareScalingLevel(), frameCap: engine.maxFPS ?? null,
				userAgent: navigator.userAgent, coarsePointer: matchMedia("(pointer: coarse)").matches,
			};
		},
		dispose() {
			if (disposed) return;
			disposed = true; recording = false;
			scene.onAfterRenderObservable.remove(observer);
			scene.onDisposeObservable.remove(sceneDisposed);
			instrumentation.dispose();
			if (gpuTimer) engineInstrumentation.captureGPUFrameTime = false;
			engineInstrumentation.dispose();
			if (window.__xexoriaRenderScaling === probe) delete window.__xexoriaRenderScaling;
		},
	};
	const sceneDisposed = scene.onDisposeObservable.addOnce(() => probe.dispose());
	window.__xexoriaRenderScaling = probe;
	return probe;
}
