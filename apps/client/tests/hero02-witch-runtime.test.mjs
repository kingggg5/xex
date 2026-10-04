// Hero 02 (witch, Mage) runtime smoke test on Babylon.js 9.27.1 NullEngine (CPU only: no GPU, no shaders).
// Loads the post-processed runtime GLBs from assets/models/heroes/hero02/runtime and proves:
//   1. the XS1 skeleton (59 joints), socket/fx nodes and the 14 clips load from LOD0;
//   2. every AnimationGroup starts, plays (weighted bone matrices move, all finite), loops or ends, and stops;
//      loops close; durations and release frames match the sidecar hero02_witch.clips.json;
//   3. LOD1/LOD2 skins follow the LOD0 joints (bones linked by name) and LOD switching by camera distance works;
//   4. the staff GLB parented to socket_weapon_R stays in the hand through every clip;
//   5. rest height, pivot and facing (Babylon +Z) are as contracted.
// Skips (with the reason) when the runtime files are missing.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { LoadAssetContainerAsync, SceneLoader } from '@babylonjs/core/Loading/sceneLoader.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode.js';
import { Vector3, Matrix, Quaternion } from '@babylonjs/core/Maths/math.vector.js';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer.js';
import { MeshoptDecoder } from 'meshoptimizer/decoder';
import '@babylonjs/core/Meshes/instancedMesh.js';
import '@babylonjs/loaders/glTF/index.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const dir = path.join(root, 'assets/models/heroes/hero02/runtime');
const files = {
	lod0: path.join(dir, 'hero02_witch_lod0.glb'),
	lod1: path.join(dir, 'hero02_witch_lod1.glb'),
	lod2: path.join(dir, 'hero02_witch_lod2.glb'),
	staff: path.join(dir, 'hero02_staff_lod0.glb'),
	clips: path.join(dir, 'hero02_witch.clips.json'),
};
const missing = Object.values(files).filter(f => !fs.existsSync(f));
const skip = missing.length ? `runtime files missing: ${missing.map(f => path.basename(f)).join(', ')}` : false;
const EXPECTED_CLIPS = ['base.idle', 'base.walk', 'base.run', 'caster.attack_1', 'caster.attack_2', 'mage.skill_nova',
	'mage.skill_gale', 'mage.skill_rift', 'mage.skill_bolt', 'mage.skill_ward', 'mage.skill_starfall', 'base.hit_light',
	'base.dodge', 'base.death'];
const LOOPS = new Set(['base.idle', 'base.walk', 'base.run']);
const SOCKETS = ['socket_weapon_R', 'socket_weapon_L', 'socket_back', 'socket_hip_L', 'socket_hip_R', 'socket_head',
	'socket_face', 'socket_mouth', 'fx_head', 'fx_chest', 'fx_hand_L', 'fx_hand_R', 'fx_feet'];

function parseGlb(bytes) {
	let gltf, binary, offset = 12;
	while (offset < bytes.length) {
		const size = bytes.readUInt32LE(offset), type = bytes.readUInt32LE(offset + 4);
		const chunk = bytes.subarray(offset + 8, offset + 8 + size);
		if (type === 0x4e4f534a) gltf = JSON.parse(chunk.toString('utf8').trim());
		if (type === 0x004e4942) binary = chunk;
		offset += 8 + size;
	}
	return { gltf, binary: binary ?? Buffer.alloc(0) };
}

