import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const compiled=await build({stdin:{contents:`
export {NullEngine} from '@babylonjs/core/Engines/nullEngine';
export {Scene} from '@babylonjs/core/scene';
export {FreeCamera} from '@babylonjs/core/Cameras/freeCamera';
export {Vector3} from '@babylonjs/core/Maths/math.vector';
export {createCityLampPools} from './src/city-lamp-pools';
`,resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const api=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
test('city pools stage until reveal, follow existing daylight and release all owned resources',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);new api.FreeCamera('camera',new api.Vector3(0,2,160),scene);
 // Material compilation can lazily request the engine-owned default material.
 void scene.defaultMaterial;
 let daylight=0;const before={meshes:scene.meshes.length,textures:scene.textures.length,materials:scene.materials.length};
 const pools=api.createCityLampPools(scene,176,()=>.12,()=>({daylight,rain:0}));
 // NullEngine has no GPU upload; emulate only texture readiness for lifecycle checks.
 for(const texture of scene.textures){const internal=texture.getInternalTexture();if(internal)internal.isReady=true;}
 await pools.ready;
 assert.equal(pools.anchors.length,12);assert.equal(pools.mesh.isEnabled(),false);
 pools.reveal();assert.equal(pools.mesh.isEnabled(),true);assert.equal(pools.mesh.thinInstanceCount,12);
 assert.equal(pools.mesh.getTotalIndices()/3,2);assert.equal(scene.lights.length,0);
 assert.ok(pools.anchors.every(p=>Math.abs(Math.hypot(p.x,p.z-176)-24)<1e-7&&p.y===.12));
 daylight=1;pools.reveal();assert.equal(pools.mesh.isEnabled(),false);
 pools.dispose();pools.dispose();await new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(scene.meshes.length,before.meshes);assert.equal(scene.textures.length,before.textures);assert.equal(scene.materials.length,before.materials);
 scene.dispose();engine.dispose();
});
test('unsupported water and sharply stepped surroundings receive no floating light cards',async()=>{
 const engine=new api.NullEngine(),scene=new api.Scene(engine);new api.FreeCamera('camera',new api.Vector3(0,2,160),scene);
 const pools=api.createCityLampPools(scene,176,()=>null,()=>({daylight:0,rain:0}));await pools.ready;pools.reveal();
 assert.equal(pools.anchors.length,0);assert.equal(pools.mesh.isEnabled(),false);pools.dispose();scene.dispose();engine.dispose();
});
