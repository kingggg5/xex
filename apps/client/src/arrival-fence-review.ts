import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { SceneLoader } from '@babylonjs/core/Loading/sceneLoader';
import type { AssetContainer } from '@babylonjs/core/assetContainer';
import type { Scene } from '@babylonjs/core/scene';
import lod0Url from '../../../assets/models/sunmeadow-props/craft/arrival-fence-r01/arrival_fence_lod0-ready.glb?url';
import lod1Url from '../../../assets/models/sunmeadow-props/craft/arrival-fence-r01/arrival_fence_lod1-ready.glb?url';
import lod2Url from '../../../assets/models/sunmeadow-props/craft/arrival-fence-r01/arrival_fence_lod2-ready.glb?url';

/** Replace only the existing22 arrival-fence meshes after a complete staged load.
 * Original collision/layout is retained. All three LODs borrow one PBR texture set.
 */
export async function createArrivalFenceReview(scene: Scene) {
	const legacy = scene.meshes.filter(mesh => /^env-fence-(post|rail)-/.test(mesh.name));
	if (legacy.length !== 22) throw new Error('Arrival fence source roster changed');
	const enabled = legacy.map(mesh => mesh.isEnabled());
	const containers: AssetContainer[] = [], merged: Mesh[] = [];
	let disposed = false;
	const dispose = () => {
		if (disposed) return;
		disposed = true;
		for (const mesh of merged) mesh.dispose(false, false);
		for (const container of containers) container.dispose();
		if (!scene.isDisposed) legacy.forEach((mesh,index) => { if (!mesh.isDisposed()) mesh.setEnabled(enabled[index]); });
	};
	try {
		for (const [index,url] of [lod0Url,lod1Url,lod2Url].entries()) {
			const container = await SceneLoader.LoadAssetContainerAsync('', url, scene);
			containers.push(container);
			if (scene.isDisposed) throw new Error('Scene closed while preparing fence');
			const parts = container.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.getTotalVertices() > 0);
			if (parts.length !== 1 || parts[0].getTotalIndices()/3 !== [2344,1344,744][index]) throw new Error('Unexpected fence LOD geometry');
			parts[0].computeWorldMatrix(true);
			const mirrored = parts[0].getWorldMatrix().determinant() < 0;
			// The standard engine merge bakes the AUTO glTF handedness transform.
			const mesh = Mesh.MergeMeshes(parts,true,true,undefined,false,false);
			if (!mesh) throw new Error('Fence geometry merge failed');
			merged.push(mesh);
			if (!mesh.material) throw new Error('Fence material missing');
			// Match static-model.mjs: Babylon only corrects mirror winding when
			// merging multiple parts. Each fence LOD is a single reflected part.
			if (mirrored) mesh.flipFaces(false);
			mesh.name = `arrival-fence-review-lod${index}`;
			mesh.setEnabled(false);mesh.isPickable=false;mesh.receiveShadows=true;
			mesh.metadata={arrivalFenceReview:true,lod:index,unadmitted:true};
			if (index > 0) mesh.material = merged[0].material;
		}
		const base = merged[0];
		await base.material!.forceCompilationAsync(base);
		if(scene.isDisposed)throw new Error('Scene closed while warming fence');
		// Conservative distance from the batch centre. Visibility is per batch,
		// not falsely described as independent per-post occlusion.
		base.addLODLevel(26,merged[1]);base.addLODLevel(52,merged[2]);base.addLODLevel(85,null);
		merged[1].setEnabled(true);merged[2].setEnabled(true);base.setEnabled(true);
		legacy.forEach(mesh => mesh.setEnabled(false));
		scene.metadata={...scene.metadata,arrivalFenceReview:{status:'NATIVE_REVIEW_REQUIRED',triangles:[2344,1344,744],materials:1,sourceMeshes:22,
			lod0Sha256:'e15836880f3b903a231dea351ecbedd270dc31ed540662175db99bedf0d134d9',colliders:'UNCHANGED'}};
		scene.onDisposeObservable.addOnce(dispose);
		return dispose;
	}catch(error){dispose();throw error;}
}
