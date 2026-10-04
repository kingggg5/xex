import test from "node:test";
import assert from "node:assert/strict";
import { LOOKDEV_MAX_SAMPLES, LookdevSampleWindow, clonePrimitiveMetadata, compareLookdevPacks, crc32, createEvidenceZip, evidenceSlug,
	lockedCamera, parseLookdevRequest, summarize } from "../src/lookdev/lookdev-data.mjs";

test("lookdev requests are explicit, bounded and path-safe", () => {
	assert.equal(parseLookdevRequest("?set=water"), null);
	assert.deepEqual(parseLookdevRequest("?lookdev=1&set=Water&cycle=water-01&variant=B&lodDistance=40"), { pillar: "water", cycle: "water-01", variant: "B", lodDistance: 40 });
	assert.deepEqual(parseLookdevRequest("?lookdev=1&set=../../secret&cycle=..&variant=E&lodDistance=999"), { pillar: "water", cycle: "baseline", variant: "A", lodDistance: null });
	assert.equal(evidenceSlug("x".repeat(65)), "baseline");
});
test("player camera is exactly 13m; close and elevated reviews differ; LOD distances are explicit", () => {
	const target = { x: 0, y: 2.3, z: 176 };
	assert.equal(lockedCamera("player", target).radius, 13);
	assert.notDeepEqual(lockedCamera("side", target), lockedCamera("player", target));
	assert.equal(lockedCamera("close", target).radius, 2.5);
	assert.equal(lockedCamera("elevated", target).radius, 26);
	assert.equal(lockedCamera("player", target, 120).radius, 120);
	assert.throws(() => lockedCamera("arbitrary", target));
	assert.throws(() => lockedCamera("player", { ...target, x: NaN }));
	assert.throws(() => lockedCamera("player", target, 99));
	assert.deepEqual(lockedCamera("player", { ...target, ignoredMesh: {} }).target, target);
});
test("metadata rejects engine/class objects, cycles and large/unbounded values", () => {
	class MeshLike { constructor() { this.name = "not-a-DTO"; } }
	const cycle = {}; cycle.parent = cycle;
	for (const value of [new MeshLike(), cycle, { value: undefined }, { value: () => {} }, { value: Infinity }, { text: "x".repeat(65537) }]) assert.throws(() => clonePrimitiveMetadata(value));
	const valid = { deviceLabel: "Unqualified browser", phaseSeed: "seed-01", assets: { runtime: "hash" }, settings: [1, true, null] };
	const copied = clonePrimitiveMetadata(valid); assert.deepEqual(copied, valid); assert.notEqual(copied.assets, valid.assets);
});
test("p50/p95 omit missing values and use documented nearest-rank statistics", () => {
	assert.deepEqual(summarize([NaN, Infinity]), { n: 0, p50: null, p95: null, min: null, max: null });
	assert.deepEqual(summarize([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, NaN]), { n: 10, p50: 5, p95: 10, min: 1, max: 10 });
});
test("a bounded render window evicts old frames without inventing unavailable GPU data", () => {
	const window = new LookdevSampleWindow(30);
	for (let i = 0; i < 100; i++) window.push({ frameIntervalMs: i, cpuSceneMs: 2, cpuSubmissionMs: 1, cpuTargetsMs: 0,
		gpuMs: null, drawCalls: 12, activeMeshes: 3, activeTriangles: 120, particles: 0 });
	const result = window.snapshot(); assert.equal(result.retained, 30); assert.equal(result.total, 100);
	assert.equal(result.frameIntervalMs.min, 70); assert.equal(result.frameIntervalMs.max, 99); assert.equal(result.gpuMs.n, 0); assert.equal(result.gpuMs.p95, null);
	assert.equal(new LookdevSampleWindow(Infinity).capacity, 600);
	assert.equal(new LookdevSampleWindow(900000).capacity, LOOKDEV_MAX_SAMPLES);
	window.reset(); assert.equal(window.snapshot().retained, 0);
});
test("focus exposure follows the retained ring rather than only the latest focus boolean", () => {
	const window = new LookdevSampleWindow(30);
	const row = { frameIntervalMs: 16, cpuSceneMs: 2, cpuSubmissionMs: 1, cpuTargetsMs: 0, gpuMs: null, drawCalls: 12, activeMeshes: 3, activeTriangles: 120, particles: 0 };
	for (let i = 0; i < 30; i++) window.push({ ...row, focused: true });
	for (let i = 0; i < 5; i++) window.push({ ...row, focused: false });
	assert.deepEqual(window.snapshot().focus, { focusedFrames: 25, unfocusedFrames: 5, unknownFrames: 0 });
	for (let i = 0; i < 30; i++) window.push({ ...row, focused: true });
	assert.deepEqual(window.snapshot().focus, { focusedFrames: 30, unfocusedFrames: 0, unknownFrames: 0 });
	window.reset(); window.push(row); assert.equal(window.snapshot().focus.unknownFrames, 1);
});
test("evidence ZIP contains standards-compliant sizes, offsets and CRC", () => {
	const payload = new TextEncoder().encode("123456789"); assert.equal(crc32(payload), 0xcbf43926);
	const zip = createEvidenceZip([{ name: "lookdev/water/baseline/A-player.png", bytes: payload }, { name: "lookdev/water/baseline/A-manifest.json", bytes: new TextEncoder().encode("{}") }]);
	const view = new DataView(zip.buffer); assert.equal(view.getUint32(0, true), 0x04034b50);
	assert.equal(view.getUint32(14, true), 0xcbf43926); assert.equal(view.getUint32(18, true), 9);
	const end = zip.length - 22; assert.equal(view.getUint32(end, true), 0x06054b50); assert.equal(view.getUint16(end + 10, true), 2);
	assert.equal(view.getUint32(view.getUint32(end + 16, true), true), 0x02014b50);
});
test("ZIP refuses unsafe, duplicate, oversized and excessive entries", () => {
	for (const name of ["../escape.png", "/absolute.png", "a/../../escape.png", "a//b", "C:/escape", "a\\b"]) assert.throws(() => createEvidenceZip([{ name, bytes: new Uint8Array() }]));
	assert.throws(() => createEvidenceZip([{ name: "x.png", bytes: new Uint8Array() }, { name: "x.png", bytes: new Uint8Array() }]));
	assert.throws(() => createEvidenceZip(Array.from({ length: 17 }, (_, i) => ({ name: `${i}.png`, bytes: new Uint8Array() }))));
	assert.throws(() => createEvidenceZip([{ name: "x.png", bytes: new Uint8Array(48 * 1024 * 1024) }]));
});
const pack = value => ({ pillar: "water", settings: { tier: "high", hours: 12, weather: "clear" }, lodDistance: null,
	capturePhaseFrozen: true, metadata: { phaseSeed: "water-01", deviceLabel: "Synthetic test device" }, captures: ["player", "side", "close", "elevated"].map(view => ({
		view, camera: lockedCamera(view, { x: 0, y: 2.3, z: 176 }), renderIdentity: { backend: "WebGL2", width: 1280, height: 720, hardwareScalingLevel: 1, gpuScope: "unavailable" },
		imageSize: { width: 1280, height: 720 }, metrics: { gpuStatus: "unavailable", window: { focus: { focusedFrames: 60, unfocusedFrames: 0, unknownFrames: 0 }, frameIntervalMs: { p95: value }, cpuSceneMs: { p95: 3 }, gpuMs: { n: 0, p95: null }, drawCalls: { p95: 60 }, activeTriangles: { p95: 10000 } } },
	})) });
