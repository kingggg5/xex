import { Constants } from "@babylonjs/core/Engines/constants";
import { Material } from "@babylonjs/core/Materials/material";
import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import type { BaseTexture } from "@babylonjs/core/Materials/Textures/baseTexture";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { Scene } from "@babylonjs/core/scene";

/** Per-instance attribute: x intensity, y extra erosion, z alpha, w heat (cracks) — register with `mesh.registerInstancedBuffer(VFX_INSTANCE_KIND, 4)`. */
export const VFX_INSTANCE_KIND = "vfxInst";

export interface VfxSurfaceOptions {
	map: BaseTexture;
	noise: BaseTexture;
	/** Ramp colours (sRGB hex): value 1 -> core, midAt -> mid, 0 -> edge. */
	core: string;
	mid: string;
	edge: string;
	midAt?: number;
	intensity?: number;
	opacity?: number;
	/** "add" = additive glow, "blend" = alpha blended (smoke, scorch, abyss). */
	blend?: "add" | "blend";
	/** Fresnel rim for meshes (power; 0 = off). Uses the vertex colour R channel as an edge mask when present. */
	fresnel?: number;
	sheet?: { cols: number; rows: number };
	/** Erode from uv.v = 1 (tip) towards 0 instead of pure noise. */
	erodeAlongV?: boolean;
	/** Ground-crack mode: texture R = seam glow (ramp), G = scorch darkening in `scorch` colour. */
	scorch?: string;
	doubleSided?: boolean;
	depthWrite?: boolean;
	/** Texture value multiplier before the ramp: < 1 keeps full-strength strokes on the saturated mid colours. */
	valueScale?: number;
	fog?: boolean;
	/** Preserve an authored RGBA source colour instead of interpreting R as a greyscale ramp. */
	sourceColor?: boolean;
}

const UNIFORMS = ["vfxCore", "vfxMid", "vfxEdge", "vfxUv", "vfxFx", "vfxSheet", "vfxAux", "vfxTone"] as const;

/**
 * Unlit, ramp-coloured VFX surface on a StandardMaterial: greyscale-intensity textures are mapped to a
 * core/mid/edge palette, with radial wipe (draw-in), noise erosion with a glowing edge, UV spin/tiling/scroll,
 * flipbook cells, fresnel rims for meshes and per-instance intensity/erosion/alpha/heat. Colour is written
 * before fog and image processing, so ACES tone mapping and fog still apply. GLSL and WGSL.
 */
export class VfxSurfacePlugin extends MaterialPluginBase {
	/** Global VFX exposure compensation (e.g. 0.82 in daylight, 1 at night) applied to every surface. */
	static exposure = 1;
	core = new Color3();
	mid = new Color3();
	edge = new Color3();
	scorch = new Color3();
	midAt: number;
	intensity: number;
	opacity: number;
	rotation = 0;
	tiling = 1;
	scrollU = 0;
	scrollV = 0;
	/** 0..1 fraction of the circle drawn (clockwise from +V); 1 = complete. */
	wipe = 1;
	erosion = 0;
	erosionEdge = 0.06;
	frame = 0;
	noiseTiling = 1.5;
	heat = 1;
	valueScale: number;
	/** Additive layers: alpha *= clamp(value * addFade). */
	addFade = 2.2;
	/** Live source recolour and segmented-ring variants reuse the same compiled material. */
	sourceRecolorStrength=0;
	segments=0;
	readonly options: VfxSurfaceOptions;

