import { subscribeLookV2PoolEvents } from './look-v2-pool-events.mjs';

export const MAX_LOOK_V2_POOLS = 64;
export const LOOK_V2_POOL_RADII = Object.freeze({ lamp: 4.5, brazier: 6, fire: 7 });
export const LOOK_V2_POOL_DIAMETERS = Object.freeze({ lamp: 9, brazier: 12, fire: 14 });
const emitterPattern = /lantern|lamp|brazier|campfire|torch|fire_glow|fire core|watch-?fire/i;
const maxDeferredAttempts = 4;
const kindFrom = value => /brazier/i.test(value) ? 'brazier' : /campfire|watch-?fire|fire_glow|fire core/i.test(value) ? 'fire' : 'lamp';
const validKind = value => Object.hasOwn(LOOK_V2_POOL_DIAMETERS, value);

/** Circular alpha with a smooth shoulder and zero alpha/derivative at the rim. */
export function lookV2PoolAlpha(u, v) {
	const radiusSquared = ((u - .5) * 2) ** 2 + ((v - .5) * 2) ** 2;
	return radiusSquared >= 1 ? 0 : (1 - radiusSquared) ** 3;
}
export function createLookV2PoolPixels(size = 64) {
	const pixels = new Uint8ClampedArray(size * size * 4);
	for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
		const offset = (y * size + x) * 4;
		pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = 255;
		pixels[offset + 3] = Math.round(lookV2PoolAlpha(x / (size - 1), y / (size - 1)) * 255);
	}
	return pixels;
}
/** The source ground is 1 m wide: the matrix scale is the requested DIAMETER. */
export function writeLookV2PoolMatrices(anchors, target) {
	target.fill(0);
	const count = Math.min(anchors.length, MAX_LOOK_V2_POOLS, Math.floor(target.length / 16));
	for (let i = 0; i < count; i++) {
		const anchor = anchors[i], offset = i * 16, diameter = LOOK_V2_POOL_DIAMETERS[anchor.type];
		target[offset] = target[offset + 10] = diameter;
		target[offset + 5] = target[offset + 15] = 1;
		target[offset + 12] = anchor.x; target[offset + 13] = anchor.y + .04; target[offset + 14] = anchor.z;
	}
	return count;
}
function namesFor(mesh) {
	let names = `${mesh.name} ${mesh.material?.name ?? ''}`;
	for (let node = mesh.parent, depth = 0; node && depth < 4; node = node.parent, depth++) names += ` ${node.name}`;
	return names;
}
function parseAnchor(value, type) {
	const [x, y, z] = Array.isArray(value) ? value : [value?.x, value?.y, value?.z];
	if (![x, y, z].every(Number.isFinite)) return null;
	const declaredType = Array.isArray(value) ? value[3] : value?.type;
	return { x, y, z, type: validKind(declaredType) ? declaredType : type };
}

/** One scene scan after dressing readiness; all later work is bounded to added/changed emitters.
 * Mesh constructors do not guarantee geometry, material or user metadata are ready at notification.
 * One microtask recheck handles synchronous builders; named late builders get four frame retries.
 * Streamed dressing metadata has an explicit notification, so it needs no scene/vertex polling. */
