import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";

/** World-height weathering supplements the authored slope tints and file albedo. */
class MountainSurfacePlugin extends MaterialPluginBase {
	constructor(material: PBRMaterial) {
		super(material, "MountainSurface", 190, {}, true, false);
		this._enable(true);
	}
	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}
	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		if (stage !== "fragment") return null;
		const wgsl = language === ShaderLanguage.WGSL;
		const variable = wgsl ? "var" : "float";
		const vector = wgsl ? "vec3f" : "vec3";
		const pos = wgsl ? "fragmentInputs.vPositionW" : "vPositionW";
		return { CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
			${variable} mountainHeight = smoothstep(8.0, 90.0, ${pos}.y);
			${variable} mountainStrata = 0.5 + 0.5 * sin(${pos}.y * 0.39
				+ sin(${pos}.x * 0.045 + ${pos}.z * 0.038) * 2.0);
			surfaceAlbedo *= mix(${vector}(0.85, 0.92, 0.82), ${vector}(1.03, 1.03, 1.04), mountainHeight);
			surfaceAlbedo *= 0.94 + 0.10 * mountainStrata;
		` };
	}
}

export function addMountainSurface(material: PBRMaterial): void {
	new MountainSurfacePlugin(material);
}
