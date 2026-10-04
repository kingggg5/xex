import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { RawTexture } from "@babylonjs/core/Materials/Textures/rawTexture";
import { Constants } from "@babylonjs/core/Engines/constants";
import type { BaseTexture } from "@babylonjs/core/Materials/Textures/baseTexture";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import type { Material } from "@babylonjs/core/Materials/material";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import type { Scene } from "@babylonjs/core/scene";
import { BRANCH_EPS, CELL_M, CELL_N, FAR_DRY_SHARE, FAR_FADE, RUT, TIER0_NRO_MIN, TIER_ANISOTROPY, bakeCellMapRGBA, decodePng, resolveTier,
	type CellFieldKind, type TerrainTier } from "./terrain-surface-math.mjs";
import { createRockMaterial, type RockMaterialOptions } from "./terrain-rock-surface";

/**
 * Sunmeadow v2 terrain splat (terrain spec §3.6, §8.1-8.2): 4 world-space layers (lush, dry, dirt, mud/moss)
 * blended by height per 64 m cell, path-edge SDF breakup, analytic ruts and berm, anti-tiling, macro value/hue,
 * wetness and far fade. One PBR material per cell; layer textures and the compiled effect are shared.
 *
 * Weather contract (unchanged world-weather.ts:98-99): the legacy ground material keeps receiving
 * roughness = .94 - wet * .22 and albedoColor; every terrain material reads those in hardBindForSubMesh.
 *
 * Shader rules: GLSL and WGSL are generated from one template (parity by construction); derivatives are taken
 * once in uniform control flow and every fetch inside a weight branch is textureGrad / textureSampleGrad.
 * Samplers: 10 custom on a cell material (8 layer + splat + data), 2 on the far material.
 * GPU cost (P1 report §10): the macro value/hue field and the anti-tiling mask are baked into the cell maps' alpha
 * when the cell PNGs are decoded (no extra sampler); value noise, ruts, the berm and the far path run only where used.
 */

/** DEV debug views (spec §3.6); albedo / splat / data are raw probes (pre-lighting linear albedo, exact cell bytes). */
export type TerrainDebugMode = "off" | "weights" | "height" | "normal" | "rough" | "ao" | "sdf" | "tiling" | "mip" | "fetches" | "albedo" | "splat" | "data";
export const TERRAIN_DEBUG_MODES: readonly TerrainDebugMode[] = ["off", "weights", "height", "normal", "rough", "ao", "sdf", "tiling", "mip", "fetches", "albedo", "splat", "data"];

export interface TerrainLayerRecord {
	id: string; name: string; channel: string; tile_m: number;
	files: { ah: Record<string, string>; nro: Record<string, string> };
	packing: { ah: string[]; nro: string[] };
	albedoEncoding: "srgb-bytes-in-unorm";
	height_range_m: number;
	mean_linear_rgb: [number, number, number];
	mean_roughness: number;
	stats?: Record<string, unknown>;
	sha256?: Record<string, string>;
}
export interface TerrainCellRecord {
	bounds: [number, number, number, number];
	splat: Record<string, string>;
	data: Record<string, string>;
	sha256?: Record<string, string>;
}
export interface TerrainLayersetManifest {
	schema: "xexoria.terrain-layerset/1";
	albedoEncoding: "srgb-bytes-in-unorm";
	layers: TerrainLayerRecord[];
	relief: TerrainLayerRecord[];
	cells: Record<string, Record<string, TerrainCellRecord>>;
	tools?: Record<string, unknown>;
}
export interface TerrainProfileLike { preset: string }
export interface TerrainLook { normalStrength: number; edgeBreakup: number; cellAO: number }
/**
 * Look defaults. normalStrength 1.25 (P1 lab, GTX 1050, both renderers): at 1.0 only 53 % of ground pixels in the
 * player view had a world normal > 3 deg from up (spec §8.5 target >= 60 %; mip filtering of the 1024 layers flattens
 * distant normals); 1.25 gives 61 %, 1.5 gives 67 %. edgeBreakup is the §3.6 path-edge amplitude, cellAO the §3.6 mix.
 */
export const TERRAIN_LOOK_DEFAULTS: Readonly<TerrainLook> = Object.freeze({ normalStrength: 1.25, edgeBreakup: 0.9, cellAO: 0.75 });

export interface TerrainSurfaceOptions {
	profile: TerrainProfileLike;
	manifest: TerrainLayersetManifest;
	/** Maps a manifest path (relative to the terrain asset folder) to a URL. */
	resolveUrl(file: string): string;
	/** Weather source: the legacy shared ground material (env-shared-world-grass). */
	legacy?: PBRMaterial | null;
	/** Cell set to use from the manifest (default "v2"). */
	set?: string;
	debug?: TerrainDebugMode;
	/** DEV lab: one layer everywhere (0..3); ignored in production builds. */
	solo?: number;
	/** Test hook: build textures without network access. */
	createTexture?: (url: string, options: { invertY: boolean; srgb: boolean; onLoad: () => void; onError: (message?: string) => void }) => Texture;
	/**
	 * Bytes of a per-cell PNG (default: fetch). The cell maps are decoded here and the macro / anti-tiling fields are
	 * baked into their alpha. With createTexture and no loadBytes (unit tests) the maps load as plain textures and the
	 * shader computes those fields per pixel.
	 */
	loadBytes?: (url: string) => Promise<ArrayBuffer | Uint8Array>;
}

export interface TerrainMemoryEstimate {
	mib: number; layersMiB: number; cellsMiB: number; reliefMiB: number; residentCells: number;
	basis: string; compressed: boolean;
}

export interface TerrainSurface {
	readonly tier: TerrainTier;
	readonly farMaterial: PBRMaterial;
	readonly decalMaterial: null;
	materialForCell(id: string): PBRMaterial;
	/** Terrain material when every texture loads, otherwise the legacy material (warns); never rejects. */
	resolveCellMaterial(id: string): Promise<Material>;
	whenCellReady(id: string): Promise<boolean>;
	rockMaterial(slot: string, cellId?: string, options?: Partial<RockMaterialOptions>): PBRMaterial;
	retainCell(id: string): void;
	releaseCell(id: string): void;
	setQuality(profile: TerrainProfileLike): void;
	memoryEstimate(): TerrainMemoryEstimate;
	debug(mode: TerrainDebugMode): void;
	/** DEV lab only: show one layer everywhere (0..3) or the splat (null). */
	solo(layer: number | null): void;
	/** DEV lab only: GPU cost probe on every cell material (null = production code). */
	probe(probe: TerrainProbe | null): void;
	/** Look knobs shared by every terrain material (normal strength, path edge breakup, cell AO mix). */
	setLook(look: Partial<TerrainLook>): void;
	/** Resolves true once the current shared layer set (AH + NRO x 4) has loaded. */
	whenLayersReady(): Promise<boolean>;
	cellIds(): string[];
	dispose(): void;
}

const LAYER_SAMPLERS = ["terrainLushAH", "terrainLushNRO", "terrainDryAH", "terrainDryNRO", "terrainDirtAH", "terrainDirtNRO", "terrainMudAH", "terrainMudNRO"] as const;
const CELL_SAMPLERS = ["terrainCellSplat", "terrainCellData"] as const;
export const TERRAIN_CELL_SAMPLERS: readonly string[] = [...LAYER_SAMPLERS, ...CELL_SAMPLERS];
export const TERRAIN_FAR_SAMPLERS: readonly string[] = ["terrainLushAH", "terrainDryAH"];
export const TERRAIN_UNIFORMS = ["terrainCell", "terrainCellRes", "terrainTile", "terrainHScale", "terrainHBias", "terrainBlend",
	"terrainRut", "terrainWeather", "terrainMean0", "terrainMean1", "terrainMean2", "terrainMean3", "terrainLook"] as const;
const DRY_TINT = [0.914, 0.941, 0.863] as const;

// ----------------------------------------------------------------------------
// Shader generation (one template, two languages)
// ----------------------------------------------------------------------------

/**
 * DEV-only GPU cost probe (terrain lab, P1 report §10): code-generation switches that remove one feature, change the
 * fetch instruction or try a look-changing candidate, so the lab can time each with GPU timers. The default (no probe)
 * is the production shader. A probe gets its own TERRAIN_PROBE define value, so Babylon compiles it as a separate
 * effect. createTerrainSurface ignores probes in production builds, exactly like the debug views.
 */
export interface TerrainProbe {
	/** grad = textureSampleGrad / textureGrad (production); implicit = textureSample / texture (forces uncond: WGSL
	 * forbids implicit derivatives in non-uniform control flow); level = textureSampleLevel / textureLod at the isotropic
	 * LOD of the same gradients (no anisotropy). */
	sample?: "grad" | "implicit" | "level";
	/** Remove the far and per-layer weight branches: every fetch runs. */
	uncond?: boolean;
	noAnti?: boolean; noEdge?: boolean; noHBlend?: boolean; noMacro?: boolean; noNro?: boolean; noRut?: boolean;
	/** P1 noise placement: every value-noise call per pixel in uniform flow (macro, mask, edge, rut wander). */
	p1Noise?: boolean;
	/** Candidate (changes the image): anti-tiling mask gain K (production 2); K > 2.2 lets the mask alone decide over
	 * part of the area, where only one AH and one NRO sample are fetched. */
	antiK?: number;
	/** Candidate (changes the image): one anti-tiling NRO sample per layer (A where t < 0.5, else B). */
	nroSelect?: boolean;
	/** Candidate (changes the image): NRO detail fades out over [nroFade, nroFade + 6] m from the eye. 0 = off. */
	nroFade?: number;
	/** Exact layer cull (identical image; measured neutral to slightly slower, so production keeps the P1 rule of
	 * fetching every layer with w > 0.004): "early" skips layers that cannot win the height blend. */
	cull?: "early" | "none";
}
type Probe = Required<TerrainProbe>;
const NO_PROBE: Probe = Object.freeze({ sample: "grad", uncond: false, noAnti: false, noEdge: false, noHBlend: false, noMacro: false,
	noNro: false, noRut: false, p1Noise: false, antiK: 2, nroSelect: false, nroFade: 0, cull: "none" });
