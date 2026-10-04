import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';

/** Drive the SDK's queued RAF callback; no Scene or scene.render is created. */
function nativeFrames(maxFPS) {
	const engine = new NullEngine({ renderWidth: 8, renderHeight: 8 });
	engine.maxFPS = maxFPS;
	let nextId = 0, now = 0, requested = 0, cancelled = 0;
	const queue = new Map(), events = [], accepted = [], engineDeltaSamples = [];
	engine.customAnimationFrameRequester = {
		requestAnimationFrame(callback) { const id = ++nextId; queue.set(id, callback); requested++; return id; },
		cancelAnimationFrame(id) { if (queue.delete(id)) cancelled++; },
	};
	engine.onBeginFrameObservable.add(() => events.push({ phase: 'begin', timestamp: now }));
	engine.onEndFrameObservable.add(() => events.push({ phase: 'end', timestamp: now }));
	const callback = () => {
		events.push({ phase: 'callback', timestamp: now });
		accepted.push(now); engineDeltaSamples.push(engine.getDeltaTime());
	};
	engine.runRenderLoop(callback);
	assert.equal(queue.size, 1, 'The native scheduler must queue one callback.');
	function tick(timestamp) {
		now = timestamp;
		assert.equal(queue.size, 1, 'Native loop should not multiply RAF requests.');
		const [id, queued] = queue.entries().next().value;
		queue.delete(id); queued(timestamp);
		assert.equal(queue.size, 1, 'Native loop must continue after both accepted and skipped frames.');
	}
	function close() {
		engine.stopRenderLoop(callback);
		assert.equal(queue.size, 0, 'Stopping the actual SDK loop must cancel its queued callback.');
		engine.dispose();
	}
	return { engine, tick, close, accepted, events, engineDeltaSamples, get requested() { return requested; }, get cancelled() { return cancelled; } };
}

function checkFrameEvents(run) {
	assert.equal(run.events.length, run.accepted.length * 3);
	for (let i = 0; i < run.events.length; i += 3) {
		assert.deepEqual(run.events.slice(i, i + 3).map(event => event.phase), ['begin', 'callback', 'end']);
		assert.ok(run.events.slice(i, i + 3).every(event => event.timestamp === run.accepted[i / 3]));
	}
	assert.equal(run.engine.frameId, run.accepted.length, 'Only accepted frames advance the native frame ID.');
}

function feed(run, rafHz, seconds, offset = 0) {
	for (let tick = 1; tick <= rafHz * seconds; tick++) run.tick(offset + tick * 1000 / rafHz);
}

for (const rafHz of [60, 120]) for (const cap of [30, 60]) {
	test(`Native maxFPS ${cap} gates begin/callback/end on a ${rafHz}Hz requester`, () => {
		const run = nativeFrames(cap);
		try {
			feed(run, rafHz, 10);
			assert.ok(Math.abs(run.accepted.length - cap * 10) <= 1, `Actual accepted count ${run.accepted.length} differs from ${cap * 10}.`);
			checkFrameEvents(run);
			for (let i = 1; i < run.accepted.length; i++) {
				const gap = run.accepted[i] - run.accepted[i - 1];
				assert.ok(gap >= 1000 / cap - 1000 / rafHz - .001 && gap <= 1000 / cap + 1000 / rafHz + .001, `Unexpected SDK cadence gap: ${gap}.`);
			}
			assert.ok(run.engineDeltaSamples.every(Number.isFinite));
		} finally { run.close(); }
	});
}

test('Native limiter skips beginFrame itself, then supports a quality cap change and uncapping', () => {
	const run = nativeFrames(30);
	try {
		run.tick(1000 / 120);
		assert.equal(run.accepted.length, 0); assert.equal(run.events.length, 0); assert.equal(run.engine.frameId, 0);
		for (let tick = 2; tick <= 600; tick++) run.tick(tick * 1000 / 120);
		const firstCount = run.accepted.length;
		assert.ok(Math.abs(firstCount - 150) <= 1);
		run.engine.maxFPS = 60;
		feed(run, 120, 5, 5000);
		assert.ok(Math.abs((run.accepted.length - firstCount) - 300) <= 1);
		const beforeUncap = run.accepted.length;
		run.engine.maxFPS = undefined;
		feed(run, 120, 1, 10000);
		assert.equal(run.accepted.length - beforeUncap, 120);
		checkFrameEvents(run);
	} finally { run.close(); }
});

test('Native maxFPS zero schedules no engine frames; stop still cancels the queued requester', () => {
	const run = nativeFrames(0);
	feed(run, 60, 1);
	assert.equal(run.accepted.length, 0); assert.equal(run.events.length, 0); assert.equal(run.engine.frameId, 0);
	run.close(); assert.equal(run.cancelled, 1);
});

// Deliberate limitation: synthetic RAF timestamps exercise _renderLoop /
// _processFrame gating. NullEngine's getDeltaTime uses real PrecisionDate.Now
// during beginFrame, not those timestamps. Tests therefore do not manufacture
// or assert 33.3/16.7ms animation deltas, particle speed, actual FPS or GPU work.
