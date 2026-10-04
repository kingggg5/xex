import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import type { Texture } from "@babylonjs/core/Materials/Textures/texture";
import type { BaseTexture } from "@babylonjs/core/Materials/Textures/baseTexture";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { Scene } from "@babylonjs/core/scene";

/**
 * Shared relief rock surface, P1 generic version (terrain spec §5.1).
 *
 * - Detail: biplanar projection of R0 (world space, 4 m) - the smallest of three triplanar weights is removed so
 *   at most two projections are fetched (AH + NRO each); normals use Golus' whiteout blend with the axis-sign fix.
 * - Strata: world-Y bands with dip, 4-colour ramp, +-6 % value per band (hash of the band index), bedding lines.
 * - Top moss: smoothstep(0.50, 0.82, n.y + noise + allowance + north shade), height-blended with R1 (top
 *   projection, 3 m) so moss fills ledges and hollows first.
 * - Generic rocks: COLOR_0 = (AO, curvature 0.5 = flat, ground-contact gradient, 1); convex highlight, concave
 *   darkening, AO and contact tint. Hero bakes (bakeA/bakeB) arrive with script 4 in P2.
 * Samplers: 4 custom (generic rock: 7 with the base PBR 3).
 * GPU cost (P1 report §10): the projection gradients and the moss UV are formed inside their branches (short live
 * ranges), value noise and the strata band hashes share their per-axis hash terms (same hash, fp32 rounding only).
 */

export interface RockMaterialOptions {
	rockAH: Texture; rockNRO: Texture; mossAH: Texture; mossNRO: Texture;
	rockTile: number; mossTile: number;
	style: "sandstone" | "granite";
	legacy?: PBRMaterial | null;
	/** 0..1 moss allowance (hero bakes provide a per-texel map later). */
	mossAllow?: number;
	/** Strata period (m), dip (deg) and dip direction (deg from +X toward +Z). */
	strata?: { periodM: number; dipDeg: number; dipDirDeg: number };
	palette?: [string, string, string, string];
	/** Linear mean colour of R0 (normalises the tint so the ramp sets the average colour). */
	rockMean?: [number, number, number];
}

const ROCK_SAMPLERS = ["rockDetailAH", "rockDetailNRO", "rockMossAH", "rockMossNRO"] as const;
export const ROCK_UNIFORMS = ["rockTiles", "rockStrata", "rockPal0", "rockPal1", "rockPal2", "rockPal3", "rockMean", "rockWeather", "rockLook"] as const;
const PALETTES = {
	sandstone: ["#a08f78", "#8a7c68", "#c2ae8e", "#958673"] as [string, string, string, string],
	granite: ["#7d7f80", "#8f8c86", "#a9a59b", "#6e7378"] as [string, string, string, string],
};
const STRATA = { sandstone: { periodM: 0.85, dipDeg: 4, dipDirDeg: 225 }, granite: { periodM: 1.8, dipDeg: 7, dipDirDeg: 270 } };

