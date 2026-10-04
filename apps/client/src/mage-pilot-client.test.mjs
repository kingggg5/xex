import {test} from 'node:test';import assert from 'node:assert/strict';import {MagePilotClient,parseMageTrialState,parseMageCastState} from './mage-pilot-client.mjs';
const skill=(skill_id='h02_basic')=>({skill_id,available:true,range_m:9,windup_ms:100,cooldown_ms:600,recovery_ms:200,sp_cost:0,projectile_speed_m_s:20,power:25});
const profile=()=>({t:'mage_trial_state',capability_enabled:true,focus_equipped:true,profile:'mage_trial',epoch:4,skills:[skill(),{...skill('h02_star_lance'),sp_cost:8}]});
const event=(phase='started',sequence=1)=>({t:'mage_cast_state',cast_id:`7:4:${sequence}`,source_id:7,epoch:4,sequence,skill_id:'h02_basic',phase,reason:'accepted',target_id:9,damage:phase==='impact'?25:0,flags:0,server_ms:100,start_ms:100,release_ms:200,impact_ms:500,recovery_end_ms:400,cooldown_end_ms:700,origin:[0,1.8,0],target:[0,1,6]});
test('unknown access, focus or insufficient SP cannot mint a cast intent',()=>{const c=new MagePilotClient(()=>100);c.connect(7,4);assert.equal(c.request('h02_basic',9,30).ok,false);c.setProfile({...profile(),focus_equipped:false});assert.equal(c.request('h02_basic',9,30).ok,false);c.setProfile(profile());assert.equal(c.request('h02_star_lance',9,0).reason,'insufficient_sp');assert.equal(c.request('h02_basic',0,30).reason,'no_target');});
test('one outstanding intent, authoritative deadlines and terminal dedupe prevent double presentation',()=>{let now=100;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());assert.equal(c.request('h02_basic',9,30).intent.sequence,1);assert.equal(c.request('h02_basic',9,30).reason,'busy');assert.ok(c.receive(event()));assert.equal(c.receive(event()),null);assert.ok(c.receive(event('released')));assert.ok(c.receive(event('impact')));assert.equal(c.receive(event('impact')),null);now=600;assert.equal(c.request('h02_basic',9,30).reason,'cooldown');now=701;assert.equal(c.request('h02_basic',9,30).intent.sequence,2);});
test('rejected casts produce no confirmed damage or predicted cooldown',()=>{const c=new MagePilotClient(()=>100);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);assert.ok(c.receive({...event('rejected'),reason:'out_of_range'}));assert.equal(c.request('h02_basic',9,30).intent.sequence,2);});
test('wrong actor, epoch, target and unrequested casts never enter presentation',()=>{const c=new MagePilotClient(()=>100);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);assert.equal(c.receive({...event(),source_id:8,cast_id:'8:4:1'}),null);assert.equal(c.receive({...event(),epoch:5,cast_id:'7:5:1'}),null);assert.equal(c.receive({...event(),target_id:10}),null);c.connect(7,5);assert.equal(c.receive(event('impact')),null);});
test('malformed phases/clock/coords and incomplete or duplicate metadata reject',()=>{assert.equal(parseMageCastState({...event(),phase:'rejected',damage:3}),null);assert.equal(parseMageCastState({...event(),impact_ms:100}),null);assert.equal(parseMageCastState({...event(),target:[NaN,0,0]}),null);assert.equal(parseMageTrialState({...profile(),skills:[skill(),skill()]}),null);assert.equal(parseMageTrialState({...profile(),skills:[{...skill(),sp_cost:-1}]}),null);});
test('failed transport does not reuse a sequence that could have been sent',()=>{const c=new MagePilotClient(()=>100);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);c.notSent(1);assert.equal(c.request('h02_basic',9,30).intent.sequence,2);});
test('charge may have no authoritative impact time; released or impact must have one',()=>{assert.equal(parseMageCastState({...event(),impact_ms:null}).impact_ms,null);assert.equal(parseMageCastState({...event('released'),impact_ms:null}),null);assert.equal(parseMageCastState({...event('cancelled'),impact_ms:null}).phase,'cancelled');});

