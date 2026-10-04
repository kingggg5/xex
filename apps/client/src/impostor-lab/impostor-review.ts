import { Engine } from "@babylonjs/core/Engines/engine";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Scene } from "@babylonjs/core/scene";
import { FreeCamera } from "@babylonjs/core/Cameras/freeCamera";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { ImageProcessingConfiguration } from "@babylonjs/core/Materials/imageProcessingConfiguration";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { InstancedMesh } from "@babylonjs/core/Meshes/instancedMesh";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import "@babylonjs/core/Meshes/instancedMesh";
import "@babylonjs/loaders/glTF";
import { configureAssetCodecs } from "../asset-codecs";
import { addMeadowSurface } from "../meadow-surface";
import { mergeStaticModel } from "../static-model.mjs";
import { createImpostorField, createImpostorLod, type ImpostorAtlasManifest, type ImpostorField, type ImpostorHandle } from "../impostors";
import manifestUrl from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees.impostors.json?url";
import albedo0Png from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_albedo_0.png?url";
import albedo1Png from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_albedo_1.png?url";
import normal0Png from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_normal_0.png?url";
import normal1Png from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_normal_1.png?url";
import albedo0Ktx from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_albedo_0.ktx2?url";
import albedo1Ktx from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_albedo_1.ktx2?url";
import normal0Ktx from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_normal_0.ktx2?url";
import normal1Ktx from "../assets/world/impostors/sunmeadow-trees-v2/sunmeadow_trees_normal_1.ktx2?url";
import treeUrl from "../assets/models/env_meadow_tree_v2.meshopt.glb?url";
import canopyV1Url from "../assets/world/leaf_canopy_albedo.png?url";
import canopyV2Url from "../assets/world/leaf_canopy_albedo_v2.png?url";
import barkUrl from "../assets/world/world_tree_bark_albedo.png?url";
import grassAlbedoUrl from "../assets/world/grass_ground_albedo_1024.png?url";
import grassNormalUrl from "../assets/world/grass_ground_normal_1024.png?url";

const FILES: Record<string, string> = {
	"sunmeadow_trees_albedo_0.png": albedo0Png, "sunmeadow_trees_albedo_1.png": albedo1Png,
	"sunmeadow_trees_normal_0.png": normal0Png, "sunmeadow_trees_normal_1.png": normal1Png,
	"sunmeadow_trees_albedo_0.ktx2": albedo0Ktx, "sunmeadow_trees_albedo_1.ktx2": albedo1Ktx,
	"sunmeadow_trees_normal_0.ktx2": normal0Ktx, "sunmeadow_trees_normal_1.ktx2": normal1Ktx,
};
const VARIANTS = ["A", "B", "C"] as const;
type Variant = typeof VARIANTS[number];
const EYE_HEIGHT = 6.6; // game camera height above the feet (radius 13 m, beta 1.18 rad, target +1.65 m)

interface Kit { trunk: Mesh; canopy: Mesh }

class ImpostorReview {
	readonly scene: Scene;
	readonly camera: FreeCamera;
	private kits = {} as Record<Variant, Kit>;
	leaf!: StandardMaterial;
	bark!: PBRMaterial;
	field!: ImpostorField;
	private real: InstancedMesh[] = [];
	private cards: ImpostorHandle[] = [];
	readonly lods: Array<{ dispose(): void }> = [];
	readonly instrumentation: SceneInstrumentation;

	constructor(readonly engine: AbstractEngine, readonly renderer: string) {
		this.scene = new Scene(engine);
		this.camera = new FreeCamera("review-camera", new Vector3(0, EYE_HEIGHT, -40), this.scene);
		this.camera.fov = 1.02;
		this.camera.minZ = 0.1;
		this.camera.maxZ = 1200;
		this.instrumentation = new SceneInstrumentation(this.scene);
		this.instrumentation.captureFrameTime = true;
	}

