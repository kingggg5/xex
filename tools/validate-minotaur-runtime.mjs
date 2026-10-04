#!/usr/bin/env node
// CPU-only asset gate. This cannot establish visual, GPU, mobile or FPS quality.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { NullEngine } from '../apps/client/node_modules/@babylonjs/core/Engines/nullEngine.js';
import { Engine } from '../apps/client/node_modules/@babylonjs/core/Engines/engine.js';
import { Scene } from '../apps/client/node_modules/@babylonjs/core/scene.js';
import { LoadAssetContainerAsync, SceneLoader } from '../apps/client/node_modules/@babylonjs/core/Loading/sceneLoader.js';
import { VertexBuffer } from '../apps/client/node_modules/@babylonjs/core/Buffers/buffer.js';
import { MeshoptDecoder } from '../apps/client/node_modules/meshoptimizer/meshopt_decoder.mjs';
import '../apps/client/node_modules/@babylonjs/loaders/glTF/index.js';

const DEFAULT_CLIPS = ['Idle', 'Walk', 'Run', 'Talk', 'StaffCast', 'StaffStrike', 'HitReact', 'Death'];
const MAX_FILE_BYTES = 256 * 1024 * 1024;
const MAX_SAMPLES_PER_CLIP = 1801;
const options = { expectedClips: DEFAULT_CLIPS, expectedHeight: null };
for (let index = 2; index < process.argv.length; index += 2) {
	const key = process.argv[index], value = process.argv[index + 1];
	if (!value || !['--input', '--out', '--expected-clips', '--expected-height'].includes(key)) {
		throw new Error('Usage: node tools/validate-minotaur-runtime.mjs --input model.glb --out report.json [--expected-clips Idle,Walk,...] [--expected-height 2.4]');
	}
	if (key === '--input') options.input = path.resolve(value);
	if (key === '--out') options.out = path.resolve(value);
	if (key === '--expected-clips') options.expectedClips = value.split(',').map(name => name.trim()).filter(Boolean);
	if (key === '--expected-height') options.expectedHeight = Number(value);
}
if (!options.input || !options.out || options.input.toLowerCase() === options.out.toLowerCase() || path.extname(options.out).toLowerCase() !== '.json') throw new Error('A distinct JSON --out path is required.');
if (options.expectedHeight !== null && !(options.expectedHeight > 0)) throw new Error('--expected-height must be positive.');
// Abort outside the report-writing catch if an existing output is a source alias.
const existingOutput = await fs.stat(options.out).catch(error => error.code === 'ENOENT' ? null : Promise.reject(error));
if (existingOutput) {
	const inputStat = await fs.stat(options.input).catch(error => error.code === 'ENOENT' ? null : Promise.reject(error));
	if (inputStat && existingOutput.dev === inputStat.dev && existingOutput.ino === inputStat.ino) throw new Error('Output aliases the input source file.');
}

const report = {
	schemaVersion: 1,
	createdAt: new Date().toISOString(),
	status: 'FAIL',
	input: options.input,
	engine: { name: 'Babylon.js', version: Engine.Version, backend: 'NullEngine' },
	scope: 'GLB byte inspection, CPU skin loading and sampled skeletal animation evaluation. Materials are skipped during engine import; no GPU texture upload, shader rendering, human visual acceptance, browser or phone performance qualification.',
	expected: { clips: options.expectedClips, heightMeters: options.expectedHeight, maximumInfluences: 4, sampleHz: 30 },
	issues: [],
	warnings: [],
};
let engine, scene, container, pluginObserver;
const issue = (code, message) => report.issues.push({ code, message });
const finite = values => Array.from(values).every(Number.isFinite);
const maximumDifference = (a, b) => {
	let maximum = 0;
	for (let i = 0; i < a.length; i++) maximum = Math.max(maximum, Math.abs(a[i] - b[i]));
	return maximum;
};