const PROBE_FLAGS = ["uncond", "noAnti", "noEdge", "noHBlend", "noMacro", "noNro", "noRut", "p1Noise", "nroSelect"] as const;

function normaliseProbe(probe: TerrainProbe | null | undefined): Probe {
	if (!probe) return NO_PROBE;
	const sample = probe.sample === "implicit" || probe.sample === "level" ? probe.sample : "grad";
	const out: Probe = { ...NO_PROBE, sample, cull: probe.cull === "early" ? "early" : "none" };
	for (const flag of PROBE_FLAGS) out[flag] = probe[flag] === true;
	const num = (v: unknown, fallback: number, min: number) => (typeof v === "number" && Number.isFinite(v) && v >= min ? v : fallback);
	out.antiK = num(probe.antiK, 2, 2);
	out.nroFade = num(probe.nroFade, 0, 0);
	// implicit derivatives are only valid in uniform control flow (WGSL uniformity analysis)
	if (out.sample === "implicit") out.uncond = true;
	return out;
}
const probeKey = (p: Probe): string => [p.sample, ...(p.cull !== "none" ? [`cull-${p.cull}`] : []), ...PROBE_FLAGS.filter(flag => p[flag]),
	...(p.antiK !== 2 ? [`k${p.antiK}`] : []), ...(p.nroFade > 0 ? [`fade${p.nroFade}`] : [])].join("+");
const PROBE_IDS = new Map<string, number>([[probeKey(NO_PROBE), 0]]);
/** Stable small define value per probe (0 = production code). */
export function terrainProbeId(probe: TerrainProbe | null | undefined): number {
	const key = probeKey(normaliseProbe(probe));
	let id = PROBE_IDS.get(key);
	if (id === undefined) { id = PROBE_IDS.size; PROBE_IDS.set(key, id); }
	return id;
}

interface Lang {
	wgsl: boolean; f: string; v2: string; v3: string; v4: string; pos: string; eye: string;
	u(name: string): string;
	decl(type: string, name: string, expr: string): string;
	grad(tex: string, uv: string, dx: string, dy: string): string;
	sample(tex: string, uv: string): string;
	level(tex: string, uv: string, dx: string, dy: string): string;
	dx(e: string): string;
	dy(e: string): string;
	lin(e: string): string;
}

function lang(wgsl: boolean): Lang {
	return wgsl ? {
		wgsl, f: "f32", v2: "vec2f", v3: "vec3f", v4: "vec4f", pos: "fragmentInputs.vPositionW", eye: "scene.vEyePosition.xyz",
		u: n => `uniforms.${n}`,
		decl: (t, n, e) => `var ${n}: ${t} = ${e};`,
		grad: (tex, uv, dx, dy) => `textureSampleGrad(${tex}, ${tex}Sampler, ${uv}, ${dx}, ${dy})`,
		sample: (tex, uv) => `textureSample(${tex}, ${tex}Sampler, ${uv})`,
		level: (tex, uv, dx, dy) => `textureSampleLevel(${tex}, ${tex}Sampler, ${uv}, terrainLod(${dx}, ${dy}, vec2f(textureDimensions(${tex}))))`,
		dx: e => `dpdx(${e})`, dy: e => `dpdy(${e})`,
		lin: e => `toLinearSpaceVec3(${e})`,
	} : {
		wgsl, f: "float", v2: "vec2", v3: "vec3", v4: "vec4", pos: "vPositionW", eye: "vEyePosition.xyz",
		u: n => n,
		decl: (t, n, e) => `${t} ${n} = ${e};`,
		grad: (tex, uv, dx, dy) => `textureGrad(${tex}, ${uv}, ${dx}, ${dy})`,
		sample: (tex, uv) => `texture(${tex}, ${uv})`,
		level: (tex, uv, dx, dy) => `textureLod(${tex}, ${uv}, terrainLod(${dx}, ${dy}, vec2(textureSize(${tex}, 0))))`,
		dx: e => `dFdx(${e})`, dy: e => `dFdy(${e})`,
		lin: e => `toLinearSpace(${e})`,
	};
}

/** Fetch expression for the probe's instruction (production: explicit gradients). */
function fetchWith(L: Lang, o: Probe, tex: string, uv: string, dx: string, dy: string): string {
	return o.sample === "implicit" ? L.sample(tex, uv) : o.sample === "level" ? L.level(tex, uv, dx, dy) : L.grad(tex, uv, dx, dy);
}

function definitions(L: Lang, o: Probe): string {
	const samplers = (names: readonly string[]) => names.map(n => L.wgsl
		? `var ${n}Sampler: sampler;\nvar ${n}: texture_2d<f32>;` : `uniform sampler2D ${n};`).join("\n");
	const lod = o.sample !== "level" ? "" : L.wgsl ? `
fn terrainLod(dx: vec2f, dy: vec2f, size: vec2f) -> f32 {
	let a = dx * size;
	let b = dy * size;
	return 0.5 * log2(max(max(dot(a, a), dot(b, b)), 1e-8));
}` : `
float terrainLod(vec2 dx, vec2 dy, vec2 size) {
	vec2 a = dx * size;
	vec2 b = dy * size;
	return 0.5 * log2(max(max(dot(a, a), dot(b, b)), 1e-8));
}`;
	// Value noise (spec §3.6: hash-based, no sin).
	// - terrainVN (path-edge and rut-wander noise, GPU only): Dave Hoskins' hash12 at the four lattice corners with the
	//   per-axis terms shared: p3 = (a, b, a), a = fract(x * 0.1031), b = fract(y * 0.1031), so dot(p3, p3.yzx + 33.33) =
	//   2ab + a^2 + 66.66a + 33.33b and hash = fract((a + b + 2d) (a + d)); same hash as P1, about a third fewer operations.
	// - terrainVNx (macro and anti-tiling mask: baked on the CPU for cells, evaluated here by the far material and the
	//   unbaked fallback): exact permutation hash, so the GPU and terrain-surface-math.mjs valueNoiseExact agree
	//   (no seam between a baked cell and the far ground).
	const fns = L.wgsl ? `
fn terrainVN(p: vec2f) -> f32 {
	let i = floor(p);
	let f = p - i;
	let w = f * f * (vec2f(3.0) - 2.0 * f);
	let a = fract(vec2f(i.x, i.x + 1.0) * 0.1031);
	let b = fract(vec2f(i.y, i.y + 1.0) * 0.1031);
	let ka = a * (a + vec2f(66.66));
	let kb = b * 33.33;
	let d = vec4f(2.0 * a.x * b.x + ka.x + kb.x, 2.0 * a.y * b.x + ka.y + kb.x, 2.0 * a.x * b.y + ka.x + kb.y, 2.0 * a.y * b.y + ka.y + kb.y);
	let ax = vec4f(a.x, a.y, a.x, a.y);
	let h = fract((ax + vec4f(b.x, b.x, b.y, b.y) + 2.0 * d) * (ax + d));
	return mix(mix(h.x, h.y, w.x), mix(h.z, h.w, w.x), w.y);
}
fn terrainMod289(x: vec4f) -> vec4f { return x - 289.0 * floor((x + vec4f(0.5)) * (1.0 / 289.0)); }
fn terrainVNx(p: vec2f) -> f32 {
	let i = floor(p);
	let f = p - i;
	let w = f * f * (vec2f(3.0) - 2.0 * f);
	let m = terrainMod289(vec4f(i.x, i.x + 1.0, i.y, i.y + 1.0));
	let px = terrainMod289((34.0 * m + vec4f(1.0)) * m);
	var s = vec4f(px.x, px.y, px.x, px.y) + vec4f(m.z, m.z, m.w, m.w);
	s = s - 289.0 * step(vec4f(289.0), s);
	let h = terrainMod289((34.0 * s + vec4f(1.0)) * s) * (1.0 / 289.0);
	return mix(mix(h.x, h.y, w.x), mix(h.z, h.w, w.x), w.y);
}
fn terrainSlope(nro: vec4f) -> vec2f {
	let n = nro.xy * 2.0 - vec2f(1.0);
	return n * inverseSqrt(max(1.0 - dot(n, n), 0.04));
}
fn terrainUnrotate(p: vec2f) -> vec2f { return vec2f(0.8 * p.x + 0.6 * p.y, -0.6 * p.x + 0.8 * p.y); }
fn terrainRotate(p: vec2f) -> vec2f { return vec2f(0.8 * p.x - 0.6 * p.y, 0.6 * p.x + 0.8 * p.y); }
var<private> terrainRough: f32 = 0.9;
var<private> terrainDebugOut: vec3f = vec3f(0.0);${lod}` : `
float terrainVN(vec2 p) {
	vec2 i = floor(p);
	vec2 f = p - i;
	vec2 w = f * f * (3.0 - 2.0 * f);
	vec2 a = fract(vec2(i.x, i.x + 1.0) * 0.1031);
	vec2 b = fract(vec2(i.y, i.y + 1.0) * 0.1031);
	vec2 ka = a * (a + 66.66);
	vec2 kb = b * 33.33;
	vec4 d = vec4(2.0 * a.x * b.x + ka.x + kb.x, 2.0 * a.y * b.x + ka.y + kb.x, 2.0 * a.x * b.y + ka.x + kb.y, 2.0 * a.y * b.y + ka.y + kb.y);
	vec4 ax = vec4(a.x, a.y, a.x, a.y);
	vec4 h = fract((ax + vec4(b.x, b.x, b.y, b.y) + 2.0 * d) * (ax + d));
	return mix(mix(h.x, h.y, w.x), mix(h.z, h.w, w.x), w.y);
}
vec4 terrainMod289(vec4 x) { return x - 289.0 * floor((x + 0.5) * (1.0 / 289.0)); }
float terrainVNx(vec2 p) {
	vec2 i = floor(p);
	vec2 f = p - i;
	vec2 w = f * f * (3.0 - 2.0 * f);
	vec4 m = terrainMod289(vec4(i.x, i.x + 1.0, i.y, i.y + 1.0));
	vec4 px = terrainMod289((34.0 * m + 1.0) * m);
	vec4 s = vec4(px.x, px.y, px.x, px.y) + vec4(m.z, m.z, m.w, m.w);
	s = s - 289.0 * step(vec4(289.0), s);
	vec4 h = terrainMod289((34.0 * s + 1.0) * s) * (1.0 / 289.0);
	return mix(mix(h.x, h.y, w.x), mix(h.z, h.w, w.x), w.y);
}
vec2 terrainSlope(vec4 nro) {
	vec2 n = nro.xy * 2.0 - 1.0;
	return n * inversesqrt(max(1.0 - dot(n, n), 0.04));
}
vec2 terrainUnrotate(vec2 p) { return vec2(0.8 * p.x + 0.6 * p.y, -0.6 * p.x + 0.8 * p.y); }
vec2 terrainRotate(vec2 p) { return vec2(0.8 * p.x - 0.6 * p.y, 0.6 * p.x + 0.8 * p.y); }
float terrainRough = 0.9;
vec3 terrainDebugOut = vec3(0.0);${lod}`;
	return `
#if defined(TERRAIN_SPLAT) || defined(TERRAIN_FAR)
${fns}
#endif
#ifdef TERRAIN_SPLAT
${samplers(TERRAIN_CELL_SAMPLERS)}
#endif
#ifdef TERRAIN_FAR
${samplers(TERRAIN_FAR_SAMPLERS)}
#endif`;
}

