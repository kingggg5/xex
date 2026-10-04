import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { skyPaletteStops } from '../src/sky-palette-stops.mjs';

const bundle = await build({ stdin: { contents: `
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
export {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
export {DynamicTexture} from '@babylonjs/core/Materials/Textures/dynamicTexture';
export {Texture} from '@babylonjs/core/Materials/Textures/texture';
export * from './src/ambient-world';`, resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'ts' },
	bundle: true, platform: 'node', format: 'esm', write: false, logLevel: 'silent' });
const api = await import('data:text/javascript;base64,' + Buffer.from(bundle.outputFiles[0].text).toString('base64'));
async function fixture(run) {
	const previousCanvas = globalThis.OffscreenCanvas, gradients = [];
	globalThis.OffscreenCanvas = class {
		constructor(width, height) {
			this.width = width; this.height = height;
			const gradient = (type, values) => { const record = { type, values, stops: [] }; gradients.push(record); return { addColorStop: (offset, color) => record.stops.push({ offset, color }) }; };
			this.context = new Proxy({
				createRadialGradient: (...values) => gradient('radial', values),
				createLinearGradient: (...values) => gradient('linear', values),
				getImageData: () => ({ width, height, data: new Uint8ClampedArray(width * height * 4) }),
			}, { get: (target, key) => key in target ? target[key] : (() => {}), set: (target, key, value) => (target[key] = value, true) });
		}
		getContext() { return this.context; }
	};
	const engine = new api.NullEngine(), scene = new api.Scene(engine);
	let world;
	try {
		new api.DynamicTexture('env-sky-texture', { width: 16, height: 256 }, scene, false);
		const legacyMaterial = new api.StandardMaterial('cloud-white', scene);
		const master = api.MeshBuilder.CreateSphere('env-cloud-master-s', { diameter: 9 }, scene); master.material = legacyMaterial; master.isVisible = false;
		const puff = master.createInstance('env-cloud-0-0'); puff.position.set(0, 40, 20);
		world = api.createAmbientWorld(scene, { cityCenterZ: 180, now: () => 0 });
		const appearance = (daylight = 0, skyPalette) => api.updateAmbientAppearance(scene, { hours: 22, daylight, dawn: 0, cloud: .15, direction: [.2, -1, .3], skyPalette });
		await run({ scene, world, gradients, appearance, legacyMaterial, puff });
	} finally { world?.dispose(); scene.dispose(); engine.dispose(); globalThis.OffscreenCanvas = previousCanvas; }
}

test('actual cloud material modulates painted diffuse RGB by night tint without additive emissive texture', () => fixture(({ scene, appearance, legacyMaterial, puff }) => {
	const material = scene.getMaterialByName('ambient-cloud-sprites');
	assert.equal(material.emissiveTexture, null, 'no painted RGB added on top of the night tint');
	assert.equal(material.diffuseTexture.name, 'ambient-cloud-mask');
	assert.equal(material.disableLighting, true); assert.equal(material.useEmissiveAsIllumination, false);
	assert.equal(material.linkEmissiveWithDiffuse, false); assert.deepEqual(material.diffuseColor.asArray(), [0, 0, 0]);
	assert.ok(material.emissiveColor.asArray().every(channel => channel <= 140 / 255), 'safe startup variant');
	appearance(0);
	assert.deepEqual(material.emissiveColor.asArray(), [.14, .19, .26]);
	// Classic GLSL/WGSL finalDiffuse = clamp(emissiveColor)*baseColor when unlit and no emissive texture.
	for (let texel = 0; texel <= 255; texel++) for (const tint of material.emissiveColor.asArray())
		assert.ok(tint * texel <= 140, 'every painted channel stays below the 140/255 night surface cap');
	assert.equal(legacyMaterial.name, 'cloud-white'); assert.equal(puff.name, 'env-cloud-0-0'); assert.equal(puff.isVisible, false);
	appearance(1);
	for (const [index, channel] of material.emissiveColor.asArray().entries())
		assert.ok(Math.abs(channel - [.89, .92, .94][index]) < 1e-12, 'day tint preserved');
}));

