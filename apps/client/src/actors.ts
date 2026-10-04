import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import "@babylonjs/core/Meshes/instancedMesh";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import type { Scene } from "@babylonjs/core/scene";

/**
 * Actor & material factory for the meadow scene (original IP, flat-shaded low-poly).
 *
 * Contracts relied on by scene.ts:
 * - createMaterials: every key below is read by scene.ts / the environment module. New keys
 *   (stone, moss, water, cloud, hillHaze, shadowBlob, slimeBelly, slimeGlint, slimeBlush)
 *   are additive.
 * - createHero: returns a root TransformNode; scene sets root.position.x/z and rotation.y
 *   (front faces +z at rotation.y = 0, matching main.ts atan2(movement.x, movement.z)),
 *   and bobs root.position.y.
 * - createSlime: body is a Mesh parented DIRECTLY to root, diameter 1.42, rest pose
 *   scaling (1.05, 0.72, 0.9) / position.y 0.52 — scene.ts animateMonsterHop writes those
 *   channels absolutely. `material` is a per-slime clone; scene.ts mutates its
 *   emissiveColor for hit flash and restores it. Face/underbelly are children of `body`
 *   so they follow squash & leap.
 * - createRouteGuide: returns a root TransformNode; scene bobs root.position.y.
 * - createWindmark: scene sets root.position, bobs crystal.position.y around 1.05 and
 *   swaps crystal/ring materials on quest activation.
 * No lights, shadow generators or glow layers are created here; scene.ts registers the
 * returned roots itself. Nothing runs at import time.
 */

export function createMaterials(scene: Scene): Record<string, StandardMaterial> {
	const make = (name: string, color: string, specular = "#000000", emissive?: string, specularPower?: number) => {
		const material = new StandardMaterial(name, scene);
		material.diffuseColor = Color3.FromHexString(color);
		material.specularColor = Color3.FromHexString(specular);
		if (emissive) material.emissiveColor = Color3.FromHexString(emissive);
		if (specularPower !== undefined) material.specularPower = specularPower;
		return material;
	};
	const materials: Record<string, StandardMaterial> = {
		// meadow
		grass: make("grass", "#5f9245", "#7fa065", undefined, 10),
		grassLight: make("grass-light", "#82b054", "#9fbd7f", undefined, 10),
		path: make("warm-stone", "#8f704b", "#a98960", undefined, 10),
		pathDark: make("path-edge", "#6e5840", "#82684a"),
		// limestone castle
		wall: make("castle-limestone", "#a09b85", "#c6bfa6", undefined, 14),
		wallLight: make("castle-highlight", "#c1bca4", "#ddd8c2", undefined, 14),
		roof: make("castle-roof", "#3f6398", "#8fb0d6", undefined, 42),
		roofLight: make("roof-light", "#5b82b4", "#9dbbdd", undefined, 42),
		// flora & props
		wood: make("warm-wood", "#6b4a32", "#8a6a4c"),
		woodLight: make("fence-wood", "#aa7f51", "#c8a374"),
		leaves: make("tree-leaves", "#4d8747", "#334a2e", undefined, 6),
		leavesLight: make("tree-leaves-light", "#7dab52", "#455f36", undefined, 6),
		leavesGold: make("sunlit-leaves", "#c0ad55", "#63562d", undefined, 8),
		flowerWhite: make("flower-white", "#fff6dc", "#fffdf2", undefined, 24),
		flowerGold: make("flower-gold", "#f6c95f", "#fff0c0", undefined, 24),
		flowerPink: make("flower-pink", "#e2879f", "#ffd9e2", undefined, 24),
		stem: make("flower-stem", "#5b8143", "#77a05c"),
		stone: make("standing-stone", "#98937f", "#4d4a40", undefined, 12),
		moss: make("stone-moss", "#6f9c4b", "#8fbb6f", undefined, 10),
		water: make("stream-water", "#7fc4d8", "#e8fbff"),
		cloud: make("cloud-white", "#f1f3ee", "#000000", undefined, 6),
		hillHaze: make("far-hill-haze", "#789468", "#111b0c", undefined, 5),
		// hero
		armor: make("blue-steel", "#54709a", "#c2d3e4", undefined, 48),
		armorLight: make("silver-armor", "#d5dfe3", "#ffffff", undefined, 64),
		cloth: make("ivory-cloak", "#eae3cd", "#fffdf0", undefined, 16),
		clothBlue: make("blue-cloth", "#3d5f92", "#a5bbd6", undefined, 24),
		leather: make("brown-leather", "#6b4a33", "#8f6c4e"),
		skin: make("warm-skin", "#e2ac85", "#f7cfae", undefined, 20),
		hair: make("dark-hair", "#43322d", "#5f4a40"),
		hairLight: make("hair-edge", "#6a5346", "#84695a"),
		eye: make("dark-eye", "#26212e", "#ffffff", undefined, 96),
		// puddlekin
		slime: make("slime-pink", "#ef92b4", "#ffe6f0", "#3a1a2b", 20),
		slimeEye: make("slime-eye", "#33243f", "#8f7fa0"),
		slimeBelly: make("slime-belly", "#c46e8d", "#ffd3e2", "#2e1220", 20),
		slimeGlint: make("slime-glint", "#f2fbff", "#ffffff", "#93b2c2", 32),
		slimeBlush: make("slime-blush", "#d95f88", "#ffb9cd", "#3c1524", 16),
		// quest & trim
		flag: make("banner-blue", "#4f7bb0", "#7e9cc4"),
		windmark: make("windmark-cyan", "#72d5de", "#eaffff", "#1d95a9", 32),
		window: make("warm-window", "#ffe5a1", "#ffffff", "#a97436"),
		metal: make("gold-trim", "#d9b76c", "#fff3c4", undefined, 56),
		// shared translucent contact-shadow disc under characters
		shadowBlob: make("shadow-blob", "#20342a"),
	};
	materials.shadowBlob.alpha = 0.22;
	return materials;
}

