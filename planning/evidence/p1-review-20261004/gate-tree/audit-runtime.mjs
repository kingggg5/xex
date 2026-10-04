// CPU-only readback. Immutable active source/runtime bytes are never modified.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { MeshoptDecoder } from '../../../../apps/client/node_modules/meshoptimizer/meshopt_decoder.mjs';
await MeshoptDecoder.ready;
const wanted = new Set(['foliage_blossom', 'flower_ivory', 'foliage_mid', 'timber_dark']);
export const readGateTreeGeometry = (path, includeData = false, materials = wanted) => {
	const bytes = fs.readFileSync(path), length = bytes.readUInt32LE(12);
	const json = JSON.parse(bytes.subarray(20, 20 + length).toString()), binary = bytes.subarray(28 + length), decoded = new Map();
	const accessor = index => {
		const a = json.accessors[index], view = json.bufferViews[a.bufferView], e = view.extensions?.EXT_meshopt_compression;
		if (!decoded.has(a.bufferView)) {
			let data;
			if (e) { data = new Uint8Array(e.count * e.byteStride); MeshoptDecoder.decodeGltfBuffer(data, e.count, e.byteStride, binary.subarray(e.byteOffset, e.byteOffset + e.byteLength), e.mode, e.filter ?? 'NONE'); }
			else data = binary.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
			decoded.set(a.bufferView, new DataView(data.buffer, data.byteOffset, data.byteLength));
		}
		const data = decoded.get(a.bufferView), width = { SCALAR: 1, VEC3: 3 }[a.type], size = { 5122: 2, 5123: 2, 5125: 4, 5126: 4 }[a.componentType], stride = view.byteStride ?? width * size;
		return Array.from({ length: a.count }, (_, i) => Array.from({ length: width }, (_, axis) => {
			const offset = (a.byteOffset ?? 0) + i * stride + axis * size;
			let value = a.componentType === 5122 ? data.getInt16(offset, true) : a.componentType === 5123 ? data.getUint16(offset, true) : a.componentType === 5125 ? data.getUint32(offset, true) : data.getFloat32(offset, true);
			if (a.normalized) value = a.componentType === 5122 ? Math.max(-1, value / 32767) : value / 65535;
			return value;
		}));
	};
	const primitives = [];
	for (const [nodeIndex, node] of json.nodes.entries()) if (node.mesh !== undefined) for (const [primitiveIndex, primitive] of json.meshes[node.mesh].primitives.entries()) {
		const material = json.materials[primitive.material].name;
		if (materials && !materials.has(material)) continue;
		if (node.matrix || json.nodes.some(parent => parent.children?.includes(nodeIndex))) throw new Error('Unexpected target transform');
		const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
		const p = accessor(primitive.attributes.POSITION).map(point => {
			const scaled = point.map((value,axis)=>value*(node.scale?.[axis]??1)),q=node.rotation??[0,0,0,1],a=cross(q,scaled),b=cross(q,a);
			return scaled.map((value,axis)=>value+2*q[3]*a[axis]+2*b[axis]+(node.translation?.[axis]??0));
		});
		const indices = accessor(primitive.indices).map(v => v[0]);
		const parent = p.map((_, i) => i), keys = new Map();
		const find = i => { while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; } return i; };
		const join = (a, b) => { a = find(a); b = find(b); if (a !== b) parent[b] = a; };
		p.forEach((point, i) => { const key = point.map(v => Math.round(v * 10000)).join(':'); if (keys.has(key)) join(i, keys.get(key)); else keys.set(key, i); });
		for (let i = 0; i < indices.length; i += 3) { join(indices[i], indices[i + 1]); join(indices[i], indices[i + 2]); }
		const components = new Map();
		for (let i = 0; i < indices.length; i += 3) {
			const key = find(indices[i]);
			let c = components.get(key);
			if (!c) { c = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity], triangleOffsets: [] }; components.set(key, c); }
			c.triangleOffsets.push(i);
			for (const index of indices.slice(i, i + 3)) for (let axis = 0; axis < 3; axis++) { c.min[axis] = Math.min(c.min[axis], p[index][axis]); c.max[axis] = Math.max(c.max[axis], p[index][axis]); }
		}
		primitives.push({ nodeIndex, nodeName: node.name, meshIndex: node.mesh, meshName: json.meshes[node.mesh].name, primitiveIndex, material, materialIndex: primitive.material, positionAccessor: primitive.attributes.POSITION, indexAccessor: primitive.indices, vertexCount: p.length, indexCount: indices.length, ...(includeData ? { positions: p.flat(), indices } : {}), components: [...components.values()].map(c => ({ ...c, centre: c.min.map((v, axis) => (v + c.max[axis]) / 2), triangles: c.triangleOffsets.length })) });
	}
	return { path, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), meshCount: json.meshes.length, primitiveCount: json.meshes.reduce((sum, mesh) => sum + mesh.primitives.length, 0), primitives };
};
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
const source = readGateTreeGeometry('assets/models/reference-city/r5/market-repair-candidate/city-source.glb');
const runtime = readGateTreeGeometry('apps/client/src/assets/models/env_reference_city.glb');
fs.writeFileSync(new URL('./components.json', import.meta.url), JSON.stringify({ source, runtime }));
const summary = file => ({ path: file.path, sha256: file.sha256, meshCount: file.meshCount, primitiveCount: file.primitiveCount, primitives: file.primitives.map(p => ({ node: p.nodeName, material: p.material, components: p.components.length, pink: p.material === 'foliage_blossom' ? p.components.map(c => ({ centre: c.centre.map(v => +v.toFixed(3)), triangles: c.triangles, firstOffset: c.triangleOffsets[0] })) : undefined, trunks: p.material === 'timber_dark' ? p.components.filter(c => c.max[1] - c.min[1] > 4 && c.max[1] - c.min[1] < 10 && c.max[0] - c.min[0] < 1.5 && c.max[2] - c.min[2] < 1.5 && Math.abs(c.min[1]) < .1).map(c => ({ centre: c.centre.map(v => +v.toFixed(3)), min: c.min.map(v => +v.toFixed(3)), max: c.max.map(v => +v.toFixed(3)), triangles: c.triangles })) : undefined })) });
console.log(JSON.stringify({ source: summary(source), runtime: summary(runtime) }, null, 2));
}
