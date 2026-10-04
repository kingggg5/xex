import { Engine } from "@babylonjs/core/Engines/engine";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Scene } from "@babylonjs/core/scene";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { GlowLayer } from "@babylonjs/core/Layers/glowLayer";
import { ImageProcessingConfiguration } from "@babylonjs/core/Materials/imageProcessingConfiguration";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import type { AnimationGroup } from "@babylonjs/core/Animations/animationGroup";
import "@babylonjs/core/Particles/particleSystemComponent";
import "@babylonjs/core/Layers/effectLayerSceneComponent";
import "@babylonjs/loaders/glTF";
import { configureAssetCodecs } from "../asset-codecs";
import { createMaterials, createSlime } from "../actors";
import { addMeadowSurface } from "../meadow-surface";
import { mergeStaticModel } from "../static-model.mjs";
import { LightPool, loadVfxKit, type VfxKit } from "./vfx-kit";
import { VfxSurfacePlugin } from "./vfx-material";
import { SKILLS, type SkillInstance, type VfxContext, type VfxTarget } from "./vfx-skills";
import warriorUrl from "../assets/characters/quaternius-warrior.meshopt-etc1s.glb?url";
import grassAlbedoUrl from "../assets/world/grass_ground_albedo_1024.png?url";
import grassNormalUrl from "../assets/world/grass_ground_normal_1024.png?url";
import treeUrl from "../assets/models/env_meadow_tree_v2.meshopt.glb?url";
import canopyUrl from "../assets/world/leaf_canopy_albedo.png?url";
import barkUrl from "../assets/world/world_tree_bark_albedo.png?url";

type TimeOfDay = "night" | "day";

/** Capture plans: 8 frames on anticipation, impact, peak, sustain, collapse/dissipation, aftermath and end. */
export const CAPTURE_TIMES: Record<string, number[]> = {
	xs_bladeward_nova: [0.06, 0.13, 0.19, 0.26, 0.42, 0.78, 1.15, 2.2],
	xs_gale_palm: [0.1, 0.2, 0.36, 0.58, 0.78, 0.92, 1.25, 2.0],
	xs_void_rift: [0.3, 0.62, 0.95, 1.27, 2.0, 2.92, 3.12, 3.9],
};
const CAMERAS: Record<string, { target: [number, number, number]; alpha: number; beta: number; radius: number }> = {
	xs_bladeward_nova: { target: [0, 0.8, 0.3], alpha: -Math.PI / 2 - 0.6, beta: 1.0, radius: 11 },
	xs_gale_palm: { target: [0.3, 0.9, 4.8], alpha: -Math.PI + 0.42, beta: 1.08, radius: 12.5 },
	xs_void_rift: { target: [0.3, 0.4, 7.2], alpha: -Math.PI / 2 - 0.85, beta: 1.0, radius: 11.5 },
};
const TARGET_LAYOUT: Record<string, Array<[number, number]>> = {
	xs_bladeward_nova: [[2.2, 2.4], [-2.6, 1.6], [0.6, -3.0], [5.6, 4.0]],
	xs_gale_palm: [[0.3, 9.0], [2.6, 10.5], [-3.5, 6.0]],
	xs_void_rift: [[1.2, 8.4], [-2.4, 7.0], [2.6, 10.6], [6.4, 4.5]],
};
const ANIMATION: Record<string, string> = { xs_bladeward_nova: "Sword_Attack2", xs_gale_palm: "Punch", xs_void_rift: "Sword_Attack" };

class VfxLab {
	readonly scene: Scene;
	private camera!: ArcRotateCamera;
	private hemi!: HemisphericLight;
	private sun!: DirectionalLight;
	private kit!: VfxKit;
	private lights!: LightPool;
	private targets: VfxTarget[] = [];
	private animations: AnimationGroup[] = [];
	private skill: SkillInstance | null = null;
	private skillId = "xs_bladeward_nova";
	private time = 0;
	private shakeAmp = 0;
	private shakeLeft = 0;
	private shakeTotal = 1;
	private readonly cameraTarget = new Vector3();
	lastCpuMs = 0;
	tod: TimeOfDay = "night";

