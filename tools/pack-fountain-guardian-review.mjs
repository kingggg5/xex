/** Pack only the unpromoted fountain-guardian city candidate, preserving art. */
import fs from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'apps/client/package.json'));
const { NodeIO } = require('@gltf-transform/core');
const { ALL_EXTENSIONS, KHRTextureBasisu, EXTMeshoptCompression } = require('@gltf-transform/extensions');
const { getBounds } = require('@gltf-transform/functions');
const { MeshoptDecoder, MeshoptEncoder } = require('meshoptimizer');
const options = parseArguments(process.argv.slice(2));
const directory = path.join(root, 'assets/models/reference-city/r5', options.candidate);
const input = path.join(directory, 'city-runtime.glb');
const donor = path.join(root, 'assets/models/reference-city/r5/market-repair-candidate/city-runtime.meshopt.glb');
const output = path.join(directory, 'city-runtime.meshopt.glb');
const receiptFile = path.join(directory, 'runtime-pack-receipt.json');
const EXPECTED_INPUT = options.expectedInput;
const EXPECTED_DONOR = '95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const relative = file => path.relative(root, file).replaceAll('\\', '/');
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (left, right, label) => { if (JSON.stringify(canonical(left)) !== JSON.stringify(canonical(right))) throw new Error(`${label} changed.`); };

function parseArguments(argv) {
	let candidate = 'fountain-guardian-review-candidate', expectedInput = null;
	const args = [...argv];
	while (args.length) {
		const flag = args.shift();
		if (flag === '--candidate') candidate = args.shift() ?? '';
		else if (flag === '--expected-input-sha256') expectedInput = args.shift() ?? '';
		else throw new Error(`Unknown packing option: ${flag}`);
	}
	if (!/^fountain-guardian-review-(?:v[1-9][0-9]*-)?candidate$/.test(candidate)) throw new Error('Candidate must be a named, versioned guardian review folder.');
	if (expectedInput === null && candidate === 'fountain-guardian-review-candidate') expectedInput = 'c07e5cfbddac3ac19ef81fddb906fd3058a722a918c47346dc03b7840406b2db';
	if (typeof expectedInput !== 'string' || !/^[a-f0-9]{64}$/.test(expectedInput)) throw new Error('Provide the exact pinned --expected-input-sha256 for this candidate.');
	return { candidate, expectedInput };
}

function glbJson(bytes) {
	if (bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length || bytes.readUInt32LE(16) !== 0x4e4f534a) throw new Error('Invalid GLB header.');
	return JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString('utf8').trim());
}

function imageBindings(json, includeMaterialIndices = true) {
	const bindings = Array.from({ length: json.images.length }, () => []);
	json.materials.forEach((material, materialIndex) => {
		function visit(value, parts) {
			if (!value || typeof value !== 'object') return;
			if (Number.isInteger(value.index) && parts.at(-1)?.toLowerCase().endsWith('texture')) {
				const texture = json.textures[value.index];
				const imageIndex = texture?.extensions?.KHR_texture_basisu?.source ?? texture?.source;
				if (!Number.isInteger(imageIndex) || !bindings[imageIndex]) throw new Error('Material texture info references an invalid image.');
				bindings[imageIndex].push(`${includeMaterialIndices ? `${materialIndex}:` : ''}${material.name ?? ''}:${parts.join('.')}:TEXCOORD_${value.texCoord ?? 0}`);
			}
			for (const [key, child] of Object.entries(value)) if (child && typeof child === 'object') visit(child, [...parts, key]);
		}
		visit(material, []);
	});
	return bindings.map(list => list.sort());
}

function resolvedMaterialJSON(json) {
	function resolve(value, parts) {
		if (Array.isArray(value)) return value.map((child, index) => resolve(child, [...parts, String(index)]));
		if (!value || typeof value !== 'object') return value;
		const result = Object.fromEntries(Object.entries(value).map(([key, child]) => [key, resolve(child, [...parts, key])]));
		if (Number.isInteger(value.index) && parts.at(-1)?.toLowerCase().endsWith('texture')) {
			const texture = json.textures[value.index];
			const imageIndex = texture?.extensions?.KHR_texture_basisu?.source ?? texture?.source;
			if (!texture || !json.images[imageIndex]) throw new Error('Invalid material texture reference.');
			// NodeIO legally reorders texture descriptors while retaining bindings.
			// Compare the referenced image and sampler, never numeric table indices.
			delete result.index;
			result.resolvedImage = json.images[imageIndex].name || `image-index-${imageIndex}`;
			result.resolvedSampler = texture.sampler === undefined ? null : { wrapS: 10497, wrapT: 10497, ...json.samplers[texture.sampler] };
		}
		return result;
	}
	return json.materials.map(material => resolve(material, []));
}

