import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import { EngineInstrumentation } from "@babylonjs/core/Instrumentation/engineInstrumentation";
import "@babylonjs/core/Engines/Extensions/engine.query";
import "@babylonjs/core/Engines/AbstractEngine/abstractEngine.timeQuery";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import type { Scene } from "@babylonjs/core/scene";
import type { PerfCounter } from "@babylonjs/core/Misc/perfCounter";
import { LookdevSampleWindow, type LookdevSample, type WindowSnapshot } from "./lookdev-data.mjs";

type TimingEngine = AbstractEngine & {
	webGLVersion?: number; _captureGPUFrameTime?: boolean;
	enabledExtensions?: readonly string[]; enableGPUTimingMeasurements?: boolean;
	gpuTimeInFrameForMainPass?: { counter: PerfCounter };
};
export interface LookdevMetricsSnapshot {
	backend: string; renderWidth: number; renderHeight: number; hardwareScalingLevel: number;
	visible: boolean; focused: boolean; samplesDiscardedWhileHidden: number; samplesDiscardedWhileUnfocused: number; warmupRemaining: number;
	focusPolicy: "visible-only" | "visible-and-focused";
	gpuStatus: "unavailable" | "pending" | "available" | "stale"; gpuScope: "frame" | "main-pass" | "unavailable"; gpuReason: string; gpuFreshAgeMs: number | null;
	counterSemantics: { activeTriangles: string; activeMeshes: string; particles: string; cpuSubmissionMs: string };
	window: WindowSnapshot; current: LookdevSample | null;
}

