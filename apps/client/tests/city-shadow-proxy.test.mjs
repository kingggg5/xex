import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder.js';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial.js';
import { MultiMaterial } from '@babylonjs/core/Materials/multiMaterial.js';
import { SubMesh } from '@babylonjs/core/Meshes/subMesh.js';
import { DirectionalLight } from '@babylonjs/core/Lights/directionalLight.js';
import { ShadowGenerator } from '@babylonjs/core/Lights/Shadows/shadowGenerator.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture.js';
import { createCityShadowProxy, planCityShadowProxy } from '../src/city-shadow-proxy.mjs';
import '@babylonjs/core/Meshes/Builders/boxBuilder.js';
const PIN='95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72';
function fixture(run) {
  const engine=new NullEngine(),scene=new Scene(engine);
  const camera=new FreeCamera('camera',new Vector3(0,3,-8),scene);camera.setTarget(Vector3.Zero());
  const source=MeshBuilder.CreateBox('reference-city-merged',{size:2},scene);
  const a=new StandardMaterial('stone',scene),b=new StandardMaterial('timber',scene),multi=new MultiMaterial('city',scene);
  multi.subMaterials=[a,b];source.material=multi;source.releaseSubMeshes();
  new SubMesh(0,0,source.getTotalVertices(),0,18,source);new SubMesh(1,0,source.getTotalVertices(),18,18,source);
  const light=new DirectionalLight('sun',new Vector3(-1,-2,1),scene),shadows=new ShadowGenerator(32,light);
  shadows.addShadowCaster(source,false);
  const options={expectedSourceName:source.name,runtimeSha256:PIN,createMesh:(n,s)=>new Mesh(n,s),createMaterial:(n,s)=>new StandardMaterial(n,s)};
  try{return run({engine,scene,camera,source,a,b,multi,shadows,options});}finally{scene.dispose();engine.dispose();}
}

test('actual NullEngine explicit shadow target admits layer0 proxy; main camera excludes it',()=>fixture(({scene,camera,source,shadows,options})=>{
  const p=createCityShadowProxy(source,options),map=shadows.getShadowMap();
  assert.equal(p.mesh.subMeshes.length,1);assert.equal(p.mesh.isEnabled(),false);
  p.bind(shadows);assert.deepEqual(map.renderList.map(m=>m.name),[p.mesh.name]);assert.equal(map.forceLayerMaskCheck,false);
  scene.render();map.render(false,false);
  assert.equal(p.mesh.layerMask&camera.layerMask,0);
  assert.ok(!scene.getActiveMeshes().data.includes(p.mesh));
  assert.ok(map._objectRenderer._activeMeshes.data.includes(p.mesh),'real RTT active-mesh path must retain shadow-only proxy');
  p.dispose();assert.deepEqual(map.renderList.map(m=>m.name),[source.name]);
}));

test('source geometry/materials/textures/world remain intact; proxy owns and releases only its resources',()=>fixture(({scene,source,a,shadows,options})=>{
  const texture=RawTexture.CreateRGBATexture(new Uint8Array([1,2,3,255]),1,1,scene,false,false);a.diffuseTexture=texture;
  source.position.set(3,4,5);source.rotation.y=.4;source.scaling.set(-1,1,1);
  const before={p:Array.from(source.getVerticesData('position')),n:Array.from(source.getVerticesData('normal')),i:Array.from(source.getIndices()),
    m:source.material,subs:source.subMeshes.slice(),world:source.computeWorldMatrix(true).clone(),layer:source.layerMask};
  const p=createCityShadowProxy(source,options);p.bind(shadows);
  assert.ok(p.mesh.getWorldMatrix().equals(before.world));assert.notEqual(p.mesh.geometry,source.geometry);
  p.dispose();p.dispose();assert.equal(p.mesh.isDisposed(),true);assert.ok(!scene.materials.includes(p.material));
  assert.deepEqual(Array.from(source.getVerticesData('position')),before.p);assert.deepEqual(Array.from(source.getVerticesData('normal')),before.n);
  assert.deepEqual(Array.from(source.getIndices()),before.i);assert.equal(source.material,before.m);assert.deepEqual(source.subMeshes,before.subs);
  assert.equal(source.layerMask,before.layer);assert.equal(source.isVisible,true);assert.equal(source.isEnabled(),true);
  assert.ok(!a.isDisposed);assert.ok(scene.textures.includes(texture));assert.equal(a.diffuseTexture,texture);
}));