export function createLookV2PoolRegistry(scene, excludedMesh = null) {
	const records = new Map(), pending = new Map();
	let disposed = false, scanned = false;
	const diagnostics = { fullScans: 0, evaluations: 0, boundsReads: 0 };
	const forget = mesh => {
		pending.delete(mesh);
		const record = records.get(mesh);
		if (record) mesh.onDisposeObservable.remove(record.disposeObserver);
		records.delete(mesh);
	};
	const evaluate = mesh => {
		if (disposed || mesh === excludedMesh || mesh.isDisposed()) { forget(mesh); return false; }
		diagnostics.evaluations++;
		const metadata = mesh.metadata ?? {}, names = namesFor(mesh);
		if (metadata.lookV2Pool === false || mesh.name.startsWith('v3-template-')) { forget(mesh); return false; }
		const declared = metadata.lookV2PoolAnchors;
		const single = metadata.lookV2PoolAnchor;
		const explicit = Array.isArray(declared) || single != null;
		if (!explicit && (!emitterPattern.test(names) || metadata.dressingV3)) { forget(mesh); return false; }
		const type = validKind(metadata.lookV2PoolType) ? metadata.lookV2PoolType : kindFrom(names);
		let anchors;
		if (explicit) anchors = (Array.isArray(declared) ? declared : [single]).map(value => parseAnchor(value, type)).filter(Boolean);
		else {
			// Never sample non-emitter vertices, or mistake a thin-instance source box for all its feet.
			if (mesh.hasThinInstances) { forget(mesh); return false; }
			if (!mesh.getTotalVertices()) return true;
			mesh.computeWorldMatrix(true);
			const box = mesh.getBoundingInfo().boundingBox;
			diagnostics.boundsReads++;
			anchors = [{ x: box.centerWorld.x, y: box.minimumWorld.y, z: box.centerWorld.z, type }];
		}
		const previous = records.get(mesh);
		if (previous) previous.anchors = anchors;
		else records.set(mesh, { anchors, disposeObserver: mesh.onDisposeObservable.add(() => forget(mesh)) });
		return false;
	};
	const queue = mesh => {
		if (disposed || mesh === excludedMesh || mesh.isDisposed() || pending.has(mesh)) return;
		pending.set(mesh, 0);
		queueMicrotask(() => {
			if (!pending.has(mesh) || disposed) return;
			pending.delete(mesh);
			if (evaluate(mesh)) pending.set(mesh, 1);
		});
	};
	const addedObserver = scene.onNewMeshAddedObservable.add(queue);
	const removedObserver = scene.onMeshRemovedObservable.add(forget);
	const frameObserver = scene.onBeforeRenderObservable.add(() => {
		// Snapshot the queue: deleting/reinserting during Map iteration would consume all retries this frame.
		for (const [mesh, attempt] of [...pending]) {
			if (!attempt) continue; // let the builder's current stack finish first
			pending.delete(mesh);
			if (evaluate(mesh) && attempt < maxDeferredAttempts) pending.set(mesh, attempt + 1);
		}
	});
	const unsubscribe = subscribeLookV2PoolEvents(scene, mesh => {
		if (mesh) { pending.delete(mesh); if (evaluate(mesh)) pending.set(mesh, 1); }
		else if (!scanned && !disposed) {
			scanned = true; diagnostics.fullScans++;
			for (const candidate of scene.meshes) if (evaluate(candidate)) pending.set(candidate, 1);
		}
	});
	const snapshot = () => {
		const unique = new Map();
		for (const [mesh, record] of records) {
			if (mesh.isDisposed() || !mesh.isEnabled() || !mesh.isVisible || mesh.visibility <= 0 || mesh.metadata?.lookV2Pool === false) continue;
			for (const anchor of record.anchors) {
				const key = `${anchor.x.toFixed(2)}:${anchor.y.toFixed(2)}:${anchor.z.toFixed(2)}`;
				const previous = unique.get(key);
				if (!previous || LOOK_V2_POOL_DIAMETERS[anchor.type] > LOOK_V2_POOL_DIAMETERS[previous.type]) unique.set(key, anchor);
			}
		}
		return [...unique.values()].slice(0, MAX_LOOK_V2_POOLS);
	};
	const dispose = () => {
		if (disposed) return; disposed = true;
		unsubscribe();
		scene.onNewMeshAddedObservable.remove(addedObserver);
		scene.onMeshRemovedObservable.remove(removedObserver);
		scene.onBeforeRenderObservable.remove(frameObserver);
		scene.onDisposeObservable.remove(disposeObserver);
		for (const mesh of records.keys()) forget(mesh);
		pending.clear();
	};
	const disposeObserver = scene.onDisposeObservable.addOnce(dispose);
	return { snapshot, dispose, stats: () => ({ ...diagnostics, emitters: records.size, pending: pending.size, anchors: snapshot().length }) };
}
