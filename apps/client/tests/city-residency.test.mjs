import test from "node:test";
import assert from "node:assert/strict";
import { planCityResidency, resolveCityResidencyProfile } from "../src/city-residency.mjs";

const base = resolveCityResidencyProfile("medium", { formFactor: "mobile" });
const cell = (id, z, bytes = 8_000_000) => ({ id, bounds: { minX: -10, maxX: 10, minZ: z - 10, maxZ: z + 10 }, lods: { near: { residentBytes: bytes }, mid: { residentBytes: Math.floor(bytes / 4) }, far: { residentBytes: Math.floor(bytes / 20) } } });
const row = (cellId, lod) => ({ cellId, lod });

test("walking from meadow through gate to plaza prefetches ahead and releases the old district", () => {
	const cells = [cell("gate", 24), cell("canal", 100), cell("plaza", 176), cell("castle", 280)];
	let resident = [], previous = {}, sawApproach = false, sawGateRetirement = false;
	for (let z = -70; z <= 270; z += 10) {
		const plan = planCityResidency({ cells, resident, previous, position: { x: 0, z }, velocity: { x: 0, z: 6 }, profile: base });
		sawApproach ||= plan.load.some(load => load.reason === "approach");
		sawGateRetirement ||= plan.evict.some(evict => evict.cellId === "gate");
		assert.ok(plan.budget.withinBudget);
		assert.ok(plan.budget.residentCells <= base.maxResidentCells);
		assert.ok(plan.budget.inflightCells <= base.maxInflightCells);
		resident = resident.filter(item => !plan.evict.some(evict => evict.cellId === item.cellId));
		for (const load of plan.load) resident = [...resident.filter(item => item.cellId !== load.cellId), row(load.cellId, load.lod)];
		previous = plan.next;
	}
	assert.ok(sawApproach);
	assert.ok(sawGateRetirement);
	assert.equal(resident.find(item => item.cellId === "castle").lod, "near");
});

test("idle camera motion around a near boundary does not reload or cancel the district", () => {
	const cells = [cell("plaza", 176)];
	const resident = [row("plaza", "near")];
	let previous = {};
	for (const z of [176, 132, 130, 134, 131, 133, 129, 132, 131]) {
		const plan = planCityResidency({ cells, resident, previous, position: { x: 0, z }, profile: base });
		assert.equal(plan.selection[0].lod, "near");
		assert.deepEqual(plan.load, []);
		assert.deepEqual(plan.cancel, []);
		previous = plan.next;
	}
	const leaving = planCityResidency({ cells, resident, previous, position: { x: 0, z: 119 }, profile: base });
	assert.equal(leaving.load[0].lod, "mid");
	assert.deepEqual(leaving.retireAfterReady, [{ cellId: "plaza", lod: "near", replacementLod: "mid" }]);
});

test("a slow network and teleport cancel obsolete requests before budgeting the destination", () => {
	const cells = [cell("gate", 24), cell("castle", 280), cell("remote", 900)];
	const before = planCityResidency({ cells, position: { x: 0, z: 24 }, profile: base });
	const inflight = before.load.map((load, index) => ({ ...row(load.cellId, load.lod), requestId: `request-${index}` }));
	const plan = planCityResidency({ cells, inflight, resident: [row("gate", "far")], previous: before.next, position: { x: 0, z: 900 }, velocity: { x: 0, z: 1000 }, profile: base });
	assert.equal(plan.teleported, true);
	assert.equal(plan.evict[0].cellId, "gate");
	assert.equal(plan.cancel.length, inflight.length);
	assert.equal(plan.load[0].cellId, "remote");
	assert.equal(plan.selection.length, 1);
	assert.ok(plan.budget.withinBudget);
});

test("shared pending loads retain request identity and do not download on every movement update", () => {
	const cells = [cell("gate", 24)];
	const first = planCityResidency({ cells, position: { x: 0, z: 24 }, profile: base });
	const inflight = [{ ...row("gate", first.load[0].lod), requestId: "gate-7" }];
	for (const z of [25, 26, 27, 28]) {
		const plan = planCityResidency({ cells, inflight, previous: first.next, position: { x: 0, z }, profile: base });
		assert.equal(plan.selection[0].state, "loading");
		assert.deepEqual(plan.load, []);
		assert.deepEqual(plan.cancel, []);
	}
});

