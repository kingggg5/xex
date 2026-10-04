import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3, Vector4 } from "@babylonjs/core/Maths/math.vector";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { ParticleSystem } from "@babylonjs/core/Particles/particleSystem";
import { PointLight } from "@babylonjs/core/Lights/pointLight";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import "@babylonjs/core/Meshes/instancedMesh";
import "@babylonjs/loaders/glTF";
import type { Scene } from "@babylonjs/core/scene";
import { mergeStaticModel } from "../static-model.mjs";
import { createVfxMaterial, VFX_INSTANCE_KIND, type VfxSurfaceOptions, type VfxSurfacePlugin } from "./vfx-material";

import runeOuterUrl from "../assets/vfx/kit-v1/vfx_rune_circle_outer.png?url";
import runeInnerUrl from "../assets/vfx/kit-v1/vfx_rune_circle_inner.png?url";
import runeBladeUrl from "../assets/vfx/kit-v1/vfx_rune_ring_blade.png?url";
import swirlUrl from "../assets/vfx/kit-v1/vfx_swirl_arms.png?url";
import shockUrl from "../assets/vfx/kit-v1/vfx_shock_ring.png?url";
import starUrl from "../assets/vfx/kit-v1/vfx_impact_star.png?url";
import cracksUrl from "../assets/vfx/kit-v1/vfx_ground_cracks.png?url";
import scorchUrl from "../assets/vfx/kit-v1/vfx_scorch.png?url";
import streakUrl from "../assets/vfx/kit-v1/vfx_streak.png?url";
import palmUrl from "../assets/vfx/kit-v1/vfx_palm_sigil.png?url";
import noiseUrl from "../assets/vfx/kit-v1/vfx_noise_erosion.png?url";
import discUrl from "../assets/vfx/kit-v1/vfx_soft_disc.png?url";
import lightningUrl from "../assets/vfx/kit-v1/vfx_fb_lightning.png?url";
import impactUrl from "../assets/vfx/kit-v1/vfx_fb_impact.png?url";
import swirlSheetUrl from "../assets/vfx/kit-v1/vfx_fb_swirl.png?url";
import shardsUrl from "../assets/vfx/kit-v1/vfx_shards.png?url";
import dustUrl from "../assets/vfx/kit-v1/vfx_fb_dust.png?url";
import bladeUrl from "../assets/vfx/kit-v1/vfx_spectral_blade.glb?url";
import funnelUrl from "../assets/vfx/kit-v1/vfx_funnel.glb?url";
import coneUrl from "../assets/vfx/kit-v1/vfx_cone_burst.glb?url";
import ringWallUrl from "../assets/vfx/kit-v1/vfx_ring_wall.glb?url";

const TEXTURES = {
	runeOuter: runeOuterUrl, runeInner: runeInnerUrl, runeBlade: runeBladeUrl, swirl: swirlUrl, shock: shockUrl,
	star: starUrl, cracks: cracksUrl, scorch: scorchUrl, streak: streakUrl, palm: palmUrl, noise: noiseUrl, disc: discUrl,
	lightning: lightningUrl, impact: impactUrl, swirlSheet: swirlSheetUrl, shards: shardsUrl, dust: dustUrl,
} as const;
export type KitTexture = keyof typeof TEXTURES;

/** Palettes from docs/reviews/2026-10-02-vfx-sample-set-v1.md (sRGB hex: core, mid, edge). */
export const PALETTE = {
	blade: { core: "#F4FBFF", mid: "#7FD3FF", edge: "#2B6CFF", dark: "#0E1F4D" },
	gale: { core: "#F2FFF9", mid: "#5FF2C8", edge: "#13A88A", dark: "#0B3D3A" },
	void: { core: "#FFF0FF", mid: "#B07CFF", edge: "#5A1FD1", dark: "#12052B" },
	rim: { core: "#E8FFFB", mid: "#5FF2D8", edge: "#0F6F6A", dark: "#06201F" },
} as const;
export type PaletteName = keyof typeof PALETTE;

