import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
const root=fileURLToPath(new URL('..',import.meta.url));
const bundled = process.env.COMBAT_VFX_TEST_BUNDLE ? null : await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';
export {RawTexture} from '@babylonjs/core/Materials/Textures/rawTexture';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
export * from './src/combat-vfx-kit';
export * from './src/combat-vfx-skills';
export * from './src/combat-vfx-surface';`,resolveDir:root,loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',loader:{'.png':'empty','.glb':'empty','.svg':'empty'}});
const api = process.env.COMBAT_VFX_TEST_BUNDLE ? await import(process.env.COMBAT_VFX_TEST_BUNDLE) : await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
async function fixture(run,preset='high',groundAt=(x,z)=>4+.03*x+.02*z,hero02Draft=false){
 const engine=new api.NullEngine(),scene=new api.Scene(engine);
 void scene.defaultMaterial; const baseline=api.sceneVfxCounts(scene),observers=scene.onBeforeRenderObservable.observers.length;
 const texture=api.RawTexture.CreateRGBATexture(new Uint8Array([255,255,255,255]),1,1,scene,false,false);
 const tex=Object.fromEntries(['runeOuter','runeInner','runeBlade','swirl','shock','star','cracks','scorch','streak','palm','noise','disc','lightning','impact','swirlSheet','shards','dust'].map(key=>[key,texture]));
 const shapes=Object.fromEntries(['blade','funnel','cone','ringWall'].map(key=>[key,api.MeshBuilder.CreateBox('fixture-'+key,{size:1},scene)]));
 const kit={scene,tex,...shapes,dispose(){texture.dispose();Object.values(shapes).forEach(s=>s.dispose());}};
 const runtime=api.createCombatVfx(scene,kit,{groundAt,preset:()=>preset,ownKit:true,hero02Draft});runtime.setManual(true);
 try {await run({scene,runtime,groundAt,baseline,observers});}finally{runtime.dispose();scene.dispose();engine.dispose();}
}
const enabled=(scene,name)=>scene.meshes.filter(m=>m.name===name).some(m=>m.isEnabled());
test('easing clamps, overshoots and envelope follows beat boundaries',()=>{
 assert.equal(api.easeOutCubic(-1),0);assert.equal(api.easeOutCubic(1),1);assert.equal(api.easeInQuad(.5),.25);assert.equal(api.easeOutQuad(.5),.75);
 assert.ok(api.easeOutBack(.7)>1);assert.equal(api.envelope(0,0,.1,.3,.5),0);assert.equal(api.envelope(.1,0,.1,.3,.5),1);assert.equal(api.envelope(.3,0,.1,.3,.5),1);assert.ok(Math.abs(api.envelope(.4,0,.1,.3,.5)-.75)<1e-9);assert.equal(api.envelope(.5,0,.1,.3,.5),0);
 assert.equal(api.exposureFromWorld(1),.78);assert.equal(api.exposureFromWorld(1.22),1);assert.ok(Math.abs(api.exposureFromWorld(1.11)-.89)<1e-9);
});
test('Nova telegraph, eruption, lightning and dissipation match lab beats',()=>fixture(({scene,runtime})=>{
 runtime.cast('xs_bladeward_nova',new api.Vector3(0,99,0),0);assert.ok(enabled(scene,'nova-ring'));assert.ok(!enabled(scene,'nova-flash'));
 runtime.step(.19);assert.ok(enabled(scene,'nova-flash'));assert.ok(enabled(scene,'nova-shock'));assert.ok(!enabled(scene,'nova-wall'));
 runtime.step(.08);assert.ok(enabled(scene,'nova-arcs'));
 runtime.step(.24);assert.ok(!enabled(scene,'nova-ring'));assert.ok(!enabled(scene,'nova-wall'));
 runtime.step(.2);assert.ok(!enabled(scene,'nova-arcs'));runtime.step(2.2);assert.equal(runtime.stats().dc,0);
}));
test('Gale releases at 200ms, travels toward +Z at 16m/s and reacts at 9m',()=>fixture(({scene,runtime,groundAt})=>{
 const handle=runtime.cast('xs_gale_palm',new api.Vector3(3,0,2),0);runtime.step(.1);assert.ok(enabled(scene,'gale-core'));assert.ok(enabled(scene,'gale-sigil'),'the palm silhouette is visible during anticipation');
 runtime.step(.11);assert.ok(enabled(scene,'gale-sigil'));assert.ok(enabled(scene,'gale-cone'));
 runtime.step(.52);assert.ok(enabled(scene,'gale-vortex'));const mesh=scene.meshes.find(m=>m.name==='gale-vortex'&&m.isEnabled());assert.equal(mesh.position.z,11);assert.equal(mesh.position.x,3);assert.equal(mesh.position.y,groundAt(3,11)+.04);
 runtime.step(handle.duration);assert.equal(runtime.stats().dc,0);
}));
test('only Gale palm preserves the authored RGBA source; other surfaces keep the shared ramp',()=>fixture(({scene,runtime})=>{
 runtime.cast('xs_gale_palm',new api.Vector3(0,0,0),0);runtime.step(.3);
 const palm=scene.meshes.find(m=>m.name==='gale-sigil'&&m.isEnabled()),plugin=palm.material.pluginManager.getPlugin('VfxSurface');
 assert.equal(plugin.options.sourceColor,true);assert.equal(plugin.options.blend,'blend');assert.equal(plugin.intensity,.95);
 const defines={};plugin.prepareDefines(defines,scene,palm);assert.equal(defines.VFX_SOURCE_COLOR,true);
 runtime.clear();runtime.cast('xs_bladeward_nova',new api.Vector3(0,0,0),0);
 const ring=scene.meshes.find(m=>m.name==='nova-ring'&&m.isEnabled()),ringPlugin=ring.material.pluginManager.getPlugin('VfxSurface');assert.equal(ringPlugin.options.sourceColor,undefined);
 ringPlugin.prepareDefines(defines,scene,ring);assert.equal(defines.VFX_SOURCE_COLOR,false);
}));
test('Rift retains circles through ticks and enables collapse/scorch at 3050ms',()=>fixture(({scene,runtime})=>{
 runtime.cast('xs_void_rift',new api.Vector3(0,0,0),Math.PI/2);assert.ok(enabled(scene,'rift-outer'));assert.ok(!enabled(scene,'rift-inner'));
 runtime.step(.16);assert.ok(enabled(scene,'rift-inner'));runtime.step(.5);assert.ok(!enabled(scene,'rift-energy-bed'));assert.ok(enabled(scene,'rift-abyss'));assert.ok(enabled(scene,'rift-curtain'));
 runtime.step(.24);assert.ok(enabled(scene,'rift-rim'));runtime.step(2.16);assert.ok(enabled(scene,'rift-implosion'));assert.ok(enabled(scene,'rift-scorch'));assert.ok(!enabled(scene,'rift-energy-bed'));
 runtime.step(.35);assert.ok(!enabled(scene,'rift-outer'));runtime.step(1.2);assert.equal(runtime.stats().dc,0);
}));
test('cycle2 keeps essential shapes, removes duplicate submissions and makes palm/blue blade/void depth readable candidates',()=>fixture(({scene,runtime})=>{
 runtime.cast('xs_bladeward_nova',new api.Vector3(),0);runtime.step(.27);
 const ring=scene.meshes.find(m=>m.name==='nova-ring'&&m.isEnabled()),blade=scene.meshes.find(m=>m.name==='nova-blades'&&m.instances.some(i=>i.isEnabled()));
 assert.ok(!ring.metadata?.glow);assert.equal(blade.metadata.glow,true);assert.ok(blade.instances.some(i=>i.position.y>.5));assert.ok(blade.instances.every(i=>i.scaling.x>i.scaling.z));assert.ok(!enabled(scene,'nova-wall'));
 runtime.clear();runtime.cast('xs_gale_palm',new api.Vector3(),0);runtime.step(.36);
 const palm=scene.meshes.find(m=>m.name==='gale-sigil'&&m.isEnabled()),uv=palm.getVerticesData(api.VertexBuffer.UVKind);
 assert.ok(palm.scaling.y>=3.6);assert.ok(palm.scaling.x<palm.scaling.y,'ROI scale preserves source aspect ratio');assert.ok(uv.every(v=>v>0&&v<1));
 runtime.step(.42);assert.ok(!enabled(scene,'gale-ground-flash'));assert.ok(enabled(scene,'gale-vortex'));
 runtime.clear();runtime.cast('xs_void_rift',new api.Vector3(),0);runtime.step(1.3);
 const abyss=scene.meshes.find(m=>m.name==='rift-abyss'&&m.isEnabled()),volume=scene.meshes.find(m=>m.name==='rift-curtain'&&m.isEnabled()),rim=scene.meshes.find(m=>m.name==='rift-rim'&&m.isEnabled());
 assert.ok(abyss.scaling.x>=7.9);assert.ok(volume.position.y>1.5);assert.ok(!enabled(scene,'rift-energy-bed'));
 const palette=rim.material.pluginManager.getPlugin('VfxSurface');assert.ok(palette.mid.g>palette.mid.r&&palette.mid.b>palette.mid.r,'rim stays cyan rather than white/pink');
}));
test('ten casts of every skill reuse pools and dispose to exact baseline',()=>fixture(async({scene,runtime,baseline,observers})=>{
 const counts=api.sceneVfxCounts(scene);assert.equal(scene.onBeforeRenderObservable.observers.length,observers+1);
 for(const id of ['xs_bladeward_nova','xs_gale_palm','xs_void_rift'])for(let i=0;i<10;i++){
  const handle=runtime.cast(id,new api.Vector3(i,5,i*2),i*.2);assert.ok(handle);runtime.step(.3);runtime.step(handle.duration);assert.deepEqual(api.sceneVfxCounts(scene),counts);assert.equal(runtime.stats().dc,0);assert.equal(runtime.stats().lights,0);
 }
 runtime.dispose();runtime.dispose();await new Promise(resolve=>setTimeout(resolve,0));assert.deepEqual(api.sceneVfxCounts(scene),baseline);assert.equal(scene.onBeforeRenderObservable.observers.length,observers);
}));
test('Low drops lights/lightning, quarters emission, and keeps both telegraph circles',()=>fixture(({scene,runtime})=>{
 runtime.cast('xs_void_rift',new api.Vector3(),0);runtime.step(.3);assert.ok(enabled(scene,'rift-outer'));assert.ok(enabled(scene,'rift-inner'));assert.ok(!enabled(scene,'rift-arcs'));assert.equal(runtime.stats().lights,0);
 runtime.clear();runtime.cast('xs_bladeward_nova',new api.Vector3(),0);runtime.step(.27);assert.ok(enabled(scene,'nova-ring'));assert.ok(!enabled(scene,'nova-arcs'));assert.equal(runtime.stats().lights,0);
 const motes=scene.particleSystems.find(s=>s.name==='nova-motes'&&s.isStarted());assert.equal(motes.manualEmitCount,4);
},'low'));
test('terrain-conforming vertices stay 3–6cm over a real sampled slope',()=>fixture(({scene,runtime,groundAt})=>{
 runtime.cast('xs_void_rift',new api.Vector3(2,50,3),.3);runtime.step(.7);
 for(const mesh of scene.meshes.filter(m=>m.metadata?.combatVfxGround&&m.isEnabled()&&!m.instances.length)){
  const positions=mesh.getVerticesData(api.VertexBuffer.PositionKind),matrix=mesh.computeWorldMatrix(true);
  for(let i=0;i<positions.length;i+=3){const world=api.Vector3.TransformCoordinates(new api.Vector3(...positions.slice(i,i+3)),matrix);const gap=world.y-groundAt(world.x,world.z);assert.ok(gap>=.029&&gap<=.061,`${mesh.name} ground gap ${gap}`);}
 }
}));
test('bounded overlapping slots reject saturation and stale handles cannot cancel replays',()=>fixture(({runtime})=>{
 const a=runtime.cast('xs_void_rift',new api.Vector3(),0),b=runtime.cast('xs_void_rift',new api.Vector3(),0);assert.ok(a&&b);assert.equal(runtime.cast('xs_void_rift',new api.Vector3(),0),null);a.cancel();const c=runtime.cast('xs_void_rift',new api.Vector3(),0);assert.ok(c);a.cancel();assert.ok(runtime.stats().dc>=2);
}));
test('unsupported ground never substitutes zero',()=>fixture(({runtime})=>{assert.equal(runtime.cast('xs_void_rift',new api.Vector3(),0),null);assert.equal(runtime.stats().dc,0);},'high',()=>null));
test('draft identities are opt-in and exact frost/crystal assets fail loudly without substituting owner palm/blades',()=>fixture(({scene,runtime})=>{
 const counts=api.sceneVfxCounts(scene);assert.equal(runtime.stats().physicalSlots,6);
 for(const id of ['h02_rimeshard_nova','h02_hoarfrost_gale','h02_moonveil_ward']){assert.equal(runtime.cast(id,new api.Vector3(),0),null);assert.equal(runtime.previewReadiness(id).ready,false);}
 assert.equal(runtime.cast('witch02_prism_ward',new api.Vector3(),0),null);assert.ok(runtime.cast('xs_gale_palm',new api.Vector3(),0));assert.deepEqual(api.sceneVfxCounts(scene),counts);
}));
test('opt-in Hollow obeys draft low tier while unsupported frost/core sources are reported ITERATE',()=>fixture(({runtime})=>{
 assert.ok(runtime.cast('h02_starless_hollow',new api.Vector3(),0));runtime.step(.15);runtime.step(.6);const estimate=runtime.stats().budgetEstimates[0];assert.ok(estimate.draws<=5);assert.ok(estimate.particles<=60);assert.deepEqual(estimate.essentialMissing,[]);
 assert.ok(runtime.previewReadiness('h02_hoarfrost_gale').missing.includes('vfx_hex_sigil'));
},'low',(x,z)=>4+.03*x+.02*z,true));
test('preview hook is DEV-only, dynamic and keeps gameplay out of the runtime',async()=>{
 const scene=await readFile(new URL('../src/scene.ts',import.meta.url),'utf8');assert.match(scene,/import\.meta\.env\.DEV && new URLSearchParams\(location\.search\)\.has\("vfxdemo"\)[\s\S]*?await import\("\.\/combat-vfx-demo"\)/);
 const source=await readFile(new URL('../src/combat-vfx-demo.ts',import.meta.url),'utf8');assert.doesNotMatch(source,/encodeAction|WebSocket|cooldown|damage|requestAnimationFrame/);
});