/**
 * Cell body (spec §3.6). Cost rules from the GPU study (P1 report §10, GTX 1050): every fetch inside a weight branch uses
 * explicit gradients taken once in uniform flow (unconditional implicit sampling measured slower on both renderers);
 * value noise runs only where its result is used (macro and anti-tiling mask come from the cell maps' alpha; path-edge
 * noise only inside the edge band, rut wander only on rutted texels); work whose weight is zero is skipped.
 */
function cellBody(L: Lang, o: Probe): string {
	const { f, v2, v3, v4, u } = L;
	const d = L.decl;
	const tile = (c: string) => `${u("terrainTile")}.${c}`;
	const lines: string[] = [];
	const push = (s: string) => lines.push(s);
	const fetch = (tex: string, uv: string, dx: string, dy: string) => fetchWith(L, o, tex, uv, dx, dy);
	// probe uncond turns every weight / far branch into a plain block (all fetches run)
	const open = (cond: string) => (o.uncond ? "{" : `if (${cond}) {`);
	const lin = (v: string) => `${v} = ${v4}(${L.lin(`${v}.rgb`)}, ${v}.a);`;
	// macro value/hue (spec §3.6 step 4) from the scalar tM2, evaluated where it is used (short live ranges)
	const macro = o.noMacro ? `${v3}(1.0)` : `(mix(${v3}(0.97, 1.0, 1.04), ${v3}(1.04, 1.0, 0.94), smoothstep(0.35, 0.75, tM2)) * mix(0.90, 1.08, tM2))`;
	// --- uniform control flow: derivatives, cell maps ---
	push(d(v2, "tXZ", `${L.pos}.xz`));
	push(d(v2, "tDx", L.dx("tXZ")));
	push(d(v2, "tDy", L.dy("tXZ")));
	push(d(f, "tDist", `length(${L.eye} - ${L.pos})`));
	push(d(f, "tFar", `smoothstep(${u("terrainBlend")}.z, ${u("terrainBlend")}.w, tDist)`));
	push(d(v2, "tCellUV", `(tXZ - ${u("terrainCell")}.xy) * ${u("terrainCell")}.z + ${v2}(${u("terrainCell")}.w)`));
	push(d(v2, "tCellDx", `tDx * ${u("terrainCell")}.z`));
	push(d(v2, "tCellDy", `tDy * ${u("terrainCell")}.z`));
	push(d(v4, "tSplat", fetch("terrainCellSplat", "tCellUV", "tCellDx", "tCellDy")));
	push(d(v4, "tData", fetch("terrainCellData", "tCellUV", "tCellDx", "tCellDy")));
	push(d(v4, "tW", `${v4}(tSplat.r, tSplat.g, tSplat.b, max(0.0, 1.0 - tSplat.r - tSplat.g - tSplat.b))`));
	// DEV lab ?layer=0..3: one layer everywhere (TERRAIN_SOLO = layer + 1), no path breakup
	push(`#ifdef TERRAIN_SOLO\n#if TERRAIN_SOLO == 1\ntW = ${v4}(1.0, 0.0, 0.0, 0.0);\n#elif TERRAIN_SOLO == 2\ntW = ${v4}(0.0, 1.0, 0.0, 0.0);\n#elif TERRAIN_SOLO == 3\ntW = ${v4}(0.0, 0.0, 1.0, 0.0);\n#else\ntW = ${v4}(0.0, 0.0, 0.0, 1.0);\n#endif\n#endif`);
	push(d(f, "tSdf", `tData.r * 6.0 - 2.0`));
	push(d(f, "tRutV", `tData.g * 255.0`));
	push(d(f, "tRutL", `tRutV / 254.0 * 6.0 - 3.0`));
	push(d(f, "tCellAO", `tData.b`));
	// macro value/hue M2 (31 m + 13 m) and the 7.3 m anti-tiling mask: baked into the cell maps' alpha at load time
	// (TERRAIN_NOISE_MAPS, terrain-surface-math.mjs macroField / antiTilingMaskField), per pixel otherwise
	push(o.p1Noise ? `${d(f, "tM2", "0.65 * terrainVNx(tXZ * (1.0 / 31.0)) + 0.35 * terrainVNx(tXZ * (1.0 / 13.0))")}
${d(f, "tMaskN", "terrainVNx(tXZ * (1.0 / 7.3))")}
${d(f, "tN1", "terrainVN(tXZ * 1.3)")}
${d(f, "tN2", "terrainVN(tXZ * 3.1)")}
${d(f, "tWander", `terrainVN(tXZ * ${RUT.wanderFreq.toFixed(2)})`)}` : `#ifdef TERRAIN_NOISE_MAPS
${d(f, "tM2", "tSplat.a")}
${d(f, "tMaskN", "tData.a")}
#else
${d(f, "tM2", "0.65 * terrainVNx(tXZ * (1.0 / 31.0)) + 0.35 * terrainVNx(tXZ * (1.0 / 13.0))")}
${d(f, "tMaskN", "terrainVNx(tXZ * (1.0 / 7.3))")}
#endif`);
	push(d(v2, "tUV0", `tXZ * ${tile("x")}`));
	push(d(v2, "tUV1", `tXZ * ${tile("y")}`));
	push(d(v2, "tUV2", `tXZ * ${tile("z")}`));
	push(d(v2, "tUV3", `tXZ * ${tile("w")}`));
	push(d(f, "tBand", `1.0 - smoothstep(0.5, 0.7, abs(tSdf))`));
	push(`#ifdef TERRAIN_SOLO\ntBand = 0.0;\n#endif`);
	// --- outputs with far-path defaults (an unfetched layer keeps AH 0.5 and has blend weight 0) ---
	push(d(v4, "tAH0", `${v4}(0.5, 0.5, 0.5, 0.5)`));
	push(d(v4, "tAH1", `${v4}(0.5, 0.5, 0.5, 0.5)`));
	push(d(v4, "tAH2", `${v4}(0.5, 0.5, 0.5, 0.5)`));
	push(d(v4, "tAH3", `${v4}(0.5, 0.5, 0.5, 0.5)`));
	push(d(v4, "tB", "tW"));
	push(d(v2, "tP", `${v2}(0.0)`));
	push(d(f, "tRoughGrass", "0.0"));
	push(d(f, "tRoughSoil", "0.0"));
	push(d(f, "tLayerAO", "1.0"));
	push(d(f, "tT0", "0.0"));
	push(d(f, "tT1", "0.0"));
	push(d(f, "tFetches", "2.0"));
	push(d(v3, "tNearAlbedo", `${v3}(0.0)`));
	push(d(f, "tH", "0.5"));
	push(d(f, "tRutMask", "0.0"));
	push(d(v2, "tAnalytic", `${v2}(0.0)`));
	if (o.nroFade > 0) push(d(f, "tNroFade", `1.0 - smoothstep(${o.nroFade.toFixed(1)}, ${(o.nroFade + 6).toFixed(1)}, tDist)`));
	// anti-tiling (spec §3.6 step 3): sample A at uv, B at R uv + (0.37, 0.71), t from the 7.3 m mask and the height
	// difference; the mask term gain is 2 (probe antiK > 2.2 lets the mask alone decide, then only A or only B is fetched)
	const mask = (i: number) => (i === 0 ? "tMaskN" : "1.0 - tMaskN");
	const antiAH = (i: number, tex: string, uv: string, tl: string, minTier: number) => {
		const a = fetch(tex, uv, `tDx * ${tl}`, `tDy * ${tl}`);
		const b = fetch(tex, `terrainRotate(${uv}) + ${v2}(0.37, 0.71)`, `terrainRotate(tDx * ${tl})`, `terrainRotate(tDy * ${tl})`);
		if (o.noAnti) return `tAH${i} = ${a};`;
		const t = `tT${i}`;
		if (o.antiK <= 2.2) return `tAH${i} = ${a};
#if TERRAIN_TIER >= ${minTier}
${d(v4, `tAH${i}B`, b)}
${t} = clamp((smoothstep(0.3, 0.7, ${mask(i)}) - 0.5) * 2.0 + (tAH${i}B.a - tAH${i}.a) * 1.2 + 0.5, 0.0, 1.0);
tAH${i} = mix(tAH${i}, tAH${i}B, ${t});
tFetches = tFetches + 1.0;
#endif`;
		// |1.2 (hB - hA)| <= 1.2: below -1.2 the blend is all A, above 2.2 all B, whatever the heights
		const k = o.antiK.toFixed(2);
		return `#if TERRAIN_TIER >= ${minTier}
${d(f, `tMk${i}`, `(smoothstep(0.3, 0.7, ${mask(i)}) - 0.5) * ${k} + 0.5`)}
${d(v4, `tAH${i}B`, `${v4}(0.5)`)}
if (tMk${i} < 2.2) { tAH${i} = ${a}; }
if (tMk${i} > -1.2) { tAH${i}B = ${b}; tFetches = tFetches + 1.0; }
${t} = clamp(tMk${i} + (tAH${i}B.a - tAH${i}.a) * 1.2, 0.0, 1.0);
if (tMk${i} >= 2.2) { ${t} = 1.0; }
if (tMk${i} <= -1.2) { ${t} = 0.0; }
tAH${i} = mix(tAH${i}, tAH${i}B, ${t});
#else
tAH${i} = ${a};
#endif`;
	};
	// NRO (spec §3.6 normals): per layer with blend weight > tNroMin; anti-tiled layers fetch A only where t < 1 and B
	// only where t > 0 (production: identical result, fewer fetches; probe nroSelect: exactly one of them)
	const nro = (i: number, tex: string, uv: string, tl: string, w: string, isGrass: boolean, antiTier: number | null) => {
		const rough = isGrass ? "tRoughGrass" : "tRoughSoil";
		const mean = `${rough} = ${rough} + ${w} * ${u(`terrainMean${i}`)}.w;`;
		if (o.noNro) return mean;
		const cond = o.nroFade > 0 ? `${w} > tNroMin && tNroFade > 0.0` : `${w} > tNroMin`;
		const wf = o.nroFade > 0 ? `${w} * tNroFade` : w;
		const fadeMean = o.nroFade > 0 ? `\n\t${rough} = ${rough} + ${w} * (1.0 - tNroFade) * ${u(`terrainMean${i}`)}.w;` : "";
		const fa = fetch(tex, uv, `tDx * ${tl}`, `tDy * ${tl}`);
		const fb = fetch(tex, `terrainRotate(${uv}) + ${v2}(0.37, 0.71)`, `terrainRotate(tDx * ${tl})`, `terrainRotate(tDy * ${tl})`);
		const t = `tT${i}`;
		const pair = antiTier === null || o.noAnti ? `${d(v4, `tNL${i}`, fa)}
	${d(v2, `tPL${i}`, `terrainSlope(tNL${i})`)}
	tFetches = tFetches + 1.0;` : o.nroSelect ? `${d(v4, `tNL${i}`, `${v4}(0.0)`)}
	${d(v2, `tPL${i}`, `${v2}(0.0)`)}
	if (${t} < 0.5) {
		tNL${i} = ${fa};
		tPL${i} = terrainSlope(tNL${i});
	} else {
		tNL${i} = ${fb};
		tPL${i} = terrainUnrotate(terrainSlope(tNL${i}));
	}
	tFetches = tFetches + 1.0;` : `${d(v4, `tNL${i}`, `${v4}(0.0)`)}
	${d(v2, `tPL${i}`, `${v2}(0.0)`)}
	${open(`${t} < 1.0`)}
		tNL${i} = ${fa};
		tPL${i} = terrainSlope(tNL${i});
		tFetches = tFetches + 1.0;
	}
#if TERRAIN_TIER >= ${antiTier}
	${open(`${t} > 0.0`)}
		${d(v4, `tNB${i}`, fb)}
		tPL${i} = mix(tPL${i}, terrainUnrotate(terrainSlope(tNB${i})), ${t});
		tNL${i} = mix(tNL${i}, tNB${i}, ${t});
		tFetches = tFetches + 1.0;
	}
#endif`;
		return `${open(cond)}
	${pair}
	tP = tP + ${wf} * tPL${i};
	${rough} = ${rough} + ${wf} * tNL${i}.b;${fadeMean}
	tLayerAO = tLayerAO - ${wf} * (1.0 - tNL${i}.a);
${o.uncond ? "}" : `} else {\n\t${mean}\n}`}`;
	};
	const edgeNoise = o.p1Noise ? "0.55 * tN1 + 0.25 * tN2" : "0.55 * terrainVN(tXZ * 1.3) + 0.25 * terrainVN(tXZ * 3.1)";
	const dirtFetch = `tAH2 = ${fetch("terrainDirtAH", "tUV2", `tDx * ${tile("z")}`, `tDy * ${tile("z")}`)};
	${lin("tAH2")}
	tFetches = tFetches + 1.0;`;
	// path-edge breakup (spec §3.6 step 2), only inside the |d| < 0.7 m band (tBand > 0); it needs the dirt height
	const edge = o.noEdge ? d(f, "tDirtW", "tW.z") : `${d(f, "tDirtW", "tW.z")}
if (tBand > 0.0) {
	${d(f, "tEdgeN", `${edgeNoise} + 0.2 * (2.0 * tAH2.a - 1.0)`)}
	tDirtW = max(0.0, tW.z + (tEdgeN - 0.5) * ${u("terrainLook")}.y * tBand);
}`;
	// Exact layer cull (DEV probe cull: "early"; identical image): with heights in [0, 1], layer i can only get a blend
	// weight b_i > 0 if its best case (height 1) beats the other layers' worst case (height 0) minus delta, so such
	// layers need not be fetched (lab cell: 1.79 -> 1.49 layers per texel outside the edge band). Measured on the GTX 1050
	// it does not pay for its tests (WebGPU +0.03 ms, WebGL2 +0.10 ms at 1080p; tested after the edge breakup instead it
	// cost +0.55 / +0.21 ms because every fetch then waits for it), so production fetches every layer with w > 0.004.
	const early = !o.noHBlend && o.cull === "early";
	const vlim = (w: string, pick: "max" | "min") => `${w} + ${u("terrainBlend")}.x * ${pick}(${u("terrainHScale")} + ${u("terrainHBias")}, ${u("terrainHBias")}) * smoothstep(${v4}(0.0), ${v4}(0.3), ${w})`;
	const bool = L.wgsl ? "let" : "bool";
	const keepEarly = !early ? "" : `
${d(v4, "tVhi", vlim("tW", "max"))}
${d(v4, "tVlo", vlim("tW", "min"))}
${d(v4, "tVoth", `${v4}(max(tVlo.y, max(tVlo.z, tVlo.w)), max(tVlo.x, max(tVlo.z, tVlo.w)), max(tVlo.x, max(tVlo.y, tVlo.w)), max(tVlo.x, max(tVlo.y, tVlo.z))) - ${v4}(${u("terrainBlend")}.y + 1e-4)`)}
${bool} tC0 = tBand > 0.0 || tVhi.x > tVoth.x;
${bool} tC1 = tBand > 0.0 || tVhi.y > tVoth.y;
${bool} tC2 = tBand > 0.0 || tVhi.z > tVoth.z;
${bool} tC3 = tBand > 0.0 || tVhi.w > tVoth.w;`;
	const kept = (i: number) => (early ? ` && tC${i}` : "");
	const blend = o.noHBlend ? `tB = tW2;` : `${d(v4, "tV", `tW2 + ${u("terrainBlend")}.x * (${v4}(tAH0.a, tAH1.a, tAH2.a, tAH3.a) * ${u("terrainHScale")} + ${u("terrainHBias")}) * smoothstep(${v4}(0.0), ${v4}(0.3), tW2)`)}
${d(f, "tMx", `max(max(tV.x, tV.y), max(tV.z, tV.w)) - ${u("terrainBlend")}.y`)}
tB = max(tV - ${v4}(tMx), ${v4}(0.0));
tB = tB / max(dot(tB, ${v4}(1.0)), 1e-5);`;
	const dirtCond = o.noEdge ? `tW.z > ${BRANCH_EPS}${kept(2)}` : early ? `tBand > 0.0 || (tW.z > ${BRANCH_EPS}${kept(2)})` : `tW.z > ${BRANCH_EPS} || tBand > 0.0`;
	// each fetched AH is linearised once (sRGB bytes in UNORM); unfetched layers have blend weight 0
	push(`${open("tFar < 0.999")}${keepEarly}
${open(`tW.x > ${BRANCH_EPS}${kept(0)}`)}
	${antiAH(0, "terrainLushAH", "tUV0", tile("x"), 1)}
	${lin("tAH0")}
	tFetches = tFetches + 1.0;
}
${open(`tW.y > ${BRANCH_EPS}${kept(1)}`)}
	${antiAH(1, "terrainDryAH", "tUV1", tile("y"), 2)}
	${lin("tAH1")}
	tFetches = tFetches + 1.0;
}
${open(dirtCond)}
	${dirtFetch}
}
${open(`tW.w > ${BRANCH_EPS}${kept(3)}`)}
	tAH3 = ${fetch("terrainMudAH", "tUV3", `tDx * ${tile("w")}`, `tDy * ${tile("w")}`)};
	${lin("tAH3")}
	tFetches = tFetches + 1.0;
}
${edge}
${d(v4, "tW2", `${v4}(tW.x, tW.y, tDirtW, tW.w)`)}
tW2 = tW2 / max(dot(tW2, ${v4}(1.0)), 1e-5);
${blend}
tH = dot(tB, ${v4}(tAH0.a, tAH1.a, tAH2.a, tAH3.a));
tNearAlbedo = (tB.x * tAH0.rgb + tB.y * tAH1.rgb) * ${macro} + tB.z * tAH2.rgb + tB.w * tAH3.rgb;
${nro(0, "terrainLushNRO", "tUV0", tile("x"), "tB.x", true, 1)}
${nro(1, "terrainDryNRO", "tUV1", tile("y"), "tB.y", true, 2)}
${nro(2, "terrainDirtNRO", "tUV2", tile("z"), "tB.z", false, null)}
${nro(3, "terrainMudNRO", "tUV3", tile("w"), "tB.w", false, null)}
}`);
	// screen derivatives of the decoded SDF and rut coordinate: here, after the near block, control flow is uniform again
	// (WGSL); the world-gradient solve runs only where a rut or the berm uses it
	push(d(v2, "tSdfS", `${v2}(${L.dx("tSdf")}, ${L.dy("tSdf")})`));
	push(d(v2, "tRutS", `${v2}(${L.dx("tRutL")}, ${L.dy("tRutL")})`));
	// --- analytic ruts and berm (normal only) ---
	const solve = (g: string, s: string) => `${d(f, "tDet", "tDx.x * tDy.y - tDx.y * tDy.x")}
	${d(v2, g, `${v2}(tDy.y * ${s}.x - tDx.y * ${s}.y, -tDy.x * ${s}.x + tDx.x * ${s}.y) * (tDet / max(tDet * tDet, 1e-20))`)}`;
	if (!o.noRut) {
		// The lateral coordinate L is distance-like (|grad L| = 1). Where the map cuts it off (3 m junction fades, the edge
		// of a rutted path's region) bilinear filtering ramps L to the 255 sentinel inside one texel: that ramp crosses the
		// rut centres and has |grad L| >> 1, which drew phantom rut lines (P1 lab pass 1). Gate on |grad L|. Only texels
		// with rut data (L < 255, |L| < 1.3 m) run any of it.
		const rut: string[] = [];
		rut.push(solve("tRutG", "tRutS"));
		rut.push(d(f, "tRutL2", `tRutL + ${u("terrainRut")}.w * (2.0 * ${o.p1Noise ? "tWander" : `terrainVN(tXZ * ${RUT.wanderFreq.toFixed(2)})`} - 1.0)`));
		rut.push(d(f, "tRutValid", `(1.0 - smoothstep(1.15, 1.3, abs(tRutL))) * (1.0 - smoothstep(1.6, 2.6, length(tRutG)))`));
		rut.push(d(f, "tRutDirt", `smoothstep(0.35, 0.8, tB.z)`));
		for (const side of [1, -1]) {
			const s = side > 0 ? "P" : "M";
			rut.push(d(f, `tRutS${s}`, `(tRutL2 - (${side.toFixed(1)}) * ${u("terrainRut")}.x) / ${u("terrainRut")}.y`));
			rut.push(d(f, `tRutQ${s}`, `clamp(1.0 - tRutS${s} * tRutS${s}, 0.0, 1.0)`));
			// dh/dL = D * 4 q (1 - q^2) / half for |q| < 1 (profile -D (1 - q^2)^2)
			rut.push(`tAnalytic = tAnalytic + tRutG * (${u("terrainRut")}.z * 4.0 * tRutS${s} * tRutQ${s} / ${u("terrainRut")}.y) * step(abs(tRutS${s}), 1.0) * tRutValid * tRutDirt;`);
			rut.push(`tRutMask = max(tRutMask, tRutQ${s} * tRutQ${s} * step(abs(tRutS${s}), 1.0) * tRutValid * tRutDirt);`);
		}
		push(`${open("tRutV < 254.5 && abs(tRutL) < 1.3")}\n\t${rut.join("\n\t")}\n}`);
		// berm lip outside the edge (spec §4.2): 0.05 <= d <= 0.45 m, tier 2
		push(`#if TERRAIN_TIER >= 2
${open("tSdf >= 0.05 && tSdf <= 0.45")}
	${solve("tSdfG", "tSdfS")}
	tAnalytic = tAnalytic + tSdfG * (0.012 * 3.14159265 / 0.4 * cos(3.14159265 * clamp((tSdf - 0.05) / 0.4, 0.0, 1.0)));
}
#endif`);
	}
	// --- composition; the far path (layer means) only where the far fade has started ---
	push(d(f, "tRainWet", `${u("terrainWeather")}.x`));
	push(d(f, "tWet", `max(smoothstep(0.25, 0.85, tB.w), max(tRainWet * (0.4 + 0.6 * (1.0 - tH)), tRainWet * tRutMask))`));
	push(d(f, "tGrassShare", `tB.x + tB.y`));
	push(d(v3, "tAlb", "tNearAlbedo"));
	push(d(f, "tR", `tRoughGrass * mix(1.0, 0.8, tWet) + tRoughSoil * mix(1.0, 0.45, tWet) + 0.08 * (1.0 - tLayerAO)`));
	push(`tR = clamp(mix(tR, tR * 0.85, tRutMask), 0.22, 1.0);`);
	push(`${open("tFar > 0.0")}
	${d(v3, "tFarAlbedo", `(tW.x * ${u("terrainMean0")}.rgb + tW.y * ${u("terrainMean1")}.rgb) * ${macro} + tW.z * ${u("terrainMean2")}.rgb + tW.w * ${u("terrainMean3")}.rgb`)}
	tAlb = mix(tAlb, tFarAlbedo, tFar);
	tR = mix(tR, dot(tW, ${v4}(${u("terrainMean0")}.w, ${u("terrainMean1")}.w, ${u("terrainMean2")}.w, ${u("terrainMean3")}.w)), tFar);
}`);
	push(`tAlb = tAlb * mix(1.0, mix(0.86, 0.72, 1.0 - tGrassShare), tWet);`);
	push(`tAlb = tAlb * mix(1.0, 0.86, tRutMask * 0.85);`);
	push(`tAlb = tAlb * mix(1.0, tCellAO, ${u("terrainLook")}.w);`);
	push(`tAlb = tAlb * (1.0 - 0.08 * tBand * (1.0 - smoothstep(-0.6, 0.0, tSdf)));`);
	push(`tAlb = tAlb * ${u("terrainWeather")}.yzw;`);
	push(`terrainRough = clamp(tR * ${u("terrainLook")}.x, 0.22, 1.0);`);
	push(`surfaceAlbedo = tAlb;`);
	push(d(v3, "tNg", "normalW"));
	push(d(v3, "tTan", `normalize(${v3}(1.0, 0.0, 0.0) - tNg * tNg.x)`));
	push(d(v3, "tBit", `normalize(${v3}(0.0, 0.0, 1.0) - tNg * tNg.z)`));
	push(d(v2, "tPn", `(tP * ${u("terrainLook")}.z - tAnalytic) * (1.0 - tFar)`));
	push(`normalW = normalize(tNg + tTan * tPn.x + tBit * tPn.y);`);
	push(debugBlock(L));
	// Tier 0 samples NRO only for layers with b > 0.15 (spec §3.6 tiers). A variable, not a valued #define: WGSL has no
	// macro substitution (Babylon evaluates #if itself but passes WGSL code through as written).
	const nroMinDecl = `#if TERRAIN_TIER == 0\n${d(f, "tNroMin", TIER0_NRO_MIN.toFixed(3))}\n#else\n${d(f, "tNroMin", BRANCH_EPS.toFixed(3))}\n#endif`;
	return `#ifdef TERRAIN_SPLAT\n${nroMinDecl}\n${lines.join("\n")}\n#endif`;
}

