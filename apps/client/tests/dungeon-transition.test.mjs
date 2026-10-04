import test from "node:test";
import assert from "node:assert/strict";
import { DungeonTransition } from "../src/dungeon-transition.mjs";

function fixture() {
	let now = 0;
	const machine = new DungeonTransition({ clock: () => now, prepareMs: 100, commitMs: 20 });
	const begin = (transferId = "t1") => machine.dispatch({ type: "begin", transferId, dungeonId: "temple" });
	const send = (type, extra = {}) => machine.dispatch({ type, generation: machine.snapshot.generation,
		transferId: machine.snapshot.transfer.transferId, ...extra });
	const destination = { reservationId: "r1", contentVersion: "v1" };
	const ready = () => {
		begin();
		send("reserved", { ...destination, expiresAt: 90 });
		send("assets_ready", { contentVersion: "v1" });
	};
	return { machine, begin, send, destination, ready, advance: (ms) => { now += ms; } };
}

test("cancel before commit releases once and preserves the old location", () => {
	for (const readyFirst of [false, true]) {
		const f = fixture();
		if (readyFirst) f.ready(); else f.begin();
		const result = f.machine.dispatch({ type: "cancel" });
		assert.equal(result.snapshot.state, "Failure");
		assert.equal(result.snapshot.reason, "cancelled");
		assert.deepEqual(result.effects.map(e => e.type), ["release", "dispose_staging"]);
		assert.equal(f.machine.dispatch({ type: "cancel" }).accepted, false);
		assert.equal(f.machine.dispatch({ type: "request_commit" }).accepted, false);
	}
});

test("server rejection is surfaced; an ambiguous post-request rejection cannot roll back", () => {
	const f = fixture();
	f.begin();
	assert.equal(f.send("rejected", { reason: "party_full" }).snapshot.reason, "party_full");
	f.ready();
	f.machine.dispatch({ type: "request_commit" });
	assert.equal(f.send("rejected", { reason: "network_error" }).accepted, false);
	assert.equal(f.machine.snapshot.state, "Commit");
	assert.equal(f.send("rejected", { reason: "expired", uncommitted: true }).snapshot.state, "Failure");
});

test("prepare and reservation deadlines expire at the boundary", () => {
	const f = fixture();
	f.begin();
	f.advance(100);
	assert.equal(f.machine.dispatch({ type: "tick" }).snapshot.state, "Failure");
	const g = fixture();
	g.ready();
	g.advance(90);
	assert.equal(g.machine.dispatch({ type: "request_commit" }).snapshot.reason, "reservation_expired");
});

test("commit timeout enters recovery; cancel and retries cannot transfer twice", () => {
	const f = fixture();
	f.ready();
	f.machine.dispatch({ type: "request_commit" });
	f.advance(20);
	const result = f.machine.dispatch({ type: "tick" });
	assert.equal(result.snapshot.state, "Recover");
	assert.ok(result.effects.some(e => e.type === "query_status"));
	assert.ok(!result.effects.some(e => e.type === "release"));
	assert.equal(f.machine.dispatch({ type: "cancel" }).accepted, false);
	assert.equal(f.machine.dispatch({ type: "request_commit" }).accepted, false);
	f.advance(20);
	assert.equal(f.machine.dispatch({ type: "tick" }).snapshot.reason, "status_timeout");
	assert.deepEqual(f.machine.dispatch({ type: "tick" }).effects, []);
});

test("readiness and commit enforce deadlines even before the adapter ticks", () => {
	const f = fixture();
	f.begin();
	f.advance(100);
	assert.equal(f.send("reserved", { ...f.destination, expiresAt: 200 }).snapshot.reason, "timeout");
	const g = fixture();
	g.begin();
	g.send("reserved", { ...g.destination, expiresAt: 200 });
	g.send("assets_ready", { contentVersion: "v1" });
	g.advance(100);
	assert.equal(g.machine.dispatch({ type: "request_commit" }).snapshot.reason, "timeout");
	const h = fixture();
	h.begin();
	h.send("reserved", { ...h.destination, expiresAt: 90 });
	h.advance(90);
	assert.equal(h.send("assets_ready", { contentVersion: "v1" }).snapshot.reason, "timeout");
});

test("stale loader completion is disposed without attaching to a new transition", () => {
	const f = fixture();
	f.begin();
	const old = { generation: f.machine.snapshot.generation, transferId: "t1" };
	f.machine.dispatch({ type: "cancel" });
	f.begin("t2");
	const result = f.machine.dispatch({ type: "assets_ready", ...old, contentVersion: "v1" });
	assert.equal(result.accepted, false);
	assert.equal(result.snapshot.state, "Prepare");
	assert.deepEqual(result.effects, [{ type: "dispose_stale", ...old }]);
	assert.equal(f.machine.dispatch({ type: "reserved", ...old, ...f.destination, expiresAt: 90 }).accepted, false);
});

