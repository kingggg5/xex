import assert from "node:assert/strict";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Scene } from "@babylonjs/core/scene";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { PerfCounter } from "@babylonjs/core/Misc/perfCounter";
import { createLookdevMetrics } from "../src/lookdev/lookdev-metrics";
import { createLookdevCameraLock } from "../src/lookdev/lookdev-camera";
import { lockedCamera } from "../src/lookdev/lookdev-data.mjs";

const engine = new NullEngine({ renderWidth: 256, renderHeight: 144, textureSize: 64, deterministicLockstep: true, lockstepMaxSteps: 4 });
const scene = new Scene(engine); new ArcRotateCamera("cpu-check", 0, 1, 13, Vector3.Zero(), scene);
const after = scene.onAfterRenderObservable.observers.length, before = scene.onBeforeRenderObservable.observers.length;
let now = 0, visible = true, focused = true;
const metrics = createLookdevMetrics(scene, { capacity: 30, now: () => now, visible: () => visible, focused: () => focused });
for (let i = 0; i < 100; i++) { now += 16; scene.render(); }
const first = metrics.snapshot();
assert.equal(first.window.retained, 30); assert.equal(first.window.total, 70); assert.equal(first.window.frameIntervalMs.p95, 16);
assert.equal(first.gpuStatus, "unavailable"); assert.equal(first.window.gpuMs.n, 0); assert.equal(first.window.gpuMs.p95, null);
metrics.setPaused(true); for (let i = 0; i < 5; i++) { now += 200; scene.render(); } assert.equal(metrics.snapshot().window.total, 70);
metrics.setPaused(false); visible = false; now += 5000; scene.render(); assert.equal(metrics.snapshot().window.total, 70);
visible = true; now += 16; scene.render(); assert.equal(metrics.snapshot().window.frameIntervalMs.max, 16);
focused = false; for (let i = 0; i < 5; i++) { now += 16; scene.render(); }
assert.equal(metrics.snapshot().window.focus.unfocusedFrames, 5); assert.equal(metrics.snapshot().focusPolicy, "visible-only");
focused = true; for (let i = 0; i < 30; i++) { now += 16; scene.render(); }
assert.equal(metrics.snapshot().window.focus.unfocusedFrames, 0);
metrics.dispose(); metrics.dispose();
assert.equal(scene.onAfterRenderObservable.observers.filter(observer => !observer._willBeUnregistered).length, after);
assert.equal(scene.onBeforeRenderObservable.observers.filter(observer => !observer._willBeUnregistered).length, before);
focused = false;
const focusedMetrics = createLookdevMetrics(scene, { capacity: 30, requireFocus: true, visible: () => true, focused: () => focused, now: () => now });
for (let i = 0; i < 40; i++) { now += 16; scene.render(); }
assert.equal(focusedMetrics.snapshot().window.total, 0); assert.equal(focusedMetrics.snapshot().warmupRemaining, 30); assert.equal(focusedMetrics.snapshot().samplesDiscardedWhileUnfocused, 40);
focused = true; for (let i = 0; i < 61; i++) { now += 16; scene.render(); }
assert.equal(focusedMetrics.snapshot().window.retained, 30); assert.equal(focusedMetrics.snapshot().window.focus.focusedFrames, 30); focusedMetrics.dispose();
scene.dispose(); engine.dispose();

