import { BoundingInfo } from "@babylonjs/core/Culling/boundingInfo";
import { Material } from "@babylonjs/core/Materials/material";
import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import { DitheredTileFadeMaterialPlugin } from "@babylonjs/core/Materials/ditheredTileFadeMaterialPlugin";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Matrix, Quaternion, Vector3 } from "@babylonjs/core/Maths/math.vector";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { Geometry } from "@babylonjs/core/Meshes/geometry";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import "@babylonjs/core/Meshes/thinInstanceMesh";
import "@babylonjs/core/Shaders/ShadersInclude/bayerDitherFunctions";
import "@babylonjs/core/ShadersWGSL/ShadersInclude/bayerDitherFunctions";
import type { Observer } from "@babylonjs/core/Misc/observable";
import type { Scene } from "@babylonjs/core/scene";
import { cardCentre, crossFade, densityKeeps, gridParams, treeLod1Distance, treeLodState } from "./impostor-math.mjs";
import type { TreeLodPlan, TreeLodState } from "./impostor-math.mjs";

/** `xexoria.impostor-atlas/2`, written by assets/blender/tools/impostor_baker.py. */
export interface ImpostorAtlasManifest {
	schema: "xexoria.impostor-atlas/2";
	name: string;
	frame_px: number;
	grid: { azimuth: number; elevation: number; el_min_deg: number; el_max_deg: number; az0_angle_rad: number; az_sign: number };
	pages: Array<{ albedo: string; normal: string; albedo_ktx2?: string; normal_ktx2?: string; cols: number; rows: number; width_px: number; height_px: number }>;
	objects: Array<{ id: string; page: number; col: number; row: number; card_size_m: number; height_m: number; center_from_origin: [number, number, number] }>;
	shading?: { emissive?: [number, number, number]; specular?: [number, number, number]; alpha_cutoff?: number; link_emissive_with_diffuse?: boolean;
		/** f = albedo_scale + view_light_slope * dot(V, L): compensates the normal-averaging bias of baked texels. */
		albedo_scale?: number; view_light_slope?: number };
}

export interface ImpostorOptions {
	/** Prefer KTX2 pages when the manifest lists them (requires configureAssetCodecs()). Default true. */
	ktx2?: boolean;
	/** 0.5 = linear blend across the whole gap between baked views; smaller = crisper, less ghosting. Default 0.28. */
	blendSharpness?: number;
	/** Alpha-coverage preservation per mip level (Golus): alpha *= 1 + lod * k. Default 0.22. */
	mipCoverage?: number;
	/** Highest mip used (keeps neighbouring cells from bleeding). Default 4. */
	maxLod?: number;
	/** Initial instance capacity per atlas page. Default 64 (grows by doubling). */
	capacity?: number;
	/** Light used for the view-light compensation; default: the first enabled DirectionalLight (sun or moon). */
	light?: DirectionalLight;
}

export interface ImpostorHandle { readonly id: number; readonly objectId: string }

export interface ImpostorField {
	readonly manifest: ImpostorAtlasManifest;
	readonly meshes: readonly Mesh[];
	readonly count: number;
	/** Place a card for `objectId` at its asset origin (x, y, z), with yaw (Babylon RotationY) and uniform scale. */
	add(objectId: string, x: number, y: number, z: number, yaw?: number, scale?: number): ImpostorHandle;
	/** Screen-door fade: the card draws where the 8x8 Bayer value lies in [lower, upper). */
	setFade(handle: ImpostorHandle, lower: number, upper: number): void;
	setHidden(handle: ImpostorHandle, hidden: boolean): void;
	remove(handle: ImpostorHandle): void;
	/** Resolves when textures are loaded and every page material is compiled (call after the first add). */
	whenReady(): Promise<void>;
	dispose(): void;
}

const UNIFORMS = ["impostorGrid", "impostorGrid2", "impostorView", "impostorShade", "impostorLight"] as const;
const DATA_KIND = "impostorData";

class ImpostorPlugin extends MaterialPluginBase {
	constructor(material: StandardMaterial, private readonly albedo: Texture, private readonly normal: Texture,
		private readonly grid: ReturnType<typeof gridParams>, private readonly page: { cols: number; rows: number },
		private readonly framePx: number, private readonly options: Required<Omit<ImpostorOptions, "ktx2" | "capacity" | "light">>, private readonly cutoff: number,
		private readonly albedoScale: number, private readonly viewLightSlope: number, private readonly light: DirectionalLight | undefined) {
		super(material, "Impostor", 210, { IMPOSTOR: false }, true, false, true);
		this.registerForExtraEvents = true;
		this._enable(true);
	}

	isCompatible(language: ShaderLanguage): boolean { return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL; }
	isReadyForSubMesh(): boolean { return this.albedo.isReady() && this.normal.isReady(); }

	prepareDefines(defines: MaterialDefines, _scene: Scene, mesh: AbstractMesh): void {
		defines.IMPOSTOR = (mesh as Mesh).hasThinInstances === true;
	}

	getAttributes(attributes: string[], _scene: Scene, mesh: AbstractMesh): void {
		if ((mesh as Mesh).hasThinInstances) attributes.push(DATA_KIND);
	}

	getSamplers(samplers: string[]): void { samplers.push("impostorAlbedoSampler", "impostorNormalSampler"); }

	getUniforms(language = ShaderLanguage.GLSL) {
		const declaration = language === ShaderLanguage.GLSL ? UNIFORMS.map(name => `uniform vec4 ${name};`).join("\n") : "";
		return { ubo: UNIFORMS.map(name => ({ name, size: 4, type: "vec4" })), vertex: declaration, fragment: declaration };
	}

	bindForSubMesh(buffer: UniformBuffer): void {
		buffer.setTexture("impostorAlbedoSampler", this.albedo);
		buffer.setTexture("impostorNormalSampler", this.normal);
	}

