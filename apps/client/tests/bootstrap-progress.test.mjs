import test from "node:test";
import assert from "node:assert/strict";
import { BOOTSTRAP_PHASE_IDS, bootstrapAssetProgress, createBootstrapProgress, parseBootstrapPhaseEvent } from "../src/bootstrap-progress.mjs";

test("download completion, welcome and an offline frame cannot substitute for remaining startup gates", () => {
	const progress = createBootstrapProgress();
	for (const id of ["content", "renderer", "codecs"]) progress.update({ id, state: "complete" });
	progress.update(bootstrapAssetProgress("hero", { lengthComputable: true, loaded: 100, total: 100 }));
	assert.equal(progress.snapshot().completed, 3, "downloaded bytes do not establish decode readiness");
	assert.equal(progress.snapshot().ready, false);
	progress.update({ id: "assets", state: "complete" });
	progress.update({ id: "shaders", state: "complete" });
	progress.update({ id: "room", state: "complete" });
	assert.equal(progress.snapshot().ready, false, "welcomed room still needs local authoritative snapshot and subsequent render");
	progress.update({ id: "snapshot", state: "complete" });
	assert.equal(progress.snapshot().ready, false);
	progress.update({ id: "first_frame", state: "complete" });
	assert.equal(progress.snapshot().ready, true);
	assert.deepEqual([progress.snapshot().completed, progress.snapshot().total, progress.snapshot().unit], [8, 8, "phases"]);
	assert.equal("percentage" in progress.snapshot(), false);
});

test("unknown transfer sizes remain indeterminate and resource bytes are never aggregated", () => {
	const progress = createBootstrapProgress();
	assert.deepEqual(bootstrapAssetProgress("city", { lengthComputable: false, loaded: 12, total: 50 }), { id: "assets", state: "active", resource: "city" });
	progress.update(bootstrapAssetProgress("hero", { lengthComputable: true, loaded: 40, total: 50 }));
	progress.update(bootstrapAssetProgress("trees", { lengthComputable: true, loaded: 2, total: 10 }));
	assert.deepEqual(progress.snapshot().phases.find(row => row.id === "assets"), { id: "assets", state: "active", resource: "trees", loaded: 2, total: 10 });
	for (const bad of [{ loaded: NaN, total: 1 }, { loaded: 2, total: 1 }, { loaded: 1, total: 0 }]) {
		assert.equal("loaded" in bootstrapAssetProgress("city", { lengthComputable: true, ...bad }), false);
	}
});

test("completion is monotonic across delayed callbacks, duplicate events and explicit incomplete retries", () => {
	const progress = createBootstrapProgress(["renderer", "assets"]);
	progress.update({ id: "renderer", state: "complete" });
	assert.equal(progress.update({ id: "renderer", state: "active" }), false);
	assert.equal(progress.update({ id: "renderer", state: "error", errorCode: "late_callback" }), false);
	progress.update({ id: "assets", state: "active" });
	assert.equal(progress.update({ id: "assets", state: "active" }), false);
	progress.update({ id: "assets", state: "error", errorCode: "asset_unavailable" });
	assert.equal(progress.snapshot().failed, true);
	assert.equal(progress.snapshot().completed, 1);
	progress.update({ id: "assets", state: "active" });
	assert.equal(progress.snapshot().failed, false);
	assert.equal(progress.snapshot().phases[1].errorCode, undefined);
	progress.update({ id: "assets", state: "complete" });
	assert.equal(progress.snapshot().ready, true);
	assert.equal(progress.update({ id: "assets", state: "pending" }), false);
});

test("status rows stay bounded and repeated byte updates do not overwrite the recent phase history", () => {
	const progress = createBootstrapProgress();
	for (const id of BOOTSTRAP_PHASE_IDS) progress.update({ id, state: "active" });
	assert.equal(progress.snapshot().recent.length, 6);
	assert.deepEqual(progress.snapshot().recent.map(row => row.id), BOOTSTRAP_PHASE_IDS.slice(-6));
	progress.update(bootstrapAssetProgress("hero", { lengthComputable: true, loaded: 0, total: 100 }));
	const order = progress.snapshot().recent.map(row => row.id);
	for (let loaded = 1; loaded <= 100; loaded++) progress.update(bootstrapAssetProgress("hero", { lengthComputable: true, loaded, total: 100 }));
	assert.deepEqual(progress.snapshot().recent.map(row => row.id), order);
	assert.equal(progress.snapshot().recent.filter(row => row.id === "assets").length, 1);
});

test("DTO parsing rejects malformed or unbounded values and strips nonprimitive payloads", () => {
	const input = { id: "assets", state: "active", resource: "hero", loaded: 2, total: 3, scene: { dispose() {} }, arbitrary: "ignored" };
	assert.deepEqual(parseBootstrapPhaseEvent(input), { id: "assets", state: "active", resource: "hero", loaded: 2, total: 3 });
	for (const value of [null, [], { id: "secret", state: "active" }, { id: "assets", state: "running" }, { id: "assets", state: "active", loaded: 3, total: 4 }, { id: "assets", state: "active", resource: "a\nb" }, { id: "room", state: "error", errorCode: "x".repeat(65) }]) assert.equal(parseBootstrapPhaseEvent(value), null);
	const progress = createBootstrapProgress();
	progress.update(input);
	input.loaded = 3;
	assert.equal(progress.snapshot().phases.find(row => row.id === "assets").loaded, 2);
	assert.throws(() => { progress.snapshot().phases[3].state = "complete"; }, TypeError);
	assert.equal(progress.update({ id: "unknown", state: "complete" }), false);
});

test("phase declarations cannot add fictitious work or denominator changes", () => {
	for (const ids of [[], ["renderer", "renderer"], ["compressing"], "renderer"]) assert.throws(() => createBootstrapProgress(ids), TypeError);
	const progress = createBootstrapProgress(["room", "snapshot", "first_frame"]);
	assert.equal(progress.update({ id: "assets", state: "complete" }), false);
	assert.equal(progress.snapshot().total, 3);
});