function parseGlb(bytes) {
	if (bytes.length < 20 || bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length) throw new Error('Invalid GLB version, magic or byte length.');
	let gltf, binary;
	for (let offset = 12; offset < bytes.length;) {
		if (offset + 8 > bytes.length) throw new Error('Truncated GLB chunk header.');
		const size = bytes.readUInt32LE(offset), type = bytes.readUInt32LE(offset + 4);
		if (offset + 8 + size > bytes.length) throw new Error('Truncated GLB chunk bytes.');
		const chunk = bytes.subarray(offset + 8, offset + 8 + size);
		if (type === 0x4e4f534a) {
			if (gltf) throw new Error('Duplicate JSON chunk.');
			gltf = JSON.parse(chunk.toString('utf8').trim());
		}
		if (type === 0x004e4942) {
			if (binary) throw new Error('Duplicate BIN chunk.');
			binary = chunk;
		}
		offset += 8 + size;
	}
	if (!gltf || gltf.asset?.version !== '2.0') throw new Error('Missing glTF 2.0 JSON.');
	if ((gltf.buffers ?? []).some(buffer => buffer.uri)) throw new Error('External buffers are unsupported by this bounded local validator.');
	return { gltf, binary: binary ?? Buffer.alloc(0) };
}

function imageDimensions(bytes) {
	if (bytes.length >= 24 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20), type: 'PNG' };
	if (bytes.length >= 48 && bytes.subarray(0, 12).equals(Buffer.from([171, 75, 84, 88, 32, 50, 48, 187, 13, 10, 26, 10]))) return { width: bytes.readUInt32LE(20), height: bytes.readUInt32LE(24), type: 'KTX2', vkFormat: bytes.readUInt32LE(12), mipLevels: bytes.readUInt32LE(40), supercompressionScheme: bytes.readUInt32LE(44) };
	if (bytes[0] === 0xff && bytes[1] === 0xd8) {
		for (let position = 2; position + 9 < bytes.length;) {
			if (bytes[position++] !== 0xff) continue;
			while (bytes[position] === 0xff) position++;
			const marker = bytes[position++];
			if (marker === 0xd9 || marker === 0xda) break;
			if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
			const length = bytes.readUInt16BE(position);
			if (length < 2 || position + length > bytes.length) break;
			if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) return { width: bytes.readUInt16BE(position + 5), height: bytes.readUInt16BE(position + 3), type: 'JPEG' };
			position += length;
		}
	}
	return { width: null, height: null, type: 'unrecognized-header' };
}

