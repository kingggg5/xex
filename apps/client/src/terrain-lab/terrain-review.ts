import { Engine } from "@babylonjs/core/Engines/engine";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Scene } from "@babylonjs/core/scene";
import { Camera } from "@babylonjs/core/Cameras/camera";
import { FreeCamera } from "@babylonjs/core/Cameras/freeCamera";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { ShadowGenerator } from "@babylonjs/core/Lights/Shadows/shadowGenerator";
import { CascadedShadowGenerator } from "@babylonjs/core/Lights/Shadows/cascadedShadowGenerator";
import { ImageProcessingConfiguration } from "@babylonjs/core/Materials/imageProcessingConfiguration";
import { ColorCurves } from "@babylonjs/core/Materials/colorCurves";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import type { Material } from "@babylonjs/core/Materials/material";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import { configureAssetCodecs } from "../asset-codecs";
import { configureLevelEnvironment } from "../level-environment-light";
import { addMeadowSurface } from "../meadow-surface";
import { createTerrainSurface, TERRAIN_DEBUG_MODES, TERRAIN_LOOK_DEFAULTS, type TerrainDebugMode, type TerrainLayersetManifest, type TerrainProbe, type TerrainSurface } from "../terrain-surface";
import { sampleEnvironment } from "../world-environment-state.mjs";
import { LOOKDEV_CAMERAS } from "../lookdev/lookdev-data.mjs";
import { rendererBootPolicy } from "../renderer-boot-policy.mjs";
import { resolveGraphicsPreset } from "../graphics-quality.mjs";
import { cellTexel, texelWorld } from "../terrain-surface-math.mjs";
import manifestJson from "../assets/world/terrain/terrain-layerset.json";
import labLayout from "../../../../assets/blender/sunmeadow_v2/terrain/terrain-lab-layout.json";
import grassAlbedoUrl from "../assets/world/meadow_grass_painted_albedo.png?url";
import grassNormalUrl from "../assets/world/meadow_grass_painted_normal.png?url";
import stoneNormalUrl from "../assets/world/stone_painted_normal.png?url";

/**
 * Terrain splat lab (terrain spec §8.5): one fixed 64 m review cell (assets/blender/sunmeadow_v2/terrain/
 * terrain-lab-layout.json) with a straight and a curved trail, a rutted gate-road segment and T-junction, a 12 m
 * stream with banks and a bridge, a 5 m hill and an outcrop, a 6 m cliff with a ledge, mossy boulders and a 1.8 m
 * witness. P1 builds the geometry here from the layout (script 7's Blender diorama is a P2 item).
 *
 * Query: variant=A (legacy ground) | B (splat) | C (splat + look overrides normalStrength/edgeBreakup/cellAO),
 * tier=0..2 | low..ultra, hour=13|18|22.5, renderer=webgl2, layer=0..3, terrainDebug=<mode>, weather=clear|rain,
 * res=WxH (render size, default 1280x720; stats() and the probes assume 1280x720).
 * API: window.terrainLab (sheet, debugSheet, compileReport, stats, orientationProbe, setView, ...). Every image it
 * returns is labelled BABYLON CAPTURE.
 * GPU cost study (P1 report §10): applyConfig() (variant parts, tier, probe, anisotropy, view, hour) and measure()
 * (per-frame GPU time: WebGPU main-pass timestamp queries, WebGL2 EXT_disjoint_timer_query_webgl2 over the main
 * camera's draw phase; shadow-map passes are excluded on both).
 */

type Variant = "A" | "B" | "C";
type ViewName = "player" | "side" | "close" | "elevated";
const VIEWS: readonly ViewName[] = ["player", "side", "close", "elevated"];
const manifest = manifestJson as unknown as TerrainLayersetManifest;
const FILES = import.meta.glob("../assets/world/terrain/**/*.{ktx2,png}", { query: "?url", import: "default", eager: true }) as Record<string, string>;
const resolveUrl = (file: string): string => {
	const url = FILES[`../assets/world/terrain/${file}`];
	if (!url) throw new Error(`Terrain lab: no bundled file ${file}`);
	return url;
};
const params = new URLSearchParams(location.search);
const LAB = labLayout as unknown as {
	cell: { id: string; bounds_xz: [number, number, number, number] };
	water: Array<{ points: [number, number][]; width_m: [number, number]; surface_y: number; bed_y: number }>;
	bridges: Array<{ center_xz: [number, number]; along_xz: [number, number]; length_m: number; deck_width_m: number }>;
	relief: Array<{ id: string; kind: string; center_xz?: [number, number]; radius_m?: number; height_m: number; polygon_xz?: [number, number][]; ledge_y?: number }>;
	rocks: Array<{ id: string; kind: string; center_xz: [number, number]; radius_m: number; height_m: number }>;
	trees: Array<{ id: string; position_xz: [number, number]; canopy_radius_m: number; trunk_radius_m: number }>;
	witness: { position_xz: [number, number]; height_m: number };
	anchors: Record<string, [number, number]>;
};
const PRESET_OF_TIER: Record<number, "low" | "medium" | "high"> = { 0: "low", 1: "medium", 2: "high" };
/** Render size (?res=WxH), DPR 1. */
const RES: readonly [number, number] = (() => {
	const m = /^(\d{3,4})x(\d{3,4})$/.exec(params.get("res") ?? "");
	return m ? [Number(m[1]), Number(m[2])] : [1280, 720];
})();
/** Top-down ortho camera height: below every tier's far-fade start (tier 0: 45 m), above the 6 m cliff. */
const TOP_VIEW_HEIGHT = 12;

// ----------------------------------------------------------------------------
// Lab geometry (same analytic relief as build_terrain_masks.py for the lab set)
// ----------------------------------------------------------------------------

const smooth = (a: number, b: number, x: number) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

function polylineDistance(x: number, z: number, pts: [number, number][]): { dist: number; arc: number; total: number } {
	let best = Infinity, arcAt = 0, total = 0;
	for (let i = 0; i + 1 < pts.length; i++) {
		const [ax, az] = pts[i], [bx, bz] = pts[i + 1];
		const dx = bx - ax, dz = bz - az, len = Math.hypot(dx, dz);
		const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (len * len)));
		const d = Math.hypot(x - (ax + t * dx), z - (az + t * dz));
		if (d < best) { best = d; arcAt = total + t * len; }
		total += len;
	}
	return { dist: best, arc: arcAt, total };
}

function labHeight(x: number, z: number): number {
	let h = 0;
	for (const r of LAB.relief) {
		if (r.kind !== "hill" || !r.center_xz || !r.radius_m) continue;
		const d = Math.hypot(x - r.center_xz[0], z - r.center_xz[1]);
		if (d < r.radius_m) h = Math.max(h, r.height_m * 0.5 * (1 + Math.cos(Math.PI * d / r.radius_m)));
	}
	for (const w of LAB.water) {
		const { dist, arc, total } = polylineDistance(x, z, w.points);
		const width = w.width_m[0] + (w.width_m[1] - w.width_m[0]) * Math.max(0, Math.min(1, arc / total));
		const d = dist - width / 2;                      // signed distance to the water edge
		const t = Math.max(0, Math.min(1, (0.3 - d) / 1.3));
		h += (w.bed_y) * t * t * (3 - 2 * t);           // bank from +0.3 m outside to the bed 1 m inside
	}
	return h;
}

function hash3(x: number, y: number, z: number): number {
	const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
	return s - Math.floor(s);
}
function noise3(x: number, y: number, z: number): number {
	const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
	const fx = x - ix, fy = y - iy, fz = z - iz;
	const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy), w = fz * fz * (3 - 2 * fz);
	const n = (a: number, b: number, c: number) => hash3(ix + a, iy + b, iz + c);
	const l = (a: number, b: number, t: number) => a + (b - a) * t;
	return l(l(l(n(0, 0, 0), n(1, 0, 0), u), l(n(0, 1, 0), n(1, 1, 0), u), v), l(l(n(0, 0, 1), n(1, 0, 1), u), l(n(0, 1, 1), n(1, 1, 1), u), v), w) * 2 - 1;
}

