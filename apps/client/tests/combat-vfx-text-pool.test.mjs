import test from 'node:test';
import assert from 'node:assert/strict';
import {createCombatTextPool,compactCombatAmount} from '../src/combat-vfx-text-pool.mjs';
const hit=(target,type=0,source=1)=>({x:0,y:2,z:0,targetId:target,sourceId:source,type,amount:10});
test('120 ms merges only target, source and type; overflow values remain bounded',()=>{
	const p=createCombatTextPool(),a=p.spawn(hit(1),0);assert.equal(p.spawn(hit(1),120),a);assert.equal(a.amount,20);assert.equal(p.spawn(hit(1),241).amount,10);assert.notEqual(p.spawn(hit(1,1),250),a);assert.notEqual(p.spawn(hit(1,0,2),250),a);
	assert.equal(compactCombatAmount(123456),'123K');assert.equal(compactCombatAmount(12345678),'12M');assert.equal(compactCombatAmount(40),'40');
});
test('desktop and phone caps, per target cap and lane rotation hold during 1000 spawns',()=>{
	for(const mobile of [false,true]){const p=createCombatTextPool(mobile),storage=p.slots;for(let i=0;i<1000;i++)p.spawn(hit(i%100),i*.1);assert.equal(p.slots,storage);assert.equal(p.active().length,mobile?20:32);}
	const p=createCombatTextPool();for(let i=0;i<9;i++)p.spawn(hit(1,0,i),i*121);assert.equal(p.active().length,4);
	const q=createCombatTextPool();assert.deepEqual([0,1,2].map(i=>q.spawn(hit(i),0).lane),[-1,0,1]);
});
test('local hurt is protected from optional spam and all storage expires/disposes',()=>{
	const p=createCombatTextPool(true);for(let i=0;i<6;i++)p.spawn(hit('me',2,i),i);
	for(let i=0;i<200;i++)p.spawn({...hit(i),relation:'other'},i);assert.equal(p.active().filter(s=>s.type===2).length,6);assert.ok(p.active().length<=20);
	p.expire(2000);assert.equal(p.active().length,0);assert.ok(p.slots.some(s=>s.dirty));p.clear();assert.equal(p.active().length,0);
});
