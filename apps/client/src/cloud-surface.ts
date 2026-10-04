import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";

/** Softens the real puff meshes; this is a surface approximation, not ray marching. */
class CloudSurfacePlugin extends MaterialPluginBase {
	constructor(material: StandardMaterial) {
		super(material, "CloudSurface", 190, {}, true, false);
		this._enable(true);
	}
	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}
	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		if (stage !== "fragment") return null;
		const wgsl = language === ShaderLanguage.WGSL;
		const pos = wgsl ? "fragmentInputs.vPositionW" : "vPositionW";
		const variable = wgsl ? "var" : "float";
		return { CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
			${variable} cloudFacing = abs(dot(normalW, viewDirectionW));
			${variable} cloudDensity = 0.79 + 0.21 * sin(${pos}.x * 0.31 + ${pos}.y * 0.22)
				* sin(${pos}.z * 0.29 - ${pos}.y * 0.35);
			alpha *= smoothstep(0.0, 0.34, cloudFacing) * cloudDensity;
		` };
	}
}

export function addCloudSurface(material: StandardMaterial): void {
	new CloudSurfacePlugin(material);
}