/** Decode EXT_meshopt_compression views in memory (same approach as tools/validate-minotaur-runtime.mjs). */
async function expandMeshopt(bytes) {
	const { gltf, binary } = parseGlb(bytes);
	if (!(gltf.bufferViews ?? []).some(v => v.extensions?.EXT_meshopt_compression)) return { bytes, gltf };
	await MeshoptDecoder.ready;
	const g = structuredClone(gltf), parts = [binary];
	let length = binary.length;
	for (const view of g.bufferViews) {
		const c = view.extensions?.EXT_meshopt_compression;
		if (!c) continue;
		const target = Buffer.alloc(c.count * c.byteStride);
		MeshoptDecoder.decodeGltfBuffer(target, c.count, c.byteStride, binary.subarray(c.byteOffset ?? 0, (c.byteOffset ?? 0) + c.byteLength), c.mode, c.filter ?? 'NONE');
		const pad = (4 - length % 4) % 4;
		if (pad) { parts.push(Buffer.alloc(pad)); length += pad; }
		view.buffer = 0; view.byteOffset = length; view.byteLength = target.length;
		delete view.extensions.EXT_meshopt_compression;
		if (!Object.keys(view.extensions).length) delete view.extensions;
		parts.push(target); length += target.length;
	}
	g.buffers = [{ byteLength: length }];
	for (const key of ['extensionsUsed', 'extensionsRequired']) if (g[key]) g[key] = g[key].filter(n => n !== 'EXT_meshopt_compression');
	const json = Buffer.from(JSON.stringify(g));
	const jsonChunk = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 0x20)]);
	const binChunk = Buffer.concat([...parts, Buffer.alloc((4 - length % 4) % 4)]);
	const header = Buffer.alloc(12), jh = Buffer.alloc(8), bh = Buffer.alloc(8);
	header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonChunk.length + binChunk.length, 8);
	jh.writeUInt32LE(jsonChunk.length); jh.writeUInt32LE(0x4e4f534a, 4);
	bh.writeUInt32LE(binChunk.length); bh.writeUInt32LE(0x004e4942, 4);
	return { bytes: Buffer.concat([header, jh, jsonChunk, bh, binChunk]), gltf };
}

async function load(scene, file) {
	const { bytes, gltf } = await expandMeshopt(fs.readFileSync(file));
	const container = await LoadAssetContainerAsync(new Uint8Array(bytes), scene, { pluginExtension: '.glb', name: path.basename(file) });
	container.addAllToScene();
	return { container, gltf };
}

function skinnedMeshes(container) { return container.meshes.filter(m => m.skeleton && m.getTotalVertices() > 0); }
function nodeMap(container) { return new Map(container.transformNodes.map(n => [n.name, n])); }
const finite = arr => Array.from(arr).every(Number.isFinite);

/** CPU skinning: world positions of a skinned mesh for the current pose. */
function skinnedWorldPositions(mesh) {
	mesh.computeWorldMatrix(true);
	mesh.skeleton.prepare(true);
	const pos = mesh.getVerticesData(VertexBuffer.PositionKind);
	const idx = mesh.getVerticesData(VertexBuffer.MatricesIndicesKind);
	const wts = mesh.getVerticesData(VertexBuffer.MatricesWeightsKind);
	const mats = mesh.skeleton.getTransformMatrices(mesh);
	const world = mesh.getWorldMatrix().m;
	const out = new Float32Array(pos.length);
	for (let v = 0; v < pos.length / 3; v++) {
		const x = pos[v * 3], y = pos[v * 3 + 1], z = pos[v * 3 + 2];
		let sx = 0, sy = 0, sz = 0;
		for (let k = 0; k < 4; k++) {
			const w = wts[v * 4 + k];
			if (w <= 0) continue;
			const o = idx[v * 4 + k] * 16;
			sx += w * (mats[o] * x + mats[o + 4] * y + mats[o + 8] * z + mats[o + 12]);
			sy += w * (mats[o + 1] * x + mats[o + 5] * y + mats[o + 9] * z + mats[o + 13]);
			sz += w * (mats[o + 2] * x + mats[o + 6] * y + mats[o + 10] * z + mats[o + 14]);
		}
		out[v * 3] = world[0] * sx + world[4] * sy + world[8] * sz + world[12];
		out[v * 3 + 1] = world[1] * sx + world[5] * sy + world[9] * sz + world[13];
		out[v * 3 + 2] = world[2] * sx + world[6] * sy + world[10] * sz + world[14];
	}
	return out;
}

function bounds(positionsList) {
	const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
	for (const p of positionsList) for (let i = 0; i < p.length; i += 3) for (let a = 0; a < 3; a++) { min[a] = Math.min(min[a], p[i + a]); max[a] = Math.max(max[a], p[i + a]); }
	return { min, max };
}

function refreshWorld(scene) {
	for (const n of scene.transformNodes) n.computeWorldMatrix(true);
	for (const m of scene.meshes) m.computeWorldMatrix(true);
}

