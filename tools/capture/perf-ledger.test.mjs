// node --test tools/capture/perf-ledger.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import { captureVerdict, compareRows, deviceClassOf, regression } from "./perf-ledger.mjs";

test("p95 rule: worse by more than 10 % or 1 ms, after the noise floor", () => {
	assert.equal(regression(10, 11.2, 0).flagged, true);
	assert.equal(regression(5, 5.6, 0).flagged, true);
	assert.equal(regression(10, 10.9, 0).flagged, false);
	assert.equal(regression(10, 11.2, 0.5).flagged, false);
	assert.equal(regression(10, 8, 0).status, "improved");
	assert.equal(regression(null, 8, 0).status, "n/a");
});

test("capture verdicts refuse blank, invalid GPU and fallback shots", () => {
	assert.deepEqual(captureVerdict({ image: "x.png", blank: false }, { metrics: { hiddenFrames: 0 } }).invalid, []);
	const blank = captureVerdict({ image: "x.png", blank: true }, { gpuErrors: { count: 3 }, metrics: {} });
	assert.equal(blank.capture, "BLANK_RENDER");
	assert.ok(blank.invalid.includes("GPU_VALIDATION_ERRORS"));
	assert.equal(captureVerdict({ image: "x.png" }, { renderer: { requested: "webgpu", actual: "WebGL2" }, metrics: {} }).capture, "FALLBACK_BACKEND");
	assert.equal(captureVerdict({ image: "x.png" }, { settled: { settled: false }, metrics: {} }).capture, "SCENE_NOT_SETTLED");
});

test("device class comes from the WebGL adapter string", () => {
	assert.equal(deviceClassOf({ shots: { a: { adapter: "Google Inc. (NVIDIA) · ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 (0x00001C81) Direct3D11 vs_5_0 ps_5_0, D3D11)" } } }), "desktop-gtx1050");
	assert.equal(deviceClassOf({ shots: {} }), "desktop-unknown");
});

test("compare matches scenarios across runs and subtracts the noise floor", () => {
	const row = (run, p95, floor = null) => ({ run_id: run, scenario: "city-noon-webgl2-player", device_class: "desktop-gtx1050", backend: "webgl2", build: { dirty: true },
		frames: { wall_ms: { p95 }, cpu_ms: { p95: 7 }, gpu_ms: null }, counts: { draws: 437 }, noise_floor: floor });
	const result = compareRows([row("A", 17.5), row("B", 18.4, { wall_p95_ms: 1.0 })], { baseline: "A", candidate: "B" });
	assert.equal(result.rows.length, 1);
	assert.equal(result.rows[0].status, "within noise");
	const regressed = compareRows([row("A", 17.5), row("C", 20)], { baseline: "A", candidate: "C" });
	assert.equal(regressed.regressions, 1);
});
