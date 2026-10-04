import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import type { Scene } from "@babylonjs/core/scene";
import { alignWorldAuthoredGlb } from "./world-asset-coordinates.mjs";
import { addMountainSurface } from "./mountain-surface";
import mountainUrl from "./assets/world/env_border_mountains_v1.meshopt.glb?url";
import cliffAlbedoUrl from "./assets/world/cliff_granite_albedo.png?url";

/** Authored scenery outside the server's traversable square, in canonical metres. */
export async function loadWorldBorder(scene: Scene, grass: PBRMaterial,
	prepare: (mesh: Mesh) => Promise<void>): Promise<void> {
	const rock = new PBRMaterial("env-border-granite", scene);
	const albedo = new Texture(cliffAlbedoUrl, scene, false, false);
	albedo.gammaSpace = true;
	albedo.wrapU = albedo.wrapV = Texture.MIRROR_ADDRESSMODE;
	albedo.uScale = albedo.vScale = 2;
	rock.albedoTexture = albedo;
	rock.metallic = 0;
	rock.roughness = 0.94;
	rock.transparencyMode = PBRMaterial.MATERIAL_OPAQUE;
	addMountainSurface(rock);
	const loaded = await SceneLoader.ImportMeshAsync("", "", mountainUrl, scene);
	alignWorldAuthoredGlb(loaded, scene);
	const meshes = loaded.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.getTotalVertices() > 0);
	if (meshes.length !== 16) throw new Error(`Expected 16 border mountain surfaces, found ${meshes.length}.`);
	for (const mesh of meshes) {
		mesh.material = mesh.name.endsWith("_grass") ? grass : rock;
		mesh.isPickable = false;
		mesh.receiveShadows = true;
		mesh.isVisible = false;
	}
	for (const mesh of meshes) await prepare(mesh);
	for (const mesh of meshes) mesh.isVisible = true;
}
