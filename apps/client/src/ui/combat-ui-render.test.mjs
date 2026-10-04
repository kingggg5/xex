import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import {compile} from 'svelte/compiler';
const bundle=await build({stdin:{contents:"import {render} from 'svelte/server'; import Review from './CombatUiReview.svelte'; import Layer from './CombatLayer.svelte'; import * as model from './combat-model'; export {model}; export const draw=props=>render(Review,{props}).body; export const drawLayer=props=>render(Layer,{props}).body;",resolveDir:fileURLToPath(new URL('.',import.meta.url)),sourcefile:'combat-ui-render.js'},bundle:true,write:false,format:'esm',platform:'node',conditions:['svelte'],logLevel:'silent',loader:{'.css':'empty','.svg':'dataurl'},plugins:[{name:'actual-svelte-components',setup(builder){builder.onLoad({filter:/\.svelte$/},async args=>({contents:compile(await readFile(args.path,'utf8'),{filename:args.path,generate:'server',runes:true}).js.code,loader:'js'}));}}]});
const {draw,drawLayer,model:m}=await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);
const row=(id,changes={})=>({id,name:`Monster ${id}`,screenX:300,screenY:200,distance:5,onScreen:true,occluded:false,hp:null,maxHp:null,level:null,rank:null,element:null,targetingMe:true,lastDamagedAtMs:null,stateChips:[],cast:null,...changes});
const view=(changes={})=>m.nextCombatView(m.emptyCombatView(),{nowMs:10000,formFactor:'desktop',selectedTargetId:1,actors:[row(1)],...changes});
const props=changes=>({view:view(),death:m.emptyDeathView(),...changes});
const down=changes=>({...m.nextDeathView(m.emptyDeathView(),{revision:1,down:true,cause:'monster',penalty:{base_exp:0,job_exp:0,gold:0},costs:{return_to_town:0},free_return:true,auto_revive_at_ms:null}),online:true,canSubmit:true,...changes});
const state=(status,hasData=false)=>({status,hasData,message:null,requestId:null});
test('actual plate/target components escape text, preserve unknown metadata and use a fixed ten-slot pool',()=>{
 const html=draw(props({view:view({actors:[row(1,{name:'<script>unsafe</script>'})]})}));
 assert.equal((html.match(/data-plate-slot=/g)||[]).length,10);assert.match(html,/&lt;script>/);assert.doesNotMatch(html,/<script>unsafe/);assert.match(html,/— \/ —/);assert.doesNotMatch(html,/Lv\. 1\b/);
});
test('mobile candidate has at most six populated slots while target HP remains exact u32',()=>{
 const html=draw(props({view:view({formFactor:'mobile',actors:Array.from({length:20},(_,i)=>row(i+1,{hp:100000,maxHp:200000,rank:'elite',level:12}))})}));
 assert.equal((html.match(/data-actor-id="[1-9][0-9]*"/g)||[]).length,6);assert.match(html,/100,000 \/ 200,000/);assert.match(html,/Elite/);assert.match(html,/Lv\. 12/);
});
test('server KO dialog shows explicit free cost, unknown penalties never become zero and accepted receipt waits',()=>{
 let html=draw(props({death:down({penalty:null,costs:null,free_return:null})}));assert.match(html,/Not reported/);assert.match(html,/Awaiting confirmed cost/);assert.doesNotMatch(html,/Base EXP −0/);assert.match(html,/data-return-to-town[^>]* disabled/);
 html=draw(props({death:down()}));assert.match(html,/Free · no gold required/);assert.match(html,/Base EXP −0/);assert.match(html,/role="dialog"/);assert.doesNotMatch(html,/data-return-to-town[^>]* disabled/);
 html=draw(props({death:down({request:{opId:'fixture',deathRevision:1,phase:'committed',reason:'returned_to_town'}})}));assert.match(html,/Waiting for authoritative character state/);assert.match(html,/data-return-to-town[^>]* disabled/);
});
test('actual modal combat layer hides world plates/target and restores latest authoritative values on close',()=>{
 const combat=view({actors:[row(1,{name:'Live threat',hp:70,maxHp:100})]});
 const layer=(modal,live=combat)=>drawLayer({view:{modal,combat:live,death:m.emptyDeathView(),language:'en'},commands:{returnToTown(){}}});
 for(const modal of ['character','bag']){
  const html=layer(modal),plates=html.match(/<div[^>]*class="plate-layer[^>]*>/)?.[0]??'';
  assert.match(plates,/\shidden(?:[\s=>])/);assert.match(plates,/aria-hidden="true"/);assert.doesNotMatch(html,/data-target-id=/);
  assert.equal((html.match(/data-plate-slot=/g)||[]).length,10,'fixed pool remains live behind its hidden world container');
 }
 const updated=view({actors:[row(1,{name:'Live threat',hp:17,maxHp:100})]});
 assert.match(layer('bag',updated),/aria-valuenow="17"/,'authoritative combat data still updates while suspended');
 const reopened=layer(null,updated),plates=reopened.match(/<div[^>]*class="plate-layer[^>]*>/)?.[0]??'';
 assert.doesNotMatch(plates,/\shidden(?:[\s=>])/);assert.match(reopened,/data-target-id="1"/);assert.match(reopened,/17 \/ 100/);
 assert.equal(combat.target.hp,70,'rendering never mutates the supplied combat view');
 assert.match(layer(undefined,updated),/data-target-id="1"/,'missing legacy modal state stays backwards compatible');
});
test('modal world suspension leaves authoritative KO/recovery cover and return action visible',()=>{
 const layer=death=>drawLayer({view:{modal:'character',combat:view(),death,language:'en'},commands:{returnToTown(){}}});
 const actionable=layer(down());
 assert.match(actionable,/class="death-cover/);assert.match(actionable,/role="dialog"/);assert.match(actionable,/data-return-to-town/);assert.doesNotMatch(actionable,/data-return-to-town[^>]* disabled/);assert.doesNotMatch(actionable,/data-target-id=/);
 const waiting=layer(down({request:{opId:'fixture',deathRevision:1,phase:'committed',reason:'returned_to_town'}}));
 assert.match(waiting,/Waiting for authoritative character state/);assert.match(waiting,/data-return-to-town[^>]* disabled/);
});
test('resource gate never renders zero or empty server content during loading, missing stale data or failure',()=>{
 for(const s of [state('loading'),state('stale'),state('error')]){const html=draw(props({mode:'panel',states:[s]}));assert.doesNotMatch(html,/Server-provided fixture value/);assert.doesNotMatch(html,/Fixture mutation/);}
 const empty=draw(props({mode:'panel',states:[state('loaded-empty',true)]}));assert.match(empty,/Loaded · no entries yet/);assert.match(empty,/Server-provided fixture value: 0/);
 const stale=draw(props({mode:'panel',states:[state('stale',true)]}));assert.match(stale,/Last received data/);assert.match(stale,/<fieldset disabled/);
});
test('pending/unknown transactions disable mutations and error copy is escaped, never an invented commit',()=>{
 for(const phase of ['submitting','outcome-unknown']) { const html=draw(props({mode:'panel',states:[state('loaded-data',true)],transactions:[{resource:'wallet',requestId:'real-id',phase,reason:null}]}));assert.match(html,/<fieldset disabled/);assert.doesNotMatch(html,/Server confirmed the transaction/); }
 const html=draw(props({mode:'panel',states:[state('error',false)],transactions:[{resource:'wallet',requestId:'real-id',phase:'rejected',reason:'<b>not enough gold</b>'}]}));assert.match(html,/&lt;b>not enough gold/);assert.doesNotMatch(html,/<b>not enough gold/);
});
test('latest terminal message supersedes old failures while every unresolved operation still blocks',()=>{
 const rejected={resource:'inventory',requestId:'old-reject',phase:'rejected',reason:'old stale_revision'};
 const committed={resource:'character',requestId:'new-commit',phase:'committed',reason:'allocated'};
 const drawState=transactions=>draw(props({mode:'panel',states:[state('loaded-data',true)],transactions}));
 const succeeded=drawState([rejected,committed]);
 assert.match(succeeded,/data-transaction-state="committed"/);assert.match(succeeded,/Server confirmed the transaction/);assert.doesNotMatch(succeeded,/old stale_revision|<fieldset disabled/);
 const failed=drawState([committed,{...rejected,requestId:'new-reject',reason:'new insufficient_gold'}]);
 assert.match(failed,/data-transaction-state="rejected"/);assert.match(failed,/new insufficient_gold/);assert.doesNotMatch(failed,/Server confirmed the transaction/);
 for(const phase of ['submitting','outcome-unknown']){
  const unresolved={resource:'inventory',requestId:'unresolved',phase,reason:null};
  const blocked=drawState([unresolved,rejected,committed]);
  assert.match(blocked,new RegExp(`data-transaction-state="${phase}"`));assert.match(blocked,/<fieldset disabled/);assert.doesNotMatch(blocked,/old stale_revision|Server confirmed the transaction/);
 }
});
test('cast bar uses supplied deadline/duration and selected-target cast label without fabricating damage',()=>{
 const html=draw(props({view:view({actors:[row(1,{cast:{label:'Heavy attack',endsAtMs:10500,durationMs:1000}})]})}));assert.match(html,/Heavy attack/);assert.match(html,/aria-valuenow="50"/);assert.match(html,/animation-duration:\s*1000ms/);assert.match(html,/animation-delay:\s*-500ms/);
});
test('inventory selector uses server UUIDs, shows equipped copies and never autoselects a mutation',()=>{
 const id='f8901e2e-f131-41f2-a6c7-a00000000001';const html=draw(props({mode:'inventory',inventory:{language:'en',online:true,loading:false,revision:9,instances:[{instanceId:id,id:'starter_blade',label:'Starter blade',location:'weapon',refine:3,equipSlot:'weapon'}],instanceMovesSupported:true,items:[],pouch:[],potionPending:false,potionReadyAtMs:0,potionUnavailable:false}}));
	assert.match(html,new RegExp(`data-instance-id="${id}"`));assert.match(html,/Starter blade/);assert.match(html,/class="equipment-refine">\+3/);assert.match(html,/Equipped weapon/);assert.match(html,/aria-pressed="false"/);assert.doesNotMatch(html,/data-move-item-instance/);assert.match(html,/No equipment selected/);
});
