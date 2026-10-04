import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const code=ts.transpileModule(await readFile(new URL('./combat-model.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const m=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const actor=(id,change={})=>({id,name:`Monster ${id}`,screenX:200+id,screenY:160,distance:5,onScreen:true,occluded:false,hp:70,maxHp:100,level:null,rank:null,element:null,targetingMe:null,hostile:true,lastDamagedAtMs:null,stateChips:[],cast:null,...change});
const presentation=(rows,change={})=>({nowMs:10000,formFactor:'desktop',selectedTargetId:null,actors:rows,...change});
const death=(change={})=>({revision:4,down:true,cause:'monster',penalty:{base_exp:0,job_exp:0,gold:0},costs:{return_to_town:0},free_return:true,auto_revive_at_ms:null,...change});
const uuid='f8901e2e-f131-41f2-a6c7-a00000000001';
test('fixed plate pool is capped by form factor; target/attacking/damaged outrank nearby hostiles',()=>{
 const rows=Array.from({length:20},(_,i)=>actor(i+1)); rows[19]=actor(20,{distance:70,targetingMe:true});
 let v=m.nextCombatView(m.emptyCombatView(),presentation(rows,{selectedTargetId:19}));
 assert.equal(v.slots.length,10); assert.equal(v.slots.filter(s=>s.visible).length,10); assert.ok(v.slots.some(s=>s.actor?.id===19));assert.ok(v.slots.some(s=>s.actor?.id===20));
 v=m.nextCombatView(v,presentation(rows,{formFactor:'mobile',selectedTargetId:19}));
 assert.equal(v.slots.length,10);assert.equal(v.slots.filter(s=>s.visible).length,2,'mobile does not show unrelated nearby normals');
 const attackers=rows.map(row=>({...row,targetingMe:true}));v=m.nextCombatView(v,presentation(attackers,{formFactor:'mobile',selectedTargetId:19}));assert.equal(v.slots.filter(s=>s.visible).length,6);
});
test('plate slots retain actor identities, expire fade-outs and do not retain unbounded actors',()=>{
 let v=m.nextCombatView(m.emptyCombatView(),presentation([actor(1),actor(2)]));const first=v.slots.find(s=>s.actor?.id===1).slot;
 v=m.nextCombatView(v,presentation([actor(2),actor(1)],{nowMs:10100}));assert.equal(v.slots.find(s=>s.actor?.id===1).slot,first);
 v=m.nextCombatView(v,presentation([],{nowMs:10200}));assert.equal(v.slots[first].visible,false);assert.equal(v.slots[first].expiresAtMs,10450);
 v=m.nextCombatView(v,presentation([],{nowMs:10451}));assert.equal(v.slots[first].actor,null);
 assert.equal(m.nextCombatView(v,presentation(Array.from({length:65},(_,i)=>actor(i+1)))),null);
});
test('eight-second damage eligibility and elite range are exact; unknown metadata remains unknown',()=>{
 const v=m.nextCombatView(m.emptyCombatView(),presentation([actor(1,{hostile:false,lastDamagedAtMs:2000}),actor(2,{hostile:false,lastDamagedAtMs:1999}),actor(3,{hostile:false,rank:'elite',distance:35}),actor(4,{hostile:false,rank:'boss',distance:35.01}),actor(5,{hp:null,maxHp:null})]));
 assert.deepEqual(v.slots.filter(s=>s.visible).map(s=>s.actor.id).sort(),[1,3,5]);assert.equal(v.slots.find(s=>s.actor?.id===5).actor.level,null);assert.equal(m.healthRatio(actor(5,{hp:null,maxHp:null})),null);
});
test('malformed/projected objects cannot introduce engine state; exact u32 HP survives',()=>{
 class Mesh {constructor(){this.id=1;this.name='mesh';}}
 const v=m.nextCombatView(m.emptyCombatView(),presentation([new Mesh(),actor(2,{hp:100000,maxHp:200000,screenX:NaN}),actor(3,{hp:100000,maxHp:200000})],{selectedTargetId:3}));
 assert.equal(v.target.hp,100000);assert.equal(v.target.maxHp,200000);assert.equal(v.slots.filter(s=>s.visible).length,1);assert.equal(JSON.parse(JSON.stringify(v)).target.level,null);
});
test('KO requires explicit free cost/revision, blocks duplicate submissions and retains UUID on unknown retry',()=>{
 let v={...m.nextDeathView(m.emptyDeathView(),death()),online:true,canSubmit:true};assert.equal(m.canReturnToTown(v),true);
 assert.equal(m.startTownRequest(v,'not-a-uuid'),null);v=m.startTownRequest(v,uuid);assert.equal(m.startTownRequest(v,uuid),null);
 v=m.applyTownResult(v,{opId:uuid,deathRevision:4,state:'outcome-unknown',reason:'connection_lost'});
 const retry=m.startTownRequest(v,'f8901e2e-f131-41f2-a6c7-a00000000002');assert.equal(retry.request.opId,uuid);
 assert.equal(m.canReturnToTown({...retry,free_return:null}),false);assert.equal(m.canReturnToTown({...v,costs:null}),false);
});
test('accepted receipt never invents alive/HP state; stale replies and revived-revision KO notices are ignored',()=>{
 let v={...m.nextDeathView(m.emptyDeathView(),death()),online:true,canSubmit:true};v=m.startTownRequest(v,uuid);
 v=m.applyTownResult(v,{opId:uuid,deathRevision:4,state:'committed',reason:'returned_to_town'});assert.equal(v.down,true);assert.equal(m.canReturnToTown(v),false);
 assert.equal(m.applyTownResult(v,{opId:uuid,deathRevision:3,state:'rejected',reason:'old'}),v);
 v=m.nextDeathView(v,death({down:false,cause:'none'}));assert.equal(v.down,false);assert.equal(v.request,null);
 assert.equal(m.nextDeathView(v,death()),null);assert.equal(m.nextDeathView(v,death({revision:3})),null);
 const pending=m.nextDeathView(v,death({revision:null}));assert.equal(pending.down,true);assert.equal(pending.penalty,null);assert.equal(pending.costs,null);assert.equal(m.canReturnToTown(pending),false);
 assert.equal(m.nextDeathView(pending,death()),null);assert.equal(m.nextDeathView(pending,death({revision:5})).revision,5);
});
test('resource loading/empty/data/stale/error remain distinct and mismatched request replies cannot overwrite',()=>{
 const states=m.createResourceStates();assert.equal(states.inventory.status,'loading');assert.equal(states.inventory.hasData,false);
 let r=m.updateResource(states.inventory,{status:'loading',requestId:'request-a'});assert.equal(m.updateResource(r,{status:'loaded-empty',requestId:'request-b'}),null);
 r=m.updateResource(r,{status:'loaded-empty',requestId:'request-a'});assert.equal(r.hasData,true);assert.equal(r.status,'loaded-empty');
 r=m.updateResource(r,{status:'stale'});assert.equal(r.hasData,true);r=m.updateResource(r,{status:'error',message:'Request failed'});assert.equal(r.status,'error');assert.equal(r.hasData,true);
 assert.deepEqual(m.resourceKeysForPanel('store'),['shop','wallet']);assert.deepEqual(m.resourceKeysForPanel('settings'),[]);
});
test('transaction receipts are terminal, wrong-resource reuse is refused and pending history is bounded',()=>{
 let rows=m.nextTransactions([],{resource:'inventory',requestId:'operation-1',phase:'submitting',reason:null});
 rows=m.nextTransactions(rows,{resource:'inventory',requestId:'operation-1',phase:'committed',reason:null});const same=m.nextTransactions(rows,{resource:'inventory',requestId:'operation-1',phase:'outcome-unknown'});assert.equal(same,rows);
 assert.equal(m.nextTransactions(rows,{resource:'wallet',requestId:'operation-1',phase:'submitting'}),rows);
 let pending=[];for(let n=0;n<16;n++)pending=m.nextTransactions(pending,{resource:'community',requestId:`pending-${n}`,phase:'submitting'});
 assert.equal(m.nextTransactions(pending,{resource:'community',requestId:'overflow',phase:'submitting'}),null);
});
test('readability is bounded and does not contain gameplay or engine objects',()=>{
 assert.deepEqual(m.normalizeReadability({combatTextScale:99,lowEffects:true,hideOtherEffects:true,scene:{}}),{combatTextScale:2,lowEffects:true,hideOtherEffects:true,screenShake:true});
 assert.equal(m.normalizeReadability({combatTextScale:-1}).combatTextScale,.8);assert.deepEqual(m.normalizeReadability(null),m.DEFAULT_COMBAT_READABILITY);
});
test('vetted positive-HP confirmation closes unknown KO and preserves the stale-revision guard',()=>{
 let v=m.nextDeathView(m.emptyDeathView(),death({revision:null}));v=m.confirmAliveView(v);assert.equal(v.down,false);assert.equal(v.revision,null);
 v=m.nextDeathView(v,death());v=m.confirmAliveView(v);assert.equal(v.confirmedRevision,4);assert.equal(v.confirmedDown,false);assert.equal(m.nextDeathView(v,death()),null);assert.equal(m.nextDeathView(v,death({revision:5})).down,true);
});
test('equipment instances preserve real UUIDs and locations, reject duplicates/missing IDs, and do not guess destinations',()=>{
 const id='f8901e2e-f131-41f2-a6c7-a00000000001',base={instance_id:id,def:'starter_blade',location:'bag',refine:3};
 const rows=m.parseItemInstances([base],()=>'<Blade>');assert.equal(rows[0].instanceId,id);assert.equal(rows[0].equipSlot,null);assert.equal(rows[0].refine,3);
 assert.equal(m.parseItemInstances([base],id=>id,()=> 'weapon')[0].equipSlot,'weapon');
 assert.equal(m.parseItemInstances([{...base,instance_id:'starter_blade'}],id=>id),null);assert.equal(m.parseItemInstances([base,base],id=>id),null);
 assert.equal(m.parseItemInstances([{...base,location:'weapon'},{...base,instance_id:'f8901e2e-f131-41f2-a6c7-a00000000002',location:'weapon'}],id=>id),null);
 assert.equal(m.parseItemInstances(Array(65).fill(base),id=>id),null);
});
