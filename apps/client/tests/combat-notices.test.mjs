import test from 'node:test';
import assert from 'node:assert/strict';
import {parseDeathNotice,parseCombatGain} from '../src/combat-notices.mjs';
const death={revision:2,down:true,cause:'monster',penalty:{base_exp:0,job_exp:0,gold:0},costs:{return_to_town:0},free_return:true,auto_revive_at_ms:null};
test('authoritative free-town death notice retains explicit zero costs rather than guessing missing values',()=>{
	assert.deepEqual(parseDeathNotice(death),death);
	for(const bad of [{...death,revision:-1},{...death,penalty:null},{...death,costs:{}},{...death,free_return:'yes'},{...death,down:1}])assert.equal(parseDeathNotice(bad),null);
});
test('heal and EXP notices reject invalid/out-of-world or incomplete gains',()=>{
	const heal={amount:10,hp:100,max_hp:100,source:'trail_potion'};assert.equal(parseCombatGain('heal',heal).amount,10);
	assert.equal(parseCombatGain('heal',{...heal,hp:101}),null);
	const gain={base:15,job:12,monster_id:101,kind:1,x:3,z:4,level_up:false,job_level_up:false};assert.equal(parseCombatGain('exp_gain',gain).job,12);
	assert.equal(parseCombatGain('exp_gain',{...gain,x:Infinity}),null);assert.equal(parseCombatGain('exp_gain',{...gain,job:-1}),null);
	assert.equal(parseCombatGain('exp_gain',{}),null);
});
