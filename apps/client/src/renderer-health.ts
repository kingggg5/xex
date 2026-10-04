import type {AbstractEngine} from '@babylonjs/core/Engines/abstractEngine';
import type {WebGPUEngine} from '@babylonjs/core/Engines/webgpuEngine';
import {createRendererHealth,type RendererHealth,type RendererHealthTracker} from './renderer-health-policy.mjs';
const health=new WeakMap<AbstractEngine,RendererHealthTracker>();
export function getRendererHealth(engine:AbstractEngine):RendererHealth|null{return health.get(engine)?.snapshot()??null;}
export function reportRendererReadback(engine:AbstractEngine,rgba:Uint8Array,ready:boolean):RendererHealth|null{
 const tracker=health.get(engine);if(!tracker)return null;
 const state=tracker.readback(rgba,{ready,scope:'resolved-target'});publish(engine,state);return state;
}
function publish(engine:AbstractEngine,state:RendererHealth):void{
 let node=document.getElementById('renderer-health-data');
 if(!node){node=document.createElement('script');node.id='renderer-health-data';node.setAttribute('type','application/json');document.body.append(node);}
 node.textContent=JSON.stringify({schema:'xexoria.renderer-health/1',renderer:engine.isWebGPU?'WebGPU':'WebGL2',...state});
 window.dispatchEvent(new CustomEvent('aetherfield:renderer-health',{detail:state}));
}
/** SDK9.27.1 declares _device but exposes no public device-error accessor; isolate this adapter. */
export function installRendererHealth(engine:AbstractEngine):()=>void{
 if(health.has(engine))return ()=>{};
 const tracker=createRendererHealth();health.set(engine,tracker);let disposed=false;
 const device=engine.isWebGPU?(engine as WebGPUEngine)._device:null;
 const onError=(event:Event)=>{
  if(disposed||engine.isDisposed)return;
  const error=(event as GPUUncapturedErrorEvent).error;
  const kind=error?.constructor?.name??'GPUError',message=error?.message??'Uncaptured GPU error';
  const distinct=tracker.error(kind,message),state=tracker.snapshot();
  // Keep first distinct failures loud without logging hundreds of identical invalid command buffers.
  if(distinct)console.error('[renderer-invalid]',{kind,message:state.messages.at(-1)?.message,renderTimingsValid:false});
  if(distinct||state.gpuErrors<8||(state.gpuErrors&(state.gpuErrors-1))===0)publish(engine,state);
 };
 device?.addEventListener('uncapturederror',onError);
 publish(engine,tracker.snapshot());
 const dispose=()=>{if(disposed)return;disposed=true;device?.removeEventListener('uncapturederror',onError);tracker.dispose();if(health.get(engine)===tracker)health.delete(engine);};
 engine.onDisposeObservable.addOnce(dispose);return dispose;
}
