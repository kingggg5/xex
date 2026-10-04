import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createSnapshotDecoder,encodeSnapshotAck,ResyncRequired} from '../src/wire.mjs';
const fixtures=JSON.parse(readFileSync(new URL('../../protocol/golden-v8.json',import.meta.url),'utf8')).fixtures;
const fixture=name=>Uint8Array.from(Buffer.from(fixtures.find(f=>f.name===name).hex,'hex')).buffer;
const decoder=()=>{const d=createSnapshotDecoder();d.decode(fixture('interest_welcome'));return d;};
test('native v8 full/delta reconstruct complete visible truth including current self and private targeting',()=>{
	const d=decoder(),full=d.decode(fixture('interest_full')),delta=d.decode(fixture('interest_delta'));
	assert.equal(full.full,true);assert.equal(full.players.length,2);assert.equal(full.monsters[0].hp,70000);assert.equal(full.monsters[0].flags,7);assert.equal(full.events[0].source_kind,0);assert.equal(full.events[0].target_kind,0);
	assert.equal(delta.full,false);assert.equal(delta.baseline_tick,42n);assert.equal(delta.players[0].x,1.75);assert.equal(delta.players[0].hp,75);assert.equal(delta.players[1].x,2.125);assert.equal(delta.monsters[0].hp,70000);assert.equal(delta.monsters[0].state_ticks,7);assert.equal(delta.events.length,0);assert.deepEqual(d.snapshotAck(),{epoch:1,tick:43n});
});
test('missing baselines, stale ticks, wrong epoch and trailing bytes never mutate last good state',()=>{
	const d=decoder();assert.throws(()=>d.decode(fixture('interest_delta')),ResyncRequired);assert.equal(d.retainedBaselines(),0);d.decode(fixture('interest_full'));
	const baseline=d.snapshotAck();assert.throws(()=>d.decode(fixture('interest_full')),/stale_tick/);
	const wrong=fixture('interest_delta');new DataView(wrong).setUint32(6,2,true);assert.throws(()=>d.decode(wrong),/wrong_epoch/);
	const truncated=fixture('interest_delta').slice(0,-1);assert.throws(()=>d.decode(truncated),/envelope/);assert.deepEqual(d.snapshotAck(),baseline);
	assert.equal(d.decode(fixture('interest_delta')).players[1].x,2.125);
});
test('returned objects and targeting overlays cannot corrupt an acknowledged baseline',()=>{
	const d=decoder(),full=d.decode(fixture('interest_full'));full.players[1].x=999;full.monsters[0].hp=1;full.monsters[0].flags=255;
	const delta=d.decode(fixture('interest_delta'));assert.equal(delta.players[1].x,2.125);assert.equal(delta.monsters[0].hp,70000);assert.equal(delta.monsters[0].flags,7);
});
test('socket reset/reconnect fences old baselines and ACK requests validate bounds',()=>{
	const d=decoder();d.decode(fixture('interest_full'));d.reset();assert.equal(d.retainedBaselines(),0);assert.equal(d.snapshotAck(),null);assert.throws(()=>d.decode(fixture('interest_delta')),/wrong_epoch/);
	const ack=new DataView(encodeSnapshotAck(1,43n));assert.equal(ack.getUint8(3),5);assert.equal(ack.getUint16(4,true),13);assert.equal(ack.getUint32(6,true),1);assert.equal(ack.getBigUint64(10,true),43n);assert.equal(ack.getUint8(18),0);assert.equal(new DataView(encodeSnapshotAck(1,0n,true)).getUint8(18),1);
	for(const args of [[0,1n],[1,0n],[1,-1n],[1,2**32],[1,1n,'yes']])assert.throws(()=>encodeSnapshotAck(...args),/invalid/);
});
test('baseline retention is bounded across sustained valid snapshots',()=>{
	const d=decoder();for(let tick=42n;tick<200n;tick++){const bytes=fixture('interest_full');new DataView(bytes).setBigUint64(10,tick,true);d.decode(bytes);}assert.equal(d.retainedBaselines(),32);
});
function emptyDelta(tick,baseline,collection=[]) {
	// Golden private header includes its one targeting overlay; shared state
	// below consists of three empty collection change/removal pairs and events.
	const b=new Uint8Array(68+collection.length+7);b.set(new Uint8Array(fixture('interest_full')).slice(0,68));
	if(collection.length)b.set(collection,68);else b.set([0,0],68);
	const v=new DataView(b.buffer);v.setUint16(4,b.byteLength-6,true);v.setBigUint64(10,tick,true);v.setBigUint64(18,baseline,true);return b.buffer;
}
test('unknown removal and incomplete new-entity patch fail without phantom despawn',()=>{
	const d=decoder();d.decode(fixture('interest_full'));
	const removal=emptyDelta(43n,42n,[0,1,0xe7,3,0,0]);assert.throws(()=>d.decode(removal),/unknown_remove/);assert.deepEqual(d.snapshotAck(),{epoch:1,tick:42n});
	const patch=emptyDelta(43n,42n,[1,0,0xe7,3,0,0,2,0,0]);assert.throws(()=>d.decode(patch),/unknown_patch/);assert.equal(d.decode(fixture('interest_delta')).players.length,2);
});
test('every truncation of native v8 full and delta packets fails closed',()=>{
	for(const name of ['interest_full','interest_delta']){const bytes=fixture(name);for(let end=0;end<bytes.byteLength;end++){const d=decoder();if(name==='interest_delta')d.decode(fixture('interest_full'));assert.throws(()=>d.decode(bytes.slice(0,end)));}}
});
for(const lossPct of [0,1,2,5])test(`acknowledged baseline reconstruction survives deterministic ${lossPct}% frame loss`,()=>{
	const d=decoder();d.decode(fixture('interest_full'));let acknowledged=42n,received=0;
	for(let index=1;index<=1000;index++){
		const tick=42n+BigInt(index),bytes=emptyDelta(tick,acknowledged);
		if((index*37)%100<lossPct)continue;
		const s=d.decode(bytes);acknowledged=s.tick;received++;assert.equal(s.players.length,2);assert.equal(s.monsters.length,1);assert.equal(s.monsters[0].flags,7);
	}
	assert.equal(received,1000-lossPct*10);assert.equal(d.retainedBaselines(),32);
});