	hardBindForSubMesh(buffer: UniformBuffer, scene: Scene): void {
		const camera = scene.activeCamera;
		const height = scene.getEngine().getRenderHeight();
		// Screen pixels per metre at 1 m for a vertical-FOV perspective camera.
		const pixelsPerMetre = camera ? height / (2 * Math.tan((camera.fov || 0.8) / 2)) : height;
		const g = this.grid;
		buffer.updateFloat4("impostorGrid", g.azimuth, g.elevation, g.elMin, g.elStep);
		buffer.updateFloat4("impostorGrid2", g.az0, g.azSign, this.page.cols, this.page.rows);
		buffer.updateFloat4("impostorView", pixelsPerMetre, this.framePx, this.options.maxLod, this.options.mipCoverage);
		buffer.updateFloat4("impostorShade", this.cutoff, this.options.blendSharpness, this.albedoScale, this.viewLightSlope);
		// Direction towards the main light (sun by day, moon by night) for the view-light compensation.
		const light = this.light ?? scene.lights.find((l): l is DirectionalLight => l instanceof DirectionalLight && l.isEnabled() && l.intensity > 0);
		if (light) {
			const d = light.direction;
			const len = Math.hypot(d.x, d.y, d.z) || 1;
			buffer.updateFloat4("impostorLight", -d.x / len, -d.y / len, -d.z / len, 1);
		} else buffer.updateFloat4("impostorLight", 0, 1, 0, 0);
	}

	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		const wgsl = language === ShaderLanguage.WGSL;
		if (stage === "vertex") return wgsl ? WGSL_VERTEX : GLSL_VERTEX;
		if (stage === "fragment") return wgsl ? WGSL_FRAGMENT : GLSL_FRAGMENT;
		return null;
	}

	getClassName(): string { return "ImpostorPlugin"; }
}

// Vertex: camera-facing card through the instance centre, frame selection in asset-local space (mirrors
// impostor-math.mjs frameCoordinates), per-card mip level from projected texel density.
const GLSL_VERTEX = {
	CUSTOM_VERTEX_DEFINITIONS: `
#ifdef IMPOSTOR
attribute vec4 impostorData;
varying vec4 vImpUV0;
varying vec4 vImpUV1;
varying vec4 vImpBlend;
varying vec4 vImpAxes;
varying vec2 vImpFade;
#endif`,
	CUSTOM_VERTEX_UPDATE_WORLDPOS: `
#ifdef IMPOSTOR
vec3 impCenter = finalWorld[3].xyz;
float impSize = length(finalWorld[0].xyz);
vec3 impX = finalWorld[0].xyz / max(impSize, 0.00001);
vec3 impZ = normalize(finalWorld[2].xyz);
vec3 impToEye = vEyePosition.xyz - impCenter;
float impDist = max(length(impToEye), 0.0001);
vec3 impDir = impToEye / impDist;
vec3 impF = -impDir;
vec3 impR = cross(vec3(0.0, 1.0, 0.0), impF);
float impRl = length(impR);
impR = impRl > 0.0001 ? impR / impRl : vec3(1.0, 0.0, 0.0);
vec3 impU = cross(impF, impR);
worldPos = vec4(impCenter + (impR * positionUpdated.x + impU * positionUpdated.y) * impSize, 1.0);
vec3 impL = vec3(dot(impDir, impX), impDir.y, dot(impDir, impZ));
float impStep = 6.28318531 / impostorGrid.x;
float impT = (atan(impL.x, impL.z) - impostorGrid2.x) * impostorGrid2.y / impStep;
impT = impT - impostorGrid.x * floor(impT / impostorGrid.x);
float impA0 = floor(impT);
float impWa = impT - impA0;
float impA1 = impA0 + 1.0;
impA1 = impA1 - impostorGrid.x * floor(impA1 / impostorGrid.x);
float impE = clamp((asin(clamp(impL.y, -1.0, 1.0)) - impostorGrid.z) / max(impostorGrid.w, 0.0001), 0.0, impostorGrid.y - 1.0);
float impE0 = min(floor(impE), max(impostorGrid.y - 2.0, 0.0));
float impE1 = min(impE0 + 1.0, impostorGrid.y - 1.0);
float impWe = clamp(impE - impE0, 0.0, 1.0);
vec2 impLocal = vec2(positionUpdated.x + 0.5, 0.5 - positionUpdated.y);
vec2 impCell = vec2(1.0 / impostorGrid2.z, 1.0 / impostorGrid2.w);
vec2 impBlock = impostorData.xy;
vImpUV0 = vec4((vec2(impBlock.x + impA0, impBlock.y + impE0) + impLocal) * impCell, (vec2(impBlock.x + impA1, impBlock.y + impE0) + impLocal) * impCell);
vImpUV1 = vec4((vec2(impBlock.x + impA0, impBlock.y + impE1) + impLocal) * impCell, (vec2(impBlock.x + impA1, impBlock.y + impE1) + impLocal) * impCell);
float impTexelsPerMetre = impostorView.y / max(impSize, 0.0001);
float impPixelsPerMetre = impostorView.x / impDist;
float impLod = clamp(log2(max(impTexelsPerMetre / max(impPixelsPerMetre, 0.0001), 1.0)), 0.0, impostorView.z);
float impComp = mix(1.0, clamp(impostorShade.z + impostorShade.w * dot(impDir, impostorLight.xyz), 0.6, 1.4), impostorLight.w);
vImpBlend = vec4(impWa, impWe, impLod, impComp);
vImpAxes = vec4(impX.x, impX.z, impZ.x, impZ.z);
vImpFade = impostorData.zw;
#endif`,
};