function debugBlock(L: Lang): string {
	const { v3 } = L;
	return `#ifdef TERRAIN_DEBUG
#if TERRAIN_DEBUG == 1
terrainDebugOut = tB.x * ${v3}(0.25, 0.62, 0.18) + tB.y * ${v3}(0.92, 0.82, 0.30) + tB.z * ${v3}(0.80, 0.55, 0.32) + tB.w * ${v3}(0.30, 0.22, 0.12);
#elif TERRAIN_DEBUG == 2
terrainDebugOut = ${v3}(tH);
#elif TERRAIN_DEBUG == 3
terrainDebugOut = normalW * 0.5 + ${v3}(0.5);
#elif TERRAIN_DEBUG == 4
terrainDebugOut = ${v3}(terrainRough);
#elif TERRAIN_DEBUG == 5
terrainDebugOut = ${v3}(tCellAO * clamp(tLayerAO, 0.0, 1.0));
#elif TERRAIN_DEBUG == 6
terrainDebugOut = mix(${v3}(0.85, 0.55, 0.2), ${v3}(0.2, 0.55, 0.85), step(0.0, tSdf)) * (0.6 + 0.4 * step(0.5, fract(tSdf * 4.0))) * (1.0 - 0.7 * tRutMask);
#elif TERRAIN_DEBUG == 7
terrainDebugOut = ${v3}(1.0 - tT0, 0.25 + 0.5 * tT1, tT0);
#elif TERRAIN_DEBUG == 8
terrainDebugOut = mix(${v3}(0.1, 0.8, 0.2), ${v3}(0.9, 0.1, 0.1), clamp(log2(max(length(tDx * 1024.0 / 6.0), 1.0)) / 4.0, 0.0, 1.0));
#elif TERRAIN_DEBUG == 9
terrainDebugOut = mix(${v3}(0.1, 0.2, 0.9), ${v3}(0.95, 0.15, 0.1), clamp((tFetches - 2.0) / 12.0, 0.0, 1.0));
#elif TERRAIN_DEBUG == 10
terrainDebugOut = tNearAlbedo;
#elif TERRAIN_DEBUG == 11
terrainDebugOut = tSplat.rgb;
#elif TERRAIN_DEBUG == 12
terrainDebugOut = tData.rgb;
#endif
#endif`;
}