interface PropMasters {
	eye: Mesh;
	glint: Mesh;
	blush: Mesh;
	mouth: Mesh;
	belly: Mesh;
	pebble: Mesh;
}

/**
 * Shared master meshes, one set per scene, so every repeated tiny prop (slime face parts,
 * windmark pebbles) renders as InstancedMesh draw-call batches instead of one mesh each.
 * Masters keep isVisible = false; Babylon evaluates each instance independently of its
 * source mesh's visibility (scene.pure.js _evaluateActiveMeshes), so only instances draw.
 */
const propMastersPerScene = new WeakMap<Scene, PropMasters>();

function getPropMasters(scene: Scene, m: Record<string, StandardMaterial>): PropMasters {
	const existing = propMastersPerScene.get(scene);
	if (existing) return existing;
	const hide = (mesh: Mesh): Mesh => {
		mesh.isVisible = false;
		return mesh;
	};
	const masters: PropMasters = {
		eye: hide(MeshBuilder.CreateSphere("prop-master-slime-eye", { diameter: 0.19, segments: 7 }, scene)),
		glint: hide(MeshBuilder.CreateSphere("prop-master-slime-glint", { diameter: 0.06, segments: 5 }, scene)),
		blush: hide(MeshBuilder.CreateSphere("prop-master-slime-blush", { diameter: 0.12, segments: 5 }, scene)),
		mouth: hide(MeshBuilder.CreateTube("prop-master-slime-mouth", {
			path: Array.from({ length: 9 }, (_, index) => {
				const x = -0.15 + index * 0.0375;
				return new Vector3(x, -0.105 + 0.06 * (x / 0.15) ** 2, -0.7);
			}),
			radius: 0.024,
			tessellation: 8,
		}, scene)),
		belly: hide(MeshBuilder.CreateSphere("prop-master-slime-belly", { diameter: 1.34, segments: 10 }, scene)),
		pebble: hide(MeshBuilder.CreateSphere("prop-master-pebble", { diameter: 0.22, segments: 5 }, scene)),
	};
	masters.eye.material = m.slimeEye;
	masters.glint.material = m.slimeGlint;
	masters.blush.material = m.slimeBlush;
	masters.mouth.material = m.slimeEye;
	masters.belly.material = m.slimeBelly;
	masters.pebble.material = m.stone;
	propMastersPerScene.set(scene, masters);
	return masters;
}