	constructor(readonly engine: AbstractEngine) {
		this.scene = new Scene(engine);
	}

	async init(): Promise<void> {
		const scene = this.scene;
		await configureAssetCodecs();
		scene.imageProcessingConfiguration.toneMappingEnabled = true;
		scene.imageProcessingConfiguration.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
		scene.imageProcessingConfiguration.contrast = 1.04;
		scene.fogMode = Scene.FOGMODE_EXP2;
		this.camera = new ArcRotateCamera("lab-camera", -Math.PI / 2, 1.18, 13, Vector3.Zero(), scene);
		this.camera.fov = 1.02;
		this.camera.minZ = 0.1;
		this.camera.maxZ = 600;
		this.camera.attachControl(this.engine.getRenderingCanvas()!, true);
		this.hemi = new HemisphericLight("lab-hemi", new Vector3(0, 1, 0), scene);
		this.hemi.groundColor = Color3.FromHexString("#8a7a58");
		this.sun = new DirectionalLight("lab-sun", new Vector3(-0.55, -0.82, 0.35), scene);
		this.sun.specular = Color3.FromHexString("#fff8ea");
		const glow = new GlowLayer("env-glow", scene, { mainTextureSamples: 1, blurKernelSize: 32 });
		glow.intensity = 0.55;
		this.lights = new LightPool(scene, 2);
		this.buildGround();
		await Promise.all([this.loadCaster(), this.loadTrees(), loadVfxKit(scene).then(kit => { this.kit = kit; })]);
		this.setTimeOfDay("night");
		this.placeTargets(this.skillId);
		this.frame(this.skillId);
		await scene.whenReadyAsync();
	}

	private buildGround(): void {
		const scene = this.scene;
		const ground = MeshBuilder.CreateGround("lab-ground", { width: 140, height: 140, subdivisions: 2 }, scene);
		const material = new PBRMaterial("lab-grass", scene);
		const albedo = new Texture(grassAlbedoUrl, scene);
		const normal = new Texture(grassNormalUrl, scene);
		for (const t of [albedo, normal]) { t.uScale = t.vScale = 140 / 6; }
		normal.level = 0.16;
		material.albedoTexture = albedo;
		material.bumpTexture = normal;
		material.albedoColor = Color3.FromHexString("#e9f0dc");
		material.metallic = 0;
		material.roughness = 0.94;
		addMeadowSurface(material);
		ground.material = material;
		ground.receiveShadows = false;
		ground.isPickable = false;
	}

	private async loadCaster(): Promise<void> {
		const loaded = await SceneLoader.ImportMeshAsync("", "", warriorUrl, this.scene);
		// Game parity (scene.ts): imported roots under a 0.9-scaled local root.
		const local = new TransformNode("lab-hero-local", this.scene);
		for (const node of [...loaded.transformNodes.filter(n => !n.parent), ...loaded.meshes.filter(m => !m.parent)]) node.parent = local;
		local.scaling.setAll(0.9);
		this.animations = loaded.animationGroups;
		for (const group of this.animations) group.stop();
		this.animations.find(g => g.name === "Idle")?.start(true);
	}

