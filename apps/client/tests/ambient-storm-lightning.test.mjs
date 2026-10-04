import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {createLightningSchedule, lightningEnvelope, lightningQuality, writeLightningPaths,
	LIGHTNING_PATHS, LIGHTNING_POINTS_PER_PATH} from '../src/ambient-storm-lightning-policy.mjs';

const rain = {rain: 1, daylight: .5};
const root = fileURLToPath(new URL('..', import.meta.url));
const bundled = await build({stdin: {contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera';
export {Matrix,Vector3} from '@babylonjs/core/Maths/math.vector';
export {Viewport} from '@babylonjs/core/Maths/math.viewport';
export {createStormLightning} from './src/ambient-storm-lightning';`,resolveDir: root, loader: 'ts'},
	bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent'});
const api = await import('data:text/javascript;base64,' + Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function collectSchedule(stepMs, options = {}) {
	const schedule = createLightningSchedule(123), starts = [];
	for (let time = 0; time < 240_000; time += stepMs) {
		const frame = schedule.update(time, rain, options);
		if (frame.began) starts.push(frame.startedAtMs);
	}
	return starts;
}
test('seeded storm cadence is 8–20 s and identical under 16 ms and 100 ms updates', () => {
	const fast = collectSchedule(16), slow = collectSchedule(100);
	assert.deepEqual(fast, slow); assert.ok(fast.length >= 12);
	for (let i = 0; i < fast.length; i++) assert.ok(fast[i] - (fast[i - 1] ?? 0) >= 8_000 && fast[i] - (fast[i - 1] ?? 0) <= 20_000);
	const low = collectSchedule(16, {quality: {preset: 'low'}});
	for (let i = 0; i < low.length; i++) assert.ok(low[i] - (low[i - 1] ?? 0) >= 14_000);
	assert.ok(low.length < fast.length);
});
test('clear weather, reduced motion, reduced flashes and non-finite samples fail dark', () => {
	for (const [sample, options] of [[{rain: 0, daylight: 1}, {}], [rain, {reducedMotion: true}],
		[rain, {reducedFlashes: true}], [{rain: NaN, daylight: 1}, {}], [{rain: 1, daylight: NaN}, {}]]) {
		const schedule = createLightningSchedule();
		for (let time = 0; time < 80_000; time += 100) {
			const state = schedule.update(time, sample, options);
			assert.equal(state.active, false); assert.equal(state.began, false); assert.equal(state.flash, 0);
		}
	}
});
test('world-time jumps and new room revisions cancel pending bolts and wait a fresh full interval', () => {
	for (const discontinuity of ['forward', 'backward', 'revision', 'invalid']) {
		const schedule = createLightningSchedule(12); let frame;
		for (let t = 0; t <= 12_000; t += 100) frame = schedule.update(t, rain, {clockRevision: 1});
		const oldGeneration = frame.generation;
		const time = discontinuity === 'forward' ? 100_000 : discontinuity === 'backward' ? 0 : 12_001;
		if (discontinuity === 'invalid') schedule.update(NaN, rain);
		frame = schedule.update(time, rain, {clockRevision: discontinuity === 'revision' ? 2 : 1});
		assert.equal(frame.active, false); assert.equal(frame.began, false);
		assert.ok(frame.nextAtMs >= time + 8_000); assert.ok(frame.generation > oldGeneration);
	}
});
test('the single pulse has one maximum, no strobe, bounded flash and no night brightness increase', () => {
	const values = Array.from({length: 601}, (_, t) => lightningEnvelope(t));
	const maximum = Math.max(...values), peakEnd = values.lastIndexOf(maximum);
	assert.ok(maximum <= 1 && maximum > .98);
	for (let t = peakEnd; t < values.length - 1; t++) assert.ok(values[t + 1] <= values[t]);
	assert.equal(lightningEnvelope(-1), 0); assert.equal(lightningEnvelope(480), 0);
	assert.equal(lightningEnvelope(NaN), 0); assert.ok(lightningQuality({preset:'low'}).flashScale < 1);
	const day = createLightningSchedule(42), night = createLightningSchedule(42);
	for (let t = 0; t < 60_000; t += 16) {
		const a = day.update(t, {rain:1, daylight:1}), b = night.update(t, {rain:1, daylight:0});
		assert.ok(a.flash <= .09 && b.flash <= .055); assert.ok(a.flash >= b.flash);
		assert.equal(a.startedAtMs, b.startedAtMs);
	}
});
test('branched paths reuse storage, attach exactly and stay above and away from the combat corridor', () => {
	const output = new Float32Array(LIGHTNING_PATHS * LIGHTNING_POINTS_PER_PATH * 3);
	const focus = {x: 12, y: 2, z: -92};
	for (let seed = 0; seed < 100; seed++) {
		writeLightningPaths(seed, focus, {x:0, y:0, z:1}, output);
		assert.ok(output.every(Number.isFinite));
		for (let i = 0; i < output.length; i += 3) {
			assert.ok(Math.hypot(output[i] - focus.x, output[i + 2] - focus.z) > 200);
			assert.ok(output[i + 1] >= focus.y + 8);
		}
		for (let branch = 1; branch < LIGHTNING_PATHS; branch++) {
			const source = (5 + branch * 3) * 3, at = branch * LIGHTNING_POINTS_PER_PATH * 3;
			assert.deepEqual(output.slice(at, at + 3), output.slice(source, source + 3));
		}
	}
	assert.throws(() => writeLightningPaths(1, focus, undefined, new Float32Array(1)), RangeError);
});
test('distant sky geometry enters the normal 13 m player view without moving the camera', () => {
	const engine = new api.NullEngine({renderWidth:1920,renderHeight:1080}), scene = new api.Scene(engine);
	try {
		const camera = new api.ArcRotateCamera('witness', -Math.PI / 2, 1.18, 13, new api.Vector3(0,1.65,0), scene);
		camera.fov = 1.02; camera.minZ = .1; camera.maxZ = 2000; scene.activeCamera = camera;
		scene.updateTransformMatrix(true);
		const output = new Float32Array(LIGHTNING_PATHS * LIGHTNING_POINTS_PER_PATH * 3);
		const viewport = new api.Viewport(0,0,1920,1080);
		for (let seed = 0; seed < 100; seed++) {
			writeLightningPaths(seed, {x:0,y:0,z:0}, {x:0,y:0,z:1}, output);
			let visible = 0;
			for (let p = 0; p < LIGHTNING_POINTS_PER_PATH; p++) {
				const point = api.Vector3.Project(new api.Vector3(...output.slice(p * 3,p * 3 + 3)), api.Matrix.Identity(), scene.getTransformMatrix(), viewport);
				if (point.x > 0 && point.x < 1920 && point.y > 0 && point.y < 1080 && point.z > 0 && point.z < 1) visible++;
			}
			assert.ok(visible >= 5, `seed ${seed} has ${visible} visible main-bolt points`);
		}
	} finally {scene.dispose(); engine.dispose();}
});
function fixture(run) {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	try {return run(scene);} finally {scene.dispose(); engine.dispose();}
}
test('actual Babylon pool reuses geometry and buffers across strikes; thunder is delayed and all resources dispose', () => fixture(scene => {
	const flashes = [], thunder = [];
	const runtime = api.createStormLightning(scene, {seed:123, quality:{preset:'high'}, onFlash:x=>flashes.push(x), onThunder:x=>thunder.push(x)});
	const mesh = scene.getMeshByName('ambient-storm-lightning');
	const geometry = mesh.geometry, positions = mesh.getVertexBuffer('position').getBuffer(), colours = mesh.getVertexBuffer('color').getBuffer();
	const focus = {x:0,y:0,z:0};
	for (let t = 0; t < 40_000; t += 16) runtime.update(rain, t, focus);
	assert.ok(runtime.diagnostics().strikeCount >= 2); assert.equal(thunder.length, runtime.diagnostics().strikeCount);
	assert.equal(mesh.geometry, geometry); assert.equal(mesh.getVertexBuffer('position').getBuffer(), positions);
	assert.equal(mesh.getVertexBuffer('color').getBuffer(), colours); assert.equal(scene.meshes.length, 1);
	assert.equal(Object.keys(geometry.getVertexBuffers()).length, 2); assert.equal(runtime.diagnostics().maxDrawCalls, 1);
	assert.equal(runtime.diagnostics().maxVertices, 600); assert.equal(runtime.diagnostics().maxTriangles, 960);
	for (const event of thunder) {assert.ok(event.delayMs > 200); assert.equal(event.playAtWorldMs, event.strikeAtWorldMs + event.delayMs);}
	assert.ok(flashes.some(x=>x > 0));
	runtime.dispose(); runtime.dispose(); runtime.update(rain, 50_000, focus);
	assert.equal(scene.meshes.length, 0); assert.equal(scene.materials.filter(x=>x.name === 'ambient-storm-lightning-material').length, 0);
	assert.equal(runtime.diagnostics().activePaths, 0); assert.equal(runtime.diagnostics().disposed, true); assert.equal(flashes.at(-1), 0);
}));
test('clearing rain or accessibility cancels the visible pool and pending thunder immediately', () => fixture(scene => {
	const thunder = [];
	const runtime = api.createStormLightning(scene, {seed:123, onThunder:x=>thunder.push(x)});
	const focus = {x:0,y:0,z:0}; let strikeTime = 0;
	for (let t = 0; t < 30_000; t += 16) {
		runtime.update(rain, t, focus);
		if (runtime.diagnostics().pendingThunder) {strikeTime = t; break;}
	}
	assert.ok(strikeTime > 0); assert.ok(runtime.diagnostics().activePaths > 0);
	runtime.update({rain:0,daylight:1}, strikeTime + 16, focus);
	assert.equal(runtime.diagnostics().activePaths, 0); assert.equal(runtime.diagnostics().pendingThunder, false);
	for (let t = strikeTime + 32; t < strikeTime + 1_000; t += 16) runtime.update({rain:0,daylight:1}, t, focus);
	assert.equal(thunder.length, 0);
	runtime.setAccessibility({reducedFlashes:true});
	for (let t = strikeTime + 1_000; t < strikeTime + 50_000; t += 16) runtime.update(rain, t, focus);
	assert.equal(runtime.diagnostics().activePaths, 0); assert.equal(thunder.length, 0);
	runtime.dispose();
}));