	async init(): Promise<void> {
		const scene = this.scene;
		await configureAssetCodecs();
		scene.imageProcessingConfiguration.toneMappingEnabled = true;
		scene.imageProcessingConfiguration.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
		scene.imageProcessingConfiguration.contrast = 1.04;
		scene.imageProcessingConfiguration.exposure = 1.0;
		scene.fogMode = Scene.FOGMODE_EXP2;
		scene.fogDensity = 0.0017;
		scene.fogColor = Color3.FromHexString("#cfe0d2");
		scene.clearColor = Color4.FromHexString("#a9c8e0ff");
		// environment.ts daytime values.
		const hemi = new HemisphericLight("env-sky-fill", new Vector3(0, 1, 0), scene);
		hemi.intensity = 0.62;
		hemi.diffuse = Color3.FromHexString("#bcd8f0");
		hemi.groundColor = Color3.FromHexString("#8a7a58");
		const sun = new DirectionalLight("env-sun", new Vector3(-0.55, -0.82, 0.35), scene);
		sun.intensity = 1.65;
		sun.diffuse = Color3.FromHexString("#fff1d6");
		sun.specular = Color3.FromHexString("#fff8ea");
		const ground = MeshBuilder.CreateGround("review-ground", { width: 900, height: 900 }, scene);
		const grass = new PBRMaterial("review-grass", scene);
		const albedo = new Texture(grassAlbedoUrl, scene);
		const normal = new Texture(grassNormalUrl, scene);
		for (const t of [albedo, normal]) t.uScale = t.vScale = 900 / 6;
		normal.level = 0.16;
		grass.albedoTexture = albedo;
		grass.bumpTexture = normal;
		grass.albedoColor = Color3.FromHexString("#e9f0dc");
		grass.metallic = 0;
		grass.roughness = 0.94;
		addMeadowSurface(grass);
		ground.material = grass;
		ground.isPickable = false;
		await this.loadTrees();
		const manifest = await (await fetch(manifestUrl)).json() as ImpostorAtlasManifest;
		this.field = createImpostorField(scene, manifest, file => FILES[file], { ktx2: new URLSearchParams(location.search).get("png") !== "1" });
	}

	/** Game-identical materials: environment.ts treeBarkMaterial (PBR) and createLeafCardMaterial (Standard). */
	private async loadTrees(): Promise<void> {
		const scene = this.scene;
		const loaded = await SceneLoader.ImportMeshAsync("", "", treeUrl, scene);
		this.bark = new PBRMaterial("env-shared-tree-bark", scene);
		const barkTexture = new Texture(barkUrl, scene, false, false);
		barkTexture.wrapU = barkTexture.wrapV = Texture.MIRROR_ADDRESSMODE;
		barkTexture.uScale = 2;
		barkTexture.vScale = 4;
		this.bark.albedoTexture = barkTexture;
		this.bark.metallic = 0;
		this.bark.roughness = 0.95;
		this.leaf = new StandardMaterial("env-field-leaf-cards", scene);
		// v2 = edge-bled RGB in transparent texels (no dark leaf fringes); ?leaf=v1 shows the current texture.
		const canopy = new Texture(new URLSearchParams(location.search).get("leaf") === "v1" ? canopyV1Url : canopyV2Url, scene, false, false);
		canopy.hasAlpha = true;
		canopy.wrapU = canopy.wrapV = Texture.CLAMP_ADDRESSMODE;
		this.leaf.diffuseTexture = canopy;
		this.leaf.diffuseColor = Color3.White();
		this.leaf.specularColor = Color3.Black();
		this.leaf.transparencyMode = StandardMaterial.MATERIAL_ALPHATEST;
		this.leaf.useAlphaFromDiffuseTexture = true;
		this.leaf.alphaCutOff = 0.42;
		this.leaf.backFaceCulling = false;
		this.leaf.twoSidedLighting = true;
		this.leaf.emissiveColor = new Color3(0.09, 0.12, 0.06);
		this.leaf.linkEmissiveWithDiffuse = true;
		for (const variant of VARIANTS) {
			const trunk = mergeStaticModel({ meshes: [loaded.meshes.find(m => m.name === `tree_${variant}_trunk`) as Mesh], transformNodes: [], animationGroups: [] }, `field-tree-trunk-${variant}`) as Mesh;
			const canopyMesh = mergeStaticModel({ meshes: [loaded.meshes.find(m => m.name === `tree_${variant}_canopy`) as Mesh], transformNodes: [], animationGroups: [] }, `field-tree-canopy-${variant}`) as Mesh;
			trunk.material = this.bark;
			canopyMesh.material = this.leaf;
			trunk.isVisible = canopyMesh.isVisible = false;
			trunk.isPickable = canopyMesh.isPickable = false;
			this.kits[variant] = { trunk, canopy: canopyMesh };
		}
		for (const mesh of loaded.meshes) if (!mesh.isDisposed() && mesh.getTotalVertices() === 0) mesh.dispose(false, false);
	}

	clear(): void {
		for (const l of this.lods) l.dispose();
		this.lods.length = 0;
		for (const r of this.real) r.dispose();
		this.real = [];
		for (const c of this.cards) this.field.remove(c);
		this.cards = [];
	}

	addReal(variant: Variant, x: number, z: number, yaw: number, scale = 1): InstancedMesh[] {
		const parts = [this.kits[variant].trunk, this.kits[variant].canopy].map((src, i) => {
			const inst = src.createInstance(`real-${variant}-${i}-${this.real.length}`);
			inst.position.set(x, 0, z);
			inst.rotation.y = yaw;
			inst.scaling.setAll(scale);
			inst.isPickable = false;
			return inst;
		});
		this.real.push(...parts);
		return parts;
	}