function addBox(
	scene: Scene,
	root: TransformNode,
	id: string,
	width: number,
	height: number,
	depth: number,
	x: number,
	y: number,
	z: number,
	material: StandardMaterial,
): Mesh {
	const mesh = MeshBuilder.CreateBox(id, { width, height, depth }, scene);
	mesh.position.set(x, y, z);
	mesh.material = material;
	mesh.parent = root;
	return mesh;
}

function addSphere(
	scene: Scene,
	root: TransformNode,
	id: string,
	diameter: number,
	segments: number,
	x: number,
	y: number,
	z: number,
	material: StandardMaterial,
): Mesh {
	const mesh = MeshBuilder.CreateSphere(id, { diameter, segments }, scene);
	mesh.position.set(x, y, z);
	mesh.material = material;
	mesh.parent = root;
	return mesh;
}

function addCylinder(
	scene: Scene,
	root: TransformNode,
	id: string,
	height: number,
	diameterTop: number,
	diameterBottom: number,
	tessellation: number,
	x: number,
	y: number,
	z: number,
	material: StandardMaterial,
): Mesh {
	const mesh = MeshBuilder.CreateCylinder(id, { height, diameterTop, diameterBottom, tessellation }, scene);
	mesh.position.set(x, y, z);
	mesh.material = material;
	mesh.parent = root;
	return mesh;
}

/** Soft painted blob under a character so it reads against the ground in light and shadow. */
function addGroundBlob(scene: Scene, m: Record<string, StandardMaterial>, id: string, root: TransformNode, radius: number): Mesh {
	const blob = MeshBuilder.CreateDisc(id, { radius, tessellation: 20 }, scene);
	blob.rotation.x = Math.PI / 2;
	blob.position.y = 0.03;
	blob.material = m.shadowBlob;
	blob.parent = root;
	return blob;
}

