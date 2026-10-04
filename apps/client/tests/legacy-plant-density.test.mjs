import assert from 'node:assert/strict';
import {test} from 'node:test';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {applyLegacyPlantDensity} from '../src/legacy-plant-density.mjs';

test('actual Babylon global-to-partial plant range retains transformed bounds and restores full geometry',()=>{
 const engine=new NullEngine();const scene=new Scene(engine);
 try{
  const plant=MeshBuilder.CreateBox('plant',{},scene);plant.position.set(7,2,-9);plant.computeWorldMatrix(true);
  const sub=plant.subMeshes[0],full=sub.indexCount;
  assert.ok(sub.IsGlobal&&sub.getBoundingInfo());
  sub.indexCount=full/2;
  assert.equal(sub.getBoundingInfo(),undefined,'installed engine reproduces the transparent-sort failure');
  const originals=new WeakMap([[sub,full]]);
  sub.indexCount=full;
  applyLegacyPlantDensity(plant,.5,originals);
  assert.ok(!sub.IsGlobal&&sub.getBoundingInfo()?.boundingSphere);
  assert.ok(Vector3.Distance(sub.getBoundingInfo().boundingSphere.centerWorld,plant.position)<1e-6);
  applyLegacyPlantDensity(plant,.25,originals);
  assert.equal(sub.indexCount,9);assert.ok(sub.getBoundingInfo().boundingSphere);
  applyLegacyPlantDensity(plant,1,originals);
  assert.equal(sub.indexCount,full);assert.ok(sub.IsGlobal&&sub.getBoundingInfo().boundingSphere);
 }finally{scene.dispose();engine.dispose();}
});
