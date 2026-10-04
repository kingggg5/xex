import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { MeshBuilder } from '@babylonjs/core/Meshes/meshBuilder.js';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData.js';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import '@babylonjs/core/Meshes/thinInstanceMesh.js';
import { bakeDressingGeometry, dressingAssetId, dressingCellLods, dressingKeep, dressingLodRanges,
  dressingPlan, dressingScale, validateDressing,blueprintEntries,blueprintScale } from '../src/sunmeadow-dressing.mjs';
const dressing=JSON.parse(readFileSync(new URL('../../../planning/levels/sunmeadow-v3-dressing.json',import.meta.url),'utf8'));
const manifest=JSON.parse(readFileSync(new URL('../../../assets/models/sunmeadow-props/manifest.json',import.meta.url),'utf8'));
const assets=new Map(Object.values(manifest.families).flat().map(a=>[a.id,a]));
const licensed=JSON.parse(readFileSync(new URL('../../../assets/models/blueprint-cc0/manifest.json',import.meta.url),'utf8'));
for(const asset of licensed.assets)assets.set(asset.id,asset);
const authored=JSON.parse(readFileSync(new URL('../../../assets/models/blueprint-p0-fence/manifest.json',import.meta.url),'utf8'));
for(const asset of authored.assets)assets.set(asset.id,asset);
assets.set('cc0_kenney_bush',{id:'cc0_kenney_bush',lods:[{tris:500}]});
assets.set('cc0_qn_mushroom_common',{id:'cc0_qn_mushroom_common',lods:[880,264,123].map(tris=>({tris}))});