function code(wgsl: boolean): Record<string, string> {
	const v2 = wgsl ? "vec2f" : "vec2", v3 = wgsl ? "vec3f" : "vec3", v4 = wgsl ? "vec4f" : "vec4", f = wgsl ? "f32" : "float";
	const u = (n: string) => (wgsl ? `uniforms.${n}` : n);
	const d = (t: string, n: string, e: string) => (wgsl ? `var ${n}: ${t} = ${e};` : `${t} ${n} = ${e};`);
	const grad = (tex: string, uv: string, dx: string, dy: string) => wgsl
		? `textureSampleGrad(${tex}, ${tex}Sampler, ${uv}, ${dx}, ${dy})` : `textureGrad(${tex}, ${uv}, ${dx}, ${dy})`;
	const dfx = (e: string) => (wgsl ? `dpdx(${e})` : `dFdx(${e})`);
	const dfy = (e: string) => (wgsl ? `dpdy(${e})` : `dFdy(${e})`);
	const lin = (e: string) => (wgsl ? `toLinearSpaceVec3(${e})` : `toLinearSpace(${e})`);
	const pos = wgsl ? "fragmentInputs.vPositionW" : "vPositionW";
	const vcol = wgsl ? "fragmentInputs.vColor" : "vColor";
	const samplers = ROCK_SAMPLERS.map(n => (wgsl ? `var ${n}Sampler: sampler;\nvar ${n}: texture_2d<f32>;` : `uniform sampler2D ${n};`)).join("\n");
	// Dave Hoskins' hash12 with p3 = (a, b, a), a = fract(x * 0.1031), b = fract(y * 0.1031): dot(p3, p3.yzx + 33.33) =
	// 2ab + a^2 + 66.66a + 33.33b and hash = fract((a + b + 2d) (a + d)); value noise shares the per-axis terms of its four
	// corners, the strata tints share a = f(band) across their three constant y (same values as P1 up to fp32 rounding).
	const fns = wgsl ? `
fn rockVN(p: vec2f) -> f32 {
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
fn rockHash3(x: f32, y: vec3f) -> vec3f {
	let a = fract(x * 0.1031);
	let b = fract(y * 0.1031);
	let d = 2.0 * a * b + vec3f(a * (a + 66.66)) + 33.33 * b;
	return fract((vec3f(a) + b + 2.0 * d) * (vec3f(a) + d));
}
fn rockTN(nro: vec4f) -> vec3f {
	let n = nro.xy * 2.0 - vec2f(1.0);
	return vec3f(n, sqrt(max(1.0 - dot(n, n), 0.0)));
}
var<private> rockRough: f32 = 0.85;` : `
float rockVN(vec2 p) {
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
vec3 rockHash3(float x, vec3 y) {
	float a = fract(x * 0.1031);
	vec3 b = fract(y * 0.1031);
	vec3 d = 2.0 * a * b + vec3(a * (a + 66.66)) + 33.33 * b;
	return fract((vec3(a) + b + 2.0 * d) * (vec3(a) + d));
}
vec3 rockTN(vec4 nro) {
	vec2 n = nro.xy * 2.0 - 1.0;
	return vec3(n, sqrt(max(1.0 - dot(n, n), 0.0)));
}
float rockRough = 0.85;`;
	const proj = (axis: "X" | "Y" | "Z", uvExpr: string, wExpr: string, gx: string, gy: string) => {
		// whiteout per projection (Golus), with the UV/normal x flip by axis sign
		const swz = axis === "X" ? "rN.zy" : axis === "Y" ? "rN.xz" : "rN.xy";
		const comp = axis === "X" ? "rN.x" : axis === "Y" ? "rN.y" : "rN.z";
		const toWorld = axis === "X" ? `${v3}(rT${axis}.z, rT${axis}.y, rT${axis}.x)` : axis === "Y" ? `${v3}(rT${axis}.x, rT${axis}.z, rT${axis}.y)` : `rT${axis}`;
		const sign = axis === "Z" ? "-rSign.z" : axis === "X" ? "rSign.x" : "rSign.y";
		return `if (${wExpr} > 0.001) {
	${d(v2, `rUV${axis}`, uvExpr)}
	${d(v2, `rG${axis}x`, gx)}
	${d(v2, `rG${axis}y`, gy)}
	${d(v4, `rA${axis}`, grad("rockDetailAH", `rUV${axis}`, `rG${axis}x`, `rG${axis}y`))}
	${d(v4, `rM${axis}`, grad("rockDetailNRO", `rUV${axis}`, `rG${axis}x`, `rG${axis}y`))}
	${d(v3, `rT${axis}`, `rockTN(rM${axis})`)}
	rT${axis} = ${v3}(rT${axis}.x * ${sign}, rT${axis}.y, rT${axis}.z);
	rT${axis} = ${v3}(rT${axis}.xy + ${swz}, abs(rT${axis}.z) * ${comp});
	rDetailN = rDetailN + ${toWorld} * ${wExpr};
	rAlb = rAlb + ${lin(`rA${axis}.rgb`)} * ${wExpr};
	rH = rH + rA${axis}.a * ${wExpr};
	rRough = rRough + rM${axis}.b * ${wExpr};
	rAO = rAO + rM${axis}.a * ${wExpr};
}`;
	};
	// Gradient vectors per projection (rG?x / rG?y) come from the world-position derivatives taken in uniform flow; they
	// are formed inside each projection's branch so they are not all live at once.
	const body = `
#ifdef TERRAIN_ROCK
${d(v3, "rP", pos)}
${d(v3, "rN", "normalize(normalW)")}
${d(v3, "rDx", dfx("rP"))}
${d(v3, "rDy", dfy("rP"))}
${d(v3, "rSign", `sign(rN) + ${v3}(1.0) - abs(sign(rN))`)}
${d(v3, "rW", "rN * rN")}
rW = rW * rW;
rW = max(rW - ${v3}(min(rW.x, min(rW.y, rW.z))), ${v3}(0.0));
rW = rW / max(rW.x + rW.y + rW.z, 1e-5);
${d(f, "rS", `${u("rockTiles")}.x`)}
${d(f, "rNoise", `rockVN(rP.xz * 0.9 + rP.y * 0.37)`)}
${d(f, "rBandS", `(rP.y + ${u("rockStrata")}.y * (rP.x * ${u("rockStrata")}.z + rP.z * ${u("rockStrata")}.w)) / ${u("rockStrata")}.x + 0.5 * rockVN(rP.xz * 0.21)`)}
${d(v3, "rDetailN", `${v3}(0.0)`)}
${d(v3, "rAlb", `${v3}(0.0)`)}
${d(f, "rH", "0.0")}
${d(f, "rRough", "0.0")}
${d(f, "rAO", "0.0")}
${d(f, "rWX", "rW.x")}
${d(f, "rWY", "rW.y")}
${d(f, "rWZ", "rW.z")}
${proj("X", `${v2}(rP.z * rSign.x, rP.y) * rS`, "rWX", `${v2}(rDx.z * rSign.x, rDx.y) * rS`, `${v2}(rDy.z * rSign.x, rDy.y) * rS`)}
${proj("Y", `${v2}(rP.x * rSign.y, rP.z) * rS`, "rWY", `${v2}(rDx.x * rSign.y, rDx.z) * rS`, `${v2}(rDy.x * rSign.y, rDy.z) * rS`)}
${proj("Z", `${v2}(-rP.x * rSign.z, rP.y) * rS`, "rWZ", `${v2}(-rDx.x * rSign.z, rDx.y) * rS`, `${v2}(-rDy.x * rSign.z, rDy.y) * rS`)}
rDetailN = normalize(rDetailN + rN * 0.0001);
${d(f, "rBand", "floor(rBandS)")}
${d(v3, "rBandH", `rockHash3(rBand, ${v3}(17.0, 41.0, 73.0))`)}
${d(v3, "rTint", `mix(mix(${u("rockPal0")}.rgb, ${u("rockPal1")}.rgb, rBandH.x), mix(${u("rockPal2")}.rgb, ${u("rockPal3")}.rgb, rBandH.x), smoothstep(0.3, 0.7, rBandH.y))`)}
rTint = rTint * (1.0 + 0.06 * (2.0 * rBandH.z - 1.0)) * mix(0.8, 1.0, step(0.04, fract(rBandS)));
${d(v3, "rRockAlb", `rAlb / max(${u("rockMean")}.rgb, ${v3}(0.01)) * rTint`)}
${d(v4, "rVC", `${v4}(1.0, 0.5, 0.0, 1.0)`)}
#ifdef VERTEXCOLOR
rVC = ${vcol};
#endif
${d(f, "rConvex", "smoothstep(0.58, 0.85, rVC.g)")}
${d(f, "rConcave", "1.0 - smoothstep(0.18, 0.42, rVC.g)")}
rRockAlb = rRockAlb + ${u("rockLook")}.w * rConvex * ${v3}(0.807, 0.687, 0.434);
rRockAlb = rRockAlb * (1.0 - 0.25 * rConcave);
${d(f, "rMossIn", `rDetailN.y + 0.10 * (2.0 * rNoise - 1.0) + 0.25 * (2.0 * ${u("rockTiles")}.z - 1.0) + 0.05 * clamp(rN.z, 0.0, 1.0)`)}
${d(f, "rMoss", "smoothstep(0.50, 0.82, rMossIn)")}
${d(v3, "rMossAlb", `${v3}(0.0)`)}
${d(v2, "rMossP", `${v2}(0.0)`)}
${d(f, "rMossRough", "0.85")}
if (rMoss > 0.001) {
	${d(v2, "rMossUV", `rP.xz * ${u("rockTiles")}.y`)}
	${d(v2, "rMossDx", `rDx.xz * ${u("rockTiles")}.y`)}
	${d(v2, "rMossDy", `rDy.xz * ${u("rockTiles")}.y`)}
	${d(v4, "rMA", grad("rockMossAH", "rMossUV", "rMossDx", "rMossDy"))}
	${d(v4, "rMN", grad("rockMossNRO", "rMossUV", "rMossDx", "rMossDy"))}
	${d(v2, "rMv", `${v2}(1.0 - rMoss, rMoss) + 0.6 * ${v2}(rH, rMA.a) * smoothstep(${v2}(0.0), ${v2}(0.3), ${v2}(1.0 - rMoss, rMoss))`)}
	${d(f, "rMm", "max(rMv.x, rMv.y) - 0.12")}
	${d(v2, "rMb", `max(rMv - ${v2}(rMm), ${v2}(0.0))`)}
	rMoss = rMb.y / max(rMb.x + rMb.y, 1e-5);
	rMossAlb = ${lin("rMA.rgb")};
	rMossP = rockTN(rMN).xy;
	rMossRough = rMN.b;
}
${d(v3, "rFinal", "mix(rRockAlb, rMossAlb, rMoss)")}
rFinal = rFinal * mix(1.0, rVC.r, ${u("rockLook")}.z) * mix(1.0, rAO, 0.5);
${d(f, "rContact", `1.0 - smoothstep(0.0, ${u("rockLook")}.y, rVC.b)`)}
rFinal = mix(rFinal, rFinal * ${v3}(0.80, 0.74, 0.62), rContact * 0.6 * (1.0 - rMoss));
${d(f, "rWet", `${u("rockWeather")}.x`)}
rFinal = rFinal * mix(1.0, 0.72, rWet * 0.7) * ${u("rockWeather")}.yzw;
surfaceAlbedo = rFinal;
${d(v3, "rMossN", `normalize(rN + ${v3}(rMossP.x, 0.0, rMossP.y))`)}
normalW = normalize(mix(rDetailN, rMossN, rMoss));
rockRough = clamp(mix(rRough, rMossRough, rMoss) - 0.05 * rConvex + 0.05 * rConcave, 0.3, 1.0);
rockRough = mix(rockRough, 0.35, rWet * 0.6) * ${u("rockLook")}.x;
#endif`;
	return {
		CUSTOM_FRAGMENT_DEFINITIONS: `#ifdef TERRAIN_ROCK\n${fns}\n${samplers}\n#endif`,
		CUSTOM_FRAGMENT_BEFORE_LIGHTS: body,
		CUSTOM_FRAGMENT_UPDATE_METALLICROUGHNESS: `\n#ifdef TERRAIN_ROCK\nmetallicRoughness.g = rockRough;\n#endif`,
	};
}

