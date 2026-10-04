import test from "node:test";
import assert from "node:assert/strict";
import {localCooldownDeadline, ActionResultOrder} from "./cooldown-clock.mjs";
test("cooldown maps room time to browser time without renewing delayed replies", () => {
	assert.equal(localCooldownDeadline(6000n,100,200),1200);
	assert.equal(localCooldownDeadline(6000n,110,700),1200);
	assert.equal(localCooldownDeadline(6000n,120,1200),0);
});
test("delayed action replies cannot reset a newer action, and room joins reset ordering", () => {
	const order = new ActionResultOrder();
	order.register("dodge", 1);
	order.register("guard", 2);
	order.register("dodge", 3);
	assert.equal(order.isLatest("dodge", 1), false);
	assert.equal(order.isLatest("guard", 2), true);
	assert.equal(order.isLatest("dodge", 3), true);
	assert.equal(order.isLatest("dodge", 1), false);
	order.reset(); order.register("dodge", 1);
	assert.equal(order.isLatest("dodge", 3), false);
	assert.equal(order.isLatest("dodge", 1), true);
});
test("cooldown rejects unsafe clocks and bounds stale room deadlines", () => {
	assert.equal(localCooldownDeadline(0n,1,200),0);
	assert.equal(localCooldownDeadline(9007199254740993n,1,200),0);
	assert.equal(localCooldownDeadline(6000n,NaN,200),0);
	assert.equal(localCooldownDeadline(9000000,1,200,5000),5200);
});
