import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';
const bundled=await build({stdin:{contents:"export {captureResolvedWebGpuVfxFrame,validateResolvedVfxPixels} from './src/combat-vfx-demo';",resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'ts'},bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent',loader:{'.png':'empty','.glb':'empty','.svg':'empty'}});
const api=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
function fixture(){let callback,begin=0,end=0;const particles=[{updateSpeed:1/60}],scene={animationsEnabled:true,spritesEnabled:true,particleSystems:particles,onAfterRenderObservable:{addOnce(fn){callback=fn;return fn;},remove(fn){if(callback===fn)callback=null;}}};return {scene,particles,camera:{getScene:()=>scene},engine:{isWebGPU:true,beginFrame(){begin++;},endFrame(){end++;}},render(){callback?.();},counts:()=>({begin,end})};}
test('resolved WebGPU screenshot uses the actual camera postprocess target and restores frozen presentation',async()=>{
 const f=fixture(),png='data:image/png;base64,iVBORw0KGgo=';
 const result=await api.captureResolvedWebGpuVfxFrame(f.engine,f.camera,1920,1080,(...args)=>{
  assert.equal(args[0],f.engine);assert.equal(args[1],f.camera);assert.deepEqual(args[2],{width:1920,height:1080});assert.equal(args[5],1);assert.equal(args[6],false);assert.equal(args[7],undefined);
  const texture={};args[12](texture);assert.equal(texture.useCameraPostProcesses,true);assert.equal(f.scene.animationsEnabled,false);assert.equal(f.particles[0].updateSpeed,0);f.render();queueMicrotask(()=>args[3](png));
 });
 assert.equal(result,png);assert.deepEqual(f.counts(),{begin:1,end:1});assert.equal(f.scene.animationsEnabled,true);assert.equal(f.particles[0].updateSpeed,1/60);
});
test('screenshot timeout and invalid dimensions fail clearly and restore particle/animation state',async()=>{
 const f=fixture();await assert.rejects(api.captureResolvedWebGpuVfxFrame(f.engine,f.camera,1920,1080,(...args)=>args[15]()),/timed out/);assert.equal(f.scene.animationsEnabled,true);assert.equal(f.particles[0].updateSpeed,1/60);
 await assert.rejects(api.captureResolvedWebGpuVfxFrame(f.engine,f.camera,0,1080),/shape/);
});
test('blank or wrong-size output cannot become a false successful contact sheet',()=>{
 assert.throws(()=>api.validateResolvedVfxPixels(new Uint8ClampedArray(8),1,1),/dimensions/);assert.throws(()=>api.validateResolvedVfxPixels(new Uint8ClampedArray([0,0,0,255]),1,1),/blank/);
 assert.throws(()=>api.validateResolvedVfxPixels(new Uint8ClampedArray([12,34,56,0]),1,1),/blank/);assert.doesNotThrow(()=>api.validateResolvedVfxPixels(new Uint8ClampedArray([12,34,56,255]),1,1));
});
test('only WebGPU uses the resolved screenshot path; existing WebGL readback and metrics remain outside capture work',async()=>{
 const source=await readFile(new URL('../src/combat-vfx-demo.ts',import.meta.url),'utf8');assert.match(source,/if\(engine.isWebGPU\)\{[\s\S]*?captureResolvedWebGpuVfxFrame[\s\S]*?\}else\{\s*const read=await engine.readPixels\(0,0,canvas.width,canvas.height,true,true\)/);
 assert.doesNotMatch(source,/getPreferredCanvasFormat/);assert.match(source,/nativeCpu.push\(lastFrameCpu\)[\s\S]*?captureResolvedWebGpuVfxFrame/);
});
