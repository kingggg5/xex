import test from "node:test";
import assert from "node:assert/strict";
import {build} from "esbuild";
import {fileURLToPath} from "node:url";
import {readFile} from "node:fs/promises";
const bundled=await build({stdin:{contents:`
import {NullEngine} from '@babylonjs/core/Engines/nullEngine';
import {Scene} from '@babylonjs/core/scene';
import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
import {createCombatFx,SlashArc} from './src/combat-fx';
export {HitStop} from './src/combat-fx';
export {CameraRig} from './src/combat-fx';
export {hitStopFor,createActorFeedback} from './src/combat-vfx-feedback';
export {TransformNode} from '@babylonjs/core/Meshes/transformNode';
export {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {createWorldCombatLabels} from './src/world-combat-labels';
export {NullEngine,Scene,MeshBuilder,Vector3,VertexBuffer,createCombatFx,SlashArc,createWorldCombatLabels};`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const gradient=()=>({addColorStop(){}});
const context=()=>new Proxy({createLinearGradient:gradient,createRadialGradient:gradient,measureText:()=>({width:20})},{get(target,key){return key in target?target[key]:(()=>{});},set(target,key,value){target[key]=value;return true;}});
async function withFx(run,groundAt=()=>0){
  const oldCanvas=globalThis.OffscreenCanvas,oldPerformance=globalThis.performance;let now=0;
  globalThis.OffscreenCanvas=class{constructor(width,height){this.width=width;this.height=height;}getContext(){return context();}};
  Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now}});
  const engine=new api.NullEngine(),scene=new api.Scene(engine);
  const baseline={meshes:scene.meshes.length,materials:scene.materials.length,textures:scene.textures.length,particles:scene.particleSystems.length,observers:scene.onBeforeRenderObservable.observers.length};
  const fx=api.createCombatFx(scene,{groundAt,lowDetail:false,now:()=>now});
  const step=time=>{now=time;scene.onBeforeRenderObservable.notifyObservers(scene);};
  try{await run({scene,fx,step,baseline});}finally{fx.dispose();scene.dispose();engine.dispose();globalThis.OffscreenCanvas=oldCanvas;Object.defineProperty(globalThis,'performance',{configurable:true,value:oldPerformance});}
}
test('100 normal/arc swings reuse all meshes and materials; shared resources survive replay',()=>withFx(({scene,fx,step})=>{
  const slash=new api.SlashArc(scene,fx),counts=[scene.meshes.length,scene.materials.length,scene.textures.length,scene.particleSystems.length];
  const shared=scene.materials.slice();
  for(let i=0;i<100;i++){step(i*240);fx.beginBladeSwing();slash.play(0,3,0,i*.02,i%2===0);step(i*240+225);}
  assert.deepEqual([scene.meshes.length,scene.materials.length,scene.textures.length,scene.particleSystems.length],counts);
  assert.ok(shared.every(material=>scene.materials.includes(material)));
  assert.equal(scene.onBeforeRenderObservable.observers.length,1);
}));
test('warning quads are ground-flat and a supported 20% ramp tilts with the terrain',()=>withFx(({scene,fx})=>{
  fx.createSplashTelegraph(0,0,2.5,900);
  const flat=scene.meshes.find(mesh=>mesh.name==='combat-warning-ring-0');flat.computeWorldMatrix(true);
  assert.ok(flat.getBoundingInfo().boundingBox.extendSizeWorld.y*2<.05);
  assert.equal(flat.parent.position.y,4.035);
  fx.createSplashTelegraph(10,0,2.5,900);
  const ramp=scene.meshes.find(mesh=>mesh.name==='combat-warning-ring-1');
  const center=api.Vector3.TransformCoordinates(api.Vector3.Zero(),ramp.computeWorldMatrix(true));
  const right=api.Vector3.TransformCoordinates(new api.Vector3(.5,0,0),ramp.computeWorldMatrix(true));
  assert.ok(Math.abs((right.y-center.y)/(right.x-center.x)-.2)<1e-5);
},x=>x<5?4:4+.2*(x-10)));
test('wind-up expiry arms but never invents impact; confirmed impact is once-only',()=>withFx(({fx,step})=>{
  const telegraph=fx.createSplashTelegraph(0,0,2.5,900);
  step(900);assert.equal(telegraph.isFinished,true,'legacy offline AI still leaps at its 900ms deadline');
  assert.equal(telegraph.update(),true);assert.equal(fx.diagnostics().impactCount,0);
  step(1551);step(1732);assert.equal(telegraph.update(),false);assert.equal(fx.diagnostics().impactCount,0);
  const confirmed=fx.createSplashTelegraph(1,1);confirmed.impact();confirmed.impact();
  assert.equal(fx.diagnostics().impactCount,1);step(2350);assert.equal(fx.diagnostics().activeImpacts,0);
}));
test('cancelled warnings and stale leases cannot alter a reused warning or emit impact',()=>withFx(({fx,step})=>{
  const old=fx.createSplashTelegraph(0,0);old.dispose();old.impact();assert.equal(fx.diagnostics().impactCount,0);
  step(181);const current=fx.createSplashTelegraph(2,2);
  old.dispose();old.impact();old.setRemainingMs(0);
  assert.equal(current.progress,0);assert.equal(fx.diagnostics().activeWarnings,1);assert.equal(fx.diagnostics().impactCount,0);
  current.impact();assert.equal(fx.diagnostics().impactCount,1);
}));
test('arc band has a 4m outer edge, 2.88m inner edge, 120-degree sector and +Z facing',()=>withFx(({scene,fx})=>{
  fx.playSlash(0,2,0,Math.PI/2,true);
  const mesh=scene.meshes.find(mesh=>mesh.name==='combat-arc-crescent-0'),positions=mesh.getVerticesData(api.VertexBuffer.PositionKind);
  for(let i=0;i<33;i++){const inner=i*6,outer=inner+3;assert.ok(Math.abs(Math.hypot(positions[inner],positions[inner+2])-2.88)<1e-5);assert.ok(Math.abs(Math.hypot(positions[outer],positions[outer+2])-4)<1e-5);}
  assert.ok(Math.abs(Math.atan2(positions[0],positions[2])+Math.PI/3)<1e-5);
  const point=api.Vector3.TransformCoordinates(new api.Vector3(0,0,4),mesh.computeWorldMatrix(true));assert.ok(point.x>3.99&&Math.abs(point.z)<1e-5);
}));
test('missing support never falls back to a floor at zero or emits splash droplets',()=>withFx(({scene,fx})=>{
  const handle=fx.createSplashTelegraph(5,5);assert.equal(scene.meshes.find(mesh=>mesh.name==='combat-warning-ring-0').isEnabled(),false);
  handle.impact();assert.equal(fx.diagnostics().impactCount,0);assert.equal(fx.diagnostics().activeImpacts,0);
},()=>null));
test('blade samples are time-based and a >3m teleport clears old trail history',()=>withFx(({scene,fx,step})=>{
  const sword=api.MeshBuilder.CreateBox('test-sword',{size:1},scene);fx.attachSword(sword);fx.beginBladeSwing();step(1);
  sword.position.x=.3;step(31);assert.equal(fx.diagnostics().trailSamples,2);
  sword.position.x=8;step(61);assert.equal(fx.diagnostics().trailSamples,1);
  step(1000);assert.equal(fx.diagnostics().trailSamples,0);sword.dispose();
}));
test('authored weapon trail follows its own markers, ignores global duplicates and retires a disposed owner',()=>withFx(({scene,fx,step})=>{
  const owner=new api.TransformNode('authored-sword',scene);owner.position.set(3,1,-2);owner.rotation.z=Math.PI/2;
  for(const [name,y] of [['fx_base',.25],['fx_tip',1.25]]){const marker=new api.TransformNode(name,scene);marker.parent=owner;marker.position.y=y;}
  const unrelated=new api.TransformNode('fx_tip',scene);unrelated.position.set(50,50,50);
  fx.attachWeaponMarkers(owner);fx.beginBladeSwing();step(1);owner.position.x+=.3;step(31);
  assert.equal(fx.diagnostics().trailSamples,2);
  const mesh=scene.meshes.find(m=>m.name==='combat-blade-trail'),p=mesh.getVerticesData(api.VertexBuffer.PositionKind),half=p.length/2;
  assert.ok(Math.abs(p[half-3]-3.05)<1e-5);assert.ok(Math.abs(p[p.length-3]-2.05)<1e-5);
  assert.ok(Math.abs(p[half-2]-1)<1e-5&&Math.abs(p[p.length-1]+2)<1e-5);
  owner.dispose();step(61);assert.equal(fx.diagnostics().trailSamples,0);assert.equal(mesh.isEnabled(),false);
}));
test('damage anchors follow terrain/explicit height and unsupported support is skipped',()=>withFx(({scene,step})=>{
  const labels=api.createWorldCombatLabels(scene,['Slime'],{groundAt:(x)=>x<0?null:5});
  labels.showDamage(1,1,42,'crit');assert.equal(labels.diagnostics().slots[0].position[1],6.8);
  step(120);
  labels.showDamage(1,1,20,'monster',9);assert.equal(labels.diagnostics().slots[1].position[1],9);
  labels.showDamage(-1,1,1);assert.equal(labels.diagnostics().active,2);
  labels.dispose();
}));
test('teardown releases pools, shared textures and both observers; stale calls remain no-ops',()=>withFx(async({scene,fx,step,baseline})=>{
  const handle=fx.createSplashTelegraph(0,0);handle.impact();fx.hitBurst(0,1,0,0,-2,true);fx.playSlash(0,0,0,0,true);step(20);
  fx.dispose();fx.dispose();handle.impact();handle.dispose();fx.hitBurst(1,1,1,0,0);step(400);
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual({meshes:scene.meshes.length,materials:scene.materials.length,textures:scene.textures.length,particles:scene.particleSystems.length,observers:scene.onBeforeRenderObservable.observers.length},baseline);
  assert.equal(scene.onDisposeObservable.observers.length,0);
}));
test('combat FX source has no independent animation frame loop',async()=>{
  assert.doesNotMatch(await readFile(new URL('../src/combat-fx.ts',import.meta.url),'utf8'),/requestAnimationFrame/);
});