function farBody(L: Lang): string {
	const { f, v2, v3, u } = L;
	const d = L.decl;
	return `#ifdef TERRAIN_FAR
${d(v2, "tXZ", `${L.pos}.xz`)}
${d(v2, "tDx", L.dx("tXZ"))}
${d(v2, "tDy", L.dy("tXZ"))}
${d(f, "tM2", "0.65 * terrainVNx(tXZ * (1.0 / 31.0)) + 0.35 * terrainVNx(tXZ * (1.0 / 13.0))")}
${d(v3, "tMacro", `mix(${v3}(0.97, 1.0, 1.04), ${v3}(1.04, 1.0, 0.94), smoothstep(0.35, 0.75, tM2)) * mix(0.90, 1.08, tM2)`)}
// dry share = the masks' outer-border default (lush 0.65 / dry 0.35, §3.5 rule 7) so a cell edge meets the far ground
// without a colour seam (P1 lab pass 3: a procedural far dry share drew the cell rectangle); the shared 31/13 m
// macro value/hue (tMacro) keeps the far ground varied
${d(f, "tDry", `${FAR_DRY_SHARE.toFixed(2)}`)}
${d(f, "tDist", `length(${L.eye} - ${L.pos})`)}
${d(f, "tFar", `smoothstep(${u("terrainBlend")}.z, ${u("terrainBlend")}.w, tDist)`)}
${d(v3, "tLush", `${u("terrainMean0")}.rgb`)}
${d(v3, "tDryC", `${u("terrainMean1")}.rgb`)}
if (tFar < 0.999) {
	${d(L.v2, "tUV0", `tXZ * ${u("terrainTile")}.x`)}
	${d(L.v4, "tA0", L.grad("terrainLushAH", "tUV0", `tDx * ${u("terrainTile")}.x`, `tDy * ${u("terrainTile")}.x`))}
	${d(L.v4, "tA0B", L.grad("terrainLushAH", `terrainRotate(tUV0) + ${v2}(0.37, 0.71)`, `terrainRotate(tDx * ${u("terrainTile")}.x)`, `terrainRotate(tDy * ${u("terrainTile")}.x)`))}
	${d(f, "tT", `clamp((smoothstep(0.3, 0.7, terrainVNx(tXZ * (1.0 / 7.3))) - 0.5) * 2.0 + (tA0B.a - tA0.a) * 1.2 + 0.5, 0.0, 1.0)`)}
	${d(L.v4, "tA1", L.grad("terrainDryAH", `tXZ * ${u("terrainTile")}.y`, `tDx * ${u("terrainTile")}.y`, `tDy * ${u("terrainTile")}.y`))}
	tLush = mix(tLush, ${L.lin("mix(tA0.rgb, tA0B.rgb, tT)")}, 1.0 - tFar);
	tDryC = mix(tDryC, ${L.lin("tA1.rgb")}, 1.0 - tFar);
}
surfaceAlbedo = mix(tLush, tDryC, tDry) * tMacro * ${u("terrainWeather")}.yzw;
terrainRough = clamp(mix(${u("terrainMean0")}.w, ${u("terrainMean1")}.w, tDry) * ${u("terrainLook")}.x, 0.22, 1.0);
#ifdef TERRAIN_DEBUG
terrainDebugOut = surfaceAlbedo;
#endif
#endif`;
}

