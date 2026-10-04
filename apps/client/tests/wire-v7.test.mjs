import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeServerMessage,PROTOCOL_VERSION} from '../src/wire.mjs';
function snapshot({count=1,hp=70000,max=90000,monsterFlags=5,events=[]}={}) {
	const bytes=new ArrayBuffer(6+24+count*36+events.length*30),v=new DataView(bytes);
	v.setUint16(0,0xa731,true);v.setUint8(2,PROTOCOL_VERSION);v.setUint8(3,0x82);v.setUint16(4,bytes.byteLength-6,true);
	v.setBigUint64(6,42n,true);v.setUint8(28,count);v.setUint8(29,events.length);
	for(let i=0;i<count;i++) {
		const p=30+i*36;v.setUint32(p,1001+i,true);v.setUint8(p+4,1);
		v.setFloat32(p+5,1.25,true);v.setFloat32(p+9,-2.5,true);
		v.setUint32(p+15,hp,true);v.setUint32(p+19,max,true);v.setUint8(p+23,monsterFlags);
	}
	for(let i=0;i<events.length;i++) {
		const p=30+count*36+i*30,e=events[i];
		v.setBigUint64(p,BigInt(i+1),true);v.setUint8(p+8,0);v.setUint32(p+9,2,true);
		v.setUint8(p+13,0);v.setUint32(p+14,1001,true);v.setUint8(p+18,1);
		v.setUint16(p+19,e.amount,true);v.setUint8(p+21,e.flags);
	}
	return bytes;
}
test('v7 decodes u32 boss health and viewer targeting without moving following fields',()=>{
	assert.equal(PROTOCOL_VERSION,8);
	const result=decodeServerMessage(snapshot());
	assert.equal(result.monsters[0].hp,70000);assert.equal(result.monsters[0].max_hp,90000);
	assert.equal(result.monsters[0].flags,5);assert.equal(result.monsters[0].x,1.25);assert.equal(result.monsters[0].z,-2.5);
	const large=decodeServerMessage(snapshot({hp:0xffff_fffe,max:0xffff_ffff}));assert.equal(large.monsters[0].max_hp,0xffff_ffff);
	const old=snapshot();new DataView(old).setUint8(2,6);assert.throws(()=>decodeServerMessage(old),/version/);
});
test('all 64 monster records decode and 65 is refused',()=>{
	const result=decodeServerMessage(snapshot({count:64}));assert.equal(result.monsters.length,64);assert.equal(result.monsters[63].id,1064);
	assert.throws(()=>decodeServerMessage(snapshot({count:65})),/counts/);
});
test('malformed health, reserved bits, duplicate identities and truncated v7 records fail closed',()=>{
	assert.throws(()=>decodeServerMessage(snapshot({hp:90001})),/monster/);
	assert.throws(()=>decodeServerMessage(snapshot({max:0,hp:0})),/monster/);
	assert.throws(()=>decodeServerMessage(snapshot({monsterFlags:8})),/monster/);
	const duplicate=snapshot({count:2});new DataView(duplicate).setUint32(66,1001,true);assert.throws(()=>decodeServerMessage(duplicate),/monster/);
	assert.throws(()=>decodeServerMessage(snapshot().slice(0,-4)),/length/);
});
test('crit and miss flags cannot contradict authoritative damage or death',()=>{
	for(const e of [{amount:25,flags:32},{amount:0,flags:64}])assert.equal(decodeServerMessage(snapshot({events:[e]})).events[0].flags,e.flags);
	for(const e of [{amount:0,flags:32},{amount:1,flags:64},{amount:0,flags:65},{amount:0,flags:96},{amount:1,flags:128}])assert.throws(()=>decodeServerMessage(snapshot({events:[e]})),/flags/);
});