export interface VfxKit {
	readonly scene: Scene;
	readonly tex: Record<KitTexture, Texture>;
	readonly blade: Mesh;
	readonly funnel: Mesh;
	readonly cone: Mesh;
	readonly ringWall: Mesh;
	dispose(): void;
}

export async function loadVfxKit(scene: Scene): Promise<VfxKit> {
	const tex = {} as Record<KitTexture, Texture>;
	for (const [key, url] of Object.entries(TEXTURES) as Array<[KitTexture, string]>) {
		const texture = new Texture(url, scene, false, true, Texture.TRILINEAR_SAMPLINGMODE);
		texture.hasAlpha = true;
		texture.wrapU = texture.wrapV = key === "noise" || key === "streak" ? Texture.WRAP_ADDRESSMODE : Texture.CLAMP_ADDRESSMODE;
		texture.anisotropicFilteringLevel = 4;
		tex[key] = texture;
	}
	const load = async (url: string, name: string) => {
		const loaded = await SceneLoader.ImportMeshAsync("", "", url, scene);
		const mesh = mergeStaticModel(loaded, name) as Mesh;
		for (const node of loaded.meshes) if (node !== mesh && !node.isDisposed()) node.dispose(false, false);
		mesh.isVisible = false;
		mesh.isPickable = false;
		mesh.material?.dispose();
		mesh.material = null;
		return mesh;
	};
	const [blade, funnel, cone, ringWall] = await Promise.all([
		load(bladeUrl, "vfx-kit-blade"), load(funnelUrl, "vfx-kit-funnel"), load(coneUrl, "vfx-kit-cone"), load(ringWallUrl, "vfx-kit-ring-wall"),
	]);
	await Promise.all(Object.values(tex).map(texture => new Promise<void>(resolve => texture.isReady() ? resolve() : texture.onLoadObservable.addOnce(() => resolve()))));
	return {
		scene, tex, blade, funnel, cone, ringWall,
		dispose() {
			for (const texture of Object.values(tex)) texture.dispose();
			for (const mesh of [blade, funnel, cone, ringWall]) mesh.dispose(false, true);
		},
	};
}

// ----------------------------------------------------------------------------------------------
// Easing and envelopes (t in seconds unless stated)
// ----------------------------------------------------------------------------------------------

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const easeOutCubic = (x: number) => 1 - Math.pow(1 - clamp01(x), 3);
export const easeInCubic = (x: number) => Math.pow(clamp01(x), 3);
export const easeInQuad = (x: number) => clamp01(x) * clamp01(x);
export const easeOutQuad = (x: number) => 1 - (1 - clamp01(x)) * (1 - clamp01(x));
export const easeOutBack = (x: number, s = 1.70158) => { const t = clamp01(x) - 1; return 1 + t * t * ((s + 1) * t + s); };
/** 0 before a, rises to 1 at b, holds until c, falls to 0 at d (smooth). */
export function envelope(t: number, a: number, b: number, c: number, d: number): number {
	if (t <= a || t >= d) return 0;
	if (t < b) return easeOutQuad((t - a) / Math.max(1e-4, b - a));
	if (t <= c) return 1;
	return 1 - easeInQuad((t - c) / Math.max(1e-4, d - c));
}
/** Deterministic per-seed random in [0, 1). */
export function hash01(seed: number): number {
	const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
	return x - Math.floor(x);
}

// ----------------------------------------------------------------------------------------------
// Layer helpers: every layer reports its draw calls so the contact sheet can show "vfx N dc".
// ----------------------------------------------------------------------------------------------

export interface VfxLayer {
	readonly name: string;
	drawCalls(): number;
	particles(): number;
	dispose(): void;
}

export interface SurfaceLayer extends VfxLayer {
	readonly mesh: Mesh;
	readonly fx: VfxSurfacePlugin;
}

