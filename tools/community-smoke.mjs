// Bounded local-only gameplay check. No real payments or public messages.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {writeFileSync,mkdirSync} from 'node:fs';
import {connectAuthenticatedClient,createSession,issueJoinTicket,toArrayBuffer} from './net-driver.mjs';
import {decodeServerMessage,encodeCold} from '../apps/client/src/wire.mjs';
const base=new URL('http://127.0.0.1:3002');const ws=new URL('ws://127.0.0.1:3002/ws');const origin='http://127.0.0.2:5174';
const clients=[];const proof={scenario:'isolated-community-v1',checks:[],real_payment:false,storage:'session-only'};
async function join(channel,device,cookie=null){
    cookie??=await createSession(base,origin);
    const response=await fetch(new URL('/session/channel',base),{method:'POST',headers:{Origin:origin,Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify({channel})});assert.equal(response.status,200);
    const c=await connectAuthenticatedClient(base,ws,origin,cookie,await issueJoinTicket(base,origin,cookie),1200);
    c.cookie=cookie;c.messages=[];c.socket.addEventListener('message',async e=>{try {const message=decodeServerMessage(await toArrayBuffer(e.data),1200);if(message.type==='cold')c.messages.push(message.data);}catch(error){c.error=error;}});clients.push(c);
    await command(c,{kind:'sync',device},m=>m.key==='community_state');
    const state=await cold(c,{t:'resync'},m=>m.t==='character_state');c.handle=state.handle;return c;
}
function wait(c,start,predicate){return new Promise((resolve,reject)=>{const began=Date.now();const timer=setInterval(()=>{const m=c.messages.slice(start).find(predicate);if(m){clearInterval(timer);resolve(m);}else if(Date.now()-began>5000){clearInterval(timer);reject(new Error('Timed out: '+predicate.toString()));}},20);});}
async function cold(c,payload,predicate){await new Promise(resolve=>setTimeout(resolve,80));const start=c.messages.length;c.socket.send(encodeCold(payload));return wait(c,start,predicate);}
function command(c,action,predicate=m=>m.key==='community_result'){return cold(c,{t:'community',action},predicate);}
async function state(c){return (await command(c,{kind:'sync',device:c===clients[0]?'desktop':'mobile'},m=>m.key==='community_state')).params;}
async function character(c){return cold(c,{t:'resync'},m=>m.t==='character_state');}
const accepted=m=>assert.equal(m.params.reason,'accepted');
try{
    const a=await join(0,'desktop');const b=await join(0,'mobile');const observer=await join(1,'mobile');
    const original=await character(a);const order=randomUUID();
    accepted(await command(a,{kind:'test_topup',pack:'preview_300',op_id:order}));
    accepted(await command(a,{kind:'test_topup',pack:'preview_300',op_id:order}));
    let data=await state(a);assert.equal(data.test_credits,300);assert.equal(data.order_count,1);assert.equal((await character(a)).coin,original.coin);
    assert.equal((await command(a,{kind:'test_topup',pack:'preview_100',op_id:order})).params.reason,'operation_conflict');
    accepted(await command(a,{kind:'pass_premium',season:data.season,op_id:randomUUID()}));data=await state(a);assert.equal(data.premium,true);assert.equal(data.test_credits,0);
    assert.equal((await command(a,{kind:'pass_claim',season:data.season,tier:1,premium:true,op_id:randomUUID()})).params.reason,'tier_locked');
    proof.checks.push('topup replay/conflict, separate credits, premium unlock, server-locked reward');
    accepted(await command(a,{kind:'invite',handle:b.handle}));let t=(await state(b)).trade;assert.ok(t?.incoming);
    accepted(await command(b,{kind:'accept',trade:t.id,revision:t.revision}));t=(await state(a)).trade;
    accepted(await command(a,{kind:'offer',trade:t.id,revision:t.revision,offer:{gold:30,items:{trail_potion:1}}}));t=(await state(a)).trade;
    accepted(await command(a,{kind:'confirm',trade:t.id,revision:t.revision}));const stale=t.revision;
    accepted(await command(b,{kind:'offer',trade:t.id,revision:t.revision,offer:{gold:10,items:{}}}));t=(await state(a)).trade;
    assert.equal(t.confirmed,false);assert.equal(t.peer_confirmed,false);
    assert.equal((await command(a,{kind:'confirm',trade:t.id,revision:stale})).params.reason,'offer_changed');
    accepted(await command(a,{kind:'confirm',trade:t.id,revision:t.revision}));
    await command(b,{kind:'confirm',trade:t.id,revision:t.revision},m=>m.key==='community_result'&&m.params.reason==='trade_complete');
    const finalA=await character(a);const finalB=await character(b);assert.equal(finalA.gold,original.gold-20);assert.equal(finalB.gold,original.gold+20);
    assert.equal(finalA.bag.find(i=>i.item==='trail_potion').count,2);assert.equal(finalB.bag.find(i=>i.item==='trail_potion').count,4);
    assert.equal((await command(b,{kind:'confirm',trade:t.id,revision:t.revision})).params.reason,'trade_expired');assert.equal((await character(b)).gold,finalB.gold);
    proof.checks.push('mutual exchange, edit resets confirmation, stale/duplicate confirmation, gold/item conservation');
    const starts=clients.map(c=>c.messages.length);a.socket.send(encodeCold({t:'community',action:{kind:'megaphone',text:'[Local QA] Preview announcement'}}));
    const echoes=await Promise.all(clients.map((c,i)=>wait(c,starts[i],m=>m.t==='chat'&&m.channel==='megaphone')));assert.ok(echoes.every(m=>m.device==='desktop'));
    assert.equal((await command(a,{kind:'megaphone',text:'[Local QA] Repeated announcement'})).params.reason,'megaphone_cooldown');
    const roster=await state(a);assert.equal(roster.players.find(p=>p.handle===b.handle).device,'mobile');
    proof.checks.push('cross-room megaphone, 30s rate limit, chat/roster device icons');
    proof.wallets={before:{gold:original.gold,coin:original.coin},afterA:{gold:finalA.gold,coin:finalA.coin,potion:2},afterB:{gold:finalB.gold,coin:finalB.coin,potion:4}};
    proof.status='PASS';console.log(JSON.stringify(proof,null,2));
}finally{for(const c of clients)c.socket.close();mkdirSync('planning/evidence/community-20261001',{recursive:true});writeFileSync('planning/evidence/community-20261001/network-smoke.json',JSON.stringify(proof,null,2));}