async function inspectStatic(gltf, binary) {
	const textures = gltf.textures ?? [], images = gltf.images ?? [];
	const materialReferences = (gltf.materials ?? []).map((material, index) => {
		const entry = { index, name: material.name ?? '', alphaMode: material.alphaMode ?? 'OPAQUE', doubleSided: Boolean(material.doubleSided), textureIndices: {} };
		for (const [name, value] of Object.entries({ baseColor: material.pbrMetallicRoughness?.baseColorTexture, metallicRoughness: material.pbrMetallicRoughness?.metallicRoughnessTexture, normal: material.normalTexture, occlusion: material.occlusionTexture, emissive: material.emissiveTexture })) {
			if (value) {
				entry.textureIndices[name] = value.index;
				if (!textures[value.index]) issue('MATERIAL_TEXTURE_MISSING', `Material ${index} ${name} points to absent texture ${value.index}.`);
			}
		}
		return entry;
	});
	for (const [index, texture] of textures.entries()) {
		const imageIndex = texture.extensions?.KHR_texture_basisu?.source ?? texture.source;
		if (imageIndex === undefined || !images[imageIndex]) issue('TEXTURE_IMAGE_MISSING', `Texture ${index} points to absent image ${imageIndex}.`);
	}
	const imageReports = [];
	for (const [index, image] of images.entries()) {
		let bytes, location;
		if (image.bufferView !== undefined) {
			const view = gltf.bufferViews?.[image.bufferView];
			if (!view || (view.buffer ?? 0) !== 0 || (view.byteOffset ?? 0) + view.byteLength > binary.length) {
				issue('IMAGE_BUFFER_MISSING', `Image ${index} has an invalid embedded buffer view.`);
				continue;
			}
			bytes = binary.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
			location = 'embedded';
		} else if (image.uri?.startsWith('data:')) {
			const match = /^data:[^,]*;base64,([a-zA-Z0-9+/=\s]+)$/.exec(image.uri);
			if (!match) { issue('IMAGE_DATA_URI_INVALID', `Image ${index} has an unsupported data URI.`); continue; }
			bytes = Buffer.from(match[1], 'base64');
			location = 'data-uri';
		} else if (typeof image.uri === 'string') {
			if (/^[a-z][a-z0-9+.-]*:/i.test(image.uri) || path.isAbsolute(image.uri)) { issue('IMAGE_REMOTE_NOT_FETCHED', `Image ${index} is not a relative local resource.`); continue; }
			location = path.resolve(path.dirname(options.input), decodeURIComponent(image.uri));
			if (!location.startsWith(path.dirname(options.input) + path.sep)) { issue('IMAGE_PATH_OUTSIDE_PACKAGE', `Image ${index} leaves the input package directory.`); continue; }
			try {
				const imageStat = await fs.stat(location);
				if (!imageStat.isFile() || imageStat.size > MAX_FILE_BYTES) throw new Error('Resource exceeds bounded size.');
				bytes = await fs.readFile(location);
			} catch { issue('IMAGE_LOCAL_MISSING', `Image ${index} local resource is missing or exceeds the bounded size.`); continue; }
		} else { issue('IMAGE_SOURCE_MISSING', `Image ${index} has no source.`); continue; }
		const dimensions = imageDimensions(bytes);
		if (!dimensions.width || !dimensions.height) issue('IMAGE_HEADER_UNKNOWN', `Image ${index} dimensions could not be checked.`);
		imageReports.push({ index, name: image.name ?? '', mimeType: image.mimeType ?? null, location, bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), ...dimensions, decodedRgba8BytesWithoutMipmaps: dimensions.type === 'KTX2' ? null : (dimensions.width && dimensions.height ? dimensions.width * dimensions.height * 4 : null) });
	}
	if (materialReferences.length && !materialReferences.some(material => material.textureIndices.normal !== undefined)) report.warnings.push('No normal texture is present. Base color does not establish a complete PBR texture set.');
	report.static = { nodes: (gltf.nodes ?? []).length, meshes: (gltf.meshes ?? []).length, skins: (gltf.skins ?? []).map(skin => ({ name: skin.name ?? '', joints: skin.joints?.length ?? 0 })), animationNames: (gltf.animations ?? []).map(animation => animation.name ?? ''), extensionsUsed: gltf.extensionsUsed ?? [], materials: materialReferences, images: imageReports };
}