	private async loadTrees(): Promise<void> {
		const scene = this.scene;
		const loaded = await SceneLoader.ImportMeshAsync("", "", treeUrl, scene);
		const bark = new StandardMaterial("lab-bark", scene);
		bark.diffuseTexture = new Texture(barkUrl, scene);
		bark.specularColor = Color3.Black();
		const leaf = new StandardMaterial("lab-leaf-cards", scene);
		const leafTex = new Texture(canopyUrl, scene, false, false);
		leafTex.hasAlpha = true;
		leaf.diffuseTexture = leafTex;
		leaf.useAlphaFromDiffuseTexture = true;
		leaf.transparencyMode = StandardMaterial.MATERIAL_ALPHATEST;
		leaf.alphaCutOff = 0.42;
		leaf.backFaceCulling = false;
		leaf.twoSidedLighting = true;
		leaf.specularColor = Color3.Black();
		leaf.emissiveColor = new Color3(0.09, 0.12, 0.06);
		leaf.linkEmissiveWithDiffuse = true;
		const kits = ["A", "B", "C"].map(v => {
			const trunk = loaded.meshes.find(m => m.name === `tree_${v}_trunk`) as Mesh;
			const canopy = loaded.meshes.find(m => m.name === `tree_${v}_canopy`) as Mesh;
			const t = mergeStaticModel({ meshes: [trunk], transformNodes: [], animationGroups: [] }, `lab-trunk-${v}`) as Mesh;
			const c = mergeStaticModel({ meshes: [canopy], transformNodes: [], animationGroups: [] }, `lab-canopy-${v}`) as Mesh;
			t.material = bark; c.material = leaf; t.isVisible = c.isVisible = false;
			return { t, c };
		});
		const spots: Array<[number, number, number]> = [[-11, 14, 1.0], [12, 17, 1.15], [-16, 2, 0.9], [15, -1, 1.05], [-7, -12, 1.1], [9, -13, 0.95], [-18, 22, 1.2], [19, 26, 1.0], [2, 24, 1.1]];
		spots.forEach(([x, z, s], i) => {
			const k = kits[i % 3];
			for (const [src, tag] of [[k.t, "t"], [k.c, "c"]] as const) {
				const inst = src.createInstance(`lab-tree-${tag}-${i}`);
				inst.position.set(x, 0, z);
				inst.scaling.setAll(s);
				inst.rotation.y = i * 1.3;
				inst.isPickable = false;
			}
		});
		for (const mesh of loaded.meshes) if (!mesh.isDisposed() && mesh.getTotalVertices() === 0) mesh.dispose(false, false);
	}

	setTimeOfDay(tod: TimeOfDay): void {
		this.tod = tod;
		const scene = this.scene;
		const night = tod === "night";
		this.hemi.intensity = night ? 0.38 : 0.62;
		this.hemi.diffuse = Color3.FromHexString(night ? "#8fb0e8" : "#bcd8f0");
		this.hemi.groundColor = Color3.FromHexString(night ? "#2a2b38" : "#8a7a58");
		this.sun.intensity = night ? 0.42 : 1.65;
		this.sun.diffuse = night ? new Color3(0.45, 0.59, 0.91) : Color3.FromHexString("#fff1d6");
		this.sun.direction = night ? new Vector3(-0.35, -0.8, 0.45).normalize() : new Vector3(-0.55, -0.82, 0.35);
		scene.fogColor = Color3.FromHexString(night ? "#182a43" : "#cfe0d2");
		scene.fogDensity = night ? 0.012 : 0.0017;
		scene.clearColor = night ? Color4.FromHexString("#0b1626ff") : Color4.FromHexString("#a9c8e0ff");
		scene.imageProcessingConfiguration.exposure = night ? 1.22 : 1.0;
		VfxSurfacePlugin.exposure = night ? 1 : 0.78;
	}

	private placeTargets(skillId: string): void {
		for (const target of this.targets) target.root.dispose(false, true);
		const materials = createMaterials(this.scene);
		this.targets = TARGET_LAYOUT[skillId].map(([x, z], i) => {
			const slime = createSlime(this.scene, materials, `lab-slime-${i}`);
			slime.root.position.set(x, 0, z);
			slime.root.rotation.y = Math.atan2(-x, -z);
			return { root: slime.root, material: slime.material, home: slime.root.position.clone(), baseEmissive: slime.material.emissiveColor.clone() };
		});
	}

	private frame(skillId: string): void {
		const c = CAMERAS[skillId];
		this.cameraTarget.set(...c.target);
		this.camera.target.copyFrom(this.cameraTarget);
		this.camera.alpha = c.alpha;
		this.camera.beta = c.beta;
		this.camera.radius = c.radius;
	}

	private context(): VfxContext {
		return {
			scene: this.scene, kit: this.kit, lights: this.lights, targets: this.targets,
			shake: (amplitude, seconds) => { this.shakeAmp = amplitude; this.shakeLeft = this.shakeTotal = seconds; },
			eye: () => this.camera.position,
		};
	}

