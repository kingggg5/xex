import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {VertexData} from '@babylonjs/core/Meshes/mesh.vertexData.js';
import {Matrix,Quaternion,Vector3} from '@babylonjs/core/Maths/math.vector.js';
import {blueprintFloor,blueprintScale,dressingCellLods} from '../src/sunmeadow-dressing.mjs';
const read=p=>JSON.parse(readFileSync(new URL('../../../'+p,import.meta.url),'utf8'));
const p0=read('planning/levels/sunmeadow-v3-dressing.json'),p1=read('planning/levels/sunmeadow-v3-dressing-p1.json'),authority=read('planning/levels/sunmeadow-blueprint-v1.json');
test('P1 opt-in dataset preserves every frozen P0 blueprint transform and exact20P1 authority',()=>{
  assert.equal(createHash('sha256').update(readFileSync(new URL('../../../planning/levels/sunmeadow-v3-dressing.json',import.meta.url))).digest('hex'),'da6bd4a1b034f9a0a9e201065c9d4d1d3f336c9505d002e32a54caadbb44b6ec');
  assert.deepEqual(p1.entries.filter(e=>e.blueprint_id&&!e.blueprint_wave),p0.entries.filter(e=>e.blueprint_id));
  assert.deepEqual(p1.p1.items.map(i=>i.id).sort(),authority.items.filter(i=>i.pr==='P1').map(i=>i.id).sort());
  for(const i of p1.p1.items){const a=authority.items.find(a=>a.id===i.id);assert.deepEqual(i.anchor,a.xz??a.line?.[0]??a.poly[0]);}
});
test('P3 and N1 are explicit terrain dependencies without below-hill ponds or fake enemy entries',()=>{
  for(const id of ['P3','N1']){assert.equal(p1.p1.items.find(i=>i.id===id).status,'DEPENDENCY_ROOT_TERRAIN');assert.equal(p1.entries.filter(e=>e.blueprint_id===id).length,0);}
  assert.ok(!p1.blueprint.water_bodies.some(w=>w.blueprint_id==='P3'));
  assert.equal(p1.p1.items.find(i=>i.id==='S5').status,'MISSING_HERO_ASSET');
  assert.ok(p1.entries.filter(e=>e.blueprint_id==='S5').every(e=>e.collider==='none'));
});
test('P1 mound normals point up and every source footprint requests closed visual-v1 admission',()=>{
  assert.equal(p1.blueprint.extra_mounds.length,5);
  for(const m of p1.blueprint.extra_mounds){const normals=[];VertexData.ComputeNormals(m.positions,m.indices,normals);assert.ok(normals.filter((_,i)=>i%3===1).every(n=>n>.05),m.id);assert.equal(m.walkable,false);assert.equal(m.physical_support_y,0);assert.equal(m.closure_required,true);assert.equal(m.admission,'DEPENDENCY_ROOT_TERRAIN');}
  assert.ok(p1.entries.filter(e=>e.blueprint_id==='R8'&&e.x>0).every(e=>typeof e.visual_absolute_base_y==='number'));
});
test('P1 rotated kit floor matches actual Babylon transform while frozenP0 bottom policy stays unchanged',()=>{
  const bounds={min:[-1,0,-2],max:[1,2,2]},scale=[1.25,.9,.75],entry={blueprint_wave:'P1',yaw:.9,pitch:.2,roll:Math.PI/2};
  const matrix=Matrix.Compose(new Vector3(...scale),Quaternion.RotationYawPitchRoll(entry.yaw,entry.pitch,entry.roll),Vector3.Zero());
  let actual=Infinity;for(const x of [bounds.min[0],bounds.max[0]])for(const y of [bounds.min[1],bounds.max[1]])for(const z of [bounds.min[2],bounds.max[2]])actual=Math.min(actual,Vector3.TransformCoordinates(new Vector3(x,y,z),matrix).y);
  assert.ok(Math.abs(blueprintFloor(entry,bounds,scale)-actual)<1e-6);
  assert.equal(blueprintFloor({...entry,blueprint_wave:undefined},bounds,scale),0);
});
test('40k cell cap includes fixed terrain geometry beside bothLOD handover representations',()=>{
  const assets=new Map([['kit',{lods:[20000,15000,2000].map(tris=>({tris}))}]]);
  const cells=dressingCellLods([{asset_id:'kit',x:1,z:-1}],assets,40000,new Map([['0,-1',6000]]));
  assert.equal(cells.get('0,-1').minimumLod,1);assert.equal(cells.get('0,-1').triangles,23000);
});