/** Generic rock: displaced icosphere; COLOR_0 = (AO, curvature 0.5 = flat, ground-contact gradient, 1) per spec §5.1. */
function buildRock(scene: Scene, name: string, cx: number, cz: number, radius: number, height: number, seed: number): Mesh {
	const mesh = MeshBuilder.CreateIcoSphere(name, { radius: 1, subdivisions: 4, flat: false }, scene);
	const pos = mesh.getVerticesData(VertexBuffer.PositionKind)!;
	const colors = new Float32Array(pos.length / 3 * 4);
	const base = labHeight(cx, cz);
	for (let i = 0, c = 0; i < pos.length; i += 3, c += 4) {
		const px = pos[i], py = pos[i + 1], pz = pos[i + 2];
		const bump = 0.22 * noise3(px * 1.6 + seed, py * 1.6, pz * 1.6) + 0.07 * noise3(px * 4.1, py * 4.1 + seed, pz * 4.1);
		const k = 1 + bump;
		let y = py * k * height * 0.62;
		y = Math.max(y, -0.12 * height);
		pos[i] = cx + px * k * radius;
		pos[i + 1] = base + y + 0.1 * height;
		pos[i + 2] = cz + pz * k * radius * 0.9;
		const above = y + 0.1 * height;
		colors[c] = 0.55 + 0.45 * smooth(-0.05 * height, 0.7 * height, y);   // AO
		colors[c + 1] = Math.max(0, Math.min(1, 0.5 + bump * 1.6));             // curvature (convex bumps > 0.5)
		colors[c + 2] = Math.max(0, Math.min(1, above / 0.6));                    // 0 at the ground -> 1 at 0.6 m
		colors[c + 3] = 1;
	}
	const normals: number[] = [];
	VertexData.ComputeNormals(pos, mesh.getIndices()!, normals);
	// setVerticesData, not updateVerticesData: CreateIcoSphere buffers are not updatable, so an update only changed the
	// CPU copy and the bounds, and every rock rendered as a unit sphere at the origin (lab pass 1)
	mesh.setVerticesData(VertexBuffer.PositionKind, pos, false);
	mesh.setVerticesData(VertexBuffer.NormalKind, normals, false);
	mesh.setVerticesData(VertexBuffer.ColorKind, colors, false, 4);
	mesh.hasVertexAlpha = false;
	mesh.refreshBoundingInfo();
	return mesh;
}

function colourBox(mesh: Mesh, top: number): void {
	const pos = mesh.getVerticesData(VertexBuffer.PositionKind)!;
	const colors = new Float32Array(pos.length / 3 * 4);
	const world = mesh.computeWorldMatrix(true);
	for (let i = 0, c = 0; i < pos.length; i += 3, c += 4) {
		const y = Vector3.TransformCoordinates(new Vector3(pos[i], pos[i + 1], pos[i + 2]), world).y;
		colors[c] = 0.7 + 0.3 * smooth(0, top, y);
		colors[c + 1] = y > top - 0.05 ? 0.72 : 0.5;
		colors[c + 2] = Math.max(0, Math.min(1, y / 0.6));
		colors[c + 3] = 1;
	}
	mesh.setVerticesData(VertexBuffer.ColorKind, colors, false, 4);
	mesh.hasVertexAlpha = false;
}

// ----------------------------------------------------------------------------
// PNG bytes (exact-byte probe reference): terrain_png.write_png uses filter 0 only
// ----------------------------------------------------------------------------

async function decodePng(url: string): Promise<{ w: number; h: number; ch: number; data: Uint8Array }> {
	const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
	const view = new DataView(buf.buffer);
	let pos = 8, w = 0, h = 0, ctype = 0;
	const idat: Uint8Array[] = [];
	while (pos < buf.length) {
		const len = view.getUint32(pos);
		const tag = String.fromCharCode(buf[pos + 4], buf[pos + 5], buf[pos + 6], buf[pos + 7]);
		if (tag === "IHDR") { w = view.getUint32(pos + 8); h = view.getUint32(pos + 12); ctype = buf[pos + 17]; }
		else if (tag === "IDAT") idat.push(buf.subarray(pos + 8, pos + 8 + len));
		pos += 12 + len;
	}
	const joined = new Uint8Array(idat.reduce((s, a) => s + a.length, 0));
	idat.reduce((o, a) => { joined.set(a, o); return o + a.length; }, 0);
	const stream = new Blob([joined]).stream().pipeThrough(new DecompressionStream("deflate"));
	const raw = new Uint8Array(await new Response(stream).arrayBuffer());
	const ch = ctype === 2 ? 3 : ctype === 6 ? 4 : 1;
	const stride = w * ch;
	const out = new Uint8Array(w * h * ch);
	for (let y = 0; y < h; y++) {
		if (raw[y * (stride + 1)] !== 0) throw new Error(`${url}: PNG filter ${raw[y * (stride + 1)]} (expected 0)`);
		out.set(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)), y * stride);
	}
	return { w, h, ch, data: out };
}

// ----------------------------------------------------------------------------
// Lab
// ----------------------------------------------------------------------------

class TerrainLab {
	readonly scene: Scene;
	readonly camera: FreeCamera;
	readonly sun: DirectionalLight;
	readonly fill: HemisphericLight;
	readonly instrumentation: SceneInstrumentation;
	shadows!: ShadowGenerator;
	surface!: TerrainSurface;
	legacy!: PBRMaterial;
	legacyStone!: PBRMaterial;
	ground!: Mesh;
	farParts: Mesh[] = [];
	rocks: Mesh[] = [];
	props: Mesh[] = [];
	water!: Mesh;
	variant: Variant;
	parts = { ground: true, far: true, rocks: true };
	tier: number;
	hour = 13;
	weather: "clear" | "rain" = "clear";
	errors: Array<{ material: string; errors: string }> = [];
	levelLight?: Awaited<ReturnType<typeof configureLevelEnvironment>>;

	constructor(readonly engine: AbstractEngine, readonly renderer: string) {
		this.scene = new Scene(engine);
		this.scene.clearColor = new Color4(0.72, 0.82, 0.9, 1);
		this.camera = new FreeCamera("lab-camera", new Vector3(0, 6.6, -13), this.scene);
		this.camera.minZ = 0.1;
		this.camera.maxZ = 1200;
		this.fill = new HemisphericLight("env-sky-fill", new Vector3(0, 1, 0), this.scene);
		this.fill.diffuse = Color3.FromHexString("#a9c9f4");
		this.fill.groundColor = Color3.FromHexString("#6a7440");
		this.sun = new DirectionalLight("env-sun", new Vector3(-0.55, -0.82, 0.35), this.scene);
		this.sun.position = new Vector3(-42, 65, -56);
		this.sun.specular = Color3.FromHexString("#fff8ea");
		this.instrumentation = new SceneInstrumentation(this.scene);
		this.instrumentation.captureFrameTime = true;
		const v = params.get("variant");
		this.variant = v === "A" || v === "C" ? v : "B";
		const t = params.get("tier");
		this.tier = t === null ? 2 : /^[0-2]$/.test(t) ? Number(t) : ({ low: 0, medium: 1, high: 2, ultra: 2 } as Record<string, number>)[t] ?? 2;
		const hour = Number(params.get("hour"));
		if (Number.isFinite(hour) && params.has("hour")) this.hour = hour;
		if (params.get("weather") === "rain") this.weather = "rain";
	}

	async init(): Promise<void> {
		const scene = this.scene;
		await configureAssetCodecs();
		const profile = resolveGraphicsPreset(PRESET_OF_TIER[this.tier], { formFactor: "desktop", width: 1280, height: 720, devicePixelRatio: 1 });
		try { this.levelLight = await configureLevelEnvironment(scene, profile); }
		catch (error) { console.warn("Lab IBL unavailable", error); }
		// environment.ts makeShadows (game settings)
		const shadows = profile.cascades > 1 && CascadedShadowGenerator.IsSupported ? new CascadedShadowGenerator(profile.shadowMapSize, this.sun) : new ShadowGenerator(profile.shadowMapSize, this.sun);
		if (shadows instanceof CascadedShadowGenerator) {
			shadows.numCascades = profile.cascades; shadows.lambda = 0.72; shadows.stabilizeCascades = true;
			shadows.shadowMaxZ = profile.shadowDistance; shadows.cascadeBlendPercentage = 0.12;
		}
		shadows.usePercentageCloserFiltering = true; shadows.filteringQuality = ShadowGenerator.QUALITY_MEDIUM;
		shadows.darkness = 0.2; shadows.bias = 0.00015; shadows.normalBias = 0.025;
		this.shadows = shadows;
		this.sun.shadowMinZ = 2; this.sun.shadowMaxZ = 240; this.sun.autoCalcShadowZBounds = true;
		const ip = scene.imageProcessingConfiguration;
		ip.toneMappingEnabled = true;
		ip.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
		ip.contrast = 1.12;
		ip.exposure = 1;
		ip.colorCurvesEnabled = true;
		ip.colorCurves = new ColorCurves();
		scene.fogMode = Scene.FOGMODE_EXP2;
		scene.onNewMaterialAddedObservable.add(material => {
			material.onError = (_effect, errors) => { this.errors.push({ material: material.name, errors: String(errors).slice(0, 2000) }); };
		});

		// legacy (A) materials: environment.ts createTerrainMaterial / createPbrCellMaterial, UV = world XZ / 6
		this.legacy = new PBRMaterial("env-shared-world-grass", scene);
		const albedo = new Texture(grassAlbedoUrl, scene, false, false);
		albedo.gammaSpace = true;
		const normal = new Texture(grassNormalUrl, scene, false, false);
		normal.gammaSpace = false;
		normal.level = 0.35;
		for (const tex of [albedo, normal]) { tex.wrapU = tex.wrapV = Texture.WRAP_ADDRESSMODE; tex.uScale = tex.vScale = 64 / 6; }
		this.legacy.albedoTexture = albedo;
		this.legacy.bumpTexture = normal;
		this.legacy.albedoColor = Color3.FromHexString("#e9f0dc");
		this.legacy.metallic = 0;
		this.legacy.roughness = 0.94;
		this.legacy.backFaceCulling = false;
		this.legacy.forceNormalForward = true;
		addMeadowSurface(this.legacy);
		// A rocks: the painted stone normal on a neutral grey (the stone albedo is authored for cell UVs, not lab boxes)
		this.legacyStone = new PBRMaterial("env-cell-stone", scene);
		const sn = new Texture(stoneNormalUrl, scene, false, false);
		sn.gammaSpace = false;
		this.legacyStone.albedoColor = Color3.FromHexString("#8c8a84");
		this.legacyStone.bumpTexture = sn;
		this.legacyStone.metallic = 0;
		this.legacyStone.roughness = 0.92;

		this.surface = createTerrainSurface(scene, {
			profile: { preset: PRESET_OF_TIER[this.tier] }, manifest, resolveUrl, legacy: this.legacy, set: "lab",
			debug: (TERRAIN_DEBUG_MODES as readonly string[]).includes(params.get("terrainDebug") ?? "") ? params.get("terrainDebug") as TerrainDebugMode : "off",
			solo: params.has("layer") ? Number(params.get("layer")) : -1,
		});
		this.buildCell();
		await this.applyVariant(this.variant);
		this.setHour(this.hour);
	}

