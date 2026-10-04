import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { Mesh } from '@babylonjs/core/Meshes/mesh.js';
import { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import { RawTexture } from '@babylonjs/core/Materials/Textures/rawTexture.js';
import { createL2BrazierRepairParts, selectL2BrazierEntries, L2_TRIPOD_PINS } from '../src/l2-brazier-material-repair.mjs';
const root=new URL('../../../',import.meta.url),read=p=>JSON.parse(readFileSync(new URL(p,root),'utf8'));
const asset=read('assets/models/sunmeadow-props/manifest.json').families.craft.find(a=>a.id==='sm_brazier_tripod');
const frozen=read('planning/levels/sunmeadow-v3-dressing-p1.json').entries;
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.decoder':MeshoptDecoder});
async function sourceMesh(scene,lod){
 await MeshoptDecoder.ready;const r=asset.lods[lod],url=new URL(r.file,root),bytes=readFileSync(url);
 assert.equal(createHash('sha256').update(bytes).digest('hex'),L2_TRIPOD_PINS[lod]);
 const d=await io.read(fileURLToPath(url)),n=d.getRoot().listNodes().find(n=>n.getMesh()),pr=n.getMesh().listPrimitives()[0],m=n.getWorldMatrix(),p=pr.getAttribute('POSITION'),u=pr.getAttribute('TEXCOORD_0'),positions=[],uv=[],v=[];
 for(let i=0;i<p.getCount();i++){p.getElement(i,v);positions.push(-(m[0]*v[0]+m[4]*v[1]+m[8]*v[2]+m[12]),m[1]*v[0]+m[5]*v[1]+m[9]*v[2]+m[13],m[2]*v[0]+m[6]*v[1]+m[10]*v[2]+m[14]);u.getElement(i,v);uv.push(v[0],v[1]);}
 const mesh=new Mesh('tripod'+lod,scene);mesh.material=new PBRMaterial('craft'+lod,scene);mesh.setVerticesData('position',positions,false,3);mesh.setVerticesData('uv',uv,false,2);mesh.setIndices(Array.from(pr.getIndices().getArray()));return mesh;
}
test('only two frozen L2 entries swap to pinned tripod; anchors and colliders remain exact',()=>{
 const before=JSON.stringify(frozen),selected=selectL2BrazierEntries(frozen,new Map([[asset.id,asset]]));assert.equal(JSON.stringify(frozen),before);
 for(let i=0;i<frozen.length;i++){if(!['bp1_L2_000','bp1_L2_001'].includes(frozen[i].id))assert.equal(selected[i],frozen[i]);else{assert.equal(selected[i].asset_id,asset.id);assert.equal(selected[i].target_height,1.6);assert.equal(selected[i].anchor_at_pivot,true);for(const k of['x','y','z','yaw','collider','footprint_r','cell'])assert.equal(selected[i][k],frozen[i][k]);}}
 assert.throws(()=>selectL2BrazierEntries(frozen,new Map()),/Pinned/);
});
test('source, borrowed textures and body faces survive forced disposal; no new emitters',async()=>{
 const engine=new NullEngine(),scene=new Scene(engine);try{const source=await sourceMesh(scene,0),original=source.material,texture=RawTexture.CreateRGBATexture(new Uint8Array([53,53,58,255]),1,1,scene,false,false);original.albedoTexture=texture;
 const p=Array.from(source.getVerticesData('position')),ix=Array.from(source.getIndices()),count=scene.textures.length;
 assert.equal(createL2BrazierRepairParts(source,'sm_brazier_cresset',['bp1_L2_000']),null);assert.equal(createL2BrazierRepairParts(source,asset.id,['bp_ST4_004']),null);
 const r=createL2BrazierRepairParts(source,asset.id,['bp1_L2_000']);assert.equal(r.parts[0].metadata.l2BrazierPart,'body');assert.equal(r.parts[1].metadata.l2BrazierPart,'ember');assert.equal(r.parts[1].receiveShadows,false);assert.equal(r.materials[1].backFaceCulling,false);
 assert.equal(scene.textures.length,count);assert.equal(scene.lights.length,0);assert.equal(r.diagnostics.extraAnchors,0);assert.equal(r.diagnostics.animatedFlame,false);assert.equal(r.diagnostics.bodyFacesRemoved,0);
 assert.deepEqual(Array.from(source.getVerticesData('position')),p);assert.deepEqual(Array.from(source.getIndices()),ix);assert.deepEqual(Array.from(r.parts[0].getIndices()),ix);
 r.materials[0].dispose(false,true);r.dispose();assert.equal(original.albedoTexture,texture);assert.ok(texture.getInternalTexture());assert.equal(texture.level,1);assert.equal(original.albedoColor.r,1);
 }finally{scene.dispose();engine.dispose();}
});
const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function hit(o,t,tri){const d=sub(t,o),a=sub(tri[1],tri[0]),b=sub(tri[2],tri[0]),h=cross(d,b),det=dot(a,h);if(Math.abs(det)<1e-10)return false;const s=sub(o,tri[0]),u=dot(s,h)/det;if(u< -1e-8||u>1+1e-8)return false;const q=cross(s,a),v=dot(d,q)/det;if(v< -1e-8||u+v>1+1e-8)return false;const f=dot(b,q)/det;return f>1e-6&&f<1-1e-6;}
test('actual three LODs fit .55m and reveal raised top coals from both exact saved-camera poses',async()=>{
 const engine=new NullEngine(),scene=new Scene(engine);try{const c=read('planning/evidence/p1-review-20261004/perf/BABYLON-CAPTURE/p1-review-final-r02/shots/arena-noon-webgl2-tier-high-player.json').identity.camera;
 const camera=[c.target.x+c.radius*Math.cos(c.alpha)*Math.sin(c.beta),c.target.y+c.radius*Math.cos(c.beta),c.target.z+c.radius*Math.sin(c.alpha)*Math.sin(c.beta)],entries=selectL2BrazierEntries(frozen,new Map([[asset.id,asset]])).filter(e=>['bp1_L2_000','bp1_L2_001'].includes(e.id)),scale=1.6/(asset.bounds.max[1]-asset.bounds.min[1]);
 for(let lod=0;lod<3;lod++){const source=await sourceMesh(scene,lod),r=createL2BrazierRepairParts(source,asset.id,['bp1_L2_000']),p=source.getVerticesData('position'),ix=source.getIndices(),ep=r.parts[1].getVerticesData('position'),ei=r.parts[1].getIndices();
 assert.equal(r.diagnostics.coalTriangles,[24,18,12][lod]);assert.equal(r.diagnostics.bodyTriangles,[284,220,156][lod]);assert.ok(Math.abs(r.diagnostics.raisedCoalTop-(r.diagnostics.rimY-.025))<1e-7);assert.ok(Math.max(...Array.from({length:p.length/3},(_,i)=>Math.hypot(p[i*3],p[i*3+2])))*scale<=.55);
 for(const e of entries){const world=v=>[e.x+v[0]*scale,(v[1]-asset.bounds.min[1])*scale,e.z+v[2]*scale],point=(data,i)=>world([data[i*3],data[i*3+1],data[i*3+2]]),body=[];for(let i=0;i<ix.length;i+=3)body.push([point(p,ix[i]),point(p,ix[i+1]),point(p,ix[i+2])]);let visible=0,total=0;
 for(let i=0;i<ei.length;i+=3){const tri=[point(ep,ei[i]),point(ep,ei[i+1]),point(ep,ei[i+2])];if(Math.max(...tri.map(v=>v[1]))<world([0,r.diagnostics.raisedCoalTop-.003,0])[1])continue;total++;const target=[0,1,2].map(k=>tri.reduce((s,v)=>s+v[k],0)/3);if(!body.some(b=>hit(camera,target,b)))visible++;}assert.ok(total>0&&visible>=total/2,`LOD${lod} ${e.id}: ${visible}/${total} exposed top-coal faces`);}
 r.dispose();source.dispose(false,true);}
 }finally{scene.dispose();engine.dispose();}
});
test('malformed coal rejects before material allocation',async()=>{const engine=new NullEngine(),scene=new Scene(engine);try{const source=await sourceMesh(scene,0);source.setVerticesData('uv',new Float32Array(source.getTotalVertices()*2),false,2);const count=scene.materials.length;assert.throws(()=>createL2BrazierRepairParts(source,asset.id,['bp1_L2_000']),/coal cap/);assert.equal(scene.materials.length,count);}finally{scene.dispose();engine.dispose();}});
