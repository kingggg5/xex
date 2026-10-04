import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Document } from '@gltf-transform/core';
import { quantize } from '@gltf-transform/functions';
import { documentFacts, PostprocessError, EXIT } from './gltf-postprocess.mjs';

function fixture({ inverseBind = true } = {}) {
  const doc = new Document();
  const buffer = doc.createBuffer();
  const acc = (type, values) => doc.createAccessor().setType(type).setArray(values).setBuffer(buffer);
  const joint = doc.createNode('joint').setTranslation([3, 2, -1]);
  const skin = doc.createSkin().addJoint(joint);
  if (inverseBind) skin.setInverseBindMatrices(acc('MAT4', new Float32Array([
    1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -3, -2, 1, 1,
  ])));
  const joints = acc('VEC4', new Uint16Array(12));
  const weights = acc('VEC4', new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]));
  const prim = doc.createPrimitive()
    .setAttribute('POSITION', acc('VEC3', new Float32Array([-0.4, 0, -0.2, 0.5, 0, 0.2, 0, 1.97, 0])))
    .setAttribute('JOINTS_0', joints).setAttribute('WEIGHTS_0', weights);
  const node = doc.createNode('body').setMesh(doc.createMesh().addPrimitive(prim)).setSkin(skin);
  // A skinned mesh-node transform cancels out of world skinning; do not apply it twice.
  node.setTranslation([100, 0, 0]);
  doc.createScene().addChild(joint).addChild(node);
  return { doc, joint, joints, weights, prim, node };
}

test('quantized skinned POSITION keeps metre-scale world bounds through inverse bind matrices', async () => {
  const { doc } = fixture();
  const before = documentFacts(doc).bounds;
  await doc.transform(quantize({ quantizePosition: 14, quantizeWeight: 8 }));
  const after = documentFacts(doc).bounds;
  assert.ok(Math.abs(after.max[1] - 1.97) < 0.0005);
  const deviation = Math.max(...before.min.map((v, i) => Math.abs(v - after.min[i])), ...before.max.map((v, i) => Math.abs(v - after.max[i])));
  assert.ok(deviation < 0.0005, `deviation ${deviation}`);
});

test('joint and inverse-bind corruption remains visible in world bounds', () => {
  const { doc, joint } = fixture();
  const before = documentFacts(doc).bounds;
  joint.setTranslation([3, 3, -1]);
  assert.ok(Math.abs(documentFacts(doc).bounds.max[1] - before.max[1] - 1) < 1e-6);
  const ibm = doc.getRoot().listSkins()[0].getInverseBindMatrices();
  const matrix = ibm.getElement(0, []); matrix[12] += 4; ibm.setElement(0, matrix);
  assert.ok(Math.abs(documentFacts(doc).bounds.min[0] - before.min[0] - 4) < 1e-6);
});

test('absent inverse bind matrices mean identity, and static mesh world transforms still apply', () => {
  const { doc, node } = fixture({ inverseBind: false });
  assert.deepEqual(documentFacts(doc).bounds, { min: [2.6, 2, -1.2], max: [3.5, 3.97, -0.8] });
  node.setSkin(null);
  assert.deepEqual(documentFacts(doc).bounds, { min: [99.6, 0, -0.2], max: [100.5, 1.97, 0.2] });
});

test('invalid skin indices and zero weight sums fail loudly', () => {
  const badJoint = fixture(); badJoint.joints.setElement(0, [2, 0, 0, 0]);
  assert.throws(() => documentFacts(badJoint.doc), e => e instanceof PostprocessError && e.exitCode === EXIT.POLICY && /joint index/.test(e.message));
  const badWeight = fixture(); badWeight.weights.setElement(0, [0, 0, 0, 0]);
  assert.throws(() => documentFacts(badWeight.doc), /zero skin weight sum/);
});
