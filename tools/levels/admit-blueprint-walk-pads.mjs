import {readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {BLUEPRINT_WALK_PADS} from '../../apps/client/src/blueprint-walk-support.mjs';
import {parseCityTraversal,sampleCityHeight} from '../../apps/client/src/grounded-city.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const file=path.join(root,'content/source/zones.json'),before=readFileSync(file),data=JSON.parse(before);
const out=path.join(root,'planning/evidence/blueprint-p0-20261003');mkdirSync(out,{recursive:true});
const backup=path.join(out,'zones-before-walk-pads.json');if(!existsSync(backup))writeFileSync(backup,before);
const zone=data.zones[0],fieldBefore=parseCityTraversal(zone.city_traversal,zone.half_extent);
const old=BLUEPRINT_WALK_PADS.map(p=>({id:p.id,support:sampleCityHeight(fieldBefore,(p.boundsXZ[0]+p.boundsXZ[1])/2,(p.boundsXZ[2]+p.boundsXZ[3])/2)}));
for(const pad of BLUEPRINT_WALK_PADS){
 if(zone.city_traversal.surfaces.some(s=>s.id===pad.id))continue;
 const [x0,x1,z0,z1]=pad.boundsXZ;
 zone.city_traversal.surfaces.push({id:pad.id,kind:'plaza',vertices:[[x0,pad.y,z0],[x1,pad.y,z0],[x1,pad.y,z1],[x0,pad.y,z1]],triangles:[[0,2,1],[0,3,2]]});
}
const field=parseCityTraversal(zone.city_traversal,zone.half_extent),checks=[];
for(const pad of BLUEPRINT_WALK_PADS){
 const [x0,x1,z0,z1]=pad.boundsXZ;
 for(const x of [x0+.45,(x0+x1)/2,x1-.45])for(const z of [z0+.45,9,z1-.45]){
  const y=sampleCityHeight(field,x,z);if(y!==pad.y)throw new Error(`Unsupported pad ${pad.id}:${x},${z}`);
  checks.push({id:pad.id,x,z,y});
 }
}
const bytes=Buffer.from(JSON.stringify(data,null,2)+'\n');writeFileSync(file,bytes);
const hash=b=>createHash('sha256').update(b).digest('hex');
const receipt={schema:'xexoria.blueprint-walk-pads/1',beforeSha256:hash(before),afterSha256:hash(bytes),old,checks,verdict:'SOURCE_AND_RENDER_CONTRACT_VALIDATED',runtimeServerRebuild:'PENDING',renderContract:'blueprint-walk-support.mjs exactsamebounds/Y0',collisionAdmission:'P0 solid objects separate pending contract'};
writeFileSync(path.join(out,'walk-pads-receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({checks:checks.length,old,sourceSha256:receipt.afterSha256}));
