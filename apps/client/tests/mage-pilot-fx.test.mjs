import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {createMagePilotFx,magePilotMotion} from './src/mage-pilot-fx';
export {mageOpenSigilShape,magePointedShape} from './src/mage-pilot-fx-geometry';
`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
async function fixture(run,extra={}){
 const engine=new api.NullEngine(),scene=new api.Scene(engine);new api.FreeCamera('original-camera',new api.Vector3(0,3,-8),scene);
 let now=0,origin={x:1,y:2,z:0};const events=[];
 const fx=api.createMagePilotFx(scene,{now:()=>now,castOrigin:()=>origin,groundAt:()=>0,onMotion:(cast,phase)=>events.push([cast.castId,phase]),basicCapacity:2,lanceCapacity:1,...extra});
 try{await fx.prewarm();return await run({engine,scene,fx,events,origin,setOrigin(value){origin=value;},step(value){now=value;scene.onBeforeRenderObservable.notifyObservers(scene);}});}
 finally{fx.dispose();scene.dispose();engine.dispose();}
}
const basic=(id='e1:b1')=>({castId:id,actorId:1,ability:'h02_basic',targetXZ:{x:1,z:4},startedAt:0,releaseAt:100,impactAt:300,facing:0});
const core=scene=>scene.meshes.find(m=>/basic-.*-core$/.test(m.name)&&m.isEnabled());
const activeShards=scene=>scene.meshes.filter(m=>/-shards$/.test(m.name)&&m.isEnabled());

test('accepted charge follows real marker then launch freezes; predicted impact never confirms a hit',()=>fixture(({scene,fx,step,setOrigin,events})=>{
 assert.equal(fx.beginAcceptedCast(basic()),true);assert.equal(core(scene).position.y,2);
 setOrigin({x:1,y:2.4,z:.2});step(90);assert.equal(core(scene).position.y,2.4);
 step(100);setOrigin({x:50,y:50,z:50});step(200);
 assert.ok(core(scene).position.z>.2&&core(scene).position.z<4);assert.ok(core(scene).position.x<2);
 const forward=api.Vector3.TransformNormal(new api.Vector3(0,0,1),core(scene).computeWorldMatrix(true)).normalize();
 const expected=new api.Vector3(0,.65-2.4,4-.2).normalize();assert.ok(api.Vector3.Dot(forward,expected)>.99,'pointed head must face its actual travel direction');
 step(300);assert.equal(fx.stats().confirmedHits,0);assert.equal(activeShards(scene).length,0);
 assert.deepEqual(events,[['e1:b1','accepted'],['e1:b1','released']]);
 step(500);assert.equal(fx.stats().drawCallsEstimate,0);assert.equal(fx.stats().phases[0].phase,'await');
 step(1801);assert.equal(fx.stats().active,0);assert.equal(fx.stats().confirmedHits,0);
}));

test('only explicit unique authoritative hit produces shards, at corrected endpoint',()=>fixture(({scene,fx,step})=>{
 fx.beginAcceptedCast(basic());step(250);
 assert.equal(fx.resolve({castId:'e1:b1',outcome:'hit',targetXZ:{x:2,z:5}}),true);
 assert.equal(fx.stats().confirmedHits,1);assert.equal(activeShards(scene).length,1);
 assert.equal(fx.resolve({castId:'e1:b1',outcome:'hit',targetXZ:{x:2,z:5}}),false);
 const positions=activeShards(scene)[0].getVerticesData('position');
 const contact=fx.stats().phases[0].cosmeticContact;assert.ok(contact[0]>1.8&&contact[0]<2);
 assert.ok(positions.filter((_,i)=>i%3===0).every(x=>x>1.5&&x<2.2));
 step(571);assert.equal(fx.stats().active,0);assert.equal(fx.stats().drawCallsEstimate,0);
}));

test('cancel, miss and clear suppress all confirmed-hit feedback and stale resolutions',()=>fixture(({scene,fx,step,events})=>{
 fx.beginAcceptedCast(basic());step(50);assert.equal(fx.resolve({castId:'e1:b1',outcome:'cancelled',targetXZ:{x:1,z:4}}),true);
 assert.equal(activeShards(scene).length,0);step(151);assert.equal(fx.stats().active,0);
 const cast={...basic('e1:b2'),startedAt:151,releaseAt:251,impactAt:451};fx.beginAcceptedCast(cast);step(300);
 fx.resolve({castId:'e1:b2',outcome:'miss',targetXZ:{x:1,z:4}});assert.equal(fx.stats().confirmedHits,0);
 fx.clear();assert.equal(fx.resolve({castId:'e1:b2',outcome:'hit',targetXZ:{x:1,z:4}}),false);
 assert.equal(fx.stats().drawCallsEstimate,0);assert.ok(events.some(e=>e[1]==='cancelled'));assert.ok(events.some(e=>e[1]==='miss'));
}));

test('invalid times/IDs/endpoint, changed replay and duplicate reject without growing resources',()=>fixture(({scene,fx})=>{
 const count=[scene.meshes.length,scene.materials.length,scene.lights.length,scene.textures.length];
 assert.equal(fx.beginAcceptedCast({...basic(),targetXZ:{x:NaN,z:4}}),false);
 assert.equal(fx.beginAcceptedCast({...basic(),releaseAt:301}),false);
 assert.equal(fx.beginAcceptedCast({...basic(),castId:''}),false);
 assert.equal(fx.beginAcceptedCast(basic()),true);assert.equal(fx.beginAcceptedCast({...basic()}),false);
 assert.equal(fx.beginAcceptedCast({...basic(),targetXZ:{x:1,z:5}}),false);
 assert.equal(fx.stats().duplicates,1);assert.equal(fx.stats().accepted,1);
 assert.deepEqual([scene.meshes.length,scene.materials.length,scene.lights.length,scene.textures.length],count);
}));

test('signature uses500msserver release and open structured sigil; no other draft template is instantiated',()=>fixture(({scene,fx,step})=>{
 fx.beginAcceptedCast({...basic('e1:l1'),ability:'h02_star_lance',releaseAt:500,impactAt:750});step(467);
 assert.equal(fx.stats().phases[0].phase,'charge');assert.ok(scene.meshes.some(m=>/-open-sigil$/.test(m.name)&&m.isEnabled()));
 step(500);assert.equal(fx.stats().phases[0].phase,'travel');assert.equal(fx.stats().lights,0);
 assert.ok(scene.meshes.every(m=>!/(nova|gale|rift|ward|orrery)/.test(m.name)));
 assert.equal(fx.stats().confirmedHits,0);
 fx.resolve({castId:'e1:l1',outcome:'hit',targetXZ:{x:2,z:5}});
 const sigil=scene.meshes.find(m=>/-open-sigil$/.test(m.name)),contact=fx.stats().phases[0].cosmeticContact;
 assert.equal(sigil.position.z,contact[2]);assert.ok(sigil.position.z<5);
 assert.ok(Math.abs(sigil.position.y-.035)<1e-8);assert.equal(sigil.rotation.x,Math.PI/2);
 step(821);fx.beginAcceptedCast({...basic('e1:l2'),ability:'h02_star_lance',startedAt:821,releaseAt:1321,impactAt:1571});
 assert.equal(sigil.rotation.x,0,'reused impact glyph must reset to vertical staff charge');
}));

test('glyph has actual negative center; pointed shapes are elongated and normals inputs finite',()=>{
 const glyph=api.mageOpenSigilShape();
 const coversOrigin=(a,b,c)=>{const cross=(p,q)=>p[0]*q[1]-p[1]*q[0];const s=[cross(a,b),cross(b,c),cross(c,a)];return s.every(v=>v>=0)||s.every(v=>v<=0);};
 for(let i=0;i<glyph.indices.length;i+=3){const p=Array.from({length:3},(_,j)=>glyph.positions.slice(glyph.indices[i+j]*3,glyph.indices[i+j]*3+2));assert.ok(!coversOrigin(...p),'no sigil triangle may fill the center');}
 for(const signature of [false,true]){const shape=api.magePointedShape(signature),z=shape.positions.filter((_,i)=>i%3===2),x=shape.positions.filter((_,i)=>i%3===0);assert.ok((Math.max(...z)-Math.min(...z))/(Math.max(...x)-Math.min(...x))>3);assert.ok(shape.positions.every(Number.isFinite));}
 const motion=api.magePilotMotion({ability:'h02_star_lance',startedAt:0,releaseAt:500});assert.equal(motion.clip,'mage.skill_bolt');assert.ok(Math.abs(motion.speedRatio-14/15)<1e-9);
});

test('actual constructed Mage meshes enable vertex alpha and their materials choose alpha blending',()=>fixture(({scene,fx})=>{
 const owned=scene.meshes.filter(mesh=>mesh.metadata?.magePilotFx);
 assert.equal(owned.length,fx.stats().meshCount);
 for(const mesh of owned){
  assert.equal(mesh.hasVertexAlpha,true,mesh.name+' must enable authored alpha');
  assert.equal(mesh.useVertexColors,true,mesh.name+' must use its vertex colours');
  assert.equal(mesh.material.needAlphaBlendingForMesh(mesh),true,mesh.name+' must use a blending pass');
  assert.ok(mesh.material.alpha<1&&mesh.material.alpha>0);
 }
 for(const mesh of owned.filter(mesh=>/-core$|-trail$|-shards$/.test(mesh.name))){
  const colours=mesh.getVerticesData('color');assert.ok(colours.some((value,index)=>index%4===3&&value<.6),mesh.name+' requires actual edge/tail falloff data');
 }
}));

test('finite pools bound overload and repeated casting; missing live marker cancels safely',()=>fixture(({scene,fx,step,setOrigin})=>{
 const count=[scene.meshes.length,scene.materials.length];fx.beginAcceptedCast(basic('1'));fx.beginAcceptedCast(basic('2'));assert.equal(fx.beginAcceptedCast(basic('3')),false);assert.equal(fx.stats().dropped,1);assert.equal(fx.beginAcceptedCast(basic('3')),false);assert.equal(fx.stats().duplicates,1,'dropped cosmetics still deduplicate server cast IDs');
 fx.clear();fx.beginAcceptedCast(basic('4'));setOrigin(null);step(50);assert.equal(fx.stats().confirmedHits,0);step(151);assert.equal(fx.stats().active,0);
 setOrigin({x:1,y:2,z:0});for(let i=0;i<30;i++){fx.clear();assert.equal(fx.beginAcceptedCast({...basic('loop'+i),startedAt:151,releaseAt:251,impactAt:451}),true);}
 assert.deepEqual([scene.meshes.length,scene.materials.length],count);
}));

test('owned resources/observers dispose while borrowed scene/camera survive; prewarm disposal cancels promptly',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine),camera=new api.FreeCamera('borrowed',api.Vector3.Zero(),scene);
 const before=[scene.meshes.length,scene.materials.length,scene.textures.length,scene.onBeforeRenderObservable.observers.length];
 const fx=api.createMagePilotFx(scene,{now:()=>0,castOrigin:()=>({x:0,y:2,z:0}),groundAt:()=>0,basicCapacity:1,lanceCapacity:1});
 for(const mesh of scene.meshes)mesh.material.isReadyForSubMesh=()=>false;
 const warm=fx.prewarm();fx.dispose();await assert.rejects(warm,/cancelled/);
 await new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(camera.isDisposed(),false);assert.deepEqual([scene.meshes.length,scene.materials.length,scene.textures.length,scene.onBeforeRenderObservable.observers.length],before);
 assert.equal(fx.beginAcceptedCast(basic()),false);scene.dispose();engine.dispose();
});

test('clock correction cannot rewind released travel; vertical travel has finite orientation and buffers',()=>fixture(({scene,fx,step})=>{
 fx.beginAcceptedCast({...basic(),targetXZ:{x:1,z:0}});step(200);const z=core(scene).position.y;step(150);
 assert.equal(core(scene).position.y,z);assert.ok(core(scene).rotationQuaternion.asArray().every(Number.isFinite));
 for(const mesh of scene.meshes.filter(m=>m.isEnabled()))assert.ok(mesh.getVerticesData('position').every(Number.isFinite));
}));

test('motion callback clearing on hit cannot resurrect shards on a released lease',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);new api.FreeCamera('borrowed',api.Vector3.Zero(),scene);
 let fx;fx=api.createMagePilotFx(scene,{now:()=>100,castOrigin:()=>({x:1,y:2,z:0}),groundAt:()=>0,basicCapacity:1,lanceCapacity:1,onMotion:(_cast,phase)=>{if(phase==='hit')fx.clear();}});
 try{await fx.prewarm();fx.beginAcceptedCast(basic());fx.resolve({castId:'e1:b1',outcome:'hit',targetXZ:{x:1,z:4}});assert.equal(fx.stats().active,0);assert.equal(fx.stats().drawCallsEstimate,0);}finally{fx.dispose();scene.dispose();engine.dispose();}
});

test('nullable started cast holds charge beyond planned release; numeric cosmetic estimate also cannot launch when deferred',()=>fixture(({scene,fx,step,events})=>{
 const started={...basic(),impactAt:null};assert.equal(fx.beginAcceptedCast(started),true);
 step(1000);assert.equal(fx.stats().phases[0].phase,'charge');assert.equal(fx.stats().phases[0].flightConfirmed,false);
 assert.equal(fx.stats().phases[0].impactAt,null);assert.equal(scene.meshes.filter(m=>/-trail$/.test(m.name)&&m.isEnabled()).length,0);
 assert.ok(!events.some(e=>e[1]==='released'));assert.equal(fx.stats().confirmedHits,0);
 fx.clear();assert.equal(fx.beginAcceptedCast({...basic('estimate'),startedAt:1000,releaseAt:1100,impactAt:1300,deferReleaseUntilConfirmed:true}),true);
 step(1400);assert.equal(fx.stats().phases[0].phase,'charge');assert.equal(fx.stats().releaseUpdates,0);
 assert.equal(scene.meshes.filter(m=>/-trail$/.test(m.name)&&m.isEnabled()).length,0);
}));

test('authoritative release updates locked origin, endpoint and times without resetting nonce/history or confirming impact',()=>fixture(({scene,fx,step,setOrigin,events})=>{
 const started={...basic(),impactAt:null};fx.beginAcceptedCast(started);step(300);
 const generation=fx.stats().phases[0].generation;
 const released={castId:'e1:b1',origin:{x:2,y:3,z:1},targetXZ:{x:4,z:8},releaseAt:350,impactAt:700};
 assert.equal(fx.confirmReleasedCast(released),true);assert.equal(fx.stats().phases[0].generation,generation);assert.equal(fx.stats().history,1);
 assert.equal(fx.beginAcceptedCast(started),false);assert.equal(fx.stats().accepted,1);
 setOrigin({x:30,y:30,z:30});step(350);assert.equal(core(scene).position.x,2);assert.equal(core(scene).position.y,3);assert.equal(core(scene).position.z,1);
 step(525);assert.ok(Math.abs(core(scene).position.x-3)<1e-8);assert.ok(Math.abs(core(scene).position.z-4.5)<1e-8);
 assert.equal(fx.confirmReleasedCast(released),false);assert.equal(fx.stats().duplicateReleaseUpdates,1);
 assert.equal(fx.confirmReleasedCast({...released,targetXZ:{x:6,z:10},impactAt:900}),true);
 assert.equal(fx.stats().phases[0].generation,generation);assert.equal(fx.stats().phases[0].phase,'travel');
 assert.equal(events.filter(e=>e[1]==='accepted').length,1);assert.equal(events.filter(e=>e[1]==='released').length,1);
 step(900);assert.equal(fx.stats().confirmedHits,0);assert.equal(activeShards(scene).length,0);
 assert.equal(fx.resolve({castId:'e1:b1',outcome:'hit',targetXZ:{x:6,z:10}}),true);assert.equal(fx.stats().confirmedHits,1);
}));

test('prerelease cancellation with null impact prevents late released update from launching or producing a hit',()=>fixture(({scene,fx,step,events})=>{
 fx.beginAcceptedCast({...basic(),impactAt:null});step(50);
 fx.resolve({castId:'e1:b1',outcome:'cancelled',targetXZ:{x:1,z:4}});
 const released={castId:'e1:b1',origin:{x:2,y:3,z:1},targetXZ:{x:4,z:8},releaseAt:100,impactAt:500};
 assert.equal(fx.confirmReleasedCast(released),false);step(500);assert.equal(fx.confirmReleasedCast(released),false);
 assert.equal(fx.stats().active,0);assert.equal(fx.stats().drawCallsEstimate,0);assert.equal(fx.stats().confirmedHits,0);
 assert.equal(activeShards(scene).length,0);assert.ok(!events.some(e=>e[1]==='released'));
}));

test('deferred flight confirmation is bounded and validates origin/times; clear rejects stale updates',()=>fixture(({fx,step})=>{
 assert.equal(fx.beginAcceptedCast({...basic(),impactAt:undefined}),false);
 assert.equal(fx.beginAcceptedCast({...basic(),impactAt:null,deferReleaseUntilConfirmed:false}),false);
 assert.equal(fx.beginAcceptedCast(basic('factory-deferred')),true);step(300);
 assert.equal(fx.stats().phases[0].phase,'charge','factory deferral also blocks a numeric cosmetic flight estimate');fx.clear();
 fx.beginAcceptedCast({...basic(),impactAt:null});
 assert.equal(fx.confirmReleasedCast({castId:'e1:b1',origin:{x:NaN,y:2,z:1},targetXZ:{x:1,z:4},releaseAt:100,impactAt:300}),false);
 assert.equal(fx.confirmReleasedCast({castId:'e1:b1',origin:{x:1,y:2,z:1},targetXZ:{x:1,z:4},releaseAt:100,impactAt:50}),false);
 step(1601);assert.equal(fx.stats().active,0);assert.equal(fx.stats().confirmedHits,0);assert.equal(fx.stats().expired,1);
 fx.clear();assert.equal(fx.confirmReleasedCast({castId:'e1:b1',origin:{x:1,y:2,z:1},targetXZ:{x:1,z:4},releaseAt:1700,impactAt:1900}),false);
},{deferReleaseUntilConfirmed:true}));

test('confirmed contact is on caster-facing surface while projectile goal/times remain authoritative',()=>fixture(({scene,fx,step})=>{
 const cast={...basic('contact'),ability:'h02_star_lance'};fx.beginAcceptedCast(cast);step(200);
 assert.ok(Math.abs(scene.meshes.find(m=>/lance-.*-core$/.test(m.name)).position.z-2)<1e-8);
 assert.equal(fx.stats().phases[0].cosmeticContact,null);assert.equal(activeShards(scene).length,0);
 fx.resolve({castId:'contact',outcome:'hit',targetXZ:{x:1,z:4},contactRadius:.825});
 const phase=fx.stats().phases[0];assert.deepEqual(phase.projectileGoal,[1,.65,4]);
 assert.ok(Math.abs(phase.cosmeticContact[0]-1)<1e-8);assert.ok(Math.abs(phase.cosmeticContact[2]-3.175)<1e-8);
 assert.ok(phase.cosmeticContact[1]>.78);assert.equal(phase.releaseAt,100);assert.equal(phase.impactAt,300);
 const sigil=scene.meshes.find(m=>/-open-sigil$/.test(m.name)&&m.isEnabled());assert.ok(Math.abs(sigil.position.z-3.175)<1e-8);
 const positions=activeShards(scene)[0].getVerticesData('position');assert.ok(Math.max(...positions.filter((_,i)=>i%3===2))<3.25,'shards must remain outside the measured.745m stock-body radius');
 assert.ok(Math.max(...positions.filter((_,i)=>i%3===1))>1,'pointed tips must clear the low body contact band');
 assert.ok(fx.stats().drawCallsEstimate<=3);assert.equal(fx.stats().lights,0);assert.equal(fx.stats().particles,0);
 step(300);assert.deepEqual(fx.stats().phases[0].projectileGoal,[1,.65,4]);assert.ok(fx.stats().drawCallsEstimate<=3);
}));

test('cosmetic contact has a finite facing fallback for zero-XZ distance and never appears for a miss',()=>fixture(({fx,step})=>{
 const cast={...basic('overlap'),ability:'h02_star_lance',targetXZ:{x:1,z:0},facing:Math.PI/2};
 fx.beginAcceptedCast(cast);step(100);fx.resolve({castId:'overlap',outcome:'hit',targetXZ:{x:1,z:0}});
 const phase=fx.stats().phases[0];assert.ok(phase.cosmeticContact.every(Number.isFinite));
 assert.ok(Math.abs(phase.cosmeticContact[0]-.15)<1e-8);assert.equal(phase.cosmeticContactRadius,.85);assert.deepEqual(phase.projectileGoal,[1,.65,0]);
 fx.clear();fx.beginAcceptedCast({...cast,castId:'miss'});fx.resolve({castId:'miss',outcome:'miss',targetXZ:{x:1,z:0}});
 assert.equal(fx.stats().phases[0].cosmeticContact,null);assert.equal(fx.stats().drawCallsEstimate,0);
}));

test('confirmed contact accepts measured bounded radius; invalid hit radius and miss cannot create contact',()=>fixture(({fx})=>{
 const cast={...basic('radius'),ability:'h02_star_lance'};fx.beginAcceptedCast(cast);
 for(const contactRadius of [NaN,Infinity,-1,.249,4.001]){
  assert.equal(fx.resolve({castId:'radius',outcome:'hit',targetXZ:{x:1,z:4},contactRadius}),false);
  assert.equal(fx.stats().confirmedHits,0);assert.equal(fx.stats().phases[0].cosmeticContact,null);
 }
 assert.equal(fx.resolve({castId:'radius',outcome:'hit',targetXZ:{x:1,z:4},contactRadius:1.25}),true);
 assert.equal(fx.stats().phases[0].cosmeticContactRadius,1.25);assert.ok(Math.abs(fx.stats().phases[0].cosmeticContact[2]-2.75)<1e-8);
 assert.deepEqual(fx.stats().phases[0].projectileGoal,[1,.65,4]);assert.ok(fx.stats().drawCallsEstimate<=3);
 fx.clear();fx.beginAcceptedCast(basic('miss-radius'));
 assert.equal(fx.resolve({castId:'miss-radius',outcome:'miss',targetXZ:{x:1,z:4},contactRadius:4}),true);
 assert.equal(fx.stats().phases[0].cosmeticContact,null);assert.equal(fx.stats().drawCallsEstimate,0);
}));
