import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCommunity,deviceKind,detectDevice} from '../src/community.ts';
const payload=()=>({rewards:Array.from({length:20},(_,i)=>[i+1,(i+1)*5,(i+1)*15]),packs:[['preview_300',300]],season:'sunmeadow-preview-01',xp:100,tiers:20,xp_per_tier:100,premium:false,free_claims:0,premium_claims:0,test_credits:300,test_enabled:true,premium_test_cost:300,order_count:1,gold:250,durable:false,orders:[{id:'one',pack:'preview_300',credits:300}],items:[{id:'trail_potion',count:3}],players:[{handle:'1234abcd',name:'Hero',device:'mobile',nearby:true}],trade:null});
test('community DTO is cloned and refuses malformed rewards, economy and offers',()=>{
    const p=payload();const data=parseCommunity(p);assert.ok(data);p.gold=999;assert.equal(data.gold,250);
    assert.equal('scene' in parseCommunity({...payload(),scene:new Map()}),false);
    for(const patch of [{xp:Infinity},{tiers:1000},{gold:-1},{free_claims:1<<20},{premium:'true'},{players:Array(13).fill(p.players[0])},{trade:{id:'one',revision:1,mine:{gold:0,items:{potion:-1}},theirs:{gold:0,items:{}}}}])assert.equal(parseCommunity({...payload(),...patch}),null);
});
test('device indicators only accept the coarse display category',()=>{assert.equal(deviceKind('mobile'),'mobile');assert.equal(deviceKind('desktop'),'desktop');for(const input of ['iPhone',null,{},123])assert.equal(deviceKind(input),'unknown');});
test('device hint is independent of window size; mobile fallback includes desktop-UA iPad',()=>{
    assert.equal(detectDevice(false,'Windows',10),'desktop');assert.equal(detectDevice(true,'Windows'),'mobile');
    assert.equal(detectDevice(undefined,'iPhone Mobile'),'mobile');assert.equal(detectDevice(undefined,'Android'),'mobile');
    assert.equal(detectDevice(undefined,'Macintosh',5),'mobile');assert.equal(detectDevice(undefined,'Macintosh',0),'desktop');assert.equal(detectDevice(undefined,''),'unknown');
});
