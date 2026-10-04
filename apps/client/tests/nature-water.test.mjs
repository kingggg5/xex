import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,unlinkSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {build} from 'esbuild';
import {NullEngine} from '@babylonjs/core/Engines/nullEngine.js';
import {Scene} from '@babylonjs/core/scene.js';
import {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture.js';
import {DirectionalLight} from '@babylonjs/core/Lights/directionalLight.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {FreeCamera} from '@babylonjs/core/Cameras/freeCamera.js';
import {waterTier,flowCycle,fallsTrajectory,depthOpacity,decodeFlow,varianceExponent,validateWaterManifest,createWaterTerrainSampler} from '../src/nature-water.mjs';

const root=path.resolve(import.meta.dirname,'../../..');
const assetDir=path.join(root,'apps/client/src/assets/world/water-v3');
const manifest=JSON.parse(readFileSync(path.join(assetDir,'water-manifest.json'),'utf8'));
test('shared phase wraps flow continuously, resetting layer has zero weight',()=>{
 const before=flowCycle(2*Math.PI-1e-8),after=flowCycle(0);
 assert.ok(before.weightB>.99999);assert.equal(after.weightB,1);assert.equal(after.b,.5);
 assert.equal(flowCycle(Math.PI/8).weightB,0);
 assert.throws(()=>flowCycle(NaN));
});
test('ballistic fall lands safely inside the amended pool',()=>{
 const p=fallsTrajectory(Math.sqrt(2*(7.45+.35)/9.81));
 assert.ok(Math.abs(p.x+9.3116)<.001);assert.ok(Math.abs(p.y+.35)<1e-9);
 assert.ok(2.6-Math.hypot(p.x+9.6,p.z+38)>1);
 assert.ok(depthOpacity(.1)<depthOpacity(.7));
 assert.ok(varianceExponent(220,.2,.2)<40);
 assert.ok(decodeFlow(128,255)[1]===1.2);
});
test('layout-derived bodies and asset hashes are bounded and fresh',()=>{
 assert.equal(validateWaterManifest(manifest),manifest);
 for(const body of ['sunmeadow_stream','falls_pool','bluff_falls','grotto_moon_pool','lotus_mere_pond','brightwater_cove_lake'])assert.ok(manifest.bodies.includes(body));
 assert.equal(manifest.layout_sha256,createHash('sha256').update(readFileSync(path.join(root,'planning/levels/sunmeadow-v2-layout.json'))).digest('hex'));
 for(const name of ['water_flow.bin','water_masks.bin'])assert.equal(readFileSync(path.join(assetDir,name)).length,1024*128*4);
 for(const name of ['water_flow_low.bin','water_masks_low.bin'])assert.equal(readFileSync(path.join(assetDir,name)).length,512*64*4);
 for(const tier of ['low','medium','high','ultra','epic'])assert.equal(waterTier(tier).draws,2);
 const invalid=structuredClone(manifest);invalid.anchors.anchor_sm_falls_landing.position[0]=NaN;assert.throws(()=>validateWaterManifest(invalid));
});
function glbAccessor(json,binary,index){
 const accessor=json.accessors[index],view=json.bufferViews[accessor.bufferView];
 const width={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[accessor.type];
 const bytes={5121:1,5123:2,5125:4,5126:4}[accessor.componentType],values=[];
 const data=new DataView(binary.buffer,binary.byteOffset,binary.byteLength);
 const read=accessor.componentType===5126?'getFloat32':accessor.componentType===5125?'getUint32':accessor.componentType===5123?'getUint16':'getUint8';
 for(let i=0;i<accessor.count;i++){const row=[];for(let k=0;k<width;k++){let v=data[read]((view.byteOffset??0)+(accessor.byteOffset??0)+i*(view.byteStride??width*bytes)+k*bytes,true);if(accessor.normalized)v/=accessor.componentType===5121?255:65535;row.push(v);}values.push(row);}return values;
}
test('exported GLB preserves canonical world positions, atlas V and layer data',()=>{
 const bytes=readFileSync(path.join(assetDir,manifest.glb));assert.equal(bytes.readUInt32LE(0),0x46546c67);assert.equal(bytes.readUInt32LE(4),2);
 assert.ok(bytes.length<250*1024);assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.glb_sha256);
 const length=bytes.readUInt32LE(12),json=JSON.parse(bytes.subarray(20,20+length).toString()),binary=bytes.subarray(28+length);
 for(const extension of ['KHR_meshopt_compression','EXT_meshopt_compression','KHR_mesh_quantization'])assert.ok(!(json.extensionsUsed??[]).includes(extension));
 const original=JSON.parse(readFileSync(path.join(root,'planning/evidence/water-20261002/water-geometry.json'),'utf8'));
 for(const [key,rec] of Object.entries(manifest.meshes)){
  const node=json.nodes.find(n=>n.name===rec.name);assert.ok(node);const primitives=json.meshes[node.mesh].primitives;assert.equal(primitives.length,1);
  const primitive=primitives[0];assert.equal(json.accessors[primitive.indices].count/3,rec.triangles);
  const positions=glbAccessor(json,binary,primitive.attributes.POSITION),uvs=glbAccessor(json,binary,primitive.attributes[key==='surface'?'TEXCOORD_1':'COLOR_0']);
  for(const probe of [0,Math.floor(positions.length/3),Math.floor(positions.length/2),positions.length-1]){
   const expectedIndex=original[key].position.findIndex(p=>p.every((v,i)=>Math.abs(v-positions[probe][i])<1e-4));assert.ok(expectedIndex>=0,'canonical position must match source');
   const expected=original[key][key==='surface'?'uv1':'color'][expectedIndex];
   for(let i=0;i<uvs[probe].length;i++)assert.ok(Math.abs(uvs[probe][i]-expected[i])<2/255,`${rec.name} probe ${probe} component ${i}`);
  }
 }
});
test('terrain contract carves negative visual beds and leaves dry paths alone',()=>{
 const derived=JSON.parse(readFileSync(path.join(root,'planning/evidence/water-20261002/water-derived.json'),'utf8')),sample=createWaterTerrainSampler(derived);
 assert.equal(sample(0,-20),null);assert.equal(sample(-46.4,3.5).body,'lotus_mere_pond');
 assert.equal(sample(-55,-86).surfaceY,-.35);assert.ok(sample(-55,-86).heightY<-.9);
 assert.ok(sample(-9.6,-38).heightY<-.9);assert.equal(sample(7.4,-41.7).surfaceY,-.12);
 assert.throws(()=>sample(NaN,0));
});
test('native surface/falls graphs generate both languages without depth/emissive/custom blocks',async()=>{
 const require=createRequire(path.join(root,'apps/client/package.json'));
 const bundle=path.join(root,'planning/evidence/water-art-pass4b-20261003/nature-water-test-bundle.mjs');
 const source=readFileSync(path.join(root,'apps/client/src/nature-water.ts'),'utf8').replace(/import\.meta\.glob\([^;]+;/g,'{};');
 await build({stdin:{contents:source,resolveDir:path.join(root,'apps/client/src'),sourcefile:'nature-water.ts',loader:'ts'},outfile:bundle,bundle:true,platform:'node',format:'esm',plugins:[{name:'native-bindings',setup(b){b.onResolve({filter:/^@babylonjs\/core\//},a=>({path:pathToFileURL(require.resolve(a.path)).href,external:true}));}}]});
 const {buildNatureWaterGraph,buildNatureWaterParticleGraph,makeNatureWaterParticles}=await import(pathToFileURL(bundle));
 const engine=new NullEngine();Object.defineProperty(engine,'supportsUniformBuffers',{value:true});const scene=new Scene(engine);new FreeCamera('native-particle-camera',new Vector3(-17,4,-45),scene);scene.updateTransformMatrix(true);
 const texture=RawTexture.CreateRGBATexture(new Uint8Array([128,128,255,255]),1,1,scene,false,false);
 new DirectionalLight('env-sun',new Vector3(-.5,-.8,.3),scene);
 const maps={masks:texture,flow:texture,ripple:texture,swell:texture,foam:texture,streak:texture,owned:[texture]};
 try{
  for(const gpu of [false,true]){
   Object.defineProperty(engine,'isWebGPU',{value:gpu,configurable:true});
   for(const tier of ['low','medium','high'])for(const falls of [false,true]){
    const {material}=buildNatureWaterGraph(scene,maps,waterTier(tier),falls);
    await new Promise((resolve,reject)=>{material.onBuildObservable.addOnce(resolve);material.onBuildErrorObservable.addOnce(reject);material.build(false,true,true);});
    assert.ok(material.compiledShaders.length>500);
    assert.ok(material.attachedBlocks.some(b=>b.getClassName()==='DerivativeBlock'));
    for(const block of material.attachedBlocks)assert.ok(!['SceneDepthBlock','CustomBlock','ReflectionBlock'].includes(block.getClassName()));
    assert.ok(!material.attachedBlocks.some(b=>/emissive/i.test(b.name)));
    assert.equal(material.disableDepthWrite,true);material.dispose(false,false);
   }
   const particles=buildNatureWaterParticleGraph(scene);
   await new Promise((resolve,reject)=>{particles.material.onBuildObservable.addOnce(resolve);particles.material.onBuildErrorObservable.addOnce(reject);particles.material.build(false,true,true);});
   assert.ok(particles.material.compiledShaders.length>300);assert.ok(!particles.material.attachedBlocks.some(b=>/emissive/i.test(b.name)));particles.material.dispose(false,false);
  }
  const before=scene.particleSystems.length;
  const emptyPlanes=scene.frustumPlanes;
  assert.ok(!emptyPlanes||emptyPlanes.length===6,'native planes may be absent before first active-mesh evaluation');
  for(const caps of [[8,12],[12,24],[16,40],[20,56]]){
   assert.ok(caps[0]+caps[1]<=116);
   const systems=caps.map((cap,i)=>makeNatureWaterParticles(scene,`test-${i}`,cap,texture,i===0));
   for(let i=0;i<2;i++){
    assert.equal(systems[i].getCapacity(),caps[i]);assert.equal(systems[i].renderingGroupId,1);assert.equal(systems[i].emitRate,0);assert.equal(systems[i].paused,true);
    systems[i].paused=false;systems[i].emitRate=50;systems[i].start();
    for(let step=0;step<4;step++)systems[i].animate(true);
    assert.ok(systems[i].getActiveCount()<=caps[i]);systems[i].dispose(false);
   }
  }
  assert.equal(scene.particleSystems.length,before);
 }finally{scene.dispose();engine.dispose();unlinkSync(bundle);}
});