export function createHero(scene: Scene, m: Record<string, StandardMaterial>, name: string, tunicColor: Color3): TransformNode {
	const root = new TransformNode(name, scene);
	root.scaling.setAll(1.08);
	const tunic = m.clothBlue.clone(`${name}-tunic`);
	tunic.diffuseColor = tunicColor;
	addGroundBlob(scene, m, `${name}-ground-shadow`, root, 0.6);

	// Rounded boots and shaped greaves give the avatar a readable silhouette from behind.
	for (const [side, x] of [["left", -0.17], ["right", 0.17]] as const) {
		const boot = addSphere(scene, root, `${name}-boot-${side}`, 0.34, 10, x, 0.13, 0.09, m.leather);
		boot.scaling.set(0.78, 0.55, 1.2);
		const greave = addCylinder(scene, root, `${name}-greave-${side}`, 0.58, 0.2, 0.27, 10, x, 0.46, -0.01, m.armor);
		greave.rotation.z = x < 0 ? -0.035 : 0.035;
	}

	// A layered field-coat, segmented cuirass and circular belt read as crafted gear.
	addCylinder(scene, root, `${name}-coat-skirt`, 0.5, 0.62, 0.95, 12, 0, 0.83, 0, tunic);
	addCylinder(scene, root, `${name}-coat-body`, 0.64, 0.62, 0.72, 12, 0, 1.32, 0, tunic);
	const breastplate = addSphere(scene, root, `${name}-breastplate`, 0.68, 12, 0, 1.34, 0.31, m.armor);
	breastplate.scaling.set(1.0, 0.8, 0.48);
	const chestInset = addSphere(scene, root, `${name}-chest-inset`, 0.28, 10, 0, 1.39, 0.49, m.clothBlue);
	chestInset.scaling.set(0.72, 1.12, 0.23);
	const belt = MeshBuilder.CreateTorus(`${name}-belt`, { diameter: 0.77, thickness: 0.1, tessellation: 16 }, scene);
	belt.rotation.x = Math.PI / 2;
	belt.position.set(0, 1.03, 0);
	belt.material = m.leather;
	belt.parent = root;
	addSphere(scene, root, `${name}-buckle`, 0.16, 8, 0, 1.03, 0.4, m.metal);

	// Rounded arms, plated shoulders and broad bracers create armor instead of cubes.
	for (const [side, x] of [["left", -0.43], ["right", 0.43]] as const) {
		const arm = addCylinder(scene, root, `${name}-arm-${side}`, 0.62, 0.19, 0.25, 10, x, 1.23, 0.02, m.armorLight);
		arm.rotation.z = x < 0 ? -0.1 : 0.1;
		const shoulder = addSphere(scene, root, `${name}-pauldron-${side}`, 0.42, 10, x * 0.93, 1.57, -0.01, m.armor);
		shoulder.scaling.set(1.15, 0.68, 0.92);
		const bracer = addCylinder(scene, root, `${name}-bracer-${side}`, 0.26, 0.24, 0.28, 10, x * 1.12, 0.98, 0.04, m.metal);
		bracer.rotation.z = x < 0 ? -0.1 : 0.1;
		addSphere(scene, root, `${name}-glove-${side}`, 0.2, 8, x * 1.14, 0.81, 0.07, m.leather);
	}
	for (const x of [-0.43, 0.43]) {
		const stud = addSphere(scene, root, `${name}-pauldron-stud-${x}`, 0.13, 7, x, 1.61, 0.34, m.metal);
		stud.scaling.set(1.0, 0.75, 0.6);
	}

	// Head, layered hair and face marks remain legible when the camera is orbited.
	addCylinder(scene, root, `${name}-neck`, 0.16, 0.17, 0.19, 9, 0, 1.68, 0.02, m.skin);
	addSphere(scene, root, `${name}-head`, 0.72, 12, 0, 2.04, 0.02, m.skin);
	const hair = addSphere(scene, root, `${name}-hair-cap`, 0.81, 12, 0, 2.19, -0.01, m.hair);
	hair.scaling.set(1.1, 0.76, 1.0);
	const fringe = addSphere(scene, root, `${name}-hair-fringe`, 0.34, 9, 0, 2.25, 0.28, m.hairLight);
	fringe.scaling.set(1.72, 0.54, 0.7);
	for (const [index, x] of [-0.25, -0.08, 0.09, 0.26].entries()) {
		const lock = addCylinder(scene, root, `${name}-hair-lock-${index}`, 0.48 + (index % 2) * 0.12, 0.025, 0.18, 7, x, 1.99, -0.34 - (index % 2) * 0.035, index % 2 ? m.hair : m.hairLight);
		lock.rotation.z = x * 0.72;
	}
	const topKnot = addSphere(scene, root, `${name}-hair-knot`, 0.13, 8, -0.05, 2.54, -0.02, m.metal);
	topKnot.scaling.set(0.8, 1.3, 0.8);
	for (const [index, x] of [-0.15, 0.15].entries()) {
		addSphere(scene, root, `${name}-eye-${index}`, 0.09, 7, x, 2.04, 0.357, m.eye);
		addSphere(scene, root, `${name}-eye-spark-${index}`, 0.035, 6, x - 0.02, 2.07, 0.388, m.slimeGlint);
		addSphere(scene, root, `${name}-cheek-${index}`, 0.065, 7, x * 1.55, 1.97, 0.32, m.flowerPink);
	}

	// A custom cloth surface replaces the cone-shaped cape. Its inset colors are woven
	// into the same mesh: deep-blue panels, a gold hem and the house sigil.
	createHeroCape(scene, root, m, name);
	addSphere(scene, root, `${name}-cloak-clasp`, 0.17, 8, 0, 1.63, 0.34, m.metal);
	const claspGem = addSphere(scene, root, `${name}-cloak-gem`, 0.09, 8, 0, 1.63, 0.48, m.windmark);
	claspGem.scaling.set(0.85, 1.15, 0.6);

	// A proper diagonal scabbard and faceted long-sword replace the detached-looking blade.
	const scabbard = addCylinder(scene, root, `${name}-scabbard`, 0.86, 0.055, 0.09, 7, -0.33, 0.75, -0.12, m.leather);
	scabbard.rotation.z = 0.37;
	const sword = new TransformNode(`${name}-sword`, scene);
	sword.position.set(0.52, 1.02, 0.1);
	sword.rotation.z = -0.43;
	sword.parent = root;
	addCylinder(scene, sword, `${name}-sword-blade`, 1.05, 0.018, 0.13, 4, 0, 0.65, 0, m.armorLight);
	addCylinder(scene, sword, `${name}-sword-grip`, 0.3, 0.08, 0.08, 8, 0, -0.04, 0, m.leather);
	const guard = addCylinder(scene, sword, `${name}-sword-guard`, 0.08, 0.32, 0.32, 8, 0, 0.16, 0, m.metal);
	guard.rotation.z = Math.PI / 2;
	addSphere(scene, sword, `${name}-sword-pommel`, 0.11, 7, 0, -0.22, 0, m.metal);
	return root;
}

