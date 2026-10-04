import { HDRCubeTexture } from '@babylonjs/core/Materials/Textures/hdrCubeTexture';
import type { Scene } from '@babylonjs/core/scene';
import type { ResolvedGraphicsPreset } from './graphics-quality.mjs';
import skyEnvironmentUrl from '../../../assets/textures/environment-cc0/kloofendal_48d_partly_cloudy_puresky_1k.hdr?url';

type EnvironmentQuality = Pick<ResolvedGraphicsPreset, 'formFactor' | 'preset'>;

export interface LevelEnvironmentLighting {
	readonly texture: HDRCubeTexture;
	readonly cubeFaceSize: 64 | 128;
	/** Call from the existing weather/day-night update; this owns no clock. */
	setIntensity(value: number): void;
	/** Releases this environment, preserving any previous scene-owned texture. */
	dispose(): void;
}

const pendingByScene = new WeakMap<Scene, Promise<LevelEnvironmentLighting>>();
// Soft sky fill; the sun is the key light (art pass v1, 2026-10-02). environment.ts drives it by time of day.
const DEFAULT_INTENSITY = .25;
const LOAD_TIMEOUT_MS = 30_000;

/**
 * One native PBR IBL texture per scene, prepared during loading before city
 * shader warm-up. The CC0 panorama remains a separate, content-hashed asset.
 * Does not add a skybox, sun, exposure override, reflection probe or render loop.
 * Desktop is capped at 128px per cube face; mobile and Low use 64px.
 * Quality changes do not repeatedly decode/rebuild this startup texture.
 */
export function configureLevelEnvironment(
	scene: Scene,
	quality: EnvironmentQuality = { formFactor: 'desktop', preset: 'medium' },
): Promise<LevelEnvironmentLighting> {
	if (scene.isDisposed) return Promise.reject(new Error('Cannot prepare IBL for a disposed scene.'));
	const existing = pendingByScene.get(scene);
	if (existing) return existing;

	const cubeFaceSize = quality.formFactor === 'mobile' || quality.preset === 'low' ? 64 : 128;
	const previousTexture = scene.environmentTexture;
	const previousIntensity = scene.environmentIntensity;
	let texture: HDRCubeTexture | null = null;
	let settled = false;
	let disposed = false;
	let disposingScene = false;
	let timeout: ReturnType<typeof setTimeout> | undefined;
	let rejectPending: (reason: Error) => void = () => {};

	const restorePrevious = () => {
		if (scene.environmentTexture !== texture) return;
		scene.environmentTexture = disposingScene ? null : previousTexture;
		if (!disposingScene) scene.environmentIntensity = previousIntensity;
	};
	const disposeTexture = () => {
		if (disposed) return;
		disposed = true;
		clearTimeout(timeout);
		restorePrevious();
		texture?.dispose();
		pendingByScene.delete(scene);
	};
	const sceneDisposal = scene.onDisposeObservable.addOnce(() => {
		disposingScene = true;
		disposeTexture();
		if (!settled) {
			settled = true;
			rejectPending(new Error('Scene disposed while preparing environment lighting.'));
		}
	});

	const pending = new Promise<LevelEnvironmentLighting>((resolve, reject) => {
		rejectPending = reject;
		const fail = (reason: Error) => {
			if (settled) return;
			settled = true;
			scene.onDisposeObservable.remove(sceneDisposal);
			disposeTexture();
			reject(reason);
		};
		timeout = setTimeout(() => fail(new Error('Environment lighting did not become ready within 30 seconds.')), LOAD_TIMEOUT_MS);
		try {
			texture = new HDRCubeTexture(
				skyEnvironmentUrl, scene, cubeFaceSize,
				false, // Full mip chain for roughness-dependent reflections.
				true, // Native diffuse spherical harmonics from the sky panorama.
				false, // PBR expects linear-space environment radiance.
				true, // Native radiance prefilter once, during loading.
				() => queueMicrotask(() => {
					if (settled || disposed) return;
					const readyTexture = texture;
					if (!readyTexture?.isReady() || scene.isDisposed) {
						fail(new Error('Environment texture loaded without a usable scene/texture.'));
						return;
					}
					settled = true;
					clearTimeout(timeout);
					scene.environmentTexture = readyTexture;
					scene.environmentIntensity = DEFAULT_INTENSITY;
					resolve({
						texture: readyTexture,
						cubeFaceSize,
						setIntensity(value: number) {
							if (!Number.isFinite(value)) throw new RangeError('Environment intensity must be finite.');
							if (!disposed && scene.environmentTexture === readyTexture) {
								scene.environmentIntensity = Math.max(0, Math.min(1, value));
							}
						},
						dispose() {
							scene.onDisposeObservable.remove(sceneDisposal);
							disposeTexture();
							},
					});
				}),
				(message) => queueMicrotask(() => fail(new Error(message || 'Could not load the CC0 environment texture.'))),
				false, // No supersampling allocation.
				false, // SH is enough for diffuse; avoid a second irradiance texture.
				false, // Default native prefilter; no extra CDF maps.
				32, // Bound SH evaluation independently of cube resolution.
			);
			texture.name = 'env-cc0-kloofendal-sky-ibl';
			texture.rotationY = 0;
			texture.metadata = {
				assetId: 'kloofendal_48d_partly_cloudy_puresky',
				license: 'CC0-1.0',
				cubeFaceSize,
			};
		} catch (error) {
			// Queue so the WeakMap write below cannot retain a synchronously failed load.
			queueMicrotask(() => fail(error instanceof Error ? error : new Error(String(error))));
		}
	});
	pendingByScene.set(scene, pending);
	return pending;
}
