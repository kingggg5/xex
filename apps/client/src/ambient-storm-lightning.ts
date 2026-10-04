import {Mesh} from '@babylonjs/core/Meshes/mesh';
import {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import type {Scene} from '@babylonjs/core/scene';
import {createLightningSchedule, lightningQuality, writeLightningPaths, LIGHTNING_PATHS, LIGHTNING_POINTS_PER_PATH,
	type LightningAppearance, type LightningPoint, type LightningScheduleOptions, type LightningQuality} from './ambient-storm-lightning-policy.mjs';

export interface StormThunderEvent {
	readonly strikeAtWorldMs:number;
	readonly playAtWorldMs:number;
	readonly distanceM:number;
	readonly delayMs:number;
	readonly position:LightningPoint;
	readonly seed:number;
	readonly clockRevision?:string|number;
}
export interface StormLightningOptions extends LightningScheduleOptions {
	readonly seed?:number;
	/** Suggested local cloud illumination 0–0.09; owner blends it using the same weather clock. */
	readonly onFlash?:(strength:number)=>void;
	/** Called once when sound would arrive. Use the existing unlocked audio engine, if desired. */
	readonly onThunder?:(event:StormThunderEvent)=>void;
}

const WIDTH_STEPS = [-1, -.20, -.055, .055, .20, 1] as const;
const ALPHA_STEPS = [0, .17, .90, .90, .17, 0] as const;
const VERTICES_PER_PATH = LIGHTNING_POINTS_PER_PATH * WIDTH_STEPS.length;
const INDICES_PER_PATH = (LIGHTNING_POINTS_PER_PATH - 1) * (WIDTH_STEPS.length - 1) * 6;

/** One pooled mesh/material, at most four sky ribbons; built-in GLSL/WGSL, no post-process or own clock. */
export function createStormLightning(scene:Scene, options:StormLightningOptions = {}) {
	const schedule = createLightningSchedule(options.seed);
	const controls:{quality:LightningQuality|undefined;reducedMotion:boolean;reducedFlashes:boolean;clockRevision:string|number|undefined} = {
		quality: options.quality, reducedMotion: options.reducedMotion ?? false,
		reducedFlashes: options.reducedFlashes ?? false, clockRevision: options.clockRevision};
	let quality = options.quality;
	let reducedMotion = options.reducedMotion ?? false, reducedFlashes = options.reducedFlashes ?? false;
	let disposed = false, lastFlash = 0, generation = -1, activePaths = 0, strikeCount = 0;
	let pendingThunder:StormThunderEvent|null = null;
	const paths = new Float32Array(LIGHTNING_PATHS * LIGHTNING_POINTS_PER_PATH * 3);
	const positions = new Float32Array(LIGHTNING_PATHS * VERTICES_PER_PATH * 3);
	const colours = new Float32Array(LIGHTNING_PATHS * VERTICES_PER_PATH * 4);
	const indices = new Uint16Array(LIGHTNING_PATHS * INDICES_PER_PATH);
	for (let path = 0; path < LIGHTNING_PATHS; path++) {
		for (let point = 0; point < LIGHTNING_POINTS_PER_PATH - 1; point++) {
			for (let strip = 0; strip < WIDTH_STEPS.length - 1; strip++) {
				const a = path * VERTICES_PER_PATH + point * WIDTH_STEPS.length + strip;
				const at = path * INDICES_PER_PATH + (point * (WIDTH_STEPS.length - 1) + strip) * 6;
				indices.set([a, a + 1, a + WIDTH_STEPS.length, a + 1, a + WIDTH_STEPS.length + 1, a + WIDTH_STEPS.length], at);
			}
		}
	}
	const material = new StandardMaterial('ambient-storm-lightning-material', scene);
	material.disableLighting = true;
	material.diffuseColor.set(1, 1, 1);
	material.emissiveColor.set(.86, .86, .86);
	material.linkEmissiveWithDiffuse = true;
	material.specularColor.set(0, 0, 0);
	material.backFaceCulling = false;
	material.disableDepthWrite = true;
	material.fogEnabled = false;
	material.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
	const mesh = new Mesh('ambient-storm-lightning', scene);
	mesh.metadata = {glow: false, decorative: true, weatherEffect: 'lightning'};
	mesh.material = material; mesh.isPickable = false; mesh.checkCollisions = false; mesh.receiveShadows = false;
	mesh.useVertexColors = true; mesh.hasVertexAlpha = true;
	mesh.setVerticesData(VertexBuffer.PositionKind, positions, true, 3);
	mesh.setVerticesData(VertexBuffer.ColorKind, colours, true, 4);
	mesh.setIndices(indices);
	mesh.setEnabled(false);

	function flash(strength:number) {
		if (strength === lastFlash) return;
		lastFlash = strength; options.onFlash?.(strength);
	}
	function hide() {mesh.setEnabled(false); activePaths = 0; flash(0);}
	function build(seed:number, focus:LightningPoint, viewDirection:LightningPoint|undefined) {
		const end = writeLightningPaths(seed, focus, viewDirection, paths);
		const dx = end.x - focus.x, dz = end.z - focus.z, length = Math.hypot(dx, dz);
		// A vertical ribbon facing the listener; still depth-tested against the actual skyline.
		const sideX = dz / length, sideZ = -dx / length;
		for (let path = 0; path < LIGHTNING_PATHS; path++) {
			for (let point = 0; point < LIGHTNING_POINTS_PER_PATH; point++) {
				const source = (path * LIGHTNING_POINTS_PER_PATH + point) * 3;
				const taper = .22 + .78 * (1 - point / LIGHTNING_POINTS_PER_PATH);
				const width = (path ? .95 : 1.85) * taper;
				for (let strip = 0; strip < WIDTH_STEPS.length; strip++) {
					const vertex = path * VERTICES_PER_PATH + point * WIDTH_STEPS.length + strip;
					const at = vertex * 3, colour = vertex * 4, offset = WIDTH_STEPS[strip] * width;
					positions[at] = paths[source] + sideX * offset;
					positions[at + 1] = paths[source + 1];
					positions[at + 2] = paths[source + 2] + sideZ * offset;
					const core = strip === 2 || strip === 3;
					colours[colour] = core ? .91 : .57;
					colours[colour + 1] = core ? .86 : .44;
					colours[colour + 2] = core ? .98 : .79;
					colours[colour + 3] = ALPHA_STEPS[strip] * (path ? .62 : 1) * taper;
				}
			}
		}
		mesh.updateVerticesData(VertexBuffer.PositionKind, positions, true, false);
		mesh.updateVerticesData(VertexBuffer.ColorKind, colours, false, false);
		return end;
	}
	function dispose() {
		if (disposed) return;
		disposed = true; pendingThunder = null; hide(); schedule.reset();
		scene.onDisposeObservable.remove(disposeObserver); mesh.dispose(false, false); material.dispose();
	}
	const disposeObserver = scene.onDisposeObservable.addOnce(dispose);
	return {
		/** worldMs is the weather authority's baseMs + elapsed, even when envHour freezes appearance. */
		update(appearance:LightningAppearance, worldMs:number, focus:LightningPoint,
			frameOptions?:{readonly viewDirection?:LightningPoint;readonly clockRevision?:string|number}) {
			if (disposed) return;
			if (!Number.isFinite(focus?.x) || !Number.isFinite(focus?.y) || !Number.isFinite(focus?.z)) {
				schedule.reset(); pendingThunder = null; hide(); return;
			}
			controls.quality = quality; controls.reducedMotion = reducedMotion; controls.reducedFlashes = reducedFlashes;
			controls.clockRevision = frameOptions?.clockRevision ?? options.clockRevision;
			const frame = schedule.update(worldMs, appearance, controls);
			if (generation !== frame.generation) {generation = frame.generation; pendingThunder = null;}
			if (!frame.eligible) {pendingThunder = null; hide(); return;}
			if (frame.began) {
				const position = build(frame.seed, focus, frameOptions?.viewDirection);
				const distanceM = Math.hypot(position.x - focus.x, position.y - focus.y, position.z - focus.z);
				const delayMs = distanceM / 343 * 1_000;
				pendingThunder = {strikeAtWorldMs: frame.startedAtMs, playAtWorldMs: frame.startedAtMs + delayMs,
					distanceM, delayMs, position, seed: frame.seed, clockRevision: controls.clockRevision};
				strikeCount++;
			}
			if (pendingThunder && worldMs >= pendingThunder.playAtWorldMs) {
				const event = pendingThunder; pendingThunder = null;
				if (worldMs - event.playAtWorldMs <= 250) options.onThunder?.(event);
			}
			activePaths = frame.active ? lightningQuality(quality).paths : 0;
			if (activePaths && mesh.subMeshes?.[0]) mesh.subMeshes[0].indexCount = activePaths * INDICES_PER_PATH;
			material.alpha = frame.opacity; mesh.setEnabled(frame.active); flash(frame.flash);
		},
		setQuality(value:LightningQuality) {if (!disposed) quality = value;},
		setAccessibility(value:{readonly reducedMotion?:boolean;readonly reducedFlashes?:boolean}) {
			if (disposed) return;
			reducedMotion = value.reducedMotion ?? reducedMotion; reducedFlashes = value.reducedFlashes ?? reducedFlashes;
			if (reducedMotion || reducedFlashes) {schedule.reset(); pendingThunder = null; hide();}
		},
		reset() {if (!disposed) {schedule.reset(); pendingThunder = null; hide();}},
		/** Called by the existing loading gate. Uses the engine's own GLSL or WGSL StandardMaterial. */
		prewarm() {return disposed ? Promise.resolve() : material.forceCompilationAsync(mesh);},
		diagnostics() {return {disposed, activePaths, strikeCount, flash: lastFlash, pendingThunder: !!pendingThunder,
			maxDrawCalls: 1, maxVertices: positions.length / 3, maxTriangles: indices.length / 3,
			cpuArrayBytes: paths.byteLength + positions.byteLength + colours.byteLength + indices.byteLength};},
		dispose,
	};
}
