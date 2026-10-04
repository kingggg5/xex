import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { SubMesh } from '@babylonjs/core/Meshes/subMesh';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import { MultiMaterial } from '@babylonjs/core/Materials/multiMaterial';
import type { Texture } from '@babylonjs/core/Materials/Textures/texture';
import type { Scene } from '@babylonjs/core/scene';
import type { NatureClock } from './nature-motion';
import { createCityWaterEngine } from './city-water-engine';

/** Existing legacy-active placeholder filter; geometry candidates remove their exact source objects. */
export function removeFountainPlaceholders(mesh: Mesh, centerZ: number): number {
	if (!(mesh.material instanceof MultiMaterial)) return 0;
	const positions = mesh.getVerticesData(VertexBuffer.PositionKind), indices = mesh.getIndices();
	if (!positions || !indices) return 0;
	mesh.computeWorldMatrix(true); const world = mesh.getWorldMatrix();
	const rebuilt: number[] = [], ranges: Array<{material: number; start: number; count: number}> = [];
	let removed = 0;
	for (const sub of mesh.subMeshes) {
		const material = mesh.material.subMaterials[sub.materialIndex], name = material?.name ?? '';
		const water = name === 'water' || name === 'water_foam';
		const start = rebuilt.length;
		for (let i = sub.indexStart; i < sub.indexStart + sub.indexCount; i += 3) {
			let discard = false;
			if (water) {
				const a = indices[i]*3, b = indices[i+1]*3, c = indices[i+2]*3;
				const point = Vector3.TransformCoordinates(new Vector3((positions[a]+positions[b]+positions[c])/3, (positions[a+1]+positions[b+1]+positions[c+1])/3, (positions[a+2]+positions[b+2]+positions[c+2])/3), world);
				const radius = Math.hypot(point.x, point.z-centerZ);
				discard = radius < 9.0 && point.y > 2.0 && point.y < 7.3;
			}
			if (discard) removed++; else rebuilt.push(indices[i], indices[i+1], indices[i+2]);
		}
		ranges.push({material:sub.materialIndex,start,count:rebuilt.length-start});
	}
	if (removed) {
		mesh.setIndices(rebuilt); mesh.releaseSubMeshes();
		for (const range of ranges) if (range.count) new SubMesh(range.material, 0, positions.length/3, range.start, range.count, mesh);
	}
	return removed;
}


/** Bridge the city's staged reveal/settings API to Babylon's native water systems. */
export function createCityFountain(
	scene: Scene, centerZ: number, clock: NatureClock,
	options: { normalTexture?: Texture } = {},
) {
	const water = createCityWaterEngine(scene, centerZ, clock, options);
	let readyToReveal = false, disposed = false;
	const ready = water.ready.then(() => { if (!disposed) readyToReveal = true; });
	const debug = import.meta.env.DEV && typeof document !== 'undefined' && new URLSearchParams(location.search).get('debugFountain') === '1'
		? document.createElement('output') : undefined;
	if (debug) {
		debug.style.cssText = 'position:fixed;top:80px;left:12px;z-index:1001;background:#10212de8;color:#ffe3a4;padding:8px;font:12px system-ui';
		document.body.append(debug);
	}
	const updateDebug = () => {
		if (!debug || disposed) return;
		const state = water.stats();
		debug.textContent = `Native fountain: ${state.revealed}; ready ${readyToReveal}; pools ${water.meshes.filter(mesh => mesh.isEnabled()).length}; outlets ${state.activeOutlets}/${state.selectedOutlets}; particles ${state.activeParticles}; IBL ${!!scene.environmentTexture}`;
	};
	const debugObserver = debug ? scene.onBeforeRenderObservable.add(updateDebug) : null;
	const sceneDisposal = scene.onDisposeObservable.addOnce(dispose);
	function dispose() {
		if (disposed) return;
		disposed = true; readyToReveal = false;
		if (debugObserver) scene.onBeforeRenderObservable.remove(debugObserver);
		scene.onDisposeObservable.remove(sceneDisposal);
		debug?.remove(); water.dispose();
	}
	// Keep lazy preparation's rejected promise observable to its caller, while
	// cleaning up a failure that happens before the player reaches the gate.
	void ready.catch(() => dispose());
	updateDebug();
	return {
		meshes: water.meshes,
		materials: water.materials,
		particleSystems: water.particleSystems,
		/** Await before the existing forceCompilationAsync warm-up and staged reveal. */
		ready,
		reveal() {
			if (disposed) return;
			if (!readyToReveal) throw new Error('Await fountain.ready before revealing native water.');
			water.reveal(); updateDebug();
		},
		hide() { if (!disposed) { water.hide(); updateDebug(); } },
		setDetail(value: number) { if (!disposed) water.setDetail(value); },
		dispose,
		get stats() {
			const state = water.stats();
			return {
				// Retain legacy keys; no tube meshes, torus rings or custom droplet pool remain.
				surfaceMeshes: state.surfaceMeshes, jetMeshes: 0, individualStreams: state.selectedOutlets,
				impactRings: 0, pooledDroplets: 1536, reflectionPasses: 0, normalDimension: 1024,
				nativeParticleSystems: state.nativeParticleSystems, nativeParticleCapacity: state.nativeParticleCapacity,
				activeOutlets: state.activeOutlets, activeParticles: state.activeParticles, culled: state.culled,
			};
		},
	};
}
