import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
import type { Geometry } from '@babylonjs/core/Meshes/geometry';
import type { Material } from '@babylonjs/core/Materials/material';
import type { Node } from '@babylonjs/core/node';
import type { Scene } from '@babylonjs/core/scene';

export type CityRepresentationFamily = 'hlod' | 'detail' | 'procedural-keep';

export interface CityRepresentationMeshReview {
	uniqueId: number;
	name: string;
	nodeClass: string;
	parentUniqueId: number | null;
	rootUniqueIds: number[];
	localEnabled: boolean;
	effectiveEnabled: boolean;
	isVisible: boolean;
	visibility: number;
	/** Enabled/visible geometry only; not a frustum, occlusion or draw proof. */
	renderEligible: boolean;
	cameraLayerCompatible: boolean | null;
	worldMatrix: Array<number | null>;
	worldMatrixFinite: boolean;
	geometry: { id: string | null; uniqueId: number | null; vertices: number; indices: number; indexedTriangles: number; vertexKinds: string[] };
	material: { uniqueId: number | null; name: string | null; slots: Array<{ uniqueId: number | null; name: string | null }> };
	subMeshes: Array<{ materialIndex: number; verticesStart: number; verticesCount: number; indexStart: number; indexCount: number }>;
	shadow: { receives: boolean; registeredMaps: string[]; sourceRegisteredMaps: string[] };
	thinInstances: number;
	animatedGeometry: boolean;
}

export interface CityRepresentationReviewSnapshot {
	schemaVersion: 1;
	phase: string;
	frameId: number;
	rootFamilies: Array<{
		family: CityRepresentationFamily;
		expectedRootName: string;
		roots: Array<{ uniqueId: number; parentUniqueId: number | null; enabled: boolean; worldMatrix: Array<number | null>; meshUniqueIds: number[] }>;
		attachedMeshCount: number;
		renderEligibleMeshCount: number;
		indexedTriangles: number;
		renderEligibleIndexedTriangles: number;
	}>;
	meshes: CityRepresentationMeshReview[];
	orphanCityMeshUniqueIds: number[];
	shadowMaps: Array<{ key: string; lightName: string; lightEnabled: boolean; generatorId: string; cameraUniqueId: number | null; explicitCasterUniqueIds: number[]; hasPredicate: boolean; hasCustomRenderList: boolean; renderListIsNull: boolean }>;
	exactDuplicateCandidates: Array<{ meshUniqueIds: number[]; meshNames: string[]; renderEligibleMeshUniqueIds: number[]; simultaneousVisibleCandidate: boolean; comparison: 'shared-geometry-object' | 'all-vertex-attributes-and-indices' }>;
	summary: { presentRootFamilies: CityRepresentationFamily[]; renderEligibleRootFamilies: CityRepresentationFamily[]; overlappingVisibleRepresentations: boolean; duplicateCandidateGroups: number; simultaneousVisibleDuplicateGroups: number };
	limitations: string[];
}

const ROOT_FAMILIES: ReadonlyArray<{ family: CityRepresentationFamily; name: string }> = [
	{ family: 'hlod', name: 'reference-city-hlod' },
	{ family: 'detail', name: 'reference-city-detail' },
	{ family: 'procedural-keep', name: 'procedural-keep' },
];

/**
 * Explicit DEV snapshot only. It never changes visibility, transforms,
 * materials, shadow registration or scene observers, and does not render.
 * Parent-owned capture labels describe cold/approach/prepared/reveal/re-entry.
 * Native getWorldMatrix() may refresh Babylon's own cached matrix normally.
 */
