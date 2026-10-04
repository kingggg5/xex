import { NodeMaterial } from '@babylonjs/core/Materials/Node/nodeMaterial';
import { InputBlock } from '@babylonjs/core/Materials/Node/Blocks/Input/inputBlock';
import { TransformBlock } from '@babylonjs/core/Materials/Node/Blocks/transformBlock';
import { VertexOutputBlock } from '@babylonjs/core/Materials/Node/Blocks/Vertex/vertexOutputBlock';
import { FragmentOutputBlock } from '@babylonjs/core/Materials/Node/Blocks/Fragment/fragmentOutputBlock';
import { ImageProcessingBlock } from '@babylonjs/core/Materials/Node/Blocks/Fragment/imageProcessingBlock';
import { FogBlock } from '@babylonjs/core/Materials/Node/Blocks/Dual/fogBlock';
import { PBRMetallicRoughnessBlock } from '@babylonjs/core/Materials/Node/Blocks/PBR/pbrMetallicRoughnessBlock';
import { ReflectionBlock } from '@babylonjs/core/Materials/Node/Blocks/PBR/reflectionBlock';
import { PerturbNormalBlock } from '@babylonjs/core/Materials/Node/Blocks/Fragment/perturbNormalBlock';
import { TextureBlock } from '@babylonjs/core/Materials/Node/Blocks/Dual/textureBlock';
import { ViewDirectionBlock } from '@babylonjs/core/Materials/Node/Blocks/viewDirectionBlock';
import { FresnelBlock } from '@babylonjs/core/Materials/Node/Blocks/fresnelBlock';
import { ColorSplitterBlock } from '@babylonjs/core/Materials/Node/Blocks/colorSplitterBlock';
import { MultiplyBlock } from '@babylonjs/core/Materials/Node/Blocks/multiplyBlock';
import { AddBlock } from '@babylonjs/core/Materials/Node/Blocks/addBlock';
import { SubtractBlock } from '@babylonjs/core/Materials/Node/Blocks/subtractBlock';
import { LengthBlock } from '@babylonjs/core/Materials/Node/Blocks/lengthBlock';
import { SmoothStepBlock } from '@babylonjs/core/Materials/Node/Blocks/smoothStepBlock';
import { OneMinusBlock } from '@babylonjs/core/Materials/Node/Blocks/oneMinusBlock';
import { TrigonometryBlock, TrigonometryBlockOperations } from '@babylonjs/core/Materials/Node/Blocks/trigonometryBlock';
import { NodeMaterialSystemValues } from '@babylonjs/core/Materials/Node/Enums/nodeMaterialSystemValues';
import { NodeMaterialModes } from '@babylonjs/core/Materials/Node/Enums/nodeMaterialModes';
import { NodeMaterialBlockTargets } from '@babylonjs/core/Materials/Node/Enums/nodeMaterialBlockTargets';
import { NodeMaterialBlockConnectionPointTypes } from '@babylonjs/core/Materials/Node/Enums/nodeMaterialBlockConnectionPointTypes';
import { ShaderLanguage } from '@babylonjs/core/Materials/shaderLanguage';
import { Texture } from '@babylonjs/core/Materials/Textures/texture';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture';
import { ParticleSystem } from '@babylonjs/core/Particles/particleSystem';
import '@babylonjs/core/Particles/particleSystemComponent';
import { CustomParticleEmitter } from '@babylonjs/core/Particles/EmitterTypes/customParticleEmitter';
import type { Particle } from '@babylonjs/core/Particles/particle';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder';
import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import { Color3, Color4 } from '@babylonjs/core/Maths/math.color';
import { Vector2, Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';
import type { NatureClock } from './nature-motion';
import normalUrl from '../../../assets/textures/fountain-water-cc0/water_wave_normal_1024.png?url';
import { CityWaterViewInput } from './city-water-view-input';

const TAU = Math.PI * 2;
const GRAVITY = 9.81;
const POOLS = [[8.51, 2.20], [4.32, 4.29], [1.86, 6.95]] as const;
const TIERS = [
	{ sourceRadius: 3.10, sourceY: 6.85, landingRadius: 3.75, landingY: 4.31 },
	{ sourceRadius: 6.10, sourceY: 4.35, landingRadius: 7.45, landingY: 2.23 },
] as const;

export interface CityWaterEngineController {
	readonly meshes: readonly Mesh[];
	readonly materials: readonly NodeMaterial[];
	readonly particleSystems: readonly ParticleSystem[];
	/** Native graph generation complete; this is not GPU visual acceptance. */
	readonly ready: Promise<void>;
	reveal(): void;
	hide(): void;
	setDetail(value: number): void;
	/** Uses the existing NatureClock and camera; no private animation clock. */
	refresh(): void;
	dispose(): void;
	stats(): { surfaceMeshes: 3; nativeParticleSystems: 3; selectedOutlets: 8 | 24; activeOutlets: number; nativeParticleCapacity: number; activeParticles: number; reflectionScenePasses: 0; revealed: boolean; culled: boolean };
}

/**
 * Isolated native-engine prototype. No integration, old-mesh removal or scene
 * lighting changes. Native graphs do water shading/particle alpha; native
 * ParticleSystem does pooling, physics, lifetime, size gradients and rendering.
 * CustomParticleEmitter callbacks configure authored outlet rules only.
 */
export function createCityWaterEngine(
	scene: Scene, centerZ: number, clock: NatureClock,
	options: { detail?: number; normalTexture?: Texture } = {},
): CityWaterEngineController {
	if (scene.isDisposed || !Number.isFinite(centerZ) || !Number.isFinite(clock.phase)) throw new Error('Water prototype needs a live scene and finite center/clock.');
	const startingDetail = boundedDetail(options.detail ?? .6);
	const normal = options.normalTexture ?? new Texture(normalUrl, scene, false, false);
	if (!options.normalTexture) { normal.gammaSpace = false; normal.wrapU = normal.wrapV = Texture.WRAP_ADDRESSMODE; }
	// Native ParticleSystem requires a bound texture even when its NodeMaterial
	// derives all visible shape/alpha. This four-byte white binding is not a sprite.
	const white = RawTexture.CreateRGBATexture(new Uint8Array([255, 255, 255, 255]), 1, 1, scene, false, false, Texture.NEAREST_SAMPLINGMODE);
	white.name = 'city-water-engine-white-binding'; white.gammaSpace = false;
	const graph = createWaterGraph(scene, normal);
	const jetGraph = createParticleGraph(scene, false), foamGraph = createParticleGraph(scene, true);
	const materials = [graph.material, jetGraph, foamGraph];
	const meshes = POOLS.map(([radius, y], index) => {
		const mesh = MeshBuilder.CreateDisc(`city-water-engine-pool-${index}`, { radius, tessellation: 64 }, scene);
		mesh.rotation.x = Math.PI / 2; mesh.position.set(0, y, centerZ);
		mesh.material = graph.material; mesh.isPickable = false; mesh.receiveShadows = true; mesh.setEnabled(false); mesh.computeWorldMatrix(true);
		return mesh;
	});
	let detail = startingDetail, revealed = false, active = false, disposed = false;
	let previousPhase = clock.phase;
	let selectedOutlets: 4 | 12 = detail >= .6 ? 12 : 4;
	const systems = TIERS.map((tier, tierIndex) => {
		const system = new ParticleSystem(`city-water-engine-tier-${tierIndex}`, 768, scene);
		configureCommonParticles(system, white);
		system.gravity.set(0, -GRAVITY, 0);
		const lifetime = Math.sqrt(2 * (tier.sourceY - tier.landingY) / GRAVITY);
		system.minLifeTime = system.maxLifeTime = lifetime;
		system.minSize = .065; system.maxSize = .085;
		system.color1 = new Color4(.44, .70, .76, .63); system.color2 = new Color4(.58, .80, .82, .51);
		system.colorDead = new Color4(.55, .78, .80, 0);
		const emitter = new CustomParticleEmitter();
		let cursor = 0;
		const angles = new WeakMap<Particle, number>();
		emitter.particlePositionGenerator = (_index, particle, position) => {
			const angle = (cursor++ % selectedOutlets) * TAU / selectedOutlets;
			if (particle) angles.set(particle, angle);
			position.set(tier.sourceRadius * Math.cos(angle), tier.sourceY, centerZ + tier.sourceRadius * Math.sin(angle));
		};
		emitter.particleDirectionGenerator = (_index, particle, direction) => {
			const angle = particle ? angles.get(particle) ?? 0 : 0;
			const horizontalSpeed = (tier.landingRadius - tier.sourceRadius) / lifetime;
			direction.set(horizontalSpeed * Math.cos(angle), 0, horizontalSpeed * Math.sin(angle));
		};
		system.particleEmitterType = emitter;
		return system;
	});
	const foam = new ParticleSystem('city-water-engine-impact-foam', 128, scene);
	configureCommonParticles(foam, white);
	foam.gravity.setAll(0); foam.minLifeTime = .3; foam.maxLifeTime = .45;
	foam.minSize = .2; foam.maxSize = .32;
	foam.color1 = new Color4(.69, .83, .82, .26); foam.color2 = new Color4(.76, .87, .85, .18); foam.colorDead = new Color4(.70, .84, .82, 0);
	foam.addSizeGradient(0, .65); foam.addSizeGradient(1, 1.8);
	const foamEmitter = new CustomParticleEmitter(); let foamCursor = 0;
	foamEmitter.particlePositionGenerator = (_index, _particle, position) => {
		const slot = foamCursor++ % (selectedOutlets * 2), tier = TIERS[Math.floor(slot / selectedOutlets)];
		const angle = (slot % selectedOutlets) * TAU / selectedOutlets;
		position.set(tier.landingRadius * Math.cos(angle), tier.landingY + .015, centerZ + tier.landingRadius * Math.sin(angle));
	};
	foamEmitter.particleDirectionGenerator = (_index, _particle, direction) => direction.setAll(0);
	foam.particleEmitterType = foamEmitter;
	const particleSystems = [...systems, foam];
	const ready = Promise.all(materials.map(buildNativeGraph)).then(() => {
		if (disposed) return;
		for (const system of systems) jetGraph.createEffectForParticles(system);
		foamGraph.createEffectForParticles(foam);
	}).catch(error => { dispose(); throw error; });
	const origin = new Vector3(0, 4.3, centerZ);
	function stopParticles() {
		for (const system of particleSystems) { system.emitRate = 0; system.updateSpeed = 0; system.paused = true; system.stop(); system.reset(); }
		active = false;
	}
	function refresh() {
		if (disposed) return;
		const phase = Number.isFinite(clock.phase) ? clock.phase : previousPhase;
		const phaseDelta = (phase - previousPhase + TAU) % TAU; previousPhase = phase;
		const delta = Math.min(.08, phaseDelta / .45);
		const camera = scene.activeCamera;
		const distanceLimit = active ? 92 : 85;
		const inView = !!camera && meshes.some(mesh => camera.isInFrustum(mesh));
		const visible = revealed && inView && !!camera && Vector3.DistanceSquared(camera.globalPosition, origin) < distanceLimit ** 2 && (clock.waterStrength ?? 1) > 0;
		for (const mesh of meshes) mesh.setEnabled(visible);
		if (!visible) { if (active) stopParticles(); return; }
		// Integer UV cycles preserve continuity at NatureClock's existing 2π wrap.
		(graph.flow.value as Vector2).copyFromFloats(phase / TAU, phase * 2 / TAU);
		const ratio = Math.max(.001, scene.getAnimationRatio());
		for (const system of particleSystems) system.updateSpeed = delta / ratio;
		if (!active) { for (const system of particleSystems) { system.paused = false; system.start(); } active = true; }
		const rate = detail >= .6 ? 75 : 40;
		for (const system of systems) system.emitRate = selectedOutlets * rate;
		foam.emitRate = selectedOutlets * 2 * (detail >= .6 ? 5 : 3);
	}
	const observer = scene.onBeforeRenderObservable.add(refresh);
	const sceneDisposal = scene.onDisposeObservable.addOnce(dispose);
	function dispose() {
		if (disposed) return;
		disposed = true; scene.onBeforeRenderObservable.remove(observer); scene.onDisposeObservable.remove(sceneDisposal);
		stopParticles(); for (const system of particleSystems) system.dispose(false);
		for (const mesh of meshes) mesh.dispose(false, false);
		for (const material of materials) material.dispose(true, false);
		white.dispose(); if (!options.normalTexture) normal.dispose();
	}
	return {
		meshes, materials, particleSystems, ready,
		reveal() { if (!disposed) { revealed = true; refresh(); } },
		hide() { revealed = false; if (!disposed) { for (const mesh of meshes) mesh.setEnabled(false); stopParticles(); } },
		setDetail(value) { const next = boundedDetail(value); const outlets = next >= .6 ? 12 : 4; if (outlets !== selectedOutlets && active) stopParticles(); detail = next; selectedOutlets = outlets; },
		refresh, dispose,
		stats() { return { surfaceMeshes: 3, nativeParticleSystems: 3, selectedOutlets: selectedOutlets === 12 ? 24 : 8, activeOutlets: active ? selectedOutlets * 2 : 0, nativeParticleCapacity: 1664, activeParticles: particleSystems.reduce((sum, system) => sum + system.getActiveCount(), 0), reflectionScenePasses: 0, revealed, culled: !active }; },
	};
}

function boundedDetail(value: number): number {
	if (!Number.isFinite(value)) throw new RangeError('Water detail must be finite.');
	return Math.max(0, Math.min(1, value));
}

function configureCommonParticles(system: ParticleSystem, texture: Texture): void {
	system.emitter = Vector3.Zero(); system.particleTexture = texture;
	system.blendMode = ParticleSystem.BLENDMODE_STANDARD; system.minEmitPower = system.maxEmitPower = 1;
	system.emitRate = 0; system.updateSpeed = 0; system.paused = true; system.disposeOnStop = false; system.preventAutoStart = true;
}

function value(name: string, data: number | Vector2 | Color3): InputBlock {
	const type = typeof data === 'number' ? NodeMaterialBlockConnectionPointTypes.Float : data instanceof Vector2 ? NodeMaterialBlockConnectionPointTypes.Vector2 : NodeMaterialBlockConnectionPointTypes.Color3;
	const input = new InputBlock(name, NodeMaterialBlockTargets.Neutral, type); input.value = data; return input;
}

function material(scene: Scene, name: string): NodeMaterial {
	return new NodeMaterial(name, scene, { emitComments: false, shaderLanguage: scene.getEngine().isWebGPU ? ShaderLanguage.WGSL : ShaderLanguage.GLSL });
}

function createWaterGraph(scene: Scene, normalTexture: Texture) {
	const water = material(scene, 'city-water-engine-pbr');
	const position = new InputBlock('position').setAsAttribute('position'), normal = new InputBlock('normal').setAsAttribute('normal');
	const world = new InputBlock('world').setAsSystemValue(NodeMaterialSystemValues.World);
	const vp = new InputBlock('viewProjection').setAsSystemValue(NodeMaterialSystemValues.ViewProjection);
	const view = new CityWaterViewInput();
	const camera = new InputBlock('camera').setAsSystemValue(NodeMaterialSystemValues.CameraPosition);
	const wp = new TransformBlock('worldPosition'), wn = new TransformBlock('worldNormal'); wn.transformAsDirection = true;
	position.output.connectTo(wp.vector); world.output.connectTo(wp.transform);
	normal.output.connectTo(wn.vector); world.output.connectTo(wn.transform);
	const clip = new TransformBlock('clipPosition'); wp.output.connectTo(clip.vector); vp.output.connectTo(clip.transform);
	const vertex = new VertexOutputBlock('vertex'); clip.output.connectTo(vertex.vector); water.addOutputNode(vertex);
	const uv = new InputBlock('uv').setAsAttribute('uv'), flow = value('flowFromNatureClock', new Vector2(0, 0));
	const tiled = new MultiplyBlock('normalTiling'); uv.output.connectTo(tiled.left); value('tileScale', 4).output.connectTo(tiled.right);
	const flowing = new AddBlock('normalFlow'); tiled.output.connectTo(flowing.left); flow.output.connectTo(flowing.right);
	const map = new TextureBlock('cc0NormalMap'); map.texture = normalTexture; map.convertToLinearSpace = false; map.convertToGammaSpace = false; flowing.output.connectTo(map.uv);
	const perturb = new PerturbNormalBlock('nativeWaterNormals'); wp.output.connectTo(perturb.worldPosition); wn.output.connectTo(perturb.worldNormal); flowing.output.connectTo(perturb.uv); map.rgb.connectTo(perturb.normalMapColor); value('normalStrength', .18).output.connectTo(perturb.strength);
	const direction = new ViewDirectionBlock('eyeDirection'); wp.output.connectTo(direction.worldPosition); camera.output.connectTo(direction.cameraPosition); direction.output.connectTo(perturb.viewDirection);
	const fresnel = new FresnelBlock('waterFresnel'); perturb.output.connectTo(fresnel.worldNormal); direction.output.connectTo(fresnel.viewDirection); value('fresnelBias', .02).output.connectTo(fresnel.bias); value('fresnelPower', 4).output.connectTo(fresnel.power);
	const alphaEdge = new MultiplyBlock('edgeOpacity'); fresnel.fresnel.connectTo(alphaEdge.left); value('edgeOpacityGain', .45).output.connectTo(alphaEdge.right);
	const opacity = new AddBlock('surfaceOpacity'); alphaEdge.output.connectTo(opacity.left); value('baseOpacity', .40).output.connectTo(opacity.right);
	const pbr = new PBRMetallicRoughnessBlock('nativePBRWater'); pbr.useAlphaBlending = true; pbr.useEnergyConservation = true; pbr.realTimeFiltering = false;
	wp.output.connectTo(pbr.worldPosition); wn.output.connectTo(pbr.worldNormal); perturb.output.connectTo(pbr.perturbedNormal); view.output.connectTo(pbr.view); camera.output.connectTo(pbr.cameraPosition);
	value('waterColour', new Color3(.035, .20, .24)).output.connectTo(pbr.baseColor); value('waterMetallic', 0).output.connectTo(pbr.metallic); value('waterRoughness', .17).output.connectTo(pbr.roughness); value('waterIOR', 1.333).output.connectTo(pbr.indexOfRefraction); opacity.output.connectTo(pbr.opacity);
	// PBR supplies the reflection block's world-position/normal/view/camera
	// connection points internally; only local position/world are independent.
	const reflection = new ReflectionBlock('sharedSceneEnvironment'); position.output.connectTo(reflection.position); world.output.connectTo(reflection.world); reflection.reflection.connectTo(pbr.reflection);
	const fog = new FogBlock('existingWorldFog'); wp.output.connectTo(fog.worldPosition); view.output.connectTo(fog.view); pbr.lighting.connectTo(fog.input);
	const processing = new ImageProcessingBlock('existingSceneImageProcessing'); fog.output.connectTo(processing.color);
	const fragment = new FragmentOutputBlock('fragment'); processing.rgb.connectTo(fragment.rgb); pbr.alpha.connectTo(fragment.a); water.addOutputNode(fragment);
	water.backFaceCulling = false; water.forceAlphaBlending = true; water.disableDepthWrite = true;
	return { material: water, flow };
}

function createParticleGraph(scene: Scene, ring: boolean): NodeMaterial {
	const particles = material(scene, ring ? 'city-water-engine-foam-alpha' : 'city-water-engine-jet-alpha'); particles.mode = NodeMaterialModes.Particle;
	const uv = new InputBlock('particleUV').setAsAttribute('particle_uv'), color = new InputBlock('particleColour').setAsAttribute('particle_color');
	const centered = new SubtractBlock('centeredUV'); uv.output.connectTo(centered.left); value('center', new Vector2(.5, .5)).output.connectTo(centered.right);
	const doubled = new MultiplyBlock('radiusScale'); centered.output.connectTo(doubled.left); value('radiusMultiplier', 2).output.connectTo(doubled.right);
	const length = new LengthBlock('particleRadius'); doubled.output.connectTo(length.value);
	const smooth = new SmoothStepBlock('softShape');
	if (ring) { const edge = new SubtractBlock('ringEdge'); length.output.connectTo(edge.left); value('ringRadius', .65).output.connectTo(edge.right); const absolute = new TrigonometryBlock('ringDistance'); absolute.operation = TrigonometryBlockOperations.Abs; edge.output.connectTo(absolute.input); absolute.output.connectTo(smooth.value); }
	else length.output.connectTo(smooth.value);
	value('softInner', ring ? .05 : .55).output.connectTo(smooth.edge0); value('softOuter', ring ? .23 : 1).output.connectTo(smooth.edge1);
	const mask = new OneMinusBlock('nativeAlphaMask'); smooth.output.connectTo(mask.input);
	const split = new ColorSplitterBlock('colourAlpha'); color.output.connectTo(split.rgba);
	const alpha = new MultiplyBlock('fadedAlpha'); mask.output.connectTo(alpha.left); split.a.connectTo(alpha.right);
	const processing = new ImageProcessingBlock('existingParticleImageProcessing'); split.rgbOut.connectTo(processing.color);
	const fragment = new FragmentOutputBlock('particleFragment'); processing.rgb.connectTo(fragment.rgb); alpha.output.connectTo(fragment.a); particles.addOutputNode(fragment);
	return particles;
}

function buildNativeGraph(graph: NodeMaterial): Promise<void> {
	return new Promise((resolve, reject) => {
		let settled = false;
		const finish = (error?: Error) => { if (settled) return; settled = true; clearTimeout(timer); graph.onBuildObservable.remove(success); graph.onBuildErrorObservable.remove(failure); graph.onDisposeObservable.remove(disposal); if (error) reject(error); else resolve(); };
		const success = graph.onBuildObservable.addOnce(() => finish());
		const failure = graph.onBuildErrorObservable.addOnce(error => finish(new Error(error)));
		const disposal = graph.onDisposeObservable.addOnce(() => finish(new Error(`Native graph disposed before build: ${graph.name}`)));
		const timer = setTimeout(() => finish(new Error(`Native graph build timed out: ${graph.name}`)), 10_000);
		try { graph.build(false, true, true); } catch (error) { finish(error instanceof Error ? error : new Error(String(error))); }
	});
}
