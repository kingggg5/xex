import test from 'node:test';import assert from 'node:assert/strict';
import {createMutationReplayLedger} from '../src/mutation-replay.mjs';
const first='11111111-1111-4111-8111-111111111111',second='22222222-2222-4222-8222-222222222222',id='33333333-3333-4333-8333-333333333333';
const bytes=()=>new Uint8Array([1,2,3]).buffer;
test('a refreshed cookie cannot replay an old purchase against a different character',()=>{
	const ledger=createMutationReplayLedger();assert.equal(ledger.register(id,bytes(),'wallet'),false);
	ledger.bind(first);assert.equal(ledger.register(id,bytes(),'wallet'),true);ledger.beginReconnect();assert.equal(ledger.ready,false);
	const next=ledger.bind(second);assert.equal(next.changed,true);assert.equal(next.replay.length,0);assert.deepEqual(next.discarded,[{opId:id,resource:'wallet'}]);
});
test('same-character reconnect resends identical copied bytes once; metadata updates never resend',()=>{
	const ledger=createMutationReplayLedger();ledger.bind(first);const packet=bytes();ledger.register(id,packet,'inventory');new Uint8Array(packet)[0]=9;
	ledger.beginReconnect();const next=ledger.bind(first);assert.deepEqual([...new Uint8Array(next.replay[0].packet)],[1,2,3]);
	new Uint8Array(next.replay[0].packet)[0]=8;assert.equal(ledger.bind(first).replay.length,0);
	ledger.beginReconnect();assert.equal(new Uint8Array(ledger.bind(first).replay[0].packet)[0],1);
	assert.deepEqual(ledger.settle(id),{resource:'inventory'});assert.equal(ledger.pending().length,0);
});
test('reused request IDs cannot replace a pending payload and work remains bounded',()=>{
	const ledger=createMutationReplayLedger(1);ledger.bind(first);assert.equal(ledger.register(id,bytes(),'inventory'),true);
	assert.equal(ledger.register(id,new Uint8Array([2,2,3]).buffer,'inventory'),false);
	assert.equal(ledger.register(id,bytes(),'wallet'),false);assert.equal(ledger.register(second,bytes(),'wallet'),false);
	assert.throws(()=>ledger.bind('not-a-character'));ledger.clear();assert.equal(ledger.ready,false);
});