	addCard(variant: Variant, x: number, z: number, yaw: number, scale = 1): ImpostorHandle {
		const handle = this.field.add(`meadow_tree_${variant}`, x, 0, z, yaw, scale);
		this.cards.push(handle);
		return handle;
	}

	lookFrom(distance: number, azimuthDeg = 0, target = new Vector3(0, 3.5, 0)): void {
		const a = (azimuthDeg * Math.PI) / 180;
		this.camera.position.set(target.x - Math.sin(a) * distance, EYE_HEIGHT, target.z - Math.cos(a) * distance);
		this.camera.setTarget(target);
	}

	async frame(): Promise<ImageData> {
		const canvas = this.engine.getRenderingCanvas()!;
		this.engine.beginFrame();
		this.scene.render();
		this.engine.endFrame();
		const pixels = await this.engine.readPixels(0, 0, canvas.width, canvas.height, true, true);
		const data = new Uint8ClampedArray((pixels.buffer as ArrayBuffer)).slice(0, canvas.width * canvas.height * 4);
		const gpu = (navigator as Navigator & { gpu?: { getPreferredCanvasFormat(): string } }).gpu;
		if (this.engine.isWebGPU && gpu?.getPreferredCanvasFormat() === "bgra8unorm") {
			for (let k = 0; k < data.length; k += 4) { const r = data[k]; data[k] = data[k + 2]; data[k + 2] = r; }
		}
		return new ImageData(data, canvas.width, canvas.height);
	}

	/** Average frame time over n frames, GPU-synchronised by a 1-pixel read-back at the end. */
	async frameTime(n = 90): Promise<number> {
		for (let i = 0; i < 10; i++) { this.engine.beginFrame(); this.scene.render(); this.engine.endFrame(); }
		await this.engine.readPixels(0, 0, 1, 1, true, true);
		const start = performance.now();
		for (let i = 0; i < n; i++) { this.engine.beginFrame(); this.scene.render(); this.engine.endFrame(); }
		await this.engine.readPixels(0, 0, 1, 1, true, true);
		return (performance.now() - start) / n;
	}

	async sheet(title: string, frames: Array<{ label: string; setup: () => void | Promise<void> }>): Promise<string> {
		const cellW = 640, cellH = 360, label = 22, header = 34;
		const sheet = document.createElement("canvas");
		sheet.width = cellW * 4;
		sheet.height = header + (cellH + label) * Math.ceil(frames.length / 4);
		const g = sheet.getContext("2d")!;
		g.fillStyle = "#11161c";
		g.fillRect(0, 0, sheet.width, sheet.height);
		const tmp = document.createElement("canvas");
		const canvas = this.engine.getRenderingCanvas()!;
		tmp.width = canvas.width;
		tmp.height = canvas.height;
		const tg = tmp.getContext("2d")!;
		for (let i = 0; i < frames.length; i++) {
			await frames[i].setup();
			await this.field.whenReady();
			await this.scene.whenReadyAsync();
			for (let k = 0; k < 3; k++) { this.engine.beginFrame(); this.scene.render(); this.engine.endFrame(); }
			const image = await this.frame();
			tg.putImageData(image, 0, 0);
			const x = (i % 4) * cellW, y = header + Math.floor(i / 4) * (cellH + label);
			g.save();
			if (!this.engine.isWebGPU) { g.translate(0, y + label + cellH); g.scale(1, -1); g.drawImage(tmp, x, 0, cellW, cellH); } else g.drawImage(tmp, x, y + label, cellW, cellH);
			g.restore();
			g.fillStyle = "#d6e2ea";
			g.font = "13px Consolas, monospace";
			g.fillText(frames[i].label, x + 8, y + 15);
		}
		g.fillStyle = "#f2c76e";
		g.font = "bold 18px Consolas, monospace";
		g.fillText(title, 10, 23);
		g.fillStyle = "#c9d4dc";
		g.font = "13px Consolas, monospace";
		g.fillText(`Xexoria impostor review · ${this.renderer} · ${canvas.width}x${canvas.height} · game day lighting · BABYLON CAPTURE`, 1200, 23);
		return sheet.toDataURL("image/png");
	}
}

async function createEngine(canvas: HTMLCanvasElement): Promise<{ engine: AbstractEngine; renderer: string }> {
	const wanted = new URLSearchParams(location.search).get("renderer") ?? "webgpu";
	if (wanted === "webgpu" && "gpu" in navigator) {
		try {
			const { WebGPUEngine } = await import("@babylonjs/core/Engines/webgpuEngine");
			const engine = new WebGPUEngine(canvas, { antialias: true, adaptToDeviceRatio: false });
			await engine.initAsync();
			return { engine, renderer: "WebGPU" };
		} catch (error) {
			console.warn("WebGPU unavailable, falling back to WebGL2", error);
		}
	}
	return { engine: new Engine(canvas, true, { stencil: true }, false), renderer: "WebGL2" };
}

