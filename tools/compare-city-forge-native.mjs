/** Read-only, pinned city texture A/B evidence checks. No capture, renderer mutation or asset admission. */
import fs from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compareLookdevPacks, LOOKDEV_VIEWS, LOOKDEV_CAMERAS } from '../apps/client/src/lookdev/lookdev-data.mjs';

const MAX_ASSET = 256 * 1024 * 1024, MAX_JSON = 512 * 1024;
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const stable = value => value !== null && typeof value === 'object' ? Array.isArray(value) ? value.map(stable) : Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const same = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
const hashObject = value => sha(JSON.stringify(stable(value)));
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const isSha = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

export async function gltfTools() {
	const require = createRequire(new URL('../apps/client/package.json', import.meta.url));
	const core = await import(pathToFileURL(require.resolve('@gltf-transform/core')).href);
	const extensions = await import(pathToFileURL(require.resolve('@gltf-transform/extensions')).href);
	const { MeshoptDecoder } = await import(pathToFileURL(require.resolve('meshoptimizer')).href);
	await MeshoptDecoder.ready;
	return { ...core, io: new core.NodeIO().registerExtensions(extensions.ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder }) };
}
export function parseEmbeddedGlb(bytes) {
	assert(Buffer.isBuffer(bytes) && bytes.length <= MAX_ASSET && bytes.length >= 20, 'GLB size is outside the bounded asset policy');
	assert(bytes.readUInt32LE(0) === 0x46546c67 && bytes.readUInt32LE(4) === 2 && bytes.readUInt32LE(8) === bytes.length, 'Invalid GLB header');
	const size = bytes.readUInt32LE(12);
	assert(bytes.readUInt32LE(16) === 0x4e4f534a && size <= 8 * 1024 * 1024 && 20 + size <= bytes.length, 'Invalid or excessive GLB JSON chunk');
	const json = JSON.parse(bytes.subarray(20, 20 + size).toString('utf8'));
	assert(![...(json.buffers ?? []), ...(json.images ?? [])].some(entry => entry.uri), 'Only self-contained embedded GLBs are admitted; external/data URI resources are refused');
	assert((json.bufferViews ?? []).reduce((sum, view) => sum + view.byteLength, 0) <= 512 * 1024 * 1024, 'Declared decoded buffer views exceed 512 MiB');
	assert((json.accessors ?? []).every(accessor => Number.isInteger(accessor.count) && accessor.count >= 0 && accessor.count <= 20_000_000), 'Accessor count exceeds the bound');
	return json;
}
export function geometryIdentity(document) {
	const root = document.getRoot(), accessors = root.listAccessors(), meshes = root.listMeshes(), nodes = root.listNodes(), skins = root.listSkins();
	const accessor = property => {
		if (!property) return null; const data = property.getArray();
		return { type: property.getType(), count: property.getCount(), componentType: property.getComponentType(), normalized: property.getNormalized(),
			bytesSha256: data ? sha(Buffer.from(data.buffer, data.byteOffset, data.byteLength)) : null };
	};
	const attributes = primitive => Object.fromEntries(primitive.listSemantics().sort().map(semantic => [semantic, accessor(primitive.getAttribute(semantic))]));
	const meshData = meshes.map(mesh => ({ name: mesh.getName(), weights: mesh.getWeights(), extras: mesh.getExtras(), primitives: mesh.listPrimitives().map(primitive => ({
		mode: primitive.getMode(), material: primitive.getMaterial()?.getName() ?? null, indices: accessor(primitive.getIndices()), attributes: attributes(primitive),
		targets: primitive.listTargets().map(attributes), extras: primitive.getExtras(),
	})) }));
	const data = { accessors: accessors.map(accessor), meshes: meshData,
		defaultScene: root.listScenes().indexOf(root.getDefaultScene()),
		nodes: nodes.map(node => ({ name: node.getName(), matrix: node.getMatrix(), weights: node.getWeights(), extras: node.getExtras(), mesh: meshes.indexOf(node.getMesh()),
			skin: skins.indexOf(node.getSkin()), children: node.listChildren().map(child => nodes.indexOf(child)) })),
		scenes: root.listScenes().map(scene => ({ name: scene.getName(), children: scene.listChildren().map(child => nodes.indexOf(child)) })),
		skins: skins.map(skin => ({ name: skin.getName(), inverseBind: accessor(skin.getInverseBindMatrices()), joints: skin.listJoints().map(node => nodes.indexOf(node)) })),
		animations: root.listAnimations().map(animation => ({ name: animation.getName(), channels: animation.listChannels().map(channel => ({ node: nodes.indexOf(channel.getTargetNode()), path: channel.getTargetPath(), sampler: animation.listSamplers().indexOf(channel.getSampler()) })),
			samplers: animation.listSamplers().map(sampler => ({ interpolation: sampler.getInterpolation(), input: accessor(sampler.getInput()), output: accessor(sampler.getOutput()) })) })),
	};
	const uvData = meshData.map(mesh => ({ name: mesh.name, primitives: mesh.primitives.map(primitive => Object.fromEntries(Object.entries(primitive.attributes).filter(([semantic]) => semantic.startsWith('TEXCOORD_')))) }));
	return { geometrySha256: hashObject(data), uvSha256: hashObject(uvData), nodes: nodes.length, meshes: meshes.length, accessors: accessors.length,
		triangles: meshData.reduce((sum, mesh) => sum + mesh.primitives.reduce((part, primitive) => part + (primitive.mode === 4 ? (primitive.indices?.count ?? primitive.attributes.POSITION?.count ?? 0) / 3 : 0), 0), 0) };
}
export function materialParameterIdentity(json) {
	const bindings = new Map();
	const collect = (value, location) => {
		if (!value || typeof value !== 'object') return;
		if (typeof value.index === 'number' && /Texture$/.test(location.split('.').at(-1))) { const list = bindings.get(value.index) ?? []; list.push(location); bindings.set(value.index, list); }
		for (const [key, child] of Object.entries(value)) collect(child, `${location}.${key}`);
	};
	(json.materials ?? []).forEach((material, index) => collect(material, `materials.${index}`));
	const normalize = (value, location) => {
		if (value === null || typeof value !== 'object') return value;
		if (Array.isArray(value)) return value.map((child, index) => normalize(child, `${location}.${index}`));
		const result = Object.fromEntries(Object.entries(value).map(([key, child]) => [key, normalize(child, `${location}.${key}`)]));
		if (typeof value.index === 'number' && /Texture$/.test(location.split('.').at(-1))) {
			const texture = json.textures?.[value.index]; assert(texture, 'Material references a missing texture');
			result.index = `binding:${hashObject((bindings.get(value.index) ?? []).sort())}`;
			result.sampler = texture.sampler === undefined ? null : json.samplers?.[texture.sampler] ?? null;
			result.textureExtensions = Object.keys(texture.extensions ?? {}).sort();
		}
		return result;
	};
	const data = (json.materials ?? []).map((material, index) => normalize(material, `materials.${index}`));
	return { sha256: hashObject(data), names: (json.materials ?? []).map(material => material.name ?? ''), textureBindingCount: bindings.size };
}
export function sceneParameterIdentity(json) {
	return hashObject({ scene: json.scene ?? null, cameras: json.cameras ?? [], extensions: json.extensions ?? {},
		nodeExtensions: (json.nodes ?? []).map(node => node.extensions ?? {}),
		meshExtensions: (json.meshes ?? []).map(mesh => ({ extensions: mesh.extensions ?? {}, primitives: mesh.primitives.map(primitive => primitive.extensions ?? {}) })) });
}
async function scopedPath(workspace, value) {
	assert(typeof value === 'string' && value.length <= 1024, 'Expected a bounded workspace path');
	const resolved = await fs.realpath(path.resolve(workspace, value));
	const relative = path.relative(workspace, resolved); assert(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Input path escapes the workspace'); return resolved;
}
async function readPinned(workspace, descriptor, keepBytes = true) {
	assert(descriptor && isSha(descriptor.sha256), 'Every asset needs an exact SHA-256 pin');
	const file = await scopedPath(workspace, descriptor.path), info = await fs.stat(file); assert(info.size <= MAX_ASSET, 'Asset exceeds 256 MiB');
	if (!keepBytes) {
		const digest = crypto.createHash('sha256'); for await (const chunk of createReadStream(file)) digest.update(chunk);
		const actual = digest.digest('hex'); assert(actual === descriptor.sha256, `Asset hash mismatch: ${descriptor.path}`); return { path: file, sha256: actual, bytes: info.size };
	}
	const bytes = await fs.readFile(file), actual = sha(bytes); assert(actual === descriptor.sha256, `Asset hash mismatch: ${descriptor.path}`);
	return { path: file, sha256: actual, bytes: bytes.length, data: bytes };
}
async function readManifest(workspace, value) {
	const file = await scopedPath(workspace, value), stat = await fs.stat(file); assert(stat.size <= MAX_JSON, 'Capture manifest exceeds 512 KiB');
	const bytes = await fs.readFile(file), manifest = JSON.parse(bytes.toString('utf8'));
	assert(manifest.schema === 'xexoria-lookdev-v0' && ['A','B'].includes(manifest.variant) && Array.isArray(manifest.captures) && manifest.captures.length === 4, 'Expected a four-camera V0 manifest');
	assert(new Set(manifest.captures.map(capture => capture.view)).size === 4 && LOOKDEV_VIEWS.every(view => manifest.captures.some(capture => capture.view === view)), 'Capture view set is incomplete or duplicated');
	const images = [];
	for (const capture of manifest.captures) {
		assert(capture.image === `${manifest.variant}-${capture.view}.png` && isSha(capture.sha256), 'Each native frame needs its expected filename and image SHA');
		const imagePath = await scopedPath(workspace, path.join(path.dirname(file), capture.image));
		assert(path.dirname(imagePath) === path.dirname(file) && (await fs.stat(imagePath)).size <= 12 * 1024 * 1024, 'Image escaped the capture folder or exceeds 12 MiB');
		const image = await fs.readFile(imagePath);
		assert(image.length <= 12 * 1024 * 1024 && image.length === capture.bytes && sha(image) === capture.sha256, `Native image hash/bytes mismatch: ${capture.view}`);
		assert(image.length >= 24 && image.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) && image.subarray(12, 16).toString() === 'IHDR', 'Expected a PNG IHDR');
		assert(image.readUInt32BE(16) === capture.imageSize?.width && image.readUInt32BE(20) === capture.imageSize?.height, `Native image dimensions mismatch: ${capture.view}`);
		images.push({ view: capture.view, path: imagePath, sha256: capture.sha256, bytes: image.length, size: capture.imageSize });
	}
	return { path: file, sha256: sha(bytes), manifest, images };
}
function graphicsParameters(metadata) {
	const graphics = structuredClone(metadata?.graphics ?? null);
	if (graphics?.environment?.fountain) delete graphics.environment.fountain.activeParticles;
	return graphics;
}
export function pairManifestFrames(a, b, expected) {
	const errors = [];
	for (const [label, manifest, pin, variant] of [['baseline', a, expected.baselineHash, 'A'], ['candidate', b, expected.candidateHash, 'B']]) {
		if (manifest.variant !== variant || manifest.settings?.hours !== expected.hours || manifest.settings?.weather !== expected.weather || manifest.lodDistance !== null) errors.push(`${label}: wrong variant/time/weather or non-default LOD mode`);
		if (expected.tier && manifest.settings?.tier !== expected.tier) errors.push(`${label}: wrong quality tier`);
		if (manifest.metadata?.runtimeGlbSha256 !== pin) errors.push(`${label}: native runtime hash identity disagrees with asset pin`);
		if (manifest.metadata?.sourceGlbSha256 !== expected.sourceHash) errors.push(`${label}: missing/different shared source hash identity`);
		if (manifest.metadata?.contentHash !== expected.contentHash) errors.push(`${label}: content bundle hash differs`);
		for (const [key, value] of Object.entries(expected.reviewParameters ?? {})) if (manifest.metadata?.reviewParameters?.[key] !== value) errors.push(`${label}: review parameter ${key} differs/missing`);
	}
	if (!same(a.settings, b.settings)) errors.push('Settings differ');
	if (!a.metadata?.deviceLabel || a.metadata.deviceLabel !== b.metadata?.deviceLabel) errors.push('Host device identities differ/missing');
	if (!graphicsParameters(a.metadata) || !same(graphicsParameters(a.metadata), graphicsParameters(b.metadata))) errors.push('Effective graphics parameters differ/missing');
	if (!same(a.metadata?.reviewParameters, b.metadata?.reviewParameters)) errors.push('Review/debug parameters differ');
	if (a.metadata?.appBuildSha256 && b.metadata?.appBuildSha256 && a.metadata.appBuildSha256 !== b.metadata.appBuildSha256) errors.push('Sealed application build identities differ');
	const pairs = [];
	for (const view of LOOKDEV_VIEWS) {
		const left = a.captures.find(capture => capture.view === view), right = b.captures.find(capture => capture.view === view); assert(left && right, 'Four camera views required');
		const mismatches = [];
		for (const key of ['camera', 'imageSize']) if (!same(left[key], right[key])) mismatches.push(`Different ${key}`);
		for (const [key, value] of Object.entries(LOOKDEV_CAMERAS[view])) if (left.camera?.[key] !== value || right.camera?.[key] !== value) mismatches.push(`Non-default locked ${key}`);
		if (expected.imageSize && (!same(left.imageSize, expected.imageSize) || !same(right.imageSize, expected.imageSize))) mismatches.push('Wrong requested output image dimensions');
		const render = value => { const { focused, visible, ...parameters } = value ?? {}; return parameters; };
		if (!same(render(left.renderIdentity), render(right.renderIdentity))) mismatches.push('Different render backend/resolution/scaling/DPR');
		if (view === 'player' && left.camera?.radius !== 13) mismatches.push('Player view is not 13 m');
		const observedDifference = (metric, percentile = 'p95') => {
			const av = left.metrics?.window?.[metric]?.[percentile], bv = right.metrics?.window?.[metric]?.[percentile];
			return Number.isFinite(av) && Number.isFinite(bv) ? bv - av : null;
		};
		pairs.push({ view, staticParametersMatch: mismatches.length === 0, mismatches, baselineImage: left.image, candidateImage: right.image,
			baselineWallTimeMs: left.baselineWallTimeMs ?? null, candidateWallTimeMs: right.baselineWallTimeMs ?? null,
			baselineFrameP95Ms: left.metrics?.window?.frameIntervalMs?.p95 ?? null, candidateFrameP95Ms: right.metrics?.window?.frameIntervalMs?.p95 ?? null,
			observedUnqualifiedDifferences: { cpuSceneP50Ms: observedDifference('cpuSceneMs','p50'), cpuSceneP95Ms: observedDifference('cpuSceneMs'),
				frameIntervalP95Ms: observedDifference('frameIntervalMs'), drawSubmissionsP95: observedDifference('drawCalls'), submittedIndexEquivalentsP95: observedDifference('activeTriangles'),
				qualification: 'Raw B−A observations only. Motion, browser scheduling and other uncontrolled variation prevent causal texture-cost/gameplay FPS claims.' } });
	}
	const comparison = compareLookdevPacks(a, b);
	return { staticParametersMatch: errors.length === 0 && pairs.every(pair => pair.staticParametersMatch), errors, pairs,
		matchedMotionAndPerformance: comparison.comparable, performanceDeltas: comparison.comparable ? comparison.deltas : [], qualificationLimits: comparison.mismatches,
		appBuildIdentityDeclaredAndMatched: isSha(a.metadata?.appBuildSha256) && a.metadata.appBuildSha256 === b.metadata?.appBuildSha256 };
}
export async function compareCityForgeNative(spec, workspace = process.cwd()) {
	workspace = await fs.realpath(workspace);
	assert(spec.schema === 'xexoria.city-forge-native-input/1' && /^[a-f0-9]{16}$/.test(spec.contentHash), 'Invalid comparator input schema/content pin');
	const source = await readPinned(workspace, spec.source, false), baseline = await readPinned(workspace, spec.baseline), candidate = await readPinned(workspace, spec.candidate);
	const { io } = await gltfTools();
	const baseJson = parseEmbeddedGlb(baseline.data), candidateJson = parseEmbeddedGlb(candidate.data);
	const baseDoc = await io.readBinary(baseline.data), candidateDoc = await io.readBinary(candidate.data);
	const baseGeometry = geometryIdentity(baseDoc), candidateGeometry = geometryIdentity(candidateDoc);
	const baseMaterials = materialParameterIdentity(baseJson), candidateMaterials = materialParameterIdentity(candidateJson);
	const geometryMatch = baseGeometry.geometrySha256 === candidateGeometry.geometrySha256 && baseGeometry.uvSha256 === candidateGeometry.uvSha256;
	const parametersMatch = baseMaterials.sha256 === candidateMaterials.sha256 && sceneParameterIdentity(baseJson) === sceneParameterIdentity(candidateJson);
	const textures = document => document.getRoot().listTextures().map(texture => ({ name: texture.getName(), mime: texture.getMimeType(), sha256: texture.getImage() ? sha(texture.getImage()) : null, bytes: texture.getImage()?.length ?? 0 }));
	const beforeTextures = textures(baseDoc), afterTextures = textures(candidateDoc);
	const changedTextures = afterTextures.map((texture, index) => ({ index, baseline: beforeTextures[index] ?? null, candidate: texture })).filter(pair => !same(pair.baseline, pair.candidate));
	const rounds = [];
	for (const [name, hours] of [['noon',12], ['dusk',18]]) {
		const paths = spec.runs?.[name]; assert(paths, `Missing ${name} run`);
		const a = await readManifest(workspace, paths.baselineManifest), b = await readManifest(workspace, paths.candidateManifest);
		const paired = pairManifestFrames(a.manifest, b.manifest, { baselineHash: baseline.sha256, candidateHash: candidate.sha256, sourceHash: source.sha256, contentHash: spec.contentHash,
			hours, weather: spec.weather ?? 'clear', tier: spec.expectedTier, imageSize: spec.expectedImageSize, reviewParameters: spec.expectedReviewParameters });
		rounds.push({ name, hours, baselineManifest: { path: a.path, sha256: a.sha256 }, candidateManifest: { path: b.path, sha256: b.sha256 }, ...paired,
			pairs: paired.pairs.map(pair => ({ ...pair, baselineNative: a.images.find(image => image.view === pair.view), candidateNative: b.images.find(image => image.view === pair.view) })) });
	}
	const dataPass = geometryMatch && parametersMatch && changedTextures.length > 0 && rounds.every(round => round.staticParametersMatch);
	return { schema: 'xexoria.city-forge-native-comparison/1', createdUtc: new Date().toISOString(),
		status: dataPass ? 'STATIC_PAIRING_VERIFIED_WITH_LIMITS' : 'PAIRING_REJECTED', pairsExpected: 8, nativeFramesVerified: 16,
		source: { path: source.path, sha256: source.sha256 }, baseline: { path: baseline.path, sha256: baseline.sha256, bytes: baseline.bytes, geometry: baseGeometry, materialParameters: baseMaterials },
		candidate: { path: candidate.path, sha256: candidate.sha256, bytes: candidate.bytes, geometry: candidateGeometry, materialParameters: candidateMaterials },
		textureOnlyDataProof: { geometryAndUvExact: geometryMatch, materialAndSceneParametersAndBindingsExact: parametersMatch,
			baselineSceneParametersSha256: sceneParameterIdentity(baseJson), candidateSceneParametersSha256: sceneParameterIdentity(candidateJson),
			baselineTextures: beforeTextures.length, candidateTextures: afterTextures.length, changedTextures }, rounds,
		matchedMotionAndPerformance: dataPass && rounds.every(round => round.matchedMotionAndPerformance),
		limits: ['Native PNG byte/hash/header checks do not establish pixel quality or approve texture art.', 'Runtime/source/device/build identities in manifests are host-declared; local asset/image hashes were independently checked.',
			'Absent appBuildSha256 means the four capture groups have no matched application-build stamp; verify the sealed build through the root capture log.',
			'Without a frozen shared animation phase, moving water, trees, clouds, particles and shadows cannot be attributed solely to texture changes. No automatic pixel-difference or visual ADOPT verdict.',
			'Missing/unmatched phase, mixed focus, stale GPU timing or throttled debug cadence cannot establish gameplay/device performance. No synthesized frames or inferred FPS.', 'No asset was promoted or source overwritten. Claude visual review and root integration remain separate.'] };
}
/** Original PNG links only. Gate on verified pairing, then recheck manifest/image hashes before writing. */
export async function writeCityForgeGallery(receipt, output, workspace = process.cwd(), receiptPath = null) {
	workspace = await fs.realpath(workspace);
	assert(receipt?.schema === 'xexoria.city-forge-native-comparison/1' && receipt.status === 'STATIC_PAIRING_VERIFIED_WITH_LIMITS'
		&& receipt.nativeFramesVerified === 16 && receipt.pairsExpected === 8 && receipt.textureOnlyDataProof?.geometryAndUvExact
		&& receipt.textureOnlyDataProof?.materialAndSceneParametersAndBindingsExact, 'Gallery requires a verified texture-only pairing receipt');
	assert(Array.isArray(receipt.rounds) && receipt.rounds.length === 2 && ['noon','dusk'].every(name => receipt.rounds.some(round => round.name === name)), 'Gallery requires noon and dusk rounds');
	assert(typeof output === 'string' && output.toLowerCase().endsWith('.md'), 'Gallery output must be a new Markdown file');
	const outputPath = path.resolve(workspace, output), parent = await fs.realpath(path.dirname(outputPath));
	assert(!path.relative(workspace, parent).startsWith('..') && !path.isAbsolute(path.relative(workspace, parent)), 'Gallery output escapes the workspace');
	await fs.access(outputPath).then(() => { throw new Error('Gallery output already exists; use a new filename'); }, error => { if (error.code !== 'ENOENT') throw error; });
	const target = value => `<${value.replaceAll('\\','/').replaceAll('>','%3E').replaceAll('<','%3C')}>`;
	const lines = ['# City forge r6 — native A/B review gallery', '',
		'Original image files are linked without pixel alteration. Markdown preview may scale their display; open the originals to inspect full resolution. Local hashes, static camera/parameter pairing and texture-only data were verified; visual approval remains pending.', '',
		`Generated: ${new Date().toISOString()}`, '',
		`Baseline runtime: \`${receipt.baseline.sha256}\``, '', `Forge candidate runtime: \`${receipt.candidate.sha256}\``, '', `Shared source: \`${receipt.source.sha256}\``, '',
		'Geometry and UVs are exact matches. Material/scene parameters and texture bindings match. Texture bytes are the intended change.', '',
		...(receiptPath ? [`[Verified comparison receipt](${target(await scopedPath(workspace, receiptPath))})`, ''] : []),
		'## Review limits', '',
		receipt.matchedMotionAndPerformance ? 'Matched metric conditions were recorded; this gallery still provides no automatic art approval or gameplay/device capacity claim.'
			: 'Motion and performance are unqualified: the shared animation phase was not matched. Moving water, trees, particles, clouds and shadows may differ. Do not attribute those differences or browser cadence to textures, or infer an FPS gain.', '',
		'Runtime/source/device/build stamps are host-declared. PNG hashes verify file integrity; they do not independently attest the browser origin or establish image quality.', '',
		'## Visual inspection checklist', '',
		'- Material identity: stone, plaster, timber and roof tiles read as their intended materials.',
		'- Scale: texel density and grain/tile size stay believable at player distance and in the close view.',
		'- Seams: inspect UV joins, repeated patterns, roof rows and facade transitions.',
		'- Roughness: compare diffuse/specular response at noon and dusk without bloom hiding defects.',
		'- Wear: edge wear, cavity dirt and water paths follow construction and use.',
		'- Record geometry, lighting and motion defects separately; texture changes do not prove those defects are fixed.', '',
		'## Eight paired views', ''];
	for (const [name, hours] of [['noon',12], ['dusk',18]]) {
		const round = receipt.rounds.find(entry => entry.name === name);
		assert(round.hours === hours && round.staticParametersMatch && round.pairs?.length === 4 && LOOKDEV_VIEWS.every(view => round.pairs.some(pair => pair.view === view && pair.staticParametersMatch)), 'Gallery round is not verified');
		const a = await readManifest(workspace, round.baselineManifest.path), b = await readManifest(workspace, round.candidateManifest.path);
		assert(a.sha256 === round.baselineManifest.sha256 && b.sha256 === round.candidateManifest.sha256, 'Manifest changed after pairing verification');
		lines.push(`### ${name === 'noon' ? 'Noon · 12:00' : 'Dusk · 18:00'}`, '');
		for (const view of LOOKDEV_VIEWS) {
			const pair = round.pairs.find(entry => entry.view === view), before = a.images.find(image => image.view === view), after = b.images.find(image => image.view === view);
			assert(before.sha256 === pair.baselineNative?.sha256 && after.sha256 === pair.candidateNative?.sha256
				&& before.path === pair.baselineNative.path && after.path === pair.candidateNative.path, 'Native frame identity changed after pairing verification');
			const camera = a.manifest.captures.find(capture => capture.view === view).camera;
			lines.push(`#### ${view[0].toUpperCase() + view.slice(1)}`, '',
				`Locked radius ${camera.radius} m · original PNG ${before.size.width}×${before.size.height} · static pairing verified.`, '',
				'| Active A | Forge B |', '|---|---|',
				`| ![${name} ${view} — active A](${target(before.path)}) | ![${name} ${view} — forge B](${target(after.path)}) |`, '',
				`[Open original A](${target(before.path)}) · [Open original B](${target(after.path)})`, '',
				`A image SHA-256: \`${before.sha256}\``, '', `B image SHA-256: \`${after.sha256}\``, '');
		}
	}
	lines.push('## Reviewer decision', '', 'Pending human/Claude visual review. Record ADOPT, ITERATE, DROP or BLOCKED with specific defects and remaining limits; this generator issues no subjective pass and promotes no asset.', '');
	await fs.writeFile(outputPath, lines.join('\n'), { flag: 'wx' });
	return { path: outputPath, pairs: 8, originalImages: 16, pixelsAltered: false };
}
export function comparisonTemplate() {
	return { schema: 'xexoria.city-forge-native-input/1', contentHash: '2c622d76e2a4c62a', weather: 'clear', expectedTier: 'high', expectedImageSize: { width: 1280, height: 720 },
		expectedReviewParameters: { noGlow: true, noShadow: false, cityOverview: false },
		source: { path: 'assets/models/reference-city/r5/market-repair-candidate/city-source.glb', sha256: '91b5c4952deeff608bbc2f6b5a9e0c67927f838aa70f34c6d9191ebdf21c4572' },
		baseline: { path: 'assets/models/reference-city/r5/market-repair-candidate/city-runtime.meshopt.glb', sha256: '95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72' },
		candidate: { path: 'assets/models/reference-city/r5/forge-r6-texture-review-candidate/city-runtime.meshopt.glb', sha256: '93910787c74e3655f40df4c8fb73630503d67e540d7fe98286febd0a1907fb61' },
		runs: {
			noon: { baselineManifest: 'planning/evidence/lookdev/materials/20261002-forge-noon/A-manifest.json', candidateManifest: 'planning/evidence/lookdev/materials/20261002-forge-noon/B-manifest.json' },
			dusk: { baselineManifest: 'planning/evidence/lookdev/materials/20261002-forge-dusk/A-manifest.json', candidateManifest: 'planning/evidence/lookdev/materials/20261002-forge-dusk/B-manifest.json' },
		} };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	const args = process.argv.slice(2), value = name => { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : null; };
	try {
		if (value('--write-template')) { await fs.writeFile(value('--write-template'), JSON.stringify(comparisonTemplate(), null, 2) + '\n', { flag: 'wx' }); console.log('Comparator input template created; fill candidate and four manifest paths.'); }
		else {
			assert(value('--spec') && value('--output'), 'Use --spec <input.json> --output <new-receipt.json> [--gallery <new-review.md>] [--workspace <game>]');
			const specBytes = await fs.readFile(value('--spec')); assert(specBytes.length <= MAX_JSON, 'Input spec exceeds 512 KiB');
			const receipt = await compareCityForgeNative(JSON.parse(specBytes), value('--workspace') ?? process.cwd());
			await fs.writeFile(value('--output'), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
			const gallery = value('--gallery') ? await writeCityForgeGallery(receipt, value('--gallery'), value('--workspace') ?? process.cwd(), path.resolve(value('--output'))) : null;
			console.log(JSON.stringify({ status: receipt.status, frames: receipt.nativeFramesVerified, pairs: receipt.pairsExpected, geometryAndUvExact: receipt.textureOnlyDataProof.geometryAndUvExact, materialParametersExact: receipt.textureOnlyDataProof.materialAndSceneParametersAndBindingsExact, matchedMotionAndPerformance: receipt.matchedMotionAndPerformance, receipt: path.resolve(value('--output')), gallery: gallery?.path ?? null }));
			if (receipt.status === 'PAIRING_REJECTED') process.exitCode = 2;
		}
	} catch (error) { console.error(`City forge comparison refused: ${error.message}`); process.exitCode = 1; }
}