	private buildCell(): void {
		const scene = this.scene;
		const ground = MeshBuilder.CreateGround("lab-ground", { width: 64, height: 64, subdivisions: 256, updatable: true }, scene);
		const pos = ground.getVerticesData(VertexBuffer.PositionKind)!;
		for (let i = 0; i < pos.length; i += 3) pos[i + 1] = labHeight(pos[i], pos[i + 2]);
		const normals: number[] = [];
		VertexData.ComputeNormals(pos, ground.getIndices()!, normals);
		ground.updateVerticesData(VertexBuffer.PositionKind, pos);
		ground.updateVerticesData(VertexBuffer.NormalKind, normals);
		ground.refreshBoundingInfo();
		ground.receiveShadows = true;
		this.ground = ground;
		// far ground around the cell (the cell is never shaded twice: four strips leave the cell footprint open)
		const strips: Array<[number, number, number, number]> = [[-400, 400, 32, 400], [-400, 400, -400, -32], [-400, -32, -32, 32], [32, 400, -32, 32]];
		this.farParts = strips.map(([x0, x1, z0, z1], i) => {
			const m = MeshBuilder.CreateGround(`lab-far-${i}`, { width: x1 - x0, height: z1 - z0, subdivisions: 4 }, scene);
			m.position.set((x0 + x1) / 2, -0.002, (z0 + z1) / 2);
			m.receiveShadows = true;
			return m;
		});
		const water = MeshBuilder.CreateGround("lab-water", { width: 64, height: 64 }, scene);
		water.position.y = LAB.water[0]?.surface_y ?? -0.35;
		const wm = new PBRMaterial("lab-water", scene);
		wm.albedoColor = Color3.FromHexString("#2b5562");
		wm.alpha = 0.82;
		wm.roughness = 0.08;
		wm.metallic = 0;
		water.material = wm;
		this.water = water;
		// cliff with a ledge (two stacked blocks), outcrop and boulders: rock plugin (B) / painted stone (A)
		for (const r of LAB.relief) {
			if (r.kind !== "cliff" || !r.polygon_xz) continue;
			const xs = r.polygon_xz.map(p => p[0]), zs = r.polygon_xz.map(p => p[1]);
			const x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
			const ledge = r.ledge_y ?? r.height_m * 0.55;
			const lower = MeshBuilder.CreateBox(`${r.id}-lower`, { width: x1 + 0.4 - x0, height: ledge, depth: z1 - z0 }, scene);
			lower.position.set((x0 + x1 + 0.4) / 2, ledge / 2, (z0 + z1) / 2);
			const upper = MeshBuilder.CreateBox(`${r.id}-upper`, { width: x1 - 0.6 - x0, height: r.height_m - ledge, depth: z1 - z0 - 1 }, scene);
			upper.position.set((x0 + x1 - 0.6) / 2, ledge + (r.height_m - ledge) / 2, (z0 + z1) / 2);
			colourBox(lower, ledge);
			colourBox(upper, r.height_m);
			this.rocks.push(lower, upper);
		}
		LAB.rocks.forEach((r, i) => this.rocks.push(buildRock(scene, `lab-${r.id}`, r.center_xz[0], r.center_xz[1], r.radius_m, r.height_m, 11 + i * 7)));
		for (const rock of this.rocks) { rock.receiveShadows = true; this.shadows.addShadowCaster(rock, false); }
		const bark = new PBRMaterial("lab-bark", scene);
		bark.albedoColor = Color3.FromHexString("#4a3a2b"); bark.roughness = 0.92; bark.metallic = 0;
		const leaves = new PBRMaterial("lab-canopy", scene);
		leaves.albedoColor = Color3.FromHexString("#3b5a28"); leaves.roughness = 0.86; leaves.metallic = 0;
		for (const t of LAB.trees) {
			const [x, z] = t.position_xz;
			const trunk = MeshBuilder.CreateCylinder(`${t.id}-trunk`, { height: 4.4, diameterTop: t.trunk_radius_m * 1.4, diameterBottom: t.trunk_radius_m * 2.2, tessellation: 10 }, scene);
			trunk.position.set(x, labHeight(x, z) + 2.2, z);
			trunk.material = bark;
			const canopy = MeshBuilder.CreateSphere(`${t.id}-canopy`, { diameter: t.canopy_radius_m * 2, segments: 12 }, scene);
			canopy.position.set(x, labHeight(x, z) + 4.8, z);
			canopy.scaling.y = 0.78;
			canopy.material = leaves;
			this.props.push(trunk, canopy);
		}
		const deckMat = new PBRMaterial("lab-deck", scene);
		deckMat.albedoColor = Color3.FromHexString("#6b5038"); deckMat.roughness = 0.85; deckMat.metallic = 0;
		for (const b of LAB.bridges) {
			const deck = MeshBuilder.CreateBox("lab-bridge", { width: b.length_m, height: 0.22, depth: b.deck_width_m }, scene);
			deck.position.set(b.center_xz[0], -0.06, b.center_xz[1]);
			deck.rotation.y = Math.atan2(-b.along_xz[1], b.along_xz[0]);
			deck.material = deckMat;
			this.props.push(deck);
		}
		const witness = MeshBuilder.CreateCapsule("lab-witness", { height: LAB.witness.height_m, radius: 0.28, tessellation: 12 }, scene);
		const [wx, wz] = LAB.witness.position_xz;
		witness.position.set(wx, labHeight(wx, wz) + LAB.witness.height_m / 2, wz);
		const wmat = new PBRMaterial("lab-witness", scene);
		wmat.albedoColor = Color3.FromHexString("#8c8c8c"); wmat.roughness = 0.7; wmat.metallic = 0;
		witness.material = wmat;
		this.props.push(witness);
		for (const p of this.props) { p.receiveShadows = true; this.shadows.addShadowCaster(p, false); }
	}

	async applyVariant(variant: Variant): Promise<void> {
		this.variant = variant;
		const splat = variant !== "A";
		await this.applyParts({ ground: splat, far: splat, rocks: splat }, false);
		// candidate look knobs for critique passes (C only): ?normalStrength=&edgeBreakup=&cellAO=
		const d = TERRAIN_LOOK_DEFAULTS;
		this.surface.setLook(variant === "C"
			? { normalStrength: Number(params.get("normalStrength") ?? d.normalStrength), edgeBreakup: Number(params.get("edgeBreakup") ?? d.edgeBreakup), cellAO: Number(params.get("cellAO") ?? d.cellAO) }
			: d);
		await this.ready();
	}

