import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
const output=await build({entryPoints:[fileURLToPath(new URL('../src/perf/controller.ts',import.meta.url))],bundle:true,write:false,format:'esm',platform:'node',logLevel:'silent'});
const {installPerfOverlay}=await import(`data:text/javascript;base64,${Buffer.from(output.outputFiles[0].text).toString('base64')}`);
test('off query performs no DOM, timer, source or hardware work',()=>{
 let called=0;assert.equal(installPerfOverlay({search:'',readState(){called++;throw new Error('should not run')}}),null);assert.equal(called,0);
});
class Element extends EventTarget {
 constructor(tag){super();this.tagName=tag;this.style={cssText:'',color:'',width:'',textAlign:''};this.children=[];this.textContent='';this.hidden=false;this.value='';this.attributes={};}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}
 setAttribute(name,value){this.attributes[name]=value;}
 remove(){this.removed=true;if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 focus(){this.focused=true;}
 select(){this.selected=true;}
}
function ports(){
 const keys=['window','document','navigator','devicePixelRatio','innerWidth','innerHeight'];const original=new Map(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 const doc=new EventTarget(),win=new EventTarget(),timers=new Map();let next=0;
 Object.assign(doc,{body:new Element('body'),visibilityState:'visible',hasFocus:()=>true,createElement:t=>new Element(t)});
 Object.assign(win,{setInterval:f=>{timers.set(++next,f);return next},clearInterval:id=>timers.delete(id)});
 const values={window:win,document:doc,navigator:{clipboard:undefined},devicePixelRatio:2,innerWidth:896,innerHeight:414};
 for(const key of keys)Object.defineProperty(globalThis,key,{configurable:true,writable:true,value:values[key]});
 return {doc,win,timers,restore(){for(const [key,descriptor] of original){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}};
}
function all(root){return [root,...root.children.flatMap(all)];}
test('actual panel controller keeps export local/bounded, default GPU label absent and clipboard fallback visible',()=>{
 const p=ports();let time=0,reads=0;try{
 const overlay=installPerfOverlay({search:'?perf=1',now:()=>time,warmupFrames:0,localGpuName:'must not auto-export',readState(){reads++;return {renderer:'WebGL2',targetFps:30,renderWidth:1054,renderHeight:487,outputWidth:1792,outputHeight:828,fsrActive:true,fsrScale:1.7}}});
 assert.equal(p.doc.body.children.length,1);assert.equal(reads,1);
 for(let n=0;n<40;n++)overlay.recordFrame({timeMs:n*1000/30,frameId:n,cpuSceneMs:2,gpuScope:'unavailable'});
 assert.equal(reads,1,'sampling never polls DOM/source per frame');time=1500;for(const f of p.timers.values())f();assert.equal(reads,2);
 const snapshot=overlay.snapshot();assert.equal(snapshot.device.localGpuName,null);assert.equal(snapshot.gpu.status,'unavailable');assert.equal(snapshot.display.dpr,2);assert.equal(snapshot.frame.actualFps,30);
 const json=overlay.exportJson();assert.ok(new TextEncoder().encode(json).byteLength<=131072);assert.equal(JSON.parse(json).schema,'xexoria.perf/1');
 const copy=all(p.doc.body).find(n=>n.textContent==='Copy JSON');copy.dispatchEvent(new Event('click'));const field=all(p.doc.body).find(n=>n.id==='perf-json');assert.equal(field.hidden,false);assert.equal(field.selected,true);assert.equal(JSON.parse(field.value).device.localGpuName,null);
 overlay.dispose();assert.equal(p.timers.size,0);assert.equal(p.doc.body.children.length,0);assert.equal(p.win.__xexPerf,undefined);
 }finally{p.restore();}
});
test('local API owns/restores only its global slot and context counts stay page-local',()=>{
 const p=ports();let time=0;try{const prior={snapshot(){return 'prior'}};p.win.__xexPerf=prior;const overlay=installPerfOverlay({search:'?perf=1',now:()=>time,readState:()=>({renderer:'WebGPU'})});time=500;overlay.contextLost();time=1500;overlay.contextRestored();assert.equal(overlay.snapshot().env.contextLost,1);assert.equal(overlay.snapshot().env.contextRestored,1);overlay.mark('city');assert.equal(overlay.snapshot().marks[0].label,'city');overlay.dispose();assert.equal(p.win.__xexPerf,prior);}finally{p.restore();}
});
