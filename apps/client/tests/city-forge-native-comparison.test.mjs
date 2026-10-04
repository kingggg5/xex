import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { gltfTools, geometryIdentity, materialParameterIdentity, sceneParameterIdentity, parseEmbeddedGlb, pairManifestFrames, compareCityForgeNative, writeCityForgeGallery } from '../../../tools/compare-city-forge-native.mjs';
import { lockedCamera } from '../src/lookdev/lookdev-data.mjs';

const { Document, io } = await gltfTools();
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42EAAAAASUVORK5CYII=', 'base64');
const fixture = () => {
	const document = new Document(), buffer = document.createBuffer();
	const position = document.createAccessor().setType('VEC3').setArray(new Float32Array([0,0,0,1,0,0,0,1,0])).setBuffer(buffer);
	const uv = document.createAccessor().setType('VEC2').setArray(new Float32Array([0,0,1,0,0,1])).setBuffer(buffer);
	const indices = document.createAccessor().setType('SCALAR').setArray(new Uint16Array([0,1,2])).setBuffer(buffer);
	const texture = document.createTexture('tile').setImage(new Uint8Array(png)).setMimeType('image/png');
	const material = document.createMaterial('stone').setBaseColorTexture(texture);
	const primitive = document.createPrimitive().setAttribute('POSITION', position).setAttribute('TEXCOORD_0', uv).setIndices(indices).setMaterial(material);
	const mesh = document.createMesh('building').addPrimitive(primitive), node = document.createNode('building').setMesh(mesh);
	const scene = document.createScene('city').addChild(node); document.getRoot().setDefaultScene(scene);
	return { document, texture, material, position, uv };
};
test('decoded geometry and UV identity ignore texture image bytes but reject shape/UV edits', () => {
	const f = fixture(), initial = geometryIdentity(f.document);
	f.texture.setImage(new Uint8Array([...png, 0])); assert.deepEqual(geometryIdentity(f.document), initial);
	f.position.getArray()[0] = .1; assert.notEqual(geometryIdentity(f.document).geometrySha256, initial.geometrySha256);
	f.position.getArray()[0] = 0; f.uv.getArray()[0] = .1; assert.notEqual(geometryIdentity(f.document).uvSha256, initial.uvSha256);
});
test('material/scenario parameter proof permits new pixels but rejects scalar, sampler and scene changes', async () => {
	const f = fixture(), before = parseEmbeddedGlb(Buffer.from(await io.writeBinary(f.document)));
	f.texture.setImage(new Uint8Array([...png, 0])); const after = parseEmbeddedGlb(Buffer.from(await io.writeBinary(f.document)));
	assert.equal(materialParameterIdentity(before).sha256, materialParameterIdentity(after).sha256);
	f.material.setRoughnessFactor(.4); const changed = parseEmbeddedGlb(Buffer.from(await io.writeBinary(f.document)));
	assert.notEqual(materialParameterIdentity(before).sha256, materialParameterIdentity(changed).sha256);
	const samplerChange = structuredClone(before); samplerChange.samplers[0].wrapS = 33071;
	assert.notEqual(materialParameterIdentity(before).sha256, materialParameterIdentity(samplerChange).sha256);
	const sceneChange = structuredClone(before); sceneChange.cameras = [{ type: 'perspective', perspective: { yfov: 1, znear: .1 } }];
	assert.notEqual(sceneParameterIdentity(before), sceneParameterIdentity(sceneChange));
});
const pins = { baselineHash: 'a'.repeat(64), candidateHash: 'b'.repeat(64), sourceHash: 'c'.repeat(64), contentHash: '0123456789abcdef', hours: 12, weather: 'clear', tier: 'high',
	imageSize: { width: 1, height: 1 }, reviewParameters: { noGlow: true, noShadow: false, cityOverview: false } };
const manifest = (variant, hours, runtimeHash) => ({ schema: 'xexoria-lookdev-v0', variant, pillar: 'materials', cycle: 'fixture', settings: { tier: 'high', hours, weather: 'clear' }, lodDistance: null,
	capturePhaseFrozen: false, metadata: { runtimeGlbSha256: runtimeHash, sourceGlbSha256: pins.sourceHash, contentHash: pins.contentHash, deviceLabel: 'Fixture device; not a physical GPU', phaseSeed: null,
		graphics: { profile: { preset: 'high' }, frameCap: 60, environment: { profile: { preset: 'high' }, fountain: { activeParticles: variant === 'A' ? 50 : 60, nativeParticleCapacity: 100 } } }, reviewParameters: { ...pins.reviewParameters } },
	captures: ['player','side','close','elevated'].map(view => ({ view, camera: lockedCamera(view, { x: 0, y: 2.3, z: 176 }), image: `${variant}-${view}.png`, imageSize: { width: 1, height: 1 }, bytes: png.length, sha256: hash(png),
		renderIdentity: { backend: 'WebGL2', width: 1280, height: 720, hardwareScalingLevel: 1, gpuScope: 'frame', visible: true, focused: true, devicePixelRatio: 1 }, baselineWallTimeMs: 90000,
		metrics: { gpuStatus: 'stale', window: { focus: { focusedFrames: 60, unfocusedFrames: 0, unknownFrames: 0 }, frameIntervalMs: { p95: 1000 }, cpuSceneMs: { p95: 5 }, gpuMs: { n: 60, p95: 2 }, drawCalls: { p95: 50 }, activeTriangles: { p95: 10 } } } })) });