test("matched A/B records report measured deltas, with unknown GPU still null", () => {
	const result = compareLookdevPacks(pack(20), pack(18)); assert.equal(result.comparable, true); assert.equal(result.deltas.length, 4);
	assert.equal(result.deltas[0].p95FrameMs, -2); assert.equal(result.deltas[0].p95GpuMs, null);
});
test("A/B rejects mismatched camera, preset, time, resolution and uncontrolled phase", () => {
	for (const edit of [b => { b.settings.hours = 18; }, b => { b.settings.tier = "low"; }, b => { b.captures[0].camera.radius = 14; },
		b => { b.captures[0].renderIdentity.width = 1920; }, b => { b.capturePhaseFrozen = false; }, b => { b.metadata.phaseSeed = null; }, b => { b.metadata.deviceLabel = "Another test device"; },
		b => { b.captures[0].metrics.window.focus.unfocusedFrames = 1; }, b => { delete b.captures[0].metrics.window.focus; }]) {
		const b = pack(18); edit(b); const result = compareLookdevPacks(pack(20), b); assert.equal(result.comparable, false); assert.deepEqual(result.deltas, []);
	}
	assert.equal(compareLookdevPacks(null, null).comparable, false);
});
test("GPU deltas require enough fresh query results and never reuse a stale percentile", () => {
	const a = pack(20), b = pack(18);
	for (const capture of a.captures) { capture.metrics.gpuStatus = "available"; capture.metrics.window.gpuMs = { n: 45, p95: 5 }; }
	for (const capture of b.captures) { capture.metrics.gpuStatus = "available"; capture.metrics.window.gpuMs = { n: 40, p95: 4 }; }
	assert.equal(compareLookdevPacks(a, b).deltas[0].p95GpuMs, -1);
	b.captures[0].metrics.gpuStatus = "stale"; assert.equal(compareLookdevPacks(a, b).deltas[0].p95GpuMs, null);
	b.captures[0].metrics.gpuStatus = "available"; b.captures[0].metrics.window.gpuMs.n = 2; assert.equal(compareLookdevPacks(a, b).deltas[0].p95GpuMs, null);
});