	constructor(material: StandardMaterial, options: VfxSurfaceOptions) {
		super(material, "VfxSurface", 200, { VFX_SHEET: false, VFX_FRESNEL: false, VFX_EROSION_V: false, VFX_CRACKS: false, VFX_INST: false, VFX_ADD: false, VFX_SOURCE_COLOR:false }, true, false);
		this.options = options;
		this.setPalette(options.core, options.mid, options.edge, options.midAt ?? 0.55);
		if (options.scorch) this.scorch.copyFrom(Color3.FromHexString(options.scorch));
		this.midAt = options.midAt ?? 0.55;
		this.intensity = options.intensity ?? 1;
		this.opacity = options.opacity ?? 1;
		this.valueScale = options.valueScale ?? 1;
		this.registerForExtraEvents = true;  // hardBindForSubMesh uploads the live uniforms every draw
		this._enable(true);
	}

	setPalette(core: string, mid: string, edge: string, midAt = this.midAt): void {
		this.core.copyFrom(Color3.FromHexString(core));
		this.mid.copyFrom(Color3.FromHexString(mid));
		this.edge.copyFrom(Color3.FromHexString(edge));
		this.midAt = midAt;
	}

	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}

	isReadyForSubMesh(): boolean {
		return this.options.map.isReady() && this.options.noise.isReady();
	}

	prepareDefinesBeforeAttributes(defines: MaterialDefines): void {
		defines._needUVs = true;
		if (this.options.fresnel) defines._needNormals = true;
	}

	prepareDefines(defines: MaterialDefines, _scene: Scene, mesh: AbstractMesh): void {
		defines.VFX_SHEET = !!this.options.sheet;
		defines.VFX_FRESNEL = !!this.options.fresnel;
		defines.VFX_EROSION_V = !!this.options.erodeAlongV;
		defines.VFX_CRACKS = !!this.options.scorch;
		defines.VFX_INST = hasInstanceBuffer(mesh);
		defines.VFX_SOURCE_COLOR=!!this.options.sourceColor;
		// Additive layers: dim halo texels must fade to nothing, not to a saturated edge colour.
		defines.VFX_ADD = this.options.blend !== "blend" && !this.options.fresnel;
	}

	getAttributes(attributes: string[], _scene: Scene, mesh: AbstractMesh): void {
		if (hasInstanceBuffer(mesh)) attributes.push(VFX_INSTANCE_KIND);
	}

	getSamplers(samplers: string[]): void {
		samplers.push("vfxMapSampler", "vfxNoiseSampler");
	}

	getUniforms(language = ShaderLanguage.GLSL) {
		return {
			ubo: UNIFORMS.map(name => ({ name, size: 4, type: "vec4" })),
			fragment: language === ShaderLanguage.GLSL ? UNIFORMS.map(name => `uniform vec4 ${name};`).join("\n") : "",
		};
	}

	bindForSubMesh(buffer: UniformBuffer): void {
		buffer.setTexture("vfxMapSampler", this.options.map);
		buffer.setTexture("vfxNoiseSampler", this.options.noise);
	}

	hardBindForSubMesh(buffer: UniformBuffer): void {
		buffer.updateFloat4("vfxCore", this.core.r, this.core.g, this.core.b, this.midAt);
		buffer.updateFloat4("vfxMid", this.mid.r, this.mid.g, this.mid.b, this.intensity * VfxSurfacePlugin.exposure);
		buffer.updateFloat4("vfxEdge", this.edge.r, this.edge.g, this.edge.b, this.opacity);
		buffer.updateFloat4("vfxUv", this.rotation, this.tiling, this.scrollU, this.scrollV);
		buffer.updateFloat4("vfxFx", this.wipe, this.erosion, this.erosionEdge, this.options.fresnel ?? 0);
		const sheet = this.options.sheet;
		buffer.updateFloat4("vfxSheet", sheet?.cols ?? 1, sheet?.rows ?? 1, this.frame, this.noiseTiling);
		buffer.updateFloat4("vfxAux", this.scorch.r, this.scorch.g, this.scorch.b, this.heat);
		buffer.updateFloat4("vfxTone", this.valueScale, this.addFade, this.sourceRecolorStrength, this.segments);
	}

	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		const wgsl = language === ShaderLanguage.WGSL;
		if (stage === "vertex") {
			return wgsl ? {
				CUSTOM_VERTEX_DEFINITIONS: `
#if defined(VFX_INST) && defined(INSTANCES)
attribute vfxInst: vec4f;
#endif
varying vVfxUV: vec2f;
varying vVfxInst: vec4f;`,
				CUSTOM_VERTEX_MAIN_END: `
vertexOutputs.vVfxUV = uvUpdated;
#if defined(VFX_INST) && defined(INSTANCES)
vertexOutputs.vVfxInst = vertexInputs.vfxInst;
#else
vertexOutputs.vVfxInst = vec4f(1.0, 0.0, 1.0, 1.0);
#endif`,
			} : {
				CUSTOM_VERTEX_DEFINITIONS: `
#if defined(VFX_INST) && defined(INSTANCES)
attribute vec4 vfxInst;
#endif
varying vec2 vVfxUV;
varying vec4 vVfxInst;`,
				CUSTOM_VERTEX_MAIN_END: `
vVfxUV = uvUpdated;
#if defined(VFX_INST) && defined(INSTANCES)
vVfxInst = vfxInst;
#else
vVfxInst = vec4(1.0, 0.0, 1.0, 1.0);
#endif`,
			};
		}
		if (stage !== "fragment") return null;
		return wgsl ? WGSL_FRAGMENT : GLSL_FRAGMENT;
	}

	getClassName(): string {
		return "VfxSurfacePlugin";
	}
}

