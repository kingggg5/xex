import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';
import {fileURLToPath} from 'node:url';
import{NullEngine}from'@babylonjs/core/Engines/nullEngine.js';import{Scene}from'@babylonjs/core/scene.js';import{MeshBuilder}from'@babylonjs/core/Meshes/meshBuilder.js';import{VertexBuffer}from'@babylonjs/core/Buffers/buffer.js';
import{bakeDressingGeometry}from'../src/sunmeadow-dressing.mjs';import{packDressingVertexBuffers}from'../src/dressing-vertex-packing.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../../../'+p,import.meta.url),'utf8'));
test('rain vegetation clipping follows the accepted puddle lifecycle',async()=>{
 const {build}=await import('esbuild');
 const compiled=await build({entryPoints:[fileURLToPath(new URL('../src/water-art-pass4b-materials.ts',import.meta.url))],bundle:true,write:false,platform:'node',format:'esm',logLevel:'silent'});
 const {WaterArtRainGrassClip}=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
 const plugin=Object.create(WaterArtRainGrassClip.prototype),written=[];
 const buffer={updateFloat4:(...args)=>written.push(args)};
 for(const state of[undefined,{ready:false,visible:false,rain:1},{ready:true,visible:false,rain:1},{ready:false,visible:true,rain:1},{ready:true,visible:true,rain:.6}]){
  plugin.sceneRef={metadata:{naturalWater:{rainPuddles:state}}};plugin.bindForSubMesh(buffer);
 }
 assert.deepEqual(written.map(row=>row[1]),[0,0,0,0,.6]);
});
test('candidategeometrycapsand48organicLotus retain sourceYinvariants',()=>{
 const d=read('planning/evidence/water-art-pass4b-20261003/water-derived.json'),m=read('apps/client/src/assets/world/water-art-pass4b/water-manifest.json');
 assert.equal(d.lakes.find(l=>l.id==='lotus_mere_pond').outline_xz.length,48);assert.equal(d.lakes.find(l=>l.id==='lotus_mere_pond').surface_y,-.3);assert.equal(d.lakes.find(l=>l.id==='brightwater_cove_lake').surface_y,-.35);
 assert.ok(m.meshes.surface.triangles<=1300);assert.ok(m.support.bank_triangles<=2000);assert.ok(m.support.bed_triangles<=6000);
});
test('candidateoverlayusesexact8approvedL1IDs andverifiedkitassetswithoutnewmodels',()=>{
 const o=read('planning/levels/sunmeadow-water-art-pass4b-overlay.json'),p=read('planning/evidence/blueprint-light-anchors-20261003/l1-anchor-proposal-r01.json'),m=read('assets/models/sunmeadow-props/manifest.json');
 assert.deepEqual(o.L1_patches.map(e=>e.id),p.proposal_rows.map(e=>e.id));for(const e of o.L1_patches){const r=p.proposal_rows.find(r=>r.id===e.id);assert.deepEqual([e.x,e.z],r.proposed.q);}
 const assets=new Set(Object.values(m.families).flat().map(a=>a.id));assert.ok(o.entries.every(e=>assets.has(e.asset_id)&&!e.pitch&&!e.roll&&e.collider==='none'));
 assert.deepEqual(o.legacy_float_patch.triangle_ordinals,[180,200]);
});
test('bakepreservesRGB3/RGBA4colourstride thenuniqueclonepacksindependently',()=>{
 const engine=new NullEngine(),scene=new Scene(engine);try{for(const size of[3,4]){
 const mesh=MeshBuilder.CreateBox('color'+size,{},scene),count=mesh.getTotalVertices(),color=new Float32Array(count*size);for(let i=0;i<count;i++){color[i*size]=.2;color[i*size+1]=.5;color[i*size+2]=.3;if(size===4)color[i*size+3]=.75;}
 mesh.setVerticesData(VertexBuffer.ColorKind,color,false,size);mesh.scaling.set(2,1.5,.7);bakeDressingGeometry(mesh,{preserveColor:true});assert.equal(mesh.getVertexBuffer('color').getSize(),size);assert.deepEqual(mesh.getVerticesData('color'),color);
 packDressingVertexBuffers(mesh);const clone=mesh.clone('clone'+size);clone.makeGeometryUnique();packDressingVertexBuffers(clone);assert.equal(clone.getVertexBuffer('color').getSize(),size);assert.deepEqual(clone.getVerticesData('color'),color);assert.notEqual(clone.getVertexBuffer('color').getBuffer(),mesh.getVertexBuffer('color').getBuffer());}}
 finally{scene.dispose();engine.dispose();}
});
