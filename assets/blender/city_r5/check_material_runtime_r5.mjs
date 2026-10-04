import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { MeshoptDecoder } from '../../../apps/client/node_modules/meshoptimizer/meshopt_decoder.mjs';

const artifact = resolve(process.argv.find(arg => arg.endsWith('.glb')) ?? 'assets/models/reference-city/r5/city-runtime.glb');
const outputIndex = process.argv.indexOf('--output');
assert.ok(outputIndex >= 0, 'Use an explicit --output JSON receipt');
const output = resolve(process.argv[outputIndex + 1]);
const roots = JSON.parse(readFileSync('.harness/.cache/city-major-landmark-placement-proof.json', 'utf8')).after;
const uvProof = JSON.parse(readFileSync('planning/evidence/city-material-roof-uv-readback-20261001.json', 'utf8'));
const bytes = readFileSync(artifact);
assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
assert.equal(bytes.readUInt32LE(4), 2);
assert.equal(bytes.readUInt32LE(8), bytes.length);
const jsonLength = bytes.readUInt32LE(12);
const document = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
const bin = bytes.subarray(28 + jsonLength);
const runtime = document.extensionsUsed?.includes('EXT_meshopt_compression') ?? false;
assert.equal(document.materials.length, 45);
assert.equal(document.images.length, 54);
const materials = new Set([...roots.map(root => root.vertex_witness_material),
  ...uvProof.roof_uv_witnesses.map(w => w.material)]);