export function snapshotCityRepresentations(scene: Scene, options: { phase?: string } = {}): CityRepresentationReviewSnapshot {
	if (!import.meta.env.DEV) throw new Error('City representation review is development-only.');
	const sceneMeshes = scene.meshes.filter(mesh => !mesh.isDisposed());
	const allNodes: Node[] = [...scene.transformNodes, ...sceneMeshes];
	const rootNodes = ROOT_FAMILIES.flatMap(family => allNodes.filter(node => node.name === family.name && !node.isDisposed()));
	const rootIds = new Set(rootNodes.map(root => root.uniqueId));
	const registeredByMesh = new Map<number, string[]>();
	const shadowMaps: CityRepresentationReviewSnapshot['shadowMaps'] = [];
	for (const light of scene.lights) {
		const generators = light.getShadowGenerators();
		if (!generators) continue;
		for (const [camera, generator] of generators) {
			const map = generator.getShadowMap();
			if (!map) continue;
			const key = `${light.uniqueId}:${generator.id}:${camera?.uniqueId ?? 'shared'}`;
			const casterIds = [...new Set((map.renderList ?? []).filter(Boolean).map(mesh => mesh.uniqueId))].sort((a, b) => a - b);
			for (const id of casterIds) registeredByMesh.set(id, [...(registeredByMesh.get(id) ?? []), key]);
			shadowMaps.push({ key, lightName: light.name, lightEnabled: light.isEnabled(), generatorId: generator.id, cameraUniqueId: camera?.uniqueId ?? null, explicitCasterUniqueIds: casterIds, hasPredicate: typeof map.renderListPredicate === 'function', hasCustomRenderList: typeof map.getCustomRenderList === 'function', renderListIsNull: map.renderList === null });
		}
	}
	const meshes = sceneMeshes.flatMap(mesh => {
		const memberships: number[] = [];
		let parent: Node | null = mesh;
		while (parent) {
			if (rootIds.has(parent.uniqueId)) memberships.push(parent.uniqueId);
			parent = parent.parent;
		}
		const orphanCandidate = /^(reference-city-(?:hlod-)?merged|env-castle-)/.test(mesh.name);
		return memberships.length || orphanCandidate ? [reviewMesh(mesh, memberships, registeredByMesh, scene)] : [];
	});
	const rootFamilies = ROOT_FAMILIES.map(({ family, name }) => {
		const nodes = rootNodes.filter(node => node.name === name);
		const ids = new Set(nodes.map(node => node.uniqueId));
		const members = meshes.filter(mesh => mesh.rootUniqueIds.some(id => ids.has(id)));
		const eligible = members.filter(mesh => mesh.renderEligible);
		return {
			family, expectedRootName: name,
			roots: nodes.map(node => ({ uniqueId: node.uniqueId, parentUniqueId: node.parent?.uniqueId ?? null, enabled: node.isEnabled(true), worldMatrix: safeMatrix(node), meshUniqueIds: members.filter(mesh => mesh.rootUniqueIds.includes(node.uniqueId)).map(mesh => mesh.uniqueId) })),
			attachedMeshCount: members.length, renderEligibleMeshCount: eligible.length,
			indexedTriangles: members.reduce((sum, mesh) => sum + mesh.geometry.indexedTriangles, 0),
			renderEligibleIndexedTriangles: eligible.reduce((sum, mesh) => sum + mesh.geometry.indexedTriangles, 0),
		};
	});
	const exactDuplicateCandidates = findExactDuplicates(meshes, new Map(sceneMeshes.map(mesh => [mesh.uniqueId, mesh])));
	const renderEligibleRootFamilies = rootFamilies.filter(root => root.renderEligibleMeshCount > 0).map(root => root.family);
	return {
		schemaVersion: 1, phase: options.phase ?? 'manual', frameId: scene.getFrameId(), rootFamilies, meshes,
		orphanCityMeshUniqueIds: meshes.filter(mesh => mesh.rootUniqueIds.length === 0).map(mesh => mesh.uniqueId), shadowMaps, exactDuplicateCandidates,
		summary: {
			presentRootFamilies: rootFamilies.filter(root => root.roots.length > 0).map(root => root.family),
			renderEligibleRootFamilies, overlappingVisibleRepresentations: renderEligibleRootFamilies.length > 1,
			duplicateCandidateGroups: exactDuplicateCandidates.length,
			simultaneousVisibleDuplicateGroups: exactDuplicateCandidates.filter(group => group.simultaneousVisibleCandidate).length,
		},
		limitations: [
			'Render eligible means inherited enabled, own isVisible, visibility > 0 and geometry > 0. It is not a GPU draw, frustum, occlusion or pixel proof.',
			'Overlapping visible representations means multiple representation families eligible together; it is not an AABB-overlap or exact-duplicate claim.',
			'Exact duplicate candidates require the same material object/ordered material slots, exact world matrix and submesh ranges, and shared geometry or equal values in every available vertex attribute and index.',
			'Skinned, morph-target and thin-instance meshes are inventoried but excluded from exact duplication proof. No material equivalence is inferred merely from matching names.',
			'Shadow lists describe explicit registration, including instance source registration; dynamic predicates/custom cascade lists and actual visible shadow pixels are not evaluated.',
		],
	};
}