function typedDigest(accessor) {
	const array = accessor.getArray();
	if (!array) throw new Error('Accessor has no CPU data.');
	return { count: accessor.getCount(), type: accessor.getType(), componentType: accessor.getComponentType(), normalized: accessor.getNormalized(), sha256: hash(new Uint8Array(array.buffer, array.byteOffset, array.byteLength)) };
}

function cyclicTriangleDigest(accessor) {
	const array = accessor.getArray();
	if (!array || array.length % 3) throw new Error('Invalid indexed triangle list.');
	const canonicalIndices = new Uint32Array(array.length);
	for (let i = 0; i < array.length; i += 3) {
		const a = array[i], b = array[i + 1], c = array[i + 2];
		const rotation = a <= b && a <= c ? 0 : b <= a && b <= c ? 1 : 2;
		canonicalIndices[i] = array[i + rotation];
		canonicalIndices[i + 1] = array[i + (rotation + 1) % 3];
		canonicalIndices[i + 2] = array[i + (rotation + 2) % 3];
	}
	return hash(new Uint8Array(canonicalIndices.buffer));
}

function documentGeometry(document) {
	const meshRows = [];
	let triangles = 0;
	const materials = document.getRoot().listMaterials();
	for (const mesh of document.getRoot().listMeshes()) {
		const primitives = mesh.listPrimitives().map(primitive => {
			if (primitive.getMode() !== 4 || !primitive.getIndices()) throw new Error('Expected indexed triangle primitives.');
			const indices = primitive.getIndices(); triangles += indices.getCount() / 3;
			return {
				materialIndex: materials.indexOf(primitive.getMaterial()), materialName: primitive.getMaterial()?.getName() ?? null,
				mode: primitive.getMode(), indices: typedDigest(indices), triangleCyclicDigest: cyclicTriangleDigest(indices),
				attributes: Object.fromEntries(primitive.listSemantics().sort().map(semantic => [semantic, typedDigest(primitive.getAttribute(semantic))])),
			};
		});
		meshRows.push({ name: mesh.getName(), primitives });
	}
	return { triangles, meshRows, sceneBounds: document.getRoot().listScenes().map(scene => ({ name: scene.getName(), ...getBounds(scene) })) };
}

function materialValues(document) {
	return document.getRoot().listMaterials().map(material => ({
		name: material.getName(), baseColorFactor: material.getBaseColorFactor(), emissiveFactor: material.getEmissiveFactor(),
		metallicFactor: material.getMetallicFactor(), roughnessFactor: material.getRoughnessFactor(), normalScale: material.getNormalScale(),
		occlusionStrength: material.getOcclusionStrength(), alphaMode: material.getAlphaMode(), alphaCutoff: material.getAlphaCutoff(),
		doubleSided: material.getDoubleSided(), extras: material.getExtras(),
	}));
}

async function ensureNew(file) {
	try { await fs.access(file); throw new Error(`Preserving existing output: ${relative(file)}`); }
	catch (error) { if (error.code !== 'ENOENT') throw error; }
}