const WGSL_VERTEX = {
	CUSTOM_VERTEX_DEFINITIONS: `
#ifdef IMPOSTOR
attribute impostorData: vec4f;
varying vImpUV0: vec4f;
varying vImpUV1: vec4f;
varying vImpBlend: vec4f;
varying vImpAxes: vec4f;
varying vImpFade: vec2f;
#endif`,
	CUSTOM_VERTEX_UPDATE_WORLDPOS: `
#ifdef IMPOSTOR
let impCenter = finalWorld[3].xyz;
let impSize = length(finalWorld[0].xyz);
let impX = finalWorld[0].xyz / max(impSize, 0.00001);
let impZ = normalize(finalWorld[2].xyz);
let impToEye = scene.vEyePosition.xyz - impCenter;
let impDist = max(length(impToEye), 0.0001);
let impDir = impToEye / impDist;
let impF = -impDir;
let impRraw = cross(vec3f(0.0, 1.0, 0.0), impF);
let impRl = length(impRraw);
let impR = select(vec3f(1.0, 0.0, 0.0), impRraw / max(impRl, 0.0001), impRl > 0.0001);
let impU = cross(impF, impR);
worldPos = vec4f(impCenter + (impR * positionUpdated.x + impU * positionUpdated.y) * impSize, 1.0);
let impL = vec3f(dot(impDir, impX), impDir.y, dot(impDir, impZ));
let impStep = 6.28318531 / uniforms.impostorGrid.x;
var impT = (atan2(impL.x, impL.z) - uniforms.impostorGrid2.x) * uniforms.impostorGrid2.y / impStep;
impT = impT - uniforms.impostorGrid.x * floor(impT / uniforms.impostorGrid.x);
let impA0 = floor(impT);
let impWa = impT - impA0;
var impA1 = impA0 + 1.0;
impA1 = impA1 - uniforms.impostorGrid.x * floor(impA1 / uniforms.impostorGrid.x);
let impE = clamp((asin(clamp(impL.y, -1.0, 1.0)) - uniforms.impostorGrid.z) / max(uniforms.impostorGrid.w, 0.0001), 0.0, uniforms.impostorGrid.y - 1.0);
let impE0 = min(floor(impE), max(uniforms.impostorGrid.y - 2.0, 0.0));
let impE1 = min(impE0 + 1.0, uniforms.impostorGrid.y - 1.0);
let impWe = clamp(impE - impE0, 0.0, 1.0);
let impLocal = vec2f(positionUpdated.x + 0.5, 0.5 - positionUpdated.y);
let impCell = vec2f(1.0 / uniforms.impostorGrid2.z, 1.0 / uniforms.impostorGrid2.w);
let impBlock = vertexInputs.impostorData.xy;
vertexOutputs.vImpUV0 = vec4f((vec2f(impBlock.x + impA0, impBlock.y + impE0) + impLocal) * impCell, (vec2f(impBlock.x + impA1, impBlock.y + impE0) + impLocal) * impCell);
vertexOutputs.vImpUV1 = vec4f((vec2f(impBlock.x + impA0, impBlock.y + impE1) + impLocal) * impCell, (vec2f(impBlock.x + impA1, impBlock.y + impE1) + impLocal) * impCell);
let impTexelsPerMetre = uniforms.impostorView.y / max(impSize, 0.0001);
let impPixelsPerMetre = uniforms.impostorView.x / impDist;
let impLod = clamp(log2(max(impTexelsPerMetre / max(impPixelsPerMetre, 0.0001), 1.0)), 0.0, uniforms.impostorView.z);
let impComp = mix(1.0, clamp(uniforms.impostorShade.z + uniforms.impostorShade.w * dot(impDir, uniforms.impostorLight.xyz), 0.6, 1.4), uniforms.impostorLight.w);
vertexOutputs.vImpBlend = vec4f(impWa, impWe, impLod, impComp);
vertexOutputs.vImpAxes = vec4f(impX.x, impX.z, impZ.x, impZ.z);
vertexOutputs.vImpFade = vertexInputs.impostorData.zw;
#endif`,
};

// Fragment: bilinear blend of four baked views (albedo + object-space normals), mip-coverage alpha
// test, screen-door fade, then the material's own lighting/fog/image processing with the card normal.
const GLSL_FRAGMENT = {
	CUSTOM_FRAGMENT_DEFINITIONS: `
#ifdef IMPOSTOR
#include<bayerDitherFunctions>
uniform sampler2D impostorAlbedoSampler;
uniform sampler2D impostorNormalSampler;
varying vec4 vImpUV0;
varying vec4 vImpUV1;
varying vec4 vImpBlend;
varying vec4 vImpAxes;
varying vec2 vImpFade;
#endif`,
	CUSTOM_FRAGMENT_UPDATE_DIFFUSE: `
#ifdef IMPOSTOR
float impLod = vImpBlend.z;
float impNl = max(impLod - 1.0, 0.0);
vec4 impA00 = textureLod(impostorAlbedoSampler, vImpUV0.xy, impLod);
vec4 impA10 = textureLod(impostorAlbedoSampler, vImpUV0.zw, impLod);
vec4 impA01 = textureLod(impostorAlbedoSampler, vImpUV1.xy, impLod);
vec4 impA11 = textureLod(impostorAlbedoSampler, vImpUV1.zw, impLod);
vec4 impN00 = textureLod(impostorNormalSampler, vImpUV0.xy, impNl);
vec4 impN10 = textureLod(impostorNormalSampler, vImpUV0.zw, impNl);
vec4 impN01 = textureLod(impostorNormalSampler, vImpUV1.xy, impNl);
vec4 impN11 = textureLod(impostorNormalSampler, vImpUV1.zw, impNl);
float impWa = smoothstep(0.5 - impostorShade.y, 0.5 + impostorShade.y, vImpBlend.x);
float impWe = smoothstep(0.5 - impostorShade.y, 0.5 + impostorShade.y, vImpBlend.y);
vec4 impAlb = mix(mix(impA00, impA10, impWa), mix(impA01, impA11, impWa), impWe);
vec4 impNrm = mix(mix(impN00, impN10, impWa), mix(impN01, impN11, impWa), impWe);
float impAlpha = impAlb.a * (1.0 + impLod * impostorView.w);
float impDither = bayerDither8(floor(gl_FragCoord.xy)) / 64.0;
if (impAlpha < impostorShade.x || impDither < vImpFade.x || impDither >= vImpFade.y) discard;
vec3 impN = normalize(impNrm.xyz * 2.0 - 1.0);
normalW = normalize(vec3(vImpAxes.x, 0.0, vImpAxes.y) * impN.x + vec3(0.0, impN.y, 0.0) + vec3(vImpAxes.z, 0.0, vImpAxes.w) * impN.z);
baseColor = vec4(impAlb.rgb * vImpBlend.w, 1.0);
#endif`,
};