	cast(skillId: string, keepCamera = false): void {
		this.skill?.dispose();
		if (skillId !== this.skillId) this.placeTargets(skillId);
		this.skillId = skillId;
		if (!keepCamera) this.frame(skillId);
		for (const target of this.targets) target.root.position.copyFrom(target.home);
		this.time = 0;
		this.skill = SKILLS[skillId](this.context(), Vector3.Zero(), 0);
		for (const group of this.animations) group.stop();
		const anim = this.animations.find(g => g.name === ANIMATION[skillId]);
		const idle = this.animations.find(g => g.name === "Idle");
		if (anim) {
			anim.start(false, 1.15);
			anim.onAnimationGroupEndObservable.addOnce(() => idle?.start(true));
		}
	}

	/** Compile every VFX material/particle effect of the current skill before its clock starts. */
	async warm(): Promise<void> {
		for (const mesh of this.scene.meshes) {
			const material = mesh.material;
			if (!(mesh instanceof Mesh) || !material?.pluginManager?.getPlugin("VfxSurface")) continue;
			await material.forceCompilationAsync(mesh, { useInstances: mesh.instances.length > 0 });
		}
		for (let i = 0; i < 400 && !this.scene.particleSystems.every(system => system.isReady()); i++) {
			await new Promise(resolve => setTimeout(resolve, 16));
		}
		await this.scene.whenReadyAsync();
	}

	/** Advance the skill clock; returns VFX update CPU ms. */
	step(dt: number): void {
		const started = performance.now();
		if (this.skill) {
			this.time += dt;
			this.skill.update(this.time);
			if (this.time > this.skill.duration + 0.5) { this.skill.dispose(); this.skill = null; }
		}
		this.lastCpuMs = performance.now() - started;
		if (this.shakeLeft > 0) {
			this.shakeLeft = Math.max(0, this.shakeLeft - dt);
			const k = this.shakeAmp * (this.shakeLeft / this.shakeTotal);
			const seed = this.time * 97;
			this.camera.target.set(this.cameraTarget.x + Math.sin(seed * 1.7) * k, this.cameraTarget.y + Math.sin(seed * 2.3) * k * 0.6, this.cameraTarget.z + Math.cos(seed * 1.3) * k);
		} else {
			this.camera.target.copyFrom(this.cameraTarget);
		}
	}

	stats(): { layers: number; dc: number; pt: number } {
		const layers = this.skill?.layers() ?? [];
		const dc = layers.reduce((n, l) => n + l.drawCalls(), 0);
		return { layers: layers.filter(l => l.drawCalls() > 0).length, dc, pt: layers.reduce((n, l) => n + l.particles(), 0) };
	}

	get skillTime(): number { return this.time; }
	get activeSkill(): SkillInstance | null { return this.skill; }

