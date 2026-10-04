import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { ShadowDepthWrapper } from "@babylonjs/core/Materials/shadowDepthWrapper";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { Material } from "@babylonjs/core/Materials/material";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import type { Scene } from "@babylonjs/core/scene";

export interface NatureClock { phase: number; strength?: number; waterStrength?: number }

/**
 * Where the sway weight comes from.
 * - "height" (default, every legacy kit): world height above `rootHeight`, ramped over `heightRange`.
 * - "uv2" (sunmeadow-trees-v4 kit, C-P1-TREE): TEXCOORD_1 authored in Blender (x = sway weight, 0 at the ground ->
 *   1 at the tips; y = per-clump phase 0..1), multiplied by a ramp on the height above the instance origin, so a tree
 *   on raised ground bends like one at y = 0 and nothing sways below `rigidBelow` (no trunk-base bending).
 */
export interface WindOptions {
	weights?: "height" | "uv2";
	/** uv2 mode: metres above the instance origin with no sway at all. Default 1 (trees); bushes use ~0.1. */
	rigidBelow?: number;
	/** uv2 mode: metres over which the sway fades in above `rigidBelow`. Default 1. */
	fadeIn?: number;
}

/** World-space gusts deform geometry; roots remain fixed. No per-frame vertex uploads. */
class NatureMotionPlugin extends MaterialPluginBase {
	/** uniform natureMotion = (clock phase, amplitude x strength, rootHeight | rigidBelow, heightRange | fadeIn). */
	constructor(material: Material, private readonly clock: NatureClock,
		private readonly amplitude: number, private readonly rootHeight: number,
		private readonly heightRange: number, private readonly water: boolean,
		private readonly uv2Weights = false) {
		super(material, "NatureMotion", 180, { NATUREWIND_UV2: false }, true, false);
		this.registerForExtraEvents = true;
		this._enable(true);
	}

	isCompatible(language: ShaderLanguage): boolean {
		return language === ShaderLanguage.GLSL || language === ShaderLanguage.WGSL;
	}

	prepareDefines(defines: MaterialDefines): void {
		defines.NATUREWIND_UV2 = this.uv2Weights && !this.water;
	}

	getUniforms(language = ShaderLanguage.GLSL) {
		const declaration = language === ShaderLanguage.GLSL ? "uniform vec4 natureMotion;" : "";
		return { ubo: [{ name: "natureMotion", size: 4, type: "vec4" }], vertex: declaration, fragment: declaration };
	}

	hardBindForSubMesh(buffer: UniformBuffer): void {
		const strength = this.water ? this.clock.waterStrength ?? 1 : this.clock.strength ?? 1;
		buffer.updateFloat4("natureMotion", this.clock.phase, this.amplitude * strength, this.rootHeight, this.heightRange);
	}