function hasInstanceBuffer(mesh: AbstractMesh): boolean {
	const buffers = (mesh as Mesh).instancedBuffers as Record<string, unknown> | undefined;
	return !!buffers && VFX_INSTANCE_KIND in buffers;
}

const GLSL_FRAGMENT = {
	CUSTOM_FRAGMENT_DEFINITIONS: `
uniform sampler2D vfxMapSampler;
uniform sampler2D vfxNoiseSampler;
varying vec2 vVfxUV;
varying vec4 vVfxInst;
vec3 vfxRamp(float v, vec4 core, vec4 mid, vec4 edge) {
	vec3 low = mix(edge.rgb, mid.rgb, clamp(v / max(core.a, 0.001), 0.0, 1.0));
	vec3 high = mix(mid.rgb, core.rgb, clamp((v - core.a) / max(1.0 - core.a, 0.001), 0.0, 1.0));
	return v < core.a ? low : high;
}`,
	CUSTOM_FRAGMENT_BEFORE_FOG: `
vec2 vfxP = vVfxUV - 0.5;
float vfxSin = sin(vfxUv.x);
float vfxCos = cos(vfxUv.x);
vec2 vfxQ = vec2(vfxCos * vfxP.x - vfxSin * vfxP.y, vfxSin * vfxP.x + vfxCos * vfxP.y) * vfxUv.y + 0.5 + vfxUv.zw;
#ifdef VFX_SHEET
float vfxFrame = floor(vfxSheet.z + 0.5);
vec2 vfxCell = vec2(vfxFrame - vfxSheet.x * floor(vfxFrame / vfxSheet.x), vfxSheet.y - 1.0 - floor(vfxFrame / vfxSheet.x));
vfxQ = (vfxCell + clamp(vfxQ, 0.002, 0.998)) / vfxSheet.xy;
#endif
vec4 vfxTex = texture2D(vfxMapSampler, vfxQ);
vec4 vfxNoiseTex = texture2D(vfxNoiseSampler, vVfxUV * vfxSheet.w + vfxUv.zw * 0.37);
float vfxF = fract(atan(vfxP.x, vfxP.y) / 6.28318531 + 1.0);
float vfxFull = step(0.999, vfxFx.x);
float vfxWipe = max(1.0 - smoothstep(vfxFx.x - 0.012, vfxFx.x, vfxF), vfxFull);
float vfxHead = (1.0 - vfxFull) * (1.0 - smoothstep(0.0, 0.05, vfxFx.x - vfxF)) * step(vfxF, vfxFx.x);
float vfxNoise = vfxNoiseTex.r;
#ifdef VFX_EROSION_V
vfxNoise = vfxNoise * 0.35 + (1.0 - vVfxUV.y) * 0.65;
#endif
float vfxErosion = vfxFx.y + vVfxInst.y;
float vfxCut = vfxNoise - vfxErosion;
float vfxKeep = mix(1.0, smoothstep(0.0, 0.015, vfxCut), step(0.0005, vfxErosion));
float vfxErodeGlow = (1.0 - smoothstep(0.0, max(vfxFx.z, 0.001), vfxCut)) * step(0.0005, vfxErosion) * step(0.0, vfxCut);
float vfxValue = vfxTex.r * vfxTone.x;
float vfxAlpha = vfxTex.a;
#ifdef VFX_SOURCE_COLOR
vfxValue=max(max(vfxTex.r,vfxTex.g),vfxTex.b)*vfxTone.x;
vfxAlpha*=smoothstep(0.025,0.075,vfxAlpha);
#endif
#ifdef VFX_FRESNEL
float vfxFres = pow(1.0 - abs(dot(normalize(vNormalW), normalize(vEyePosition.xyz - vPositionW))), vfxFx.w);
float vfxEdgeMask = 0.0;
#ifdef VERTEXCOLOR
vfxEdgeMask = vColor.r;
#endif
vfxValue = clamp(0.36 + vfxTex.r * 0.3 + vfxFres * 0.62 + vfxEdgeMask * 0.22, 0.0, 1.0);
vfxAlpha = clamp(0.62 + vfxFres * 0.5 + vfxEdgeMask * 0.2, 0.0, 1.0);
#endif
vfxValue = clamp(vfxValue + vfxHead * 0.8 + vfxErodeGlow, 0.0, 1.0);
vfxAlpha *= vfxWipe * vfxKeep * vfxEdge.a * vVfxInst.z;
if(vfxTone.w>1.0){float segmentPhase=fract(vfxF*vfxTone.w);vfxAlpha*=smoothstep(.025,.08,segmentPhase)*(1.0-smoothstep(.88,.98,segmentPhase));}
#ifdef VFX_ADD
vfxAlpha *= clamp(vfxValue * vfxTone.y, 0.0, 1.0);
#endif
#ifdef VERTEXALPHA
vfxAlpha *= vColor.a;
#endif
vec3 vfxRgb = vfxRamp(vfxValue, vfxCore, vfxMid, vfxEdge) * vfxMid.a * vVfxInst.x;
#ifdef VFX_SOURCE_COLOR
vfxRgb=mix(vfxTex.rgb,vfxRamp(vfxValue,vfxCore,vfxMid,vfxEdge),clamp(vfxTone.z,0.0,1.0))*vfxMid.a*vVfxInst.x;
#endif
#ifdef VFX_CRACKS
float vfxSeam = vfxTex.r * vfxAux.a * vVfxInst.w;
vfxRgb = mix(vfxAux.rgb, vfxRamp(vfxTex.r, vfxCore, vfxMid, vfxEdge) * vfxMid.a * vVfxInst.x, clamp(vfxSeam * 1.5, 0.0, 1.0));
vfxAlpha = clamp(max(vfxTex.g * vfxTex.a * 0.8, vfxSeam), 0.0, 1.0) * vfxKeep * vfxEdge.a * vVfxInst.z;
#endif
vfxRgb /= max(1.0, max(max(vfxRgb.r,vfxRgb.g),vfxRgb.b)/1.25);
color = vec4(vfxRgb, clamp(vfxAlpha, 0.0, 1.0));`,
};