const WGSL_FRAGMENT = {
	CUSTOM_FRAGMENT_DEFINITIONS: `
#ifdef IMPOSTOR
#include<bayerDitherFunctions>
var impostorAlbedoSamplerSampler: sampler;
var impostorAlbedoSampler: texture_2d<f32>;
var impostorNormalSamplerSampler: sampler;
var impostorNormalSampler: texture_2d<f32>;
varying vImpUV0: vec4f;
varying vImpUV1: vec4f;
varying vImpBlend: vec4f;
varying vImpAxes: vec4f;
varying vImpFade: vec2f;
#endif`,
	CUSTOM_FRAGMENT_UPDATE_DIFFUSE: `
#ifdef IMPOSTOR
let impLod = fragmentInputs.vImpBlend.z;
let impNl = max(impLod - 1.0, 0.0);
let impA00 = textureSampleLevel(impostorAlbedoSampler, impostorAlbedoSamplerSampler, fragmentInputs.vImpUV0.xy, impLod);
let impA10 = textureSampleLevel(impostorAlbedoSampler, impostorAlbedoSamplerSampler, fragmentInputs.vImpUV0.zw, impLod);
let impA01 = textureSampleLevel(impostorAlbedoSampler, impostorAlbedoSamplerSampler, fragmentInputs.vImpUV1.xy, impLod);
let impA11 = textureSampleLevel(impostorAlbedoSampler, impostorAlbedoSamplerSampler, fragmentInputs.vImpUV1.zw, impLod);
let impN00 = textureSampleLevel(impostorNormalSampler, impostorNormalSamplerSampler, fragmentInputs.vImpUV0.xy, impNl);
let impN10 = textureSampleLevel(impostorNormalSampler, impostorNormalSamplerSampler, fragmentInputs.vImpUV0.zw, impNl);
let impN01 = textureSampleLevel(impostorNormalSampler, impostorNormalSamplerSampler, fragmentInputs.vImpUV1.xy, impNl);
let impN11 = textureSampleLevel(impostorNormalSampler, impostorNormalSamplerSampler, fragmentInputs.vImpUV1.zw, impNl);
let impWa = smoothstep(0.5 - uniforms.impostorShade.y, 0.5 + uniforms.impostorShade.y, fragmentInputs.vImpBlend.x);
let impWe = smoothstep(0.5 - uniforms.impostorShade.y, 0.5 + uniforms.impostorShade.y, fragmentInputs.vImpBlend.y);
let impAlb = mix(mix(impA00, impA10, impWa), mix(impA01, impA11, impWa), impWe);
let impNrm = mix(mix(impN00, impN10, impWa), mix(impN01, impN11, impWa), impWe);
let impAlpha = impAlb.a * (1.0 + impLod * uniforms.impostorView.w);
let impDither = bayerDither8(floor(fragmentInputs.position.xy)) / 64.0;
if (impAlpha < uniforms.impostorShade.x || impDither < fragmentInputs.vImpFade.x || impDither >= fragmentInputs.vImpFade.y) { discard; }
let impN = normalize(impNrm.xyz * 2.0 - 1.0);
normalW = normalize(vec3f(fragmentInputs.vImpAxes.x, 0.0, fragmentInputs.vImpAxes.y) * impN.x + vec3f(0.0, impN.y, 0.0) + vec3f(fragmentInputs.vImpAxes.z, 0.0, fragmentInputs.vImpAxes.w) * impN.z);
baseColor = vec4f(impAlb.rgb * fragmentInputs.vImpBlend.w, 1.0);
#endif`,
};

interface PageBatch {
	mesh: Mesh;
	material: StandardMaterial;
	textures: Texture[];
	matrices: Float32Array;
	data: Float32Array;
	ids: Int32Array;
	count: number;
	dirty: boolean;
	/** The arrays currently bound as GPU buffers (rebound only when `grow` replaces them). */
	bound: Float32Array | null;
}

interface Slot { page: number; index: number; objectIndex: number; centre: [number, number, number]; size: number; yaw: number; hidden: boolean }

/**
 * Lit, view-blended impostor cards: one thin-instanced quad + StandardMaterial per atlas page, so each
 * page is one draw call however many trees it holds. Cards face the camera, pick and blend the four
 * nearest baked views in the asset's own space (instance yaw included), light with the scene's lights
 * through baked object-space normals, fog and tone-map like the real foliage, and support screen-door
 * fades that pair exactly with DitheredTileFadeMaterialPlugin on the real meshes.
 */