	/** Per-part material choice (GPU cost study): splat ground, far material and rock plugin, each against legacy. */
	async applyParts(parts: { ground: boolean; far: boolean; rocks: boolean }, settle = true): Promise<void> {
		this.parts = { ...parts };
		this.ground.material = parts.ground ? await this.surface.resolveCellMaterial(LAB.cell.id) : this.legacy;
		for (const m of this.farParts) m.material = parts.far ? this.surface.farMaterial : this.legacy;
		const rockMat = parts.rocks ? this.surface.rockMaterial("terrain_outcrop_rock", LAB.cell.id) : this.legacyStone;
		const cliffMat = parts.rocks ? this.surface.rockMaterial("terrain_cliff_rock", LAB.cell.id) : this.legacyStone;
		for (const r of this.rocks) r.material = r.name.startsWith("lab_cliff") ? cliffMat : rockMat;
		if (settle) await this.ready();
	}

	/** Game day/night (world-weather.ts:81-99 and environment.ts:308-323), sampled at a fixed hour. */
	setHour(hour: number): void {
		this.hour = hour;
		const elapsed = (((hour % 24 + 24) % 24 - 13.5 + 24) % 24) / 24 * 2_700_000;
		const state = sampleEnvironment(elapsed, { weather: this.weather, cycle: true });
		const wet = state.rain;
		this.sun.intensity = state.sunIntensity;
		this.sun.direction.copyFromFloats(state.direction[0], state.direction[1], state.direction[2]);
		Color3.LerpToRef(new Color3(0.45, 0.59, 0.91), new Color3(1, 0.9, 0.74), state.daylight, this.sun.diffuse);
		this.fill.intensity = state.hemisphereIntensity;
		const ip = this.scene.imageProcessingConfiguration;
		ip.exposure = 1 + (1 - state.daylight) * 0.22;
		const grade = ip.colorCurves!;
		const night = 1 - state.daylight;
		grade.globalSaturation = 16 - night * 40; grade.shadowsHue = 225; grade.shadowsDensity = night * 45; grade.midtonesHue = 215; grade.midtonesDensity = night * 22;
		const fog = Color3.Lerp(Color3.FromHexString("#182a43"), Color3.FromHexString("#b8d2e6"), state.daylight);
		this.scene.fogColor = fog;
		this.scene.fogDensity = state.fogDensity;
		this.scene.clearColor = new Color4(fog.r, fog.g, fog.b, 1);
		const sunWeight = Math.max(0, Math.min(1, (this.sun.intensity - 0.25) / 0.9));
		this.levelLight?.setIntensity(0.03 + 0.22 * sunWeight);
		for (const material of this.scene.materials) if (material instanceof PBRMaterial) material.directIntensity = 1 + 0.6 * sunWeight;
		// weather contract: world-weather.ts writes these on the legacy ground; terrain materials read them
		this.legacy.roughness = 0.94 - wet * 0.22;
		this.legacy.albedoColor.set(0.91 - wet * 0.1, 0.94 - wet * 0.08, 0.86 - wet * 0.08);
	}

	setView(view: ViewName | "top", anchorName = "junction", orthoWidth = 0): void {
		const [ax, az] = LAB.anchors[anchorName] ?? LAB.anchors.junction;
		const cam = this.camera;
		if (view === "top") {
			cam.mode = Camera.ORTHOGRAPHIC_CAMERA;
			const w = orthoWidth || 24, h = w * 720 / 1280;
			cam.orthoLeft = -w / 2; cam.orthoRight = w / 2; cam.orthoTop = h / 2; cam.orthoBottom = -h / 2;
			// 12 m up: an ortho view's extent ignores height, but the §3.6 far fade is distance-based (tier 0 starts at
			// 45 m); at 80 m the near branch was skipped (tier 0 frame black, tier 2 half far-faded - lab pass 2)
			cam.position.set(ax, TOP_VIEW_HEIGHT, az);
			cam.upVector = new Vector3(0, 0, 1);   // screen up = +Z (north), right = +X: same as the mask previews
			cam.setTarget(new Vector3(ax, 0, az));
			return;
		}
		cam.mode = Camera.PERSPECTIVE_CAMERA;
		cam.upVector = new Vector3(0, 1, 0);
		const c = LOOKDEV_CAMERAS[view];
		const target = new Vector3(ax, labHeight(ax, az) + 1.65, az);
		cam.fov = c.fov;
		cam.position.set(target.x + c.radius * Math.cos(c.alpha) * Math.sin(c.beta), target.y + c.radius * Math.cos(c.beta),
			target.z + c.radius * Math.sin(c.alpha) * Math.sin(c.beta));
		cam.setTarget(target);
	}

	/** Wait for textures and for every material in use to (re)compile, then settle 3 frames. A define change (tier,
	 * debug, solo) recompiles; on WebGL2 parallel compile an earlier frame read could still show the old effect. */
	async ready(extra: Array<[Material | null, Mesh]> = []): Promise<void> {
		await this.surface.whenLayersReady();
		const pairs: Array<[Material | null, Mesh]> = [[this.ground.material, this.ground], [this.farParts[0].material, this.farParts[0]],
			...this.rocks.slice(-2).map(r => [r.material, r] as [Material | null, Mesh]), ...extra];
		for (const [material, mesh] of pairs) if (material) await material.forceCompilationAsync(mesh);
		await this.scene.whenReadyAsync();
		for (let i = 0; i < 3; i++) this.renderFrame();
	}

	renderFrame(): void { this.engine.beginFrame(); this.scene.render(); this.engine.endFrame(); }

	/** RGBA pixels of the current frame, top row first, RGBA order on both renderers. */
	async frame(): Promise<ImageData> {
		const canvas = this.engine.getRenderingCanvas()!;
		this.renderFrame();
		const pixels = await this.engine.readPixels(0, 0, canvas.width, canvas.height, true, true);
		const w = canvas.width, h = canvas.height;
		const src = new Uint8ClampedArray(pixels.buffer as ArrayBuffer, pixels.byteOffset, w * h * 4);
		const data = new Uint8ClampedArray(w * h * 4);
		const flip = !this.engine.isWebGPU;      // WebGL2 read-back is bottom row first
		for (let y = 0; y < h; y++) data.set(src.subarray((flip ? h - 1 - y : y) * w * 4, ((flip ? h - 1 - y : y) + 1) * w * 4), y * w * 4);
		const gpu = (navigator as Navigator & { gpu?: { getPreferredCanvasFormat(): string } }).gpu;
		if (this.engine.isWebGPU && gpu?.getPreferredCanvasFormat() === "bgra8unorm") {
			for (let k = 0; k < data.length; k += 4) { const r = data[k]; data[k] = data[k + 2]; data[k + 2] = r; }
		}
		return new ImageData(data, w, h);
	}

	/** Contact sheet of labelled frames (BABYLON CAPTURE). */
	async sheet(title: string, frames: Array<{ label: string; setup: () => void | Promise<void> }>, cols = 2): Promise<string> {
		const cellW = 640, cellH = 360, label = 22, header = 34;
		const sheet = document.createElement("canvas");
		sheet.width = cellW * cols;
		sheet.height = header + (cellH + label) * Math.ceil(frames.length / cols);
		const g = sheet.getContext("2d")!;
		g.fillStyle = "#11161c";
		g.fillRect(0, 0, sheet.width, sheet.height);
		const tmp = document.createElement("canvas");
		const renderCanvas = this.engine.getRenderingCanvas()!;
		tmp.width = renderCanvas.width; tmp.height = renderCanvas.height;
		const tg = tmp.getContext("2d")!;
		for (let i = 0; i < frames.length; i++) {
			await frames[i].setup();
			await this.ready();
			tg.putImageData(await this.frame(), 0, 0);
			const x = (i % cols) * cellW, y = header + Math.floor(i / cols) * (cellH + label);
			g.drawImage(tmp, x, y + label, cellW, cellH);
			g.fillStyle = "#d6e2ea";
			g.font = "13px Consolas, monospace";
			g.fillText(frames[i].label, x + 8, y + 15);
		}
		g.fillStyle = "#f2c76e";
		g.font = "bold 16px Consolas, monospace";
		g.fillText(`BABYLON CAPTURE · ${title}`, 10, 23);
		g.fillStyle = "#c9d4dc";
		g.font = "12px Consolas, monospace";
		const right = `Xexoria terrain lab · ${this.renderer} · tier ${this.surface.tier} · ${tmp.width}x${tmp.height} · ${new Date().toISOString().slice(0, 16)}`;
		g.fillText(right, sheet.width - g.measureText(right).width - 10, 23);
		return sheet.toDataURL("image/png");
	}

	setHidden(hidden: boolean): void {
		for (const m of [...this.rocks, ...this.props, this.water, ...this.farParts]) m.isVisible = !hidden;
	}
}

// ----------------------------------------------------------------------------
// Measurements (§8.5 stats)
// ----------------------------------------------------------------------------

function groundPixels(image: ImageData, clear: [number, number, number]): number[] {
	const out: number[] = [];
	const d = image.data;
	for (let k = 0; k < d.length; k += 4) {
		if (Math.abs(d[k] - clear[0]) + Math.abs(d[k + 1] - clear[1]) + Math.abs(d[k + 2] - clear[2]) > 3) out.push(k);
	}
	return out;
}

