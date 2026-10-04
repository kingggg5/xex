import { GlowLayer, type IGlowLayerOptions } from "@babylonjs/core/Layers/glowLayer";
import type { Color3 } from "@babylonjs/core/Maths/math.color";
import type { BaseTexture } from "@babylonjs/core/Materials/Textures/baseTexture";
import type { Material } from "@babylonjs/core/Materials/material";
import { MultiMaterial } from "@babylonjs/core/Materials/multiMaterial";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { InstancedMesh } from "@babylonjs/core/Meshes/instancedMesh";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { Observer } from "@babylonjs/core/Misc/observable";
import type { Scene } from "@babylonjs/core/scene";

/** A glow colour below 1/255 on every channel is invisible after the blur, so it counts as black. */
const GLOW_EPSILON = 1 / 255;
/** Emissive colours are mutated in place (day/night, weather, flashes); re-check every mesh this often. */
const RESCAN_FRAMES = 20;

/** The fields ThinGlowLayer._setEmissiveTextureAndColor reads, plus the flag that switches its draw path. */
interface GlowReadableMaterial {
	emissiveColor?: Color3;
	emissiveTexture?: BaseTexture | null;
	emissiveIntensity?: number;
	/** NodeMaterial: true when a FragmentOutput block has `additionalColor` connected (rendered with its own shader). */
	_supportGlowLayer?: boolean;
}

/**
 * True when the glow layer would write a visible colour for this material. Mirrors what
 * ThinGlowLayer draws: `emissiveColor × emissiveIntensity × emissiveTexture.level`, so an emissive
 * texture with a black emissive colour (the sky dome) writes black and is not an emitter.
 * Emissive used as a fill (`linkEmissiveWithDiffuse`, the leaf cards) still counts: the old layer
 * bloomed it and the art pass was tuned with that bloom (about +20 levels on canopies by day).
 * Opt such a mesh out with `metadata.glow = false`.
 */
export function materialEmitsGlow(material: Material | null | undefined): boolean {
	if (!material) return false;
	if (material instanceof MultiMaterial) return material.subMaterials.some((sub) => materialEmitsGlow(sub));
	const source = material as Material & GlowReadableMaterial;
	if (source._supportGlowLayer) return true;
	const color = source.emissiveColor;
	if (!color) return false;
	const level = (source.emissiveTexture?.level ?? 1) * (source.emissiveIntensity ?? 1);
	return Math.max(color.r, color.g, color.b) * level > GLOW_EPSILON;
}

const renderingMesh = (mesh: AbstractMesh): AbstractMesh => mesh.isAnInstance ? (mesh as InstancedMesh).sourceMesh : mesh;

/**
 * The world glow layer, opt-in: only emitters are drawn into its target, instead of every active mesh
 * (community practice §3.11). Without an include list GlowLayer redraws the whole visible scene.
 *
 * A mesh is an emitter when, in priority order:
 * 1. it is excluded (`addExcludedMesh`, or `mesh.metadata.glow === false`): never drawn;
 * 2. it is opted in (`mesh.metadata.glow === true`, `addIncludedOnlyMesh`, `referenceMeshToUseItsOwnMaterial`): drawn;
 * 3. otherwise its material writes a visible glow colour ({@link materialEmitsGlow}).
 *
 * Instances render through their source mesh, so tags and API calls apply to the source mesh.
 * New meshes, material swaps and removals are tracked through scene and mesh observables; emissive
 * colours changed in place are picked up by a cheap rescan every {@link RESCAN_FRAMES} frames.
 * Particles never enter a glow target (`renderParticles = false`), before or after this change.
 *
 * Trade-off: meshes that are not drawn into the glow target do not occlude it, so an emitter behind
 * an opaque non-emitter can bleed its halo through. Tag such an occluder with `metadata.glow = true`
 * and a black emissive colour if a locked view shows it.
 */
export class EmitterGlowLayer extends GlowLayer {
	private readonly included = new Set<AbstractMesh>();
	private readonly forcedOn = new WeakSet<AbstractMesh>();
	private readonly forcedOff = new WeakSet<AbstractMesh>();
	private readonly pending = new Set<AbstractMesh>();
	private readonly visible: AbstractMesh[] = [];
	private visibleFrame = -1;
	private framesUntilRescan = RESCAN_FRAMES;
	private readonly queueChanged = (mesh: AbstractMesh) => { this.pending.add(mesh); };
	private readonly addedObserver: Observer<AbstractMesh> | null;
	private readonly removedObserver: Observer<AbstractMesh> | null;
	private readonly frameObserver: Observer<Scene> | null;

