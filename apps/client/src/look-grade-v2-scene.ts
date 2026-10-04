// C-LOOK-V2 (lane look-grade, file look-grade-v2-scene.ts so it never resolves to the .mjs): runtime half of ?look=v2 (DEV, default off). Installed from the C-LOOK-V2 hunk in
// environment.ts. Colours, sun, fill, fog colour and the post grade are applied by world-weather.ts from
// sampleLookGrade(); this module adds what has no home there yet (see planning/evidence/look-grade-v2/codex-requests.md):
// 1. the sky-dome UV remap that puts the zenith-to-horizon gradient where the 13 m camera sees it;
// 2. the distance-fog density of the grade (aerial perspective on far layers);
// 3. night light pools: one additive ground-decal draw at every lamp, brazier or fire found in the scene.
import type { Scene } from "@babylonjs/core/scene";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import "@babylonjs/core/Meshes/thinInstanceMesh";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Constants } from "@babylonjs/core/Engines/constants";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { readWeatherFrame } from "./ambient-weather-channel";
import { LOOK_POOL, poolStrength, sampleLookGrade, skyCanvasFraction } from "./look-grade-v2.mjs";
import { createLookV2PoolPixels, createLookV2PoolRegistry, MAX_LOOK_V2_POOLS,
	writeLookV2PoolMatrices, type LookV2PoolAnchor } from "./look-v2-pools.mjs";

export function installLookGradeV2(scene: Scene, glow: { addExcludedMesh(mesh: Mesh): void } | null,
	integration: {nativeSky?: boolean; nativeFog?: boolean} = {}): void {
	if(!integration.nativeSky)remapSkyDome(scene);
	const query = new URLSearchParams(location.search);
	const pool = MeshBuilder.CreateGround("look-v2-pool", { width: 1, height: 1 }, scene);
	pool.isPickable = false; pool.receiveShadows = false; pool.metadata = { glow: false, lookV2: true };
	glow?.addExcludedMesh(pool);
	const texture = new DynamicTexture("look-v2-pool-falloff", { width: 64, height: 64 }, scene, true);
	const ctx = texture.getContext() as CanvasRenderingContext2D;
	const image = ctx.createImageData(64, 64);
	image.data.set(createLookV2PoolPixels()); ctx.putImageData(image, 0, 0); texture.update();
	texture.hasAlpha = true; texture.getAlphaFromRGB = false;
	const material = new StandardMaterial("look-v2-pool-mat", scene);
	// StandardMaterial adds emissiveTexture RGB to the warm color. Falloff must multiply alpha.
	material.disableLighting = true; material.opacityTexture = texture; material.useEmissiveAsIllumination = true;
	material.emissiveColor = new Color3(...(LOOK_POOL.color as [number, number, number]));
	material.diffuseColor = Color3.Black(); material.specularColor = Color3.Black();
	material.alphaMode = Constants.ALPHA_ADD; material.alpha = .999; material.disableDepthWrite = true;
	material.zOffset = -2; material.fogEnabled = false;
	pool.material = material;
	const matrices = new Float32Array(MAX_LOOK_V2_POOLS * 16);
	pool.thinInstanceSetBuffer("matrix", matrices, 16, false);
	pool.thinInstanceCount = 0;
	pool.setEnabled(false);
	void material.forceCompilationAsync(pool, { useInstances: true }).catch(error => {
		if (!scene.isDisposed) console.warn('look v2 pool prewarm failed', error);
	}); // prewarm the actual draw variant

	const registry = createLookV2PoolRegistry(scene, pool);
	pool.metadata.poolRegistration = registry.stats;
	let nextUpdate = 0, signature = '', testAnchor: LookV2PoolAnchor | null = null;
	let testAnchorPending = import.meta.env.DEV && query.get("lookPoolTest") === "1";
	const observer = scene.onBeforeCameraRenderObservable.add(() => {
		const now = performance.now();
		if (now < nextUpdate) return;
		nextUpdate = now + 200;
		const frame = readWeatherFrame(scene);
		if (!frame) return;
		const grade = sampleLookGrade(frame.appearance);
		if(!integration.nativeFog)scene.fogDensity = grade.fogDensity;
		const camera = scene.activeCamera;
		if (testAnchorPending && camera instanceof ArcRotateCamera) {
			// DEV evidence fixture only (?lookPoolTest=1): a pool under the locked lookdev target, labelled TEST ANCHOR.
			testAnchorPending = false; testAnchor = { x: camera.target.x + 1.5, y: camera.target.y - 1.65, z: camera.target.z, type: 'lamp' };
		}
		const registered = registry.snapshot();
		const anchors = testAnchor ? [testAnchor, ...registered].slice(0, MAX_LOOK_V2_POOLS) : registered;
		const nextSignature = anchors.map(a => `${a.x},${a.y},${a.z},${a.type}`).join('|');
		if (nextSignature !== signature) {
			signature = nextSignature;
			pool.thinInstanceCount = writeLookV2PoolMatrices(anchors, matrices);
			pool.thinInstanceBufferUpdated('matrix');
			if (anchors.length) pool.thinInstanceRefreshBoundingInfo(false);
		}
		const strength = poolStrength(frame.appearance.daylight, frame.appearance.rain);
		const enabled = strength > .01 && anchors.length > 0;
		if (pool.isEnabled() !== enabled) pool.setEnabled(enabled);
		const alpha = Math.min(.999, strength);
		if (material.alpha !== alpha) material.alpha = alpha;
	});
	scene.onDisposeObservable.addOnce(() => {
		scene.onBeforeCameraRenderObservable.remove(observer);
		registry.dispose();
	});
}

/** Moves the dome's V so the painter's zenith (canvas 0..0.48) and horizon (0.76..1) bands meet 0-10 deg up. */
function remapSkyDome(scene: Scene): void {
	const dome = scene.getMeshByName("env-sky-dome");
	if (!(dome instanceof Mesh)) return;
	const positions = dome.getVerticesData(VertexBuffer.PositionKind), uvs = dome.getVerticesData(VertexBuffer.UVKind);
	if (!positions || !uvs) return;
	let top = 0, bottom = 0, maxY = -Infinity, minY = Infinity, radius = 0;
	for (let i = 0, j = 0; i < positions.length; i += 3, j += 2) {
		const y = positions[i + 1];
		radius = Math.max(radius, Math.hypot(positions[i], y, positions[i + 2]));
		if (y > maxY) { maxY = y; top = uvs[j + 1]; }
		if (y < minY) { minY = y; bottom = uvs[j + 1]; }
	}
	const next = Float32Array.from(uvs);
	for (let i = 0, j = 0; i < positions.length; i += 3, j += 2) {
		const elevation = Math.asin(Math.max(-1, Math.min(1, positions[i + 1] / radius))) * 180 / Math.PI;
		next[j + 1] = top + skyCanvasFraction(elevation) * (bottom - top);
	}
	dome.setVerticesData(VertexBuffer.UVKind, next, false);
}
