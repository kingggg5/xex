import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { SceneLoader } from '@babylonjs/core/Loading/sceneLoader.js';
import { Scene } from '@babylonjs/core/scene.js';
import '@babylonjs/core/Meshes/instancedMesh.js';
import '@babylonjs/loaders/glTF/2.0/index.js';

const asset = new URL('../src/assets/models/prop_wayfarer_kit.glb', import.meta.url);
const expectedHeights = {
  prop_wayfinder_sign_01: 2.12,
  prop_village_banner_01: 2.28,
  prop_flower_planter_01: 0.70,
};

test('wayfarer kit GLB has three grounded, vertex-painted props within the mobile budget', () => {
  const bytes = readFileSync(asset);
  assert.ok(bytes.length < 160 * 1024, 'kit must stay below 160 KiB');
  assert.equal(bytes.toString('ascii', 0, 4), 'glTF');
  assert.equal(bytes.readUInt32LE(4), 2);
  assert.equal(bytes.readUInt32LE(8), bytes.length);
  const jsonLength = bytes.readUInt32LE(12);
  assert.equal(bytes.toString('ascii', 16, 20), 'JSON');
  const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString('utf8').trim());
  assert.equal(gltf.asset.version, '2.0');
  assert.equal(gltf.materials.length, 1);
  assert.equal(gltf.images?.length ?? 0, 0);
  assert.equal(gltf.textures?.length ?? 0, 0);
  assert.deepEqual(gltf.meshes.map((mesh) => mesh.name).sort(), Object.keys(expectedHeights).sort());
  assert.equal(gltf.nodes.filter((node) => node.mesh !== undefined).length, 3);

  for (const [name, height] of Object.entries(expectedHeights)) {
    const meshIndex = gltf.meshes.findIndex((mesh) => mesh.name === name);
    const mesh = gltf.meshes[meshIndex];
    assert.equal(mesh.primitives.length, 1, `${name} must use one draw primitive`);
    const [primitive] = mesh.primitives;
    assert.equal(primitive.mode ?? 4, 4);
    assert.equal(primitive.material, 0);
    assert.ok(primitive.attributes.NORMAL !== undefined);
    assert.ok(primitive.attributes.COLOR_0 !== undefined);
    const position = gltf.accessors[primitive.attributes.POSITION];
    assert.equal(gltf.accessors[primitive.attributes.COLOR_0].count, position.count);
    const triangleCount = gltf.accessors[primitive.indices].count / 3;
    assert.ok(Number.isInteger(triangleCount) && triangleCount > 0 && triangleCount <= 1500, name);
    assert.ok(Math.abs(position.min[1]) < 0.002, `${name} must sit on its base pivot`);
    assert.ok(Math.abs(position.max[1] - height) < 0.01, `${name} has an unexpected height`);
    for (const axis of [0, 2]) {
      assert.ok(position.min[axis] < 0 && position.max[axis] > 0, `${name} pivot must be inside its footprint`);
    }
    const nodes = gltf.nodes.filter((node) => node.mesh === meshIndex && node.name === name);
    assert.equal(nodes.length, 1, `${name} must have one untransformed placement node`);
    assert.equal(nodes[0].translation, undefined);
    assert.equal(nodes[0].rotation, undefined);
    assert.equal(nodes[0].scale, undefined);
  }
});

test('Babylon places hidden-source wayfarer instances outside the starter path', async () => {
  const engine = new NullEngine();
  const scene = new Scene(engine);
  try {
    const bytes = readFileSync(asset);
    const loaded = await SceneLoader.ImportMeshAsync('', '', new Uint8Array(bytes), scene, undefined, '.glb');
    for (const name of Object.keys(expectedHeights)) {
      const source = loaded.meshes.find((mesh) => mesh.name === name);
      assert.ok(source, `Babylon must load ${name} by its authored name`);
      source.isVisible = false;
      for (const x of [-4.8, 4.8]) {
        const instance = source.createInstance(`${name}-${x}`);
        instance.setAbsolutePosition(new Vector3(x, 0, -15.5));
        instance.computeWorldMatrix(true);
        const bounds = instance.getBoundingInfo().boundingBox;
        assert.equal(instance.isVisible, true);
        assert.ok(Math.abs(instance.absolutePosition.x - x) < 0.001, `${name} must remain at its world-space X`);
        assert.ok(bounds.minimumWorld.y >= -0.002, `${name} must stand on the ground`);
        assert.ok(x < 0 ? bounds.maximumWorld.x < -3.2 : bounds.minimumWorld.x > 3.2,
          `${name} must clear the 3.2 m half-width starter path`);
      }
    }
  } finally {
    scene.dispose();
    engine.dispose();
  }
});