test('local-only hitstop has prescribed times, never stacks and weaker hits cannot shorten it',()=>{
  let now=0;const stop=new api.HitStop(()=>now);
  assert.deepEqual(['light','heavy','crit','counter','kill'].map(kind=>api.hitStopFor(kind,true)),[50,70,85,85,110]);
  assert.equal(api.hitStopFor('kill',false),0);stop.trigger(110);now=20;stop.trigger(50);assert.equal(stop.remainingMs(),90);
  stop.trigger(999);assert.equal(stop.remainingMs(),120);now=141;assert.equal(stop.isStopped(),false);stop.clear();assert.equal(stop.remainingMs(),0);
});
test('telegraph shape survives low effects and hidden remote decoration; party hits still show',()=>withFx(({scene,fx})=>{
  fx.setLowDetail(true);fx.setHideOtherEffects(true);
  for(const [i,style] of ['amber','unblockable','guard','opening'].entries())fx.createSplashTelegraph(i,0,2,900,style);
  assert.equal(fx.diagnostics().activeWarnings,4);
  assert.equal(new Set(scene.meshes.filter(m=>m.name.startsWith('combat-warning-ring-')&&m.isEnabled()).map(m=>m.material.name)).size,4);
  fx.hitBurst(0,2,0,0,-1,false,'other');assert.equal(fx.diagnostics().hitCount,0);
  fx.hitBurst(0,2,0,0,-1,false,'party');assert.equal(fx.diagnostics().hitCount,1);
}));
test('actor feedback moves only its child, holds flash 40 ms and dissolves 450+800 ms',()=>withFx(({scene,step})=>{
  const root=new api.TransformNode('authority',scene),child=new api.TransformNode('visual',scene);child.parent=root;
  root.position.set(10,0,10);child.position.set(0,.2,0);const material=new api.StandardMaterial('actor',scene);
  const body=api.MeshBuilder.CreateBox('actor-body',{size:1},scene);body.parent=child;body.material=material;body.isPickable=true;
  let now=0;const feedback=api.createActorFeedback(scene,child,[material],{now:()=>now});
  feedback.hit('heavy',10,9);now=40;step(now);assert.deepEqual(root.position.asArray(),[10,0,10]);assert.ok(child.position.z>0&&child.position.z<=.3);
  assert.equal(material.pluginManager.getPlugin('CombatActorFeedback').flash,.6);now=120;step(now);assert.equal(material.pluginManager.getPlugin('CombatActorFeedback').flash,0);
  feedback.die();assert.equal(body.isPickable,false);now=570;step(now);assert.equal(material.pluginManager.getPlugin('CombatActorFeedback').dissolve,0);
  now=1370;step(now);assert.equal(feedback.finished,true);assert.equal(child.isEnabled(),false);
  feedback.respawn();assert.equal(child.isEnabled(),true);assert.equal(body.isPickable,true);assert.deepEqual(child.position.asArray(),[0,.2,0]);feedback.dispose();material.dispose();root.dispose();
}));

