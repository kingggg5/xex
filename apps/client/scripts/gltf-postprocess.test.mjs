import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import { Document, NodeIO } from '@gltf-transform/core';
import { EXIT, PostprocessError, createIO, packGlb, parseGlb, postprocessGlb } from './gltf-postprocess.mjs';

const script = fileURLToPath(new URL('./gltf-postprocess.mjs', import.meta.url));
const repoRoot = path.resolve(path.dirname(script), '../../..');
const ktxDir = process.env.KTX_SOFTWARE_BIN || path.join(repoRoot, '.harness/.cache/toolchains/ktx-4.4.2/portable/bin');
const hasKtx = existsSync(path.join(ktxDir, process.platform === 'win32' ? 'ktx.exe' : 'ktx'));
let work;

const budgets = {
  schema: 'xexoria.asset-budgets/1',
  defaults: { policy: { color0: 'RGB', max_uv_sets: 2, strip_unused_tangents: true, weld: true }, ktx: { jobs: 1 } },
  classes: {
    roomy: { profile: 'prop', source: 'test', limits: { triangles: 1000, draw_calls: 4, materials: 4, texture_mib: 4, vertex_attributes: 8 } },
    tiny: { profile: 'prop', source: 'test', limits: { triangles: 4, draw_calls: 4, materials: 4 } },
  },
};

function png(width, height, rgba) {
  const crc = (buf) => { const b = Buffer.alloc(4); b.writeUInt32BE(zlib.crc32(buf) >>> 0); return b; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type, 'ascii'), data]); return Buffer.concat([len, td, crc(td)]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = 6;
  const rows = [];
  for (let y = 0; y < height; y++) { rows.push(Buffer.from([0])); for (let x = 0; x < width; x++) rows.push(Buffer.from(rgba(x, y))); }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(rows))), chunk('IEND', Buffer.alloc(0))]);
}

