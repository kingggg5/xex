import { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { InstancedMesh } from "@babylonjs/core/Meshes/instancedMesh";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import type { Scene } from "@babylonjs/core/scene";
import type { ShadowGenerator } from "@babylonjs/core/Lights/Shadows/shadowGenerator";
import { mergeStaticModel } from "./static-model.mjs";
import { configureHeroOakLod } from "./hero-oak-lod.mjs";
import { addWind, type NatureClock } from "./nature-motion";
import type { WorldPropDefinition } from "./world-layout";
import lod0Url from "./assets/world/hero_oak_lod0.meshopt.glb?url";
import lod1Url from "./assets/world/hero_oak_lod1.meshopt.glb?url";
import lod2Url from "./assets/world/hero_oak_lod2.meshopt.glb?url";
import albedoUrl from "./assets/world/hero_oak_albedo.ktx2?url";

export const HERO_OAK_PROP_IDS = new Set(["sunmeadow_pine_west_mid", "sunmeadow_oak_east"]);

/** One shared texture/material and three instanced LODs, at authored blockers. */
export async function loadHeroOaks(scene: Scene, props: readonly WorldPropDefinition[],
	clock: NatureClock, shadows: ShadowGenerator, shadowsEnabled: boolean,
	prepare: (mesh: Mesh) => Promise<void>): Promise<void> {
	const placements = props.filter(prop => HERO_OAK_PROP_IDS.has(prop.id));
	if (!placements.length) return;
	const material = new PBRMaterial("sunmeadow-hero-oak", scene);
	material.albedoTexture = new Texture(albedoUrl, scene, false, false);
	material.albedoColor = Color3.FromHexString("#eef3df");
	material.metallic = 0;
	material.roughness = 0.92;
	addWind(material, scene, clock, 0.22, 1.85, 6.75);
	const kits: Mesh[] = [];
	const instances: InstancedMesh[] = [];
	try {
		for (const [index, url] of [lod0Url, lod1Url, lod2Url].entries()) {
			const loaded = await SceneLoader.ImportMeshAsync("", "", url, scene);
			const kit = mergeStaticModel(loaded, `sunmeadow-hero-oak-lod${index}`);
			kit.material = material;
			kit.isPickable = false;
			kit.receiveShadows = true;
			kit.isVisible = false;
			kits.push(kit);
		}
		const [master, medium, distant] = kits;
		configureHeroOakLod(master, medium, distant);
		for (const prop of placements) {
			if (prop.height !== 8.6 || Math.min(prop.collider_size[0], prop.collider_size[2]) < 1.4) {
				throw new Error(`Hero oak ${prop.id} does not match the normalized collision footprint.`);
			}
			const instance = master.createInstance(`hero-oak-${prop.id}`);
			instance.position.set(prop.x, 0, prop.z);
			// This rejected experimental kit must still fit its authored blocker.
			instance.scaling.setAll(Math.min(prop.scale, Math.min(prop.collider_size[0], prop.collider_size[2]) / 1.5));
			instance.rotation.y = prop.yaw;
			instance.isPickable = false;
			instance.isVisible = false;
			// Warm the instanced variant before exposing either tree.
			instances.push(instance);
		}
		for (const kit of kits) {
			await material.forceCompilationAsync(kit, { useInstances: true });
			await prepare(kit);
		}
		for (const instance of instances) {
			instance.isVisible = true;
			if (shadowsEnabled) shadows.addShadowCaster(instance, false);
		}
	} catch (error) {
		for (const instance of instances) instance.dispose();
		for (const kit of kits) kit.dispose(false, false);
		material.dispose(false, true);
		throw error;
	}
}