function surfaceOptions(kit: VfxKit, map: KitTexture, palette: PaletteName, extra: Partial<VfxSurfaceOptions>): VfxSurfaceOptions {
	const p = PALETTE[palette];
	return { map: kit.tex[map], noise: kit.tex.noise, core: p.core, mid: p.mid, edge: p.edge, ...extra };
}

function surfaceLayer(name: string, mesh: Mesh, fx: VfxSurfacePlugin, instanced = false): SurfaceLayer {
	return {
		name, mesh, fx,
		drawCalls: () => (instanced ? (mesh.instances.some(i => i.isEnabled()) ? 1 : 0) : (mesh.isEnabled() && mesh.visibility > 0.001 ? 1 : 0)),
		particles: () => 0,
		dispose: () => { mesh.instances.slice().forEach(i => i.dispose()); mesh.material?.dispose(); mesh.dispose(); },
	};
}

/** A flat ground decal (unit square in XZ, uv 0..1), placed with mesh.position/scaling. */
export function decal(kit: VfxKit, name: string, map: KitTexture, palette: PaletteName, extra: Partial<VfxSurfaceOptions> = {}): SurfaceLayer {
	const mesh = MeshBuilder.CreateGround(name, { width: 1, height: 1 }, kit.scene);
	mesh.isPickable = false;
	const { material, fx } = createVfxMaterial(kit.scene, `${name}-mat`, surfaceOptions(kit, map, palette, extra));
	material.zOffset = -2;
	mesh.material = material;
	mesh.setEnabled(false);
	return surfaceLayer(name, mesh, fx);
}

/** Instanced copies of a decal or kit mesh with the per-instance vfxInst attribute. */
export function instanced(kit: VfxKit, name: string, source: Mesh | "decal", map: KitTexture, palette: PaletteName,
	count: number, extra: Partial<VfxSurfaceOptions> = {}): SurfaceLayer & { readonly instances: Mesh["instances"] } {
	const mesh = source === "decal" ? MeshBuilder.CreateGround(name, { width: 1, height: 1 }, kit.scene) : source.clone(name, null, true, false) as Mesh;
	if (source !== "decal") mesh.makeGeometryUnique();
	mesh.isPickable = false;
	mesh.isVisible = true;
	mesh.registerInstancedBuffer(VFX_INSTANCE_KIND, 4);
	mesh.instancedBuffers[VFX_INSTANCE_KIND] = new Vector4(0, 0, 0, 0);
	const { material, fx } = createVfxMaterial(kit.scene, `${name}-mat`, surfaceOptions(kit, map, palette, extra));
	if (source === "decal") material.zOffset = -2;
	mesh.material = material;
	for (let i = 0; i < count; i++) {
		const instance = mesh.createInstance(`${name}-${i}`);
		instance.instancedBuffers[VFX_INSTANCE_KIND] = new Vector4(1, 0, 1, 1);
		instance.isPickable = false;
	}
	// The source stays enabled (its instances render through it) but never draws itself.
	mesh.isVisible = false;
	for (const instance of mesh.instances) instance.setEnabled(false);
	const layer = surfaceLayer(name, mesh, fx, true);
	return Object.assign(layer, { instances: mesh.instances });
}

/** A kit mesh (blade/funnel/cone/ring wall) with its own VFX surface. */
export function meshLayer(kit: VfxKit, name: string, source: Mesh, map: KitTexture, palette: PaletteName, extra: Partial<VfxSurfaceOptions> = {}): SurfaceLayer {
	const mesh = source.clone(name, null, true, false) as Mesh;
	mesh.isVisible = true;
	mesh.isPickable = false;
	const { material, fx } = createVfxMaterial(kit.scene, `${name}-mat`, surfaceOptions(kit, map, palette, { doubleSided: true, ...extra }));
	mesh.material = material;
	mesh.setEnabled(false);
	return surfaceLayer(name, mesh, fx);
}

