import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { Scene } from "@babylonjs/core/scene";

/**
 * Cosmetic presentation for D-14 (outfits/skins and a follower pet).
 * Presentation only: the server owns ownership/equipment state and the client
 * renders it. The pet is a decorative follower — combat pets are out of P1.
 */

const DEFAULT_TUNIC = "#3d5f92";

/** Recolors the local hero's tunic (both skirt and torso share one material). */
export function applyLocalSkin(world: { localRoot: TransformNode }, tunicHex: string | null): void {
	const color = Color3.FromHexString(tunicHex ?? DEFAULT_TUNIC);
	for (const descendant of world.localRoot.getDescendants(false)) {
		if (!descendant.name.includes("-tunic-") || !(descendant instanceof Mesh)) continue;
		const material = descendant.material;
		if (material instanceof StandardMaterial) {
			material.diffuseColor = color;
		}
	}
}

/**
 * Spawns the decorative follower pet and returns its cleanup. The pet trails
 * behind the local player with a light bob; call the cleanup before spawning
 * a different pet (or on dispose).
 */
export function spawnLocalPet(
	scene: Scene,
	world: { localRoot: TransformNode },
	tintHex: string | null,
): (() => void) | null {
	const tint = Color3.FromHexString(tintHex ?? "#8fd06a");

	const root = new TransformNode("cosmetic-pet", scene);
	const bodyMaterial = new StandardMaterial("cosmetic-pet-body", scene);
	bodyMaterial.diffuseColor = tint;
	bodyMaterial.specularColor = Color3.FromHexString("#ffffff");
	bodyMaterial.specularPower = 32;

	const body = MeshBuilder.CreateSphere("cosmetic-pet-body", { diameter: 0.55, segments: 8 }, scene);
	body.scaling.set(1, 0.82, 1.05);
	body.material = bodyMaterial;
	body.parent = root;
	body.isPickable = false;

	const leaf = MeshBuilder.CreateCylinder("cosmetic-pet-leaf", { height: 0.34, diameterBottom: 0.1, diameterTop: 0, tessellation: 4 }, scene);
	leaf.position.y = 0.36;
	leaf.rotation.z = 0.2;
	const leafMaterial = new StandardMaterial("cosmetic-pet-leaf-material", scene);
	leafMaterial.diffuseColor = Color3.FromHexString("#4d8747");
	leaf.material = leafMaterial;
	leaf.parent = root;
	leaf.isPickable = false;

	const eyeMaterial = new StandardMaterial("cosmetic-pet-eye", scene);
	eyeMaterial.diffuseColor = Color3.FromHexString("#26212e");
	for (const [index, x] of [-0.09, 0.09].entries()) {
		const eye = MeshBuilder.CreateSphere(`cosmetic-pet-eye-${index}`, { diameter: 0.07, segments: 5 }, scene);
		eye.position.set(x, 0.06, 0.24);
		eye.material = eyeMaterial;
		eye.parent = root;
		eye.isPickable = false;
	}

	const trailOffset = new Vector3(0, 0, -0.9);
	let bobPhase = 0;
	const observer = scene.onBeforeRenderObservable.add(() => {
		const delta = scene.getEngine().getDeltaTime() / 1000;
		const now = performance.now() * 0.001;
		bobPhase = now * 4.2;
		const target = world.localRoot.position.add(trailOffset);
		// Exponential trail so the pet lags the turn like a real follower.
		root.position.x += (target.x - root.position.x) * Math.min(1, delta * 6);
		root.position.z += (target.z - root.position.z) * Math.min(1, delta * 6);
		root.position.y = Math.abs(Math.sin(bobPhase)) * 0.1;
	});

	return () => {
		scene.onBeforeRenderObservable.remove(observer);
		root.dispose(false, true);
		bodyMaterial.dispose();
		leafMaterial.dispose();
		eyeMaterial.dispose();
	};
}

/** Resolves a bundle cosmetic id to the hex the presentation layer needs. */
export function cosmeticHex(
	economy: { skins: Record<string, { tunic: string }>; pets: Record<string, { tint?: string }> } | null | undefined,
	id: string,
): string | null {
	if (!economy) return null;
	return economy.skins[id]?.tunic ?? economy.pets[id]?.tint ?? null;
}
