import {ParticleSystem} from '@babylonjs/core/Particles/particleSystem';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
import {Texture} from '@babylonjs/core/Materials/Textures/texture';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color4} from '@babylonjs/core/Maths/math.color';
import type {Scene} from '@babylonjs/core/scene';
import type {EnvironmentSample} from './world-environment-state.mjs';
import type {ResolvedGraphicsPreset} from './graphics-quality.mjs';
import {NIGHT_MOTE_CAPACITY, createNightMoteSeeds, nightMoteBudget, nightMoteOpacity, sampleNightMote,
	type NightMoteCluster} from './ambient-night-motes-policy.mjs';

export type {NightMoteCluster} from './ambient-night-motes-policy.mjs';
type Quality = Pick<ResolvedGraphicsPreset, 'preset' | 'formFactor'>;
export interface NightMoteOptions {
	/** Terrain/water surface Y, not a mesh centre. Habitats must avoid doors, roads and interiors. */
	readonly clusters: readonly NightMoteCluster[];
	readonly quality?: Quality;
	readonly reducedMotion?: boolean;
}

/** One built-in Babylon particle draw; no custom shader, point lights, glow-layer or world clock. */
export function createNightMotes(scene: Scene, options: NightMoteOptions) {
	const seeds = createNightMoteSeeds(options.clusters);
	let budget = nightMoteBudget(options.quality);
	let reducedMotion = options.reducedMotion ?? false;
	let disposed = false;
	let running = false;
	let opacity = 0;
	let phase = 0;
	let visible = 0;
	const focus = {x: 0, y: 0, z: 0};
	const sampled = {x: 0, y: 0, z: 0, alpha: 0};
	// 4 KiB reusable analytic sprite: a tiny core and restrained halo, not a large emissive orb.
	const pixels = new Uint8Array(32 * 32 * 4);
	for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
		const radius = Math.hypot((x - 15.5) / 15.5, (y - 15.5) / 15.5);
		const core = Math.exp(-radius * radius * 75);
		const halo = Math.exp(-radius * radius * 8) * .16;
		const offset = (y * 32 + x) * 4;
		pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = 255;
		pixels[offset + 3] = radius >= 1 ? 0 : Math.round(Math.min(1, core + halo) * 255);
	}
	const texture = RawTexture.CreateRGBATexture(pixels, 32, 32, scene, false, false, Texture.BILINEAR_SAMPLINGMODE);
	texture.name = 'ambient-night-mote-mask';
	texture.hasAlpha = true;
	texture.wrapU = texture.wrapV = Texture.CLAMP_ADDRESSMODE;
	const system = new ParticleSystem('ambient-night-motes', NIGHT_MOTE_CAPACITY, scene);
	system.particleTexture = texture;
	system.emitter = Vector3.Zero();
	system.emitRate = 0;
	system.manualEmitCount = 0;
	system.minLifeTime = system.maxLifeTime = 1e9;
	system.minEmitPower = system.maxEmitPower = 0;
	system.minSize = system.maxSize = .09;
	system.color1 = system.color2 = new Color4(1, .74, .3, 0);
	system.blendMode = ParticleSystem.BLENDMODE_ADD;
	system.forceDepthWrite = false;
	system.preventAutoStart = true;
	system.updateFunction = particles => {
		visible = 0;
		for (let i = 0; i < particles.length; i++) {
			const particle = particles[i];
			const seed = seeds[i];
			if (!seed) {particle.color.a = 0; continue;}
			sampleNightMote(seed, phase, reducedMotion, focus, opacity, sampled);
			particle.position.set(sampled.x, sampled.y, sampled.z);
			particle.size = seed.size;
			particle.color.set(seed.cool ? .42 : 1, seed.cool ? .76 : .74, seed.cool ? 1 : .30, sampled.alpha);
			if (sampled.alpha > .005) visible++;
		}
	};
	// New particles begin invisible at their final habitat, never as a one-frame flash at world origin.
	system.startPositionFunction = (_world, position, particle) => {
		const index = Math.max(0, system.getActiveCount() - 1);
		const seed = seeds[index];
		position.set(seed?.x ?? 0, seed?.y ?? 0, seed?.z ?? 0);
		particle.color.a = 0;
	};

	function drainTo(count: number) {
		while (system.particles.length > count) system.recycleParticle(system.particles[system.particles.length - 1]);
	}
	function dispose() {
		if (disposed) return;
		disposed = true;
		visible = 0;
		scene.onDisposeObservable.remove(disposeObserver);
		system.dispose(false);
		texture.dispose();
	}
	const disposeObserver = scene.onDisposeObservable.addOnce(dispose);
	return {
		/** Call from the existing frame owner with its bounded NatureClock.phase, never wall time. */
		update(appearance: Pick<EnvironmentSample, 'daylight' | 'rain'>, naturePhase: number,
			viewFocus: {readonly x: number; readonly y: number; readonly z: number}) {
			if (disposed) return;
			opacity = nightMoteOpacity(appearance);
			if (!Number.isFinite(viewFocus.x) || !Number.isFinite(viewFocus.y)
				|| !Number.isFinite(viewFocus.z) || !Number.isFinite(naturePhase)) opacity = 0;
			phase = naturePhase;
			focus.x = viewFocus.x; focus.y = viewFocus.y; focus.z = viewFocus.z;
			const count = opacity > .001 ? Math.min(budget, seeds.length) : 0;
			drainTo(count);
			if (!count) {
				visible = 0;
				system.manualEmitCount = 0;
				if (running) system.stop();
				running = false;
				return;
			}
			if (!running) {system.start(); running = true;}
			system.manualEmitCount = Math.max(0, count - system.getActiveCount());
		},
		setQuality(quality: Quality) {if (!disposed) budget = nightMoteBudget(quality);},
		setReducedMotion(value: boolean) {if (!disposed) reducedMotion = value;},
		/** Call during the existing loading warm-up. The engine chooses its native GLSL/WGSL path. */
		prewarm() {return !disposed && system.isReady();},
		diagnostics() {return {disposed, budget, opacity, running, reducedMotion, visible,
			activeParticles: disposed ? 0 : system.getActiveCount(), capacity: NIGHT_MOTE_CAPACITY, textureBytes: 4096};},
		dispose,
	};
}
