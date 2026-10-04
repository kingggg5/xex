import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('..',import.meta.url));
const sourceFiles=['src/combat-vfx-caster-detail.ts','src/hero-review-loader.ts','src/combat-vfx-kit.ts','src/combat-vfx-skills.ts','src/combat-vfx-demo.ts'];
const sourceText=Object.fromEntries(await Promise.all(sourceFiles.map(async path=>[path,await readFile(new URL(`../${path}`,import.meta.url),'utf8')])));
const hash=text=>createHash('sha256').update(text).digest('hex');
const sourceHashes=Object.fromEntries(Object.entries(sourceText).map(([path,text])=>[path,hash(text)]));
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
export {LightPool} from './src/combat-vfx-kit';
export {casterDetailFactory} from './src/combat-vfx-caster-detail';
export {createCombatVfx,sceneVfxCounts} from './src/combat-vfx-skills';
export {WITCH_VFX_DEFINITIONS,VFX_TIER_BUDGETS} from './src/combat-vfx-lookv2.mjs';
`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',loader:{'.png':'empty','.glb':'empty','.svg':'empty'}});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const releases={lance:.467,ward:.3,orrery:.9};
const ids={lance:'h02_star_lance',ward:'h02_moonveil_ward',orrery:'h02_celestial_orrery'};
const review={schema:'xexoria.vfx-cpu-review/1',status:'CPU_CHECKS_ONLY',started_utc:new Date().toISOString(),
 source_hashes:sourceHashes,tests:[],factory_budgets:[],limits:['NullEngine/static source inspection only; no native GPU timing, raster or appearance claim.'],
 jev:'USED_VERIFIED parent 20261004-heroes-six/jev-intake-receipt.json reused'};
function checked(name,run){test(name,async t=>{try{await run(t);review.tests.push({name,status:'PASS'});}catch(error){review.tests.push({name,status:'FAIL',error:String(error.message).slice(0,600)});throw error;}});}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const observerCounts=scene=>({beforeRender:scene.onBeforeRenderObservable.observers.length,dispose:scene.onDisposeObservable.observers.length});
const counts=scene=>({...api.sceneVfxCounts(scene),geometries:scene.geometries.length});
function fixtureKit(scene,groundAt,tier='high'){
 const texture=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene,false,false);
 const names=['runeOuter','runeInner','runeBlade','swirl','shock','star','cracks','scorch','streak','palm','noise','disc','lightning','impact','swirlSheet','shards','dust'];
 const tex=Object.fromEntries(names.map(name=>[name,texture]));
 const shapes=Object.fromEntries(['blade','funnel','cone','ringWall'].map(name=>[name,api.MeshBuilder.CreateBox('fixture-'+name,{size:1},scene)]));
 for(const mesh of Object.values(shapes)){mesh.isVisible=false;mesh.isPickable=false;}
 return {scene,groundAt,tier,tex,...shapes,crystalShard:shapes.blade,hexSigil:texture,
  readyKitIds:['vfx_crystal_shard','vfx_hex_sigil','vfx_caster_detail_r01'],
  dispose(){texture.dispose();for(const mesh of Object.values(shapes))mesh.dispose();}};
}
async function fixture(kind,tier,run,groundAt=(x,z)=>4+.03*x+.02*z){
 const engine=new api.NullEngine(),scene=new api.Scene(engine);void scene.defaultMaterial;
 const kit=fixtureKit(scene,groundAt,tier),lights=new api.LightPool(scene);
 const ctx={scene,kit,lights,tier,targets:[],groundAt,shake(){},eye:()=>new api.Vector3(0,8,-10)};
 const baseline=counts(scene),observers=observerCounts(scene);
 const skill=api.casterDetailFactory(kind)(ctx,new api.Vector3(),0);
 try{await run({engine,scene,kit,ctx,skill,baseline,observers});}
 finally{skill.dispose();lights.dispose();kit.dispose();scene.dispose();engine.dispose();}
}
const layer=(skill,name)=>{const value=skill.layers().find(item=>item.name===name);assert.ok(value,`missing ${name}`);return value;};
const systems=skill=>skill.layers().filter(item=>'system' in item);
function stopped(skill){
 for(const item of skill.layers()){
  assert.equal(item.drawCalls(),0,`${item.name} stopped submission`);
  if('mesh' in item){assert.equal(item.mesh.isEnabled(),false,`${item.name} hidden`);for(const inst of item.mesh.instances)assert.equal(inst.isEnabled(),false);}
  // Babylon isStarted() deliberately remains true after stop(); liveness/emission are the contract.
  if('system' in item){assert.ok(!item.system.isAlive(),'no live particle simulation');assert.equal(item.system.emitRate,0);assert.equal(item.system.manualEmitCount,0);assert.equal(item.system.getActiveCount(),0);}
 }
}
function submissions(skill){
 let draws=0,particles=0,glow=0;
 for(const item of skill.layers()){
  if('system' in item){const amount=item.system.getActiveCount()+Math.max(0,item.system.manualEmitCount);particles+=amount;if(amount>0)draws++;}
  else draws+=item.drawCalls();
  if('mesh' in item&&item.mesh.metadata?.glow&&item.drawCalls()>0)glow++;
 }
 return {draws:draws+glow,particles,glowDraws:glow};
}

for(const kind of Object.keys(releases)){
 checked(`${kind}: anticipation, one release burst, dissipation and stop follow seconds`,()=>fixture(kind,'high',({skill})=>{
  stopped(skill);const origin=new api.Vector3(3,4,5),before=origin.clone();skill.reset(origin,0);skill.update(0);
  const ring=layer(skill,'prior-ground'),shock=layer(skill,'prior-anticipation'),core=layer(skill,'prior-core');
  assert.ok(ring.mesh.isEnabled());assert.ok(core.instances.some(i=>i.isEnabled()));assert.equal(shock.mesh.isEnabled(),false);
  assert.deepEqual(origin.asArray(),before.asArray(),'factory owns its origin copy');
  skill.update(releases[kind]-.001);assert.equal(shock.mesh.isEnabled(),false);assert.equal(systems(skill).reduce((n,l)=>n+l.system.manualEmitCount,0),0);
  skill.update(releases[kind]);assert.equal(shock.mesh.isEnabled(),true);assert.equal(systems(skill).reduce((n,l)=>n+l.system.manualEmitCount,0),96);
  for(const item of systems(skill))item.system.manualEmitCount=0; // CPU renderer consumes a burst once.
  skill.update(releases[kind]+.1);assert.equal(systems(skill).reduce((n,l)=>n+l.system.manualEmitCount,0),0,'release cannot re-emit each update');
  skill.update(skill.duration+.01);assert.equal(skill.layers().reduce((n,l)=>n+l.drawCalls(),0),0);
  skill.stop();stopped(skill);
 }));
 for(const tier of ['high','medium'])checked(`${kind}: ${tier} bounded estimated submissions include particles and glow`,()=>fixture(kind,tier,({skill,scene,baseline})=>{
  const budget=api.VFX_TIER_BUDGETS[tier],max={draws:0,particles:0,glowDraws:0};skill.reset(new api.Vector3(0,4,0),.7);
  for(const time of [0,releases[kind]-.001,releases[kind],releases[kind]+.1,releases[kind]+.4,skill.duration]){
   skill.update(time);const estimate=submissions(skill);for(const key of Object.keys(max))max[key]=Math.max(max[key],estimate[key]);
   assert.ok(estimate.draws<=budget.draws,`${estimate.draws}>${budget.draws} estimated draws`);
   assert.ok(estimate.particles<=budget.particles,`${estimate.particles}>${budget.particles} estimated particles`);
  }
  assert.equal(max.particles,tier==='medium'?48:96,'tier scales the actual manual burst');
  assert.equal(scene.lights.length,baseline.lights,'factory allocates no additional lights');assert.ok(scene.lights.every(l=>l.intensity===0));
  review.factory_budgets.push({kind,tier,maximum:max,budget,basis:'enabled analytic layers+pending/active CPU particles+explicit glow metadata; not native counters'});
 }));
 checked(`${kind}: ten casts reuse geometry/materials/observers; reset and dispose restore baseline`,()=>fixture(kind,'high',async({skill,scene,baseline,observers})=>{
  const pooled=counts(scene),poolObservers=observerCounts(scene);
  const geometry=scene.geometries.slice(),materials=scene.materials.slice();
  for(let i=0;i<10;i++){
   skill.reset(new api.Vector3(i,4,i*2),i*.2);skill.update(0);skill.update(releases[kind]);skill.update(releases[kind]+.2);skill.stop();stopped(skill);
   skill.reset(new api.Vector3(-i,4,i),0);stoppedAfterResetHasNoRelease(skill);skill.stop();stopped(skill);
   assert.deepEqual(counts(scene),pooled);assert.deepEqual(scene.geometries,geometry);assert.deepEqual(scene.materials,materials);assert.deepEqual(observerCounts(scene),poolObservers);
  }
  skill.dispose();await tick();assert.deepEqual(counts(scene),baseline);assert.deepEqual(observerCounts(scene),observers);
 }));
 checked(`${kind}: an unsupported reset clears the previous cast before rejecting its floor`,async()=>{
  let supported=true;const groundAt=()=>supported?4:null;
  await fixture(kind,'high',({skill})=>{
   skill.reset(new api.Vector3(0,4,0),0);skill.update(releases[kind]);supported=false;
   assert.throws(()=>skill.reset(new api.Vector3(0,4,0),0),/Unsupported caster effect endpoint/);stopped(skill);
  },groundAt);
 });
}
function stoppedAfterResetHasNoRelease(skill){
 for(const item of systems(skill))assert.equal(item.system.manualEmitCount,0);
 for(const item of skill.layers())if('mesh' in item)assert.equal(item.mesh.isEnabled(),false,'reset clears last cast shapes before the next update');
}

checked('lance uses metres, radians and sampled destination height without mutating input',()=>fixture('lance','high',({skill,ctx})=>{
 const origin=new api.Vector3(8,4,-7);skill.reset(origin,Math.PI/2);skill.update(releases.lance+.38);
 const shock=layer(skill,'prior-anticipation').mesh;
 assert.ok(Math.abs(shock.position.x-14)<1e-6);assert.ok(Math.abs(shock.position.z+7)<1e-6);assert.ok(Math.abs(shock.position.y-(ctx.groundAt(14,-7)+.06))<1e-6);
 const core=layer(skill,'prior-core');assert.ok(core.instances.every(i=>Math.abs(i.position.x-14)<1e-6));
 for(const item of skill.layers())if('mesh' in item){assert.ok(item.mesh.position.asArray().every(Number.isFinite));const pos=item.mesh.getVerticesData(api.VertexBuffer.PositionKind);assert.ok(pos.every(Number.isFinite));}
 assert.deepEqual(origin.asArray(),[8,4,-7]);
}));

checked('local caster readiness needs its local kit, not unused owner source containers',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);void scene.defaultMaterial;const kit=fixtureKit(scene,()=>4);
 const runtime=api.createCombatVfx(scene,kit,{groundAt:()=>4,preset:()=> 'high',hero02Draft:true,ownKit:true});runtime.setManual(true);
 try{for(const kind of Object.keys(ids)){const ready=runtime.previewReadiness(ids[kind]);assert.equal(ready.ready,true,JSON.stringify(ready));assert.ok(runtime.cast(ids[kind],new api.Vector3(0,4,0),0),`ready ${kind} must have a constructed slot`);runtime.clear();}}
 finally{runtime.dispose();scene.dispose();engine.dispose();}
});

checked('runtime lance refuses unsupported six-metre destination and nonfinite world coordinates',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);void scene.defaultMaterial;
 const groundAt=(x,z)=>x>10?null:4,kit=fixtureKit(scene,groundAt);kit.hero02Prior={lance:{},aegis:{},orrery:{}};
 const runtime=api.createCombatVfx(scene,kit,{groundAt,preset:()=> 'high',hero02Draft:true,ownKit:true});runtime.setManual(true);
 try{
  assert.equal(runtime.previewReadiness(ids.lance).ready,true,'terrain guard is exercised with a ready caster');
  assert.equal(runtime.previewReadiness(ids.ward).ready,true,'coordinate guard is exercised with a ready caster');
  assert.equal(runtime.cast(ids.lance,new api.Vector3(8,4,-7),Math.PI/2),null,'unsupported target cannot substitute origin height');
  assert.equal(runtime.cast(ids.ward,new api.Vector3(NaN,4,0),0),null,'nonfinite X cannot corrupt geometry');
  assert.equal(runtime.cast(ids.ward,new api.Vector3(0,4,Infinity),0),null,'nonfinite Z cannot corrupt geometry');
 }
 finally{runtime.dispose();scene.dispose();engine.dispose();}
});

checked('factory accepts an inherited readonly tier getter and reads Medium on reuse',()=>fixture('ward','high',({scene,kit,ctx})=>{
 let tier='high';const parent=Object.create(kit);Object.defineProperty(parent,'tier',{get:()=>tier});const shared=Object.create(parent);
 const before=counts(scene),wrapped={...ctx,kit:shared,get tier(){return tier;}};
 let detail;
 try{
  detail=api.casterDetailFactory('ward')(wrapped,new api.Vector3(),0);
  detail.reset(new api.Vector3(0,4,0),0);detail.update(releases.ward);assert.equal(submissions(detail).particles,96);
  detail.stop();tier='medium';detail.reset(new api.Vector3(0,4,0),0);detail.update(releases.ward);assert.equal(submissions(detail).particles,48);
  detail.stop();stopped(detail);detail.dispose();assert.deepEqual(counts(scene),before);
 }finally{detail?.dispose();}
}));

checked('runtime rejects a nonfinite destination height without throwing or reserving a caster slot',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);void scene.defaultMaterial;
 let finite=false;const groundAt=(x,z)=>!finite&&x>10?NaN:4,kit=fixtureKit(scene,groundAt);
 const runtime=api.createCombatVfx(scene,kit,{groundAt,preset:()=> 'high',hero02Draft:true,ownKit:true});runtime.setManual(true);
 try{
  assert.equal(runtime.previewReadiness(ids.lance).ready,true);
  assert.equal(runtime.cast(ids.lance,new api.Vector3(8,4,-7),Math.PI/2),null);
  finite=true;assert.ok(runtime.cast(ids.lance,new api.Vector3(8,4,-7),Math.PI/2));assert.ok(runtime.cast(ids.lance,new api.Vector3(8,4,-7),Math.PI/2),'failed validation did not consume a pooled slot');
 }finally{runtime.dispose();scene.dispose();engine.dispose();}
});

checked('caster particle systems are included in the real demo prewarm selection',()=>fixture('orrery','high',({skill})=>{
 const demo=sourceText['src/combat-vfx-demo.ts'];
 const filter=demo.match(/particleSystems\.filter\(s\s*=>\s*(\/[^\n]+?\/[a-z]*)\.test\(s\.name\)\)/);
 assert.ok(filter,'inspect the real particle prewarm filter');
 const literal=filter[1],last=literal.lastIndexOf('/'),pattern=new RegExp(literal.slice(1,last),literal.slice(last+1));
 for(const item of systems(skill))assert.ok(pattern.test(item.system.name),`${item.system.name} is omitted from particle shader prewarm`);
}));

test.after(async()=>{
 const finish=Object.fromEntries(await Promise.all(sourceFiles.map(async path=>[path,hash(await readFile(new URL(`../${path}`,import.meta.url),'utf8'))])));
 review.finished_utc=new Date().toISOString();review.source_hashes_at_finish=finish;review.sources_changed_during_run=sourceFiles.filter(path=>finish[path]!==sourceHashes[path]);
 review.passed=review.tests.filter(t=>t.status==='PASS').length;review.failed=review.tests.filter(t=>t.status==='FAIL').length;
 review.status=review.failed?'CPU_REGRESSIONS_FOUND':'CPU_CHECKS_PASS_NATIVE_REVIEW_PENDING';
 review.audit_findings=[
  {area:'owner-relative marker',status:'UNVERIFIED',evidence:'combat-vfx-demo passes player.position to cast; runtime reports ITERATE_LOCAL_GROUND_FALLBACK_UNTIL_SC3_MARKERS. Factory receives no attached staff fx_head transform.'},
  {area:'loader',status:'REVIEW_ONLY',evidence:'LOD skeletons are linked by bone name and retain per-file inverse binds. loadMageReview has no partial-load cleanup/finally; import failure can leave earlier objects in the scene.'},
  {area:'light/glow',status:'CPU_ONLY',evidence:'New caster factory does not acquire a LightPool light or register glowWith; budgets include explicit glow metadata when present. Appearance is not established.'},
 ];
 await writeFile(new URL('../../../planning/evidence/heroes-six-20261004/vfx-cpu-review.json',import.meta.url),JSON.stringify(review,null,2)+'\n');
});
