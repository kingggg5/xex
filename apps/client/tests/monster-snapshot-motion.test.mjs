import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {monsterActiveMotion} from '../src/monster-snapshot-motion.mjs';

test('all authored enemy active windows show impact before expiry, including 50 ms puddlekin',async()=>{
	const data=JSON.parse(await readFile(new URL('../../../content/source/enemies.json',import.meta.url),'utf8'));
	const entries=Array.isArray(data)?data:Object.values(data.enemies??data);
	assert.ok(entries.length>=4);
	for(const enemy of entries){
		if(!Number.isFinite(enemy.splash_active_ms))continue;
		const ticks=enemy.splash_active_ms/50, motion=monsterActiveMotion(2,ticks);
		assert.ok(motion.impactDelayMs<enemy.splash_active_ms,`${enemy.id??enemy.key} impact must remain inside the observed state`);
	}
	assert.deepEqual(monsterActiveMotion(2,1),{phase:'impact',impactDelayMs:0});
});

test('repeated active snapshots preserve leap or impact rather than resetting to idle',()=>{
	let phase='windup';
	for(const [previous,ticks] of [[2,5],[3,4],[3,3]]){
		const motion=monsterActiveMotion(previous,ticks);
		if(motion.phase)phase=motion.phase;
	}
	assert.equal(phase,'leap');
	phase='impact';
	const repeated=monsterActiveMotion(3,1);
	if(repeated.phase)phase=repeated.phase;
	assert.equal(phase,'impact');assert.equal(repeated.impactDelayMs,0);
});

test('short late snapshots cannot schedule a stale 110 ms cosmetic impact',()=>{
	assert.equal(monsterActiveMotion(undefined,0).impactDelayMs,0);
	assert.equal(monsterActiveMotion(2,2).impactDelayMs,50);
	assert.equal(monsterActiveMotion(2,65535).impactDelayMs,110);
	for(const invalid of [-1,1.5,Infinity,65536])assert.throws(()=>monsterActiveMotion(2,invalid),/tick count/);
});
