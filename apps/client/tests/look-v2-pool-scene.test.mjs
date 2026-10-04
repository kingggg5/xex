import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { setTimeout } from 'node:timers/promises';

const root = fileURLToPath(new URL('..', import.meta.url));
const bundle = await build({ stdin: { contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {Mesh} from '@babylonjs/core/Meshes/mesh';
export {Constants} from '@babylonjs/core/Engines/constants';
export {installLookGradeV2} from './src/look-grade-v2-scene';
export {registerWeatherReader} from './src/ambient-weather-channel';
export * from './src/look-v2-pool-events.mjs';`, resolveDir: root, loader: 'ts' },
	bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent', define: { 'import.meta.env.DEV': 'true' } });
const api = await import('data:text/javascript;base64,' + Buffer.from(bundle.outputFiles[0].text).toString('base64'));

test('actual DEV installer uses one radial-opacity thin-instance pool, bounded sizing and disposal hooks', async () => {
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	// NullEngine has no canvas/GPU upload; retain actual Babylon material, geometry and instancing objects.
	let painted;
	engine.getCaps().instancedArrays = true;
	engine.createCanvas = () => ({ width: 1, height: 1, getContext: () => ({
		createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
		putImageData: image => { painted = image.data; }
	}) });
	engine.updateDynamicTexture = texture => { texture.isReady = true; };
	const previousLocation = globalThis.location, previousPerformance = globalThis.performance;
	globalThis.location = { search: '?look=v2' };
	let now = 1000;
	globalThis.performance = { now: () => now };
	try {
		const camera = new api.FreeCamera('test-camera', api.Vector3.Zero(), scene); scene.activeCamera = camera;
		let daylight = 0;
		const removeWeather = api.registerWeatherReader(scene, () => ({ appearance: { hours: 0, daylight, rain: 0 }, worldMs: 0, phase: 0, clockRevision: 1 }));
		const emitter = new api.Mesh('streamed-bank-emitter', scene);
		emitter.metadata = { lookV2PoolAnchors: [{ x: 10, y: 2.36, z: 4, type: 'brazier' }] };
		api.markLookV2DressingReady(scene);
		const excluded = [];
		const fog = scene.fogDensity = .0067;
		api.installLookGradeV2(scene, { addExcludedMesh: mesh => excluded.push(mesh) }, { nativeSky: true, nativeFog: true });
		await setTimeout(20);
		const pool = scene.getMeshByName('look-v2-pool'), material = pool.material;
		assert.equal(scene.meshes.filter(mesh => mesh.name === 'look-v2-pool').length, 1);
		assert.equal(pool.subMeshes.length, 1); assert.equal(pool.getTotalVertices(), 4);
		assert.deepEqual(excluded, [pool]); assert.equal(pool.metadata.glow, false);
		assert.equal(material.emissiveTexture, null); assert.equal(material.opacityTexture.name, 'look-v2-pool-falloff');
		assert.equal(material.opacityTexture.hasAlpha, true); assert.equal(material.opacityTexture.getAlphaFromRGB, false);
		assert.equal(material.useEmissiveAsIllumination, true); assert.equal(material.alphaMode, api.Constants.ALPHA_ADD);
		assert.equal(painted[3], 0); assert.equal(painted[(32 * 64 + 32) * 4 + 3], 255);
		const renderUpdate = () => { now += 201; scene.onBeforeCameraRenderObservable.notifyObservers(camera); };
		renderUpdate(); assert.equal(pool.thinInstanceCount, 1); assert.equal(pool.isEnabled(), true);
		const matrices = pool._thinInstanceDataStorage.matrixData, buffer = pool._thinInstanceDataStorage.matrixBuffer;
		assert.equal(matrices.length, 64 * 16); assert.equal(matrices[0], 12);
		assert.ok(Math.abs(matrices[13] - 2.4) < 1e-6); assert.equal(scene.fogDensity, fog, 'nativeFog keeps ownership');
		let enabledWrites = 0, alphaWrites = 0;
		const originalEnabled = pool.setEnabled.bind(pool);
		pool.setEnabled = value => { enabledWrites++; originalEnabled(value); };
		let prototype = material, descriptor;
		while (!descriptor) { descriptor = Object.getOwnPropertyDescriptor(prototype, 'alpha'); prototype = Object.getPrototypeOf(prototype); }
		Object.defineProperty(material, 'alpha', { configurable: true, get: () => descriptor.get.call(material),
			set: value => { alphaWrites++; descriptor.set.call(material, value); } });
		renderUpdate(); renderUpdate();
		assert.equal(enabledWrites, 0); assert.equal(alphaWrites, 0, 'unchanged strength does not dirty materials');
		emitter.metadata.lookV2PoolAnchors = Array.from({ length: 100 }, (_, index) => [index * 20, 0, 0, 'lamp']);
		api.notifyLookV2PoolEmitterChanged(emitter); renderUpdate();
		assert.equal(pool.thinInstanceCount, 64); assert.equal(pool._thinInstanceDataStorage.matrixBuffer, buffer, 'buffer reused');
		assert.equal(pool.metadata.poolRegistration().fullScans, 1);
		assert.equal(pool.metadata.poolRegistration().boundsReads, 0);
		daylight = 1; renderUpdate(); assert.equal(pool.isEnabled(), false); assert.equal(material.alpha, 0);
		daylight = 0; emitter.dispose(); renderUpdate(); assert.equal(pool.thinInstanceCount, 0); assert.equal(pool.isEnabled(), false);
		removeWeather(); scene.dispose(); assert.equal(pool.isDisposed(), true); assert.equal(scene.textures.length, 0);
	} finally {
		globalThis.location = previousLocation; globalThis.performance = previousPerformance;
		scene.dispose(); engine.dispose();
	}
});
