// Regression guard for one post-process rule: glTF Transform `prune` must keep vertex attributes
// (`keepAttributes: true`). With the default `prune()` every TEXCOORD_n that no material texture reads is deleted, and the
// tree kit's wind data lives in TEXCOORD_1 (nothing samples a texture with it), so the wind would be lost silently.
// See docs/reviews/2026-10-02-export-helper.md. No KTX-Software is needed (--no-ktx path).
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import zlib from 'node:zlib';
import { Document, Logger, NodeIO } from '@gltf-transform/core';
import { prune } from '@gltf-transform/functions';
import { createIO, parseGlb, postprocessGlb } from './gltf-postprocess.mjs';

let work;
const budgets = {
  schema: 'xexoria.asset-budgets/1',
  defaults: { policy: { color0: 'RGB', max_uv_sets: 2, strip_unused_tangents: true, weld: true }, ktx: { jobs: 1 } },
  classes: { card: { profile: 'foliage', source: 'test', limits: { triangles: 8, draw_calls: 2, materials: 2, vertex_attributes: 8 } } },
};

function png(width, height, rgba) {
  const crc = (buf) => { const b = Buffer.alloc(4); b.writeUInt32BE(zlib.crc32(buf) >>> 0); return b; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type, 'ascii'), data]); return Buffer.concat([len, td, crc(td)]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = 6;
  const rows = [];
  for (let y = 0; y < height; y++) { rows.push(Buffer.from([0])); for (let x = 0; x < width; x++) rows.push(Buffer.from(rgba(x, y))); }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(rows))), chunk('IEND', Buffer.alloc(0))]);
}

/** One alpha-tested leaf card (2 triangles): the atlas texture reads TEXCOORD_0, TEXCOORD_1 carries wind (nothing reads it). */
function windCardDocument(wind) {
  const doc = new Document().setLogger(new Logger(Logger.Verbosity.SILENT));
  const buffer = doc.createBuffer();
  const acc = (type, array) => doc.createAccessor().setType(type).setArray(array).setBuffer(buffer);
  const atlas = doc.createTexture('leaf_atlas').setImage(png(8, 8, (x, y) => [60 + x * 16, 140 + y * 8, 50, 255])).setMimeType('image/png');
  const material = doc.createMaterial('leaf').setAlphaMode('MASK').setAlphaCutoff(0.5).setDoubleSided(true).setBaseColorTexture(atlas);
  const prim = doc.createPrimitive().setMaterial(material)
    .setIndices(acc('SCALAR', new Uint16Array([0, 1, 2, 0, 2, 3])))
    .setAttribute('POSITION', acc('VEC3', new Float32Array([-1, 0, 0, 1, 0, 0, 1, 2, 0, -1, 2, 0])))
    .setAttribute('NORMAL', acc('VEC3', new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1])))
    .setAttribute('TEXCOORD_0', acc('VEC2', new Float32Array([0, 0, 1, 0, 1, 1, 0, 1])))
    .setAttribute('TEXCOORD_1', acc('VEC2', new Float32Array(wind.flat())))
    .setAttribute('COLOR_0', acc('VEC3', new Float32Array(12).fill(0.8)));
  doc.createScene('card').addChild(doc.createNode('leaf_card').setMesh(doc.createMesh('leaf_card').addPrimitive(prim)));
  return doc;
}

const primitiveOf = (doc) => doc.getRoot().listMeshes()[0].listPrimitives()[0];
const readPairs = (accessor) => Array.from({ length: accessor.getCount() }, (_, i) => accessor.getElement(i, [0, 0]).slice())
  .sort((a, b) => a[0] - b[0] || a[1] - b[1]);

// Wind weights as the tree kit stores them: values outside [0,1] (the quantizer then keeps float32) and inside [0,1].
const cases = [
  ['out-of-range wind values stay float32 and bit-exact', [[-0.25, 0.1], [1.75, 0.2], [1.75, 1.2], [-0.25, 1.3]], 0],
  ['in-range wind values survive (quantized to 12 bits at most)', [[0.05, 0.1], [0.55, 0.2], [0.95, 0.6], [0.3, 0.9]], 1e-3],
];

before(() => { work = mkdtempSync(path.join(tmpdir(), 'xex-gltf-postprocess-attrs-')); });
after(() => { rmSync(work, { recursive: true, force: true }); });

for (const [label, wind, tolerance] of cases) {
  test(`prune keeps unread TEXCOORD_1 wind data: ${label}`, async () => {
    const input = path.join(work, `card-${tolerance}.glb`);
    await new NodeIO().write(input, windCardDocument(wind));
    const output = path.join(work, 'out', `card-${tolerance}.glb`);
    const io = (await createIO()).setLogger(new Logger(Logger.Verbosity.SILENT));
    const report = await postprocessGlb({ input, output, className: 'card', budgets, noKtx: true, textureOut: path.join(work, 'tex'), io });
    assert.equal(report.status, 'PASS', JSON.stringify(report.failures));

    // the written file still declares the wind set, and the atlas still reads TEXCOORD_0
    const { json } = parseGlb(readFileSync(output));
    const attributes = json.meshes[0].primitives[0].attributes;
    assert.notEqual(attributes.TEXCOORD_0, undefined);
    assert.notEqual(attributes.TEXCOORD_1, undefined, 'TEXCOORD_1 (wind data) must survive prune');
    assert.ok([undefined, 0].includes(json.materials[0].pbrMetallicRoughness.baseColorTexture.texCoord), 'atlas still on TEXCOORD_0');

    // the values survive meshopt decode (vertex order changes, so compare sorted pairs)
    const decoded = primitiveOf(await io.read(output)).getAttribute('TEXCOORD_1');
    assert.ok(decoded, 'TEXCOORD_1 decodes');
    const got = readPairs(decoded);
    const want = wind.map((pair) => pair.map(Math.fround)).sort((a, b) => a[0] - b[0] || a[1] - b[1]);   // accessors are float32
    assert.equal(got.length, want.length);
    for (const [i, pair] of want.entries()) for (const k of [0, 1]) assert.ok(Math.abs(got[i][k] - pair[k]) <= tolerance, `wind ${i}.${k}: ${got[i][k]} vs ${pair[k]}`);

    // the report agrees: the policy stripped nothing and the parity check lost no semantic
    assert.ok(!report.stripped_attributes.some((s) => s.attribute === 'TEXCOORD_1'));
    const parity = report.parity.find((p) => p.check === 'attribute_semantics_kept');
    assert.ok(parity.pass && parity.lost.length === 0 && parity.after.includes('TEXCOORD_1'), JSON.stringify(parity));
  });
}

test('negative control: glTF Transform prune() with default options deletes the unread TEXCOORD_1', async () => {
  const byDefault = windCardDocument(cases[1][1]);
  await byDefault.transform(prune());
  assert.equal(primitiveOf(byDefault).getAttribute('TEXCOORD_1'), null, 'default prune must drop it (this is why keepAttributes: true matters)');
  assert.ok(primitiveOf(byDefault).getAttribute('TEXCOORD_0'), 'the atlas UV set is kept either way');
  const kept = windCardDocument(cases[1][1]);
  await kept.transform(prune({ keepAttributes: true }));
  assert.ok(primitiveOf(kept).getAttribute('TEXCOORD_1'), 'keepAttributes: true keeps it');
});