/** A 2x2x2 cube (12 triangles) with float POSITION/NORMAL/TEXCOORD_0, a VEC4 COLOR_0 and optional textures. */
async function cubeGlb(file, { textures = false, tangent = false } = {}) {
  const doc = new Document();
  const buffer = doc.createBuffer();
  const p = []; const n = []; const uv = []; const c = []; const idx = [];
  const faces = [[0, 1, 2, 1], [0, 1, 2, -1], [1, 2, 0, 1], [1, 2, 0, -1], [2, 0, 1, 1], [2, 0, 1, -1]];
  for (const [a, b, axis, s] of faces) {
    const base = p.length / 3;
    for (const [u, v] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      const q = [0, 0, 0]; q[a] = u; q[b] = v * s; q[axis] = s; p.push(...q);
      const nn = [0, 0, 0]; nn[axis] = s; n.push(...nn); uv.push((u + 1) / 2, (v + 1) / 2); c.push(0.8, 0.6, 0.4, 1);
    }
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  const acc = (type, arr) => doc.createAccessor().setType(type).setArray(arr).setBuffer(buffer);
  const material = doc.createMaterial('crate').setDoubleSided(false);
  if (textures) {
    const colour = doc.createTexture('crate_albedo').setImage(png(8, 8, (x, y) => [200, 120 + x * 8, 60 + y * 8, 255])).setMimeType('image/png');
    const normal = doc.createTexture('crate_normal').setImage(png(8, 8, () => [128, 128, 255, 255])).setMimeType('image/png');
    material.setBaseColorTexture(colour).setNormalTexture(normal);
  }
  const prim = doc.createPrimitive().setMaterial(material).setIndices(acc('SCALAR', new Uint16Array(idx)))
    .setAttribute('POSITION', acc('VEC3', new Float32Array(p))).setAttribute('NORMAL', acc('VEC3', new Float32Array(n)))
    .setAttribute('TEXCOORD_0', acc('VEC2', new Float32Array(uv))).setAttribute('COLOR_0', acc('VEC4', new Float32Array(c)));
  if (textures || tangent) prim.setAttribute('TANGENT', acc('VEC4', new Float32Array(p.length / 3 * 4).fill(1)));
  const mesh = doc.createMesh('crate').addPrimitive(prim);
  doc.createScene('test').addChild(doc.createNode('crate').setMesh(mesh));
  writeFileSync(file, await new NodeIO().writeBinary(doc));
  return file;
}

before(() => { work = mkdtempSync(path.join(tmpdir(), 'xex-gltf-postprocess-test-')); });
after(() => { rmSync(work, { recursive: true, force: true }); });

test('post-process writes EXT_meshopt_compression (never KHR) with KHR_mesh_quantization and RGB COLOR_0', async () => {
  const input = await cubeGlb(path.join(work, 'cube.glb'), { tangent: true });
  const output = path.join(work, 'out', 'cube.glb');
  const report = await postprocessGlb({ input, output, className: 'roomy', budgets, noKtx: true, io: await createIO() });
  assert.equal(report.status, 'PASS', JSON.stringify(report.failures));
  const { json } = parseGlb(readFileSync(output));
  const text = JSON.stringify(json);
  assert.ok(json.extensionsUsed.includes('EXT_meshopt_compression'));
  assert.ok(json.extensionsRequired.includes('EXT_meshopt_compression'));
  assert.ok(json.extensionsUsed.includes('KHR_mesh_quantization'));
  assert.ok(!text.includes('KHR_meshopt_compression'), 'KHR_meshopt_compression must never be written');
  assert.ok(json.bufferViews.some((v) => v.extensions?.EXT_meshopt_compression), 'compressed buffer views');
  const prim = json.meshes[0].primitives[0];
  const position = json.accessors[prim.attributes.POSITION];
  assert.ok([5120, 5121, 5122, 5123].includes(position.componentType), `quantized POSITION, got ${position.componentType}`);
  assert.equal(json.accessors[prim.attributes.COLOR_0].type, 'VEC3', 'GAP-3: COLOR_0 rewritten as RGB');
  assert.equal(prim.attributes.TANGENT, undefined, 'TANGENT dropped: the material has no normal map');
  assert.ok(report.stripped_attributes.some((s) => s.attribute === 'TANGENT'));
  assert.equal(report.metrics.triangles, 12);
  assert.ok(report.parity.every((p) => p.pass));
  assert.equal(report.validator.errors, 0);
  const decoded = await (await createIO()).read(output);   // the meshopt stream decodes with the repo decoder
  assert.equal(decoded.getRoot().listMeshes()[0].listPrimitives()[0].getIndices().getCount(), 36);
});

test('a budget breach exits 2 with a clear message', () => {
  const input = path.join(work, 'cube.glb');
  const budgetFile = path.join(work, 'budgets.json');
  writeFileSync(budgetFile, JSON.stringify(budgets));
  const r = spawnSync(process.execPath, [script, input, '--out', path.join(work, 'breach', 'cube.glb'), '--class', 'tiny', '--budgets', budgetFile, '--no-ktx'], { encoding: 'utf8' });
  assert.equal(r.status, EXIT.BUDGET, r.stdout + r.stderr);
  assert.match(r.stderr, /BUDGET FAIL tiny \(tier high\): triangles 12 > 4/);
  assert.match(r.stdout, /FAIL_BUDGET/);
});

test('KHR_meshopt_compression input is refused (policy exit 3)', async () => {
  const bad = path.join(work, 'khr.glb');
  writeFileSync(bad, packGlb({ asset: { version: '2.0' }, extensionsUsed: ['KHR_meshopt_compression'] }, Buffer.alloc(0)));
  await assert.rejects(postprocessGlb({ input: bad, output: path.join(work, 'khr-out.glb'), className: 'roomy', budgets, noKtx: true }),
    (e) => e instanceof PostprocessError && e.exitCode === EXIT.POLICY && /KHR_meshopt_compression/.test(e.message));
});

test('textures stay external in one shared folder, deduplicated across GLBs; normal-mapped tangents kept', async () => {
  const input = await cubeGlb(path.join(work, 'textured.glb'), { textures: true });
  const shared = path.join(work, 'shared-textures');
  const io = await createIO();
  for (const name of ['a', 'b']) {
    const output = path.join(work, 'ext', `${name}.glb`);
    const report = await postprocessGlb({ input, output, className: 'roomy', budgets, noKtx: true, textureOut: shared, io });
    assert.equal(report.status, 'PASS', JSON.stringify(report.failures));
    const { json } = parseGlb(readFileSync(output));
    assert.equal(json.images.length, 2);
    assert.notEqual(json.meshes[0].primitives[0].attributes.TANGENT, undefined, 'normal map keeps TANGENT');
    for (const image of json.images) {
      assert.ok(image.uri && !image.bufferView, 'external uri, not embedded');
      assert.ok(existsSync(path.resolve(path.dirname(output), decodeURIComponent(image.uri))));
    }
  }
  assert.equal(readdirSync(shared).filter((f) => f.endsWith('.png')).length, 2, 'two GLBs share two files');
});

test('KTX2: ETC1S for colour, UASTC for normals, cached by content hash', { skip: hasKtx ? false : `KTX-Software not found in ${ktxDir}` }, async () => {
  const input = path.join(work, 'textured.glb');
  const shared = path.join(work, 'ktx-textures');
  const io = await createIO();
  const first = await postprocessGlb({ input, output: path.join(work, 'ktx', 'a.glb'), className: 'roomy', budgets, textureOut: shared, ktxBin: ktxDir, io });
  assert.equal(first.status, 'PASS', JSON.stringify(first.failures));
  assert.deepEqual(first.textures.map((t) => `${t.slots[0]}:${t.mode}:${t.cache}`).sort(), ['baseColorTexture:ETC1S:miss', 'normalTexture:UASTC:miss']);
  const { json } = parseGlb(readFileSync(path.join(work, 'ktx', 'a.glb')));
  assert.ok(json.extensionsRequired.includes('KHR_texture_basisu'));
  assert.ok(json.images.every((i) => i.mimeType === 'image/ktx2' && i.uri.endsWith('.ktx2')));
  const second = await postprocessGlb({ input, output: path.join(work, 'ktx', 'b.glb'), className: 'roomy', budgets, textureOut: shared, ktxBin: ktxDir, io });
  assert.ok(second.textures.every((t) => t.cache === 'hit'), 'second GLB reuses the cached KTX2 files');
  assert.equal(second.status, 'PASS', `all-hit cache output must stay valid: ${JSON.stringify(second.failures)}`);
  const b = parseGlb(readFileSync(path.join(work, 'ktx', 'b.glb'))).json;
  assert.ok(b.extensionsRequired.includes('KHR_texture_basisu'), 'KHR_texture_basisu registered even when nothing was encoded');
  assert.ok(b.textures.every((t) => t.source === undefined && t.extensions?.KHR_texture_basisu), 'KTX2 only via the extension');
  assert.equal(readdirSync(shared).filter((f) => f.endsWith('.ktx2')).length, 2);
});
