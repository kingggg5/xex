import { HemisphericLight } from '@babylonjs/core/Lights/hemisphericLight';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
import type { Scene } from '@babylonjs/core/scene';
import { readWeatherFrame } from './ambient-weather-channel';

/** One borrowed-clock fill for the inspected local hero, including its LODs.
 * No emission, shadow target, particles, scene scan or per-actor render pass.
 */
export function bindHeroReadabilityLight(scene: Scene, meshes: readonly AbstractMesh[],
	readDaylight = () => readWeatherFrame(scene)?.appearance.daylight ?? 1) {
	const selected = meshes.filter(mesh => !mesh.isDisposed() && mesh.getTotalVertices() > 0);
	if (!selected.length) return () => {};
	const fill = new HemisphericLight('hero-night-readability', new Vector3(0, 1, -.25), scene);
	fill.includedOnlyMeshes = selected;
	fill.diffuse = Color3.FromHexString('#bdd6ed');
	fill.groundColor = Color3.FromHexString('#304450');
	fill.specular = Color3.Black();
	const update = () => {
		const daylight = readDaylight();
		fill.intensity = Number.isFinite(daylight) ? .48 * (1 - Math.min(1, Math.max(0, daylight))) : 0;
	};
	update();
	const observer = scene.onBeforeRenderObservable.add(update);
	let disposed = false;
	const dispose = () => {
		if (disposed) return;
		disposed = true;
		scene.onBeforeRenderObservable.remove(observer);
		scene.onDisposeObservable.remove(onDispose);
		fill.dispose();
	};
	const onDispose = scene.onDisposeObservable.addOnce(dispose);
	return dispose;
}
