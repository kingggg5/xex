import type { Camera } from "@babylonjs/core/Cameras/camera";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import "@babylonjs/core/Engines/Extensions/engine.query";
import "@babylonjs/core/Engines/AbstractEngine/abstractEngine.timeQuery";
import type { PerfCounter } from "@babylonjs/core/Misc/perfCounter";
import { FSR1RenderingPipeline } from "@babylonjs/core/PostProcesses/RenderPipeline/Pipelines/fsr1RenderingPipeline";
import type { Scene } from "@babylonjs/core/scene";
import {
	createRenderScaleController, normalizeRenderScalingSettings, parseRenderScalingQuery, scaleFactorFromScale, scaleFromScaleFactor,
	scaledRenderSize, type RenderScaleController, type RenderScaleControllerState, type RenderScalingSettings,
} from "./render-scale-controller.mjs";

export type { RenderScalingMode, RenderScalingSettings } from "./render-scale-controller.mjs";

export interface RenderScalingStats {
	/** Requested mode; `active` says whether an FSR pipeline is attached right now. */
	readonly mode: RenderScalingSettings["mode"];
	readonly active: boolean;
	readonly supported: boolean;
	readonly backend: string;
	/** FSR factor in use (1 when not active) and its linear scale. */
	readonly scaleFactor: number;
	readonly scale: number;
	readonly sharpnessStops: number;
	/** Effective MSAA samples on the reduced scene target; null when not active. */
	readonly samples: number | null;
	readonly adaptive: boolean;
	/** 3D scene render size: the FSR input when active, otherwise the drawing buffer. */
	readonly renderWidth: number;
	readonly renderHeight: number;
	/** Size Babylon actually allocated for the FSR input after the last render; null until allocated. */
	readonly allocatedWidth: number | null;
	readonly allocatedHeight: number | null;
	/** Drawing-buffer (canvas) size; DOM UI is composited separately at device resolution. */
	readonly outputWidth: number;
	readonly outputHeight: number;
	readonly hardwareScalingLevel: number;
	readonly gpuTimer: "webgl2-timer-query" | "unavailable";
	readonly controller: RenderScaleControllerState | null;
	/** Pipeline creations (camera change, context restore, mode change); scale changes rebuild inside Babylon. */
	readonly rebuilds: number;
	readonly scaleChanges: number;
	readonly reason: string;
}

export interface RenderScalingHandle {
	stats(): RenderScalingStats;
	update(change: Partial<RenderScalingSettings>): RenderScalingStats;
	dispose(): void;
}

export interface RenderScalingOptions {
	/** Current frame-rate target (tier or frame-rate policy); read every frame by the adaptive controller. */
	targetFps?: () => number;
	/** A paced render interval; null withholds intentional probes and uncertain browser-throttled frames. */
	frameSample?: () => number | null;
}

type TimedEngine = AbstractEngine & { _captureGPUFrameTime?: boolean; version: number };
type FsrInternals = { _upscalePostProcess?: { width: number; height: number } | null };

const handles = new WeakMap<Scene, RenderScalingHandle>();
let nextPipelineId = 0;

/** The render-scaling handle installed on a scene, if any (lookdev readouts and manifests use it). */
export function getRenderScaling(scene: Scene): RenderScalingHandle | null {
	return handles.get(scene) ?? null;
}

/**
 * Installs render scaling only when the URL carries `?fsr=` (default off).
 * `&rsProbe=1` additionally loads the measurement probe used by the FSR receipts.
 */
export function installRenderScalingFromQuery(scene: Scene, options?: (() => number) | RenderScalingOptions, search = location.search): RenderScalingHandle | null {
	const settings = parseRenderScalingQuery(search);
	// The module loads asynchronously; the scene may already be gone.
	if (!settings || scene.isDisposed) return null;
	const handle = installRenderScaling(scene, settings, typeof options === 'function' ? { targetFps: options } : options);
	if (new URLSearchParams(search).get("rsProbe") === "1") {
		void import("./lookdev/render-scaling-probe")
			.then(({ installRenderScalingProbe }) => installRenderScalingProbe(scene, handle))
			.catch((error: unknown) => console.warn("Render-scaling probe unavailable.", error));
	}
	return handle;
}

/**
 * Renders the active camera(s) below the drawing-buffer size and upscales with
 * Babylon's FSR 1 pipeline (EASU then RCAS; WGSL on WebGPU, GLSL on WebGL2).
 * Mode "off" leaves the camera untouched. One handle per scene.
 */
