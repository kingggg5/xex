import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseCityTraversal,sampleCityHeight,moveGroundedCapsule} from '../../apps/client/src/grounded-city.mjs';

const read=p=>JSON.parse(readFileSync(p));
const hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const prefix='planning/evidence/blueprint-p0-20261003/';
const zones=read('content/source/zones.json'),zone=zones.zones[0];
const field=parseCityTraversal(zone.city_traversal,zone.half_extent);
const dressing=read('planning/levels/sunmeadow-v3-dressing.json');
const entries=new Map(dressing.entries.map(e=>[e.id,e]));
const requests=dressing.blueprint.collider_requests;
const audit=read(prefix+'collision-admission-audit.json');
const measured=new Map(audit.measured_cc0_ground_band_candidates_NOT_ADMITTED.map(item=>[item.blocker.id,item.blocker]));
const blockers=[],skipped=[];
for(const request of requests){
 const entry=entries.get(request.id);
 if(!entry)throw new Error('Missing visual entry '+request.id);
 if(['T1','ST4','R6'].includes(request.blueprint_id)){skipped.push({id:request.id,reason:'Mound footprint controls access; elevated structure is not a flat-ground blocker.'});continue;}
 const support=sampleCityHeight(field,entry.x,entry.z);
 if(support===null)throw new Error('Missing canonical support '+entry.id);
 const height=request.height_m??entry.target_height??entry.target_size_xyz?.[1];
 if(!(height>0))throw new Error('Missing real height '+entry.id);
 const base=support+(entry.visual_base_y??0);
 if(measured.has(entry.id)){
  const blocker=measured.get(entry.id);
  blockers.push({...blocker,polygon_xz:blocker.polygon_xz.map(p=>[...p])});
  continue;
 }
 let polygon;
 if(request.shape==='box'){
  const [sx,sz]=request.size_xz,c=Math.cos(entry.yaw),s=Math.sin(entry.yaw);
  polygon=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,z])=>[entry.x+c*x*sx/2+s*z*sz/2,entry.z-s*x*sx/2+c*z*sz/2]);
 }else if(request.shape==='circle'){
  const radius=request.radius_m/Math.cos(Math.PI/16);
  polygon=Array.from({length:16},(_,i)=>[entry.x+radius*Math.cos(i*Math.PI/8),entry.z+radius*Math.sin(i*Math.PI/8)]);
 }else throw new Error('Unsupported collision shape '+request.shape);
 blockers.push({id:entry.id,kind:request.blueprint_id==='PL1'?'tree_trunk':'solid_structure',polygon_xz:polygon,y_min:base,y_max:base+height});
}
blockers.push(audit.t1.recommended_filled_barrier);
const candidateInput={...zone.city_traversal,blockers:[...zone.city_traversal.blockers,...blockers]};
const candidate=parseCityTraversal(candidateInput,zone.half_extent);
const checks=[];
for(const radius of [.35,.45]){
 for(const [label,x,z] of [['market-side',-12,7],['merchant-side',24,7]]){
  let p={x,y:0,z};for(let i=0;i<20;i++)p=moveGroundedCapsule(p,{x:0,z:.25},radius,1.8,[],zone.half_extent,candidate);
  if(Math.abs(p.z-12)>1e-4)throw new Error('Candidate blocked apron side approach '+label);
  const reached={...p};for(let i=0;i<20;i++)p=moveGroundedCapsule(p,{x:0,z:-.25},radius,1.8,[],zone.half_extent,candidate);
  if(Math.abs(p.z-7)>1e-4)throw new Error('Candidate blocked apron return '+label);
  checks.push({label,radius,approach:reached,returned:p});
 }
 for(const [label,x] of [['market-front',-17],['merchant-front',21]]){
  let p={x,y:0,z:5};for(let i=0;i<25;i++)p=moveGroundedCapsule(p,{x:0,z:.2},radius,1.8,[],zone.half_extent,candidate);
  if(p.z>=9-radius)throw new Error('Solid prop allowed centre penetration '+label);
  checks.push({label,radius,blocked:p});
 }
 // The closed footprint must reject every attempted edge crossing, including ring gaps.
 const poly=audit.t1.recommended_filled_barrier.polygon_xz;
 for(let i=0;i<poly.length;i++){
  const a=poly[i],b=poly[(i+1)%poly.length],mid=[(a[0]+b[0])/2,(a[1]+b[1])/2];
  const dx=30-mid[0],dz=-94-mid[1],length=Math.hypot(dx,dz),ux=dx/length,uz=dz/length;
  let p={x:mid[0]-ux*(radius+.6),y:0,z:mid[1]-uz*(radius+.6)};
  for(let j=0;j<6;j++)p=moveGroundedCapsule(p,{x:ux*.2,z:uz*.2},radius,1.8,[],zone.half_extent,candidate);
  const progress=(p.x-mid[0])*ux+(p.z-mid[1])*uz;
  if(progress>=0)throw new Error('Mound edge entry was admitted '+i);
  checks.push({label:'mound-edge-'+i,radius,blocked:p});
 }
}
const result={schema:'xexoria.blueprint-collision-addon/1',status:'CANDIDATE_ONLY_NOT_ADMITTED',zone:zone.key,
 sourceSha256:hash('content/source/zones.json'),visualSha256:hash('planning/levels/sunmeadow-v3-dressing.json'),
 cc0ManifestSha256:hash('assets/models/blueprint-cc0/manifest.json'),blockers,skipped,checks,
 limits:['No default source mutation: visuals and server collision must be activated together.','CC0 hulls preserve decoded ground-band geometry; tentative closed tents have no admitted interior route.','Mound v1 is closed. A walkable v2 needs server height support. Planned boar row27 must relocate before v2 migration.','Live browser/server traversal, all routes and phone budgets remain unverified.']};
writeFileSync(prefix+'collision-addon-candidate.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({blockers:blockers.length,checks:checks.length,status:result.status}));