function createHeroCape(scene: Scene, root: TransformNode, m: Record<string, StandardMaterial>, name: string): void {
	const columns = 16;
	const rows = 18;
	const positions: number[] = [];
	const colors: number[] = [];
	const indices: number[] = [];
	for (let row = 0; row <= rows; row++) {
		const t = row / rows;
		for (let column = 0; column <= columns; column++) {
			const u = column / columns * 2 - 1;
			const width = 0.38 + 0.53 * t;
			const hemWave = (1 - Math.abs(u)) * 0.045 * Math.sin((u + 1) * Math.PI * 2.5);
			const x = u * width;
			const y = 1.58 - t * 1.22 + hemWave;
			const z = -0.35 - t * 0.12 - Math.sin((u + 1) * Math.PI * 3) * t * 0.025;
			positions.push(x, y, z);
			const gem = Math.abs(u) < Math.max(0, 0.095 - Math.abs(t - 0.52) * 0.55);
			const centerBand = Math.abs(u) < 0.14 && t > 0.16 && t < 0.9;
			const edgePanels = Math.abs(u) > 0.78 && t > 0.18 && t < 0.92;
			const hem = t > 0.94;
			const color = hem || gem ? [0.82, 0.65, 0.34] : centerBand || edgePanels ? [0.35, 0.49, 0.67] : [1, 1, 1];
			colors.push(color[0], color[1], color[2], 1);
		}
	}
	for (let row = 0; row < rows; row++) {
		for (let column = 0; column < columns; column++) {
			const a = row * (columns + 1) + column;
			const b = a + 1;
			const c = a + columns + 1;
			const d = c + 1;
			indices.push(a, c, b, b, c, d);
		}
	}
	const cape = MeshBuilder.CreateGround(`${name}-embroidered-cape`, { width: 1, height: 1, subdivisions: 1 }, scene);
	const data = new VertexData();
	data.positions = positions;
	data.indices = indices;
	data.colors = colors;
	const normals: number[] = [];
	VertexData.ComputeNormals(positions, indices, normals);
	data.normals = normals;
	data.applyToMesh(cape, false);
	cape.position.y = 0;
	cape.material = m.cloth;
	cape.useVertexColors = true;
	cape.hasVertexAlpha = false;
	cape.isPickable = false;
	cape.parent = root;
}

