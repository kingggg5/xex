import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer';
import { Vector3 } from '@babylonjs/core/Maths/math.vector';
import { GATE_CITY_TREE_PARTS, planGateCityTreeCandidate, type GateTreePrimitive, type GateTreePlacement } from './gate-city-tree-candidate.mjs';

/** Call only on original loaded active-R5 primitives, before merging, after the shared CC0 kit is ready.
 * All index/count/AABB witnesses validate before the first mutation; failure leaves original art intact. */
export function prepareGateCityTreeCandidate(loaded: { meshes: readonly unknown[] }, runtimeSha256: string): {
	placement: GateTreePlacement; removedTriangles: number; originalCollider: string;
} {
	const targets = new Set(GATE_CITY_TREE_PARTS.map(part => part.material));
	const meshes = loaded.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && targets.has(mesh.material?.name ?? ''));
	const point = new Vector3();
	const inputs: GateTreePrimitive[] = meshes.map(mesh => {
		if (mesh.getScene().useRightHandedSystem || !mesh.geometry || mesh.geometry.meshes.length !== 1)
			throw new Error('Gate tree guard: original LH primitive geometry must be unique');
		const positions = mesh.getVerticesData(VertexBuffer.PositionKind), indices = mesh.getIndices();
		if (!positions || !indices) throw new Error('Gate tree guard: primitive data missing');
		const world = mesh.computeWorldMatrix(true);
		return { name: mesh.name, material: mesh.material!.name, indices,
			gltfPositionAt(index) {
				Vector3.TransformCoordinatesFromFloatsToRef(positions[index*3], positions[index*3+1], positions[index*3+2], world, point);
				// AUTO glTF in LH reflects X (Y=pi, Z=-1). Restore glTF space only for immutable witnesses.
				return [-point.x, point.y, point.z];
			} };
	});
	const plan = planGateCityTreeCandidate(inputs, runtimeSha256);
	const applied: Mesh[] = [];
	try {
		for (const patch of plan.patches) {
			const mesh = meshes.find(item => item.material!.name === patch.material)!;
			mesh.setIndices(patch.indices); applied.push(mesh);
		}
	} catch (error) {
		for (const mesh of applied) mesh.setIndices(plan.patches.find(patch => patch.material === mesh.material!.name)!.originalIndices as number[]);
		throw error;
	}
	return { placement: plan.placement, removedTriangles: plan.removedTriangles, originalCollider: 'blossom tree trunk.003' };
}
