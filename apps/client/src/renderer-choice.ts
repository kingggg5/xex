import {Engine} from '@babylonjs/core/Engines/engine';
import type {AbstractEngine} from '@babylonjs/core/Engines/abstractEngine';
import type {WebGPUEngine} from '@babylonjs/core/Engines/webgpuEngine';
import {ensureAssetLoaders} from './asset-loader-registration';
import {rendererBootPolicy} from './renderer-boot-policy.mjs';
import {installAssetNetworkGuards,getWebGpuCompilerOptions} from './asset-codecs';
import {installManualRendererReset} from './renderer-manual-reset';
import {installRendererHealth} from './renderer-health';
import {rendererFailureReason} from './renderer-reset-policy.mjs';
export interface RendererChoice{engine:AbstractEngine;label:string;canvas:HTMLCanvasElement;fallbackReason:string|null;}
/** Renderer boot is independent of map modules, so model labs do not import the entire world. */
export async function createRenderer(canvas:HTMLCanvasElement):Promise<RendererChoice>{
 ensureAssetLoaders();installAssetNetworkGuards();
 const mobile=matchMedia('(pointer: coarse)').matches||/iPhone|iPad|Android/i.test(navigator.userAgent),policy=rendererBootPolicy(mobile,new URLSearchParams(location.search).get('renderer'));
 let activeCanvas=canvas,fallbackReason:string|null=null;
 if(policy.preferWebGpu&&!('gpu' in navigator)){fallbackReason='WebGPU API is unavailable in this browser context';console.warn('[renderer-fallback]',{requested:'WEBGPU',effective:'WEBGL2',reason:fallbackReason});}
 if(policy.preferWebGpu&&'gpu' in navigator){let candidate:WebGPUEngine|undefined;try{
  const {WebGPUEngine}=await import('@babylonjs/core/Engines/webgpuEngine');candidate=new WebGPUEngine(canvas,policy.webGpuOptions);const compilers=getWebGpuCompilerOptions();await candidate.initAsync(compilers.glslangOptions,compilers.twgslOptions);monitor(candidate);return{engine:candidate,label:'WEBGPU',canvas:activeCanvas,fallbackReason};
 }catch(error){fallbackReason=rendererFailureReason(error);console.error('[renderer-fallback]',{requested:'WEBGPU',effective:'WEBGL2',reason:fallbackReason});try{candidate?.dispose();}catch{}activeCanvas=canvas.cloneNode(false) as HTMLCanvasElement;activeCanvas.id=canvas.id;canvas.replaceWith(activeCanvas);}}
 const engine=new Engine(activeCanvas,policy.antialias,{disableWebGL2Support:false,adaptToDeviceRatio:true,powerPreference:policy.powerPreference,doNotHandleContextLost:policy.doNotHandleContextLost});
 if(!activeCanvas.getContext('webgl2')){engine.dispose();throw Error('This prototype requires WebGL2 when WebGPU is unavailable.');}
 monitor(engine);return{engine,label:'WEBGL2',canvas:activeCanvas,fallbackReason};
}
function monitor(engine:AbstractEngine){installManualRendererReset(engine);installRendererHealth(engine);}