function lumaImage(image: ImageData): Float32Array {
	const out = new Float32Array(image.width * image.height);
	for (let i = 0, k = 0; i < out.length; i++, k += 4) out[i] = 0.2126 * image.data[k] + 0.7152 * image.data[k + 1] + 0.0722 * image.data[k + 2];
	return out;
}

/** Pearson correlation of the image with itself shifted by (dx, dy) pixels, over the overlap. */
function shiftCorrelation(img: Float32Array, w: number, h: number, dx: number, dy: number): number {
	let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
	for (let y = 0; y + dy < h; y++) {
		for (let x = 0; x + dx < w; x++) {
			const a = img[y * w + x], b = img[(y + dy) * w + x + dx];
			n++; sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b;
		}
	}
	const cov = sab / n - (sa / n) * (sb / n);
	const va = saa / n - (sa / n) ** 2, vb = sbb / n - (sb / n) ** 2;
	return cov / Math.sqrt(Math.max(1e-9, va * vb));
}

// ----------------------------------------------------------------------------
// GPU timing (GPU cost study, P1 report §10)
// ----------------------------------------------------------------------------

interface CostConfig {
	variant?: "A" | "B";
	parts?: Partial<{ ground: boolean; far: boolean; rocks: boolean }>;
	tier?: number;
	probe?: TerrainProbe | null;
	aniso?: number | null;
	/** NRO maps only (overrides aniso for them). */
	anisoNro?: number | null;
	view?: ViewName;
	anchor?: string;
	hour?: number;
}

function summarize(values: number[]): { n: number; p50: number | null; p95: number | null; mean: number | null; min: number | null; max: number | null } {
	const v = values.filter(Number.isFinite).sort((a, b) => a - b);
	if (!v.length) return { n: 0, p50: null, p95: null, mean: null, min: null, max: null };
	const q = (f: number) => v[Math.max(0, Math.ceil(f * v.length) - 1)];
	const r = (x: number) => +x.toFixed(4);
	return { n: v.length, p50: r(q(0.5)), p95: r(q(0.95)), mean: r(v.reduce((s, x) => s + x, 0) / v.length), min: r(v[0]), max: r(v[v.length - 1]) };
}

/**
 * Per-frame GPU time of the main camera pass. WebGPU: Babylon's main-pass timestamp queries
 * (engine.enableGPUTimingMeasurements; durations summed per frame id, so a split main pass still counts once).
 * WebGL2: TIME_ELAPSED queries around the main camera's draw phase (after the shadow-map render targets).
 */
class GpuTimer {
	scope = "unavailable";
	available = false;
	private recording = false;
	private samples: number[] = [];
	private rejected = 0;
	private startFrame = 0;
	private stopFrame = Infinity;
	private perFrame = new Map<number, number>();
	private pending: WebGLQuery[] = [];
	private current: WebGLQuery | null = null;

	constructor(private readonly engine: AbstractEngine, scene: Scene) {
		if (engine.isWebGPU) {
			const e = engine as unknown as { enableGPUTimingMeasurements: boolean; gpuTimeInFrameForMainPass?: { _addDuration(id: number, ns: number): void } };
			try {
				e.enableGPUTimingMeasurements = true;
				const perf = e.gpuTimeInFrameForMainPass;
				if (!perf) return;
				const original = perf._addDuration.bind(perf);
				perf._addDuration = (frameId: number, ns: number) => {
					original(frameId, ns);
					if (frameId >= this.startFrame && frameId < this.stopFrame) this.perFrame.set(frameId, (this.perFrame.get(frameId) ?? 0) + ns);
				};
				this.scope = "webgpu-main-pass-timestamps";
				this.available = true;
			} catch (error) { console.warn("WebGPU timestamp queries unavailable", error); }
			return;
		}
		const gl = (engine as unknown as { _gl?: WebGL2RenderingContext })._gl;
		const ext = gl?.getExtension("EXT_disjoint_timer_query_webgl2") as { TIME_ELAPSED_EXT: number; GPU_DISJOINT_EXT: number } | null | undefined;
		if (!gl || !ext) return;
		this.scope = "webgl2-main-draw-phase-time-elapsed";
		this.available = true;
		scene.onBeforeDrawPhaseObservable.add(() => {
			if (!this.recording || this.current) return;
			this.current = gl.createQuery();
			if (this.current) gl.beginQuery(ext.TIME_ELAPSED_EXT, this.current);
		});
		scene.onAfterDrawPhaseObservable.add(() => {
			if (this.current) { gl.endQuery(ext.TIME_ELAPSED_EXT); this.pending.push(this.current); this.current = null; }
			this.poll(gl, ext);
		});
	}

	private poll(gl: WebGL2RenderingContext, ext: { GPU_DISJOINT_EXT: number }): void {
		while (this.pending.length) {
			const q = this.pending[0];
			if (!gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE)) break;
			const disjoint = gl.getParameter(ext.GPU_DISJOINT_EXT);
			const ns = gl.getQueryParameter(q, gl.QUERY_RESULT) as number;
			if (disjoint || !(ns > 0)) this.rejected++;
			else if (this.recording || this.draining) this.samples.push(ns / 1e6);
			gl.deleteQuery(q);
			this.pending.shift();
		}
	}
	private draining = false;

	start(): void {
		this.samples = []; this.rejected = 0; this.perFrame.clear();
		this.startFrame = (this.engine as unknown as { frameId: number }).frameId + 1;
		this.stopFrame = Infinity;
		this.recording = true;
	}

	async stop(): Promise<{ samples: number[]; rejected: number }> {
		this.recording = false;
		this.draining = true;
		this.stopFrame = (this.engine as unknown as { frameId: number }).frameId;
		// timestamp and query results arrive a few frames late
		await new Promise(resolve => setTimeout(resolve, 400));
		this.draining = false;
		if (this.engine.isWebGPU) {
			for (const ns of this.perFrame.values()) { if (ns > 0) this.samples.push(ns / 1e6); else this.rejected++; }
		}
		return { samples: this.samples.slice(), rejected: this.rejected };
	}
}

async function createEngine(canvas: HTMLCanvasElement): Promise<{ engine: AbstractEngine; renderer: string }> {
	// Game-identical WebGPU device features (renderer-boot-policy.mjs: texture compression, float32, timestamp query)
	const policy = rendererBootPolicy(false, params.get("renderer"));
	if (policy.preferWebGpu && "gpu" in navigator) {
		try {
			const { WebGPUEngine } = await import("@babylonjs/core/Engines/webgpuEngine");
			const engine = new WebGPUEngine(canvas, { ...policy.webGpuOptions, adaptToDeviceRatio: false });
			await engine.initAsync();
			return { engine, renderer: "WebGPU" };
		} catch (error) {
			console.warn("WebGPU unavailable, falling back to WebGL2", error);
		}
	}
	return { engine: new Engine(canvas, policy.antialias, { stencil: true, adaptToDeviceRatio: false }, false), renderer: "WebGL2" };
}