let fixture;
async function getFixture() {
	if (fixture) return fixture;
	const engine = new NullEngine({ renderWidth: 1280, renderHeight: 720, textureSize: 256 });
	const scene = new Scene(engine);
	const observer = SceneLoader.OnPluginActivatedObservable.add(loader => {
		if (loader.name === 'gltf') { loader.skipMaterials = true; loader.animationStartMode = 0; }
	});
	const lod0 = await load(scene, files.lod0);
	const lod1 = await load(scene, files.lod1);
	const lod2 = await load(scene, files.lod2);
	const staff = await load(scene, files.staff);
	SceneLoader.OnPluginActivatedObservable.remove(observer);
	const sidecar = JSON.parse(fs.readFileSync(files.clips, 'utf8'));
	fixture = { engine, scene, lod0, lod1, lod2, staff, sidecar };
	return fixture;
}

test('LOD0 loads the XS1 skeleton, the socket and fx nodes and all 14 clips', { skip }, async () => {
	const { lod0 } = await getFixture();
	const meshes = skinnedMeshes(lod0.container);
	assert.ok(meshes.length >= 1, 'skinned LOD0 mesh present');
	const skel = lod0.container.skeletons[0];
	const joints = lod0.gltf.skins[0].joints.length;
	assert.equal(joints, 59, 'XS1 core 43 + hero 02 secondaries 16');
	assert.ok(skel.bones.length === joints || skel.bones.length === joints + 1, `bones ${skel.bones.length}`);
	const names = nodeMap(lod0.container);
	for (const s of SOCKETS) assert.ok(names.has(s), `node ${s}`);
	const groups = lod0.container.animationGroups.map(g => g.name).sort();
	assert.deepEqual(groups, [...EXPECTED_CLIPS].sort());
	for (const m of meshes) {
		const w = m.getVerticesData(VertexBuffer.MatricesWeightsKind);
		for (let v = 0; v < w.length / 4; v++) {
			const s = w[v * 4] + w[v * 4 + 1] + w[v * 4 + 2] + w[v * 4 + 3];
			assert.ok(Math.abs(s - 1) < 0.01, `weights of ${m.name} vertex ${v} sum ${s}`);
		}
		assert.equal(m.getVerticesData(VertexBuffer.MatricesWeightsExtraKind), null, 'max 4 influences');
	}
});

test('every clip starts, plays with finite moving bone matrices, loops or ends, and stops', { skip }, async () => {
	const { scene, lod0, sidecar } = await getFixture();
	const meshes = skinnedMeshes(lod0.container);
	const skel = meshes[0].skeleton;
	for (const group of lod0.container.animationGroups) {
		lod0.container.animationGroups.forEach(g => g.stop());
		const meta = sidecar.clips[group.name];
		assert.ok(meta, `sidecar entry for ${group.name}`);
		const fps = group.targetedAnimations[0].animation.framePerSecond;
		const durationMs = (group.to - group.from) / fps * 1000;
		assert.ok(Math.abs(durationMs - meta.duration_ms) <= 34, `${group.name}: ${durationMs} ms vs sidecar ${meta.duration_ms}`);
		group.start(LOOPS.has(group.name), 1, group.from, group.to, false);
		assert.ok(group.isStarted, `${group.name} started`);
		const samples = Math.max(8, Math.round(durationMs / 33));
		let first = null, maxChange = 0, last = null;
		for (let i = 0; i <= samples; i++) {
			group.goToFrame(group.from + (group.to - group.from) * i / samples);
			refreshWorld(scene);
			skel.prepare(true);
			const m = Float32Array.from(skel.getTransformMatrices(meshes[0]));
			assert.ok(finite(m), `${group.name} finite matrices at sample ${i}`);
			if (!first) first = m;
			let d = 0;
			for (let k = 0; k < m.length; k++) d = Math.max(d, Math.abs(m[k] - first[k]));
			maxChange = Math.max(maxChange, d);
			last = m;
		}
		assert.ok(maxChange > 1e-3, `${group.name} moves (max matrix change ${maxChange})`);
		if (LOOPS.has(group.name)) {
			let d = 0;
			for (let k = 0; k < last.length; k++) d = Math.max(d, Math.abs(last[k] - first[k]));
			assert.ok(d < 5e-3, `${group.name} loop closes (endpoint difference ${d})`);
		}
		for (const ev of meta.events) assert.ok(ev.t_ms >= 0 && ev.t_ms <= meta.duration_ms + 1, `${group.name} event ${ev.id} inside the clip`);
		if (!LOOPS.has(group.name) && group.name.startsWith('mage.')) assert.ok(meta.events.some(e => e.id === 'release'), `${group.name} names its release frame`);
		group.stop();
		assert.equal(group.isPlaying, false, `${group.name} stopped`);
	}
});

