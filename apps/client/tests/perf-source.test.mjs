import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const bundle=await build({entryPoints:[fileURLToPath(new URL('../src/perf/babylon-source.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node',logLevel:'silent',plugins:[{name:'cpu-only-sdk-port',setup(builder){builder.onResolve({filter:/sceneInstrumentation$/},()=>({path:'instrument',namespace:'port'}));builder.onLoad({filter:/.*/,namespace:'port'},()=>({loader:'js',contents:`export class SceneInstrumentation { constructor(){this.frameTimeCounter={current:2,count:1};this.drawCallsCounter={current:50,count:1};globalThis.__perfInstrumentation=this;}dispose(){this.disposed=true;}}`}));}}]});
const {createBabylonPerfSource}=await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);
function scene(engine){return {getEngine:()=>engine,getFrameId:()=>1,getActiveIndices:()=>300,getActiveParticles:()=>12,getActiveMeshes:()=>({length:3}),onDisposeObservable:{addOnce:f=>f,remove(){}}};}
test('Babylon adapter borrows one primitive frame DTO and never enables/toggles shared GPU timing',()=>{
 const previous=globalThis.document;globalThis.document={visibilityState:'visible',hasFocus:()=>true};try{
 const counter={count:5,current:1000000};let captures=0;const engine={isWebGPU:false,webGLVersion:2,getCaps:()=>({timerQuery:true}),getGPUFrameTimeCounter:()=>counter,captureGPUFrameTime(){captures++},getRenderWidth:()=>1000,getRenderHeight:()=>500,getHardwareScalingLevel:()=>1,getClassName:()=> 'Engine'};
 const source=createBabylonPerfSource(scene(engine));const first=source.readFrame(100);assert.equal(first.gpuMs,null);counter.count=6;counter.current=2000000;const next=source.readFrame(110);assert.equal(next,first);assert.equal(next.gpuMs,2);assert.equal(next.triangles,100);assert.equal(source.readFrame(120).gpuMs,null);source.dispose();assert.equal(captures,0);assert.equal(globalThis.__perfInstrumentation.disposed,true);
 }finally{globalThis.document=previous;delete globalThis.__perfInstrumentation;}
});
test('Safari-like missing timers remain unavailable and WebGPU timing is explicitly main-pass only',()=>{
 const previous=globalThis.document;globalThis.document={visibilityState:'visible',hasFocus:()=>false};try{
 const base={getCaps:()=>({timerQuery:false}),getRenderWidth:()=>1000,getRenderHeight:()=>500,getHardwareScalingLevel:()=>1,getClassName:()=> 'Engine'};
 const no=createBabylonPerfSource(scene({...base,isWebGPU:false,webGLVersion:2}));assert.equal(no.readFrame(10).gpuScope,'unavailable');no.dispose();
 const counter={count:0,current:0},yes=createBabylonPerfSource(scene({...base,isWebGPU:true,enabledExtensions:['timestamp-query'],gpuTimeInFrameForMainPass:{counter}}));counter.count=1;counter.current=4000000;const row=yes.readFrame(20);assert.equal(row.gpuScope,'main-pass');assert.equal(row.gpuMs,4);assert.equal(row.focused,false);yes.dispose();
 }finally{globalThis.document=previous;delete globalThis.__perfInstrumentation;}
});