async function main(): Promise<void> {
	const canvas = document.getElementById("review") as HTMLCanvasElement;
	const status = document.getElementById("status")!;
	canvas.width = RES[0]; canvas.height = RES[1];
	canvas.style.width = `${RES[0]}px`; canvas.style.height = `${RES[1]}px`;
	const { engine, renderer } = await createEngine(canvas);
	const lab = new TerrainLab(engine, renderer);
	await lab.init();
	const gpuTimer = new GpuTimer(engine, lab.scene);
	lab.setView("player", "junction");
	await lab.ready();
	const cdnRequests = () => performance.getEntriesByType("resource").map(e => e.name).filter(n => /cdn\.babylonjs\.com/.test(n));

	const api = {
		renderer,
		lab,
		get variant() { return lab.variant; },
		async setVariant(v: Variant) { await lab.applyVariant(v); },
		setHour(h: number) { lab.setHour(h); },
		async setTier(t: number) { lab.tier = t; lab.surface.setQuality({ preset: PRESET_OF_TIER[t] }); await lab.ready(); },
		async setDebug(mode: TerrainDebugMode) { lab.surface.debug(mode); await lab.ready(); },
		async setSolo(layer: number | null) { lab.surface.solo(layer); await lab.ready(); },
		setView(view: ViewName | "top", anchor?: string, width?: number) { lab.setView(view, anchor, width); },
		async render() { await lab.ready(); },
		/** Four locked lookdev views at one anchor (+ a top-down), current variant/hour. */
		async sheet(anchor = "junction", views: readonly (ViewName | "top")[] = [...VIEWS, "top"]) {
			const frames = views.map(view => ({
				label: `variant ${lab.variant} · ${view} · anchor ${anchor} · ${String(lab.hour).padStart(4, "0")} h · ${lab.weather}`,
				setup: () => lab.setView(view, anchor, view === "top" ? 24 : 0),
			}));
			return lab.sheet(`terrain-splat-p1 · variant ${lab.variant} · ${anchor}`, frames, 2);
		},
		/** Every §3.6 debug view at the elevated view. */
		async debugSheet(anchor = "junction") {
			const modes: TerrainDebugMode[] = ["weights", "height", "normal", "rough", "ao", "sdf", "tiling", "mip", "fetches", "albedo"];
			const frames = modes.map(mode => ({ label: `terrainDebug=${mode} · elevated · ${anchor}`, setup: async () => { lab.surface.debug(mode); lab.setView("elevated", anchor); } }));
			const out = await lab.sheet(`terrain debug views · ${anchor}`, frames, 2);
			lab.surface.debug("off");
			await lab.ready();
			return out;
		},
		/** effect.onError capture per material and tier (both languages are whatever this engine uses). */
		async compileReport() {
			const rows: Array<Record<string, unknown>> = [];
			const before = lab.errors.length;
			const cell = await lab.surface.resolveCellMaterial(LAB.cell.id);
			const rock = lab.surface.rockMaterial("terrain_outcrop_rock", LAB.cell.id);
			const cliff = lab.surface.rockMaterial("terrain_cliff_rock", LAB.cell.id);
			const meshFor = (m: Material) => m === lab.surface.farMaterial ? lab.farParts[0] : m === cell ? lab.ground : lab.rocks[lab.rocks.length - 1];
			for (const tier of [2, 1, 0]) {
				lab.surface.setQuality({ preset: PRESET_OF_TIER[tier] });
				await lab.surface.whenLayersReady();
				for (const material of [cell, lab.surface.farMaterial, rock, cliff]) {
					const started = performance.now();
					let ok = true, error = "";
					try { await material.forceCompilationAsync(meshFor(material)); } catch (e) { ok = false; error = String(e).slice(0, 1500); }
					const effect = material.getEffect();
					rows.push({ material: material.name, tier, language: (material as PBRMaterial).shaderLanguage === ShaderLanguage.WGSL ? "WGSL" : "GLSL",
						ok: ok && !!effect?.isReady(), ms: +(performance.now() - started).toFixed(1), samplers: effect?.getSamplers().length ?? null,
						samplerNames: effect?.getSamplers() ?? [], error });
				}
			}
			lab.surface.setQuality({ preset: PRESET_OF_TIER[lab.tier] });
			await lab.ready();
			return { renderer, rows, onError: lab.errors.slice(before), cdnRequests: cdnRequests(),
				caps: { bptc: !!engine.getCaps().bptc, astc: !!engine.getCaps().astc, s3tc: !!engine.getCaps().s3tc, etc2: !!engine.getCaps().etc2 } };
		},
		/** §8.5 stats(): normal coverage, roughness std, tile autocorrelation, samplers, memory, exact-byte probes. */
		async stats(anchor = "junction") {
			const out: Record<string, unknown> = { renderer, tier: lab.surface.tier, variant: lab.variant, anchor,
				gpu: (engine as unknown as { getGlInfo?: () => Record<string, string> }).getGlInfo?.() ?? null };
			const restoreClear = lab.scene.clearColor.clone();
			const restoreTier = lab.tier;
			const restoreVariant = lab.variant;
			lab.scene.clearColor = new Color4(0, 0, 0, 1);
			lab.setHidden(true);
			await lab.applyVariant("B");
			await api.setTier(2);
			lab.setView("player", anchor);
			// normal coverage: world normal > 3 deg from up (debug normal = n * 0.5 + 0.5)
			await api.setDebug("normal");
			let img = await lab.frame();
			let px = groundPixels(img, [0, 0, 0]);
			let tilted = 0;
			const cos3 = Math.cos(3 * Math.PI / 180);
			for (const k of px) {
				const nx = img.data[k] / 127.5 - 1, ny = img.data[k + 1] / 127.5 - 1, nz = img.data[k + 2] / 127.5 - 1;
				if (ny / Math.max(1e-6, Math.hypot(nx, ny, nz)) < cos3) tilted++;
			}
			out.normalCoverage = { ratio: +(tilted / Math.max(1, px.length)).toFixed(4), groundPixels: px.length, target: ">= 0.60 (player view, High)" };
			// sweep of the shared normal-strength knob (look.normalStrength; variant C) for the critique record
			const sweep: Record<string, number> = {};
			for (const strength of [1.0, 1.5]) {
				lab.surface.setLook({ normalStrength: strength });
				await lab.ready();
				const f = await lab.frame();
				const g = groundPixels(f, [0, 0, 0]);
				let t = 0;
				for (const k of g) {
					const nx = f.data[k] / 127.5 - 1, ny = f.data[k + 1] / 127.5 - 1, nz = f.data[k + 2] / 127.5 - 1;
					if (ny / Math.max(1e-6, Math.hypot(nx, ny, nz)) < cos3) t++;
				}
				sweep[String(strength)] = +(t / Math.max(1, g.length)).toFixed(4);
			}
			lab.surface.setLook({ normalStrength: TERRAIN_LOOK_DEFAULTS.normalStrength });
			(out.normalCoverage as Record<string, unknown>).byNormalStrength = sweep;
			// roughness debug std over ground
			await api.setDebug("rough");
			img = await lab.frame();
			px = groundPixels(img, [0, 0, 0]);
			let s = 0, ss = 0;
			for (const k of px) { const r = img.data[k] / 255; s += r; ss += r * r; }
			const mean = s / Math.max(1, px.length);
			out.roughness = { mean: +mean.toFixed(4), std: +Math.sqrt(Math.max(0, ss / Math.max(1, px.length) - mean * mean)).toFixed(4), target: "std >= 0.05" };
			// tile-period autocorrelation: top-down albedo of L0 (6 m tile) with and without anti-tiling
			const tileCorr: Record<string, number> = {};
			for (const tier of [2, 0]) {
				await api.setTier(tier);
				await api.setSolo(0);
				await api.setDebug("albedo");
				lab.setView("top", "road_ruts", 24);
				lab.camera.position.set(12, TOP_VIEW_HEIGHT, 15); lab.camera.setTarget(new Vector3(12, 0, 15));
				await lab.ready();
				const top = await lab.frame();
				const lum = lumaImage(top);
				const lag = Math.round(6 / 24 * 1280);
				tileCorr[`tier${tier}`] = +((shiftCorrelation(lum, 1280, 720, lag, 0) + shiftCorrelation(lum, 1280, 720, 0, lag)) / 2).toFixed(4);
			}
			out.tileAutocorrelation = { ...tileCorr, period_m: 6, target: "<= 0.25 with anti-tiling (tier 2), >= 0.6 without (tier 0)" };
			await api.setSolo(null);
			// exact-byte probes: one splat and one data texel (debug splat / data, top-down, texel-centred)
			const record = manifest.cells.lab[LAB.cell.id];
			const [minX, , minZ] = record.bounds;
			const probe = { col: 128, row: 100 };
			const world = texelWorld(probe.col, probe.row, minX, minZ);
			const back = cellTexel(world.x, world.z, minX, minZ);
			const bytes: Record<string, unknown> = { texel: probe, world, roundTrip: back };
			for (const [mode, key] of [["splat", "splat"], ["data", "data"]] as const) {
				await api.setDebug(mode);
				lab.setView("top", "junction", 2);
				lab.camera.position.set(world.x, TOP_VIEW_HEIGHT, world.z); lab.camera.setTarget(new Vector3(world.x, 0, world.z));
				await lab.ready();
				const f = await lab.frame();
				const k = (360 * 1280 + 640) * 4;
				const png = await decodePng(resolveUrl(record[key]["257"]));
				const e = (probe.row * png.w + probe.col) * png.ch;
				const expected = [png.data[e], png.data[e + 1], png.data[e + 2]];
				const got = [f.data[k], f.data[k + 1], f.data[k + 2]];
				bytes[mode] = { expected, got, maxAbsDiff: Math.max(...expected.map((v, i) => Math.abs(v - got[i]))), limit: 1 };
			}
			out.exactBytes = bytes;
			await api.setDebug("off");
			const cellMaterial = await lab.surface.resolveCellMaterial(LAB.cell.id);
			out.samplers = {
				cell: cellMaterial.getEffect()?.getSamplers() ?? [],
				far: lab.surface.farMaterial.getEffect()?.getSamplers() ?? [],
				rock: lab.surface.rockMaterial("terrain_outcrop_rock", LAB.cell.id).getEffect()?.getSamplers() ?? [],
			};
			out.memory = lab.surface.memoryEstimate();
			out.cdnRequests = cdnRequests();
			lab.scene.clearColor = restoreClear;
			lab.setHidden(false);
			await api.setTier(restoreTier);
			await lab.applyVariant(restoreVariant);
			return out;
		},
		/**
		 * Orientation + grey-card probe (spec §6.2 item 8, §8.5): the calibration layer (red arrow to image top, blue
		 * flag on its right, sRGB 128 grey card, one bump) replaces every layer, as KTX2 or as PNG, through the same
		 * plugin path (L2 solo, debug albedo / normal). Returns arrow direction, grey-card byte and the KTX2/PNG diff.
		 */
		async orientationProbe() {
			const result: Record<string, unknown> = {};
			const images: Record<string, ImageData> = {};
			const calib = (manifest as unknown as { calibration: Record<string, { ktx2: string; png: string }> }).calibration;
			lab.setHidden(true);
			for (const kind of ["ktx2", "png"] as const) {
				const files = { ah: { "1024": calib.terrain_calibration_ah[kind], "512": calib.terrain_calibration_ah[kind] },
					nro: { "1024": calib.terrain_calibration_nro[kind], "512": calib.terrain_calibration_nro[kind] } };
				const probeManifest = { ...manifest, layers: manifest.layers.map(l => ({ ...l, files })) } as TerrainLayersetManifest;
				const surface = createTerrainSurface(lab.scene, { profile: { preset: "high" }, manifest: probeManifest, resolveUrl, legacy: lab.legacy, set: "lab", debug: "albedo", solo: 2 });
				const material = await surface.resolveCellMaterial(LAB.cell.id);
				const previous = lab.ground.material;
				lab.ground.material = material;
				lab.scene.clearColor = new Color4(0, 0, 0, 1);
				// L2 tile is 4 m; the tile [0,4] x [0,4] m is centred at (2, 2)
				lab.setView("top", "junction", 8);
				lab.camera.position.set(2, TOP_VIEW_HEIGHT, 2); lab.camera.setTarget(new Vector3(2, 0, 2));
				result[`${kind}LoadOk`] = await surface.whenLayersReady();
				await lab.ready([[material, lab.ground]]);
				const albedo = await lab.frame();
				surface.debug("normal");
				await lab.ready([[material, lab.ground]]);
				const normal = await lab.frame();
				images[kind] = albedo;
				const thumb = (img: ImageData) => {
					const c = document.createElement("canvas"); c.width = 1280; c.height = 720; c.getContext("2d")!.putImageData(img, 0, 0);
					const t = document.createElement("canvas"); t.width = 640; t.height = 360; t.getContext("2d")!.drawImage(c, 0, 0, 640, 360);
					return t.toDataURL("image/png");
				};
				result[`${kind}Images`] = { albedo: thumb(albedo), normal: thumb(normal) };
				// arrow: the wide head pulls the red centroid toward the tip, so "points up the screen (= +Z)" means the
				// red centroid lies above the red bounding-box centre (screen y grows downward)
				let hx = 0, hy = 0, hn = 0, fx = 0, fn = 0, top = 720, bottom = 0, grey: number[] = [];
				const pxPerM = 1280 / 8;
				const toScreen = (wx: number, wz: number) => [Math.round(640 + (wx - 2) * pxPerM), Math.round(360 - (wz - 2) * pxPerM)];
				// only the central tile [0, 4] x [0, 4] m (screen x 320..960): the 8 m view repeats the 4 m tile, and the
				// partial copies at the frame edges skew whole-frame centroids (lab pass 2 reported a false mirror)
				for (let y = 0; y < 720; y++) for (let x = 320; x < 960; x++) {
					const k = (y * 1280 + x) * 4;
					const r = albedo.data[k], g = albedo.data[k + 1], b = albedo.data[k + 2];
					if (r > 2 * g + 10 && r > 2 * b + 10) { hx += x; hy += y; hn++; top = Math.min(top, y); bottom = Math.max(bottom, y); }
					if (b > 2 * r + 4 && b > g + 4) { fx += x; fn++; }
				}
				const [gx, gy] = toScreen(0.4, 0.4);   // grey card area near the tile origin corner (texture lower-left = world (0,0))
				const k = (gy * 1280 + gx) * 4;
				grey = [albedo.data[k], albedo.data[k + 1], albedo.data[k + 2]];
				// bump: lower-left quadrant (texture px (64, 192) of 256 -> world (1.0, 1.0)); north side normal z > 0
				const [bx, by] = toScreen(1.0, 1.0);
				const sample = (sx: number, sy: number) => { const q = (sy * 1280 + sx) * 4; return [normal.data[q] / 127.5 - 1, normal.data[q + 1] / 127.5 - 1, normal.data[q + 2] / 127.5 - 1]; };
				const north = sample(bx, by - Math.round(0.4 * pxPerM)), south = sample(bx, by + Math.round(0.4 * pxPerM));
				const east = sample(bx + Math.round(0.4 * pxPerM), by), west = sample(bx - Math.round(0.4 * pxPerM), by);
				result[kind] = {
					arrowCentroidPx: hn ? [+(hx / hn).toFixed(1), +(hy / hn).toFixed(1)] : null, redPixels: hn, redRowsPx: [top, bottom],
					arrowPointsScreenUpPlusZ: hn ? hy / hn < (top + bottom) / 2 : null,
					flagRightOfArrow: fn && hn ? fx / fn > hx / hn : null,
					greyCardByte: grey, greyCardExpected: "55-56 (linear 0.216; 9 = double decode, 128 = no decode)",
					bump: { northNz: +north[2].toFixed(3), southNz: +south[2].toFixed(3), eastNx: +east[0].toFixed(3), westNx: +west[0].toFixed(3) },
				};
				lab.ground.material = previous;
				surface.dispose();
			}
			// arrow points up the screen (= +Z) when the head centroid is above the shaft: head occupies the upper half
			let diff = 0, n = 0;
			for (let k = 0; k < images.ktx2.data.length; k += 4) {
				diff += Math.abs(images.ktx2.data[k] - images.png.data[k]) + Math.abs(images.ktx2.data[k + 1] - images.png.data[k + 1]) + Math.abs(images.ktx2.data[k + 2] - images.png.data[k + 2]);
				n += 3;
			}
			result.ktx2VsPngMeanAbsDiff = +(diff / n).toFixed(3);
			lab.setHidden(false);
			lab.setHour(lab.hour);
			await lab.ready();
			return result;
		},
		/** Frame time (lab only; not the GTX 1050 protocol). */
		async frameTime(n = 120) {
			for (let i = 0; i < 20; i++) lab.renderFrame();
			await engine.readPixels(0, 0, 1, 1, true, true);
			const started = performance.now();
			for (let i = 0; i < n; i++) lab.renderFrame();
			await engine.readPixels(0, 0, 1, 1, true, true);
			return { avgMs: +((performance.now() - started) / n).toFixed(3), drawCalls: lab.instrumentation.drawCallsCounter.current };
		},
		/** Full-resolution PNG of the current view (for the §2.3 look metrics; unlabelled, the driver names it). */
		async frameDataUrl() {
			await lab.ready();
			const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
			c.getContext("2d")!.putImageData(await lab.frame(), 0, 0);
			return c.toDataURL("image/png");
		},
		cdnRequests,
		errors: () => lab.errors,
		resolution: [engine.getRenderWidth(), engine.getRenderHeight()],
		gpuTimer: { scope: gpuTimer.scope, available: gpuTimer.available },
		/** GPU cost study: set parts / tier / probe / anisotropy / view / hour, then wait for every effect to compile. */
		async applyConfig(cfg: CostConfig) {
			lab.surface.probe(cfg.probe ?? null);
			if (cfg.tier !== undefined && cfg.tier !== lab.tier) { lab.tier = cfg.tier; lab.surface.setQuality({ preset: PRESET_OF_TIER[cfg.tier] }); }
			const parts = cfg.variant === "A" ? { ground: false, far: false, rocks: false } : { ground: true, far: true, rocks: true, ...(cfg.parts ?? {}) };
			lab.variant = parts.ground ? "B" : "A";
			lab.setHour(cfg.hour ?? 13);
			lab.setView(cfg.view ?? "player", cfg.anchor ?? "junction");
			await lab.applyParts(parts, false);
			await lab.surface.whenLayersReady();
			const tierAniso = ({ 0: 2, 1: 4, 2: 8 } as Record<number, number>)[lab.surface.tier];
			for (const texture of lab.scene.textures) {
				if (!texture.name.startsWith("terrain:") || texture.name.includes("cells/")) continue;
				const nro = texture.name.includes("_nro_");
				texture.anisotropicFilteringLevel = (nro ? cfg.anisoNro : undefined) ?? cfg.aniso ?? tierAniso;
			}
			await lab.ready();
			return { tier: lab.surface.tier, parts: lab.parts, probe: cfg.probe ?? null, aniso: cfg.aniso ?? null };
		},
		/** Per-frame GPU time over `seconds` after `warmup` seconds of the running render loop (ms; p50/p95). */
		async measure(opts: { seconds?: number; warmup?: number } = {}) {
			const seconds = opts.seconds ?? 10, warmup = opts.warmup ?? 2;
			const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
			await wait(warmup * 1000);
			const intervals: number[] = [], cpu: number[] = [];
			let last = 0, began = 0;
			const before = lab.scene.onBeforeRenderObservable.add(() => { began = performance.now(); });
			const after = lab.scene.onAfterRenderObservable.add(() => {
				const now = performance.now();
				if (last) intervals.push(now - last);
				cpu.push(now - began);
				last = now;
			});
			gpuTimer.start();
			const started = performance.now();
			await wait(seconds * 1000);
			const elapsed = performance.now() - started;
			const gpu = await gpuTimer.stop();
			lab.scene.onBeforeRenderObservable.remove(before);
			lab.scene.onAfterRenderObservable.remove(after);
			return { seconds: +(elapsed / 1000).toFixed(2), scope: gpuTimer.scope, gpu: summarize(gpu.samples), gpuRejected: gpu.rejected,
				frameInterval: summarize(intervals), cpuScene: summarize(cpu), drawCalls: lab.instrumentation.drawCallsCounter.current };
		},
		/**
		 * GPU-bound throughput (WebGL2 primary, WebGPU cross-check): the render loop is paused and `frames` frames are
		 * rendered back to back, closed by a 1-pixel readPixels sync; per-batch ms/frame (whole frame: shadow maps, main
		 * pass, resolve). WebGL2 TIME_ELAPSED readings proved unusable at this precision on this machine (bimodal,
		 * ~1.2 ms apart, drifting between identical runs), consistent with compositor work interleaving on ANGLE's
		 * shared D3D11 device.
		 */
		async throughput(opts: { seconds?: number; warmup?: number; frames?: number } = {}) {
			const seconds = opts.seconds ?? 10, warmup = opts.warmup ?? 2, frames = opts.frames ?? 10;
			engine.stopRenderLoop();
			const perFrame: number[] = [];
			const sync = () => engine.readPixels(0, 0, 1, 1, true, true);
			try {
				const warmEnd = performance.now() + warmup * 1000;
				while (performance.now() < warmEnd) { for (let i = 0; i < frames; i++) lab.renderFrame(); await sync(); }
				const end = performance.now() + seconds * 1000;
				while (performance.now() < end) {
					await sync();
					const t0 = performance.now();
					for (let i = 0; i < frames; i++) lab.renderFrame();
					await sync();
					perFrame.push((performance.now() - t0) / frames);
				}
			} finally {
				startLoop();
			}
			return { seconds, framesPerBatch: frames, batches: perFrame.length, msPerFrame: summarize(perFrame) };
		},
		/** Non-blank check of the current frame: share of pixels away from the clear colour, mean luminance, pixel hash. */
		async frameCheck() {
			const img = await lab.frame();
			const c = lab.scene.clearColor;
			const clear = [Math.round(c.r * 255), Math.round(c.g * 255), Math.round(c.b * 255)];
			let away = 0, lum = 0, hash = 2166136261;
			for (let k = 0; k < img.data.length; k += 4) {
				const r = img.data[k], g = img.data[k + 1], b = img.data[k + 2];
				if (Math.abs(r - clear[0]) + Math.abs(g - clear[1]) + Math.abs(b - clear[2]) > 12) away++;
				lum += 0.2126 * r + 0.7152 * g + 0.0722 * b;
				if ((k & 4095) === 0) hash = Math.imul(hash ^ (r << 16 | g << 8 | b), 16777619) >>> 0;
			}
			const n = img.width * img.height;
			return { width: img.width, height: img.height, nonClearShare: +(away / n).toFixed(4), meanLum: +(lum / n / 255).toFixed(4), sampleHash: hash.toString(16) };
		},
		/** WebGPU P0 checks for the terrain meshes: vertex buffers per draw, CSM receiver, shader language. */
		meshFacts() {
			const meshes = [lab.ground, lab.farParts[0], ...lab.rocks.slice(0, 2)];
			return {
				shadowGenerator: lab.shadows.getClassName(), cascades: (lab.shadows as unknown as { numCascades?: number }).numCascades ?? 1,
				meshes: meshes.map(m => ({ name: m.name, material: m.material?.name ?? null, vertexBuffers: m.getVerticesDataKinds(),
					instanced: m.hasThinInstances || m.instances.length > 0, receiveShadows: m.receiveShadows,
					language: (m.material as PBRMaterial | null)?.shaderLanguage === ShaderLanguage.WGSL ? "WGSL" : "GLSL" })),
			};
		},
		/** Pixel shares of the current view (cell ground / far ground / rocks / other / sky) from flat unlit colours. */
		async coverage() {
			const restore = lab.scene.clearColor.clone();
			lab.scene.clearColor = new Color4(0, 0, 0, 1);
			const fogMode = lab.scene.fogMode;
			lab.scene.fogMode = Scene.FOGMODE_NONE;
			const flat = (name: string, rgb: [number, number, number]) => {
				const m = new PBRMaterial(name, lab.scene);
				m.unlit = true; m.albedoColor = new Color3(rgb[0], rgb[1], rgb[2]); return m;
			};
			const mats = { ground: flat("cov-ground", [1, 0, 0]), far: flat("cov-far", [0, 1, 0]), rock: flat("cov-rock", [0, 0, 1]) };
			const saved = new Map<Mesh, Material | null>();
			const assign = (mesh: Mesh, m: Material) => { saved.set(mesh, mesh.material); mesh.material = m; };
			assign(lab.ground, mats.ground);
			for (const m of lab.farParts) assign(m, mats.far);
			for (const r of lab.rocks) assign(r, mats.rock);
			for (const m of Object.values(mats)) await m.forceCompilationAsync(lab.ground);
			await lab.scene.whenReadyAsync();
			for (let i = 0; i < 3; i++) lab.renderFrame();
			const img = await lab.frame();
			const counts = { ground: 0, far: 0, rock: 0, other: 0, sky: 0 };
			for (let k = 0; k < img.data.length; k += 4) {
				const r = img.data[k], g = img.data[k + 1], b = img.data[k + 2];
				if (r > 150 && g < 90 && b < 90) counts.ground++;
				else if (g > 150 && r < 90 && b < 90) counts.far++;
				else if (b > 150 && r < 90 && g < 90) counts.rock++;
				else if (r + g + b < 10) counts.sky++;
				else counts.other++;
			}
			for (const [mesh, m] of saved) mesh.material = m;
			for (const m of Object.values(mats)) m.dispose();
			lab.scene.clearColor = restore;
			lab.scene.fogMode = fogMode;
			await lab.ready();
			const total = img.width * img.height;
			return Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, +(v / total).toFixed(4)]));
		},
	};
	(window as unknown as { terrainLab: typeof api }).terrainLab = api;
	status.textContent = `terrain lab · ${renderer} · variant ${lab.variant} · tier ${lab.surface.tier} · hour ${lab.hour}`;
	status.dataset.ready = "1";
	// WebGL2: at most 3 frames in flight. With vsync and the frame-rate limit off (GPU timing protocol) the CPU otherwise
	// runs thousands of frames ahead of the GPU and TIME_ELAPSED readings stop matching the configuration being measured
	// (GPU cost study, WebGL2 baseline pass 1). WebGPU already blocks on the swap chain.
	const throttle = engine.isWebGPU ? null : new FrameThrottle((engine as unknown as { _gl: WebGL2RenderingContext })._gl, 3);
	function startLoop(): void {
		engine.runRenderLoop(() => {
			if (throttle && !throttle.ready()) return;
			lab.scene.render();
			throttle?.mark();
		});
	}
	startLoop();
}

/** Non-blocking frames-in-flight limit (fence polling; WebGL2 cannot block the CPU on a fence). */
class FrameThrottle {
	private fences: WebGLSync[] = [];
	constructor(private readonly gl: WebGL2RenderingContext, private readonly depth: number) {}
	ready(): boolean {
		while (this.fences.length >= this.depth) {
			const fence = this.fences[0];
			if (this.gl.getSyncParameter(fence, this.gl.SYNC_STATUS) !== this.gl.SIGNALED) return false;
			this.gl.deleteSync(fence);
			this.fences.shift();
		}
		return true;
	}
	mark(): void {
		const fence = this.gl.fenceSync(this.gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
		if (fence) { this.fences.push(fence); this.gl.flush(); }
	}
}

void main().catch(error => {
	const status = document.getElementById("status");
	if (status) { status.textContent = `terrain lab failed: ${String(error)}`; status.dataset.ready = "error"; }
	console.error(error);
});
