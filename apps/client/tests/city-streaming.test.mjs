import test from "node:test";
import assert from "node:assert/strict";
import { createGateTriggeredLoader, createLazyLoadOnce, createSouthboundCellLoader, createStagedCityLoader } from "../src/city-streaming.mjs";

test("prepared city stays hidden until an explicit reveal, and failed preparation retains the proxy", async () => {
	let swaps = 0, requests = 0;
	const city = createStagedCityLoader(async () => { requests++; if (requests === 1) throw new Error("offline"); }, () => { swaps++; });
	city.reveal(); assert.equal(swaps, 0);
	await assert.rejects(city(), /offline/); assert.equal(city.getState(), "failed");
	city.reveal(); assert.equal(swaps, 0);
	await city(); assert.equal(city.getState(), "prepared"); assert.equal(swaps, 0);
	city.reveal(); assert.equal(city.getState(), "ready"); assert.equal(swaps, 1);
	await city(); city.reveal(); assert.equal(requests, 2); assert.equal(swaps, 1);
});

test("failed activation can retry its prepared city without downloading a duplicate", async () => {
	let preparations = 0, reveals = 0;
	const city = createStagedCityLoader(async () => { preparations++; }, () => { if (++reveals === 1) throw new Error("shadow restore"); });
	await city(); assert.throws(() => city.reveal(), /shadow restore/);
	assert.equal(city.getState(), "failed");
	await city(); city.reveal();
	assert.equal(city.getState(), "ready"); assert.equal(preparations, 1); assert.equal(reveals, 2);
});

test("city detail stays unloaded until the gate asks for it", async () => {
	let requests = 0;
	const ensureLoaded = createLazyLoadOnce(async () => {
		requests += 1;
		return "full-city";
	});
	assert.equal(requests, 0);
	assert.equal(await ensureLoaded(), "full-city");
	assert.equal(requests, 1);
});

test("simultaneous gate requests share one in-flight city download", async () => {
	let requests = 0;
	let release;
	const ensureLoaded = createLazyLoadOnce(() => {
		requests += 1;
		return new Promise((resolve) => { release = resolve; });
	});
	const first = ensureLoaded();
	const second = ensureLoaded();
	assert.strictEqual(first, second);
	await Promise.resolve();
	assert.equal(requests, 1);
	release("ready");
	assert.deepEqual(await Promise.all([first, second]), ["ready", "ready"]);
});

test("failed city download can retry on a later gate crossing", async () => {
	let requests = 0;
	const ensureLoaded = createLazyLoadOnce(async () => {
		requests += 1;
		if (requests === 1) throw new Error("offline");
		return "full-city";
	});
	await assert.rejects(ensureLoaded(), /offline/);
	assert.equal(await ensureLoaded(), "full-city");
	assert.equal(requests, 2);
});

test("full city request begins at the gate, not while the player is in the meadow", async () => {
	const crossings = [];
	const update = createGateTriggeredLoader(24, async () => { crossings.push("load"); });
	assert.equal(update(-3), null);
	assert.equal(update(23.99), null);
	await update(24);
	await update(40);
	assert.deepEqual(crossings, ["load"]);
	assert.equal(update(11), null); // Re-arm only after leaving the 12 m gate buffer.
	await update(24);
	assert.deepEqual(crossings, ["load", "load"]);
});

test("southbound details load before the first ground-cell seam and only once", async () => {
	const requests = [];
	const update = createSouthboundCellLoader(-40, async () => { requests.push("load"); });
	assert.equal(update(-3), null);
	assert.equal(update(-39.99), null);
	await update(-40);
	await update(-96);
	assert.deepEqual(requests, ["load"]);
});

test("failed southbound cell load retries when the player remains at the seam", async () => {
	let requests = 0;
	const update = createSouthboundCellLoader(-40, async () => {
		requests += 1;
		if (requests === 1) throw new Error("offline");
	});
	await assert.rejects(update(-42), /offline/);
	await update(-43);
	assert.equal(requests, 2);
});
