import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout } from 'node:timers/promises';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder.js';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { createLookV2PoolPixels, createLookV2PoolRegistry, lookV2PoolAlpha,
	LOOK_V2_POOL_DIAMETERS, LOOK_V2_POOL_RADII, MAX_LOOK_V2_POOLS, writeLookV2PoolMatrices } from '../src/look-v2-pools.mjs';
import { markLookV2DressingReady, notifyLookV2PoolEmitterChanged } from '../src/look-v2-pool-events.mjs';

// Babylon TimingTools.SetImmediate uses a timer here; await the real add notification and its microtask.
const settle = async () => { await setTimeout(2); };
function fixture() {
	const engine = new NullEngine(), scene = new Scene(engine), registry = createLookV2PoolRegistry(scene);
	return { engine, scene, registry, dispose() { registry.dispose(); scene.dispose(); engine.dispose(); } };
}
const activeObservers = observable => observable.observers.filter(observer => !observer._willBeUnregistered).length;

test('radial opacity has circular support, monotonic soft shoulder and zero alpha on every quad edge', () => {
	assert.equal(lookV2PoolAlpha(.5, .5), 1);
	assert.equal(lookV2PoolAlpha(0, .5), 0);
	assert.equal(lookV2PoolAlpha(.05, .05), 0, 'inside the square but outside the circle');
	for (let radius = 0; radius <= 1; radius += .01) {
		const x = .5 + radius / 2;
		assert.ok(Math.abs(lookV2PoolAlpha(x, .5) - lookV2PoolAlpha(.5, x)) < 1e-12);
		assert.ok(lookV2PoolAlpha(x, .5) >= lookV2PoolAlpha(x + .005, .5));
	}
	assert.ok(lookV2PoolAlpha(.99, .5) < .0001, 'no bright ring at the edge');
	const pixels = createLookV2PoolPixels(64);
	for (let index = 0; index < 64; index++) for (const [x, y] of [[index, 0], [index, 63], [0, index], [63, index]])
		assert.equal(pixels[(y * 64 + x) * 4 + 3], 0);
});

test('one fixed 64-instance buffer uses lamp/brazier/fire radii 4.5/6/7m and diameters 9/12/14m', () => {
	const anchors = ['lamp', 'brazier', 'fire'].map((type, index) => ({ x: index * 20, y: 2.36, z: -6, type }));
	const buffer = new Float32Array(MAX_LOOK_V2_POOLS * 16);
	assert.equal(writeLookV2PoolMatrices(anchors, buffer), 3);
	for (let index = 0; index < anchors.length; index++) {
		const offset = index * 16, { type } = anchors[index];
		assert.equal(buffer[offset], LOOK_V2_POOL_RADII[type] * 2);
		assert.equal(buffer[offset + 10], LOOK_V2_POOL_DIAMETERS[type]);
		assert.ok(Math.abs(buffer[offset + 13] - 2.4) < 1e-6, 'bank foot +4cm');
	}
	assert.equal(writeLookV2PoolMatrices(Array(100).fill(anchors[0]), buffer), 64);
	assert.equal(writeLookV2PoolMatrices([], buffer), 0); assert.ok(buffer.every(value => value === 0));
});

test('real Babylon add event defers named constructor until geometry/material are ready and uses actual feet', async () => {
	const f = fixture();
	try {
		const lamp = new Mesh('raised-bank-lamp', f.scene);
		await settle();
		assert.equal(f.registry.stats().anchors, 0); assert.equal(f.registry.stats().pending, 1);
		f.scene.onBeforeRenderObservable.notifyObservers(f.scene);
		f.scene.onBeforeRenderObservable.notifyObservers(f.scene);
		assert.equal(f.registry.stats().pending, 1, 'deferred retries span distinct frames');
		VertexData.CreateBox({ width: .4, height: 2, depth: .4 }).applyToMesh(lamp);
		lamp.position.set(20, 3.36, -6);
		lamp.material = new StandardMaterial('warm-lantern', f.scene);
		f.scene.onBeforeRenderObservable.notifyObservers(f.scene);
		const [anchor] = f.registry.snapshot();
		assert.equal(anchor.x, 20); assert.equal(anchor.z, -6); assert.equal(anchor.type, 'lamp');
		assert.ok(Math.abs(anchor.y - 2.36) < 1e-6, 'Babylon world matrix stores f32 foot height');
		assert.equal(f.registry.stats().fullScans, 0, 'no scan before dressing ready');
		markLookV2DressingReady(f.scene); markLookV2DressingReady(f.scene);
		assert.equal(f.registry.stats().fullScans, 1, 'one readiness scan');
		lamp.dispose(); assert.equal(f.registry.snapshot().length, 0); assert.equal(f.registry.stats().emitters, 0);
	} finally { f.dispose(); }
});

