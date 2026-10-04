import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
import { transform } from "esbuild";

// Replay the actual entry functions; do not copy their decisions into a second implementation.
// Extract only these declarations, so importing the test never initializes the game or its assets.
const mainSource = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
const syntax = ts.createSourceFile("main.ts", mainSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const declarations = new Map();
const variables = new Set(["reportBoot", "failEntry"]);
function collect(node) {
	if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && variables.has(node.name.text)) {
		declarations.set(node.name.text, `const ${node.getText(syntax)};`);
	}
	if (ts.isFunctionDeclaration(node) && node.name?.text === "acceptEntrySnapshot") {
		declarations.set(node.name.text, node.getText(syntax));
	}
	ts.forEachChild(node, collect);
}
collect(syntax);
for (const name of ["reportBoot", "failEntry", "acceptEntrySnapshot"]) {
	assert.ok(declarations.has(name), `The startup declaration ${name} must be available for regression replay.`);
}
const replaySource = (await transform([...declarations.values()].join("\n"), { loader: "ts", format: "esm" })).code;
const createReplay = new Function("environment", `
	let gameEntryReady = false, bootPhase = "room", entryTimer = "entry-deadline";
	let entryFrameQueued = false, entryFailed = false, disposed = false, online = true;
	let socket = environment.initialSocket, connectionEpoch = 41;
	const startupFetch = new AbortController();
	const world = environment.world, startupLobby = environment.lobby;
	const clearTimeout = environment.clearTimeout;
	const abortEntryConnection = environment.abortEntryConnection;
	const readLoginLanguage = () => "en";
	const location = { reload: environment.reload };
	${replaySource}
	return {
		acceptEntrySnapshot, failEntry,
		state() { return { gameEntryReady, entryFrameQueued, entryFailed, disposed, aborted: startupFetch.signal.aborted }; },
		changeConnection(nextSocket, nextEpoch) { socket = nextSocket; connectionEpoch = nextEpoch; online = true; },
		setOnline(value) { online = value; },
		setDisposed(value) { disposed = value; },
		report(event) { reportBoot(event); },
	};
`);

function fixture() {
	const observations = { phases: [], errors: [], ready: 0, clearedTimers: [], abortedConnections: 0 };
	const afterRender = [];
	const initialSocket = { id: "first-connection" };
	const scene = { isDisposed: false, onAfterRenderObservable: { addOnce: callback => afterRender.push(callback) } };
	const entry = createReplay({
		initialSocket,
		world: { scene },
		lobby: {
			updatePhase: event => observations.phases.push({ ...event }),
			showError: (message, retry) => observations.errors.push({ message, retry }),
			ready: () => observations.ready++,
		},
		clearTimeout: timer => observations.clearedTimers.push(timer),
		abortEntryConnection: () => observations.abortedConnections++,
		reload: () => {},
	});
	return {
		entry, observations, initialSocket, scene,
		pendingFrames: () => afterRender.length,
		render() { for (const callback of afterRender.splice(0)) callback(); },
	};
}

test("a valid snapshot becomes ready only after the subsequent rendered frame", () => {
	const { entry, observations, pendingFrames, render } = fixture();
	entry.acceptEntrySnapshot();
	assert.equal(entry.state().gameEntryReady, false);
	assert.equal(observations.ready, 0);
	assert.equal(pendingFrames(), 1);
	assert.deepEqual(observations.phases, [
		{ id: "snapshot", state: "complete" },
		{ id: "first_frame", state: "active" },
	]);
	entry.acceptEntrySnapshot();
	assert.equal(pendingFrames(), 1, "duplicate snapshots cannot queue duplicate completion callbacks");
	render();
	assert.equal(entry.state().gameEntryReady, true);
	assert.equal(entry.state().entryFrameQueued, false);
	assert.equal(observations.ready, 1);
	assert.deepEqual(observations.phases.at(-1), { id: "first_frame", state: "complete" });
	assert.deepEqual(observations.clearedTimers, ["entry-deadline"]);
	entry.acceptEntrySnapshot();
	render();
	assert.equal(observations.ready, 1);
});