test("dense plaza traversal remains inside both decoded memory and cell limits", () => {
	const cells = Array.from({ length: 50 }, (_, index) => ({ ...cell(`block-${index}`, 176 + index * 2, 30_000_000), bounds: { minX: index % 5 * 20, maxX: index % 5 * 20 + 15, minZ: 160 + Math.floor(index / 5) * 20, maxZ: 175 + Math.floor(index / 5) * 20 } }));
	const profile = { ...base, maxResidentBytes: 22_000_000, maxResidentCells: 3, maxInflightCells: 2 };
	const resident = cells.slice(0, 6).map(item => row(item.id, "near"));
	const plan = planCityResidency({ cells, resident, position: { x: 5, z: 170 }, reservedBytes: 2_000_000, profile });
	assert.ok(plan.budget.withinBudget);
	assert.ok(plan.budget.accountedBytes <= 22_000_000);
	assert.ok(plan.selection.length <= 3);
	assert.ok(plan.load.length <= 2);
	assert.ok(plan.evict.length >= 4);
	assert.equal(plan.selection[0].cellId, "block-0");
	assert.ok(plan.selection.every(item => item.lod !== "near"));
	assert.equal(plan.keepDistantFallback, true);
});

test("an oversized near-only district cannot bypass the mobile ceiling", () => {
	const district = cell("huge", 176, 120_000_000);
	delete district.lods.mid; delete district.lods.far;
	const plan = planCityResidency({ cells: [district], position: { x: 0, z: 176 }, profile: base });
	assert.deepEqual(plan.load, []);
	assert.deepEqual(plan.selection, []);
	assert.equal(plan.rejected[0].reason, "byte-budget");
	assert.ok(plan.budget.withinBudget);
});

test("budget includes old and new LOD together until replacement is ready", () => {
	const cells = [cell("plaza", 176, 8_000_000)];
	const plan = planCityResidency({ cells, resident: [row("plaza", "mid")], position: { x: 0, z: 176 }, profile: base });
	assert.equal(plan.budget.accountedBytes, 10_000_000);
	assert.equal(plan.load[0].residentBytes, 8_000_000);
	assert.equal(plan.retireAfterReady[0].lod, "mid");
	const constrained = planCityResidency({ cells, resident: [row("plaza", "mid")], position: { x: 0, z: 176 }, profile: { ...base, maxResidentBytes: 9_000_000 } });
	assert.equal(constrained.selection[0].lod, "mid");
	assert.deepEqual(constrained.load, []);
});

test("approach does not prefetch behind the traveller and speed cannot widen the corridor indefinitely", () => {
	const nearOnly = z => ({ ...cell(`zone-${z}`, z), lods: { near: { residentBytes: 1_000_000 } } });
	const cells = [nearOnly(95), nearOnly(-95), nearOnly(1000)];
	const plan = planCityResidency({ cells, position: { x: 0, z: 0 }, velocity: { x: 0, z: 100_000 }, profile: base });
	assert.deepEqual(plan.load.map(load => load.cellId), ["zone-95"]);
	assert.equal(plan.load[0].reason, "approach");
});

test("catalog validation rejects malformed assets before any plan is emitted", () => {
	assert.throws(() => planCityResidency({ cells: [cell("a", 0), cell("a", 10)], position: { x: 0, z: 0 } }), /unique/);
	assert.throws(() => planCityResidency({ cells: [cell("a", 0, NaN)], position: { x: 0, z: 0 } }), /safe integer/);
	assert.throws(() => planCityResidency({ cells: [cell("a", 0)], position: { x: Infinity, z: 0 } }), /finite/);
	assert.throws(() => resolveCityResidencyProfile("cinema"), /Unknown/);
	assert.ok(resolveCityResidencyProfile("ultra", { formFactor: "mobile" }).maxResidentBytes <= base.maxResidentBytes);
});