test('late streamed metadata registers feet and type without geometry reads; duplicate/retired LODs leave one pool', async () => {
	const f = fixture();
	try {
		markLookV2DressingReady(f.scene);
		const lod0 = new Mesh('opaque-stream-cell-lod0', f.scene), lod1 = new Mesh('opaque-stream-cell-lod1', f.scene);
		await settle(); assert.equal(f.registry.snapshot().length, 0);
		for (const mesh of [lod0, lod1]) {
			mesh.getVerticesData = () => { throw new Error('declared anchors must not sample vertices'); };
			mesh.getBoundingInfo = () => { throw new Error('declared anchors must not read source bounds'); };
			mesh.metadata = { dressingV3: true, lookV2PoolAnchors: [[10, 2.36, 12, 'brazier'], [30, .4, 5, 'fire']] };
			notifyLookV2PoolEmitterChanged(mesh);
		}
		assert.deepEqual(f.registry.snapshot(), [{ x: 10, y: 2.36, z: 12, type: 'brazier' }, { x: 30, y: .4, z: 5, type: 'fire' }]);
		lod0.setEnabled(false); lod1.metadata.lookV2PoolAnchors = [[10, 2.36, 12, 'brazier']];
		notifyLookV2PoolEmitterChanged(lod1);
		assert.equal(f.registry.snapshot().length, 1, 'retired lod0 fire anchor is removed');
		lod1.metadata.lookV2PoolAnchors = []; lod1.setEnabled(false); notifyLookV2PoolEmitterChanged(lod1);
		assert.equal(f.registry.snapshot().length, 0, 'empty metadata is authoritative');
		assert.equal(f.registry.stats().boundsReads, 0); assert.equal(f.registry.stats().fullScans, 1);
	} finally { f.dispose(); }
});

test('100 non-emitter additions/material/visibility/removal changes cause no full scans or vertex sampling', async () => {
	const f = fixture();
	try {
		markLookV2DressingReady(f.scene);
		const before = f.registry.stats();
		for (let i = 0; i < 100; i++) {
			const mesh = new Mesh(`stream-stone-${i}`, f.scene);
			mesh.getVerticesData = () => { throw new Error('non-emitter vertex sampling'); };
			mesh.getBoundingInfo = () => { throw new Error('non-emitter bounds sampling'); };
			mesh.metadata = { dressingV3: true }; mesh.isVisible = i % 2 === 0;
			mesh.material = new StandardMaterial(`stone-${i}`, f.scene);
			await settle(); mesh.dispose();
		}
		for (let i = 0; i < 100; i++) f.scene.onBeforeRenderObservable.notifyObservers(f.scene);
		const after = f.registry.stats();
		assert.equal(after.fullScans, before.fullScans); assert.equal(after.boundsReads, before.boundsReads);
		assert.equal(after.anchors, 0); assert.equal(after.emitters, 0); assert.equal(after.pending, 0);
		assert.equal(after.evaluations - before.evaluations, 100, 'one deferred cheap filter per addition');
	} finally { f.dispose(); }
});

test('enabled, visible and metadata overrides are authoritative; ordinary lamp bounds work on raised banks', async () => {
	const f = fixture();
	try {
		const lamp = MeshBuilder.CreateBox('bank-lamp', { width: .4, height: 3, depth: .4 }, f.scene);
		lamp.position.y = 4;
		await settle(); assert.equal(f.registry.snapshot()[0].y, 2.5);
		lamp.isVisible = false; assert.equal(f.registry.snapshot().length, 0);
		lamp.isVisible = true; lamp.setEnabled(false); assert.equal(f.registry.snapshot().length, 0);
		lamp.setEnabled(true); lamp.metadata = { lookV2PoolAnchor: [8, 3.2, 4], lookV2PoolType: 'fire' };
		notifyLookV2PoolEmitterChanged(lamp);
		assert.deepEqual(f.registry.snapshot(), [{ x: 8, y: 3.2, z: 4, type: 'fire' }]);
		lamp.metadata.lookV2Pool = false; assert.equal(f.registry.snapshot().length, 0);
		delete lamp.metadata.lookV2Pool; lamp.visibility = 0; assert.equal(f.registry.snapshot().length, 0);
		lamp.visibility = 1; f.scene.removeMesh(lamp); assert.equal(f.registry.snapshot().length, 0);
		f.scene.addMesh(lamp); await settle(); assert.equal(f.registry.snapshot().length, 1);
	} finally { f.dispose(); }
});

test('late installer remembers readiness; bounded deferred attempts and disposal remove every observer', async () => {
	const engine = new NullEngine(), scene = new Scene(engine);
	try {
		const lamp = new Mesh('unfinished-lamp', scene); await settle();
		markLookV2DressingReady(scene);
		const baseline = [scene.onNewMeshAddedObservable, scene.onMeshRemovedObservable, scene.onBeforeRenderObservable, scene.onDisposeObservable].map(activeObservers);
		const registry = createLookV2PoolRegistry(scene);
		await settle();
		assert.equal(registry.stats().fullScans, 1);
		for (let i = 0; i < 100; i++) scene.onBeforeRenderObservable.notifyObservers(scene);
		assert.equal(registry.stats().pending, 0);
		assert.ok(registry.stats().evaluations <= 5, 'unfinished constructor retries are bounded');
		registry.dispose(); registry.dispose(); await settle();
		assert.deepEqual([scene.onNewMeshAddedObservable, scene.onMeshRemovedObservable, scene.onBeforeRenderObservable, scene.onDisposeObservable].map(activeObservers), baseline);
		VertexData.CreateBox({ size: 1 }).applyToMesh(lamp); notifyLookV2PoolEmitterChanged(lamp);
		assert.equal(registry.snapshot().length, 0, 'disposed listener cannot revive');
	} finally { scene.dispose(); engine.dispose(); }
});
