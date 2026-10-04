import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import{VertexData}from'@babylonjs/core/Meshes/mesh.vertexData.js';
import{rainPuddleVisibility,supportedRainPuddles}from'../src/nature-water.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../../../'+p,import.meta.url),'utf8'));
const p1=read('planning/levels/sunmeadow-v3-dressing-p1.json'),p2=read('planning/levels/sunmeadow-v3-dressing-p2.json');
test('P2preservesallP0/P1blueprinttransformsand exactfourP2authority',()=>{
 assert.deepEqual(p2.entries.filter(e=>e.blueprint_id&&e.blueprint_wave!=='P2'),p1.entries.filter(e=>e.blueprint_id));
 assert.deepEqual(p2.p2.items.map(i=>i.id).sort(),['F6','L3','P4','S6']);
 const guardians=p2.entries.filter(e=>e.blueprint_id==='S6'&&e.asset_id==='blueprint_cc0_guardian');
 assert.deepEqual(guardians.map(e=>[e.x,e.z,e.target_height]),[[-6,-96,3.5],[6,-96,3.5]]);
 assert.equal(p2.entries.filter(e=>e.blueprint_id==='L3').length,3);
 assert.ok(p2.entries.filter(e=>e.blueprint_id==='F6').every(e=>Math.abs(e.x)===6&&e.collider==='none'&&e.z<-84&&e.z>-93));
});
test('P4onlyacceptsactualY0support atcentreandentireoutline,no null/raised phantom floor',()=>{
 const b=p2.p2.rain_bodies;assert.equal(supportedRainPuddles(b,()=>0).accepted.length,3);
 assert.equal(supportedRainPuddles(b,()=>null).accepted.length,0);assert.equal(supportedRainPuddles(b,()=>.2).accepted.length,0);
 const corner=b[0].outline_xz[0];assert.ok(supportedRainPuddles(b,(x,z)=>x===corner[0]&&z===corner[1]?null:0).pending.includes(b[0].id));
 assert.ok(b.every(b=>b.host_cut===false&&b.collider==='none'&&b.rain_only&&b.surface_y===.012));
});
test('P4clear/rain/hidden/failuretransitionsuseexistingrain state andfailclosed',()=>{
 const s={ready:true,revealed:true,culled:false,rain:0};assert.equal(rainPuddleVisibility(s),false);
 assert.equal(rainPuddleVisibility({...s,rain:1}),true);
 for(const state of [{rain:1,ready:false},{rain:1,revealed:false},{rain:1,culled:true},{rain:NaN}])assert.equal(rainPuddleVisibility({...s,...state}),false);
});
test('P4fanwindingmatchesactualBabylonupnormals',()=>{
 for(const b of p2.p2.rain_bodies){const positions=[b.center_xz[0],b.surface_y,b.center_xz[1],...b.outline_xz.flatMap(p=>[p[0],b.surface_y,p[1]])],indices=[];
 for(let k=0;k<b.outline_xz.length;k++)indices.push(0,k+1,(k+1)%b.outline_xz.length+1);
 const normals=[];VertexData.ComputeNormals(positions,indices,normals);assert.ok(normals.filter((_,i)=>i%3===1).every(y=>y>.999));}
});
