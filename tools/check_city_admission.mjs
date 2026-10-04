import fs from 'node:fs/promises';
import path from 'node:path';
import {parseCityTraversal,sampleCityHeight,moveGroundedCapsule} from '../apps/client/src/grounded-city.mjs';
import {staticColliderBoxes} from '../apps/client/src/coordinate-collision.mjs';

const input=process.argv[2]??'assets/models/reference-city/r5/traversal-repair-candidate/city-traversal-v1.json';
const data=JSON.parse(await fs.readFile(input,'utf8'));
const zones=JSON.parse(await fs.readFile('apps/client/public/content/bundle.json','utf8'));
const field=parseCityTraversal(data,zones.zones[0].half_extent),boxes=staticColliderBoxes(zones.zones[0].static_colliders);
const author=JSON.parse(await fs.readFile('planning/evidence/city-floor-alignment-20261001-traversal.json','utf8'));
const routes=author.routes.concat([{id:'wizard-entry-new-flight',points_xz:[[-65,248.8],[-65,255.25]]},
 {id:'arrival-east-bank',points_xz:[[0,-2],[8,-2],[8,31],[10.1,35],[10.1,130],[20,156]]},
 {id:'arrival-narrow-gate',points_xz:[[0,-2],[6.95,4],[6.95,31],[10.1,35],[10.1,130],[20,156]]}]);
const results=[];
for(const route of routes){
 let [x,z]=route.points_xz[0],pos={x,z,y:sampleCityHeight(field,x,z)},failure=null,count=0;
 if(pos.y===null){results.push({id:route.id,passed:false,failure:'unsupported-start'});continue;}
 for(let segment=0;segment<route.points_xz.length-1&&!failure;segment++){
  const [a,b]=[route.points_xz[segment],route.points_xz[segment+1]],steps=Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/.05);
  for(let i=1;i<=steps;i++){
   const target={x:a[0]+(b[0]-a[0])*i/steps,z:a[1]+(b[1]-a[1])*i/steps};
   const next=moveGroundedCapsule(pos,{x:target.x-pos.x,z:target.z-pos.z},.35,1.8,boxes,zones.zones[0].half_extent,field);count++;
   if(Math.hypot(next.x-target.x,next.z-target.z)>.004){failure={target,actual:next,support:sampleCityHeight(field,target.x,target.z)};break;}pos=next;
  }
 }
 results.push({id:route.id,passed:!failure,count,end:pos,failure});
}
const report={input:path.resolve(input),boxCount:boxes.length,fieldStats:field.stats,routes:results,passed:results.every(row=>row.passed)};
await fs.writeFile('planning/evidence/city-admission-collision-20261001.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({boxCount:boxes.length,passed:report.passed,failed:results.filter(row=>!row.passed)}));
process.exitCode=report.passed?0:1;