const CODE_CACHE = new Map<string, Record<string, string>>();

/** Generated fragment code per language (exported for tests). A probe (DEV lab only) changes the cell body. */
export function terrainFragmentCode(language: ShaderLanguage, probe?: TerrainProbe | null): Record<string, string> {
	const wgsl = language === ShaderLanguage.WGSL;
	const o = normaliseProbe(probe);
	const key = `${wgsl ? "wgsl" : "glsl"}:${probeKey(o)}`;
	let code = CODE_CACHE.get(key);
	if (!code) {
		const L = lang(wgsl);
		code = {
			CUSTOM_FRAGMENT_DEFINITIONS: definitions(L, o),
			CUSTOM_FRAGMENT_BEFORE_LIGHTS: `${cellBody(L, o)}
${farBody(L)}`,
			CUSTOM_FRAGMENT_UPDATE_METALLICROUGHNESS: `
#if defined(TERRAIN_SPLAT) || defined(TERRAIN_FAR)
metallicRoughness.g = terrainRough;
#endif`,
			CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR: `
#ifdef TERRAIN_DEBUG
finalColor = ${L.v4}(terrainDebugOut, 1.0);
#endif`,
		};
		CODE_CACHE.set(key, code);
	}
	return code;
}

// ----------------------------------------------------------------------------
// Plugin
// ----------------------------------------------------------------------------

export interface TerrainPluginState {
	mode: "cell" | "far";
	tier: TerrainTier;
	debug: number;
	layerTextures: () => Texture[];
	cellTextures: () => Texture[];
	cell: { minX: number; minZ: number; n: number } | null;
	tiles: [number, number, number, number];
	means: Array<[number, number, number, number]>;
	legacy: PBRMaterial | null;
	look: TerrainLook;
	/** DEV lab: -1 = splat, 0..3 = one layer everywhere. */
	solo: number;
	/** DEV lab GPU cost probe (cell materials only); absent or null = production code. */
	probe?: TerrainProbe | null;
	/** Cell maps carry the baked macro (splat alpha) and anti-tiling mask (data alpha): TERRAIN_NOISE_MAPS. */
	noiseMaps?: boolean;
}

export class TerrainSurfacePlugin extends MaterialPluginBase {
	constructor(material: PBRMaterial, readonly state: TerrainPluginState) {
		super(material, "TerrainSurface", 186, { TERRAIN_SPLAT: false, TERRAIN_FAR: false, TERRAIN_TIER: 2, TERRAIN_DEBUG: false, TERRAIN_SOLO: false, TERRAIN_PROBE: false, TERRAIN_NOISE_MAPS: false }, true, false);
		// Without this Babylon never calls hardBindForSubMesh and every terrain uniform stays zero (impostors.ts:77,
		// VFX lab pass 2).
		this.registerForExtraEvents = true;
		this._enable(true);
	}

	isCompatible(language: ShaderLanguage): boolean { return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL; }

	getClassName(): string { return "TerrainSurfacePlugin"; }

	/** Re-evaluate defines after a tier or debug change. */
	refresh(): void { this.markAllDefinesAsDirty(); }

	prepareDefines(defines: MaterialDefines): void {
		const d = defines as unknown as Record<string, unknown>;
		d.TERRAIN_SPLAT = this.state.mode === "cell";
		d.TERRAIN_FAR = this.state.mode === "far";
		d.TERRAIN_TIER = this.state.tier;
		// DEV-only debug: production builds never set a mode (createTerrainSurface ignores debug in production).
		d.TERRAIN_DEBUG = this.state.debug > 0 ? this.state.debug : false;
		d.TERRAIN_SOLO = this.state.mode === "cell" && this.state.solo >= 0 ? this.state.solo + 1 : false;
		// DEV-only cost probe: its own define value, so the probe code compiles as a separate effect.
		const probe = this.state.mode === "cell" ? terrainProbeId(this.state.probe) : 0;
		d.TERRAIN_PROBE = probe > 0 ? probe : false;
		d.TERRAIN_NOISE_MAPS = this.state.mode === "cell" && this.state.noiseMaps === true;
	}

	private textures(): Texture[] {
		const layers = this.state.layerTextures();
		return this.state.mode === "cell" ? [...layers, ...this.state.cellTextures()] : [layers[0], layers[2]];
	}

	isReadyForSubMesh(): boolean { return this.textures().every(texture => texture.isReady()); }

	getSamplers(samplers: string[]): void { samplers.push(...(this.state.mode === "cell" ? TERRAIN_CELL_SAMPLERS : TERRAIN_FAR_SAMPLERS)); }

	getUniforms(language = ShaderLanguage.GLSL) {
		const declaration = language === ShaderLanguage.GLSL ? TERRAIN_UNIFORMS.map(name => `uniform vec4 ${name};`).join("\n") : "";
		return { ubo: TERRAIN_UNIFORMS.map(name => ({ name, size: 4, type: "vec4" })), fragment: declaration };
	}

	bindForSubMesh(buffer: UniformBuffer): void {
		const layers = this.state.layerTextures();
		if (this.state.mode === "cell") {
			LAYER_SAMPLERS.forEach((name, i) => buffer.setTexture(name, layers[i]));
			const [splat, data] = this.state.cellTextures();
			buffer.setTexture("terrainCellSplat", splat);
			buffer.setTexture("terrainCellData", data);
		} else {
			buffer.setTexture("terrainLushAH", layers[0]);
			buffer.setTexture("terrainDryAH", layers[2]);
		}
	}

