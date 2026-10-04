/** Local, bounded rendered-frame telemetry. No DOM, clocks, network or hardware probing. */
const finite = value => typeof value === 'number' && Number.isFinite(value);
const number = (value, max = 1e12) => finite(value) && value >= 0 && value <= max ? value : null;
const short = value => typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g,' ').slice(0,160) : null;
const round = value => value === null ? null : Math.round(value * 10) / 10;
export function perfRequested(search) { try { const params=new URLSearchParams(search);return params.getAll('perf').length===1&&params.get('perf')==='1'; } catch {return false;} }

class Ring {
 constructor(size){this.data=new Float64Array(size);this.index=0;this.size=0;this.sum=0;}
 push(value){if(this.size===this.data.length)this.sum-=this.data[this.index];else this.size++;this.data[this.index]=value;this.sum+=value;this.index=(this.index+1)%this.data.length;}
 clear(){this.index=this.size=this.sum=0;}
 summary(){if(!this.size)return {n:0,p50:null,p95:null,p99:null,average:null};const values=Array.from(this.data.subarray(0,this.size)).sort((a,b)=>a-b);const q=p=>round(values[Math.max(0,Math.ceil(values.length*p)-1)]);return {n:this.size,p50:q(.5),p95:q(.95),p99:q(.99),average:round(this.sum/this.size)};}
}
// Minute history uses bounded histograms, not fabricated exact five-minute percentiles.
const BINS=711;
function bin(value){return value<=50?Math.max(0,Math.ceil(value*4)-1):value<=250?200+Math.ceil(value-50)-1:value<=1000?400+Math.ceil((value-250)/5)-1:value<=5000?550+Math.ceil((value-1000)/25)-1:710;}
function range(index){return index<200?[index/4,(index+1)/4]:index<400?[50+index-200,51+index-200]:index<550?[250+(index-400)*5,255+(index-400)*5]:index<710?[1000+(index-550)*25,1025+(index-550)*25]:[5000,null];}
function histQuantile(hist,total,p=.95){if(!total)return null;let count=0;for(let i=0;i<BINS;i++){count+=hist[i];if(count>=Math.ceil(total*p)){const [lower,upper]=range(i);return {lowerMs:lower,upperMs:upper,estimateMs:upper===null?null:round((lower+upper)/2),approximate:true};}}return null;}
function emptyMinute(){return {minute:-1,interval:new Uint32Array(BINS),cpu:new Uint32Array(BINS),gpu:new Uint32Array(BINS),frames:0,cpuN:0,gpuN:0,sum:0,unfocused:0,hidden:false,contextLost:false,mixedSettings:false,gpuScope:null,mixedGpuScope:false,cap:null,scale:null};}
export function createPerfCollector(options={}) {
 const capacity=Math.max(30,Math.min(2400,Math.floor(finite(options.capacity)?options.capacity:300))),warmupTarget=Math.max(0,Math.min(120,Math.floor(finite(options.warmupFrames)?options.warmupFrames:30)));
 const frames=new Ring(capacity),cpu=new Ring(capacity),gpu=new Ring(capacity),minutes=Array.from({length:60},emptyMinute);
 let start=number(options.startAtMs)??0,previous=null,lastRenderedAt=null,lastId=null,warmup=warmupTarget,totalFrames=0,discarded=0,unfocused=0,contextLost=0,contextRestored=0,lastGpuSequence=null,lastGpuAt=null;
 let visible=true,focused=true,surface={},gpuScope='unavailable',gpuReason='GPU timing was not supplied',marks=[],events=[],latest={drawCalls:null,triangles:null,particles:null,activeMeshes:null};
 function minuteAt(time){const index=Math.floor(Math.max(0,time-start)/60000),slot=minutes[index%60];if(slot.minute!==index){slot.interval.fill(0);slot.cpu.fill(0);slot.gpu.fill(0);Object.assign(slot,{minute:index,frames:0,cpuN:0,gpuN:0,sum:0,unfocused:0,hidden:false,contextLost:false,mixedSettings:false,gpuScope:null,mixedGpuScope:false,cap:number(surface.targetFps,1000),scale:number(surface.fsrScale,10)});}return slot;}
 function event(kind,time){events.push({kind,timeMs:round(Math.max(0,time-start))});if(events.length>64)events.shift();}
 function resetWindow(){frames.clear();cpu.clear();gpu.clear();previous=null;lastRenderedAt=null;lastId=null;lastGpuAt=null;lastGpuSequence=null;warmup=warmupTarget;}
 function recordFrame(value){
  if(!value||!finite(value.timeMs)||value.timeMs<start)return false;
  if(number(value.frameId)!==null&&value.frameId===lastId)return false;
  if(number(value.frameId)!==null)lastId=value.frameId;
  if(typeof value.visible==='boolean')visible=value.visible;if(typeof value.focused==='boolean')focused=value.focused;
  const slot=minuteAt(value.timeMs);
  if(!visible){discarded++;slot.hidden=true;previous=null;lastGpuSequence=value.gpuSequence??lastGpuSequence;return false;}
  totalFrames++;lastRenderedAt=value.timeMs;
  if(!focused){unfocused++;slot.unfocused++;}
  latest.drawCalls=number(value.drawCalls);latest.triangles=number(value.triangles);latest.particles=number(value.particles);latest.activeMeshes=number(value.activeMeshes);
  const scope=value.gpuScope==='frame'||value.gpuScope==='main-pass'?value.gpuScope:'unavailable';
  if(scope!==gpuScope){gpu.clear();lastGpuAt=null;lastGpuSequence=null;gpuScope=scope;}
  if(value.gpuReason!==gpuReason)gpuReason=short(value.gpuReason)??gpuReason;
  if(warmup>0){warmup--;previous=value.timeMs;lastGpuSequence=value.gpuSequence??lastGpuSequence;return false;}
  const elapsed=previous===null?null:value.timeMs-previous;previous=value.timeMs;
  if(elapsed!==null&&elapsed>0&&elapsed<=300000){frames.push(elapsed);slot.interval[bin(elapsed)]++;slot.frames++;slot.sum+=elapsed;}
  const work=number(value.cpuSceneMs,300000);if(work!==null){cpu.push(work);slot.cpu[bin(work)]++;slot.cpuN++;}
  const duration=number(value.gpuMs,300000),sequence=number(value.gpuSequence);
  if(scope!=='unavailable'&&duration!==null&&duration>0&&sequence!==null&&sequence!==lastGpuSequence){gpu.push(duration);lastGpuAt=value.timeMs;lastGpuSequence=sequence;slot.gpu[bin(duration)]++;slot.gpuN++;if(slot.gpuScope&&slot.gpuScope!==scope)slot.mixedGpuScope=true;slot.gpuScope=scope;}
  return true;
 }
 function updateState(value,time=0){
  if(!value||typeof value!=='object')return;
  const next={renderer:short(value.renderer),fallbackReason:short(value.fallbackReason),preset:short(value.preset),targetFps:number(value.targetFps,1000),rafHz:number(value.rafHz,1000),browserCap30:typeof value.browserCap30==='boolean'?value.browserCap30:null,dpr:number(value.dpr,16),renderWidth:number(value.renderWidth,32768),renderHeight:number(value.renderHeight,32768),outputWidth:number(value.outputWidth,32768),outputHeight:number(value.outputHeight,32768),cssWidth:number(value.cssWidth,32768),cssHeight:number(value.cssHeight,32768),hardwareScaling:number(value.hardwareScaling,32),fsrScale:number(value.fsrScale,10),fsrActive:typeof value.fsrActive==='boolean'?value.fsrActive:null,visible:typeof value.visible==='boolean'?value.visible:visible,focused:typeof value.focused==='boolean'?value.focused:focused};
  next.rendererHealth=['BLANK_RENDER','INVALID_RENDER','NONEMPTY_OUTPUT','UNVERIFIED'].includes(value.rendererHealth)?value.rendererHealth:null;
  if(surface.renderer&&next.renderer!==surface.renderer)resetWindow();
  const slot=minuteAt(time);if(surface.targetFps!==undefined&&(surface.targetFps!==next.targetFps||surface.fsrScale!==next.fsrScale||surface.renderWidth!==next.renderWidth||surface.renderHeight!==next.renderHeight||surface.renderer!==next.renderer))slot.mixedSettings=true;
  surface=next;visible=next.visible;focused=next.focused;
 }
 function visibility(isVisible,isFocused,time){visible=isVisible;focused=isFocused;if(!visible){previous=null;minuteAt(time).hidden=true;event('hidden',time);}else{previous=null;event('visible',time);}}
 function context(kind,time){if(kind==='lost'){contextLost++;minuteAt(time).contextLost=true;}else if(kind==='restored')contextRestored++;else return;resetWindow();event(`context-${kind}`,time);}
 function compact(now){const f=frames.summary(),c=cpu.summary(),g=gpu.summary();let age=lastGpuAt===null?null:Math.max(0,now-lastGpuAt),frameAge=lastRenderedAt===null?null:Math.max(0,now-lastRenderedAt);let missed=0,long=0,hitches=0;const budget=surface.targetFps?1000/surface.targetFps:null;for(let i=0;i<frames.size;i++){const ms=frames.data[i];if(budget!==null&&ms>budget*1.5)missed++;if(ms>100)long++;if(ms>250)hitches++;}
  const invalid=surface.rendererHealth==='BLANK_RENDER'||surface.rendererHealth==='INVALID_RENDER';
  if(invalid){f.n=0;f.p50=f.p95=f.p99=f.average=null;g.n=0;g.p50=g.p95=g.p99=g.average=null;frameAge=null;age=null;}
  return {elapsedMs:round(Math.max(0,now-start)),warmupRemaining:warmup,renderedFrames:totalFrames,discardedHiddenFrames:discarded,unfocusedFrames:unfocused,windowCapacity:capacity,frame:{...f,status:frameAge===null?'warming':!visible?'hidden':frameAge>2000?'stale':'available',freshAgeMs:round(frameAge),actualFps:visible&&frameAge!==null&&frameAge<=2000&&frames.size&&frames.sum>0?round(1000*frames.size/frames.sum):null,missedPercent:budget!==null&&frames.size?round(100*missed/frames.size):null,longFrames:long,hitches},cpu:c,gpu:{...g,scope:gpuScope,status:gpuScope==='unavailable'?'unavailable':age===null?'pending':age>2000?'stale':'available',freshAgeMs:round(age),reason:gpuReason},display:{...surface},scene:{...latest},env:{visible,focused,contextLost,contextRestored},limits:{frameScope:'Rendered callbacks only; hidden intervals excluded, focus exposure tracked. Percentiles retain historical samples when stale; FPS unavailable after a 2s gap.',cpuScope:'SceneInstrumentation frame counter or caller-declared scene.render wall time; never GPU time.',gpuScope:'Asynchronous samples; no claim of CPU/GPU per-frame pairing.',triangles:'Submitted index equivalents / 3 across render passes and instances; not unique visible triangles.',particles:'Accumulated rendered particle count; not necessarily unique live particles.',qualification:'Instrumentation only; no physical-phone/FPS/device acceptance.'}};
 }
 function history(){return minutes.filter(slot=>slot.minute>=0).sort((a,b)=>a.minute-b.minute).map(slot=>({minute:slot.minute,n:slot.frames,averageFps:slot.sum>0?round(1000*slot.frames/slot.sum):null,p95:histQuantile(slot.interval,slot.frames),cpuP95:histQuantile(slot.cpu,slot.cpuN),gpuP95:slot.mixedGpuScope?null:histQuantile(slot.gpu,slot.gpuN),gpuScope:slot.gpuScope,flags:{hidden:slot.hidden,unfocused:slot.unfocused,contextLost:slot.contextLost,mixedSettings:slot.mixedSettings,mixedGpuScope:slot.mixedGpuScope},cap:slot.cap,fsrScale:slot.scale}));}
 function lateWindow(){const hist=new Uint32Array(BINS);let n=0;for(const slot of minutes){if(slot.minute>=15&&slot.minute<20){for(let i=0;i<BINS;i++)hist[i]+=slot.interval[i];n+=slot.frames;}}return {rangeMinutes:[15,20],n,p95:histQuantile(hist,n),approximate:true};}
 function mark(label,time){const value=short(label);if(!value)return false;marks.push({timeMs:round(Math.max(0,time-start)),label:value.slice(0,64)});if(marks.length>64)marks.shift();return true;}
 function reset(time){start=number(time)??start;previous=null;lastRenderedAt=null;lastId=null;warmup=warmupTarget;totalFrames=discarded=unfocused=contextLost=contextRestored=0;frames.clear();cpu.clear();gpu.clear();lastGpuAt=lastGpuSequence=null;for(const slot of minutes)slot.minute=-1;marks=[];events=[];}
 return {recordFrame,updateState,visibility,context,compact,history,lateWindow,mark,reset,snapshot(now){return {schema:'xexoria.perf/1',...compact(now),history:history(),minutes15to20:lateWindow(),marks:marks.map(x=>({...x})),events:events.map(x=>({...x}))};}};
}