export function createSlime(
	scene: Scene,
	m: Record<string, StandardMaterial>,
	name: string,
): { root: TransformNode; body: Mesh; material: StandardMaterial } {
	const root = new TransformNode(name, scene);
	root.scaling.setAll(1.15);
	const masters = getPropMasters(scene, m);

	// Body contract: Mesh parented DIRECTLY to root, diameter ~1.4, rest pose equals the
	// scene's "idle" hop frame so the pose is correct before the first animateMonsterHop.
	const body = MeshBuilder.CreateSphere(`${name}-body`, { diameter: 1.42, segments: 20 }, scene);
	body.scaling.set(1.1, 0.8, 0.94);
	body.position.y = 0.52;
	const material = m.slime.clone(`${name}-mat`);
	body.material = material;
	body.parent = root;

	// subtle darker underbelly + puddle foot, child of body so it squashes/stretches with
	// every hop phase; the foot also spreads ~3 cm past the ground line like a resting puddle
	const belly = masters.belly.createInstance(`${name}-belly`);
	belly.position.set(0, -0.55, 0);
	belly.scaling.set(0.78, 0.33, 0.75);
	belly.parent = body;

	// face rides the body: big shiny eyes, one-sided glints, blush, crescent smile.
	// Positions are in body-local space (unit sphere radius 0.71); face looks toward -z,
	// the side the follow camera actually sees (camera looks +z from behind the hero).
	for (const [index, x] of [-0.22, 0.22].entries()) {
		const eye = masters.eye.createInstance(`${name}-eye-${index}`);
		eye.position.set(x, 0.15, -0.66);
		eye.parent = body;
		const glint = masters.glint.createInstance(`${name}-glint-${index}`);
		glint.position.set(x - 0.045, 0.21, -0.72);
		glint.parent = body;
		const blush = masters.blush.createInstance(`${name}-blush-${index}`);
		blush.position.set(x * 2.0, -0.02, -0.575);
		blush.parent = body;
	}
	const mouth = masters.mouth.createInstance(`${name}-mouth`);
	// The smile tube is authored directly on the body's front in local space.
	mouth.parent = body;

	return { root, body, material };
}

export function createRouteGuide(scene: Scene, m: Record<string, StandardMaterial>, name: string): TransformNode {
	const root = new TransformNode(`npc-${name}`, scene);
	// pose three-quarters toward the approaching player (default camera looks +z)
	root.rotation.y = 2.79;
	addGroundBlob(scene, m, `npc-${name}-ground-shadow`, root, 0.55);

	// boots peeking from under the traveller robe
	addBox(scene, root, `npc-${name}-boot-left`, 0.2, 0.14, 0.32, -0.17, 0.07, 0.42, m.leather);
	addBox(scene, root, `npc-${name}-boot-right`, 0.2, 0.14, 0.32, 0.17, 0.07, 0.42, m.leather);

	// baggy robe with dark hem and golden sash
	addCylinder(scene, root, `npc-${name}-robe`, 1.3, 0.56, 1.02, 9, 0, 0.78, 0, m.cloth);
	addCylinder(scene, root, `npc-${name}-hem`, 0.1, 0.98, 1.04, 9, 0, 0.16, 0, m.leather);
	addCylinder(scene, root, `npc-${name}-sash`, 0.17, 0.82, 0.82, 9, 0, 1.12, 0, m.leavesGold);
	const scarf = MeshBuilder.CreateTorus(`npc-${name}-scarf`, { diameter: 0.4, thickness: 0.09, tessellation: 12 }, scene);
	scarf.position.y = 1.7;
	scarf.material = m.clothBlue;
	scarf.parent = root;
	addSphere(scene, root, `npc-${name}-chest`, 0.56, 8, 0, 1.5, 0, m.cloth).scaling.set(1, 0.85, 0.9);

	// head with gentle face, hair and braid
	addSphere(scene, root, `npc-${name}-head`, 0.52, 9, 0, 1.93, 0.02, m.skin);
	for (const [index, x] of [-0.115, 0.115].entries()) {
		addSphere(scene, root, `npc-${name}-eye-${index}`, 0.08, 6, x, 1.95, 0.25, m.eye);
		addSphere(scene, root, `npc-${name}-cheek-${index}`, 0.06, 5, x * 1.65, 1.9, 0.22, m.flowerPink);
	}
	const hair = addSphere(scene, root, `npc-${name}-hair`, 0.58, 8, 0, 2.04, -0.05, m.hair);
	hair.scaling.set(1.02, 0.62, 1);
	const braid = addSphere(scene, root, `npc-${name}-braid`, 0.17, 6, 0, 1.86, -0.31, m.hair);
	braid.scaling.set(1, 1.6, 1);

	// wide-brim traveller hat, slightly jaunty
	const hat = new TransformNode(`npc-${name}-hat`, scene);
	hat.parent = root;
	hat.rotation.set(-0.05, 0, 0.08);
	addCylinder(scene, hat, `npc-${name}-hat-brim`, 0.05, 1.14, 1.14, 14, 0, 2.2, 0, m.leather);
	const band = MeshBuilder.CreateCylinder(`npc-${name}-hat-band`, { height: 0.08, diameterTop: 0.46, diameterBottom: 0.46, tessellation: 12 }, scene);
	band.position.y = 2.26;
	band.material = m.metal;
	band.parent = hat;
	addCylinder(scene, hat, `npc-${name}-hat-crown`, 0.32, 0.3, 0.44, 12, 0, 2.38, 0, m.leather);

	// satchel on the hip
	const satchel = addBox(scene, root, `npc-${name}-satchel`, 0.34, 0.4, 0.18, -0.42, 0.85, -0.06, m.leather);
	satchel.rotation.z = 0.12;

	// staff topped with a glowing cyan orb in a gold ring
	const staff = addCylinder(scene, root, `npc-${name}-staff`, 1.75, 0.05, 0.09, 6, 0.52, 0.87, 0.06, m.woodLight);
	staff.rotation.z = -0.07;
	addSphere(scene, root, `npc-${name}-staff-orb`, 0.24, 8, 0.58, 1.79, 0.06, m.windmark);
	const cage = MeshBuilder.CreateTorus(`npc-${name}-orb-cage`, { diameter: 0.3, thickness: 0.025, tessellation: 12 }, scene);
	cage.rotation.x = Math.PI / 2;
	cage.position.set(0.58, 1.79, 0.06);
	cage.material = m.metal;
	cage.parent = root;
	return root;
}