test('LOD1 and LOD2 follow the LOD0 joints and LOD switching by distance works', { skip }, async () => {
	const { scene, lod0, lod1, lod2 } = await getFixture();
	const hero = new TransformNode('hero02_root', scene);
	const roots = [lod0, lod1, lod2].map(l => l.container.meshes.find(m => m.name === '__root__'));
	for (const r of roots) r.parent = hero;
	const joints0 = nodeMap(lod0.container);
	for (const l of [lod1, lod2]) {
		for (const skel of l.container.skeletons) {
			for (const bone of skel.bones) {
				const target = joints0.get(bone.name);
				assert.ok(target, `LOD0 has node ${bone.name}`);
				bone.linkTransformNode(target);
			}
		}
	}
	const m0 = skinnedMeshes(lod0.container), m1 = skinnedMeshes(lod1.container), m2 = skinnedMeshes(lod2.container);
	const byMaterialIndex = list => list.slice().sort((a, b) => a.name.localeCompare(b.name));
	const [s0, s1, s2] = [byMaterialIndex(m0), byMaterialIndex(m1), byMaterialIndex(m2)];
	assert.equal(s0.length, s1.length);
	assert.equal(s0.length, s2.length);
	for (let i = 0; i < s0.length; i++) {
		s0[i].addLODLevel(15, s1[i]);
		s0[i].addLODLevel(35, s2[i]);
		s0[i].addLODLevel(60, null);
	}
	const camera = new FreeCamera('lod-cam', new Vector3(0, 1.6, -10), scene);
	camera.minZ = 0.1;
	camera.setTarget(new Vector3(0, 1, 0));
	const check = (dist, expected) => {
		camera.position.set(0, 1.6, -dist);
		camera.getViewMatrix(true);
		camera.getProjectionMatrix(true);
		refreshWorld(scene);
		for (let i = 0; i < s0.length; i++) assert.equal(s0[i].getLOD(camera), expected[i], `LOD at ${dist} m`);
	};
	check(8, s0);
	check(22, s1);
	check(45, s2);
	check(80, s0.map(() => null));
	// the linked LOD1/LOD2 skins follow the LOD0 animation: compare skinned bounds while clips play
	const groups = new Map(lod0.container.animationGroups.map(g => [g.name, g]));
	for (const [name, t] of [['base.run', 0.3], ['mage.skill_rift', 0.66], ['base.death', 1.0], ['mage.skill_starfall', 0.5]]) {
		const g = groups.get(name);
		lod0.container.animationGroups.forEach(x => x.stop());
		g.start(false, 1, g.from, g.to, false);
		g.goToFrame(g.from + (g.to - g.from) * t);
		refreshWorld(scene);
		for (const sk of [...lod1.container.skeletons, ...lod2.container.skeletons]) sk.prepare(true);
		const b0 = bounds(s0.map(skinnedWorldPositions));
		const b1 = bounds(s1.map(skinnedWorldPositions));
		const b2 = bounds(s2.map(skinnedWorldPositions));
		for (let a = 0; a < 3; a++) {
			assert.ok(Math.abs(b1.min[a] - b0.min[a]) < 0.06 && Math.abs(b1.max[a] - b0.max[a]) < 0.06, `${name} LOD1 bounds axis ${a}: ${b1.min[a]}..${b1.max[a]} vs ${b0.min[a]}..${b0.max[a]}`);
			assert.ok(Math.abs(b2.min[a] - b0.min[a]) < 0.15 && Math.abs(b2.max[a] - b0.max[a]) < 0.15, `${name} LOD2 bounds axis ${a}: ${b2.min[a]}..${b2.max[a]} vs ${b0.min[a]}..${b0.max[a]}`);
		}
		g.stop();
	}
});

