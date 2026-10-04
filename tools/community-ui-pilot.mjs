// One owned local trader for native UI review; exits after 10 minutes.
import {connectAuthenticatedClient,createSession,issueJoinTicket,toArrayBuffer} from './net-driver.mjs';
import {decodeServerMessage,encodeCold,encodeInput} from '../apps/client/src/wire.mjs';
import {writeFileSync} from 'node:fs';
const base=new URL('http://127.0.0.1:3002');const origin='http://127.0.0.2:5174';const cookie=await createSession(base,origin);
await fetch(new URL('/session/channel',base),{method:'POST',headers:{Origin:origin,Cookie:cookie,'Content-Type':'application/json'},body:'{"channel":0}'});
const c=await connectAuthenticatedClient(base,new URL('ws://127.0.0.1:3002/ws'),origin,cookie,await issueJoinTicket(base,origin,cookie),308);
const seen=new Set();let chain=Promise.resolve();const log=[];let seq=1;
function send(action){c.socket.send(encodeCold({t:'community',action}));}
c.socket.addEventListener('message',async e=>{
 const m=decodeServerMessage(await toArrayBuffer(e.data),308);
 if(m.type==='snapshot') {
    const self=m.players.find(p=>p.id===c.welcome.player_id);
    if(self){const dx=-self.x,dz=-20-self.z,d=Math.hypot(dx,dz);c.socket.send(encodeInput(c.welcome.epoch,seq++,d>1?dx/d:0,d>1?dz/d:0,0));}
    return;
 }
 if(m.type!=='cold')return;
 if(m.data.t==='character_state'){console.log(JSON.stringify({handle:m.data.handle,name:m.data.name,device:'mobile'}));}
 if(m.data.key==='community_result')log.push(m.data.params.reason);
 if(m.data.key!=='community_state'||!m.data.params.trade)return;
 const t=m.data.params.trade;const key=t.id+':'+t.revision;if(seen.has(key)||t.pending)return;seen.add(key);
 chain=chain.then(async()=>{await new Promise(r=>setTimeout(r,180));if(t.incoming&&!t.accepted)send({kind:'accept',trade:t.id,revision:t.revision});else if(t.accepted&&t.mine.gold===0)send({kind:'offer',trade:t.id,revision:t.revision,offer:{gold:10,items:{}}});else if(t.accepted&&!t.confirmed)send({kind:'confirm',trade:t.id,revision:t.revision});});
});
send({kind:'sync',device:'mobile'});await new Promise(r=>setTimeout(r,120));c.socket.send(encodeCold({t:'resync'}));
await new Promise(r=>setTimeout(r,180));c.socket.send(encodeCold({t:'chat',channel:'room',text:'[Local QA] Preview trader ready.'}));
await new Promise(r=>setTimeout(r,600000));await c.socket.close();
writeFileSync('planning/evidence/community-20261001/ui-pilot.json',JSON.stringify({owned_local_trader:true,closed:true,results:log},null,2));
