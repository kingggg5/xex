import test from 'node:test';
import assert from 'node:assert/strict';
import {COMBAT_ACTIONS,actionByCode,actionDescription} from '../src/combat-actions.mjs';
import {encodeAction} from '../src/wire.mjs';
test('bindings and wire share the same player action identity and tutorial key',()=>{
	for(const row of COMBAT_ACTIONS.filter(row=>row.player)){
		assert.equal(actionByCode(row.code),row.action);assert.equal(actionDescription(row.action).key,row.key);
		assert.equal(new DataView(encodeAction(1,1,row.action,0,0,0)).getUint8(14),row.id);
	}
	assert.equal(actionByCode('KeyX'),null);assert.equal(actionDescription('unknown'),null);
	assert.equal(actionDescription('guard','th').label,'ป้องกัน');
});
test('a monster-only action cannot be encoded by a player binding',()=>{
	assert.throws(()=>encodeAction(1,1,'splash_hop',0,0,0),/unsupported/);
});