	hardBindForSubMesh(buffer: UniformBuffer): void {
		const s = this.state;
		const cell = s.cell ?? { minX: 0, minZ: 0, n: CELL_N.high };
		buffer.updateFloat4("terrainCell", cell.minX, cell.minZ, cell.n / (cell.n + 1) / CELL_M, 0.5 / (cell.n + 1));
		buffer.updateFloat4("terrainCellRes", cell.n, 1 / (cell.n + 1), s.tier, 0);
		buffer.updateFloat4("terrainTile", 1 / s.tiles[0], 1 / s.tiles[1], 1 / s.tiles[2], 1 / s.tiles[3]);
		buffer.updateFloat4("terrainHScale", 1, 1, 1, 0.5);
		buffer.updateFloat4("terrainHBias", 0, 0, 0, 0);
		const [farStart, farEnd] = FAR_FADE[s.tier];
		buffer.updateFloat4("terrainBlend", 0.6, 0.12, farStart, farEnd);
		buffer.updateFloat4("terrainRut", RUT.centreM, RUT.profileHalfM, RUT.depthM, RUT.wanderM);
		// Weather: world-weather.ts writes roughness = .94 - wet * .22 and albedoColor on the legacy material.
		const roughness = s.legacy?.roughness ?? 0.94;
		const albedo = s.legacy?.albedoColor ?? new Color3(DRY_TINT[0], DRY_TINT[1], DRY_TINT[2]);
		const rainWet = Math.max(0, Math.min(1, (0.94 - roughness) / 0.22));
		buffer.updateFloat4("terrainWeather", rainWet, albedo.r / DRY_TINT[0], albedo.g / DRY_TINT[1], albedo.b / DRY_TINT[2]);
		s.means.forEach((m, i) => buffer.updateFloat4(`terrainMean${i}`, m[0], m[1], m[2], m[3]));
		buffer.updateFloat4("terrainLook", roughness / 0.94, s.look.edgeBreakup, s.look.normalStrength, s.look.cellAO);
	}

	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		// called from the MaterialPluginBase constructor (point-name collection) before `state` is assigned
		return stage === "fragment" ? terrainFragmentCode(language, this.state?.mode === "cell" ? this.state.probe : null) : null;
	}

	getActiveTextures(active: BaseTexture[]): void { active.push(...this.textures()); }

	hasTexture(texture: BaseTexture): boolean { return this.textures().includes(texture as Texture); }
}

// ----------------------------------------------------------------------------
// Factory
// ----------------------------------------------------------------------------

const DEBUG_INDEX: Record<TerrainDebugMode, number> = { off: 0, weights: 1, height: 2, normal: 3, rough: 4, ao: 5, sdf: 6, tiling: 7, mip: 8, fetches: 9, albedo: 10, splat: 11, data: 12 };
const RES_BY_TIER: Record<TerrainTier, "high" | "medium" | "low"> = { 2: "high", 1: "medium", 0: "low" };
const LAYER_RES: Record<string, Record<"high" | "medium" | "low", number>> = {
	L0: { high: 1024, medium: 1024, low: 512 }, L1: { high: 1024, medium: 512, low: 512 },
	L2: { high: 1024, medium: 1024, low: 512 }, L3: { high: 512, medium: 512, low: 512 },
	R0: { high: 1024, medium: 512, low: 512 }, R1: { high: 512, medium: 256, low: 256 },
};

interface CellEntry {
	id: string; record: TerrainCellRecord; material: PBRMaterial; plugin: TerrainSurfacePlugin;
	textures: Texture[]; refs: number; ready: Promise<boolean>; failed: boolean;
}