export function createImpostorField(scene: Scene, manifest: ImpostorAtlasManifest, resolveUrl: (file: string) => string,
	options: ImpostorOptions = {}): ImpostorField {
	if (manifest.schema !== "xexoria.impostor-atlas/2") throw new Error(`Unsupported impostor manifest ${manifest.schema}`);
	const settings = { blendSharpness: options.blendSharpness ?? 0.28, mipCoverage: options.mipCoverage ?? 0.22, maxLod: options.maxLod ?? 4 };
	const useKtx2 = options.ktx2 !== false;
	const grid = gridParams(manifest);
	const shading = manifest.shading ?? {};
	const objectIndex = new Map(manifest.objects.map((object, index) => [object.id, index]));
	const slots = new Map<number, Slot>();
	let nextId = 1;
	let disposed = false;
	const tmpMatrix = new Matrix();
	const tmpScale = new Vector3();
	const tmpPosition = new Vector3();
	const tmpRotation = new Quaternion();

	const pages: PageBatch[] = manifest.pages.map((page, index) => {
		const load = (png: string, ktx2: string | undefined, gamma: boolean) => {
			const texture = new Texture(resolveUrl(useKtx2 && ktx2 ? ktx2 : png), scene, false, false, Texture.TRILINEAR_SAMPLINGMODE);
			texture.wrapU = texture.wrapV = Texture.CLAMP_ADDRESSMODE;
			texture.gammaSpace = gamma;
			return texture;
		};
		const albedo = load(page.albedo, page.albedo_ktx2, true);
		const normal = load(page.normal, page.normal_ktx2, false);
		// Named *foliage* so world-weather dims its emissive fill at night like the leaf cards.
		const material = new StandardMaterial(`${manifest.name}-impostor-foliage-${index}`, scene);
		material.diffuseColor = Color3.White();
		material.specularColor = Color3.FromArray(shading.specular ?? [0, 0, 0]);
		material.emissiveColor = Color3.FromArray(shading.emissive ?? [0, 0, 0]);
		material.linkEmissiveWithDiffuse = shading.link_emissive_with_diffuse ?? true;
		material.backFaceCulling = false;
		material.transparencyMode = Material.MATERIAL_OPAQUE;
		new ImpostorPlugin(material, albedo, normal, grid, page, manifest.frame_px, settings, shading.alpha_cutoff ?? 0.5,
			shading.albedo_scale ?? 1, shading.view_light_slope ?? 0, options.light);
		const mesh = new Mesh(`${manifest.name}-impostors-${index}`, scene);
		const quad = new VertexData();
		quad.positions = [-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0];
		quad.normals = [0, 0, -1, 0, 0, -1, 0, 0, -1, 0, 0, -1];
		quad.indices = [0, 1, 2, 0, 2, 3];
		quad.applyToMesh(mesh, false);
		mesh.material = material;
		mesh.isPickable = false;
		mesh.receiveShadows = false;
		mesh.doNotSyncBoundingInfo = true;
		mesh.setEnabled(false);
		const capacity = options.capacity ?? 64;
		return { mesh, material, textures: [albedo, normal], matrices: new Float32Array(capacity * 16), data: new Float32Array(capacity * 4), ids: new Int32Array(capacity), count: 0, dirty: false, bound: null };
	});

	const grow = (batch: PageBatch) => {
		const capacity = batch.ids.length * 2;
		const matrices = new Float32Array(capacity * 16); matrices.set(batch.matrices);
		const data = new Float32Array(capacity * 4); data.set(batch.data);
		const ids = new Int32Array(capacity); ids.set(batch.ids);
		batch.matrices = matrices; batch.data = data; batch.ids = ids;
	};

	const writeSlot = (slot: Slot) => {
		const batch = pages[slot.page];
		const size = slot.hidden ? 0 : slot.size;
		tmpScale.setAll(size);
		Quaternion.RotationYawPitchRollToRef(slot.yaw, 0, 0, tmpRotation);
		tmpPosition.set(slot.centre[0], slot.centre[1], slot.centre[2]);
		Matrix.ComposeToRef(tmpScale, tmpRotation, tmpPosition, tmpMatrix);
		tmpMatrix.copyToArray(batch.matrices, slot.index * 16);
		batch.dirty = true;
	};

	const flush = () => {
		for (const batch of pages) {
			if (!batch.dirty) continue;
			batch.dirty = false;
			const mesh = batch.mesh;
			// Bind the full-capacity arrays once (again only after `grow`) and upload in place afterwards: fades change
			// every frame while the camera crosses a swap band, and recreating GPU buffers per frame is wasteful
			// (C-P1-TREE). The count never drops to 0 (that would toggle the thin-instance shader variant); an empty
			// page is disabled instead.
			if (batch.bound !== batch.matrices) {
				mesh.thinInstanceSetBuffer("matrix", batch.matrices, 16, false);
				mesh.thinInstanceSetBuffer(DATA_KIND, batch.data, 4, false);
				batch.bound = batch.matrices;
			}
			mesh.thinInstanceCount = Math.max(1, batch.count);
			mesh.thinInstanceBufferUpdated("matrix");
			mesh.thinInstanceBufferUpdated(DATA_KIND);
			mesh.setEnabled(batch.count > 0);
			if (batch.count === 0) continue;
			const min = new Vector3(Infinity, Infinity, Infinity);
			const max = new Vector3(-Infinity, -Infinity, -Infinity);
			for (const slot of slots.values()) {
				if (pages[slot.page] !== batch) continue;
				const r = slot.size * 0.75;
				min.minimizeInPlaceFromFloats(slot.centre[0] - r, slot.centre[1] - r, slot.centre[2] - r);
				max.maximizeInPlaceFromFloats(slot.centre[0] + r, slot.centre[1] + r, slot.centre[2] + r);
			}
			mesh.setBoundingInfo(new BoundingInfo(min, max));
		}
	};
	const observer: Observer<Scene> | null = scene.onBeforeRenderObservable.add(flush);

	const field: ImpostorField = {
		manifest,
		meshes: pages.map(p => p.mesh),
		get count() { return slots.size; },
		add(objectId, x, y, z, yaw = 0, scale = 1) {
			if (disposed) throw new Error("Impostor field is disposed");
			const index = objectIndex.get(objectId);
			if (index === undefined) throw new Error(`Unknown impostor object ${objectId}`);
			const object = manifest.objects[index];
			const batch = pages[object.page];
			if (batch.count >= batch.ids.length) grow(batch);
			const id = nextId++;
			const slot: Slot = { page: object.page, index: batch.count, objectIndex: index, centre: cardCentre(object, x, y, z, yaw, scale), size: object.card_size_m * scale, yaw, hidden: false };
			batch.ids[slot.index] = id;
			batch.data.set([object.col, object.row, 0, 1], slot.index * 4);
			batch.count += 1;
			slots.set(id, slot);
			writeSlot(slot);
			return { id, objectId };
		},
		setFade(handle, lower, upper) {
			const slot = slots.get(handle.id);
			if (!slot) return;
			const batch = pages[slot.page];
			batch.data[slot.index * 4 + 2] = lower;
			batch.data[slot.index * 4 + 3] = upper;
			batch.dirty = true;
		},
		setHidden(handle, hidden) {
			const slot = slots.get(handle.id);
			if (!slot || slot.hidden === hidden) return;
			slot.hidden = hidden;
			writeSlot(slot);
		},
		remove(handle) {
			const slot = slots.get(handle.id);
			if (!slot) return;
			const batch = pages[slot.page];
			const last = batch.count - 1;
			if (slot.index !== last) {
				// Swap the last card into the freed slot.
				batch.matrices.copyWithin(slot.index * 16, last * 16, last * 16 + 16);
				batch.data.copyWithin(slot.index * 4, last * 4, last * 4 + 4);
				const movedId = batch.ids[last];
				batch.ids[slot.index] = movedId;
				const moved = slots.get(movedId);
				if (moved) moved.index = slot.index;
			}
			batch.count = last;
			batch.dirty = true;
			slots.delete(handle.id);
		},
		async whenReady() {
			flush();
			await Promise.all(pages.flatMap(p => p.textures).map(t => new Promise<void>(resolve => t.isReady() ? resolve() : t.onLoadObservable.addOnce(() => resolve()))));
			for (const batch of pages) if (batch.count > 0) await batch.material.forceCompilationAsync(batch.mesh);
		},
		dispose() {
			if (disposed) return;
			disposed = true;
			scene.onBeforeRenderObservable.remove(observer);
			for (const batch of pages) {
				batch.mesh.dispose(false, false);
				batch.material.dispose(false, false);
				for (const texture of batch.textures) texture.dispose();
			}
			slots.clear();
		},
	};
	return field;
}