test('static frame pairing stays usable while unfrozen motion/performance remain explicitly unqualified', () => {
	const result = pairManifestFrames(manifest('A',12,pins.baselineHash), manifest('B',12,pins.candidateHash), pins);
	assert.equal(result.staticParametersMatch, true); assert.equal(result.matchedMotionAndPerformance, false); assert.deepEqual(result.performanceDeltas, []);
	assert.ok(result.qualificationLimits.some(reason => reason.includes('phase'))); assert.equal(result.appBuildIdentityDeclaredAndMatched, false);
});
test('frame pairing rejects stale identity, camera, settings, output size and debug parameters', () => {
	for (const change of [m => { m.metadata.runtimeGlbSha256 = pins.baselineHash; }, m => { delete m.metadata.sourceGlbSha256; }, m => { m.settings.hours = 18; },
		m => { m.captures[0].camera.radius = 15; }, m => { m.captures[1].camera.alpha = .2; }, m => { m.captures[0].imageSize.width = 2; },
		m => { m.metadata.reviewParameters.noGlow = false; }, m => { m.metadata.graphics.profile.preset = 'low'; }]) {
		const b = manifest('B',12,pins.candidateHash); change(b); assert.equal(pairManifestFrames(manifest('A',12,pins.baselineHash), b, pins).staticParametersMatch, false);
	}
});
test('GLB validation refuses external resources before NodeIO can read them', async () => {
	const bytes = Buffer.from(await io.writeBinary(fixture().document)), json = parseEmbeddedGlb(bytes);
	json.images[0].uri = 'file:///outside.png';
	const encoded = Buffer.from(JSON.stringify(json)); const padded = Buffer.concat([encoded, Buffer.alloc((4 - encoded.length % 4) % 4, 32)]);
	const bin = bytes.subarray(20 + bytes.readUInt32LE(12)); const malformed = Buffer.alloc(20 + padded.length + bin.length);
	bytes.copy(malformed, 0, 0, 12); malformed.writeUInt32LE(malformed.length, 8); malformed.writeUInt32LE(padded.length, 12); malformed.writeUInt32LE(0x4e4f534a,16); padded.copy(malformed,20); bin.copy(malformed,20+padded.length);
	assert.throws(() => parseEmbeddedGlb(malformed), /self-contained/);
});
test('full receipt checks sixteen immutable PNGs and catches tampering (serialization fixtures only)', async () => {
	const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'xexoria-forge-contract-'));
	const f = fixture(), base = Buffer.from(await io.writeBinary(f.document)); f.texture.setImage(new Uint8Array([...png,0])); const candidate = Buffer.from(await io.writeBinary(f.document));
	await fs.writeFile(path.join(folder,'source.glb'),base); await fs.writeFile(path.join(folder,'baseline.glb'),base); await fs.writeFile(path.join(folder,'candidate.glb'),candidate);
	const input = { schema: 'xexoria.city-forge-native-input/1', contentHash: pins.contentHash, weather: 'clear', expectedTier: 'high', expectedImageSize: pins.imageSize, expectedReviewParameters: pins.reviewParameters,
		source: { path: 'source.glb', sha256: hash(base) }, baseline: { path: 'baseline.glb', sha256: hash(base) }, candidate: { path: 'candidate.glb', sha256: hash(candidate) }, runs: {} };
	for (const [name,hours] of [['noon',12],['dusk',18]]) {
		input.runs[name] = {};
		for (const [variant,role,bytes] of [['A','baseline',base],['B','candidate',candidate]]) {
			const dir = path.join(folder,name,variant); await fs.mkdir(dir,{recursive:true});
			const m = manifest(variant,hours,hash(bytes)); m.metadata.sourceGlbSha256 = hash(base);
			for (const capture of m.captures) await fs.writeFile(path.join(dir,capture.image),png);
			await fs.writeFile(path.join(dir,`${variant}-manifest.json`),JSON.stringify(m)); input.runs[name][`${role}Manifest`] = path.relative(folder,path.join(dir,`${variant}-manifest.json`));
		}
	}
	const result = await compareCityForgeNative(input,folder);
	assert.equal(result.status,'STATIC_PAIRING_VERIFIED_WITH_LIMITS'); assert.equal(result.nativeFramesVerified,16); assert.equal(result.rounds.length,2); assert.equal(result.matchedMotionAndPerformance,false);
	const galleryPath = path.join(folder,'gallery.md'), gallery = await writeCityForgeGallery(result,galleryPath,folder);
	const markdown = await fs.readFile(galleryPath,'utf8'); assert.equal(gallery.originalImages,16); assert.equal(gallery.pixelsAltered,false);
	assert.equal((markdown.match(/!\[/g) ?? []).length,16); assert.ok(markdown.includes('Motion and performance are unqualified'));
	assert.ok(markdown.includes((await fs.realpath(path.join(folder,'noon/A/A-player.png'))).replaceAll('\\','/')));
	assert.equal(hash(await fs.readFile(path.join(folder,'noon/A/A-player.png'))),hash(png));
	await assert.rejects(writeCityForgeGallery(result,galleryPath,folder),/already exists/);
	await assert.rejects(writeCityForgeGallery({...result,status:'PAIRING_REJECTED'},path.join(folder,'rejected-gallery.md'),folder),/requires a verified/);
	await fs.appendFile(path.join(folder,'noon/A/A-player.png'),Buffer.from([0]));
	await assert.rejects(compareCityForgeNative(input,folder),/Native image hash/);
	const tamperedGallery = path.join(folder,'tampered-gallery.md'); await assert.rejects(writeCityForgeGallery(result,tamperedGallery,folder),/Native image hash/);
	await assert.rejects(fs.access(tamperedGallery));
	// Deliberately no recursive deletion: this small test workspace remains an isolated OS temp fixture.
});
