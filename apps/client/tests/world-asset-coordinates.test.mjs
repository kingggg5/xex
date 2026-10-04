import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder.js';
import { Quaternion } from '@babylonjs/core/Maths/math.vector.js';
import { alignWorldAuthoredGlb } from '../src/world-asset-coordinates.mjs';

test('canonical world landmarks preserve X/Z despite the LH glTF loader root', () => {
	const engine = new NullEngine();
	const scene = new Scene(engine);
	try {
		const root = new Mesh('__root__', scene);
		root.rotationQuaternion = new Quaternion(0, 1, 0, 0);
		root.scaling.set(1, 1, -1);
		const west = MeshBuilder.CreateBox('west-marker', { size: 1 }, scene);
		west.parent = root;
		west.position.set(-18, 1.3, -98);
		const east = MeshBuilder.CreateBox('east-cart', { size: 1 }, scene);
		east.parent = root;
		east.position.set(30, 0.7, -103);
		west.computeWorldMatrix(true);
		assert.equal(west.getAbsolutePosition().x, 18);
		const loaded = { meshes: [root, west, east] };
		const closePosition = (mesh, expected) => {
			mesh.getAbsolutePosition().asArray().forEach((value, index) => {
				assert.ok(Math.abs(value - expected[index]) < 1e-6);
			});
		};
		alignWorldAuthoredGlb(loaded, scene);
		closePosition(west, [-18, 1.3, -98]);
		closePosition(east, [30, 0.7, -103]);
		alignWorldAuthoredGlb(loaded, scene);
		closePosition(west, [-18, 1.3, -98]);
	} finally { scene.dispose(); engine.dispose(); }
});