test("timeout followed by a late snapshot cannot replace the error with readiness", () => {
	const { entry, observations, pendingFrames, render } = fixture();
	entry.failEntry("join_timeout");
	entry.acceptEntrySnapshot();
	render();
	assert.equal(entry.state().entryFailed, true);
	assert.equal(entry.state().aborted, true);
	assert.equal(entry.state().gameEntryReady, false);
	assert.equal(pendingFrames(), 0);
	assert.equal(observations.ready, 0);
	assert.equal(observations.errors.length, 1);
	assert.equal(observations.abortedConnections, 1);
	assert.deepEqual(observations.phases, [{ id: "room", state: "error", errorCode: "join_timeout" }]);
	entry.report({ id: "snapshot", state: "complete" });
	entry.failEntry("ticket_failed");
	assert.equal(observations.phases.length, 1, "late progress cannot overwrite the terminal failure");
	assert.equal(observations.errors.length, 1);
	assert.equal(observations.abortedConnections, 1);
});

test("timeout after a snapshot was queued also suppresses its late frame callback", () => {
	const { entry, observations, render } = fixture();
	entry.acceptEntrySnapshot();
	entry.failEntry("join_timeout");
	render();
	assert.equal(entry.state().gameEntryReady, false);
	assert.equal(entry.state().entryFrameQueued, false);
	assert.equal(observations.ready, 0);
	assert.deepEqual(observations.phases.at(-1), { id: "first_frame", state: "error", errorCode: "join_timeout" });
});

test("an old snapshot cannot ready a replacement socket or connection epoch", async t => {
	for (const [label, replacement, epoch] of [
		["socket changed", true, 41],
		["epoch changed", false, 42],
		["socket and epoch changed", true, 42],
	]) await t.test(label, () => {
		const { entry, observations, initialSocket, render } = fixture();
		entry.acceptEntrySnapshot();
		entry.setOnline(false);
		entry.changeConnection(replacement ? { id: "new-connection" } : initialSocket, epoch);
		render();
		assert.equal(entry.state().gameEntryReady, false);
		assert.equal(entry.state().entryFrameQueued, false);
		assert.equal(observations.ready, 0);
		assert.equal(observations.phases.some(event => event.id === "first_frame" && event.state === "complete"), false);
		entry.acceptEntrySnapshot();
		render();
		assert.equal(entry.state().gameEntryReady, true, "the new connection's own snapshot and frame may complete entry");
		assert.equal(observations.ready, 1);
	});
});

test("disposing the page before a queued frame prevents readiness and later progress", () => {
	const { entry, observations, pendingFrames, render } = fixture();
	entry.acceptEntrySnapshot();
	entry.setDisposed(true);
	render();
	assert.equal(entry.state().gameEntryReady, false);
	assert.equal(entry.state().entryFrameQueued, false);
	assert.equal(observations.ready, 0);
	entry.acceptEntrySnapshot();
	entry.report({ id: "first_frame", state: "complete" });
	assert.equal(pendingFrames(), 0);
	assert.equal(observations.phases.length, 2);
});

test("a disposed scene or disconnected socket cannot complete a queued frame", async t => {
	for (const label of ["scene", "socket"]) await t.test(label, () => {
		const { entry, observations, scene, render } = fixture();
		entry.acceptEntrySnapshot();
		if (label === "scene") scene.isDisposed = true;
		else entry.setOnline(false);
		render();
		assert.equal(entry.state().gameEntryReady, false);
		assert.equal(observations.ready, 0);
	});
});

test("failure callbacks after a successful first frame cannot revoke readiness", () => {
	const { entry, observations, render } = fixture();
	entry.acceptEntrySnapshot();
	render();
	entry.failEntry("join_timeout");
	assert.equal(entry.state().gameEntryReady, true);
	assert.equal(entry.state().entryFailed, false);
	assert.equal(entry.state().aborted, false);
	assert.equal(observations.errors.length, 0);
	assert.equal(observations.abortedConnections, 0);
});
