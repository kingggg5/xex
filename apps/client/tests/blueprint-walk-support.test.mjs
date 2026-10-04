import test,{after}from'node:test';
import assert from'node:assert/strict';
import{readFileSync,mkdirSync,writeFileSync}from'node:fs';
import{createHash}from'node:crypto';
import{parseCityTraversal,sampleCityHeight,moveGroundedCapsule}from'../src/grounded-city.mjs';
import{staticColliderBoxes}from'../src/coordinate-collision.mjs';

const sourceUrl=new URL('../../../content/source/zones.json',import.meta.url),bytes=readFileSync(sourceUrl),zones=JSON.parse(bytes).zones;
const zone=zones.find(z=>z.city_traversal?.surfaces.some(s=>s.id==='blueprint_market_access'));
assert.ok(zone,'Canonical blueprint support surfaces must exist');
const blueprint=JSON.parse(readFileSync(new URL('../../../planning/levels/sunmeadow-blueprint-v1.json',import.meta.url)));
const field=parseCityTraversal(zone.city_traversal),boxes=staticColliderBoxes(zone.static_colliders),radius=.35,height=1.8,worldLimit=zone.half_extent;
const padIds={ST2:'blueprint_market_access',C2:'blueprint_merchant_access'};
const results=[];
const near=(value,target,label)=>assert.ok(typeof value==='number'&&Number.isFinite(value)&&Math.abs(value-target)<.0003,`${label}: ${value} versus ${target}`);
const hash=url=>createHash('sha256').update(readFileSync(url)).digest('hex');
const receipt={schema:'xexoria.blueprint-walk-support-tests/1',startedAt:new Date().toISOString(),bundleHash:'4f7f48d756feb999',bundleHashAuthority:'root-provided build identity; source hashes below are read from actual bytes',sourceSha256:{zones:createHash('sha256').update(bytes).digest('hex'),movement:hash(new URL('../src/grounded-city.mjs',import.meta.url)),collision:hash(new URL('../src/coordinate-collision.mjs',import.meta.url)),blueprint:hash(new URL('../../../planning/levels/sunmeadow-blueprint-v1.json',import.meta.url))},zone:zone.key??zone.id,capsule:{radius,height,worldLimit,externalMoveStep:.25,canonicalMaxSubstep:field.substepM},fieldStats:field.stats,results,limits:'Math-only canonical movement/support verification. Does not establish visual support alignment, new prop collider admission, native GPU behavior or server wire parity.'};

function padFor(item){const surface=zone.city_traversal.surfaces.find(s=>s.id===padIds[item]);assert.ok(surface);const xs=surface.vertices.map(v=>v[0]),zs=surface.vertices.map(v=>v[2]);return{surface,minX:Math.min(...xs),maxX:Math.max(...xs),minZ:Math.min(...zs),maxZ:Math.max(...zs),y:surface.vertices[0][1]};}
function walk(start,target){let position={...start};const steps=Math.ceil(Math.hypot(target.x-start.x,target.z-start.z)/.25),dx=(target.x-start.x)/steps,dz=(target.z-start.z)/steps;const samples=[];for(let i=0;i<steps;i++){position=moveGroundedCapsule(position,{x:dx,z:dz},radius,height,boxes,worldLimit,field);assert.notEqual(sampleCityHeight(field,position.x,position.z),null,'Route moved onto missing support');samples.push({...position});}return{end:position,steps,samples};}

for(const item of['ST2','C2']){
 test(`${item} canonical south approach reaches authored anchor and pad centre, then returns`,()=>{
  const pad=padFor(item),anchor=blueprint.items.find(i=>i.id===item).xz,start={x:anchor[0],y:0,z:7};
  const anchored=walk(start,{x:anchor[0],z:anchor[1]});near(anchored.end.x,anchor[0],'anchorX');near(anchored.end.z,anchor[1],'anchorZ');near(anchored.end.y,pad.y,'anchor support');
  const centre={x:(pad.minX+pad.maxX)/2,z:(pad.minZ+pad.maxZ)/2},arrived=walk(anchored.end,centre);near(arrived.end.x,centre.x,'centreX');near(arrived.end.z,centre.z,'centreZ');near(arrived.end.y,pad.y,'centre support');
  const returned=walk(arrived.end,start);near(returned.end.x,start.x,'returnX');near(returned.end.z,start.z,'returnZ');near(returned.end.y,0,'meadow support');
  results.push({item,kind:'approach-and-return',status:'PASS',start,anchor,centre,anchorOutcome:anchored.end,centreOutcome:arrived.end,returnOutcome:returned.end,moveCalls:anchored.steps+arrived.steps+returned.steps});
 });
 test(`${item} declared corners and radius-safe inset retain real pad support`,()=>{
  const pad=padFor(item),corners=pad.surface.vertices.map(v=>({x:v[0],z:v[2],declaredY:v[1]})),inset=radius+.01;
  const insetPoints=[[pad.minX+inset,pad.minZ+inset],[pad.maxX-inset,pad.minZ+inset],[pad.maxX-inset,pad.maxZ-inset],[pad.minX+inset,pad.maxZ-inset]];
  for(const p of corners)near(sampleCityHeight(field,p.x,p.z),p.declaredY,'declared corner');for(const[x,z]of insetPoints)near(sampleCityHeight(field,x,z),pad.y,'safe inset');
  results.push({item,kind:'declared-corner-and-inset',status:'PASS',corners,insetPoints,inset});
 });
}

test('nearby known city gaps reject outward movement and cannot teleport onto new pads',()=>{
 const gaps=[{item:'ST2',side:'west',x:-24,z:12},{item:'C2',side:'west',x:16,z:12},{item:'C2',side:'east',x:26,z:12}];
 for(const gap of gaps){const pad=padFor(gap.item);assert.equal(sampleCityHeight(field,gap.x,gap.z),null,'Known neighbouring city gap gained fake support');const start={x:gap.side==='west'?pad.minX+.5:pad.maxX-.5,y:pad.y,z:gap.z},out=moveGroundedCapsule(start,{x:gap.x-start.x,z:0},radius,height,boxes,worldLimit,field);assert.ok(out.x>=pad.minX-.00005&&out.x<=pad.maxX+.00005,'Walk leaked into gap');assert.ok(Math.abs(out.x-gap.x)>.5,'Walk reached unsupported target');
  const unsupported={x:gap.x,y:pad.y,z:gap.z},back=moveGroundedCapsule(unsupported,{x:start.x-gap.x,z:0},radius,height,boxes,worldLimit,field);assert.deepEqual(back,unsupported,'Missing support must not snap onto pad');results.push({item:gap.item,kind:'known-gap-rejection',status:'PASS',gap,start,outcome:out,unsupportedStartOutcome:back});
 }
});

after(()=>{receipt.finishedAt=new Date().toISOString();receipt.status=results.length===7?'PASS':'INCOMPLETE_OR_FAILED';const dir=new URL('../../../planning/evidence/blueprint-p0-20261003/',import.meta.url);mkdirSync(dir,{recursive:true});writeFileSync(new URL('walk-support-tests.json',dir),JSON.stringify(receipt,null,2));});