async function main(): Promise<void> {
	const canvas = document.getElementById("review") as HTMLCanvasElement;
	const { engine, renderer } = await createEngine(canvas);
	const lab = new ImpostorReview(engine, renderer);
	await lab.init();
	const yaw = 0.6;
	const api = {
		renderer,
		/** Real (left) vs impostor (right), same variant and yaw, at 20/40/80/120 m. */
		async distances() {
			const frames = [];
			for (const variant of ["A", "C"] as const) {
				for (const d of [20, 40, 80, 120]) {
					frames.push({
						label: `tree ${variant} · D=${d} m · left REAL mesh · right IMPOSTOR card`,
						setup: () => { lab.clear(); const s = 5.5; lab.addReal(variant, -s, 0, yaw); lab.addCard(variant, s, 0, yaw); lab.lookFrom(d); },
					});
				}
			}
			return lab.sheet("impostor_distance_ladder", frames);
		},
		/** Orbit across a 45-degree gap between baked views at 30 m: blending must not pop. */
		async orbit() {
			const frames = [];
			for (let k = 0; k < 8; k++) {
				const az = (k / 7) * 45;
				frames.push({
					label: `tree A · D=30 m · camera azimuth +${az.toFixed(1)}° · left REAL · right IMPOSTOR`,
					setup: () => { lab.clear(); lab.addReal("A", -5.5, 0, 0); lab.addCard("A", 5.5, 0, 0); lab.lookFrom(30, az); },
				});
			}
			return lab.sheet("impostor_orbit_sweep", frames);
		},
		/** 400 trees in a 60-200 m ring: real meshes vs impostor cards, metrics per frame. */
		async forest() {
			const spots: Array<[Variant, number, number, number, number]> = [];
			for (let i = 0; i < 400; i++) {
				const a = (i / 400) * Math.PI * 2 * 7.3 + Math.sin(i * 12.9898) * 0.4;
				const r = 60 + ((i * 37) % 140);
				spots.push([VARIANTS[i % 3], Math.sin(a) * r, Math.cos(a) * r, (i * 1.3) % (Math.PI * 2), 0.85 + ((i * 17) % 40) / 100]);
			}
			const results: Record<string, unknown> = {};
			const frames = [];
			for (const mode of ["real", "impostor"] as const) {
				frames.push({
					label: `${mode === "real" ? "REAL meshes" : "IMPOSTOR cards"} · 400 trees, 60-200 m ring · eye 6.6 m`,
					setup: async () => {
						lab.clear();
						for (const [v, x, z, ya, sc] of spots) mode === "real" ? lab.addReal(v, x, z, ya, sc) : lab.addCard(v, x, z, ya, sc);
						lab.camera.position.set(0, EYE_HEIGHT, 0);
						lab.camera.setTarget(new Vector3(0, 4, 80));
						await lab.field.whenReady();
						await lab.scene.whenReadyAsync();
						const ms = await lab.frameTime(90);
						lab.engine.beginFrame(); lab.scene.render(); lab.engine.endFrame();
						results[mode] = { avgFrameMs: +ms.toFixed(2), drawCalls: lab.instrumentation.drawCallsCounter.current, activeIndices: lab.scene.getActiveIndices(), activeMeshes: lab.scene.getActiveMeshes().length };
					},
				});
			}
			const sheet = await lab.sheet("impostor_forest_stress", frames);
			return { sheet, results };
		},
		/** Dithered cross-fade with the real mesh as the camera walks through the swap band (swap 60 m, band 10 m). */
		async crossfade() {
			const frames = [];
			for (const d of [50, 54, 57, 59, 61, 63, 66, 70]) {
				frames.push({
					label: `swap 60 m ±5 · D=${d} m · single tree C (real ↔ card)`,
					setup: () => {
						lab.clear();
						const parts = lab.addReal("C", 0, 0, yaw);
						const handle = lab.addCard("C", 0, 0, yaw);
						const lod = createImpostorLod(lab.scene, lab.field, [{ parts, handle, position: new Vector3(0, 4.3, 0) }], { swap: 60, band: 10, materials: [lab.bark, lab.leaf] });
						lab.lods.push(lod);
						lab.lookFrom(d);
						lod.update();
					},
				});
			}
			return lab.sheet("impostor_crossfade", frames);
		},
	};
	(window as unknown as { impostorLab: typeof api }).impostorLab = api;
	(window as unknown as { impostorLabDebug: ImpostorReview }).impostorLabDebug = lab;
	document.body.dataset.ready = "1";
	document.getElementById("status")!.textContent = `${renderer} · ready`;
	engine.runRenderLoop(() => lab.scene.render());
}

void main();