	/** Deterministic contact sheet in the owner's reference format (8 frames, 4 x 2). */
	async captureSheet(skillId: string, tod: TimeOfDay, renderer: string): Promise<string> {
		const canvas = this.engine.getRenderingCanvas()!;
		this.setTimeOfDay(tod);
		this.scene.useConstantAnimationDeltaTime = true;
		const times = CAPTURE_TIMES[skillId];
		const cellW = 640, cellH = 360, label = 22, header = 34;
		const sheet = document.createElement("canvas");
		sheet.width = cellW * 4;
		sheet.height = header + (cellH + label) * 2;
		const g = sheet.getContext("2d")!;
		g.fillStyle = "#11161c";
		g.fillRect(0, 0, sheet.width, sheet.height);
		this.cast(skillId);
		await this.warm();
		let frame = 0;
		const dt = 1 / 60;
		const cpu: number[] = [];
		const frameCanvas = document.createElement("canvas");
		frameCanvas.width = canvas.width;
		frameCanvas.height = canvas.height;
		const fg = frameCanvas.getContext("2d")!;
		for (let i = 0; i < times.length; i++) {
			let pixels: Promise<ArrayBufferView> | null = null;
			while (this.time + dt / 2 < times[i]) {
				this.step(dt);
				cpu.push(this.lastCpuMs);
				// Proper engine frames: WebGPU must acquire a fresh swap-chain texture every frame.
				this.engine.beginFrame();
				this.scene.render();
				this.engine.endFrame();
				frame++;
				if (!(this.time + dt / 2 < times[i])) pixels = this.engine.readPixels(0, 0, canvas.width, canvas.height, true, true);
			}
			const s = this.stats();
			const x = (i % 4) * cellW, y = header + Math.floor(i / 4) * (cellH + label);
			if (pixels) {
				const data = new Uint8ClampedArray((await pixels).buffer as ArrayBuffer).slice(0, canvas.width * canvas.height * 4);
				// WebGPU swap chains on Windows are bgra8unorm: swap back to RGBA.
				const gpu = (navigator as Navigator & { gpu?: { getPreferredCanvasFormat(): string } }).gpu;
				if (this.engine.isWebGPU && gpu?.getPreferredCanvasFormat() === "bgra8unorm") {
					for (let k = 0; k < data.length; k += 4) { const r = data[k]; data[k] = data[k + 2]; data[k + 2] = r; }
				}
				const image = new ImageData(data, canvas.width, canvas.height);
				fg.putImageData(image, 0, 0);
				// GL framebuffers read bottom-up; WebGPU reads top-down.
				g.save();
				if (!this.engine.isWebGPU) { g.translate(0, y + label + cellH); g.scale(1, -1); g.drawImage(frameCanvas, x, 0, cellW, cellH); }
				else g.drawImage(frameCanvas, x, y + label, cellW, cellH);
				g.restore();
			}
			const recent = cpu.slice(-6);
			const cpuMs = recent.reduce((a, b) => a + b, 0) / Math.max(1, recent.length);
			g.fillStyle = "#d6e2ea";
			g.font = "13px Consolas, monospace";
			g.fillText(`t=${times[i].toFixed(2)}s   vfx ${s.dc} dc   ${s.pt} pt   ${s.layers} layers   cpu ${cpuMs.toFixed(2)}ms`, x + 8, y + 15);
		}
		g.fillStyle = "#f2c76e";
		g.font = "bold 18px Consolas, monospace";
		g.fillText(`${skillId} · ${tod}`, 10, 23);
		g.fillStyle = "#c9d4dc";
		g.font = "13px Consolas, monospace";
		g.fillText(`Xexoria VFX lab · ${renderer} · ${canvas.width}x${canvas.height} · ${this.skill?.contract ?? ""} · Blender kit v1 · BABYLON CAPTURE`, 330, 23);
		this.scene.useConstantAnimationDeltaTime = false;
		void frame;
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
	const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: true }, false);
	return { engine, renderer: "WebGL2" };
}

async function main(): Promise<void> {
	const canvas = document.getElementById("lab") as HTMLCanvasElement;
	const { engine, renderer } = await createEngine(canvas);
	const lab = new VfxLab(engine);
	const status = document.getElementById("status")!;
	status.textContent = `${renderer} · loading kit…`;
	await lab.init();
	status.textContent = `${renderer} · ready`;
	let last = performance.now();
	let paused = false;
	engine.runRenderLoop(() => {
		if (paused) return;
		const now = performance.now();
		lab.step(Math.min(0.05, (now - last) / 1000));
		last = now;
		lab.scene.render();
		const s = lab.stats();
		status.textContent = `${renderer} · ${lab.tod} · t=${lab.skillTime.toFixed(2)}s · vfx ${s.dc} dc · ${s.pt} pt · cpu ${lab.lastCpuMs.toFixed(2)}ms · ${engine.getFps().toFixed(0)} fps`;
	});
	window.addEventListener("resize", () => engine.resize());
	for (const button of document.querySelectorAll<HTMLButtonElement>("[data-skill]")) {
		button.addEventListener("click", () => lab.cast(button.dataset.skill!));
	}
	document.getElementById("tod")!.addEventListener("click", () => lab.setTimeOfDay(lab.tod === "night" ? "day" : "night"));
	(window as unknown as { vfxLab: unknown }).vfxLab = {
		renderer,
		async capture(skillId: string, tod: TimeOfDay) {
			paused = true;
			try { return await lab.captureSheet(skillId, tod, renderer); } finally { paused = false; last = performance.now(); }
		},
	};
	(window as unknown as { vfxLabDebug: VfxLab }).vfxLabDebug = lab;
	document.body.dataset.ready = "1";
}

void main();
