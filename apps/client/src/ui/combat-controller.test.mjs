import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';

// Test the actual GameHud controller with explicit DOM/renderer ports.
// These are synthetic routing tests, not touch, Svelte DOM or device qualification.
const result=await build({entryPoints:[fileURLToPath(new URL('../ui.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node',logLevel:'silent',define:{'import.meta.env.DEV':'false'},plugins:[{name:'controller-ports',setup(builder){
 builder.onResolve({filter:/^\.\/ui\/bridge\.svelte$/},()=>({path:'bridge',namespace:'ports'}));
 builder.onResolve({filter:/^\.\/chat$/},()=>({path:'chat',namespace:'ports'}));
 builder.onLoad({filter:/.*/,namespace:'ports'},args=>({loader:'js',contents:args.path==='chat'?'export const initChat=()=>{},onSystemLine=()=>{},setChatGroupAvailable=()=>{},appendLocalChat=()=>{},releaseChat=()=>{};':`export function mountGameUi(a,b,c,language,commands){const state={};globalThis.__combatUiPort={state,commands,unmounted:false};return {update(p){Object.assign(state,structuredClone(p))},updateHud(p){state.hud={...state.hud,...structuredClone(p)}},updatePanels(p){state.panels={...state.panels,...structuredClone(p)}},openModal(){return b},closeModal(){},unmount(){globalThis.__combatUiPort.unmounted=true}}}`}));
}}]});
const {GameHud}=await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
class Element { constructor(){this.isConnected=true;this.style={setProperty(){}};}closest(){return null;}focus(){} }
function environment(){
 const previous=new Map(['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','HTMLSelectElement'].map(k=>[k,globalThis[k]]));
 const storage=new Map(), win=new EventTarget(), doc=new EventTarget();const host=new Element();
 Object.assign(win,{setTimeout,clearTimeout,devicePixelRatio:2,innerWidth:896,innerHeight:414,matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}}),localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)}});
 Object.assign(doc,{hidden:false,fullscreenEnabled:false,fullscreenElement:null,activeElement:null,documentElement:host,getElementById:()=>host,querySelector:()=>host});
 Object.assign(globalThis,{window:win,document:doc,HTMLElement:Element,HTMLInputElement:class extends Element{},HTMLTextAreaElement:class extends Element{},HTMLSelectElement:class extends Element{}});
 return {win,doc,storage,restore(){for(const [k,v]of previous){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}};
}
function fixture(extra={}){const env=environment(), sent=[],actions=[];const hud=new GameHud({language:'en',onAction:a=>actions.push(a),onPotion:()=>true,onContext(){},onChoose(){},onClaim(){},onParty(){},itemName:id=>id,questName:id=>id,translate:id=>id,onReturnToTown:(id,rev)=>{sent.push({id,rev});return true},...extra});return {env,hud,sent,actions,port:globalThis.__combatUiPort,dispose(){hud.dispose();env.restore();delete globalThis.__combatUiPort}};}
const death=change=>({revision:2,down:true,cause:'monster',penalty:{base_exp:0,job_exp:0,gold:0},costs:{return_to_town:0},free_return:true,auto_revive_at_ms:null,...change});
function key(win,type,code){const e=new Event(type);Object.assign(e,{key:code==='KeyW'?'w':'f',code,repeat:false});win.dispatchEvent(e);}
test('actual controller immediately releases movement on KO and canonical gameplay keys stay blocked until server alive',()=>{
 const f=fixture();try {f.hud.setConnection(true);key(f.env.win,'keydown','KeyW');assert.notEqual(f.hud.getMovement().z,0);f.hud.setDeathState(death());assert.deepEqual(f.hud.getMovement(),{x:0,z:0});assert.equal(f.hud.isGameplayBlocked(),true);key(f.env.win,'keydown','KeyF');assert.deepEqual(f.actions,[]);f.hud.setDeathState(death({down:false,cause:'none'}));assert.deepEqual(f.hud.getMovement(),{x:0,z:0});key(f.env.win,'keydown','KeyF');assert.deepEqual(f.actions,['attack']);}finally{f.dispose();}
});
test('actual return intent is single-flight; disconnect/reconnect retry preserves UUID and stale result cannot close KO',()=>{
 const f=fixture();try {f.hud.setConnection(true);f.hud.setDeathState(death());f.port.commands.returnToTown();f.port.commands.returnToTown();assert.equal(f.sent.length,1);const first=f.hud.getPendingReturnToTown();assert.match(first.opId,/^[a-f0-9-]{36}$/);f.hud.setConnection(false);assert.equal(f.port.state.death.request.phase,'outcome-unknown');f.port.commands.returnToTown();assert.equal(f.sent.length,1);f.hud.setConnection(true);f.port.commands.returnToTown();assert.equal(f.sent.length,2);assert.equal(f.sent[0].id,f.sent[1].id);assert.equal(f.hud.setReturnToTownResult({opId:first.opId,deathRevision:1,state:'committed',reason:'old'}),false);assert.equal(f.hud.isGameplayBlocked(),true);f.hud.setReturnToTownResult({opId:first.opId,deathRevision:2,state:'committed',reason:'returned_to_town'});assert.equal(f.port.state.death.down,true);f.hud.setDeathState(death({down:false,cause:'none'}));assert.equal(f.hud.getPendingReturnToTown(),null);}finally{f.dispose();}
});
test('resource bridge retains last loaded empty/data as stale and transactions as unknown when connection drops',()=>{
 const f=fixture();try {f.hud.setConnection(true);f.hud.setFriends([]);assert.equal(f.port.state.resources.friends.status,'loaded-empty');f.hud.setPanelResource('wallet',{status:'loaded-data'});f.hud.setTransactionState({resource:'wallet',requestId:'server-operation',phase:'submitting',reason:null});f.hud.setConnection(false);assert.equal(f.port.state.resources.friends.status,'stale');assert.equal(f.port.state.resources.friends.hasData,true);assert.equal(f.port.state.resources.wallet.hasData,true);assert.equal(f.port.state.transactions[0].phase,'outcome-unknown');assert.equal(f.hud.isGameplayBlocked(),true);f.hud.setConnection(true);assert.equal(f.port.state.resources.friends.status,'loading');assert.equal(f.port.state.resources.friends.hasData,false);}finally{f.dispose();}
});
test('readability applies through callback and device-local storage without renderer objects',()=>{
 const updates=[];const f=fixture({onCombatReadabilityChanged:v=>updates.push(v)});try {f.hud.setCombatReadability({combatTextScale:2.5,lowEffects:true,hideOtherEffects:true,screenShake:false});assert.deepEqual(updates,[{combatTextScale:2,lowEffects:true,hideOtherEffects:true,screenShake:false}]);assert.equal(f.hud.getCombatReadability().combatTextScale,2);assert.equal(JSON.parse(f.env.storage.get('xexoria_combat_readability_v1')).version,1);f.hud.dispose();assert.equal(f.port.unmounted,true);f.hud.setCombatReadability({combatTextScale:1,lowEffects:false,hideOtherEffects:false});assert.equal(updates.length,1);}finally{f.dispose();}
});
test('positive self-snapshot API clears missing-notice KO; old matching-revision notice cannot reopen it',()=>{
 const f=fixture();try {f.hud.setConnection(true);f.hud.setDeathState(death({revision:null}));assert.equal(f.hud.isGameplayBlocked(),true);f.hud.confirmAliveSnapshot();assert.equal(f.hud.isGameplayBlocked(),false);assert.equal(f.port.state.death.revision,null);f.hud.setDeathState(death());f.hud.confirmAliveSnapshot();assert.equal(f.hud.setDeathState(death()),false);assert.equal(f.hud.setDeathState(death({revision:3})),true);}finally{f.dispose();}
});
const instance='f8901e2e-f131-41f2-a6c7-a00000000001';
const character=change=>({t:'character_state',rev:5,name:'Server traveler',level:1,job_level:1,exp:0,job_exp:0,base_exp_next:100,job_exp_next:100,hp:100,max_hp:100,gold:100,coin:0,bag:[],pouch:{},equipment:[{slot:'weapon',item:'starter_blade'}],refine:{weapon:3},stats:{str:1,agi:1,vit:1,int:1,dex:1,luk:1},stat_points:1,atk:10,def:2,item_instances:[{instance_id:instance,def:'starter_blade',location:'bag',refine:3}],...change});
test('actual inventory move reads an admitted UUID/current revision, is single-flight and resolves only receipt',()=>{
 const moves=[];const f=fixture({itemEquipmentSlot:()=> 'weapon',onMoveItemInstance:(...args)=>{moves.push(args);return true}});try{f.hud.setConnection(true);assert.equal(f.hud.setCharacterState(character()),true);const cmd=f.port.commands;
 cmd.moveItemInstance('forged',5,'weapon');cmd.moveItemInstance(instance,4,'weapon');assert.equal(moves.length,0);
 cmd.moveItemInstance(instance,5,'weapon');cmd.moveItemInstance(instance,5,'weapon');assert.equal(moves.length,1);assert.equal(moves[0][1],instance);assert.equal(moves[0][2],5);assert.equal(moves[0][3],'weapon');
 const pending=f.hud.getPendingItemMoves();assert.equal(pending.length,1);assert.equal(pending[0].opId,moves[0][0]);f.hud.setConnection(false);assert.equal(f.hud.getPendingItemMoves().length,1);
 assert.equal(f.hud.setTransactionState({resource:'inventory',requestId:moves[0][0],phase:'committed',reason:null}),true);assert.deepEqual(f.hud.getPendingItemMoves(),[]);
 }finally{f.dispose();}
});
test('refine forwards only the currently equipped UUID/revision and missing admitted slot stays suppressed',()=>{
 const refined=[];const f=fixture({itemEquipmentSlot:()=> 'weapon',onRefineItem:(...args)=>refined.push(args)});try{f.hud.setConnection(true);f.hud.setCharacterState(character());f.port.commands.panels.refineItem('weapon');assert.deepEqual(refined,[]);
 f.hud.setCharacterState(character({rev:6,item_instances:[{instance_id:instance,def:'starter_blade',location:'weapon',refine:3}]}));f.port.commands.panels.refineItem('weapon');assert.deepEqual(refined,[['weapon',instance,6]]);
 }finally{f.dispose();}
});
test('public character authority changes reset death revision and pending intent, same UUID/case preserves them',()=>{
 const f=fixture();try {f.hud.setConnection(true);const first='f8901e2e-f131-41f2-a6c7-a00000000011',second='f8901e2e-f131-41f2-a6c7-a00000000012';
 assert.equal(f.hud.beginCharacterAuthority(first),true);f.hud.setDeathState(death({revision:8}));f.port.commands.returnToTown();const old=f.hud.getPendingReturnToTown();assert.ok(old);
 assert.equal(f.hud.beginCharacterAuthority(first.toUpperCase()),false);assert.deepEqual(f.hud.getPendingReturnToTown(),old);f.hud.confirmAliveSnapshot();assert.equal(f.hud.setDeathState(death({revision:8})),false);
 assert.equal(f.hud.beginCharacterAuthority('invalid'),false);assert.equal(f.hud.beginCharacterAuthority(second),true);assert.equal(f.hud.getPendingReturnToTown(),null);assert.equal(f.hud.setDeathState(death({revision:0,down:false})),true);assert.equal(f.hud.setDeathState(death({revision:1})),true);
 }finally{f.dispose();}
});
test('correlated HTTP responses cannot overwrite a newer request or a current-socket push',()=>{
 const f=fixture();try {f.hud.setConnection(true);f.hud.setPanelResource('friends',{status:'loading',requestId:'request-new'});f.hud.setFriends([], 'request-old');assert.equal(f.port.state.resources.friends.status,'loading');
 f.hud.setFriends([], 'request-new');assert.equal(f.port.state.resources.friends.status,'loaded-empty');f.hud.setPanelResource('friends',{status:'loading',requestId:'request-next'});f.hud.setFriends([]);assert.equal(f.port.state.resources.friends.requestId,null);
 f.hud.setFriends([{handle:'a1b2c3d4',name:'Old HTTP result',online:true,channel:0}], 'request-next');assert.deepEqual(f.port.state.panels.friends,[]);
 }finally{f.dispose();}
});
