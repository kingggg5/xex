import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import { Color3 } from "@babylonjs/core/Maths/math.color";

export interface GrassShadingOptions {
	/** sRGB albedo at the blade root. StandardMaterial lights in gamma space, so keep channels <= ~0.55
	 * or the noon sun (intensity ~1.8) clips them to white. */
	root: string;
	/** sRGB albedo at the blade tip (same clipping rule). */
	tip: string;
	/** World-space height (m) over which root -> tip runs. The meadow surface is flat at y = 0. */
	height?: number;
	/** 0 = geometric blade normal, 1 = straight up: blades take the same light as the ground they grow from. */
	upBend?: number;
}

/**
 * Painted-grass shading for blade/tuft meshes (art pass v1, 2026-10-02):
 * - albedo runs from a dark, ground-matched root to a lit tip over the blade height, so tufts sit in the
 *   ground instead of reading as dark spikes;
 * - lighting uses a mostly-up normal, so thin blades seen edge-on under a high sun or the moon are not black.
 * Replaces the material diffuse colour; vertex-colour jitter and wind displacement still apply. GLSL and WGSL.
 */
class GrassShadingPlugin extends MaterialPluginBase {
	private readonly root: Color3;
	private readonly tip: Color3;
	private readonly height: number;
	private readonly upBend: number;

	constructor(material: StandardMaterial, options: GrassShadingOptions) {
		super(material, "GrassShading", 190, { GRASS_SHADING: false }, true, false);
		this.root = Color3.FromHexString(options.root);
		this.tip = Color3.FromHexString(options.tip);
		this.height = Math.max(0.05, options.height ?? 0.8);
		this.upBend = Math.max(0, Math.min(1, options.upBend ?? 0.8));
		this.registerForExtraEvents = true;  // hardBindForSubMesh uploads the uniforms on every draw
		this._enable(true);
	}

	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}

	prepareDefines(defines: MaterialDefines): void {
		defines.GRASS_SHADING = true;
	}

	getUniforms(language = ShaderLanguage.GLSL) {
		return {
			ubo: [{ name: "grassRoot", size: 4, type: "vec4" }, { name: "grassTip", size: 4, type: "vec4" }],
			fragment: language === ShaderLanguage.GLSL ? "uniform vec4 grassRoot;\nuniform vec4 grassTip;" : "",
		};
	}

	hardBindForSubMesh(buffer: UniformBuffer): void {
		buffer.updateFloat4("grassRoot", this.root.r, this.root.g, this.root.b, this.height);
		buffer.updateFloat4("grassTip", this.tip.r, this.tip.g, this.tip.b, this.upBend);
	}

	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		if (stage !== "fragment") return null;
		if (language === ShaderLanguage.WGSL) {
			return {
				CUSTOM_FRAGMENT_UPDATE_DIFFUSE: `
					#ifdef GRASS_SHADING
					let grassT = clamp(fragmentInputs.vPositionW.y / uniforms.grassRoot.w, 0.0, 1.0);
					diffuseColor = mix(uniforms.grassRoot.rgb, uniforms.grassTip.rgb, grassT * grassT * (3.0 - 2.0 * grassT));
					#endif`,
				CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
					#ifdef GRASS_SHADING
					normalW = normalize(mix(normalW, vec3f(0.0, 1.0, 0.0), uniforms.grassTip.w));
					#endif`,
			};
		}
		return {
			CUSTOM_FRAGMENT_UPDATE_DIFFUSE: `
				#ifdef GRASS_SHADING
				float grassT = clamp(vPositionW.y / grassRoot.w, 0.0, 1.0);
				diffuseColor = mix(grassRoot.rgb, grassTip.rgb, grassT * grassT * (3.0 - 2.0 * grassT));
				#endif`,
			CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
				#ifdef GRASS_SHADING
				normalW = normalize(mix(normalW, vec3(0.0, 1.0, 0.0), grassTip.w));
				#endif`,
		};
	}
}

export function addGrassShading(material: StandardMaterial, options: GrassShadingOptions): void {
	new GrassShadingPlugin(material, options);
	// Painted grass is matte; the shared palette's specular made blades look like plastic.
	material.specularColor = Color3.Black();
}
