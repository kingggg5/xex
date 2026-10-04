import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,unlinkSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
import {build} from 'esbuild';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {Mesh} from '@babylonjs/core/Meshes/mesh.js';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture.js';
import {DirectionalLight} from '@babylonjs/core/Lights/directionalLight.js';
import {FreeCamera} from '@babylonjs/core/Cameras/freeCamera.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {supportedRainPuddles,rainPuddleAtlasUV,waterTier} from '../src/nature-water.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=p=>JSON.parse(readFileSync(path.join(root,p),'utf8'));
const r01='planning/levels/sunmeadow-water-art-pass4b-overlay.json';
const r02=read('planning/levels/sunmeadow-water-art-pass4b-r02-overlay.json');
const puddles=read('apps/client/src/assets/world/water-art-pass4b-r02/p4-derived.json').rain_bodies;
async function compileSource(name,dev=false){
 const require=createRequire(path.join(root,'apps/client/package.json'));
 const source=readFileSync(path.join(root,'apps/client/src',name),'utf8').replace(/import\.meta\.glob\([^;]+;/g,'{};');
 const bundle=path.join(root,'planning/evidence/water-art-pass4b-20261003/r02',name+'.test-bundle.mjs');
 await build({stdin:{contents:source,resolveDir:path.join(root,'apps/client/src'),sourcefile:name,loader:'ts'},outfile:bundle,bundle:true,platform:'node',format:'esm',define:{'import.meta.env':JSON.stringify({DEV:dev})},plugins:[{name:'same-native-bindings',setup(b){b.onResolve({filter:/^@babylonjs\/core\//},a=>({path:pathToFileURL(require.resolve(a.path)).href,external:true}));}}],logLevel:'silent'});
 try{return await import(pathToFileURL(bundle));}finally{unlinkSync(bundle);}
}
test('r02 uses measured seven poses while r01 and all other entries remain immutable',()=>{
 const preflight=read('planning/evidence/water-art-pass4b-20261003/r02/grotto-geometry-preflight.json');
 assert.equal(preflight.status,'SELECTED_FINAL_GEOMETRY_PASS');
 assert.deepEqual(r02.entries.filter(e=>e.role==='grotto_bluff'),preflight.selectedFinal.entries);
 const old=read(r01);assert.equal(r02.base_overlay_sha256,createHash('sha256').update(readFileSync(path.join(root,r01))).digest('hex'));
 assert.deepEqual(r02.entries.filter(e=>e.role!=='grotto_bluff'),old.entries.filter(e=>e.role!=='grotto_bluff'));
 assert.deepEqual(r02.L1_patches,old.L1_patches);
});
test('48-point wet films require true Y0 support and have zero alpha at every organic boundary',()=>{
 assert.throws(()=>supportedRainPuddles(puddles,()=>0));
 assert.equal(supportedRainPuddles(puddles,()=>0,{maxOutlineVertices:48}).accepted.length,3);
 assert.equal(supportedRainPuddles(puddles,()=>null,{maxOutlineVertices:48}).accepted.length,0);
 assert.equal(supportedRainPuddles(puddles,()=>.04,{maxOutlineVertices:48}).accepted.length,0);
 assert.throws(()=>supportedRainPuddles(puddles,()=>0,{maxOutlineVertices:64}));
 for(const b of puddles){
  assert.equal(b.outline_xz.length,48);assert.equal(b.surface_y,.012);assert.equal(b.host_cut,false);
  const rx=Math.max(...b.outline_xz.map(p=>Math.abs(p[0]-b.center_xz[0]))),rz=Math.max(...b.outline_xz.map(p=>Math.abs(p[1]-b.center_xz[1])));
  for(const p of b.outline_xz){const [u,v]=rainPuddleAtlasUV(p,b.center_xz,rx,rz,true);assert.ok(Math.abs(Math.hypot(u-.5,v-.5)-.5)<1e-10);assert.ok((.46-Math.hypot(u-.5,v-.5))/.16<0);}
  const positions=[b.center_xz[0],b.surface_y,b.center_xz[1],...b.outline_xz.flatMap(p=>[p[0],b.surface_y,p[1]])],indices=[];
  for(let k=0;k<48;k++)indices.push(0,k+1,(k+1)%48+1);
  const normals=[];VertexData.ComputeNormals(positions,indices,normals);assert.ok(normals.filter((_,i)=>i%3===1).every(y=>y>.999));
 }
});
test('exact runtime float mesh bypasses renamed material while index and AABB guards remain fail-closed',async()=>{
 const {installWaterArtScene}=await compileSource('water-art-pass4b-scene.ts');
 for(const mode of ['valid','wrong-name','wrong-count','wrong-bounds']){
  const engine=new NullEngine(),scene=new Scene(engine);try{
   const mesh=new Mesh(mode==='wrong-name'?'decoy stone_foundation':'Cell sunmeadow_c7_r6 / stone_foundation',scene);
   mesh.material=new PBRMaterial('env-cell-stone',scene);
   const positions=new Float32Array(5319*3),indices=Array.from({length:mode==='wrong-count'?10305:10308},(_,i)=>i%5319);
   const box=r02.legacy_float_patch.world_aabb;
   for(let i=540;i<600;i++)for(let j=0;j<3;j++)positions[i*3+j]=(i%2?box.max:box.min)[j]+(mode==='wrong-bounds'?.1:0);
   mesh.setVerticesData('position',positions);mesh.setIndices(indices);
   const status=installWaterArtScene(scene,2);scene.onBeforeRenderObservable.notifyObservers(scene);
   if(mode==='valid'){assert.equal(status.legacyFloat.state,'LOCAL20_TRIANGLE_PATCH_APPLIED');assert.deepEqual(Array.from(mesh.getIndices()),indices.filter((_,i)=>i<540||i>=600));assert.equal(status.legacyFloat.removedTriangles,20);}
   else{assert.notEqual(status.legacyFloat.state,'LOCAL20_TRIANGLE_PATCH_APPLIED');assert.deepEqual(Array.from(mesh.getIndices()),indices);}
  }finally{scene.dispose();engine.dispose();}
 }
});
test('r02 actual NodeMaterial paths generate both GLSL and WGSL without emissive or reflection render passes',async()=>{
 const oldLocation=globalThis.location;globalThis.location={search:'?waterArt=pass4b&waterArtRev=2&blueprintWave=p2'};
 try{
  const {buildNatureWaterGraph}=await compileSource('nature-water.ts',true),engine=new NullEngine(),scene=new Scene(engine);
  const texture=RawTexture.CreateRGBATexture(new Uint8Array([128,128,255,255]),1,1,scene,false,false);
  new FreeCamera('r02-camera',new Vector3(-17,4,-45),scene);new DirectionalLight('env-sun',new Vector3(-.5,-.8,.3),scene);scene.updateTransformMatrix(true);
  const maps={masks:texture,flow:texture,ripple:texture,swell:texture,foam:texture,streak:texture,owned:[texture]};
  try{for(const gpu of [false,true]){Object.defineProperty(engine,'isWebGPU',{value:gpu,configurable:true});for(const rain of [false,true]){const graph=buildNatureWaterGraph(scene,maps,waterTier('high'),false,rain);await new Promise((resolve,reject)=>{graph.material.onBuildObservable.addOnce(resolve);graph.material.onBuildErrorObservable.addOnce(reject);graph.material.build(false,true,true);});assert.ok(graph.material.compiledShaders.length>500);assert.ok(!graph.material.attachedBlocks.some(b=>/emissive/i.test(b.name)||['ReflectionBlock','SceneDepthBlock'].includes(b.getClassName())));graph.material.dispose(false,false);}}}
  finally{texture.dispose();scene.dispose();engine.dispose();}
 }finally{if(oldLocation===undefined)delete globalThis.location;else globalThis.location=oldLocation;}
});
