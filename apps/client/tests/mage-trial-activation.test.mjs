import test from 'node:test';import assert from 'node:assert/strict';
import {MageTrialActivation} from '../src/mage-trial-activation.mjs';
test('dropped activation retries one identity, then holds unknown until a new epoch',()=>{
 let now=0,ids=0;const a=new MageTrialActivation(()=>now,()=>`id-${++ids}`);a.connect(7);
 assert.equal(a.poll(false),null);const first=a.poll(true);assert.equal(first.kind,'retry');
 for(now=1000;now<=3000;now+=1000)assert.equal(a.poll(true).intent,first.intent);
 assert.deepEqual(a.poll(true),{kind:'reconnect'});now=100000;assert.equal(a.poll(true),null);assert.equal(ids,1);
 a.connect(8);assert.notEqual(a.poll(true).intent.op_id,first.intent.op_id);
});
test('only current confirmed trial or disabled capability stops activation',()=>{
 let now=0;const a=new MageTrialActivation(()=>now,()=> 'id');a.connect(2);
 a.confirm({epoch:1,profile:'mage_trial',capability_enabled:true});assert.equal(a.poll(true).kind,'retry');
 a.confirm({epoch:2,profile:'trailblade',capability_enabled:true});now=1000;assert.equal(a.poll(true).kind,'retry');
 a.confirm({epoch:2,profile:'mage_trial',capability_enabled:true});now=2000;assert.equal(a.poll(true),null);
 a.connect(3);a.confirm({epoch:3,profile:'trailblade',capability_enabled:false});assert.equal(a.poll(true),null);
});
test('correlated terminal operation result stops retries without locally applying a grant',()=>{
 let now=0;const a=new MageTrialActivation(()=>now,()=> 'exact-op');a.connect(1);a.poll(true);
 a.settle('other');now=1000;assert.equal(a.poll(true).kind,'retry');
 a.settle('exact-op');now=2000;assert.equal(a.poll(true),null);
});