export function createTerrainSurface(scene: Scene, options: TerrainSurfaceOptions): TerrainSurface {
	const manifest = options.manifest;
	if (manifest.schema !== "xexoria.terrain-layerset/1") throw new Error(`Unsupported terrain layerset ${String(manifest.schema)}`);
	if (manifest.albedoEncoding !== "srgb-bytes-in-unorm") throw new Error("Terrain albedo must be sRGB bytes in UNORM");
	const set = options.set ?? "v2";
	const cells = manifest.cells[set] ?? {};
	const byId = new Map(manifest.layers.map(layer => [layer.id, layer]));
	const relief = new Map((manifest.relief ?? []).map(layer => [layer.id, layer]));
	const ordered = (["L0", "L1", "L2", "L3"] as const).map(id => {
		const layer = byId.get(id);
		if (!layer) throw new Error(`Terrain layerset is missing ${id}`);
		return layer;
	});
	let tier = resolveTier(options.profile.preset);
	const devDebug = typeof import.meta !== "undefined" && (import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV !== false;
	let debugIndex = devDebug ? DEBUG_INDEX[options.debug ?? "off"] : 0;
	const legacy = options.legacy ?? null;
	const failures: string[] = [];
	let disposed = false;

	// Every texture gets a settle-once readiness promise at creation (load -> true, error -> false).
	const readiness = new WeakMap<Texture, Promise<boolean>>();
	const makeTexture = (file: string, srgb: boolean, invertY: boolean, sampling: number, wrap: number): Texture => {
		const url = options.resolveUrl(file);
		let settle!: (ok: boolean) => void;
		const ready = new Promise<boolean>(resolve => { settle = resolve; });
		const fail = (message?: string) => { failures.push(`${file}: ${message ?? "load failed"}`); settle(false); };
		// forcedExtension: bundlers may inline small files as data: URLs, which carry no extension for Babylon's loader pick
		const forcedExtension = file.endsWith(".ktx2") ? ".ktx2" : undefined;
		const texture = options.createTexture
			? options.createTexture(url, { invertY, srgb, onLoad: () => settle(true), onError: fail })
			: new Texture(url, scene, { noMipmap: false, invertY, samplingMode: sampling, gammaSpace: srgb, onError: fail, forcedExtension });
		texture.name = `terrain:${file}`;
		texture.gammaSpace = srgb;
		texture.wrapU = texture.wrapV = wrap;
		if (texture.isReady()) settle(true);
		else texture.onLoadObservable.addOnce(() => settle(true));
		readiness.set(texture, ready);
		return texture;
	};
	const allReady = (textures: Texture[]) => Promise.all(textures.map(t => readiness.get(t) ?? Promise.resolve(t.isReady())))
		.then(results => results.every(Boolean));
	// Per-cell maps with a baked field in alpha: the PNG is decoded here (exact bytes; no colour management or
	// premultiplication can touch them) and uploaded as RGBA8. Needs DecompressionStream; without it, and in the unit
	// tests' createTexture mode, the maps load as plain textures and the shader evaluates the fields per pixel.
	const bakeCellMaps = Boolean(options.loadBytes) || (!options.createTexture && typeof DecompressionStream !== "undefined");
	const inflate = async (data: Uint8Array): Promise<Uint8Array> => {
		const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate"));
		return new Uint8Array(await new Response(stream).arrayBuffer());
	};
	const loadBytes = options.loadBytes ?? (async (url: string) => {
		const response = await fetch(url);
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		return response.arrayBuffer();
	});
	const makeCellMap = (file: string, field: CellFieldKind, minX: number, minZ: number, n: number): Texture => {
		const size = n + 1;
		// waitDataToBeReady: not ready (so never drawn) until the decoded bytes are uploaded
		const texture = new RawTexture(null, size, size, Constants.TEXTUREFORMAT_RGBA, scene, true, false, Texture.TRILINEAR_SAMPLINGMODE,
			Constants.TEXTURETYPE_UNSIGNED_BYTE, undefined, false, true);
		texture.name = `terrain:${file}`;
		texture.gammaSpace = false;
		texture.wrapU = texture.wrapV = Texture.CLAMP_ADDRESSMODE;
		let settle!: (ok: boolean) => void;
		readiness.set(texture, new Promise<boolean>(resolve => { settle = resolve; }));
		void loadBytes(options.resolveUrl(file))
			.then(bytes => decodePng(bytes, inflate))
			.then(png => {
				if (png.width !== size || png.height !== size) throw new Error(`${png.width}x${png.height}, expected ${size}x${size}`);
				if (disposed || !texture.getInternalTexture()) { settle(false); return; }
				texture.update(bakeCellMapRGBA(png, field, minX, minZ, n));
				settle(true);
			})
			.catch((error: unknown) => {
				failures.push(`${file}: ${error instanceof Error ? error.message : String(error)}`);
				settle(false);
			});
		return texture;
	};

	// Shared layer textures (AH then NRO per layer: lush, dry, dirt, mud), reloaded on a resolution change.
	let layerTextures: Texture[] = [];
	const loadLayers = () => {
		const res = RES_BY_TIER[tier];
		const textures: Texture[] = [];
		for (const layer of ordered) {
			const size = String(LAYER_RES[layer.id][res]);
			// AH stores sRGB bytes in UNORM (the shader linearises): never tag sRGB, or the GPU decodes twice.
			textures.push(makeTexture(layer.files.ah[size] ?? Object.values(layer.files.ah)[0], false, true, Texture.TRILINEAR_SAMPLINGMODE, Texture.WRAP_ADDRESSMODE));
			textures.push(makeTexture(layer.files.nro[size] ?? Object.values(layer.files.nro)[0], false, true, Texture.TRILINEAR_SAMPLINGMODE, Texture.WRAP_ADDRESSMODE));
		}
		for (const texture of textures) texture.anisotropicFilteringLevel = TIER_ANISOTROPY[tier];
		return textures;
	};
	layerTextures = loadLayers();
	let layersReady = allReady(layerTextures);
	const means = (): Array<[number, number, number, number]> => ordered.map(layer => [...layer.mean_linear_rgb, layer.mean_roughness] as [number, number, number, number]);
	const tiles = ordered.map(layer => layer.tile_m) as [number, number, number, number];
	const look: TerrainLook = { ...TERRAIN_LOOK_DEFAULTS };
	let solo = devDebug ? Math.max(-1, Math.min(3, Math.trunc(options.solo ?? -1))) : -1;
	let probe: TerrainProbe | null = null;

	const newMaterial = (name: string, state: TerrainPluginState) => {
		const material = new PBRMaterial(name, scene);
		material.albedoColor = Color3.White();
		material.metallic = 0;
		material.roughness = 0.9;
		material.backFaceCulling = false;
		material.forceNormalForward = true;
		const plugin = new TerrainSurfacePlugin(material, state);
		return { material, plugin };
	};

	const far = newMaterial("terrain-far", {
		mode: "far", tier, debug: debugIndex, layerTextures: () => layerTextures, cellTextures: () => [], cell: null,
		tiles, means: means(), legacy, look, solo: -1,
	});
	const entries = new Map<string, CellEntry>();
	const rocks = new Map<string, PBRMaterial>();
	let rockTextures: Texture[] | null = null;

	const cellEntry = (id: string): CellEntry => {
		const existing = entries.get(id);
		if (existing) return existing;
		const record = cells[id];
		if (!record) throw new Error(`No terrain cell ${id} in set ${set}`);
		const res = tier === 0 ? "129" : "257";
		const n = tier === 0 ? CELL_N.low : CELL_N.high;
		const sampling = Texture.TRILINEAR_SAMPLINGMODE;
		const [minX, , minZ] = record.bounds;
		// Per-cell maps stay lossless PNG (RGB8, no colour chunks); row 0 = north (§3.1, §3.4). Baked: decoded here with
		// the macro field in splat alpha and the anti-tiling mask in data alpha. Plain: loaded with invertY = true.
		const splat = bakeCellMaps ? makeCellMap(record.splat[res], "macro", minX, minZ, n) : makeTexture(record.splat[res], false, true, sampling, Texture.CLAMP_ADDRESSMODE);
		const data = bakeCellMaps ? makeCellMap(record.data[res], "mask", minX, minZ, n) : makeTexture(record.data[res], false, true, sampling, Texture.CLAMP_ADDRESSMODE);
		for (const texture of [splat, data]) texture.anisotropicFilteringLevel = 2;
		const { material, plugin } = newMaterial(`terrain-cell-${id}`, {
			mode: "cell", tier, debug: debugIndex, layerTextures: () => layerTextures, cellTextures: () => [splat, data],
			cell: { minX, minZ, n }, tiles, means: means(), legacy, look, solo, probe, noiseMaps: bakeCellMaps,
		});
		const entry: CellEntry = { id, record, material, plugin, textures: [splat, data], refs: 0, ready: Promise.resolve(false), failed: false };
		// Transactional reveal: the cell maps and the shared layer set must all load (any failure -> legacy fallback).
		entry.ready = Promise.all([allReady([splat, data]), layersReady]).then(([cellOk, layersOk]) => {
			entry.failed = !(cellOk && layersOk);
			return !entry.failed;
		});
		entries.set(id, entry);
		return entry;
	};

	const plugins = () => [far.plugin, ...[...entries.values()].map(entry => entry.plugin)];

	const surface: TerrainSurface = {
		get tier() { return tier; },
		farMaterial: far.material,
		decalMaterial: null,
		materialForCell: id => cellEntry(id).material,
		async resolveCellMaterial(id) {
			const entry = cellEntry(id);
			const ok = await entry.ready;
			if (ok) return entry.material;
			console.warn(`Terrain cell ${id} textures failed; using the legacy ground material.`, failures);
			return legacy ?? far.material;
		},
		whenCellReady: id => cellEntry(id).ready.then(ok => ok && layersReady),
		rockMaterial(slot, cellId, rockOptions = {}) {
			const key = `${slot}:${cellId ?? ""}`;
			const existing = rocks.get(key);
			if (existing) return existing;
			if (!rockTextures) {
				const res = RES_BY_TIER[tier];
				rockTextures = (["R0", "R1"] as const).flatMap(id => {
					const layer = relief.get(id);
					if (!layer) throw new Error(`Terrain layerset is missing relief layer ${id}`);
					const size = String(LAYER_RES[id][res]);
					return [makeTexture(layer.files.ah[size] ?? Object.values(layer.files.ah)[0], false, true, Texture.TRILINEAR_SAMPLINGMODE, Texture.WRAP_ADDRESSMODE),
						makeTexture(layer.files.nro[size] ?? Object.values(layer.files.nro)[0], false, true, Texture.TRILINEAR_SAMPLINGMODE, Texture.WRAP_ADDRESSMODE)];
				});
			}
			const [rockAH, rockNRO, mossAH, mossNRO] = rockTextures;
			const r0 = relief.get("R0")!, r1 = relief.get("R1")!;
			const material = createRockMaterial(scene, `terrain-rock-${slot}${cellId ? `-${cellId}` : ""}`, {
				rockAH, rockNRO, mossAH, mossNRO, rockTile: r0.tile_m, mossTile: r1.tile_m, legacy,
				style: slot.includes("cliff") ? "granite" : "sandstone", ...rockOptions,
			});
			rocks.set(key, material);
			return material;
		},
		retainCell(id) { cellEntry(id).refs += 1; },
		releaseCell(id) {
			const entry = entries.get(id);
			if (!entry) return;
			entry.refs -= 1;
			if (entry.refs > 0) return;
			entry.material.dispose(false, false);
			for (const texture of entry.textures) texture.dispose();
			entries.delete(id);
		},
		setQuality(profile) {
			const next = resolveTier(profile.preset);
			if (next === tier) return;
			const resChanged = RES_BY_TIER[next] !== RES_BY_TIER[tier];
			tier = next;
			if (resChanged) {
				// Lazy 512 <-> 1024 swap: keep rendering with the old set until the new one has loaded (no blank frames).
				const incoming = loadLayers();
				const swap = allReady(incoming).then(ok => {
					if (disposed || !ok) {
						if (!ok && !disposed) console.warn("Terrain layer swap failed; keeping the current resolution.", failures);
						for (const texture of incoming) texture.dispose();
						return !disposed && layerTextures.length > 0;
					}
					const old = layerTextures;
					layerTextures = incoming;
					for (const texture of old) texture.dispose();
					for (const p of plugins()) p.refresh();
					return true;
				});
				layersReady = swap;
			} else {
				for (const texture of layerTextures) texture.anisotropicFilteringLevel = TIER_ANISOTROPY[tier];
			}
			for (const p of plugins()) { p.state.tier = tier; p.refresh(); }
		},
		solo(layer) {
			solo = devDebug && layer !== null ? Math.max(-1, Math.min(3, Math.trunc(layer))) : -1;
			for (const p of plugins()) { p.state.solo = p.state.mode === "cell" ? solo : -1; p.refresh(); }
		},
		probe(next) {
			probe = devDebug && next ? { ...next } : null;
			for (const p of plugins()) { p.state.probe = p.state.mode === "cell" ? probe : null; p.refresh(); }
		},
		setLook(next) {
			for (const key of ["normalStrength", "edgeBreakup", "cellAO"] as const) {
				const value = next[key];
				if (typeof value === "number" && Number.isFinite(value)) look[key] = value;
			}
		},
		whenLayersReady: () => layersReady,
		memoryEstimate() {
			const engine = scene.getEngine();
			const caps = engine.getCaps() as unknown as Record<string, unknown>;
			const compressed = Boolean(caps.bptc || caps.astc || caps.s3tc || caps.etc2);
			const res = RES_BY_TIER[tier];
			const mip = 4 / 3;
			const bpt = compressed ? 1 : 4;
			const layersMiB = ordered.reduce((s, layer) => s + 2 * LAYER_RES[layer.id][res] ** 2 * bpt * mip, 0) / 2 ** 20;
			const reliefMiB = rockTextures ? (["R0", "R1"].reduce((s, id) => s + 2 * LAYER_RES[id][res] ** 2 * bpt * mip, 0) / 2 ** 20) : 0;
			const texels = tier === 0 ? 129 : 257;
			const cellsMiB = entries.size * 2 * texels * texels * 4 * mip / 2 ** 20;
			return {
				mib: +(layersMiB + cellsMiB + reliefMiB).toFixed(3), layersMiB: +layersMiB.toFixed(3), cellsMiB: +cellsMiB.toFixed(3),
				reliefMiB: +reliefMiB.toFixed(3), residentCells: entries.size, compressed,
				basis: compressed ? "UASTC transcoded to a block format (~1 B/texel), mips x4/3; cell PNGs RGBA8"
					: "KTX2 transcoded to RGBA8 (no compressed-texture caps on this engine, see recheck GAP-1), mips x4/3",
			};
		},
		debug(mode) {
			debugIndex = devDebug ? DEBUG_INDEX[mode] : 0;
			for (const p of plugins()) { p.state.debug = debugIndex; p.refresh(); }
		},
		cellIds: () => Object.keys(cells),
		dispose() {
			if (disposed) return;
			disposed = true;
			for (const entry of entries.values()) {
				entry.material.dispose(false, false);
				for (const texture of entry.textures) texture.dispose();
			}
			entries.clear();
			for (const material of rocks.values()) material.dispose(false, false);
			rocks.clear();
			far.material.dispose(false, false);
			for (const texture of layerTextures) texture.dispose();
			layerTextures = [];
			for (const texture of rockTextures ?? []) texture.dispose();
			rockTextures = null;
		},
	};
	return surface;
}