/** A real tree (its instanced parts) paired with an impostor card for distance cross-fading. */
export interface ImpostorLodEntry {
	readonly parts: readonly AbstractMesh[];
	readonly handle: ImpostorHandle;
	readonly position: Vector3;
}

/**
 * Distance LOD with a dithered cross-fade: inside `swap - band/2` only the real mesh draws, beyond
 * `swap + band/2` only the card, and in between both draw complementary screen-door halves (no pop,
 * no blending). Real materials get Babylon's DitheredTileFadeMaterialPlugin. Choose `swap` beyond the
 * cascaded-shadow distance so a tree's shadow does not vanish at the swap.
 */
export function createImpostorLod(scene: Scene, field: ImpostorField, entries: readonly ImpostorLodEntry[],
	options: { swap: number; band?: number; materials: readonly Material[] }): { update(): void; dispose(): void } {
	const band = options.band ?? 8;
	const plugins = new Map(options.materials.map(material => [material, DitheredTileFadeMaterialPlugin.GetOrCreate(material as StandardMaterial)] as const));
	const state = entries.map(() => -1);
	const update = () => {
		const camera = scene.activeCamera;
		if (!camera) return;
		const eye = camera.globalPosition;
		entries.forEach((entry, i) => {
			const t = Math.round(crossFade(Vector3.Distance(eye, entry.position), options.swap, band) * 64) / 64;
			if (t === state[i]) return;
			state[i] = t;
			for (const part of entry.parts) {
				part.setEnabled(t < 1);
				const plugin = part.material ? plugins.get(part.material) : undefined;
				if (t < 1 && plugin) plugin.setFadeBounds(part as Mesh, 0, 1 - t);
			}
			field.setHidden(entry.handle, t <= 0);
			field.setFade(entry.handle, 1 - t, 1);
		});
	};
	const observer = scene.onBeforeRenderObservable.add(update);
	return { update, dispose: () => { scene.onBeforeRenderObservable.remove(observer); } };
}

// -------------------------------------------------------------------------------------------------------------------
// Thin-instance tree LOD field (C-P1-TREE, docs/reviews/2026-10-02-trees-in-babylon.md)
//
// One thin-instance batch per (64 m world cell, species, LOD, material part): culling stays per cell, a batch is
// one draw call per pass, and every tree picks its own representation each frame (treeLodState):
//   LOD0 --(LOD1 screen coverage, 4 m dithered band)--> LOD1 --(shadow distance + 10 m, 10 m band)--> impostor card
//   --(detail draw distance)--> nothing.
// Inside a band the two representations draw complementary halves of the 8x8 Bayer screen-door, so there is no pop
// and no alpha blending: meshes through DitheredTileFadeMaterialPlugin per thin instance (recheck C14), cards through
// the impostor field's own fade. The plugin works in the colour pass only, so a fading tree keeps its full shadow;
// the swap sits beyond the cascaded-shadow distance anyway, which is why cards never need to cast.

/** One species: LOD0 and LOD1 part templates (one Mesh per material, geometry in asset space, hidden). */
export interface TreeLodSpecies {
	readonly lods: readonly [readonly Mesh[], readonly Mesh[]];
	/** Object id in the impostor manifest; omitted (bushes): the tree dissolves over the swap band instead. */
	readonly impostorId?: string;
	/** Bounding-sphere centre height and radius of the asset at scale 1, metres (LOD distance and coverage). */
	readonly centreY: number;
	readonly radius: number;
}

/** One placed tree. */
export interface TreeLodPlacement {
	readonly species: string;
	readonly x: number;
	readonly y: number;
	readonly z: number;
	readonly yaw: number;
	readonly scale: number;
	/** World cell key of the 64 m grid ("c7_r6"); one batch per species, LOD and part per cell. */
	readonly cell: string;
	/** Never thinned by vegetation density: authoritative collision blockers must stay visible. */
	readonly keep: boolean;
	/** Stable thinning index (densityKeeps). */
	readonly order: number;
	/** Diagnostics label (world prop id or spot index). */
	readonly id: string;
}

/** Plain data (a type alias, so it is assignable to the lookdev metadata records). */
export type TreeLodStats = {
	trees: number;
	drawn: { lod0: number; lod1: number; card: number; bands: number; hidden: number };
	batches: number;
	enabledBatches: number;
	cards: number;
};

