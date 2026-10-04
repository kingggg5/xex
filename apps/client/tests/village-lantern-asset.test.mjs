import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const asset = new URL('../src/assets/models/prop_village_lantern_01.glb', import.meta.url);

test('village lantern GLB has a base pivot, painted material, and bounded geometry', () => {
  const bytes = readFileSync(asset);
  assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
  assert.equal(bytes.readUInt32LE(4), 2);
  assert.equal(bytes.readUInt32LE(8), bytes.length);
  const jsonLength = bytes.readUInt32LE(12);
  assert.equal(bytes.toString('ascii', 16, 20), 'JSON');
  const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
  assert.equal(gltf.asset.version, '2.0');
  assert.equal(gltf.meshes.length, 1);
  assert.equal(gltf.materials.length, 1);
  assert.equal(gltf.images?.length ?? 0, 0);
  assert.equal(gltf.nodes.filter((node) => node.mesh !== undefined).length, 1);

  const [primitive] = gltf.meshes[0].primitives;
  assert.equal(gltf.meshes[0].primitives.length, 1);
  assert.equal(primitive.mode ?? 4, 4); // triangles
  assert.ok(primitive.attributes.NORMAL !== undefined);
  assert.ok(primitive.attributes.COLOR_0 !== undefined);
  const position = gltf.accessors[primitive.attributes.POSITION];
  assert.equal(gltf.accessors[primitive.attributes.COLOR_0].count, position.count);
  const triangleCount = gltf.accessors[primitive.indices].count / 3;
  assert.ok(Number.isInteger(triangleCount) && triangleCount > 0 && triangleCount <= 1500);

  assert.ok(Math.abs(position.min[1]) < 0.001, 'pivot must sit at ground level');
  assert.ok(Math.abs(position.max[1] - 1.2) < 0.001, 'height must be 1.2 m');
  for (const axis of [0, 2]) {
    assert.ok(position.min[axis] >= -0.32 && position.max[axis] <= 0.32);
  }
});