test('night tint leaves gamma/ACES headroom under the unchanged look-v2 grade', () => fixture(({ scene, appearance }) => {
	appearance(0);
	const tint = scene.getMaterialByName('ambient-cloud-sprites').emissiveColor.asArray();
	// Independent CPU oracle of installed classic Babylon imageProcessingFunctions:
	// white-balance/grading are absent; this is not a native pixel measurement.
	const multiply = (matrix, vector) => matrix.map(row => row.reduce((sum, value, index) => sum + value * vector[index], 0));
	const grade = color => multiply([[1.60475,-.53108,-.07367],[-.10208,1.10813,-.00605],[-.00327,-.07276,1.07602]],
		multiply([[.59719,.35458,.04823],[.076,.90834,.01566],[.0284,.13383,.83777]], color.map(v => v * 1.15))
		.map(v => (v * (v + .0245786) - .000090537) / (v * (.983729 * v + .432951) + .238081)))
		.map(v => Math.min(1, Math.max(0, v)) ** (1 / 2.2))
		.map(v => (v + (v*v*(3-2*v)-v)*.22) * 255);
	assert.ok(Math.max(...grade([.20,.25,.38])) > 140, 'old linear-only cap missed the final blue overshoot');
	for (let mask = 0; mask < 8; mask++) {
		const paintedTexel = tint.map((value, axis) => mask & (1 << axis) ? value : 0);
		assert.ok(grade(paintedTexel).every(value => value <= 140), 'painted texture corners retain grade headroom');
	}
}));

test('cloud edge retains smooth texture alpha and alpha blending; sun and shadow materials keep their original channels', () => fixture(({ scene, gradients, appearance }) => {
	appearance(0);
	const material = scene.getMaterialByName('ambient-cloud-sprites'), texture = material.diffuseTexture;
	assert.equal(texture.hasAlpha, true); assert.equal(material.useAlphaFromDiffuseTexture, true);
	assert.equal(material.transparencyMode, api.StandardMaterial.MATERIAL_ALPHABLEND); assert.equal(material.needAlphaBlending(), true);
	assert.equal(texture.samplingMode, api.Texture.BILINEAR_SAMPLINGMODE);
	assert.equal(material.disableDepthWrite, true); assert.equal(material.backFaceCulling, false);
	const lobes = gradients.filter(record => record.type === 'radial').slice(0, 18);
	assert.equal(lobes.length, 18);
	for (const lobe of lobes) {
		assert.equal(lobe.stops.at(-1).offset, 1); assert.match(lobe.stops.at(-1).color, /,0\)$/);
		assert.equal(lobe.stops[1].offset, .65); assert.match(lobe.stops[1].color, /,\.22\)$/);
		const [x, y, , , , radius] = lobe.values;
		assert.ok(x - radius > 0 && x + radius < 256 && y - radius > 0 && y + radius < 128, 'no lobe clipped at a quad edge');
	}
	const sun = scene.getMaterialByName('ambient-sun-glow'), shadow = scene.getMaterialByName('ambient-cloud-shadow-mask');
	assert.equal(sun.emissiveTexture, sun.diffuseTexture); assert.equal(sun.alphaMode, 1);
	assert.equal(shadow.emissiveTexture, shadow.diffuseTexture); assert.equal(shadow.transparencyMode, api.StandardMaterial.MATERIAL_ALPHATEST);
}));

test('shared sky palette, cloud names, clock-driven cirrus state and resource budgets are preserved', () => fixture(({ scene, world, gradients, appearance }) => {
	const resources = () => [scene.meshes.length, scene.materials.length, scene.textures.length];
	const baseline = resources(), skyPalette = { zenith: [29 / 255, 56 / 255, 102 / 255], horizon: [61 / 255, 91 / 255, 134 / 255] };
	appearance(0, skyPalette); scene.onBeforeRenderObservable.notifyObservers(scene);
	assert.ok(world.diagnostics().skyKey.includes('v2:#1D3866:#3D5B86'));
	const gradient = gradients.filter(record => record.type === 'linear').at(-1);
	const expected = skyPaletteStops(skyPalette.zenith, skyPalette.horizon);
	assert.deepEqual(gradient.stops.map(stop => stop.offset), expected.map(stop => stop.offset));
	assert.equal(scene.getMeshByName('ambient-cirrus-0').isEnabled(), false, 'cirrus does not create night stripes');
	for (let step = 0; step < 100; step++) appearance(step % 2, skyPalette);
	assert.deepEqual(resources(), baseline);
	assert.ok(scene.getMeshByName('ambient-cloud-0-0')); assert.ok(scene.getMeshByName('env-cloud-master-s'));
}));