// Expand compressed views in memory only; preserve source file bytes and hash.
async function expandMeshopt(gltf, binary, originalBytes) {
	if (!(gltf.bufferViews ?? []).some(view => view.extensions?.EXT_meshopt_compression)) return originalBytes;
	await MeshoptDecoder.ready;
	const decodedGltf = structuredClone(gltf), parts = [binary];
	let length = binary.length;
	for (const view of decodedGltf.bufferViews ?? []) {
		const compressed = view.extensions?.EXT_meshopt_compression;
		if (!compressed) {
			if ((view.buffer ?? 0) !== 0) throw new Error('Uncompressed view references a non-embedded buffer.');
			continue;
		}
		const sourceOffset = compressed.byteOffset ?? 0, decodedSize = compressed.count * compressed.byteStride;
		if (compressed.buffer !== 0 || !Number.isSafeInteger(sourceOffset) || sourceOffset < 0 || sourceOffset + compressed.byteLength > binary.length) throw new Error('Invalid Meshopt source span.');
		if (!Number.isSafeInteger(decodedSize) || decodedSize < 0 || length + decodedSize > MAX_FILE_BYTES) throw new Error('Decoded Meshopt data exceeds the 256 MiB validation bound.');
		const target = Buffer.alloc(decodedSize);
		MeshoptDecoder.decodeGltfBuffer(target, compressed.count, compressed.byteStride, binary.subarray(sourceOffset, sourceOffset + compressed.byteLength), compressed.mode, compressed.filter ?? 'NONE');
		const padding = (4 - length % 4) % 4;
		if (padding) { parts.push(Buffer.alloc(padding)); length += padding; }
		view.buffer = 0; view.byteOffset = length; view.byteLength = target.length;
		delete view.extensions.EXT_meshopt_compression;
		if (!Object.keys(view.extensions).length) delete view.extensions;
		parts.push(target); length += target.length;
	}
	decodedGltf.buffers = [{ byteLength: length }];
	for (const key of ['extensionsUsed', 'extensionsRequired']) {
		if (decodedGltf[key]) decodedGltf[key] = decodedGltf[key].filter(name => name !== 'EXT_meshopt_compression');
	}
	const jsonBytes = Buffer.from(JSON.stringify(decodedGltf));
	const jsonPadding = (4 - jsonBytes.length % 4) % 4, binPadding = (4 - length % 4) % 4;
	const jsonChunk = Buffer.concat([jsonBytes, Buffer.alloc(jsonPadding, 0x20)]), binChunk = Buffer.concat([...parts, Buffer.alloc(binPadding)]);
	const header = Buffer.alloc(12), jsonHeader = Buffer.alloc(8), binHeader = Buffer.alloc(8);
	header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonChunk.length + binChunk.length, 8);
	jsonHeader.writeUInt32LE(jsonChunk.length); jsonHeader.writeUInt32LE(0x4e4f534a, 4);
	binHeader.writeUInt32LE(binChunk.length); binHeader.writeUInt32LE(0x004e4942, 4);
	report.meshoptDecodedInMemory = true;
	return Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binChunk]);
}

function inspectWeights(mesh) {
	const positions = mesh.getVerticesData(VertexBuffer.PositionKind);
	if (!positions || !finite(positions)) issue('VERTEX_NONFINITE', `${mesh.name} has missing or non-finite vertex positions.`);
	const indices = mesh.getIndices();
	if (!indices || indices.length % 3 || Array.from(indices).some(index => !Number.isInteger(index) || index < 0 || index >= mesh.getTotalVertices())) issue('TRIANGLE_INDICES_INVALID', `${mesh.name} has missing or invalid triangle indices.`);
	const joints = mesh.getVerticesData(VertexBuffer.MatricesIndicesKind), weights = mesh.getVerticesData(VertexBuffer.MatricesWeightsKind);
	const extraWeights = mesh.getVerticesData(VertexBuffer.MatricesWeightsExtraKind);
	if (!joints || !weights || joints.length !== weights.length || weights.length !== mesh.getTotalVertices() * 4) throw new Error(`${mesh.name} has missing or inconsistent four-slot skin data.`);
	if (!finite(weights) || !finite(joints)) throw new Error(`${mesh.name} has non-finite skin data.`);
	if (extraWeights && (extraWeights.length !== weights.length || !finite(extraWeights))) throw new Error(`${mesh.name} has invalid extra skin weights.`);
	const usedJoints = new Set();
	let maximumWeightSumError = 0, maximumInfluences = 0, zeroWeightVertices = 0, negativeWeightInfluences = 0, invalidJointInfluences = 0;
	for (let vertex = 0; vertex < mesh.getTotalVertices(); vertex++) {
		let sum = 0, influences = 0;
		for (let slot = 0; slot < 4; slot++) {
			const weight = weights[vertex * 4 + slot], joint = joints[vertex * 4 + slot];
			if (weight < -1e-6) negativeWeightInfluences++;
			if (weight > 1e-6) {
				influences++; usedJoints.add(joint);
				if (!Number.isInteger(joint) || joint < 0 || joint >= mesh.skeleton.bones.length) invalidJointInfluences++;
			}
			sum += weight;
		}
		if (extraWeights) for (let slot = 0; slot < 4; slot++) { const weight = extraWeights[vertex * 4 + slot]; sum += weight; if (weight > 1e-6) influences++; if (weight < -1e-6) negativeWeightInfluences++; }
		if (sum < 1e-6) zeroWeightVertices++;
		maximumWeightSumError = Math.max(maximumWeightSumError, Math.abs(1 - sum));
		maximumInfluences = Math.max(maximumInfluences, influences);
	}
	if (maximumInfluences > 4) issue('TOO_MANY_INFLUENCES', `${mesh.name} uses ${maximumInfluences} influences; maximum is 4.`);
	if (maximumWeightSumError > 0.002 || zeroWeightVertices || negativeWeightInfluences || invalidJointInfluences) issue('INVALID_SKIN_WEIGHTS', `${mesh.name} has invalid or unnormalized skin weights.`);
	return { mesh: mesh.name, vertices: mesh.getTotalVertices(), triangles: mesh.getTotalIndices() / 3, boneCount: mesh.skeleton.bones.length, usedJoints: [...usedJoints].sort((a, b) => a - b), maximumInfluences, maximumWeightSumError, zeroWeightVertices, negativeWeightInfluences, invalidJointInfluences };
}