test("double commit and duplicate snapshot reveal only once", () => {
	const f = fixture();
	f.ready();
	assert.equal(f.machine.dispatch({ type: "request_commit" }).effects[0].type, "confirm_and_commit");
	assert.equal(f.machine.dispatch({ type: "request_commit" }).accepted, false);
	assert.equal(f.send("destination_ready", f.destination).snapshot.state, "Commit");
	assert.equal(f.send("committed", f.destination).effects[0].type, "reveal");
	assert.equal(f.send("committed", f.destination).accepted, false);
	assert.equal(f.send("destination_ready", f.destination).accepted, false);
	assert.equal(f.machine.snapshot.state, "Enter");
});

test("reconnect after commit reuses identity and waits for staged assets plus safe snapshot", () => {
	const f = fixture();
	f.ready();
	f.machine.dispatch({ type: "request_commit" });
	f.send("committed", f.destination);
	const oldGeneration = f.machine.snapshot.generation;
	const reconnect = f.machine.dispatch({ type: "reconnect" });
	assert.equal(reconnect.snapshot.state, "Recover");
	assert.equal(reconnect.snapshot.transfer.transferId, "t1");
	assert.ok(reconnect.snapshot.generation > oldGeneration);
	const status = f.send("status_committed", f.destination);
	assert.deepEqual(status.effects.map(e => e.type), ["stage_assets", "request_destination"]);
	assert.equal(f.send("destination_ready", f.destination).snapshot.state, "Commit");
	const result = f.send("assets_ready", { contentVersion: "v1" });
	assert.equal(result.snapshot.state, "Enter");
	assert.equal(result.effects[0].type, "reveal");
	assert.equal(f.send("rejected", { reason: "late", uncommitted: true }).accepted, false);
	assert.equal(f.machine.dispatch({ type: "finish" }).snapshot.state, "Explore");
});

test("lost commit response resolves through status without a second commit", () => {
	const f = fixture();
	f.ready();
	f.machine.dispatch({ type: "request_commit" });
	f.machine.dispatch({ type: "reconnect" });
	assert.equal(f.send("status_committed", f.destination).snapshot.transfer.committed, true);
	assert.equal(f.machine.dispatch({ type: "request_commit" }).accepted, false);
});

test("a fresh coordinator resumes a committed transfer after a browser reload", () => {
	const f = fixture();
	const resume = f.machine.dispatch({ type: "resume", transferId: "t1", dungeonId: "temple", ...f.destination });
	assert.equal(resume.snapshot.state, "Recover");
	assert.deepEqual(resume.effects.map(e => e.type), ["query_status"]);
	f.send("status_committed", f.destination);
	f.send("assets_ready", { contentVersion: "v1" });
	assert.equal(f.send("destination_ready", f.destination).snapshot.state, "Enter");
	assert.equal(f.machine.dispatch({ type: "begin", transferId: "new", dungeonId: "temple" }).accepted, false);
});

test("version mismatch and wrong reservation cannot authorize a reveal", () => {
	const f = fixture();
	f.begin();
	f.send("reserved", { ...f.destination, expiresAt: 90 });
	assert.equal(f.send("assets_ready", { contentVersion: "v2" }).accepted, false);
	f.send("assets_ready", { contentVersion: "v1" });
	f.machine.dispatch({ type: "request_commit" });
	assert.equal(f.send("committed", { ...f.destination, reservationId: "other" }).accepted, false);
	assert.equal(f.send("destination_ready", { ...f.destination, contentVersion: "v2" }).accepted, false);
	assert.equal(f.machine.snapshot.state, "Commit");
});

test("load failure and precommit disconnect dispose staging; time never moves backwards", () => {
	const f = fixture();
	f.begin();
	assert.equal(f.send("load_failed", { reason: "decode_failed" }).snapshot.reason, "decode_failed");
	f.begin("t2");
	assert.equal(f.machine.dispatch({ type: "reconnect" }).snapshot.state, "Failure");
	f.advance(1);
	f.machine.dispatch({ type: "tick" });
	f.advance(-1);
	assert.throws(() => f.machine.dispatch({ type: "tick" }), /monotonic/);
	assert.throws(() => new DungeonTransition({ prepareMs: 0 }), /positive/);
});