export interface TreeLodField {
	readonly batches: readonly Mesh[];
	readonly plan: TreeLodPlan;
	/** Adds trees (cells that stream in later); returns the new batch meshes. */
	add(placements: readonly TreeLodPlacement[]): Mesh[];
	setPlan(plan: TreeLodPlan): void;
	update(): void;
	stats(): TreeLodStats;
	/** Diagnostics: every tree with its crown centre, radius and current representation (review captures). */
	list(): Array<{ id: string; species: string; cell: string; centre: [number, number, number]; radius: number; state: TreeLodState }>;
	dispose(): void;
}

interface TreeSlot {
	readonly placement: TreeLodPlacement;
	readonly group: TreeGroup;
	readonly world: Float32Array;
	readonly centre: Vector3;
	readonly radius: number;
	readonly handle: ImpostorHandle | null;
	state: TreeLodState;
	lod1Distance: number;
}

interface TreeGroup {
	readonly key: string;
	readonly members: TreeSlot[];
	/** batches[lod][part]: thin-instance meshes; matrices[lod]: capacity-sized matrix data shared by the LOD's parts. */
	readonly batches: [Mesh[], Mesh[]];
	readonly matrices: [Float32Array, Float32Array];
	dirty: boolean;
}

/**
 * A batch mesh drawing `template`'s vertex and index buffers through its own Geometry. Thin-instance buffers are
 * stored on the Geometry, so batches cannot be clones (clones share one Geometry, and every batch would then draw
 * the last batch's matrices). The vertex buffers themselves are shared and reference-counted by Geometry, and the
 * index buffer's reference count is raised here, so there is one GPU copy per species LOD whatever the batch count.
 */
function shareTemplateGeometry(scene: Scene, template: Mesh, name: string): Mesh {
	const source = template.geometry;
	const indexBuffer = source?.getIndexBuffer();
	if (!source || !indexBuffer) throw new Error(`Tree template ${template.name} has no indexed geometry`);
	const geometry = new Geometry(`${name}-geometry`, scene, undefined, false);
	for (const kind of source.getVerticesDataKinds()) {
		const buffer = source.getVertexBuffer(kind);
		if (buffer && !buffer.getIsInstanced()) geometry.setVerticesBuffer(buffer, source.getTotalVertices(), false);
	}
	indexBuffer.references++;
	geometry.setIndexBuffer(indexBuffer, source.getTotalVertices(), source.getTotalIndices(), indexBuffer.is32Bits);
	if (source.boundingBias) geometry.boundingBias = source.boundingBias;
	const mesh = new Mesh(name, scene);
	geometry.applyToMesh(mesh);
	mesh.material = template.material;
	mesh.sideOrientation = template.sideOrientation;
	mesh.receiveShadows = template.receiveShadows;
	mesh.useVertexColors = template.useVertexColors;
	return mesh;
}

const NO_TREE: TreeLodState = { lod0: null, lod1: null, card: null };
const sameRange = (a: readonly number[] | null, b: readonly number[] | null) =>
	a === b || (!!a && !!b && a[0] === b[0] && a[1] === b[1]);

/**
 * Thin-instance trees with per-tree LOD and dithered cross-fades (see the section comment above). `onBatch` runs
 * once per created batch mesh (shadow casters, glow tags); batch meshes are enabled only while they hold trees, and
 * their thin-instance count never drops to 0 (that would switch the shader variant and recompile).
 */