// Counter/capture mocks verify ownership and units. They are not a physical GPU benchmark.
for (const previous of [false, true]) {
	const timerEngine = new NullEngine(), timerScene = new Scene(timerEngine); new ArcRotateCamera("timer-check", 0, 1, 13, Vector3.Zero(), timerScene);
	const mutable = timerEngine as unknown as { _captureGPUFrameTime: boolean; captureGPUFrameTime(value: boolean): void; getGPUFrameTimeCounter(): PerfCounter; getCaps(): { timerQuery?: unknown } };
	const counter = new PerfCounter(), toggles: boolean[] = [];
	mutable._captureGPUFrameTime = previous; mutable.getCaps().timerQuery = {};
	mutable.captureGPUFrameTime = value => { mutable._captureGPUFrameTime = value; toggles.push(value); }; mutable.getGPUFrameTimeCounter = () => counter;
	let gpuClock = 0;
	const capture = createLookdevMetrics(timerScene, { visible: () => true, focused: () => true, now: () => gpuClock });
	for (let i = 0; i < 34; i++) { counter.fetchNewFrame(); counter.addCount(2_000_000, true); gpuClock += 16; timerScene.render(); }
	assert.equal(capture.snapshot().window.gpuMs.p95, 2); assert.equal(capture.snapshot().gpuScope, "frame");
	assert.equal(capture.snapshot().window.gpuMs.n, 4);
	for (let i = 0; i < 4; i++) { gpuClock += 16; timerScene.render(); }
	assert.equal(capture.snapshot().window.gpuMs.n, 4); // Repeated counter value is not four new GPU samples.
	capture.setPaused(true); counter.fetchNewFrame(); counter.addCount(9_000_000, true); timerScene.render(); capture.setPaused(false);
	capture.reset(); for (let i = 0; i < 32; i++) { gpuClock += 16; timerScene.render(); }
	assert.equal(capture.snapshot().window.gpuMs.n, 0); assert.equal(capture.snapshot().gpuStatus, "pending");
	counter.fetchNewFrame(); counter.addCount(3_000_000, true); gpuClock += 16; timerScene.render();
	assert.equal(capture.snapshot().window.gpuMs.p95, 3); assert.equal(capture.snapshot().gpuStatus, "available");
	gpuClock += 2001; timerScene.render(); assert.equal(capture.snapshot().gpuStatus, "stale"); assert.equal(capture.snapshot().gpuFreshAgeMs, 2001);
	capture.dispose(); assert.equal(mutable._captureGPUFrameTime, previous); assert.deepEqual(toggles, previous ? [true] : [true, false]); timerScene.dispose(); timerEngine.dispose();
}
console.log(JSON.stringify({ result: "PASS", engine: "NullEngine", boundedWindow: true, screenshotFramesExcluded: true, hiddenGapExcluded: true, focusExposureAndOptInGate: true,
	gpuMissingNotZero: true, gpuFreshnessAndPauseFence: true, gpuUnitsAndCaptureOwnershipMocked: true, qualification: "CPU/API lifecycle only; no native image, physical GPU, performance or device acceptance" }));

const cameraEngine = new NullEngine(), cameraScene = new Scene(cameraEngine);
const camera = new ArcRotateCamera("production-camera", .4, .9, 13, new Vector3(1, 2, 3), cameraScene);
camera.lowerRadiusLimit = 8.5; camera.upperRadiusLimit = 24; camera.inertialAlphaOffset = .3;
let view: "player" | "close" = "player";
const lock = createLookdevCameraLock(cameraScene, camera, () => lockedCamera(view, { x: 0, y: 2.3, z: 176 }));
lock.apply(); assert.equal(camera.radius, 13); assert.equal(camera.alpha, -Math.PI / 2); assert.equal(camera.inertialAlphaOffset, 0);
view = "close"; cameraScene.render(); assert.equal(camera.radius, 2.5); assert.equal(camera.lowerRadiusLimit, null);
lock.dispose(); lock.dispose(); assert.equal(camera.radius, 13); assert.equal(camera.alpha, .4); assert.equal(camera.beta, .9);
assert.deepEqual(camera.getTarget().asArray(), [1, 2, 3]); assert.equal(camera.lowerRadiusLimit, 8.5); assert.equal(camera.upperRadiusLimit, 24);
assert.equal(camera.inertialAlphaOffset, .3); cameraScene.dispose(); cameraEngine.dispose();
console.log(JSON.stringify({ result: "PASS", cameraPoseAndLimitsRestored: true, productionCameraRetained: true, player13m: true, close2_5m: true, qualification: "NullEngine camera/API check only" }));
