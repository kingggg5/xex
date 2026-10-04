import { Color3 } from '@babylonjs/core/Maths/math.color';
import { MultiMaterial } from '@babylonjs/core/Materials/multiMaterial';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import type { Material } from '@babylonjs/core/Materials/material';
import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import type { Scene } from '@babylonjs/core/scene';

type LightingFamily = 'window-warm' | 'window-blue' | 'magic' | 'fire';

interface LightingBudget {
	family: LightingFamily;
	dayEmission: number;
	nightEmission: number;
}

// Linear emission multipliers, independent of the source GLB's HDR strength.
// These affect only the named city materials, never world exposure or actors.
const BUDGETS: Readonly<Record<string, LightingBudget>> = Object.freeze({
	glass_window_warm: { family: 'window-warm', dayEmission: 0.015, nightEmission: 0.62 },
	glass_window_blue: { family: 'window-blue', dayEmission: 0.01, nightEmission: 0.46 },
	magic_blue: { family: 'magic', dayEmission: 0.48, nightEmission: 0.64 },
	magic_green: { family: 'magic', dayEmission: 0.40, nightEmission: 0.56 },
	magic_purple: { family: 'magic', dayEmission: 0.46, nightEmission: 0.62 },
	fire_glow: { family: 'fire', dayEmission: 0.48, nightEmission: 0.68 },
});
const SAMPLE_INTERVAL_MS = 160;

interface MaterialBinding {
	material: PBRMaterial;
	budget: LightingBudget;
	emissionHue: Color3;
	dayAlbedo: Color3 | null;
	nightAlbedo: Color3 | null;
	original: {
		albedo: Color3;
		emission: Color3;
		intensity: number;
		roughness: number | null;
		specularIntensity: number;
	};
}

export interface CityMaterialLightingController {
	/** The bounded set captured when the city is imported. */
	readonly materialNames: readonly string[];
	/** Sample the existing weather/sun now, e.g. immediately before warm-up. */
	refresh(): void;
	/** Remove owned observers and restore the source material values. */
	dispose(): void;
}

/**
 * Keep city glass and magic readable under the world's existing day/night sun.
 * Bind once after the static city merge, before material warm-up. The six
 * eligible PBR materials are cached; this never scans the scene each frame,
 * creates lights, changes textures, or establishes a second weather clock.
 */
export function bindCityMaterialLighting(
	scene: Scene,
	mergedCityMesh: Mesh,
	getSunIntensity: () => number,
): CityMaterialLightingController {
	const bindings: MaterialBinding[] = [];
	const seen = new Set<Material>();
	function collect(material: Material | null): void {
		if (!material || seen.has(material)) return;
		seen.add(material);
		if (material instanceof MultiMaterial) {
			for (const child of material.subMaterials) collect(child);
			return;
		}
		if (!(material instanceof PBRMaterial)) return;
		const name = material.name.toLowerCase().replace(/\.\d{3}$/, '');
		const budget = BUDGETS[name];
		if (!budget) return;
		const original = {
			albedo: material.albedoColor.clone(),
			emission: material.emissiveColor.clone(),
			intensity: material.emissiveIntensity,
			roughness: material.roughness,
			specularIntensity: material.specularIntensity,
		};
		const emissionHue = boundedHue(original.emission);
		const window = budget.family === 'window-warm' || budget.family === 'window-blue';
		// Dark panes retain the source warm/cool identity, with a quiet sky tint.
		// Opaque construction and existing mullions stay untouched.
		const dayAlbedo = window ? original.albedo.scale(0.16) : null;
		if (dayAlbedo) dayAlbedo.addInPlaceFromFloats(0.012, 0.022, 0.035);
		const nightAlbedo = window ? original.albedo.scale(0.23) : null;
		if (window) {
			material.roughness = Math.max(0.30, finite(original.roughness, 0.30));
			material.specularIntensity = Math.min(0.65, Math.max(0, finite(original.specularIntensity, 0.65)));
		}
		material.emissiveColor.copyFrom(emissionHue);
		bindings.push({ material, budget, emissionHue, dayAlbedo, nightAlbedo, original });
	}
	collect(mergedCityMesh.material);
	const materialNames = Object.freeze(bindings.map(binding => binding.material.name));
	let lastSample = -Infinity;
	let previousNight = -1;
	let disposed = false;

	function refresh(): void {
		if (disposed || scene.isDisposed) return;
		const sun = Math.max(0, Math.min(4, finite(getSunIntensity(), 1.65)));
		// Existing weather ranges: night 0.18–0.24; overcast noon >=1.18.
		// Finish dimming windows before daylight; rain alone never turns them on.
		const t = Math.max(0, Math.min(1, (sun - 0.30) / 0.65));
		const night = Math.round((1 - t * t * (3 - 2 * t)) * 128) / 128;
		if (night === previousNight) return;
		previousNight = night;
		for (const binding of bindings) {
			const { material, budget, dayAlbedo, nightAlbedo } = binding;
			material.emissiveIntensity = budget.dayEmission + (budget.nightEmission - budget.dayEmission) * night;
			if (dayAlbedo && nightAlbedo) Color3.LerpToRef(dayAlbedo, nightAlbedo, night, material.albedoColor);
		}
	}
	refresh();
	const renderObserver = scene.onBeforeRenderObservable.add(() => {
		const now = performance.now();
		if (now - lastSample < SAMPLE_INTERVAL_MS) return;
		lastSample = now;
		refresh();
	});
	const sceneDisposeObserver = scene.onDisposeObservable.addOnce(dispose);
	function dispose(): void {
		if (disposed) return;
		disposed = true;
		scene.onBeforeRenderObservable.remove(renderObserver);
		scene.onDisposeObservable.remove(sceneDisposeObserver);
		if (scene.isDisposed) return;
		for (const { material, original } of bindings) {
			material.albedoColor.copyFrom(original.albedo);
			material.emissiveColor.copyFrom(original.emission);
			material.emissiveIntensity = original.intensity;
			material.roughness = original.roughness;
			material.specularIntensity = original.specularIntensity;
		}
	}
	return { materialNames, refresh, dispose };
}

function finite(value: number | null, fallback: number): number {
	return value !== null && Number.isFinite(value) ? value : fallback;
}

function boundedHue(source: Color3): Color3 {
	const r = Math.max(0, finite(source.r, 0));
	const g = Math.max(0, finite(source.g, 0));
	const b = Math.max(0, finite(source.b, 0));
	const peak = Math.max(1, r, g, b);
	return new Color3(r / peak, g / peak, b / peak);
}