test('lost request retries the exact immutable intent at1/2/3s then holds unknown and reconnects once',()=>{
 let now=0;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());const result=c.request('h02_basic',9,30),intent=result.intent;
 assert(Object.isFrozen(intent));assert.equal(c.pollRecovery(),null);
 for(const deadline of [1000,2000,3000]){now=deadline-1;assert.equal(c.pollRecovery(),null);now=deadline;
  const action=c.pollRecovery();assert.equal(action.kind,'retry');assert.strictEqual(action.intent,intent);assert.equal(JSON.stringify(action.intent),JSON.stringify(intent));assert.equal(c.pollRecovery(),null);
 }
 now=4000;assert.equal(c.pollRecovery(),null);assert.equal(c.sequence,1);now=4500;assert.deepEqual(c.pollRecovery(),{kind:'reconnect'});
 assert.equal(c.pollRecovery(),null);now=9000;assert.equal(c.pollRecovery(),null);assert.strictEqual(c.pending.intent,intent);assert.equal(c.request('h02_basic',9,30).reason,'busy');assert.equal(c.sequence,1);
 c.connect(7,5);assert.equal(c.pollRecovery(),null);assert.equal(c.pending,null);
});
test('delayed polling cannot burst missed retries or manufacture a terminal event',()=>{
 let now=0;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);
 now=3200;assert.equal(c.pollRecovery().kind,'retry');assert.equal(c.pollRecovery(),null);now=4200;assert.equal(c.pollRecovery().kind,'retry');now=4500;assert.equal(c.pollRecovery().kind,'reconnect');assert.equal(c.lastEvent,null);
});
test('known charge and release postpone transport recovery through bounded flight; duplicate phases cannot extend it',()=>{
 let now=100;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());const intent=c.request('h02_basic',9,30).intent;
 assert(c.receive({...event(),impact_ms:null}));now=1649;assert.equal(c.pollRecovery(),null);now=1650;assert.strictEqual(c.pollRecovery().intent,intent);
 now=1800;assert(c.receive({...event('released'),server_ms:1800,impact_ms:2200}));assert.equal(c.pending.retries,1);
 now=3100;assert.equal(c.receive({...event('released'),server_ms:3100,impact_ms:3400}),null);
 now=3200;assert.strictEqual(c.pollRecovery().intent,intent);assert.equal(c.pending.retries,2);
 now=3300;assert(c.receive({...event('impact'),server_ms:3300,impact_ms:2200}));assert.equal(c.pending,null);assert.equal(c.pollRecovery(),null);assert.equal(c.receive({...event('impact'),server_ms:3300,impact_ms:2200}),null);
});
test('phase progress cannot refund the three-retry budget and cancellation stops recovery',()=>{
 let now=100;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);
 for(now=1100;now<=3100;now+=1000)assert.equal(c.pollRecovery().kind,'retry');
 assert.equal(c.pending.retries,3);assert(c.receive({...event(),impact_ms:null}));const deadline=c.pending.reconnectAt;
 now=deadline-1;assert.equal(c.pollRecovery(),null);assert(c.receive({...event('cancelled'),impact_ms:null,reason:'moved'}));now=deadline+1;assert.equal(c.pollRecovery(),null);assert.equal(c.receive({...event('cancelled'),reason:'moved'}),null);
});
test('reconnect cooldown rejection restores only the server ready deadline, not hypothetical rejected recovery',()=>{
 let now=100;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);
 assert(c.receive(event()));c.connect(7,5);c.setProfile({...profile(),epoch:5});c.request('h02_basic',9,30);
 const nextEpoch=(phase,sequence=1)=>({...event(phase,sequence),epoch:5,cast_id:`7:5:${sequence}`});
 const rejected={...nextEpoch('rejected'),reason:'cooldown',cooldown_end_ms:3000,recovery_end_ms:400};assert(c.receive(rejected));assert.equal(c.busyUntil,0);
 now=200;assert.equal(c.request('h02_basic',9,30).reason,'cooldown');now=3000;assert.equal(c.request('h02_basic',9,30).intent.sequence,2);
 assert(c.receive({...nextEpoch('started',2),start_ms:3000,release_ms:3100,recovery_end_ms:3300,impact_ms:null,cooldown_end_ms:3600,server_ms:3000}));
 assert(c.receive({...nextEpoch('rejected',2),reason:'cooldown',start_ms:3000,cooldown_end_ms:3600,recovery_end_ms:900000}));assert.equal(c.busyUntil,3300);
});
test('invalid rejected deadlines cannot poison an otherwise available skill',()=>{
 const c=new MagePilotClient(()=>100);c.connect(7,4);c.setProfile(profile());c.request('h02_basic',9,30);
 assert(c.receive({...event('rejected'),reason:'cooldown',cooldown_end_ms:1,recovery_end_ms:900000}));assert.equal(c.busyUntil,0);assert.equal(c.request('h02_basic',9,30).ok,true);
});
test('unconfirmed range estimate cannot postpone unknown recovery without a fixed upper bound',()=>{
 let now=100;const c=new MagePilotClient(()=>now);c.connect(7,4);c.setProfile({...profile(),skills:[{...skill(),range_m:40,projectile_speed_m_s:1}]});c.request('h02_basic',9,30);
 assert(c.receive({...event(),impact_ms:null}));now=14599;c.pollRecovery();now=14600;assert.deepEqual(c.pollRecovery(),{kind:'reconnect'});assert.equal(c.lastEvent.phase,'started');assert(c.pending);
});
