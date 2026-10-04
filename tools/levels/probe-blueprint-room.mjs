import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createSession,issueJoinTicket,connectAuthenticatedClient,decodeSocketMessage,delay,waitForMessage} from '../net-driver.mjs';
import {encodeInput,fnv1a64} from '../../apps/client/src/wire.mjs';
import {parseCityTraversal,sampleCityHeight} from '../../apps/client/src/grounded-city.mjs';

const prefix='planning/evidence/blueprint-p0-20261003/';
const cityProbe=process.argv.includes('--city');
const bytes=readFileSync(prefix+'private-room/content/build/993a2b5474ee84b1/bundle.json');
const bundle=JSON.parse(bytes),zone=bundle.zones[0],field=parseCityTraversal(zone.city_traversal,zone.half_extent);
const http=new URL('http://127.0.0.1:3931'),ws=new URL('ws://127.0.0.1:3931/ws'),origin='http://127.0.0.1:5173';
const receipt={schema:'xexoria.blueprint-private-room-probe/1',contentHash:fnv1a64(bytes).toString(16).padStart(16,'0'),
 bundleSha256:createHash('sha256').update(bytes).digest('hex'),startedAt:new Date().toISOString(),status:'RUNNING',routes:[],
 scope:'Authenticated v8 local room input/snapshot and capsule support. No Babylon or device qualification.'};
let client,latest,fault;
try{
 const health=await(await fetch(new URL('/healthz',http))).json();assert.equal(health.protocol,8);
 const cookie=await createSession(http,origin);
 const selected=await fetch(new URL('/session/channel',http),{method:'POST',headers:{Origin:origin,Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify({channel:0})});assert.equal(selected.status,200);
 const ticket=await issueJoinTicket(http,origin,cookie);client=await connectAuthenticatedClient(http,ws,origin,cookie,ticket,zone.half_extent);
 assert.equal(client.welcome.type,'welcome');assert.equal(client.welcome.content_hash.toString(16).padStart(16,'0'),receipt.contentHash);
 const accept=message=>{if(message.type==='snapshot')latest=message.players.find(p=>p.id===client.welcome.player_id);};
 client.socket.addEventListener('message',event=>decodeSocketMessage(client.socket,event.data,zone.half_extent).then(accept).catch(error=>{fault=error;}));
 const initial=await waitForMessage(client.socket,m=>m.type==='snapshot',5000,zone.half_extent);accept(initial);assert.ok(latest);
 receipt.spawn={x:latest.x,z:latest.z,hp:latest.hp};
 async function walk(label,x,z){
  const started=Date.now();
  while(Math.hypot(latest.x-x,latest.z-z)>.3){
   if(fault)throw fault;if(Date.now()-started>20000)throw new Error(`Route stalled ${label} at ${latest.x},${latest.z}`);
   if(latest.hp===0)throw new Error(`Player died during ${label}; no traversal qualification`);
   const dx=x-latest.x,dz=z-latest.z,length=Math.hypot(dx,dz);
   client.socket.send(encodeInput(client.welcome.epoch,++client.sequence,dx/length,dz/length,0));
   await delay(50);
   const y=sampleCityHeight(field,latest.x,latest.z);assert.notEqual(y,null,'Authoritative position must have support');
  }
  client.socket.send(encodeInput(client.welcome.epoch,++client.sequence,0,0,0));
  receipt.routes.push({label,target:[x,z],reached:{x:latest.x,z:latest.z,supportY:sampleCityHeight(field,latest.x,latest.z),hp:latest.hp},seconds:(Date.now()-started)/1000});
  console.log(JSON.stringify({route:label,reached:receipt.routes.at(-1).reached}));
 }
 if(cityProbe){
  const plan=JSON.parse(readFileSync(prefix+'city-ingress/route-preflight.json'));
  const route=plan.detourRoutes.find(row=>row.id==='east-bounded-detour-castle');assert.ok(route);
  for(const [index,point] of route.points.entries())await walk('city-forward-'+index,...point);
  for(const [index,point] of route.points.slice(0,-1).reverse().entries())await walk('city-return-'+index,...point);
 }else{
  const plan=JSON.parse(readFileSync(prefix+'private-route-preflight.json'));
  assert.equal(plan.rows.length,19);assert.ok(plan.rows.every(row=>row.pass),'Route must clear candidate props and canonical static colliders');
  for(const [index,row] of plan.rows.entries())await walk('preflight-'+index,...row.target);
 }
 receipt.status='PASS_PRIVATE_AUTHENTICATED_ROUTES';receipt.limits=['No native player camera walk recorded.','Mound edge and solid front checks are Rust/client parity checks, not covered by this live route.','No default collision/content promotion.'];
}catch(error){receipt.status='FAIL';receipt.reason=error.message;process.exitCode=1;}
finally{client?.socket.close();receipt.finishedAt=new Date().toISOString();writeFileSync(prefix+(cityProbe?'private-city-room-probe.json':'private-room-probe.json'),JSON.stringify(receipt,null,2)+'\n');}
console.log(JSON.stringify({status:receipt.status,routes:receipt.routes.length,reason:receipt.reason??null}));