function reviewMesh(mesh: AbstractMesh, roots: number[], registered: Map<number, string[]>, scene: Scene): CityRepresentationMeshReview {
	const geometry = mesh.geometry;
	const material = mesh.material;
	const multi = material as (Material & { subMaterials?: Array<Material | null> }) | null;
	const materials = multi?.subMaterials ?? (material ? [material] : []);
	const source = (mesh as AbstractMesh & { sourceMesh?: AbstractMesh }).sourceMesh;
	const thinInstances = (mesh as AbstractMesh & { thinInstanceCount?: number }).thinInstanceCount ?? 0;
	const worldMatrix = safeMatrix(mesh);
	const vertices = mesh.getTotalVertices(), indices = mesh.getTotalIndices();
	const effectiveEnabled = mesh.isEnabled(true);
	return {
		uniqueId: mesh.uniqueId, name: mesh.name, nodeClass: mesh.getClassName(), parentUniqueId: mesh.parent?.uniqueId ?? null, rootUniqueIds: roots,
		localEnabled: mesh.isEnabled(false), effectiveEnabled, isVisible: mesh.isVisible, visibility: mesh.visibility,
		renderEligible: effectiveEnabled && mesh.isVisible && mesh.visibility > 0 && vertices > 0,
		cameraLayerCompatible: scene.activeCamera ? (mesh.layerMask & scene.activeCamera.layerMask) !== 0 : null,
		worldMatrix, worldMatrixFinite: worldMatrix.every(value => value !== null),
		geometry: { id: geometry?.id ?? null, uniqueId: geometry?.uniqueId ?? null, vertices, indices, indexedTriangles: Math.floor(indices / 3), vertexKinds: geometry?.getVerticesDataKinds().slice().sort() ?? [] },
		material: { uniqueId: material?.uniqueId ?? null, name: material?.name ?? null, slots: materials.map(slot => ({ uniqueId: slot?.uniqueId ?? null, name: slot?.name ?? null })) },
		subMeshes: mesh.subMeshes.map(sub => ({ materialIndex: sub.materialIndex, verticesStart: sub.verticesStart, verticesCount: sub.verticesCount, indexStart: sub.indexStart, indexCount: sub.indexCount })),
		shadow: { receives: mesh.receiveShadows, registeredMaps: registered.get(mesh.uniqueId) ?? [], sourceRegisteredMaps: source ? registered.get(source.uniqueId) ?? [] : [] },
		thinInstances, animatedGeometry: !!(mesh.skeleton || mesh.morphTargetManager),
	};
}

function safeMatrix(node: Node): Array<number | null> {
	// Bootstrap snapshots run before the first render. Reading the cached matrix
	// there can return identity for every newly placed mesh and invent duplicates.
	return Array.from(node.computeWorldMatrix(true).asArray(), value => Number.isFinite(value) ? value : null);
}

function findExactDuplicates(reviews: CityRepresentationMeshReview[], actual: Map<number, AbstractMesh>): CityRepresentationReviewSnapshot['exactDuplicateCandidates'] {
	const buckets = new Map<string, CityRepresentationMeshReview[]>();
	for (const mesh of reviews) {
		if (mesh.geometry.vertices === 0 || !mesh.worldMatrixFinite || mesh.animatedGeometry || mesh.thinInstances > 0) continue;
		// No bounds are involved. Only potentially identical draw definitions get
		// expensive CPU buffer comparison; unique transforms remain inexpensive.
		const key = JSON.stringify([mesh.geometry.vertices, mesh.geometry.indices, mesh.geometry.vertexKinds, mesh.material.uniqueId, mesh.material.slots.map(slot => slot.uniqueId), mesh.subMeshes, mesh.worldMatrix]);
		buckets.set(key, [...(buckets.get(key) ?? []), mesh]);
	}
	const duplicates: CityRepresentationReviewSnapshot['exactDuplicateCandidates'] = [];
	for (const bucket of buckets.values()) {
		const groups: CityRepresentationMeshReview[][] = [];
		for (const mesh of bucket) {
			const geometry = actual.get(mesh.uniqueId)?.geometry;
			if (!geometry) continue;
			const group = groups.find(group => equalGeometry(geometry, actual.get(group[0].uniqueId)?.geometry ?? null));
			if (group) group.push(mesh); else groups.push([mesh]);
		}
		for (const group of groups.filter(group => group.length > 1)) {
			const visible = group.filter(mesh => mesh.renderEligible).map(mesh => mesh.uniqueId);
			const firstGeometry = actual.get(group[0].uniqueId)?.geometry;
			duplicates.push({ meshUniqueIds: group.map(mesh => mesh.uniqueId), meshNames: group.map(mesh => mesh.name), renderEligibleMeshUniqueIds: visible, simultaneousVisibleCandidate: visible.length > 1, comparison: group.every(mesh => actual.get(mesh.uniqueId)?.geometry === firstGeometry) ? 'shared-geometry-object' : 'all-vertex-attributes-and-indices' });
		}
	}
	return duplicates;
}

function equalGeometry(left: Geometry, right: Geometry | null): boolean {
	if (!right) return false;
	if (left === right) return true;
	const leftKinds = left.getVerticesDataKinds().slice().sort();
	const rightKinds = right.getVerticesDataKinds().slice().sort();
	if (leftKinds.length !== rightKinds.length || leftKinds.some((kind, index) => kind !== rightKinds[index])) return false;
	if (!equalNumbers(left.getIndices(), right.getIndices())) return false;
	return leftKinds.every(kind => equalNumbers(left.getVerticesData(kind), right.getVerticesData(kind)));
}

function equalNumbers(left: ArrayLike<number> | null, right: ArrayLike<number> | null): boolean {
	if (left === null || right === null || left.length !== right.length) return false;
	for (let i = 0; i < left.length; i++) if (!Number.isFinite(left[i]) || left[i] !== right[i]) return false;
	return true;
}