/** Same Babylon instrumentation used by render-diagnostics, with bounded samples and explicit ownership. */
export function createLookdevMetrics(scene: Scene, options: {
	capacity?: number; visible?: () => boolean; focused?: () => boolean; now?: () => number; requireFocus?: boolean;
} = {}) {
	const engine = scene.getEngine() as TimingEngine;
	const metrics = new SceneInstrumentation(scene);
	metrics.captureFrameTime = true; metrics.captureRenderTime = true; metrics.captureRenderTargetsRenderTime = true;
	const engineMetrics = new EngineInstrumentation(engine);
	const windowSamples = new LookdevSampleWindow(options.capacity);
	const visible = options.visible ?? (() => typeof document === "undefined" || document.visibilityState === "visible");
	const focused = options.focused ?? (() => typeof document === "undefined" || document.hasFocus());
	const now = options.now ?? (() => performance.now());
	const previousWebGLCapture = engine._captureGPUFrameTime === true;
	const previousWebGPUCapture = engine.isWebGPU && engine.enableGPUTimingMeasurements === true;
	let gpuScope: "frame" | "main-pass" | "unavailable" = "unavailable";
	let gpuReason = "GPU timestamp queries are unavailable on this backend/device.";
	let ownWebGLCapture = false, ownWebGPUCapture = false;
	try {
		if (engine.isWebGPU && engine.enabledExtensions?.includes("timestamp-query") && typeof engine.enableGPUTimingMeasurements === "boolean") {
			if (!previousWebGPUCapture) { engine.enableGPUTimingMeasurements = true; ownWebGPUCapture = true; }
			if (engine.enableGPUTimingMeasurements) {
				gpuScope = "main-pass"; gpuReason = "Asynchronous WebGPU main render pass only; excludes extra render targets and compute passes.";
			}
		} else if (!engine.isWebGPU && engine.getCaps().timerQuery && typeof engine.captureGPUFrameTime === "function") {
			engineMetrics.captureGPUFrameTime = true; ownWebGLCapture = !previousWebGLCapture;
			gpuScope = "frame"; gpuReason = "Asynchronous WebGL frame timer; nanoseconds converted to milliseconds. Disjoint/unfinished query results are omitted.";
		}
	} catch { gpuReason = "GPU timing could not be enabled on this backend/device; no CPU value is substituted."; }
	let paused = false, disposed = false, previousTime = 0, warmup = 30, discarded = 0, unfocusedDiscarded = 0, gpuCount = -1;
	let lastGpuSampleAt: number | null = null;
	let current: LookdevSample | null = null;
	function gpuCounter() { return gpuScope === "main-pass" ? engine.gpuTimeInFrameForMainPass?.counter : gpuScope === "frame" ? engineMetrics.gpuFrameTimeCounter : undefined; }
	function discardGpuResult() { try { const counter = gpuCounter(); if (counter) gpuCount = counter.count; } catch { /* A missing result is not GPU time. */ } }
	const observer = scene.onAfterRenderObservable.add(() => {
		const time = now();
		const frameVisible = visible(), frameFocused = focused();
		if (disposed || paused) { previousTime = 0; discardGpuResult(); return; }
		if (!frameVisible || (options.requireFocus && !frameFocused)) { previousTime = 0; discardGpuResult(); if (!frameVisible) discarded++; else unfocusedDiscarded++; return; }
		if (warmup > 0) { warmup--; previousTime = time; discardGpuResult(); return; }
		let gpuMs: number | null = null;
		if (gpuScope !== "unavailable") {
			try {
				const counter = gpuCounter();
				if (counter && counter.count !== gpuCount && counter.current > 0) { gpuMs = counter.current / 1_000_000; gpuCount = counter.count; lastGpuSampleAt = time; }
			} catch { gpuScope = "unavailable"; gpuReason = "GPU counter read failed; CPU timing is still available."; }
		}
		current = { frameIntervalMs: previousTime ? time - previousTime : null,
			cpuSceneMs: metrics.frameTimeCounter.current, cpuSubmissionMs: metrics.renderTimeCounter.current,
			cpuTargetsMs: metrics.renderTargetsRenderTimeCounter.current, gpuMs,
			drawCalls: metrics.drawCallsCounter.current, activeMeshes: scene.getActiveMeshes().length,
			activeTriangles: scene.getActiveIndices() / 3, particles: scene.getActiveParticles(), focused: frameFocused };
		previousTime = time; windowSamples.push(current);
	});
	function snapshot(): LookdevMetricsSnapshot {
		const window = windowSamples.snapshot();
		const age = lastGpuSampleAt === null ? null : Math.max(0, now() - lastGpuSampleAt);
		return { backend: engine.isWebGPU ? "WebGPU" : engine.webGLVersion ? `WebGL${engine.webGLVersion}` : engine.getClassName(),
			renderWidth: engine.getRenderWidth(), renderHeight: engine.getRenderHeight(), hardwareScalingLevel: engine.getHardwareScalingLevel(),
			visible: visible(), focused: focused(), samplesDiscardedWhileHidden: discarded, samplesDiscardedWhileUnfocused: unfocusedDiscarded, warmupRemaining: warmup,
			focusPolicy: options.requireFocus ? "visible-and-focused" : "visible-only",
			gpuStatus: gpuScope === "unavailable" ? "unavailable" : window.gpuMs.n ? age !== null && age > 1000 ? "stale" : "available" : "pending", gpuScope, gpuReason, gpuFreshAgeMs: age,
			counterSemantics: {
				activeTriangles: "Babylon submitted indices / 3, accumulated across counted render passes and instances, including shadow Mesh._processRendering paths. Triangle equivalents, not unique visible geometry.",
				activeMeshes: "Scene camera active-mesh list length; does not count each drawn instance or off-camera shadow caster separately.",
				particles: "Babylon accumulated particle render count, potentially across passes; not unique particles or effects.",
				cpuSubmissionMs: "SceneInstrumentation.renderTimeCounter CPU rendering span. Not GPU time and not submission-only overhead.",
			},
			window, current: current ? { ...current } : null };
	}
	function reset() { windowSamples.reset(); previousTime = 0; current = null; warmup = 30; discarded = 0; unfocusedDiscarded = 0; lastGpuSampleAt = null; discardGpuResult(); }
	function dispose() {
		if (disposed) return; disposed = true; scene.onAfterRenderObservable.remove(observer); scene.onDisposeObservable.remove(disposalObserver);
		metrics.dispose();
		// EngineInstrumentation.dispose does not disable the shared engine GPU timer in 9.27.1.
		if (ownWebGLCapture) engineMetrics.captureGPUFrameTime = false;
		if (ownWebGPUCapture && engine.enableGPUTimingMeasurements === true) engine.enableGPUTimingMeasurements = false;
		engineMetrics.dispose(); windowSamples.reset(); current = null;
	}
	const disposalObserver = scene.onDisposeObservable.addOnce(dispose);
	return { snapshot, reset, setPaused(value: boolean) { paused = value; previousTime = 0; discardGpuResult(); }, dispose };
}
