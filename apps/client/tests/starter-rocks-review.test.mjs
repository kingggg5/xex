import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const entry=[
"export {NullEngine} from '@babylonjs/core/Engines/nullEngine';",
"export {Scene} from '@babylonjs/core/scene';",
"export {Mesh} from '@babylonjs/core/Meshes/mesh';",
"export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';",
"export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';",
"export {Vector3} from '@babylonjs/core/Maths/math.vector';",
"export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';",
"export {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial';",
"export {AssetContainer} from '@babylonjs/core/assetContainer';",
"export {installStarterRocksReview} from './src/starter-rocks-review';",
"export {createStarterRockMaterial,STARTER_ROCK_SOURCE} from './src/starter-rocks-policy.mjs';"
].join('\n');
const plugin={name:'bounded-review-io-fixture',setup(b){
 b.onResolve({filter:/\?url$/},a=>({path:a.path,namespace:'fixture-asset'}));
 b.onLoad({filter:/.*/,namespace:'fixture-asset'},a=>({contents:'export default '+JSON.stringify(a.path),loader:'js'}));
 b.onResolve({filter:/^@babylonjs\/core\/Loading\/sceneLoader$/},a=>a.importer.endsWith('starter-rocks-review.ts')?{path:'loader',namespace:'fixture'}:undefined);
 b.onResolve({filter:/^@babylonjs\/loaders\/glTF$/},a=>a.importer.endsWith('starter-rocks-review.ts')?{path:'empty',namespace:'fixture'}:undefined);
 b.onResolve({filter:/^@babylonjs\/core\/Materials\/Textures\/texture$/},a=>a.importer.endsWith('starter-rocks-review.ts')?{path:'texture',namespace:'fixture'}:undefined);
 b.onLoad({filter:/.*/,namespace:'fixture'},a=>({loader:'js',resolveDir:fileURLToPath(new URL('..',import.meta.url)),contents:a.path==='loader'
  ?'export function LoadAssetContainerAsync(...args){return globalThis.__starterReviewHooks.load(...args)}'
  :a.path==='texture'?
  "import {Texture as RealTexture} from '@babylonjs/core/Materials/Textures/texture.js'; export class Texture { static TRILINEAR_SAMPLINGMODE=RealTexture.TRILINEAR_SAMPLINGMODE; static [Symbol.hasInstance](x){return x instanceof RealTexture;} constructor(...args){return globalThis.__starterReviewHooks.texture(...args);}}":''}));
}};
const bundle=await build({stdin:{contents:entry,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},plugins:[plugin],define:{'import.meta.env.DEV':'true'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
function source(lod){
 const b=fs.readFileSync(new URL('../../../assets/models/sunmeadow-props/stone/source/sm_boulder_01_lod'+lod+'.glb',import.meta.url));
 let json,bin;for(let offset=12;offset<b.length;){const n=b.readUInt32LE(offset),type=b.readUInt32LE(offset+4),chunk=b.subarray(offset+8,offset+8+n);if(type===0x4e4f534a)json=JSON.parse(chunk.toString());if(type===0x004e4942)bin=chunk;offset+=8+n;}
 const primitive=json.meshes[0].primitives[0];
 const read=id=>{const a=json.accessors[id],v=json.bufferViews[a.bufferView],size={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type],width={5123:2,5125:4,5126:4}[a.componentType],out=[];
  for(let i=0;i<a.count;i++)for(let k=0;k<size;k++){const o=(v.byteOffset??0)+(a.byteOffset??0)+i*(v.byteStride??size*width)+k*width;out.push(a.componentType===5126?bin.readFloatLE(o):a.componentType===5123?bin.readUInt16LE(o):bin.readUInt32LE(o));}return out;};
 return {attributes:Object.fromEntries(Object.entries(primitive.attributes).map(([k,i])=>[k,read(i)])),indices:read(primitive.indices)};
}
const data=[source(0),source(1),source(2)];
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
async function fixture(run,{borrow=true,positions=[2,4,7,10,12]}={}){
 const engine=new api.NullEngine(),scene=new api.Scene(engine),camera=new api.FreeCamera('fixed-camera',new api.Vector3(0,3,-8),scene);
 // CPU lifecycle fixture controls texture and material readiness. No GPU import/decoding/readiness assertion.
 scene.onNewMaterialAddedObservable.add(material=>{material.isReadyForSubMesh=()=>true;});
 const foreignMaterial=new api.PBRMaterial('unrelated-live-material',scene);
 const textures=[],loads=[],staged=[],created=[],events=[];
 const raw=(name,gamma)=>{const t=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene);t.name=name;t.gammaSpace=gamma;t.hasAlpha=false;t.isReady=()=>true;textures.push(t);return t;};
 let borrowedMaterial;
 if(borrow){
  const atlas=Object.fromEntries(['albedo','normal','orm'].map(key=>[key,raw(api.STARTER_ROCK_SOURCE.atlas[key]+'.ktx2',key==='albedo')]));
  borrowedMaterial=api.createStarterRockMaterial(scene,atlas);
 }
 const master=api.MeshBuilder.CreateSphere('env-rock-master',{diameter:1.1,segments:4},scene);master.isVisible=false;master.isPickable=false;
 const legacy=positions.map((x,i)=>{const mesh=master.createInstance('env-rock-'+i);mesh.position.set(x,.25,1);mesh.isPickable=false;return mesh;});
 const makeContainer=lod=>{
  const container=new api.AssetContainer(scene),mesh=new api.Mesh('sm_boulder_01__lod'+lod,scene);
  for(const [semantic,kind,size] of [['POSITION','position',3],['NORMAL','normal',3],['TEXCOORD_0','uv',2],['TANGENT','tangent',4],['COLOR_0','color',3]])
   mesh.setVerticesData(kind,data[lod].attributes[semantic],false,size);
  mesh.setIndices(data[lod].indices);container.meshes.push(mesh);container.geometries.push(mesh.geometry);container.removeAllFromScene();
  const dispose=container.dispose.bind(container);container.dispose=()=>{events.push('container'+lod);dispose();};staged.push(container);return container;
 };
 const hooks={
  load:async(url,loadScene,options)=>{loads.push({url,scene:loadScene,options});return makeContainer(Number(url.match(/lod([012])\.glb/)[1]));},
  texture:(url,loadScene)=>{assert.equal(loadScene,scene);const t=raw(url,false);created.push(t);return t;}
 };
 globalThis.__starterReviewHooks=hooks;
 try{return await run({scene,engine,camera,legacy,borrowedMaterial,foreignMaterial,textures,loads,staged,created,events,hooks,makeContainer});}
 finally{scene.dispose();engine.dispose();delete globalThis.__starterReviewHooks;}
}
test('installer uses exact per-call skipMaterials, fixed-camera same-cell selection and borrowed atlas',async()=>{
 await fixture(async({scene,legacy,borrowedMaterial,loads,created,events})=>{
  const matrices=legacy.map(mesh=>Array.from(mesh.computeWorldMatrix(true).m)),materials=scene.materials.length,textures=scene.textures.length;
  await api.installStarterRocksReview(scene);const diagnostic=scene.metadata.starterRocksReview;
  assert.equal(diagnostic.status,'ACTIVE_UNADMITTED');assert.ok(Math.abs(diagnostic.selectionCamera.x)<1e-8);
  assert.equal(diagnostic.selectionCamera.y,3);assert.equal(diagnostic.selectionCamera.z,-8);
  assert.equal(diagnostic.cell,'0,0');assert.equal(diagnostic.selectedIds.length,5);assert.equal(diagnostic.materialBorrowed,true);
  assert.equal(loads.length,3);for(const load of loads){assert.equal(load.scene,scene);assert.equal(load.options.pluginOptions.gltf.skipMaterials,true);assert.equal(load.options.pluginExtension,'.glb');}
  assert.equal(created.length,0);assert.equal(scene.materials.length,materials);assert.equal(scene.textures.length,textures);
  assert.equal(events.length,3);assert.ok(legacy.every(mesh=>!mesh.isVisible));assert.ok(scene.materials.includes(borrowedMaterial));
  for(let i=0;i<legacy.length;i++)assert.deepEqual(Array.from(legacy[i].computeWorldMatrix(true).m),matrices[i]);
  await api.installStarterRocksReview(scene);assert.equal(loads.length,3);
  assert.equal(scene.onBeforeRenderObservable.observers.length,1);
 });
});
test('fallback owns only three new atlas maps and one material, restores legacy on callback failure',async()=>{
 await fixture(async({scene,camera,legacy,foreignMaterial,created,events})=>{
  const beforeMaterials=scene.materials.length,beforeTextures=scene.textures.length;
  await api.installStarterRocksReview(scene);
  assert.equal(scene.metadata.starterRocksReview.status,'ACTIVE_UNADMITTED');assert.equal(created.length,3);
  assert.equal(scene.metadata.starterRocksReview.materialBorrowed,false);assert.equal(scene.metadata.starterRocksReview.ownedTextureCount,3);
  const disposal=[];created.forEach(texture=>texture.onDisposeObservable.add(()=>disposal.push(texture.name)));
  assert.equal(created.find(t=>t.name.includes('albedo')).gammaSpace,true);assert.ok(created.filter(t=>!t.name.includes('albedo')).every(t=>!t.gammaSpace));
  camera.globalPosition.x=NaN;scene.onBeforeRenderObservable.notifyObservers(scene);
  assert.equal(scene.metadata.starterRocksReview.status,'FAILED_RESTORED_LEGACY');assert.ok(legacy.every(mesh=>mesh.isVisible));
  assert.equal(disposal.length,3);assert.equal(scene.materials.length,beforeMaterials,'material ownership');
  // Babylon's lazily initialized scene-owned BRDF cache remains shared; all three owned atlas maps are gone.
  assert.ok(scene.textures.every(texture=>texture.name.startsWith('data:EnvironmentBRDFTexture')));
  assert.ok(scene.materials.includes(foreignMaterial));assert.equal(events.length,3);
  await flush();assert.equal(scene.onBeforeRenderObservable.observers.length,0);
 },{borrow:false});
});
test('existing wrong-colour-space atlas is retained unchanged and prototype cannot hide old rocks',async()=>{
 await fixture(async({scene,legacy,hooks,textures})=>{
  const bad=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene);bad.name=api.STARTER_ROCK_SOURCE.atlas.normal+'.ktx2';bad.gammaSpace=true;bad.hasAlpha=false;bad.isReady=()=>true;textures.push(bad);
  let badDisposed=0;bad.onDisposeObservable.add(()=>badDisposed++);await api.installStarterRocksReview(scene);
  assert.equal(scene.metadata.starterRocksReview.status,'FAILED_RETAINED_LEGACY');assert.ok(legacy.every(mesh=>mesh.isVisible));assert.equal(bad.gammaSpace,true);assert.equal(badDisposed,0);
 },{borrow:false});
});
test('owned texture-load error rejects promptly and clears waits/resources without staging models',async()=>{
 await fixture(async({scene,legacy,hooks,created,loads})=>{
  hooks.texture=(url,loadScene,noMip,invert,sampling,onLoad,onError)=>{
   const texture=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,loadScene);texture.name=url;texture.hasAlpha=false;created.push(texture);
   if(url.includes('normal')){texture.isReady=()=>false;queueMicrotask(()=>onError('normal load rejected'));}
   return texture;
  };
  const start=Date.now();await api.installStarterRocksReview(scene);
  assert.ok(Date.now()-start<1000);assert.equal(scene.metadata.starterRocksReview.status,'FAILED_RETAINED_LEGACY');
  assert.match(scene.metadata.starterRocksReview.error,/normal load rejected/);assert.equal(loads.length,0);assert.ok(legacy.every(mesh=>mesh.isVisible));assert.equal(scene.metadata.starterRocksReview.ownedTextureCount,0);
 },{borrow:false});
});
test('ready hardware sRGB albedo reuses its compatible material without flag changes',async()=>{
 await fixture(async({scene,borrowedMaterial,created})=>{
  const albedo=borrowedMaterial.albedoTexture;albedo.getInternalTexture()._useSRGBBuffer=true;
  assert.equal(albedo.gammaSpace,false);const materials=scene.materials.length;
  await api.installStarterRocksReview(scene);
  const diagnostic=scene.metadata.starterRocksReview;
  assert.equal(diagnostic.status,'ACTIVE_UNADMITTED');assert.equal(diagnostic.materialBorrowed,true);assert.equal(created.length,0);
  assert.equal(scene.materials.length,materials);assert.deepEqual(diagnostic.textureColorSpace.albedo,{shaderGamma:false,hardwareSRGB:true,valid:true});
  assert.equal(albedo.getInternalTexture()._useSRGBBuffer,true);
 });
});
test('scene disposal cancels waits and late containers are disposed instead of reactivating',async()=>{
 await fixture(async({scene,legacy,hooks,makeContainer,events})=>{
  const containers=[0,1,2].map(makeContainer),resolvers=[];
  hooks.load=(url)=>new Promise(resolve=>resolvers.push(()=>resolve(containers[Number(url.match(/lod([012])\.glb/)[1])])));
  const pending=api.installStarterRocksReview(scene);await flush();assert.equal(resolvers.length,3);
  const diagnostic=scene.metadata.starterRocksReview;
  scene.dispose();await pending;assert.equal(diagnostic.status,'DISPOSED');
  for(const resolve of resolvers)resolve();await flush();
  // AssetContainer also registers a scene-disposal handler; a late explicit dispose is safely idempotent.
  assert.equal(new Set(events).size,3);assert.ok(events.length>=3);assert.ok(containers.every(container=>container.meshes.every(mesh=>mesh.isDisposed())));
  assert.equal(diagnostic.status,'DISPOSED');assert.equal(scene.onBeforeRenderObservable.observers.length,0);
 });
});
