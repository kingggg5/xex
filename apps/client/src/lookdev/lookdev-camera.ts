import type { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import type { Scene } from "@babylonjs/core/scene";
import type { LockedCamera } from "./lookdev-data.mjs";

/** Preserve the production camera/pipeline; own and restore only the review pose/input lock. */
export function createLookdevCameraLock(scene: Scene, camera: ArcRotateCamera, contract: () => LockedCamera) {
	const previousCamera = scene.activeCamera, previousCameras = scene.activeCameras;
	const pose = { alpha: camera.alpha, beta: camera.beta, radius: camera.radius, fov: camera.fov, target: camera.getTarget().clone(),
		lowerRadiusLimit: camera.lowerRadiusLimit, upperRadiusLimit: camera.upperRadiusLimit, lowerBetaLimit: camera.lowerBetaLimit, upperBetaLimit: camera.upperBetaLimit,
		inertialAlphaOffset: camera.inertialAlphaOffset, inertialBetaOffset: camera.inertialBetaOffset, inertialRadiusOffset: camera.inertialRadiusOffset,
		inertialPanningX: camera.inertialPanningX, inertialPanningY: camera.inertialPanningY };
	const inputsWereAttached = camera.inputs.attachedToElement, previousNoPreventDefault = camera.inputs.noPreventDefault;
	if (inputsWereAttached) camera.inputs.detachElement();
	camera.lowerRadiusLimit = null; camera.upperRadiusLimit = null; camera.lowerBetaLimit = null; camera.upperBetaLimit = null;
	let disposed = false;
	function apply() {
		if (disposed) return; const spec = contract();
		camera.alpha = spec.alpha; camera.beta = spec.beta; camera.radius = spec.radius; camera.fov = spec.fov;
		camera.inertialAlphaOffset = 0; camera.inertialBetaOffset = 0; camera.inertialRadiusOffset = 0; camera.inertialPanningX = 0; camera.inertialPanningY = 0;
		camera.setTarget(new Vector3(spec.target.x, spec.target.y, spec.target.z), false, false, true);
		scene.activeCamera = camera; scene.activeCameras = null;
	}
	const observer = scene.onBeforeRenderObservable.add(apply);
	function dispose() {
		if (disposed) return; disposed = true; scene.onBeforeRenderObservable.remove(observer);
		if (scene.activeCamera === camera) { scene.activeCamera = previousCamera; scene.activeCameras = previousCameras; }
		const { target, ...properties } = pose; Object.assign(camera, properties); camera.setTarget(target, false, false, true);
		if (inputsWereAttached && !scene.isDisposed) camera.inputs.attachElement(previousNoPreventDefault);
	}
	return { apply, dispose };
}
