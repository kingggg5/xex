import { Quaternion } from '@babylonjs/core/Maths/math.vector.js';
import { Material } from '@babylonjs/core/Materials/material.js';

/** These GLBs encode canonical world X/Y/Z, rather than an asset-local placement. */
export function alignWorldAuthoredGlb(loaded, scene) {
	const root = loaded.meshes.find(mesh => mesh.name === '__root__' && !mesh.parent);
	if (!root) throw new Error('World-authored GLB is missing its loader root.');
	if (root.position.lengthSquared() > 1e-8) throw new Error('Unexpected translated world-asset loader root.');
	// AUTO imports into a LH scene reflect X through Y=pi and Z=-1. Those
	// canonical cell/prop coordinates already share the server basis.
	root.rotationQuaternion = Quaternion.Identity();
	root.rotation.setAll(0);
	root.scaling.setAll(1);
	root.computeWorldMatrix(true);
	for (const mesh of loaded.meshes) {
		// With AUTO's reflection removed, front faces must follow the scene's
		// camera basis. Native LH A/B review restores the mountain toe with CW.
		mesh.sideOrientation = scene.useRightHandedSystem
			? Material.CounterClockWiseSideOrientation : Material.ClockWiseSideOrientation;
		mesh.computeWorldMatrix(true);
	}
	return root;
}