	getCustomCode(stage: string, language = ShaderLanguage.GLSL): Record<string, string> | null {
		const wgsl = language === ShaderLanguage.WGSL;
		const u = wgsl ? "uniforms.natureMotion" : "natureMotion";
		const f = wgsl ? "var" : "float";
		if (stage === "vertex") {
			// uv2 mode (UV2 is defined whenever a textured material draws a mesh with TEXCOORD_1): the weight and the
			// clump phase are authored per vertex, the gust and the main phase are per instance (finalWorld[3] is the
			// thin-instance origin), so a clump and the limb under it move as one piece. finalWorld[3].y is the
			// instance's ground height; uv2Updated is declared by the stock shaders before this injection point.
			const weights = `
#if defined(NATUREWIND_UV2) && defined(UV2)
				${f} natureLocalY = worldPos.y - finalWorld[3].y;
				${f} natureWeight = uv2Updated.x * clamp((natureLocalY - ${u}.z) / max(${u}.w, 0.001), 0.0, 1.0);
				${f} natureClump = uv2Updated.y * 6.2831853;
				${f} natureSpatial = finalWorld[3].x * 0.11 + finalWorld[3].z * 0.075;
#else
				${f} natureWeight = clamp((worldPos.y - ${u}.z) / ${u}.w, 0.0, 1.0);
				${f} natureClump = 0.0;
				${f} natureSpatial = worldPos.x * 0.11 + worldPos.z * 0.075;
#endif
			`;
			const wind = `${weights}
				${f} natureGust = 0.65 + 0.35 * sin(${u}.x + natureSpatial * 0.4);
				${f} natureSway = sin(${u}.x * 2.0 + natureSpatial + natureClump * 0.35) * 0.65
					+ sin(${u}.x * 3.0 + worldPos.z * 0.21 + natureClump * 0.6) * 0.25
					+ sin(${u}.x * 11.0 + worldPos.x * 2.3 + worldPos.z * 1.7 + natureClump) * 0.10;
				worldPos.x += natureSway * natureGust * natureWeight * ${u}.y;
				worldPos.z += natureSway * natureGust * natureWeight * ${u}.y * 0.37;
			`;
			const waves = `
				worldPos.y += (sin(worldPos.x * 1.4 + worldPos.z * 2.1 - ${u}.x * 3.0)
					+ 0.45 * sin(worldPos.x * 3.2 - worldPos.z * 2.6 + ${u}.x * 5.0)) * ${u}.y;
			`;
			return { CUSTOM_VERTEX_UPDATE_WORLDPOS: this.water ? waves : wind };
		}
		if (stage !== "fragment" || !this.water) return null;
		const pos = wgsl ? "fragmentInputs.vPositionW" : "vPositionW";
		const vec3 = wgsl ? "vec3f" : "vec3";
		return { CUSTOM_FRAGMENT_BEFORE_LIGHTS: `
			${f} natureRippleA = cos(${pos}.x * 1.4 + ${pos}.z * 2.1 - ${u}.x * 3.0);
			${f} natureRippleB = cos(${pos}.x * 3.2 - ${pos}.z * 2.6 + ${u}.x * 5.0);
			normalW = normalize(${vec3}(-0.13 * natureRippleA - 0.08 * natureRippleB,
				1.0, -0.16 * natureRippleA + 0.07 * natureRippleB));
			${f} natureFresnel = pow(1.0 - max(0.0, dot(normalW, viewDirectionW)), 3.0);
			diffuseColor = mix(${vec3}(0.07, 0.30, 0.33), ${vec3}(0.30, 0.58, 0.63), natureFresnel);
		` };
	}

	getClassName(): string { return "NatureMotionPlugin"; }
}

/**
 * Vertex wind for a material, in the colour pass and (through ShadowDepthWrapper) in the shadow-map pass, so cast
 * shadows sway with the leaves. `rootHeight`/`heightRange` drive the legacy world-height weights; with
 * `options.weights = "uv2"` the two values are replaced by `rigidBelow`/`fadeIn` (see WindOptions).
 */
export function addWind(material: Material, scene: Scene, clock: NatureClock,
	amplitude: number, rootHeight = 0, heightRange = 6, options: WindOptions = {}): void {
	const uv2 = options.weights === "uv2";
	new NatureMotionPlugin(material, clock, amplitude,
		uv2 ? options.rigidBelow ?? 1 : rootHeight, uv2 ? options.fadeIn ?? 1 : heightRange, false, uv2);
	// Stock WGSL shaders expose the varying through their output structure.
	const depth = new ShadowDepthWrapper(material, scene, {
		remappedVariables: ["vNormalW", scene.getEngine().isWebGPU ? "vertexOutputs.vNormalW" : "vNormalW"],
	});
	material.shadowDepthWrapper = depth;
	material.onDisposeObservable.addOnce(() => depth.dispose());
}

export function addWaterWaves(material: Material, clock: NatureClock): void {
	new NatureMotionPlugin(material, clock, 0.018, 0, 1, true);
}

export function advanceNatureClock(clock: NatureClock, deltaSeconds: number): void {
	// Integer shader frequencies preserve continuity across this bounded phase wrap.
	if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0) return;
	clock.phase = (clock.phase + Math.min(0.08, deltaSeconds) * 0.45) % (Math.PI * 2);
}