/** Camera-facing billboard quad (unit square in XY). */
export function billboard(kit: VfxKit, name: string, map: KitTexture, palette: PaletteName, extra: Partial<VfxSurfaceOptions> = {}): SurfaceLayer {
	const mesh = MeshBuilder.CreatePlane(name, { size: 1 }, kit.scene);
	mesh.billboardMode = Mesh.BILLBOARDMODE_ALL;
	mesh.isPickable = false;
	const { material, fx } = createVfxMaterial(kit.scene, `${name}-mat`, surfaceOptions(kit, map, palette, { doubleSided: true, ...extra }));
	mesh.material = material;
	mesh.setEnabled(false);
	return surfaceLayer(name, mesh, fx);
}

/**
 * Up to `capacity` camera-facing beam quads in one mesh (lightning). Each beam spans A->B with a width,
 * and samples one cell of the 4x4 lightning atlas through its own UVs.
 */
export interface BeamLayer extends VfxLayer {
	readonly fx: VfxSurfacePlugin;
	set(index: number, a: Vector3, b: Vector3, width: number, cell: number, alpha: number): void;
	hide(index: number): void;
	commit(eye: Vector3): void;
}

export function beams(kit: VfxKit, name: string, palette: PaletteName, capacity: number, extra: Partial<VfxSurfaceOptions> = {}): BeamLayer {
	const scene = kit.scene;
	const positions = new Float32Array(capacity * 4 * 3);
	const uvs = new Float32Array(capacity * 4 * 2);
	const colors = new Float32Array(capacity * 4 * 4);
	const indices: number[] = [];
	for (let i = 0; i < capacity; i++) indices.push(i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3);
	const mesh = new Mesh(name, scene);
	const data = new VertexData();
	data.positions = positions;
	data.uvs = uvs;
	data.colors = colors;
	data.indices = indices;
	data.applyToMesh(mesh, true);
	mesh.useVertexColors = true;
	mesh.hasVertexAlpha = true;  // per-beam alpha in the vertex colour A channel
	mesh.alwaysSelectAsActiveMesh = true;
	mesh.isPickable = false;
	const { material, fx } = createVfxMaterial(scene, `${name}-mat`, surfaceOptions(kit, "lightning", palette, { doubleSided: true, ...extra }));
	mesh.material = material;
	const beamsState = Array.from({ length: capacity }, () => ({ a: new Vector3(), b: new Vector3(), width: 0, cell: 0, alpha: 0, on: false }));
	const side = new Vector3();
	const dir = new Vector3();
	const toEye = new Vector3();
	return {
		name, fx,
		drawCalls: () => (mesh.isEnabled() && beamsState.some(b => b.on) ? 1 : 0),
		particles: () => 0,
		set(index, a, b, width, cell, alpha) {
			const s = beamsState[index];
			s.a.copyFrom(a); s.b.copyFrom(b); s.width = width; s.cell = cell; s.alpha = alpha; s.on = alpha > 0.001;
		},
		hide(index) { beamsState[index].on = false; },
		commit(eye) {
			for (let i = 0; i < capacity; i++) {
				const s = beamsState[i];
				const p = i * 12;
				if (!s.on) { positions.fill(0, p, p + 12); continue; }
				s.b.subtractToRef(s.a, dir);
				eye.subtractToRef(s.a, toEye);
				Vector3.CrossToRef(dir, toEye, side);
				side.normalize().scaleInPlace(s.width / 2);
				const corners = [s.a.subtract(side), s.b.subtract(side), s.b.add(side), s.a.add(side)];
				corners.forEach((c, k) => { positions[p + k * 3] = c.x; positions[p + k * 3 + 1] = c.y; positions[p + k * 3 + 2] = c.z; });
				const col = s.cell % 4, row = Math.floor(s.cell / 4);
				const u0 = col / 4, u1 = (col + 1) / 4, v0 = 1 - (row + 1) / 4, v1 = 1 - row / 4;
				const q = i * 8;
				uvs.set([u0, v0, u1, v0, u1, v1, u0, v1], q);
				colors.fill(s.alpha, i * 16, i * 16 + 16);
			}
			mesh.updateVerticesData(VertexBuffer.PositionKind, positions);
			mesh.updateVerticesData(VertexBuffer.UVKind, uvs);
			mesh.updateVerticesData(VertexBuffer.ColorKind, colors);
		},
		dispose() { mesh.material?.dispose(); mesh.dispose(); },
	};
}

