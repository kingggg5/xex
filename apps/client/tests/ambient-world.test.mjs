import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundled=await build({stdin:{contents:`
import {NullEngine} from '@babylonjs/core/Engines/nullEngine';import {Scene} from '@babylonjs/core/scene';
import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder';import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {DynamicTexture} from '@babylonjs/core/Materials/Textures/dynamicTexture';import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';import {DirectionalLight} from '@babylonjs/core/Lights/directionalLight';import {ShadowGenerator} from '@babylonjs/core/Lights/Shadows/shadowGenerator';
import '@babylonjs/core/Meshes/instancedMesh';
import {createAmbientWorld,updateAmbientAppearance} from './src/ambient-world';
export {NullEngine,Scene,MeshBuilder,StandardMaterial,DynamicTexture,Vector3,FreeCamera,DirectionalLight,ShadowGenerator,createAmbientWorld,updateAmbientAppearance};`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
const counts=scene=>({meshes:scene.meshes.length,materials:scene.materials.length,textures:scene.textures.length,transforms:scene.transformNodes.length,before:scene.onBeforeRenderObservable.observers.length,newMeshes:scene.onNewMeshAddedObservable.observers.length,dispose:scene.onDisposeObservable.observers.length});
async function fixture(run){
  const oldCanvas=globalThis.OffscreenCanvas;
  globalThis.OffscreenCanvas=class{constructor(width,height){this.width=width;this.height=height;this.ctx=new Proxy({createLinearGradient:()=>({addColorStop(){}}),createRadialGradient:()=>({addColorStop(){}}),getImageData:()=>({width,height,data:new Uint8ClampedArray(width*height*4)})},{get:(target,key)=>key in target?target[key]:(()=>{}),set:(target,key,value)=>(target[key]=value,true)});}getContext(){return this.ctx;}};
  let now=0;const engine=new api.NullEngine(),scene=new api.Scene(engine);
  const camera=new api.FreeCamera('camera',new api.Vector3(0,4,-15),scene);scene.activeCamera=camera;
  const sky=new api.DynamicTexture('env-sky-texture',{width:16,height:256},scene,false),cloudMaterial=new api.StandardMaterial('cloud-white',scene);
  const master=api.MeshBuilder.CreateSphere('env-cloud-master-s',{diameter:9},scene);master.material=cloudMaterial;master.isVisible=false;
  const puffs=[];for(let i=0;i<2;i++){const puff=master.createInstance('env-cloud-'+i+'-0');puff.position.set(i*30,40,20);puffs.push(puff);}
  const sun=new api.DirectionalLight('sun',new api.Vector3(.2,-1,.3),scene),shadows=new api.ShadowGenerator(128,sun);puffs.forEach(puff=>shadows.addShadowCaster(puff,false));
  const tower=api.MeshBuilder.CreateBox('city-tower',{width:30,height:120,depth:30},scene);tower.position.set(0,60,180);tower.computeWorldMatrix(true);
  // Babylon's shared default material is lazy engine state, not an ambient-owned resource.
  void scene.defaultMaterial;
  const baseline=counts(scene);
  const world=api.createAmbientWorld(scene,{cityCenterZ:180,cityBounds:{minX:-60,maxX:60,minZ:100,maxZ:260},now:()=>now});
  const step=time=>{now=time;scene.onBeforeRenderObservable.notifyObservers(scene);};
  const appearance=(hours,daylight,dawn=0)=>api.updateAmbientAppearance(scene,{hours,daylight,dawn,cloud:.15,direction:[.2,-1,.3]});
  try{await run({scene,camera,world,shadows,puffs,baseline,step,appearance,sky});}finally{world.dispose();scene.dispose();engine.dispose();globalThis.OffscreenCanvas=oldCanvas;}
}
test('ambient pools stay bounded across appearance changes and quality switches',()=>fixture(({scene,world,step,appearance})=>{
  const initial=counts(scene);world.setQuality({preset:'ultra',formFactor:'desktop'});appearance(14,1);step(0);
  assert.equal(world.diagnostics().activeBirds,24);assert.equal(world.diagnostics().visibleCards,6);assert.equal(world.diagnostics().legacyBallsVisible,0);
  for(let i=0;i<100;i++){appearance(i%24,i%2, .4);step(i*220);}
  assert.deepEqual(counts(scene),initial);
  world.setQuality({preset:'low',formFactor:'mobile'});appearance(14,1);step(23000);
  assert.equal(world.diagnostics().activeBirds,6);assert.equal(world.diagnostics().visibleCards,4);
}));
test('one weather sample drives sky key and night suppresses every bird',()=>fixture(({world,step,appearance})=>{
  appearance(14,1);step(0);const day=world.diagnostics().skyKey;assert.ok(world.diagnostics().activeBirds>0);
  appearance(18,.5,1);step(200);const dusk=world.diagnostics().skyKey;assert.notEqual(day,dusk);
  appearance(22,0);step(400);assert.equal(world.diagnostics().activeBirds,0);assert.notEqual(dusk,world.diagnostics().skyKey);
}));
test('flocks remain above city roof clearance and camera proximity hides nearby birds',()=>fixture(({scene,camera,world,step,appearance})=>{
  appearance(14,1);step(0);assert.equal(world.diagnostics().highestCity,120);
  const bird=scene.getTransformNodeByName('ambient-bird-0');assert.ok(bird.position.y>145);
  camera.position.copyFrom(bird.position);step(1);assert.equal(bird.isEnabled(),false);
}));
test('alpha-card cloud casters replace visible balls and teardown restores original resources',()=>fixture(async({scene,world,shadows,puffs,baseline,step,appearance})=>{
  appearance(14,1);step(0);assert.ok(puffs.every(puff=>!puff.isVisible));
  assert.ok(shadows.getShadowMap().renderList.some(mesh=>mesh.name.startsWith('ambient-cloud-shadow-')));
  world.dispose();world.dispose();await new Promise(resolve=>setTimeout(resolve,0));
  assert.ok(puffs.every(puff=>puff.isVisible));assert.ok(!shadows.getShadowMap().renderList.some(mesh=>mesh.name.startsWith('ambient-')));
  assert.deepEqual(counts(scene),baseline,JSON.stringify(scene.materials.map(material=>material.name)));
}));
test('ambient does not invent cloud shadow casters when the original cloud shadows are disabled',()=>fixture(({shadows,step,appearance})=>{
  shadows.getShadowMap().renderList.length=0;appearance(14,1);step(0);
  assert.equal(shadows.getShadowMap().renderList.length,0);
}));
