import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";

/** Broad botanical/soil variation over the shared file texture; stable in world space. */
class MeadowSurfacePlugin extends MaterialPluginBase {
	constructor(material: PBRMaterial) {
		super(material, "MeadowSurface", 185, {}, true, false);
		this._enable(true);
	}
	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}
	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		if (stage !== "fragment") return null;
		const wgsl = language === ShaderLanguage.WGSL;
		const v2 = wgsl ? "vec2f" : "vec2";
		const v3 = wgsl ? "vec3f" : "vec3";
		const variable = wgsl ? "var" : "float";
		const pos = wgsl ? "fragmentInputs.vPositionW" : "vPositionW";
		const definitions = wgsl ? `
			fn meadowHash(p: vec2f) -> f32 { return fract(sin(dot(p, vec2f(127.1, 311.7))) * 43758.5453); }
			fn meadowNoise(p: vec2f) -> f32 {
				let i = floor(p); let f = fract(p); let u = f * f * (vec2f(3.0) - 2.0 * f);
				return mix(mix(meadowHash(i), meadowHash(i + vec2f(1.0, 0.0)), u.x),
					mix(meadowHash(i + vec2f(0.0, 1.0)), meadowHash(i + vec2f(1.0, 1.0)), u.x), u.y);
			}` : `
			float meadowHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
			float meadowNoise(vec2 p) {
				vec2 i = floor(p); vec2 f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
				return mix(mix(meadowHash(i), meadowHash(i + vec2(1.0, 0.0)), u.x),
					mix(meadowHash(i + vec2(0.0, 1.0)), meadowHash(i + vec2(1.0, 1.0)), u.x), u.y);
			}`;
		return {
			CUSTOM_FRAGMENT_DEFINITIONS: definitions,
			CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
				${variable} meadowBroad = meadowNoise(${pos}.xz * 0.055 + ${v2}(4.8, -1.7));
				${variable} meadowFine = meadowNoise(${pos}.xz * 0.19 + ${v2}(-2.3, 3.1));
				${variable} meadowSoil = smoothstep(0.52, 0.86, meadowBroad * 0.72 + meadowFine * 0.28);
				surfaceAlbedo *= mix(${v3}(0.80, 0.93, 0.77), ${v3}(1.11, 1.07, 0.87), meadowBroad);
				surfaceAlbedo = mix(surfaceAlbedo, ${v3}(0.16, 0.13, 0.065), meadowSoil * 0.40);
			`,
		};
	}
}

export function addMeadowSurface(material: PBRMaterial): void {
	new MeadowSurfacePlugin(material);
}