test('old 411 baseline is preserved and P0 resolves without substitute proxy geometry',()=>{
  assert.equal(blueprintEntries(dressing,false).length,411);
  assert.ok(validateDressing(dressing.entries).length>411);
  const missing=dressing.entries.filter(e=>!dressingAssetId(e,assets));
  assert.ok(missing.every(e=>e.asset_id==='blueprint_cc0_sheep'),'missing sheep is an explicit component gap');
  assert.equal(missing.length,6);
  assert.equal(dressingAssetId({...dressing.entries[0],asset_id:'rock_M',variant:2},assets),'sm_medium_02');
});
test('input bounds and duplicate IDs fail before loading',()=>{
  assert.throws(()=>validateDressing([...dressing.entries,dressing.entries[0]]));
  assert.throws(()=>validateDressing([{...dressing.entries[0],yaw:NaN}]));
  assert.throws(()=>validateDressing([{...dressing.entries[0],collider:'wall'}]));
  assert.throws(()=>validateDressing(new Array(2001)));
});
test('F5 uses pointed timber and the one moved T1 rock is embedded clear of the live home',()=>{
  const fence=dressing.entries.filter(e=>e.blueprint_id==='F5');
  assert.equal(fence.length,12);assert.ok(fence.every(e=>e.asset_id==='blueprint_hunter_stakes'));
  const asset=assets.get('blueprint_hunter_stakes');assert.equal(asset.family,'craft');
  assert.deepEqual(asset.lods.map(l=>l.tris),[392,264,200]);
  assert.equal(asset.textures.atlas,'sm_craft');
  const moved=dressing.entries.find(e=>e.id==='bp_T1_035');
  assert.deepEqual([moved.x,moved.z],[17.5,-90]);assert.ok(moved.visual_base_y>0);
  assert.ok(Math.hypot(moved.x-14,moved.z+88)>moved.footprint_r+1.6);
  const collider=dressing.blueprint.collider_requests.find(c=>c.id===moved.id);
  assert.deepEqual(collider.center_xz,[17.5,-90]);assert.equal(collider.visual_base_y,moved.visual_base_y);
});
test('P0 uses the exact 20 IDs and authored anchors, with measured landmark dimensions',()=>{
  const bp=JSON.parse(readFileSync(new URL('../../../planning/levels/sunmeadow-blueprint-v1.json',import.meta.url),'utf8'));
  assert.deepEqual(dressing.blueprint.items.map(i=>i.id).sort(),bp.items.filter(i=>i.pr==='P0').map(i=>i.id).sort());
  for(const item of dressing.blueprint.items){const original=bp.items.find(i=>i.id===item.id);assert.deepEqual(item.anchor,original.xz??original.line?.[0]??original.poly[0]);}
  for(const entry of dressing.entries.filter(e=>e.target_height)){const asset=assets.get(entry.asset_id);if(!asset)continue;const scale=blueprintScale(entry,asset.bounds);assert.ok(Math.abs((asset.bounds.max[1]-asset.bounds.min[1])*scale[1]-entry.target_height)<1e-9);}
  assert.equal(dressing.entries.filter(e=>e.blueprint_id==='PL1').length,10);
  assert.equal(dressing.entries.filter(e=>e.blueprint_id==='ST2'&&e.asset_id.startsWith('sm_market_stall_')).length,3);
  assert.equal(dressing.entries.filter(e=>e.blueprint_id==='ST3'&&e.asset_id==='blueprint_cc0_tent').length,2);
  const waters=dressing.blueprint.water_bodies;assert.equal(waters.filter(w=>w.blueprint_id==='P1').length,3);assert.deepEqual(waters.find(w=>w.blueprint_id==='P2').center_xz,[22,-56]);
});
test('T1 is real shaped 6m terrain with upward-facing faces and an explicit flat-server contract',()=>{
  const m=dressing.blueprint.mound;assert.equal(Math.min(...m.positions.filter((_,i)=>i%3===1)),0);assert.equal(Math.max(...m.positions.filter((_,i)=>i%3===1)),6);assert.equal(m.walkable,false);assert.equal(m.physical_support_y,0);
  const normals=[];VertexData.ComputeNormals(m.positions,m.indices,normals);assert.ok(normals.filter((_,i)=>i%3===1).every(y=>y>0),'actual Babylon LH normals must face up');
  assert.ok(dressing.blueprint.collider_requests.filter(c=>c.blueprint_id==='T1').length>20);
});
test('dither intervals complement through both LOD transitions and far culling',()=>{
  const plan=dressingPlan({formFactor:'desktop',vegetationDensity:1});
  for(let d=0;d<plan.end;d+=.125){
    const ranges=dressingLodRanges(d,plan);
    assert.ok(ranges.length>=1&&ranges.length<=2);
    for(let i=0;i<ranges.length;i++){
      assert.ok(ranges[i].lower>=0&&ranges[i].upper<=1.00000001);
      if(i)assert.equal(ranges[i-1].upper,ranges[i].lower);
    }
    const expected=Math.min(1,(plan.end-d)/plan.fade);
    assert.ok(Math.abs(ranges.reduce((n,r)=>n+r.upper-r.lower,0)-expected)<1e-8);
  }
  assert.deepEqual(dressingLodRanges(Infinity,plan),[]);
  assert.deepEqual(dressingLodRanges(90,plan),[]);
  assert.deepEqual(dressingLodRanges(0,plan,1),[{lod:1,lower:0,upper:1}]);
});
test('density is stable and keeps all physical solids and explicit landmarks',()=>{
  for(const e of dressing.entries.filter(e=>e.collider==='solid'))assert.equal(dressingKeep(e,0),true);
  assert.equal(dressingKeep({...dressing.entries[0],landmark:true},0),true);
  const count=level=>dressing.entries.filter(e=>dressingKeep(e,level)).length;
  assert.ok(count(.35)<count(.75)&&count(.75)<=count(1));
  assert.equal(count(.75),count(.75));
});
test('selected alias geometry stays within the planned avoidance footprint',()=>{
  for(const e of dressing.entries){
    if(e.blueprint_id)continue;
    const a=assets.get(dressingAssetId(e,assets));if(!a?.bounds)continue;
    const s=dressingScale(e,a.bounds),r=Math.hypot(Math.max(...[a.bounds.min[0],a.bounds.max[0]].map(Math.abs)),
      Math.max(...[a.bounds.min[2],a.bounds.max[2]].map(Math.abs)));
    assert.ok(s>0&&s<=e.scale);
    assert.ok(r*s<=e.footprint_r+1e-8);
  }
});
test('actual manifest LOD counts, rather than source estimates, keep each cell below 40k',()=>{
  const entries=dressing.entries.flatMap(e=>{const id=dressingAssetId(e,assets);return id?[{...e,asset_id:id}]:[];});
  const cells=dressingCellLods(entries,assets);
  assert.ok(cells.size>=4);
  assert.ok([...cells.values()].every(c=>c.triangles<=40000));
  const impossible=new Map([['a',{lods:[{tris:50000}]}]]);
  assert.throws(()=>dressingCellLods([{asset_id:'a',x:0,z:0}],impossible));
  const transitions=new Map([['a',{lods:[{tris:30000},{tris:20000},{tris:10000}]}]]);
  const band=dressingCellLods([{asset_id:'a',x:0,z:0}],transitions).get('0,0');
  assert.equal(band.minimumLod,1,'a nominally in-budget LOD0 must include simultaneous handover geometry');
  assert.equal(band.triangles,30000);
});
test('quantized node plus mirrored importer hierarchy retains world shape before thin instancing',()=>{
  const engine=new NullEngine(),scene=new Scene(engine);
  try{
    const root=new TransformNode('import-root',scene);root.scaling.z=-1;
    const quantized=new TransformNode('dequantization',scene);quantized.parent=root;
    quantized.scaling.set(.0001,.0002,.0003);quantized.position.set(-1,2,3);
    const mesh=MeshBuilder.CreateBox('integer-space',{size:10000},scene);mesh.parent=quantized;
    mesh.position.set(2500,-1250,500);mesh.computeWorldMatrix(true);
    const positions=mesh.getVerticesData('position'),world=mesh.getWorldMatrix().clone();
    const originalIndices=mesh.getIndices(),originalNormals=mesh.getVerticesData('normal');
    const originalTriangle=originalIndices.slice(0,3).map(index=>Vector3.FromArray(positions,index*3));
    const expectedWinding=Math.sign(Vector3.Dot(Vector3.Cross(originalTriangle[1].subtract(originalTriangle[0]),
      originalTriangle[2].subtract(originalTriangle[0])),Vector3.FromArray(originalNormals,originalIndices[0]*3)));
    const before=[];
    for(let i=0;i<positions.length;i+=3)before.push(Vector3.TransformCoordinates(Vector3.FromArray(positions,i),world));
    bakeDressingGeometry(mesh);
    assert.equal(mesh.parent,null);assert.ok(mesh.getWorldMatrix().isIdentity());
    const after=mesh.getVerticesData('position');
    for(let i=0;i<before.length;i++)assert.ok(Vector3.Distance(before[i],Vector3.FromArray(after,i*3))<.00001);
    assert.equal(mesh.isVerticesDataPresent('tangent'),false);
    assert.equal(mesh.isVerticesDataPresent('uv2'),false);
    const normals=mesh.getVerticesData('normal'),indices=mesh.getIndices();
    for(let i=0;i<indices.length;i+=3){
      const [a,b,c]=indices.slice(i,i+3).map(index=>Vector3.FromArray(after,index*3));
      const winding=Vector3.Cross(b.subtract(a),c.subtract(a));
      assert.equal(Math.sign(Vector3.Dot(winding,Vector3.FromArray(normals,indices[i]*3))),expectedWinding,
        'mirroring must repair winding exactly once while retaining the scene handedness convention');
    }
  }finally{scene.dispose();engine.dispose();}
});
test('baking one shared glTF primitive leaves sibling node geometry and transforms intact',()=>{
  const engine=new NullEngine(),scene=new Scene(engine);
  try{
    const first=MeshBuilder.CreateBox('first',{size:1},scene),second=first.clone('second');
    first.position.set(2,3,4);second.position.set(-6,0,0);
    const original=second.getVerticesData('position').slice();
    assert.equal(first.geometry,second.geometry);
    bakeDressingGeometry(first);
    assert.notEqual(first.geometry,second.geometry);
    assert.deepEqual(second.getVerticesData('position'),original);
    assert.equal(second.position.x,-6);
  }finally{scene.dispose();engine.dispose();}
});
test('cell batches own matrix/fade vertex bindings with independent capacities',()=>{
  const engine=new NullEngine(),scene=new Scene(engine);
  try{
    const template=MeshBuilder.CreateBox('template',{size:1},scene);
    const small=template.clone('cell-small'),large=template.clone('cell-large');
    small.makeGeometryUnique();large.makeGeometryUnique();
    small.thinInstanceSetBuffer('matrix',new Float32Array(16),16,false);
    large.thinInstanceSetBuffer('matrix',new Float32Array(16*37),16,false);
    assert.notEqual(small.geometry,large.geometry);
    assert.notEqual(small.geometry,template.geometry);
    assert.equal(small.getVertexBuffer('world0').getData().length,16);
    assert.equal(large.getVertexBuffer('world0').getData().length,16*37);
    small.thinInstanceSetBuffer('ditherFade',new Float32Array(4),4,false);
    large.thinInstanceSetBuffer('ditherFade',new Float32Array(4*37),4,false);
    assert.equal(small.getVertexBuffer('ditherFade').getData().length,4);
    assert.equal(large.getVertexBuffer('ditherFade').getData().length,4*37);
  }finally{scene.dispose();engine.dispose();}
});
