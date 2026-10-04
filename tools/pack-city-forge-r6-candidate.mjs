/** Texture-only candidate: encode selected forge maps, preserve geometry bytes. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'apps/client/package.json'));
const { Document, NodeIO } = require('@gltf-transform/core');
const { ALL_EXTENSIONS } = require('@gltf-transform/extensions');
const { MeshoptDecoder } = require('meshoptimizer');
const source = path.join(root, 'assets/models/reference-city/r5/market-repair-candidate/city-runtime.meshopt.glb');
const forge = path.join(root, 'assets/models/reference-city/r5/textures-forge-r6');
const directory = path.join(root, 'assets/models/reference-city/r5/forge-r6-texture-review-candidate');
const output = path.join(directory, 'city-runtime.meshopt.glb');
const cli = path.join(root, 'apps/client/node_modules/@gltf-transform/cli/bin/cli.js');
const ktxBin = path.join(root, '.harness/.cache/toolchains/ktx-4.4.2/portable/bin');
const SOURCE_SHA = '95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72';
const MATERIALS = ['roof_slate_blue', 'roof_slate_navy', 'roof_shingle_green', 'roof_tile_red', 'stone_wall_warm', 'stone_foundation', 'stone_trim_carved', 'stone_accent_bluegrey', 'plaza_flagstone', 'paver_surface', 'cobble_path', 'timber_dark', 'plaster_cream', 'grass_ground'];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const relative = file => path.relative(root, file).replaceAll('\\', '/');
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const equal = (a, b, label) => { if (JSON.stringify(canonical(a)) !== JSON.stringify(canonical(b))) throw new Error(`${label} changed.`); };
const align4 = length => (length + 3) & ~3;

function parseGlb(bytes) {
	if (bytes.toString('ascii', 0, 4) !== 'glTF' || bytes.readUInt32LE(4) !== 2 || bytes.readUInt32LE(8) !== bytes.length || bytes.readUInt32LE(16) !== 0x4e4f534a) throw new Error('Invalid GLB header.');
	const jsonLength = bytes.readUInt32LE(12), binHeader = 20 + jsonLength;
	if (bytes.readUInt32LE(binHeader + 4) !== 0x004e4942) throw new Error('Expected one GLB binary chunk.');
	const binLength = bytes.readUInt32LE(binHeader);
	if (binHeader + 8 + binLength !== bytes.length) throw new Error('Unexpected GLB chunk layout.');
	return { json: JSON.parse(bytes.subarray(20, binHeader).toString('utf8').trim()), bin: bytes.subarray(binHeader + 8) };
}

function writeGlb(json, bin) {
	const text = Buffer.from(JSON.stringify(json)), paddedText = Buffer.alloc(align4(text.length), 0x20); text.copy(paddedText);
	const paddedBin = Buffer.alloc(align4(bin.length)); bin.copy(paddedBin);
	const bytes = Buffer.alloc(12 + 8 + paddedText.length + 8 + paddedBin.length);
	bytes.write('glTF', 0, 'ascii'); bytes.writeUInt32LE(2, 4); bytes.writeUInt32LE(bytes.length, 8);
	bytes.writeUInt32LE(paddedText.length, 12); bytes.writeUInt32LE(0x4e4f534a, 16); paddedText.copy(bytes, 20);
	const at = 20 + paddedText.length; bytes.writeUInt32LE(paddedBin.length, at); bytes.writeUInt32LE(0x004e4942, at + 4); paddedBin.copy(bytes, at + 8);
	return bytes;
}

function imageBytes(glb, index) {
	const image = glb.json.images[index], view = glb.json.bufferViews[image.bufferView];
	if (image.mimeType !== 'image/ktx2' || view.buffer !== 0) throw new Error('Expected embedded KTX2 image on physical buffer0.');
	return glb.bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
}

function imageIndex(json, info) {
	if (!info || !Number.isInteger(info.index)) throw new Error('Required material texture slot missing.');
	const texture = json.textures[info.index], index = texture.extensions?.KHR_texture_basisu?.source ?? texture.source;
	if (!Number.isInteger(index) || !json.images[index]) throw new Error('Invalid material texture image reference.');
	return index;
}

function ktxInfo(bytes, role) {
	if (!bytes.subarray(0, 12).equals(Buffer.from([0xab,0x4b,0x54,0x58,0x20,0x32,0x30,0xbb,0x0d,0x0a,0x1a,0x0a]))) throw new Error('Invalid KTX2 signature.');
	const dfd = bytes.readUInt32LE(48);
	const info = { width: bytes.readUInt32LE(20), height: bytes.readUInt32LE(24), levels: bytes.readUInt32LE(40), colorModel: bytes[dfd + 12], transfer: bytes[dfd + 14], supercompression: bytes.readUInt32LE(44) };
	if (info.width !== 1024 || info.height !== 1024 || info.levels !== 11 || info.transfer !== (role === 'albedo' ? 2 : 1)) throw new Error(`KTX2 dimensions/mips/transfer contract failed for ${role}.`);
	if (info.colorModel !== (role === 'albedo' ? 163 : 166)) throw new Error(`Unexpected Basis codec for ${role}.`);
	return info;
}

async function runEncoder(label, args) {
	const log = path.join(directory, `${label}.log`);
	const handle = await fs.open(log, 'wx');
	const env = { ...process.env, PATH: [ktxBin, process.env.PATH ?? ''].join(path.delimiter) };
	console.log(JSON.stringify({ phase: label, status: 'ENCODING', jobs: 2 }));
	await new Promise((resolve, reject) => {
		const child = spawn(process.execPath, [cli, ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
		let tail = '';
		const record = chunk => { const text = String(chunk); tail = (tail + text).slice(-4000); void handle.write(text); };
		child.stdout.on('data', record); child.stderr.on('data', record);
		child.once('error', reject);
		child.once('close', code => code === 0 ? resolve() : reject(new Error(`${label} encoder failed (${code}): ${tail}`)));
	}).finally(() => handle.close());
	console.log(JSON.stringify({ phase: label, status: 'COMPLETE' }));
}

function accessorRoster(document) {
	return document.getRoot().listAccessors().map(accessor => {
		const data = accessor.getArray();
		return { name: accessor.getName(), count: accessor.getCount(), type: accessor.getType(), componentType: accessor.getComponentType(), normalized: accessor.getNormalized(), sha256: hash(new Uint8Array(data.buffer, data.byteOffset, data.byteLength)) };
	});
}

async function main() {
	try { if ((await fs.readdir(directory)).length) throw new Error('Preserve the existing candidate folder; choose a separately authorized new revision.'); }
	catch (error) { if (error.code !== 'ENOENT') throw error; }
	const realParent = await fs.realpath(path.dirname(directory));
	if (!realParent.startsWith(await fs.realpath(root) + path.sep)) throw new Error('Candidate parent resolves outside the project.');
	const sourceBytes = await fs.readFile(source), manifestBytes = await fs.readFile(path.join(forge, 'forge-manifest.json'));
	if (hash(sourceBytes) !== SOURCE_SHA) throw new Error('Pinned active texture source changed.');
	const manifest = JSON.parse(manifestBytes), sourceGlb = parseGlb(sourceBytes), original = sourceGlb.json;
	if (manifest.contract !== '<name>_albedo.png sRGB, <name>_normal.png OpenGL +Y, <name>_orm.png AO/roughness/metal') throw new Error('Forge color/normal/ORM contract is ambiguous.');
	if (original.images.length !== 54 || original.bufferViews.filter(view => !view.extensions?.EXT_meshopt_compression).length !== 54 || original.buffers.length !== 2) throw new Error('Unexpected physical image/geometry layout.');
	const imageViews = new Set(original.images.map(image => image.bufferView));
	if (imageViews.size !== 54 || [...imageViews].some(index => index < 0 || index >= 54)) throw new Error('Image view prefix is not the verified unique54 layout.');
	const meshoptViews = original.bufferViews.filter(view => view.extensions?.EXT_meshopt_compression);
	const geometryStart = Math.min(...meshoptViews.map(view => view.extensions.EXT_meshopt_compression.byteOffset));
	if (meshoptViews.some(view => view.buffer !== 1 || view.extensions.EXT_meshopt_compression.buffer !== 0 || view.extensions.EXT_meshopt_compression.byteOffset + view.extensions.EXT_meshopt_compression.byteLength > sourceGlb.bin.length)) throw new Error('Unexpected Meshopt buffer/reference layout.');
	if (original.images.some(image => { const view = original.bufferViews[image.bufferView]; return view.buffer !== 0 || (view.byteOffset ?? 0) + view.byteLength > geometryStart; })) throw new Error('Image data overlaps the immutable geometry tail.');
	const materialByName = new Map(original.materials.map(material => [material.name, material]));
	if (materialByName.size !== original.materials.length) throw new Error('Material names are ambiguous.');
	const owners = Array.from({ length: 54 }, () => new Set());
	for (const material of original.materials) {
		function visit(value, key) {
			if (!value || typeof value !== 'object') return;
			if (Number.isInteger(value.index) && key.toLowerCase().endsWith('texture')) owners[imageIndex(original, value)].add(material.name);
			for (const [childKey, child] of Object.entries(value)) if (child && typeof child === 'object') visit(child, childKey);
		}
		visit(material, '');
	}
	const pngInputs = [], replacements = new Map();
	for (const name of MATERIALS) {
		const material = materialByName.get(name), forgeRows = manifest.materials.filter(row => row.name === name);
		if (!material || forgeRows.length !== 1 || forgeRows[0].final_px !== 1024) throw new Error(`Missing/ambiguous forge material ${name}.`);
		const slots = { albedo: material.pbrMetallicRoughness?.baseColorTexture, normal: material.normalTexture, orm: material.pbrMetallicRoughness?.metallicRoughnessTexture };
		if (imageIndex(original, slots.orm) !== imageIndex(original, material.occlusionTexture)) throw new Error(`${name} does not share ORM with occlusion.`);
		for (const [role, info] of Object.entries(slots)) {
			const index = imageIndex(original, info), expectedName = `${name}_${role}`;
			if (original.images[index].name !== expectedName || replacements.has(index) || owners[index].size !== 1 || !owners[index].has(name)) throw new Error(`Material/image association is ambiguous: ${name}/${role}.`);
			const record = forgeRows[0].files[role], file = path.join(forge, `${expectedName}.png`);
			if (path.resolve(root, record.path) !== file || await fs.realpath(file) !== file) throw new Error('Forge image path escapes the authorized source.');
			const png = await fs.readFile(file);
			if (hash(png) !== record.sha256 || png.length !== record.bytes || png.readUInt32BE(16) !== 1024 || png.readUInt32BE(20) !== 1024) throw new Error(`Forge PNG bytes/dimensions changed: ${expectedName}.`);
			const input = { name, role, imageName: expectedName, imageIndex: index, path: relative(file), sha256: hash(png), bytes: png.length, declaredNormalConvention: role === 'normal' ? 'OpenGL +Y' : null, declaredColorSpace: role === 'albedo' ? 'sRGB' : 'linear', seamScore: record.seam_score, png };
			pngInputs.push(input); replacements.set(index, input);
		}
	}
	if (replacements.size !== 42) throw new Error('Expected exactly42 replacement maps.');
	const ktxVersion = await new Promise((resolve, reject) => {
		const child = spawn(path.join(ktxBin, 'ktx.exe'), ['--version'], { windowsHide: true }); let text = '';
		child.stdout.on('data', chunk => text += chunk); child.stderr.on('data', chunk => text += chunk); child.on('error', reject); child.on('close', code => code === 0 ? resolve(text.trim()) : reject(new Error('KTX version check failed.')));
	});
	if (!ktxVersion.includes('4.4.2') || JSON.parse(await fs.readFile(path.join(root, 'apps/client/node_modules/@gltf-transform/cli/package.json'))).version !== '4.5.0') throw new Error('Encoder toolchain version changed.');
	await fs.mkdir(directory, { recursive: true });
	const document = new Document(); document.createBuffer('forge-texture-encoding');
	for (const name of MATERIALS) {
		const material = document.createMaterial(name), textures = {};
		for (const role of ['albedo', 'normal', 'orm']) { const input = pngInputs.find(input => input.name === name && input.role === role); textures[role] = document.createTexture(input.imageName).setImage(input.png).setMimeType('image/png'); }
		material.setBaseColorTexture(textures.albedo).setNormalTexture(textures.normal).setMetallicRoughnessTexture(textures.orm).setOcclusionTexture(textures.orm);
	}
	const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
	const inputFile = path.join(directory, 'forge-encoding-input.glb'), uastcFile = path.join(directory, 'forge-encoding-uastc.glb'), encodedFile = path.join(directory, 'forge-encoding-basis.glb');
	await io.write(inputFile, document);
	await runEncoder('uastc', ['uastc', inputFile, uastcFile, '--slots', '{normalTexture,occlusionTexture,metallicRoughnessTexture}', '--level', '2', '--jobs', '2', '--rdo', '--rdo-lambda', '2', '--zstd', '9']);
	await runEncoder('etc1s', ['etc1s', uastcFile, encodedFile, '--slots', 'baseColor', '--quality', '180', '--jobs', '2']);
	const encoded = parseGlb(await fs.readFile(encodedFile)), encodedByName = new Map();
	for (let index = 0; index < encoded.json.images.length; index++) {
		const image = encoded.json.images[index]; if (!image.name || encodedByName.has(image.name)) throw new Error('Encoded image names are ambiguous.');
		encodedByName.set(image.name, imageBytes(encoded, index));
	}
	if (encodedByName.size !== 42) throw new Error('Encoder did not preserve exactly42 images.');
	const json = structuredClone(original), pieces = [], imageRecords = []; let offset = 0;
	for (let index = 0; index < original.images.length; index++) {
		const changed = replacements.get(index), oldBytes = imageBytes(sourceGlb, index), bytes = changed ? encodedByName.get(changed.imageName) : oldBytes;
		if (!bytes) throw new Error('Encoded map missing.');
		const info = changed ? ktxInfo(bytes, changed.role) : null;
		const view = json.bufferViews[json.images[index].bufferView]; view.byteOffset = offset; view.byteLength = bytes.length;
		pieces.push(bytes, Buffer.alloc(align4(bytes.length) - bytes.length)); offset += align4(bytes.length);
		imageRecords.push({ imageIndex: index, name: original.images[index].name, changed: !!changed, previousSha256: hash(oldBytes), outputSha256: hash(bytes), bytes: bytes.length, encoding: info, sourcePNG: changed ? { ...changed, png: undefined } : null });
	}
	const newGeometryStart = offset, tail = sourceGlb.bin.subarray(geometryStart), delta = newGeometryStart - geometryStart;
	pieces.push(tail);
	for (const view of json.bufferViews) if (view.extensions?.EXT_meshopt_compression) view.extensions.EXT_meshopt_compression.byteOffset += delta;
	const bin = Buffer.concat(pieces); json.buffers[0].byteLength = bin.length;
	const packedBytes = writeGlb(json, bin); await fs.writeFile(output, packedBytes, { flag: 'wx' });
	const finalBytes = await fs.readFile(output), final = parseGlb(finalBytes);
	if (hash(final.bin.subarray(newGeometryStart)) !== hash(tail)) throw new Error('Immutable geometry-tail bytes changed.');
	const normalized = structuredClone(final.json); normalized.buffers[0].byteLength = original.buffers[0].byteLength;
	for (const index of imageViews) normalized.bufferViews[index] = structuredClone(original.bufferViews[index]);
	for (const view of normalized.bufferViews) if (view.extensions?.EXT_meshopt_compression) view.extensions.EXT_meshopt_compression.byteOffset -= delta;
	equal(original, normalized, 'Non-image glTF metadata');
	for (const image of imageRecords) if (hash(imageBytes(final, image.imageIndex)) !== image.outputSha256) throw new Error('Final KTX2 image bytes changed.');
	for (let index = 54; index < original.bufferViews.length; index++) {
		const before = original.bufferViews[index].extensions.EXT_meshopt_compression, after = final.json.bufferViews[index].extensions.EXT_meshopt_compression;
		if (hash(sourceGlb.bin.subarray(before.byteOffset, before.byteOffset + before.byteLength)) !== hash(final.bin.subarray(after.byteOffset, after.byteOffset + after.byteLength))) throw new Error('An individual compressed geometry buffer changed.');
	}
	await MeshoptDecoder.ready; const verificationIO = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder });
	const beforeDocument = await verificationIO.read(source), afterDocument = await verificationIO.read(output);
	const beforeAccessors = accessorRoster(beforeDocument), afterAccessors = accessorRoster(afterDocument); equal(beforeAccessors, afterAccessors, 'Decoded accessors including UVs');
	if (hash(await fs.readFile(source)) !== SOURCE_SHA || hash(await fs.readFile(path.join(forge, 'forge-manifest.json'))) !== hash(manifestBytes)) throw new Error('Immutable source or forge manifest changed.');
	for (const input of pngInputs) if (hash(await fs.readFile(path.resolve(root, input.path))) !== input.sha256) throw new Error('Forge source changed during encoding.');
	const triangles = original.meshes.reduce((sum, mesh) => sum + mesh.primitives.reduce((sum, primitive) => sum + original.accessors[primitive.indices].count / 3, 0), 0);
	const receipt = {
		schema: 'xexoria.city-forge-r6-texture-candidate/1', status: 'PASS_STRUCTURAL_TEXTURE_ONLY_NATIVE_REVIEW_REQUIRED', created_utc: new Date().toISOString(),
		source: { path: relative(source), sha256: SOURCE_SHA, bytes: sourceBytes.length }, forgeManifest: { path: relative(path.join(forge, 'forge-manifest.json')), sha256: hash(manifestBytes), contract: manifest.contract, license: manifest.license },
		output: { path: relative(output), sha256: hash(finalBytes), bytes: finalBytes.length, triangles, meshes: json.meshes.length, nodes: json.nodes.length, materials: json.materials.length, images: json.images.length },
		requestedMaterials: MATERIALS, replacedImages: 42, unchangedImages: 12, cliffRockImagesUnchanged: imageRecords.filter(image => image.name.startsWith('cliff_rock')).every(image => !image.changed && image.previousSha256 === image.outputSha256),
		geometry: { strategy: 'Copy immutable compressed geometry tail, relocate container offsets only; no geometry re-encoding.', sourceTailOffset: geometryStart, outputTailOffset: newGeometryStart, tailBytes: tail.length, tailSha256: hash(tail), meshoptBuffersByteExact: meshoptViews.length, decodedAccessorsByteExact: afterAccessors.length },
		verification: { geometryPayloadExact: true, decodedAttributesIndicesUvExact: true, nodesMeshesAccessorsMaterialsSamplersTexturesNamesAndUvTransformsExact: true, fallbackBufferExact: true, all42EncodedImagesReadBackExact: true, all12UntargetedImagesByteExact: true, sourcePNGsManifestAndActiveRuntimeUnchanged: true, albedoSrgbNormalOrmLinearMipmapped: true, noTileOrMaterialParameterChanges: true },
		encoder: { gltfTransform: '4.5.0', ktxSoftware: ktxVersion, uastc: { level: 2, rdoLambda: 2, zstd: 9, jobs: 2, roles: ['normal', 'orm'] }, etc1s: { quality: 180, jobs: 2, roles: ['albedo'] }, resizing: false, normalFlip: false },
		images: imageRecords, decodedAccessorRoster: afterAccessors,
		limitations: ['Versioned DEV texture review only; no active promotion or live/snapshot writes.', 'Encoding intentionally changes selected pixels lossily; original forge PNGs are preserved.', 'Source normals declare OpenGL +Y; native direction/strength and texture-repeat art review are still required.', 'Forge tile_m is provenance only; existing geometry UVs and texture transforms remain unchanged.', 'Existing vertex colours and material tints still multiply the new maps; no palette/material correction was performed.', 'No GPU import, appearance, memory, FPS or phone qualification is established by these structural checks.'],
	};
	await fs.writeFile(path.join(directory, 'runtime-pack-receipt.json'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
	console.log(JSON.stringify({ status: receipt.status, output: receipt.output, replaced_images: 42, unchanged_images: 12, compressed_geometry_buffers_exact: meshoptViews.length, decoded_accessors_exact: afterAccessors.length, receipt: relative(path.join(directory, 'runtime-pack-receipt.json')) }));
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