export interface ParticleLayer extends VfxLayer {
	readonly system: ParticleSystem;
}

export interface ParticleOptions {
	capacity: number;
	texture: KitTexture;
	sheet?: { cols: number; rows: number; cell: number; random?: boolean; loop?: boolean };
	blend?: "add" | "standard";
	color: Color4;
	color2?: Color4;
	dead?: Color4;
	size: [number, number];
	life: [number, number];
	gravity?: Vector3;
	billboard?: "all" | "y" | "stretched";
}

export function particles(kit: VfxKit, name: string, o: ParticleOptions): ParticleLayer {
	const system = new ParticleSystem(name, o.capacity, kit.scene);
	system.particleTexture = kit.tex[o.texture];
	system.updateSpeed = 1 / 60;
	system.blendMode = o.blend === "standard" ? ParticleSystem.BLENDMODE_STANDARD : ParticleSystem.BLENDMODE_ADD;
	system.color1 = o.color;
	system.color2 = o.color2 ?? o.color;
	system.colorDead = o.dead ?? new Color4(o.color.r, o.color.g, o.color.b, 0);
	system.minSize = o.size[0];
	system.maxSize = o.size[1];
	system.minLifeTime = o.life[0];
	system.maxLifeTime = o.life[1];
	system.emitRate = 0;
	system.manualEmitCount = 0;  // manual bursts only (Babylon resets it to 0 after each emission)
	system.gravity = o.gravity ?? Vector3.Zero();
	system.minEmitPower = system.maxEmitPower = 1;  // start-direction functions supply velocity in m/s
	system.emitter = Vector3.Zero();
	system.isLocal = false;
	if (o.billboard === "y") system.billboardMode = ParticleSystem.BILLBOARDMODE_Y;
	if (o.billboard === "stretched") system.billboardMode = ParticleSystem.BILLBOARDMODE_STRETCHED;
	if (o.sheet) {
		system.isAnimationSheetEnabled = true;
		system.spriteCellWidth = kit.tex[o.texture].getSize().width / o.sheet.cols;
		system.spriteCellHeight = kit.tex[o.texture].getSize().height / o.sheet.rows;
		system.startSpriteCellID = 0;
		system.endSpriteCellID = o.sheet.cell - 1;
		system.spriteCellChangeSpeed = 1;
		system.spriteCellLoop = o.sheet.loop ?? false;
		system.spriteRandomStartCell = o.sheet.random ?? false;
	}
	system.preventAutoStart = true;
	return {
		name, system,
		drawCalls: () => (system.getActiveCount() > 0 ? 1 : 0),
		particles: () => system.getActiveCount(),
		dispose: () => system.dispose(false),
	};
}

/** Two pooled point lights, created once so materials never recompile when an effect lights up. */
export class LightPool {
	private readonly lights: PointLight[];
	private readonly owners = new Map<PointLight, object>();
	constructor(scene: Scene, count = 2) {
		this.lights = Array.from({ length: count }, (_, i) => {
			const light = new PointLight(`vfx-light-${i}`, Vector3.Zero(), scene);
			light.intensity = 0;
			light.range = 10;
			light.specular = Color3.Black();
			return light;
		});
	}
	acquire(owner: object): PointLight | null {
		const free = this.lights.find(l => !this.owners.has(l));
		if (!free) return null;
		this.owners.set(free, owner);
		return free;
	}
	release(light: PointLight | null): void {
		if (!light) return;
		light.intensity = 0;
		this.owners.delete(light);
	}
	get active(): number { return this.lights.filter(l => l.intensity > 0.01).length; }
}