async function main() {
	await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
	await Promise.all([ensureNew(output), ensureNew(receiptFile)]);
	const realDirectory = await fs.realpath(directory);
	if (realDirectory !== path.resolve(directory) || !realDirectory.startsWith(await fs.realpath(root) + path.sep)) throw new Error('Candidate output resolves outside its owned folder.');
	const inputBytes = await fs.readFile(input), donorBytes = await fs.readFile(donor);
	if (hash(inputBytes) !== EXPECTED_INPUT || hash(donorBytes) !== EXPECTED_DONOR) throw new Error('Pinned candidate or active texture donor changed.');
	const inputJSON = glbJson(inputBytes), donorJSON = glbJson(donorBytes);
	const statsFile = path.join(directory, 'city-runtime.stats.json');
	const statsBytes = await fs.readFile(statsFile), expected = JSON.parse(statsBytes).candidate;
	if (expected.sha256 !== EXPECTED_INPUT || expected.bytes !== inputBytes.length) throw new Error('Versioned runtime manifest does not match the pinned input.');
	if (inputJSON.meshes.length !== expected.mesh_primitives || inputJSON.nodes.length !== expected.nodes || inputJSON.nodes.filter(node => node.name?.startsWith('City / ')).length !== expected.static_material_groups) throw new Error('Input mesh/node/static-group counts differ from its runtime manifest.');
	const materialNames = inputJSON.materials.map(material => material.name), donorNames = donorJSON.materials.map(material => material.name);
	if (materialNames.some(name => !name || !donorNames.includes(name)) || new Set(materialNames).size !== materialNames.length || new Set(donorNames).size !== donorNames.length) throw new Error('Candidate materials have ambiguous or unknown donor names.');
	if (inputJSON.images.length !== 54 || donorJSON.images.length !== 54) throw new Error('Expected exactly54 existing images.');
	const inputBindings = imageBindings(inputJSON), donorBindings = imageBindings(donorJSON);
	const donorAssociationBindings = imageBindings(donorJSON, false), inputAssociationBindings = imageBindings(inputJSON, false);
	const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder });
	const document = await io.read(input), baseline = await io.read(donor);
	const geometryBefore = documentGeometry(document), materialsBefore = materialValues(document);
	if (geometryBefore.triangles !== expected.glb_accessor_triangles) throw new Error('Candidate triangle count differs from its manifest.');
	const rootBefore = document.getRoot();
	const hooksBefore = rootBefore.listNodes().filter(node => /^(?:fx_|emit_|anim_|light_)/.test(node.getName())).map(node => node.getName()).sort();
	if (hooksBefore.length !== 34 || hooksBefore.length !== expected.runtime_hooks) throw new Error('Expected 34 stable runtime hook nodes.');
	const donorTextures = baseline.getRoot().listTextures(), textures = rootBefore.listTextures();
	if (textures.length !== 54 || donorTextures.length !== 54) throw new Error('NodeIO image count changed.');
	const donorByName = new Map();
	donorTextures.forEach((texture, index) => {
		if (texture.getMimeType() !== 'image/ktx2' || !texture.getImage()) throw new Error('Donor must contain exact KTX2 bytes.');
		const name = texture.getName();
		if (name && donorByName.has(name)) throw new Error(`Ambiguous donor texture name: ${name}`);
		if (name) donorByName.set(name, { texture, index });
	});
	const usedDonors = new Set(), textureRecords = [];
	for (let index = 0; index < textures.length; index++) {
		const texture = textures[index], name = texture.getName();
		let match = name ? donorByName.get(name) : null;
		if (!name) {
			const matches = donorTextures.map((candidate, candidateIndex) => ({ texture: candidate, index: candidateIndex })).filter(candidate => JSON.stringify(inputAssociationBindings[index]) === JSON.stringify(donorAssociationBindings[candidate.index]) && inputAssociationBindings[index].length > 0);
			if (matches.length !== 1) throw new Error('Unnamed texture has ambiguous material-slot association.');
			match = matches[0];
		}
		if (!match || usedDonors.has(match.index)) throw new Error(`Missing or reused donor association: ${name}`);
		usedDonors.add(match.index);
		same(inputAssociationBindings[index], donorAssociationBindings[match.index], `Texture material-name/slot binding ${name}`);
		same(texture.getSize(), match.texture.getSize(), `Texture dimensions ${name}`);
		const image = match.texture.getImage();
		textureRecords.push({ name, donorName: match.texture.getName(), donorIndex: match.index, sourceImageIndex: index, materialSlots: inputBindings[index], donorMaterialSlots: donorBindings[match.index], associationMaterialNameSlots: inputAssociationBindings[index], dimensions: match.texture.getSize(), sourceImageSha256: hash(texture.getImage()), reusedKtx2Sha256: hash(image), bytes: image.byteLength });
		texture.setMimeType('image/ktx2').setImage(image).setURI(match.texture.getURI());
	}
	if (usedDonors.size !== 54) throw new Error('Not every pinned KTX2 image was reused exactly once.');
	document.createExtension(KHRTextureBasisu).setRequired(true);
	// Direct writer byte compression, without the lossy meshopt() convenience
	// transform's reorder/quantize preprocessing. QUANTIZE here selects NONE
	// filters; raw Float32 accessors are left intact by installed 4.5.0 writer.
	document.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.QUANTIZE });
	const packed = await io.writeBinary(document);
	const pending = path.join(directory, `.city-runtime.meshopt-${randomUUID()}.pending.glb`);
	await fs.writeFile(pending, packed, { flag: 'wx' });
	try {
		const readback = await io.read(pending), packedJSON = glbJson(await fs.readFile(pending));
		const geometryAfter = documentGeometry(readback), materialsAfter = materialValues(readback);
		same(materialsBefore, materialsAfter, 'PBR material values');
		same(inputJSON.nodes, packedJSON.nodes, 'Exact node transforms/hierarchy/names');
		same(inputJSON.scenes, packedJSON.scenes, 'Scene roots');
		same(resolvedMaterialJSON(inputJSON), resolvedMaterialJSON(packedJSON), 'Material values and exact referenced image/sampler/UV/extension bindings');
		same(geometryBefore.sceneBounds, geometryAfter.sceneBounds, 'Exact scene bounds');
		if (geometryAfter.triangles !== expected.glb_accessor_triangles || geometryAfter.meshRows.length !== inputJSON.meshes.length) throw new Error('Packed triangle/mesh totals changed.');
		let cyclicRotatedIndexPrimitives = 0;
		geometryBefore.meshRows.forEach((mesh, meshIndex) => {
			const after = geometryAfter.meshRows[meshIndex];
			if (mesh.name !== after.name || mesh.primitives.length !== after.primitives.length) throw new Error('Mesh/primitive identity changed.');
			mesh.primitives.forEach((primitive, primitiveIndex) => {
				const packedPrimitive = after.primitives[primitiveIndex];
				same(primitive.attributes, packedPrimitive.attributes, `Exact vertex/UV attributes ${mesh.name}/${primitiveIndex}`);
				if (primitive.materialIndex !== packedPrimitive.materialIndex || primitive.materialName !== packedPrimitive.materialName || primitive.mode !== packedPrimitive.mode || primitive.triangleCyclicDigest !== packedPrimitive.triangleCyclicDigest || primitive.indices.count !== packedPrimitive.indices.count) throw new Error('Primitive material/winding/triangle sequence changed.');
				if (primitive.indices.sha256 !== packedPrimitive.indices.sha256) cyclicRotatedIndexPrimitives++;
			});
		});
		const readbackTextures = readback.getRoot().listTextures();
		if (readbackTextures.length !== 54 || packedJSON.images.length !== 54 || packedJSON.materials.length !== inputJSON.materials.length) throw new Error('Packed image/material totals changed.');
		readbackTextures.forEach((texture, index) => {
			if (texture.getName() !== textureRecords[index].name || texture.getMimeType() !== 'image/ktx2' || hash(texture.getImage()) !== textureRecords[index].reusedKtx2Sha256) throw new Error('Packed KTX2 image bytes/name changed.');
			same(imageBindings(packedJSON)[index], textureRecords[index].materialSlots, 'Packed texture slot bindings');
		});
		const hooksAfter = readback.getRoot().listNodes().filter(node => /^(?:fx_|emit_|anim_|light_)/.test(node.getName())).map(node => node.getName()).sort();
		same(hooksBefore, hooksAfter, 'Runtime hook names/count');
		if (!packedJSON.extensionsRequired?.includes('EXT_meshopt_compression') || !packedJSON.extensionsRequired?.includes('KHR_texture_basisu')) throw new Error('Required native compression extensions missing.');
		if ((packedJSON.bufferViews ?? []).some(view => view.extensions?.EXT_meshopt_compression?.filter && view.extensions.EXT_meshopt_compression.filter !== 'NONE')) throw new Error('Unexpected lossy Meshopt filter.');
		if (hash(await fs.readFile(input)) !== EXPECTED_INPUT || hash(await fs.readFile(donor)) !== EXPECTED_DONOR || hash(await fs.readFile(statsFile)) !== hash(statsBytes)) throw new Error('An immutable source/manifest changed during packing.');
		await fs.copyFile(pending, output, fsConstants.COPYFILE_EXCL);
		const written = await fs.readFile(output);
		if (hash(written) !== hash(packed)) throw new Error('Final output differs from validated disk readback.');
		const finalReadback = await io.read(output);
		const finalGeometry = documentGeometry(finalReadback);
		same(finalGeometry, geometryAfter, 'Final-path native geometry reread');
		finalReadback.getRoot().listTextures().forEach((texture, index) => { if (hash(texture.getImage()) !== textureRecords[index].reusedKtx2Sha256) throw new Error('Final-path KTX2 image reread differs.'); });
		const receipt = {
			schema: 'xexoria.fountain-guardian-runtime-pack/1', status: 'PASS_STRUCTURAL_DEV_REVIEW_ONLY', created_utc: new Date().toISOString(),
			input: { path: relative(input), sha256: EXPECTED_INPUT, bytes: inputBytes.length }, donor: { path: relative(donor), sha256: EXPECTED_DONOR, bytes: donorBytes.length },
			input_manifest: { path: relative(statsFile), sha256: hash(statsBytes), expected_runtime: expected },
			output: { path: relative(output), sha256: hash(written), bytes: written.length, triangles: geometryAfter.triangles, meshes: packedJSON.meshes.length, nodes: packedJSON.nodes.length, static_material_groups: expected.static_material_groups, materials: packedJSON.materials.length, images: 54, runtime_hooks: 34, extensionsUsed: packedJSON.extensionsUsed, extensionsRequired: packedJSON.extensionsRequired },
			texture_records: textureRecords, geometry_before: geometryBefore, geometry_after: geometryAfter,
			verification: { image_bytes_exact: true, image_slot_bindings_exact: true, all_vertex_attributes_including_uv_bytes_exact: true, node_transforms_and_hierarchy_exact: true, material_values_and_slots_exact: true, material_comparison: 'Exact material JSON after resolving numeric texture-table indices to unchanged image names and sampler values; implicit glTF REPEAT wraps normalize to 10497. NodeIO legally reorders texture descriptors and writes explicit default wraps.', bounds_exact: true, triangle_sequence_and_winding_preserved: true, cyclic_rotated_index_primitives: cyclicRotatedIndexPrimitives, runtime_hooks_exact: true, source_and_donor_and_manifest_unchanged: true, final_output_matches_validated_disk_readback: true, final_path_native_nodeio_reread: true },
			production_gate: { status: geometryAfter.triangles > 900000 ? 'FAIL' : 'PASS_TRIANGLE_COUNT_ONLY', maximum_triangles: 900000, measured_triangles: geometryAfter.triangles, over_budget_triangles: Math.max(0, geometryAfter.triangles - 900000), promoted: false },
			recipe: 'Direct glTF Transform 4.5.0 EXTMeshoptCompression writer with Meshopt NONE filters; no reorder(), quantize(), meshopt(), UV, material, geometry or texture-transform pass. Reuse all 54 pinned active KTX2 byte arrays by exact name plus material slot/dimensions, with unique binding fallback only for unnamed images.',
			limitations: ['DEV review candidate only. Not admitted or copied into any active/live/snapshot asset.', 'CPU structural readback proves no GPU pixels, native visual acceptance, mobile frame time or release capacity.', 'Required Meshopt/Basis runtime decoders remain the existing engine responsibility.', 'Packaging never waives the 900000-triangle production gate or any other release gate.'],
		};
		await fs.writeFile(receiptFile, JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
		console.log(JSON.stringify({ status: receipt.status, output: receipt.output, texture_bytes_exact: true, uv_bytes_exact: true, cyclic_rotated_index_primitives: cyclicRotatedIndexPrimitives, production_gate: receipt.production_gate, receipt: relative(receiptFile) }));
	} finally { await fs.unlink(pending); }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