const WGSL_FRAGMENT = {
	CUSTOM_FRAGMENT_DEFINITIONS: `
var vfxMapSamplerSampler: sampler;
var vfxMapSampler: texture_2d<f32>;
var vfxNoiseSamplerSampler: sampler;
var vfxNoiseSampler: texture_2d<f32>;
varying vVfxUV: vec2f;
varying vVfxInst: vec4f;
fn vfxRamp(v: f32, core: vec4f, mid: vec4f, edge: vec4f) -> vec3f {
	let low = mix(edge.rgb, mid.rgb, clamp(v / max(core.a, 0.001), 0.0, 1.0));
	let high = mix(mid.rgb, core.rgb, clamp((v - core.a) / max(1.0 - core.a, 0.001), 0.0, 1.0));
	return select(high, low, v < core.a);
}`,
	CUSTOM_FRAGMENT_BEFORE_FOG: `
let vfxP = fragmentInputs.vVfxUV - vec2f(0.5);
let vfxSin = sin(uniforms.vfxUv.x);
let vfxCos = cos(uniforms.vfxUv.x);
var vfxQ = vec2f(vfxCos * vfxP.x - vfxSin * vfxP.y, vfxSin * vfxP.x + vfxCos * vfxP.y) * uniforms.vfxUv.y + vec2f(0.5) + uniforms.vfxUv.zw;
#ifdef VFX_SHEET
let vfxFrame = floor(uniforms.vfxSheet.z + 0.5);
let vfxCell = vec2f(vfxFrame - uniforms.vfxSheet.x * floor(vfxFrame / uniforms.vfxSheet.x), uniforms.vfxSheet.y - 1.0 - floor(vfxFrame / uniforms.vfxSheet.x));
vfxQ = (vfxCell + clamp(vfxQ, vec2f(0.002), vec2f(0.998))) / uniforms.vfxSheet.xy;
#endif
let vfxTex = textureSample(vfxMapSampler, vfxMapSamplerSampler, vfxQ);
let vfxNoiseTex = textureSample(vfxNoiseSampler, vfxNoiseSamplerSampler, fragmentInputs.vVfxUV * uniforms.vfxSheet.w + uniforms.vfxUv.zw * 0.37);
let vfxF = fract(atan2(vfxP.x, vfxP.y) / 6.28318531 + 1.0);
let vfxFull = step(0.999, uniforms.vfxFx.x);
let vfxWipe = max(1.0 - smoothstep(uniforms.vfxFx.x - 0.012, uniforms.vfxFx.x, vfxF), vfxFull);
let vfxHead = (1.0 - vfxFull) * (1.0 - smoothstep(0.0, 0.05, uniforms.vfxFx.x - vfxF)) * step(vfxF, uniforms.vfxFx.x);
var vfxNoise = vfxNoiseTex.r;
#ifdef VFX_EROSION_V
vfxNoise = vfxNoise * 0.35 + (1.0 - fragmentInputs.vVfxUV.y) * 0.65;
#endif
let vfxErosion = uniforms.vfxFx.y + fragmentInputs.vVfxInst.y;
let vfxCut = vfxNoise - vfxErosion;
let vfxKeep = mix(1.0, smoothstep(0.0, 0.015, vfxCut), step(0.0005, vfxErosion));
let vfxErodeGlow = (1.0 - smoothstep(0.0, max(uniforms.vfxFx.z, 0.001), vfxCut)) * step(0.0005, vfxErosion) * step(0.0, vfxCut);
var vfxValue = vfxTex.r * uniforms.vfxTone.x;
var vfxAlpha = vfxTex.a;
#ifdef VFX_SOURCE_COLOR
vfxValue=max(max(vfxTex.r,vfxTex.g),vfxTex.b)*uniforms.vfxTone.x;
vfxAlpha=vfxAlpha*smoothstep(0.025,0.075,vfxAlpha);
#endif
#ifdef VFX_FRESNEL
let vfxFres = pow(1.0 - abs(dot(normalize(fragmentInputs.vNormalW), normalize(scene.vEyePosition.xyz - fragmentInputs.vPositionW))), uniforms.vfxFx.w);
var vfxEdgeMask = 0.0;
#ifdef VERTEXCOLOR
vfxEdgeMask = fragmentInputs.vColor.r;
#endif
vfxValue = clamp(0.36 + vfxTex.r * 0.3 + vfxFres * 0.62 + vfxEdgeMask * 0.22, 0.0, 1.0);
vfxAlpha = clamp(0.62 + vfxFres * 0.5 + vfxEdgeMask * 0.2, 0.0, 1.0);
#endif
vfxValue = clamp(vfxValue + vfxHead * 0.8 + vfxErodeGlow, 0.0, 1.0);
vfxAlpha = vfxAlpha * vfxWipe * vfxKeep * uniforms.vfxEdge.a * fragmentInputs.vVfxInst.z;
if(uniforms.vfxTone.w>1.0){let segmentPhase=fract(vfxF*uniforms.vfxTone.w);vfxAlpha=vfxAlpha*smoothstep(.025,.08,segmentPhase)*(1.0-smoothstep(.88,.98,segmentPhase));}
#ifdef VFX_ADD
vfxAlpha = vfxAlpha * clamp(vfxValue * uniforms.vfxTone.y, 0.0, 1.0);
#endif
#ifdef VERTEXALPHA
vfxAlpha = vfxAlpha * fragmentInputs.vColor.a;
#endif
var vfxRgb = vfxRamp(vfxValue, uniforms.vfxCore, uniforms.vfxMid, uniforms.vfxEdge) * uniforms.vfxMid.a * fragmentInputs.vVfxInst.x;
#ifdef VFX_SOURCE_COLOR
vfxRgb=mix(vfxTex.rgb,vfxRamp(vfxValue,uniforms.vfxCore,uniforms.vfxMid,uniforms.vfxEdge),clamp(uniforms.vfxTone.z,0.0,1.0))*uniforms.vfxMid.a*fragmentInputs.vVfxInst.x;
#endif
#ifdef VFX_CRACKS
let vfxSeam = vfxTex.r * uniforms.vfxAux.a * fragmentInputs.vVfxInst.w;
vfxRgb = mix(uniforms.vfxAux.rgb, vfxRamp(vfxTex.r, uniforms.vfxCore, uniforms.vfxMid, uniforms.vfxEdge) * uniforms.vfxMid.a * fragmentInputs.vVfxInst.x, clamp(vfxSeam * 1.5, 0.0, 1.0));
vfxAlpha = clamp(max(vfxTex.g * vfxTex.a * 0.8, vfxSeam), 0.0, 1.0) * vfxKeep * uniforms.vfxEdge.a * fragmentInputs.vVfxInst.z;
#endif
vfxRgb = vfxRgb / max(1.0,max(max(vfxRgb.r,vfxRgb.g),vfxRgb.b)/1.25);
color = vec4f(vfxRgb, clamp(vfxAlpha, 0.0, 1.0));`,
};

/** A StandardMaterial configured as an unlit VFX surface; returns the material and its live controls. */
export function createVfxMaterial(scene: Scene, name: string, options: VfxSurfaceOptions): { material: StandardMaterial; fx: VfxSurfacePlugin } {
	const material = new StandardMaterial(name, scene);
	material.disableLighting = true;
	material.specularColor = Color3.Black();
	material.diffuseColor = Color3.Black();
	material.transparencyMode = Material.MATERIAL_ALPHABLEND;
	material.alphaMode = options.blend === "blend" ? Constants.ALPHA_COMBINE : Constants.ALPHA_ADD;
	material.alpha = 0.999;
	material.backFaceCulling = !options.doubleSided;
	material.disableDepthWrite = !options.depthWrite;
	material.fogEnabled = options.fog ?? true;
	const fx = new VfxSurfacePlugin(material, options);
	return { material, fx };
}