test('low effects removes cosmetic particle/trail work, retains every warning and party impact, and can restore detail',()=>withFx(({scene,fx,step})=>{
  const sword=api.MeshBuilder.CreateBox('low-fx-sword',{size:1},scene);fx.attachSword(sword);fx.beginBladeSwing();step(1);sword.position.x=.4;step(31);assert.equal(fx.diagnostics().trailSamples,2);
  fx.hitBurst(0,2,0,0,-1,true);assert.ok(scene.particleSystems.find(s=>s.name==='combat-hit-sparks-0').isStarted());
  fx.setLowEffects(true);fx.setHideOtherEffects(true);assert.equal(fx.diagnostics().trailSamples,0);
  for(const [i,style] of ['amber','unblockable','guard','opening'].entries())fx.createSplashTelegraph(i,0,2,900,style);
  fx.hitBurst(1,2,0,0,-1,true,'party');const tel=fx.createSplashTelegraph(2,2);tel.impact();
  step(60);assert.equal(fx.diagnostics().activeWarnings,4);assert.ok(scene.meshes.filter(m=>m.name.startsWith('combat-warning-ring-')&&m.isEnabled()).length===4);
  assert.ok(scene.meshes.filter(m=>m.name.startsWith('combat-warning-fill-')&&m.isEnabled()).length===4);
  assert.equal(scene.meshes.filter(m=>m.name.startsWith('combat-warning-pulse-')&&m.isEnabled()).length,0);
  assert.ok(scene.particleSystems.every(s=>s.getActiveCount()===0&&s.manualEmitCount===0));assert.equal(fx.diagnostics().hitCount,2);
  fx.setLowDetail(false);assert.equal(fx.diagnostics().lowEffects,true,'quality changes do not erase the user preference');
  fx.setLowEffects(false);fx.hitBurst(2,2,0,0,-1,false,'party');assert.ok(scene.particleSystems.some(s=>s.isStarted()));sword.dispose();
}));
test('shake toggle clears displacement and FOV punch without disabling camera follow',()=>{
  const camera={target:new api.Vector3(),fov:1},rig=new api.CameraRig(camera);rig.setTarget(2,3,4);rig.addTrauma(.5);rig.punchFov(.5);rig.update(.02);assert.notDeepEqual(camera.target.asArray(),[2,3,4]);assert.ok(camera.fov<1);
  rig.setShakeEnabled(false);rig.addTrauma(1);rig.punchFov(1);rig.setTarget(5,6,7);rig.update(.02);assert.deepEqual(camera.target.asArray(),[5,6,7]);assert.equal(camera.fov,1);
  rig.setShakeEnabled(true);rig.addTrauma(.5);rig.update(.02);assert.notDeepEqual(camera.target.asArray(),[5,6,7]);
});
