import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {createNightMoteSeeds, nightMoteOpacity, nightMoteBudget, sampleNightMote} from '../src/ambient-night-motes-policy.mjs';

const habitats = [{x: 8, y: 2, z: -12, radius: 2, kind: 'vegetation'}, {x: -4, y: .7, z: 8, radius: 3, kind: 'water'}];
const quality = (preset = 'high', formFactor = 'desktop') => ({preset, formFactor});
test('night, twilight and rain use the shared daylight/rain sample and fail dark on invalid state', () => {
	assert.equal(nightMoteOpacity({daylight: 1, rain: 0}), 0);
	assert.equal(nightMoteOpacity({daylight: 0, rain: 0}), 1);
	const dusk = nightMoteOpacity({daylight: .15, rain: 0});
	assert.ok(dusk > .2 && dusk < .8);
	assert.equal(nightMoteOpacity({daylight: 0, rain: 1}), 0);
	assert.ok(nightMoteOpacity({daylight: 0, rain: .4}) < 1);
	assert.equal(nightMoteOpacity({daylight: NaN, rain: 0}), 0);
	assert.equal(nightMoteOpacity(undefined), 0);
});
test('quality budgets remain bounded at 72 desktop and 24 mobile', () => {
	assert.deepEqual(['low', 'medium', 'high', 'ultra'].map(p => nightMoteBudget(quality(p))), [12, 24, 48, 72]);
	assert.deepEqual(['low', 'medium', 'high', 'ultra'].map(p => nightMoteBudget(quality(p, 'mobile'))), [12, 24, 24, 24]);
	assert.equal(nightMoteBudget({preset: 'bogus'}), 24);
});
test('habitats are deterministic, bounded and copied; invalid or excessive sets reject', () => {
	const input = structuredClone(habitats), seeds = createNightMoteSeeds(input);
	assert.equal(seeds.length, 72);
	assert.deepEqual(seeds, createNightMoteSeeds(input));
	input[0].x = 900;
	assert.notEqual(seeds[0].x, 900);
	assert.ok(seeds.every(seed => seed.size >= .075 && seed.size <= .11));
	assert.equal(createNightMoteSeeds([]).length, 0);
	assert.throws(() => createNightMoteSeeds(Array(25).fill(habitats[0])), RangeError);
	assert.throws(() => createNightMoteSeeds([{...habitats[0], x: NaN}]), TypeError);
	assert.throws(() => createNightMoteSeeds([{...habitats[0], radius: 1000}]), TypeError);
});
test('reduced motion freezes flight and pulsing; near-camera and far sprites fade out', () => {
	const seed = createNightMoteSeeds(habitats)[0], focus = {x: 0, y: 0, z: 0};
	const a = {x: 0, y: 0, z: 0, alpha: 0}, b = {...a};
	assert.equal(sampleNightMote(seed, 0, true, focus, 1, a), a);
	sampleNightMote(seed, 999, true, focus, 1, b);
	assert.deepEqual(a, b);
	sampleNightMote(seed, 12, false, focus, 1, b);
	assert.notDeepEqual(a, b);
	sampleNightMote(seed, 0, true, seed, 1, a); assert.equal(a.alpha, 0);
	sampleNightMote(seed, 0, true, {x: 900, y: 0, z: 0}, 1, a); assert.equal(a.alpha, 0);
});
test('flight and pulse remain continuous across the existing NatureClock 2π phase wrap', () => {
	const seed = createNightMoteSeeds(habitats)[0], focus = {x: 0, y: 0, z: 0};
	const a = {x: 0, y: 0, z: 0, alpha: 0}, b = {...a};
	sampleNightMote(seed, 0, false, focus, 1, a);
	sampleNightMote(seed, Math.PI * 2, false, focus, 1, b);
	for (const key of ['x', 'y', 'z', 'alpha']) assert.ok(Math.abs(a[key] - b[key]) < 1e-12);
});

const bundled = await build({stdin: {contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {createNightMotes} from './src/ambient-night-motes';`,
	resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'ts'},
	bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent'});
const api = await import('data:text/javascript;base64,' + Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function fixture(run) {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	const motes = api.createNightMotes(scene, {clusters: habitats, quality: quality()});
	const system = scene.particleSystems.find(s => s.name === 'ambient-night-motes');
	const tick = () => {system.animate(true); system.animate(true);};
	try {run({engine, scene, motes, system, tick});} finally {motes.dispose(); scene.dispose(); engine.dispose();}
}
test('actual ParticleSystem emits only at night, drains in rain/day and reuses the same pool resources', () => fixture(({scene, motes, system, tick}) => {
	const focus = {x: 0, y: 0, z: 0}, texture = system.particleTexture;
	motes.update({daylight: 1, rain: 0}, 0, focus); tick();
	assert.equal(system.getActiveCount(), 0);
	motes.update({daylight: 0, rain: 0}, 1, focus); tick();
	assert.equal(system.getActiveCount(), 48);
	const originalParticles = new Set(system.particles);
	assert.ok(motes.diagnostics().visible > 0);
	assert.ok(system.particles.every(p => p.size <= .11 && p.color.a <= .72));
	motes.update({daylight: 0, rain: 1}, 2, focus); tick();
	assert.equal(system.getActiveCount(), 0);
	motes.update({daylight: 0, rain: 0}, 3, focus); tick();
	assert.equal(system.getActiveCount(), 48);
	assert.ok(system.particles.every(p => originalParticles.has(p)), 'particles returned from the engine stock pool');
	assert.equal(system.particleTexture, texture);
	assert.equal(scene.particleSystems.length, 1);
	assert.equal(scene.lights.length, 0);
	motes.update({daylight: 1, rain: 0}, 4, focus); tick();
	assert.equal(system.getActiveCount(), 0);
}));
test('actual pool applies mobile quality, reduced motion and idempotent cleanup', () => fixture(({scene, motes, system, tick}) => {
	const focus = {x: 0, y: 0, z: 0};
	motes.setQuality(quality('ultra', 'mobile'));
	motes.setReducedMotion(true);
	motes.update({daylight: 0, rain: 0}, 1, focus); tick();
	assert.equal(system.getActiveCount(), 24);
	const original = system.particles.map(p => [p.position.x, p.position.y, p.position.z, p.color.a]);
	motes.update({daylight: 0, rain: 0}, 400, focus); tick();
	assert.deepEqual(system.particles.map(p => [p.position.x, p.position.y, p.position.z, p.color.a]), original);
	motes.setQuality(quality('low')); motes.update({daylight: 0, rain: 0}, 401, focus); tick();
	assert.equal(system.getActiveCount(), 12);
	motes.dispose(); motes.dispose();
	assert.equal(scene.particleSystems.length, 0);
	assert.equal(scene.textures.some(t => t.name === 'ambient-night-mote-mask'), false);
	assert.equal(motes.diagnostics().disposed, true);
	motes.update({daylight: 0, rain: 0}, 402, focus);
	assert.equal(motes.diagnostics().activeParticles, 0);
}));