const samples = new Map([...materials].map(name => [name, []]));
const views = new Map();
const componentBytes = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
await MeshoptDecoder.ready;
function accessorValues(index) {
  const accessor = document.accessors[index];
  const view = document.bufferViews[accessor.bufferView];
  if (!views.has(accessor.bufferView)) {
    const compression = view.extensions?.EXT_meshopt_compression;
    let buffer;
    if (compression) {
      assert.equal(compression.buffer, 0);
      buffer = new Uint8Array(compression.count * compression.byteStride);
      MeshoptDecoder.decodeGltfBuffer(buffer, compression.count, compression.byteStride,
        bin.subarray(compression.byteOffset, compression.byteOffset + compression.byteLength), compression.mode, compression.filter);
    } else {
      assert.equal(view.buffer, 0);
      buffer = bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
    }
    views.set(accessor.bufferView, new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength));
  }
  const data = views.get(accessor.bufferView);
  const width = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }[accessor.type];
  const component = componentBytes[accessor.componentType];
  assert.ok(width && component);
  const stride = view.byteStride ?? width * component;
  return Array.from({ length: accessor.count }, (_, i) => Array.from({ length: width }, (_, axis) => {
    const offset = (accessor.byteOffset ?? 0) + i * stride + axis * component;
    let value = { 5120: () => data.getInt8(offset), 5121: () => data.getUint8(offset),
      5122: () => data.getInt16(offset, true), 5123: () => data.getUint16(offset, true),
      5125: () => data.getUint32(offset, true), 5126: () => data.getFloat32(offset, true) }[accessor.componentType]();
    if (accessor.normalized) value = accessor.componentType === 5120 ? Math.max(-1, value / 127)
      : accessor.componentType === 5121 ? value / 255
        : accessor.componentType === 5122 ? Math.max(-1, value / 32767) : value / 65535;
    assert.ok(Number.isFinite(value));
    return value;
  }));
}
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
for (const node of document.nodes.filter(node => node.mesh !== undefined)) {
  for (const primitive of document.meshes[node.mesh].primitives) {
    const name = document.materials[primitive.material].name;
    if (!materials.has(name)) continue;
    assert.ok(!node.matrix && !document.nodes.some(parent => parent.children?.includes(document.nodes.indexOf(node))),
      'Merged static material nodes must use root TRS transforms');
    assert.deepEqual(Object.keys(primitive.attributes).sort(), ['COLOR_0', 'NORMAL', 'POSITION', 'TEXCOORD_0']);
    const positions = accessorValues(primitive.attributes.POSITION);
    const uvs = accessorValues(primitive.attributes.TEXCOORD_0);
    assert.equal(positions.length, uvs.length);
    const scale = node.scale ?? [1, 1, 1], translation = node.translation ?? [0, 0, 0], rotation = node.rotation ?? [0, 0, 0, 1];
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i].map((v, axis) => v * scale[axis]);
      const a = cross(rotation, p), b = cross(rotation, a);
      samples.get(name).push({ point: p.map((v, axis) => v + 2 * rotation[3] * a[axis] + 2 * b[axis] + translation[axis]), uv: uvs[i] });
    }
  }
}
const squared = (a, b) => a.reduce((sum, v, axis) => sum + (v - b[axis]) ** 2, 0);
const rootErrors = roots.map(root => Math.sqrt(Math.min(...samples.get(root.vertex_witness_material).map(s => squared(s.point, root.gltf_vertex_witness)))));
assert.equal(rootErrors.length, 37);
assert.ok(rootErrors.every(error => error < 0.02), `Root witness moved: ${Math.max(...rootErrors)}`);
let maxPositionError = 0, maxUvError = 0;
for (const witness of uvProof.roof_uv_witnesses) {
  let best = null;
  for (const sample of samples.get(witness.material)) {
    const positionError = Math.sqrt(squared(sample.point, witness.position));
    if (positionError >= (runtime ? 0.02 : 0.0001)) continue;
    const uvError = Math.sqrt(squared(sample.uv, witness.uv));
    if (best === null || uvError < best.uvError) best = { positionError, uvError };
  }
  assert.ok(best && best.uvError < 0.0001, `Roof UV witness failed: ${witness.object} (${JSON.stringify(best)})`);
  maxPositionError = Math.max(maxPositionError, best.positionError);
  maxUvError = Math.max(maxUvError, best.uvError);
}
const imageIndex = tex => document.textures[tex.index].source ?? document.textures[tex.index].extensions.KHR_texture_basisu.source;
const textureChecks = [];
for (const material of document.materials) {
  if (!['roof_slate_blue', 'roof_slate_navy', 'roof_tile_red', 'roof_shingle_green', 'stone_wall_warm', 'paver_surface'].includes(material.name)) continue;
  const mr = material.pbrMetallicRoughness;
  assert.ok(mr.baseColorTexture && mr.metallicRoughnessTexture && material.normalTexture && material.occlusionTexture);
  assert.equal(imageIndex(mr.metallicRoughnessTexture), imageIndex(material.occlusionTexture));
  for (const [slot, tex] of Object.entries({ albedo: mr.baseColorTexture, normal: material.normalTexture, orm: mr.metallicRoughnessTexture })) {
    assert.equal(tex.texCoord ?? 0, 0);
    const image = document.images[imageIndex(tex)];
    const view = document.bufferViews[image.bufferView];
    const raw = bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
    if (runtime) {
      assert.equal(image.mimeType, 'image/ktx2');
      assert.equal(raw.readUInt32LE(20), 1024);
      assert.equal(raw.readUInt32LE(24), 1024);
      assert.equal(raw.readUInt32LE(40), 11);
      const dfdOffset = raw.readUInt32LE(48);
      assert.equal(raw[dfdOffset + 14], slot === 'albedo' ? 2 : 1, `${material.name}/${slot} colorspace`);
    } else {
      assert.equal(image.mimeType, 'image/png');
      assert.equal(raw.readUInt32BE(16), 1024);
      assert.equal(raw.readUInt32BE(20), 1024);
      const file = readFileSync(`assets/models/reference-city/r5/textures/${material.name}_${slot}.png`);
      assert.equal(createHash('sha256').update(raw).digest('hex'), createHash('sha256').update(file).digest('hex'), 'Source must embed current foundry maps');
    }
    textureChecks.push({ material: material.name, slot, bytes: view.byteLength, size: [1024, 1024] });
  }
}
for (const sampler of document.samplers) {
  assert.equal(sampler.minFilter, 9987);
  assert.equal(sampler.wrapS ?? 10497, 10497);
  assert.equal(sampler.wrapT ?? 10497, 10497);
}
const result = { result: 'PASS', artifact, sha256: createHash('sha256').update(bytes).digest('hex'),
  bytes: bytes.length, runtime, roots_verified: 37, homes_verified: uvProof.homes_verified,
  max_root_witness_error_m: Math.max(...rootErrors), roof_uv_witnesses_verified: uvProof.roof_uv_witnesses.length,
  roof_meshes_verified: uvProof.roof_meshes_verified, max_roof_witness_error_m: maxPositionError,
  max_uv_witness_error: maxUvError, material_count: document.materials.length,
  image_count: document.images.length, paired_texture_channels_verified: true,
  repeat_mipmapped_sampling_verified: true, texture_checks: textureChecks };
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify({ ...result, texture_checks: undefined }));
