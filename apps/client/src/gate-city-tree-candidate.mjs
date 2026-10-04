// Exact active-R5 primitive offsets, before MergeMeshes. A failed guard retires nothing.
export const GATE_CITY_TREE = Object.freeze({
	id: 'blossom tree trunk.003',
	runtimeSha256: '95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72',
	placement: Object.freeze({ id: 'city-gate-blossom-003-cc0', species: 'qn_conifer_m', x: -6.30322, y: 0, z: 27.76605, yaw: 0, scale: 1.08, cell: '-1,0', keep: true, order: 300 }),
	oldHeight: 11.033226796243596, replacementHeight: 8.64,
	removedTriangles: 1564,
});
export const GATE_CITY_TREE_PARTS = Object.freeze([
	{ material: 'flower_ivory', count: 21600, ranges: [[5760, 7680]], hash: 'f4b959c5', bounds: [-8.6567240471, 3.5522031484, 144.9790698484, -2.1796659034, 9.9464344617, 151.6880431175], aabb: '-87:36:1450:-22:99:1517', ends: [[[5760,5761,5762,5763,5764,5765,5766,5767,5768],[7671,7672,7673,7674,7675,7676,7677,7678,7679]]] },
	{ material: 'foliage_blossom', count: 6480, ranges: [[2160, 2880]], hash: '7afa32c5', bounds: [-9.4842293671, 3.5144318108, 145.9004109968, -4.6391895211, 9.5379862464, 151.2175196165], aabb: '-95:35:1459:-46:95:1512', ends: [[[2160,2161,2162,2163,2164,2165,2166,2167,2168],[2871,2872,2873,2874,2875,2876,2877,2878,2879]]] },
	{ material: 'foliage_mid', count: 69720, ranges: [[27360, 28080]], hash: '277f1255', bounds: [-8.8117082968, 4.6929319018, 144.4386140804, -3.0736511999, 11.0379284208, 150.1403791594], aabb: '-88:47:1444:-31:110:1501', ends: [[[27360,27361,27362,27363,27364,27365,27366,27367,27368],[28071,28072,28073,28074,28075,28076,28077,28078,28079]]] },
	{ material: 'timber_dark', count: 444942, ranges: [[35178, 35280], [405282, 406512]], hash: '851c9f19', bounds: [-8.7843432035, .0027695271, 145.2958234059, -3.8448353055, 6.5214318863, 151.8723143668], aabb: '-88:0:1453:-38:65:1519', ends: [[[32164,32165,32166,32164,32166,32167,32168,32169,32170],[32255,32256,32257,32258,32259,32260,32261,32262,32263]],[[280639,280640,280641,280639,280641,280642,280643,280644,280645],[281460,281462,281463,281464,281465,281466,281464,281466,281467]]] },
]);
const requireGuard = (valid, label) => { if (!valid) throw new Error(`Gate tree guard: ${label}`); };

/** Returns all four replacement index buffers only after all five ranges validate.
 * Positions are original primitive vertices transformed back into glTF city space. */
export function planGateCityTreeCandidate(primitives, runtimeSha256) {
	requireGuard(runtimeSha256 === GATE_CITY_TREE.runtimeSha256, 'active runtime SHA256');
	const validated = [];
	for (const spec of GATE_CITY_TREE_PARTS) {
		const matches = primitives.filter(p => p.material === spec.material);
		requireGuard(matches.length === 1, `${spec.material} unique original primitive`);
		const input = matches[0], indices = input.indices;
		requireGuard(input.name === `City / ${spec.material}` && indices.length === spec.count, `${spec.material} name/count`);
		const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
		let hash = 2166136261, removed = 0;
		for (const [rangeIndex, [start, end]] of spec.ranges.entries()) {
			for (let i = 0; i < 9; i++) {
				requireGuard(indices[start+i] === spec.ends[rangeIndex][0][i] && indices[end-9+i] === spec.ends[rangeIndex][1][i], `${spec.material} first/last index witnesses`);
			}
			for (let offset = start; offset < end; offset++) {
				const index = indices[offset]; requireGuard(Number.isSafeInteger(index) && index >= 0, 'vertex index');
				for (let shift = 0; shift < 32; shift += 8) hash = Math.imul(hash ^ ((index >>> shift) & 255), 16777619) >>> 0;
				const point = input.gltfPositionAt(index);
				for (let axis = 0; axis < 3; axis++) {
					requireGuard(Number.isFinite(point[axis]), 'finite original vertex');
					min[axis] = Math.min(min[axis], point[axis]); max[axis] = Math.max(max[axis], point[axis]);
				}
				removed++;
			}
		}
		requireGuard(hash.toString(16).padStart(8, '0') === spec.hash, `${spec.material} selected index hash`);
		const bounds = [...min, ...max];
		requireGuard(bounds.map(v => Math.round(v*10)).join(':') === spec.aabb && bounds.every((v,i) => Math.abs(v-spec.bounds[i]) < .02), `${spec.material} selected AABB/hash`);
		validated.push({ input, spec, removed });
	}
	return { placement: { ...GATE_CITY_TREE.placement }, removedTriangles: GATE_CITY_TREE.removedTriangles,
		patches: validated.map(({input,spec,removed}) => {
			const output = new Uint32Array(input.indices.length-removed); let write = 0, range = 0;
			for (let offset = 0; offset < input.indices.length; offset++) {
				while (range < spec.ranges.length && offset >= spec.ranges[range][1]) range++;
				if (range < spec.ranges.length && offset >= spec.ranges[range][0]) continue;
				output[write++] = input.indices[offset];
			}
			return { material: spec.material, indices: output, originalIndices: input.indices, removedTriangles: removed/3 };
		}) };
}
