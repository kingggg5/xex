import test from "node:test";
import assert from "node:assert/strict";
import { createRendererRecoveryController } from "../src/renderer-recovery.mjs";

test("renderer restore hides recovery state and cancels the reload fallback", () => {
	const calls = [];
	let cancelled = false;
	const controller = createRendererRecoveryController({
		onLost: () => calls.push("lost"),
		onRestored: () => calls.push("restored"),
		onReloadAvailable: () => calls.push("reload-available"),
		schedule: () => 7,
		cancel: (id) => { assert.equal(id, 7); cancelled = true; },
	});
	controller.contextLost();
	assert.deepEqual(calls, ["lost"]);
	controller.contextRestored();
	assert.deepEqual(calls, ["lost", "restored"]);
	assert.equal(cancelled, true);
});

test("persistent renderer loss reveals a manual reload fallback", () => {
	const calls = [];
	let timerCallback;
	const controller = createRendererRecoveryController({
		onLost: () => calls.push("lost"),
		onRestored: () => calls.push("restored"),
		onReloadAvailable: () => calls.push("reload-available"),
		schedule: (callback, delay) => { assert.equal(delay, 8_000); timerCallback = callback; return 1; },
		cancel: () => {},
	});
	controller.contextLost();
	timerCallback();
	assert.deepEqual(calls, ["lost", "reload-available"]);
});