export function createWindmark(
	scene: Scene,
	m: Record<string, StandardMaterial>,
	id: string,
): { root: TransformNode; crystal: Mesh; ring: Mesh } {
	const root = new TransformNode(id, scene);
	const masters = getPropMasters(scene, m);

	// mossy standing-stone base (~0.9 m); the crystal rises out of its mossy crown
	const stone = addCylinder(scene, root, `${id}-stone`, 0.9, 0.55, 0.78, 5, 0, 0.45, 0, m.stone);
	stone.rotation.y = 0.4;
	const moss = addSphere(scene, root, `${id}-moss`, 0.74, 6, 0.02, 0.86, -0.02, m.moss);
	moss.scaling.set(1.02, 0.4, 0.92);
	const shard = addSphere(scene, root, `${id}-shard`, 0.16, 5, 0.26, 0.84, 0.14, m.windmark);
	shard.scaling.set(0.8, 1.7, 0.8);
	const pebbleA = masters.pebble.createInstance(`${id}-pebble-a`);
	pebbleA.position.set(0.36, 0.05, 0.12);
	pebbleA.rotation.y = 0.7;
	pebbleA.scaling.set(1.2, 0.55, 1);
	pebbleA.parent = root;
	const pebbleB = masters.pebble.createInstance(`${id}-pebble-b`);
	pebbleB.position.set(-0.34, 0.05, -0.14);
	pebbleB.rotation.y = 2.1;
	pebbleB.scaling.set(0.9, 0.5, 1.05);
	pebbleB.parent = root;

	// quest ring: scene swaps ring.material to flowerGold when the windmark activates
	const ring = MeshBuilder.CreateTorus(`${id}-ring`, { diameter: 1.25, thickness: 0.1, tessellation: 14 }, scene);
	ring.rotation.x = Math.PI / 2;
	ring.position.y = 0.07;
	ring.material = m.windmark;
	ring.parent = root;

	// floating crystal: scene bobs position.y around 1.05 and swaps its material to metal
	const crystal = MeshBuilder.CreateCylinder(`${id}-crystal`, { height: 1.35, diameterTop: 0.05, diameterBottom: 0.48, tessellation: 6 }, scene);
	crystal.position.y = 1.05;
	crystal.material = m.windmark;
	crystal.parent = root;
	const cap = MeshBuilder.CreateSphere(`${id}-light`, { diameter: 0.24, segments: 6 }, scene);
	cap.position.set(0, 0.78, 0);
	cap.material = m.flowerGold;
	cap.parent = crystal;
	return { root, crystal, ring };
}
