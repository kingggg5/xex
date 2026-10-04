import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder.js';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { mergeStaticModel } from '../src/static-model.mjs';
import '@babylonjs/core/Meshes/instancedMesh.js';

test('static import preserves all primitives, transforms and materials without origin leftovers', () => {
  const engine = new NullEngine();
  const scene = new Scene(engine);
  try {
    const root = new TransformNode('gltf-root', scene);
    root.scaling.z = -1;
    const stem = MeshBuilder.CreateBox('stem', {size: 1}, scene);
    const leaves = MeshBuilder.CreateBox('leaves', {size: 2}, scene);
    stem.parent = root;
    leaves.parent = stem;
    leaves.position.set(0, 2, 1);
    stem.material = new StandardMaterial('wood', scene);
    leaves.material = new StandardMaterial('foliage', scene);
    const materials = [stem.material, leaves.material];
    const vertices = stem.getTotalVertices() + leaves.getTotalVertices();
    const merged = mergeStaticModel({meshes: [stem, leaves], transformNodes: [root], animationGroups: []}, 'tree');
    assert.equal(merged.getTotalVertices(), vertices);
    assert.equal(scene.meshes.length, 1);
    assert.equal(scene.transformNodes.length, 0);
    assert.equal(merged.isVisible, false);
    assert.equal(merged.material.subMaterials.length, 2);
    assert.ok(merged.material.subMaterials.every((material, index) => material === materials[index]));
    merged.computeWorldMatrix(true);
    assert.equal(merged.getBoundingInfo().boundingBox.maximumWorld.y, 3);
    assert.equal(merged.getBoundingInfo().boundingBox.minimumWorld.z, -2);
    const instance = merged.createInstance('placed-tree');
    instance.position.x = 10;
    instance.computeWorldMatrix(true);
    assert.equal(instance.isVisible, true);
    assert.equal(instance.getBoundingInfo().boundingBox.minimumWorld.x, 9);
    assert.ok(materials.every(material => scene.materials.includes(material)));
  } finally { scene.dispose(); engine.dispose(); }
});

/** Sign of dot(triangle winding normal, vertex normal) for every triangle: winding and normals must agree. */
function windingSigns(mesh) {
  const positions = mesh.getVerticesData('position');
  const normals = mesh.getVerticesData('normal');
  const indices = mesh.getIndices();
  const signs = new Set();
  for (let t = 0; t < indices.length; t += 3) {
    const [a, b, c] = [indices[t], indices[t + 1], indices[t + 2]].map(i => i * 3);
    const u = [positions[b] - positions[a], positions[b + 1] - positions[a + 1], positions[b + 2] - positions[a + 2]];
    const v = [positions[c] - positions[a], positions[c + 1] - positions[a + 1], positions[c + 2] - positions[a + 2]];
    const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    signs.add(Math.sign(n[0] * normals[a] + n[1] * normals[a + 1] + n[2] * normals[a + 2]));
  }
  return [...signs];
}

test('a single mirrored glTF part keeps front-face winding consistent with its normals', () => {
  const engine = new NullEngine();
  const scene = new Scene(engine);
  try {
    const reference = MeshBuilder.CreateBox('reference', {size: 1}, scene);
    const expected = windingSigns(mergeStaticModel({meshes: [reference], transformNodes: [], animationGroups: []}, 'reference'));
    assert.equal(expected.length, 1);
    const root = new TransformNode('gltf-root', scene);
    root.scaling.z = -1;
    const part = MeshBuilder.CreateBox('canopy', {size: 1}, scene);
    part.parent = root;
    const merged = mergeStaticModel({meshes: [part], transformNodes: [root], animationGroups: []}, 'single-mirrored');
    assert.deepEqual(windingSigns(merged), expected, 'single mirrored part must not be inside-out');
    const root2 = new TransformNode('gltf-root-2', scene);
    root2.scaling.z = -1;
    const a = MeshBuilder.CreateBox('trunk', {size: 1}, scene);
    const b = MeshBuilder.CreateBox('leaves', {size: 1}, scene);
    a.parent = root2; b.parent = root2; b.position.y = 2;
    assert.deepEqual(windingSigns(mergeStaticModel({meshes: [a, b], transformNodes: [root2], animationGroups: []}, 'multi-mirrored')), expected, 'multi-part merge stays consistent');
  } finally { scene.dispose(); engine.dispose(); }
});
