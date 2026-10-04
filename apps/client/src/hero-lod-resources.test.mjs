import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture.js';
import {Texture} from '@babylonjs/core/Materials/Textures/texture.js';
import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {MultiMaterial} from '@babylonjs/core/Materials/multiMaterial.js';
import {AnimationGroup} from '@babylonjs/core/Animations/animationGroup.js';
import {Animation} from '@babylonjs/core/Animations/animation.js';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode.js';
import {Skeleton} from '@babylonjs/core/Bones/skeleton.js';
import {Bone} from '@babylonjs/core/Bones/bone.js';
import {Matrix} from '@babylonjs/core/Maths/math.vector.js';
import {optimizeHeroLodResources} from './hero-lod-resources.mjs';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
const setup=()=>{const engine=new NullEngine();return{engine,scene:new Scene(engine),close(){engine.dispose();}};};
function image(scene,bytes,name){
 const texture=RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene,false,false,Texture.NEAREST_SAMPLINGMODE);
 texture.name=name;
 // NullEngine performs no GPU upload; explicitly admit readiness for this CPU lifecycle fixture.
 texture.getInternalTexture().isReady=true;
 // Fixture encoded-image views exercise SHA identity without a browser/GPU decoder.
 const backing=new Uint8Array([9,...bytes,8]);texture._buffer=backing.subarray(1,backing.length-1);return texture;
}
const asset=material=>({meshes:[{material}],animationGroups:[]});
test('identical encoded views and settings share albedo/ORM, rebind every alias before disposal, retain normals',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene),outside=new PBRMaterial('other-owner',ctx.scene);
  const color=image(ctx.scene,[1,2,3],'same-bytes-different-name0'),duplicate=image(ctx.scene,[1,2,3],'same-bytes-different-name1');
  const orm=image(ctx.scene,[4,5],'orm0'),ormDuplicate=image(ctx.scene,[4,5],'orm1');
  const normal0=image(ctx.scene,[6],'normal0'),normal1=image(ctx.scene,[7],'normal1');
  a.albedoTexture=color;b.albedoTexture=duplicate;outside.albedoTexture=duplicate;
  a.metallicTexture=a.ambientTexture=orm;b.metallicTexture=b.ambientTexture=ormDuplicate;
  a.bumpTexture=normal0;b.bumpTexture=normal1;
  const duplicateObserver=duplicate.onDisposeObservable.add(()=>{assert.ok(b.albedoTexture===color);assert.ok(outside.albedoTexture===color);});
  const ormObserver=ormDuplicate.onDisposeObservable.add(()=>{assert.ok(b.metallicTexture===orm);assert.ok(b.ambientTexture===orm);});
  let report;try{report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);}finally{duplicate.onDisposeObservable.remove(duplicateObserver);ormDuplicate.onDisposeObservable.remove(ormObserver);}
  assert.equal(report.texturesDisposed,2);assert.equal(report.bindingsReplaced,4);assert.equal(report.after.uniqueInternalTextures,report.before.uniqueInternalTextures-2);
  assert.equal(a.bumpTexture,normal0);assert.equal(b.bumpTexture,normal1);assert(normal1.getInternalTexture());assert(color.getInternalTexture());
  assert.equal(report.hardwareMemoryMeasured,false);assert.equal(report.shared[0].imageSha256.length,64);
 }finally{ctx.close();}
});
test('same filenames or changed UV/sampler/gamma/level never establish image compatibility',async()=>{
 for(const alter of ['bytes','uv','sampler','gamma','level']){
  const ctx=setup();try{
   const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene);
   a.albedoTexture=image(ctx.scene,[1,2],'same-name');b.albedoTexture=image(ctx.scene,alter==='bytes'?[3,4]:[1,2],'same-name');
   if(alter==='uv')b.albedoTexture.uOffset=.25;if(alter==='sampler')b.albedoTexture.wrapU=Texture.WRAP_ADDRESSMODE;
   if(alter==='gamma')b.albedoTexture.gammaSpace=!a.albedoTexture.gammaSpace;if(alter==='level')b.albedoTexture.level=.5;
   const old=b.albedoTexture,report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);
   assert.equal(report.texturesDisposed,0,alter);assert.equal(b.albedoTexture,old);assert(old.getInternalTexture());
  }finally{ctx.close();}
 }
});
test('unknown or unsupported material owner preserves the duplicate resource',async()=>{
 for(const ownerKind of ['standard','bump','extension']){
  const ctx=setup();try{
   const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene);a.albedoTexture=image(ctx.scene,[1],'base');b.albedoTexture=image(ctx.scene,[1],'duplicate');
   const original=b.albedoTexture;
   if(ownerKind==='standard'){const owner=new StandardMaterial('foreign',ctx.scene);owner.diffuseTexture=original;}
   if(ownerKind==='bump')b.bumpTexture=original;
   if(ownerKind==='extension'){b.clearCoat.isEnabled=true;b.clearCoat.texture=original;}
   const report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);
   assert.equal(report.texturesDisposed,0,ownerKind);assert.equal(b.albedoTexture,original);assert(original.getInternalTexture());
  }finally{ctx.close();}
 }
});
test('MultiMaterial children are rebound while child flags/factors remain unchanged',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('body',ctx.scene),b=new PBRMaterial('cloth',ctx.scene),multi=new MultiMaterial('aggregate',ctx.scene);
  a.albedoTexture=image(ctx.scene,[1],'a');b.albedoTexture=image(ctx.scene,[1],'b');b.backFaceCulling=false;b.metallic=.1;b.roughness=.8;multi.subMaterials=[b];
  const report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(multi)]);
  assert.equal(report.texturesDisposed,1);assert.equal(b.albedoTexture,a.albedoTexture);assert.equal(b.backFaceCulling,false);assert.equal(b.metallic,.1);assert.equal(b.roughness,.8);
 }finally{ctx.close();}
});
test('disposes only dormant lower groups, preserving base animation targets and all skeletons/nodes',async()=>{
 const ctx=setup();try{
  const base=new AnimationGroup('shared-name',ctx.scene),lower=new AnimationGroup('shared-name',ctx.scene),node=new TransformNode('joint',ctx.scene);
  const animation=new Animation('pose','rotation.x',30,Animation.ANIMATIONTYPE_FLOAT,Animation.ANIMATIONLOOPMODE_CYCLE);animation.setKeys([{frame:0,value:0},{frame:30,value:1}]);
  base.addTargetedAnimation(animation,node);lower.addTargetedAnimation(animation,node);
  const skeleton=new Skeleton('source-rig','s0',ctx.scene);new Bone('core',skeleton,null,Matrix.Identity());
  const report=await optimizeHeroLodResources(ctx.scene,{meshes:[],animationGroups:[base]},[{meshes:[],animationGroups:[base,lower,lower]}]);
  assert.equal(report.lowerGroupsDisposed,1);assert.equal(ctx.scene.animationGroups.length,1);assert.equal(base.targetedAnimations.length,1);assert.equal(lower.targetedAnimations.length,0);
  assert.equal(ctx.scene.skeletons.length,1);assert.equal(skeleton.bones.length,1);assert.equal(node.isDisposed(),false);
 }finally{ctx.close();}
});
test('missing encoded buffers and animated textures are retained; repeated cleanup is safe',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene);a.albedoTexture=image(ctx.scene,[1],'a');b.albedoTexture=image(ctx.scene,[1],'b');
  b.albedoTexture._buffer=null;let report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);assert.equal(report.texturesDisposed,0);
  b.albedoTexture._buffer=new Uint8Array([1]);b.albedoTexture.animations=[{}];report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);assert.equal(report.texturesDisposed,0);
  b.albedoTexture.animations=[];report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);assert.equal(report.texturesDisposed,1);
  report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);assert.equal(report.texturesDisposed,0);
 }finally{ctx.close();}
});
test('all14 base clips survive retiring28 lower clips; unrelated scene animation is protected',async()=>{
 const ctx=setup();try{
  const node=new TransformNode('base-joint',ctx.scene),baseGroups=[],lowGroups=[];
  for(let i=0;i<14;i++){
   const animation=new Animation(`curve-${i}`,'rotation.x',30,Animation.ANIMATIONTYPE_FLOAT);animation.setKeys([{frame:0,value:0},{frame:1,value:1}]);
   const base=new AnimationGroup(`clip-${i}`,ctx.scene);base.addTargetedAnimation(animation,node);baseGroups.push(base);
   for(let lod=0;lod<2;lod++){const lower=new AnimationGroup(`clip-${i}`,ctx.scene);lower.addTargetedAnimation(animation,node);lowGroups.push(lower);}
  }
  const other=new AnimationGroup('outside',ctx.scene);const report=await optimizeHeroLodResources(ctx.scene,{meshes:[],animationGroups:baseGroups},[{meshes:[],animationGroups:lowGroups}]);
  assert.equal(report.lowerGroupsDisposed,28);assert.equal(ctx.scene.animationGroups.length,15);assert(ctx.scene.animationGroups.includes(other));
  assert(baseGroups.every(group=>group.targetedAnimations.length===1));assert.equal(node.isDisposed(),false);
 }finally{ctx.close();}
});
test('binding failure rolls back already rebound owners and disposes no texture',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene),foreign=new PBRMaterial('setter-owner',ctx.scene);
  a.albedoTexture=image(ctx.scene,[1],'base');const duplicate=image(ctx.scene,[1],'low');b.albedoTexture=foreign.albedoTexture=duplicate;
  Object.defineProperty(foreign,'albedoTexture',{get:()=>duplicate,set:()=>{throw new Error('fixture setter failure');}});
  await assert.rejects(optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]),/fixture setter failure/);
  assert.ok(b.albedoTexture===duplicate);assert.ok(foreign.albedoTexture===duplicate);assert(duplicate.getInternalTexture());
 }finally{ctx.close();}
});
test('a texture without completed upload cannot be disposed or rebound',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene);a.albedoTexture=image(ctx.scene,[1],'a');b.albedoTexture=image(ctx.scene,[1],'b');
  b.albedoTexture.getInternalTexture().isReady=false;const old=b.albedoTexture;const report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);
  assert.equal(report.texturesDisposed,0);assert.ok(b.albedoTexture===old);
 }finally{ctx.close();}
});
test('settings changed while image proof is gathered are rechecked before rebinding',async()=>{
 const ctx=setup();try{
  const a=new PBRMaterial('base',ctx.scene),b=new PBRMaterial('low',ctx.scene);a.albedoTexture=image(ctx.scene,[1],'a');b.albedoTexture=image(ctx.scene,[1],'b');
  const old=b.albedoTexture;let buffer=old._buffer,changed=false;
  Object.defineProperty(old,'_buffer',{get(){if(!changed){changed=true;old.uOffset=.2;}return buffer;},set(value){buffer=value;}});
  const report=await optimizeHeroLodResources(ctx.scene,asset(a),[asset(b)]);
  assert.equal(report.texturesDisposed,0);assert.ok(b.albedoTexture===old);assert(old.getInternalTexture());
 }finally{ctx.close();}
});