test('the staff stays in the right-hand socket through every clip', { skip }, async () => {
	const { scene, lod0, staff } = await getFixture();
	const socket = nodeMap(lod0.container).get('socket_weapon_R');
	const hand = nodeMap(lod0.container).get('hand.R');
	const staffRoot = staff.container.meshes.find(m => m.name === '__root__');
	const staffNode = staffRoot.getChildren()[0];
	assert.ok(staffNode, 'staff top node');
	staffNode.parent = socket;
	staffNode.position.setAll(0);
	staffNode.rotationQuaternion = Quaternion.Identity();
	staffNode.scaling.setAll(1);
	const all = staff.container.transformNodes.concat(staff.container.meshes);
	const tip = all.find(n => n.name === 'fx_tip'), base = all.find(n => n.name === 'fx_base'), head = all.find(n => n.name === 'fx_head');
	assert.ok(tip && base && head, 'staff fx_tip / fx_base / fx_head markers');
	let d0 = null, maxDev = 0, maxSocketGap = 0, tipTravel = 0;
	for (const g of lod0.container.animationGroups) {
		lod0.container.animationGroups.forEach(x => x.stop());
		g.start(false, 1, g.from, g.to, false);
		let prevTip = null;
		for (let i = 0; i <= 10; i++) {
			g.goToFrame(g.from + (g.to - g.from) * i / 10);
			refreshWorld(scene);
			const s = socket.getAbsolutePosition(), st = staffNode.getAbsolutePosition(), h = hand.getAbsolutePosition();
			maxSocketGap = Math.max(maxSocketGap, Vector3.Distance(s, st));
			const d = Vector3.Distance(st, h);
			if (d0 === null) d0 = d;
			maxDev = Math.max(maxDev, Math.abs(d - d0));
			const tp = tip.getAbsolutePosition();
			assert.ok([tp.x, tp.y, tp.z].every(Number.isFinite));
			if (prevTip) tipTravel = Math.max(tipTravel, Vector3.Distance(tp, prevTip));
			prevTip = tp.clone();
		}
		g.stop();
	}
	assert.ok(maxSocketGap < 1e-4, `staff origin stays on the socket (gap ${maxSocketGap})`);
	assert.ok(maxDev < 1e-3, `grip-to-hand distance constant (deviation ${maxDev} m)`);
	assert.ok(d0 > 0.02 && d0 < 0.15, `grip sits in the fist, ${d0.toFixed(3)} m from the wrist joint`);
	const len = Vector3.Distance(tip.getAbsolutePosition(), base.getAbsolutePosition());
	assert.ok(Math.abs(len - 1.15) < 0.002, `canonical fx_base -> fx_tip trail segment ${len.toFixed(3)} m`);
	assert.ok(tipTravel > 0.05, 'the staff tip moves with the clips');
});

test('rest pose: crown and hat heights, pivot between the feet, facing Babylon +Z', { skip }, async () => {
	const { scene, lod0 } = await getFixture();
	lod0.container.animationGroups.forEach(g => g.stop());
	const names = nodeMap(lod0.container);
	// stopped groups leave the last sampled pose on the joint nodes: restore the bind pose from the glTF nodes
	for (const n of lod0.gltf.nodes) {
		const node = names.get(n.name);
		if (!node) continue;
		if (n.translation) node.position = Vector3.FromArray(n.translation); else node.position.setAll(0);
		node.rotationQuaternion = n.rotation ? Quaternion.FromArray(n.rotation) : Quaternion.Identity();
		if (n.scale) node.scaling = Vector3.FromArray(n.scale); else node.scaling.setAll(1);
	}
	refreshWorld(scene);
	const head = names.get('head').getAbsolutePosition();
	const footL = names.get('foot.L').getAbsolutePosition(), toeL = names.get('toe.L').getAbsolutePosition();
	const footR = names.get('foot.R').getAbsolutePosition();
	assert.ok(toeL.z > footL.z + 0.05, `toes point to +Z (foot ${footL.z.toFixed(3)} -> toe ${toeL.z.toFixed(3)})`);
	assert.ok(Math.abs((footL.x + footR.x) / 2) < 0.02, 'pivot centred between the feet (x)');
	assert.ok(head.y > 1.6 && head.y < 1.72, `head joint at ${head.y.toFixed(3)} m`);
	const b = bounds(skinnedMeshes(lod0.container).map(skinnedWorldPositions));
	assert.ok(b.min[1] > -0.02 && b.min[1] < 0.02, `soles on the ground (min y ${b.min[1].toFixed(3)})`);
	assert.ok(b.max[1] > 1.90 && b.max[1] < 2.02, `hat tip at ${b.max[1].toFixed(3)} m (crown 1.80 m without the hat)`);
});
