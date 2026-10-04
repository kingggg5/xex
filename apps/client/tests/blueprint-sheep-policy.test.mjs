import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,unlinkSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';

const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';
export {TransformNode} from '@babylonjs/core/Meshes/transformNode';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {Frustum} from '@babylonjs/core/Maths/math.frustum';
export {LoadAssetContainerAsync} from '@babylonjs/core/Loading/sceneLoader';
export {createSheepActor,createSheepVisibilityPolicy,SHEEP_DISTANCE_LIMIT_M} from './src/blueprint-sheep-policy';
export {createBlueprintSheep} from './src/blueprint-sheep';
export {registerWeatherReader} from './src/ambient-weather-channel';
export {DirectionalLight} from '@babylonjs/core/Lights/directionalLight';
export {ShadowGenerator} from '@babylonjs/core/Lights/Shadows/shadowGenerator';
import '@babylonjs/core/Meshes/instancedMesh';
import '@babylonjs/loaders/glTF';`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},
 bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',plugins:[{name:'sheep-test-asset-urls',setup(build){
  build.onLoad({filter:/blueprint-sheep\.ts$/},async({path})=>({loader:'ts',contents:readFileSync(path,'utf8').replace(
   /const urls=import\.meta\.glob\([\s\S]*?as Record<string,string>;/,'const urls=globalThis.__sheepTestUrls;')}));
 }}]});
globalThis.__sheepTestUrls=Object.fromEntries([0,1,2].map(lod=>[
 `../../../assets/models/blueprint-cc0/candidates/sheep-v1/r03/runtime/blueprint_cc0_sheep_lod${lod}.meshopt.glb`,
 new Uint8Array(readFileSync(new URL(`../../../assets/models/blueprint-cc0/candidates/sheep-v1/r03/source/blueprint_cc0_sheep_lod${lod}.glb`,import.meta.url)))
]));
const bundleUrl=new URL(`../../../planning/evidence/spawn-perf-gate-20261004/sheep/sheep-test-bundle-${process.pid}.mjs`,import.meta.url);
mkdirSync(fileURLToPath(new URL('.',bundleUrl)),{recursive:true});writeFileSync(bundleUrl,bundled.outputFiles[0].text);
let api;
try {api=await import(bundleUrl.href);} finally {unlinkSync(bundleUrl);}
async function fixture(run,lod=0) {
 const engine=new api.NullEngine({renderWidth:1280,renderHeight:720,textureSize:32}),scene=new api.Scene(engine);
 const camera=new api.FreeCamera('sheep-test-camera',new api.Vector3(0,.5,-8),scene);
 camera.setTarget(new api.Vector3(0,.5,0));camera.minZ=.1;camera.maxZ=200;scene.activeCamera=camera;
 const bytes=readFileSync(new URL(`../../../assets/models/blueprint-cc0/candidates/sheep-v1/r03/source/blueprint_cc0_sheep_lod${lod}.glb`,import.meta.url));
 const container=await api.LoadAssetContainerAsync(new Uint8Array(bytes),scene,{pluginExtension:'.glb'});
 for(const group of container.animationGroups)group.stop();
 const entries=[],actors=[];
 for(let i=0;i<6;i++) {
  const entry=container.instantiateModelsToScene(name=>`sheep-${i}-${name}`,false,{doNotInstantiate:true});entries.push(entry);
  for(const group of entry.animationGroups)group.stop();
  const root=new api.TransformNode(`sheep-${i}`,scene);root.position.x=i*2;
  for(const node of entry.rootNodes)node.parent=root;
  const idle=entry.animationGroups.find(group=>group.name.endsWith('Idle'));assert.ok(idle);
  idle.start(true);idle.pause();actors.push(api.createSheepActor(root,idle,i));
 }
 const policy=api.createSheepVisibilityPolicy(scene,actors);
 try {await run({engine,scene,camera,container,entries,actors,policy});}
 finally {for(const entry of entries)entry.dispose();for(const actor of actors)actor.root.dispose();container.dispose();scene.dispose();engine.dispose();}
}

for(const lod of [0,1,2])test(`original sheep LOD${lod} skins, clips and full bounds survive; idle stays inside cached envelope`,async()=>fixture(({entries,actors})=>{
 assert.equal(entries.length,6);assert.ok(entries.every(entry=>entry.skeletons.length===1));
 assert.ok(entries.every(entry=>entry.animationGroups.length===6));
 const actor=actors[0],meshes=actor.root.getChildMeshes().filter(mesh=>mesh.getTotalVertices()>0);
 assert.ok(meshes.every(mesh=>mesh.skeleton));
 const box=actor.bounds.boundingBox;
 for(let frame=actor.idle.from;frame<=actor.idle.to;frame++) {
  actor.idle.goToFrame(frame);
  for(const node of actor.root.getDescendants())node.computeWorldMatrix(true);
  for(const mesh of meshes) {
   mesh.skeleton.prepare(true);mesh.refreshBoundingInfo({applySkeleton:true});mesh.computeWorldMatrix(true);
   const b=mesh.getBoundingInfo().boundingBox;
   for(const key of ['x','y','z']) {
    assert.ok(b.minimumWorld[key]>=box.minimumWorld[key]-1e-5,`idle min ${key} at ${frame}`);
    assert.ok(b.maximumWorld[key]<=box.maximumWorld[key]+1e-5,`idle max ${key} at ${frame}`);
   }
  }
 }
},lod));

test('distance cutoff is inclusive at 45 m, freezes hidden bone targets, and reenters at current shared time',async()=>fixture(({scene,camera,actors,policy})=>{
 const actor=actors[0],center=actor.bounds.boundingSphere.centerWorld;
 const move=distance=>{camera.position.set(center.x,center.y,center.z-distance);camera.setTarget(center);};
 move(45);policy.update(1000);assert.equal(actor.root.isEnabled(),true);
 const targets=actor.idle.targetedAnimations.map(t=>t.target);
 const pose=targets.map(t=>Array.from(t.getWorldMatrix().m));
 const seeks=policy.stats.poseUpdates;
 move(45.001);policy.update(3000);assert.equal(actor.root.isEnabled(),false);
 assert.equal(policy.stats.animatedCount,0);assert.equal(policy.stats.poseUpdates,seeks);
 assert.deepEqual(targets.map(t=>Array.from(t.getWorldMatrix().m)),pose);
 assert.ok(actor.root.getChildMeshes().every(mesh=>!mesh.isEnabled()));
 let prepares=0;
 const originalPrepares=scene.skeletons.map(skeleton=>skeleton.prepare);
 for(const skeleton of scene.skeletons) {
  const prepare=skeleton.prepare.bind(skeleton);
  skeleton.prepare=(...args)=>{prepares++;return prepare(...args);};
 }
 scene.render(false);assert.equal(prepares,0,'disabled sheep never enter actual scene skeleton preparation');
 scene.skeletons.forEach((skeleton,index)=>{skeleton.prepare=originalPrepares[index];});
 move(8);policy.update(5000);
 assert.equal(actor.root.isEnabled(),true);
 const expected=actor.idle.from+((5*actor.fps+actor.index*37)%actor.length);
 assert.equal(actor.idle.animatables[0].masterFrame,expected);
 assert.ok(actor.root.getChildMeshes().filter(m=>m.getTotalVertices()>0).every(m=>m.skeleton));
 policy.update(undefined);assert.equal(policy.stats.animatedCount,0);
 assert.equal(policy.stats.distanceLimitM,api.SHEEP_DISTANCE_LIMIT_M);
 // Six sheep checks cannot accidentally traverse a whole scene each frame.
 scene.meshes=new Proxy(scene.meshes,{get(target,key){if(key===Symbol.iterator)throw new Error('whole-scene scan');return Reflect.get(target,key);}});
 policy.update(5100);
}));

test('actual camera rotation freezes offscreen sheep; a partially visible full sheep remains active',async()=>fixture(({camera,actors,policy})=>{
 const actor=actors[0],center=actor.bounds.boundingSphere.centerWorld;
 camera.position.set(center.x,center.y,center.z-8);camera.setTarget(center);policy.update(1200);
 const frame=actor.idle.animatables[0].masterFrame;
 camera.setTarget(camera.position.add(new api.Vector3(0,0,-1)));policy.update(2400);
 assert.equal(actor.root.isEnabled(),false);assert.equal(actor.idle.animatables[0].masterFrame,frame);
 assert.ok(policy.stats.frustumCulledCount>0);
 camera.setTarget(center);policy.update(3600);assert.equal(actor.root.isEnabled(),true);
 // Pan until the actor centre exits but the complete envelope intersects an edge.
 let partial=false;
 for(let x=0;x<12;x+=.02) {
  camera.setTarget(new api.Vector3(center.x+x,center.y,center.z));policy.update(3600);
  const planes=api.Frustum.GetPlanes(camera.getTransformationMatrix());
  if(!api.Frustum.IsPointInFrustum(center,planes)&&actor.bounds.isInFrustum(planes)) {
   partial=true;assert.equal(actor.root.isEnabled(),true);break;
  }
 }
 assert.equal(partial,true,'full sheep envelope, rather than root/centre point, intersects the actual camera frustum');
}));

for(const [preset,formFactor,lod] of [['high','desktop',0],['medium','desktop',1],['low','mobile',2]])
test(`real sheep factory ${preset}/${formFactor} keeps placements, skin, shadow policy and cleanup`,async()=>{
 const engine=new api.NullEngine({renderWidth:1280,renderHeight:720,textureSize:32}),scene=new api.Scene(engine);
 const camera=new api.FreeCamera('pen-camera',new api.Vector3(39,.5,-38),scene);camera.setTarget(new api.Vector3(39,.5,-28));scene.activeCamera=camera;
 const light=new api.DirectionalLight('sun',new api.Vector3(0,-1,1),scene),shadows=new api.ShadowGenerator(32,light);
 const frame={worldMs:1000};const unregister=api.registerWeatherReader(scene,()=>frame);
 let sheep;
 try {
  sheep=await api.createBlueprintSheep(scene,{profile:{preset,formFactor},groundAt:()=>0,shadows,shadowsEnabled:true});
  const roots=scene.transformNodes.filter(node=>/^blueprint-F1-sheep-\d$/.test(node.name));
  assert.equal(roots.length,6);
  assert.deepEqual(roots.map(root=>[root.position.x,root.position.z,root.rotation.y]),[
   [35.8,-25.7,.3],[39.1,-26.1,-.7],[41.1,-27.6,1.1],[35.9,-29.7,-1.2],[39.2,-30.4,.6],[41.1,-32,2.2]
  ]);
  assert.equal(sheep.stats().skeletons,6);assert.equal(sheep.stats().sourceClips,6);assert.equal(sheep.stats().lod,lod);
  assert.equal(sheep.stats().shadowCasterCount,0);assert.equal(shadows.getShadowMap().renderList.length,0);
  assert.ok(roots.flatMap(root=>root.getChildMeshes()).filter(mesh=>mesh.getTotalVertices()>0).every(mesh=>mesh.receiveShadows&&mesh.skeleton));
  assert.equal(sheep.stats().visibility.animatedCount,6);
  camera.position.set(0,.5,0);camera.setTarget(new api.Vector3(0,.5,1));frame.worldMs=10000;
  scene.onBeforeRenderObservable.notifyObservers(scene);
  assert.equal(sheep.stats().visibility.animatedCount,0);assert.ok(roots.every(root=>!root.isEnabled()));
  camera.position.set(39,.5,-38);camera.setTarget(new api.Vector3(39,.5,-28));frame.worldMs=12000;
  scene.onBeforeRenderObservable.notifyObservers(scene);assert.equal(sheep.stats().visibility.animatedCount,6);
  const policyObserver=scene.onBeforeRenderObservable.observers.at(-1);
  const poseUpdates=sheep.stats().visibility.poseUpdates;
  sheep.dispose();sheep.dispose();
  assert.equal(sheep.stats().disposed,true);
  assert.equal(policyObserver._willBeUnregistered,true);
  scene.onBeforeRenderObservable.notifyObservers(scene);assert.equal(sheep.stats().visibility.poseUpdates,poseUpdates);
  assert.equal(scene.transformNodes.filter(node=>/^blueprint-F1-sheep-\d$/.test(node.name)).length,0);
 } finally {sheep?.dispose();unregister();shadows.dispose();scene.dispose();engine.dispose();}
});