test('transparent residual stays on original caster; only copied opaque ranges are filtered, existing callback is chained',()=>fixture(({source,b,shadows,options})=>{
  b.alpha=.6;let calls=0;const prior=()=>{calls++;return true;};shadows.customAllowRendering=prior;
  const p=createCityShadowProxy(source,options);assert.equal(p.diagnostics.proxyTriangles,6);assert.equal(p.diagnostics.residualSubMeshes,1);
  p.bind(shadows);assert.deepEqual(shadows.getShadowMap().renderList.map(m=>m.name),[source.name,p.mesh.name]);
  assert.equal(shadows.customAllowRendering(source.subMeshes[0]),false);assert.equal(shadows.customAllowRendering(source.subMeshes[1]),true);
  assert.equal(shadows.customAllowRendering(p.mesh.subMeshes[0]),true);assert.equal(calls,2);
  p.dispose();assert.equal(shadows.customAllowRendering,prior);assert.deepEqual(shadows.getShadowMap().renderList.map(m=>m.name),[source.name]);
}));

test('invalid coverage, nonfinite and alpha-test data never allocate proxy resources',()=>fixture(({scene,source,b,options})=>{
  const counts=[scene.meshes.length,scene.materials.length];source.subMeshes[1].indexStart=15;
  assert.throws(()=>createCityShadowProxy(source,options),/coverage/);source.subMeshes[1].indexStart=18;
  const positions=source.getVerticesData('position');positions[0]=NaN;assert.throws(()=>createCityShadowProxy(source,options),/Nonfinite/);
  positions[0]=-1;assert.deepEqual([scene.meshes.length,scene.materials.length],counts);
  b.needAlphaTestingForMesh=()=>true;const plan=planCityShadowProxy(source);assert.equal(plan.residualSubMeshes.length,1);
}));

test('changed prepared geometry, unrevealed source and masked target reject binding without caster mutation',()=>fixture(({source,shadows,options})=>{
  const p=createCityShadowProxy(source,options),map=shadows.getShadowMap();source.isVisible=false;
  assert.throws(()=>p.bind(shadows),/revealed/);source.isVisible=true;map.forceLayerMaskCheck=true;
  assert.throws(()=>p.bind(shadows),/unmasked/);map.forceLayerMaskCheck=false;
  source.position.x=1;assert.throws(()=>p.bind(shadows),/world changed/);source.position.x=0;
  source.getVerticesData('position')[0]+=.1;assert.throws(()=>p.bind(shadows),/geometry\/world changed/);
  assert.deepEqual(map.renderList.map(m=>m.name),[source.name]);assert.equal(p.mesh.isEnabled(),false);p.dispose();
}));

test('profile shadow-generator replacement and source disposal leave no orphan caster or material',()=>fixture(({scene,source,shadows,options})=>{
  const p=createCityShadowProxy(source,options);p.bind(shadows);p.bind(shadows);
  const next=new ShadowGenerator(32,new DirectionalLight('other-sun',new Vector3(1,-2,1),scene));
  next.getShadowMap().renderList=shadows.getShadowMap().renderList.slice();p.bind(next);
  assert.deepEqual(next.getShadowMap().renderList.map(m=>m.name),[p.mesh.name]);
  source.dispose(false,false);assert.equal(p.mesh.isDisposed(),true);assert.ok(!scene.materials.includes(p.material));
  assert.deepEqual(next.getShadowMap().renderList.map(m=>m.name),[]);assert.deepEqual(shadows.getShadowMap().renderList.map(m=>m.name),[]);
}));
