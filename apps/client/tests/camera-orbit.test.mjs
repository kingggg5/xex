import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundle=await build({stdin:{contents:`
import {NullEngine} from '@babylonjs/core/Engines/nullEngine';import {Scene} from '@babylonjs/core/scene';
import {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera';import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {configure360Orbit} from './src/camera-orbit';export{NullEngine,Scene,ArcRotateCamera,Vector3,configure360Orbit};`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
class Media extends EventTarget {constructor(matches){super();this.matches=matches;}change(value){this.matches=value;this.dispatchEvent(new Event('change'));}}
function fixture(run){const engine=new api.NullEngine(),scene=new api.Scene(engine),camera=new api.ArcRotateCamera('orbit',0,1,13,api.Vector3.Zero(),scene),canvas=new EventTarget();
  camera.lowerAlphaLimit=-1;camera.upperAlphaLimit=1;camera.lowerBetaLimit=.72;camera.upperBetaLimit=1.25;
  const touch=new Media(false),reduced=new Media(false),dispose=api.configure360Orbit(camera,canvas,{touch,reducedMotion:reduced});
  try{run({scene,camera,canvas,touch,reduced,dispose});}finally{dispose();scene.dispose();engine.dispose();}
}
test('native orbit can cross both ends of a full turn while pitch stays bounded',()=>fixture(({scene,camera})=>{
  assert.equal(camera.lowerAlphaLimit,null);assert.equal(camera.upperAlphaLimit,null);
  for(const alpha of [-Math.PI*4-.2,Math.PI*4+.2]){camera.alpha=alpha;scene.render();assert.ok(Math.abs(camera.alpha-alpha)<1e-6);}
  camera.beta=0;scene.render();assert.equal(camera.beta,.72);
  camera.beta=2;scene.render();assert.equal(camera.beta,1.25);
}));
test('both mouse buttons and one-finger pointer input rotate, with no pan or keyboard conflict',()=>fixture(({camera,canvas})=>{
  for(const button of [0,2])assert.equal(camera.movement.input.resolveInteraction('pointer',{button}).interaction,'rotate');
  assert.equal(camera.movement.input.resolveInteraction('pointer',{button:0,modifiers:{ctrl:true}}).interaction,'rotate');
  assert.ok(!camera.movement.input.inputMap.some(entry=>entry.source==='keyboard'||entry.interaction==='pan'));
  assert.equal(camera.inputs.attached.keyboard,undefined);
  const pointers=camera.inputs.attached.pointers;
  assert.deepEqual(pointers.buttons,[0,2]);assert.equal(pointers.multiTouchPanning,false);assert.equal(pointers.pinchZoom,true);
  const event=new Event('contextmenu',{cancelable:true});canvas.dispatchEvent(event);assert.equal(event.defaultPrevented,true);
}));
test('mobile sensitivity, reduced-motion inertia and teardown respond to preferences',()=>fixture(({camera,canvas,touch,reduced,dispose})=>{
  assert.equal(camera.angularSensibilityX,750);touch.change(true);assert.equal(camera.angularSensibilityX,380);
  reduced.change(true);assert.equal(camera.inertia,0);reduced.change(false);assert.equal(camera.inertia,.82);
  dispose();dispose();touch.change(false);assert.equal(camera.angularSensibilityX,380);
  const event=new Event('contextmenu',{cancelable:true});canvas.dispatchEvent(event);assert.equal(event.defaultPrevented,false);
}));
