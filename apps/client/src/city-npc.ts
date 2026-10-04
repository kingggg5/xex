import { SceneLoader } from '@babylonjs/core/Loading/sceneLoader';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode';
import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { Vector3, Matrix } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';
import type { AssetContainer } from '@babylonjs/core/assetContainer';
import type { AnimationGroup } from '@babylonjs/core/Animations/animationGroup';
import balancedUrl from '../../../assets/characters/bovine-shaman/rig-v1/runtime/optimized/minotaur_lod1.etc1s-meshopt.glb?url';
import lowUrl from '../../../assets/characters/bovine-shaman/rig-v1/runtime/optimized/minotaur_lod2.etc1s-meshopt.glb?url';

export interface CityNpcDefinition { id: string; x: number; y?: number; z: number; facing: number; name: string; }

/** One resident, loaded on approach. Imported hidden, warmed, then revealed. */
export function createCityNpc(scene: Scene, definition: CityNpcDefinition, options: {
	low: boolean; preview: boolean; addShadowCaster(root: TransformNode): void;
	prepare(meshes: readonly Mesh[]): Promise<void>;
}) {
	const root = new TransformNode(`npc-${definition.id}`, scene);
	root.position.set(definition.x, definition.y ?? 0, definition.z); root.rotation.y = definition.facing;
	let state: 'idle' | 'loading' | 'ready' | 'failed' = 'idle';
	let container: AssetContainer | undefined, idle: AnimationGroup | undefined, talk: AnimationGroup | undefined;
	let disposed = false, talkUntil = 0, lastLabelUpdate = 0;
	let motion: 'paused' | 'idle' | 'talk' = 'paused';
	const identity = Matrix.Identity(), labelPosition = new Vector3(definition.x, (definition.y ?? 0) + 2.68, definition.z);
	const label = document.createElement('div'); label.className = 'city-npc-label'; label.textContent = definition.name;
	label.style.cssText = 'position:fixed;left:0;top:0;z-index:25;pointer-events:none;white-space:nowrap;font:600 13px system-ui;color:#ffdf9b;text-shadow:0 1px 3px #10212f,1px 0 2px #10212f;display:none';
	document.body.append(label);
	async function load(): Promise<void> {
		if (disposed || state !== 'idle') return; state = 'loading';
		try {
			const imported = await SceneLoader.LoadAssetContainerAsync('', options.low ? lowUrl : balancedUrl, scene);
			if (disposed || scene.isDisposed) { imported.dispose(); return; }
			container = imported;
			for (const mesh of imported.meshes) { mesh.isVisible = false; mesh.isPickable = false; mesh.receiveShadows = true; }
			imported.addAllToScene();
			for (const node of [...imported.transformNodes, ...imported.meshes]) if (!node.parent) node.parent = root;
			idle = imported.animationGroups.find(group => group.name === 'Idle');
			talk = imported.animationGroups.find(group => group.name === 'Talk');
			if (!idle || !talk || imported.skeletons.length !== 1) throw new Error('City resident is missing its verified skeleton/Idle/Talk clips.');
			imported.animationGroups.forEach(group => group.stop());
			await options.prepare(imported.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh));
			if (disposed || scene.isDisposed) { imported.dispose(); return; }
			idle.start(true); motion = 'idle'; imported.meshes.forEach(mesh => { mesh.isVisible = true; });
			options.addShadowCaster(root); state = 'ready';
		} catch (error) {
			container?.dispose(); container = undefined;
			if (!disposed) { state = 'failed'; console.warn('City resident model unavailable.', error); }
		}
	}
	const observer = scene.onBeforeRenderObservable.add(() => {
		const camera = scene.activeCamera; if (!camera || disposed) return;
		const now = performance.now(), distance = Vector3.DistanceSquared(camera.globalPosition, root.position);
		if (state === 'idle' && (options.preview || distance < 85 ** 2)) void load();
		const active = state === 'ready' && distance < 60 ** 2;
		if (container) for (const mesh of container.meshes) mesh.isVisible = active;
		if (idle && talk) {
			const nextMotion = !active ? 'paused' : now < talkUntil ? 'talk' : 'idle';
			if (nextMotion !== motion) {
				if (nextMotion === 'paused') { idle.pause(); talk.pause(); }
				else if (nextMotion === 'talk') { idle.pause(); talk.play(true); }
				else { if (talk.isStarted) talk.stop(); idle.play(true); }
				motion = nextMotion;
			}
		}
		if (now - lastLabelUpdate < 100) return; lastLabelUpdate = now;
		const viewport = camera.viewport.toGlobal(scene.getEngine().getRenderWidth(), scene.getEngine().getRenderHeight());
		const point = Vector3.Project(labelPosition, identity, scene.getTransformMatrix(), viewport);
		const canvas = scene.getEngine().getRenderingCanvas(), bounds = canvas?.getBoundingClientRect();
		if (!active || !bounds || point.z < 0 || point.z > 1) { label.style.display = 'none'; return; }
		label.style.display = 'block';
		const x = bounds.left + point.x * bounds.width / scene.getEngine().getRenderWidth();
		const y = bounds.top + point.y * bounds.height / scene.getEngine().getRenderHeight();
		label.style.transform = `translate(${x}px,${y}px) translate(-50%,-100%)`;
	});
	const dispose = () => { if (disposed) return; disposed = true; scene.onBeforeRenderObservable.remove(observer); container?.dispose(); root.dispose(); label.remove(); };
	scene.onDisposeObservable.addOnce(dispose);
	return { root, state: () => state, speak() { talkUntil = performance.now() + 3000; }, dispose };
}