	constructor(name: string, scene: Scene, options: Partial<IGlowLayerOptions> = {}) {
		// excludeByDefault: an empty include list skips the layer (no target, blur or merge) instead of drawing everything.
		super(name, scene, { ...options, excludeByDefault: true });
		for (const mesh of scene.meshes) this.track(mesh);
		this.addedObserver = scene.onNewMeshAddedObservable.add((mesh) => this.track(mesh));
		this.removedObserver = scene.onMeshRemovedObservable.add((mesh) => this.forget(mesh));
		this.frameObserver = scene.onBeforeRenderObservable.add(() => this.flush());
		// Only the emitters among this frame's active meshes reach the glow target's render queue. Set on the
		// shared ObjectRenderer, which survives the main texture being recreated when the canvas resizes.
		this._thinEffectLayer.objectRenderer.getCustomRenderList = () => this.visibleEmitters();
		// Start compiling the blur and merge effects during loading: with an opt-in list the first
		// compose can come long after load, when the first emitter enters the view.
		this.isLayerReady();
	}

	/** Emitter counts for diagnostics: registered meshes, and those drawn into the target last frame. */
	emitterStats(): { included: number; visible: number } {
		return { included: this.included.size, visible: this.visibleFrame === this._scene.getFrameId() ? this.visible.length : 0 };
	}

	/** Skips the target, its four blur passes and the merge when no emitter is in view (§3.11). */
	override shouldRender(): boolean {
		return super.shouldRender() && this.visibleEmitters().length > 0;
	}

	override addIncludedOnlyMesh(mesh: Mesh): void {
		this.forcedOn.add(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override removeIncludedOnlyMesh(mesh: Mesh): void {
		this.forcedOn.delete(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override addExcludedMesh(mesh: Mesh): void {
		super.addExcludedMesh(mesh);
		this.forcedOff.add(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override removeExcludedMesh(mesh: Mesh): void {
		super.removeExcludedMesh(mesh);
		this.forcedOff.delete(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override referenceMeshToUseItsOwnMaterial(mesh: AbstractMesh): void {
		super.referenceMeshToUseItsOwnMaterial(mesh);
		this.forcedOn.add(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override unReferenceMeshFromUsingItsOwnMaterial(mesh: AbstractMesh): void {
		super.unReferenceMeshFromUsingItsOwnMaterial(mesh);
		this.forcedOn.delete(renderingMesh(mesh));
		this.evaluate(mesh);
	}

	override dispose(): void {
		this._scene.onNewMeshAddedObservable.remove(this.addedObserver);
		this._scene.onMeshRemovedObservable.remove(this.removedObserver);
		this._scene.onBeforeRenderObservable.remove(this.frameObserver);
		for (const mesh of this._scene.meshes) mesh.onMaterialChangedObservable.removeCallback(this.queueChanged);
		this._thinEffectLayer.objectRenderer.getCustomRenderList = null;
		this.included.clear();
		this.pending.clear();
		this.visible.length = 0;
		super.dispose();
	}

	private track(mesh: AbstractMesh): void {
		// Material assignment usually follows creation; evaluate on the next frame.
		this.pending.add(mesh);
		if (!mesh.isAnInstance) mesh.onMaterialChangedObservable.add(this.queueChanged);
	}

	private forget(mesh: AbstractMesh): void {
		this.pending.delete(mesh);
		mesh.onMaterialChangedObservable.removeCallback(this.queueChanged);
		if (mesh instanceof Mesh) this.setIncluded(mesh, false);
	}

	private flush(): void {
		if (--this.framesUntilRescan <= 0) {
			this.framesUntilRescan = RESCAN_FRAMES;
			for (const mesh of this._scene.meshes) if (!mesh.isAnInstance) this.evaluate(mesh);
		}
		if (this.pending.size === 0) return;
		for (const mesh of this.pending) this.evaluate(mesh);
		this.pending.clear();
	}

	private evaluate(candidate: AbstractMesh): void {
		const mesh = renderingMesh(candidate);
		if (!(mesh instanceof Mesh) || mesh.isDisposed()) return;
		const tag = (mesh.metadata as { glow?: unknown } | null | undefined)?.glow;
		const glows = tag !== false && !this.forcedOff.has(mesh)
			&& (tag === true || this.forcedOn.has(mesh) || materialEmitsGlow(mesh.material));
		this.setIncluded(mesh, glows);
	}

	private setIncluded(mesh: Mesh, on: boolean): void {
		if (on === this.included.has(mesh)) return;
		if (on) {
			this.included.add(mesh);
			super.addIncludedOnlyMesh(mesh);
		} else {
			this.included.delete(mesh);
			super.removeIncludedOnlyMesh(mesh);
		}
	}

	/** This frame's active meshes (already frustum and layer culled) whose rendering mesh is an emitter. */
	private visibleEmitters(): AbstractMesh[] {
		const frame = this._scene.getFrameId();
		if (frame === this.visibleFrame) return this.visible;
		this.visibleFrame = frame;
		this.visible.length = 0;
		if (this.included.size === 0) return this.visible;
		const active = this._scene.getActiveMeshes();
		for (let index = 0; index < active.length; index++) {
			const mesh = active.data[index];
			if (this.included.has(renderingMesh(mesh))) this.visible.push(mesh);
		}
		return this.visible;
	}
}