export function installRenderScaling(scene: Scene, settings: Partial<RenderScalingSettings>, options: RenderScalingOptions = {}): RenderScalingHandle {
	getRenderScaling(scene)?.dispose();
	const engine = scene.getEngine() as TimedEngine;
	// Same rule as FSR1RenderingPipeline.isSupported: integer texel fetch needs WebGPU or WebGL2.
	const supported = engine.isWebGPU || engine.version >= 2;
	const pipelineName = `xexoria-fsr1-${++nextPipelineId}`;
	let current = normalizeRenderScalingSettings(settings);
	let pipeline: FSR1RenderingPipeline | null = null;
	let attached: Camera[] = [];
	let controller: RenderScaleController | null = null;
	let appliedScaleFactor = current.scaleFactor;
	let gpuCounter: PerfCounter | null = null;
	let gpuSeen = -1;
	let ownsGpuCapture = false;
	let lastFrameAt = 0;
	let contextLost = false;
	let disposed = false;
	let rebuilds = 0;
	let scaleChanges = 0;
	let reason = "";

	function effectiveSamples(): number {
		if (current.samples <= 1) return 1;
		// WebGPU render targets accept a sample count of 1 or 4 only.
		if (engine.isWebGPU) return 4;
		return Math.max(1, Math.min(current.samples, engine.getCaps().maxMSAASamples || 1));
	}

	function camerasChanged(): boolean {
		const list = scene.activeCameras;
		if (list && list.length > 0) return list.length !== attached.length || list.some((camera, index) => camera !== attached[index]);
		return attached.length !== 1 || attached[0] !== scene.activeCamera;
	}

	function detach() {
		if (!pipeline) return;
		const manager = scene.postProcessRenderPipelineManager;
		try {
			manager.detachCamerasFromRenderPipeline(pipeline.name, attached);
		} catch {
			// A camera disposed before us has already released its post-processes.
		}
		manager.removePipeline(pipeline.name);
		pipeline.dispose();
		pipeline = null;
		attached = [];
	}

	function attach() {
		detach();
		if (disposed || contextLost || current.mode !== "fsr") return;
		if (!supported) { reason = "unsupported: FSR 1 needs WebGPU or WebGL2"; return; }
		const list = scene.activeCameras && scene.activeCameras.length > 0 ? scene.activeCameras.slice() : scene.activeCamera ? [scene.activeCamera] : [];
		if (list.length === 0) { reason = "waiting for an active camera"; return; }
		const created = new FSR1RenderingPipeline(pipelineName, scene, list);
		created.samples = effectiveSamples();
		created.sharpnessStops = current.sharpnessStops;
		created.scaleFactor = appliedScaleFactor;
		pipeline = created;
		attached = list;
		rebuilds++;
		reason = "";
	}

	function setGpuCapture(enabled: boolean) {
		if (enabled && !gpuCounter && !engine.isWebGPU && engine.getCaps().timerQuery && typeof engine.captureGPUFrameTime === "function") {
			ownsGpuCapture = engine._captureGPUFrameTime !== true;
			engine.captureGPUFrameTime(true);
			gpuCounter = engine.getGPUFrameTimeCounter();
			gpuSeen = gpuCounter.count;
		} else if (!enabled && gpuCounter) {
			if (ownsGpuCapture) engine.captureGPUFrameTime(false);
			gpuCounter = null;
			ownsGpuCapture = false;
		}
	}

	function configureController() {
		if (current.mode !== "fsr" || !current.adaptive) {
			controller = null;
			appliedScaleFactor = current.scaleFactor;
			setGpuCapture(false);
			return;
		}
		controller = createRenderScaleController({
			minScale: scaleFromScaleFactor(current.maxScaleFactor),
			maxScale: scaleFromScaleFactor(current.minScaleFactor),
			initialScale: scaleFromScaleFactor(current.scaleFactor),
		});
		appliedScaleFactor = scaleFactorFromScale(controller.scale);
		setGpuCapture(true);
	}

	function readGpuMs(): number | null {
		if (!gpuCounter || gpuCounter.count === gpuSeen) return null;
		gpuSeen = gpuCounter.count;
		const ms = gpuCounter.current / 1_000_000;
		return ms > 0 ? ms : null;
	}

	function restartTiming(why: string) {
		lastFrameAt = 0;
		controller?.reset(why);
	}

	const beforeRender = scene.onBeforeRenderObservable.add(() => {
		if (current.mode === "fsr" && !contextLost && supported && camerasChanged()) attach();
	});
	const afterRender = scene.onAfterRenderObservable.add(() => {
		const now = performance.now();
		const frameMs = options.frameSample ? options.frameSample() : lastFrameAt > 0 ? now - lastFrameAt : 0;
		lastFrameAt = now;
		if (!controller || !pipeline || frameMs === null || !Number.isFinite(frameMs) || frameMs <= 0) return;
		const next = controller.update({ frameMs, gpuMs: readGpuMs(), targetFps: options.targetFps?.() ?? 60 });
		if (next === null) return;
		appliedScaleFactor = scaleFactorFromScale(next);
		// Between frames: Babylon rebuilds the upscale post-process; its effect is cached, only the target is reallocated.
		pipeline.scaleFactor = appliedScaleFactor;
		scaleChanges++;
	});
	const resized = engine.onResizeObservable.add(() => restartTiming("resize"));
	const lost = engine.onContextLostObservable.add(() => { contextLost = true; restartTiming("context-lost"); });
	const restored = engine.onContextRestoredObservable.add(() => {
		contextLost = false;
		restartTiming("context-restored");
		attach();
	});
	const doc = typeof document === "undefined" ? null : document;
	const onVisibility = () => restartTiming(doc?.visibilityState === "hidden" ? "hidden" : "visible");
	doc?.addEventListener("visibilitychange", onVisibility);

	function stats(): RenderScalingStats {
		const outputWidth = engine.getRenderWidth(true), outputHeight = engine.getRenderHeight(true);
		const active = pipeline !== null;
		const factor = active ? appliedScaleFactor : 1;
		const size = active ? scaledRenderSize(outputWidth, outputHeight, factor) : { width: outputWidth, height: outputHeight };
		const upscale = active ? (pipeline as unknown as FsrInternals)._upscalePostProcess : null;
		const allocated = upscale && upscale.width > 0 && upscale.height > 0;
		return Object.freeze({
			mode: current.mode, active, supported,
			backend: engine.isWebGPU ? "WebGPU" : engine.version >= 2 ? "WebGL2" : `WebGL${engine.version}`,
			scaleFactor: factor, scale: scaleFromScaleFactor(factor), sharpnessStops: current.sharpnessStops,
			samples: active ? effectiveSamples() : null, adaptive: controller !== null,
			renderWidth: size.width, renderHeight: size.height,
			allocatedWidth: allocated ? upscale.width : null, allocatedHeight: allocated ? upscale.height : null,
			outputWidth, outputHeight, hardwareScalingLevel: engine.getHardwareScalingLevel(),
			gpuTimer: gpuCounter ? "webgl2-timer-query" : "unavailable",
			controller: controller?.state() ?? null, rebuilds, scaleChanges,
			reason: reason || (current.mode === "off" ? "off" : active ? "" : "inactive"),
		});
	}

	function update(change: Partial<RenderScalingSettings>): RenderScalingStats {
		if (disposed) return stats();
		const previous = current;
		current = normalizeRenderScalingSettings({ ...previous, ...change });
		const controllerChanged = current.mode !== previous.mode || current.adaptive !== previous.adaptive || current.scaleFactor !== previous.scaleFactor
			|| current.minScaleFactor !== previous.minScaleFactor || current.maxScaleFactor !== previous.maxScaleFactor;
		if (controllerChanged) configureController();
		if (current.mode !== previous.mode || !pipeline) {
			attach();
		} else {
			pipeline.samples = effectiveSamples();
			pipeline.sharpnessStops = current.sharpnessStops;
			if (pipeline.scaleFactor !== appliedScaleFactor) pipeline.scaleFactor = appliedScaleFactor;
		}
		restartTiming("settings");
		return stats();
	}

	function dispose() {
		if (disposed) return;
		disposed = true;
		scene.onBeforeRenderObservable.remove(beforeRender);
		scene.onAfterRenderObservable.remove(afterRender);
		engine.onResizeObservable.remove(resized);
		engine.onContextLostObservable.remove(lost);
		engine.onContextRestoredObservable.remove(restored);
		scene.onDisposeObservable.remove(sceneDisposed);
		doc?.removeEventListener("visibilitychange", onVisibility);
		setGpuCapture(false);
		if (!scene.isDisposed) detach();
		pipeline = null;
		controller = null;
		if (handles.get(scene) === handle) handles.delete(scene);
	}

	const handle: RenderScalingHandle = { stats, update, dispose };
	const sceneDisposed = scene.onDisposeObservable.addOnce(dispose);
	handles.set(scene, handle);
	configureController();
	attach();
	return handle;
}
