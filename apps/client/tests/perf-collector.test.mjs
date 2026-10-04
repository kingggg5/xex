import test from 'node:test';
import assert from 'node:assert/strict';
import {createPerfCollector,perfRequested} from '../src/perf/collector.mjs';
test('perf is off by default and ambiguous/other query values stay off',()=>{
 for(const value of ['', '?perf=0','?perf=true','?perf=1&perf=0'])assert.equal(perfRequested(value),false);assert.equal(perfRequested('?perf=1&fsr=1.7'),true);
});
test('exact rolling interval/cpu percentiles and actual rendered FPS use bounded retained samples',()=>{
 const m=createPerfCollector({capacity:30,warmupFrames:0});m.updateState({targetFps:30,renderer:'WebGL2'},0);
 for(let n=0;n<100;n++)m.recordFrame({timeMs:n*1000/30,frameId:n,cpuSceneMs:2,drawCalls:90,triangles:100000,particles:20});
 const s=m.compact(3400);assert.equal(s.frame.n,30);assert.equal(s.frame.p50,33.3);assert.equal(s.frame.p95,33.3);assert.equal(s.frame.actualFps,30);assert.equal(s.cpu.p95,2);assert.equal(s.gpu.status,'unavailable');assert.equal(s.gpu.p95,null);assert.equal(s.scene.triangles,100000);assert.equal(m.compact(7000).frame.status,'stale');assert.equal(m.compact(7000).frame.actualFps,null);
});
test('hidden gaps and duplicate rendered ids are omitted; focus exposure and context generations remain visible',()=>{
 const m=createPerfCollector({warmupFrames:0});m.recordFrame({timeMs:10,frameId:1});assert.equal(m.recordFrame({timeMs:12,frameId:1}),false);m.recordFrame({timeMs:20,frameId:2,focused:false});
 m.visibility(false,false,25);m.recordFrame({timeMs:2000,frameId:3,visible:false});m.visibility(true,true,2010);m.recordFrame({timeMs:2020,frameId:4,visible:true,focused:true});
 assert.equal(m.compact(2030).frame.n,1);assert.equal(m.compact(2030).discardedHiddenFrames,1);assert.equal(m.compact(2030).unfocusedFrames,1);
 m.context('lost',2040);m.context('restored',2050);m.recordFrame({timeMs:2060,frameId:1});const s=m.compact(2070);assert.equal(s.frame.n,0);assert.deepEqual([s.env.contextLost,s.env.contextRestored],[1,1]);
});
test('GPU accepts fresh async counter samples only, keeps main-pass scope and reports stale rather than CPU substitution',()=>{
 const m=createPerfCollector({warmupFrames:0});for(let n=0;n<4;n++)m.recordFrame({timeMs:10+n*10,frameId:n,cpuSceneMs:1,gpuScope:'main-pass',gpuMs:8,gpuSequence:1});
 let s=m.compact(50);assert.equal(s.gpu.n,1);assert.equal(s.gpu.p95,8);assert.equal(s.gpu.scope,'main-pass');assert.equal(s.gpu.status,'available');assert.equal(m.compact(3000).gpu.status,'stale');
 m.recordFrame({timeMs:3010,frameId:5,gpuScope:'unavailable',cpuSceneMs:9,gpuMs:null});s=m.compact(3020);assert.equal(s.gpu.n,0);assert.equal(s.gpu.p95,null);assert.equal(s.gpu.status,'unavailable');
});
test('minute15–20 captures use declared approximate bounded histograms; history/events/marks cannot grow indefinitely',()=>{
 const m=createPerfCollector({warmupFrames:0});for(let n=0;n<30;n++)m.recordFrame({timeMs:900000+n*1000/30,frameId:n,cpuSceneMs:1});
 const late=m.lateWindow();assert.equal(late.n,29);assert.equal(late.p95.approximate,true);assert.ok(late.p95.lowerMs<=1000/30&&late.p95.upperMs>=1000/30);
 for(let n=0;n<70;n++){m.recordFrame({timeMs:(n+20)*60000,frameId:n+100});m.mark('city',n*1000);m.visibility(true,true,n*1000);}
 const s=m.snapshot(6000000);assert.equal(s.history.length,60);assert.equal(s.marks.length,64);assert.equal(s.events.length,64);
});
test('cold/warm reset and invalid timings never synthesize fps or GPU values',()=>{
 const m=createPerfCollector({warmupFrames:2});m.recordFrame({timeMs:10,frameId:1,cpuSceneMs:3});m.recordFrame({timeMs:20,frameId:2,cpuSceneMs:3});assert.equal(m.compact(20).frame.actualFps,null);
 assert.equal(m.recordFrame({timeMs:NaN}),false);m.reset(100);assert.equal(m.compact(100).renderedFrames,0);assert.equal(m.compact(100).gpu.p95,null);
});
