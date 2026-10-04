#!/usr/bin/env node
// Stage 2: hero 02 LOD index buffers with meshoptimizer 1.3.0 (repo-pinned, apps/client/node_modules).
// Input:  assets/models/heroes/hero02/work/meshopt/{positions,normals,uvs,material,protect}.f32 + indices.u32
//         (written by h02_build_highpoly.py: one vertex per unique (position, atlas UV, material) corner)
// Output: work/meshopt/lod{0,1,2}.indices.u32 + simplify-report.json
// The simplifier only removes vertices (simplifyWithAttributes, no vertex update), so every LOD vertex is an
// original vertex: UVs and skin weights are exact copies of the high-poly values ("UV-preserving collapse").
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MeshoptSimplifier } from '../../../../apps/client/node_modules/meshoptimizer/meshopt_simplifier.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../../..');
// CLI: node h02_simplify.mjs [arrayDir] [target0,target1,target2]   (defaults: the hero body, 11950,5975,2490)
const dir = path.resolve(root, process.argv[2] ?? 'assets/models/heroes/hero02/work/meshopt');
const targets = (process.argv[3] ?? '11950,5975,2490').split(',').map(Number);
const readF32 = name => new Float32Array(fs.readFileSync(path.join(dir, name)).buffer.slice(0));
const readU32 = name => new Uint32Array(fs.readFileSync(path.join(dir, name)).buffer.slice(0));

await MeshoptSimplifier.ready;
const positions = readF32('positions.f32');
const normals = readF32('normals.f32');
const uvs = readF32('uvs.f32');
const material = readF32('material.f32');
const protect = readF32('protect.f32');
const indices = readU32('indices.u32');
const vertexCount = positions.length / 3;
if (normals.length !== positions.length || uvs.length !== vertexCount * 2 || material.length !== vertexCount || protect.length !== vertexCount) {
	throw new Error('attribute array lengths do not match the vertex count');
}

// Attributes: normal (3), atlas UV (2), protection channel = protect * position (3): inside protected regions
// (face 1.0, hands 0.7, head 0.4, hair 0.35, hat 0.2) the extra channel multiplies the geometric error, so the face
// and hands keep more triangles; at their borders the channel jumps, which keeps a clean ring of edges.
const STRIDE = 8;
const weights = [0.6, 0.6, 0.6, 1.0, 1.0, 4.0, 4.0, 4.0];
const attributes = new Float32Array(vertexCount * STRIDE);
for (let v = 0; v < vertexCount; v++) {
	const o = v * STRIDE;
	attributes[o] = normals[v * 3]; attributes[o + 1] = normals[v * 3 + 1]; attributes[o + 2] = normals[v * 3 + 2];
	attributes[o + 3] = uvs[v * 2]; attributes[o + 4] = uvs[v * 2 + 1];
	const p = protect[v];
	attributes[o + 5] = p * positions[v * 3]; attributes[o + 6] = p * positions[v * 3 + 1]; attributes[o + 7] = p * positions[v * 3 + 2];
}
const scale = MeshoptSimplifier.getScale(positions, 3);

const lods = [
	{ lod: 0, target: targets[0], flags: [['RegularizeLight'], ['RegularizeLight', 'Prune']] },
	{ lod: 1, target: targets[1], flags: [['RegularizeLight', 'Prune'], ['Prune']] },
	{ lod: 2, target: targets[2], flags: [['Prune'], ['Prune', 'Permissive']] },
].filter(spec => spec.lod < targets.length);
const report = { source: { vertices: vertexCount, triangles: indices.length / 3, scaleMetres: scale }, weights, lods: [] };
for (const spec of lods) {
	let best = null;
	for (const flags of spec.flags) {
		const [out, error] = MeshoptSimplifier.simplifyWithAttributes(indices, positions, 3, attributes, STRIDE, weights, null, spec.target * 3, 1.0, flags);
		const tris = out.length / 3;
		best = { out, error, flags, tris };
		if (tris <= spec.target) break;
	}
	if (best.tris === 0) throw new Error(`LOD${spec.lod}: simplification removed every triangle; choose a less aggressive target or omit this optional LOD`);
	if (best.tris > spec.target) throw new Error(`LOD${spec.lod}: ${best.tris} triangles > target ${spec.target}`);
	// material per triangle from its vertices (vertices are split by material, so all three agree)
	let mismatched = 0;
	const perMaterial = [0, 0, 0, 0];
	const used = new Set();
	for (let t = 0; t < best.out.length; t += 3) {
		const a = material[best.out[t]], b = material[best.out[t + 1]], c = material[best.out[t + 2]];
		if (a !== b || b !== c) mismatched++;
		perMaterial[a]++;
		used.add(best.out[t]); used.add(best.out[t + 1]); used.add(best.out[t + 2]);
	}
	fs.writeFileSync(path.join(dir, `lod${spec.lod}.indices.u32`), Buffer.from(best.out.buffer, best.out.byteOffset, best.out.byteLength));
	const row = { lod: spec.lod, target: spec.target, triangles: best.tris, verticesUsed: used.size, flags: best.flags,
		errorRelative: best.error, errorMetres: best.error * scale, perMaterial, mismatchedMaterialTriangles: mismatched };
	report.lods.push(row);
	console.log(JSON.stringify(row));
}
fs.writeFileSync(path.join(dir, 'simplify-report.json'), JSON.stringify(report, null, 2) + '\n');
