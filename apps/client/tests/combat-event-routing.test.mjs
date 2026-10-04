import test from 'node:test';
import assert from 'node:assert/strict';
import {combatEventPresentation,movementSimulationEnabled,gameplayInputBlocked} from '../src/combat-event-routing.mjs';
const hit={source_kind:0,source_id:2,target_kind:0,target_id:101,action:'attack',amount:25,flags:0};
test('remote player collisions with numeric IDs never trigger local impact feedback',()=>{
	assert.equal(combatEventPresentation(hit,3).localImpact,false);
	assert.equal(combatEventPresentation(hit,3).hitStopMs,0);
	assert.equal(combatEventPresentation({...hit,source_kind:1},2).mine,false);
	assert.equal(combatEventPresentation(hit,0).mine,false);
	assert.equal(combatEventPresentation(hit,2).hitStopMs,50);
});
test('only authoritative crit flag selects critical feedback; misses cannot hitstop or flash',()=>{
	assert.equal(combatEventPresentation({...hit,action:'arc_slash'},2).damageKind,'monster');
	assert.equal(combatEventPresentation({...hit,flags:32},2).hitStopMs,85);
	assert.equal(combatEventPresentation({...hit,flags:32,action:'arc_slash'},2).hitStopMs,85);
	assert.equal(combatEventPresentation({...hit,flags:33},2).hitStopMs,110);
	assert.equal(combatEventPresentation({...hit,flags:4},2).word,'counter');
	assert.equal(combatEventPresentation({...hit,flags:4,target_kind:1},2).word,'parry');
	const miss=combatEventPresentation({...hit,flags:64,amount:0},2);
	assert.equal(miss.word,'miss'); assert.equal(miss.damaging,false);assert.equal(miss.localImpact,false);
	assert.equal(combatEventPresentation({...hit,target_kind:1,target_id:2},2).hurtsMe,true);
});
test('fixed-step movement scheduling survives all hitstop durations',()=>{
	for(const duration of [0,50,70,85,110]) {
		let steps=0;
		for(let now=0;now<250;now+=50) if(movementSimulationEnabled({lookdev:false,hitStopUntil:duration}))steps++;
		assert.equal(steps,5);
	}
	assert.equal(movementSimulationEnabled({lookdev:true}),false);
});
test('held input is neutral while KO, typing, hidden, editing, loading or in a modal',()=>{
	const active={ready:true,dead:false,hidden:false,typing:false,uiBlocked:false,mobileBlocked:false,editing:false,cityHeld:false};
	assert.equal(gameplayInputBlocked(active),false);
	for(const key of ['dead','hidden','typing','uiBlocked','mobileBlocked','editing','cityHeld'])assert.equal(gameplayInputBlocked({...active,[key]:true}),true,key);
	assert.equal(gameplayInputBlocked({...active,ready:false}),true);
});