export function createTreeLodField(scene: Scene, species: Readonly<Record<string, TreeLodSpecies>>, options: {
	name: string; plan: TreeLodPlan; field?: ImpostorField | null; onBatch?(mesh: Mesh, lod: 0 | 1): void;
}): TreeLodField {
	let plan = options.plan;
	const field = options.field ?? null;
	const groups = new Map<string, TreeGroup>();
	const slots: TreeSlot[] = [];
	const batches: Mesh[] = [];
	const fadePlugins = new Map<Material, DitheredTileFadeMaterialPlugin>();
	const tmp = { m: new Matrix(), q: new Quaternion(), s: new Vector3(), p: new Vector3() };
	let disposed = false;

	const pluginFor = (material: Material | null) => {
		if (!material) return null;
		let plugin = fadePlugins.get(material);
		if (!plugin) {
			plugin = DitheredTileFadeMaterialPlugin.GetOrCreate(material as StandardMaterial);
			fadePlugins.set(material, plugin);
		}
		return plugin;
	};

	const makeGroup = (key: string, kind: TreeLodSpecies, capacity: number): TreeGroup => {
		const lodBatches: [Mesh[], Mesh[]] = [[], []];
		const matrices: [Float32Array, Float32Array] = [new Float32Array(capacity * 16), new Float32Array(capacity * 16)];
		for (const lod of [0, 1] as const) {
			kind.lods[lod].forEach((template, part) => {
				const mesh = shareTemplateGeometry(scene, template, `${options.name}-${key}-lod${lod}-${part}`);
				mesh.isVisible = true;
				mesh.isPickable = false;
				mesh.thinInstanceSetBuffer("matrix", matrices[lod], 16, false);
				mesh.thinInstanceCount = 1;
				mesh.setEnabled(false);
				mesh.freezeWorldMatrix();
				pluginFor(mesh.material);
				lodBatches[lod].push(mesh);
				batches.push(mesh);
				options.onBatch?.(mesh, lod);
			});
		}
		return { key, members: [], batches: lodBatches, matrices, dirty: true };
	};

	const rebuild = (group: TreeGroup) => {
		group.dirty = false;
		for (const lod of [0, 1] as const) {
			const pick = (slot: TreeSlot) => (lod === 0 ? slot.state.lod0 : slot.state.lod1);
			const members = group.members.filter(slot => pick(slot));
			const data = group.matrices[lod];
			members.forEach((slot, index) => data.set(slot.world, index * 16));
			for (const mesh of group.batches[lod]) {
				if (!members.length) { mesh.setEnabled(false); continue; }
				mesh.thinInstanceCount = members.length;
				mesh.thinInstanceBufferUpdated("matrix");
				const plugin = pluginFor(mesh.material);
				if (plugin) {
					members.forEach((slot, index) => {
						const [lower, upper] = pick(slot)!;
						plugin.setThinInstanceFadeBounds(mesh, index, lower, upper, false);
					});
					plugin.commitThinInstanceFadeBounds(mesh);
				}
				mesh.thinInstanceRefreshBoundingInfo(false);
				mesh.setEnabled(true);
			}
		}
	};

	// LOD1 distances depend on the camera's FOV and aspect and on the plan; recomputed only when one changes.
	const lod1Key = { fov: NaN, aspect: NaN, plan: null as TreeLodPlan | null };
	const refreshLod1 = (camera: NonNullable<Scene["activeCamera"]>): boolean => {
		const fov = camera.fov ?? 1.02;
		const aspect = scene.getEngine().getAspectRatio(camera);
		if (fov === lod1Key.fov && aspect === lod1Key.aspect && plan === lod1Key.plan) return false;
		lod1Key.fov = fov; lod1Key.aspect = aspect; lod1Key.plan = plan;
		for (const slot of slots) slot.lod1Distance = treeLod1Distance(plan, slot.radius, fov, aspect);
		return true;
	};
	// Skip the per-tree pass while the eye has not moved (2 cm) and nothing else changed: no work, no allocations.
	const lastEye = new Vector3(NaN, NaN, NaN);
	let stale = true;

	const update = () => {
		if (disposed) return;
		const camera = scene.activeCamera;
		if (!camera) return;
		const lodChanged = refreshLod1(camera);
		// Runs before the frame's own camera update: sync the view (cached when nothing moved) so globalPosition is current.
		camera.getViewMatrix();
		const eye = camera.globalPosition;
		if (!stale && !lodChanged && Vector3.DistanceSquared(eye, lastEye) < 0.0004) return;
		stale = false;
		lastEye.copyFrom(eye);
		for (const slot of slots) {
			const p = slot.placement;
			const shown = p.keep || densityKeeps(p.order, plan.density);
			const next = shown ? treeLodState(Vector3.Distance(eye, slot.centre), plan, slot.lod1Distance, slot.handle !== null) : NO_TREE;
			const prev = slot.state;
			if (!sameRange(prev.lod0, next.lod0) || !sameRange(prev.lod1, next.lod1)) slot.group.dirty = true;
			if (slot.handle && field && !sameRange(prev.card, next.card)) {
				field.setHidden(slot.handle, !next.card);
				if (next.card) field.setFade(slot.handle, next.card[0], next.card[1]);
			}
			slot.state = next;
		}
		for (const group of groups.values()) if (group.dirty) rebuild(group);
	};

	const add = (placements: readonly TreeLodPlacement[]): Mesh[] => {
		const created = batches.length;
		const byGroup = new Map<string, TreeLodPlacement[]>();
		for (const p of placements) {
			if (!species[p.species]) throw new Error(`Unknown tree species ${p.species}`);
			const key = `${p.cell}-${p.species}`;
			byGroup.set(key, [...(byGroup.get(key) ?? []), p]);
		}
		for (const [key, list] of byGroup) {
			// A cell that is re-added (a retried cell load) keeps its first trees.
			if (groups.has(key)) { console.warn(`Tree group ${key} already exists; its trees are kept, the new ones skipped.`); continue; }
			const kind = species[list[0].species];
			const group = makeGroup(key, kind, list.length);
			groups.set(key, group);
			for (const p of list) {
				tmp.s.setAll(p.scale);
				Quaternion.RotationYawPitchRollToRef(p.yaw, 0, 0, tmp.q);
				tmp.p.set(p.x, p.y, p.z);
				Matrix.ComposeToRef(tmp.s, tmp.q, tmp.p, tmp.m);
				const world = new Float32Array(16);
				tmp.m.copyToArray(world);
				const handle = field && kind.impostorId ? field.add(kind.impostorId, p.x, p.y, p.z, p.yaw, p.scale) : null;
				if (handle && field) field.setHidden(handle, true);
				const slot: TreeSlot = { placement: p, group, world, centre: new Vector3(p.x, p.y + kind.centreY * p.scale, p.z),
					radius: kind.radius * p.scale, handle, state: NO_TREE, lod1Distance: 0 };
				group.members.push(slot);
				slots.push(slot);
			}
		}
		lod1Key.plan = null;
		stale = true;
		update();
		return batches.slice(created);
	};

	const observer = scene.onBeforeRenderObservable.add(update);
	return {
		get batches() { return batches; },
		get plan() { return plan; },
		add,
		setPlan(next) { plan = next; stale = true; update(); },
		update,
		stats() {
			const drawn = { lod0: 0, lod1: 0, card: 0, bands: 0, hidden: 0 };
			for (const slot of slots) {
				const s = slot.state;
				const n = (s.lod0 ? 1 : 0) + (s.lod1 ? 1 : 0) + (s.card ? 1 : 0);
				if (s.lod0) drawn.lod0++;
				if (s.lod1) drawn.lod1++;
				if (s.card) drawn.card++;
				if (n > 1) drawn.bands++;
				if (n === 0) drawn.hidden++;
			}
			return { trees: slots.length, drawn, batches: batches.length, enabledBatches: batches.filter(mesh => mesh.isEnabled()).length, cards: field?.count ?? 0 };
		},
		list() {
			return slots.map(slot => ({ id: slot.placement.id, species: slot.placement.species, cell: slot.placement.cell,
				centre: [slot.centre.x, slot.centre.y, slot.centre.z] as [number, number, number], radius: slot.radius, state: slot.state }));
		},
		dispose() {
			if (disposed) return;
			disposed = true;
			scene.onBeforeRenderObservable.remove(observer);
			for (const mesh of batches) mesh.dispose(false, false);
			for (const slot of slots) if (slot.handle) field?.remove(slot.handle);
			batches.length = 0;
			slots.length = 0;
			groups.clear();
		},
	};
}