try {
	const stat = await fs.stat(options.input);
	if (!stat.isFile() || stat.size > MAX_FILE_BYTES) throw new Error('Input must be a regular GLB file no larger than 256 MiB.');
	const bytes = await fs.readFile(options.input);
	report.bytes = bytes.length;
	report.sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
	const { gltf, binary } = parseGlb(bytes);
	await inspectStatic(gltf, binary);
	if (!(gltf.skins?.length > 0)) throw new Error('GLB contains no skin.');
	if (!(gltf.animations?.length > 0)) throw new Error('GLB contains no animations.');
	engine = new NullEngine({ renderWidth: 640, renderHeight: 480, textureSize: 512 });
	scene = new Scene(engine);
	pluginObserver = SceneLoader.OnPluginActivatedObservable.add(loader => {
		if (loader.name === 'gltf') { loader.skipMaterials = true; loader.animationStartMode = 0; }
	});
	const importBytes = await expandMeshopt(gltf, binary, bytes);
	container = await LoadAssetContainerAsync(new Uint8Array(importBytes), scene, { pluginExtension: '.glb', name: path.basename(options.input) });
	container.addAllToScene();
	const meshes = container.meshes.filter(mesh => mesh.skeleton && mesh.getTotalVertices() > 0);
	if (!meshes.length || !container.skeletons.length) throw new Error('Babylon import contains no skinned mesh or skeleton.');
	const weights = meshes.map(inspectWeights);
	// Capture authored rest geometry before any animation changes object transforms.
	const minimum = [Infinity, Infinity, Infinity], maximum = [-Infinity, -Infinity, -Infinity];
	for (const mesh of meshes) {
		mesh.computeWorldMatrix(true);
		const bounds = mesh.getBoundingInfo().boundingBox;
		for (const [axis, component] of ['x', 'y', 'z'].entries()) { minimum[axis] = Math.min(minimum[axis], bounds.minimumWorld[component]); maximum[axis] = Math.max(maximum[axis], bounds.maximumWorld[component]); }
	}
	const heightMeters = maximum[1] - minimum[1];
	if (options.expectedHeight !== null && Math.abs(heightMeters - options.expectedHeight) > 0.15) issue('HEIGHT_MISMATCH', `Rest-pose bounding height ${heightMeters.toFixed(3)} m differs from expected ${options.expectedHeight} m.`);
	const actualNames = container.animationGroups.map(group => group.name);
	if (new Set(actualNames).size !== actualNames.length) issue('DUPLICATE_CLIP', 'Animation group names are not unique.');
	if (JSON.stringify([...actualNames].sort()) !== JSON.stringify([...options.expectedClips].sort())) issue('CLIP_SET_MISMATCH', `Expected ${options.expectedClips.join(', ')}; imported ${actualNames.join(', ')}.`);
	const clips = [];
	for (const group of container.animationGroups) {
		container.animationGroups.forEach(other => other.stop());
		const fpsValues = [...new Set(group.targetedAnimations.map(target => target.animation.framePerSecond))];
		if (fpsValues.length !== 1 || !(fpsValues[0] > 0)) throw new Error(`${group.name} has inconsistent animation frame rates.`);
		const durationSeconds = (group.to - group.from) / fpsValues[0];
		if (!(durationSeconds > 0) || !Number.isFinite(durationSeconds)) throw new Error(`${group.name} has invalid duration.`);
		const sampleCount = Math.ceil(durationSeconds * 30) + 1;
		if (sampleCount > MAX_SAMPLES_PER_CLIP) throw new Error(`${group.name} exceeds the 60-second bounded validation duration.`);
		group.start(false, 1, group.from, group.to, false);
		const reference = new Map();
		let maximumWeightedBoneMatrixChange = 0, maximumEndpointWeightedBoneMatrixDifference = 0;
		for (let sample = 0; sample < sampleCount; sample++) {
			const frame = group.from + (group.to - group.from) * sample / (sampleCount - 1);
			group.goToFrame(frame);
			scene.transformNodes.forEach(node => node.computeWorldMatrix(true));
			container.skeletons.forEach(skeleton => skeleton.prepare(true));
			for (const [index, mesh] of meshes.entries()) {
				mesh.computeWorldMatrix(true);
				const matrices = mesh.skeleton.getTransformMatrices(mesh);
				if (!finite(matrices)) throw new Error(`${group.name} has non-finite skin matrices at sample ${sample}.`);
				const weighted = weights[index].usedJoints.flatMap(joint => Array.from(matrices.subarray(joint * 16, joint * 16 + 16)));
				if (sample === 0) reference.set(mesh, weighted);
				const delta = maximumDifference(reference.get(mesh), weighted);
				maximumWeightedBoneMatrixChange = Math.max(maximumWeightedBoneMatrixChange, delta);
				if (sample === sampleCount - 1) maximumEndpointWeightedBoneMatrixDifference = Math.max(maximumEndpointWeightedBoneMatrixDifference, delta);
			}
		}
		if (maximumWeightedBoneMatrixChange < 1e-5) issue('STATIC_CLIP', `${group.name} does not move any weighted skin matrix.`);
		if (['Idle', 'Walk', 'Run'].includes(group.name) && maximumEndpointWeightedBoneMatrixDifference > 0.003) issue('LOOP_ENDPOINT_DISCONTINUITY', `${group.name} start/end weighted matrices differ by ${maximumEndpointWeightedBoneMatrixDifference}; intended movement loops must close.`);
		clips.push({ name: group.name, from: group.from, to: group.to, engineFramesPerSecond: fpsValues[0], durationSeconds, sampledFrames: sampleCount, finite: true, maximumWeightedBoneMatrixChange, maximumEndpointWeightedBoneMatrixDifference });
		group.stop();
	}
	report.runtime = { skinnedMeshCount: meshes.length, skeletonCount: container.skeletons.length, animationGroupCount: clips.length, importedTransformNodes: container.transformNodes.length, weights, restGeometryWorldBounds: { minimum, maximum, heightMeters }, clips, totalSampledFrames: clips.reduce((sum, clip) => sum + clip.sampledFrames, 0) };
	report.status = report.issues.length ? 'FAIL' : 'PASS';
} catch (error) {
	issue('VALIDATION_EXCEPTION', error?.message ?? String(error));
} finally {
	if (pluginObserver) SceneLoader.OnPluginActivatedObservable.remove(pluginObserver);
	container?.dispose();
	scene?.dispose();
	engine?.dispose();
}
await fs.mkdir(path.dirname(options.out), { recursive: true });
await fs.writeFile(options.out, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: report.status, file: path.basename(options.input), sha256: report.sha256, bones: report.runtime?.weights.map(weight => weight.boneCount), clips: report.runtime?.animationGroupCount, sampledFrames: report.runtime?.totalSampledFrames, issues: report.issues, report: options.out }));
if (report.status !== 'PASS') process.exitCode = 1;
