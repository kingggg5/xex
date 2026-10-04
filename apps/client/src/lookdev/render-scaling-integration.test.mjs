import test from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

// Bundles the real render-scaling.ts with Babylon 9.27.1 and runs it on a NullEngine (no GPU).
const bundled = await build({ stdin: { contents: `
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Scene } from "@babylonjs/core/scene";
import { FreeCamera } from "@babylonjs/core/Cameras/freeCamera";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { installRenderScaling, installRenderScalingFromQuery, getRenderScaling } from "./src/render-scaling";
export { NullEngine, Scene, FreeCamera, Vector3, installRenderScaling, installRenderScalingFromQuery, getRenderScaling };`,
resolveDir: fileURLToPath(new URL("../..", import.meta.url)), loader: "ts" }, bundle: true, platform: "node", format: "esm", write: false, logLevel: "silent" });
const { NullEngine, Scene, FreeCamera, Vector3, installRenderScaling, installRenderScalingFromQuery, getRenderScaling } =
	await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`);

/** NullEngine reports WebGL1; FSR 1 needs WebGL2 or WebGPU, so the fixture claims WebGL2 to exercise the attach paths. */
function fixture(webGLVersion = 2) {
	const engine = new NullEngine({ renderWidth: 1920, renderHeight: 1080, textureSize: 512, deterministicLockstep: false, lockstepMaxSteps: 1 });
	engine._webGLVersion = webGLVersion;
	const scene = new Scene(engine);
	const camera = new FreeCamera("main", new Vector3(0, 2, -10), scene);
	return { engine, scene, camera };
}

const fsrNames = camera => camera._postProcesses.filter(Boolean).map(postProcess => postProcess.name);

test("fsr attaches EASU then RCAS to the active camera and reports reduced render size", () => {
	const { engine, scene, camera } = fixture();
	try {
		const handle = installRenderScaling(scene, { mode: "fsr", scaleFactor: 1.5 });
		scene.render();
		const names = fsrNames(camera);
		assert.equal(names.length, 2);
		assert.match(names[0], /Upscale$/);
		assert.match(names[1], /Sharpen$/);
		const stats = handle.stats();
		assert.equal(stats.active, true);
		assert.equal(stats.backend, "WebGL2");
		assert.deepEqual([stats.outputWidth, stats.outputHeight], [1920, 1080]);
		assert.deepEqual([stats.renderWidth, stats.renderHeight], [1280, 720]);
		assert.deepEqual([stats.allocatedWidth, stats.allocatedHeight], [1280, 720], "Babylon allocated the documented size");
		assert.equal(stats.samples, 1, "MSAA is clamped to the engine's maxMSAASamples");
		assert.equal(getRenderScaling(scene), handle);
	} finally { engine.dispose(); }
});

test("off by default, WebGL1 refuses, and mode switches detach cleanly", () => {
	const legacy = fixture(1);
	try {
		const handle = installRenderScaling(legacy.scene, { mode: "fsr", scaleFactor: 1.5 });
		legacy.scene.render();
		assert.equal(fsrNames(legacy.camera).length, 0);
		assert.match(handle.stats().reason, /unsupported/);
	} finally { legacy.engine.dispose(); }
	const { engine, scene, camera } = fixture();
	try {
		assert.equal(installRenderScalingFromQuery(scene, () => 60, "?renderer=webgl2"), null, "no ?fsr= means nothing is installed");
		const handle = installRenderScalingFromQuery(scene, () => 60, "?fsr=off");
		scene.render();
		assert.equal(handle.stats().mode, "off");
		assert.equal(fsrNames(camera).length, 0);
		handle.update({ mode: "fsr", scaleFactor: 1.7 });
		scene.render();
		assert.equal(fsrNames(camera).length, 2);
		assert.deepEqual([handle.stats().renderWidth, handle.stats().renderHeight], [1129, 635]);
		handle.update({ scaleFactor: 1.3, sharpnessStops: 0.5 });
		scene.render();
		assert.equal(fsrNames(camera).length, 2, "a scale change rebuilds inside the same pipeline");
		assert.deepEqual([handle.stats().allocatedWidth, handle.stats().allocatedHeight], [1476, 830]);
		assert.equal(handle.stats().sharpnessStops, 0.5);
		handle.update({ mode: "off" });
		scene.render();
		assert.equal(fsrNames(camera).length, 0);
		assert.equal(handle.stats().active, false);
	} finally { engine.dispose(); }
});

test("camera changes, context restore and resize keep exactly one pipeline on the active camera", () => {
	const { engine, scene, camera } = fixture();
	try {
		const handle = installRenderScaling(scene, { mode: "fsr", scaleFactor: 1.5, adaptive: true });
		scene.render();
		const other = new FreeCamera("other", new Vector3(5, 2, -10), scene);
		scene.activeCamera = other;
		scene.render();
		assert.equal(fsrNames(camera).length, 0, "the previous camera is released");
		assert.equal(fsrNames(other).length, 2);
		const before = handle.stats().rebuilds;
		engine.onContextLostObservable.notifyObservers(engine);
		engine.onContextRestoredObservable.notifyObservers(engine);
		scene.render();
		assert.equal(handle.stats().rebuilds, before + 1, "restore recreates the pipeline");
		assert.equal(fsrNames(other).length, 2);
		engine.onResizeObservable.notifyObservers(engine);
		assert.equal(handle.stats().controller.warmupRemaining, 12, "resize restarts the adaptive warm-up");
		assert.equal(handle.stats().gpuTimer, "unavailable", "no timer-query extension on this engine");
		scene.activeCamera = camera;
		scene.render();
		assert.equal(fsrNames(other).length, 0);
		assert.equal(fsrNames(camera).length, 2);
		handle.dispose();
		scene.render();
		assert.equal(fsrNames(camera).length, 0, "dispose detaches the pipeline");
		assert.equal(getRenderScaling(scene), null);
		assert.equal(Object.keys(scene.postProcessRenderPipelineManager.supportedPipelines).length, 0, "no pipeline left registered");
	} finally { engine.dispose(); }
});

test("adaptive mode starts at the exact preset and applies controller steps between frames", () => {
	const { engine, scene, camera } = fixture();
	const realPerformance = globalThis.performance;
	let now = 1000;
	Object.defineProperty(globalThis, "performance", { configurable: true, value: { now: () => now } });
	try {
		const handle = installRenderScaling(scene, { mode: "fsr", scaleFactor: 1.5, adaptive: true, minScaleFactor: 1, maxScaleFactor: 2 }, { targetFps: () => 60 });
		scene.render();
		assert.deepEqual([handle.stats().allocatedWidth, handle.stats().allocatedHeight], [1280, 720], "adaptive starts at exactly 1 / 1.5");
		// 5 ms frames against a 60 fps target: frame time is visible below the cap, so the controller climbs.
		for (let frame = 0; frame < 1700; frame++) { now += 5; scene.render(); }
		const stats = handle.stats();
		assert.ok(stats.scaleChanges >= 2, `scale changes ${stats.scaleChanges}`);
		assert.ok(stats.scaleFactor < 1.5, `climbed to factor ${stats.scaleFactor}`);
		assert.equal(stats.controller.signal, "frame");
		assert.deepEqual([stats.allocatedWidth, stats.allocatedHeight], [stats.renderWidth, stats.renderHeight], "the rebuilt target matches the reported size");
		assert.equal(fsrNames(camera).length, 2, "rebuilds keep exactly two post-processes");
	} finally {
		Object.defineProperty(globalThis, "performance", { configurable: true, value: realPerformance });
		engine.dispose();
	}
});

test("a second install replaces the first and scene disposal tears everything down", () => {
	const { engine, scene, camera } = fixture();
	const first = installRenderScaling(scene, { mode: "fsr", scaleFactor: 2 });
	scene.render();
	const second = installRenderScaling(scene, { mode: "fsr", scaleFactor: 1.3 });
	scene.render();
	assert.equal(fsrNames(camera).length, 2, "one pipeline per scene");
	assert.equal(first.stats().active, false);
	assert.equal(second.stats().scaleFactor, 1.3);
	scene.dispose();
	assert.equal(getRenderScaling(scene), null);
	assert.equal(installRenderScalingFromQuery(scene, () => 60, "?fsr=1.5"), null, "a disposed scene is ignored");
	engine.dispose();
});

test("withheld paced samples do not count probes or browser throttling as adaptive load", () => {
	const { engine, scene } = fixture();
	const realPerformance = globalThis.performance;
	let now = 1000, sample = null;
	Object.defineProperty(globalThis, "performance", { configurable: true, value: { now: () => now } });
	try {
		const handle = installRenderScalingFromQuery(scene, { targetFps: () => 30, frameSample: () => sample }, "?fsr=1.5&auto=1");
		assert.ok(handle);
		const initial = handle.stats();
		for (let frame = 0; frame < 240; frame++) { now += 50; scene.render(); }
		assert.equal(handle.stats().controller.warmupRemaining, initial.controller.warmupRemaining);
		assert.equal(handle.stats().scaleChanges, 0); assert.equal(handle.stats().scaleFactor, initial.scaleFactor);
		for (const invalid of [0, -1, NaN, Infinity]) { sample = invalid; now += 50; scene.render(); }
		assert.equal(handle.stats().controller.warmupRemaining, initial.controller.warmupRemaining);
		sample = 1000 / 30;
		for (let frame = 0; frame < 12; frame++) { now += 200; scene.render(); }
		assert.equal(handle.stats().controller.warmupRemaining, 0, 'valid paced intervals enter warm-up despite the wall-clock gaps');
		assert.equal(handle.stats().scaleChanges, 0, 'wall-clock gaps were not sampled as load');
	} finally {
		Object.defineProperty(globalThis, "performance", { configurable: true, value: realPerformance });
		engine.dispose();
	}
});