const CODE = new Map<boolean, Record<string, string>>();
export function rockFragmentCode(language: ShaderLanguage): Record<string, string> {
	const wgsl = language === ShaderLanguage.WGSL;
	let c = CODE.get(wgsl);
	if (!c) { c = code(wgsl); CODE.set(wgsl, c); }
	return c;
}

function hexLinear(hex: string): [number, number, number] {
	const c = Color3.FromHexString(hex).toLinearSpace();
	return [c.r, c.g, c.b];
}

export class RockSurfacePlugin extends MaterialPluginBase {
	constructor(material: PBRMaterial, readonly options: RockMaterialOptions) {
		super(material, "RockSurface", 187, { TERRAIN_ROCK: false }, true, false);
		this.registerForExtraEvents = true;   // hardBindForSubMesh must run (rock uniforms), as impostors.ts:77
		this._enable(true);
	}
	isCompatible(language: ShaderLanguage): boolean { return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL; }
	getClassName(): string { return "RockSurfacePlugin"; }
	prepareDefines(defines: MaterialDefines, _scene: Scene, _mesh: AbstractMesh): void {
		(defines as unknown as Record<string, unknown>).TERRAIN_ROCK = true;
	}
	private textures(): Texture[] { const o = this.options; return [o.rockAH, o.rockNRO, o.mossAH, o.mossNRO]; }
	isReadyForSubMesh(): boolean { return this.textures().every(t => t.isReady()); }
	getSamplers(samplers: string[]): void { samplers.push(...ROCK_SAMPLERS); }
	getUniforms(language = ShaderLanguage.GLSL) {
		const declaration = language === ShaderLanguage.GLSL ? ROCK_UNIFORMS.map(n => `uniform vec4 ${n};`).join("\n") : "";
		return { ubo: ROCK_UNIFORMS.map(name => ({ name, size: 4, type: "vec4" })), fragment: declaration };
	}
	bindForSubMesh(buffer: UniformBuffer): void {
		const [a, b, c, d] = this.textures();
		buffer.setTexture("rockDetailAH", a);
		buffer.setTexture("rockDetailNRO", b);
		buffer.setTexture("rockMossAH", c);
		buffer.setTexture("rockMossNRO", d);
	}
	hardBindForSubMesh(buffer: UniformBuffer): void {
		const o = this.options;
		const strata = o.strata ?? STRATA[o.style];
		const dip = Math.tan(strata.dipDeg * Math.PI / 180), dir = strata.dipDirDeg * Math.PI / 180;
		buffer.updateFloat4("rockTiles", 1 / o.rockTile, 1 / o.mossTile, o.mossAllow ?? 0.5, 1);
		buffer.updateFloat4("rockStrata", strata.periodM, dip, Math.cos(dir), Math.sin(dir));
		const palette = o.palette ?? PALETTES[o.style];
		palette.forEach((hex, i) => { const [r, g, bl] = hexLinear(hex); buffer.updateFloat4(`rockPal${i}`, r, g, bl, 1); });
		const mean = o.rockMean ?? [0.18, 0.17, 0.15];
		buffer.updateFloat4("rockMean", mean[0], mean[1], mean[2], 1);
		const roughness = o.legacy?.roughness ?? 0.94;
		const albedo = o.legacy?.albedoColor;
		const wet = Math.max(0, Math.min(1, (0.94 - roughness) / 0.22));
		buffer.updateFloat4("rockWeather", wet, albedo ? albedo.r / 0.914 : 1, albedo ? albedo.g / 0.941 : 1, albedo ? albedo.b / 0.863 : 1);
		buffer.updateFloat4("rockLook", roughness / 0.94, 0.6, 0.7, 0.18);
	}
	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		return stage === "fragment" ? rockFragmentCode(language) : null;
	}
	getActiveTextures(active: BaseTexture[]): void { active.push(...this.textures()); }
	hasTexture(texture: BaseTexture): boolean { return this.textures().includes(texture as Texture); }
}

export function createRockMaterial(scene: Scene, name: string, options: RockMaterialOptions): PBRMaterial {
	const material = new PBRMaterial(name, scene);
	material.albedoColor = Color3.White();
	material.metallic = 0;
	material.roughness = 0.85;
	new RockSurfacePlugin(material, options);
	return material;
}
