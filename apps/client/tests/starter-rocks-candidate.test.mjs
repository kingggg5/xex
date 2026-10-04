import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const compiled=await build({stdin:{contents:[
"export {NullEngine} from '@babylonjs/core/Engines/nullEngine';",
"export {Scene} from '@babylonjs/core/scene';",
"export {Mesh} from '@babylonjs/core/Meshes/mesh';",
"export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';",
"export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';",
"export {Vector3} from '@babylonjs/core/Maths/math.vector';",
"export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';",
"export {createStarterRocksCandidate} from './src/starter-rocks-candidate';",
"export {createStarterRockMaterial,STARTER_ROCK_SOURCE} from './src/starter-rocks-policy.mjs';"
].join('\n'),resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
/** Read immutable uncompressed author geometry: no renderer, decoder, network or asset mutation. */
function source(lod){
 const path=new URL('../../../assets/models/sunmeadow-props/stone/source/sm_boulder_01_lod'+lod+'.glb',import.meta.url);
 const bytes=fs.readFileSync(path);assert.equal(bytes.readUInt32LE(0),0x46546c67);
 let json,bin;
 for(let offset=12;offset<bytes.length;){const length=bytes.readUInt32LE(offset),type=bytes.readUInt32LE(offset+4),chunk=bytes.subarray(offset+8,offset+8+length);
  if(type===0x4e4f534a)json=JSON.parse(chunk.toString());if(type===0x004e4942)bin=chunk;offset+=8+length;}
 assert.ok(json&&bin);assert.ok(!json.extensionsUsed?.includes('EXT_meshopt_compression'));
 const primitive=json.meshes[0].primitives[0];
 const read=index=>{const accessor=json.accessors[index],view=json.bufferViews[accessor.bufferView],size={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[accessor.type];
  const width={5123:2,5125:4,5126:4}[accessor.componentType],result=[],data=new DataView(bin.buffer,bin.byteOffset,bin.length);
  assert.ok(size&&width);for(let vertex=0;vertex<accessor.count;vertex++)for(let component=0;component<size;component++){
   const offset=(view.byteOffset??0)+(accessor.byteOffset??0)+vertex*(view.byteStride??size*width)+component*width;
   result.push(accessor.componentType===5126?data.getFloat32(offset,true):accessor.componentType===5123?data.getUint16(offset,true):data.getUint32(offset,true));}return result;};
 return {attributes:Object.fromEntries(Object.entries(primitive.attributes).map(([key,index])=>[key,read(index)])),indices:read(primitive.indices)};
}
const sourceData=[source(0),source(1),source(2)];
async function fixture(run,positions=[2,25,55]){
 const engine=new api.NullEngine(),scene=new api.Scene(engine);
 new api.FreeCamera('test-camera',new api.Vector3(0,2,-4),scene);
 const textures=Object.fromEntries(['albedo','normal','orm'].map(key=>{
  const texture=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene);
  texture.name=api.STARTER_ROCK_SOURCE.atlas[key]+'.ktx2';texture.gammaSpace=key==='albedo';texture.hasAlpha=false;return [key,texture];}));
 const material=api.createStarterRockMaterial(scene,textures);
 // NullEngine has no GPU shader/texture-readiness proof. Control only this fixture's
 // admission signal; geometry, PBR flags, buffers and ownership remain real Babylon objects.
 material.isReadyForSubMesh=()=>true;
 const templates=sourceData.map((data,lod)=>{
  const mesh=new api.Mesh('sm_boulder_01__lod'+lod,scene);
  for(const [semantic,kind,size] of [['POSITION','position',3],['NORMAL','normal',3],['TEXCOORD_0','uv',2],['TANGENT','tangent',4],['COLOR_0','color',3]])
   mesh.setVerticesData(kind,data.attributes[semantic],false,size);
  mesh.setIndices(data.indices);return mesh;
 });
 const master=api.MeshBuilder.CreateSphere('env-rock-master',{diameter:1.1,segments:4},scene);master.isVisible=false;master.isPickable=false;
 const legacy=positions.map((x,index)=>{const mesh=master.createInstance('env-rock-'+index);mesh.position.set(x,.25,1);mesh.rotation.set(.2,.4,.1);mesh.scaling.set(1.2,.8,1.1);mesh.isPickable=false;return mesh;});
 let candidate;const create=(extra={})=>candidate=api.createStarterRocksCandidate(scene,{templates,sourceHashes:api.STARTER_ROCK_SOURCE.sha256,material,legacy,...extra});
 try{return await run({scene,engine,templates,legacy,material,textures,create});}
 finally{candidate?.dispose();scene.dispose();engine.dispose();}
}
test('actual three LOD geometry preserves colour and input buffers while fitting legacy envelope',async()=>{
 await fixture(async({templates,create,material})=>{
  const snapshots=templates.map(mesh=>Object.fromEntries(mesh.getVerticesDataKinds().map(kind=>[kind,Array.from(mesh.getVerticesData(kind))])));
  const candidate=create();assert.equal(candidate.stats().geometryCopies,3);
  for(let lod=0;lod<3;lod++){
   const mesh=candidate.batches[lod];assert.notEqual(mesh.geometry,templates[lod].geometry);assert.equal(mesh.material,material);
   assert.deepEqual(Array.from(mesh.getVerticesData('color')),snapshots[lod].color);
   assert.equal(mesh.getTotalIndices()/3,api.STARTER_ROCK_SOURCE.triangles[lod]);
   assert.equal(mesh.useVertexColors,true);assert.equal(mesh.hasVertexAlpha,false);
   assert.equal(mesh.isVerticesDataPresent('tangent'),false);assert.equal(mesh.getVerticesDataKinds().length,8);
   const attributes=['position','normal','uv','color'].map(kind=>mesh.getVertexBuffer(kind));
   assert.equal(new Set(attributes.map(buffer=>buffer.getBuffer())).size,1);
   const points=mesh.getVerticesData('position');let radius=0;
   for(let index=0;index<points.length;index+=3)radius=Math.max(radius,Math.hypot(points[index],points[index+1],points[index+2]));
   assert.ok(radius<=.550001);assert.ok(radius>.4);
   const scale=candidate.stats().uniformSourceScale,uv=mesh.getVerticesData('uv');
   for(let index=0;index<uv.length;index++)assert.ok(Math.abs(uv[index]-snapshots[lod].uv[index]*scale)<1e-6);
   for(const kind of templates[lod].getVerticesDataKinds())assert.deepEqual(Array.from(templates[lod].getVerticesData(kind)),snapshots[lod][kind]);
  }
  assert.equal(candidate.stats().maximumAttributeLocations,8);
 });
});
test('ready swap only hides chosen originals and partitions exact world matrices by LOD',async()=>{
 await fixture(async({legacy,create})=>{
  const matrices=legacy.map(mesh=>Array.from(mesh.computeWorldMatrix(true).m)),candidate=create();
  assert.equal(candidate.activate({x:0,y:.25,z:1}),false);assert.ok(legacy.every(mesh=>mesh.isVisible));
  await candidate.prewarm();assert.equal(candidate.activate({x:0,y:.25,z:1}),true);
  assert.deepEqual(candidate.stats().lodCounts,[1,1,1]);assert.equal(candidate.stats().estimatedDraws,3);assert.equal(candidate.stats().triangles,1280);
  for(let lod=0;lod<3;lod++){
   assert.deepEqual(Array.from(candidate.batches[lod].thinInstanceGetWorldMatrices()[0].m),matrices[lod]);
   assert.ok(candidate.batches[lod].getBoundingInfo().boundingBox.minimumWorld.asArray().every(Number.isFinite));
  }
  assert.ok(legacy.every(mesh=>!mesh.isVisible));
  candidate.update({x:100,y:.25,z:1});assert.deepEqual(candidate.stats().lodCounts,[0,0,3]);
  assert.equal(candidate.stats().estimatedDraws,1);assert.equal(candidate.stats().triangles,450);
  assert.throws(()=>candidate.update({x:NaN,y:0,z:0}),/Finite camera/);
  candidate.restore();assert.ok(legacy.every(mesh=>mesh.isVisible));assert.ok(candidate.batches.every(mesh=>!mesh.isEnabled()));
 });
});
test('mirrored nonuniform source transform preserves colour and uses inverse-transpose normals',async()=>{
 await fixture(async({templates,create})=>{
  for(const mesh of templates)mesh.scaling.set(.6,1.3,-.4);
  const world=templates[0].computeWorldMatrix(true).clone(),normals=Array.from(templates[0].getVerticesData('normal'));
  const expected=api.Vector3.TransformNormal(api.Vector3.FromArray(normals),world.invert().transpose()).normalize();
  const candidate=create(),actual=api.Vector3.FromArray(candidate.batches[0].getVerticesData('normal'));
  assert.ok(actual.subtract(expected).length()<1e-5);
  assert.deepEqual(Array.from(templates[0].getVerticesData('normal')),normals);
  assert.deepEqual(Array.from(candidate.batches[0].getVerticesData('color')),sourceData[0].attributes.COLOR_0);
 });
});
test('bound count, actor names, cell and source identity before allocating candidate meshes',async()=>{
 await fixture(async({scene,legacy,create})=>{
  const count=scene.meshes.length;
  assert.throws(()=>create({legacy:[...legacy,...legacy]}),/Bounded unique/);assert.equal(scene.meshes.length,count);
  legacy[0].name='monster-pink-ball';assert.throws(()=>create(),/Only.*existing/);assert.equal(scene.meshes.length,count);legacy[0].name='env-rock-0';
  legacy[0].isVisible=false;assert.throws(()=>create(),/Only visible/);assert.equal(scene.meshes.length,count);legacy[0].isVisible=true;
  legacy[0].position.x=-1;assert.throws(()=>create(),/One cell/);assert.equal(scene.meshes.length,count);legacy[0].position.x=2;
  assert.throws(()=>create({sourceHashes:['stale',...api.STARTER_ROCK_SOURCE.sha256.slice(1)]}),/pinned/);assert.equal(scene.meshes.length,count);
 });
 await fixture(async({create})=>{const candidate=create();await candidate.prewarm();candidate.activate({x:0,y:.25,z:1});assert.equal(candidate.stats().anchors.length,5);},[1,2,3,4,5]);
});
test('wrong atlas ORM and colour space are rejected without changing borrowed textures',async()=>{
 await fixture(async({scene,create,material,textures})=>{
  const count=scene.meshes.length;
  material.useRoughnessFromMetallicTextureAlpha=true;assert.throws(()=>create(),/ORM/);assert.equal(scene.meshes.length,count);
  material.useRoughnessFromMetallicTextureAlpha=false;textures.normal.gammaSpace=true;
  assert.throws(()=>create(),/colour space/);assert.equal(scene.meshes.length,count);assert.equal(textures.normal.gammaSpace,true);
 });
});
test('hardware sRGB albedo is accepted once while normal and ORM stay strictly linear',async()=>{
 await fixture(async({create,textures,scene})=>{
  textures.albedo.getInternalTexture()._useSRGBBuffer=true;
  assert.equal(textures.albedo.gammaSpace,false);const candidate=create();candidate.dispose();
  const meshCount=scene.meshes.length;
  textures.normal.getInternalTexture()._useSRGBBuffer=true;
  assert.equal(textures.normal.gammaSpace,false);
  assert.throws(()=>create(),/normal colour space/);assert.equal(scene.meshes.length,meshCount);
  assert.equal(textures.normal.getInternalTexture()._useSRGBBuffer,true);
 });
});
test('dispose restores originals and frees own geometry without disposing borrowed material/textures',async()=>{
 await fixture(async({scene,legacy,templates,create,material,textures})=>{
  const meshes=scene.meshes.length,materials=scene.materials.length,textureCount=scene.textures.length,candidate=create();
  const geometries=candidate.batches.map(mesh=>mesh.geometry);let disposedBorrowed=0;
  material.onDisposeObservable.add(()=>disposedBorrowed++);Object.values(textures).forEach(texture=>texture.onDisposeObservable.add(()=>disposedBorrowed++));
  await candidate.prewarm();candidate.activate({x:0,y:.25,z:1});candidate.dispose();candidate.dispose();
  assert.ok(legacy.every(mesh=>mesh.isVisible));assert.equal(scene.meshes.length,meshes);assert.equal(scene.materials.length,materials);assert.equal(scene.textures.length,textureCount);
  assert.equal(disposedBorrowed,0);assert.ok(templates.every(mesh=>!mesh.isDisposed()));assert.ok(geometries.every(geometry=>geometry.isDisposed()));
 });
});
test('moved original cannot activate or hide eggs',async()=>{
 await fixture(async({legacy,create})=>{
  const candidate=create();await candidate.prewarm();legacy[0].position.x+=.1;
  assert.equal(candidate.activate({x:0,y:.25,z:1}),false);assert.ok(legacy.every(mesh=>mesh.isVisible));
  candidate.update({x:NaN,y:0,z:0}); // Inactive updates cannot affect visibility.
 });
});
test('disposal cancels its warmup timer and leaves the borrowed readiness hook untouched',async()=>{
 await fixture(async({legacy,create,material})=>{
  const original=material.isReadyForSubMesh;material.isReadyForSubMesh=()=>false;
  const candidate=create(),waiting=candidate.prewarm(5000);candidate.dispose();
  await assert.rejects(waiting,/disposed/);assert.ok(legacy.every(mesh=>mesh.isVisible));
  assert.equal(material.isReadyForSubMesh(),false);material.isReadyForSubMesh=original;
 });
});
