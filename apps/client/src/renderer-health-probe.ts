import type {Scene} from '@babylonjs/core/scene';
import {RenderTargetTexture} from '@babylonjs/core/Materials/Textures/renderTargetTexture';
import {reportRendererReadback} from './renderer-health';
/** One explicit diagnostic readback, never a per-frame or default gameplay cost. */
export function installRendererHealthProbe(scene:Scene):void{
 const button=document.createElement('button');button.id='renderer-health-probe';button.type='button';button.textContent='Check renderer pixels';
 button.style.cssText='position:fixed;left:12px;bottom:12px;z-index:99999;padding:10px;pointer-events:auto';document.body.append(button);
 let disposed=false;
 const click=async()=>{
  if(disposed||button.disabled||!scene.activeCamera)return;
  button.disabled=true;button.textContent='Checking resolved pixels…';
	let target:RenderTargetTexture|null=null;
  try{
		target=new RenderTargetTexture('renderer-health-resolved-target',{width:64,height:36},scene,false,true);
		target.samples=1;target.activeCamera=scene.activeCamera;target.useCameraPostProcesses=true;
		target.renderList=scene.meshes.filter(mesh=>mesh.isEnabled()&&mesh.isVisible&&mesh.getTotalVertices()>0);
		scene.getEngine().beginFrame();target.render(true);scene.getEngine().endFrame();
		const pixels=await target.readPixels();
		if(disposed)return;
		if(!(pixels instanceof Uint8Array))throw new Error('Resolved RGBA8 pixels unavailable');
		const state=reportRendererReadback(scene.getEngine(),pixels,scene.getFrameId()>1);
   button.textContent=state?.status??'Output unverified';
  }catch(error){button.textContent='Output probe unavailable';console.error('[renderer-output-probe]',error instanceof Error?error.message:'Probe failed');}
	finally{target?.dispose();if(!disposed)button.disabled=false;}
 };
 button.addEventListener('click',click);
 scene.onDisposeObservable.addOnce(()=>{disposed=true;button.removeEventListener('click',click);button.remove();});
}
